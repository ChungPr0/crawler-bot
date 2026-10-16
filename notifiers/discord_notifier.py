from datetime import datetime
from typing import Optional
import httpx
from models.job import JobItem
from utils.logger import logger

# Source color palette (Hex integer format for Discord)
SOURCE_COLORS = {
    "itviec": 0x2ECC71,   # Emerald Green
    "topcv": 0xE67E22,    # TopCV Orange
    "facebook": 0x1877F2, # Facebook Blue
}
DEFAULT_COLOR = 0x3498DB   # Default Blue


class DiscordNotifier:
    """Sends rich embed notifications to a Discord Webhook channel."""

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url.strip()

    async def send_job_alert(self, job: JobItem) -> bool:
        """
        Build and post a Discord Rich Embed for the given job posting.
        Returns True on success, False otherwise.
        """
        if not self.webhook_url:
            logger.warning("Discord Webhook URL is not configured.")
            return False

        color = SOURCE_COLORS.get(job.source.lower(), DEFAULT_COLOR)

        embed = {
            "title": f"🔥 [{job.source}] {job.title}",
            "url": job.url,
            "color": color,
            "fields": [
                {
                    "name": "🏢 Công ty",
                    "value": job.company or "Không rõ công ty",
                    "inline": True,
                },
                {
                    "name": "💵 Mức lương",
                    "value": job.salary or "Thỏa thuận",
                    "inline": True,
                },
                {
                    "name": "📍 Địa điểm",
                    "value": job.location or "Hà Nội",
                    "inline": False,
                },
                {
                    "name": "🏷️ Keywords Bắt Trúng",
                    "value": f"`{job.tags_formatted}`",
                    "inline": False,
                },
            ],
            "footer": {
                "text": f"Hanoi IT Job Bot • {job.source}",
            },
            "timestamp": datetime.utcnow().isoformat(),
        }

        payload = {
            "username": "Hanoi IT Job Radar",
            "avatar_url": "https://cdn-icons-png.flaticon.com/512/3281/3281289.png",
            "embeds": [embed],
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(self.webhook_url, json=payload)
                if response.status_code in (200, 204):
                    logger.info(f"[Discord] Sent alert successfully: '{job.title}'")
                    return True
                else:
                    logger.error(
                        f"[Discord] Failed to send webhook. Status: {response.status_code}, Body: {response.text}"
                    )
                    return False
        except Exception as e:
            logger.error(f"[Discord] Exception occurred while sending alert: {e}")
            return False

