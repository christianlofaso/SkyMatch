"""Resource-URL validation for roadmap items.

Two-layer guardrail to prevent hallucinated learning links:
  1. Domain allowlist (synchronous, fast) — see config/resource_allowlist.py.
  2. Async HEAD liveness check with a hard 3-second timeout per URL, results
     cached for 7 days in url_liveness_cache.

The 3-second cap is per-URL; an entire roadmap's resources are checked in
parallel via asyncio.gather, so total wait is roughly one round trip.
"""

import asyncio
from urllib.parse import parse_qs, urlsplit

import httpx

from cache import get_url_liveness, set_url_liveness
from config.resource_allowlist import is_allowlisted

_HEAD_TIMEOUT_SECONDS = 3.0

# Query-param keys that indicate a search/listing page rather than a specific
# resource. youtube.com/results uses "search_query"; most others use "search"
# or "query". A live HEAD on these always returns 200, so the liveness check
# alone can't catch them — the LLM was gaming it by emitting search URLs.
_SEARCH_QUERY_KEYS = frozenset({"search_query", "search", "query"})

# Path components (after rstrip("/")) that are search/listing endpoints, not a
# specific page. "/results" is youtube's search page; "/search" is generic.
_SEARCH_PATHS = frozenset({"/results", "/search"})


def _is_generic_url(url: str) -> bool:
    """True if the URL points at a search/listing/homepage rather than a
    specific learning resource. These pass the allowlist + HEAD-liveness
    guards (the domain is trusted and the page returns 200), so they need a
    dedicated rule. Catches the failure mode where the LLM emits a search
    query (e.g. youtube.com/results?search_query=...) it knows will resolve,
    instead of a real video/article/course page."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return True  # unparseable — treat as junk

    path = parts.path.rstrip("/")

    # 1. Search/results endpoints (youtube /results, google-style /search).
    if path.lower() in _SEARCH_PATHS:
        return True

    # 2. Any search-style query parameter.
    query_keys = {k.lower() for k in parse_qs(parts.query)}
    if query_keys & _SEARCH_QUERY_KEYS:
        return True

    # 3. Bare domain root with no path and no query — a homepage, not a
    #    resource. (A specific resource always has a meaningful path.)
    if path == "" and not parts.query:
        return True

    return False
_HEAD_HEADERS = {
    # Some CDNs 4xx unknown User-Agents on HEAD; identify as a normal browser.
    "User-Agent": (
        "Mozilla/5.0 (compatible; SkyMatchBot/1.0; "
        "+https://github.com/anthropics/claude-code)"
    ),
    "Accept": "*/*",
}


async def _head_once(url: str, client: httpx.AsyncClient) -> bool:
    try:
        resp = await client.head(
            url,
            timeout=_HEAD_TIMEOUT_SECONDS,
            follow_redirects=True,
            headers=_HEAD_HEADERS,
        )
    except (httpx.TimeoutException, httpx.RequestError):
        return False
    # Some servers reject HEAD with 405 — retry once with a tiny GET range.
    if resp.status_code == 405:
        try:
            resp = await client.get(
                url,
                timeout=_HEAD_TIMEOUT_SECONDS,
                follow_redirects=True,
                headers={**_HEAD_HEADERS, "Range": "bytes=0-0"},
            )
        except (httpx.TimeoutException, httpx.RequestError):
            return False
    return 200 <= resp.status_code < 400


async def check_url_alive(url: str, client: httpx.AsyncClient) -> bool:
    """Cached HEAD liveness check. 7-day TTL on hits and misses."""
    cached = get_url_liveness(url)
    if cached is not None:
        return cached
    alive = await _head_once(url, client)
    set_url_liveness(url, alive)
    return alive


async def validate_resource_urls(urls: list[str]) -> dict[str, bool]:
    """Returns {url: is_valid}. A URL is valid iff it passes the allowlist
    check AND the HEAD liveness check (cache-hit-friendly)."""
    if not urls:
        return {}

    # Stage 1: allowlist + generic-URL rejection (synchronous, free). A URL
    # must be on a trusted domain AND point at a specific resource (not a
    # search/listing/homepage) to advance to the liveness check.
    eligible = {u: (is_allowlisted(u) and not _is_generic_url(u)) for u in urls}

    # Stage 2: HEAD only for eligible URLs.
    to_check = [u for u, ok in eligible.items() if ok]
    if not to_check:
        return eligible

    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(
            *(check_url_alive(u, client) for u in to_check),
            return_exceptions=False,
        )

    alive_map = dict(zip(to_check, results))
    return {u: (eligible[u] and alive_map.get(u, False)) for u in urls}
