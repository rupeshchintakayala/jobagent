"""Run the daily pipeline for every eligible user. Dry-run only: it drafts, a human approves.
One user's failure never stops the others. Jobs are fetched once and shared."""
from __future__ import annotations
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable
from jobagent.budget.guard import BudgetGuard
from jobagent.config import DEFAULT_SOURCES, Settings
from jobagent.db import Repo
from jobagent.llm import ClaudeProvider, KeyVault, LLMClient
from jobagent.pipeline import run_daily
from jobagent.sources import ADAPTERS

log = logging.getLogger("jobagent.scheduler")


@dataclass
class RunAllResult:
    ran: list[str] = field(default_factory=list)          # emails
    skipped: list[tuple[str, str]] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    queued: int = 0
    spent_eur: float = 0.0


def fetch_all_jobs(settings: Settings) -> list:
    jobs = []
    for ats, boards in (settings.sources or DEFAULT_SOURCES).items():
        for b in boards:
            try:
                jobs += ADAPTERS[ats].fetch(b)
            except Exception as e:  # noqa: BLE001 - one broken board must not stop the run
                log.warning("skip %s/%s: %s", ats, b, type(e).__name__)
    return jobs


def run_all(repo: Repo, settings: Settings, *, fetch: Callable[[Settings], list] = fetch_all_jobs,
            provider_factory: Callable[[str], object] = lambda k: ClaudeProvider(k),
            min_hours_between_runs: float = 20.0, now: datetime | None = None) -> RunAllResult:
    res = RunAllResult()
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    users = repo.list_runnable_users()
    due = []
    for u in users:
        last = repo.last_run_at(u["id"])
        if last and now - last < timedelta(hours=min_hours_between_runs):
            res.skipped.append((u["email"], "already ran recently"))
        else:
            due.append(u)
    if not due:
        return res
    jobs = fetch(settings)
    vault = KeyVault()
    for u in due:
        uid = u["id"]
        try:
            row = repo.get_key(uid)
            llm = LLMClient(uid, provider_factory(vault.decrypt(row["key_encrypted"])),
                            BudgetGuard(row["monthly_cap_eur"], repo.month_spend_eur(uid)), usage_sink=repo.record_usage)
            rep = run_daily(repo, uid, jobs, llm, match_model=settings.match_model, tailor_model=settings.tailor_model)
            res.ran.append(u["email"]); res.queued += len(rep.queue); res.spent_eur += rep.spent_eur
            log.info("ran %s: queued %d, spent %.4f", u["email"], len(rep.queue), rep.spent_eur)
        except Exception as e:  # noqa: BLE001 - isolate users from each other
            res.failed.append((u["email"], type(e).__name__))
            repo.audit(uid, "run_failed", {"error": type(e).__name__})
            log.error("run failed for %s: %s", u["email"], type(e).__name__)
    return res
