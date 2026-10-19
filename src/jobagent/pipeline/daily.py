"""Daily pipeline for ONE user: filter -> dedupe -> match -> quota/score gate -> tailor -> review queue.
Never submits. Everything lands as a 'drafted' application awaiting human approval."""
from __future__ import annotations
from dataclasses import dataclass, field
from jobagent.budget.guard import BudgetExceeded
from jobagent.db import Repo
from jobagent.filters import Deduper, apply_filters
from jobagent.llm import LLMClient
from jobagent.matching import Matcher, MatchError, required_score
from jobagent.profile import ProfileService
from jobagent.safety.service import quota_for
from jobagent.sources.models import Job
from jobagent.tailoring import TailoringRejected, tailor


@dataclass
class Candidate:
    job: Job
    score: int
    reasons: list[str]
    red_flags: list[str]
    quota_remaining: int | None
    quota_max: int | None
    application_id: str | None = None
    cv: str = ""
    letter: str = ""
    salary_unknown: bool = False


@dataclass
class DailyReport:
    fetched: int = 0
    filtered_out: int = 0
    scored: int = 0
    below_threshold: list[tuple[Job, int]] = field(default_factory=list)
    quota_blocked: list[tuple[Job, str]] = field(default_factory=list)
    tailoring_rejected: list[tuple[Job, list[str]]] = field(default_factory=list)
    queue: list[Candidate] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    budget_stopped: bool = False
    spent_eur: float = 0.0


def run_daily(repo: Repo, user_id: str, jobs: list[Job], llm: LLMClient, *, match_model: str, tailor_model: str,
              dry_run: bool = True, max_tailor: int = 10) -> DailyReport:
    rep = DailyReport(fetched=len(jobs))
    profiles = ProfileService(repo)
    pver, profile = profiles.require_confirmed(user_id)          # PermissionError if not confirmed
    prefs = repo.get_preferences(user_id)
    min_salary, base_score = prefs["min_salary_eur"], prefs["min_score"]

    seen_urls, seen_hashes = repo.applied_urls_and_hashes(user_id)
    fres = apply_filters(jobs, min_salary_eur=min_salary, deduper=Deduper(seen_urls, seen_hashes))
    rep.filtered_out = len(fres.rejected)
    unknown_ids = {id(j) for j in fres.unknown_salary}
    matcher = Matcher(repo, llm, user_id, model=match_model)

    scored: list[Candidate] = []
    for job in fres.passed + fres.unknown_salary:
        cid = repo.get_or_create_company(job.company, job.source)
        repo.upsert_job(job, cid)
        try:
            m = matcher.score(job, profile, pver)
        except BudgetExceeded:
            rep.budget_stopped = True
            break
        except MatchError as e:
            rep.errors.append(f"{job.title}: {e}")
            continue
        rep.scored += 1
        q = quota_for(repo, user_id, cid)
        scored.append(Candidate(job, m.score, m.reasons, m.red_flags, q.remaining,
                                None, salary_unknown=id(job) in unknown_ids))
        if not q.allowed:
            rep.quota_blocked.append((job, q.reason))
            scored.pop()
            continue
        need = required_score(base_score, q.remaining)
        if m.score < need:
            rep.below_threshold.append((job, m.score))
            scored.pop()

    scored.sort(key=lambda c: c.score, reverse=True)
    for cand in scored[:max_tailor]:
        job = cand.job
        try:
            t = tailor(job, profile, llm, model=tailor_model)
        except TailoringRejected as e:
            rep.tailoring_rejected.append((job, e.violations))
            continue
        except BudgetExceeded:
            rep.budget_stopped = True
            break
        cid = repo.get_or_create_company(job.company, job.source)
        jid = repo.upsert_job(job, cid)
        repo.save_match(user_id, jid, pver, cand.score, cand.reasons, cand.red_flags)
        cand.cv, cand.letter = t.cv_markdown, t.cover_letter
        cand.application_id = repo.create_application(user_id, jid, cid, "drafted", t.cv_markdown, t.cover_letter)
        pol = repo.get_company_policy(cid)
        cand.quota_max = pol["max_applications"] if pol else 3
        rep.queue.append(cand)
    rep.spent_eur = llm.guard.spent
    repo.audit(user_id, "run_daily", {"fetched": rep.fetched, "queued": len(rep.queue), "dry_run": dry_run})
    return rep
