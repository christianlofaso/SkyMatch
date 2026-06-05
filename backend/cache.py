import hashlib
import json
import re
import sqlite3
import time
from pathlib import Path

DB_PATH = Path(__file__).parent / "pathfinder_cache.db"

SEVEN_DAYS = 7 * 24 * 3600
ONE_DAY = 24 * 3600
THIRTY_DAYS = 30 * 24 * 3600

_WS_RE = re.compile(r"\s+")


def get_db() -> sqlite3.Connection:
    # timeout + busy_timeout let a momentary write lock wait rather than raising
    # "database is locked" — needed because the standalone ingestion worker
    # (worker/ingest.py) writes listing_store in a separate process while uvicorn reads.
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=15000;")
    return conn


def init_db() -> None:
    with get_db() as conn:
        # WAL is a persistent property of the DB file (set once) — it lets the worker
        # process write while API requests read the same file without blocking.
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS profile_cache (
                linkedin_url TEXT PRIMARY KEY,
                data         TEXT NOT NULL,
                created_at   INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS people_search_cache (
                filter_hash  TEXT PRIMARY KEY,
                data         TEXT NOT NULL,
                created_at   INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS jobs_search_cache (
                filter_hash  TEXT PRIMARY KEY,
                data         TEXT NOT NULL,
                created_at   INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS run_cache (
                url          TEXT PRIMARY KEY,
                data         TEXT NOT NULL,
                created_at   INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS url_validation_cache (
                url        TEXT PRIMARY KEY,
                data       TEXT NOT NULL,
                created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS enrichment_cache (
                url        TEXT PRIMARY KEY,
                data       TEXT NOT NULL,
                created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS analysis_cache (
                cache_key  TEXT PRIMARY KEY,
                data       TEXT NOT NULL,
                created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS requirements_cache (
                job_hash   TEXT PRIMARY KEY,
                data       TEXT NOT NULL,
                created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS job_fetch_cache (
                url_hash   TEXT PRIMARY KEY,
                data       TEXT NOT NULL,
                created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS user_analysis_cache (
                cache_key  TEXT PRIMARY KEY,
                mode       TEXT NOT NULL,
                data       TEXT NOT NULL,
                created_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_user_analysis_mode
                ON user_analysis_cache(mode);
            CREATE TABLE IF NOT EXISTS url_liveness_cache (
                url        TEXT PRIMARY KEY,
                alive      INTEGER NOT NULL,
                checked_at INTEGER NOT NULL
            );
            -- Per-(profile, role) "why you fit" reasoning from /internships/annotate.
            -- cache_key = profile_hash : bucket : (listing content_hash, else url) — see
            -- annotate_cache_key. 30-day TTL via _get. The served feed stays zero-LLM; this
            -- just spares the deferred Sonnet call on repeat (cross-device / same-profile) views.
            CREATE TABLE IF NOT EXISTS annotate_cache (
                cache_key  TEXT PRIMARY KEY,
                data       TEXT NOT NULL,
                created_at INTEGER NOT NULL
            );
            -- Append-only ledger of Claude spend + cache savings (written by lib/cost.py).
            -- kind='call' rows carry real tokens/usd; kind='hit' rows carry est_saved_usd for
            -- a full-call cache avoidance (usd=0). Read by GET /cost/summary.
            CREATE TABLE IF NOT EXISTS cost_events (
                id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at         INTEGER NOT NULL,
                kind               TEXT NOT NULL,        -- 'call' | 'hit'
                session            TEXT,
                label              TEXT,
                model              TEXT,
                input_tokens       INTEGER NOT NULL DEFAULT 0,
                output_tokens      INTEGER NOT NULL DEFAULT 0,
                cache_read_tokens  INTEGER NOT NULL DEFAULT 0,
                cache_write_tokens INTEGER NOT NULL DEFAULT 0,
                usd                REAL NOT NULL DEFAULT 0,
                est_saved_usd      REAL NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_cost_events_created
                ON cost_events(created_at);
            -- Tiny persistent key/value flags for runtime app state (e.g. the manual
            -- kill switch, key='kill_switch' value='on'|'off'). Survives restarts so an
            -- emergency halt stays in effect; read by lib/guard.py, written by /admin.
            CREATE TABLE IF NOT EXISTS app_flags (
                key        TEXT PRIMARY KEY,
                value      TEXT NOT NULL,
                updated_at INTEGER NOT NULL
            );
            -- Pre-ingested job listings, populated by the background worker
            -- (worker/ingest.py). Unlike every other table here (one JSON blob per
            -- key), this is a QUERYABLE COLLECTION the serving layer filters by
            -- niche/bucket/freshness. Holds the PRE-ANNOTATION listing — fit_explanation
            -- is per-user and generated at request time, never stored.
            CREATE TABLE IF NOT EXISTS listing_store (
                url                TEXT NOT NULL,
                bucket             TEXT NOT NULL,      -- startup|big_tech|local|reach
                niche_key          TEXT NOT NULL,      -- Niche.key, or '_reach' pool
                company            TEXT,
                search_title       TEXT,
                snippet            TEXT,
                verified_location  TEXT,
                is_category_page   INTEGER NOT NULL DEFAULT 0,
                status             TEXT NOT NULL DEFAULT 'valid',  -- valid|dead
                validation_reason  TEXT,
                raw_json           TEXT,
                first_seen         INTEGER NOT NULL,
                last_seen          INTEGER NOT NULL,
                last_validated     INTEGER NOT NULL,
                -- Precompute columns (worker/ingest.py parse pass; see set_listing_parse).
                -- All NULL until parsed. parsed_at IS NULL is the single "needs work"
                -- sentinel; upsert NULLs it back when the listing's content changes.
                parsed_json        TEXT,     -- {title,company,company_description,location,
                                             --  skills[],seniority,role_category,
                                             --  is_internship,sponsorship}
                embedding          BLOB,     -- normalized float32 vector (np.tobytes)
                embedding_model    TEXT,     -- model id the vector was produced with
                embedding_dim      INTEGER,  -- authoritative vector length
                content_hash       TEXT,     -- hash of the embed text the parse was keyed on
                parsed_at          INTEGER,  -- when parse+embed last ran (NULL = unparsed)
                -- Composite key: the SAME url legitimately belongs to multiple contexts
                -- (Stripe's listing is big_tech for every CS niche AND in the _reach pool).
                -- Keying on url alone would let later niches clobber earlier ones.
                PRIMARY KEY (niche_key, bucket, url)
            );
            CREATE INDEX IF NOT EXISTS idx_listing_niche_bucket
                ON listing_store(niche_key, bucket);
            CREATE INDEX IF NOT EXISTS idx_listing_bucket
                ON listing_store(bucket);
            CREATE INDEX IF NOT EXISTS idx_listing_freshness
                ON listing_store(last_validated);
            CREATE INDEX IF NOT EXISTS idx_listing_status
                ON listing_store(status);
            -- Which metros the worker refreshes `local` for, and which serve local from
            -- the index. Seeded with SEED_METROS; serving promotes uncovered metros here
            -- on first request. `metro` is the canonical _parse_metro output.
            CREATE TABLE IF NOT EXISTS metro_rotation (
                metro     TEXT PRIMARY KEY,
                added_at  INTEGER NOT NULL,
                source    TEXT NOT NULL        -- 'seed' | 'serving'
            );
        """)
        # Additive migration for DBs created before the precompute columns existed —
        # CREATE TABLE IF NOT EXISTS won't ALTER an existing table. ADD COLUMN with no
        # default is instant; existing rows get NULL (= unparsed), so the worker's next
        # parse pass backfills them. Idempotent: skips columns already present.
        existing_cols = {r["name"] for r in conn.execute("PRAGMA table_info(listing_store)")}
        for col, decl in (
            ("parsed_json", "TEXT"), ("embedding", "BLOB"), ("embedding_model", "TEXT"),
            ("embedding_dim", "INTEGER"), ("content_hash", "TEXT"), ("parsed_at", "INTEGER"),
        ):
            if col not in existing_cols:
                conn.execute(f"ALTER TABLE listing_store ADD COLUMN {col} {decl}")
        # Created AFTER the migration: it references parsed_at, which the ALTER loop above
        # adds to pre-existing tables (the inline CREATE TABLE only has it for fresh DBs).
        # Cheap scan for the worker's parse pass (status='valid' AND parsed_at IS NULL).
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_listing_unparsed "
            "ON listing_store(status, parsed_at)"
        )

        # Seed the rotation (idempotent — INSERT OR IGNORE keeps existing rows).
        from config.niches import SEED_METROS
        now = int(time.time())
        conn.executemany(
            "INSERT OR IGNORE INTO metro_rotation (metro, added_at, source) VALUES (?, ?, 'seed')",
            [(m, now) for m in SEED_METROS],
        )


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
    with get_db() as conn:
        row = conn.execute(
            f"SELECT data, created_at FROM {table} WHERE {key_col} = ?", (key_val,)
        ).fetchone()
    if row is None:
        return None
    if ttl and (time.time() - row["created_at"]) > ttl:
        return None
    return json.loads(row["data"])


def _set(table: str, key_col: str, key_val: str, data: dict | list) -> None:
    with get_db() as conn:
        conn.execute(
            f"INSERT OR REPLACE INTO {table} ({key_col}, data, created_at) VALUES (?, ?, ?)",
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
            "INSERT OR REPLACE INTO user_analysis_cache "
            "(cache_key, mode, data, created_at) VALUES (?, ?, ?, ?)",
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
    usd: float = 0.0, est_saved_usd: float = 0.0,
) -> None:
    with get_db() as conn:
        conn.execute(
            "INSERT INTO cost_events (created_at, kind, session, label, model, "
            "input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, usd, est_saved_usd) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (int(time.time()), kind, session, label, model, input_tokens, output_tokens,
             cache_read_tokens, cache_write_tokens, usd, est_saved_usd),
        )


def query_cost_events(since: int) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM cost_events WHERE created_at >= ? ORDER BY created_at", (since,)
        ).fetchall()
    return [dict(r) for r in rows]


def sum_spend_since(since: int) -> float:
    """Total real Claude spend (USD) since `since` (Unix ts). Only kind='call' rows
    carry spend; 'hit' rows are savings. Used by the spend-cap kill switch."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(usd), 0.0) AS total FROM cost_events "
            "WHERE kind = 'call' AND created_at >= ?",
            (since,),
        ).fetchone()
    return float(row["total"]) if row else 0.0


# --- App flags (persistent runtime key/value, e.g. the manual kill switch) ----

def get_flag(key: str) -> str | None:
    with get_db() as conn:
        row = conn.execute("SELECT value FROM app_flags WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_flag(key: str, value: str) -> None:
    with get_db() as conn:
        conn.execute(
            "INSERT INTO app_flags (key, value, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
            (key, value, int(time.time())),
        )


# --- URL liveness cache (global, 7-day TTL) --------------------------------

def get_url_liveness(url: str) -> bool | None:
    """Returns True/False if cached and fresh, None on miss/expiry."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT alive, checked_at FROM url_liveness_cache WHERE url = ?", (url,)
        ).fetchone()
    if row is None:
        return None
    if (time.time() - row["checked_at"]) > SEVEN_DAYS:
        return None
    return bool(row["alive"])


def set_url_liveness(url: str, alive: bool) -> None:
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO url_liveness_cache "
            "(url, alive, checked_at) VALUES (?, ?, ?)",
            (url, 1 if alive else 0, int(time.time())),
        )


# --- Listing store (background-ingested job listings) ----------------------
# A queryable collection, not the one-blob-per-key pattern above. Written by
# worker/ingest.py; read by the serving layer (next step).

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
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(niche_key, bucket, url) DO UPDATE SET
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
                -- changes, so the worker re-parses. `IS NOT` (not `<>`, which yields NULL
                -- when either side is NULL and would silently never fire) compares safely
                -- across NULLs. parsed_json/embedding/etc. are intentionally NOT touched
                -- here — they're stale but harmless; serving guards on parsed_at/model and
                -- the parse pass overwrites them on the next run.
                parsed_at = CASE
                    WHEN listing_store.search_title      IS NOT excluded.search_title
                      OR listing_store.snippet           IS NOT excluded.snippet
                      OR listing_store.verified_location IS NOT excluded.verified_location
                      OR listing_store.company           IS NOT excluded.company
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
        clauses.append("niche_key = ?"); params.append(niche_key)
    if bucket is not None:
        clauses.append("bucket = ?"); params.append(bucket)
    if only_valid:
        clauses.append("status = 'valid'")
    if max_age is not None:
        clauses.append("last_validated >= ?"); params.append(int(time.time()) - max_age)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    with get_db() as conn:
        rows = conn.execute(f"SELECT * FROM listing_store{where}", params).fetchall()
    return [dict(r) for r in rows]


def get_listing_by_url(url: str) -> dict | None:
    """Fetch a single listing row by URL alone, for the deferred /internships/annotate pass.

    The PK is (niche_key, bucket, url) so a URL can have several rows (e.g. a company in both
    _national and _reach), but parsed_json/snippet/etc. are profile-independent and identical
    across them — so any row serves the annotation. We prefer a parsed, valid row (it carries
    the trusted display fields the slim annotate uses) and fall back to whatever exists."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM listing_store WHERE url = ? "
            "ORDER BY (status='valid') DESC, (parsed_json IS NOT NULL) DESC LIMIT 1",
            (url,),
        ).fetchone()
    return dict(row) if row else None


def get_listings_to_parse(limit: int | None = None) -> list[dict]:
    """Valid listings the worker's parse pass hasn't processed yet (parsed_at IS NULL).
    Returns row dicts (full columns, incl. company/search_title/snippet/verified_location
    needed to build the embed text). Uses idx_listing_unparsed."""
    sql = "SELECT * FROM listing_store WHERE status='valid' AND parsed_at IS NULL"
    params: list = []
    if limit is not None:
        sql += " LIMIT ?"; params.append(limit)
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
        sql += " LIMIT ?"; params.append(limit)
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
            "UPDATE listing_store SET embedding=?, embedding_model=?, embedding_dim=? "
            "WHERE niche_key=? AND bucket=? AND url=?",
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
            "UPDATE listing_store SET parsed_json=?, embedding=?, embedding_model=?, "
            "embedding_dim=?, content_hash=?, parsed_at=? "
            "WHERE niche_key=? AND bucket=? AND url=?",
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
            "UPDATE listing_store SET status='dead', validation_reason=?, "
            "last_seen=?, last_validated=? WHERE url=?",
            (reason, now, now, url),
        )


def prune_stale_listings(max_age: int) -> int:
    """Delete listings not re-discovered (last_seen) within max_age seconds. Returns
    the number deleted. The hard GC for listings that fell off all search results."""
    cutoff = int(time.time()) - max_age
    with get_db() as conn:
        cur = conn.execute("DELETE FROM listing_store WHERE last_seen < ?", (cutoff,))
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
    """Promote a metro into the rotation. Idempotent (INSERT OR IGNORE), so concurrent
    first-hits for the same new metro are race-safe."""
    with get_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO metro_rotation (metro, added_at, source) VALUES (?, ?, ?)",
            (metro, int(time.time()), source),
        )
