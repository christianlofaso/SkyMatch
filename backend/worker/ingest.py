"""Background ingestion worker — pre-populates listing_store from the open web so
request-time serving can query a local index instead of calling DDGS/ATS/Firecrawl
live per user.

After the scrape/enrich/validate/store passes it runs a PARSE PASS (parse_pass) that
precomputes, ONCE per listing, the profile-independent structured + display fields
(Haiku) and an embedding (Voyage) that serving used to derive live per request. The
parse pass is INCREMENTAL — it only touches rows with parsed_at IS NULL (new listings,
or ones whose content changed since the last parse) — so a steady-state run is cheap;
the FIRST run after the precompute-columns migration is a one-time full backfill.

Runs as a STANDALONE process (not inside uvicorn). Idempotent — every write is an
upsert keyed by url, so it's safe to re-run on any cadence.

    cd backend && ./venv/Scripts/python.exe -m worker.ingest

In PRODUCTION this runs as a Railway cron service every ~8h (cronSchedule "0 */8 * * *"
in railway.worker.toml) — a fresh container per tick that exits when the pass finishes.

Windows Task Scheduler (local dev, every ~8h):
    Program/script:  C:\\Users\\chris\\Desktop\\pathfinder\\backend\\venv\\Scripts\\python.exe
    Arguments:       -m worker.ingest
    Start in:        C:\\Users\\chris\\Desktop\\pathfinder\\backend
POSIX cron equivalent:
    cd backend && ./venv/bin/python -m worker.ingest
"""
import sys

# Force UTF-8 stdout/stderr. As a standalone process (Task Scheduler / redirected
# output), Windows defaults to cp1252, which can't encode the non-ASCII chars (→, etc.)
# in some shared log lines — that would crash the whole run mid-ingest. Harmless no-op
# when the stream is already UTF-8.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# Load .env BEFORE importing anything that reads env at import time — lib.firecrawl reads
# FIRECRAWL_* and lib.embeddings reads VOYAGE_API_KEY/EMBED_MODEL on import. The parse pass
# now makes Haiku (ANTHROPIC_API_KEY) + Voyage (VOYAGE_API_KEY) calls, but BOTH keys are
# OPTIONAL: when absent, the parse pass skips that work, rows stay parsed_at IS NULL, and
# serving uses its non-precomputed fallback path. FIRECRAWL_API_KEY is likewise optional.
import os  # noqa: E402
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import asyncio  # noqa: E402
import json  # noqa: E402
import time  # noqa: E402

import httpx  # noqa: E402

from cache import (  # noqa: E402
    ONE_DAY, count_listings_by_niche_bucket, get_listings_missing_logo, get_listings_to_embed,
    get_listings_to_parse, get_rotation_metros, init_db, mark_listing_dead, prune_stale_listings,
    set_listing_embedding, set_listing_logo, sum_worker_spend_since, upsert_listing,
)
from lib.cost import cost_session  # noqa: E402
from config.niches import (  # noqa: E402
    NATIONAL_FIELDS, NATIONAL_NICHE_KEY, NationalField,
    REACH_ATS_SLUGS, REACH_NICHE_KEY,
)
from lib import embeddings  # noqa: E402
from lib.ingest_core import (  # noqa: E402
    _enrich_listing, _fetch_ats_listings, _scrape_bigtech_listings,
    _scrape_local_listings, _scrape_startup_listings, validate_job_url,
)
from lib.listing_parser import build_embed_text  # noqa: E402
from lib.logo_resolver import resolve_logo  # noqa: E402
from lib.precompute import parse_and_embed_rows  # noqa: E402
from lib.timing import timed, timing_session  # noqa: E402
from schemas import ProfileAnalysis  # noqa: E402

# Listings not re-discovered (last_seen) within this window are GC'd each run.
STALE_MAX_AGE = 14 * ONE_DAY
_ENRICH_CONCURRENCY = 8       # mirror the live pipeline's enrichment semaphore
_VALIDATE_CONCURRENCY = 10    # mirror the live pipeline's validation semaphore

# Worker soft spend cap (M5). The parse pass's Haiku calls are tagged with the
# 'worker:ingest' cost_session, which sum_spend_since() EXCLUDES — so ingestion can never
# trip the user-facing kill switch. This is the worker's OWN budget bucket: it stops
# parsing (leaving rows unparsed for the next run) once its rolling-window spend reaches
# the cap. 0 = disabled (code default; .env.example sets a real ceiling). Mirrors the
# SPEND_CAP_USD_DAILY / SPEND_CAP_WINDOW_SEC pattern in lib/guard.py.
WORKER_SPEND_CAP_USD_DAILY = float(os.getenv("WORKER_SPEND_CAP_USD_DAILY", "0") or "0")
WORKER_SPEND_CAP_WINDOW_SEC = int(os.getenv("WORKER_SPEND_CAP_WINDOW_SEC", "86400"))
# Rows are parsed in chunks of this size so the cap is re-checked mid-pass (not just before
# it) — bounds a single huge first-run backfill, not just runaway across runs.
_PARSE_CAP_CHUNK = 64


def _field_to_profile(nf: NationalField) -> ProfileAnalysis:
    """Synthetic profile for a national field. Location is neutral/empty — the national
    scrapers (_scrape_startup_listings/_scrape_bigtech_listings) read only field / major /
    technical_skills, never location. Remaining fields are required-but-unused stubs."""
    return ProfileAnalysis(
        full_name="", headline="", location="", school="",
        graduation_year=None, major=nf.major, fraternity_or_orgs=[],
        past_companies=[], current_company=None,
        technical_skills=list(nf.skills),
        field_of_interest=nf.field, key_values=[],
    )


def _metro_to_profile(metro: str) -> ProfileAnalysis:
    """Synthetic profile for a local-bucket metro. `location=metro` round-trips through
    `_parse_metro` (the scraper re-parses it to the same metro); field is kept generic-CS
    so the local scraper's `{field}` queries stay meaningful."""
    return ProfileAnalysis(
        full_name="", headline="", location=metro, school="",
        graduation_year=None, major=None, fraternity_or_orgs=[],
        past_companies=[], current_company=None,
        technical_skills=[], field_of_interest="Computer Science", key_values=[],
    )


async def _enrich_all(listings: list[dict]) -> list[dict]:
    sem = asyncio.Semaphore(_ENRICH_CONCURRENCY)
    return await asyncio.gather(*[_enrich_listing(l, sem) for l in listings])


async def _validate_and_store(
    listings: list[dict], *, bucket: str, niche_key: str
) -> tuple[int, int]:
    """Validate every listing (re-uses the 24h url_validation_cache) and upsert the
    survivors; mark the rest dead. Returns (n_valid, n_dropped)."""
    sem = asyncio.Semaphore(_VALIDATE_CONCURRENCY)

    async def _check(listing: dict) -> tuple[dict, bool, str]:
        async with sem:
            ok, reason = await validate_job_url(
                listing.get("url"), listing.get("search_title", "")
            )
        return listing, ok, reason

    results = await asyncio.gather(*[_check(l) for l in listings])
    n_valid = n_dead = 0
    for listing, ok, reason in results:
        if ok:
            upsert_listing(listing, bucket=bucket, niche_key=niche_key,
                           status="valid", validation_reason=reason)
            n_valid += 1
        else:
            mark_listing_dead(listing["url"], reason)
            n_dead += 1
    return n_valid, n_dead


async def ingest_national() -> None:
    """Scrape startup + big_tech across every NATIONAL_FIELD, union+dedup by url, and store
    under the metro-independent `_national` pool. Fields run sequentially (each does its two
    scrapes in parallel) to keep DDG/Firecrawl load sane. The big_tech ATS half is
    field-independent, so it's re-fetched per field and deduped away — accepted redundancy."""
    startup_all: dict[str, dict] = {}
    bigtech_all: dict[str, dict] = {}
    async with timed("ingest/national scrapes (all fields)"):
        for nf in NATIONAL_FIELDS:
            profile = _field_to_profile(nf)
            startup, bigtech = await asyncio.gather(
                _scrape_startup_listings(profile),   # NOT enriched by its scraper
                _scrape_bigtech_listings(profile),   # enriched + category-filtered internally
            )
            for l in startup:
                startup_all.setdefault(l["url"].rstrip("/"), l)
            for l in bigtech:
                bigtech_all.setdefault(l["url"].rstrip("/"), l)
            print(f"[ingest] national field={nf.field!r}: +{len(startup)} startup, "
                  f"+{len(bigtech)} big_tech (unique so far: "
                  f"{len(startup_all)} startup, {len(bigtech_all)} big_tech)")

    startup_listings = list(startup_all.values())
    bigtech_listings = list(bigtech_all.values())
    # Startup is the one bucket whose scraper skips enrichment; enrich it here so the store
    # carries verified_location (big_tech already enriched inside its scraper).
    async with timed("ingest/national enrich-startup"):
        startup_listings = await _enrich_all(startup_listings)

    for bucket, items in (("startup", startup_listings), ("big_tech", bigtech_listings)):
        async with timed(f"ingest/national validate:{bucket}"):
            n_valid, n_dead = await _validate_and_store(
                items, bucket=bucket, niche_key=NATIONAL_NICHE_KEY
            )
        print(f"[ingest] national/{bucket}: {n_valid} valid, {n_dead} dropped "
              f"(of {len(items)} unique)")


async def ingest_local(metro: str) -> None:
    """Scrape + enrich + validate the local bucket for one metro, stored under niche_key=metro.
    `_scrape_local_listings` enriches and metro-filters internally."""
    profile = _metro_to_profile(metro)
    async with timed(f"ingest/local:{metro} scrape"):
        local = await _scrape_local_listings(profile)
    async with timed(f"ingest/local:{metro} validate"):
        n_valid, n_dead = await _validate_and_store(local, bucket="local", niche_key=metro)
    print(f"[ingest] local/{metro}: {n_valid} valid, {n_dead} dropped (of {len(local)} scraped)")


async def ingest_reach() -> None:
    """Populate the aspirational/elite pool from public ATS boards. Niche-independent:
    the 'reach' judgment is made per-user at serving time, so one shared pool suffices."""
    async with timed("ingest/reach fetch-ats"):
        listings = await _fetch_ats_listings(REACH_ATS_SLUGS)
    async with timed("ingest/reach enrich"):
        listings = await _enrich_all(listings)
    async with timed("ingest/reach validate"):
        n_valid, n_dead = await _validate_and_store(
            listings, bucket="reach", niche_key=REACH_NICHE_KEY
        )
    print(f"[ingest] reach/{REACH_NICHE_KEY}: {n_valid} valid, {n_dead} dropped "
          f"(of {len(listings)} fetched)")


async def parse_pass() -> None:
    """Precompute structured/display fields (Haiku) + an embedding (Voyage) for every
    listing the parse pass hasn't processed yet (parsed_at IS NULL). Incremental by
    construction. Resilient: a Haiku failure leaves the row unparsed (retried next run);
    a Voyage failure stores the parse WITHOUT a vector (parse success alone stamps
    parsed_at, so Haiku isn't re-run) and serving treats the row as unranked."""
    rows = get_listings_to_parse()
    if not rows:
        print("[ingest] parse pass: nothing to parse")
        return
    print(f"[ingest] parse pass: {len(rows)} unparsed listings "
          f"(haiku={'on' if os.getenv('ANTHROPIC_API_KEY') else 'OFF'}, "
          f"voyage={'on' if embeddings.is_available() else 'OFF'})")

    cap = WORKER_SPEND_CAP_USD_DAILY
    window = WORKER_SPEND_CAP_WINDOW_SEC

    def _spent() -> float:
        # Worker spend over the rolling window (prior runs + this run so far — record_usage
        # persists each call immediately, so a mid-pass read sees the running total).
        return sum_worker_spend_since(int(time.time()) - window)

    # Pre-gate: if the worker has already spent its budget this window, skip entirely.
    if cap > 0:
        spent = await asyncio.to_thread(_spent)
        if spent >= cap:
            print(f"[ingest] parse pass: worker spend cap reached "
                  f"(~${spent:.2f}/${cap:.2f} in {window // 3600}h) — skipping this run")
            return

    # Parse + (SPA) company-resolve + embed + persist — shared with the request-time local
    # live-fetch (lib/precompute.parse_and_embed_rows). firecrawl_company=True: the worker
    # CAN afford the bounded SPA company render for new wellfound/workatastartup rows.
    # All Haiku calls inside are tagged 'worker:ingest' (excluded from the user kill switch).
    totals = {"parsed": 0, "embedded": 0, "haiku_failed": 0}
    with cost_session("worker:ingest"):
        # When the cap is off, parse in one call (unchanged behavior); when on, chunk so the
        # cap is enforced mid-pass.
        chunk = _PARSE_CAP_CHUNK if cap > 0 else len(rows)
        for i in range(0, len(rows), chunk):
            if cap > 0:
                spent = await asyncio.to_thread(_spent)
                if spent >= cap:
                    remaining = len(rows) - i
                    print(f"[ingest] parse pass: worker spend cap hit "
                          f"(~${spent:.2f}/${cap:.2f}) — {remaining} rows left "
                          f"unparsed for next run")
                    break
            stats = await parse_and_embed_rows(rows[i:i + chunk], firecrawl_company=True)
            for k in totals:
                totals[k] += stats[k]
    print(f"[ingest] parse pass: parsed {totals['parsed']}, embedded {totals['embedded']}, "
          f"haiku-failed {totals['haiku_failed']}")


async def embed_backfill_pass() -> None:
    """Backfill embeddings for rows that were PARSED but never EMBEDDED (Voyage was
    unavailable/rate-limited at parse time). Re-uses the precomputed parse — NO Haiku — so
    it cheaply fills vectors once Voyage works (e.g. after a payment method unlocks rate
    limits). No-op when Voyage is unavailable or nothing needs embedding."""
    if not embeddings.is_available():
        return
    rows = get_listings_to_embed()
    if not rows:
        print("[ingest] embed backfill: nothing to embed")
        return
    print(f"[ingest] embed backfill: {len(rows)} parsed rows missing an embedding")
    texts = [build_embed_text(r) for r in rows]
    try:
        async with timed("ingest/embed backfill"):
            vectors = await asyncio.to_thread(embeddings.embed_documents, texts)
    except Exception as e:
        print(f"[ingest] embed backfill failed ({e}) — leaving rows unembedded for next run")
        return
    if not vectors:
        return
    n = 0
    for r, vec in zip(rows, vectors):
        if vec is None:
            continue
        set_listing_embedding(
            r["niche_key"], r["bucket"], r["url"],
            embedding_bytes=embeddings.to_bytes(vec), model=embeddings.EMBED_MODEL, dim=len(vec),
        )
        n += 1
    print(f"[ingest] embed backfill: embedded {n}/{len(rows)}")


async def logo_backfill_pass() -> None:
    """Self-heal logos: re-resolve logo_url for parsed rows where it's null/absent. Without
    this, a transient logo.dev/network failure — or a half-finished deploy whose resolver
    returned None for a whole batch — leaves logo_url null, and because the parse pass is
    incremental (parsed_at already stamped) that null FREEZES forever and the frontend shows a
    letter avatar for a company that actually has a logo. Cheap and Haiku-/Voyage-free: curated
    + listing-extracted domains resolve with no network; only an uncurated name costs one
    logo.dev search. Mirrors embed_backfill_pass (the 'Voyage-down trap')."""
    rows = get_listings_missing_logo()
    if not rows:
        print("[ingest] logo backfill: nothing to re-resolve")
        return
    print(f"[ingest] logo backfill: {len(rows)} parsed rows missing a logo")
    healed = 0
    sem = asyncio.Semaphore(8)
    async with httpx.AsyncClient() as client:
        async def _heal(r: dict) -> None:
            nonlocal healed
            try:
                pj = json.loads(r["parsed_json"])
            except Exception:
                return
            async with sem:
                logo = await resolve_logo(pj.get("company"), pj.get("company_domain"), client)
            # Only write when we actually recovered a logo — leave genuinely unresolvable rows
            # null (correct letter avatar) so this stays idempotent and write-light.
            if logo and logo != pj.get("logo_url"):
                pj["logo_url"] = logo
                await asyncio.to_thread(
                    set_listing_logo, r["niche_key"], r["bucket"], r["url"], parsed_json=json.dumps(pj)
                )
                healed += 1
        await asyncio.gather(*[_heal(r) for r in rows])
    print(f"[ingest] logo backfill: healed {healed}/{len(rows)}")


async def run_all() -> None:
    init_db()
    with timing_session("ingest run"):
        print("[ingest] === national pool (startup + big_tech, all fields) ===")
        await ingest_national()
        await ingest_reach()
        metros = get_rotation_metros()
        print(f"[ingest] === local pool for {len(metros)} rotation metros: {metros} ===")
        for metro in metros:   # sequential to keep DDG/Firecrawl load sane
            await ingest_local(metro)
        deleted = prune_stale_listings(STALE_MAX_AGE)
        print(f"[ingest] pruned {deleted} stale listings (> {STALE_MAX_AGE // ONE_DAY}d)")
        # Parse pass runs AFTER prune so we never spend Haiku/Voyage calls on rows about
        # to be GC'd.
        print("[ingest] === parse pass (structured fields + embeddings) ===")
        await parse_pass()
        # Backfill embeddings for any parsed-but-unembedded rows (e.g. Voyage was rate-
        # limited on a prior run) — re-uses the parse, no Haiku.
        await embed_backfill_pass()
        # Self-heal logos for any parsed-but-null-logo rows (e.g. logo.dev hiccup or a
        # half-finished deploy resolved nothing) — the incremental parse would otherwise
        # freeze those nulls forever. No Haiku/Voyage; curated names need no network.
        await logo_backfill_pass()

    print("[ingest] ===== final store counts =====")
    for row in count_listings_by_niche_bucket():
        print(f"[ingest]   {row['niche_key']:>16} / {row['bucket']:<9} "
              f"{row['status']:<5}: {row['count']}")


if __name__ == "__main__":
    asyncio.run(run_all())
