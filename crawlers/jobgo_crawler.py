import asyncio
import hashlib
from typing import List, Set
from playwright.async_api import async_playwright

from config.settings import settings
from models.job import JobItem
from utils.logger import logger
from utils.user_agents import get_random_user_agent


class JobGOCrawler:
    """
    Crawler specialized for scraping IT jobs in Hanoi from JobsGO.vn.
    Uses Playwright headless browser with image/font blocking to bypass bot protections on low-RAM VPS.
    """

    BASE_URL = "https://jobsgo.vn"

    def __init__(self):
        self.name = "JobsGO"
        self.headless = settings.PLAYWRIGHT_HEADLESS
        self.search_endpoints = (
            settings.JOBGO_SEARCH_ENDPOINTS
            if isinstance(settings.JOBGO_SEARCH_ENDPOINTS, list)
            else [settings.JOBGO_SEARCH_ENDPOINTS]
        )

    async def crawl(self) -> List[JobItem]:
        """Scrape configured JobsGO search endpoints using Playwright and return normalized JobItem objects."""
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
                viewport={"width": 1280, "height": 800},
                locale="vi-VN",
            )
            page = await context.new_page()

            # Block images, fonts, and media to save ~60% RAM and CPU on low-end VPS
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
                            await asyncio.sleep(2.0)
                            
                            cards_data = await page.evaluate(r'''() => {
                                const results = [];
                                const cards = document.querySelectorAll(".job-card, div[data-id]");
                                cards.forEach(card => {
                                    const titleElem = card.querySelector("h3.job-title a, a.job-title, a[href*='/viec-lam/']");
                                    if (!titleElem) return;
                                    
                                    let title = titleElem.getAttribute("title") || titleElem.innerText || "";
                                    title = title.replace(/^HOT\s*/i, "").replace(/^GẤP\s*/i, "").trim();
                                    
                                    let href = titleElem.href || "";
                                    if (href) href = href.split("?")[0];
                                    if (!href) return;
                                    
                                    const companyElem = card.querySelector("a.company-title, a[href*='/tuyen-dung/'], .company-name");
                                    const company = companyElem ? companyElem.innerText.trim() : "Không rõ công ty";
                                    
                                    let salary = "Thỏa thuận";
                                    let location = "Hà Nội";
                                    
                                    const metaDiv = card.querySelector(".text-primary.fw-semibold");
                                    if (metaDiv) {
                                        const spans = Array.from(metaDiv.querySelectorAll("span")).map(s => s.innerText.trim()).filter(s => s && s !== "|");
                                        if (spans.length >= 1) salary = spans[0];
                                        if (spans.length >= 2) location = spans[1];
                                    }
                                    
                                    const fullText = (card.innerText || "").replace(/\n+/g, " ").trim();
                                    
                                    results.push({
                                        title: title,
                                        company: company,
                                        salary: salary,
                                        location: location,
                                        url: href,
                                        description: fullText
                                    });
                                });
                                return results;
                            }''')

                            for item in cards_data:
                                url = item["url"]
                                if url in seen_urls:
                                    continue
                                seen_urls.add(url)

                                job_id = hashlib.md5(f"jobgo:{url}".encode("utf-8")).hexdigest()
                                job = JobItem(
                                    job_id=job_id,
                                    title=item["title"],
                                    company=item["company"],
                                    salary=item["salary"],
                                    location=item["location"],
                                    url=url,
                                    source="JobsGO",
                                    description=item["description"],
                                )
                                jobs.append(job)

                            logger.info(f"[{self.name}] Found {len(cards_data)} jobs from {endpoint}")
                        else:
                            status_code = response.status if response else "No response"
                            logger.warning(f"[{self.name}] Non-200 response ({status_code}) on {endpoint}")

                    except Exception as ge:
                        logger.error(f"[{self.name}] Error loading endpoint '{endpoint}': {ge}")

                    await asyncio.sleep(1.5)

            finally:
                try:
                    await page.close()
                except Exception:
                    pass
                try:
                    await browser.close()
                except Exception:
                    pass

        logger.info(f"[{self.name}] Total unique jobs collected: {len(jobs)}")
        return jobs

