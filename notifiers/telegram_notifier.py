import html
from datetime import datetime
import httpx
from models.job import JobItem
from utils.logger import logger


class TelegramNotifier:
    """Sends clean, structured HTML messages with inline buttons to a Telegram Chat/Channel."""

    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token.strip()
        self.chat_id = str(chat_id).strip()
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"

    @staticmethod
    def _escape_html(text: str) -> str:
        """Escape special HTML characters for Telegram HTML parse mode."""
        return html.escape(text or "")

    async def send_job_alert(self, job: JobItem) -> bool:
        """
        Send a formatted Telegram message with an inline button linking to the job post.
        Returns True on success, False otherwise.
        """
        if not self.bot_token or not self.chat_id:
            logger.warning("Telegram Bot Token or Chat ID is not configured.")
            return False

        safe_title = self._escape_html(job.title)
        safe_company = self._escape_html(job.company or "Không rõ công ty")
        safe_location = self._escape_html(job.location or "Hà Nội")
        safe_salary = self._escape_html(job.salary or "Thỏa thuận")
        safe_tags = self._escape_html(job.tags_formatted)
        now_str = datetime.now().strftime("%H:%M - %d/%m/%Y")

        message_text = (
            f"🔥 <b>[{job.source}] {safe_title}</b>\n\n"
            f"🏢 <b>Công ty:</b> {safe_company}\n"
            f"📍 <b>Địa điểm:</b> {safe_location}\n"
            f"💵 <b>Mức lương:</b> {safe_salary}\n"
            f"🏷️ <b>Từ khóa:</b> <code>{safe_tags}</code>\n\n"
            f"⏰ <i>Thời gian phát hiện: {now_str}</i>"
        )

        payload = {
            "chat_id": self.chat_id,
            "text": message_text,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
            "reply_markup": {
                "inline_keyboard": [
                    [
                        {
                            "text": "👉 Xem Chi Tiết Bài Viết",
                            "url": job.url,
                        }
                    ]
                ]
            },
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(self.api_url, json=payload)
                data = response.json()
                if response.status_code == 200 and data.get("ok"):
                    logger.info(f"[Telegram] Sent alert successfully: '{job.title}'")
                    return True
                else:
                    logger.error(
                        f"[Telegram] API Error: Status {response.status_code}, Response: {data}"
                    )
                    return False
        except Exception as e:
            logger.error(f"[Telegram] Exception occurred while sending alert: {e}")
            return False

