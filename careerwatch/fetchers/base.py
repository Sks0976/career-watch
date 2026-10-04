import time
from itertools import islice
from typing import Iterator

import httpx

from ..config import Company
from ..models import Job

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0 Safari/537.36"
)


def new_client() -> httpx.Client:
    return httpx.Client(timeout=40, follow_redirects=True, headers={"User-Agent": USER_AGENT})


class Fetcher:
    # False for sources that return every job in one call and ignore the search term
    searchable = True
    needs_browser = False

    def __init__(self, company: Company, client: httpx.Client):
        self.company = company
        self.client = client

    def search(self, term: str) -> Iterator[Job]:
        raise NotImplementedError

    def describe(self, job: Job) -> str:
        """Full job description (HTML or text); fetched only for new jobs that pass the cheap filters."""
        return job.description

    def fetch(self) -> list[Job]:
        terms = (self.company.search or [""]) if self.searchable else [""]
        jobs: dict[str, Job] = {}
        for term in terms:
            for job in islice(self.search(term), self.company.max_jobs):
                jobs.setdefault(job.id, job)
        return list(jobs.values())

    def request(self, method: str, url: str, **kwargs) -> httpx.Response:
        for attempt in range(3):
            try:
                response = self.client.request(method, url, **kwargs)
                if response.status_code not in (429, 500, 502, 503, 504):
                    response.raise_for_status()
                    return response
                error = httpx.HTTPStatusError(f"HTTP {response.status_code}", request=response.request, response=response)
            except httpx.TransportError as exc:
                error = exc
            if attempt < 2:
                time.sleep(3 * (attempt + 1))
        raise error
