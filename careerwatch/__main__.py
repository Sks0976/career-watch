import argparse
import sys

from . import config, filters, notify
from .fetchers import build, detect, new_client
from .state import State

# descriptions are fetched one request per job, so cap how many a single run will look up
MAX_DESCRIPTIONS = 40
# consecutive failed runs before a warning is sent
WARN_AFTER = 3


def check(company, fetcher, state, list_only=False):
    """Returns (jobs to alert on, number of jobs passing the title/location filters)."""
    jobs = fetcher.fetch()
    if not jobs:
        raise RuntimeError("no jobs found on the page")
    candidates = [j for j in jobs if filters.title_ok(j, company) and filters.location_ok(j, company)]
    print(f"[{company.name}] {len(jobs)} fetched, {len(candidates)} pass title/location filters")
    if list_only:
        return candidates, len(candidates)
    alerts = []
    if not state.is_baseline(company.name):
        new = [j for j in candidates if state.is_new(company.name, j.id)]
        for i, job in enumerate(new):
            if i < MAX_DESCRIPTIONS:
                try:
                    job.description = fetcher.describe(job)
                except Exception as exc:  # a missing description only costs the experience/skill tags
                    print(f"[{company.name}] description failed for {job.id}: {exc}")
            filters.analyse(job, company)
        alerts = [j for j in new if filters.detail_ok(j, company)]
        alerts.sort(key=lambda j: not j.skills)
        print(f"[{company.name}] {len(new)} new, {len(alerts)} to alert")
    state.mark(company.name, [j.id for j in candidates])
    return alerts, len(candidates)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="careerwatch", description="Alert on new job postings.")
    parser.add_argument("--config", default="companies.yaml")
    parser.add_argument("--state", default="state/seen.json")
    parser.add_argument("--only", help="check a single company by name")
    parser.add_argument("--dry-run", action="store_true", help="print alerts; do not send or save state")
    parser.add_argument("--list", action="store_true", help="print every job passing the title/location filters")
    parser.add_argument("--needs-browser", action="store_true",
                        help="exit 0 if any company needs the headless browser, else 1")
    args = parser.parse_args(argv)

    companies = config.load(args.config)
    if args.needs_browser:
        return 0 if any(detect(c) == "generic" for c in companies) else 1
    selected = [c for c in companies if not args.only or c.name.lower() == args.only.lower()]
    if not selected:
        parser.error(f"no company named '{args.only}'")

    state = State(args.state)
    sections, tracking, warnings, failed = [], [], [], 0
    with new_client() as client:
        for company in selected:
            baseline = state.is_baseline(company.name)
            try:
                alerts, matching = check(company, build(company, client), state, list_only=args.list)
            except Exception as exc:
                failed += 1
                print(f"[{company.name}] FAILED: {exc!r}")
                if state.record_result(company.name, ok=False) == WARN_AFTER:
                    warnings.append(f"{company.name}: {WARN_AFTER} runs in a row failed ({str(exc)[:150]})")
                continue
            state.record_result(company.name, ok=True)
            if args.list:
                for job in alerts:
                    print(f"   {job.title}  |  {job.location}")
            elif baseline:
                tracking.append(f"{company.name}: {matching} open jobs match your filters")
            elif alerts:
                sections.append((f"{company.name} ({len(alerts)} new)", [notify.format_job(j) for j in alerts]))

    if args.list:
        return 0
    if tracking:
        sections.append(("Now tracking (alerts start with the next new posting)", tracking))
    if warnings:
        sections.append(("⚠️ Checks failing", warnings))
    notify.send(notify.build_messages(sections), dry_run=args.dry_run)
    if not args.dry_run:
        # saved only after a successful send, so a failed send is retried on the next run
        state.save([c.name for c in companies])
    return 1 if failed == len(selected) else 0


if __name__ == "__main__":
    sys.exit(main())
