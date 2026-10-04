"""Fetchers for job platforms that expose JSON endpoints."""
import html
import re
from typing import Iterator
from urllib.parse import quote, urlsplit

from ..models import Job
from .base import Fetcher


class Workday(Fetcher):
    """url: https://<tenant>.<wdN>.myworkdayjobs.com/<site>   options: facets"""

    PAGE = 20  # the API rejects larger pages

    def _base(self) -> tuple[str, str]:
        parts = urlsplit(self.company.url)
        site = [p for p in parts.path.split("/") if p][-1]
        tenant = parts.netloc.split(".")[0]
        return f"https://{parts.netloc}/wday/cxs/{tenant}/{site}", f"https://{parts.netloc}/{site}"

    def search(self, term: str) -> Iterator[Job]:
        api, public = self._base()
        offset = 0
        while True:
            body = {"appliedFacets": self.company.options.get("facets") or {}, "limit": self.PAGE,
                    "offset": offset, "searchText": term}
            postings = self.request("POST", f"{api}/jobs", json=body).json().get("jobPostings") or []
            for p in postings:
                path = p.get("externalPath")
                if not path:
                    continue
                yield Job(id=(p.get("bulletFields") or [path])[0], title=p.get("title", ""), url=public + path,
                          location=p.get("locationsText", ""), posted=p.get("postedOn", ""))
            if len(postings) < self.PAGE:
                return
            offset += self.PAGE

    def describe(self, job: Job) -> str:
        api, public = self._base()
        info = self.request("GET", api + job.url[len(public):]).json().get("jobPostingInfo") or {}
        return info.get("jobDescription", "")


class Oracle(Fetcher):
    """url: https://<host>.oraclecloud.com/hcmUI/CandidateExperience/en/sites/<site>   options: finder"""

    PAGE = 200

    def _site(self) -> tuple[str, str]:
        parts = urlsplit(self.company.url)
        match = re.search(r"/sites/([^/]+)", parts.path)
        if not match:
            raise ValueError(f"{self.company.name}: Oracle url must contain /sites/<site>")
        return f"https://{parts.netloc}", match.group(1)

    def search(self, term: str) -> Iterator[Job]:
        host, site = self._site()
        extra = "".join(f",{k}={v}" for k, v in (self.company.options.get("finder") or {}).items())
        offset = 0
        while True:
            finder = (f"findReqs;siteNumber={site},keyword={quote(chr(34) + term + chr(34))},limit={self.PAGE},"
                      f"offset={offset},sortBy=POSTING_DATES_DESC{extra}")
            url = (f"{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions?onlyData=true"
                   f"&expand=requisitionList.secondaryLocations&finder={finder}")
            items = self.request("GET", url).json().get("items") or [{}]
            reqs = items[0].get("requisitionList") or []
            for r in reqs:
                places = [r.get("PrimaryLocation") or ""] + [s.get("Name", "") for s in r.get("secondaryLocations") or []]
                yield Job(id=str(r["Id"]), title=r.get("Title", ""),
                          url=f"{host}/hcmUI/CandidateExperience/en/sites/{site}/job/{r['Id']}",
                          location="; ".join(p for p in places if p), posted=r.get("PostedDate") or "")
            if len(reqs) < self.PAGE:
                return
            offset += self.PAGE

    def describe(self, job: Job) -> str:
        host, site = self._site()
        url = (f"{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails?expand=all&onlyData=true"
               f"&finder=ById;Id=%22{job.id}%22,siteNumber={site}")
        item = (self.request("GET", url).json().get("items") or [{}])[0]
        keys = ("ExternalDescriptionStr", "ExternalQualificationsStr", "ExternalResponsibilitiesStr")
        return " ".join(item.get(k) or "" for k in keys)


class Greenhouse(Fetcher):
    """url: https://boards.greenhouse.io/<board>"""

    searchable = False

    def search(self, term: str) -> Iterator[Job]:
        board = [p for p in urlsplit(self.company.url).path.split("/") if p][-1]
        url = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"
        for j in self.request("GET", url).json().get("jobs") or []:
            yield Job(id=str(j["id"]), title=j.get("title", ""), url=j.get("absolute_url", ""),
                      location=(j.get("location") or {}).get("name", ""), posted=(j.get("updated_at") or "")[:10],
                      description=html.unescape(j.get("content") or ""))


class Lever(Fetcher):
    """url: https://jobs.lever.co/<company>"""

    searchable = False

    def search(self, term: str) -> Iterator[Job]:
        slug = [p for p in urlsplit(self.company.url).path.split("/") if p][-1]
        for j in self.request("GET", f"https://api.lever.co/v0/postings/{slug}?mode=json").json():
            lists = " ".join(f"{l.get('text', '')} {l.get('content', '')}" for l in j.get("lists") or [])
            yield Job(id=str(j["id"]), title=j.get("text", ""), url=j.get("hostedUrl", ""),
                      location=(j.get("categories") or {}).get("location") or "",
                      description=f"{j.get('descriptionPlain') or ''} {lists}")
