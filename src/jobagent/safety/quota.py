"""Per-company application quota guard (e.g. max 5 applications, then 6-month lockout)."""
from dataclasses import dataclass
from datetime import datetime, timedelta

@dataclass(frozen=True)
class CompanyPolicy:
    max_applications: int | None = None   # None = unknown/no limit
    window_days: int = 180
    cooldown_days: int | None = None      # lockout after hitting the max (defaults to window)

@dataclass(frozen=True)
class QuotaDecision:
    allowed: bool
    reason: str
    used: int = 0
    remaining: int | None = None

# Conservative default when a company's policy is unknown: don't burn applications.
DEFAULT_UNKNOWN = CompanyPolicy(max_applications=3, window_days=180)

def check_quota(policy: CompanyPolicy | None, past_application_dates: list[datetime], now: datetime,
                pending_approved: int = 0, policy_known: bool = True) -> QuotaDecision:
    p = policy or DEFAULT_UNKNOWN
    if p.max_applications is None:
        return QuotaDecision(True, "no limit known")
    since = now - timedelta(days=p.window_days)
    used = sum(1 for d in past_application_dates if d >= since) + pending_approved
    remaining = p.max_applications - used
    if remaining <= 0:
        return QuotaDecision(False, f"quota reached ({used}/{p.max_applications} in {p.window_days}d)", used, 0)
    note = "" if policy_known else " (policy unknown: conservative default)"
    return QuotaDecision(True, f"{remaining} left{note}", used, remaining)
