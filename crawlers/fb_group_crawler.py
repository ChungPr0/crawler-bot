import asyncio
import hashlib
import json
from pathlib import Path
from typing import List, Optional
from datetime import datetime
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from config.settings import settings
from models.job import JobItem
from utils.logger import logger
from utils.user_agents import get_random_user_agent


class FBGroupCrawler:
    """Crawler specialized for scraping IT Recruitment Facebook Groups using Playwright & saved cookies."""

    def __init__(self):
        self.name = "Facebook"
        self.cookies_path = Path(settings.FB_COOKIES_PATH)
        self.group_urls = (
            settings.FB_GROUP_URLS
            if isinstance(settings.FB_GROUP_URLS, list)
            else [settings.FB_GROUP_URLS]
        )
        self.headless = settings.PLAYWRIGHT_HEADLESS

    def _load_and_sanitize_cookies(self) -> List[dict]:
        """Load and sanitize cookie format for Playwright context."""
        if not self.cookies_path.exists():
            logger.warning(
                f"[{self.name}] Cookies file not found at '{self.cookies_path}'. "
                "Facebook crawl will proceed without login session (may have limited visibility)."
            )
            return []

        try:
            with open(self.cookies_path, "r", encoding="utf-8") as f:
                cookies = json.load(f)

            sanitized = []
            for c in cookies:
                cookie_dict = {
                    "name": c.get("name"),
                    "value": c.get("value"),
                    "domain": c.get("domain", ".facebook.com"),
                    "path": c.get("path", "/"),
                }
                # Sanitize sameSite for Playwright compatibility
                same_site = str(c.get("sameSite", "")).lower()
                if same_site in ("strict", "lax"):
                    cookie_dict["sameSite"] = same_site.capitalize()
                elif same_site == "none" or same_site == "no_restriction":
                    cookie_dict["sameSite"] = "None"
                    cookie_dict["secure"] = True

                if "expires" in c and isinstance(c["expires"], (int, float)):
                    cookie_dict["expires"] = float(c["expires"])

                sanitized.append(cookie_dict)

            logger.info(f"[{self.name}] Loaded {len(sanitized)} cookies successfully.")
            return sanitized
        except Exception as e:
            logger.error(f"[{self.name}] Error reading cookies file: {e}")
            return []

    async def crawl(self) -> List[JobItem]:
        """Launch Playwright browser, visit groups, and extract recent posts."""
        jobs: List[JobItem] = []
        cookies = self._load_and_sanitize_cookies()

        async with async_playwright() as p:
            # Launch Chromium with anti-bot and low-memory arguments for 1GB RAM VPS
            browser: Browser = await p.chromium.launch(
                headless=self.headless,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-extensions",
                    "--mute-audio",
                    "--js-flags=--max-old-space-size=256",
                    "--disable-blink-features=AutomationControlled",
                ],
            )

            context: BrowserContext = await browser.new_context(
                user_agent=get_random_user_agent(),
                viewport={"width": 1024, "height": 800},
                locale="vi-VN",
                timezone_id="Asia/Ho_Chi_Minh",
            )

            # Block heavy Facebook images, videos, and fonts to save ~60% RAM & CPU
            await context.route(
                "**/*",
                lambda route: route.abort()
                if route.request.resource_type in ("image", "media", "font")
                else route.continue_(),
            )

            # Apply cookies if available
            if cookies:
                try:
                    await context.add_cookies(cookies)
                except Exception as ex:
                    logger.warning(f"[{self.name}] Could not add some cookies: {ex}")

            try:
                for group_url in self.group_urls:
                    try:
                        group_jobs = await self._crawl_group(context, group_url.strip())
                        jobs.extend(group_jobs)
                        await asyncio.sleep(2.0)
                    except Exception as ge:
                        logger.error(f"[{self.name}] Error while processing group '{group_url}': {ge}")
            finally:
                try:
                    await context.close()
                except Exception:
                    pass
                try:
                    await browser.close()
                except Exception:
                    pass

        logger.info(f"[{self.name}] Total unique posts extracted: {len(jobs)}")
        return jobs

    async def _crawl_group(self, context: BrowserContext, group_url: str) -> List[JobItem]:
        """Navigate to a Facebook Group URL and extract the newest job posts."""
        logger.info(f"[{self.name}] Opening group: {group_url}")
        page: Page = await context.new_page()
        group_jobs: List[JobItem] = []

        try:
            # Navigate to group with timeout
            await page.goto(group_url, wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(3.5)

            # Scroll gently to trigger lazy rendering of recent posts
            for _ in range(2):
                await page.mouse.wheel(0, 800)
                await asyncio.sleep(2)

            # Expand 'Xem thêm' / 'See more' buttons to reveal full recruitment descriptions
            see_more_buttons = await page.query_selector_all(
                "div[role='button']:has-text('Xem thêm'), div[role='button']:has-text('See more')"
            )
            for btn in see_more_buttons[:6]:
                try:
                    await btn.click(timeout=1000)
                    await asyncio.sleep(0.3)
                except Exception:
                    pass

            # Target post message text elements
            text_divs = await page.query_selector_all("div[role='feed'] div[dir='auto'], div[role='article'] div[dir='auto']")
            logger.info(f"[{self.name}] Found {len(text_divs)} potential text blocks in {group_url}")

            seen_signatures = set()

            for elem in text_divs:
                try:
                    post_text = (await elem.inner_text()).strip()
                    if not post_text or len(post_text) < 45:
                        continue  # Skip short non-job UI texts

                    # Avoid parsing duplicates within the same group feed
                    sig = post_text[:70].lower()
                    if sig in seen_signatures:
                        continue
                    seen_signatures.add(sig)

                    # Derive a clean title from the first non-empty lines
                    lines = [line.strip() for line in post_text.split("\n") if line.strip()]
                    derived_title = lines[0] if lines else "Tuyển dụng IT Facebook Group"
                    if len(derived_title) > 90:
                        derived_title = derived_title[:87] + "..."

                    # Try to find link from nearby elements or parent article
                    text_hash = hashlib.md5(post_text[:120].encode("utf-8")).hexdigest()[:12]
                    post_url = f"{group_url.rstrip('/')}#post_{text_hash}"
                    post_id = hashlib.md5(f"fb:{post_url}".encode("utf-8")).hexdigest()

                    job = JobItem(
                        job_id=post_id,
                        title=derived_title,
                        company="Facebook IT Group",
                        salary="Thỏa thuận",
                        location="Hà Nội",
                        url=post_url,
                        source="Facebook",
                        description=post_text,
                    )
                    group_jobs.append(job)

                except Exception as ex:
                    logger.debug(f"[{self.name}] Error parsing individual post element: {ex}")
                    continue

        except Exception as e:
            logger.error(f"[{self.name}] Error crawling Facebook group '{group_url}': {e}")
        finally:
            await page.close()

        return group_jobs

