from __future__ import annotations
import os
from dataclasses import dataclass


@dataclass
class Settings:
    db_url: str = "sqlite:///jobagent.db"
    match_model: str = "claude-haiku-4-5"
    tailor_model: str = "claude-sonnet-4-5"
    # board lists: ATS -> company board slugs the user wants watched
    sources: dict | None = None

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(db_url=os.environ.get("JOBAGENT_DB", "sqlite:///jobagent.db"),
                   match_model=os.environ.get("JOBAGENT_MATCH_MODEL", "claude-haiku-4-5"),
                   tailor_model=os.environ.get("JOBAGENT_TAILOR_MODEL", "claude-sonnet-4-5"))


DEFAULT_SOURCES = {
    "greenhouse": ["stripe", "datadog", "intercom", "hubspot", "cloudflare", "mongodb"],
    "lever": [],
    "ashby": [],
}
