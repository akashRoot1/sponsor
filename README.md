# Sponsor-Friendly QA/SDET Job Alerts

This repository runs a GitHub Actions workflow that searches public job boards and company career sources for sponsor-friendly Ireland companies, then emails direct job links to `akashvikram98@gmail.com`.

It only collects public job links. It never applies automatically, never logs in to sites, and does not collect personal data.

## How It Searches

The search now prioritizes direct public company sources instead of DuckDuckGo or Bing:

- Greenhouse public API
- Lever public API
- Ashby public API
- SmartRecruiters public API
- Workday CXS API where reliable
- Amazon Jobs API
- Simple public company careers pages
- Search fallback only when a direct source is unavailable

Direct APIs are better than DuckDuckGo/Bing because they return actual job records with titles, URLs, locations, and work types. Search engines often return homepages, login pages, Wikipedia, support pages, app stores, or HTTP challenge pages.

## Cubic Telecom

Cubic Telecom / Cubic³ is configured as a priority company using the direct Ashby board:

`https://api.ashbyhq.com/posting-api/job-board/cubic3?includeCompensation=true`

This source captures jobs such as:

- `Test Support Engineer (Maternity Cover)` in Dublin / Remote
- `Senior Test Automation Engineer` in Dublin / Hybrid
- `Test Automation Engineer` in Dublin / Hybrid

## Scheduler

GitHub cron runs in UTC. The workflow runs at both possible UTC times for 5 AM Ireland:

- `04:00 UTC`
- `05:00 UTC`

Python checks `Europe/Dublin` with `zoneinfo` and only proceeds when local Irish time is `05:00`. Manual runs bypass this gate.

## Manual Runs

Open the repository on GitHub:

1. Go to `Actions`.
2. Select `Daily Sponsor-Friendly QA/SDET Job Links`.
3. Click `Run workflow`.
4. Choose inputs:

| Input | Meaning |
| --- | --- |
| `test_mode` | Searches only priority companies: Cubic Telecom, Stripe, Workday, Amazon, Mastercard, Version 1, Accenture, Fiserv, PayPal, Guidewire |
| `send_email` | Sends or skips the email |
| `update_seen` | Updates `data/seen_jobs.json` only after a successful email |
| `max_companies` | Optional number of companies to search |

To test Cubic specifically, run with:

- `test_mode=true`
- `send_email=true`
- `update_seen=false`
- `max_companies=1`

Cubic is first in the priority list.

## Email Setup

Add these GitHub Actions secrets:

| Secret | Required | Gmail example |
| --- | --- | --- |
| `SMTP_HOST` | Yes | `smtp.gmail.com` |
| `SMTP_PORT` | Yes | `587` |
| `SMTP_USER` | Yes | `akashvikram98@gmail.com` |
| `SMTP_PASSWORD` | Yes | Gmail App Password |
| `EMAIL_FROM` | Yes | `akashvikram98@gmail.com` |
| `EMAIL_TO` | Yes | `akashvikram98@gmail.com` |

For Gmail, `SMTP_PASSWORD` must be a Gmail App Password, not your normal Gmail password.

If a required email secret is missing and `send_email=true`, the workflow fails clearly and lists the missing environment variable names.

## Artifacts

Every run uploads `job-search-debug-results` with:

| File | Purpose |
| --- | --- |
| `data/raw_results.json` | Raw public jobs collected before filtering |
| `data/filtered_results.json` | Accepted matching jobs |
| `data/rejected_results.json` | Rejected jobs with reason, matched keyword, source, URL, and snippet |
| `data/search_failures.json` | Failed sources with source type, endpoint, error, and HTTP status |

Use these artifacts to inspect why a role was accepted or rejected.

## Filtering

A job is accepted when it has relevant QA/testing/support/validation language and a relevant Ireland/remote/hybrid location signal.

Accepted role families include:

- QA Automation, QA Engineer, Quality Engineer, Quality Assurance
- SDET, Software Development Engineer in Test, Software Engineer in Test
- Test Engineer, Software Test Engineer, Test Analyst, Test Automation
- API Testing, Performance Testing, JMeter, Postman, Rest Assured
- Application Support Engineer, Production Support Engineer, Test Support Engineer
- Technical Support Engineer, L2/L3 Support, Incident Management
- Validation Engineer, Computer System Validation, CSV roles

Clearly unrelated sales, marketing, HR, finance, legal, warehouse, chef, nurse, driver, accountant, product manager, and business development roles are rejected. Pure frontend/backend developer roles are rejected unless the title itself shows testing, QA, support, or validation relevance.

## Duplicate Prevention

`data/seen_jobs.json` stores stable job IDs derived from:

- company
- title
- location
- URL

A job is marked seen only after:

- it passed filters
- it was included in the email
- the email was successfully sent
- `update_seen=true`

Rejected jobs and raw jobs are never marked as seen.

## Add Companies Or Sources

Edit `src/companies.py`.

Each company has:

- legal company name
- short brand name
- aliases
- careers URL
- source configs
- priority flag

Example:

```python
company(
    "Cubic Telecom Limited",
    "Cubic Telecom",
    ["Cubic Telecom", "Cubic³", "Cubic"],
    "https://www.cubic3.com/careers",
    [source("ashby", slug="cubic3")],
    True,
)
```

Supported source types are implemented in `src/sources.py`.

## Add Keywords

Edit `src/filters.py`.

Use `ROLE_KEYWORDS`, `GENERAL_RELEVANT_TERMS`, `IRELAND_LOCATION_TERMS`, and `EXCLUDED_TERMS`.

## Local Test

```powershell
pip install -r requirements.txt
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = "1"
python -m pytest -q
```

Run a manual script with email disabled:

```powershell
$env:FORCE_RUN = "true"
$env:TEST_MODE = "true"
$env:SEND_EMAIL = "false"
$env:UPDATE_SEEN = "false"
$env:MAX_COMPANIES = "1"
python src/main.py
```

## Limitations

- Some company career pages are JavaScript-heavy and may expose little useful HTML.
- Workday endpoints differ by tenant and can change.
- Search fallback is intentionally low priority and filters out generic search results.
- If many sources fail, the email warns: `Search completed with failures, so results may be incomplete.`

