"""
LinkdAPI client — patterns lifted directly from dossier/backend/main.py.
Same env var (LINKDAPI_KEY), same header (X-linkdapi-apikey), same base URL,
same httpx async pattern.
"""
import os
import httpx
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://linkdapi.com/api/v1"


class LinkdClient:
    def __init__(self):
        self.api_key = os.getenv("LINKDAPI_KEY")  # same var name as dossier
        if not self.api_key:
            raise RuntimeError("LINKDAPI_KEY is not set in environment")

    def _headers(self) -> dict:
        return {"X-linkdapi-apikey": self.api_key}  # same header as dossier

    async def get_profile(self, username: str) -> dict:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{BASE_URL}/profile/full",
                params={"username": username},
                headers=self._headers(),
            )
            resp.raise_for_status()
        return resp.json()

    async def search_people(self, **params) -> dict:
        """
        Supported params: keyword, firstName, lastName, currentCompany, pastCompany,
        title, school, industry, geoUrn, profileLanguage, serviceCategory, start, count
        """
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{BASE_URL}/search/people",
                params={k: v for k, v in params.items() if v is not None},
                headers=self._headers(),
            )
            resp.raise_for_status()
        return resp.json()

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
