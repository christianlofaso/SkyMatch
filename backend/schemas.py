from __future__ import annotations
from typing import Literal
from pydantic import BaseModel


class ProfileAnalysis(BaseModel):
    full_name: str
    headline: str
    location: str
    school: str
    graduation_year: int | None = None
    major: str | None = None
    fraternity_or_orgs: list[str]
    past_companies: list[str]
    current_company: str | None = None
    technical_skills: list[str]
    field_of_interest: str
    key_values: list[str]  # 3-5 noun phrases, Claude-extracted


class Connection(BaseModel):
    name: str
    title: str
    company: str
    linkedin_url: str
    commonality_type: Literal["fraternity", "school", "past_company", "field", "major"]
    commonality_detail: str
    why_relevant: str


class Internship(BaseModel):
    title: str
    company: str
    location: str
    company_description: str
    fit_explanation: str
    application_url: str | None = None
    bucket: Literal["local", "big_tech", "startup", "reach"]
    reach_gap: str | None = None  # only when bucket == "reach"


class InternshipBuckets(BaseModel):
    local: list[Internship]     # max 5
    big_tech: list[Internship]  # max 5
    startup: list[Internship]   # max 5
    reach: list[Internship]     # max 5


class RunRequest(BaseModel):
    url: str | None = None
    text: str | None = None


class RunResponse(BaseModel):
    profile: ProfileAnalysis
    connections: list[Connection]  # exactly 10
    internships: InternshipBuckets
