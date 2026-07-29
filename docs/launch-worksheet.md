# Launch provisioning worksheet

A fill as you go execution checklist for the one time dashboard setup. **Companion to
[`deploy.md`](deploy.md)**, that file is the *reference* (topology + why + per category env
inventory); this file is the *worksheet* you tick through in one sitting, in dependency order,
copying each secret into the table in §B as you go.

Do **staging first, end to end**, then repeat for prod. `main` auto deploys staging; prod is a
manual promote (see `deploy.md §4`).

> **Three guardrails that bite if ignored, read once:**
> 1. **`service_role` key and the legacy `JWT secret` are BACKEND ONLY.** The browser gets only
>    the project URL + `anon` key. Never put either behind a `NEXT_PUBLIC_*` var.
> 2. **Two different DB endpoints:** `ALEMBIC_DATABASE_URL` = Supabase **direct** (`:5432`);
>    `DATABASE_URL` = Supabase **pooler** (`:6543`). Swapping them breaks migrations or runtime.
> 3. **Never run >1 web replica without `REDIS_URL` set**: the guard + Sonnet governor degrade
>    to per replica (looser) limits. Add the Redis plugin before scaling replicas.

---

## A. Ordered steps (do top to bottom, per environment)

### Step 1, Domain registrar
- [ ] Own a domain.
- [ ] Decide the two hostnames: **`app.<domain>`** (frontend / Vercel) and **`api.<domain>`**
      (backend / Railway via Cloudflare). Write them down, many later values reference them.

### Step 2, Supabase (create TWO projects: `skymatch-staging`, `skymatch-prod`)
For **each** project (colocate region with Railway):
- [ ] Create the project on a tier with **daily backups / PITR** (Pro), needed for the
      backup restore checklist item.
- [ ] **Authentication → Providers → Email**: enable **magic link**.
- [ ] **Authentication → URL Configuration**: add redirect URL `https://app.<domain>`
      (and the staging URL for the staging project).
- [ ] **Settings → API / Database**: copy these four into §B:
  - Project **URL** → (backend `SUPABASE_URL` + frontend `NEXT_PUBLIC_SUPABASE_URL`)
  - **`anon`** key → (frontend `NEXT_PUBLIC_SUPABASE_ANON_KEY`)
  - **`service_role`** key → (backend `SUPABASE_SERVICE_ROLE_KEY`, **backend only**)
  - legacy **JWT secret** → (backend `SUPABASE_JWT_SECRET`, optional HS256 fallback only)
  - **Direct** connection string (`:5432`) → (backend `ALEMBIC_DATABASE_URL`)
  - **Pooler / transaction** connection string (`:6543`) → (backend `DATABASE_URL`)

### Step 3, Railway (one project, TWO environments: staging + prod)
In **each** environment, root directory for all services = `backend/`:
- [ ] Add the **Redis** plugin first (it injects `REDIS_URL` into the other services).
- [ ] Add the **web** service, uses default config `backend/railway.toml` (2 replicas,
      `preDeployCommand = alembic upgrade head`, healthcheck `/health`,
      `uvicorn main:app --host 0.0.0.0 --port $PORT`).
- [ ] Add the **worker** service, set **Config Path → `backend/railway.worker.toml`**
      (cron `0 */6 * * *`, `python -m worker.ingest`, no replicas).
- [ ] Set all backend env vars from §B on **both** web + worker (worker also gets
      `WORKER_SPEND_CAP_USD_DAILY`). Do NOT deploy yet if migrations should run against a
      fresh DB, the first web deploy runs `alembic upgrade head` automatically.

### Step 4, Vercel (frontend)
- [ ] Import the repo; **root directory = `frontend/`**.
- [ ] Add custom domain **`app.<domain>`**.
- [ ] Set the 5 `NEXT_PUBLIC_*` env vars from §B (per environment).

### Step 5, Cloudflare
- [ ] Proxy **`api.<domain>` → Railway** (orange cloud / WAF + DDoS in front).
- [ ] **Turnstile → Add widget**: copy the **site key** → frontend
      `NEXT_PUBLIC_TURNSTILE_SITE_KEY`, and the **secret key** → backend `TURNSTILE_SECRET`.

### Step 6, Anthropic Console
- [ ] Set a **hard budget cap of $50/day** (the real circuit breaker, independent of app logic).
- [ ] Set a spend alert at ~50% (~$25).

### Step 7, Sentry
- [ ] Create a project (or two, one per environment).
- [ ] Copy the **DSN** → backend `SENTRY_DSN`. Set `SENTRY_TRACES_SAMPLE_RATE=0.1` and
      `ENVIRONMENT=staging|production`.

---

## B. Secrets collected (fill the Value column as you go)

> Source of truth cross checked against `deploy.md §3`. **"Surface"** = where the var is set.
> Set every backend var on **both** the Railway web AND worker service unless noted.

### Backend, required (Railway web + worker)
| Value (fill in) | Env var | Where it comes from |
|---|---|---|
| | `DATABASE_URL` | Supabase **pooler** conn string (`:6543`) |
| | `ALEMBIC_DATABASE_URL` | Supabase **direct** conn string (`:5432`) |
| | `REDIS_URL` | Railway Redis plugin (auto injected) |
| | `ANTHROPIC_API_KEY` | Anthropic Console (already held) |
| | `VOYAGE_API_KEY` | Voyage dashboard (already held) |
| | `FIRECRAWL_API_KEY` | Firecrawl dashboard (already held) |
| | `LINKDAPI_KEY` | LinkdAPI dashboard (already held) |
| `false` | `USE_MOCKS` | literal, never ship mocks |
| `https://app.<domain>` | `CORS_ORIGINS` | the real frontend origin (Step 1) |
| `32` | `SPEND_CAP_USD_DAILY` | app graceful-503 below the $50 Anthropic hard cap |
| | `ADMIN_TOKEN` | invent a strong secret, gates `/admin/*` |

### Backend, auth + abuse gate (set together to turn gating ON)
| Value (fill in) | Env var | Where it comes from |
|---|---|---|
| | `SUPABASE_URL` | Supabase project URL, **the switch** that enables JWKS user token verification |
| | `SUPABASE_SERVICE_ROLE_KEY` | Supabase `service_role` key, **backend only**; used only by `DELETE /account` |
| | `TURNSTILE_SECRET` | Cloudflare Turnstile **secret** key, **backend only** |
| `20` | `QUOTA_MATCHER_PER_DAY` | per user/day matcher cap (default) |
| `5` | `QUOTA_ANALYSIS_PER_DAY` | per user/day analysis cap (default) |
| | `SUPABASE_JWT_SECRET` | *(optional)* legacy HS256 fallback, verifies anon/service keys, NOT modern user logins. Leave unset on a modern project. |

> *Optional auth tuning (rarely needed, code defaults are fine):* `SUPABASE_JWT_AUD`,
> `SUPABASE_JWT_ALG`, `SUPABASE_JWKS_TIMEOUT_SEC`, `TURNSTILE_TIMEOUT_SEC`,
> `SUPABASE_ADMIN_TIMEOUT_SEC`.

### Backend, observability
| Value (fill in) | Env var | Where it comes from |
|---|---|---|
| | `SENTRY_DSN` | Sentry project DSN |
| `0.1` | `SENTRY_TRACES_SAMPLE_RATE` | trace sample rate |
| `staging` / `production` | `ENVIRONMENT` | per environment |

### Backend, tuning (optional; code defaults in `.env.example`)
| Value (fill in) | Env var | Notes |
|---|---|---|
| `5` | `WORKER_SPEND_CAP_USD_DAILY` | **worker service only**, ingestion's own spend bucket (excluded from the user kill switch); 0 disables |
| *(default)* | `SONNET_MAX_CONCURRENCY` | org wide Sonnet cap; default 6 |
| *(default)* | `DB_POOL_MAX` | budget Supabase backend cap across replicas + worker |
| *(default)* | `RATE_LIMIT_PER_MIN` / `_CONCURRENT` / `_WINDOW_SEC` | per IP guard knobs |
| *(default)* | `SERVE_MAX_AGE_HOURS` | listing serve freshness |

### Frontend (Vercel, per environment)
| Value (fill in) | Env var | Where it comes from |
|---|---|---|
| `https://api.<domain>` | `NEXT_PUBLIC_API_URL` | the backend origin (Step 1) |
| | `NEXT_PUBLIC_SUPABASE_URL` | Supabase project URL (same as backend `SUPABASE_URL`) |
| | `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase `anon` key (the ONLY Supabase secret the browser may hold) |
| `true` | `NEXT_PUBLIC_AUTH_REQUIRED` | flips gates ON; set together with backend `SUPABASE_URL` |
| | `NEXT_PUBLIC_TURNSTILE_SITE_KEY` | Cloudflare Turnstile **site** key |

---

## C. Post provision wiring + verification

After all secrets are set, in order:
1. [ ] **First web deploy** to staging → confirm `preDeployCommand` ran `alembic upgrade head`
       clean (logs show migration to `0002_auth_tables`).
   - [ ] **Enable RLS on every `public` table** (Supabase SQL Editor), the Alembic tables are
         created RLS off, and the public anon key + PostgREST Data API would otherwise expose them
         (Supabase Security Advisor flags `rls_disabled_in_public`). Deny by default is safe: the
         app never uses PostgREST (frontend Supabase client is auth only; backend is direct
         psycopg as the `postgres` owner, which bypasses RLS). Run:
         `DO $$ DECLARE r record; BEGIN FOR r IN SELECT tablename FROM pg_tables WHERE schemaname='public' LOOP EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY;', r.tablename); END LOOP; END $$;`
         then verify `SELECT tablename FROM pg_tables WHERE schemaname='public' AND rowsecurity=false;`
         returns zero rows. The follow on "RLS enabled but no policy" advisor notices are expected,
         do NOT add policies. **This must be rerun on prod after its first migration.**
2. [ ] **Run the worker once** in staging (trigger the cron service manually) → national buckets
       populate. National buckets are empty until this runs.
3. [ ] Set frontend `NEXT_PUBLIC_AUTH_REQUIRED=true` **and** backend `SUPABASE_URL` together to
       flip the auth gate on.
4. [ ] Run the **`deploy.md §5` staging verifications**:
   - [ ] Auth e2e: magic link → token → `POST /analyze/batch` returns 200; anonymous → 401.
   - [ ] Turnstile verified; Cloudflare proxying `api.<domain>`.
   - [ ] `/admin/killswitch` + `/admin/status` reachable with `ADMIN_TOKEN`.
   - [ ] Anthropic $50/day cap set; `SPEND_CAP_USD_DAILY=32`; spend alert ~50%.
   - [ ] Supabase daily backups on + a **tested restore** (verify the restore, not just existence).
   - [ ] Sentry receiving events from staging.
   - [ ] One **load test** vs staging (`backend/loadtest/`, default tags = free `smoke`+`serve`+`guard`;
         run paid `governor` only deliberately with `PF_AUTH_TOKEN` set).
   - [ ] Privacy/ToS/account deletion published (counsel finalizes legal copy + contact emails).
5. [ ] **Promote to prod**: repeat §A Step 2-7 for the prod project/environment, then Railway
       redeploy prod from the same commit + Vercel promote the build. Rerun the §5 checks.
