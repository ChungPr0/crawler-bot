import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class JobItem:
    """Represents a normalized job posting across all crawlers."""
    title: str
    url: str
    source: str
    company: str = "Không rõ công ty"
    salary: str = "Thỏa thuận"
    location: str = "Hà Nội"
    description: str = ""
    job_id: str = ""
    matched_tech: List[str] = field(default_factory=list)
    matched_level: List[str] = field(default_factory=list)
    matched_location: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        """Ensure job_id is populated if not provided explicitly."""
        if not self.job_id:
            raw_id = f"{self.source.lower()}:{self.url.strip()}"
            self.job_id = hashlib.md5(raw_id.encode("utf-8")).hexdigest()

    @property
    def tags_formatted(self) -> str:
        """Format matched keywords into readable hashtags."""
        all_tags = []
        for tag in self.matched_tech + self.matched_level:
            clean_tag = tag.replace(" ", "").replace("-", "").capitalize()
            if f"#{clean_tag}" not in all_tags:
                all_tags.append(f"#{clean_tag}")
        return " ".join(all_tags) if all_tags else "#ITJob"

    def to_dict(self) -> dict:
        """Convert job item to standard dictionary for serialization/logging."""
        return {
            "job_id": self.job_id,
            "title": self.title,
            "company": self.company,
            "salary": self.salary,
            "location": self.location,
            "url": self.url,
            "source": self.source,
            "matched_keywords": self.tags_formatted,
            "created_at": self.created_at.isoformat(),
        }

