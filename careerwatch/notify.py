import html
import os

import httpx

from .models import Job

LIMIT = 4096


def format_job(job: Job) -> str:
    details = [job.location]
    if job.min_years is not None:
        details.append(f"{job.min_years}+ yrs")
    if job.skills:
        details.append(", ".join(job.skills))
    line = f'• <a href="{html.escape(job.url, quote=True)}">{html.escape(job.title)}</a>'
    details = " · ".join(html.escape(d) for d in details if d)
    return f"{line}\n   {details}" if details else line


def build_messages(sections: list[tuple[str, list[str]]]) -> list[str]:
    """Pack (heading, lines) sections into as few Telegram messages as possible."""
    messages, current = [], ""
    for heading, lines in sections:
        head = f"<b>{html.escape(heading)}</b>"
        first = True
        for line in lines:
            piece = (f"\n\n{head}\n" if first else "\n") + line
            if len(current) + len(piece) > LIMIT:
                messages.append(current)
                current, piece = "", f"{head} (cont.)\n{line}"
            current += piece
            first = False
    if current.strip():
        messages.append(current)
    return [m.strip() for m in messages]


def send(messages: list[str], dry_run: bool = False) -> None:
    token, chat_id = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not dry_run and not (token and chat_id):
        # failing here keeps the state unsaved, so nothing is marked as seen without being delivered
        raise RuntimeError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set (or use --dry-run)")
    if dry_run:
        for message in messages:
            print("-" * 60 + "\n" + message)
        return
    for message in messages:
        response = httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": message, "parse_mode": "HTML",
                  "link_preview_options": {"is_disabled": True}},
            timeout=30,
        )
        if response.status_code != 200:
            raise RuntimeError(f"Telegram send failed: {response.status_code} {response.text[:300]}")
