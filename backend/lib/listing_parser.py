"""Ingestion-time listing parse (Haiku) — turns one raw listing into the profile-INDEPENDENT
structured + display fields that serving used to derive live per request.

Kept separate from lib/ingest_core.py (which stays pure scrape/enrich/validate, no Claude).
Used by worker/ingest.py's parse pass. The blocking Haiku call must be dispatched via
asyncio.to_thread from the async worker.
"""

import hashlib
import re
from pathlib import Path
from urllib.parse import urlparse

from config.models import MODEL_QUICK
from lib import firecrawl
from lib.anthropic_client import client as ai
from lib.cost import record_usage
from lib.jsonparse import parse_json_with_context, strip_fences
from lib.logos import registrable_domain

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
_PARSE_SYSTEM = (_PROMPTS_DIR / "listing_parse.txt").read_text(encoding="utf-8")

# Controlled vocabularies — keep in sync with prompts/listing_parse.txt and the reach
# pre-filter in routes/internships.py. Out-of-vocab values are coerced to a safe default.
ROLE_CATEGORIES = {
    "software_engineering", "data_ml", "hardware_ee", "finance", "sales",
    "marketing", "recruiting", "product", "design", "other",
}
SPONSORSHIP_VALUES = {"offered", "not_offered", "unknown"}


# Career-portal URL shapes where the company is recoverable from the URL itself — used as a
# fallback when neither Haiku nor the stored `company` column yields a name (common for ATS
# boards + amazon.jobs, whose titles/snippets never repeat the company). Maps host -> the
# 1-based path segment holding the company slug.
_ATS_PATH_HOSTS = {
    "jobs.lever.co": 1,            # jobs.lever.co/<company>/<id>
    "boards.greenhouse.io": 1,    # boards.greenhouse.io/<company>/jobs/<id>
    "job-boards.greenhouse.io": 1,
    "jobs.ashbyhq.com": 1,        # jobs.ashbyhq.com/<company>/<id>
}
# Hosts that ARE the company (slug not in the path).
_DOMAIN_COMPANY = {
    "amazon.jobs": "Amazon",
    "www.amazon.jobs": "Amazon",
}


# Model-emitted stand-ins for "no company". Haiku sometimes writes one of these INTO the
# company field instead of leaving it blank, which would otherwise sail past the fallback
# chain as if it were a real name. Treated as missing (case-insensitive).
_PLACEHOLDER_COMPANIES = {
    "", "unknown", "n/a", "na", "none", "null", "not specified", "not available",
    "not provided", "company", "the company", "unknown company", "undisclosed",
    "confidential", "tbd",
}


def is_placeholder_company(v) -> bool:
    """True when `v` is missing or a model placeholder ('unknown', 'N/A', …) — i.e. NOT a
    usable company name, so the URL/Firecrawl fallback should run."""
    return not isinstance(v, str) or v.strip().lower() in _PLACEHOLDER_COMPANIES


def _slug_to_company(slug: str) -> str | None:
    slug = slug.strip().strip("-_")
    if not slug:
        return None
    return re.sub(r"[-_]+", " ", slug).title()  # "constellationspace"->"Constellationspace"


def company_from_url(url: str) -> str | None:
    """Deterministically recover the hiring company from known career-portal URL shapes
    (ATS slug in the path, or a company-specific host). None when the URL doesn't encode it
    (e.g. wellfound/workatastartup job-id URLs — the company lives behind the SPA wall)."""
    try:
        u = urlparse(url or "")
    except Exception:
        return None
    host = (u.netloc or "").lower()
    if host in _DOMAIN_COMPANY:
        return _DOMAIN_COMPANY[host]
    seg = _ATS_PATH_HOSTS.get(host)
    if seg is not None:
        parts = [p for p in u.path.split("/") if p]
        if len(parts) >= seg:
            return _slug_to_company(parts[seg - 1])
    return None


# SPA job boards whose company name is NOT in the snippet or the URL — it only renders on
# the page (e.g. wellfound shows "Neuralink" only in the live DOM). For these, neither Haiku
# nor company_from_url can recover it; a Firecrawl render can.
_FIRECRAWL_COMPANY_DOMAINS = ("wellfound.com", "workatastartup.com")


def needs_firecrawl_company(url: str, company: str | None) -> bool:
    """True when a row's company is still unresolved AND it's an SPA board where the company
    is only on the rendered page — the only case worth spending a Firecrawl render on."""
    if not is_placeholder_company(company):
        return False
    host = (urlparse(url or "").netloc or "").lower()
    return any(d in host for d in _FIRECRAWL_COMPANY_DOMAINS)


# Posted-date recovery from rendered markdown — the structured extract misses date_posted on
# some renders even when the page shows it ("Posted: 4 weeks ago"). Prefer a "posted … ago"
# phrase; fall back to a bare "<n> <unit> ago". Group 1 is the clean "<n> <unit> ago" (no prefix).
_POSTED_AGO_RE = re.compile(
    r"(?:re)?posted[\s:\-]*?(\d+\+?\s+(?:second|minute|hour|day|week|month|year)s?\s+ago)", re.I)
_BARE_AGO_RE = re.compile(r"\b(\d+\+?\s+(?:hour|day|week|month|year)s?\s+ago)\b", re.I)


def _posted_from_markdown(md: str) -> str | None:
    m = _POSTED_AGO_RE.search(md) or _BARE_AGO_RE.search(md)
    return m.group(1).strip() if m else None


# Hosts that are the JOB BOARD or a social/profile site — never the company's OWN site, so a
# company_website pointing here is rejected (we want the real domain, e.g. terminal.io).
_NON_COMPANY_HOSTS = (
    "wellfound.com", "angel.co", "workatastartup.com", "ycombinator.com",
    "linkedin.com", "twitter.com", "x.com", "facebook.com", "instagram.com",
    "github.com", "greenhouse.io", "lever.co", "ashbyhq.com", "crunchbase.com",
)


async def company_from_firecrawl(url: str) -> tuple[str | None, str | None, str | None, str | None]:
    """Render an SPA job page and pull (company, location, posted, logo_domain) from Firecrawl's
    JOB_SCHEMA extract — the only place these appear for wellfound/workatastartup listings (the
    posted date + the company's own website are rendered, never in the snippet). logo_domain is the
    registrable domain of the company's OWN website, used to fetch its real logo (the exact signal
    a name-search can't guess for a generic name like 'Terminal'). Firecrawl 'auto' proxy escalates
    past Cloudflare server-side when blocked. (None,)*4 on no key / any failure."""
    if not firecrawl.is_available():
        return None, None, None, None
    try:
        data = await firecrawl.scrape(url, "auto")
    except Exception:
        return None, None, None, None
    d = (data.get("data") or {}) if data else {}
    ex = d.get("extract") or {}

    def _clean(v):
        return v.strip() if isinstance(v, str) and v.strip() else None

    # Posted: structured extract first, else regex the rendered markdown (the extract misses it
    # on some renders even though the page shows it).
    posted = _clean(ex.get("date_posted")) or _posted_from_markdown(d.get("markdown") or "")
    # Company logo domain: from the company's OWN website, rejecting the job board / social links.
    logo_domain = registrable_domain(_clean(ex.get("company_website")))
    if logo_domain and any(logo_domain == h or logo_domain.endswith("." + h) for h in _NON_COMPANY_HOSTS):
        logo_domain = None
    return _clean(ex.get("company_name")), _clean(ex.get("location")), posted, logo_domain


def build_embed_text(row: dict) -> str:
    """Profile-independent text rendering of a listing for embedding. Built from the RAW
    row (company/title/location/snippet) so it's stable and matches the upsert content
    invalidation; independent of the parse output."""
    parts = [
        (row.get("company") or "").strip(),
        (row.get("search_title") or "").strip(),
        (row.get("verified_location") or "").strip(),
        " ".join((row.get("snippet") or "").split()),
    ]
    return " — ".join(p for p in parts if p)


def content_hash(text: str) -> str:
    """Stable short hash of the embed text the parse was keyed on."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


def _as_str(v, default: str = "") -> str:
    return v.strip() if isinstance(v, str) and v.strip() else default


def _resolve_company(haiku_company, listing: dict) -> str:
    """Company fallback chain: Haiku's answer -> stored `company` column -> recoverable from
    the URL (ATS slug / amazon.jobs) -> "Unknown". Placeholder strings ('unknown', 'N/A', …)
    at any step are skipped so a real name downstream can win (the wellfound/SPA Firecrawl
    rescue then runs separately in the worker for the remaining "Unknown"s)."""
    if not is_placeholder_company(haiku_company):
        return haiku_company.strip()
    col = listing.get("company")
    if not is_placeholder_company(col):
        return col.strip()
    return company_from_url(listing.get("url") or "") or "Unknown"


def _normalize_parsed(p: dict, listing: dict) -> dict:
    """Coerce the model's object into a complete, valid record with safe fallbacks so
    serving can build an Internship straight from it (display fields never null/empty)."""
    skills_raw = p.get("skills")
    skills = (
        [s.strip() for s in skills_raw if isinstance(s, str) and s.strip()][:8]
        if isinstance(skills_raw, list) else []
    )
    role = _as_str(p.get("role_category"), "other").lower()
    if role not in ROLE_CATEGORIES:
        role = "other"
    sponsorship = _as_str(p.get("sponsorship"), "unknown").lower()
    if sponsorship not in SPONSORSHIP_VALUES:
        sponsorship = "unknown"
    is_intern = p.get("is_internship")
    requires_phd = p.get("requires_phd")
    return {
        "title": _as_str(p.get("title"), _as_str(listing.get("search_title"), "Internship")),
        "company": _resolve_company(p.get("company"), listing),
        "company_description": _as_str(p.get("company_description")),
        "location": _as_str(
            p.get("location"), _as_str(listing.get("verified_location"), "Remote / Various")
        ),
        "skills": skills,
        "seniority": _as_str(p.get("seniority"), "unknown").lower(),
        "role_category": role,
        # Default True when unclear/missing — the serving pre-filter only DROPS on an
        # explicit False, so a parse miss never silently removes a real listing.
        "is_internship": is_intern if isinstance(is_intern, bool) else True,
        # Default False — the serving pre-filter DROPS on an explicit True (PhD-mandatory
        # roles are never eligible for this undergrad-intern audience); a parse miss is
        # additionally backstopped by a "PhD" title check at serve time.
        "requires_phd": requires_phd if isinstance(requires_phd, bool) else False,
        "sponsorship": sponsorship,
        # Drawer fact-grid display fields — "" when the listing doesn't state them (serving
        # maps "" → None so the frontend falls back to company name alone / a heuristic term).
        # posted_at from the snippet here; the Firecrawl SPA render (precompute) fills it for
        # wellfound/workatastartup rows, whose posted date is only on the rendered page.
        "term": _as_str(p.get("term")),
        "company_size": _as_str(p.get("company_size")),
        "posted_at": _as_str(p.get("posted_at")),
    }


def parse_listing_sync(listing: dict) -> dict | None:
    """Blocking Haiku call → normalized structured/display fields dict, or None on failure
    (the worker leaves the row unparsed to retry next run). Call via asyncio.to_thread."""
    user = (
        f"Bucket: {listing.get('bucket') or '?'}\n"
        f"Company: {listing.get('company') or '?'}\n"
        f"Title: {listing.get('search_title') or '?'}\n"
        f"Verified location: {listing.get('verified_location') or '?'}\n"
        f"Snippet: {' '.join((listing.get('snippet') or '').split())}"
    )
    try:
        msg = ai.messages.create(
            model=MODEL_QUICK,
            max_tokens=420,  # bumped from 300 for the added term/company_size/posted_at fields
            temperature=0,  # Haiku accepts sampling params (only Opus 4.8 rejects them)
            system=_PARSE_SYSTEM,
            messages=[{"role": "user", "content": user}],
        )
        # Record spend the moment the call succeeds (before JSON parsing — we paid for the
        # tokens regardless). Tagged by the active cost_session: 'worker:ingest' for the
        # worker parse pass (excluded from the user-facing kill switch + capped separately),
        # the request session (/run, /internships/...) for the local live-fetch fallback.
        record_usage("listing-parse", MODEL_QUICK, msg.usage)
        raw = strip_fences(msg.content[0].text)
        parsed = parse_json_with_context(raw, "listing_parse")
        if isinstance(parsed, list):
            parsed = parsed[0] if parsed else None
        if not isinstance(parsed, dict):
            return None
        return _normalize_parsed(parsed, listing)
    except Exception as e:
        print(f"[listing_parse] ERROR url={listing.get('url')!r}: {e}")
        return None
