"""Dedupe: by URL and by hash(company+title+location). Also skips jobs already applied for."""
from __future__ import annotations
from urllib.parse import urlsplit, urlunsplit
from jobagent.sources.models import Job


def canonical_url(url: str) -> str:
    p = urlsplit(url or "")
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/"), "", ""))


class Deduper:
    def __init__(self, seen_urls: set[str] | None = None, seen_hashes: set[str] | None = None):
        self.urls = {canonical_url(u) for u in (seen_urls or set())}
        self.hashes = set(seen_hashes or set())

    def is_duplicate(self, job: Job) -> bool:
        return canonical_url(job.url) in self.urls or job.dedupe_hash in self.hashes

    def add(self, job: Job) -> None:
        self.urls.add(canonical_url(job.url))
        self.hashes.add(job.dedupe_hash)

    def filter_new(self, jobs: list[Job]) -> list[Job]:
        out = []
        for j in jobs:
            if not self.is_duplicate(j):
                self.add(j)
                out.append(j)
        return out
