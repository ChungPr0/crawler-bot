import asyncio
import hashlib
import json
import re
from pathlib import Path
from typing import List, Optional, Set
from datetime import datetime
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from config.settings import settings
from models.job import JobItem
from utils.logger import logger
from utils.user_agents import get_random_user_agent


class CookieAuthError(Exception):
    """Exception raised when Facebook rejects cookies or forces redirect to login/checkpoint."""
    pass


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
        self.user_agent = getattr(
            settings,
            "FB_USER_AGENT",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        )

    def _load_and_sanitize_cookies(self) -> List[dict]:
        """Load and sanitize cookie format for Playwright context."""
        if not self.cookies_path.exists():
            logger.warning(
                f"[{self.name}] ⚠️ Cookies file not found at '{self.cookies_path}'. "
                "Facebook crawl will proceed without login session (Facebook blocks unauthenticated access to groups)."
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
                elif same_site in ("none", "no_restriction"):
                    cookie_dict["sameSite"] = "None"
                    cookie_dict["secure"] = True

                # Support both 'expires' and 'expirationDate' (used by Cookie-Editor)
                expires_val = c.get("expires") or c.get("expirationDate")
                if expires_val and isinstance(expires_val, (int, float)):
                    cookie_dict["expires"] = float(expires_val)

                sanitized.append(cookie_dict)

            # Check presence of vital Facebook authentication cookies
            cookie_names = {c.get("name") for c in sanitized}
            has_auth = "c_user" in cookie_names and "xs" in cookie_names
            if not has_auth:
                logger.warning(
                    f"[{self.name}] ⚠️ Cookies file loaded, but missing essential session cookies ('c_user' or 'xs'). "
                    "Make sure you were fully logged in when exporting cookies!"
                )
            else:
                logger.info(f"[{self.name}] Loaded {len(sanitized)} cookies successfully (session cookies 'c_user' & 'xs' verified).")

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

            # Use consistent desktop User-Agent to avoid session invalidation
            context: BrowserContext = await browser.new_context(
                user_agent=self.user_agent,
                viewport={"width": 1280, "height": 900},
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
                seen_signatures: Set[str] = set()
                seen_urls: Set[str] = set()
                for group_url in self.group_urls:
                    try:
                        group_jobs = await self._crawl_group(
                            context, group_url.strip(), seen_signatures, seen_urls
                        )
                        jobs.extend(group_jobs)
                        await asyncio.sleep(2.0)
                    except CookieAuthError:
                        logger.error(f"[{self.name}] 🛑 Dừng quét các nhóm còn lại trong chu kỳ này do phiên đăng nhập đã hỏng (tiết kiệm CPU & RAM).")
                        break
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

    async def _crawl_group(
        self,
        context: BrowserContext,
        group_url: str,
        seen_signatures: Optional[Set[str]] = None,
        seen_urls: Optional[Set[str]] = None,
    ) -> List[JobItem]:
        """Navigate to a Facebook Group URL and extract the newest job posts."""
        if seen_signatures is None:
            seen_signatures = set()
        if seen_urls is None:
            seen_urls = set()
        # Force Facebook to display posts chronologically (Newest first) instead of "Most Relevant"
        if "sorting_setting=" not in group_url:
            delimiter = "&" if "?" in group_url else "?"
            target_url = f"{group_url.rstrip('/')}/{delimiter}sorting_setting=CHRONOLOGICAL"
        else:
            target_url = group_url

        logger.info(f"[{self.name}] Opening group: {target_url}")
        page: Page = await context.new_page()
        group_jobs: List[JobItem] = []

        try:
            # Navigate to group with timeout
            await page.goto(target_url, wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(3.5)

            current_url = page.url.lower()
            page_title = await page.title()
            logger.info(f"[{self.name}] Page landed: '{page_title}' | URL: {page.url}")

            # 1. Cookie & Session Health Check: Detect redirection to Login or Checkpoint
            is_checkpoint = "checkpoint" in current_url
            is_login_url = "/login" in current_url or "login.php" in current_url
            is_login_title = any(term in page_title.lower() for term in ["đăng nhập", "log in to facebook", "facebook – log in", "facebook - log in"])
            is_unavailable = any(term in page_title.lower() for term in ["không khả dụng", "isn't available", "not found"])

            if is_checkpoint:
                logger.error(
                    f"[{self.name}] ❌ TÀI KHOẢN BỊ CHECKPOINT! "
                    f"Facebook yêu cầu xác minh bảo mật. URL: {page.url} | Title: '{page_title}'. "
                    "Hãy đăng nhập nick này trên trình duyệt máy tính để xác minh rồi xuất lại cookie."
                )
                raise CookieAuthError("Account checkpointed")

            if is_login_url or is_login_title:
                logger.error(
                    f"[{self.name}] ❌ LỖI COOKIE: Facebook chuyển hướng về trang Đăng nhập! "
                    f"URL thực tế: {page.url} | Title: '{page_title}'. "
                    f"Cookie trong '{self.cookies_path}' đã hết hạn hoặc bị Facebook hủy phiên đăng nhập. "
                    "Vui lòng xuất lại cookie mới."
                )
                raise CookieAuthError("Cookie invalid or session expired")

            if is_unavailable:
                logger.warning(
                    f"[{self.name}] ⚠️ NHÓM KHÔNG TRUY CẬP ĐƯỢC: {group_url} | Title: '{page_title}'. "
                    "Nhóm có thể là nhóm riêng tư (cần tham gia nhóm bằng nick này trước) hoặc URL bị sai."
                )
                return []

            # Dismiss modal popup/dialog if Facebook displays "Xem thêm trên Facebook" overlay
            close_btn = await page.query_selector("div[aria-label='Đóng'], div[aria-label='Close']")
            if close_btn:
                try:
                    await close_btn.click(timeout=1000)
                    await asyncio.sleep(0.5)
                except Exception:
                    pass

            # Scroll to trigger lazy rendering of recent posts (expanded depth)
            for _ in range(4):
                await page.mouse.wheel(0, 1500)
                await asyncio.sleep(2.5)

            # Expand 'Xem thêm' / 'See more' buttons to reveal full recruitment descriptions
            see_more_buttons = await page.query_selector_all(
                "div[role='button']:has-text('Xem thêm'), div[role='button']:has-text('See more')"
            )
            for btn in see_more_buttons[:12]:
                try:
                    await btn.click(timeout=1000)
                    await asyncio.sleep(0.3)
                except Exception:
                    pass

            # Extract posts with both content AND exact direct permalinks via browser DOM evaluation
            extracted_posts = await page.evaluate(r'''() => {
                const results = [];
                const feed = document.querySelector("div[role='feed']");
                let postContainers = [];

                if (feed) {
                    // Only get direct children of the feed (each child is strictly ONE isolated post item)
                    postContainers = Array.from(feed.children);
                } else {
                    // Fallback if role='feed' is not found
                    postContainers = Array.from(document.querySelectorAll("div[role='article']"));
                }

                postContainers.forEach(container => {
                    // 1. Extract post text strictly within this post container
                    let postText = '';
                    const msgElem = container.querySelector("div[data-ad-preview='message'], div[data-ad-comet-preview='message']");
                    if (msgElem) {
                        postText = (msgElem.innerText || '').trim();
                    } else {
                        const dirElements = container.querySelectorAll("div[dir='auto']");
                        for (const d of dirElements) {
                            const t = (d.innerText || '').trim();
                            if (t.length >= 35) {
                                postText = t;
                                break;
                            }
                        }
                    }

                    if (!postText || postText.length < 35) return;

                    // Clean out inline "Xem thêm" / "See more" fragments from text
                    postText = postText.replace(/Xem thêm/g, '').replace(/See more/g, '').trim();
                    if (postText.length < 35) return;

                    // 2. Extract direct post permalink STRICTLY within this post container
                    // DO NOT traverse outside container into parent feed (prevents leaking links from other posts above)
                    let postUrl = '';
                    const links = Array.from(container.querySelectorAll("a[href]"));
                    for (const a of links) {
                        const href = a.href || '';
                        // Direct group post: /groups/.../posts/<id>/, /permalink/<id>/, or share link /share/p/<id>/
                        if (href.includes('/posts/') || href.includes('/permalink/') || href.includes('/share/p/') || href.includes('/share/g/')) {
                            postUrl = href.split('?')[0].split('&')[0].split('#')[0];
                            break;
                        }
                        if (href.includes('multi_permalinks=')) {
                            const match = href.match(/multi_permalinks=([0-9]+)/);
                            if (match) {
                                postUrl = `https://www.facebook.com/groups/permalink/${match[1]}/`;
                                break;
                            }
                        }
                        if (href.includes('story_fbid=')) {
                            const match = href.match(/story_fbid=([^&]+)/);
                            if (match) {
                                postUrl = `https://www.facebook.com/permalink.php?story_fbid=${match[1]}`;
                                break;
                            }
                        }
                        if (href.includes('set=gm.') || href.includes('set=pcb.')) {
                            const match = href.match(/set=(?:gm|pcb)\.([0-9]+)/);
                            if (match) {
                                postUrl = `https://www.facebook.com/groups/permalink/${match[1]}/`;
                                break;
                            }
                        }
                    }

                    // Only keep candidates that have their OWN direct post permalink inside their container
                    if (postUrl) {
                        results.push({
                            text: postText,
                            url: postUrl
                        });
                    }
                });
                return results;
            }''')

            logger.info(f"[{self.name}] Found {len(extracted_posts)} potential posts in {target_url}")

            # If 0 posts found, log visible page text snippet (0 disk/RAM overhead)
            if not extracted_posts:
                try:
                    body_text = (await page.inner_text("body"))[:150].replace("\n", " ").strip()
                except Exception:
                    body_text = "N/A"
                logger.warning(
                    f"[{self.name}] ⚠️ Đã mở trang ('{page_title}') nhưng tìm thấy 0 bài viết. "
                    f"Nội dung hiển thị trên trang: '{body_text}'"
                )

            for item in extracted_posts:
                try:
                    post_text = item.get("text", "").strip()
                    post_url = item.get("url", "").strip()

                    if not post_text or len(post_text) < 35:
                        continue  # Skip short non-job UI texts

                    if post_url and not post_url.endswith("/") and ("/posts/" in post_url or "/permalink/" in post_url or "/share/p/" in post_url):
                        post_url = f"{post_url}/"

                    # Discard candidate block if no valid direct post permalink was found
                    # (Strictly eliminates group headers, rules, 'About this group' cards from being sent with #post_...)
                    if not post_url:
                        logger.debug(f"[{self.name}] Discarded block without post permalink: '{post_text[:50]}...'")
                        continue

                    # Avoid duplicate posts by URL across all groups in this cycle
                    if post_url in seen_urls:
                        continue
                    seen_urls.add(post_url)

                    # Deduplicate by content signature across all groups in this cycle
                    # (Prevents recruiter cross-posting spam to multiple groups)
                    clean_sig = re.sub(r"[^\w\s]", "", post_text[:140].lower())
                    clean_sig = re.sub(r"\s+", " ", clean_sig).strip()
                    if clean_sig in seen_signatures:
                        logger.debug(f"[{self.name}] Duplicate content skipped across groups: '{post_text[:50]}...'")
                        continue
                    seen_signatures.add(clean_sig)

                    # Derive a clean title from the first non-empty lines
                    lines = [line.strip() for line in post_text.split("\n") if line.strip()]
                    derived_title = lines[0] if lines else "Tuyển dụng IT Facebook Group"
                    if len(derived_title) > 90:
                        derived_title = derived_title[:87] + "..."

                    # Deterministic post_id based on content signature (ensures cross-group and cross-cycle deduplication in SQLite)
                    post_id = hashlib.md5(f"fb:{clean_sig}".encode("utf-8")).hexdigest()

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

