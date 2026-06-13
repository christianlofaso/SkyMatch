"""
Shared Firecrawl client — a single source of truth for both the /analyze fetch
pipeline (routes/analyze.py) and the internships URL-liveness check
(routes/internships.py).

Firecrawl renders JavaScript and (in "auto"/"enhanced" proxy mode) bypasses
Cloudflare, so it's the only way to get a real signal from JS-SPA career sites
and Cloudflare-walled domains where a plain httpx request sees nothing useful.
"""

import asyncio
import os

import httpx

# ── Env config ────────────────────────────────────────────────────────────────
API_KEY    = os.getenv("FIRECRAWL_API_KEY", "")
BASE_URL   = os.getenv("FIRECRAWL_BASE_URL", "https://api.firecrawl.dev").rstrip("/")
WAIT_MS    = int(os.getenv("FIRECRAWL_WAIT_MS",    "8000"))    # JS render wait (bumped from 5000
# so SPA boards like Wellfound finish rendering the posted-date / lazy content before we scrape;
# TIMEOUT_MS below comfortably covers it. Env-overridable.
TIMEOUT_MS = int(os.getenv("FIRECRAWL_TIMEOUT_MS", "90000"))   # total request budget
# NOTE: this is a SINGLE budget covering BOTH the page fetch (~10s) AND the LLM
# schema-extraction step (the "extract"/json format), which alone can run ~30s+ on
# verbose career pages. At 45000 the combination timed out and the whole scrape
# returned nothing even though the page fetched fine (HTTP 200) — so keep this >= 90000.
# "auto" lets Firecrawl pick the cheapest proxy that works and escalate to a
# Cloudflare-bypassing proxy server-side only when the page is blocked (replaces the
# old manual basic→stealth retry). "stealth" is the deprecated v1 alias — don't use it.
PROXY_MODE = os.getenv("FIRECRAWL_PROXY_MODE", "auto")         # "auto" | "basic" | "enhanced"

# Cap simultaneous scrape requests to the plan's concurrent-browser limit (free/hobby = 2;
# see GET /v2/team/queue-status -> maxConcurrency). The worker fans validation out at
# _VALIDATE_CONCURRENCY=10 and company-recovery at WORKER_PARSE_CONCURRENCY=8 — far above this —
# so without a gate the excess QUEUES on Firecrawl's side, and queue-wait counts against our
# request timeout, producing SCRAPE_TIMEOUT 408s + orphaned dashboard jobs. Bounding here costs
# ~nothing in throughput (Firecrawl is the bottleneck regardless) and removes the thrash.
# NOTE: per-process — the worker and each web replica each get their own pool, so under
# concurrent worker+web load the effective total is N×this (acceptable; Firecrawl just queues
# the small overflow). Raise this only if you upgrade the Firecrawl plan's maxConcurrency.
MAX_CONCURRENCY = int(os.getenv("FIRECRAWL_MAX_CONCURRENCY", "2"))
_slot = asyncio.Semaphore(MAX_CONCURRENCY)

# ── Job extraction schema ───────────────────────────────────────────────────────
JOB_SCHEMA = {
    "type": "object",
    "properties": {
        "job_title":       {"type": "string", "description": "Job title or position name"},
        "company_name":    {"type": "string", "description": "Hiring company name"},
        "location":        {"type": "string", "description": "Job location or 'Remote'"},
        "employment_type": {"type": "string", "description": "e.g. Internship, Full-time, Part-time"},
        "date_posted":     {"type": "string", "description": "When the job was posted, as shown (e.g. 'Posted 3 days ago', '1 month ago', 'Jan 5, 2026'); empty if not shown"},
        "description":     {"type": "string", "description": "Full job description body text"},
        "requirements": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Must-have qualifications, each as a short phrase",
        },
        "nice_to_haves": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Preferred but not required qualifications",
        },
        "compensation": {"type": "string", "description": "Salary range or compensation details"},
    },
    "required": ["job_title", "description"],
}


def is_available() -> bool:
    """True when a Firecrawl API key is configured."""
    return bool(API_KEY)


async def scrape(url: str, proxy: str) -> dict:
    """
    POST one Firecrawl scrape request and return the raw response dict.
    Returns {} when no API key is set or on HTTP >= 400.
    Raises httpx.RequestError on network failure (callers decide how to handle).
    """
    if not API_KEY:
        return {}
    fc_timeout = TIMEOUT_MS / 1000 + 5  # add 5 s buffer over Firecrawl's own budget
    payload = {
        "url": url,
        "formats": ["markdown", "extract"],
        "extract": {
            "schema": JOB_SCHEMA,
            "prompt": "Extract the job posting details from this career page.",
        },
        "waitFor": WAIT_MS,
        "proxy":   proxy,
        "timeout": TIMEOUT_MS,
    }
    # One retry on a NETWORK error only (a transient blip). HTTP >= 400 is a real answer
    # (returns {} below) and is NOT retried; the caller maps it. The whole attempt loop runs
    # under _slot so we never put more than MAX_CONCURRENCY scrapes in flight at once (a retry
    # reuses the same slot rather than grabbing a second); the slot releases as soon as the HTTP
    # response is in hand, before the cheap json parse below.
    last_exc: httpx.RequestError | None = None
    async with _slot:
        for attempt in range(2):
            try:
                async with httpx.AsyncClient(timeout=fc_timeout) as client:
                    resp = await client.post(
                        f"{BASE_URL}/v1/scrape",
                        headers={"Authorization": f"Bearer {API_KEY}"},
                        json=payload,
                    )
                break
            except httpx.RequestError as e:
                last_exc = e
                if attempt == 0:
                    print(f"[firecrawl] {proxy}: network error, retrying once: {e!r}")
                    await asyncio.sleep(1.0)
                    continue
                raise last_exc
    if resp.status_code >= 400:
        print(f"[firecrawl] {proxy}: HTTP {resp.status_code}: {resp.text[:200]}")
        return {}
    return resp.json()
