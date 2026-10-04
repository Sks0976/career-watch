import json
from datetime import date, timedelta
from pathlib import Path

# ids not seen for this long are forgotten, which keeps the file from growing forever
RETENTION_DAYS = 45


class State:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        data = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}
        self.seen: dict[str, dict[str, str]] = data.get("seen", {})
        self.failures: dict[str, int] = data.get("failures", {})

    def is_baseline(self, company: str) -> bool:
        return company not in self.seen

    def is_new(self, company: str, job_id: str) -> bool:
        return job_id not in self.seen.get(company, {})

    def mark(self, company: str, job_ids, today: date | None = None) -> None:
        stamp = (today or date.today()).isoformat()
        self.seen.setdefault(company, {}).update({job_id: stamp for job_id in job_ids})

    def record_result(self, company: str, ok: bool) -> int:
        """Returns the number of consecutive failed runs for the company."""
        if ok:
            self.failures.pop(company, None)
            return 0
        self.failures[company] = self.failures.get(company, 0) + 1
        return self.failures[company]

    def save(self, companies: list[str], today: date | None = None) -> None:
        cutoff = ((today or date.today()) - timedelta(days=RETENTION_DAYS)).isoformat()
        seen = {
            name: {job_id: stamp for job_id, stamp in sorted(ids.items()) if stamp >= cutoff}
            for name, ids in sorted(self.seen.items())
            if name in companies
        }
        failures = {k: v for k, v in sorted(self.failures.items()) if k in companies}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"seen": seen, "failures": failures}, indent=1) + "\n", encoding="utf-8")
