# Brief: Dublin job-search agent, prototype v0

You are building a **prototype** of a multi-user, bring-your-own-key (BYOK) job-search agent for Dublin, Ireland.
Work in small steps. After each step: run the tests, fix failures, then stop and summarise in 3 lines. Keep every step small enough to finish in one short session (free-plan limits).

## Hard rules (never break)
1. Dry-run by default. Nothing is ever submitted to an employer. Live submission is NOT part of this prototype.
2. A human approves every application. No auto-submit.
3. No scraping of LinkedIn or Indeed. Sources: public ATS APIs only (Greenhouse, Lever, Ashby).
4. Never bypass CAPTCHAs, logins or robots.txt.
5. Tailored CVs/cover letters may use ONLY facts from the user's confirmed profile. A fact-check step must reject anything else.
6. Each user brings their own LLM key and pays for it. Keys are encrypted at rest (Fernet) and never logged.
7. Per-user monthly API cap (default EUR 15) enforced BEFORE each call by BudgetGuard.
8. Per-company application quota (e.g. max 5, then 6-month lockout): unknown policy = conservative default of 3; count approved-pending too.
9. Every user-owned table has user_id; tests must prove user A can't read user B's data.

## Stack
Python 3.11+, SQLite for the prototype (schema Postgres-compatible), SQLAlchemy 2, pydantic v2, httpx, typer (CLI), pytest + respx. LLM calls go through an `LLMProvider` protocol; Claude (anthropic SDK) first. **In tests the LLM is always a fake: never spend real tokens in tests.**

## Pipeline
CV -> parse to profile (LLM) -> user confirms -> daily: fetch jobs (shared pool) -> hard filters (Dublin/Ireland/remote-IE, published salary >= EUR 80k, role keywords: software/backend/platform/distributed/AI engineer) -> dedupe (URL + hash of company+title+location) -> per-user match score 0-100 (cheap model, cached by job hash + profile version) -> if score >= threshold and quota ok and budget ok: tailor CV + letter (stronger model) -> fact-check -> review queue (markdown digest). Salary unknown = separate "unknown salary" bucket, not dropped.

## Steps (do in order; one per session)
1. Project setup: pyproject, package `jobagent`, SQLite schema (users, user_llm_keys, profiles, preferences, companies, company_policies, jobs, matches, applications, api_usage, audit_log), pytest config.
2. `safety/quota.py` + `budget/guard.py` + submit gate (`submit/runner.py` always refuses in dry-run/no approval/CAPTCHA/quota). Tests for each.
3. Source adapters `sources/greenhouse.py`, `lever.py`, `ashby.py` returning a common `Job` model. Use saved JSON fixtures in tests/fixtures (fetch one real sample each once, save it). Greenhouse: `https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true`. Lever: `https://api.lever.co/v0/postings/{company}?mode=json`.
4. `filters/`: location, salary parsing (EUR, ranges, "k"), role keywords, dedupe. Table-driven tests.
5. `llm/` provider protocol + Claude provider + FakeProvider; cost estimator; API-usage logging.
6. `profile/` CV text -> profile (pydantic) -> confirm step. Store versioned.
7. `matching/` scorer with cache and budget guard. Tests with FakeProvider.
8. `tailoring/` CV + letter + fact-checker (rejects claims not in profile; test with an invented claim).
9. `cli.py` (typer): `signup`, `set-key`, `upload-cv`, `confirm-profile`, `run-daily --dry-run`, `digest`. End-to-end test on fixtures with FakeProvider.
10. Multi-user isolation tests; GDPR `delete-my-data` command.

## Done when
`pytest` is green, `run-daily --dry-run` on fixtures produces a markdown digest with scores, quota remaining ("2 of 5 left"), and tailored drafts, and spends EUR 0 in tests.

## Token-saving tips for the free plan
- One step per session; start each by reading only the files that step touches.
- Don't paste whole files back; make targeted edits.
- Commit after each green step so progress is never lost.

## Start with step 1 now.

## NOTES.md (session memory)
Keep a `NOTES.md` in the project root. At the end of EVERY step (and whenever you are about to run out of budget), update it with: steps done, current step and what is left, decisions made, and any failing tests. At the start of every session, read CLAUDE.md and NOTES.md only, then continue. If the user says "finish the current step", use NOTES.md to resume.
