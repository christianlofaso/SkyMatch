"""Server-side company-logo resolution — run ONCE at ingestion (result stored in the listing's
parsed_json as `logo_url`), so neither the request path nor the browser ever resolves a logo live.

Why server-side: the old client-side chain failed structurally. Favicon services (Google/DuckDuckGo)
serve a generic globe/placeholder image with HTTP 200, and a squatter domain serves a wrong-but-real
favicon at 200 — neither fires `<img onError>`, so a browser chain locks onto garbage and can't
recover. Resolving here (where we control the domain and can use a real logo API) means the frontend
just renders the stored URL or a clean letter avatar.

Domain priority (most-trusted first):
  1. the company's OWN domain extracted from the listing page  (lib/listing_parser, via Firecrawl)
  2. the curated company→domain map                            (lib/logos.curated_domain)
  3. logo.dev Brand Search — name → correct domain, popularity-ranked (fixes ambiguous names like
     "The Mosaic Company" → mosaicco.com, which a favicon guess resolves to a squatter)

Image URL for the resolved domain:
  - logo.dev image API when LOGODEV_PUBLISHABLE_KEY is set — returns the real logo OR a clean
    monogram (`fallback=monogram`), so it's never a broken/globe image; else
  - Google's favicon for the (trusted) resolved domain.

logo.dev keys are FREE (https://logo.dev, 500k req/mo). Both are optional:
  LOGODEV_SECRET_KEY      (sk_…) — server-side Brand Search (name → domain). Enables name coverage.
  LOGODEV_PUBLISHABLE_KEY (pk_…) — image URLs (safe to embed; rendered by the browser).
Without them, resolution still covers curated + listing-extracted domains; uncurated names get a
letter avatar (no unreliable guessing, so never a wrong/placeholder logo).
"""
import os
import re

import httpx

from lib.logos import curated_domain, favicon_url

LOGODEV_SECRET = os.getenv("LOGODEV_SECRET_KEY", "")
LOGODEV_PUBLISHABLE = os.getenv("LOGODEV_PUBLISHABLE_KEY", "")
_SEARCH_URL = "https://api.logo.dev/search"

# Trailing legal-entity suffix (",Inc.", "LLC", "Corp", "Pte Ltd", …) — stripped on a SECOND search
# attempt so "Veryfi, Inc." → "Veryfi" resolves. Applied only as a retry (the full name is tried
# first), so it never degrades a name that already resolves.
_LEGAL_SUFFIX = re.compile(
    r"[,\s]+(?:inc|llc|l\.l\.c|ltd|limited|corp|corporation|co|pc|pllc|plc|llp|gmbh|ag|s\.?a|"
    r"pte\.?\s*ltd|pvt\.?\s*ltd|sarl)\.?\s*$",
    re.I,
)


def _strip_legal(name: str) -> str:
    n = name.strip()
    prev = None
    while n and n != prev:
        prev = n
        n = _LEGAL_SUFFIX.sub("", n).strip().rstrip(",").strip()
    return n


def _logodev_image(domain: str) -> str:
    # fallback=monogram → a clean letter badge for unknown domains (never a broken/globe image).
    return (f"https://img.logo.dev/{domain}?token={LOGODEV_PUBLISHABLE}"
            "&size=128&format=png&fallback=monogram")


async def _search_once(query: str, client: httpx.AsyncClient) -> str | None:
    try:
        r = await client.get(
            _SEARCH_URL, params={"q": query},
            headers={"Authorization": f"Bearer {LOGODEV_SECRET}"}, timeout=10.0,
        )
        if r.status_code != 200:
            return None
        data = r.json()
    except Exception:
        return None
    if isinstance(data, list) and data:
        dom = data[0].get("domain") if isinstance(data[0], dict) else None
        if isinstance(dom, str) and dom.strip():
            return dom.strip().lower()
    return None


async def _search_domain(company: str, client: httpx.AsyncClient) -> str | None:
    """logo.dev Brand Search: company name → its primary domain (top popularity-ranked match).
    Tries the full name, then retries with the legal suffix stripped ("Veryfi, Inc." → "Veryfi")."""
    if not LOGODEV_SECRET or not company.strip():
        return None
    dom = await _search_once(company, client)
    if dom:
        return dom
    cleaned = _strip_legal(company)
    if cleaned and cleaned.lower() != company.strip().lower():
        return await _search_once(cleaned, client)
    return None


async def resolve_logo(
    company: str | None, company_domain: str | None, client: httpx.AsyncClient | None = None,
) -> str | None:
    """Resolve a company to a logo URL, or None (→ the frontend's letter avatar). Pure network at
    most ONE logo.dev search (only for an uncurated, un-extracted name); curated/extracted domains
    resolve with no I/O. Call at ingestion and store the result."""
    domain = company_domain or curated_domain(company)
    if not domain and company and LOGODEV_SECRET:
        if client is not None:
            domain = await _search_domain(company, client)
        else:
            async with httpx.AsyncClient() as own:
                domain = await _search_domain(company, own)
    if not domain:
        return None
    return _logodev_image(domain) if LOGODEV_PUBLISHABLE else favicon_url(domain)
