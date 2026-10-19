"""Deterministic fact-checker (no LLM). Rejects any generated claim not grounded in the verified profile.

Checks, on generated CV / letter text:
  1. numbers (percentages, money, counts, years) must appear in the profile or the job posting is NOT a source
  2. capitalised proper-noun phrases (employers, institutions, products) must appear in the profile
     or be the target company / job title (allowed context)
  3. years-of-experience claims must not exceed the profile's
  4. degrees / certifications must exist in the profile
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from jobagent.profile import Profile

NUM = re.compile(r"(?<![\w.])(?:[€$£]\s?)?\d[\d,]*(?:\.\d+)?\s?(?:%|k\b|m\b|x\b)?", re.I)
YEARS = re.compile(r"(\d{1,2})\+?\s*(?:years|yrs)", re.I)
PROPER = re.compile(r"\b[A-Z][\w&-]*(?:[ \t]+(?:[A-Z][\w&-]*|of|and|&))*")
DEGREE = re.compile(r"\b(ph\.?d|doctorate|master'?s|msc|m\.sc|mba|bsc|b\.sc|bachelor'?s|bachelor|beng|meng)\b", re.I)
CERT = re.compile(r"\b(aws certified[\w\s-]*|azure[\w\s-]*certified[\w\s-]*|cka|ckad|cissp|pmp|scrum master|gcp[\w\s-]*certified[\w\s-]*)\b", re.I)

# Common capitalised words that are not facts
STOP = {"i", "my", "the", "a", "an", "dear", "sincerely", "regards", "best", "thank", "thanks", "hiring", "team",
        "manager", "hello", "hi", "kind", "yours", "faithfully", "in", "at", "with", "as", "for", "to", "and", "of",
        "ireland", "dublin", "cv", "experience", "skills", "education", "summary", "profile", "contact", "email",
        "phone", "location", "projects", "certifications", "languages", "links", "present", "current", "engineer",
        "software", "senior", "backend", "platform", "role", "position", "application", "january", "february", "march",
        "april", "may", "june", "july", "august", "september", "october", "november", "december", "english",
        "technologies", "achievements", "work", "authorization", "technical", "lead", "staff", "principal"}


@dataclass
class FactCheckResult:
    ok: bool
    violations: list[str] = field(default_factory=list)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower()).strip()


def _num_key(s: str) -> str:
    return re.sub(r"[€$£,\s]", "", s.lower())


def _profile_numbers(corpus: str) -> set[str]:
    return {_num_key(m.group(0)) for m in NUM.finditer(corpus)}


def check_text(text: str, profile: Profile, *, allowed_context: list[str] | None = None) -> FactCheckResult:
    corpus = profile.fact_corpus()
    allowed = _norm(" ".join(allowed_context or []))
    viol: list[str] = []

    # 1. numbers
    pnums = _profile_numbers(corpus)
    for m in NUM.finditer(text):
        raw = m.group(0).strip()
        key = _num_key(raw)
        digits = re.sub(r"\D", "", key)
        if not digits:
            continue
        if re.fullmatch(r"(19|20)\d{2}", digits):          # plain years: must be in profile too
            if digits not in corpus and digits not in allowed:
                viol.append(f"unverified year: {raw}")
            continue
        if key in pnums or (key in allowed):
            continue
        if len(digits) == 1 and not re.search(r"[%kmx€$£]", raw, re.I):  # tiny list numbers like "3 projects"
            continue
        viol.append(f"unverified number: {raw}")

    # 2. proper nouns
    for m in PROPER.finditer(text):
        phrase = m.group(0).strip(" .,-")
        words = [w for w in re.split(r"\s+", phrase) if w]
        core = [w for w in words if w.lower() not in STOP and w.lower() not in ("of", "and", "&")]
        if not core:
            continue
        p = _norm(" ".join(core))
        if p in corpus or p in allowed or all(_norm(w) in corpus or _norm(w) in allowed for w in core):
            continue
        viol.append(f"unverified name: {phrase}")

    # 3. years of experience
    claimed = [int(x) for x in YEARS.findall(text)]
    if claimed and profile.years_experience is not None and max(claimed) > profile.years_experience + 0.5:
        viol.append(f"claims {max(claimed)} years but profile verifies {profile.years_experience}")
    elif claimed and profile.years_experience is None:
        if not any(f"{c} year" in corpus or f"{c}+ year" in corpus for c in claimed):
            viol.append(f"unverified years of experience: {max(claimed)}")

    # 4. degrees and certifications
    for m in DEGREE.finditer(text):
        if _norm(m.group(0)) not in corpus:
            viol.append(f"unverified degree: {m.group(0)}")
    for m in CERT.finditer(text):
        if _norm(m.group(0)) not in corpus:
            viol.append(f"unverified certification: {m.group(0)}")

    return FactCheckResult(ok=not viol, violations=list(dict.fromkeys(viol)))
