import hashlib
import json
import sqlite3
import time
from pathlib import Path

DB_PATH = Path(__file__).parent / "pathfinder_cache.db"

SEVEN_DAYS = 7 * 24 * 3600
ONE_DAY = 24 * 3600


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_db() as conn:
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
        """)


def hash_filters(filters: dict) -> str:
    serialized = json.dumps(filters, sort_keys=True)
    return hashlib.sha256(serialized.encode()).hexdigest()


def text_cache_key(text: str) -> str:
    h = hashlib.sha256(text[:500].encode()).hexdigest()[:16]
    return f"text:{h}"


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
