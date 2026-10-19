from __future__ import annotations
from datetime import datetime, timezone
import httpx
from .models import Job

URL = "https://api.lever.co/v0/postings/{company}?mode=json"


def parse(payload: list[dict], company: str = "") -> list[Job]:
    jobs = []
    for j in payload:
        cat = j.get("categories") or {}
        locs = cat.get("allLocations") or ([cat["location"]] if cat.get("location") else [])
        wt = (j.get("workplaceType") or "").lower()
        sr = j.get("salaryRange") or {}
        created = j.get("createdAt")
        jobs.append(Job(
            source="lever",
            external_id=j["id"],
            company=company,
            title=j.get("text", ""),
            location=cat.get("location") or (locs[0] if locs else ""),
            locations=locs,
            remote=True if wt == "remote" else (False if wt in ("onsite", "on-site", "hybrid") else None),
            url=j.get("hostedUrl", ""),
            apply_url=j.get("applyUrl"),
            description=(j.get("descriptionPlain") or "") + "\n" + (j.get("additionalPlain") or ""),
            salary_min=int(sr["min"]) if sr.get("min") else None,
            salary_max=int(sr["max"]) if sr.get("max") else None,
            salary_currency=sr.get("currency"),
            posted_at=datetime.fromtimestamp(created / 1000, tz=timezone.utc) if created else None,
            department=cat.get("department") or cat.get("team"),
        ))
    return jobs


def fetch(company: str, client: httpx.Client | None = None) -> list[Job]:
    c = client or httpx.Client(timeout=30, headers={"User-Agent": "jobagent/0.1 (personal job search)"})
    r = c.get(URL.format(company=company))
    r.raise_for_status()
    return parse(r.json(), company)
