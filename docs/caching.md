# Caching

All caching in `cache.py` using `pathfinder_cache.db` (SQLite, auto-created by `init_db()`).

| Table | Key | TTL | Stores |
|-------|-----|-----|--------|
| `profile_cache` | `linkedin_url` | None (permanent) | `ProfileAnalysis` / `UnifiedProfile` dict |
| `people_search_cache` | `filter_hash` | 7 days | List of LinkedIn people results |
| `jobs_search_cache` | `filter_hash` | 1 day | List of LinkedIn job results |
| `run_cache` | `url` | 1 day | `RunResponse` dict |
| `url_validation_cache` | `url` | 1 day | `{"is_valid": bool, "reason": str}` |
| `enrichment_cache` | `url` | 1 day | `{"verified_location": str\|None, "is_category_page": bool}` |
| `analysis_cache` | `cache_key` | 1 day | `AnalysisResponse` dict — **orphaned** since quick-mode / batch landed; no longer read or written |
| `requirements_cache` | `job_hash` | 30 days | `{"job_summary": dict, "requirements": [dict, ...]}` — global, shared across users |
| `job_fetch_cache` | `url_hash` (sha256 of URL) | 3 days | `{"text", "posted_at", "apply_url", "path"}` — the scraped job page, so a 2nd `/analyze` of the same URL (any profile) skips the expensive fetch (esp. Firecrawl JS render). Global. |
| `user_analysis_cache` | `cache_key = "{mode}:{profile_hash}:{job_hash}"` | 30 days | `AnalysisResponse` or `QuickAnalysisResponse` dict; extra `mode` column enables selective wipes. Full-mode rows now also store the Phase 3 `roadmap` / `roadmap_note` / `project_suggestion` fields. |
| `url_liveness_cache` | `url` | 7 days | `{alive: 0\|1, checked_at: epoch}` — Phase 3 HEAD-check result for roadmap resource URLs. Global, shared across users. |
| `listing_store` | `(niche_key, bucket, url)` composite PK | soft `last_validated`; GC at 14d `last_seen` | **Queryable collection** of pre-ingested internship listings (one row per listing), written by `worker/ingest.py`, read by `search_internships`. Columns: `url, bucket, niche_key, company, search_title, snippet, verified_location, is_category_page, status, validation_reason, raw_json, first_seen, last_seen, last_validated`, **+ precompute columns** `parsed_json, embedding, embedding_model, embedding_dim, content_hash, parsed_at` (all NULL until the worker's parse pass fills them). Holds the **pre-annotation, pre-parse** listing (no per-user `fit_explanation`). |
| `metro_rotation` | `metro` | None | `{added_at, source}` — which metros have a pre-ingested `local` pool. Seeded with the ~30 `SEED_METROS` (`source='seed'`, idempotent `INSERT OR IGNORE` in `init_db()`); serving promotes any still-uncovered metro (`source='serving'`). `metro` is the canonical `_parse_metro` output, and every `_STATE_FALLBACK` value is a seeded metro so US locations resolve into the index. Rotation size doesn't affect serving cost (one metro read per request) but does scale the worker's per-run local-ingest time. |

**`listing_store` is the only multi-row collection table** (everything else is one blob per key). It is NOT TTL-on-read like the caches: `get_listings(niche_key, bucket, *, only_valid=True, max_age=None)` filters on `status='valid'` and optionally `last_validated >= now-max_age`; rows are pruned by `prune_stale_listings(max_age)` (deletes by `last_seen`). The composite PK lets the same URL coexist across niches/buckets (a Stripe listing is `big_tech` for every national field AND in `_reach`). `niche_key` is `"_national"` (startup/big_tech), `"_reach"` (reach), or a parsed metro (local). Writers: `upsert_listing` (`INSERT ... ON CONFLICT(niche_key,bucket,url) DO UPDATE`, preserves `first_seen`), `mark_listing_dead`, `prune_stale_listings`, `count_listings_by_niche_bucket`.

**Precompute columns + parse pass.** `parsed_json` (Haiku-extracted `{title, company, company_description, location, skills[], seniority, role_category, is_internship, requires_phd, sponsorship}`) and `embedding` (normalized float32 Voyage vector, raw bytes) are filled **once per listing** by `worker/ingest.py`'s `parse_pass()` — NOT in the request path. `parsed_at IS NULL` is the single "needs work" sentinel: `get_listings_to_parse()` returns those rows; `set_listing_parse()` stamps them (parse success alone sets `parsed_at`; the embedding is best-effort and stays NULL if Voyage is down). `upsert_listing`'s `ON CONFLICT` **NULLs `parsed_at` when `search_title`/`snippet`/`verified_location`/`company` change** (using `IS NOT`, not `<>`, so NULLs compare correctly), so a content change triggers re-parse next run. The migration in `init_db()` `ALTER TABLE ADD COLUMN`s these onto pre-existing DBs (existing rows → NULL = unparsed). `idx_listing_unparsed (status, parsed_at)` keeps the parse-pass scan cheap. **Caveat:** changing `EMBED_MODEL` orphans stored vectors (serving only cosine-matches the same model+dim and treats the rest as unranked); `content_hash` does NOT fire on a model swap — reset manually with `UPDATE listing_store SET parsed_at=NULL`.

**WAL mode** is set in `init_db()` (`PRAGMA journal_mode=WAL` + `busy_timeout=15000`, and `get_db()` opens with `timeout=15`) so the standalone worker process and uvicorn can read/write `pathfinder_cache.db` concurrently. The `.db-wal` / `.db-shm` sidecar files are normal — gitignore them.

**Current key format** is derived from `_compute_job_id(url, text)` → `"url:<canonical_url>"` when a URL is provided, `"text:<sha256(normalize)[:32]>"` otherwise. Same URL across fetches → same key (fixes Firecrawl-induced cache misses). `profile_hash` hashes the full canonical `profile.model_dump_json()` (fixes an earlier 500-char truncation bug from the legacy `analysis_cache` table). That legacy table can be dropped in a future cleanup.

**Most tables use a single `data TEXT NOT NULL` column.** Exceptions: `user_analysis_cache` adds a `mode TEXT NOT NULL` column for selective deletes; `listing_store` and `metro_rotation` are typed multi-column tables (not the `data`-blob shape) with their own helpers. The generic `_get`/`_set` helpers work for the blob caches; `set_user_analysis_cache`, the `listing_store` helpers, and the `metro_rotation` helpers write directly.

**To clear a table** (e.g. after changing validation logic):
```
py -3.12 -c "import sqlite3; c=sqlite3.connect(r'backend\pathfinder_cache.db'); c.execute('DELETE FROM url_validation_cache'); c.commit()"
```

**To fully reset:** delete `pathfinder_cache.db`. Recreates on next server start.
