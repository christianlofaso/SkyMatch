"""
LinkdAPI client — patterns lifted directly from dossier/backend/main.py.
Same env var (LINKDAPI_KEY), same header (X-linkdapi-apikey), same base URL,
same httpx async pattern.
"""
import asyncio
import os
import httpx
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://linkdapi.com/api/v1"

# Retry only TRANSIENT failures (rate limit / upstream blip / network) — never 4xx like a
# 404 (missing/private profile), which is a permanent answer the caller maps to a friendly
# message. Tune attempts via LINKD_MAX_RETRIES.
_MAX_RETRIES = int(os.getenv("LINKD_MAX_RETRIES", "2"))
_RETRY_STATUS = {429, 500, 502, 503, 504}


class LinkdClient:
    def __init__(self):
        self.api_key = os.getenv("LINKDAPI_KEY")  # same var name as dossier
        if not self.api_key:
            raise RuntimeError("LINKDAPI_KEY is not set in environment")

    def _headers(self) -> dict:
        return {"X-linkdapi-apikey": self.api_key}  # same header as dossier

    async def _get_json(self, path: str, params: dict) -> dict:
        """GET + parse JSON with bounded retries on transient errors. Raises
        httpx.HTTPStatusError on a final non-2xx (incl. a permanent 404) and
        httpx.RequestError on a final network failure — the caller maps both."""
        clean = {k: v for k, v in params.items() if v is not None}
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    resp = await client.get(f"{BASE_URL}{path}", params=clean, headers=self._headers())
                if resp.status_code in _RETRY_STATUS and attempt < _MAX_RETRIES:
                    await asyncio.sleep(0.5 * (2 ** attempt))
                    continue
                resp.raise_for_status()
                return resp.json()
            except httpx.RequestError as e:  # network/timeout — transient, retry
                last_exc = e
                if attempt < _MAX_RETRIES:
                    await asyncio.sleep(0.5 * (2 ** attempt))
                    continue
                raise
        if last_exc:
            raise last_exc
        raise RuntimeError("linkd: exhausted retries without a response")

    async def get_profile(self, username: str) -> dict:
        return await self._get_json("/profile/full", {"username": username})

    async def search_people(self, **params) -> dict:
        """
        Supported params: keyword, firstName, lastName, currentCompany, pastCompany,
        title, school, industry, geoUrn, profileLanguage, serviceCategory, start, count
        """
        return await self._get_json("/search/people", params)

    async def search_jobs(self, **params) -> dict:
        """
        Supported params: keyword, experience, jobTypes, locations, companies,
        industries, functions, titles, datePosted, salary, workplaceTypes,
        sortBy, easyApply, start, count
        """
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{BASE_URL}/search/jobs",
                params={k: v for k, v in params.items() if v is not None},
                headers=self._headers(),
            )
            resp.raise_for_status()
        return resp.json()

    async def geo_lookup(self, location_name: str) -> str | None:
        """Convert a city/location name to a LinkedIn geoUrn string."""
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{BASE_URL}/geos/name-lookup",
                params={"q": location_name},
                headers=self._headers(),
            )
            if resp.status_code != 200:
                return None
        data = resp.json()
        elements = data.get("elements", [])
        if elements:
            return str(elements[0]["id"])
        return None


def extract_username(url: str) -> str:
    """Extract LinkedIn username from a profile URL. Verbatim from dossier."""
    return url.rstrip("/").split("/")[-1]
