import html
import re

from .config import Company
from .models import Job

_TAG = re.compile(r"<[^>]+>")
# "3+ years", "2-4 yrs", "5 or more years", "minimum of 3 years"
_YEARS = re.compile(
    r"(\d{1,2})\s*(?:\+|or more|plus)?\s*(?:(?:-|–|—|to)\s*\d{1,2}\s*\+?\s*)?(?:years?|yrs?)\b", re.I
)


def to_text(markup: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(_TAG.sub(" ", markup or ""))).strip()


def _term(term: str) -> re.Pattern:
    # word-ish boundaries that also work for terms like "c++" or ".net"
    return re.compile(rf"(?<![\w+#]){re.escape(term.strip())}(?![\w+#])", re.I)


def matches_any(text: str, terms: list[str]) -> bool:
    return any(_term(t).search(text) for t in terms)


def title_ok(job: Job, company: Company) -> bool:
    include, exclude = company.title.get("include") or [], company.title.get("exclude") or []
    if include and not matches_any(job.title, include):
        return False
    return not matches_any(job.title, exclude)


def location_ok(job: Job, company: Company) -> bool:
    # jobs with no location information are kept rather than silently dropped
    if not company.locations or not job.location:
        return True
    return any(loc.lower() in job.location.lower() for loc in company.locations)


def required_years(text: str) -> int | None:
    """Years of experience asked for: the first figure stated next to the word 'experience'."""
    for m in _YEARS.finditer(text):
        window = text[max(0, m.start() - 60): m.end() + 80].lower()
        if "experience" in window and int(m.group(1)) <= 25:
            return int(m.group(1))
    return None


def analyse(job: Job, company: Company) -> None:
    text = f"{job.title} {to_text(job.description)}"
    job.min_years = required_years(text)
    job.skills = [s for s in company.skills.get("prefer") or [] if _term(s).search(text)]


def detail_ok(job: Job, company: Company) -> bool:
    """Experience and skill checks; jobs whose requirement is unknown are kept."""
    lo, hi = company.experience.get("min_years"), company.experience.get("max_years")
    if job.min_years is not None:
        if lo is not None and job.min_years < lo:
            return False
        if hi is not None and job.min_years > hi:
            return False
    if company.skills.get("required") and company.skills.get("prefer") and not job.skills:
        return False
    return True
