import httpx

from ..config import Company
from .apis import Amazon, Eightfold, Greenhouse, Lever, Oracle, SmartRecruiters, Workday
from .base import Fetcher, new_client
from .generic import Generic
from .pages import Google, SuccessFactors, TalentBrew

TYPES: dict[str, type[Fetcher]] = {
    "workday": Workday,
    "oracle": Oracle,
    "greenhouse": Greenhouse,
    "lever": Lever,
    "talentbrew": TalentBrew,
    "successfactors": SuccessFactors,
    "smartrecruiters": SmartRecruiters,
    "eightfold": Eightfold,
    "amazon": Amazon,
    "google": Google,
    "generic": Generic,
}

# sources with a fixed address, so `url` can be left out
NO_URL = {"amazon", "google"}

# url fragments that identify a platform when no type is given
_HOSTS = {
    "myworkdayjobs.com": "workday",
    "oraclecloud.com": "oracle",
    "greenhouse.io": "greenhouse",
    "lever.co": "lever",
    "smartrecruiters.com": "smartrecruiters",
}


def detect(company: Company) -> str:
    if company.type:
        if company.type not in TYPES:
            raise ValueError(f"{company.name}: unknown type '{company.type}' (known: {', '.join(TYPES)})")
        return company.type
    return next((kind for host, kind in _HOSTS.items() if host in company.url), "generic")


def build(company: Company, client: httpx.Client) -> Fetcher:
    kind = detect(company)
    if kind not in NO_URL and not company.url:
        raise ValueError(f"{company.name}: 'url' is required")
    return TYPES[kind](company, client)
