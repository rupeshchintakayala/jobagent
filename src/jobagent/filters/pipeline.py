"""Combine the hard filters (no LLM, free)."""
from __future__ import annotations
from dataclasses import dataclass, field
from jobagent.sources.models import Job
from .dedupe import Deduper
from .location import location_ok
from .roles import role_ok
from .salary import SalaryStatus, salary_status


@dataclass
class FilterResult:
    passed: list[Job] = field(default_factory=list)          # salary known and >= min
    unknown_salary: list[Job] = field(default_factory=list)  # kept in a separate bucket
    rejected: list[tuple[Job, str]] = field(default_factory=list)


def apply_filters(jobs: list[Job], *, min_salary_eur: int = 80_000, deduper: Deduper | None = None,
                  include_roles: list[str] | None = None, exclude_roles: list[str] | None = None) -> FilterResult:
    d = deduper or Deduper()
    res = FilterResult()
    for j in jobs:
        if d.is_duplicate(j):
            res.rejected.append((j, "duplicate"))
            continue
        ok, why = location_ok(j)
        if not ok:
            res.rejected.append((j, f"location: {why}"))
            continue
        ok, why = role_ok(j, include_roles, exclude_roles)
        if not ok:
            res.rejected.append((j, f"role: {why}"))
            continue
        status, why = salary_status(j, min_salary_eur)
        if status is SalaryStatus.FAIL:
            res.rejected.append((j, f"salary: {why}"))
            continue
        d.add(j)
        (res.passed if status is SalaryStatus.PASS else res.unknown_salary).append(j)
    return res
