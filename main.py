import asyncio
import gc
import signal
import sys
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from config.settings import settings
from crawlers import ITViecCrawler, TopCVCrawler, FBGroupCrawler
from database.repository import JobRepository
from filters.filter_engine import JobFilter
from notifiers.notifier_manager import NotifierManager
from utils.logger import setup_logger, logger


class JobAutomationEngine:
    """Master engine orchestrating Crawlers -> Filter Engine -> Database Deduplication -> Multi-channel Notifiers."""

    def __init__(self):
        # Configure logging
        setup_logger(log_dir=settings.LOG_DIR, log_level=settings.LOG_LEVEL)

        # Database repository
        self.repository = JobRepository(db_path=settings.DATABASE_PATH)

        # Multi-channel notification manager
        self.notifier = NotifierManager()

        # Register active crawlers
        self.crawlers = []
        if settings.ENABLE_ITVIEC:
            self.crawlers.append(ITViecCrawler())
        if settings.ENABLE_TOPCV:
            self.crawlers.append(TopCVCrawler())
        if settings.ENABLE_FACEBOOK:
            self.crawlers.append(FBGroupCrawler())

        self.scheduler = AsyncIOScheduler()
        self._is_running = True

    async def initialize(self) -> None:
        """Initialize database schema and infrastructure before starting execution."""
        logger.info("Initializing Hanoi IT Job Radar Engine...")
        await self.repository.init_db()
        total_existing = await self.repository.get_total_jobs_count()
        logger.info(
            f"Active crawlers: {[c.name for c in self.crawlers]} | "
            f"Database loaded with {total_existing} previously processed jobs."
        )

    async def execute_crawl_cycle(self) -> None:
        """Run a single end-to-end cycle: Crawl -> Filter -> Deduplicate -> Save & Notify."""
        cycle_start = datetime.now()
        logger.info(f"========== Starting Crawl Cycle at {cycle_start.strftime('%Y-%m-%d %H:%M:%S')} ==========")

        total_scraped = 0
        total_matched = 0
        total_new_notified = 0

        for crawler in self.crawlers:
            try:
                logger.info(f"--> [Crawler: {crawler.name}] Starting fetch...")
                jobs = await crawler.crawl()
                total_scraped += len(jobs)

                for job in jobs:
                    # 1. Filter evaluation
                    eval_result = JobFilter.evaluate(job)
                    if not eval_result.passed:
                        logger.debug(f"[{crawler.name}] Filter rejected '{job.title}': {eval_result.reason}")
                        continue

                    total_matched += 1
                    job.matched_tech = eval_result.matched_tech
                    job.matched_level = eval_result.matched_level
                    job.matched_location = eval_result.matched_location

                    # 2. Database Deduplication check
                    if await self.repository.is_job_exists(job.job_id):
                        logger.debug(f"[{crawler.name}] Duplicate job skipped: ID {job.job_id} ({job.title})")
                        continue

                    # 3. Save new job to SQLite
                    saved = await self.repository.save_job(job)
                    if not saved:
                        continue

                    # 4. Dispatch instant notifications
                    logger.info(f"🔥 [{crawler.name}] NEW TARGET JOB DETECTED: '{job.title}' at '{job.company}'")
                    await self.notifier.notify(job)
                    total_new_notified += 1

                    # Polite rate-limiting between webhook requests
                    await asyncio.sleep(0.8)

            except Exception as e:
                logger.error(f"Error during crawl cycle for crawler '{crawler.name}': {e}", exc_info=True)
            finally:
                # Immediately reclaim memory after each crawler completes (critical for 1GB RAM VPS)
                gc.collect()

        elapsed = (datetime.now() - cycle_start).total_seconds()
        logger.info(
            f"========== Crawl Cycle Finished in {elapsed:.1f}s | "
            f"Scraped: {total_scraped} | Matched Criteria: {total_matched} | "
            f"New & Notified: {total_new_notified} =========="
        )

    def start(self, run_once: bool = False) -> None:
        """Start the engine in either one-shot mode (--once) or continuous scheduler mode."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        if run_once:
            try:
                loop.run_until_complete(self._run_once())
            finally:
                loop.close()
            return

        # Setup graceful shutdown handlers
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, lambda: self._shutdown(sig))
            except NotImplementedError:
                pass

        try:
            loop.run_until_complete(self._run_loop())
        except (KeyboardInterrupt, SystemExit):
            logger.info("Application stopped by user signal.")
        finally:
            loop.close()

    async def _run_once(self) -> None:
        """Execute a single crawl cycle and exit immediately to free 100% RAM."""
        await self.initialize()
        logger.info("Running in ONE-SHOT mode (--once)...")
        await self.execute_crawl_cycle()
        logger.info("One-shot cycle finished. Exiting process to release all memory.")

    def _shutdown(self, sig):
        """Signal handler for graceful shutdown."""
        logger.info(f"Received exit signal ({sig.name}). Shutting down gracefully...")
        self._is_running = False
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    async def _run_loop(self) -> None:
        """Main async runner."""
        await self.initialize()

        # Run immediate first crawl on boot
        logger.info("Executing initial crawl on startup...")
        await self.execute_crawl_cycle()

        # Schedule recurring background jobs
        interval = settings.CHECK_INTERVAL_MINUTES
        logger.info(f"Setting up periodic scheduler: every {interval} minutes.")
        self.scheduler.add_job(
            self.execute_crawl_cycle,
            trigger=IntervalTrigger(minutes=interval),
            id="job_crawl_task",
            name="Periodic IT Job Scraping Task",
            replace_existing=True,
        )
        self.scheduler.start()

        # Keep alive
        try:
            while self._is_running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass


if __name__ == "__main__":
    is_once = "--once" in sys.argv
    engine = JobAutomationEngine()
    engine.start(run_once=is_once)

