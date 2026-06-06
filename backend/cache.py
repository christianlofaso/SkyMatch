import hashlib
import json
import re
import time

# The connection pool + get_db()/init_db() live in db.py now (Postgres, not sqlite).
# Re-exported here so every existing `from cache import get_db / init_db` keeps working
# (main.py startup, worker/ingest.py). Schema is owned by Alembic — init_db() only warms
# the pool; it no longer creates tables/indexes/seeds.
from db import get_db, init_db  # noqa: F401  (re-exported)

SEVEN_DAYS = 7 * 24 * 3600
ONE_DAY = 24 * 3600
THIRTY_DAYS = 30 * 24 * 3600

_WS_RE = re.compile(r"\s+")


def hash_filters(filters: dict) -> str:
    serialized = json.dumps(filters, sort_keys=True)
    return hashlib.sha256(serialized.encode()).hexdigest()


def text_cache_key(text: str) -> str:
    h = hashlib.sha256(text[:500].encode()).hexdigest()[:16]
    return f"text:{h}"


def normalize_job_text(text: str) -> str:
    """Cheap normalization for cache keys: lowercase + collapse whitespace."""
    return _WS_RE.sub(" ", text.strip().lower())


def job_text_hash(text: str) -> str:
    """sha256 of the *normalized* job text, hex, first 32 chars."""
    return hashlib.sha256(normalize_job_text(text).encode()).hexdigest()[:32]


def profile_hash(profile_json: str) -> str:
    """sha256 of the *full canonical* profile JSON, hex, first 16 chars.

    Hashing the full string fixes the 500-char truncation bug in the old
    analysis_cache key — editing a resume past byte 500 used to leave the
    cache stale.
    """
    return hashlib.sha256(profile_json.encode()).hexdigest()[:16]


def analysis_cache_key(mode: str, profile_json: str, job_text: str) -> str:
    return f"{mode}:{profile_hash(profile_json)}:{job_text_hash(job_text)}"


def annotate_cache_key(profile_json: str, bucket: str, sig: str) -> str:
    """Key for the per-(profile, role) fit-reasoning cache. `sig` is the listing's
    content_hash when parsed (so a re-parse invalidates), else its url. Location/city is
    already folded into profile_hash, so bucket is the only extra dimension needed."""
    return f"{profile_hash(profile_json)}:{bucket}:{sig}"


def _get(table: str, key_col: str, key_val: str, ttl: int | None) -> dict | list | None:
    # {table}/{key_col} are trusted internal constants (never user input); values are
    # always parameterized via %s.
    with get_db() as conn:
        row = conn.execute(
            f"SELECT data, created_at FROM {table} WHERE {key_col} = %s", (key_val,)
        ).fetchone()
    if row is None:
        return None
    if ttl and (time.time() - row["created_at"]) > ttl:
        return None
    return json.loads(row["data"])


def _set(table: str, key_col: str, key_val: str, data: dict | list) -> None:
    with get_db() as conn:
        conn.execute(
            f"INSERT INTO {table} ({key_col}, data, created_at) VALUES (%s, %s, %s) "
            f"ON CONFLICT ({key_col}) DO UPDATE SET "
            f"data = EXCLUDED.data, created_at = EXCLUDED.created_at",
            (key_val, json.dumps(data), int(time.time())),
        )


# --- Profile cache (no TTL) ---

def get_profile_cache(linkedin_url: str) -> dict | None:
    return _get("profile_cache", "linkedin_url", linkedin_url, ttl=None)


def set_profile_cache(linkedin_url: str, data: dict) -> None:
    _set("profile_cache", "linkedin_url", linkedin_url, data)


# --- People search cache (7-day TTL) ---

def get_people_cache(filter_hash: str) -> list | None:
    return _get("people_search_cache", "filter_hash", filter_hash, ttl=SEVEN_DAYS)


def set_people_cache(filter_hash: str, data: list) -> None:
    _set("people_search_cache", "filter_hash", filter_hash, data)


# --- Jobs search cache (24-hour TTL) ---

def get_jobs_cache(filter_hash: str) -> list | None:
    return _get("jobs_search_cache", "filter_hash", filter_hash, ttl=ONE_DAY)


def set_jobs_cache(filter_hash: str, data: list) -> None:
    _set("jobs_search_cache", "filter_hash", filter_hash, data)


# --- Run cache (24-hour TTL) ---

def get_run_cache(url: str) -> dict | None:
    return _get("run_cache", "url", url, ttl=ONE_DAY)


def set_run_cache(url: str, data: dict) -> None:
    _set("run_cache", "url", url, data)


# --- URL validation cache (24-hour TTL) ---

def get_url_validation_cache(url: str) -> dict | None:
    """Returns {"is_valid": bool, "reason": str} or None on cache miss / expiry."""
    return _get("url_validation_cache", "url", url, ttl=ONE_DAY)


def set_url_validation_cache(url: str, is_valid: bool, reason: str) -> None:
    _set("url_validation_cache", "url", url, {"is_valid": is_valid, "reason": reason})


# --- Enrichment cache (24-hour TTL) ---

def get_enrichment_cache(url: str) -> dict | None:
    """Returns {"verified_location": str | None, "is_category_page": bool} or None on miss."""
    return _get("enrichment_cache", "url", url, ttl=ONE_DAY)


def set_enrichment_cache(url: str, data: dict) -> None:
    _set("enrichment_cache", "url", url, data)


# --- Analysis cache (24-hour TTL) ---

def get_analysis_cache(cache_key: str) -> dict | None:
    return _get("analysis_cache", "cache_key", cache_key, ttl=ONE_DAY)


def set_analysis_cache(cache_key: str, data: dict) -> None:
    _set("analysis_cache", "cache_key", cache_key, data)


# --- Requirements cache (global, 30-day TTL) -------------------------------

def get_requirements_cache(job_hash: str) -> dict | None:
    """Returns {'job_summary': {...}, 'requirements': [...]} or None."""
    return _get("requirements_cache", "job_hash", job_hash, ttl=THIRTY_DAYS)


def set_requirements_cache(job_hash: str, data: dict) -> None:
    _set("requirements_cache", "job_hash", job_hash, data)


# --- Job fetch cache (per-URL scraped text, 3-day TTL) ---------------------
# Caches the EXPENSIVE scrape (Firecrawl JS render) per job URL so a 2nd analysis of the
# same URL (e.g. a different profile) skips the fetch. 3-day TTL since postings expire.

def _url_hash(url: str) -> str:
    return hashlib.sha256(url.strip().encode()).hexdigest()[:32]


def get_job_fetch_cache(url: str) -> dict | None:
    """Returns {'text', 'posted_at', 'apply_url', 'path'} or None on miss/expiry."""
    return _get("job_fetch_cache", "url_hash", _url_hash(url), ttl=3 * ONE_DAY)


def set_job_fetch_cache(url: str, data: dict) -> None:
    _set("job_fetch_cache", "url_hash", _url_hash(url), data)


# --- User analysis cache (per-user, 30-day TTL) ----------------------------

def get_user_analysis_cache(cache_key: str) -> dict | None:
    return _get("user_analysis_cache", "cache_key", cache_key, ttl=THIRTY_DAYS)


def set_user_analysis_cache(cache_key: str, mode: str, data: dict) -> None:
    """Writes the mode column (used for selective wipes)."""
    with get_db() as conn:
        conn.execute(
            "INSERT INTO user_analysis_cache (cache_key, mode, data, created_at) "
            "VALUES (%s, %s, %s, %s) "
            "ON CONFLICT (cache_key) DO UPDATE SET "
            "mode = EXCLUDED.mode, data = EXCLUDED.data, created_at = EXCLUDED.created_at",
            (cache_key, mode, json.dumps(data), int(time.time())),
        )


# --- Annotate (fit reasoning) cache (per-(profile, role), 30-day TTL) -------
# Stores {"fit_explanation", "reach_gap"} so the deferred /internships/annotate Sonnet
# call is skipped on repeat views (different browser/device, or another user with the
# same profile). Keyed by annotate_cache_key (profile_hash : bucket : content_hash|url).

def get_annotate_cache(cache_key: str) -> dict | None:
    return _get("annotate_cache", "cache_key", cache_key, ttl=THIRTY_DAYS)


def set_annotate_cache(cache_key: str, data: dict) -> None:
    _set("annotate_cache", "cache_key", cache_key, data)


# --- Cost events ledger (append-only spend + savings) ----------------------
# Written by lib/cost.py; read by GET /cost/summary. 'call' rows = real spend;
# 'hit' rows = a full-call cache avoidance (usd=0, est_saved_usd>0).

def insert_cost_event(
    *, kind: str, session: str | None = None, label: str | None = None,
    model: str | None = None, input_tokens: int = 0, output_tokens: int = 0,
    cache_read_tokens: int = 0, cache_write_tokens: int = 0,
    usd: float = 0.0, est_saved_usd: float = 0.0, user_id: str | None = None,
) -> None:
    # id is supplied by the IDENTITY column — omitted from the INSERT, as before.
    with get_db() as conn:
        conn.execute(
            "INSERT INTO cost_events (created_at, kind, session, label, model, "
            "input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, usd, est_saved_usd, user_id) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (int(time.time()), kind, session, label, model, input_tokens, output_tokens,
             cache_read_tokens, cache_write_tokens, usd, est_saved_usd, user_id),
        )


def query_cost_events(since: int) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM cost_events WHERE created_at >= %s ORDER BY created_at", (since,)
        ).fetchall()
    return [dict(r) for r in rows]


def sum_spend_since(since: int) -> float:
    """Total real USER-FACING Claude spend (USD) since `since` (Unix ts). Only kind='call'
    rows carry spend; 'hit' rows are savings. Used by the spend-cap kill switch — which
    must NOT be tripped by background ingestion, so worker-tagged rows (session LIKE
    'worker:%') are EXCLUDED here (they have their own cap; see sum_worker_spend_since).
    A NULL session is request-path spend (a direct call with no cost_session) → counted."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(usd), 0.0) AS total FROM cost_events "
            "WHERE kind = 'call' AND created_at >= %s "
            "AND (session IS NULL OR session NOT LIKE 'worker:%%')",
            (since,),
        ).fetchone()
    return float(row["total"]) if row else 0.0


def sum_worker_spend_since(since: int) -> float:
    """Total background-WORKER Claude spend (USD) since `since` (Unix ts) — the inverse of
    sum_spend_since's exclusion. Sums kind='call' rows tagged with a 'worker:%' cost_session
    (the worker's Haiku parse pass). Used by the worker's own soft spend cap so ingestion
    self-limits independently of the user-facing kill switch."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(usd), 0.0) AS total FROM cost_events "
            "WHERE kind = 'call' AND created_at >= %s AND session LIKE 'worker:%%'",
            (since,),
        ).fetchone()
    return float(row["total"]) if row else 0.0


# --- App flags (persistent runtime key/value, e.g. the manual kill switch) ----

def get_flag(key: str) -> str | None:
    with get_db() as conn:
        row = conn.execute("SELECT value FROM app_flags WHERE key = %s", (key,)).fetchone()
    return row["value"] if row else None


def set_flag(key: str, value: str) -> None:
    with get_db() as conn:
        conn.execute(
            "INSERT INTO app_flags (key, value, updated_at) VALUES (%s, %s, %s) "
            "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = EXCLUDED.updated_at",
            (key, value, int(time.time())),
        )


# --- Auth: users + per-user daily quota counters (milestone 3) --------------
# Only touched when auth is enabled (SUPABASE_JWT_SECRET set); otherwise unused.

def upsert_user(user_id: str, email: str | None) -> None:
    """Record/refresh a Supabase auth user (keyed by JWT `sub`). Email is updated when
    present, never nulled by a token that omits it."""
    now = int(time.time())
    with get_db() as conn:
        conn.execute(
            "INSERT INTO users (id, email, created_at, last_seen) VALUES (%s, %s, %s, %s) "
            "ON CONFLICT (id) DO UPDATE SET "
            "email = COALESCE(EXCLUDED.email, users.email), last_seen = EXCLUDED.last_seen",
            (user_id, email, now, now),
        )


def incr_usage(user_id: str, day: str, kind: str) -> int:
    """Atomically increment the (user, UTC-day, kind) counter and return the NEW count.
    Quota enforcement increments first, then rejects if over the cap (a daily counter, so a
    rejected over-cap attempt simply stays over)."""
    with get_db() as conn:
        row = conn.execute(
            "INSERT INTO usage_counters (user_id, day, kind, count) VALUES (%s, %s, %s, 1) "
            "ON CONFLICT (user_id, day, kind) DO UPDATE SET count = usage_counters.count + 1 "
            "RETURNING count",
            (user_id, day, kind),
        ).fetchone()
    return int(row["count"])


def get_usage_counts(user_id: str, day: str) -> dict:
    """All of a user's counters for a UTC day, as {kind: count}. For surfacing remaining quota."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT kind, count FROM usage_counters WHERE user_id = %s AND day = %s",
            (user_id, day),
        ).fetchall()
    return {r["kind"]: int(r["count"]) for r in rows}


def delete_user_data(user_id: str) -> dict:
    """Erase a user's app-side data (account-deletion / M10). Deletes their `users` row and
    `usage_counters`, and ANONYMIZES the `cost_events` ledger by nulling `user_id` (the rows
    are an append-only financial record we keep for accounting — nulling de-links the PII).
    Returns row counts per table. Caller also deletes the Supabase auth user (lib/supabase_admin).
    All in one transaction so a partial delete can't leave dangling references."""
    with get_db() as conn:
        anon = conn.execute(
            "UPDATE cost_events SET user_id = NULL WHERE user_id = %s", (user_id,)
        ).rowcount
        usage = conn.execute(
            "DELETE FROM usage_counters WHERE user_id = %s", (user_id,)
        ).rowcount
        users = conn.execute(
            "DELETE FROM users WHERE id = %s", (user_id,)
        ).rowcount
    return {"users": users, "usage_counters": usage, "cost_events_anonymized": anon}


# --- URL liveness cache (global, 7-day TTL) --------------------------------

def get_url_liveness(url: str) -> bool | None:
    """Returns True/False if cached and fresh, None on miss/expiry."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT alive, checked_at FROM url_liveness_cache WHERE url = %s", (url,)
        ).fetchone()
    if row is None:
        return None
    if (time.time() - row["checked_at"]) > SEVEN_DAYS:
        return None
    return bool(row["alive"])


def set_url_liveness(url: str, alive: bool) -> None:
    with get_db() as conn:
        conn.execute(
            "INSERT INTO url_liveness_cache (url, alive, checked_at) VALUES (%s, %s, %s) "
            "ON CONFLICT (url) DO UPDATE SET alive = EXCLUDED.alive, checked_at = EXCLUDED.checked_at",
            (url, 1 if alive else 0, int(time.time())),
        )


# --- Listing store (background-ingested job listings) ----------------------
# A queryable collection, not the one-blob-per-key pattern above. Written by
# worker/ingest.py; read by the serving layer.

def _row_with_bytes_embedding(d: dict) -> dict:
    """psycopg3 returns BYTEA as `bytes`, but normalize defensively (a future driver/
    version could hand back a memoryview) so embeddings.from_bytes(np.frombuffer) is safe."""
    emb = d.get("embedding")
    if emb is not None and not isinstance(emb, bytes):
        d["embedding"] = bytes(emb)
    return d


def upsert_listing(
    listing: dict,
    *,
    bucket: str,
    niche_key: str,
    status: str = "valid",
    validation_reason: str | None = None,
) -> None:
    """Insert or refresh one listing keyed by url.

    `listing` is the scraped+enriched dict ({url, search_title, snippet,
    verified_location?, is_category_page?, company?}). On re-discovery, first_seen is
    preserved (ON CONFLICT keeps the original) while last_seen/last_validated advance.
    """
    now = int(time.time())
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO listing_store
                (url, bucket, niche_key, company, search_title, snippet,
                 verified_location, is_category_page, status, validation_reason,
                 raw_json, first_seen, last_seen, last_validated)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (niche_key, bucket, url) DO UPDATE SET
                company           = excluded.company,
                search_title      = excluded.search_title,
                snippet           = excluded.snippet,
                verified_location = excluded.verified_location,
                is_category_page  = excluded.is_category_page,
                status            = excluded.status,
                validation_reason = excluded.validation_reason,
                raw_json          = excluded.raw_json,
                last_seen         = excluded.last_seen,
                last_validated    = excluded.last_validated,
                -- Invalidate the precompute when the content the parse/embed was keyed on
                -- changes, so the worker re-parses. `IS DISTINCT FROM` (not `<>`, which
                -- yields NULL when either side is NULL and would silently never fire)
                -- compares safely across NULLs. parsed_json/embedding/etc. are
                -- intentionally NOT touched here — they're stale but harmless; serving
                -- guards on parsed_at/model and the parse pass overwrites them next run.
                parsed_at = CASE
                    WHEN listing_store.search_title      IS DISTINCT FROM excluded.search_title
                      OR listing_store.snippet           IS DISTINCT FROM excluded.snippet
                      OR listing_store.verified_location IS DISTINCT FROM excluded.verified_location
                      OR listing_store.company           IS DISTINCT FROM excluded.company
                    THEN NULL ELSE listing_store.parsed_at END
            """,
            (
                listing["url"], bucket, niche_key, listing.get("company"),
                listing.get("search_title"), listing.get("snippet"),
                listing.get("verified_location"),
                1 if listing.get("is_category_page") else 0,
                status, validation_reason, json.dumps(listing),
                now, now, now,
            ),
        )


def get_listings(
    niche_key: str | None = None,
    bucket: str | None = None,
    *,
    only_valid: bool = True,
    max_age: int | None = None,
) -> list[dict]:
    """Query the listing collection. Filters by niche_key/bucket when given,
    status='valid' when only_valid, and last_validated within max_age seconds when
    given. Returns row dicts."""
    clauses: list[str] = []
    params: list = []
    if niche_key is not None:
        clauses.append("niche_key = %s"); params.append(niche_key)
    if bucket is not None:
        clauses.append("bucket = %s"); params.append(bucket)
    if only_valid:
        clauses.append("status = 'valid'")
    if max_age is not None:
        clauses.append("last_validated >= %s"); params.append(int(time.time()) - max_age)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    with get_db() as conn:
        rows = conn.execute(f"SELECT * FROM listing_store{where}", params).fetchall()
    return [_row_with_bytes_embedding(dict(r)) for r in rows]


def get_listing_by_url(url: str) -> dict | None:
    """Fetch a single listing row by URL alone, for the deferred /internships/annotate pass.

    The PK is (niche_key, bucket, url) so a URL can have several rows (e.g. a company in both
    _national and _reach), but parsed_json/snippet/etc. are profile-independent and identical
    across them — so any row serves the annotation. We prefer a parsed, valid row (it carries
    the trusted display fields the slim annotate uses) and fall back to whatever exists."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM listing_store WHERE url = %s "
            "ORDER BY (status='valid') DESC, (parsed_json IS NOT NULL) DESC LIMIT 1",
            (url,),
        ).fetchone()
    return _row_with_bytes_embedding(dict(row)) if row else None


def get_listings_to_parse(limit: int | None = None) -> list[dict]:
    """Valid listings the worker's parse pass hasn't processed yet (parsed_at IS NULL).
    Returns row dicts (full columns, incl. company/search_title/snippet/verified_location
    needed to build the embed text). Uses idx_listing_unparsed."""
    sql = "SELECT * FROM listing_store WHERE status='valid' AND parsed_at IS NULL"
    params: list = []
    if limit is not None:
        sql += " LIMIT %s"; params.append(limit)
    with get_db() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def get_listings_to_embed(limit: int | None = None) -> list[dict]:
    """Parsed valid listings that are still MISSING an embedding (e.g. Voyage was
    down/rate-limited when they were parsed). Lets a later run backfill embeddings WITHOUT
    re-running the Haiku parse — avoids the 'Voyage-down trap' where parsed_at is stamped
    but the vector never lands. Uses idx_listing_unparsed only loosely; this is a rare,
    bounded scan."""
    sql = ("SELECT * FROM listing_store WHERE status='valid' "
           "AND parsed_at IS NOT NULL AND embedding IS NULL")
    params: list = []
    if limit is not None:
        sql += " LIMIT %s"; params.append(limit)
    with get_db() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def set_listing_embedding(
    niche_key: str, bucket: str, url: str, *,
    embedding_bytes: bytes, model: str, dim: int,
) -> None:
    """Attach (only) the embedding to an already-parsed row — does NOT touch parsed_json /
    parsed_at / content_hash. Used by the embed backfill pass."""
    with get_db() as conn:
        conn.execute(
            "UPDATE listing_store SET embedding=%s, embedding_model=%s, embedding_dim=%s "
            "WHERE niche_key=%s AND bucket=%s AND url=%s",
            (embedding_bytes, model, dim, niche_key, bucket, url),
        )


def set_listing_parse(
    niche_key: str, bucket: str, url: str, *,
    parsed_json: str,
    embedding_bytes: bytes | None,
    model: str | None,
    dim: int | None,
    content_hash: str,
) -> None:
    """Record the precomputed parse + embedding for one listing row (full composite PK).

    Success is defined as `parsed_json` present → parsed_at is stamped so the row drops out
    of get_listings_to_parse. The embedding is BEST-EFFORT: when Voyage is unavailable,
    embedding_bytes/model/dim are None, the parse is still recorded (Haiku isn't re-run),
    and serving simply treats the row as unranked. (A future row whose embedding stayed
    NULL can be re-embedded by a separate pass without re-parsing — see plan follow-up.)"""
    with get_db() as conn:
        conn.execute(
            "UPDATE listing_store SET parsed_json=%s, embedding=%s, embedding_model=%s, "
            "embedding_dim=%s, content_hash=%s, parsed_at=%s "
            "WHERE niche_key=%s AND bucket=%s AND url=%s",
            (parsed_json, embedding_bytes, model, dim, content_hash, int(time.time()),
             niche_key, bucket, url),
        )


def mark_listing_dead(url: str, reason: str) -> None:
    """Flag a listing as dead (failed re-validation). No-ops if the url was never
    stored — brand-new dead listings simply aren't recorded. Kept (not deleted) so
    serving can filter on status='valid' and the row is auditable."""
    now = int(time.time())
    with get_db() as conn:
        conn.execute(
            "UPDATE listing_store SET status='dead', validation_reason=%s, "
            "last_seen=%s, last_validated=%s WHERE url=%s",
            (reason, now, now, url),
        )


def prune_stale_listings(max_age: int) -> int:
    """Delete listings not re-discovered (last_seen) within max_age seconds. Returns
    the number deleted. The hard GC for listings that fell off all search results."""
    cutoff = int(time.time()) - max_age
    with get_db() as conn:
        cur = conn.execute("DELETE FROM listing_store WHERE last_seen < %s", (cutoff,))
        return cur.rowcount


def count_listings_by_niche_bucket() -> list[dict]:
    """[{niche_key, bucket, status, count}, ...] — for worker logging / inspection."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT niche_key, bucket, status, COUNT(*) AS count "
            "FROM listing_store GROUP BY niche_key, bucket, status "
            "ORDER BY niche_key, bucket, status"
        ).fetchall()
    return [dict(r) for r in rows]


# --- Metro rotation (which metros have a pre-ingested `local` pool) --------

def get_rotation_metros() -> list[str]:
    """Metros the worker refreshes / that serve local from the index, oldest first."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT metro FROM metro_rotation ORDER BY added_at"
        ).fetchall()
    return [r["metro"] for r in rows]


def add_rotation_metro(metro: str, source: str = "serving") -> None:
    """Promote a metro into the rotation. Idempotent (ON CONFLICT DO NOTHING), so concurrent
    first-hits for the same new metro are race-safe."""
    with get_db() as conn:
        conn.execute(
            "INSERT INTO metro_rotation (metro, added_at, source) VALUES (%s, %s, %s) "
            "ON CONFLICT (metro) DO NOTHING",
            (metro, int(time.time()), source),
        )
