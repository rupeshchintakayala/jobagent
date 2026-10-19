# Run and test locally

## 1. One-time setup
```bash
cd jobagent
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest                             # all green, no network, no API key, costs nothing
```

## 2. Try discovery on real job boards (no API key needed)
```bash
python - <<'PY'
from jobagent.sources import greenhouse
from jobagent.filters import apply_filters
jobs = greenhouse.fetch("stripe")
res = apply_filters(jobs, min_salary_eur=80_000)
print(f"fetched {len(jobs)}  passed {len(res.passed)}  unknown salary {len(res.unknown_salary)}  rejected {len(res.rejected)}")
for j in (res.passed + res.unknown_salary)[:10]:
    print("-", j.title, "|", j.location, "|", j.url)
PY
```

## 3. Full flow with the CLI (uses YOUR Claude key; you pay Anthropic directly)
```bash
# one-time: create the encryption master key and keep it safe
export JOBAGENT_MASTER_KEY=$(jobagent init-master-key)      # Windows PowerShell: $env:JOBAGENT_MASTER_KEY = jobagent init-master-key
# (add the export to your shell profile, or you will not be able to decrypt your key later)

jobagent signup you@example.com
jobagent set-key you@example.com --cap-eur 15               # paste your Claude key when prompted (verified, then stored encrypted)
jobagent upload-cv you@example.com ~/cv.pdf                 # prints your parsed profile: CHECK EVERY FACT
jobagent confirm-profile you@example.com 1                  # only confirmed facts are ever used
jobagent run-daily you@example.com --dry-run                # fetch, filter, score, tailor, writes digest.md
jobagent digest you@example.com                             # list drafts waiting for you
jobagent approve you@example.com <application-id>           # you decide; nothing is auto-submitted
jobagent mark-applied you@example.com <application-id>      # after YOU applied on the employer site (updates company quota)
jobagent delete-my-data you@example.com                     # GDPR: removes everything
```
Open `digest.md` in any markdown viewer (VS Code: right click > Open Preview).

### Rough cost per daily run
Scoring uses the cheap model (Haiku), tailoring uses Sonnet only for jobs that pass your score threshold and quota check, capped at 10 per run. Results are cached, so unchanged jobs cost nothing on later days. Your monthly cap (default EUR 15) is checked BEFORE every call and the run stops cleanly when it is reached.

### Choose which companies to watch
Edit `DEFAULT_SOURCES` in `src/jobagent/config.py` (Greenhouse/Lever/Ashby board names, the last part of the company's jobs URL).

### Set a company's application limit (e.g. max 5 then locked out for 6 months)
Unknown companies default to a conservative 3. Known limits go in the `company_policies` table (a CLI command for this arrives with the web UI).

## Safety defaults
Dry-run always. Nothing is ever submitted to an employer; you approve every application and apply yourself. Tailored CVs and letters are fact-checked against your confirmed profile and rejected if they contain anything not in it.

## Not built yet
Web UI, Postgres deployment, daily scheduling, per-company policy editor.


## 4. Web UI (recommended)
```bash
# keys (once). Keep both: losing the master key means saved API keys can't be decrypted.
export JOBAGENT_MASTER_KEY=$(jobagent init-master-key)
export JOBAGENT_SESSION_SECRET=$(python -c "import secrets;print(secrets.token_urlsafe(48))")
jobagent serve                                   # then open http://127.0.0.1:8000
```
Windows PowerShell: `$env:JOBAGENT_MASTER_KEY = jobagent init-master-key`, and
`$env:JOBAGENT_SESSION_SECRET = python -c "import secrets;print(secrets.token_urlsafe(48))"`.

Flow in the browser: Sign up -> Settings (paste your Claude key, set cap) -> Profile (upload CV, check every field, confirm)
-> Home (Find jobs now; takes a few minutes, refresh the page) -> Review queue (open a draft, Approve, then apply on the
company site yourself and click "I applied") -> Privacy (delete everything).

Notes: for local use leave cookies as they are. When served over HTTPS (deployment), set `JOBAGENT_COOKIE_SECURE=1`.
