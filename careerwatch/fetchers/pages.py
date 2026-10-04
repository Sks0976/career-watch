"""Fetchers for job platforms that render results as server-side HTML."""
import re
from typing import Iterator
from urllib.parse import urljoin

from selectolax.lexbor import LexborHTMLParser

from ..models import Job
from .base import Fetcher


def _text(node) -> str:
    return node.text(strip=True) if node else ""


class TalentBrew(Fetcher):
    """Radancy/TalentBrew sites.   url: https://careers.<company>.com"""

    PAGE = 100

    def search(self, term: str) -> Iterator[Job]:
        page = 1
        while True:
            params = {"ActiveFacetID": 0, "CurrentPage": page, "RecordsPerPage": self.PAGE, "Keywords": term,
                      "SearchResultsModuleName": "Search Results", "SearchFiltersModuleName": "Search Filters",
                      "SortCriteria": 0, "SortDirection": 0, "SearchType": 5, "ResultsType": 0}
            response = self.request("GET", f"{self.company.url}/search-jobs/results", params=params,
                                    headers={"X-Requested-With": "XMLHttpRequest"})
            links = LexborHTMLParser(response.json().get("results") or "").css("a[data-job-id]")
            for a in links:
                yield Job(id=a.attributes["data-job-id"], title=_text(a.css_first("h2, h3")) or _text(a),
                          url=urljoin(self.company.url + "/", a.attributes.get("href", "")),
                          location=_text(a.css_first(".job-location")))
            if len(links) < self.PAGE:
                return
            page += 1

    def describe(self, job: Job) -> str:
        node = LexborHTMLParser(self.request("GET", job.url).text).css_first(".ats-description, .job-description")
        return node.html if node else ""


class SuccessFactors(Fetcher):
    """SAP SuccessFactors career sites.   url: https://careers.<company>.com/<site>   options: params"""

    PAGE = 25

    def search(self, term: str) -> Iterator[Job]:
        start = 0
        while True:
            params = {"q": term, "sortColumn": "referencedate", "sortDirection": "desc", "startrow": start,
                      **(self.company.options.get("params") or {})}
            rows = LexborHTMLParser(self.request("GET", f"{self.company.url}/search/", params=params).text).css("tr.data-row")
            for row in rows:
                a = row.css_first("a.jobTitle-link")
                href = a.attributes.get("href", "") if a else ""
                ids = re.findall(r"/(\d+)/?$", href)
                if not ids:
                    continue
                yield Job(id=ids[0], title=_text(a), url=urljoin(self.company.url, href),
                          location=_text(row.css_first("span.jobLocation")), posted=_text(row.css_first("span.jobDate")))
            if len(rows) < self.PAGE:
                return
            start += self.PAGE

    def describe(self, job: Job) -> str:
        node = LexborHTMLParser(self.request("GET", job.url).text).css_first("span.jobdescription")
        return node.html if node else ""
