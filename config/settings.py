import re
from typing import List, Union
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables or .env file."""

    # Scheduling
    CHECK_INTERVAL_MINUTES: int = Field(default=120, description="Interval in minutes between crawl cycles")

    # Notifications - Discord
    DISCORD_WEBHOOK_URL: str = Field(default="", description="Discord Webhook URL")
    ENABLE_DISCORD: bool = Field(default=True, description="Enable Discord notifications")

    # Notifications - Telegram
    TELEGRAM_BOT_TOKEN: str = Field(default="", description="Telegram Bot API Token")
    TELEGRAM_CHAT_ID: str = Field(default="", description="Telegram Chat ID / Channel ID")
    ENABLE_TELEGRAM: bool = Field(default=True, description="Enable Telegram notifications")

    # Storage & Logging
    DATABASE_PATH: str = Field(default="data/jobs.db", description="Path to SQLite database file")
    LOG_DIR: str = Field(default="logs", description="Path to log directory")
    LOG_LEVEL: str = Field(default="INFO", description="Log level: DEBUG, INFO, WARNING, ERROR")

    # Crawler Toggles
    ENABLE_ITVIEC: bool = Field(default=True, description="Toggle ITviec crawler")
    ENABLE_TOPCV: bool = Field(default=True, description="Toggle TopCV crawler")
    ENABLE_JOBGO: bool = Field(default=True, description="Toggle JobsGO crawler")
    ENABLE_FACEBOOK: bool = Field(default=True, description="Toggle Facebook Group crawler")

    # Search Endpoints (Configurable via .env)
    ITVIEC_SEARCH_ENDPOINTS: Union[List[str], str] = Field(
        default_factory=lambda: [
            "https://itviec.com/it-jobs/java/ha-noi",
            "https://itviec.com/it-jobs/backend/ha-noi",
            "https://itviec.com/it-jobs/frontend/ha-noi",
            "https://itviec.com/it-jobs/devops/ha-noi",
        ],
        description="ITviec search endpoints",
    )
    TOPCV_SEARCH_ENDPOINTS: Union[List[str], str] = Field(
        default_factory=lambda: [
            "https://www.topcv.vn/tim-viec-lam-it-phan-mem-c10026?city=1&exp=0",
        ],
        description="TopCV search endpoints",
    )
    JOBGO_SEARCH_ENDPOINTS: Union[List[str], str] = Field(
        default_factory=lambda: [
            "https://jobsgo.vn/viec-lam-cong-nghe-thong-tin-tai-ha-noi.html",
        ],
        description="JobsGO search endpoints",
    )

    # Facebook Crawler Specifics
    FB_COOKIES_PATH: str = Field(default="cookies/cookies.json", description="Path to Facebook exported cookies JSON")
    FB_GROUP_URLS: Union[List[str], str] = Field(
        default_factory=lambda: [
            "https://www.facebook.com/groups/tuyendungitvietnam",
            "https://www.facebook.com/groups/vieclamit.hanoi",
        ],
        description="Facebook recruitment group URLs to scrape",
    )
    PLAYWRIGHT_HEADLESS: bool = Field(default=True, description="Run Playwright browser in headless mode")
    FB_USER_AGENT: str = Field(
        default="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        description="Fixed User-Agent for Facebook crawler to match exported cookies",
    )

    # Filter Engine Keywords (Configurable via .env)
    TECH_KEYWORDS: Union[List[str], str] = Field(
        default_factory=lambda: [
            "java",
        ],
        description="Required technical keywords (at least 1 match)",
    )
    LEVEL_KEYWORDS: Union[List[str], str] = Field(
        default_factory=lambda: [
            "intern",
        ],
        description="Required job level/rank keywords (at least 1 match)",
    )
    BLACKLIST_KEYWORDS: Union[List[str], str] = Field(
        default_factory=lambda: [
            "khóa học",
        ],
        description="Blacklisted keywords (instant rejection if any match)",
    )
    LOCATION_KEYWORDS: Union[List[str], str] = Field(
        default_factory=lambda: [
            "hà nội",
        ],
        description="Allowed location keywords for target city",
    )
    EXCLUDED_LOCATIONS: Union[List[str], str] = Field(
        default_factory=lambda: [
            "hcm",
        ],
        description="Excluded cities/provinces outside target location",
    )

    # Network & Retry settings
    REQUEST_TIMEOUT: int = Field(default=30, description="HTTP request timeout in seconds")
    MAX_RETRIES: int = Field(default=3, description="Maximum retry attempts on network error")

    @field_validator(
        "FB_GROUP_URLS",
        "ITVIEC_SEARCH_ENDPOINTS",
        "TOPCV_SEARCH_ENDPOINTS",
        "JOBGO_SEARCH_ENDPOINTS",
        "TECH_KEYWORDS",
        "LEVEL_KEYWORDS",
        "BLACKLIST_KEYWORDS",
        "LOCATION_KEYWORDS",
        "EXCLUDED_LOCATIONS",
        mode="before",
    )
    @classmethod
    def parse_delimited_list(cls, v):
        if isinstance(v, str):
            return [item.strip().rstrip(";") for item in re.split(r"[,;\n\r]+", v) if item.strip()]
        if isinstance(v, list):
            items = []
            for entry in v:
                for sub in re.split(r"[,;\n\r]+", str(entry)):
                    clean = sub.strip().rstrip(";")
                    if clean:
                        items.append(clean)
            return items
        return v

    @field_validator("FB_GROUP_URLS", mode="after")
    @classmethod
    def normalize_facebook_groups(cls, v):
        """Allows users to specify group ID/name only (e.g. 'internvietnam' or '123456') or full URLs."""
        normalized = []
        for item in v:
            clean = str(item).strip().rstrip("/;")
            if not clean:
                continue
            if clean.startswith("http://") or clean.startswith("https://"):
                normalized.append(clean)
            else:
                slug = clean.split("groups/")[-1].strip("/")
                normalized.append(f"https://www.facebook.com/groups/{slug}/")
        return normalized

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )


settings = Settings()
