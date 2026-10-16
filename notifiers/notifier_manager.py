import asyncio
from typing import List
from config.settings import settings
from models.job import JobItem
from notifiers.discord_notifier import DiscordNotifier
from notifiers.telegram_notifier import TelegramNotifier
from utils.logger import logger


class NotifierManager:
    """Coordinates and broadcasts alerts across multiple notification channels."""

    def __init__(self):
        self.discord: DiscordNotifier | None = None
        self.telegram: TelegramNotifier | None = None

        if settings.ENABLE_DISCORD and settings.DISCORD_WEBHOOK_URL:
            self.discord = DiscordNotifier(settings.DISCORD_WEBHOOK_URL)
            logger.info("Discord Notifier is ENABLED.")
        else:
            logger.info("Discord Notifier is DISABLED or URL not provided.")

        if (
            settings.ENABLE_TELEGRAM
            and settings.TELEGRAM_BOT_TOKEN
            and settings.TELEGRAM_CHAT_ID
        ):
            self.telegram = TelegramNotifier(
                settings.TELEGRAM_BOT_TOKEN, settings.TELEGRAM_CHAT_ID
            )
            logger.info("Telegram Notifier is ENABLED.")
        else:
            logger.info("Telegram Notifier is DISABLED or Token/Chat ID not provided.")

    async def notify(self, job: JobItem) -> None:
        """
        Broadcast job alert concurrently to all active notification channels.
        Handles individual exceptions so a failure on Discord won't block Telegram.
        """
        tasks = []

        if self.discord:
            tasks.append(self.discord.send_job_alert(job))

        if self.telegram:
            tasks.append(self.telegram.send_job_alert(job))

        if not tasks:
            logger.warning(
                f"No notification channels enabled. Skipping alert for job: {job.title}"
            )
            return

        # Execute concurrently with return_exceptions=True
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for res in results:
            if isinstance(res, Exception):
                logger.error(f"Notification task error: {res}")

