"""Fetchers for job platforms that expose JSON endpoints."""
import html
import re
from typing import Iterator
from urllib.parse import quote, urlsplit

from ..models import Job
from .base import Fetcher


def with_country(location: str, country: str) -> str:
    if country.lower() in location.lower():
        return location
    return f"{location}, {country}" if location else country


class Workday(Fetcher):
    """url: https://<tenant>.<wdN>.myworkdayjobs.com/<site>   options: facets"""

    PAGE = 20  # the API rejects larger pages

    def _base(self) -> tuple[str, str]:
        parts = urlsplit(self.company.url)
        site = [p for p in parts.path.split("/") if p][-1]
        tenant = parts.netloc.split(".")[0]
        return f"https://{parts.netloc}/wday/cxs/{tenant}/{site}", f"https://{parts.netloc}/{site}"

    def _country_facet(self, api: str, term: str) -> dict:
        """Facet that limits results to `country`, read from the site's own filter list."""
        body = {"appliedFacets": {}, "limit": 1, "offset": 0, "searchText": term}
        facets = self.request("POST", f"{api}/jobs", json=body).json().get("facets") or []
        word = re.compile(rf"\b{re.escape(self.company.country)}\b", re.I)
        found: dict[str, list[str]] = {}

        def walk(items):
            for facet in items:
                for value in facet.get("values") or []:
                    if "facetParameter" in value:
                        walk([value])
                    elif word.search(value.get("descriptor", "")):
                        found.setdefault(facet["facetParameter"], []).append(value["id"])

        walk(facets)
        # a single value named exactly after the country beats a list of its cities
        for param, ids in found.items():
            if len(ids) == 1 and param.lower().endswith(("country", "hierarchy1")):
                return {param: ids}
        return dict([max(found.items(), key=lambda kv: len(kv[1]))]) if found else {}

    def search(self, term: str) -> Iterator[Job]:
        api, public = self._base()
        facets = self.company.options.get("facets")
        if facets is None and self.company.country:
            facets = self._country_facet(api, term)
        offset = 0
        while True:
            body = {"appliedFacets": facets or {}, "limit": self.PAGE, "offset": offset, "searchText": term}
            postings = self.request("POST", f"{api}/jobs", json=body).json().get("jobPostings") or []
            for p in postings:
                path = p.get("externalPath")
                if not path:
                    continue
                location = p.get("locationsText", "")
                if facets and not self.company.options.get("facets"):
                    # results are already limited to the country; "3 Locations" would otherwise fail the filter
                    location = with_country(location, self.company.country)
                yield Job(id=(p.get("bulletFields") or [path])[0], title=p.get("title", ""), url=public + path,
                          location=location, posted=p.get("postedOn", ""))
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

    def _page(self, term: str, offset: int, limit: int, finder: dict) -> dict:
        host, site = self._site()
        extra = "".join(f",{k}={v}" for k, v in finder.items())
        query = (f"findReqs;siteNumber={site},keyword={quote(chr(34) + term + chr(34))},limit={limit},"
                 f"offset={offset},sortBy=POSTING_DATES_DESC{extra}")
        url = (f"{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions?onlyData=true"
               f"&expand=requisitionList.secondaryLocations&finder={query}")
        return (self.request("GET", url).json().get("items") or [{}])[0]

    def search(self, term: str) -> Iterator[Job]:
        host, site = self._site()
        finder = self.company.options.get("finder")
        by_country = False
        if finder is None:
            finder = {}
            if self.company.country:
                facet = self._page(term, 0, 1, {}).get("locationsFacet") or []
                ids = [f["Id"] for f in facet if f.get("Name", "").lower() == self.company.country.lower()]
                if ids:
                    finder, by_country = {"selectedLocationsFacet": ids[0]}, True
        offset = 0
        while True:
            reqs = self._page(term, offset, self.PAGE, finder).get("requisitionList") or []
            for r in reqs:
                places = [r.get("PrimaryLocation") or ""] + [s.get("Name", "") for s in r.get("secondaryLocations") or []]
                location = "; ".join(p for p in places if p)
                yield Job(id=str(r["Id"]), title=r.get("Title", ""),
                          url=f"{host}/hcmUI/CandidateExperience/en/sites/{site}/job/{r['Id']}",
                          location=with_country(location, self.company.country) if by_country else location,
                          posted=r.get("PostedDate") or "")
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


class SmartRecruiters(Fetcher):
    """url: https://jobs.smartrecruiters.com/<company>"""

    PAGE = 100

    def _slug(self) -> str:
        return [p for p in urlsplit(self.company.url).path.split("/") if p][-1]

    def search(self, term: str) -> Iterator[Job]:
        slug, offset = self._slug(), 0
        while True:
            params = {"limit": self.PAGE, "offset": offset, "q": term}
            content = self.request("GET", f"https://api.smartrecruiters.com/v1/companies/{slug}/postings",
                                   params=params).json().get("content") or []
            for j in content:
                place = j.get("location") or {}
                yield Job(id=str(j["id"]), title=j.get("name", ""),
                          url=f"https://jobs.smartrecruiters.com/{slug}/{j['id']}",
                          location=", ".join(p for p in (place.get("city"), place.get("country", "").upper()) if p),
                          posted=(j.get("releasedDate") or "")[:10])
            if len(content) < self.PAGE:
                return
            offset += self.PAGE

    def describe(self, job: Job) -> str:
        url = f"https://api.smartrecruiters.com/v1/companies/{self._slug()}/postings/{job.id}"
        sections = (self.request("GET", url).json().get("jobAd") or {}).get("sections") or {}
        return " ".join((sections.get(k) or {}).get("text", "") for k in ("jobDescription", "qualifications"))


class Eightfold(Fetcher):
    """Eightfold career sites (Microsoft, Qualcomm, ...).   url: https://<careers host>   options: domain"""

    PAGE = 10  # fixed by the API

    def _domain(self) -> str:
        host = urlsplit(self.company.url).netloc
        return self.company.options.get("domain") or ".".join(host.split(".")[-2:])

    def search(self, term: str) -> Iterator[Job]:
        start = 0
        while True:
            params = {"domain": self._domain(), "query": term, "location": self.company.country, "start": start,
                      "sort_by": "timestamp"}
            data = self.request("GET", f"{self.company.url}/api/pcsx/search", params=params).json().get("data") or {}
            positions = data.get("positions") or []
            for p in positions:
                yield Job(id=str(p["id"]), title=p.get("name", ""), url=self.company.url + p.get("positionUrl", ""),
                          location="; ".join(p.get("locations") or []))
            start += len(positions)
            if not positions or start >= (data.get("count") or 0):
                return

    def describe(self, job: Job) -> str:
        params = {"position_id": job.id, "domain": self._domain(), "hl": "en"}
        data = self.request("GET", f"{self.company.url}/api/pcsx/position_details", params=params).json()
        return (data.get("data") or {}).get("jobDescription", "")


class Amazon(Fetcher):
    """amazon.jobs; no url needed.   options: country_code (ISO 3166 alpha-3, e.g. IND)"""

    PAGE = 100
    CODES = {"india": "IND", "united states": "USA", "united kingdom": "GBR", "canada": "CAN", "germany": "DEU",
             "ireland": "IRL", "singapore": "SGP"}

    def search(self, term: str) -> Iterator[Job]:
        code = self.company.options.get("country_code") or self.CODES.get(self.company.country.lower())
        offset = 0
        while True:
            params = {"base_query": term, "result_limit": self.PAGE, "offset": offset, "sort": "recent"}
            if code:
                params["normalized_country_code[]"] = code
            jobs = self.request("GET", "https://www.amazon.jobs/en/search.json", params=params).json().get("jobs") or []
            for j in jobs:
                yield Job(id=str(j["id_icims"]), title=j.get("title", ""), url="https://www.amazon.jobs" + j.get("job_path", ""),
                          location=j.get("normalized_location", ""), posted=j.get("posted_date", ""),
                          description=f"{j.get('description') or ''} {j.get('basic_qualifications') or ''}")
            if len(jobs) < self.PAGE:
                return
            offset += self.PAGE
