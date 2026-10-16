import re
from typing import List, Set
from urllib.parse import urljoin
from bs4 import BeautifulSoup

from crawlers.base_crawler import BaseCrawler
from models.job import JobItem
from utils.logger import logger


class ITViecCrawler(BaseCrawler):
    """Crawler specialized for scraping Java & Backend job listings in Hanoi from ITViec."""

    BASE_URL = "https://itviec.com"
    SEARCH_ENDPOINTS = [
        "https://itviec.com/it-jobs/java/ha-noi",
        "https://itviec.com/it-jobs/backend/ha-noi",
    ]

    def __init__(self):
        super().__init__(name="ITViec")

    async def crawl(self) -> List[JobItem]:
        """Scrape configured ITviec endpoints and return normalized JobItem objects."""
        jobs: List[JobItem] = []
        seen_urls: Set[str] = set()

        for endpoint in self.SEARCH_ENDPOINTS:
            logger.info(f"[{self.name}] Crawling endpoint: {endpoint}")
            try:
                html = await self.fetch(endpoint, referer="https://itviec.com/")
                parsed_jobs = self._parse_html(html, endpoint)
                for job in parsed_jobs:
                    if job.url not in seen_urls:
                        seen_urls.add(job.url)
                        jobs.append(job)
                logger.info(
                    f"[{self.name}] Found {len(parsed_jobs)} jobs from {endpoint}"
                )
            except Exception as e:
                logger.error(f"[{self.name}] Error crawling {endpoint}: {e}")

        logger.info(f"[{self.name}] Total unique jobs collected: {len(jobs)}")
        return jobs

    def _parse_html(self, html_content: str, source_url: str) -> List[JobItem]:
        """Parse raw HTML and extract job cards."""
        soup = BeautifulSoup(html_content, "lxml")
        results: List[JobItem] = []

        # Find job card containers with multiple fallback selectors
        cards = soup.select("div.job-card")
        if not cards:
            cards = soup.select("div[data-job-id]")
        if not cards:
            cards = soup.select("div.search-page__jobs > div, div.job_item")
        if not cards:
            # Fallback for alternative layout
            cards = soup.find_all("div", class_=lambda c: c and "job-card" in c)

        for card in cards:
            try:
                # 1. Job Link & Title
                title_link = (
                    card.select_one("h3 a")
                    or card.select_one("h2 a")
                    or card.select_one("a.job-card__title")
                    or card.select_one("a[data-job-id]")
                    or card.find("a", href=re.compile(r"/it-jobs/"))
                )

                if not title_link:
                    continue

                raw_title = title_link.get_text(strip=True)
                relative_url = title_link.get("href", "").strip()
                job_url = urljoin(self.BASE_URL, relative_url)

                # Skip invalid or non-job links
                if not raw_title or "/it-jobs/" not in job_url:
                    continue

                # 2. Extract Job ID
                data_job_id = (
                    card.get("data-job-id")
                    or title_link.get("data-job-id")
                    or ""
                )
                if not data_job_id:
                    # Try extracting id from URL slug, e.g. /it-jobs/java-developer-company-1234
                    match = re.search(r"-(\d+)$", relative_url.rstrip("/"))
                    data_job_id = match.group(1) if match else job_url

                # 3. Company Name
                company_elem = (
                    card.select_one(".company-name")
                    or card.select_one(".job-card__company")
                    or card.select_one("a[href*='/companies/']")
                    or card.select_one(".employer-name")
                )
                company = company_elem.get_text(strip=True) if company_elem else "Không rõ công ty"

                # 4. Salary
                salary_elem = (
                    card.select_one(".salary")
                    or card.select_one(".job-card__salary")
                    or card.select_one(".salary-label")
                    or card.select_one("span.badge-salary")
                )
                salary = salary_elem.get_text(strip=True) if salary_elem else "Thỏa thuận"

                # 5. Location
                location_elem = (
                    card.select_one(".city")
                    or card.select_one(".job-card__location")
                    or card.select_one(".location")
                )
                location = location_elem.get_text(strip=True) if location_elem else "Hà Nội"

                # 6. Description / Tags preview
                tags = [
                    tag.get_text(strip=True)
                    for tag in card.select(".tag-list span, .itag, .badge, .job-card__tech-stack span")
                ]
                desc_elem = card.select_one(".job-card__description, .description, .job-desc")
                desc_text = desc_elem.get_text(strip=True) if desc_elem else ""
                full_description = f"{desc_text} {' '.join(tags)}"

                item = JobItem(
                    job_id=str(data_job_id),
                    title=raw_title,
                    company=company,
                    salary=salary,
                    location=location,
                    url=job_url,
                    source="ITviec",
                    description=full_description,
                )
                results.append(item)
            except Exception as ex:
                logger.debug(f"[{self.name}] Skipped parsing card due to error: {ex}")
                continue

        return results

