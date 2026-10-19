from __future__ import annotations
from datetime import datetime
import httpx
from .models import Job
from .text import html_to_text

URL = "https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"


def parse(payload: dict, board: str = "") -> list[Job]:
    jobs = []
    for j in payload.get("jobs", []):
        loc = (j.get("location") or {}).get("name", "") or ""
        offices = [o.get("name", "") for o in j.get("offices") or [] if o.get("name")]
        locs = list(dict.fromkeys([loc, *offices])) if loc else offices
        depts = j.get("departments") or []
        posted = j.get("first_published") or j.get("updated_at")
        jobs.append(Job(
            source="greenhouse",
            external_id=str(j["id"]),
            company=j.get("company_name") or board,
            title=j.get("title", ""),
            location=loc,
            locations=[x for x in locs if x],
            remote=("remote" in loc.lower()) or None,
            url=j.get("absolute_url", ""),
            apply_url=j.get("absolute_url"),
            description=html_to_text(j.get("content")),
            posted_at=datetime.fromisoformat(posted) if posted else None,
            department=depts[0].get("name") if depts else None,
        ))
    return jobs


def fetch(board: str, client: httpx.Client | None = None) -> list[Job]:
    c = client or httpx.Client(timeout=30, headers={"User-Agent": "jobagent/0.1 (personal job search)"})
    r = c.get(URL.format(board=board))
    r.raise_for_status()
    return parse(r.json(), board)
