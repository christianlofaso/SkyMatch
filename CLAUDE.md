# Pathfinder — CLAUDE.md

Career discovery tool: paste a LinkedIn profile URL or raw text (+ optional resume) and get personalized internship listings across 4 buckets. Includes a standalone job-fit analyzer that scores a profile against any job posting URL or pasted description.

> **Connections feature is currently disabled in `/run`.** The warm LinkedIn *connection* recommendations used to be a parallel branch of `/run`, but are being reworked to live inside the job listings. `/run` now computes **internships only** (returns `connections: []`); the backend code (`connections.py`, the `POST /connections/suggest` route) and the frontend `ConnectionCard` + `ConnectionSchema` are **retained but dormant** — no longer wired into `/run` or rendered on the results page.

> **Ingestion is decoupled from serving.** Job listings are no longer scraped live per request. A standalone background worker — `backend/worker/ingest.py`, run as `python -m worker.ingest` on a cron / Task Scheduler cadence (~6h) — continuously pulls listings from DDG/ATS/Firecrawl into a local SQLite index (`listing_store` in `pathfinder_cache.db`), then **precomputes the profile-independent work once per listing** (a parse pass: Haiku structured/display fields + a Voyage embedding, both stored on the row). `/run` → `search_internships` serves from that index with **ZERO LLM on the request path**: a no-LLM **embedding rank** (profile embedded once → cosine-narrow each bucket) → a **deterministic select+build** (`_select_and_build`: company-diversity trim → cards assembled straight from the precomputed display fields, raw-column fallback for unparsed rows). The per-user `fit_explanation`/`reach_gap` ("why you fit") is **deferred AND lazy**: the feed ships it empty, cards render collapsed (click-to-expand accordions), and only on a card's **first expand** does the results page call `POST /internships/annotate` for that one role (slim fit-only `MODEL_MID` call, streamed). The result is cached **server-side** in `annotate_cache` (key `profile_hash:bucket:content_hash`, 30d → a repeat cross-device / same-profile view is served from SQLite with no LLM) **and** client-side in localStorage. (The score badge stays eager — batch-scored on load via `/analyze/batch`, also cached.)
> - **Three "national" buckets** (startup, big_tech, reach) are metro-independent and served to everyone, keyed under `niche_key="_national"` / `"_reach"`.
> - **`local`** is the only per-metro pool (keyed by parsed metro). Served from the index if the metro is in the rotation (`metro_rotation` table, **seeded with the ~30 `SEED_METROS`** covering where CS/ECE students intern; `_STATE_FALLBACK` routes every US state + college towns onto one of them, so nearly all students serve from the index). It's **live-fetched** at request time only when the metro isn't in rotation **OR its local index is empty/stale** (e.g. a freshly-seeded metro the worker hasn't ingested yet — so seeding never serves an empty bucket) (bounded ~35s): scrape + validate + upsert, then **run the SAME parse precompute the worker does — Haiku company/role_category + Voyage embedding — INLINE** (`lib/precompute.parse_and_embed_rows`, the only LLM on the request path, and only for an uncovered metro's first visit) so this request serves clean, field-filtered, ranked rows; the metro is then **promoted** into the rotation so the next user + next worker run get it from the index. No "unsupported metro" branch. _(A scraped-but-unparsed local row has no resolved company → "Unknown", no `role_category` → off-field roles leak, no embedding → no ranking; parsing inline closes all three at the source.)_
> - The profile-independent scrape/enrich/validate code now lives in `backend/lib/ingest_core.py` (shared by the worker; the request path uses it only for the local fallback). Config is in `backend/config/niches.py` (`NATIONAL_FIELDS`, `SEED_METROS`, `REACH_ATS_SLUGS`).
> - **The worker's parse pass (`parse_pass()` in `worker/ingest.py`) now makes cheap model calls** — Haiku (`MODEL_QUICK`) listing parse via `lib/listing_parser.py` + Voyage embeddings via `lib/embeddings.py` — but runs **after** store+prune, is **incremental** (only `parsed_at IS NULL` rows), and BOTH `ANTHROPIC_API_KEY`/`VOYAGE_API_KEY` are **optional**: missing either skips that work, the row stays unparsed, and serving uses its fallback path. The precompute lands in 6 new `listing_store` columns (`parsed_json`, `embedding`, `embedding_model`, `embedding_dim`, `content_hash`, `parsed_at`); `upsert_listing` NULLs `parsed_at` when the listing content changes so it re-parses.
>   - **Company resolution** (`_resolve_company` in `listing_parser.py`) is a fallback chain: Haiku's answer → stored `company` column → `company_from_url()` (ATS slug / `amazon.jobs`) → `"Unknown"`. Placeholder strings Haiku sometimes emits (`"unknown"`, `"N/A"`, … — see `is_placeholder_company`) are treated as *missing* at every step. For SPA boards where the company is only on the rendered page (wellfound/workatastartup), the parse pass additionally runs a bounded `company_from_firecrawl()` render to recover it.
>   - **Two follow-on passes** in the worker keep the precompute consistent without re-running Haiku: `embed_backfill_pass()` embeds rows that were parsed but never embedded (e.g. Voyage was down — `parsed_at` is set on parse success alone, so they'd otherwise never re-enter the parse queue); the `scratch/backfill_company*.py` tools re-resolve companies for already-parsed rows (URL-based + Firecrawl-based). `scratch/inspect_parse.py` reads back parsed/embedded counts.
> - The old live-scrape per-request path in `internships.py` (Claude fabrication via `INTERNSHIPS_SYSTEM`, the `_get_url`/`_find_*` URL-finders) has been **removed**, and so has the per-request Sonnet **SELECT** + inline **annotation** that briefly replaced it. `search_internships` now serves via **embedding rank (no LLM) → `_select_and_build` (no LLM)** — cards are assembled from the precomputed display fields (`parsed_json`), with a raw-column fallback for unparsed rows (warming index). For unparsed rows the company chain is **`parsed → title("@"/" - ")-derived → company_from_url (ATS slug) → column → "Unknown"`** (`_build_internship`/`_fit_fields`), so an ATS-board URL never shows "Unknown". The only `MODEL_MID` call left in this file is the **deferred, lazy** slim fit-only annotate, exposed as the streamed `POST /internships/annotate` (`_annotate_one` → `_annotate_fit_sync` → `{fit_explanation, reach_gap}`); it looks the row up by URL (`cache.get_listing_by_url`) and reads `parsed_json` or the raw columns via `_fit_fields`. It is **cached server-side**: `_annotate_one` serves a hit from `annotate_cache` (key `profile_hash:bucket:(content_hash|url)`, 30d) **without** Sonnet or `sonnet_sem`, and writes successful results back — so repeat (profile, role) reasoning is a free index read. The local live-fetch fallback keeps `_scrape_local_listings`/`_parse_metro`/`validate_job_url` **and now runs the worker's parse precompute inline** (`lib/precompute.parse_and_embed_rows`, Haiku — so an uncovered metro's first serve is clean/ranked/filtered, not raw). JSON-from-prose recovery now lives in `backend/lib/jsonparse.py` (shared by `internships.py` + `listing_parser.py`).

## How to work on this codebase

**Reach 95% confidence before writing any code.** Before editing or creating code, continuously ask clarifying questions until you are ~95% confident you understand exactly what is needed and what to do. Don't start writing on a vague or ambiguous request — surface the unknowns as questions first. (Read-only investigation to *inform* those questions is fine.)

**Finish each todo before moving on.** When working through a todo list, do not advance to the next item until you are ~95% confident the current one is actually good — verified, not just written. No leaving an item half-done to come back to later unless explicitly asked to stage work.

**Diagnose root cause before writing fixes.** Read the relevant code, trace the failure path, and identify *why* it breaks — not just *where*. A fix that addresses symptoms while leaving the root cause in place will break again.

**Never propose a workaround that requires manual user intervention if a code-side fix exists.** "Just paste it manually" or "restart the server and try again" are only acceptable answers when no programmatic solution is possible. If the failure mode can be handled in code, handle it in code.

**If the fix is genuinely ambiguous, present two options with trade-offs — don't silently pick the smaller one.** Format: Option A (brief label) / what it does / downside. Option B (brief label) / what it does / downside. Then state which you'd pick and why. Do not default to the conservative choice without saying so.

**Make the complete change.** If a fix requires updating a prompt, a schema, a route, and a frontend type — do all four in one pass. Don't ship a partial fix and leave TODOs for follow-up unless explicitly asked to stage work.

**Prefer explicit over implicit.** When adding guards, blocklists, or special-case logic, document the reason in a comment at the point of use — not just in a commit message or response. Future-you reading the code won't have this conversation for context.

---

## Detailed docs — open the relevant file before working in that area

This file is the always-loaded map. Deep reference lives in `docs/`; read the matching file when your task touches that area instead of guessing.

| File | Read it when you're… |
|------|----------------------|
| [docs/data-models.md](docs/data-models.md) | adding/changing a field, or need the exact shape of any Pydantic/Zod model (Profile, Analysis, Roadmap, Batch, etc.) |
| [docs/routes.md](docs/routes.md) | editing any backend route — `/run` orchestration + merge, the index-served internships pipeline + ingestion worker, `/analyze` full/quick pipeline + Phase 3, batch, connections, and the URL-validation DROP POLICY |
| [docs/caching.md](docs/caching.md) | touching cache keys, TTLs, or the Postgres tables (`db.py` pool + `alembic/` schema) — including the `listing_store` index + `metro_rotation` |
| [docs/frontend.md](docs/frontend.md) | working on pages, components, theme/CSS vars, sessionStorage flow, or type safety |
| [docs/logging.md](docs/logging.md) | reading logs or adding a log line — `[analyze]`/`[timing]`/`[cost]`/`[validate]` conventions |
| [docs/development.md](docs/development.md) | doing a recurring task — adding a profile field, site handler, bucket, model constant, tuning weights, adjusting Phase 3 / batch knobs |
| [docs/gotchas.md](docs/gotchas.md) | **anything non-trivial — read this first.** Async/blocking traps, Opus 4.8 quirks, `max_tokens` truncation, mojibake, Cloudflare-walled domains, cache subtleties |
| [docs/deploy.md](docs/deploy.md) | deploying / changing infra — Vercel + Railway (web ×2 + worker cron + Redis) + Supabase, env-var inventory, CI + staging→prod promote, Dockerfile/`railway.toml`, pre-launch checklist |

**Keep sources of truth in sync:** `backend/schemas.py` ⇄ `frontend/src/types/pathfinder.ts` for data shapes; `backend/config/models.py` for model IDs; `backend/config/niches.py` for ingestion fields/metros/reach pool; `frontend/src/lib/constants.ts` for verdict labels/colors. Also: the listing `role_category` vocabulary in `prompts/listing_parse.txt` ⇄ `lib/listing_parser.ROLE_CATEGORIES` ⇄ the off-field exclusion set `_OFF_FIELD_CATEGORIES` in `routes/internships.py` (applied to the **reach AND local** buckets via `_OFF_FIELD_BUCKETS`).

---

## Architecture

```
frontend (Next.js 14)
  ├── POST /run/stream           → profile → internships, phased-progress ndjson (home page)
  ├── POST /analyze/stream       → job-fit full pipeline, progressive ndjson (analyze page)
  ├── POST /analyze/batch        → ndjson stream of quick analyses across many jobs (results page)
  ├── POST /internships/annotate → lazy per-role "why you fit" ndjson (card expand)
  └── POST /profile/from-resume  → resume parse → UnifiedProfile

backend (FastAPI) — request path
  ├── /run                   → orchestrator (run.py) → search_internships (reads listing_store)
  ├── /run/stream            → streaming twin of /run: profile→internships phase envelopes (run.py)
  ├── /profile/analyze       → Claude extraction (profile.py)
  ├── /profile/from-resume   → file upload → text → UnifiedProfile (resume.py)
  ├── /connections/suggest   → LinkdAPI + Claude (connections.py — dormant)
  ├── /internships/search    → serve from listing_store, zero-LLM rank + build (internships.py)
  ├── /internships/annotate  → deferred per-role fit text (ndjson stream) — slim Sonnet (internships.py)
  ├── /analyze               → site_handler → fetch → extract → quick OR full path (analyze.py)
  ├── /analyze/stream        → streaming twin of /analyze full: verdict→roadmap→project ndjson (analyze.py)
  └── /analyze/batch         → bounded-concurrency quick analyses streamed back as ndjson

  (All four ndjson streamers — /run/stream, /analyze/stream, /analyze/batch, /internships/annotate —
   share one pattern: async-gen yielding `envelope.model_dump_json()+"\n"`, sessions opened INSIDE the
   generator, and `cost_guard` as a yield-dependency, NOT middleware, so it doesn't buffer the
   StreamingResponse. NOTE: /run/stream + /analyze/stream serialize WITHOUT exclude_none — their
   envelopes wrap full data models (RunResponse / AnalysisResponse pieces) whose nullable fields the
   Zod schemas require PRESENT, so exclude_none would drop them and break validation; the wrapper Zod
   schemas mark off-phase fields nullable+optional. (batch/annotate use exclude_none — their payload
   schemas are already nullish.) The JSON /run + /analyze stay intact as additive siblings.)

ingestion (standalone, NOT in the request path)
  └── worker/ingest.py       → DDG + ATS APIs + Firecrawl → listing_store
                               (national pool: startup/big_tech, per-metro local, reach pool)
```

**Backend stack:** Python 3.12, FastAPI, Anthropic SDK, httpx (async HTTP), LinkdAPI, DuckDuckGo (`ddgs`), Firecrawl (SPA scraping), pdfplumber + python-docx (resume parsing), Postgres (Supabase in prod) via `psycopg` v3 + `psycopg_pool` with Alembic migrations (caching + the `listing_store` index — see `db.py`/`cache.py`/`alembic/`), Pydantic v2, python-dotenv. **DDG/ATS/Firecrawl scraping is now ingestion-side** (`worker/ingest.py` → `lib/ingest_core.py`), not in the request path. Model IDs are centralized in `backend/config/models.py` (`MODEL_FULL = claude-opus-4-8`, `MODEL_MID = claude-sonnet-4-6`, `MODEL_QUICK = claude-haiku-4-5`). `analyze.py`, `profile.py`, and `internships.py` import from there — **`MODEL_MID` (Sonnet) runs the extraction/annotation-style calls** (profile + rich-field extraction in `profile.py`; in `internships.py`, **only** the deferred per-role **fit annotation** (`POST /internships/annotate`) — the request path / `search_internships` is now zero-LLM; in `analyze.py`, requirement **extraction** + evidence **matching**) where Opus latency isn't justified. In `analyze.py`, **`MODEL_FULL` (Opus) still runs Phase 3** (`_run_roadmap` + `_run_project_suggestion`) — the dominant `/analyze` cost (~80%; roadmap retries). `connections.py` still inlines its own `claude-opus-4-8` model string. **All routes share ONE Anthropic client from `lib/anthropic_client.py`** (raised `max_retries` for SDK 429 backoff) and gate every Sonnet call through the process-wide `sonnet_sem` rate-limit governor — see the gotcha below. The worker fires **no Sonnet/Opus calls**, but its **parse pass does make cheap Haiku + Voyage calls** (`worker/ingest.py` `parse_pass` → `lib/listing_parser.py` + `lib/embeddings.py`) — both keys optional; absent → rows stay unparsed and serving falls back. A `backend/site_handlers/` package handles vendor SPA career portals (Microsoft today, Workday/SuccessFactors/iCIMS in future).

**Frontend stack:** Next.js 14 App Router, React 18, TypeScript, Tailwind CSS, Zod (runtime validation).

---

## Running the project

### Database (Postgres)
The data layer is **Postgres** (Supabase in prod), not SQLite. Start a local DB and apply
migrations before running the backend or worker:
```
cd backend
docker compose up -d db        # local Postgres (postgres:16) on :5432 — or point DATABASE_URL at a Supabase project
venv\Scripts\activate
alembic upgrade head           # create the 16 tables + indexes + seed metro_rotation
```
Schema is owned by **Alembic** (`alembic/versions/`), NOT by app code — `init_db()` now only
warms the connection pool (`db.py`). `DATABASE_URL` = runtime (Supabase pgBouncer **pooler**,
6543, in prod); `ALEMBIC_DATABASE_URL` = migrations (Supabase **direct**, 5432). Locally both
can be the same local URL. New migration: `alembic revision -m "..."` then edit + `upgrade head`.

### Backend
```
cd backend
py -3.12 -m venv venv          # first time only
venv\Scripts\activate
pip install -r requirements.txt  # first time only
uvicorn main:app --reload --port 8000
```

### Ingestion worker (populates the listing index)
```
cd backend
venv\Scripts\activate
python -m worker.ingest        # one pass: national pool + per-rotation-metro local + reach pool
```
Run on a schedule (Windows Task Scheduler / cron, ~6h) so the index stays fresh — see the docstring in `worker/ingest.py`. It's a separate process from uvicorn; both connect to the same Postgres (`DATABASE_URL`) and Postgres MVCC handles concurrent read/write. `/run` serves whatever is currently in `listing_store`, so **run the worker at least once before the first `/run`** (an empty index → empty national buckets).

### Frontend
```
cd frontend
npm install    # first time only
npm run dev    # runs on http://localhost:3000
```

### Environment
Copy `.env.example` to `.env` in `backend/` and fill in:
```
ANTHROPIC_API_KEY=...         # Claude API (required)
LINKDAPI_KEY=...              # LinkdAPI key (required for /run)
DATABASE_URL=...              # Postgres runtime conn (required). Prod: Supabase pgBouncer POOLER (6543). Local: docker-compose db
ALEMBIC_DATABASE_URL=...      # Postgres migrations conn (required). Prod: Supabase DIRECT (5432). Local: same as DATABASE_URL
DB_POOL_MIN=1                 # Connection-pool min (db.py); optional, default 1
DB_POOL_MAX=5                 # Connection-pool max; optional, default 5 — budget Supabase backend cap across replicas+worker
USE_MOCKS=false               # Return hardcoded mock data — set true for dev without real calls
FIRECRAWL_API_KEY=...         # Firecrawl (JS-heavy /analyze URLs + internship liveness for wellfound/SPA listings)
FIRECRAWL_WAIT_MS=5000        # How long to wait for JS render (ms); default 5000
FIRECRAWL_TIMEOUT_MS=90000    # Total Firecrawl request budget (ms); default 90000 — covers BOTH page fetch AND LLM extraction; keep >= 90000 or verbose pages time out
FIRECRAWL_PROXY_MODE=basic    # Firecrawl proxy tier: "basic" (default) or "stealth"
VOYAGE_API_KEY=...            # Voyage embeddings — listing embeddings (worker parse pass) + profile embedding (internships rank). OPTIONAL: absent → ranking skipped, serving falls back
EMBED_MODEL=voyage-3.5        # Voyage model id (optional; changing it orphans stored vectors — see docs/caching.md)
WORKER_PARSE_CONCURRENCY=8    # Max in-flight Haiku listing-parse calls in the worker parse pass (worker-only; optional)
```

> The worker parse pass uses `ANTHROPIC_API_KEY` (Haiku) + `VOYAGE_API_KEY` (embeddings); both are **optional** — the worker still ingests/validates/stores without them, just leaving rows unparsed for serving to fall back on.

Frontend env (optional, defaults to localhost:8000): `NEXT_PUBLIC_API_URL=http://localhost:8000`

### Local dev pitfalls (recurring — read before running commands)
- **Working directory resets to project root between Bash/PowerShell calls.** Always `cd` into the correct directory (e.g. `backend/`) at the start of *every* command that depends on cwd, and append `sys.path` fixes for imports from `scratch/`. _(Background worker launches and imports have failed multiple times across sessions because cwd reset between calls.)_
- **Use Python 3.x (NOT 3.14 — it breaks dependency builds); this project pins 3.12.** Always ensure the `.env` file is loaded before running scripts that need auth (Firecrawl/Voyage/LinkdAPI keys). _(Python 3.14 caused build failures and an unloaded `.env` caused auth errors in setup sessions.)_

---

## Project structure

```
pathfinder/
├── CLAUDE.md
├── docs/                         # Deep reference — see the docs index above
├── backend/
│   ├── main.py                  # FastAPI app + CORS + router registration + init_db()
│   ├── schemas.py               # All Pydantic models (single source of truth for data shapes)
│   ├── linkd.py                 # Async LinkdAPI client
│   ├── db.py                    # Postgres connection pool + get_db()/init_db() (psycopg_pool; pgBouncer-safe)
│   ├── cache.py                 # Postgres data-access helpers — per-blob caches + listing_store (queryable index) + metro_rotation
│   ├── alembic/                 # Schema migrations (0001_initial_schema = the 16 tables + indexes); owns DDL (init_db no longer does)
│   ├── mocks/run_response.json  # Hardcoded response used when USE_MOCKS=true
│   ├── worker/
│   │   └── ingest.py               # Standalone ingestion worker (python -m worker.ingest) → listing_store; no Claude calls
│   ├── config/
│   │   ├── models.py               # MODEL_FULL / MODEL_MID / MODEL_QUICK constants — single source of truth
│   │   ├── niches.py               # NATIONAL_FIELDS, SEED_METROS, REACH_ATS_SLUGS, _national/_reach keys
│   │   └── resource_allowlist.py   # Trusted-domain frozenset + is_allowlisted() for roadmap resources
│   ├── lib/
│   │   ├── anthropic_client.py     # Shared Anthropic client (raised max_retries) + process-wide Sonnet concurrency cap (sonnet_sem) — imported by all routes
│   │   ├── embeddings.py           # Shared Voyage client (is_available/embed_documents/embed_query, normalized float32 + bytes round-trip) — worker parse pass + internships rank
│   │   ├── jsonparse.py            # Lenient JSON-from-prose recovery (strip_fences/extract_json_value/parse_json_with_context) — internships.py + listing_parser.py
│   │   ├── listing_parser.py       # Ingestion-time Haiku listing parse (structured/display fields) + build_embed_text/content_hash — used by worker parse pass
│   │   ├── ingest_core.py          # Profile-independent scrape/enrich/validate (DDG/ATS/Firecrawl) — shared by worker + local fallback
│   │   ├── firecrawl.py            # Shared Firecrawl client (is_available/scrape/JOB_SCHEMA) — used by analyze.py + ingest_core.py
│   │   ├── resource_validation.py  # Generic-URL reject + allowlist + async HEAD liveness for roadmap URLs (cached 7d)
│   │   ├── timing.py               # Request timing — timing_session/timed/timed_call → sorted [timing] breakdown
│   │   └── cost.py                 # Token/cost accounting — cost_session/record_usage/record_cache_hit → [cost] log + persisted to cost_events ledger (read by GET /cost/summary)
│   ├── site_handlers/           # Per-vendor SPA career-portal handlers (base.py + microsoft.py)
│   ├── prompts/                 # *.txt system prompts (extraction, matching, quick_verdict, roadmap, …)
│   └── routes/
│       ├── run.py               # POST /run — orchestrator (profile → internships; connections branch removed); also handles resume merge
│       ├── profile.py           # POST /profile/analyze — Claude extraction; extract_rich_fields
│       ├── resume.py            # POST /profile/from-resume — file upload + parse + cache
│       ├── analyze.py           # POST /analyze + /analyze/batch — full + quick pipelines, caches
│       ├── connections.py       # POST /connections/suggest — LinkdAPI + Claude (DORMANT: retained but no longer called by /run)
│       ├── internships.py       # POST /internships/search (zero-LLM serve) + /internships/annotate (deferred, lazy, cached fit text); local live-fetch fallback
│       └── cost.py              # GET /cost/summary — spend + cache-savings + prompt-cache % from the cost_events ledger
└── frontend/src/
    ├── app/                     # layout, globals.css, page.tsx (home), analyze/, results/[id]/
    ├── components/              # ProfileCard, ConnectionCard, InternshipCard, BucketSection, VerdictCard, BreakdownView, PreviousRuns
    ├── lib/                     # api.ts (runPathfinder/parseResume/analyzeJob/analyzeBatch), constants.ts, storage.ts (localStorage run history)
    └── types/pathfinder.ts      # Zod schemas + inferred TS types (source of truth)
```

---

## API endpoints

| Method | Path | Request | Response |
|--------|------|---------|----------|
| POST | `/run` | `RunRequest` (`url?`, `text?`, `profile_id?`) | `RunResponse` (`connections` is always `[]` — see note above) |
| POST | `/run/stream` | `RunRequest` | `application/x-ndjson` — phased-progress twin of `/run`: one `RunStreamEnvelope` per line (`profile`/`internships`/`done`/`error`). The `done` line carries the full `RunResponse`. The home page uses this for a 2-step progress indicator. Mid-stream failures arrive as an `error` envelope (same friendly message as `/run`; HTTP status is advisory) since a stream locks status at 200. The JSON `/run` is unchanged |
| POST | `/profile/analyze` | `RunRequest` | `ProfileAnalysis` |
| POST | `/profile/from-resume` | `multipart/form-data` file | `{profile_id, profile}` |
| POST | `/connections/suggest` | `ProfileAnalysis` | `list[Connection]` (10) — standalone route; **not called by `/run`** (dormant, being reworked) |
| POST | `/internships/search` | `ProfileAnalysis` | `InternshipBuckets` — served from `listing_store` (index), **zero-LLM** (rank + deterministic build); `fit_explanation` ships empty and is filled via `/internships/annotate`. Exception: an **uncovered metro's first visit** triggers the bounded local live-fetch, which scrapes + **parses inline** (Haiku) before serving |
| POST | `/internships/annotate` | `AnnotateRequest` (`profile`, `jobs: [{url, bucket}]`) | `application/x-ndjson` — one `AnnotateEnvelope` per line (`fit_explanation`/`reach_gap`), completion order; **lazy** "why you fit" (fired per role on card expand, not for the whole feed) — results cached in `annotate_cache` (per-(profile,role), 30d) |
| POST | `/analyze` | `AnalyzeRequest` (`mode` defaults `"full"`; `include.{roadmap,project}` default `true` for full) | `AnalysisResponse` (full, incl. Phase 3) or `QuickAnalysisResponse` (quick) |
| POST | `/analyze/stream` | `AnalyzeRequest` (full mode) | `application/x-ndjson` — true-streaming twin of `/analyze` full: one `AnalyzeStreamEnvelope` per line (`verdict` → `roadmap`/`project` in completion order → `done`). The analyze page renders progressively in-place. The **prelude** (resolve/extract/match/score) runs BEFORE the stream, so a bad page / no-requirements still raises a proper **422/500**; only the (failure-free) Phase 3 streams. Two `[cost]` ledgers print (prelude + phase3). The JSON `/analyze` is unchanged |
| POST | `/analyze/batch` | `BatchAnalyzeRequest` (max 50 jobs) | `application/x-ndjson` — one `BatchEnvelope` per line, completion order |
| GET | `/cost/summary` | `?days=N` (default 7) | spend + estimated cache savings + per-model/session breakdown + prompt-cache % from the `cost_events` ledger |
| POST | `/admin/killswitch` | `{on: bool}` + `X-Admin-Token` header | toggles the manual kill switch (`app_flags.kill_switch`); halts all gated routes with `503` while on. `403` if `ADMIN_TOKEN` unset/mismatched |
| GET | `/admin/status` | `X-Admin-Token` header | current kill-switch state, rolling-window spend vs cap, and rate-limit config (`lib/guard.status_snapshot`) |
| GET | `/health` | — | `{"status": "ok"}` |

> **Cost-protection gate.** The LLM-firing routers (`/run`, `/analyze*`, `/profile*`, `/internships*`, `/connections/*`) are wired with `dependencies=[Depends(cost_guard)]` in `main.py` (`lib/guard.py`): per-IP **rate + concurrency limits** (`429`) and a **spend-cap kill switch** (`503`, automatic on rolling spend ≥ `SPEND_CAP_USD_DAILY` OR the manual `app_flags.kill_switch`). `/cost/summary`, `/admin/*`, and `/health` are **ungated** so observability + recovery stay reachable during a halt. State is **Redis-backed (shared across replicas) when `REDIS_URL` is set, else in-process / per-replica** (the rate-limiter + spend cache via `lib/redis_client.py`; the manual flag persists in Postgres `app_flags`). Knobs: `RATE_LIMIT_PER_MIN`/`_CONCURRENT`/`_WINDOW_SEC`/`_INFLIGHT_TTL_SEC`, `SPEND_CAP_USD_DAILY`/`_WINDOW_SEC`, `SPEND_CACHE_TTL_SEC`, `REDIS_URL`/`REDIS_RETRY_COOLDOWN_SEC`, `ADMIN_TOKEN`.

> **Auth + per-user quota gate (`lib/auth.py`) — OPTIONAL, off until `SUPABASE_URL` (or the legacy `SUPABASE_JWT_SECRET`) is set.** Supabase magic-link auth verified **locally + statelessly** (`sub` = user id), NOT a per-request Supabase call. `_decode` routes by the token's `alg`: **modern Supabase signs user-session tokens with asymmetric ES256 keys** (keyed by `kid`) → verified against the project **JWKS** (`{SUPABASE_URL}/auth/v1/.well-known/jwks.json`, fetched via `PyJWKClient`, cached); the legacy **HS256** shared secret (`SUPABASE_JWT_SECRET`) is a **fallback** that only verifies the anon/service API keys, NOT real user logins — so HS256-only config 401s every login on a modern project (the "secret matches the anon key" check passes anyway, the classic trap). **The switch is now `SUPABASE_URL`** (enables JWKS; auth is on if EITHER it or the HS256 secret is set): unset both → auth **disabled**, every dep returns `None`/no-ops, all routes stay anonymous (local dev + current flow unchanged); set `SUPABASE_URL` → gating goes live with no code change. `requirements.txt` pins `PyJWT[crypto]` (ES256 needs `cryptography`). This is why `require_user` returns `User | None` (None = "auth off", not "anonymous through a required gate"). One **cached** dep does the work — `optional_user` (decode + `upsert_user`, 401 on a present-but-invalid token); `require_user` depends on it (401 when auth on + anonymous); `quota(kind)`/`enforce_quota` depend on it (increment the per-(user, UTC-day, kind) `usage_counters` row, **429** over cap; no-op for anonymous — the spend cap is the backstop). **Two-rule gate, attached per-route in the decorators** (not router-level): matcher *results-reveal* requires sign-in — `POST /analyze/batch` (`require_user` + `quota("matcher")`) and `POST /internships/annotate` (`require_user`, NOT separately quota'd — one page = many cards); standalone analyzer = *one free then gate* — `/analyze` (full) + `/analyze/stream` charge `quota("analysis")` (the hard anonymous gate is frontend-side; spend cap backstops). `/run`, `/run/stream`, `/profile/*`, `/internships/search` stay open. `cost_events` gained a `user_id` column (threaded via `cost_session(name, user_id=…)`). **Cloudflare Turnstile** (`lib/turnstile.py`, `verify_turnstile` dep on the expensive routes) is likewise no-op until `TURNSTILE_SECRET` is set (then requires `X-Turnstile-Token`; siteverify network errors **fail open**, a definitive reject → `403`). Knobs: `SUPABASE_URL` (JWKS switch), `SUPABASE_JWKS_TIMEOUT_SEC` (10), `SUPABASE_JWT_SECRET` (HS256 fallback)/`_ALG`/`_AUD`, `QUOTA_MATCHER_PER_DAY` (20), `QUOTA_ANALYSIS_PER_DAY` (5), `TURNSTILE_SECRET`/`TURNSTILE_TIMEOUT_SEC`.

---

## Critical gotchas (full list in [docs/gotchas.md](docs/gotchas.md) — read it before non-trivial work)

- **`ai.messages.create` is synchronous** — always wrap in `asyncio.to_thread()` when alongside other async work, or it blocks the whole event loop (freezes parallel `asyncio.gather` branches).
- **The Anthropic client + Sonnet rate-limit governor are centralized in `lib/anthropic_client.py`** — every route imports `client as ai` (not its own `anthropic.Anthropic()`), so the raised `max_retries` (SDK exponential backoff w/ jitter honoring `Retry-After`) applies everywhere. **Sonnet (`MODEL_MID`) is the only model that maxes the org's per-minute limits**, so `sonnet_slot()` caps in-flight Sonnet calls to `SONNET_MAX_CONCURRENCY` (default 6) **globally**: wrap **every** Sonnet `messages.create` in `async with sonnet_slot():` in the async layer (around the `to_thread`/`run_in_executor` dispatch — never inside the sync fn) — it's a **factory returning a fresh per-acquire async CM**, NOT a shared semaphore object (the old `sonnet_sem`), so don't store acquire state on one shared singleton. When `REDIS_URL` is set the slot is a **self-healing Redis ZSET semaphore** (held slots TTL-stamped → a crashed replica's slots auto-reclaim; `SONNET_SLOT_TTL_SEC` ≥ `ANTHROPIC_TIMEOUT_SEC`), so the cap is **org-wide across all replicas**; without Redis it degrades to a per-process `asyncio.Semaphore`. **Haiku (batch/results) and Opus (roadmap) stay ungated** (they have headroom). Env knobs: `SONNET_MAX_CONCURRENCY`, `SONNET_SLOT_TTL_SEC`/`_POLL_SEC`/`_MAX_WAIT_SEC`, `ANTHROPIC_MAX_RETRIES`, `REDIS_URL`. **Caveat: without `REDIS_URL` the cap is per-process** — under N replicas the effective global cap becomes N×.
- **DDGS is synchronous, not thread-safe, and can hang for minutes** when rate-limited — each thread instantiates its own `DDGS()`, bounded by `asyncio.wait_for`. It now runs **only in the worker** (`lib/ingest_core.py`); the request path hits it solely via the bounded local live-fetch fallback (`_live_local_fetch`, ~35s budget).
- **`listing_store` keying is `PRIMARY KEY (niche_key, bucket, url)`** — the same URL legitimately lives in multiple contexts (a Stripe listing is big_tech for every field AND in `_reach`). Local rows are keyed by the **`_parse_metro` output** — the worker, serving, and `metro_rotation` must ALL key on parsed metros, never a raw profile location, or covered-metro lookups silently miss.
- **The worker forces UTF-8 stdout** (`sys.stdout.reconfigure`) — as a standalone process with redirected output, Windows defaults to cp1252 and a stray `→`/non-ASCII char in a log line crashes the whole run. Keep that guard.
- **The data layer is Postgres** (`db.py` → `psycopg_pool.ConnectionPool`), shared by uvicorn and the worker; Postgres MVCC handles concurrent read/write (no WAL/sidecar files). **Prod uses the Supabase pgBouncer pooler in transaction mode, so the pool sets `prepare_threshold=None`** (server-side prepared statements break under transaction pooling) — keep that. `cache.py` stays **synchronous**; async routes call it through `asyncio.to_thread` (same discipline as the synchronous Anthropic SDK) so a DB round-trip never blocks the event loop. Schema lives in `alembic/`, not `init_db()`.
- **Opus 4.8 rejects `temperature`/`top_p`/`top_k`** (400). No sampling params on `MODEL_FULL` calls; Haiku quick-verdict keeps `temperature`.
- **`MODEL_MID` (Sonnet) sometimes wraps JSON answers in reasoning prose** (`"Looking at the listings:…"` then the array), despite "respond with ONLY JSON" — which breaks a plain `json.loads`. `internships.py`'s shared `_parse_json_with_context` falls back to `_extract_json_value` (scans for the first `[`/`{` that `raw_decode`s) to recover it; reuse that path for any new Sonnet JSON call rather than `json.loads` directly.
- **`max_tokens` truncation surfaces as a "retry" badge** — Opus 4.8 runs long; extraction is 2048, roadmap 4096, evidence 2048. Internships serving is zero-LLM; the only Internships call is the deferred fit annotation (`/internships/annotate`) at a small 160-token cap (~2-sentence `fit_explanation` +reach_gap) — see [docs/routes.md](docs/routes.md).
- **The quick-verdict prompt (`prompts/quick_verdict.txt`) is no longer a bare rubric** — it carries an **eligibility-gates rule** (date-independent gates like exact major → hard `skip`; time-relative gates like "completed junior year" → only gate on an *explicit* year in the posting, never guess from the current date) + **4 calibration anchors** (same candidate, four jobs: 78/74/60/50). Scoring-behavior tuning for quick/batch lives here. It's now ~1900 tokens (was ~280); the larger stable prefix also helps batch profile-caching clear Haiku's 4096-token cache minimum.
- **`[cost]` logging mirrors `[timing]`** — `cost_session`/`record_usage` (`lib/cost.py`) wrap `/analyze` + `/analyze/batch` + `/internships/annotate` **and `/run` + `/profile/analyze` + `/profile/from-resume` + `/connections/suggest`** (the profile-extraction Sonnet + connections Opus calls were previously untracked — `profile.py`/`connections.py` now call `record_usage`, so the ledger is complete) and print est-USD per Claude call + a sorted breakdown. Token counts are exact; **USD is approximate** (price table in `cost.py` — update it if pricing changes). Watch `cache_r` to confirm batch profile-caching is engaging. Every call now also **persists to the `cost_events` SQLite ledger**, and `record_cache_hit(label, model)` logs a full-call cache avoidance (annotate + batch-quick hits, est-USD saved from `_HIT_ESTIMATE`) — both surfaced via `GET /cost/summary`. _(Adding a new cache-hit type? add its label to `_HIT_ESTIMATE` or savings show as $0.)_
- **Reliability hardening (Day 4):** bad input maps to friendly statuses, not raw 500s — `analyze_profile` (`profile.py`) translates LinkdAPI `httpx.HTTPStatusError`/`RequestError` (404/private→422, 429→503, 5xx→502, timeout→504) and guards short pastes; **a global `@app.exception_handler(Exception)` in `main.py`** is the backstop (logs `[error]` + traceback, returns a clean 500, has a `# SENTRY:` hook — Sentry deferred). **Critical: routes wrapping extraction must `except HTTPException: raise` before the generic `except`** or the friendly errors regress to 500s (see gotchas). Timeouts/retries added: Anthropic request `timeout` (`ANTHROPIC_TIMEOUT_SEC`), LinkdAPI transient retries (`linkd.py`), per-query DDG `wait_for` in the worker (`ingest_core.py`), one Firecrawl network retry. `_select_and_build` isolates each card build (one malformed `listing_store` row can't break a bucket). Serve freshness tightened to `SERVE_MAX_AGE_HOURS` (48h) with an empty-national-bucket fallback to `SERVE_MAX_AGE_FALLBACK_HOURS` (96h) — depends on the worker's cron cadence.
- **Cost-protection gate (`lib/guard.py`) is a per-router dependency, NOT middleware** — `cost_guard` is attached via `dependencies=[Depends(cost_guard)]` on the LLM-firing routers in `main.py` (deliberately a `yield`-dependency, not `BaseHTTPMiddleware`, which would buffer/break the ndjson `StreamingResponse` of `/analyze/batch` + `/internships/annotate`; dependency teardown runs after the stream, so the per-IP concurrent counter releases correctly). It enforces per-IP rate + concurrency caps (`429`) and a kill switch (`503`: auto when rolling spend ≥ `SPEND_CAP_USD_DAILY`, or the manual persistent `app_flags.kill_switch` toggled via `POST /admin/killswitch`). **State is Redis-backed (shared across replicas) when `REDIS_URL` is set, else in-process / per-replica.** The per-IP limiter is an atomic Lua reserve over two ZSETs (sliding-window rate + crash-TTL'd concurrency, `RATE_LIMIT_INFLIGHT_TTL_SEC`); the rolling spend total is a shared Redis cache key with an in-process throttle on the Postgres `SUM`. The manual kill-switch flag stays in **Postgres `app_flags`** (must survive restart + toggle instantly). All three paths **fall back to the original in-process implementation** when Redis is absent/unhealthy — local dev needs no Redis, and a Redis outage degrades to per-replica limiting (looser, never tighter), not a 503. `lib/redis_client.py` is the shared async client + a **circuit breaker** (`REDIS_RETRY_COOLDOWN_SEC`) so a dead Redis trips fast instead of timing out every request. `/cost/summary`, `/admin/*`, `/health` are ungated on purpose. Both spend-cap and flag reads **fail open** (a DB/Redis hiccup must not 503 all traffic).
- **The results page dedupes internships by `application_url` before batch scoring** (`frontend/src/app/results/[id]/page.tsx`) — the same listing can sit in multiple buckets (big_tech AND reach), so each URL is scored **once** and the verdict fanned out to every slot that shares it. Scoring is per `(profile, job)` and bucket-independent.
- **The annotation ("why you fit") is lazy, the score badge is eager** — `InternshipCard` is a click-to-expand accordion; expanding a card fires a **single-role** `/internships/annotate` call on first open (not on page load), guarded by `annotateRequestedRef` so it never refetches, and fanned to every slot sharing the URL. It caches client-side (localStorage) and server-side (`annotate_cache`). Score badges still batch-score on load. See [docs/frontend.md](docs/frontend.md).
- **Mojibake (`â€"`) repair** lives in `analyze.py` (`_fix_mojibake`); stale cached rows are repaired on read, but the browser's durable `localStorage` `pf:analyses:{runId}` (see `frontend/src/lib/storage.ts`) must be cleared to pick up the fix.
- **Run history is durable `localStorage`, not `sessionStorage`** — all run/analysis persistence is centralized in `frontend/src/lib/storage.ts` (`pf:`-namespaced keys, last 10 runs, per-browser only). The home page shows a "Previous runs" list. See [docs/frontend.md](docs/frontend.md).
- **Voyage embeddings (`lib/embeddings.py`) are optional + have operational quirks.** (1) **Anthropic has no embeddings API** — embeddings are Voyage (`VOYAGE_API_KEY`); the wrapper is import-guarded so a missing `voyageai` package / key never crashes a route (`is_available()` → False → serving skips cosine ranking, worker stores parses without vectors). (2) **Free tier needs a payment method** — without one Voyage caps at **3 RPM / 10K TPM**, which is too small for even one 128-doc batch (it 408/429s the whole `embed_documents` call); adding a card unlocks real limits and the 200M voyage-3 free tokens still apply, so it stays effectively free. (3) **Vectors are normalized at store + query time** so serve-time cosine == dot product; **changing `EMBED_MODEL` orphans existing vectors** (serving only cosine-matches the same `embedding_model`+`embedding_dim`; mismatches fall to unranked) and `content_hash` does NOT fire on a model swap — reset with `UPDATE listing_store SET parsed_at=NULL`.
- **CORS is localhost-only** (`main.py`) — update `allow_origins` before deploying.
- **When fixing URL/listing validation for internship buckets, verify against the ACTUAL page title and real listings — not DDG search titles or minified SPA JS — and confirm the fix returns >0 live roles before declaring done.** _(Multiple bucket/category fixes — startup, local, big_tech, reach, category landing page — repeatedly returned 0 results because validation matched the wrong source; one over-aggressive `CLOSED_STRINGS` match against minified SPA JS deleted every startup role and forced a revert.)_
- **After modifying caching logic, confirm quick and full modes share consistent cache keys and that the backend was actually restarted before testing.** _(A score-mismatch fix failed repeatedly because quick and full modes used divergent cache keys, compounded by confusion over whether the backend had restarted.)_
