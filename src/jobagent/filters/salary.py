"""Salary handling. Unknown salary goes to its own bucket (never silently dropped)."""
from __future__ import annotations
import re
from enum import Enum
from jobagent.sources.models import Job

# Rough annual conversion to EUR for threshold checks only.
FX_TO_EUR = {"EUR": 1.0, "GBP": 1.15, "USD": 0.92, "CAD": 0.68, "CHF": 1.05}
SYMBOL = {"€": "EUR", "£": "GBP", "$": "USD"}

_NUM = r"(\d{1,3}(?:[,\.]\d{3})+|\d+(?:\.\d+)?)\s*(k|K)?"
_RANGE = re.compile(rf"([€£$])?\s*{_NUM}\s*(?:-|–|—|to)\s*([€£$])?\s*{_NUM}")
_SINGLE = re.compile(rf"([€£$])\s*{_NUM}")
_HOURLY = re.compile(r"(per hour|/hr|/hour|hourly|per day|daily)", re.I)


def _to_number(num: str, k: str | None) -> float:
    n = float(num.replace(",", "")) if re.fullmatch(r"\d{1,3}(,\d{3})+", num) else float(num.replace(",", "")) if "," in num else float(num)
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", num):  # 80.000 european thousands
        n = float(num.replace(".", ""))
    return n * 1000 if k else n


def parse_salary_text(text: str) -> tuple[int | None, int | None, str | None]:
    """Parse '€80,000 - €100,000', '€110K – €185K', '80k-100k EUR', '€90k'. Annual only."""
    if not text or _HOURLY.search(text):
        return None, None, None
    m = _RANGE.search(text)
    if m:
        sym1, n1, k1, sym2, n2, k2 = m.groups()
        sym = sym1 or sym2
        cur = SYMBOL.get(sym) if sym else _currency_word(text)
        lo, hi = _to_number(n1, k1 or k2), _to_number(n2, k2)
        if lo < 1000 and not (k1 or k2):  # not a salary (e.g. "2 - 3 years")
            return None, None, None
        if lo > hi:
            lo, hi = hi, lo
        return int(lo), int(hi), cur
    m = _SINGLE.search(text)
    if m:
        sym, n, k = m.groups()
        v = _to_number(n, k)
        if v >= 1000:
            return int(v), int(v), SYMBOL[sym]
    return None, None, None


def _currency_word(text: str) -> str | None:
    for c in ("EUR", "GBP", "USD", "CAD", "CHF"):
        if re.search(rf"\b{c}\b", text, re.I):
            return c
    return None


class SalaryStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"


def salary_status(job: Job, min_eur: int = 80_000) -> tuple[SalaryStatus, str]:
    lo, hi, cur = job.salary_min, job.salary_max, job.salary_currency
    if lo is None and hi is None:
        lo, hi, cur = parse_salary_text(job.description)
        # only trust description text if currency symbol/word was present
        if cur is None:
            lo = hi = None
    if lo is None and hi is None:
        return SalaryStatus.UNKNOWN, "no published salary"
    rate = FX_TO_EUR.get((cur or "EUR").upper())
    if rate is None:
        return SalaryStatus.UNKNOWN, f"unsupported currency {cur}"
    top = (hi or lo) * rate
    if top >= min_eur:
        return SalaryStatus.PASS, f"max ~€{int(top):,} >= €{min_eur:,}"
    return SalaryStatus.FAIL, f"max ~€{int(top):,} < €{min_eur:,}"
