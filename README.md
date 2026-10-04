# career-watch

Checks company career pages on a schedule and sends a Telegram message when a
new job matching your filters appears. Runs for free on GitHub Actions.

## How it works

1. Every 3 hours the workflow in `.github/workflows/watch.yml` runs `python -m careerwatch`.
2. For each company in `companies.yaml` it fetches the current job list.
3. Jobs are filtered by title and location. Ones not seen before have their
   description fetched to read the years of experience asked for and to tag
   preferred skills.
4. New matches are sent as one Telegram message, grouped by company. Nothing is
   sent when nothing is new.
5. The ids of seen jobs are committed back to `state/seen.json`.

The first run for a company only records what is already open and reports the
count; alerts start from the next new posting.

## Setup

1. **Create the Telegram bot.** Message [@BotFather](https://t.me/BotFather),
   send `/newbot`, and copy the token it gives you.
2. **Get your chat id.** Send any message to your new bot, then open
   `https://api.telegram.org/bot<TOKEN>/getUpdates` and copy `result[0].message.chat.id`.
3. **Push this folder to a GitHub repository.**
4. **Add the secrets.** In the repository: Settings → Secrets and variables →
   Actions → New repository secret. Add `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.
5. **Run it once.** Actions → Career watch → Run workflow. You should receive a
   "Now tracking" message.

## Editing the watchlist

Everything is in `companies.yaml`; the comments there explain each setting.
`defaults` apply to every company, and any key can be repeated under a company
to override it.

| Type | Use for | `url` |
|---|---|---|
| `workday` | `*.myworkdayjobs.com` sites | `https://<tenant>.<wdN>.myworkdayjobs.com/<site>` |
| `oracle` | `*.oraclecloud.com` sites | `https://<host>/hcmUI/CandidateExperience/en/sites/<site>` |
| `successfactors` | SAP SuccessFactors sites | `https://careers.<company>.com/<site>` |
| `talentbrew` | Radancy/TalentBrew sites (`/search-jobs` in the address) | `https://careers.<company>.com` |
| `greenhouse` | `boards.greenhouse.io/<board>` | the board address |
| `lever` | `jobs.lever.co/<company>` | the board address |
| `generic` | anything else | the page that lists the jobs |

`type` can be left out for Workday, Oracle, Greenhouse and Lever addresses.
Any other address without a `type` is treated as `generic`, which opens the page
in a headless browser and collects links that look like job postings. If it
picks up the wrong links, set `options.selector` to the CSS selector of a job link.

Workday sites can be narrowed on the server with `options.facets`, and Oracle
sites with `options.finder` (for example `selectedLocationsFacet: "<id>"`).

## Running locally

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt pytest
.venv\Scripts\python -m careerwatch --list        # show every job passing the title/location filters
.venv\Scripts\python -m careerwatch --dry-run     # show what would be sent; nothing is saved
.venv\Scripts\python -m careerwatch --only Visa --dry-run
.venv\Scripts\python -m pytest
```

`generic` companies also need `python -m playwright install chromium`.

## Things to know

- The years-of-experience figure is the first "N years ... experience" phrase in
  the description. It is a heuristic; jobs with no figure are always kept.
- If a company fails three runs in a row you get a warning message.
- A job that disappears for more than 45 days and comes back is reported as new.
- At most 40 descriptions per company are looked up in one run; further new
  jobs are still alerted, without the experience and skill tags.
