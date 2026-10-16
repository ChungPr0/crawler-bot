from abc import ABC, abstractmethod
from typing import Dict, List, Optional
import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)
import logging
from config.settings import settings
from models.job import JobItem
from utils.logger import logger
from utils.user_agents import get_browser_headers

# Standard logging adapter for tenacity
_tenacity_logger = logging.getLogger("tenacity")


class BaseCrawler(ABC):
    """Abstract base class for all web scrapers with automatic retry and UA rotation."""

    def __init__(self, name: str):
        self.name = name
        self.timeout = settings.REQUEST_TIMEOUT
        self.max_retries = settings.MAX_RETRIES

    def _get_headers(self, referer: str = "https://google.com/") -> Dict[str, str]:
        """Obtain fresh browser headers with rotating User-Agent."""
        return get_browser_headers(referer=referer)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1.5, min=2, max=10),
        retry=retry_if_exception_type((httpx.RequestError, httpx.TimeoutException, httpx.HTTPStatusError)),
        before_sleep=before_sleep_log(_tenacity_logger, logging.WARNING),
        reraise=True,
    )
    async def fetch(
        self,
        url: str,
        params: Optional[Dict[str, str]] = None,
        referer: str = "https://google.com/",
    ) -> str:
        """
        Fetch HTML content from a URL with automatic User-Agent spoofing and retry logic.
        """
        headers = self._get_headers(referer=referer)
        logger.debug(f"[{self.name}] Fetching {url} with UA: {headers['User-Agent'][:40]}...")

        async with httpx.AsyncClient(
            headers=headers,
            timeout=self.timeout,
            follow_redirects=True,
            verify=False,  # Avoid SSL issues on legacy proxies/VPS
        ) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.text

    @abstractmethod
    async def crawl(self) -> List[JobItem]:
        """Execute crawler run and return a list of extracted JobItem objects."""
        pass

