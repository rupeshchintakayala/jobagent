"""Location filter: Dublin / Ireland / remote roles eligible for Ireland."""
from __future__ import annotations
import re
from jobagent.sources.models import Job

IRELAND = re.compile(r"\b(dublin|ireland|irl|cork|galway|limerick|waterford|dun laoghaire|dún laoghaire|leopardstown|sandyford)\b", re.I)
REMOTE = re.compile(r"\b(remote|work from home|wfh|anywhere)\b", re.I)
# Remote but clearly restricted to somewhere that excludes Ireland
RESTRICTED = re.compile(
    r"\b(us only|usa only|u\.s\. only|united states only|canada only|uk only|"
    r"remote\s*[-–(,]\s*(us|usa|united states|canada|uk|united kingdom|india|brazil|australia|latam)\b)",
    re.I)
ELIGIBLE_REMOTE = re.compile(r"\b(emea|europe|european union|eu|ireland|worldwide|global|anywhere)\b", re.I)


def is_dublin(text: str) -> bool:
    return bool(re.search(r"\bdublin\b", text or "", re.I))


def location_ok(job: Job) -> tuple[bool, str]:
    """Return (ok, reason). Remote roles pass only if they aren't restricted away from Ireland."""
    texts = [job.location, *job.locations]
    joined = " | ".join(dict.fromkeys(t for t in texts if t))
    if any(IRELAND.search(t) for t in texts if t):
        return True, "ireland"
    is_remote = bool(job.remote) or bool(REMOTE.search(joined))
    if is_remote:
        if RESTRICTED.search(joined):
            return False, "remote restricted outside ireland"
        if ELIGIBLE_REMOTE.search(joined):
            return True, "remote eligible (emea/eu/global)"
        if re.sub(r"[^a-z]", "", joined.lower()) in ("remote", ""):
            return True, "remote (region unspecified)"
        return False, "remote but region excludes ireland"
    return False, "not in ireland"
