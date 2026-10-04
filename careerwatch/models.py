from dataclasses import dataclass, field


@dataclass
class Job:
    id: str
    title: str
    url: str
    location: str = ""
    posted: str = ""
    description: str = ""
    # filled in by the filter stage
    min_years: int | None = None
    skills: list[str] = field(default_factory=list)
