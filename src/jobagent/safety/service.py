"""Quota service: reads the DB, applies safety.quota rules for one user and company."""
from __future__ import annotations
from datetime import datetime, timezone
from jobagent.db import Repo
from .quota import CompanyPolicy, QuotaDecision, check_quota


def quota_for(repo: Repo, user_id: str, company_id: str, now: datetime | None = None) -> QuotaDecision:
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    row = repo.get_company_policy(company_id)
    policy = CompanyPolicy(row["max_applications"], row["window_days"] or 180, row["cooldown_days"]) if row else None
    dates, pending = repo.company_application_stats(user_id, company_id)
    return check_quota(policy, dates, now, pending_approved=pending, policy_known=row is not None)
