# Data models

Defined in `backend/schemas.py` (Pydantic) and mirrored in `frontend/src/types/skymatch.ts` (Zod). **Keep both in sync when adding fields.**

### ProfileAnalysis
```python
full_name: str
headline: str
location: str
school: str
graduation_year: int | None
major: str | None
fraternity_or_orgs: list[str]
past_companies: list[str]
current_company: str | None
technical_skills: list[str]
field_of_interest: str
key_values: list[str]          # 3-5 noun phrases, Claude-extracted
```

### UnifiedProfile (extends ProfileAnalysis)
```python
# All ProfileAnalysis fields, plus:
skills_with_context: list[SkillEntry]   # default []
education:           list[EducationEntry]  # default []
work_experience:     list[WorkEntry]    # default []
projects:            list[ProjectEntry] # default []
certifications:      list[str]          # default []
sources:             list[Literal["linkedin", "resume"]]  # default []
```

`UnifiedProfile` is a Pydantic subclass of `ProfileAnalysis`. It passes everywhere a `ProfileAnalysis` is expected. All extra fields default to empty so LinkedIn only runs are valid without a resume.

### Rich submodels
```python
class SkillEntry:    skill: str;  context: str        # where/how skill was used
class EducationEntry: school, degree, field_of_study, start_year, end_year
class WorkEntry:     company, title, start_date, end_date, description
class ProjectEntry:  name: str;  description: str;  technologies: list[str]
```

### Analysis models (in `routes/analyze.py`, not `schemas.py`)
```python
class IncludeFlags:      roadmap: bool = True;  project: bool = True   # Phase 3 opt-out (both default true)
class AnalyzeRequest:    profile: UnifiedProfile;  job_url: str | None;  job_text: str | None
                         mode: Literal["full","quick"] = "full"   # default preserves pre-Phase-3 behavior
                         include: IncludeFlags = IncludeFlags()   # quick mode ignores this

# Full mode, Phase 2 fields unchanged; Phase 3 fields are additive optional
class JobSummary:        title, company, key_requirements: list[str]
class MatchItem:         requirement, type, must_have, match_strength, evidence_snippet, evidence_source
class GapItem:           requirement, type, must_have, severity: Literal["critical","moderate","minor"]
class Verdict:           call: Literal["apply_now","apply_after_prep","skip"];  reasoning: str

# Phase 3, roadmap (skill-gap plan) + project_suggestion (build this to apply)
class RoadmapResource:   type: Literal["docs","course","tutorial","video","book","roadmap"]
                         title, url, duration; cost: Literal["free","paid"]
class RoadmapItem:       skill, priority: Literal["must_have","nice_to_have"], timeline, why_it_matters,
                         milestone (concrete deliverable, not "feel comfortable with X"),
                         resources: list[RoadmapResource]   # 2-4 after URL validation
class Roadmap:           total_timeline, summary, items: list[RoadmapItem]   # max 5
class ProjectSuggestion: title, pitch (one sentence), why_this_role (cites real requirements),
                         mvp_features: list[str] (5-8), tech_stack: list[str] (specific names),
                         estimated_time, stretch_goals: list[str] (2-4),
                         interview_talking_points: list[str] (3-5)

class AnalysisResponse:  fit_score: int;  category_scores: dict[str,int];  matches, gaps, verdict, job_summary
                         roadmap: Roadmap | None = None              # Phase 3, None when include.roadmap=False
                         roadmap_note: str | None = None             # Phase 3, set instead of roadmap when gaps=[]
                         project_suggestion: ProjectSuggestion | None = None   # Phase 3

# Quick mode (separate types, JobSummary intentionally NOT extended)
class QuickJobSummary:        title, company, posted_at: str | None, apply_url: str | None
class QuickAnalysisResponse:  fit_score: int;  verdict: Verdict;  job_summary: QuickJobSummary

# Batch (POST /analyze/batch)
class BatchJobInput:       text: str | None  XOR  url: str | None    # model_validator enforces exactly one
class BatchAnalyzeRequest: profile: UnifiedProfile;  jobs: list[BatchJobInput] = Field(max_length=50)
class BatchErrorBody:      message: str;  code: Literal["FETCH_FAILED","EXTRACTION_FAILED","VERDICT_FAILED","INTERNAL"]
class BatchEnvelope:       index: int;  status: "ok" | "error";  data?: QuickAnalysisResponse;  error?: BatchErrorBody
```

### Connection / Internship
```python
class Connection:    name, title, company, linkedin_url, commonality_type, commonality_detail, why_relevant
class Internship:    title, company, location, company_description, fit_explanation="",  # default "", see below
                     application_url, bucket, reach_gap, logo_url=None  # logo_url: lib/logos, None → letter avatar
class InternshipBuckets: local, big_tech, startup, reach, each list[Internship] max 5
```
> `Internship.fit_explanation` now **defaults `""`**: the zero LLM `/run` feed ships it empty and the results page fills it lazily via `/internships/annotate` (see [routes.md](routes.md)). Keep `InternshipSchema.fit_explanation` as `.default("")` in `skymatch.ts` in sync.

### Deferred annotation (POST /internships/annotate, ndjson)
```python
class AnnotateJobInput: url: str;  bucket: Literal["local","big_tech","startup","reach"]
class AnnotateRequest:  profile: UnifiedProfile;  jobs: list[AnnotateJobInput]
class AnnotateError:    message: str;  code: Literal["NOT_FOUND","ANNOTATE_FAILED","INTERNAL"]
class AnnotateEnvelope: index: int;  status: "ok" | "error";  fit_explanation?: str;  why: list[str]=[];  have: list[str]=[];  need: list[str]=[];  reach_gap?: str;  error?: AnnotateError
```
Frontend mirror: `AnnotateEnvelopeSchema` / `AnnotateEnvelope` in `skymatch.ts`.

> `why`/`have`/`need` are the drawer's enriched content (added when the option j UI was ported): `why` = 2-3 "why you fit" bullets; `have` = skills the student already brings (⊆ the listing's parsed skills); `need` = skills the posting wants that the profile lacks. The slim fit only annotate call (`_annotate_fit_sync`, `MODEL_MID`, max_tokens 400) emits all of them in one JSON object alongside `fit_explanation`/`reach_gap`; the page renders `why`/`have`/`need` in the role drawer. Old `annotate_cache` entries predating the enrichment lack these keys and degrade to `[]` (read with `.get(..., [])`).

### Request/Response
```python
class RunRequest:    url, text, profile_id (all optional; at least one required)
class RunResponse:   profile: UnifiedProfile;  connections: list[Connection];  internships: InternshipBuckets
```
