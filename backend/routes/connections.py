import asyncio
import json
from fastapi import APIRouter, HTTPException

from cache import get_people_cache, set_people_cache, hash_filters
from lib.anthropic_client import client as ai
from lib.jsonparse import parse_json_with_context
from lib.timing import timed
from linkd import LinkdClient
from schemas import Connection, ProfileAnalysis

router = APIRouter()

CONNECTIONS_SYSTEM = """You are given a LinkedIn ProfileAnalysis and a list of candidate profiles from a people search.
Your job is to select the 10 best connections for this person based on shared commonalities.

For each selected connection, you must assign:
- commonality_type: one of "fraternity", "school", "past_company", "field", "major"
- commonality_detail: specific and concrete, not generic. Examples:
    WEAK: "Same school"
    STRONG: "UIUC ECE Class of 2022, also Phi Delt Illinois Eta, now ML eng at Anduril"
- why_relevant: one sentence, specific to how this connection is useful to the user

Respond with ONLY a valid JSON array of exactly 10 Connection objects — no markdown, no commentary:

[
  {
    "name": "string",
    "title": "string",
    "company": "string",
    "linkedin_url": "string",
    "commonality_type": "school" | "fraternity" | "past_company" | "field" | "major",
    "commonality_detail": "string",
    "why_relevant": "string"
  }
]

If fewer than 10 strong candidates exist, pick the best available and fill to 10 using weaker matches rather than returning fewer.
"""


def _strip_fences(raw: str) -> str:
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return raw.strip()


async def _search_once(linkd: LinkdClient, filters: dict) -> list:
    """Run a single people search and return raw results list, with cache."""
    fhash = hash_filters(filters)
    cached = get_people_cache(fhash)
    if cached is not None:
        return cached

    try:
        resp = await linkd.search_people(**filters)
        # LinkdAPI returns {"success": true, "data": {"people": [...]}}
        if isinstance(resp, dict):
            results = resp.get("data", {}).get("people", [])
        else:
            results = resp if isinstance(resp, list) else []
    except Exception:
        results = []

    set_people_cache(fhash, results)
    return results


async def suggest_connections(profile: ProfileAnalysis) -> list[Connection]:
    """Core logic — called by both the /connections/suggest route and /run orchestrator."""
    linkd = LinkdClient()

    # Build search tasks in parallel
    tasks = []

    school_short = profile.school.replace("University of ", "").replace("University at ", "")
    print(f"[connections] school_short={school_short!r}, orgs={profile.fraternity_or_orgs}, past_cos={profile.past_companies}, major={profile.major}")

    # Strategy A: frat + school keyword (one search per frat)
    for frat in profile.fraternity_or_orgs[:3]:
        tasks.append(_search_once(linkd, {
            "keyword": f"{frat} {school_short}",
            "count": 10,
        }))

    # Strategy B: past company + school keyword (one search per company)
    for company in profile.past_companies[:2]:
        tasks.append(_search_once(linkd, {
            "keyword": f"{company} {school_short}",
            "count": 10,
        }))

    # Strategy C: school + field keyword
    tasks.append(_search_once(linkd, {
        "keyword": f"{school_short} {profile.field_of_interest}",
        "count": 20,
    }))

    # Strategy D: school + major keyword (catches more relevant classmates)
    if profile.major:
        tasks.append(_search_once(linkd, {
            "keyword": f"{school_short} {profile.major}",
            "count": 20,
        }))

    async with timed("connections: people search (linkd, parallel)"):
        all_results_nested = await asyncio.gather(*tasks)

    print(f"[connections] searches run: {len(tasks)}, results per search: {[len(b) for b in all_results_nested]}")

    # Deduplicate by linkedin_url
    seen_urls: set[str] = set()
    candidates = []
    for batch in all_results_nested:
        for person in batch:
            url = person.get("url") or person.get("profileUrl") or person.get("linkedin_url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                candidates.append(person)

    # Take up to 15 candidates — keeps the JSON complete (no mid-object truncation)
    candidates = candidates[:15]
    print(f"[connections] unique candidates: {len(candidates)}")

    if not candidates:
        return []

    # ai.messages.create is blocking — run it in a thread so it doesn't freeze the
    # event loop (and the parallel internships branch) while it waits on the LLM.
    async with timed("connections: claude (opus)"):
        msg = await asyncio.to_thread(
            ai.messages.create,
            model="claude-opus-4-8",
            max_tokens=3000,
            system=CONNECTIONS_SYSTEM,
            messages=[{
                "role": "user",
                "content": (
                    f"User profile:\n{json.dumps(profile.model_dump(), indent=2)}\n\n"
                    f"Candidate profiles ({len(candidates)} total):\n"
                    f"{json.dumps(candidates, indent=2)}"
                ),
            }],
        )

    raw = _strip_fences(msg.content[0].text)
    print(f"[connections] Claude raw (first 300 chars): {raw[:300]}")
    if not raw:
        print("[connections] WARNING: Claude returned empty response — returning []")
        return []
    # Lenient parse: recover the JSON even if Claude wraps it in prose.
    data = parse_json_with_context(raw, "connections")
    return [Connection(**c) for c in data]


@router.post("/connections/suggest", response_model=list[Connection])
async def connections_suggest_route(profile: ProfileAnalysis):
    try:
        return await suggest_connections(profile)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
