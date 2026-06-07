"""Site-handler abstraction for vendor career platforms.

A site handler is a per-domain pre-fetch step that runs BEFORE the generic
httpx + Firecrawl pipeline in routes/analyze.py. It exists because some
vendor career platforms (Microsoft, Workday, SuccessFactors, iCIMS) embed
job data in ways the generic fetcher can't reach — but expose structured
data via a vendor-specific API or embedded HTML payload.

Order of resolution in routes/analyze.py:
  1. LinkedIn auth-wall check  (paste fallback, route handler)
  2. _SPA_SEARCH_PORTALS       (generic 422 + paste instructions, route handler)
  3. site handler dispatch     ← THIS MODULE (Attempt 0 inside _fetch_job_content)
  4. direct httpx GET          (Attempt 1)
  5. Firecrawl (proxy "auto")  (Attempt 2 — escalates past Cloudflare/JS shells server-side)
  6. all-failed 422

Adding a new handler:
  1. Create site_handlers/<vendor>.py defining a class with
     `name: str`, `matches(url) -> bool`, `fetch(url) -> JobPosting | None`
  2. At the module bottom: `register(VendorHandler())`
  3. Import the module from site_handlers/__init__.py so the registration runs

TODO future handlers (not in this pass):
  - workday.py         (myworkdayjobs.com — JSON API on /wday/cxs/.../jobs/{id})
  - successfactors.py  (jobs.sap.com)
  - icims.com domains
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel


class JobPosting(BaseModel):
    title: str
    company: str
    location: str | None = None
    description: str
    requirements: list[str] = []
    apply_url: str | None = None
    source_url: str
    posted_at: str | None = None
    raw: dict = {}


@runtime_checkable
class SiteHandler(Protocol):
    name: str

    def matches(self, url: str) -> bool: ...
    async def fetch(self, url: str) -> JobPosting | None: ...


_HANDLERS: list[SiteHandler] = []


def register(h: SiteHandler) -> None:
    _HANDLERS.append(h)


def dispatch(url: str) -> SiteHandler | None:
    return next((h for h in _HANDLERS if h.matches(url)), None)
