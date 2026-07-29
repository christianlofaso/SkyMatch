# SkyMatch Backend Deployment: Brainstorm / Discovery Notes
Date: 2026-06-05 · Goal: Decide how to deploy the FastAPI backend (+ SQLite + ingestion worker) to production, surfacing every constraint before writing config.

## Summary / key decisions  (FINAL, reconciled)
**Goal:** production-grade, horizontally-scalable backend launch (not a demo). Time is not a constraint, the deferred Postgres+Redis rework IS the deploy.

**Stack (locked):**
- **Frontend** → Vercel at `app.<domain>`. **Backend** → Railway at `api.<domain>` (custom domain owned; route `api.<domain>` through **Cloudflare** for WAF/DDoS). Frontend↔backend share parent domain for clean magic-link redirects + CORS.
- **Database** → **Supabase Postgres** for ALL app data + auth (Option B). Railway runs **compute + Redis only**. Co-locate Railway + Supabase regions; use Supabase **pooler** endpoint. Likely Supabase **Pro tier** (backups + connections).
- **Compute on Railway:** **web service = 2 fixed replicas** (redundancy + rolling deploys; autoscale later) + **worker service** (`python -m worker.ingest` via Railway **Cron ~6h**). Both connect to Supabase via `DATABASE_URL`.
- **Redis (Railway):** externalize the 3 in-process singletons → per-IP rate limiter, spend-cap total (manual kill-switch flag stays in `app_flags` in Supabase Postgres; reads fail-open), and `sonnet_sem` → **TTL token-bucket** sized to the Anthropic org Sonnet/min limit.

**Auth & abuse (locked):**
- **Floor (already ~exists):** hard global daily spend cap + kill switch + per-search cost tracking → move guard state to Redis, make cost per-user.
- **Model:** Cloudflare **Turnstile** + per-IP limit + **Supabase magic-link**. **Two-rule gate:** matcher gates at *results reveal* (`/run` open; `/analyze/batch` + `/internships/annotate` require auth); standalone analyzer = *one free, then gate*. Free-run tracking best-effort; spend cap is the true backstop.
- **Backend auth:** local HS256 JWT verify (`SUPABASE_JWT_SECRET`) via `require_user` dep on gated routes. New `users` + `usage` tables; `user_id` on `cost_events`. **Per-user quota = 20 matcher + 5 analyses/day → 429**; global cap → 503.

**Money (locked):** absolute ceiling **$50/day** → Anthropic Console hard cap $50; app `SPEND_CAP_USD_DAILY` ≈ **$32**; spend alert at ~50%.

**Ops (locked):** **Alembic** migrations; **staging + prod** (separate Supabase projects + Railway envs); **daily backups + tested restore**; CI gate (`py_compile`/`import main`/`tsc`) → **main auto-deploys staging, manual promote to prod**; **Sentry** wired; `USE_MOCKS=false` in prod; one **load test** vs staging pre-launch.

**Accepted risk:** LinkedIn/LinkdAPI scraping ToS exposure, launch as-is. **To author:** privacy policy + ToS + retention + deletion path.

**Supersession note:** Q2/Q4 (single-worker soft-launch) overridden by Q4b. Q3, Q13 "Railway Postgres" references superseded by Q14 → **Supabase Postgres**. The Q&A log below is kept verbatim as the decision trail.

## Hard constraints discovered in code (pre-grill)
- **SQLite is a local file**: `DB_PATH = Path(__file__).parent / "skymatch_cache.db"`, WAL mode. Needs a **persistent disk** that survives deploys/restarts, and the web process + worker must share the **same filesystem**.
- **Everything stateful is in-process / single-worker**: `sonnet_sem`, the per-IP rate limiter + concurrency caps, and the cached spend-cap total all live in process memory (CLAUDE.md). → Deployment must run **ONE uvicorn worker** (or multi-worker needs Redis, deferred).
- **Ingestion worker is a separate process** (`python -m worker.ingest`) on a ~6h schedule; today it's Windows Task Scheduler. On a Linux host it needs cron / the platform scheduler, and **must reach the same SQLite file** as the web process.
- **CORS is localhost-only** (`main.py`): must add the deployed frontend origin.
- No Dockerfile / Procfile / deploy config exists yet.
- `requirements.txt` does not pin firecrawl/linkdapi SDKs (those are raw httpx), fine, just noting.

## Q&A log

### Q1, Purpose & scale of the deployment
- Asked: Is this a portfolio/demo, or do you need to survive real concurrent traffic?
- Captured: **Real traffic, launch-ready.** Wants to test with a few people first, but the deployment must be ready for a real public launch, NOT just a demo.
- Implication: This collides head-on with the current single-process architecture (SQLite local file, in-process rate limiter / spend cap / sonnet_sem, worker sharing the same disk). "Launch-ready for real traffic" likely forces the deferred **Postgres + Redis** rework, OR a deliberate decision to soft-launch single-worker with a migration path. → drives Q2.
- Flags: none

### Q2, Scale-out now vs soft-launch single-worker?
- Asked: Fix the single-process limits now (Postgres+Redis) or soft-launch single-worker with a migration path?
- Captured: **Option A, ship single-worker NOW, rework gated BEFORE real launch.** Deploy one box / one uvicorn worker / persistent disk so testers hit a real URL this week. The Postgres+Redis migration is a hard blocker on any real/marketing launch, written down as such.
- Consequences accepted: hard traffic ceiling (vertical scale only); spend cap + per-IP rate limit + sonnet_sem are only correct because there is exactly ONE process, **must stay 1 uvicorn worker, no `--workers N`, no second replica.**
- Flags: BLOCKER-FOR-LAUNCH → migrate SQLite→Postgres + in-process guard/sonnet_sem state→Redis before any traffic spike. Owner: Chris (future work).

### Q3, Platform
- Asked: Which host, given web+worker must share a filesystem (SQLite)?
- Captured: **Railway.** Extra criterion: pick the Phase-1 path that makes the eventual **full launch easiest** (Railway one-clicks managed Postgres + Redis, so it's well-suited to Phase 2).
- Railway-specific trap: a **volume mounts to exactly ONE service**; a second worker service can't share it. So SQLite-on-Railway forces web + worker into **one service / one container** (worker via in-container scheduler, e.g. supercronic or a background process), volume-mounted.
- Migration-cost recon: `cache.py` = 702 lines with ~15 SQLite-specific constructs (`INSERT OR REPLACE`, `PRAGMA WAL`, etc.); `worker/ingest.py` 277; `lib/guard.py` 167. SQLite→Postgres is real but bounded.
- Flags: none

### Q4, Database: SQLite-now vs Postgres-now
- Asked: Keep SQLite for Phase 1, or adopt managed Postgres now?
- Captured: **Superseded by the next answer.** User then said: *"let's just plan for the full launch, I am not worried about time."*

### Q4b, REVERSAL: build for the full launch now
- Captured: **Drop the staged/soft-launch plan. Build the real, launch-ready, horizontally-scalable architecture from day one.** Time is not a constraint.
- This **overrides Q2's Option A and Q4's A1.** We are now doing the full Postgres + Redis rework (the old "Phase 2") as the actual deploy.

## Decisions locked  (UPDATED, full-launch architecture)
> ⚠️ Postgres host in this block was later changed by **Q14 → Supabase Postgres** (Railway = compute + Redis only). Read with that override.
- **Target = production-grade, horizontally-scalable from launch.** No single-worker soft launch.
- **Platform = Railway** (compute + managed **Redis**); **database = Supabase Postgres** (per Q14).
- **Data layer → Supabase Postgres.** Rewrite `cache.py` (702 lines, ~15 SQLite-specific constructs) + `worker/ingest.py` data access off SQLite/WAL onto Postgres. Co-location constraint dissolves → **worker becomes its own Railway service.**
- **Coordination state → Redis.** The three in-process singletons must move to Redis so >1 web replica is correct:
  - per-IP rate limiter + concurrency caps (`lib/guard.py`)
  - rolling spend-cap total + manual kill switch (`lib/guard.py` / `app_flags`)
  - `sonnet_sem` Sonnet concurrency governor (`lib/anthropic_client.py`) → distributed semaphore/token-bucket
- **Web service may now run multiple replicas / uvicorn workers** once the above is Redis-backed (the old ONE-worker invariant is lifted *only after* that work lands).
- Old "exactly one worker" invariant: **retired** (was a Phase-1 artifact).

### Q5, Access model / abuse + cost-runaway protection
- Asked: Who can hit it, and what stops a stranger running up the Anthropic bill? Open / captcha / accounts?
- Captured: User designed a **hybrid** (doesn't map cleanly to my 1/2/3):
  - **Non-negotiable FLOOR (every option):** hard **global daily spend cap + kill switch** + **per-search cost tracking in the DB**. This is what prevents the catastrophic "one Product Hunt day drains all credits" outcome. Cheapest piece, no access model is safe without it.
    - NOTE (code reality): this floor **largely already exists**, `lib/guard.py` (spend cap + manual/auto kill switch) + the `cost_events` ledger (`lib/cost.py`). Launch work = (a) move guard state to **Redis** for multi-replica correctness, (b) make cost tracking **per-user**, not just per-session/IP, (c) verify the cap is genuinely hard.
  - **On top of the floor, the chosen model:**
    - **Turnstile** (Cloudflare) on the expensive endpoint(s) + **per-IP rate limit**, free, invisible, stops bots & casual abuse.
    - **Supabase magic-link** auth gating the **results reveal**. User lands → runs the matcher → enters email → sees matches via magic link.
    - Feels like Option 2 to the user (email, no password); is actually **Option 3 underneath**, a real lightweight account, **per-user quotas**, foundation for monetization.
    - Bonus: real **validation signal** (who signs in, who clicks "paid early access") > a passive waitlist.
  - **Auth provider = Supabase** (locked).
- **Key design principle (locked):** **Do NOT wall the front door.** Let the run happen; gate at the *results reveal*. Preserves the "let them try it" behavior Product Hunt rewards while still capturing identity + capping spend.
- Flags: **OPEN SUB-DECISION**, exact gate placement: (a) gate at results reveal (run is free, results require auth) vs (b) one free full run, gate the *second*. User left this open → grill next (Q6).

### Q6, Exact gate placement + free-run tracking
- Asked: One uniform gate or two rules? And how to track an anonymous "free" run?
- Captured: **Two-rule gate (LOCKED):**
  - **Matcher flow** (home → results): **gate at results reveal.** `/run` is free + anonymous (it's zero-LLM serving + one cached Sonnet extraction, cheap). The **results page** (`/analyze/batch` Haiku volume + lazy `/internships/annotate` Sonnet) requires magic-link sign-in.
  - **Standalone analyzer** (`/analyze`, Opus Phase 3 = priciest single action): **one free analysis, then gate.** Try-it once, then sign-in.
- **Free-run tracking = best-effort** (Turnstile token + IP; cookie/IP are gameable). Accepted implicitly by choosing the two-rule gate; **the global spend cap is the true backstop** for anyone gaming the free tier. (Confirm if user wanted stronger.)
- Per-user daily quota once signed in: **numbers TBD** (placeholder 20 matcher runs + 10 analyses/day).
- Flags: per-user quota numbers TBD → Q10.

### Q7, Frontend host + production domain
- Asked: Where does the frontend deploy, and custom domain or platform subdomains?
- Captured: **Frontend = Vercel, backend = Railway (LOCKED).** User **owns a domain** (exact string TBD, needed for config).
- Recommended subdomain split (to confirm): **`app.<domain>` (Vercel frontend) + `api.<domain>` (Railway backend)**, shared parent domain makes magic-link redirects + cookies clean and stabilizes CORS (whitelist `*.<domain>` once vs churning `*.vercel.app`/`*.railway.app`).
- Backend config blocked on this: `main.py` CORS `allow_origins` → `https://app.<domain>`; Supabase magic-link redirect URL → frontend domain.
- Flags: provide exact domain string → Chris.

### Q8, Ingestion worker on Railway
- Asked: How does the worker run now that Postgres removed the shared-volume constraint? Spend accounting? Cadence?
- Captured (LOCKED):
  - **Worker = separate Railway service**, same repo/image, start command `python -m worker.ingest`, connects to managed Postgres via `DATABASE_URL`. No shared volume, no supervisor, no APScheduler.
  - **Scheduling = Railway native Cron** at **~6h** (run-and-exit shape already matches `python -m worker.ingest`). Cadence confirmed 6h.
  - **Spend accounting = SEPARATE.** Worker's Haiku/Voyage parse-pass spend is tracked in its **own budget bucket / own cap**, NOT the request-path `SPEND_CAP_USD_DAILY`. Rationale: ingestion is a background cost controlled by cadence; it must **never** trip the user-facing kill switch and 503 real users.
  - NOTE: CLAUDE.md is self-contradictory ("worker makes zero Claude calls" vs the Haiku parse pass), **the parse pass is real**; fix the doc. Need to wire worker LLM calls to a separate cost bucket (today they may be untracked).
- Flags: worker spend may currently be untracked in `cost_events` → add separate-bucket accounting. Fix CLAUDE.md contradiction.

### Q9, Redis + replica strategy
- Asked: Multi-replica at launch (forces Redis) or single replica (Redis optional)? Know your Anthropic Sonnet tier?
- Captured: User deferred to my judgment. **DECIDED (locked):**
  - **2 fixed web replicas at launch** (redundancy + rolling/zero-downtime deploys; no autoscaling yet, turn on later after watching real load). This makes Redis **non-optional**.
  - **Externalize all three in-process singletons to Redis:**
    - per-IP rate limiter + concurrency → Redis counters w/ TTL.
    - spend-cap total → Redis key; **manual kill-switch flag stays in Postgres** (`app_flags`); both reads **fail-open** (DB/Redis hiccup must not 503 everyone).
    - **`sonnet_sem` → Redis TTL token-bucket** sized to the Anthropic org's Sonnet/min limit (NOT a counting semaphore, abandoned tokens must self-expire so a crashed replica can't deadlock the governor; bucket reflects org-wide rate across all replicas).
- Flags: **need real Anthropic Sonnet tier limits** (req/min + tokens/min) to size the bucket → Chris reads Anthropic Console.
- **BUILD NOTE (milestone 2, 2026-06-05, implemented):** the governor shipped as a **crash-safe distributed *counting semaphore*** (a self-healing Redis ZSET where held slots are TTL-stamped and reclaimed once older than `SONNET_SLOT_TTL_SEC`), NOT a rate token-bucket. This satisfies Q9's actual requirement, *abandoned slots self-expire so a crashed replica can't deadlock the governor*, while **preserving the current concurrency semantics** (`SONNET_MAX_CONCURRENCY` becomes the global cap across replicas) and needing **no org tok/min number** (Chris didn't have it; chosen explicitly over the literal token-bucket). The objection to "a counting semaphore" in Q9 was the deadlock-on-crash failure mode, which the TTL reclaim removes. If we later want true rate (req/min or tok/min) limiting, revisit then with the Console numbers. **Redis is OPTIONAL with an in-process fallback** (no `REDIS_URL` → old single-worker behaviour); the per-IP limiter + spend cache got the same Redis-or-fallback treatment.

### Q10, Budget ceiling + quotas
- Asked: Absolute daily $ ceiling? Launch per-user quota OK?
- Captured (LOCKED):
  - **Absolute daily ceiling = $50.** This is the "if everything failed" number.
  - **Anthropic Console hard cap = $50/day** (the real circuit breaker, set in Anthropic dashboard, holds even if app logic is bypassed). → Chris sets this in Console.
  - **App-level `SPEND_CAP_USD_DAILY` ≈ $30-35** (~60-70% of $50) so the app graceful-503s itself *before* Anthropic hard-stops. (Pick exact: recommend **$32**.)
  - **Per-user daily quota = 20 matcher runs + 5 analyses** (analyses are Opus-heavy → tighter). Confirmed.
- Flags: Chris sets Anthropic Console monthly/daily budget cap to enforce $50/day. Decide exact app cap (rec $32).

### Q11, Migrations, environments, backups
- Asked: Alembic vs raw DDL? Staging/prod split? Backups?
- Captured (LOCKED, all three):
  - **Alembic** for schema migrations (versioned/reversible). Set up at Postgres-port time. Replaces relying on `CREATE TABLE IF NOT EXISTS` for schema evolution on populated tables.
  - **Staging + prod Railway environments** (each own Postgres + Redis). Deploy flow staging→prod; run migrations against staging copy first.
  - **Daily automated Postgres backups** + a **tested restore** (verify restore works, not just that backups exist).
- Flags: none.

### Q12, Deploys, secrets, observability
- Asked: CI/CD trigger? Secrets? Observability?, confirm the bundle.
- Captured (LOCKED):
  - **CI/CD:** GitHub-connected. **`main` auto-deploys to STAGING; manual promote staging→prod.** CI gate before deploy = existing checks (`py_compile`, `import main`, `npx tsc --noEmit`) as a GitHub Action so a broken build never ships.
  - **Secrets = Railway env vars, per-environment** (staging ≠ prod values), never committed. Full launch set:
    - Existing: `ANTHROPIC_API_KEY`, `VOYAGE_API_KEY`, `FIRECRAWL_API_KEY`, `LINKDAPI_KEY`, `ADMIN_TOKEN`, `SPEND_CAP_USD_DAILY`, Firecrawl knobs.
    - New: `DATABASE_URL` + `REDIS_URL` (Railway-injected), Supabase (`SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_JWT_SECRET`), `TURNSTILE_SECRET`, prod CORS origin.
    - **CRITICAL:** Supabase **service-role key + JWT secret are backend-only**; client gets only `anon` key + URL.
  - **Observability:** wire **Sentry** (errors + traces; the `# SENTRY:` stub in `main.py` global handler) + a **spend alert at ~50% of cap** so the kill switch is never the first warning. Railway logs for the rest.
- Flags: none.

### Q13, Auth verification + user/usage data model
- Asked: How does the backend verify the Supabase user, and where does per-user usage live?
- Captured (LOCKED):
  - **Local JWT verify** with `SUPABASE_JWT_SECRET` (HS256), stateless, via a FastAPI `require_user` dependency → extracts Supabase `sub`, 401 on invalid/expired. Attached **only to gated routes**: `/analyze/batch`, `/internships/annotate`, and the *second* `/analyze`. `/run` + first `/analyze` stay open.
  - **New Postgres tables:** `users` (keyed by Supabase `sub`; email, created_at, plan default `free`) + `usage` (per-(user, day) counters enforcing **20 matcher + 5 analyses/day**, checked before LLM fire → **429 over-quota**).
  - `cost_events` gets a **`user_id` column** → per-user spend attribution (Q5 floor, now per-user).
  - **Two distinct layers:** per-user quota = count-based **429**; global spend cap = dollar-based **503**. Both retained.
- Flags: none.

### Q14, Which Postgres holds app data (Supabase vs Railway)?
- Asked: Supabase Postgres for everything (B) vs Railway Postgres for data + Supabase identity-only (C)?
- Captured: **Option B (LOCKED), consolidate on Supabase Postgres for ALL app data + auth.** Railway runs only **compute (web + worker) + Redis**. One DB, one backup regime.
- **Latency tradeoff accepted:** every request-path DB query crosses providers (Railway compute → Supabase Postgres). MITIGATE: (1) **co-locate regions**, pick the Railway region + Supabase region in the **same geography**; (2) use the **Supabase connection pooler** (pgBouncer) endpoint, not direct, given 2 replicas + worker.
- **Ripple fixes to earlier answers (all "Railway Postgres" → "Supabase Postgres"):**
  - Q4b/Q8/Q9/Q11/Q13 data layer now targets **Supabase Postgres**; `DATABASE_URL` = Supabase pooler connection string (Redis stays Railway-injected `REDIS_URL`).
  - **Backups (Q11):** now **Supabase's** backup feature, NOTE this needs **Supabase Pro tier** for daily backups / PITR (free tier is limited). Tested restore still required.
  - **Staging vs prod (Q11):** Supabase environments = **separate projects** → provision **two Supabase projects** (staging + prod), each with its own keys/JWT secret. Railway environments handle compute/Redis per env.
  - Worker service connects to the same Supabase Postgres via `DATABASE_URL`.
- Flags: Supabase **Pro tier** likely required (backups + connection limits) → cost line for Chris. Region co-location is a setup-time must.

### Q15, Completeness sweep
- Asked: Legal/PII, LinkedIn risk, USE_MOCKS, retention, Cloudflare, load test, plus anything else?
- Captured:
  - **LinkedIn/ToS + scraping risk: ACCEPT AS-IS for launch** (user's explicit call). Documented as a known, accepted risk, not a blocker.
  - **Privacy policy + ToS + account-deletion path:** build (PII/accounts make this required-ish). Pairs with retention.
  - **`USE_MOCKS=false` enforced in prod**: yes (prod-safety guard).
  - **Cloudflare in front of `api.<domain>`**: yes (WAF/DDoS/edge rate-limit; already using Turnstile).
  - **One load test vs staging** before launch (k6/locust) to validate 2-replica + Redis Sonnet governor under concurrency, yes.
  - **Data retention policy**: define (profiles/results/cost_events); pairs with deletion path.
  - Nothing else surfaced by user.
- Flags: privacy policy / ToS / retention copy = Chris to author (or legal).

## Open flags (pending input)
- BLOCKER-FOR-LAUNCH: Supabase Postgres + Redis rework, now the actual deploy (no longer deferred).
- ACTION (Chris, external): set Anthropic Console hard budget cap (~$50/day); provide exact domain; read Anthropic Sonnet tier limits; provision 2 Supabase projects (staging+prod, co-located region, likely Pro tier).
- AUTHOR (Chris): privacy policy + ToS + data-retention policy + deletion path.
- ACCEPTED RISK: LinkedIn/LinkdAPI scraping ToS exposure, launch as-is.
- PROVIDE: exact domain string → Chris (for CORS, Supabase redirect, Railway/Vercel custom domains).
- PROVIDE: Anthropic org Sonnet rate-limit tier (req/min + tok/min) → Chris (Anthropic Console), sizes the Redis token-bucket.
- TODO(code): separate cost bucket for worker LLM spend; fix CLAUDE.md "zero Claude calls" contradiction.
