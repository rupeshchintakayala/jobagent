from __future__ import annotations
from pydantic import BaseModel, Field


class Experience(BaseModel):
    company: str
    title: str
    start: str = ""            # free text e.g. "2021-03"
    end: str = ""              # "" or "present" = current
    summary: str = ""
    achievements: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)


class Education(BaseModel):
    institution: str
    degree: str = ""
    field: str = ""
    year: str = ""


class Profile(BaseModel):
    name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    headline: str = ""
    summary: str = ""
    skills: list[str] = Field(default_factory=list)
    experience: list[Experience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)
    work_authorization: str = ""          # e.g. "Irish citizen", "Stamp 1G", "Critical Skills permit" (user-confirmed)
    target_roles: list[str] = Field(default_factory=list)
    years_experience: float | None = None

    def fact_corpus(self) -> str:
        """Lower-cased text of everything verified; used by the fact-checker."""
        return self.model_dump_json().lower()
