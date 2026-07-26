r"""One-off logo backfill — re-resolve ONLY each listing's `logo_url` in place.

Why this exists: the parse pass (worker/ingest.parse_pass) is INCREMENTAL — it only touches
rows with `parsed_at IS NULL`. Once a row is parsed, the worker never re-runs Haiku/embed on it,
so a *change to logo resolution alone* (e.g. adding the LOGODEV_* keys after the first ingest, or
extending lib/logo_resolver) would never reach already-parsed rows without nulling `parsed_at` and
paying for a full re-parse (Haiku + Firecrawl + Voyage). This script does the cheap thing instead:
re-runs ONLY lib.logo_resolver.resolve_logo per row and rewrites `parsed_json.logo_url`. It does NOT
touch `parsed_at`, `embedding`, or `content_hash` — so the row stays parsed, the embed text is
unchanged, and the annotate cache (keyed on content_hash) stays valid. No Haiku, Firecrawl, or Voyage.

Safety: DRY-RUN by default (prints what would change, writes nothing). Pass --apply to persist.
The target database is printed loudly at startup — VERIFY it before --apply. Note the local
backend/.env points at PROD; to target staging, override DATABASE_URL for the run (it wins over .env
because load_dotenv does not override an already-set env var).

Run LOCALLY against staging (PowerShell):
    cd backend
    $env:DATABASE_URL = "<staging txn-pooler URL, :6543>"
    .\venv\Scripts\python.exe -m worker.backfill_logos              # dry run — inspect the plan
    .\venv\Scripts\python.exe -m worker.backfill_logos --apply      # persist

Run ON Railway (uses the service's own DATABASE_URL + LOGODEV_* env, no local secret handling):
    Temporarily set the worker service's start command to
        python -m worker.backfill_logos --apply
    ensure LOGODEV_SECRET_KEY + LOGODEV_PUBLISHABLE_KEY are set on the service, click Run now,
    then REVERT the command back to `python -m worker.ingest`.
"""
import sys

# Force UTF-8 stdout/stderr (Windows defaults to cp1252 and a stray non-ASCII char would crash the
# run mid-stream). Harmless no-op when the stream is already UTF-8. Same guard as worker/ingest.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# Load .env BEFORE importing db/cache/logo_resolver — db.py reads DATABASE_URL and logo_resolver
# reads LOGODEV_* at import time. load_dotenv(override=False) means a DATABASE_URL already set in
# the shell (to point at staging) takes precedence over .env (which points at prod locally).
import argparse  # noqa: E402
import asyncio  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
from collections import Counter  # noqa: E402
from pathlib import Path  # noqa: E402
from urllib.parse import urlsplit  # noqa: E402

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import httpx  # noqa: E402

from cache import get_db, init_db  # noqa: E402
from lib import logo_resolver  # noqa: E402
from lib.logo_resolver import resolve_logo  # noqa: E402

# Bounded in-flight logo.dev searches (one GET per uncurated, un-extracted company name).
RESOLVE_CONCURRENCY = int(os.getenv("LOGO_BACKFILL_CONCURRENCY", "8"))


def _classify(url: str | None) -> str:
    """Bucket a logo URL by source, for the before/after report."""
    if not url:
        return "none"
    if "img.logo.dev" in url:
        return "logodev"
    if "google.com/s2/favicons" in url:
        return "favicon"
    return "other"


def _db_target() -> str:
    """host:port/db of the active DATABASE_URL, credentials stripped — printed for confirmation."""
    try:
        s = urlsplit(os.getenv("DATABASE_URL", ""))
        return f"{s.hostname}:{s.port}/{s.path.lstrip('/')}"
    except Exception:
        return "(unparseable DATABASE_URL)"


def _fetch_rows(bucket: str | None, niche: str | None, limit: int | None) -> list[dict]:
    """Parsed, servable rows. Only status='valid' + parsed (others aren't served, so spending a
    logo.dev search on them is waste)."""
    sql = ("SELECT niche_key, bucket, url, parsed_json FROM listing_store "
           "WHERE status = 'valid' AND parsed_json IS NOT NULL")
    params: list = []
    if niche:
        sql += " AND niche_key = %s"
        params.append(niche)
    if bucket:
        sql += " AND bucket = %s"
        params.append(bucket)
    sql += " ORDER BY niche_key, bucket, url"
    if limit:
        sql += " LIMIT %s"
        params.append(limit)
    with get_db() as conn:
        return conn.execute(sql, tuple(params)).fetchall()


async def _resolve_all(rows: list[dict]) -> list[tuple]:
    """Resolve a fresh logo for every row, bounded. Returns (row, parsed_dict, old_url, new_url)
    tuples (skipping rows whose parsed_json isn't a JSON object)."""
    sem = asyncio.Semaphore(RESOLVE_CONCURRENCY)

    async def _one(row: dict, client: httpx.AsyncClient) -> tuple | None:
        try:
            parsed = json.loads(row["parsed_json"])
        except Exception:
            return None
        if not isinstance(parsed, dict):
            return None
        old = parsed.get("logo_url")
        async with sem:
            new = await resolve_logo(parsed.get("company"), parsed.get("company_domain"), client)
        return (row, parsed, old, new)

    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(*[_one(r, client) for r in rows])
    return [r for r in results if r is not None]


def _apply_updates(changes: list[tuple]) -> None:
    """Persist new logo_url for changed rows — rewrites ONLY parsed_json (not parsed_at/embedding/
    content_hash). PK is (niche_key, bucket, url)."""
    with get_db() as conn:
        for niche_key, bucket, url, parsed_json in changes:
            conn.execute(
                "UPDATE listing_store SET parsed_json = %s "
                "WHERE niche_key = %s AND bucket = %s AND url = %s",
                (parsed_json, niche_key, bucket, url),
            )


async def main() -> None:
    ap = argparse.ArgumentParser(description="Re-resolve listing_store logo_url in place (no re-parse).")
    ap.add_argument("--apply", action="store_true", help="persist changes (default: dry run)")
    ap.add_argument("--force", action="store_true",
                    help="proceed with --apply even when no LOGODEV_* key is set")
    ap.add_argument("--bucket", help="restrict to one bucket (big_tech/startup/reach/local)")
    ap.add_argument("--niche", help="restrict to one niche_key")
    ap.add_argument("--limit", type=int, help="cap rows processed (for a spot-check)")
    args = ap.parse_args()

    init_db()

    has_keys = bool(logo_resolver.LOGODEV_SECRET or logo_resolver.LOGODEV_PUBLISHABLE)
    print(f"[backfill-logos] TARGET DB : {_db_target()}")
    print(f"[backfill-logos] LOGODEV   : secret={'set' if logo_resolver.LOGODEV_SECRET else 'UNSET'}, "
          f"publishable={'set' if logo_resolver.LOGODEV_PUBLISHABLE else 'UNSET'}")
    print(f"[backfill-logos] mode      : {'APPLY (writes)' if args.apply else 'DRY RUN (no writes)'}")

    if args.apply and not has_keys and not args.force:
        print("[backfill-logos] ABORT: no LOGODEV_* key set — this would only re-write favicons/"
              "letters, i.e. no improvement. Set the keys (the point of this backfill) or pass "
              "--force to run anyway.")
        return

    rows = _fetch_rows(args.bucket, args.niche, args.limit)
    print(f"[backfill-logos] scanning {len(rows)} parsed, valid listings...")
    resolved = await _resolve_all(rows)

    before, after = Counter(), Counter()
    changes: list[tuple] = []
    for row, parsed, old, new in resolved:
        before[_classify(old)] += 1
        after[_classify(new)] += 1
        # Normalize "" → None so a no-op (both empty) isn't counted as a change.
        if (new or None) != (old or None):
            parsed["logo_url"] = new
            changes.append((row["niche_key"], row["bucket"], row["url"], json.dumps(parsed)))

    def _fmt(c: Counter) -> str:
        return ", ".join(f"{k}={c.get(k, 0)}" for k in ("logodev", "favicon", "other", "none"))

    print(f"[backfill-logos] before : {_fmt(before)}")
    print(f"[backfill-logos] after  : {_fmt(after)}")
    print(f"[backfill-logos] changed: {len(changes)} / {len(resolved)} rows")

    if not args.apply:
        print("[backfill-logos] DRY RUN — nothing written. Re-run with --apply to persist.")
        return
    _apply_updates(changes)
    print(f"[backfill-logos] applied {len(changes)} updates.")


if __name__ == "__main__":
    asyncio.run(main())
