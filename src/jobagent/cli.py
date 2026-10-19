"""jobagent CLI. Dry-run by default. Nothing is ever submitted."""
from __future__ import annotations
import json
import sys
from pathlib import Path
import typer
from jobagent.budget.guard import BudgetGuard
from jobagent.config import DEFAULT_SOURCES, Settings
from jobagent.cvreader import CVReadError, read_cv
from jobagent.db import Repo, init_db, make_engine, tables as t
from jobagent.llm import ClaudeProvider, InvalidKey, KeyVault, KeyVaultError, LLMClient, LLMError, mask
from jobagent.pipeline import render_digest, run_daily
from jobagent.profile import Profile, ProfileParseError, ProfileService
from jobagent.sources import ADAPTERS

app = typer.Typer(help="Dublin job-search agent (dry-run by default; you approve every application).", no_args_is_help=True)


def _repo() -> Repo:
    e = make_engine(Settings.from_env().db_url)
    init_db(e)
    return Repo(e)


def _uid(repo: Repo, email: str) -> str:
    uid = repo.get_user_by_email(email)
    if not uid:
        typer.secho(f"No such user. Run: jobagent signup {email}", fg="red"); raise typer.Exit(1)
    return uid


def _llm(repo: Repo, uid: str, provider=None) -> LLMClient:
    row = repo.get_key(uid)
    if not row:
        typer.secho("No API key set. Run: jobagent set-key", fg="red"); raise typer.Exit(1)
    if provider is None:
        try:
            provider = ClaudeProvider(KeyVault().decrypt(row["key_encrypted"]))
        except KeyVaultError as e:
            typer.secho(str(e), fg="red"); raise typer.Exit(1)
    guard = BudgetGuard(row["monthly_cap_eur"], repo.month_spend_eur(uid))
    return LLMClient(uid, provider, guard, usage_sink=repo.record_usage)


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000):
    """Start the web UI (needs JOBAGENT_MASTER_KEY and JOBAGENT_SESSION_SECRET)."""
    import uvicorn
    from jobagent.web import create_app
    try:
        web = create_app()
    except RuntimeError as e:
        typer.secho(str(e), fg="red"); raise typer.Exit(1)
    typer.echo(f"Open http://{host}:{port}")
    uvicorn.run(web, host=host, port=port, log_level="warning")


@app.command("run-all")
def run_all_cmd(loop_hours: float = typer.Option(0, help="0 = run once and exit (use with cron). >0 = stay running and repeat every N hours.")):
    """Run the daily search for EVERY user who has a key and a confirmed profile. Dry-run: drafts only."""
    import logging, time
    from jobagent.scheduler import run_all
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    s = Settings.from_env(); repo = _repo()
    while True:
        r = run_all(repo, s)
        typer.echo(f"ran {len(r.ran)}, skipped {len(r.skipped)}, failed {len(r.failed)}, queued {r.queued}, spent EUR {r.spent_eur:.4f}")
        if loop_hours <= 0:
            break
        time.sleep(loop_hours * 3600)


@app.command("set-policy")
def set_policy(company: str, max_applications: int = typer.Option(None, help="Max applications allowed; omit for no limit"),
               window_days: int = 180, note: str = typer.Option("", help="Where you got this rule, e.g. careers page URL")):
    """Set a company's real application limit (default for unknown companies is 3)."""
    repo = _repo()
    cid = repo.get_or_create_company(company)
    repo.set_company_policy(cid, max_applications, window_days, note=note, verified_by="cli")
    typer.secho(f"{company}: max {max_applications if max_applications is not None else 'no limit'} per {window_days} days.", fg="green")


@app.command("list-policies")
def list_policies():
    """Show every known company and its application limit."""
    for r in _repo().list_companies_with_policies():
        lim = "unknown (default 3)" if r["max_applications"] is None and r["window_days"] is None else (
            "no limit" if r["max_applications"] is None else f"{r['max_applications']} per {r['window_days']}d")
        typer.echo(f"{r['name']}: {lim}")


@app.command()
def init_master_key():
    """Print a new master encryption key. Put it in the JOBAGENT_MASTER_KEY environment variable."""
    typer.echo(KeyVault.generate_master_key())


@app.command()
def signup(email: str):
    """Create your user."""
    repo = _repo()
    if repo.get_user_by_email(email):
        typer.echo("Already signed up."); return
    repo.create_user(email); typer.secho("Signed up.", fg="green")


@app.command()
def set_key(email: str, api_key: str = typer.Option(..., prompt=True, hide_input=True, help="Your Claude API key"),
            cap_eur: float = typer.Option(15.0, help="Your monthly API cap in EUR"), skip_verify: bool = False):
    """Store your own Claude key (encrypted). You pay Anthropic directly; we cap your spend."""
    repo = _repo(); uid = _uid(repo, email)
    if not skip_verify:
        try:
            ClaudeProvider(api_key).verify_key()
        except InvalidKey:
            typer.secho("That key was rejected by Claude. Check it and try again.", fg="red"); raise typer.Exit(1)
        except LLMError as e:
            typer.secho(f"Could not verify the key ({e}). Use --skip-verify to save anyway.", fg="red"); raise typer.Exit(1)
    try:
        enc = KeyVault().encrypt(api_key)
    except KeyVaultError as e:
        typer.secho(f"{e}\nRun `jobagent init-master-key` and export the result as JOBAGENT_MASTER_KEY.", fg="red"); raise typer.Exit(1)
    repo.save_key(uid, "claude", enc, cap_eur)
    typer.secho(f"Key saved ({mask(api_key)}), monthly cap €{cap_eur:.2f}.", fg="green")


@app.command()
def upload_cv(email: str, path: Path):
    """Parse your CV into a draft profile (review it, then run confirm-profile)."""
    repo = _repo(); uid = _uid(repo, email)
    try:
        text = read_cv(path)
        v, p = ProfileService(repo).create_draft(uid, text, _llm(repo, uid))
    except (CVReadError, ProfileParseError) as e:
        typer.secho(str(e), fg="red"); raise typer.Exit(1)
    typer.echo(json.dumps(p.model_dump(), indent=2))
    typer.secho(f"\nDraft profile v{v} saved. Check every fact above, then: jobagent confirm-profile {email} {v}", fg="yellow")


@app.command()
def confirm_profile(email: str, version: int):
    """Confirm that your profile is accurate. Only confirmed facts are ever used in applications."""
    repo = _repo(); uid = _uid(repo, email)
    ProfileService(repo).confirm(uid, version); typer.secho(f"Profile v{version} confirmed.", fg="green")


@app.command("run-daily")
def run_daily_cmd(email: str, dry_run: bool = typer.Option(True, "--dry-run/--no-dry-run"),
                  out: Path = Path("digest.md"), fixtures: Path = typer.Option(None, help="JSON file of jobs (offline testing)")):
    """Fetch jobs, filter, score, tailor and write the review digest. Never submits."""
    if not dry_run:
        typer.secho("Live submission is not implemented. Running in dry-run.", fg="yellow")
    s = Settings.from_env(); repo = _repo(); uid = _uid(repo, email); llm = _llm(repo, uid)
    jobs = []
    if fixtures:
        from jobagent.sources.models import Job
        jobs = [Job.model_validate(j) for j in json.loads(fixtures.read_text())]
    else:
        for ats, boards in (s.sources or DEFAULT_SOURCES).items():
            for b in boards:
                try:
                    jobs += ADAPTERS[ats].fetch(b)
                except Exception as e:  # noqa: BLE001 - one broken board must not stop the run
                    typer.secho(f"skip {ats}/{b}: {type(e).__name__}", fg="yellow")
    try:
        rep = run_daily(repo, uid, jobs, llm, match_model=s.match_model, tailor_model=s.tailor_model)
    except PermissionError as e:
        typer.secho(str(e), fg="red"); raise typer.Exit(1)
    out.write_text(render_digest(rep, llm.guard.cap))
    typer.secho(f"Done: {len(rep.queue)} drafts queued, spent €{rep.spent_eur:.4f}. Digest: {out}", fg="green")


@app.command()
def digest(email: str, status: str = "drafted"):
    """List applications awaiting your decision."""
    repo = _repo(); uid = _uid(repo, email)
    rows = repo.list_applications(uid, status)
    for r in rows:
        typer.echo(f"{r['id']}  {r['company']} — {r['title']}  [{r['status']}]\n    {r['url']}")
    if not rows:
        typer.echo("Nothing waiting.")


@app.command()
def approve(email: str, application_id: str):
    """Approve a draft (you still apply yourself: submission is disabled)."""
    repo = _repo(); uid = _uid(repo, email)
    repo.set_application_status(uid, application_id, "approved"); typer.secho("Approved (counts toward the company's quota).", fg="green")


@app.command()
def reject(email: str, application_id: str):
    repo = _repo(); uid = _uid(repo, email)
    repo.set_application_status(uid, application_id, "rejected"); typer.echo("Rejected.")


@app.command()
def mark_applied(email: str, application_id: str):
    """Record that YOU submitted this application yourself (updates the company quota)."""
    repo = _repo(); uid = _uid(repo, email)
    repo.set_application_status(uid, application_id, "submitted"); typer.secho("Recorded as submitted.", fg="green")


@app.command()
def delete_my_data(email: str, yes: bool = typer.Option(False, "--yes", help="skip the confirmation")):
    """Permanently delete all your data (GDPR)."""
    repo = _repo(); uid = _uid(repo, email)
    if not yes and not typer.confirm("This permanently deletes your account, key, profiles and applications. Continue?"):
        raise typer.Exit()
    repo.delete_user_data(uid); typer.secho("All your data was deleted.", fg="green")


if __name__ == "__main__":
    app()
