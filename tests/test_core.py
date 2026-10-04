from datetime import date

import pytest

from careerwatch import config, filters, notify
from careerwatch.__main__ import check
from careerwatch.config import Company
from careerwatch.models import Job
from careerwatch.state import State


def company(**overrides):
    base = dict(name="Acme", title={"include": ["software engineer", "java", "c++"], "exclude": ["intern", "manager"]},
                locations=[], experience={"min_years": 2, "max_years": None},
                skills={"prefer": ["java", "c++"], "required": False})
    return Company(**{**base, **overrides})


@pytest.mark.parametrize("title,expected", [
    ("Software Engineer II", True),
    ("Senior Java Developer", True),
    ("C++ Developer", True),
    ("JavaScript Developer", False),
    ("Software Engineer Intern", False),
    ("Internal Tools Software Engineer", True),
    ("Manager, Software Engineering", False),
    ("Data Analyst", False),
])
def test_title_filter(title, expected):
    assert filters.title_ok(Job("1", title, "u"), company()) is expected


def test_location_filter():
    c = company(locations=["india", "bangalore"])
    assert filters.location_ok(Job("1", "t", "u", location="Bengaluru, Karnataka, India"), c)
    assert filters.location_ok(Job("1", "t", "u", location="IN KA BANGALORE Home Office"), c)
    assert not filters.location_ok(Job("1", "t", "u", location="Austin, TX, United States"), c)
    assert filters.location_ok(Job("1", "t", "u", location=""), c)


@pytest.mark.parametrize("text,expected", [
    ("Requires 3+ years of experience in Java", 3),
    ("2-4 years of relevant experience", 2),
    ("Minimum of 5 years experience building services", 5),
    ("Experience: 4 yrs or more", 4),
    ("<li>7 or more years of work experience</li>", 7),
    ("We have been in business for 40 years", None),
    ("No figure stated", None),
])
def test_required_years(text, expected):
    assert filters.required_years(filters.to_text(text)) == expected


def test_experience_and_skills():
    c = company()
    job = Job("1", "Software Engineer", "u", description="<p>1+ years of experience with C++ and Java&nbsp;</p>")
    filters.analyse(job, c)
    assert (job.min_years, job.skills) == (1, ["java", "c++"])
    assert not filters.detail_ok(job, c)

    unknown = Job("2", "Software Engineer", "u", description="Great team")
    filters.analyse(unknown, c)
    assert filters.detail_ok(unknown, c)
    assert not filters.detail_ok(unknown, company(skills={"prefer": ["java"], "required": True}))

    senior = Job("3", "Software Engineer", "u", description="8 years of experience with JavaScript")
    filters.analyse(senior, c)
    assert senior.skills == [] and filters.detail_ok(senior, c)
    assert not filters.detail_ok(senior, company(experience={"min_years": 2, "max_years": 5}))


class FakeFetcher:
    def __init__(self, jobs):
        self.jobs = jobs

    def fetch(self):
        return self.jobs

    def describe(self, job):
        return "3+ years of experience in Java"


def test_baseline_then_new(tmp_path):
    c, state = company(), State(tmp_path / "seen.json")
    first = [Job("1", "Software Engineer", "u1"), Job("2", "Data Analyst", "u2")]
    alerts, matching = check(c, FakeFetcher(first), state)
    assert (alerts, matching) == ([], 1)

    second = first + [Job("3", "Java Developer", "u3"), Job("4", "Software Engineer Intern", "u4")]
    alerts, _ = check(c, FakeFetcher(second), state)
    assert [j.id for j in alerts] == ["3"]
    assert (alerts[0].min_years, alerts[0].skills) == (3, ["java"])
    assert check(c, FakeFetcher(second), state)[0] == []


def test_empty_fetch_is_a_failure(tmp_path):
    with pytest.raises(RuntimeError):
        check(company(), FakeFetcher([]), State(tmp_path / "seen.json"))


def test_state_roundtrip_and_pruning(tmp_path):
    path = tmp_path / "state" / "seen.json"
    state = State(path)
    state.mark("Acme", ["old"], today=date(2026, 1, 1))
    state.mark("Acme", ["fresh"], today=date(2026, 3, 1))
    state.mark("Removed", ["x"], today=date(2026, 3, 1))
    assert state.record_result("Acme", ok=False) == 1
    assert state.record_result("Acme", ok=False) == 2
    state.save(["Acme"], today=date(2026, 3, 1))

    reloaded = State(path)
    assert reloaded.seen == {"Acme": {"fresh": "2026-03-01"}}
    assert reloaded.failures == {"Acme": 2}
    assert reloaded.record_result("Acme", ok=True) == 0


def test_messages_split_under_limit():
    lines = [notify.format_job(Job(str(i), f"Software Engineer <{i}>", f"https://x/{i}?a=1&b=2", "Pune")) for i in range(120)]
    messages = notify.build_messages([("Acme (120 new)", lines), ("Other", ["one"])])
    assert len(messages) > 1 and all(len(m) <= notify.LIMIT for m in messages)
    assert "&lt;0&gt;" in messages[0] and "a=1&amp;b=2" in messages[0]
    assert sum(m.count("•") for m in messages) == 120
    assert notify.build_messages([]) == []


def test_config_defaults_and_overrides(tmp_path):
    path = tmp_path / "companies.yaml"
    path.write_text(
        "defaults:\n  locations: [India]\n  experience: {min_years: 2}\n"
        "companies:\n  - name: A\n    url: https://a.wd5.myworkdayjobs.com/Ext/\n"
        "  - name: B\n    type: visa\n    locations: []\n    experience: {max_years: 5}\n",
        encoding="utf-8",
    )
    a, b = config.load(path)
    assert (a.url, a.locations, a.experience) == ("https://a.wd5.myworkdayjobs.com/Ext", ["India"], {"min_years": 2, "max_years": None})
    assert (b.locations, b.experience) == ([], {"min_years": 2, "max_years": 5})

    path.write_text("companies:\n  - name: A\n    urll: x\n", encoding="utf-8")
    with pytest.raises(ValueError):
        config.load(path)
