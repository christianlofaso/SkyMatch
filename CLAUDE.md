# SkyMatch (CLAUDE.md)

Career discovery tool: paste a LinkedIn profile URL or raw text (+ optional resume) and get
personalized internship listings across 4 buckets. Includes a standalone job-fit analyzer that
scores a profile against any job posting URL or pasted description.

This file is the always-loaded **map**. Deep reference lives in `docs/`, open the matching file
before working in that area instead of guessing.

## Current state (detail in [docs/architecture.md](docs/architecture.md))

- **Connections are dormant in `/run`.** It computes **internships only** (`connections: []`).
  `connections.py` + `ConnectionCard` are retained but no longer wired in.
- **Ingestion is decoupled from serving.** A standalone worker (`worker/ingest.py`, cron ~6h) scrapes
  + precomputes (Haiku parse + Voyage embedding) into the `listing_store` index. `/run` →
  `search_internships` serves from that index with **ZERO LLM on the request path** (embedding rank →
  deterministic `_select_and_build`). The per-role "why you fit" is **deferred + lazy**, filled on
  card expand via `POST /internships/annotate` (slim Sonnet, cached server + client side). The score
  badge stays eager (batch-scored on load). Three "national" buckets (startup/big_tech/reach) are
  served to everyone; **`local`** is the only per-metro pool (live-fetched + parsed inline on an
  uncovered metro's first visit, then promoted into `metro_rotation`).

## How to work on this codebase

**Reach 95% confidence before writing any code.** Ask clarifying questions until you understand
exactly what's needed. Don't start on a vague request, surface unknowns first. (Read-only
investigation to *inform* those questions is fine.)

**Finish each todo before moving on.** Don't advance until ~95% confident the current item is
verified, not just written. No half-done items unless explicitly asked to stage work.

**Diagnose root cause before writing fixes.** Trace the failure path and identify *why* it breaks, not
just *where*. A symptom fix leaving the root cause in place will break again.

**Never propose a manual workaround if a code-side fix exists.** "Paste it manually" / "restart and
retry" are only acceptable when no programmatic solution is possible.

**If the fix is genuinely ambiguous, present two options with trade-offs**: Option A / what / downside,
Option B / what / downside, then state which you'd pick and why. Don't silently pick the conservative one.

**Make the complete change.** If a fix touches a prompt, schema, route, and frontend type, do all
four in one pass. No partial fixes with TODOs unless asked to stage work.

**Prefer explicit over implicit.** Document the reason for guards/blocklists/special-cases in a comment
at the point of use, not just in a commit message.

---

## Detailed docs, open the relevant file before working in that area

| File | Read it when you're… |
|------|----------------------|
| [docs/architecture.md](docs/architecture.md) | needing the deep design, current-state notes, backend stack, project-structure tree, cost/auth gate internals, full env-var inventory |
| [docs/data-models.md](docs/data-models.md) | adding/changing a field, or need the exact shape of any Pydantic/Zod model (Profile, Analysis, Roadmap, Batch, etc.) |
| [docs/routes.md](docs/routes.md) | editing any backend route, `/run` orchestration + merge, the index-served internships pipeline + ingestion worker, `/analyze` full/quick + Phase 3, batch, connections, the URL-validation DROP POLICY |
| [docs/caching.md](docs/caching.md) | touching cache keys, TTLs, or the Postgres tables (`db.py` pool + `alembic/` schema), including the `listing_store` index + `metro_rotation` |
| [docs/frontend.md](docs/frontend.md) | working on pages, components, theme/CSS vars, sessionStorage flow, or type safety |
| [docs/logging.md](docs/logging.md) | reading logs or adding a log line, `[analyze]`/`[timing]`/`[cost]`/`[validate]` conventions |
| [docs/development.md](docs/development.md) | doing a recurring task, adding a profile field, site handler, bucket, model constant, tuning weights, adjusting Phase 3 / batch knobs |
| [docs/gotchas.md](docs/gotchas.md) | **anything non-trivial, read this first.** Async/blocking traps, Opus 4.8 quirks, `max_tokens` truncation, mojibake, Cloudflare-walled domains, cache subtleties |
| [docs/deploy.md](docs/deploy.md) | deploying / changing infra, Vercel + Railway (web ×2 + worker cron + Redis) + Supabase, env-var inventory, CI + staging→prod promote, Dockerfile/`railway.toml`, pre-launch checklist |

**Keep sources of truth in sync:** `backend/schemas.py` ⇄ `frontend/src/types/skymatch.ts` for
data shapes; `backend/config/models.py` for model IDs; `backend/config/niches.py` for ingestion
fields/metros/reach pool; `frontend/src/lib/constants.ts` for verdict labels/colors. Also: the
listing `role_category` vocabulary in `prompts/listing_parse.txt` ⇄ `lib/listing_parser.ROLE_CATEGORIES`
⇄ the off-field exclusion set `_OFF_FIELD_CATEGORIES` in `routes/internships.py` (applied to the
**reach AND local** buckets via `_OFF_FIELD_BUCKETS`).

---

## Architecture (full rundown + project tree in [docs/architecture.md](docs/architecture.md))

```
frontend (Next.js 14)
  ├── POST /run/stream           → profile → internships, phased-progress ndjson (home page)
  ├── POST /analyze/stream       → job-fit full pipeline, progressive ndjson (analyze page)
  ├── POST /analyze/batch        → ndjson stream of quick analyses across many jobs (results page)
  ├── POST /internships/annotate → lazy per-role "why you fit" ndjson (card expand)
  └── POST /profile/from-resume  → resume parse → UnifiedProfile

backend (FastAPI), request path
  ├── /run[/stream]          → orchestrator (run.py) → search_internships (reads listing_store)
  ├── /profile/analyze       → Claude extraction (profile.py)
  ├── /profile/from-resume   → file upload → text → UnifiedProfile (resume.py)
  ├── /connections/suggest   → LinkdAPI + Claude (connections.py, dormant)
  ├── /internships/search    → serve from listing_store, zero-LLM rank + build (internships.py)
  ├── /internships/annotate  → deferred per-role fit text (ndjson stream), slim Sonnet
  ├── /analyze[/stream]      → site_handler → fetch → extract → quick OR full path (analyze.py)
  └── /analyze/batch         → bounded-concurrency quick analyses streamed back as ndjson

ingestion (standalone, NOT in the request path)
  └── worker/ingest.py       → DDG + ATS APIs + Firecrawl → listing_store
                               (national pool: startup/big_tech, per-metro local, reach pool)
```

**Backend:** Python 3.12, FastAPI, Anthropic SDK, httpx, LinkdAPI, DDG (`ddgs`), Firecrawl,
pdfplumber + python-docx, Postgres (Supabase) via `psycopg` v3 + `psycopg_pool` + Alembic, Pydantic
v2. Model IDs centralized in `config/models.py` (`MODEL_FULL=claude-opus-4-8`,
`MODEL_MID=claude-sonnet-4-6`, `MODEL_QUICK=claude-haiku-4-5`); all routes share one client from
`lib/anthropic_client.py` and gate Sonnet calls through `sonnet_slot()`. **Frontend:** Next.js 14 App
Router, React 18, TypeScript, Tailwind, Zod.

---

## Running the project

Full env-var inventory is in [docs/architecture.md](docs/architecture.md); copy `.env.example` →
`backend/.env` first. **Run the worker at least once before the first `/run`** (an empty index → empty
national buckets).

```
# Database (Postgres), schema owned by Alembic, NOT init_db()
cd backend
docker compose up -d db        # local Postgres (postgres:16) on :5432, or point DATABASE_URL at Supabase
venv\Scripts\activate
alembic upgrade head           # create tables + indexes + seed metro_rotation

# Backend (first time: py -3.12 -m venv venv && pip install -r requirements.txt)
uvicorn main:app --reload --port 8000

# Ingestion worker, populates listing_store; run on a ~6h schedule
python -m worker.ingest

# Frontend (first time: npm install)
cd frontend && npm run dev     # http://localhost:3000
```

`DATABASE_URL` = runtime (Supabase pgBouncer **pooler**, 6543 in prod); `ALEMBIC_DATABASE_URL` =
migrations (Supabase **direct**, 5432). Locally both can be the same URL.

### Local dev pitfalls (recurring, read before running commands)
- **Working directory resets to project root between Bash/PowerShell calls.** Always `cd` into the
  right dir (e.g. `backend/`) at the start of *every* cwd-dependent command, and append `sys.path`
  fixes for imports from `scratch/`.
- **Use Python 3.12 (NOT 3.14, it breaks dependency builds).** Ensure `.env` is loaded before
  running scripts that need auth (Firecrawl/Voyage/LinkdAPI keys).

---

## API endpoints (full request/response shapes + gate prose in [docs/routes.md](docs/routes.md))

| Method | Path | Notes |
|--------|------|-------|
| POST | `/run` | `RunRequest` → `RunResponse` (`connections` always `[]`) |
| POST | `/run/stream` | ndjson twin of `/run`, `RunStreamEnvelope` per line; `done` carries full `RunResponse` |
| POST | `/profile/analyze` | `RunRequest` → `ProfileAnalysis` |
| POST | `/profile/from-resume` | `multipart/form-data` → `{profile_id, profile}` |
| POST | `/connections/suggest` | `ProfileAnalysis` → `list[Connection]`, standalone, **not** called by `/run` (dormant) |
| POST | `/internships/search` | `ProfileAnalysis` → `InternshipBuckets`, served from index, **zero-LLM** (uncovered metro's first visit live-fetches + parses inline) |
| POST | `/internships/annotate` | `AnnotateRequest` → ndjson `AnnotateEnvelope`; **lazy** per-role "why you fit", cached in `annotate_cache` (30d) |
| POST | `/analyze` | `AnalyzeRequest` (`mode` defaults `full`) → `AnalysisResponse` or `QuickAnalysisResponse` |
| POST | `/analyze/stream` | ndjson true-streaming twin of full `/analyze` (prelude runs before stream → real 422/500; only Phase 3 streams) |
| POST | `/analyze/batch` | `BatchAnalyzeRequest` (max 50) → ndjson `BatchEnvelope`, completion order |
| GET | `/cost/summary` | `?days=N` → spend + cache savings + per-model/session breakdown |
| POST | `/admin/killswitch` | `{on}` + `X-Admin-Token` → toggle `app_flags.kill_switch` (503 while on) |
| GET | `/admin/status` | `X-Admin-Token` → kill-switch state + spend vs cap + rate-limit config |
| DELETE | `/account` | bearer token → delete signed-in user; **ungated** by `cost_guard` |
| GET | `/health` | `{"status": "ok"}` |

**Gates** (both detailed in [docs/architecture.md](docs/architecture.md)): a **cost-protection gate**
(`lib/guard.py`, per-router `Depends(cost_guard)`, per-IP rate/concurrency 429 + spend-cap kill switch
503; worker spend excluded) and an **optional auth + per-user quota gate** (`lib/auth.py`, off until
`SUPABASE_URL` is set; Supabase JWKS/ES256 verified locally). `/cost/summary`, `/admin/*`, `/health`
stay ungated.

---

## Critical gotchas (one-liners, full detail in [docs/gotchas.md](docs/gotchas.md), read it first)

- **`ai.messages.create` is synchronous**: wrap in `asyncio.to_thread()` alongside other async work, or it freezes the event loop.
- **Sonnet (`MODEL_MID`) is governed**: wrap every Sonnet `messages.create` in `async with sonnet_slot():` (factory, not a shared semaphore); Haiku/Opus stay ungated.
- **DDGS is synchronous, not thread-safe, can hang for minutes**: worker-only now; request path hits it solely via the bounded local live-fetch (~35s).
- **`listing_store` PK is `(niche_key, bucket, url)`**: same URL lives in many contexts; local rows key on `_parse_metro` output, never a raw profile location.
- **The worker forces UTF-8 stdout** (`sys.stdout.reconfigure`): Windows defaults to cp1252 and a stray non-ASCII char crashes the run. Keep the guard.
- **Data layer is Postgres**: pool sets `prepare_threshold=None` (pgBouncer txn pooling); `cache.py` is synchronous, call via `asyncio.to_thread`; schema lives in `alembic/`, not `init_db()`.
- **Opus 4.8 rejects `temperature`/`top_p`/`top_k`** (400): no sampling params on `MODEL_FULL`; Haiku quick-verdict keeps `temperature`.
- **`MODEL_MID` (Sonnet) sometimes wraps JSON in prose**: use `_parse_json_with_context` / `lib/jsonparse`, never a plain `json.loads`.
- **`max_tokens` truncation surfaces as a "retry" badge**: extraction 2048, roadmap 4096, evidence 2048; annotate is a 160-token cap.
- **Cost/auth gates are per-router dependencies, NOT middleware**: a `yield`-dependency so they don't buffer the ndjson `StreamingResponse`.
- **The results page dedupes internships by `application_url` before batch scoring**, each URL scored once, verdict fanned to every slot sharing it.
- **Annotation ("why you fit") is lazy, the score badge is eager**: `InternshipCard` fires a single-role annotate on first expand (`annotateRequestedRef` guard); badges batch-score on load.
- **Voyage embeddings are optional**: missing key → ranking skipped; free tier needs a payment method; changing `EMBED_MODEL` orphans vectors (reset with `parsed_at=NULL`).
- **Run history is durable `localStorage`** (`frontend/src/lib/storage.ts`, `pf:`-namespaced, last 10 runs), clear `pf:analyses:{runId}` to pick up mojibake/cache-format fixes.
- **CORS is localhost-only** (`main.py`): update `allow_origins` before deploying.
- **Verify bucket/URL validation against the ACTUAL page + confirm >0 live roles before declaring done**, fixes repeatedly returned 0 by matching DDG titles or minified SPA JS.
- **After caching changes, confirm quick + full share consistent cache keys and the backend actually restarted before testing.**
