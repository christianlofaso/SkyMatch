import asyncio
import json
import re
import urllib.parse
import anthropic
import httpx
from fastapi import APIRouter, HTTPException

from cache import get_url_validation_cache, set_url_validation_cache
from schemas import Internship, InternshipBuckets, ProfileAnalysis

router = APIRouter()
ai = anthropic.Anthropic()

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

BIG_TECH_COMPANIES = [
    "Google", "Meta", "Apple", "Microsoft", "Amazon", "Netflix",
    "Salesforce", "Adobe", "Nvidia", "OpenAI", "Anthropic",
    "Stripe", "Databricks", "Snowflake", "Palantir", "Tesla",
]

INTERNSHIPS_SYSTEM = """You are a career advisor who generates realistic, specific internship recommendations for a student based on their LinkedIn profile.

Generate internship opportunities across 4 buckets. Each opportunity should be REAL or highly plausible — use actual companies that hire interns in this field.

Buckets:
- local: roles at companies headquartered or with offices within ~50 miles of the user's location. For Chicago-area students: Morningstar, CME Group, Citadel, Tempus, Outcome Health, Sprout Social, Relativity, etc.
- big_tech: roles at well-known large tech companies (Google, Meta, Apple, Microsoft, Amazon, Stripe, Databricks, Snowflake, Palantir, Nvidia, OpenAI, Anthropic, Tesla, etc.)
- startup: companies that are roughly Series C or earlier. If a startup is also a reach, classify it as reach instead.
- reach: top-tier company AND the candidate has a significant credential gap given they are an early undergrad. Be specific about the gap.

Rules:
- fit_explanation: MUST reference specific fields from their profile (school, skills, orgs, major, past companies). Never generic.
  BAD: "You're a great fit for this role."
  GOOD: "Your CompE coursework at UIUC and your Phi Delta Theta leadership map well to Citadel's quantitative engineering team, which recruits heavily from Champaign."
- reach_gap: specific and constructive.
  BAD: "You're not qualified."
  GOOD: "This role lists 1-2 prior SWE internships as preferred. Close the gap by shipping a personal project in Python or C++ and applying again sophomore year."
- application_url: always set to null. URLs are sourced from real job boards separately.
- company_description: one sentence, factual.
- Max 10 per bucket. Aim for 8-10 per bucket. More candidates are better — many will be dropped during URL validation.
- A single internship goes in exactly ONE bucket.

Respond with ONLY valid JSON — no markdown fences, no commentary:

{
  "local": [...],
  "big_tech": [...],
  "startup": [...],
  "reach": [...]
}

Each item:
{
  "title": "string",
  "company": "string",
  "location": "string",
  "company_description": "string",
  "fit_explanation": "string",
  "application_url": "string or null",
  "bucket": "local" | "big_tech" | "startup" | "reach",
  "reach_gap": "string or null"
}
"""


_SKIP_STARTUP_ADDENDUM = (
    '\n\nIMPORTANT: Do NOT generate any items for the "startup" bucket. '
    'That bucket is sourced from real live listings. Return "startup": [] in your JSON.'
)

STARTUP_SYSTEM = """You are a career advisor matching real startup internship listings to a student's profile.

You receive a student's ProfileAnalysis and a list of verified open listings from YC Work at a Startup and Wellfound (each has url, search_title, snippet).

Select up to 10 listings that best fit this student and return ONE Internship object per listing.

Rules:
- application_url: copy the EXACT url from the listing verbatim. Do not modify it.
- bucket: always "startup".
- reach_gap: always null.
- title: extract from search_title (the role title, not the company name).
- company: extract from search_title or snippet.
- location: extract from snippet if visible; otherwise "Remote / Various".
- company_description: one factual sentence inferred from the snippet.
- fit_explanation: MUST reference specific profile fields (school, skills, major, orgs, past companies). Be concrete.
  BAD: "You're a great fit."
  GOOD: "Your Python skills and UIUC CompE coursework map directly to this YC-backed startup's ML infrastructure work."
- Skip listings where the snippet clearly indicates a full-time role or a closed/filled position.
- If fewer than 10 strong matches exist, return fewer — do not pad with weak matches.

Respond with ONLY a valid JSON array — no markdown, no commentary:

[
  {
    "title": "string",
    "company": "string",
    "location": "string",
    "company_description": "string",
    "fit_explanation": "string",
    "application_url": "string",
    "bucket": "startup",
    "reach_gap": null
  }
]
"""


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
    async with httpx.AsyncClient(timeout=6, follow_redirects=True) as client:
        for slug in slugs:
            # Greenhouse
            try:
                r = await client.get(
                    f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
                )
                if r.status_code == 200:
                    url = _best_intern_match(
                        r.json().get("jobs", []), "title", "absolute_url", title
                    )
                    if url:
                        print(f"[ats] greenhouse slug={slug} url={url}")
                        return url
            except Exception:
                pass

            # Lever
            try:
                r = await client.get(
                    f"https://api.lever.co/v0/postings/{slug}?mode=json"
                )
                if r.status_code == 200:
                    url = _best_intern_match(
                        r.json(), "text", "hostedUrl", title
                    )
                    if url:
                        print(f"[ats] lever slug={slug} url={url}")
                        return url
            except Exception:
                pass

            # Ashby
            try:
                r = await client.get(
                    f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
                )
                if r.status_code == 200:
                    url = _best_intern_match(
                        r.json().get("jobPostings", []), "title", "jobUrl", title
                    )
                    if url:
                        print(f"[ats] ashby slug={slug} url={url}")
                        return url
            except Exception:
                pass

    return None


async def _find_via_startup_boards(title: str, company: str) -> str | None:
    """Search YC Work at a Startup and Wellfound for a startup internship listing.

    Both platforms embed numeric job IDs in listing URLs so results naturally
    pass the _JOB_ID_RE check. We pre-filter here to avoid returning company
    overview pages that lack an ID.
    """
    queries = [
        f'"{company}" "{title}" site:workatastartup.com',
        f'"{company}" intern site:workatastartup.com',
        f'"{company}" "{title}" site:wellfound.com',
        f'"{company}" intern site:wellfound.com',
    ]
    try:
        from ddgs import DDGS
        ddgs = DDGS()
        for query in queries:
            results = list(ddgs.text(query, max_results=5))
            for r in results:
                url = r.get("href", "")
                parsed = urllib.parse.urlparse(url)
                domain = parsed.netloc.lower()
                if "workatastartup.com" in domain or "wellfound.com" in domain:
                    if _JOB_ID_RE.search(parsed.path):
                        print(f"[startup-boards] found url={url}")
                        return url
    except Exception:
        pass
    return None


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

    all_batches = await asyncio.gather(*[asyncio.to_thread(_run_query, q) for q in queries])

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


def _generate_startup_internships_sync(
    profile: ProfileAnalysis,
    listings: list[dict],
) -> list[Internship]:
    """Synchronous Claude call that maps real startup listings to Internship objects.

    Called via asyncio.to_thread so it doesn't block the event loop.
    Returns [] on any error so the startup bucket degrades gracefully.
    """
    try:
        msg = ai.messages.create(
            model="claude-opus-4-5",
            max_tokens=4096,
            system=STARTUP_SYSTEM,
            messages=[{
                "role": "user",
                "content": (
                    f"Student profile:\n{json.dumps(profile.model_dump(), indent=2)}\n\n"
                    f"Open listings ({len(listings)} total):\n"
                    f"{json.dumps(listings, indent=2)}"
                ),
            }],
        )
        raw = _strip_fences(msg.content[0].text)
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            parsed = parsed.get("internships") or parsed.get("startup") or []
        if not isinstance(parsed, list):
            return []
        result = [Internship(**item) for item in parsed]
        print(f"[startup-claude] generated {len(result)} startup internships from real listings")
        return result
    except Exception as e:
        print(f"[startup-claude] ERROR: {e}")
        return []


async def _get_url(title: str, company: str, bucket: str = "") -> str | None:
    """URL lookup priority:
    - startup bucket: YC/Wellfound → ATS APIs → DuckDuckGo
    - all others:     ATS APIs → DuckDuckGo
    """
    if bucket == "startup":
        url = await _find_via_startup_boards(title, company)
        if url:
            return url
    url = await _find_via_ats(title, company)
    if url:
        return url
    return await _find_job_url(title, company)


async def _find_job_url(title: str, company: str) -> str | None:
    """Search DuckDuckGo for a direct job listing on the company site or a trusted board."""
    slug = _company_slug(company)

    # Try two queries: one targeting the company's own site, one broader
    queries = [
        f'"{company}" "{title}" internship 2026 apply -site:linkedin.com',
        f"{title} internship {company} 2026 careers apply",
    ]

    company_domain_hit = None
    board_hit = None

    try:
        from ddgs import DDGS
        ddgs = DDGS()
        for query in queries:
            results = list(ddgs.text(query, max_results=10))
            for r in results:
                url = r.get("href", "")
                domain = urllib.parse.urlparse(url).netloc.lower()

                # Skip blocked domains entirely
                if any(b in domain for b in BLOCKED_DOMAINS):
                    continue

                # Best: company's own careers domain
                if slug in domain and company_domain_hit is None:
                    company_domain_hit = url

                # Good: trusted job board
                if board_hit is None and any(b in domain for b in TRUSTED_BOARDS):
                    board_hit = url

            # If we found the company's own site, stop searching
            if company_domain_hit:
                break

    except Exception:
        return None

    return company_domain_hit or board_hit or None


def _strip_fences(raw: str) -> str:
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return raw.strip()


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

    # Application-form pages — the listing is the parent URL, not /apply or /application.
    # Lever: jobs.lever.co/{co}/{uuid}/apply
    # Greenhouse: boards.greenhouse.io/{co}/jobs/{id}/application
    path_parts_raw = [p for p in parsed.path.split("/") if p]
    if path_parts_raw and path_parts_raw[-1].lower() in ("apply", "application", "applications"):
        return True, "application_form_url"

    # A real listing URL contains a numeric job ID (≥5 digits) or a UUID.
    # University landing pages, emerging-talent hubs, and internship overview pages
    # all have human-readable paths with no ID — drop them.
    if not _JOB_ID_RE.search(parsed.path):
        return True, "no_job_id_in_url"

    return False, ""


def _title_in_body(expected_title: str, body: str) -> bool:
    """Return True if ≥70% of title tokens appear anywhere in the page body."""
    def tokenize(s: str) -> list[str]:
        return re.sub(r"[^\w\s]", " ", s.lower()).split()

    tokens = tokenize(expected_title)
    if not tokens:
        return True
    body_lower = body.lower()
    matched = sum(1 for t in tokens if t in body_lower)
    return matched / len(tokens) >= 0.7


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

    # Rules 3 + 4: HEAD to check status and follow redirects cheaply
    final_url = url
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=10) as client:
            head_resp = await client.head(url)
            final_url = str(head_resp.url)

            if head_resp.status_code >= 400:
                reason = f"http_{head_resp.status_code}"
                set_url_validation_cache(url, False, reason)
                return False, reason

            if final_url != url:
                is_gen_final, reason_final = _is_generic_url(final_url)
                if is_gen_final:
                    reason = f"redirect_to_{reason_final}"
                    set_url_validation_cache(url, False, reason)
                    return False, reason
    except Exception:
        set_url_validation_cache(url, False, "head_failed")
        return False, "head_failed"

    # Rules 5 + 6: GET the final URL and scan the body
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


async def _validate_with_sem(
    sem: asyncio.Semaphore, internship: Internship, bucket: str
) -> bool:
    """Semaphore-wrapped validate_job_url with structured logging."""
    async with sem:
        is_valid, reason = await validate_job_url(
            internship.application_url, internship.title
        )
        label = "PASS" if is_valid else "DROP"
        print(
            f"[validate] bucket={bucket} company={internship.company} "
            f'title="{internship.title}" result={label} reason={reason} '
            f"url={internship.application_url}"
        )
        return is_valid


async def search_internships(profile: ProfileAnalysis) -> InternshipBuckets:
    """Generate personalized internship recommendations using Claude.

    Startup bucket uses a search-first approach:
      1. Scrape real listings from YC Work at a Startup + Wellfound via DDG
      2. Separate Claude call annotates those real listings with fit explanations
      3. URLs are already known — no URL-finding step for startup items
    All other buckets use the original Claude-generates → URL-find → validate flow.
    Both Claude calls run in parallel via asyncio.to_thread.
    """
    # ── 1. Scrape real startup listings concurrently (fast async DDG search)
    startup_listings = await _scrape_startup_listings(profile)

    # ── 2. Build main system prompt — tell Claude to skip startup if we have real ones
    system_prompt = INTERNSHIPS_SYSTEM
    if startup_listings:
        system_prompt = INTERNSHIPS_SYSTEM + _SKIP_STARTUP_ADDENDUM

    # ── 3. Sync callables for asyncio.to_thread (ai.messages.create is blocking)
    def _main_claude_call() -> dict:
        msg = ai.messages.create(
            model="claude-opus-4-5",
            max_tokens=8192,
            system=system_prompt,
            messages=[{
                "role": "user",
                "content": (
                    f"Generate internship recommendations for this student:\n\n"
                    f"{json.dumps(profile.model_dump(), indent=2)}"
                ),
            }],
        )
        raw = _strip_fences(msg.content[0].text)
        print(f"[internships] Claude raw response (first 300 chars): {raw[:300]}")
        data = json.loads(raw)
        print(
            f"[internships] bucket sizes: local={len(data.get('local', []))}, "
            f"big_tech={len(data.get('big_tech', []))}, "
            f"startup={len(data.get('startup', []))}, "
            f"reach={len(data.get('reach', []))}"
        )
        return data

    # ── 4. Run both Claude calls in parallel
    if startup_listings:
        main_data, startup_items = await asyncio.gather(
            asyncio.to_thread(_main_claude_call),
            asyncio.to_thread(_generate_startup_internships_sync, profile, startup_listings),
        )
    else:
        # Fallback: let main Claude generate startup too (current behavior)
        main_data = await asyncio.to_thread(_main_claude_call)
        startup_items = []

    # ── 5. Build candidate pool (up to 10 per bucket)
    all_items = {
        "local":    [Internship(**i) for i in main_data.get("local",    [])[:10]],
        "big_tech": [Internship(**i) for i in main_data.get("big_tech", [])[:10]],
        "startup":  startup_items[:10] if startup_listings
                    else [Internship(**i) for i in main_data.get("startup", [])[:10]],
        "reach":    [Internship(**i) for i in main_data.get("reach",    [])[:10]],
    }

    # ── 6. URL finding — skip for startup items that already have application_url set
    flat: list[Internship] = []
    flat_buckets: list[str] = []
    for bucket_name, items in all_items.items():
        for item in items:
            flat.append(item)
            flat_buckets.append(bucket_name)

    url_sem = asyncio.Semaphore(8)

    async def _get_url_sem(i: Internship, bucket: str) -> str | None:
        if i.application_url:  # already set from real listing — skip URL-finding
            return i.application_url
        async with url_sem:
            return await _get_url(i.title, i.company, bucket)

    urls = await asyncio.gather(*[_get_url_sem(i, b) for i, b in zip(flat, flat_buckets)])
    for internship, url in zip(flat, urls):
        internship.application_url = url

    # ── 7. Validate all URLs — cap at 10 concurrent HTTP calls with a semaphore
    sem = asyncio.Semaphore(10)
    validated: dict[str, list[Internship]] = {}
    for bucket_name, candidates in all_items.items():
        flags = await asyncio.gather(
            *[_validate_with_sem(sem, i, bucket_name) for i in candidates]
        )
        passed = [i for i, ok in zip(candidates, flags) if ok][:5]
        n_dropped = sum(1 for ok in flags if not ok)
        print(
            f"[validate-summary] bucket={bucket_name} "
            f"candidates={len(candidates)} passed={len(passed)} dropped={n_dropped}"
        )
        if len(passed) < 3:
            print(f"[validate] WARNING bucket={bucket_name} only {len(passed)} passed")
        validated[bucket_name] = passed

    return InternshipBuckets(**validated)


@router.post("/internships/search", response_model=InternshipBuckets)
async def internships_search_route(profile: ProfileAnalysis):
    try:
        return await search_internships(profile)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
