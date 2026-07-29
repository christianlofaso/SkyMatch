# Architecture, deep reference

The always-loaded map is [CLAUDE.md](../CLAUDE.md); this file holds the deep detail it points to:
current-state design notes, the full backend-stack rundown, the project-structure tree, and the
cost/auth gate prose.

---

## Current state

### Connections feature is currently disabled in `/run`
The warm LinkedIn *connection* recommendations used to be a parallel branch of `/run`, but are being
reworked to live inside the job listings. `/run` now computes **internships only** (returns
`connections: []`); the backend code (`connections.py`, the `POST /connections/suggest` route) and
the frontend `ConnectionCard` + `ConnectionSchema` are **retained but dormant**, no longer wired
into `/run` or rendered on the results page.

### Ingestion is decoupled from serving
Job listings are no longer scraped live per request. A standalone background worker,
`backend/worker/ingest.py`, run as `python -m worker.ingest` on a cron / Task Scheduler cadence
(~6h), continuously pulls listings from DDG/ATS/Firecrawl into the `listing_store` index, then
**precomputes the profile-independent work once per listing** (a parse pass: Haiku structured/display
fields + a Voyage embedding, both stored on the row). `/run` → `search_internships` serves from that
index with **ZERO LLM on the request path**: a no-LLM **embedding rank** (profile embedded once →
cosine-narrow each bucket) → a **deterministic select+build** (`_select_and_build`: company-diversity
trim → cards assembled straight from the precomputed display fields, raw-column fallback for unparsed
rows). The per-user `fit_explanation`/`reach_gap` ("why you fit") is **deferred AND lazy**: the feed
ships it empty, cards render collapsed (click-to-expand accordions), and only on a card's **first
expand** does the results page call `POST /internships/annotate` for that one role (slim fit-only
`MODEL_MID` call, streamed). The result is cached **server-side** in `annotate_cache` (key
`profile_hash:bucket:content_hash`, 30d → a repeat cross-device / same-profile view is served from
the DB with no LLM) **and** client-side in localStorage. (The score badge stays eager, batch-scored
on load via `/analyze/batch`, also cached.)

- **Three "national" buckets** (startup, big_tech, reach) are metro-independent and served to
  everyone, keyed under `niche_key="_national"` / `"_reach"`.
- **`local`** is the only per-metro pool (keyed by parsed metro). Served from the index if the metro
  is in the rotation (`metro_rotation` table, **seeded with the ~30 `SEED_METROS`** covering where
  CS/ECE students intern; `_STATE_FALLBACK` routes every US state + college towns onto one of them,
  so nearly all students serve from the index). It's **live-fetched** at request time only when the
  metro isn't in rotation **OR its local index is empty/stale** (e.g. a freshly-seeded metro the
  worker hasn't ingested yet, so seeding never serves an empty bucket) (bounded ~35s): scrape +
  validate + upsert, then **run the SAME parse precompute the worker does, Haiku company/role_category
  + Voyage embedding, INLINE** (`lib/precompute.parse_and_embed_rows`, the only LLM on the request
  path, and only for an uncovered metro's first visit) so this request serves clean, field-filtered,
  ranked rows; the metro is then **promoted** into the rotation so the next user + next worker run get
  it from the index. No "unsupported metro" branch. _(A scraped-but-unparsed local row has no resolved
  company → "Unknown", no `role_category` → off-field roles leak, no embedding → no ranking; parsing
  inline closes all three at the source.)_
- The profile-independent scrape/enrich/validate code lives in `backend/lib/ingest_core.py` (shared by
  the worker; the request path uses it only for the local fallback). Config is in
  `backend/config/niches.py` (`NATIONAL_FIELDS`, `SEED_METROS`, `REACH_ATS_SLUGS`).
- **The worker's parse pass (`parse_pass()` in `worker/ingest.py`) makes cheap model calls**, Haiku
  (`MODEL_QUICK`) listing parse via `lib/listing_parser.py` + Voyage embeddings via `lib/embeddings.py`
, but runs **after** store+prune, is **incremental** (only `parsed_at IS NULL` rows), and BOTH
  `ANTHROPIC_API_KEY`/`VOYAGE_API_KEY` are **optional**: missing either skips that work, the row stays
  unparsed, and serving uses its fallback path. The precompute lands in 6 `listing_store` columns
  (`parsed_json`, `embedding`, `embedding_model`, `embedding_dim`, `content_hash`, `parsed_at`);
  `upsert_listing` NULLs `parsed_at` when the listing content changes so it re-parses.
  - **Company resolution** (`_resolve_company` in `listing_parser.py`) is a fallback chain: Haiku's
    answer → stored `company` column → `company_from_url()` (ATS slug / `amazon.jobs`) → `"Unknown"`.
    Placeholder strings Haiku sometimes emits (`"unknown"`, `"N/A"`, …, see `is_placeholder_company`)
    are treated as *missing* at every step. For SPA boards where the company is only on the rendered
    page (wellfound/workatastartup), the parse pass additionally runs a bounded
    `company_from_firecrawl()` render to recover it.
  - **Two follow-on passes** in the worker keep the precompute consistent without re-running Haiku:
    `embed_backfill_pass()` embeds rows that were parsed but never embedded (e.g. Voyage was down,
    `parsed_at` is set on parse success alone, so they'd otherwise never re-enter the parse queue); the
    `scratch/backfill_company*.py` tools re-resolve companies for already-parsed rows (URL-based +
    Firecrawl-based). `scratch/inspect_parse.py` reads back parsed/embedded counts.
- The old live-scrape per-request path in `internships.py` (Claude fabrication via `INTERNSHIPS_SYSTEM`,
  the `_get_url`/`_find_*` URL-finders) has been **removed**, and so has the per-request Sonnet
  **SELECT** + inline **annotation** that briefly replaced it. `search_internships` now serves via
  **embedding rank (no LLM) → `_select_and_build` (no LLM)**: cards are assembled from the precomputed
  display fields (`parsed_json`), with a raw-column fallback for unparsed rows (warming index). For
  unparsed rows the company chain is **`parsed → title("@"/" - ")-derived → company_from_url (ATS slug)
  → column → "Unknown"`** (`_build_internship`/`_fit_fields`), so an ATS-board URL never shows
  "Unknown". The only `MODEL_MID` call left in this file is the **deferred, lazy** slim fit-only
  annotate, exposed as the streamed `POST /internships/annotate` (`_annotate_one` → `_annotate_fit_sync`
  → `{fit_explanation, reach_gap}`); it looks the row up by URL (`cache.get_listing_by_url`) and reads
  `parsed_json` or the raw columns via `_fit_fields`. It is **cached server-side**: `_annotate_one`
  serves a hit from `annotate_cache` (key `profile_hash:bucket:(content_hash|url)`, 30d) **without**
  Sonnet, and writes successful results back, so repeat (profile, role) reasoning is a free index
  read. The local live-fetch fallback keeps `_scrape_local_listings`/`_parse_metro`/`validate_job_url`
  **and runs the worker's parse precompute inline** (`lib/precompute.parse_and_embed_rows`, Haiku, so
  an uncovered metro's first serve is clean/ranked/filtered, not raw). JSON-from-prose recovery lives
  in `backend/lib/jsonparse.py` (shared by `internships.py` + `listing_parser.py`).

---

## Backend stack (detail)

Python 3.12, FastAPI, Anthropic SDK, httpx (async HTTP), LinkdAPI, DuckDuckGo (`ddgs`), Firecrawl
(SPA scraping), pdfplumber + python-docx (resume parsing), Postgres (Supabase in prod) via `psycopg`
v3 + `psycopg_pool` with Alembic migrations (caching + the `listing_store` index, see
`db.py`/`cache.py`/`alembic/`), Pydantic v2, python-dotenv. **DDG/ATS/Firecrawl scraping is
ingestion-side** (`worker/ingest.py` → `lib/ingest_core.py`), not in the request path.

Model IDs are centralized in `backend/config/models.py` (`MODEL_FULL = claude-opus-4-8`,
`MODEL_MID = claude-sonnet-4-6`, `MODEL_QUICK = claude-haiku-4-5`). `analyze.py`, `profile.py`, and
`internships.py` import from there, **`MODEL_MID` (Sonnet) runs the extraction/annotation-style
calls** (profile + rich-field extraction in `profile.py`; in `internships.py`, **only** the deferred
per-role **fit annotation** (`POST /internships/annotate`), the request path / `search_internships`
is zero-LLM; in `analyze.py`, requirement **extraction** + evidence **matching**) where Opus latency
isn't justified. In `analyze.py`, **`MODEL_FULL` (Opus) still runs Phase 3** (`_run_roadmap` +
`_run_project_suggestion`), the dominant `/analyze` cost (~80%; roadmap retries). `connections.py`
still inlines its own `claude-opus-4-8` model string.

**All routes share ONE Anthropic client from `lib/anthropic_client.py`** (raised `max_retries` for
SDK 429 backoff) and gate every Sonnet call through the process-wide `sonnet_slot()` governor (see
gotchas). The worker fires **no Sonnet/Opus calls**, but its **parse pass makes cheap Haiku + Voyage
calls** (`worker/ingest.py` `parse_pass` → `lib/listing_parser.py` + `lib/embeddings.py`), both keys
optional; absent → rows stay unparsed and serving falls back. A `backend/site_handlers/` package
handles vendor SPA career portals (Microsoft today, Workday/SuccessFactors/iCIMS in future).

---

## ndjson streamers, shared pattern

All four ndjson streamers, `/run/stream`, `/analyze/stream`, `/analyze/batch`,
`/internships/annotate`: share one pattern: async-gen yielding `envelope.model_dump_json()+"\n"`,
sessions opened INSIDE the generator, and `cost_guard` as a yield-dependency, NOT middleware, so it
doesn't buffer the `StreamingResponse`.

NOTE: `/run/stream` + `/analyze/stream` serialize WITHOUT `exclude_none`, their envelopes wrap full
data models (RunResponse / AnalysisResponse pieces) whose nullable fields the Zod schemas require
PRESENT, so `exclude_none` would drop them and break validation; the wrapper Zod schemas mark
off-phase fields nullable+optional. (batch/annotate use `exclude_none`, their payload schemas are
already nullish.) The JSON `/run` + `/analyze` stay intact as additive siblings.

---

## Project structure

```
skymatch/
├── CLAUDE.md
├── docs/                         # Deep reference, see the docs index in CLAUDE.md
├── backend/
│   ├── main.py                  # FastAPI app + CORS + router registration + init_db()
│   ├── schemas.py               # All Pydantic models (single source of truth for data shapes)
│   ├── linkd.py                 # Async LinkdAPI client
│   ├── db.py                    # Postgres connection pool + get_db()/init_db() (psycopg_pool; pgBouncer-safe)
│   ├── cache.py                 # Postgres data-access helpers, per-blob caches + listing_store (queryable index) + metro_rotation
│   ├── alembic/                 # Schema migrations (0001_initial_schema = the 16 tables + indexes); owns DDL (init_db no longer does)
│   ├── mocks/run_response.json  # Hardcoded response used when USE_MOCKS=true
│   ├── worker/
│   │   └── ingest.py               # Standalone ingestion worker (python -m worker.ingest) → listing_store; no Sonnet/Opus, but its parse pass makes cheap Haiku + Voyage calls (both keys optional). Spend tagged 'worker:ingest' (excluded from the user kill switch) + bounded by WORKER_SPEND_CAP_USD_DAILY
│   ├── config/
│   │   ├── models.py               # MODEL_FULL / MODEL_MID / MODEL_QUICK constants, single source of truth
│   │   ├── niches.py               # NATIONAL_FIELDS, SEED_METROS, REACH_ATS_SLUGS, _national/_reach keys
│   │   └── resource_allowlist.py   # Trusted-domain frozenset + is_allowlisted() for roadmap resources
│   ├── lib/
│   │   ├── anthropic_client.py     # Shared Anthropic client (raised max_retries) + process-wide Sonnet concurrency cap (sonnet_slot), imported by all routes
│   │   ├── embeddings.py           # Shared Voyage client (is_available/embed_documents/embed_query, normalized float32 + bytes round-trip), worker parse pass + internships rank
│   │   ├── jsonparse.py            # Lenient JSON-from-prose recovery (strip_fences/extract_json_value/parse_json_with_context), internships.py + listing_parser.py
│   │   ├── listing_parser.py       # Ingestion-time Haiku listing parse (structured/display fields) + build_embed_text/content_hash, used by worker parse pass
│   │   ├── ingest_core.py          # Profile-independent scrape/enrich/validate (DDG/ATS/Firecrawl), shared by worker + local fallback
│   │   ├── firecrawl.py            # Shared Firecrawl client (is_available/scrape/JOB_SCHEMA), used by analyze.py + ingest_core.py
│   │   ├── resource_validation.py  # Generic-URL reject + allowlist + async HEAD liveness for roadmap URLs (cached 7d)
│   │   ├── timing.py               # Request timing, timing_session/timed/timed_call → sorted [timing] breakdown
│   │   ├── cost.py                 # Token/cost accounting, cost_session/record_usage/record_cache_hit → [cost] log + persisted to cost_events ledger (read by GET /cost/summary)
│   │   └── supabase_admin.py       # Supabase Admin API client (service_role), auth-user delete for DELETE /account; best-effort, optional (the only backend→Supabase HTTP call)
│   ├── site_handlers/           # Per-vendor SPA career-portal handlers (base.py + microsoft.py)
│   ├── prompts/                 # *.txt system prompts (extraction, matching, quick_verdict, roadmap, …)
│   └── routes/
│       ├── run.py               # POST /run, orchestrator (profile → internships; connections branch removed); also handles resume merge
│       ├── profile.py           # POST /profile/analyze, Claude extraction; extract_rich_fields
│       ├── resume.py            # POST /profile/from-resume, file upload + parse + cache
│       ├── analyze.py           # POST /analyze + /analyze/batch, full + quick pipelines, caches
│       ├── connections.py       # POST /connections/suggest, LinkdAPI + Claude (DORMANT: retained but no longer called by /run)
│       ├── internships.py       # POST /internships/search (zero-LLM serve) + /internships/annotate (deferred, lazy, cached fit text); local live-fetch fallback
│       ├── cost.py              # GET /cost/summary, spend + cache-savings + prompt-cache % from the cost_events ledger
│       └── account.py           # DELETE /account, account self-deletion (require_user; ungated by cost_guard); uses cache.delete_user_data + lib/supabase_admin
└── frontend/src/
    ├── app/                     # layout (+ site footer: privacy/terms/account), globals.css, page.tsx (home), analyze/, results/[id]/, account/, privacy/, terms/
    ├── components/              # ProfileCard, ConnectionCard, InternshipCard, BucketSection, VerdictCard, BreakdownView, PreviousRuns
    ├── lib/                     # api.ts (runSkyMatch/parseResume/analyzeJob/analyzeBatch), constants.ts, storage.ts (localStorage run history)
    └── types/skymatch.ts      # Zod schemas + inferred TS types (source of truth)
```

---

## Cost-protection gate

The LLM-firing routers (`/run`, `/analyze*`, `/profile*`, `/internships*`, `/connections/*`) are
wired with `dependencies=[Depends(cost_guard)]` in `main.py` (`lib/guard.py`): per-IP **rate +
concurrency limits** (`429`) and a **spend-cap kill switch** (`503`, automatic on rolling spend ≥
`SPEND_CAP_USD_DAILY` OR the manual `app_flags.kill_switch`). `/cost/summary`, `/admin/*`, and
`/health` are **ungated** so observability + recovery stay reachable during a halt. State is
**Redis-backed (shared across replicas) when `REDIS_URL` is set, else in-process / per-replica** (the
rate-limiter + spend cache via `lib/redis_client.py`; the manual flag persists in Postgres
`app_flags`). **The kill-switch SUM (`cache.sum_spend_since`) counts USER-FACING spend ONLY, it
EXCLUDES `cost_events` rows tagged with a `worker:%` `cost_session`**, so background ingestion (the
worker's Haiku parse pass) can never trip the user-facing 503. The worker has its **own** soft budget
instead: `WORKER_SPEND_CAP_USD_DAILY` (over `WORKER_SPEND_CAP_WINDOW_SEC`, summed by
`cache.sum_worker_spend_since`), enforced inside `parse_pass()` (stops parsing, leaving rows for next
run). Knobs: `RATE_LIMIT_PER_MIN`/`_CONCURRENT`/`_WINDOW_SEC`/`_INFLIGHT_TTL_SEC`,
`SPEND_CAP_USD_DAILY`/`_WINDOW_SEC`, `SPEND_CACHE_TTL_SEC`,
`WORKER_SPEND_CAP_USD_DAILY`/`_WINDOW_SEC`, `REDIS_URL`/`REDIS_RETRY_COOLDOWN_SEC`, `ADMIN_TOKEN`.

(The gate is a per-router **dependency, not middleware**, full reasoning in [gotchas.md](gotchas.md).)

---

## Auth + per-user quota gate (`lib/auth.py`)

**OPTIONAL, off until `SUPABASE_URL` (or the legacy `SUPABASE_JWT_SECRET`) is set.** Supabase
magic-link auth verified **locally + statelessly** (`sub` = user id), NOT a per-request Supabase call.
`_decode` routes by the token's `alg`: **modern Supabase signs user-session tokens with asymmetric
ES256 keys** (keyed by `kid`) → verified against the project **JWKS**
(`{SUPABASE_URL}/auth/v1/.well-known/jwks.json`, fetched via `PyJWKClient`, cached); the legacy
**HS256** shared secret (`SUPABASE_JWT_SECRET`) is a **fallback** that only verifies the anon/service
API keys, NOT real user logins, so HS256-only config 401s every login on a modern project (the
"secret matches the anon key" check passes anyway, the classic trap). **The switch is
`SUPABASE_URL`** (enables JWKS; auth is on if EITHER it or the HS256 secret is set): unset both →
auth **disabled**, every dep returns `None`/no-ops, all routes stay anonymous (local dev + current
flow unchanged); set `SUPABASE_URL` → gating goes live with no code change. `requirements.txt` pins
`PyJWT[crypto]` (ES256 needs `cryptography`). This is why `require_user` returns `User | None` (None =
"auth off", not "anonymous through a required gate").

One **cached** dep does the work, `optional_user` (decode + `upsert_user`, 401 on a present-but-invalid
token); `require_user` depends on it (401 when auth on + anonymous); `quota(kind)`/`enforce_quota`
depend on it (increment the per-(user, UTC-day, kind) `usage_counters` row, **429** over cap; no-op
for anonymous, the spend cap is the backstop). **Two-rule gate, attached per-route in the
decorators** (not router-level): matcher *results-reveal* requires sign-in, `POST /analyze/batch`
(`require_user` + `quota("matcher")`) and `POST /internships/annotate` (`require_user`, NOT separately
quota'd, one page = many cards); standalone analyzer = *one free then gate*, `/analyze` (full) +
`/analyze/stream` charge `quota("analysis")` (the hard anonymous gate is frontend-side; spend cap
backstops). `/run`, `/run/stream`, `/profile/*`, `/internships/search` stay open. `cost_events`
gained a `user_id` column (threaded via `cost_session(name, user_id=…)`).

**Cloudflare Turnstile** (`lib/turnstile.py`, `verify_turnstile` dep on the expensive routes) is
likewise no-op until `TURNSTILE_SECRET` is set (then requires `X-Turnstile-Token`; siteverify network
errors **fail open**, a definitive reject → `403`). Knobs: `SUPABASE_URL` (JWKS switch),
`SUPABASE_JWKS_TIMEOUT_SEC` (10), `SUPABASE_JWT_SECRET` (HS256 fallback)/`_ALG`/`_AUD`,
`QUOTA_MATCHER_PER_DAY` (20), `QUOTA_ANALYSIS_PER_DAY` (5), `TURNSTILE_SECRET`/`TURNSTILE_TIMEOUT_SEC`.

---

## Environment variables (full inventory)

Copy `.env.example` to `.env` in `backend/` and fill in:
```
ANTHROPIC_API_KEY=...         # Claude API (required)
LINKDAPI_KEY=...              # LinkdAPI key (required for /run)
DATABASE_URL=...              # Postgres runtime conn (required). Prod: Supabase pgBouncer POOLER (6543). Local: docker-compose db
ALEMBIC_DATABASE_URL=...      # Postgres migrations conn (required). Prod: Supabase DIRECT (5432). Local: same as DATABASE_URL
DB_POOL_MIN=1                 # Connection-pool min (db.py); optional, default 1
DB_POOL_MAX=5                 # Connection-pool max; optional, default 5, budget Supabase backend cap across replicas+worker
USE_MOCKS=false               # Return hardcoded mock data, set true for dev without real calls
FIRECRAWL_API_KEY=...         # Firecrawl (JS-heavy /analyze URLs + internship liveness for wellfound/SPA listings)
FIRECRAWL_WAIT_MS=5000        # How long to wait for JS render (ms); default 5000
FIRECRAWL_TIMEOUT_MS=90000    # Total Firecrawl request budget (ms); default 90000, covers BOTH page fetch AND LLM extraction; keep >= 90000 or verbose pages time out
FIRECRAWL_PROXY_MODE=auto     # Firecrawl proxy tier: "auto" (default; escalates past Cloudflare/JS shells server-side) | "basic" | "enhanced". ("stealth" is the deprecated v1 alias, don't use it)
FIRECRAWL_MAX_CONCURRENCY=2   # Cap on simultaneous Firecrawl scrapes, sized to the plan's concurrent-browser limit (free/hobby = 2). Per-process gate in lib/firecrawl.py; prevents the worker over-subscribing Firecrawl (queue-wait → 408s + orphaned jobs). Default 2
VOYAGE_API_KEY=...            # Voyage embeddings, listing embeddings (worker parse pass) + profile embedding (internships rank). OPTIONAL: absent → ranking skipped, serving falls back
EMBED_MODEL=voyage-3.5        # Voyage model id (optional; changing it orphans stored vectors, see docs/caching.md)
LOGODEV_SECRET_KEY=sk_...     # logo.dev Brand Search (name → domain) in the worker logo resolve. OPTIONAL but set on the worker: absent → uncurated company names get a letter avatar, not a logo
LOGODEV_PUBLISHABLE_KEY=pk_...# logo.dev image URLs (img.logo.dev, monogram fallback); safe to embed. OPTIONAL: absent → resolved domains use Google favicon instead. See lib/logo_resolver
WORKER_PARSE_CONCURRENCY=8    # Max in-flight Haiku listing-parse calls in the worker parse pass (worker-only; optional)
```

> The worker parse pass uses `ANTHROPIC_API_KEY` (Haiku) + `VOYAGE_API_KEY` (embeddings); both are
> **optional**: the worker still ingests/validates/stores without them, just leaving rows unparsed
> for serving to fall back on.

Frontend env (optional, defaults to localhost:8000): `NEXT_PUBLIC_API_URL=http://localhost:8000`

Gate/auth knobs are listed in their sections above; deploy-time infra env lives in
[deploy.md](deploy.md).
