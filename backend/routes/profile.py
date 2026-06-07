import asyncio
import json
from pathlib import Path
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from cache import get_profile_cache, set_profile_cache, text_cache_key
from config.models import MODEL_MID
from lib.anthropic_client import client as ai, sonnet_slot
from lib.cost import cost_session, record_usage
from lib.jsonparse import parse_json_with_context
from linkd import LinkdClient, extract_username
from schemas import ProfileAnalysis, RunRequest

router = APIRouter()

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
RICH_SYSTEM = (_PROMPTS_DIR / "rich_profile_extraction.txt").read_text()

PROFILE_SYSTEM = """You analyze LinkedIn profile data and extract structured information.
Respond with ONLY valid JSON matching this exact schema — no markdown fences, no commentary:

{
  "full_name": "string",
  "headline": "string",
  "location": "string",
  "school": "string",
  "graduation_year": number or null,
  "major": "string or null",
  "fraternity_or_orgs": ["string"],
  "past_companies": ["string"],
  "current_company": "string or null",
  "technical_skills": ["string"],
  "field_of_interest": "string",
  "key_values": ["string", "string", "string"]
}

Rules:
- school: most recent or most prestigious university attended
- graduation_year: 4-digit year of graduation or expected graduation, null if unknown
- fraternity_or_orgs: scan Activities, Interests, and About sections — include Greek life, clubs, honor societies
- past_companies: all previous employers, not including current company
- current_company: current employer, null if unemployed or student
- technical_skills: programming languages, frameworks, tools mentioned anywhere in the profile
- field_of_interest: single broad field, e.g. "Software Engineering", "Investment Banking", "Product Management"
- key_values: exactly 3-5 noun phrases describing what this person clearly cares about based on their experience and headline.
  Write short noun phrases like "applied ML research", "early-stage startups", "product thinking", "quantitative finance".
  Never write full sentences.
"""


def _strip_fences(raw: str) -> str:
    """Strip accidental markdown fences from LLM output — verbatim from dossier."""
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return raw.strip()


_MONTHS = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _fmt_linkd_date(d: dict | None) -> str | None:
    """LinkdAPI {year,month,day} → 'Mon YYYY' (or 'YYYY'); None when year is missing/0."""
    if not isinstance(d, dict):
        return None
    y = d.get("year") or 0
    if not y:
        return None
    m = d.get("month") or 0
    return f"{_MONTHS[m]} {y}" if 1 <= m <= 12 else str(y)


def _linkedin_profile_to_text(raw_profile: dict) -> str:
    """Flatten a LinkdAPI /profile/full payload into clean, resume-like sectioned TEXT.

    The extraction prompts (PROFILE_SYSTEM + RICH_SYSTEM) handle resume-style prose far
    better than a raw nested JSON blob. Feeding `json.dumps(raw_profile, indent=2)[:8000]`
    was doubly broken: (1) ~2/3 of the budget went to image URLs / logos / multiLocale
    dupes / ids, and (2) the payload is ~24k chars pretty-printed, so the 8000-char cut
    landed BEFORE the experience descriptions, skills, and certifications — silently
    dropping skills and 3 of 5 jobs. It also made Sonnet echo/prose-wrap the JSON. Rendering
    only the meaningful fields keeps the whole profile well under budget AND yields clean
    JSON back (like the resume path). See docs/gotchas.md.
    """
    data = raw_profile.get("data") if isinstance(raw_profile, dict) else None
    if not isinstance(data, dict):
        # Unknown shape — degrade to compact JSON rather than crash.
        return json.dumps(raw_profile)[:12000]

    lines: list[str] = []
    name = " ".join(x for x in [data.get("firstName"), data.get("lastName")] if x).strip()
    if name:
        lines.append(f"Name: {name}")
    if data.get("headline"):
        lines.append(f"Headline: {data['headline']}")
    geo = data.get("geo") or {}
    if geo.get("full"):
        lines.append(f"Location: {geo['full']}")
    if (data.get("industry") or {}).get("name"):
        lines.append(f"Industry: {data['industry']['name']}")
    if data.get("summary"):
        lines.append(f"\nSummary:\n{data['summary']}")

    # fullPositions == position here, but fullPositions is the canonical complete list.
    positions = data.get("fullPositions") or data.get("position") or []
    if positions:
        lines.append("\nExperience:")
        for p in positions:
            title = p.get("title") or ""
            company = p.get("companyName") or ""
            meta = ", ".join(x for x in [p.get("employmentType"), p.get("location")] if x)
            start = _fmt_linkd_date(p.get("start"))
            end_d = p.get("end") or {}
            end = "Present" if not (end_d.get("year") or 0) else _fmt_linkd_date(end_d)
            dates = " to ".join(x for x in [start, end] if x)
            header = f"- {title} at {company}".rstrip()
            if meta:
                header += f" ({meta})"
            if dates:
                header += f" | {dates}"
            lines.append(header)
            desc = (p.get("description") or "").strip()
            if desc:
                lines.append(desc)

    educations = data.get("educations") or []
    if educations:
        lines.append("\nEducation:")
        for e in educations:
            degree_field = ", ".join(x for x in [e.get("degree"), e.get("fieldOfStudy")] if x)
            start = _fmt_linkd_date(e.get("start"))
            end = _fmt_linkd_date(e.get("end"))
            extras = ", ".join(
                x for x in [e.get("grade"), " to ".join(y for y in [start, end] if y)] if x
            )
            header = f"- {e.get('schoolName') or ''}".rstrip()
            if degree_field:
                header += f": {degree_field}"
            if extras:
                header += f" ({extras})"
            lines.append(header)
            if e.get("activities"):
                lines.append(f"  Activities: {e['activities']}")

    skills = [s.get("name") for s in (data.get("skills") or []) if s.get("name")]
    if skills:
        lines.append("\nSkills: " + ", ".join(skills))

    certs = [c.get("name") for c in (data.get("certifications") or []) if c.get("name")]
    if certs:
        lines.append("\nCertifications: " + ", ".join(certs))

    vol = data.get("volunteering") or []
    if vol:
        lines.append("\nVolunteering:")
        for v in vol:
            header = f"- {v.get('title') or ''} at {v.get('companyName') or ''}".rstrip()
            lines.append(header)
            d = (v.get("description") or "").strip()
            if d:
                lines.append(d)

    honors = [h.get("title") for h in (data.get("honorsAndAwards") or []) if h.get("title")]
    if honors:
        lines.append("\nHonors & Awards: " + ", ".join(honors))

    return "\n".join(lines)


async def analyze_profile(req: RunRequest) -> tuple[ProfileAnalysis, str]:
    """Core logic — called by both the /profile/analyze route and /run orchestrator.

    Returns (profile, source_text). `source_text` is the RAW profile data (the full
    LinkedIn JSON or the pasted text) — NOT the compacted ProfileAnalysis. Callers feed
    it straight to extract_rich_fields so skills/projects/experience detail survives;
    distilling to ProfileAnalysis first drops technical-skill context, work descriptions,
    and projects entirely (ProfileAnalysis has no projects field), which silently empties
    the rich fields. On a warm-cache hit the raw source is gone, so it falls back to the
    pasted text or the compacted profile (lossy, but only on that cold-rich-fields path)."""
    if not req.url and not req.text:
        raise ValueError("url or text required")

    # Reject non-LinkedIn URLs immediately — job boards, company pages, etc. are not profiles
    if req.url:
        host = urlparse(req.url).hostname or ""
        if "linkedin.com" not in host:
            raise ValueError(
                "That doesn't look like a LinkedIn profile URL. "
                "Enter your personal LinkedIn URL (linkedin.com/in/yourname) "
                "or switch to the 'Paste text' tab and paste your profile text."
            )

    cache_key = req.url if req.url else text_cache_key(req.text or "")
    cached = await asyncio.to_thread(get_profile_cache, cache_key)
    if cached:
        # Raw source didn't survive caching. Prefer the pasted text (still raw) when we
        # have it; otherwise fall back to the compacted profile (lossy rich fields).
        return ProfileAnalysis(**cached), (req.text or json.dumps(cached))

    if req.url:
        username = extract_username(req.url)
        linkd = LinkdClient()
        try:
            raw_profile = await linkd.get_profile(username)
        except httpx.HTTPStatusError as e:
            # Map LinkdAPI HTTP errors to friendly responses instead of leaking a raw 500.
            status = e.response.status_code
            if status in (404, 410):
                raise ValueError(
                    "No LinkedIn profile found at that URL — it may be private, renamed, "
                    "or deleted. Try the 'Paste text' tab: open your profile, copy all the "
                    "text, and paste it."
                ) from e
            if status == 429:
                raise HTTPException(
                    status_code=503,
                    detail="The LinkedIn lookup service is busy right now. Please try again in a moment.",
                ) from e
            if status in (401, 403):
                print(f"[profile] LinkdAPI auth error {status} for {username!r} — check LINKDAPI_KEY")
                raise HTTPException(
                    status_code=502,
                    detail="LinkedIn lookup is temporarily unavailable. Try the 'Paste text' tab instead.",
                ) from e
            raise HTTPException(
                status_code=502,
                detail="LinkedIn lookup is temporarily unavailable. Try again, or paste your profile text.",
            ) from e
        except httpx.RequestError as e:  # network / timeout after retries
            print(f"[profile] LinkdAPI network error for {username!r}: {e!r}")
            raise HTTPException(
                status_code=504,
                detail="Timed out fetching your LinkedIn profile. Try again, or paste your profile text.",
            ) from e
        # Flatten the LinkdAPI JSON into clean resume-like text (NOT a raw json.dumps blob):
        # the prompts extract far better from prose, and the old indent=2 [:8000] dump
        # truncated before skills/experience-descriptions ever reached the model. See
        # _linkedin_profile_to_text. Cap generously; the flattened text is naturally small.
        profile_text = _linkedin_profile_to_text(raw_profile)[:16000]
    else:
        profile_text = (req.text or "")[:8000]
        # Guard against an empty/too-short paste BEFORE spending an LLM call.
        if len(profile_text.strip()) < 40:
            raise ValueError(
                "That's too short to read as a profile. Paste the full text of your "
                "LinkedIn profile (headline, experience, education, skills)."
            )

    # ai.messages.create is BLOCKING — must run in a worker thread, or it freezes the
    # event loop and serializes the asyncio.gather in resume.py (analyze_profile +
    # extract_rich_fields would run back-to-back instead of in parallel). MODEL_MID
    # (Sonnet): this is pure field extraction, not deep reasoning — Opus latency unjustified.
    # sonnet_slot() caps global concurrent Sonnet calls (Redis-distributed rate-limit
    # governor — see lib/anthropic_client.py); acquire it in the async layer, around the
    # thread dispatch.
    async with sonnet_slot():
        msg = await asyncio.to_thread(
            ai.messages.create,
            model=MODEL_MID,
            max_tokens=1024,
            system=PROFILE_SYSTEM,
            messages=[{"role": "user", "content": f"LinkedIn profile data:\n\n{profile_text}"}],
        )
    record_usage("profile-extract", MODEL_MID, msg.usage)

    raw = _strip_fences(msg.content[0].text)
    # Lenient parse: recover the JSON even if the model wraps it in prose.
    data = parse_json_with_context(raw, "profile-extract")

    # If the LLM couldn't find a person's name, the URL was not a real profile page
    if not data.get("full_name"):
        raise ValueError(
            "No LinkedIn profile found at that URL. "
            "Make sure you're using your personal profile URL (linkedin.com/in/yourname), "
            "not a job listing or company page."
        )

    try:
        result = ProfileAnalysis(**data)
    except ValidationError as exc:
        raise ValueError(
            "Could not extract a complete profile from that URL. "
            "Try the 'Paste text' tab: open your LinkedIn profile, copy all the text, and paste it."
        ) from exc

    await asyncio.to_thread(set_profile_cache, cache_key, result.model_dump())
    return result, profile_text


async def extract_rich_fields(source_text: str) -> dict:
    """Second Claude call to extract SkillEntry/WorkEntry/etc. from any profile text.

    Returns a dict with keys: skills_with_context, education, work_experience,
    projects, certifications. Caller is responsible for exception handling.
    """
    # Blocking call → worker thread (see analyze_profile). MODEL_MID (Sonnet): rich-field
    # extraction (skills/work/education/projects) is structured extraction, not reasoning.
    # sonnet_slot(): global Sonnet concurrency cap (Redis-distributed — see lib/anthropic_client.py).
    async with sonnet_slot():
        msg = await asyncio.to_thread(
            ai.messages.create,
            model=MODEL_MID,
            max_tokens=2048,
            system=RICH_SYSTEM,
            messages=[{"role": "user", "content": f"Profile data:\n\n{source_text[:12000]}"}],
        )
    record_usage("profile-rich", MODEL_MID, msg.usage)
    raw = _strip_fences(msg.content[0].text)
    # Lenient parse: recover the JSON even if the model wraps it in prose. expected_keys
    # makes recovery pick the real answer, not an example object buried in reasoning prose.
    data = parse_json_with_context(
        raw, "profile-rich",
        expected_keys=("skills_with_context", "work_experience", "education",
                       "projects", "certifications"),
    )
    print(
        f"[profile-rich] extracted {len(data.get('skills_with_context', []))} skills, "
        f"{len(data.get('work_experience', []))} work entries, "
        f"{len(data.get('projects', []))} projects"
    )
    return data


@router.post("/profile/analyze", response_model=ProfileAnalysis)
async def profile_analyze_route(req: RunRequest):
    try:
        with cost_session("/profile/analyze"):
            profile, _ = await analyze_profile(req)
            return profile
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except HTTPException:
        raise  # already a friendly mapped error — don't bury it in a generic 500
    except Exception as e:
        print(f"[profile] unexpected error in /profile/analyze: {e!r}")
        raise HTTPException(status_code=500, detail="Couldn't analyze that profile. Please try again.")
