"""Shared per-listing precompute: Haiku structured/display parse + Voyage embedding,
persisted to listing_store.

Used by BOTH the ingestion worker's parse pass (worker/ingest.py) AND the request-time
local live-fetch (routes/internships.py:_live_local_fetch), so the parse+embed+persist
orchestration lives in exactly ONE place. No parsing logic is defined here — it reuses
lib.listing_parser.

All model work is best-effort + optional: no ANTHROPIC_API_KEY → parse_listing_sync raises
and the row stays unparsed (retried later); no VOYAGE_API_KEY → parse stored WITHOUT a vector
(parse success alone stamps parsed_at, so Haiku isn't re-run); serving falls back gracefully.
"""
import asyncio
import json
import os

import httpx

from cache import set_listing_parse
from lib import embeddings, firecrawl
from lib.listing_parser import (
    build_embed_text, company_from_firecrawl, content_hash, needs_firecrawl_enrichment,
    parse_listing_sync,
)
from lib.logo_resolver import resolve_logo
from lib.timing import timed

# Max in-flight Haiku listing-parse calls (Haiku is intentionally ungated by sonnet_slot()).
WORKER_PARSE_CONCURRENCY = int(os.getenv("WORKER_PARSE_CONCURRENCY", "8"))


async def parse_and_embed_rows(rows: list[dict], *, firecrawl_company: bool = True) -> dict:
    """Parse (Haiku) → optionally resolve SPA company (Firecrawl) → embed (Voyage) → persist
    each row via set_listing_parse. Returns summary counts {parsed, embedded, haiku_failed}.

    `rows` are listing_store-shaped dicts (need niche_key, bucket, url, search_title, snippet,
    and optionally company/verified_location). `firecrawl_company=False` skips the SPA
    company-render step — used by the bounded local live-fetch, which only hits ATS boards
    (greenhouse/lever/ashby) where the URL slug / Haiku already resolve the company, so a
    render isn't worth the latency.
    """
    if not rows:
        return {"parsed": 0, "embedded": 0, "haiku_failed": 0}

    # 1. Haiku parse, bounded (Haiku is ungated by sonnet_slot()). Blocking → to_thread.
    sem = asyncio.Semaphore(WORKER_PARSE_CONCURRENCY)

    async def _parse(row: dict) -> dict | None:
        async with sem:
            return await asyncio.to_thread(parse_listing_sync, row)

    async with timed("precompute/parse haiku"):
        parsed_list = await asyncio.gather(*[_parse(r) for r in rows])

    ok = [(r, p) for r, p in zip(rows, parsed_list) if p is not None]
    n_haiku_fail = len(rows) - len(ok)

    # 1b. Render SPA listings (wellfound/workatastartup) to recover company AND/OR location
    #     AND/OR posted date — all three live only behind the Cloudflare-walled page. Fires when
    #     ANY is missing (not just company), so a known-company row still gets its real city
    #     instead of the "Remote / Various" fallback. Incremental + bounded; failures leave the
    #     row as-is. Skipped when firecrawl_company=False (e.g. the request-time local live-fetch).
    if firecrawl_company:
        spa = [(r, p) for r, p in ok
               if needs_firecrawl_enrichment(r["url"], p.get("company"), p.get("location"), p.get("posted_at"))]
        if spa and firecrawl.is_available():
            fsem = asyncio.Semaphore(4)

            async def _resolve(r: dict, p: dict) -> None:
                async with fsem:
                    co, loc, posted, logo_domain = await company_from_firecrawl(r["url"])
                if co:
                    p["company"] = co
                if loc and (not p.get("location") or p["location"] == "Remote / Various"):
                    p["location"] = loc
                # The posted date for SPA rows is only on the rendered page — fill it when the
                # snippet parse didn't already (wellfound/workatastartup hide it behind the app).
                if posted and not p.get("posted_at"):
                    p["posted_at"] = posted
                # The company's OWN domain (from its website link on the page) → its real logo,
                # which a name-search can't guess for a generic name like "Terminal".
                if logo_domain:
                    p["company_domain"] = logo_domain

            async with timed("precompute/parse firecrawl-company"):
                await asyncio.gather(*[_resolve(r, p) for r, p in spa])

    # 1c. Resolve a logo URL per row (server-side, once) → stored in parsed_json so the request path
    #     and the browser never resolve a logo live. Curated/extracted domains need no network; only
    #     an uncurated name triggers a single (optional) logo.dev search.
    async with timed("precompute/logos"):
        async with httpx.AsyncClient() as lclient:
            lsem = asyncio.Semaphore(8)

            async def _logo(p: dict) -> None:
                async with lsem:
                    p["logo_url"] = await resolve_logo(p.get("company"), p.get("company_domain"), lclient)

            await asyncio.gather(*[_logo(p) for _, p in ok])

    # 2. Embed the parsed rows in one batched (<=128/request) Voyage call, if available.
    texts = [build_embed_text(r) for r, _ in ok]
    vectors = None
    if ok and embeddings.is_available():
        try:
            async with timed("precompute/embed"):
                vectors = await asyncio.to_thread(embeddings.embed_documents, texts)
        except Exception as e:
            print(f"[precompute] embedding failed ({e}) — storing parse w/o vectors")
            vectors = None

    # 3. Persist (embedding best-effort; parse success stamps parsed_at).
    n_embedded = 0
    for i, (row, parsed) in enumerate(ok):
        vec = vectors[i] if vectors is not None and i < len(vectors) else None
        emb_bytes = embeddings.to_bytes(vec) if vec is not None else None
        if emb_bytes is not None:
            n_embedded += 1
        set_listing_parse(
            row["niche_key"], row["bucket"], row["url"],
            parsed_json=json.dumps(parsed),
            embedding_bytes=emb_bytes,
            model=embeddings.EMBED_MODEL if emb_bytes is not None else None,
            dim=len(vec) if vec is not None else None,
            content_hash=content_hash(texts[i]),
        )
    return {"parsed": len(ok), "embedded": n_embedded, "haiku_failed": n_haiku_fail}
