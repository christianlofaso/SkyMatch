"""Microsoft Careers handler.

apply.careers.microsoft.com is a SPA whose visible HTML body is the search
results shell. But the page embeds a schema.org JSON-LD JobPosting block
for SEO (Google for Jobs) — that block carries the full title, description,
location, posting date, and apply URL. No auth, no special headers, no
vendor API call: just GET the page the user pasted and parse the JSON-LD.
"""
from __future__ import annotations

import json
import re
from urllib.parse import parse_qs, urlparse

import httpx

from .base import JobPosting, register

_JSON_LD_RE = re.compile(
    r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)

_HOSTS = ("apply.careers.microsoft.com", "careers.microsoft.com")


def _format_location(job_location) -> str | None:
    """schema.org JobPosting jobLocation can be a single dict or a list of dicts."""
    if not job_location:
        return None
    locs = job_location if isinstance(job_location, list) else [job_location]
    out: list[str] = []
    for loc in locs:
        if not isinstance(loc, dict):
            continue
        addr = loc.get("address") or {}
        if not isinstance(addr, dict):
            continue
        country = addr.get("addressCountry")
        country_name = country.get("name") if isinstance(country, dict) else country
        bits = [
            addr.get("addressLocality") or "",
            addr.get("addressRegion") or "",
            country_name or "",
        ]
        bits = [b for b in bits if b]
        if bits:
            out.append(", ".join(bits))
    return " | ".join(dict.fromkeys(out)) if out else None


def _extract_jsonld(html: str) -> dict | None:
    for m in _JSON_LD_RE.finditer(html):
        try:
            d = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        if isinstance(d, dict) and d.get("@type") == "JobPosting":
            return d
    return None


class MicrosoftHandler:
    name = "microsoft"

    def matches(self, url: str) -> bool:
        host = (urlparse(url).hostname or "").lower()
        return host in _HOSTS

    async def fetch(self, url: str) -> JobPosting | None:
        # Microsoft requires `pid` in the query string; without it the page is a
        # generic search results page with no JobPosting JSON-LD embedded.
        params = parse_qs(urlparse(url).query)
        pid = (params.get("pid") or [None])[0]
        if not pid:
            print("[site_handlers.microsoft] no pid in query string")
            return None

        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                resp = await client.get(url)
        except httpx.RequestError as exc:
            print(f"[site_handlers.microsoft] fetch failed: {exc}")
            return None

        if resp.status_code >= 400:
            print(f"[site_handlers.microsoft] HTTP {resp.status_code}")
            return None

        jp = _extract_jsonld(resp.text)
        if not jp:
            print("[site_handlers.microsoft] no JobPosting JSON-LD in page")
            return None
        if not jp.get("title") or not jp.get("description"):
            print("[site_handlers.microsoft] JSON-LD missing title or description")
            return None

        org = jp.get("hiringOrganization") or {}
        company = org.get("name") if isinstance(org, dict) else None

        return JobPosting(
            title=jp["title"],
            company=company or "Microsoft",
            location=_format_location(jp.get("jobLocation")),
            description=jp["description"],
            requirements=[],
            apply_url=jp.get("url"),
            source_url=url,
            posted_at=jp.get("datePosted"),
            raw={"pid": pid, "json_ld": jp},
        )


register(MicrosoftHandler())
