import json
import anthropic
from fastapi import APIRouter, HTTPException

from cache import get_profile_cache, set_profile_cache, text_cache_key
from linkd import LinkdClient, extract_username
from schemas import ProfileAnalysis, RunRequest

router = APIRouter()
ai = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY automatically — same as dossier

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

    cache_key = req.url if req.url else text_cache_key(req.text or "")
    cached = get_profile_cache(cache_key)
    if cached:
        return ProfileAnalysis(**cached)

    if req.url:
        username = extract_username(req.url)
        linkd = LinkdClient()
        raw_profile = await linkd.get_profile(username)
        profile_text = json.dumps(raw_profile, indent=2)[:8000]
    else:
        profile_text = (req.text or "")[:8000]

    msg = ai.messages.create(
        model="claude-opus-4-5",
        max_tokens=1024,
        system=PROFILE_SYSTEM,
        messages=[{"role": "user", "content": f"LinkedIn profile data:\n\n{profile_text}"}],
    )

    raw = _strip_fences(msg.content[0].text)
    data = json.loads(raw)
    result = ProfileAnalysis(**data)
    set_profile_cache(cache_key, result.model_dump())
    return result


@router.post("/profile/analyze", response_model=ProfileAnalysis)
async def profile_analyze_route(req: RunRequest):
    try:
        return await analyze_profile(req)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
