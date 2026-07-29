# Route details

## Cost-protection gate (`lib/guard.py` + `routes/admin.py`)

The LLM-firing routers are wired in `main.py` with `dependencies=[Depends(cost_guard)]`: `run_router`, `profile_router`, `resume_router`, `analyze_router`, `internships_router`, `connections_router`. `cost_router`, `admin_router`, and the app-level `/health` are **ungated** so observability and recovery survive a halt.

`cost_guard` (a `yield`-dependency, chosen over `BaseHTTPMiddleware`, which buffers/breaks the ndjson streams of `/analyze/batch` + `/internships/annotate`) does, per request:
1. **Kill switch → `503`** if the manual flag `app_flags.kill_switch == 'on'` (read per request) OR rolling-window spend ≥ `SPEND_CAP_USD_DAILY` (cached `SPEND_CACHE_TTL_SEC`, computed by `cache.sum_spend_since`). Both reads fail **open**.
2. **Per-IP concurrency cap → `429`** if in-flight ≥ `RATE_LIMIT_CONCURRENT`.
3. **Per-IP sliding-window rate cap → `429`** if ≥ `RATE_LIMIT_PER_MIN` in `RATE_LIMIT_WINDOW_SEC`.
4. Reserve a slot; `yield`; release in `finally` (teardown runs after the stream completes).

Client IP = first hop of `X-Forwarded-For` (deploy is behind a proxy) else the direct peer. **State is Redis-backed (shared across replicas) when `REDIS_URL` is set, else in-process / per-replica.** The per-IP rate + concurrency limiter is an atomic Lua reserve over two Redis ZSETs, a sliding-window rate set and a crash-TTL'd concurrency set (`RATE_LIMIT_INFLIGHT_TTL_SEC`, so a crashed replica's in-flight slots self-expire); the rolling spend total is a shared Redis cache key (`guard:spend`) recomputed via `cache.sum_spend_since` at most once per `SPEND_CACHE_TTL_SEC` per replica. The manual kill-switch flag stays in **Postgres `app_flags`** (must survive restart + toggle instantly). All paths **fall back to the in-process implementation** when Redis is absent/unhealthy (`lib/redis_client.py` circuit breaker, `REDIS_RETRY_COOLDOWN_SEC`), local dev needs no Redis; a Redis outage degrades to per-replica limiting, never a 503. Knobs: `RATE_LIMIT_PER_MIN`/`_CONCURRENT`/`_WINDOW_SEC`/`_INFLIGHT_TTL_SEC`, `SPEND_CAP_USD_DAILY`/`_WINDOW_SEC`, `SPEND_CACHE_TTL_SEC`, `REDIS_URL`/`REDIS_RETRY_COOLDOWN_SEC`.

## Auth + per-user quota gate (`lib/auth.py`), OPTIONAL

Supabase magic-link auth, verified **locally + statelessly** (`sub` = user id). `_decode` routes by the token's `alg`: modern Supabase user-session tokens are **ES256** (asymmetric, keyed by `kid`) → verified against the project **JWKS** (`{SUPABASE_URL}/auth/v1/.well-known/jwks.json`, via `PyJWKClient`, cached); legacy **HS256** (`SUPABASE_JWT_SECRET`) is a fallback that only covers the anon/service keys, not real user logins (HS256-only → every login 401s on a modern project). **Switch = `SUPABASE_URL`** (auth on if it OR the HS256 secret is set); unset both → auth disabled, every dep returns `None`/no-ops, all routes stay anonymous (local dev unchanged). Set `SUPABASE_URL` → gating goes live, no code change.

One **cached** dependency does the work and the others build on it (FastAPI caches `Depends` per request, so decode+upsert runs once):
- `optional_user(request) -> User | None`: parse the `Bearer` token; `None` when auth off or no token; **401** on a present-but-invalid/expired token; else decode (verify sig + `exp` + `aud`) → `User`, and `upsert_user` (non-fatal on DB error). 
- `require_user(user=Depends(optional_user))`: **401** when auth is ON and the caller is anonymous; `None` when auth is off.
- `quota(kind)` / `enforce_quota(user, kind)`, increment the `usage_counters` row for `(user, UTC-day, kind)` and **429** over the cap; **no-op for anonymous** (spend cap is the backstop); fails **open** on a quota-store hiccup.

**Two-rule gate, attached per-route in the decorators** (router-level stays `cost_guard` only):
- **Matcher results-reveal → requires sign-in:** `POST /analyze/batch` (`require_user` + `quota("matcher")`, default 20/day) and `POST /internships/annotate` (`require_user` only, one results page expands many cards, so it's NOT separately quota'd; the matcher run is charged once on `/analyze/batch`).
- **Standalone analyzer → one free then gate:** `POST /analyze` (full mode only) + `POST /analyze/stream` charge `quota("analysis")` (default 5/day; Opus-heavy → tighter). The hard anonymous gate is frontend-side; the spend cap backstops.
- **Open (no auth dep):** `/run`, `/run/stream`, `/profile/*`, `/internships/search`, first `/analyze`.

`cost_events.user_id` attributes spend per user (threaded via `cost_session(name, user_id=…)`). **Cloudflare Turnstile** (`lib/turnstile.verify_turnstile`, on the expensive routes) is no-op until `TURNSTILE_SECRET` is set, then it requires `X-Turnstile-Token`; siteverify network errors **fail open**, a definitive reject → **403**. Knobs: `SUPABASE_URL` (JWKS switch) / `SUPABASE_JWKS_TIMEOUT_SEC`, `SUPABASE_JWT_SECRET` (HS256 fallback)/`_ALG`/`_AUD`, `QUOTA_MATCHER_PER_DAY`, `QUOTA_ANALYSIS_PER_DAY`, `TURNSTILE_SECRET`/`TURNSTILE_TIMEOUT_SEC`.

**`routes/admin.py`** (token-guarded by `X-Admin-Token` == env `ADMIN_TOKEN`; unset/mismatch → `403`, fail closed):
- `POST /admin/killswitch {on: bool}` → `set_flag("kill_switch", "on"|"off")`.
- `GET /admin/status` → `status_snapshot()`: kill-switch state, rolling spend vs cap, rate-limit config.

> Account-side backstop (not code): also set a monthly usage limit + billing alert in the Anthropic Console, the in-app cap guards credit burn, the account limit is the hard stop.

## `routes/run.py`, POST /run

Orchestrator with three code paths depending on inputs:

**Case 1: Resume only (`profile_id` set, no LinkedIn)**
Looks up the cached `UnifiedProfile` by `profile_id` (from `/profile/from-resume`). Fast path, no API calls.

**Case 2: LinkedIn only (`url` or `text`, no `profile_id`)**
Calls `analyze_profile()` → `extract_rich_fields()` (two Claude calls) → assembles `UnifiedProfile` → calls `search_internships(profile)`. (The old `suggest_connections` fan-out is removed, connections are dormant; `/run` returns `connections: []`.)

**Case 3: Both LinkedIn + resume**
Runs both Case 1 and Case 2 paths, then calls `_merge_profiles(linkedin_profile, resume_profile)`.

> `search_internships` no longer scrapes live and is now **zero-LLM**; it serves from the `listing_store` index by rank + deterministic build (see the internships section below). The per-user "why you fit" text is deferred to `POST /internships/annotate`, fired from the results page after the feed paints. The only `search_internships` call site is here in `run.py`.

**Merge logic (`_merge_profiles`):**
- Scalar fields (name, headline, location, school, company), LinkedIn is authoritative
- Flat list fields (technical_skills, fraternity_or_orgs, past_companies, certifications), union, deduped case-insensitively
- Rich list fields:
  - `work_experience`: keyed by `(company.lower(), title.lower())`; resume wins when both have descriptions; sorted by start date descending
  - `education`: keyed by `school.lower()`; entry with more non-null fields wins
  - `projects`: resume wins on duplicates; LinkedIn-only projects appended
  - `skills_with_context`: keyed by `skill.lower()`; longer context string wins

`USE_MOCKS=true` skips all API calls and returns `mocks/run_response.json`.

The 3-case profile resolution (+ merge) is factored into **`_resolve_profile(req) -> UnifiedProfile`**, shared by the JSON `/run` and the streaming `/run/stream` so the cases AND their Day-4 friendly error messages have one source of truth.

## `routes/run.py`, POST /run/stream (phased progress)

Additive streaming twin of `/run` for the home page's 2-step progress indicator. Emits `application/x-ndjson`, one `RunStreamEnvelope` per line:
`profile`(state=working) → `profile`(state=done) → `internships`(state=working) → `done` (carries the full `RunResponse`).

The no-input guard + `USE_MOCKS` short-circuit run **before** the `StreamingResponse` is constructed, so they still raise proper status codes. Profile + internship failures stream as an **`error` envelope** instead, a `StreamingResponse` locks its HTTP status at 200 the moment it starts, so the friendly Day-4 message is carried in `error.message` (byte-identical to what the JSON `/run` returns) and `error.status` is advisory (the home page only surfaces the message). This is the deliberate trade-off that lets the profile long-pole (the failure-prone part) show real progress; the JSON `/run` keeps full status-code granularity for any non-browser consumer. `timing_session`/`cost_session("/run/stream")` wrap the generator body so profile-extraction Claude spend is still captured.

## `routes/profile.py`, POST /profile/analyze

Extracts `ProfileAnalysis` from raw LinkedIn data using Claude. Two-function module:

**`analyze_profile(req)`**: rejects non-LinkedIn URLs immediately (hostname check: must contain `linkedin.com`). If URL, fetches via `LinkdClient.get_profile()`. Sends to Claude, validates result. Raises `ValueError` (→422) for soft guards and `HTTPException` for upstream failures. Guards:
- Non-LinkedIn URL → `ValueError("That doesn't look like a LinkedIn profile URL...")`
- Paste shorter than ~40 chars → `ValueError("That's too short to read as a profile...")` (before any LLM call)
- LLM returned no `full_name` → `ValueError("No LinkedIn profile found at that URL...")`
- Pydantic `ValidationError` → `ValueError("Could not extract a complete profile...")`
- **LinkdAPI errors mapped** (was a raw 500): `httpx.HTTPStatusError` 404/410 → `ValueError` (private/missing → 422), 429 → `HTTPException(503)`, 401/403 → `HTTPException(502)` (logs the key issue), other 5xx → `HTTPException(502)`; `httpx.RequestError`/timeout → `HTTPException(504)`. `LinkdClient` retries transient failures (429/5xx/network) before these surface. **Callers (`/profile/analyze`, `/run`, `/profile/from-resume`) must `except HTTPException: raise` before their generic handler** or these regress to 500s.

**`extract_rich_fields(source_text)`**: second Claude call using `rich_profile_extraction.txt` prompt. Returns dict with `skills_with_context`, `education`, `work_experience`, `projects`, `certifications`. Caller handles exceptions.

Claude call: `claude-opus-4-8`, max 1024 tokens (analyze), 2048 tokens (rich fields).

## `routes/resume.py`, POST /profile/from-resume

Accepts PDF or DOCX file upload (max 5 MB). Extracts text using `pdfplumber` (PDF) or `python-docx` (DOCX). Runs `analyze_profile()` + `extract_rich_fields()` in parallel. Assembles `UnifiedProfile` with `sources=["resume"]`. Caches under hash of file bytes. Returns `{"profile_id": cache_key, "profile": UnifiedProfile}`.

The `profile_id` is what the frontend sends to `/run`; it's just a cache lookup key.

## `routes/analyze.py`, POST /analyze

Job-fit pipeline with two modes (`full` default, `quick`). High-level flow: **Resolve → Per-user cache check → Step A (cached) → branch on mode → cache result**.

**Stage 1: Resolve job content (`_resolve_job`)**

Priority checks before any fetch:
1. LinkedIn domains (`_AUTH_WALL_DOMAINS`) → 422 with paste instructions
2. `_SPA_SEARCH_PORTALS` → 422 with site-specific paste instructions (currently empty; Microsoft moved to a `site_handler`)

For a URL, `_resolve_job` first checks `job_fetch_cache` (per-URL, 3-day), a hit skips the fetch entirely (path `"cache"`). On a miss, `_fetch_job_content()` runs four tiers (wrapped in the `analyze/fetch` timing span) and the scraped text + `posted_at`/`apply_url` are written back to `job_fetch_cache`:
- **Attempt 0, site handler dispatch** (`site_handlers.dispatch(url)`). Matched handlers (e.g. Microsoft) return a normalized `JobPosting`. If a handler matches but returns `None`, falls through to Attempt 1.
- **Attempt 1, direct httpx GET** (15s, browser headers, follow redirects): accepts if `_MIN_CONTENT_LEN (200) ≤ len ≤ _MAX_CONTENT_LEN (50,000)` chars. Out-of-range → Firecrawl.
- **Attempt 2, Firecrawl with `_FIRECRAWL_PROXY_MODE`** (default `"auto"`): POST `/v1/scrape`, `formats: ["markdown","extract"]`, schema-locked extraction via `_JOB_SCHEMA`, then `_build_text_from_extraction()`. Falls back to markdown if ≥ 200 chars. `"auto"` escalates past Cloudflare / JS shells server-side, so the old manual basic→stealth retry (2a/2b) collapsed into this single call.
- All attempts failed → 422.

`_FetchResult(text, path, extracted, posted_at, apply_url)`: `posted_at` and `apply_url` are populated only by site_handlers (Microsoft today).

`_resolve_job()` returns `(job_text, fetch_result, job_id)`. **`job_id` is the stable cache identifier**: `"url:" + _canonical_url(url)` when a URL is present, `"text:" + sha256(normalize_job_text(text))[:32]` otherwise. Two fetches of the same URL → same `job_id` even if the fetched markdown differs.

**Stage 2: Per-user cache check**

`cache_key = analysis_cache_key(mode, profile_json, job_id)` → `get_user_analysis_cache(cache_key)`. Hit → return immediately.

For a `full`-mode cache hit, the route also looks up the **quick** cache for the same `(profile, job_id)` and reconciles `fit_score` + `verdict.call` if the stored full headline differs (self-healing for entries written before the reconcile fix). The cleaned dict is rewritten.

**Stage 3: Extract requirements (`extract_requirements`)**

Wraps `_run_extraction` (**`MODEL_MID` / Sonnet** call, `job_requirements_extraction.txt`; parsed via `_loads_lenient` for Sonnet prose-wrap safety) with a global `requirements_cache` (SQLite, 30d, keyed by `job_text_hash`). Both modes call this so the second pass on the same job text, even by a different user, skips the call entirely.

**Quick mode (when `mode="quick"`)**

`_run_quick_verdict(profile, requirements)`: one Haiku call with `quick_verdict.txt` prompt; returns `(fit_score, Verdict)`. Result wrapped in `QuickAnalysisResponse` with a `QuickJobSummary` that surfaces `posted_at` and `apply_url` from `_FetchResult` (currently populated only on Microsoft URLs).

**Full mode (when `mode="full"`)**

`_run_matching(profile, requirements)`: **`MODEL_MID` / Sonnet** call using `evidence_matching.txt` (parsed via `_loads_lenient`). Returns `(list[_EvaluationItem], verdict_reasoning)` with `match_strength` ∈ `{strong, partial, missing}` and evidence snippets+sources from the profile.

**Score computation (deterministic, no LLM):**
- `category_scores`: per-type weighted score (must-have = 2×, nice-to-have = 1×); strong = 100%, partial = 50%, missing = 0%
- `fit_score`: weighted average of category scores using `CATEGORY_WEIGHTS` (technical 35%, experience 30%, education 20%, domain 15%). `"soft"` is tracked in `category_scores` but excluded from `fit_score`.
- `gaps`: missing/partial must-haves + missing nice-to-haves; severity = critical (missing must-have experience/education) → moderate (missing must-have other) → minor
- `verdict_call`: `"skip"` if any critical gap or fit < 40; `"apply_now"` if fit ≥ 70 and no must-have missing; else `"apply_after_prep"`

**Headline reconciliation:** if a quick analysis is cached for the same `(profile, job_id)`, the full response's `fit_score` and `verdict.call` are overridden with quick's values so the card and the detail page show the same numbers. `category_scores`, `matches`, `gaps`, `verdict.reasoning`, and `job_summary` still come from the full computation. (Implication: the category bars on the full view don't strictly weighted-average to the reconciled headline, accepted trade-off.)

**Phase 3, roadmap + project_suggestion (parallel, additive):**

After Step B + headline reconciliation, `_generate_phase3()` fires two LLM calls in parallel via `asyncio.create_task`:

- `_run_roadmap` (when `include.roadmap=true` AND `gaps` non-empty), one Opus call using `prompts/roadmap.txt`. Up to 2 attempts total (1 + `_ROADMAP_MAX_RETRIES=1`); after each attempt, every resource URL is validated through the two-stage pipeline (allowlist → async HEAD with 3 s timeout, results cached 7 days in `url_liveness_cache`). Valid resources accumulate per skill across attempts (deduped by URL, capped at 4). Retries only fire if any item still has < 2 valid resources. Under-filled items pass through with fewer resources rather than being dropped. Items capped at 5 total.
- `_run_project_suggestion` (when `include.project=true`): one Opus call using `prompts/project_suggestion.txt`. No URL validation needed.

When `include.roadmap=true` but `gaps` is empty, `roadmap_note` is set to a canned string instead of running the LLM. Failures in either call are logged and swallowed (`None`) so a Phase 3 failure can't break the rest of the analysis. Both results land in `AnalysisResponse` and serialize through `set_user_analysis_cache`.

**Perf / timing:** the whole route is wrapped in `timing_session(f"/analyze {mode}")` (mirrors `/run`) with spans `analyze/fetch`, `analyze/extract`, `analyze/match`, `analyze/phase3` (+ `analyze/firecrawl:{proxy_mode}`, e.g. `analyze/firecrawl:auto`). Measured on a real full run: extract **6.6s** + match **9.5s** (both now Sonnet, down from Opus) but **phase3 ≈ 54s (~77% of the request)**, `_run_roadmap` dominates (Opus 4096 + `_ROADMAP_MAX_RETRIES=1` retry, each with URL HEAD validation). Cutting retries 2→1 trimmed ~10s (total ~80s→~70s). Roadmap + project remain `MODEL_FULL` (Opus) by choice; **downgrading them to Sonnet is the next lever** (~54s→~25s) if `/analyze` needs to be faster.

**Phase 3 cache backfill:** in the cache-hit branch, if a stored full-mode row predates Phase 3 (missing `roadmap`/`project_suggestion`) and the request asks for them, `_phase3_backfill_cached_row` rehydrates `JobSummary`/`MatchItem`/`GapItem`/`Verdict` from the cached row, runs only the missing LLM calls using the live request profile, and writes the patched dict back. No job re-fetch, no Step A re-run.

**Caching:** keyed by `analysis_cache_key(mode, profile_hash, job_id)`. `profile_hash` = sha256 of the **full** `profile.model_dump_json()` (fixes the old 500-char-truncation bug). 30-day TTL.

## `routes/analyze.py`, POST /analyze/stream (full-mode true streaming)

Additive streaming twin of `/analyze` full for the analyze page's progressive in-place render. Emits `application/x-ndjson`, one `AnalyzeStreamEnvelope` per line: `verdict` → `roadmap`/`project` (completion order) → `done`. The JSON `/analyze` is untouched (quick mode, detail-page cache re-reads, and any other caller still use it).

- **Prelude before the stream:** `_analyze_stream_prelude(req)` runs the entire can-fail prefix, `_resolve_job` → user-cache check (incl. self-heal + `_phase3_backfill_cached_row`) → `extract_requirements` → `_run_matching` → scoring/matches/gaps/verdict + headline reconcile, and **raises `HTTPException` 422/500 here, before the `StreamingResponse` is constructed**, so the JSON endpoint's error contract is preserved with zero regression. (Phase 3, which streams, already swallows its own failures, so nothing in the streamed portion needs to surface as an HTTP error; the `"error"` phase is a defensive belt-and-suspenders only.) It returns either `("cache_hit", AnalysisResponse)` or `("computed", verdict_payload, cache_key, include)`.
- **Cache hit:** `_cached_stream_envelopes(full)` replays the cached `AnalysisResponse` as the same `verdict → roadmap → project → done` sequence, so the frontend's stream-assembly path is identical for hits and misses.
- **Computed:** the generator emits the `verdict` envelope (everything available right after matching), then `_stream_phase3(...)`, the async-generator twin of `_generate_phase3`, fires the same roadmap + project tasks concurrently but yields each as **it** completes (via `asyncio.wait(FIRST_COMPLETED)`, mapping task→kind), so whichever finishes first reaches the client first. Same no-gaps `roadmap_note` + failure-swallow semantics. After both, it assembles the full `AnalysisResponse`, writes `set_user_analysis_cache`, and emits `done`.
- **Sessions / cost:** the prelude runs under its own `cost_session("/analyze/stream prelude")` (extract/match spend) and the generator under `cost_session("/analyze/stream phase3")` (Phase-3 spend), **two `[cost]` ledgers print by design**, because a single `with` can't straddle the route's `return` of the StreamingResponse. Phase-3 tasks are created inside the generator's `cost_session` so the `_rows` contextvar propagates (same guarantee `/analyze/batch` relies on).
- `_generate_phase3` itself is unchanged (still used by JSON `/analyze` + the cache backfill).

## `routes/analyze.py`, POST /analyze/batch

Streams quick analyses across many jobs. Built on the same `_quick_for_one()` helper as the single-job quick path.

- Body: `BatchAnalyzeRequest { profile, jobs[1..50] }`. Pydantic's `Field(max_length=50)` produces the 422, no manual count check.
- Response: `application/x-ndjson` with `Cache-Control: no-store` and `X-Accel-Buffering: no`. One `BatchEnvelope` per line, terminated with `\n`. Order = completion order, not request order.
- Concurrency: `asyncio.Semaphore(_BATCH_LLM_CONCURRENCY = 8)`. Cache hits return without acquiring the semaphore.
- Per-job try/except wraps `_quick_for_one`. `_classify_exc(exc)` maps to one of `{FETCH_FAILED, EXTRACTION_FAILED, VERDICT_FAILED, INTERNAL}`. A single failed job emits an error envelope and never aborts the batch.
- Internal task pattern: each `_one(i, job)` pushes to a shared `asyncio.Queue`; the generator awaits the queue and `yield`s each line, then decrements its pending counter. The route's cleanup cancels any tasks still in flight on early disconnect.

## `routes/connections.py`, POST /connections/suggest

Runs 3-5 parallel LinkdAPI `search_people` queries using different keyword combinations (frat+school, past_company+school, school+field, school+major). Deduplicates by `linkedin_url`, takes up to 15 candidates, sends to Claude → exactly 10 `Connection` objects. People-search results cached 7 days.

## `routes/internships.py`, POST /internships/search (index-served, zero-LLM)

`search_internships(profile)` serves from the `listing_store` index (populated by `worker/ingest.py`), it does **no** live scraping, URL-finding, validation, **or LLM calls** at request time. In steady state the profile-independent work (display fields + an embedding) is **precomputed at ingestion** (the worker's parse pass), so the per-request work is just: (1) a no-LLM **rank**, embed the profile once (Voyage), drop precomputed-ineligible rows, and cosine-narrow each bucket to `_PRESELECT=18`; (2) a no-LLM **select + build**, `_select_and_build` walks the ranked rows, enforces company-diversity (≤2/company), and assembles up to 5 `Internship` cards per bucket straight from the precomputed display fields. The per-user `fit_explanation`/`reach_gap` ships **empty** and is filled lazily by `POST /internships/annotate` (below). Wall time = embed + cosine (the only network call) + in-memory build.

**Flow:**
1. `metro = _parse_metro(profile.location)`.
2. Read the index via `_serve_national_rows("_national", "startup"|"big_tech")` + `_serve_national_rows("_reach", "reach")` (metro-independent, served to all), at `max_age = _SERVE_MAX_AGE` (`SERVE_MAX_AGE_HOURS`, default **48h**, tightened from 72h so served links are fresher). **Empty-bucket fallback:** if a national/reach bucket is empty at the tight window (the worker lagged past 48h), `_serve_national_rows` retries that bucket once at `_SERVE_MAX_AGE_FALLBACK` (`SERVE_MAX_AGE_FALLBACK_HOURS`, default 96h) and logs `[serve] bucket … fell back`, degrades to slightly-staler rather than empty. (Local has its own live-fetch fallback, so it reads at the tight window directly.) **This freshness depends on the worker's cron cadence**, see the gotcha.
3. **local**: read `get_listings(metro, "local")` if `metro in get_rotation_metros()`; **fall back to `_live_local_fetch(profile, metro)` when that's empty** (metro not in rotation, OR seeded-but-not-yet-ingested/stale, so seeding the ~30 `SEED_METROS` can never serve an empty local bucket; once the worker populates them, this never fires for a seeded metro). The live-fetch, scrape + validate the local bucket once (bounded by `_LIVE_LOCAL_BUDGET=35s` via `asyncio.wait_for`), `upsert_listing` the survivors under `niche_key=metro`, then **run the worker's parse precompute INLINE** on them (`lib.precompute.parse_and_embed_rows(..., firecrawl_company=False)`, Haiku company/role_category + Voyage embedding; the **only LLM on the request path**, and only for an uncovered metro's first visit), and `add_rotation_metro(metro)`. Returns the **freshly-read DB rows** (`get_listings(metro, "local")`) so the inline parse takes effect THIS request; on timeout/error it still returns whatever upserted (parsed or not), never `[]`. _(Parsing inline is the fix for the recurring "Unknown company" + off-field local role: a scraped-but-unparsed row has no resolved company, no `role_category`, no embedding, see step 4/5.)_
4. **Rank** (`internships/rank (embed + cosine)`, no LLM): `_to_listings(rows)` maps store rows → the serving shape (the precompute, `parsed`, `embedding`, `embedding_model`, `embedding_dim`, **plus** the raw scraped columns `search_title`/`company`/`verified_location`/`snippet` used as a fallback). `_embed_profile` embeds `_profile_brief(profile)` once (Voyage, `input_type=query`, per-process cached by `EMBED_MODEL`+brief). `_safe_rank`/`_prefilter_and_rank` per bucket: drop rows whose `parsed.is_internship is False`; drop **PhD-mandatory** roles in EVERY bucket (parsed `requires_phd is True` OR a `_PHD_TITLE_RE` "PhD"/"Ph.D" title match, the undergrad-intern audience can't apply, and the title regex backstops unparsed rows + parse misses); and, for **reach OR local** (`_OFF_FIELD_BUCKETS`), drop `role_category` in `_OFF_FIELD_CATEGORIES` = finance/sales/marketing/recruiting/audit (off-field for this product's CS/eng audience); then cosine-rank embeddable rows (`mat @ q_vec`, both unit-normalized so dot == cosine) and keep top `_PRESELECT=18` + any unrankable remainder. **Degrades gracefully:** Voyage unavailable → `q_vec=None` → skip cosine, serve unranked (DB order); a per-bucket error → unranked pool; only rows whose `embedding_model`/`embedding_dim` match the current query are ranked. (The off-field filter only fires on **parsed** rows, an unparsed row can't be category-filtered, so the inline parse above is what makes it bite for live-fetched local.)
5. **Select + build** (no LLM): `_select_and_build(rows, bucket)` walks the ranked rows in order, builds each card via `_build_internship` (display fields from `parsed_json`, or the raw columns when a row is unparsed; `fit_explanation=""`, `reach_gap=None`, `application_url`/`bucket` forced from the row) **wrapped in a per-row `try/except`, a single malformed/wrong-typed row is logged (`[serve] skipped malformed …`) and skipped, so it can't break the whole bucket**, and keeps the top 5 while dropping exact-duplicate `(company, title)` roles and enforcing ≤2 per company, replacing both the old Sonnet SELECT and the old `_cap`. **Unparsed rows** (warming index / live-fetch before parse) have no `parsed_json`, so `_build_internship` + `_fit_fields` resolve a clean title + company via the chain **`parsed → _parse_title_company (`"{Role} @ {Company} - Jobs"` and `"{Role} - {Company} - {Lever/Greenhouse/Ashby}"`) → company_from_url (ATS slug) → column → "Unknown"`**, so an ATS-board URL never shows "Unknown" even with no Haiku key. **The ≤2/company cap is skipped for unresolved (`"Unknown"`) companies** so distinct unknowns don't collapse the bucket to 2.

## `routes/internships.py`, POST /internships/annotate (deferred fit text)

The zero-LLM feed ships `fit_explanation` empty; the results page fans the served URLs out here to fill in the personalized "why you fit" text one role at a time. Mirrors `/analyze/batch`: streamed `application/x-ndjson` (`Cache-Control: no-store`, `X-Accel-Buffering: no`), one `AnnotateEnvelope` per line in completion order, each `_one(i, job)` pushing to a shared `asyncio.Queue` and the generator cancelling in-flight tasks on disconnect.

- Body: `AnnotateRequest { profile: UnifiedProfile, jobs: [{url, bucket}] }` (each job a served listing). `AnnotateEnvelope { index, status, fit_explanation?, why[], have[], need[], reach_gap?, error? }` (`error.code ∈ {NOT_FOUND, ANNOTATE_FAILED, INTERNAL}`). `why` (2-3 "why you fit" bullets), `have` (skills the student already brings), and `need` (gaps to shore up) feed the role drawer; the slim Sonnet call (`_annotate_fit_sync`, max_tokens 400) emits them in one JSON object grounded in the listing's parsed `skills`. Pre-enrichment `annotate_cache` hits lack these keys → default `[]`.
- Per job (`_annotate_one`): `cache.get_listing_by_url(url)` (prefers a valid, parsed row; `parsed_json` is profile-independent so any row for the URL serves). Missing → `error/NOT_FOUND`. `_fit_fields(listing)` builds the prompt context from `parsed_json` when present, else the raw columns (`search_title`/`company`/`verified_location`/`snippet`) so unparsed/live-fetched rows still annotate. Then the **slim fit-only** `_annotate_fit_sync` (`_annotate_fit_system`, `MODEL_MID`, `max_tokens≈160`) returns `{fit_explanation, reach_gap}`, gated by the global `sonnet_slot()` governor. A model decline/error → `ok` with empty `fit_explanation` (the card just keeps its blank "why you fit" rather than spinning). `reach_gap` is only requested/returned for `bucket=="reach"`.
- Frontend: `lib/api.annotateFit` streams these; the results page dedupes by `application_url` (reusing the scoring dedup), prefers the `reach` bucket for a URL so `reach_gap` is computed, fans `fit_explanation` to every slot sharing the URL (and `reach_gap` to reach slots), and persists to `pf:annotations:{runId}` so a return visit hydrates without re-calling.

**Ingestion (`worker/ingest.py`, standalone, NOT this route):** `ingest_national()` scrapes startup + big_tech across `NATIONAL_FIELDS` (CS/CompE/EE/SWE/ML/DS), unions+dedups by URL, stores under `"_national"`; `ingest_reach()` pulls `REACH_ATS_SLUGS` via `_fetch_ats_listings` under `"_reach"`; `ingest_local(metro)` per metro in the rotation. Each runs `_enrich_listing` (verified_location + category-page drop) and `validate_job_url` (6-rule DROP POLICY below), then `upsert_listing`. All of this discovery/enrich/validate code lives in `lib/ingest_core.py` (the request path imports it only for `_live_local_fetch`). **After** storing + pruning, `parse_pass()` runs the profile-independent precompute by delegating to the shared **`lib/precompute.parse_and_embed_rows`** (the SAME helper the request-time local live-fetch calls): for every `parsed_at IS NULL` valid row, a bounded Haiku call (`lib/listing_parser.py`, `WORKER_PARSE_CONCURRENCY=8`, defined in `lib/precompute.py`) extracts the structured/display fields and a batched Voyage call (`lib/embeddings.py`) embeds it; `set_listing_parse` persists both. Incremental (only new/changed rows). The worker passes `firecrawl_company=True` (it can afford the SPA render); the live-fetch passes `False`. Both `ANTHROPIC_API_KEY` and `VOYAGE_API_KEY` are **optional**, missing either skips that work and serving falls back. The worker makes **no Sonnet/Opus** calls. Company resolution in the parse uses a fallback chain (Haiku → stored `company` column → `company_from_url()` for ATS/amazon URL shapes → `"Unknown"`); for SPA boards where the company is only on the rendered page (wellfound/workatastartup), the parse pass additionally runs a bounded `company_from_firecrawl()` render to recover it (only for new/changed SPA rows). A follow-on `embed_backfill_pass()` then embeds any rows that were **parsed but never embedded** (Voyage down/rate-limited at parse time), re-using the stored parse, **no Haiku**, so embeddings land on a later run without re-parsing (avoids the "Voyage-down trap": `parsed_at` is stamped on parse success alone, so those rows would otherwise never re-enter `get_listings_to_parse`).

> The old per-request live-scrape/fabrication path (`INTERNSHIPS_SYSTEM`, `_get_url`/`_find_via_*`/`_find_job_url` URL-finders, `_validate_with_sem`) has been **removed**. So has the per-request Sonnet **SELECT** + inline annotation that briefly replaced it (`_select_system`/`_select_bucket_sync`/`_format_candidates`, `_annotate_system`/`_annotate_one_role_sync`, `_cap`, the `_ANNOTATE_POOL` thread pool, `_OVERSELECT`): serving is now zero-LLM and the only Sonnet call left in the file is the deferred `_annotate_fit_sync` behind `/internships/annotate`. The DROP POLICY below still governs ingest-time + local-fallback validation.

---

# URL validation DROP POLICY

In `validate_job_url()` in `routes/internships.py`. Rules checked cheapest-first:

1. **No URL** → `no_url`
2. **Generic URL pattern** → `no_job_id_in_url`, `careers_subdomain_root`, etc., no HTTP call
3. **HTTP status ≥ 400** → `http_404` etc.
4. **Redirects to generic URL** → `redirect_to_{reason}` (Greenhouse redirect exception, see below)
5. **Closed listing string in body** → `closed: {string}`
6. **Title tokens not found in body** → `title_not_found` (≥ 60% of tokens required)

Any URL without a 5+ digit number or UUID in path fails rule 2 (`_JOB_ID_RE`). Results cached 24h in `url_validation_cache`.

**Domain exceptions:**
- `workatastartup.com`: rules 5+6 incompatible with Rails SSR; checks HTTP status + domain redirect instead
- `wellfound.com`: Cloudflare 403s plain clients, so it's rendered + liveness-checked via Firecrawl proxy **`"auto"`** (`_firecrawl_job_alive`; `auto` escalates past Cloudflare server-side). Dropped if unrenderable (network error, empty, or no `FIRECRAWL_API_KEY`).
- `_SPA_CAREER_DOMAINS` (Microsoft careers, `jobs.nvidia.com`, …): JS-SPA / Eightfold sites that serve a generic shell server-side, so a plain fetch can't tell open from closed. Rendered + liveness-checked via Firecrawl proxy **`"auto"`** (same call path as wellfound, `auto` stays on the cheap proxy when a basic render suffices). Add new SPA ATS domains to this set.

`_firecrawl_job_alive` liveness logic: (1) drop if any `CLOSED_STRINGS` phrase is in the rendered markdown; (2) trust Firecrawl's **focused `extract.job_title`**, NOT the raw markdown, since a dead SPA listing renders a huge generic hub shell that false-matches title tokens. Drop when the extracted title is empty or a dead sentinel (`_DEAD_TITLE_SENTINELS`: "not found"/"no longer"/"404", e.g. nvidia returns `job_title="Not Found"`), pass only when it token-matches the expected title.
- `boards.greenhouse.io` redirects, relaxed rule 4: if redirect has `?gh_jid=` or non-generic path, continue to rules 5+6

The Firecrawl scrape itself lives in the shared `backend/lib/firecrawl.py` (`is_available()`, `scrape(url, proxy)`, `JOB_SCHEMA`), reused by both `analyze.py` and `internships.py`.

```python
_PROPRIETARY_ATS = {"google", "meta", "apple", "microsoft", "amazon", "netflix", "tesla", "linkedin"}
BLOCKED_DOMAINS  = ["linkedin.com", "facebook.com", "twitter.com", "instagram.com"]
```
