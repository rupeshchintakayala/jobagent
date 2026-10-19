from __future__ import annotations
from datetime import datetime
import httpx
from .models import Job

URL = "https://api.ashbyhq.com/posting-api/job-board/{board}?includeCompensation=true"


def _salary(comp: dict | None) -> tuple[int | None, int | None, str | None]:
    if not comp:
        return None, None, None
    for tier in comp.get("compensationTiers") or []:
        for c in tier.get("components") or []:
            if c.get("compensationType") == "Salary" and (c.get("interval") or "").upper().startswith("1 YEAR"):
                lo, hi = c.get("minValue"), c.get("maxValue")
                return (int(lo) if lo else None, int(hi) if hi else None, c.get("currencyCode"))
    return None, None, None


def parse(payload: dict, board: str = "") -> list[Job]:
    jobs = []
    for j in payload.get("jobs", []):
        if j.get("isListed") is False:
            continue
        locs = [j["location"]] if j.get("location") else []
        locs += [s["location"] for s in j.get("secondaryLocations") or [] if s.get("location")]
        lo, hi, cur = _salary(j.get("compensation"))
        pub = j.get("publishedAt")
        jobs.append(Job(
            source="ashby",
            external_id=j["id"],
            company=board,
            title=j.get("title", ""),
            location=j.get("location", "") or "",
            locations=list(dict.fromkeys(locs)),
            remote=j.get("isRemote"),
            url=j.get("jobUrl", ""),
            apply_url=j.get("applyUrl"),
            description=j.get("descriptionPlain") or "",
            salary_min=lo, salary_max=hi, salary_currency=cur,
            posted_at=datetime.fromisoformat(pub.replace("Z", "+00:00")) if pub else None,
            department=j.get("department"),
        ))
    return jobs


def fetch(board: str, client: httpx.Client | None = None) -> list[Job]:
    c = client or httpx.Client(timeout=30, headers={"User-Agent": "jobagent/0.1 (personal job search)"})
    r = c.get(URL.format(board=board))
    r.raise_for_status()
    return parse(r.json(), board)
