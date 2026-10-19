"""Common job model shared by all source adapters."""
from __future__ import annotations
import hashlib
import re
from datetime import datetime
from pydantic import BaseModel, Field


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


class Job(BaseModel):
    source: str                      # greenhouse | lever | ashby
    external_id: str
    company: str
    title: str
    location: str = ""               # primary location text
    locations: list[str] = Field(default_factory=list)  # all known locations
    remote: bool | None = None       # None = unknown
    url: str                         # public posting URL
    apply_url: str | None = None
    description: str = ""            # plain text (untrusted input!)
    salary_min: int | None = None    # annual, EUR-or-other (see currency)
    salary_max: int | None = None
    salary_currency: str | None = None
    posted_at: datetime | None = None
    department: str | None = None

    @property
    def dedupe_hash(self) -> str:
        key = "|".join([_norm(self.company), _norm(self.title), _norm(self.location)])
        return hashlib.sha256(key.encode()).hexdigest()[:32]
