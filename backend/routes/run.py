import asyncio
import json
import os
import traceback
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from cache import get_profile_cache, get_run_cache, set_profile_cache, set_run_cache, text_cache_key
from lib.cost import cost_session
from lib.timing import timed, timed_call, timing_session
from routes.internships import search_internships
from routes.profile import analyze_profile, extract_rich_fields
from schemas import (
    RunRequest, RunResponse, UnifiedProfile, SkillEntry, WorkEntry, EducationEntry, ProjectEntry,
    RunStreamEnvelope, RunStreamError,
)

router = APIRouter()

USE_MOCKS = os.getenv("USE_MOCKS", "false").lower() == "true"
MOCK_PATH = Path(__file__).parent.parent / "mocks" / "run_response.json"

# ── Merge helpers ─────────────────────────────────────────────────────────────

def _coalesce(a, b):
    return a if a is not None and a != "" else b


def _union_strings(a: list[str], b: list[str]) -> list[str]:
    seen = {s.lower() for s in a}
    result = list(a)
    for s in b:
        if s.lower() not in seen:
            seen.add(s.lower())
            result.append(s)
    return result


_MONTH_INDEX = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _parse_date(s: str | None) -> tuple[int, int]:
    """Return (year, month) for sorting. Present → very high value. Unparseable → (0, 0)."""
    if not s:
        return (0, 0)
    low = s.lower().strip()
    if low in ("present", "current", "now"):
        return (9999, 13)
    parts = low.split()
    year, month = 0, 0
    for p in parts:
        if p.isdigit() and len(p) == 4:
            year = int(p)
        elif p[:3] in _MONTH_INDEX:
            month = _MONTH_INDEX[p[:3]]
    return (year, month)


def _merge_work(li: list[WorkEntry], re: list[WorkEntry]) -> list[WorkEntry]:
    index: dict[tuple[str, str], WorkEntry] = {}
    for entry in li:
        key = (entry.company.lower(), entry.title.lower())
        index[key] = entry
    for entry in re:
        key = (entry.company.lower(), entry.title.lower())
        if key in index:
            existing = index[key]
            # prefer whichever has a description; if both, prefer resume
            if entry.description and not existing.description:
                index[key] = entry
            elif entry.description and existing.description:
                index[key] = entry
        else:
            index[key] = entry
    merged = list(index.values())
    merged.sort(key=lambda e: _parse_date(e.start_date), reverse=True)
    return merged


def _merge_education(li: list[EducationEntry], re: list[EducationEntry]) -> list[EducationEntry]:
    index: dict[str, EducationEntry] = {}
    for entry in li:
        index[entry.school.lower()] = entry
    for entry in re:
        key = entry.school.lower()
        if key in index:
            existing = index[key]
            # prefer the entry with more non-null fields
            def _non_null_count(e: EducationEntry) -> int:
                return sum(1 for v in [e.degree, e.field_of_study, e.start_year, e.end_year] if v is not None)
            if _non_null_count(entry) > _non_null_count(existing):
                index[key] = entry
        else:
            index[key] = entry
    return list(index.values())


def _merge_projects(li: list[ProjectEntry], re: list[ProjectEntry]) -> list[ProjectEntry]:
    # resume wins on duplicates; LinkedIn-only projects appended at the end
    resume_keys = {e.name.lower() for e in re}
    result = list(re)
    for entry in li:
        if entry.name.lower() not in resume_keys:
            result.append(entry)
    return result


def _merge_skills(li: list[SkillEntry], re: list[SkillEntry]) -> list[SkillEntry]:
    index: dict[str, SkillEntry] = {}
    for entry in li:
        index[entry.skill.lower()] = entry
    for entry in re:
        key = entry.skill.lower()
        if key in index:
            # keep the entry with the longer context (more specific)
            if len(entry.context) > len(index[key].context):
                index[key] = entry
        else:
            index[key] = entry
    return list(index.values())


def _merge_profiles(linkedin: UnifiedProfile, resume: UnifiedProfile) -> UnifiedProfile:
    return UnifiedProfile(
        # Scalar fields — LinkedIn authoritative for live identity
        full_name=linkedin.full_name,
        headline=linkedin.headline,
        location=linkedin.location,
        school=linkedin.school,
        graduation_year=_coalesce(linkedin.graduation_year, resume.graduation_year),
        major=_coalesce(linkedin.major, resume.major),
        current_company=linkedin.current_company,
        field_of_interest=linkedin.field_of_interest,
        key_values=linkedin.key_values,
        # Flat list fields — union
        technical_skills=_union_strings(linkedin.technical_skills, resume.technical_skills),
        fraternity_or_orgs=_union_strings(linkedin.fraternity_or_orgs, resume.fraternity_or_orgs),
        past_companies=_union_strings(linkedin.past_companies, resume.past_companies),
        certifications=_union_strings(linkedin.certifications, resume.certifications),
        # Rich list fields — keyed merge
        skills_with_context=_merge_skills(linkedin.skills_with_context, resume.skills_with_context),
        work_experience=_merge_work(linkedin.work_experience, resume.work_experience),
        education=_merge_education(linkedin.education, resume.education),
        projects=_merge_projects(linkedin.projects, resume.projects),
        sources=["linkedin", "resume"],
    )


# ── Route ─────────────────────────────────────────────────────────────────────

@router.post("/run", response_model=RunResponse)
async def run(req: RunRequest):
    # timing_session prints a sorted [timing] breakdown when the request finishes;
    # cost_session attributes the profile-extraction Claude spend to this /run.
    with timing_session("/run"), cost_session("/run"):
        return await _run_impl(req)


async def _resolve_profile(req: RunRequest) -> UnifiedProfile:
    """Resolve the unified profile from url/text/profile_id — the 3 input cases +
    merge — preserving the Day-4 friendly HTTPException mapping verbatim. Shared by
    the JSON /run and the streaming /run/stream so the cases (and their friendly
    error messages) have ONE source of truth. Does NOT handle USE_MOCKS or the
    no-input guard — callers do that before reaching here."""
    has_linkedin = bool(req.url or req.text)
    has_resume = bool(req.profile_id)

    # ── CASE 1: Resume only — fast path ───────────────────────────────────────
    if has_resume and not has_linkedin:
        cached = get_profile_cache(req.profile_id)
        if not cached:
            raise HTTPException(status_code=404, detail="profile_id not found. Re-upload the resume.")
        return UnifiedProfile(**cached)

    # ── CASE 2: LinkedIn / paste only ────────────────────────────────────────
    if has_linkedin and not has_resume:
        cache_key = req.url if req.url else text_cache_key(req.text or "")
        cached = get_profile_cache(cache_key)
        if cached and "sources" in cached:
            profile = UnifiedProfile(**cached)
        else:
            try:
                async with timed("profile: analyze_profile (linkd+claude)"):
                    base = await analyze_profile(req)
            except ValueError as e:
                raise HTTPException(status_code=422, detail=str(e))
            except HTTPException:
                raise  # already a friendly mapped error (LinkdAPI 404/429/timeout) — pass through
            except Exception as e:
                print(f"[run] unexpected error in analyze_profile: {e!r}")
                raise HTTPException(status_code=500, detail="Couldn't read your profile. Please try again, or paste your profile text.")

            source_text = json.dumps(base.model_dump(), indent=2) if req.url else (req.text or "")[:12000]

            try:
                async with timed("profile: extract_rich_fields (claude)"):
                    rich_data = await extract_rich_fields(source_text)
            except Exception:
                rich_data = {}

            profile = UnifiedProfile(
                **base.model_dump(),
                sources=["linkedin"],
                skills_with_context=rich_data.get("skills_with_context", []),
                education=rich_data.get("education", []),
                work_experience=rich_data.get("work_experience", []),
                projects=rich_data.get("projects", []),
                certifications=rich_data.get("certifications", []),
            )
            set_profile_cache(cache_key, profile.model_dump())
        return profile

    # ── CASE 3: Both LinkedIn and resume ─────────────────────────────────────
    else:
        resume_cached = get_profile_cache(req.profile_id)
        if not resume_cached:
            raise HTTPException(status_code=404, detail="profile_id not found. Re-upload the resume.")
        resume_profile = UnifiedProfile(**resume_cached)

        linkedin_cache_key = req.url if req.url else text_cache_key(req.text or "")
        linkedin_cached = get_profile_cache(linkedin_cache_key)
        if linkedin_cached and "sources" in linkedin_cached:
            linkedin_profile = UnifiedProfile(**linkedin_cached)
        else:
            try:
                async with timed("profile: analyze_profile (linkd+claude)"):
                    base = await analyze_profile(req)
            except ValueError as e:
                raise HTTPException(status_code=422, detail=str(e))
            except HTTPException:
                raise  # already a friendly mapped error (LinkdAPI 404/429/timeout) — pass through
            except Exception as e:
                print(f"[run] unexpected error in analyze_profile: {e!r}")
                raise HTTPException(status_code=500, detail="Couldn't read your profile. Please try again, or paste your profile text.")

            source_text = json.dumps(base.model_dump(), indent=2) if req.url else (req.text or "")[:12000]

            try:
                async with timed("profile: extract_rich_fields (claude)"):
                    rich_data = await extract_rich_fields(source_text)
            except Exception:
                rich_data = {}

            linkedin_profile = UnifiedProfile(
                **base.model_dump(),
                sources=["linkedin"],
                skills_with_context=rich_data.get("skills_with_context", []),
                education=rich_data.get("education", []),
                work_experience=rich_data.get("work_experience", []),
                projects=rich_data.get("projects", []),
                certifications=rich_data.get("certifications", []),
            )
            set_profile_cache(linkedin_cache_key, linkedin_profile.model_dump())

        profile = _merge_profiles(linkedin_profile, resume_profile)
        set_profile_cache(f"merged:{linkedin_cache_key}:{req.profile_id}", profile.model_dump())
        return profile


async def _run_impl(req: RunRequest):
    has_linkedin = bool(req.url or req.text)
    has_resume = bool(req.profile_id)

    if not has_linkedin and not has_resume:
        raise HTTPException(status_code=422, detail="Provide url, text, or profile_id.")

    # Mock mode — returns hardcoded data, no API calls
    if USE_MOCKS:
        with open(MOCK_PATH) as f:
            return RunResponse(**json.load(f))

    profile = await _resolve_profile(req)

    # ── Internships ───────────────────────────────────────────────────────────
    # Connections (LinkedIn warm-intro search) is temporarily removed from /run —
    # it's being reworked to live inside the job listings. suggest_connections() and
    # POST /connections/suggest stay intact; /run just no longer triggers them, which
    # also reclaims the ~34s Opus call that was this branch's long pole.
    try:
        internships = await timed_call("internships (branch total)", search_internships(profile))
    except HTTPException:
        raise
    except Exception:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Couldn't load internship matches right now. Please try again.")

    result = RunResponse(profile=profile, connections=[], internships=internships)
    run_cache_key = req.profile_id or (req.url if req.url else text_cache_key(req.text or ""))
    set_run_cache(run_cache_key, result.model_dump())
    return result


# ── Streaming /run (phased progress) ───────────────────────────────────────────

_NDJSON_HEADERS = {"Cache-Control": "no-store", "X-Accel-Buffering": "no"}


@router.post("/run/stream")
async def run_stream(req: RunRequest):
    """Additive streaming twin of POST /run. Emits ndjson RunStreamEnvelopes so
    the home page shows real phase progress: profile(working→done) → internships
    (working) → done(full RunResponse). The no-input guard + USE_MOCKS short-circuit
    run BEFORE the StreamingResponse, so those raise proper status codes. Profile +
    internship failures stream as a typed error envelope carrying the SAME friendly
    message the JSON /run returns (status is locked at 200 once a stream starts).
    The JSON /run is unchanged."""
    if not (req.url or req.text or req.profile_id):
        raise HTTPException(status_code=422, detail="Provide url, text, or profile_id.")

    if USE_MOCKS:
        with open(MOCK_PATH) as f:
            mock = RunResponse(**json.load(f))

        async def _mock_gen():
            yield RunStreamEnvelope(phase="done", data=mock).model_dump_json() + "\n"

        return StreamingResponse(_mock_gen(), media_type="application/x-ndjson", headers=_NDJSON_HEADERS)

    async def _gen():
        # Sessions wrap the generator body so the profile-extraction Claude spend +
        # [timing] breakdown are still captured (mirrors /analyze/batch).
        with timing_session("/run/stream"), cost_session("/run/stream"):
            yield RunStreamEnvelope(phase="profile", state="working").model_dump_json() + "\n"
            try:
                profile = await _resolve_profile(req)
            except HTTPException as exc:
                msg = exc.detail if isinstance(exc.detail, str) else "Couldn't read your profile. Please try again, or paste your profile text."
                yield RunStreamEnvelope(
                    phase="error", error=RunStreamError(message=msg, status=exc.status_code)
                ).model_dump_json() + "\n"
                return
            except Exception as e:
                print(f"[run/stream] unexpected error resolving profile: {e!r}")
                yield RunStreamEnvelope(
                    phase="error",
                    error=RunStreamError(
                        message="Couldn't read your profile. Please try again, or paste your profile text.",
                        status=500,
                    ),
                ).model_dump_json() + "\n"
                return

            yield RunStreamEnvelope(phase="profile", state="done").model_dump_json() + "\n"
            yield RunStreamEnvelope(phase="internships", state="working").model_dump_json() + "\n"
            try:
                internships = await timed_call("internships (branch total)", search_internships(profile))
            except HTTPException as exc:
                msg = exc.detail if isinstance(exc.detail, str) else "Couldn't load internship matches right now. Please try again."
                yield RunStreamEnvelope(
                    phase="error", error=RunStreamError(message=msg, status=exc.status_code)
                ).model_dump_json() + "\n"
                return
            except Exception:
                traceback.print_exc()
                yield RunStreamEnvelope(
                    phase="error",
                    error=RunStreamError(
                        message="Couldn't load internship matches right now. Please try again.", status=500
                    ),
                ).model_dump_json() + "\n"
                return

            result = RunResponse(profile=profile, connections=[], internships=internships)
            run_cache_key = req.profile_id or (req.url if req.url else text_cache_key(req.text or ""))
            set_run_cache(run_cache_key, result.model_dump())
            yield RunStreamEnvelope(phase="done", data=result).model_dump_json() + "\n"

    return StreamingResponse(_gen(), media_type="application/x-ndjson", headers=_NDJSON_HEADERS)
