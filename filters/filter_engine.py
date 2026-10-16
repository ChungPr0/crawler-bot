import re
from dataclasses import dataclass, field
from typing import List, Tuple
from config.settings import settings
from models.job import JobItem


@dataclass
class FilterResult:
    """Represents the evaluation result of a job posting against filter criteria."""
    passed: bool
    matched_tech: List[str] = field(default_factory=list)
    matched_level: List[str] = field(default_factory=list)
    matched_location: List[str] = field(default_factory=list)
    reason: str = ""


def _build_regex_patterns(keywords: List[str]) -> List[Tuple[str, re.Pattern]]:
    """
    Dynamically compile word-boundary regex patterns from a list of keywords configured in .env.
    Handles special cases like 'Java' (blocking 'JavaScript') and symbols like 'C#', 'C++', '.NET'.
    """
    compiled: List[Tuple[str, re.Pattern]] = []
    for raw_kw in keywords:
        kw = raw_kw.strip()
        if not kw:
            continue

        # Display label (capitalize nicely)
        label = kw.upper() if len(kw) <= 3 else kw.title()

        if kw.lower() == "java":
            pattern = re.compile(r"\bjava\b(?!script)", re.IGNORECASE)
        else:
            # Escape regex special chars and allow flexible whitespace
            escaped = re.escape(kw).replace(r"\ ", r"\s+")
            prefix = r"\b" if kw[0].isalnum() else r"(?<!\w)"
            suffix = r"\b" if kw[-1].isalnum() else r"(?!\w)"
            pattern = re.compile(f"{prefix}{escaped}{suffix}", re.IGNORECASE)

        compiled.append((label, pattern))
    return compiled


class JobFilter:
    """
    Intelligent filter engine reading dynamic keywords from .env (via settings):
    1. At least 1 technical keyword (TECH_KEYWORDS)
    2. At least 1 level keyword (LEVEL_KEYWORDS)
    3. ZERO blacklisted keywords (BLACKLIST_KEYWORDS)
    4. Location matching target city (LOCATION_KEYWORDS)
    """

    TECH_PATTERNS: List[Tuple[str, re.Pattern]] = _build_regex_patterns(settings.TECH_KEYWORDS)
    LEVEL_PATTERNS: List[Tuple[str, re.Pattern]] = _build_regex_patterns(settings.LEVEL_KEYWORDS)
    BLACKLIST_PATTERNS: List[Tuple[str, re.Pattern]] = _build_regex_patterns(settings.BLACKLIST_KEYWORDS)
    LOCATION_KEYWORDS: List[str] = [loc.lower().strip() for loc in settings.LOCATION_KEYWORDS if loc.strip()]
    EXCLUDED_LOCATIONS: List[str] = [loc.lower().strip() for loc in settings.EXCLUDED_LOCATIONS if loc.strip()]

    @classmethod
    def evaluate(cls, job: JobItem) -> FilterResult:
        """
        Evaluate a JobItem against all configured filter criteria.
        Returns a FilterResult with passed boolean, matched tags, and evaluation details.
        """
        full_text = f"{job.title} {job.description} {job.location}".strip()
        search_target = full_text.lower()

        # Step 1: Check Blacklist (Instant discard)
        for label, pattern in cls.BLACKLIST_PATTERNS:
            if pattern.search(full_text):
                return FilterResult(
                    passed=False,
                    reason=f"Chứa từ khóa Blacklist: '{label}'"
                )

        # Step 2: Check Location
        matched_locations = []
        for loc in cls.LOCATION_KEYWORDS:
            if loc in search_target:
                matched_locations.append(loc.title())

        # Check if job explicitly mentions an excluded city without mentioning target location
        has_excluded_city = any(city in search_target for city in cls.EXCLUDED_LOCATIONS)
        if has_excluded_city and not matched_locations:
            return FilterResult(
                passed=False,
                reason="Địa điểm không thuộc khu vực mục tiêu (thuộc tỉnh/thành phố khác)"
            )

        if not matched_locations:
            if "hà nội" in job.location.lower() or "ha noi" in job.location.lower() or not job.location:
                matched_locations.append("Hà Nội (Mặc định)")
            else:
                return FilterResult(
                    passed=False,
                    reason="Không tìm thấy thông tin địa điểm phù hợp"
                )

        # Step 3: Match Technical Keywords (At least 1 required)
        matched_tech = []
        for label, pattern in cls.TECH_PATTERNS:
            if pattern.search(full_text):
                if label not in matched_tech:
                    matched_tech.append(label)

        if not matched_tech:
            return FilterResult(
                passed=False,
                reason="Không tìm thấy từ khóa chuyên môn yêu cầu (TECH_KEYWORDS)"
            )

        # Step 4: Match Level/Rank Keywords (At least 1 required)
        matched_level = []
        for label, pattern in cls.LEVEL_PATTERNS:
            if pattern.search(full_text):
                if label not in matched_level:
                    matched_level.append(label)

        if not matched_level:
            return FilterResult(
                passed=False,
                reason="Không tìm thấy từ khóa cấp bậc yêu cầu (LEVEL_KEYWORDS)"
            )

        # All conditions satisfied!
        return FilterResult(
            passed=True,
            matched_tech=matched_tech,
            matched_level=matched_level,
            matched_location=matched_locations,
            reason="Thỏa mãn tất cả tiêu chí lọc"
        )
