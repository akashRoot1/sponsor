# Sponsor-Friendly QA/SDET Job Alerts

This repository runs a GitHub Actions automation that searches for public, direct job links from sponsor-friendly Ireland employers and emails matching QA / SDET / automation / testing roles to `akashvikram98@gmail.com`.

The tool only collects public job posting links. It does not apply to jobs, log in to websites, scrape private pages, or collect personal data.

## How The Scheduler Works

GitHub Actions cron uses UTC, while Ireland switches between GMT and Irish Standard Time. The workflow runs at both possible UTC times:

- `04:00 UTC`, which is `05:00 Europe/Dublin` during Irish Standard Time
- `05:00 UTC`, which is `05:00 Europe/Dublin` during GMT

The Python app then checks `Europe/Dublin` with `zoneinfo` and only sends the scheduled email when the local hour is exactly `05:00`. Manual runs skip this gate.

## GitHub Secrets

Add these secrets in GitHub:

1. Open `akashRoot1/sponsor` on GitHub.
2. Go to `Settings` -> `Secrets and variables` -> `Actions`.
3. Add these repository secrets:

| Secret | Required | Example |
| --- | --- | --- |
| `SMTP_HOST` | Yes | `smtp.gmail.com` |
| `SMTP_PORT` | Yes | `587` |
| `SMTP_USER` | Yes | your SMTP username |
| `SMTP_PASSWORD` | Yes | your SMTP password or app password |
| `EMAIL_FROM` | Yes | sender email address |
| `EMAIL_TO` | No | defaults to `akashvikram98@gmail.com` |

For Gmail, use an app password rather than your normal account password.

## Run Manually

In GitHub:

1. Open `Actions`.
2. Select `Daily Sponsor-Friendly QA/SDET Job Links`.
3. Choose `Run workflow`.

Manual runs bypass the 5 AM Ireland time gate so you can test immediately.

## Run Locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
FORCE_RUN=true python src/main.py
```

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:FORCE_RUN = "true"
python src/main.py
```

SMTP environment variables are required for sending email.

## Add Or Remove Companies

Edit `src/companies.py`.

The `COMPANIES` list is the initial sponsor-friendly target list. Add, remove, or rename companies there.

## Add Or Remove Keywords

Edit `src/companies.py`.

The `ROLE_KEYWORDS` list controls the role matching terms. The filtering logic also contains broader QA/testing inclusion terms and unrelated-role exclusion terms in `src/search_jobs.py`.

## Duplicate Prevention

Previously emailed job URLs are stored in `data/seen_jobs.json`. The workflow commits updates to this file after every successful run, so the next email only includes new matching jobs.

If there are no new jobs, the email says:

> No new matching sponsor-friendly QA/SDET jobs found today.

## Limitations

- Search results depend on public pages discoverable without login.
- Some company career portals may block search engines or hide jobs behind JavaScript.
- The automation uses polite delays and a clear user-agent, so it intentionally avoids aggressive crawling.
- Search engines and ATS pages can change their HTML, so parsing may need occasional maintenance.

