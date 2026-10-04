from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULTS = {
    "search": ["software engineer"],
    "title": {"include": [], "exclude": []},
    "locations": [],
    "experience": {"min_years": None, "max_years": None},
    "skills": {"prefer": [], "required": False},
    "max_jobs": 1500,
}


@dataclass
class Company:
    name: str
    url: str = ""
    type: str = ""
    search: list[str] = field(default_factory=list)
    title: dict = field(default_factory=dict)
    locations: list[str] = field(default_factory=list)
    experience: dict = field(default_factory=dict)
    skills: dict = field(default_factory=dict)
    max_jobs: int = 1500
    # fetcher-specific settings (facets, selector, params, ...)
    options: dict = field(default_factory=dict)


def _merge(base, override):
    if isinstance(base, dict) and isinstance(override, dict):
        return {**base, **{k: _merge(base.get(k), v) for k, v in override.items()}}
    return base if override is None else override


def load(path: str | Path) -> list[Company]:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    defaults = _merge(DEFAULTS, raw.get("defaults") or {})
    companies, names = [], set()
    for i, entry in enumerate(raw.get("companies") or []):
        if not isinstance(entry, dict) or not entry.get("name"):
            raise ValueError(f"companies[{i}]: every entry needs a 'name'")
        name = str(entry["name"])
        if name in names:
            raise ValueError(f"duplicate company name: {name}")
        names.add(name)
        unknown = set(entry) - set(DEFAULTS) - {"name", "url", "type", "options"}
        if unknown:
            raise ValueError(f"{name}: unknown keys {sorted(unknown)}")
        merged = _merge(defaults, {k: v for k, v in entry.items() if k in DEFAULTS})
        companies.append(
            Company(name=name, url=str(entry.get("url") or "").rstrip("/"), type=str(entry.get("type") or ""),
                    options=entry.get("options") or {}, **merged)
        )
    if not companies:
        raise ValueError("no companies configured")
    return companies
