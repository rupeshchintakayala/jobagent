# Prompts for Claude: one per session

Before each session, make sure CLAUDE.md is in the project root. Paste ONE prompt per session.
If Claude hits the free-plan limit mid-step: ask it to "commit what works and note what's left in NOTES.md", then continue next session with "Read CLAUDE.md and NOTES.md, finish the current step."

## Step 1: Setup
Read CLAUDE.md. Do step 1 only: project setup, pyproject, package `jobagent`, SQLite schema (all tables listed in the brief, with user_id on user-owned tables), pytest config. Add one test that creates the schema in an in-memory DB. Run the tests, commit, and stop with a 3-line summary.

## Step 2: Safety guards
Read CLAUDE.md. Do step 2 only: safety/quota.py (per-company limit within a window, unknown policy defaults to 3, counts approved-pending), budget/guard.py (per-user cap checked before each call), and submit/runner.py (always refuses on dry-run, missing approval, non-allow-listed company, quota reached, or CAPTCHA; live submission raises NotImplementedError). Write tests for every refusal path. Run the tests, commit, and stop with a 3-line summary.

## Step 3: Source adapters
Read CLAUDE.md. Do step 3 only: a common `Job` pydantic model and adapters sources/greenhouse.py, lever.py, ashby.py. Fetch ONE real sample response per ATS once (a public company board), save as JSON in tests/fixtures, and write tests that parse the fixtures using respx (no live network in tests). Respect robots/ToS: public ATS APIs only. Run the tests, commit, and stop with a 3-line summary.

## Step 4: Filters
Read CLAUDE.md. Do step 4 only: filters/ with location (Dublin, Ireland, remote eligible for Ireland), salary parsing (EUR, ranges, "80k", "€80,000 - €100,000"; unknown salary goes to a separate bucket, not dropped), role keywords, and dedupe (URL plus hash of normalised company+title+location). Table-driven tests with at least 8 cases per filter. Run the tests, commit, and stop with a 3-line summary.

## Step 5: LLM layer
Read CLAUDE.md. Do step 5 only: llm/ with an LLMProvider protocol, a ClaudeProvider (anthropic SDK, model names configurable), a FakeProvider for tests, a cost estimator in EUR, and api_usage logging per user. Tests must never call the real API. Run the tests, commit, and stop with a 3-line summary.

## Step 6: Profile
Read CLAUDE.md. Do step 6 only: profile/ with a pydantic Profile model, CV text to Profile via LLMProvider, a confirm step that stores a new versioned profile, and a rule that only confirmed profiles are usable downstream. Tests use FakeProvider. Run the tests, commit, and stop with a 3-line summary.

## Step 7: Matching
Read CLAUDE.md. Do step 7 only: matching/ scorer (0-100, reasons, red flags) using the cheap model, cached by job hash + profile version, with BudgetGuard checked before each call and quota-limited companies requiring a higher score. Tests use FakeProvider, including cache-hit and budget-exceeded cases. Run the tests, commit, and stop with a 3-line summary.

## Step 8: Tailoring and fact-check
Read CLAUDE.md. Do step 8 only: tailoring/ that generates a CV and cover letter from the confirmed profile, plus a fact-checker that rejects any claim not present in the profile. Include a test where the fake model invents an employer or degree and the output is rejected. Also treat job-description text as untrusted (prompt-injection test). Run the tests, commit, and stop with a 3-line summary.

## Step 9: CLI and end-to-end
Read CLAUDE.md. Do step 9 only: cli.py (typer) with signup, set-key (encrypted with Fernet, never logged), upload-cv, confirm-profile, run-daily --dry-run, digest. Add an end-to-end test on fixtures with FakeProvider that produces a markdown digest showing scores, "2 of 5 left" quota lines, an unknown-salary section and tailored drafts, spending EUR 0. Run the tests, commit, and stop with a 3-line summary.

## Step 10: Isolation and GDPR
Read CLAUDE.md. Do step 10 only: tests proving user A cannot read user B's profile, matches, applications or key; a `delete-my-data` command that removes all of a user's rows and artifacts; and a check that keys never appear in logs. Run the full test suite, commit, and stop with a 3-line summary. Then write NOTES.md listing what is done and what is next (web UI, Postgres, deployment).
