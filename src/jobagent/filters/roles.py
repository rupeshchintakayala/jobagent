"""Role keyword filter: software / backend / platform / distributed / AI engineering."""
from __future__ import annotations
import re
from jobagent.sources.models import Job

INCLUDE = [
    r"software (engineer|developer)", r"backend", r"back-end", r"back end", r"platform engineer",
    r"distributed", r"site reliability|\bsre\b", r"infrastructure engineer", r"\bai engineer",
    r"machine learning engineer|\bml engineer", r"applied (ai|scientist|ml)", r"llm", r"full[- ]?stack",
    r"staff engineer|principal engineer|senior engineer", r"member of technical staff", r"data engineer",
    r"cloud engineer", r"devops",
]
EXCLUDE = [
    r"\bintern(ship)?\b", r"\bgraduate\b", r"new grad", r"early career", r"\bapprentice", r"\bmanager\b(?!.*engineer)", r"sales", r"account executive",
    r"recruit", r"marketing", r"designer", r"\bsupport\b", r"customer success", r"legal", r"counsel",
    r"finance", r"accountant", r"hr\b", r"investigator", r"\boperations\b",
]
_inc = re.compile("|".join(INCLUDE), re.I)
_exc = re.compile("|".join(EXCLUDE), re.I)


def role_ok(job: Job, include: list[str] | None = None, exclude: list[str] | None = None) -> tuple[bool, str]:
    inc = re.compile("|".join(include), re.I) if include else _inc
    exc = re.compile("|".join(exclude), re.I) if exclude else _exc
    t = job.title or ""
    if exc.search(t):
        return False, "excluded title keyword"
    if inc.search(t):
        return True, "title matches target role"
    return False, "title not a target role"
