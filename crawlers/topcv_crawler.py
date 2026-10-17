import asyncio
import re
from typing import List, Set
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

from config.settings import settings
from models.job import JobItem
from utils.logger import logger
from utils.user_agents import get_random_user_agent


class TopCVCrawler:
    """
    Crawler specialized for scraping IT Fresher & Intern positions in Hanoi from TopCV.
    Uses Playwright headless browser to bypass Cloudflare WAF bot protection.
    """

    BASE_URL = "https://www.topcv.vn"
    SEARCH_ENDPOINTS = [
        # IT Phần mềm tại Hà Nội (city=1), Cấp bậc Thực tập & Chưa có kinh nghiệm (exp=0)
        "https://www.topcv.vn/tim-viec-lam-it-phan-mem-c10026?city=1&exp=0",
    ]

    def __init__(self):
        self.name = "TopCV"
        self.headless = settings.PLAYWRIGHT_HEADLESS
        self.search_endpoints = (
            settings.TOPCV_SEARCH_ENDPOINTS
            if isinstance(settings.TOPCV_SEARCH_ENDPOINTS, list)
            else [settings.TOPCV_SEARCH_ENDPOINTS]
        )

    async def crawl(self) -> List[JobItem]:
        """Scrape configured TopCV search endpoints using Playwright and return normalized JobItem objects."""
        jobs: List[JobItem] = []
        seen_urls: Set[str] = set()

        async with async_playwright() as p:
            browser = await p.chromium.launch(
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
            context = await browser.new_context(
                user_agent=get_random_user_agent(),
                viewport={"width": 1024, "height": 768},
                locale="vi-VN",
            )
            page = await context.new_page()

            # Block images, fonts, and media to save ~60% RAM on low-end VPS
            await page.route(
                "**/*",
                lambda route: route.abort()
                if route.request.resource_type in ("image", "media", "font")
                else route.continue_(),
            )

            try:
                for endpoint in self.search_endpoints:
                    logger.info(f"[{self.name}] Crawling endpoint via browser: {endpoint}")
                    try:
                        response = await page.goto(
                            endpoint,
                            wait_until="domcontentloaded",
                            timeout=35000,
                        )
                        if response and response.status == 200:
                            # Allow brief moment for JS rendering
                            await asyncio.sleep(1.5)
                            html = await page.content()
                            parsed_jobs = self._parse_html(html, endpoint)
                            for job in parsed_jobs:
                                if job.url not in seen_urls:
                                    seen_urls.add(job.url)
                                    jobs.append(job)
                            logger.info(
                                f"[{self.name}] Found {len(parsed_jobs)} jobs from {endpoint}"
                            )
                        else:
                            status = response.status if response else "Unknown"
                            logger.warning(f"[{self.name}] Unexpected response status {status} for {endpoint}")
                    except Exception as e:
                        logger.error(f"[{self.name}] Error crawling {endpoint}: {e}")
            finally:
                await page.close()
                await context.close()
                await browser.close()

        logger.info(f"[{self.name}] Total unique jobs collected: {len(jobs)}")
        return jobs

    def _parse_html(self, html_content: str, source_url: str) -> List[JobItem]:
        """Parse raw HTML and extract TopCV job items."""
        soup = BeautifulSoup(html_content, "lxml")
        results: List[JobItem] = []

        # Find job card containers with fallback selectors
        cards = soup.select(".job-item-2, .job-item-search-result, [data-box='box-job'], div.job-ta")
        if not cards:
            cards = soup.find_all("div", class_=lambda c: c and ("job-item" in c or "box-job" in c))

        for card in cards:
            try:
                # 1. Title & URL
                title_elem = (
                    card.select_one("h3.title a")
                    or card.select_one(".job-title a")
                    or card.select_one("a.job-item-2__title")
                    or card.select_one("a[data-job-id]")
                    or card.find("a", href=re.compile(r"/viec-lam/"))
                )

                if not title_elem:
                    continue

                raw_title = title_elem.get_text(strip=True)
                relative_url = title_elem.get("href", "").strip()
                job_url = urljoin(self.BASE_URL, relative_url)

                if not raw_title or "/viec-lam/" not in job_url:
                    continue

                # 2. Job ID
                job_id = (
                    card.get("data-job-id")
                    or card.get("data-job-position-id")
                    or title_elem.get("data-job-id")
                    or ""
                )
                if not job_id:
                    # Match /viec-lam/.../<id>.html
                    match = re.search(r"/(\d+)\.html", job_url)
                    job_id = match.group(1) if match else job_url

                # 3. Company Name
                company_elem = (
                    card.select_one("a.company")
                    or card.select_one(".company-name")
                    or card.select_one(".text-silver")
                    or card.select_one("span.company-title")
                )
                company = company_elem.get_text(strip=True) if company_elem else "Không rõ công ty"

                # 4. Salary
                salary_elem = (
                    card.select_one(".salary")
                    or card.select_one("span.text-salary")
                    or card.select_one(".salary-label")
                )
                salary = salary_elem.get_text(strip=True) if salary_elem else "Thỏa thuận"

                # 5. Location
                location_elem = (
                    card.select_one(".address")
                    or card.select_one(".location")
                    or card.select_one("span.city")
                )
                location = location_elem.get_text(strip=True) if location_elem else "Hà Nội"

                # 6. Description / Exp snippet
                desc_elem = card.select_one(".job-desc, .exp, .text-gray")
                desc_text = desc_elem.get_text(strip=True) if desc_elem else ""

                item = JobItem(
                    job_id=str(job_id),
                    title=raw_title,
                    company=company,
                    salary=salary,
                    location=location,
                    url=job_url,
                    source="TopCV",
                    description=desc_text,
                )
                results.append(item)
            except Exception as ex:
                logger.debug(f"[{self.name}] Skipped parsing card due to error: {ex}")
                continue

        return results
