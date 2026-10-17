import aiosqlite
from pathlib import Path
from typing import Optional
from models.job import JobItem
from utils.logger import logger


class JobRepository:
    """Async SQLite repository for persistent job tracking and deduplication."""

    def __init__(self, db_path: str = "data/jobs.db"):
        self.db_path = db_path
        # Ensure directory exists
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

    async def init_db(self) -> None:
        """Create jobs table and indexing if they do not already exist."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    company TEXT,
                    salary TEXT,
                    location TEXT,
                    url TEXT NOT NULL,
                    source TEXT NOT NULL,
                    matched_keywords TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_jobs_source ON jobs (source);"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs (created_at);"
            )
            await db.commit()
            logger.info(f"Database initialized successfully at {self.db_path}")

    async def is_job_exists(
        self, job_id: str, title: Optional[str] = None, company: Optional[str] = None
    ) -> bool:
        """Check whether a job already exists by job_id OR by identical (title, company)."""
        async with aiosqlite.connect(self.db_path) as db:
            # 1. Primary check by job_id
            async with db.execute(
                "SELECT 1 FROM jobs WHERE job_id = ? LIMIT 1;", (job_id,)
            ) as cursor:
                if await cursor.fetchone() is not None:
                    return True

            # 2. Secondary check by exact (title, company)
            if title and company:
                async with db.execute(
                    "SELECT 1 FROM jobs WHERE title = ? AND company = ? LIMIT 1;",
                    (title.strip(), company.strip()),
                ) as cursor:
                    if await cursor.fetchone() is not None:
                        return True

            return False

    async def save_job(self, job: JobItem) -> bool:
        """
        Insert a new job posting into SQLite.
        Returns True if inserted successfully, False if already exists (primary key conflict).
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    """
                    INSERT INTO jobs (
                        job_id, title, company, salary, location, url, source, matched_keywords, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        job.job_id,
                        job.title,
                        job.company,
                        job.salary,
                        job.location,
                        job.url,
                        job.source,
                        job.tags_formatted,
                        job.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                    ),
                )
                await db.commit()
                return True
        except aiosqlite.IntegrityError:
            logger.debug(f"Job ID {job.job_id} already exists in database (skipped insert).")
            return False
        except Exception as e:
            logger.error(f"Error saving job {job.job_id} to database: {e}")
            return False

    async def get_total_jobs_count(self) -> int:
        """Return total count of recorded jobs."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT COUNT(*) FROM jobs;") as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0

