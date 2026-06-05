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


class SkillEntry(BaseModel):
    skill: str
    context: str  # one sentence describing where/how the skill was used


class EducationEntry(BaseModel):
    school: str
    degree: str | None = None
    field_of_study: str | None = None
    start_year: int | None = None
    end_year: int | None = None


class WorkEntry(BaseModel):
    company: str
    title: str
    start_date: str | None = None   # "May 2024" — kept as string
    end_date: str | None = None     # "Aug 2024" or "Present"
    description: str | None = None


class ProjectEntry(BaseModel):
    name: str
    description: str
    technologies: list[str]


class UnifiedProfile(ProfileAnalysis):
    """Superset of ProfileAnalysis with rich extracted fields.

    Passable anywhere ProfileAnalysis is expected — no existing consumer code changes.
    Extra fields default to empty lists so LinkedIn-only runs are valid without them.
    """
    skills_with_context: list[SkillEntry] = []
    education: list[EducationEntry] = []
    work_experience: list[WorkEntry] = []
    projects: list[ProjectEntry] = []
    certifications: list[str] = []
    sources: list[Literal["linkedin", "resume"]] = []


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
    fit_explanation: str = ""  # filled lazily by /internships/annotate; "" on the initial feed
    application_url: str | None = None
    bucket: Literal["local", "big_tech", "startup", "reach"]
    reach_gap: str | None = None  # only when bucket == "reach"


class InternshipBuckets(BaseModel):
    local: list[Internship]     # max 5
    big_tech: list[Internship]  # max 5
    startup: list[Internship]   # max 5
    reach: list[Internship]     # max 5


# ── Deferred per-role annotation (POST /internships/annotate, ndjson stream) ──
# The /run feed is now zero-LLM: cards paint from precomputed display fields with an
# empty fit_explanation. The results page fans these jobs out to /internships/annotate,
# which streams back the per-user "why you fit" text (+reach_gap) one role at a time —
# the same deferred pattern /analyze/batch uses for the score badge.

class AnnotateJobInput(BaseModel):
    url: str
    bucket: Literal["local", "big_tech", "startup", "reach"]


class AnnotateRequest(BaseModel):
    profile: UnifiedProfile
    jobs: list[AnnotateJobInput]


class AnnotateError(BaseModel):
    message: str
    code: Literal["NOT_FOUND", "ANNOTATE_FAILED", "INTERNAL"]


class AnnotateEnvelope(BaseModel):
    index: int
    status: Literal["ok", "error"]
    fit_explanation: str | None = None
    reach_gap: str | None = None
    error: AnnotateError | None = None


class RunRequest(BaseModel):
    url: str | None = None
    text: str | None = None
    profile_id: str | None = None  # reference to a cached UnifiedProfile


class RunResponse(BaseModel):
    profile: UnifiedProfile
    connections: list[Connection] = []  # populated by /connections/suggest; /run returns []
    internships: InternshipBuckets
