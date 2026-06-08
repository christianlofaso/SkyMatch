"""Profile-independent job-listing discovery, enrichment, and validation.

Relocated verbatim from routes/internships.py so both the live /internships/search
route AND the standalone ingestion worker (worker/ingest.py) can share them without
the worker importing the FastAPI router or the Anthropic client. internships.py
re-imports these names, so live serving behavior is unchanged.
"""
import asyncio
import html
import json
import os
import re
import urllib.parse

import httpx

from cache import (
    get_enrichment_cache, set_enrichment_cache,
    get_url_validation_cache, set_url_validation_cache,
)
from config.niches import WORKDAY_CONFIG
from lib import firecrawl
from schemas import ProfileAnalysis

# Per-query DDG timeout. DDGS is synchronous, not thread-safe, and can hang for MINUTES when
# rate-limited; without a bound one stuck query stalls the whole worker run. Each query thread
# is wrapped in asyncio.wait_for so a hung endpoint degrades to an empty result, not a hang.
_DDG_QUERY_TIMEOUT = int(os.getenv("DDG_QUERY_TIMEOUT_SEC", "20"))


async def _bounded_query(run_query, q: str) -> list[dict]:
    """Run a blocking DDG `run_query(q)` in a worker thread under a hard timeout.
    Timeout or error → empty list (same degradation as the existing per-query swallow).
    Note: wait_for can't kill the underlying thread, but it unblocks the gather so the
    run proceeds while the orphaned DDGS call finishes on its own."""
    try:
        return await asyncio.wait_for(asyncio.to_thread(run_query, q), timeout=_DDG_QUERY_TIMEOUT)
    except Exception as e:
        print(f"[ingest] DDG query bailed ({q!r}): {type(e).__name__}")
        return []


# Matches a numeric job ID (≥5 digits) or a UUID anywhere in a URL path
_JOB_ID_RE = re.compile(
    r"/(\d{5,}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
    re.IGNORECASE,
)

# Tokens to ignore when comparing expected vs ATS job titles
_TRIVIAL_TITLE_TOKENS = {
    "intern", "internship", "summer", "fall", "spring", "winter",
    "2024", "2025", "2026", "remote", "hybrid", "us", "usa",
    "the", "a", "an", "and", "or", "of", "for", "at", "in", "to",
}

# Companies known to use proprietary ATS — skip Greenhouse/Lever/Ashby lookup for these
_PROPRIETARY_ATS = {
    "google", "meta", "apple", "microsoft", "amazon", "netflix", "tesla",
    # LinkedIn's own jobs live on linkedin.com (a BLOCKED_DOMAIN); skip ATS lookup
    # so they fall through to no-URL rather than linking to the apply form.
    "linkedin",
}


# Non-proprietary big-tech companies with public greenhouse/lever/ashby ATS APIs.
# OpenAI omitted — their Greenhouse board returns no intern roles. (Workday-based big-tech
# companies live in config.niches.WORKDAY_CONFIG, fetched via _fetch_workday_listings.)
_BIGTECH_ATS_CONFIG = [
    ("Stripe",     "greenhouse", "stripe"),
    ("Databricks", "greenhouse", "databricks"),
    ("Palantir",   "lever",      "palantir"),
    ("Anthropic",  "greenhouse", "anthropic"),  # was ashby/"Anthropic" (404); Anthropic is on Greenhouse
    ("AppLovin",   "greenhouse", "applovin"),   # seasonal — board exists, 0 interns off-cycle
    # Snowflake removed — no public greenhouse/lever/ashby board (Workday); now via WORKDAY_CONFIG.
]


# Job boards we accept as fallbacks (ordered by quality)
TRUSTED_BOARDS = [
    "greenhouse.io", "lever.co", "workday.com", "icims.com",
    "myworkdayjobs.com", "taleo.net", "smartrecruiters.com",
    "builtinchicago.org", "builtin.com",
    "wellfound.com", "workatastartup.com",
    "indeed.com", "ziprecruiter.com", "glassdoor.com",
]

# Domains we always skip
BLOCKED_DOMAINS = ["linkedin.com", "facebook.com", "twitter.com", "instagram.com"]

# These domains use JS rendering or login walls — skip body checks (rules 5+6).
# The HEAD check (rules 3+4) + job-ID gate (rule 2) are sufficient trust signals.
# myworkdayjobs.com: a React SPA with no title in the server HTML, but its listings come
# from the authoritative CXS feed (a closed job leaves the feed and is pruned), so the feed
# itself is the liveness signal — skip the body-token check, just confirm the URL resolves.
SKIP_BODY_CHECK_DOMAINS = {"workatastartup.com", "wellfound.com", "myworkdayjobs.com"}

# Career sites that render in a JS SPA: a server-side fetch sees only a generic
# shell, so HEAD/body checks can't tell an open listing from a closed one.
# validate_job_url() routes these through a Firecrawl-rendered liveness check.
# Extend this set as new SPA/Eightfold ATS domains surface.
_SPA_CAREER_DOMAINS = {
    "jobs.careers.microsoft.com",
    "careers.microsoft.com",
    "jobs.nvidia.com",          # Eightfold SPA — serves a generic hub shell server-side
}

# Big-tech career SPAs that render sticky nav/footer with 3+ "Apply Now" buttons
# on every single-listing page. Skip body-level apply_count check in _enrich_listing
# to prevent false-positive category-page detection.
_ENRICH_SKIP_BODY_DOMAINS = frozenset({
    "careers.google.com",
    "metacareers.com",
    "jobs.apple.com",
    "amazon.jobs",
})

# workatastartup.com returns 406 to httpx's default Accept: */* — browser-like
# headers are required to get real 200 responses with SSR content.
_WORKATASTARTUP_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}

# Strings that indicate a job listing is no longer active
CLOSED_STRINGS = [
    # Original
    "no longer available",
    "this job has closed",
    "position has been filled",
    "no longer accepting applications",
    "page not found",
    "job not found",
    "this position is no longer open",
    # Additional ATS patterns
    "this role is no longer",
    "this position has been filled",
    "applications are closed",
    "this job is no longer",
    "listing has expired",
    "this posting has been removed",
    "job posting has been removed",
    "no longer accepting",
    "role has been filled",
    "this position is closed",
    "posting is no longer active",
    "sorry, this job",
    "we've filled this role",
    "this opportunity is no longer",
]

# Sentinel titles a Firecrawl extractor returns for a dead/missing SPA listing
# (e.g. jobs.nvidia.com renders a "Not Found" shell). Matched against the
# extracted job_title in _firecrawl_job_alive → drop.
_DEAD_TITLE_SENTINELS = ("not found", "no longer", "page not found", "404")


_KNOWN_METROS = {
    "chicago", "new york", "new york city", "nyc", "san francisco", "sf",
    "los angeles", "la", "seattle", "boston", "austin", "denver", "atlanta",
    "miami", "washington", "philadelphia", "houston", "phoenix", "portland",
    "minneapolis", "detroit", "pittsburgh", "raleigh", "dallas", "san diego",
    "san jose", "salt lake city", "orlando", "nashville", "charlotte",
    "columbus", "columbus, oh", "madison", "madison, wi", "indianapolis", "indy",
    "kansas city", "kc",
}

# Every value MUST be in config.niches.SEED_METROS so the location resolves to a
# pre-ingested (index-served) metro instead of a request-time live-fetch. Covers all 50
# states + DC; college towns route to their nearest seeded hub via this fallback.
_STATE_FALLBACK: dict[str, str] = {
    "AL": "Atlanta",        "AK": "Seattle",        "AZ": "Phoenix",
    "AR": "Dallas",         "CA": "San Francisco",  "CO": "Denver",
    "CT": "New York",       "DC": "Washington",     "DE": "Philadelphia",
    "FL": "Miami",          "GA": "Atlanta",        "HI": "Los Angeles",
    "IA": "Chicago",        "ID": "Salt Lake City", "IL": "Chicago",
    "IN": "Indianapolis",   "KS": "Kansas City",    "KY": "Nashville",
    "LA": "Houston",        "MA": "Boston",         "MD": "Washington",
    "ME": "Boston",         "MI": "Detroit",        "MN": "Minneapolis",
    "MO": "Kansas City",    "MS": "Atlanta",        "MT": "Salt Lake City",
    "NC": "Charlotte",      "ND": "Minneapolis",    "NE": "Kansas City",
    "NH": "Boston",         "NJ": "New York",       "NM": "Phoenix",
    "NV": "Phoenix",        "NY": "New York",       "OH": "Columbus",
    "OK": "Dallas",         "OR": "Portland",       "PA": "Philadelphia",
    "RI": "Boston",         "SC": "Charlotte",      "SD": "Minneapolis",
    "TN": "Nashville",      "TX": "Austin",         "UT": "Salt Lake City",
    "VA": "Washington",     "VT": "Boston",         "WA": "Seattle",
    "WI": "Madison",        "WV": "Pittsburgh",     "WY": "Denver",
}

_BUILTIN_DOMAINS: dict[str, str] = {
    "Chicago": "builtinchicago.org",
    "New York": "builtinnyc.com",
    "San Francisco": "builtinsf.com",
    "Seattle": "builtinseattle.com",
    "Boston": "builtinboston.com",
    "Austin": "builtinaustin.com",
    "Denver": "builtincolorado.com",
    "Los Angeles": "builtinla.com",
    "Atlanta": "builtinatlanta.com",
}


_CATEGORY_TITLE_TRIGGERS = frozenset({
    "opportunities",
    "internship program",
    "multiple positions",
    "various roles",
})

_METRO_ACCEPTED: dict[str, frozenset[str]] = {
    "Chicago": frozenset({
        "chicago", "illinois", ", il", "evanston", "naperville",
        "oak park", "schaumburg", "wasco", "downers grove", "rosemont",
        "oak brook", "lisle", "lombard",
    }),
    "New York": frozenset({
        "new york", ", ny", "nyc", "brooklyn", "manhattan",
        "jersey city", "hoboken", "newark",
    }),
    "San Francisco": frozenset({
        "san francisco", "bay area", "san jose", "oakland",
        "berkeley", "palo alto", "mountain view", "sunnyvale",
    }),
    "Seattle": frozenset({"seattle", ", wa", "bellevue", "kirkland", "redmond"}),
    "Boston": frozenset({"boston", ", ma", "cambridge", "somerville"}),
    # NOTE: no bare ", st" for states with MULTIPLE seeded metros (CA/TX/FL/NC/PA) — it would
    # pull a sibling metro's listings into this pool. Use city + named suburbs there instead.
    "Austin": frozenset({"austin", "round rock", "cedar park", "pflugerville"}),
    "Denver": frozenset({"denver", ", co", "boulder"}),
    "Atlanta": frozenset({"atlanta", ", ga"}),
    "Los Angeles": frozenset({"los angeles", "santa monica", "culver city", "el segundo", "pasadena"}),
    "Miami": frozenset({"miami", "miami beach", "coral gables", "fort lauderdale", "boca raton"}),
    "Washington": frozenset({
        "washington", ", dc", "d.c.", "arlington, va", "alexandria, va",
        "bethesda", "rockville", "reston", "mclean", "tysons",
    }),
    "Philadelphia": frozenset({"philadelphia", "philly", "king of prussia", "conshohocken", "malvern"}),
    "Houston": frozenset({"houston", "the woodlands", "sugar land", "katy"}),
    "Phoenix": frozenset({"phoenix", ", az", "tempe", "scottsdale", "chandler", "mesa"}),
    "Portland": frozenset({"portland, or", ", or", "beaverton", "hillsboro", "lake oswego", "tigard"}),
    "Minneapolis": frozenset({"minneapolis", ", mn", "saint paul", "st. paul", "st paul", "bloomington, mn"}),
    "Detroit": frozenset({"detroit", ", mi", "ann arbor", "dearborn", "troy", "royal oak"}),
    "Pittsburgh": frozenset({"pittsburgh", "carnegie mellon", "oakland, pa"}),
    "Raleigh": frozenset({"raleigh", "durham", "chapel hill", "cary", "research triangle", "rtp", "morrisville"}),
    "Dallas": frozenset({"dallas", "plano", "irving", "fort worth", "richardson", "addison", "frisco"}),
    "San Diego": frozenset({"san diego", "la jolla", "carlsbad"}),
    "San Jose": frozenset({"san jose", "santa clara", "sunnyvale", "mountain view", "cupertino", "milpitas"}),
    "Salt Lake City": frozenset({"salt lake city", ", ut", "provo", "lehi", "draper", "south jordan", "orem"}),
    "Orlando": frozenset({"orlando", "winter park", "lake mary", "maitland"}),
    "Nashville": frozenset({"nashville", ", tn", "franklin, tn", "brentwood, tn"}),
    "Charlotte": frozenset({"charlotte", "concord, nc", "huntersville"}),
    "Columbus": frozenset({"columbus, oh", ", oh", "dublin, oh", "westerville"}),
    "Madison": frozenset({"madison, wi", ", wi", "middleton"}),
    "Indianapolis": frozenset({"indianapolis", ", in", "carmel, in", "fishers", "indy"}),
    "Kansas City": frozenset({"kansas city", ", ks", ", mo", "overland park", "olathe"}),
}

_REMOTE_INDICATORS = frozenset({"remote", "anywhere", "distributed", "work from home", "wfh"})


def _parse_metro(location: str) -> str:
    """Normalize a location string to a known metro name for local job searches.

    "Greater Chicago Area" → "Chicago"  (LinkedIn format)
    "Champaign, IL"        → "Chicago"  (state fallback)
    "Chicago, IL"          → "Chicago"  (direct match)
    "Wasco, IL"            → "Chicago"  (state fallback)
    """
    loc = location.strip()
    loc_lower = loc.lower()

    # LinkedIn "Greater X Area" format — very common profile location string
    if loc_lower.startswith("greater ") and loc_lower.endswith(" area"):
        city_raw = loc[8:-5].strip()  # "Greater Chicago Area" → "Chicago"
        return city_raw

    parts = [p.strip() for p in loc.split(",")]
    city_raw = parts[0] if parts else loc
    if city_raw.lower() in _KNOWN_METROS:
        return city_raw
    state = parts[-1].strip().upper() if len(parts) > 1 else ""
    if state in _STATE_FALLBACK:
        return _STATE_FALLBACK[state]
    return city_raw


# Non-US location tokens for the big_tech location gate (Fix: international-role dilution).
# The national big_tech pool is served to US students, but Workday's CXS feed returns plenty
# of overseas intern roles (Intel Costa-Rica/Malaysia, Analog Devices Philippines/Thailand) —
# genuine non-fits that score below 50. We can't enumerate every US location, so the heuristic
# is INVERTED: drop only on an EXPLICIT non-US signal, keep everything ambiguous. Country names
# are the reliable signal — Workday's `locationsText` includes the country for foreign roles
# ("Cavite, Philippines"); a few unambiguous foreign tech hubs are added for feeds that omit it.
# Erring toward KEEP avoids nuking valid US rows whose location is "Multiple Locations" / a bare
# city. US-city collisions (Manchester, Birmingham, ...) are deliberately NOT listed — relying on
# the country token, not the city, prevents false drops. Matched word-boundaried, lowercased.
_NON_US_TOKENS: frozenset[str] = frozenset({
    # Countries
    "india", "china", "malaysia", "philippines", "thailand", "vietnam", "indonesia",
    "singapore", "japan", "korea", "south korea", "taiwan", "hong kong",
    "canada", "mexico", "brazil", "argentina", "chile", "colombia", "costa rica",
    "united kingdom", "england", "scotland", "ireland", "france", "germany", "spain",
    "italy", "netherlands", "belgium", "switzerland", "sweden", "norway", "denmark",
    "finland", "poland", "austria", "portugal", "czech", "romania", "hungary",
    "israel", "turkey", "egypt", "saudi arabia", "united arab emirates", "uae",
    "australia", "new zealand", "south africa", "nigeria", "kenya",
    # Unambiguous foreign tech hubs (for feeds that omit the country)
    "bengaluru", "bangalore", "hyderabad", "pune", "gurgaon", "gurugram", "noida",
    "chennai", "mumbai", "delhi", "shanghai", "beijing", "shenzhen", "guangzhou",
    "penang", "kulim", "cavite", "manila", "bangkok", "ho chi minh", "hanoi",
    "tel aviv", "haifa", "zurich", "geneva", "munich", "berlin", "dublin", "cork",
    "toronto", "vancouver", "montreal", "ottawa", "taipei", "hsinchu",
    "seoul", "tokyo", "osaka", "sydney", "melbourne", "guadalajara", "sao paulo",
})
_NON_US_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(t) for t in _NON_US_TOKENS) + r")\b", re.IGNORECASE,
)
# Positive US signal — overrides a non-US token match so a US city that happens to share a name
# with a foreign hub (Dublin CA, Vancouver WA, Paris TX, Berlin CT) is KEPT. Two forms only, both
# unambiguous: a comma-anchored 2-letter state code ("Santa Clara, CA") and an explicit country
# name. The comma anchor is deliberate — a bare 2-letter scan would misread "Dublin OR London" as
# Oregon. (Full state names like "Texas" are not matched; the ", TX" form is what feeds emit.)
_US_SIGNAL_RE = re.compile(
    r",\s*(?:" + "|".join(_STATE_FALLBACK.keys()) + r")\b"
    r"|\b(?:united states|u\.?\s?s\.?\s?a)\b",
    re.IGNORECASE,
)


def _is_us_location(loc: str | None) -> bool:
    """Heuristic US-location gate for the national big_tech pool. Order: empty/ambiguous → keep;
    an explicit US signal (", ST" / "United States") → keep even if a foreign city token also
    matches; an explicit non-US token (see _NON_US_TOKENS) → drop; otherwise → keep. Deliberately
    permissive — better to serve a rare ambiguous foreign role than to drop valid US rows whose
    location string is vague."""
    if not loc or not loc.strip():
        return True
    if _US_SIGNAL_RE.search(loc):
        return True
    return not _NON_US_RE.search(loc)


def _is_category_title(title: str) -> bool:
    """Return True if title describes a multi-role category page, not a specific role.

    Fires when a trigger phrase is present AND neither "Intern" nor "Internship"
    appears as a standalone word — those signal a concrete role designation.

    "Software Engineer Intern, Summer 2026 Program"   → False  (has standalone Intern)
    "Software Engineering Internship, Summer 2026"    → False  (has standalone Internship)
    "Software Engineering: Internship Opportunities"  → False  (Internship present)
    "Multiple Engineering Opportunities"              → True   (no Intern/Internship)
    "Fall 2026 Annapurna Labs at AWS Internship"      → False  (no trigger phrase)
    """
    t = title.lower()
    if not any(trigger in t for trigger in _CATEGORY_TITLE_TRIGGERS):
        return False
    return not bool(re.search(r"\bIntern(?:ship)?\b", title, re.IGNORECASE))


def _location_matches_metro(verified_location: str | None, metro: str) -> bool:
    """Return True if verified_location is within the given metro area.

    None → False (cannot verify; caller should drop from local bucket).
    Remote indicators → always False.
    Falls back to substring match on metro name for unlisted metros.
    """
    if verified_location is None:
        return False
    loc = verified_location.lower()
    if any(ind in loc for ind in _REMOTE_INDICATORS):
        return False
    accepted = _METRO_ACCEPTED.get(metro)
    if accepted:
        return any(a in loc for a in accepted)
    return metro.lower() in loc


def _company_slug(company: str) -> str:
    """Turn 'Morningstar' into 'morningstar' for domain matching."""
    return re.sub(r"[^a-z0-9]", "", company.lower())


def _to_slugs(company: str) -> list[str]:
    """Generate ATS slug variations to try for a company name.

    Examples:
      "Sprout Social"      → ["sproutsocial", "sprout-social", "sprout"]
      "Anduril Industries" → ["anduril", "anduril-industries"]
      "Two Sigma"          → ["twosigma", "two-sigma", "two"]
    """
    base = company.lower()
    for suffix in (" technologies", " tech", " systems", " industries",
                   " solutions", " inc", " corp", " llc", " ltd", " group", " ai"):
        if base.endswith(suffix):
            base = base[: -len(suffix)].strip()

    clean = re.sub(r"[^a-z0-9\s]", "", base).strip()
    parts = clean.split()
    slugs: list[str] = []
    if parts:
        slugs += ["".join(parts), "-".join(parts), parts[0]]

    # Also try original without suffix removal (catches "openai", "palantir", etc.)
    orig = re.sub(r"[^a-z0-9]", "", company.lower())
    slugs.append(orig)

    seen: set[str] = set()
    return [s for s in slugs if s and not (s in seen or seen.add(s))]  # type: ignore[func-returns-value]


def _best_intern_match(
    jobs: list[dict], title_key: str, url_key: str, expected_title: str
) -> str | None:
    """Return the URL of the best-matching internship from an ATS job list.

    Filters for roles with 'intern' in the title, scores by non-trivial token
    overlap with the expected title. Returns None if no candidate has any
    meaningful overlap (prevents linking a supply-chain job for 'Engineering Intern').
    """
    candidates = [j for j in jobs if "intern" in j.get(title_key, "").lower()]
    if not candidates:
        return None

    exp_tokens = (
        set(re.sub(r"[^\w\s]", " ", expected_title.lower()).split())
        - _TRIVIAL_TITLE_TOKENS
    )

    def overlap(j: dict) -> int:
        t = (
            set(re.sub(r"[^\w\s]", " ", j.get(title_key, "").lower()).split())
            - _TRIVIAL_TITLE_TOKENS
        )
        return len(exp_tokens & t)

    best = max(candidates, key=overlap)
    # If no meaningful token overlap, don't risk linking the wrong role
    if exp_tokens and overlap(best) == 0:
        return None
    return best.get(url_key)


async def _find_via_ats(title: str, company: str) -> str | None:
    """Try Greenhouse, Lever, Ashby public APIs for a real internship listing.

    Returns the first specific listing URL found, or None if not on any of these platforms.
    Skips companies known to use proprietary ATS systems.
    """
    if re.sub(r"[^a-z]", "", company.lower()) in _PROPRIETARY_ATS:
        return None  # proprietary ATS — DuckDuckGo fallback will handle these

    slugs = _to_slugs(company)

    async def _greenhouse(client: httpx.AsyncClient, slug: str) -> str | None:
        r = await client.get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs")
        if r.status_code != 200:
            return None
        jobs_list = r.json().get("jobs", [])
        url = _best_intern_match(jobs_list, "title", "absolute_url", title)
        if not url:
            return None
        # Greenhouse absolute_url is the company's own redirect URL; the job ID is often
        # in ?gh_jid= (query string), which _JOB_ID_RE misses. Use the canonical board URL
        # instead so the numeric ID is always in the path.
        matched = next((j for j in jobs_list if j.get("absolute_url") == url), None)
        if matched and matched.get("id"):
            url = f"https://boards.greenhouse.io/{slug}/jobs/{matched['id']}"
        return url

    async def _lever(client: httpx.AsyncClient, slug: str) -> str | None:
        r = await client.get(f"https://api.lever.co/v0/postings/{slug}?mode=json")
        if r.status_code != 200:
            return None
        return _best_intern_match(r.json(), "text", "hostedUrl", title)

    async def _ashby(client: httpx.AsyncClient, slug: str) -> str | None:
        r = await client.get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}")
        if r.status_code != 200:
            return None
        return _best_intern_match(r.json().get("jobPostings", []), "title", "jobUrl", title)

    # Fire every (slug, provider) lookup CONCURRENTLY at a short timeout, then pick the
    # highest-priority hit deterministically: earliest slug, then greenhouse > lever > ashby.
    # Previously these ran sequentially at 6s/call → up to len(slugs)*3*6s (~54s for a
    # 3-slug company when an ATS endpoint hangs), which was the stage-3 latency tail.
    providers = [("greenhouse", _greenhouse), ("lever", _lever), ("ashby", _ashby)]
    combos = [
        (si, pi, name, slug, fn)
        for si, slug in enumerate(slugs)
        for pi, (name, fn) in enumerate(providers)
    ]

    async def _try(fn, client, slug) -> str | None:
        try:
            return await fn(client, slug)
        except Exception:
            return None

    async with httpx.AsyncClient(timeout=4, follow_redirects=True) as client:
        results = await asyncio.gather(
            *[_try(fn, client, slug) for (_si, _pi, _name, slug, fn) in combos]
        )

    best: str | None = None
    best_key: tuple[int, int] | None = None
    best_name = best_slug = ""
    for (si, pi, name, slug, _fn), url in zip(combos, results):
        if url and (best_key is None or (si, pi) < best_key):
            best_key, best, best_name, best_slug = (si, pi), url, name, slug
    if best:
        print(f"[ats] {best_name} slug={best_slug} url={best}")
        return best
    return None


# Max chars of a fetched JD body we keep in `snippet` for the parse pass. The body is the
# richest signal for skill extraction (most big_tech rows otherwise carry only a location
# string → Haiku finds no skills). Bounded so the Haiku parse input + Voyage embed stay cheap;
# the top of a JD (responsibilities + qualifications) is where the skills are.
_BODY_MAX_CHARS = 3000


def _html_to_text(raw: str | None) -> str | None:
    """Strip an HTML JD body (Greenhouse `content`, Workday `jobDescription`) to bounded plain
    text suitable for the listing parser. Drops script/style, unescapes entities, collapses all
    whitespace (incl. the \\xa0 nbsp Workday emits). None when there's nothing usable."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    # Unescape FIRST: Greenhouse `content` is HTML-ESCAPED (&lt;h2&gt;…), so tag-stripping before
    # unescape would no-op and leave the tags after a later unescape. Workday/Lever HTML is
    # literal, where unescape-first is a harmless no-op on the tags. Then strip, then collapse.
    text = html.unescape(raw)
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = " ".join(text.split())
    return text[:_BODY_MAX_CHARS] or None


async def _enrich_listing(listing: dict, sem: asyncio.Semaphore) -> dict:
    """Enrich a scraped listing with verified_location and is_category_page.

    Returns the listing dict augmented with:
      verified_location: str | None  — authoritative location from ATS API or JSON-LD
      is_category_page: bool         — True if the listing is a multi-role landing page

    Never raises. On failure, returns verified_location=None, is_category_page as detected
    from title/URL (which may still be True if the title triggered detection).
    Results are cached for 24 h via enrichment_cache.
    """
    url = listing["url"]

    cached = get_enrichment_cache(url)
    if cached is not None:
        return {**listing, **cached}

    async with sem:
        parsed = urllib.parse.urlparse(url)
        host = parsed.netloc.lower()

        verified_location: str | None = None
        # JD body captured from the source API → stored into `snippet` so the parse pass has real
        # text to extract skills from (most big_tech rows otherwise carry only a location string).
        jd_body: str | None = None
        is_category_page = _is_category_title(listing.get("search_title", ""))

        # URL-structure category signals — no HTTP needed
        path_lower = parsed.path.lower()
        query_lower = (parsed.query or "").lower()
        if any(p in path_lower for p in ("/category/", "/categories/", "/search")):
            is_category_page = True
        if any(k in query_lower for k in ("category=", "keywords=")):
            is_category_page = True

        # ── Greenhouse: public JSON API ───────────────────────────────────
        if "greenhouse.io" in host:
            parts = [p for p in parsed.path.split("/") if p]
            if len(parts) >= 3 and parts[1] == "jobs":
                slug, job_id = parts[0], parts[2]
                try:
                    async with httpx.AsyncClient(timeout=8) as client:
                        r = await client.get(
                            f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs/{job_id}"
                        )
                        if r.status_code == 200:
                            data = r.json()
                            verified_location = (data.get("location") or {}).get("name")
                            jd_body = _html_to_text(data.get("content"))  # HTML-escaped JD
                except Exception:
                    pass

        # ── Lever: public JSON API ────────────────────────────────────────
        elif "lever.co" in host:
            parts = [p for p in parsed.path.split("/") if p]
            if len(parts) >= 2:
                slug, uuid = parts[0], parts[1]
                try:
                    async with httpx.AsyncClient(timeout=8) as client:
                        r = await client.get(
                            f"https://api.lever.co/v0/postings/{slug}/{uuid}?mode=json"
                        )
                        if r.status_code == 200:
                            data = r.json()
                            verified_location = (data.get("categories") or {}).get("location")
                            # Lever ships both; descriptionPlain is already plain text.
                            jd_body = data.get("descriptionPlain") or _html_to_text(data.get("description"))
                except Exception:
                    pass

        # ── Workday: public CXS JSON API (the page GET is a useless JS shell) ──
        elif "myworkdayjobs.com" in host:
            # Reconstruct the CXS detail endpoint from the public URL:
            #   https://{tenant}.{wdN}.myworkdayjobs.com/{siteId}{/job/...}
            #   → https://{tenant}.{wdN}.myworkdayjobs.com/wday/cxs/{tenant}/{siteId}{/job/...}
            # jobPostingInfo carries the full HTML jobDescription + a clean location. Without
            # this, Workday rows parse from the title alone → no skills (the biggest skill-less
            # big_tech source). The fetcher left locationsText in `snippet` as a location fallback.
            parts = [p for p in parsed.path.split("/") if p]
            tenant = host.split(".")[0]
            if parts and tenant:
                site_id, ext = parts[0], "/" + "/".join(parts[1:])
                detail = f"https://{host}/wday/cxs/{tenant}/{site_id}{ext}"
                try:
                    async with httpx.AsyncClient(timeout=10) as client:
                        r = await client.get(detail, headers={"Accept": "application/json"})
                        if r.status_code == 200:
                            info = (r.json() or {}).get("jobPostingInfo") or {}
                            jd_body = _html_to_text(info.get("jobDescription"))
                            loc = info.get("location")
                            if isinstance(loc, str) and loc.strip():
                                verified_location = loc.strip()
                except Exception:
                    pass
            if not verified_location:  # detail failed — keep the fetcher's locationsText
                verified_location = (listing.get("snippet") or "").strip() or None

        # ── All other domains: GET + JSON-LD + body signals ──────────────
        else:
            try:
                async with httpx.AsyncClient(
                    timeout=10, follow_redirects=True,
                    headers={"User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    )},
                ) as client:
                    r = await client.get(url)
                    if r.status_code < 400:
                        body = r.text
                        body_lower = body.lower()

                        # Category signals from body — skip for SPAs that render
                        # sticky nav/footer with multiple Apply buttons on every page.
                        if not is_category_page and not any(
                            d in host for d in _ENRICH_SKIP_BODY_DOMAINS
                        ):
                            apply_count = (
                                body_lower.count("apply now")
                                + body_lower.count('"apply"')
                                + body_lower.count(">apply<")
                            )
                            if apply_count >= 3:
                                is_category_page = True
                            for phrase in (
                                "explore our open roles", "view all positions",
                                "browse opportunities", "view open positions",
                                "browse all jobs",
                            ):
                                if phrase in body_lower:
                                    is_category_page = True
                                    break

                        # JSON-LD JobPosting schema — works for Ashby, Built In, etc.
                        ld_match = re.search(
                            r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>'
                            r'(.*?)</script>',
                            body, re.DOTALL | re.IGNORECASE,
                        )
                        if ld_match and not verified_location:
                            try:
                                ld = json.loads(ld_match.group(1))
                                if isinstance(ld, list):
                                    ld = next(
                                        (x for x in ld if x.get("@type") == "JobPosting"),
                                        {}
                                    )
                                if ld.get("@type") == "JobPosting":
                                    job_loc = ld.get("jobLocation") or {}
                                    if isinstance(job_loc, list):
                                        job_loc = job_loc[0] if job_loc else {}
                                    addr = job_loc.get("address") or {}
                                    city_part = addr.get("addressLocality", "")
                                    state_part = addr.get("addressRegion", "")
                                    if city_part or state_part:
                                        verified_location = ", ".join(
                                            p for p in [city_part, state_part] if p
                                        )
                            except Exception:
                                pass
            except Exception:
                pass

        enriched = {
            "verified_location": verified_location,
            "is_category_page": is_category_page,
        }
        # Replace the location-only snippet with the JD body when we captured one, so the parse
        # pass (which reads `snippet`) can extract skills, and the embedding is richer. Cached in
        # the enriched payload so it survives the merge below AND re-applies on a cache hit. When
        # no body was found, the key is omitted and the original snippet flows through unchanged.
        if jd_body:
            enriched["snippet"] = jd_body
        set_enrichment_cache(url, enriched)
        return {**listing, **enriched}


async def _scrape_startup_listings(profile: ProfileAnalysis) -> list[dict]:
    """Search YC Work at a Startup and Wellfound for real open intern listings.

    Runs 6 DuckDuckGo site: queries concurrently (each in its own thread so
    DDGS blocking I/O doesn't block the event loop). Returns up to 30 unique
    listings whose URLs already contain a numeric job ID.
    """
    field = profile.field_of_interest
    major = profile.major or field
    skills = profile.technical_skills[:2]
    skill_str = " ".join(f'"{s}"' for s in skills) if skills else f'"{field}"'

    queries = [
        f'intern "{field}" site:workatastartup.com',
        f'intern "{major}" site:workatastartup.com',
        f'intern {skill_str} site:workatastartup.com',
        f'intern "{field}" site:wellfound.com/jobs',
        f'intern "{major}" site:wellfound.com/jobs',
        f'intern {skill_str} site:wellfound.com/jobs',
    ]

    def _run_query(q: str) -> list[dict]:
        try:
            from ddgs import DDGS
            hits = list(DDGS().text(q, max_results=10))
            results = []
            for r in hits:
                url = r.get("href", "")
                parsed = urllib.parse.urlparse(url)
                domain = parsed.netloc.lower()
                if "workatastartup.com" not in domain and "wellfound.com" not in domain:
                    continue
                if not _JOB_ID_RE.search(parsed.path):
                    continue
                results.append({
                    "url": url,
                    "search_title": r.get("title", ""),
                    "snippet": r.get("body", ""),
                })
            return results
        except Exception:
            return []

    all_batches = await asyncio.gather(*[_bounded_query(_run_query, q) for q in queries])

    seen: set[str] = set()
    listings: list[dict] = []
    for batch in all_batches:
        for item in batch:
            url = item["url"].rstrip("/")
            if url not in seen:
                seen.add(url)
                listings.append(item)
            if len(listings) >= 30:
                break

    print(f"[startup-listings] found {len(listings)} real listings from YC/Wellfound")
    return listings


# Match "intern" only as a whole word (+ "interns"/"internship"/"internships"), NOT as a
# substring of "Internal", "International", "Internals", etc. A plain `"intern" in title`
# check let "Internal Audit Lead" / "International Accounting" / "Database Engine Internals"
# through as fake internships — polluting both the reach and big-tech ATS pools.
_INTERN_TITLE_RE = re.compile(r"\bintern(?:ship)?s?\b", re.IGNORECASE)


def _is_intern_title(title: str) -> bool:
    return bool(_INTERN_TITLE_RE.search(title or ""))


# CS/engineering relevance allowlist for the Workday feed. Workday's searchText="intern" pulls
# a company's ENTIRE intern class (finance, marketing, HR, supply-chain, legal, comms, …), but
# the big_tech bucket is NOT off-field-filtered at serve time and is assumed field-curated. So
# keep only software/hardware/data/ML/EE-type roles at ingest — this both matches the product's
# CS/ECE audience and bounds the Haiku parse cost (fewer rows stored). Positive allowlist (not a
# denylist) since Workday off-field functions are too numerous to enumerate. Word-boundaried.
_TECH_INTERN_RE = re.compile(
    r"\b(software|engineer\w*|developer|hardware|firmware|embedded|silicon|asic|fpga|"
    r"verification|vlsi|systems?|security|devops|sre|cloud|infrastructure|computer|"
    r"electrical|electronics|data|machine\s+learning|\bml\b|\bai\b|robotics|backend|"
    r"frontend|full[-\s]?stack|platform|network\w*|database|\bqa\b|test|research\s+scientist|"
    r"applied\s+scientist|technical|programming|developer|analytics)\b",
    re.IGNORECASE,
)


def _is_tech_intern_title(title: str) -> bool:
    return bool(_TECH_INTERN_RE.search(title or ""))


# Workday's CXS `searchText` is honored by SOME tenants (results are pre-filtered to interns) but
# IGNORED by others (the endpoint returns the company's ENTIRE job board, unsorted). So we always
# client-filter titles, and bound BOTH the kept-results count AND the pages scanned — the latter
# stops us from paginating a 1000-job board for a company that has no current interns.
_WORKDAY_MAX_PER_COMPANY = 40   # max intern listings KEPT per company (caps index + Haiku cost)
_WORKDAY_MAX_PAGES = 10         # max CXS pages scanned per company (×20 jobs) — request bound


async def _fetch_workday_listings(
    config: list[tuple[str, str, str, str]] = WORKDAY_CONFIG,
) -> list[dict]:
    """Query Workday's public, unauthenticated CXS JSON API for intern listings.

    `config` is a list of (company, tenant, wdN, siteId) tuples. POSTs the CXS jobs endpoint
    with searchText="intern", paginates via offset, and returns intern listings in the same
    {url, search_title, snippet} shape as _fetch_ats_listings — so the downstream
    enrich/validate/store/parse chain is identical. Two filters are applied: _is_intern_title
    (Workday substring-matches "internal") and _is_tech_intern_title (CS/eng relevance — the
    big_tech bucket has no serve-time off-field filter). All companies run in parallel; per-company
    failures (a moved tenant/shard 404s, network blip) are swallowed so one bad tenant can't break
    the pass.
    """
    async def _fetch_one(company: str, tenant: str, wdn: str, site_id: str) -> list[dict]:
        results: list[dict] = []
        base = f"https://{tenant}.{wdn}.myworkdayjobs.com"
        endpoint = f"{base}/wday/cxs/{tenant}/{site_id}/jobs"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                offset = 0
                for _page in range(_WORKDAY_MAX_PAGES):
                    if len(results) >= _WORKDAY_MAX_PER_COMPANY:
                        break
                    r = await client.post(
                        endpoint,
                        headers={"Content-Type": "application/json", "Accept": "application/json"},
                        json={"appliedFacets": {}, "limit": 20, "offset": offset, "searchText": "intern"},
                    )
                    if r.status_code != 200:
                        break
                    data = r.json()
                    postings = data.get("jobPostings") or []
                    if not postings:
                        break
                    for p in postings:
                        title = (p.get("title") or "").strip()
                        if not _is_intern_title(title) or not _is_tech_intern_title(title):
                            continue
                        # Drop non-US roles: big_tech is a national pool served to US students,
                        # and the CXS feed is full of overseas interns. locationsText reliably
                        # carries the country for foreign roles (see _is_us_location).
                        if not _is_us_location(p.get("locationsText")):
                            continue
                        ext = p.get("externalPath") or ""
                        if not ext:
                            continue
                        # externalPath starts with "/job/..."; public URL = base/{siteId}{externalPath}
                        url = f"{base}/{site_id}{ext}"
                        results.append({
                            "url": url,
                            "search_title": f"{title} at {company}",
                            "snippet": p.get("locationsText") or "",
                        })
                        if len(results) >= _WORKDAY_MAX_PER_COMPANY:
                            break
                    total = data.get("total") or 0
                    offset += 20
                    if offset >= total:
                        break
        except Exception as e:
            print(f"[workday-ats] {company} error: {e}")
        print(f"[workday-ats] {company}/{tenant} -> {len(results)} intern listings")
        return results

    batches = await asyncio.gather(*[
        _fetch_one(c, t, w, s) for c, t, w, s in config
    ])
    seen: set[str] = set()
    listings: list[dict] = []
    for batch in batches:
        for item in batch:
            url = item["url"].rstrip("/")
            if url not in seen:
                seen.add(url)
                listings.append(item)
    print(f"[workday-ats] total: {len(listings)} listings across {len(config)} companies")
    return listings


async def _fetch_ats_listings(
    config: list[tuple[str, str, str]] = _BIGTECH_ATS_CONFIG,
) -> list[dict]:
    """Query public Greenhouse/Lever/Ashby APIs directly for intern listings.

    `config` is a list of (company, provider, slug) tuples — defaults to the big-tech
    set, but the ingestion worker passes its own elite/reach slug list. Returns all
    intern listings in {url, search_title, snippet} format — identical to DDG scrape
    output — so the downstream Claude annotation handles them the same way.
    All companies are queried in parallel; individual failures are swallowed.
    """
    async def _fetch_one(company: str, ats: str, slug: str) -> list[dict]:
        results = []
        try:
            async with httpx.AsyncClient(timeout=8, follow_redirects=True) as client:
                if ats == "greenhouse":
                    r = await client.get(
                        f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
                    )
                    if r.status_code == 200:
                        for job in r.json().get("jobs", []):
                            if not _is_intern_title(job.get("title", "")):
                                continue
                            job_id = job.get("id")
                            if not job_id:
                                continue
                            url = f"https://boards.greenhouse.io/{slug}/jobs/{job_id}"
                            results.append({
                                "url": url,
                                "search_title": f"{job['title']} at {company}",
                                "snippet": (job.get("location") or {}).get("name", ""),
                            })
                elif ats == "lever":
                    r = await client.get(
                        f"https://api.lever.co/v0/postings/{slug}?mode=json"
                    )
                    if r.status_code == 200:
                        for posting in r.json():
                            if not _is_intern_title(posting.get("text", "")):
                                continue
                            url = posting.get("hostedUrl", "")
                            if not url:
                                continue
                            results.append({
                                "url": url,
                                "search_title": f"{posting['text']} at {company}",
                                "snippet": (posting.get("categories") or {}).get("location", ""),
                            })
                elif ats == "ashby":
                    r = await client.get(
                        f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
                    )
                    if r.status_code == 200:
                        for posting in r.json().get("jobPostings", []):
                            if not _is_intern_title(posting.get("title", "")):
                                continue
                            url = posting.get("jobUrl", "")
                            if not url:
                                continue
                            results.append({
                                "url": url,
                                "search_title": f"{posting['title']} at {company}",
                                "snippet": posting.get("locationName", ""),
                            })
        except Exception as e:
            print(f"[bigtech-ats] {company} error: {e}")
        print(f"[bigtech-ats] {company}/{slug} → {len(results)} intern listings")
        return results

    batches = await asyncio.gather(*[
        _fetch_one(c, a, s) for c, a, s in config
    ])
    seen: set[str] = set()
    listings: list[dict] = []
    for batch in batches:
        for item in batch:
            url = item["url"].rstrip("/")
            if url not in seen:
                seen.add(url)
                listings.append(item)
    print(f"[bigtech-ats] total: {len(listings)} listings across {len(config)} companies")
    return listings


async def _fetch_bigtech_ats_listings(profile: ProfileAnalysis) -> list[dict]:
    """Thin back-compat wrapper for the live big-tech scrape (profile is unused — the listing
    set is fixed by _BIGTECH_ATS_CONFIG + WORKDAY_CONFIG). Preserves the original call signature
    so _scrape_bigtech_listings is unchanged. Gathers BOTH the greenhouse/lever/ashby ATS pool
    and the Workday CXS pool (the bulk of the mega-cap tech set); _scrape_bigtech_listings dedups
    the merged set by URL."""
    ats, workday = await asyncio.gather(
        _fetch_ats_listings(),
        _fetch_workday_listings(),
    )
    return ats + workday


async def _scrape_bigtech_listings(profile: ProfileAnalysis) -> list[dict]:
    """Search DDG for real internship listings on big-tech career pages, and query
    public ATS APIs directly for ATS-using big-tech companies.

    DDG: one query per company in its own asyncio.to_thread (DDGS is not thread-safe).
    ATS: concurrent Greenhouse/Lever/Ashby calls via _fetch_bigtech_ats_listings.
    Both run in parallel; ATS results are always appended even if DDG returns nothing.
    """
    field = profile.field_of_interest

    # Microsoft excluded: their career site is a JS SPA with no body-checkable responses,
    # and their URL format cannot distinguish single-role pages from category landing pages
    # (e.g., "Software Engineering: Internship Opportunities" has the same URL structure
    # as a real job). They appear in reach via Claude-generated suggestions.
    #
    # The per-company site: queries below MUST point at the domain where that company's board
    # actually lives, or DDG indexes nothing. Verified against each provider's public API:
    # OpenAI is on Ashby (NOT Greenhouse), Anthropic is on Greenhouse (NOT Ashby), and Snowflake
    # has no public ATS board at all (Workday/Eightfold) — its slot is reused for Cloudflare,
    # which does (mirrors the REACH_ATS_SLUGS fix). Keep these in sync with config/niches.py.
    queries = [
        f"site:careers.google.com/jobs/results/ intern {field} 2026",
        f"site:metacareers.com/v2/jobs/ intern {field} 2026",
        f"site:jobs.apple.com/en-us/details/ intern {field} 2026",
        f"site:amazon.jobs/en/jobs/ intern {field} 2026",
        f"site:boards.greenhouse.io/stripe intern {field}",
        f"site:boards.greenhouse.io/databricks intern {field}",
        f"site:jobs.lever.co/palantir intern {field}",
        f"site:jobs.ashbyhq.com/openai intern {field}",
        f"site:boards.greenhouse.io/anthropic intern {field}",
        f"site:boards.greenhouse.io/cloudflare intern {field}",
    ]

    def _run_query(q: str) -> list[dict]:
        try:
            from ddgs import DDGS
            hits = list(DDGS().text(q, max_results=8))
            results = []
            for r in hits:
                url = r.get("href", "")
                is_gen, _ = _is_generic_url(url)
                if not is_gen:
                    results.append({
                        "url": url,
                        "search_title": r.get("title", ""),
                        "snippet": r.get("body", ""),
                    })
            return results
        except Exception:
            return []

    ddg_gather = asyncio.gather(*[_bounded_query(_run_query, q) for q in queries])
    all_batches, ats_listings = await asyncio.gather(ddg_gather, _fetch_bigtech_ats_listings(profile))

    seen: set[str] = set()
    listings: list[dict] = []
    for batch in all_batches:       # DDG results (includes proprietary ATS companies)
        for item in batch:
            url = item["url"].rstrip("/")
            if url not in seen:
                seen.add(url)
                listings.append(item)
            if len(listings) >= 30:
                break

    for item in ats_listings:       # Direct ATS — always appended, no cap
        url = item["url"].rstrip("/")
        if url not in seen:
            seen.add(url)
            listings.append(item)

    print(f"[bigtech-listings] found {len(listings)} before enrichment "
          f"(ddg + {len(ats_listings)} direct ats)")
    enrich_sem = asyncio.Semaphore(8)
    enriched_all = await asyncio.gather(*[_enrich_listing(l, enrich_sem) for l in listings])
    listings = [l for l in enriched_all if not l["is_category_page"]]
    print(f"[bigtech-listings] after enrichment: {len(listings)} (dropped {len(enriched_all) - len(listings)} category pages)")
    return listings


async def _scrape_local_listings(profile: ProfileAnalysis) -> list[dict]:
    """Search DDG for real internship listings at companies near the student's metro.

    Runs ATS site: queries mentioning the city, plus a Built In city domain query
    if the metro is known. Each query runs in its own thread (DDGS thread-safety).
    Returns up to 30 unique listings.
    """
    city = _parse_metro(profile.location)
    field = profile.field_of_interest

    queries = [
        f'site:boards.greenhouse.io intern "{city}"',
        f'site:jobs.lever.co intern "{city}"',
        f'site:jobs.ashbyhq.com intern "{city}"',
        f'site:boards.greenhouse.io intern "{city}" {field}',
        f'site:jobs.lever.co intern "{city}" {field}',
    ]

    builtin_domain = _BUILTIN_DOMAINS.get(city)
    if builtin_domain:
        queries.append(f"site:{builtin_domain} intern {field}")
        queries.append(f"site:{builtin_domain} intern")

    def _run_query(q: str) -> list[dict]:
        try:
            from ddgs import DDGS
            hits = list(DDGS().text(q, max_results=10))
            results = []
            for r in hits:
                url = r.get("href", "")
                is_gen, _ = _is_generic_url(url)
                if not is_gen:
                    results.append({
                        "url": url,
                        "search_title": r.get("title", ""),
                        "snippet": r.get("body", ""),
                    })
            return results
        except Exception:
            return []

    all_batches = await asyncio.gather(*[_bounded_query(_run_query, q) for q in queries])

    seen: set[str] = set()
    listings: list[dict] = []
    for batch in all_batches:
        for item in batch:
            url = item["url"].rstrip("/")
            if url not in seen:
                seen.add(url)
                listings.append(item)
            if len(listings) >= 30:
                break

    print(f"[local-listings] city={city!r} found {len(listings)} before enrichment")
    enrich_sem = asyncio.Semaphore(8)
    enriched_all = await asyncio.gather(*[_enrich_listing(l, enrich_sem) for l in listings])
    listings = [
        l for l in enriched_all
        if not l["is_category_page"] and _location_matches_metro(l["verified_location"], city)
    ]
    print(
        f"[local-listings] after enrichment: {len(listings)} in {city!r} "
        f"(dropped {len(enriched_all) - len(listings)} — wrong location or category page)"
    )
    return listings


# ---------------------------------------------------------------------------
# DROP POLICY helpers
# ---------------------------------------------------------------------------

def _is_generic_url(url: str) -> tuple[bool, str]:
    """Return (is_generic, reason). Uses urllib.parse — no regex on raw string."""
    if not url:
        return True, "empty_url"
    try:
        parsed = urllib.parse.urlparse(url)
    except Exception:
        return True, "unparseable_url"

    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = parsed.path.rstrip("/").lower() or "/"

    # linkedin.com/company/*/jobs (no /view/ in path)
    if "linkedin.com" in host:
        if "/company/" in path and path.endswith("/jobs"):
            return True, "linkedin_company_jobs_page"
        if path in ("/", "/jobs"):
            return True, "linkedin_root"

    # amazon.jobs root (no /jobs/ subpath)
    if host == "amazon.jobs" and "/jobs/" not in parsed.path:
        return True, "amazon_jobs_root"

    # careers.google.com root
    if host == "careers.google.com" and path == "/":
        return True, "google_careers_root"

    # careers.{anything}.com root
    if host.startswith("careers.") and path == "/":
        return True, "careers_subdomain_root"

    # boards.greenhouse.io/{company} with no /jobs/{id}
    if "greenhouse.io" in host:
        parts = [p for p in parsed.path.split("/") if p]
        # Specific: /company/jobs/12345 → at least 3 non-empty parts, "jobs" present
        if len(parts) < 3 or "jobs" not in parts:
            return True, "greenhouse_board_no_listing"

    # jobs.lever.co/{company} with no posting slug
    if "lever.co" in host:
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) < 2:
            return True, "lever_board_no_listing"

    # Generic /careers page (path ends in /careers with nothing further)
    if path == "/careers" or path.endswith("/careers"):
        return True, "generic_careers_page"

    # Generic /jobs page (path ends in /jobs with nothing further)
    if path == "/jobs" or path.endswith("/jobs"):
        return True, "generic_jobs_page"

    # /job-search page
    if path.endswith("/job-search"):
        return True, "generic_job_search"

    # Application-form and post-application pages — the listing is the parent URL.
    # Lever: jobs.lever.co/{co}/{uuid}/apply
    # Greenhouse: boards.greenhouse.io/{co}/jobs/{id}/application
    #             boards.greenhouse.io/{co}/jobs/{id}/confirmation
    path_parts_raw = [p for p in parsed.path.split("/") if p]
    if path_parts_raw and path_parts_raw[-1].lower() in (
        "apply", "application", "applications", "confirmation"
    ):
        return True, "application_form_url"

    # Workday CXS job URLs (.../{siteId}/job/.../<Title>_JR12345) carry the job id as a
    # "_JR<digits>" suffix that _JOB_ID_RE (which wants /<5+ digits> or a UUID) doesn't match,
    # so they'd be wrongly dropped as "no_job_id_in_url". The "/job/" path segment is the
    # reliable Workday listing marker (the board root /{siteId} has no "/job/"). Accept it here;
    # validate_job_url confirms liveness for myworkdayjobs.com via the skip-body branch.
    if host.endswith("myworkdayjobs.com") and "/job/" in path:
        return False, ""

    # A real listing URL contains a numeric job ID (≥5 digits) or a UUID.
    # University landing pages, emerging-talent hubs, and internship overview pages
    # all have human-readable paths with no ID — drop them.
    if not _JOB_ID_RE.search(parsed.path):
        return True, "no_job_id_in_url"

    return False, ""


def _title_in_body(expected_title: str, body: str) -> bool:
    """Return True if ≥60% of title tokens (length ≥ 2) appear anywhere in the body."""
    def tokenize(s: str) -> list[str]:
        # Drop 1-char tokens (e.g. a stray "C"): they match almost any body and
        # inflate the score, letting generic SPA shells pass the title check.
        return [t for t in re.sub(r"[^\w\s]", " ", s.lower()).split() if len(t) > 1]

    tokens = tokenize(expected_title)
    if not tokens:
        return True
    body_lower = body.lower()
    matched = sum(1 for t in tokens if t in body_lower)
    return matched / len(tokens) >= 0.6


async def _firecrawl_job_alive(url: str, expected_title: str, proxy: str) -> tuple[bool, str]:
    """
    Liveness check for Cloudflare-walled / JS-SPA job pages that a plain httpx
    request can't read. Renders the page with Firecrawl (proxy="auto" — Firecrawl
    escalates past Cloudflare server-side when blocked) and inspects the RENDERED content.

    Policy: if Firecrawl can't render the page (no key / network error / empty),
    DROP — we never surface a link we couldn't actually confirm is live.
    Returns (is_valid, reason).
    """
    if not firecrawl.is_available():
        return False, "firecrawl_unavailable"
    try:
        data = await firecrawl.scrape(url, proxy)
    except httpx.RequestError:
        return False, "firecrawl_network_error"
    if not data or not data.get("success"):
        return False, "firecrawl_unrendered"

    payload  = data.get("data") or {}
    extract  = payload.get("extract") or {}
    markdown = payload.get("markdown") or ""
    md_lower = markdown.lower()

    # Rendered page explicitly says the listing is closed/gone → drop.
    for s in CLOSED_STRINGS:
        if s in md_lower:
            return False, f"closed: {s}"

    # Liveness signal = Firecrawl's FOCUSED extraction of the posting, NOT the raw
    # markdown. A dead SPA listing renders a huge generic hub shell (every other
    # job + theme config), so scanning the markdown false-matches generic title
    # tokens. The extractor instead reports the real title — or "Not Found" /
    # empty for a dead page (observed: jobs.nvidia.com → job_title="Not Found").
    job_title = (extract.get("job_title") or "").strip()
    jt_lower = job_title.lower()
    if not job_title or any(s in jt_lower for s in _DEAD_TITLE_SENTINELS):
        return False, "firecrawl_not_found"
    if _title_in_body(expected_title, job_title):
        return True, "pass_firecrawl"
    return False, "title_not_found_firecrawl"


async def validate_job_url(url: str | None, expected_title: str) -> tuple[bool, str]:
    """
    Full DROP POLICY check. Returns (is_valid, reason).
    Results are cached for 24 hours in url_validation_cache.
    Rules:
      1. Missing/empty URL → drop
      2. Generic URL pattern → drop (no HTTP call)
      3. HTTP status ≥ 400 → drop
      4. Final URL after redirects is generic → drop
      5. Page body contains a closed-listing string → drop
      6. Page body does not contain ≥70% of title tokens → drop
    """
    # Rule 1
    if not url:
        return False, "no_url"

    # Cache hit
    cached = get_url_validation_cache(url)
    if cached is not None:
        return bool(cached["is_valid"]), cached["reason"]

    # Rule 2
    is_generic, reason = _is_generic_url(url)
    if is_generic:
        set_url_validation_cache(url, False, reason)
        return False, reason

    # Pre-HTTP title check: drop category landing pages before any HTTP call.
    # Catches Microsoft-style "Software Engineering: Internship Opportunities" pages
    # even when the URL has a numeric ID and the domain is in _SPA_CAREER_DOMAINS.
    if _is_category_title(expected_title):
        set_url_validation_cache(url, False, "category_landing_title")
        return False, "category_landing_title"

    url_domain = urllib.parse.urlparse(url).netloc.lower()

    if "workatastartup.com" in url_domain:
        # Rails SSR app. Dead listings fall into two observed patterns:
        #   1. HTTP 404 — job record deleted ("Y Combinator | File Not Found")
        #   2. HTTP 200 after redirect to ycombinator.com/companies/<slug> — listing
        #      archived, redirected off-domain. Final URL has no job ID.
        # Live listings: HTTP 200, final URL stays on www.workatastartup.com.
        # Browser-like headers are required — site returns 406 to default Accept: */*.
        try:
            async with httpx.AsyncClient(
                follow_redirects=True, timeout=12, headers=_WORKATASTARTUP_HEADERS
            ) as client:
                resp = await client.get(url)
            if resp.status_code >= 400:
                reason = f"http_{resp.status_code}"
                set_url_validation_cache(url, False, reason)
                return False, reason
            final_domain = urllib.parse.urlparse(str(resp.url)).netloc.lower()
            if "workatastartup.com" not in final_domain:
                set_url_validation_cache(url, False, "redirect_off_domain")
                return False, "redirect_off_domain"
        except Exception:
            pass  # network error → accept, trust the job ID from rule 2
        set_url_validation_cache(url, True, "pass_skip_body")
        return True, "pass_skip_body"

    if url_domain.endswith("myworkdayjobs.com"):
        # Workday job pages are React SPAs (no title in server HTML → body-token check would
        # falsely drop them), but the CXS feed they came from is the authoritative liveness
        # signal (a closed job leaves the feed and is pruned). Skip the body check; one GET
        # confirms the URL still resolves. Mirror the workatastartup trusted-feed branch.
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=10) as client:
                resp = await client.get(url)
            if resp.status_code >= 400:
                reason = f"http_{resp.status_code}"
                set_url_validation_cache(url, False, reason)
                return False, reason
        except Exception:
            pass  # network error → accept, trust the CXS feed
        set_url_validation_cache(url, True, "pass_skip_body")
        return True, "pass_skip_body"

    if "wellfound.com" in url_domain:
        # Cloudflare 403s every plain client, and active vs. deleted listings look
        # identical to httpx. Render with Firecrawl auto (escalates past Cloudflare
        # server-side when blocked) and check the real page; drop if it can't be rendered.
        is_valid, reason = await _firecrawl_job_alive(url, expected_title, proxy="auto")
        set_url_validation_cache(url, is_valid, reason)
        return is_valid, reason

    if any(d in url_domain for d in _SPA_CAREER_DOMAINS):
        # JS-SPA career site — a server-side fetch sees only a generic shell, so
        # HEAD/body checks can't tell an open listing from a closed one. Render
        # with Firecrawl and check the rendered page; drop if it can't be rendered.
        is_valid, reason = await _firecrawl_job_alive(url, expected_title, proxy="auto")
        set_url_validation_cache(url, is_valid, reason)
        return is_valid, reason

    # Normalize www.boards.greenhouse.io → boards.greenhouse.io.
    # DDG occasionally returns URLs with an erroneous www. prefix on the
    # boards subdomain; that hostname doesn't resolve and causes HEAD to fail.
    normalized_url = url
    if url.startswith("https://www.boards.greenhouse.io/"):
        normalized_url = "https://boards.greenhouse.io/" + url[len("https://www.boards.greenhouse.io/"):]
    elif url.startswith("http://www.boards.greenhouse.io/"):
        normalized_url = "https://boards.greenhouse.io/" + url[len("http://www.boards.greenhouse.io/"):]

    # Rules 3 + 4: HEAD to check status and follow redirects cheaply
    final_url = normalized_url
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=10) as client:
            head_resp = await client.head(normalized_url)
            final_url = str(head_resp.url)

            if head_resp.status_code >= 400:
                reason = f"http_{head_resp.status_code}"
                set_url_validation_cache(url, False, reason)
                return False, reason

            if final_url != url:
                is_gen_final, reason_final = _is_generic_url(final_url)
                if is_gen_final:
                    # boards.greenhouse.io sometimes does an HTTP redirect to the
                    # company's own career page, where the job ID is in ?gh_jid=
                    # rather than the path. The Greenhouse API already confirmed
                    # this listing exists, so trust the redirect if gh_jid is present
                    # and continue to the body check on the redirect target.
                    if "boards.greenhouse.io" in url_domain:
                        # boards.greenhouse.io redirects to the company's own career
                        # page when they use a custom domain. Only ?gh_jid= proves the
                        # redirect target is a specific job page (Databricks-style).
                        # Path-only redirects (e.g., /careers/open-positions/) are
                        # generic listing pages that slip through body checks — drop them.
                        final_parsed_tmp = urllib.parse.urlparse(final_url)
                        qs = urllib.parse.parse_qs(final_parsed_tmp.query)
                        if qs.get("gh_jid"):
                            pass  # fall through to body check on final_url
                        else:
                            reason = f"redirect_to_{reason_final}"
                            set_url_validation_cache(url, False, reason)
                            return False, reason
                    else:
                        reason = f"redirect_to_{reason_final}"
                        set_url_validation_cache(url, False, reason)
                        return False, reason
    except Exception:
        set_url_validation_cache(url, False, "head_failed")
        return False, "head_failed"

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
            get_resp = await client.get(final_url)
            body = get_resp.text
            body_lower = body.lower()

            for s in CLOSED_STRINGS:
                if s in body_lower:
                    reason = f"closed: {s}"
                    set_url_validation_cache(url, False, reason)
                    return False, reason

            if not _title_in_body(expected_title, body):
                set_url_validation_cache(url, False, "title_not_found")
                return False, "title_not_found"

    except Exception:
        set_url_validation_cache(url, False, "get_failed")
        return False, "get_failed"

    set_url_validation_cache(url, True, "pass")
    return True, "pass"
