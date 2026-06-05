import asyncio
import json
from pathlib import Path
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from cache import get_profile_cache, set_profile_cache, text_cache_key
from config.models import MODEL_MID
from lib.anthropic_client import client as ai, sonnet_sem
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


async def analyze_profile(req: RunRequest) -> ProfileAnalysis:
    """Core logic — called by both the /profile/analyze route and /run orchestrator."""
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
        return ProfileAnalysis(**cached)

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
        profile_text = json.dumps(raw_profile, indent=2)[:8000]
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
    # sonnet_sem caps process-wide concurrent Sonnet calls (rate-limit governor — see
    # lib/anthropic_client.py); acquire it in the async layer, around the thread dispatch.
    async with sonnet_sem:
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
    return result


async def extract_rich_fields(source_text: str) -> dict:
    """Second Claude call to extract SkillEntry/WorkEntry/etc. from any profile text.

    Returns a dict with keys: skills_with_context, education, work_experience,
    projects, certifications. Caller is responsible for exception handling.
    """
    # Blocking call → worker thread (see analyze_profile). MODEL_MID (Sonnet): rich-field
    # extraction (skills/work/education/projects) is structured extraction, not reasoning.
    # sonnet_sem: process-wide Sonnet concurrency cap (see lib/anthropic_client.py).
    async with sonnet_sem:
        msg = await asyncio.to_thread(
            ai.messages.create,
            model=MODEL_MID,
            max_tokens=2048,
            system=RICH_SYSTEM,
            messages=[{"role": "user", "content": f"Profile data:\n\n{source_text[:12000]}"}],
        )
    record_usage("profile-rich", MODEL_MID, msg.usage)
    raw = _strip_fences(msg.content[0].text)
    # Lenient parse: recover the JSON even if the model wraps it in prose.
    data = parse_json_with_context(raw, "profile-rich")
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
            return await analyze_profile(req)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except HTTPException:
        raise  # already a friendly mapped error — don't bury it in a generic 500
    except Exception as e:
        print(f"[profile] unexpected error in /profile/analyze: {e!r}")
        raise HTTPException(status_code=500, detail="Couldn't analyze that profile. Please try again.")
