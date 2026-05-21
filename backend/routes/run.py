import asyncio
import json
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException

from cache import get_run_cache, set_run_cache, text_cache_key
from routes.connections import suggest_connections
from routes.internships import search_internships
from routes.profile import analyze_profile
from schemas import RunRequest, RunResponse

router = APIRouter()

USE_MOCKS = os.getenv("USE_MOCKS", "false").lower() == "true"
MOCK_PATH = Path(__file__).parent.parent / "mocks" / "run_response.json"


@router.post("/run", response_model=RunResponse)
async def run(req: RunRequest):
    if not req.url and not req.text:
        raise HTTPException(status_code=422, detail="Provide either url or text.")

    # Mock mode — returns hardcoded data, no API calls
    if USE_MOCKS:
        with open(MOCK_PATH) as f:
            return RunResponse(**json.load(f))

    cache_key = req.url if req.url else text_cache_key(req.text or "")
    # Run cache disabled during development
    # cached = get_run_cache(cache_key)
    # if cached:
    #     return RunResponse(**cached)

    # Step 1: profile (connections + internships both depend on it)
    try:
        profile = await analyze_profile(req)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Profile analysis failed: {e}")

    # Step 2: connections + internships in parallel
    try:
        connections, internships = await asyncio.gather(
            suggest_connections(profile),
            search_internships(profile),
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Search failed: {e}")

    result = RunResponse(profile=profile, connections=connections, internships=internships)

    # Cache the full result for 24 hours
    set_run_cache(cache_key, result.model_dump())

    return result
