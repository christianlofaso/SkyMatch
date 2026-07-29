# Deploying SkyMatch

The launch architecture decided in [`brainstorms/2026-06-05-backend-deploy.md`](../brainstorms/2026-06-05-backend-deploy.md). This file is the runbook; read the brainstorm for the *why*.

```
Vercel (frontend)            Railway (compute + Redis)            Supabase (Postgres + Auth)
  app.<domain>  ──HTTPS──►   api.<domain>  ──► web ×2 replicas ──►  Postgres (pooler :6543)
  (Next.js 14)   (Cloudflare   (FastAPI)        worker (cron 8h) ──►  Auth (magic-link)
                  in front)                     Redis (guard/governor)
```

- **Frontend** → Vercel at `app.<domain>`.
- **Backend** → Railway at `api.<domain>`, routed through **Cloudflare** (WAF/DDoS).
- **Database + Auth** → **Supabase** (all app data + auth). Railway runs compute + Redis only.
- **2 Supabase projects** (staging + prod) and **2 Railway environments**; `main` auto deploys **staging**, prod is a **manual promote**.

---

## 0. One time external setup (you, in dashboards)

| Where | Action |
|-------|--------|
| **Domain registrar** | Own a domain. Decide `app.<domain>` (frontend) + `api.<domain>` (backend). |
| **Supabase** | Create **two** projects: `skymatch-staging`, `skymatch-prod` (colocate region with Railway). **Pro tier** for daily backups / PITR. In each: enable **Email (magic link)** auth; add the redirect URL `https://app.<domain>` (+ the staging URL). Grab per project: **project URL** (the backend auth switch, JWKS verifies the project's ES256 user tokens), `anon` key, `service_role` key, and the legacy `JWT secret` (HS256 fallback only). |
| **Railway** | Create a project with **2 environments** (staging, prod). In each, add **3 services** (see §2) + a **Redis** plugin. |
| **Vercel** | Import the repo; root directory `frontend/`. Add the custom domain `app.<domain>`. |
| **Cloudflare** | Proxy `api.<domain>` → Railway. Turnstile: create a widget → **site key** (frontend) + **secret key** (backend). |
| **Anthropic Console** | Set a **hard budget cap ($50/day)**, the real circuit breaker, independent of app logic. |

---

## 1. Schema / migrations (Alembic)

Schema is owned by Alembic (`backend/alembic/versions/`), NOT app code. Migrations run as the
Railway **`preDeployCommand` (`alembic upgrade head`)** before a new web version takes traffic
(see `backend/railway.toml`). Run them against **staging first**.

- `ALEMBIC_DATABASE_URL` must be the Supabase **direct** endpoint (`:5432`), transactional DDL
  needs a real session, which the transaction mode pooler can't give.
- `DATABASE_URL` (runtime) is the Supabase **pooler** endpoint (`:6543`).

New migration: `alembic revision -m "..."` → edit → `alembic upgrade head` locally → commit.

---

## 2. Railway services (all from this repo, root directory = `backend/`)

| Service | Config | Start | Notes |
|---------|--------|-------|-------|
| **web** | `backend/railway.toml` (default config path) | `uvicorn main:app --host 0.0.0.0 --port $PORT` | **2 replicas**; `preDeployCommand = alembic upgrade head`; healthcheck `/health`. |
| **worker** | set Config Path → `backend/railway.worker.toml` | `python -m worker.ingest` | **Cron `0 */8 * * *`**; run to exit; no replicas. |
| **Redis** | Railway Redis plugin |, | Injects `REDIS_URL` into web + worker. |

Both web + worker use the same `backend/Dockerfile`. The multireplica web is only correct
because the guard + Sonnet governor are now **Redis backed** (`lib/redis_client.py`), do NOT
run >1 replica without `REDIS_URL` set (it would degrade to per replica limits, looser but not
broken; still, set Redis).

---

## 3. Environment variables (per Railway environment, never committed)

**Required (backend, both services):**
- `DATABASE_URL`: Supabase pooler (`:6543`).
- `ALEMBIC_DATABASE_URL`: Supabase direct (`:5432`).
- `REDIS_URL`: Railway injected.
- `ANTHROPIC_API_KEY`, `VOYAGE_API_KEY`, `FIRECRAWL_API_KEY`, `LINKDAPI_KEY`.
- `LOGODEV_SECRET_KEY` (`sk_…`) + `LOGODEV_PUBLISHABLE_KEY` (`pk_…`), company logo resolution in
  the **worker** parse pass (Brand Search → domain → `img.logo.dev`). FREE (logo.dev, 500k/mo).
  Optional but **must be set on the worker service**: without the secret key, uncurated company
  names resolve to a letter avatar instead of a real logo. Logos are resolved once at ingestion
  and stored (`lib/logo_resolver`); a null is self healed on the next run (`logo_backfill_pass`).
- `USE_MOCKS=false` (prod safety, never ship mocks).
- `CORS_ORIGINS=https://app.<domain>` (the web service).
- `SPEND_CAP_USD_DAILY=32` (app graceful-503 below the $50 Anthropic hard cap).
- `ADMIN_TOKEN`: for `/admin/*`.

**Auth + abuse (turns the gate ON, see [routes.md](routes.md#auth--per-user-quota-gate-libauthpy--optional)):**
- `SUPABASE_URL` (**backend only**). The real switch: enables JWKS verification of the
  project's ES256 user session tokens. (`SUPABASE_JWT_SECRET` is a legacy HS256 *fallback*
  that verifies the anon/service keys but NOT modern user logins.) Optional `SUPABASE_JWT_AUD`/`_ALG`/`SUPABASE_JWKS_TIMEOUT_SEC`.
- `QUOTA_MATCHER_PER_DAY=20`, `QUOTA_ANALYSIS_PER_DAY=5`.
- `TURNSTILE_SECRET` (**backend only**).
- `SUPABASE_SERVICE_ROLE_KEY` (**backend only**, admin scoped): used ONLY by `DELETE /account`
  to hard delete the Supabase auth user. Unset → deletion still erases all app side data but
  leaves the auth user for manual cleanup. **Never expose to the browser.**

**Observability:** `SENTRY_DSN`, `SENTRY_TRACES_SAMPLE_RATE=0.1`, `ENVIRONMENT=staging|production`.

**Tuning (optional, code defaults shown in `.env.example`):** `SONNET_MAX_CONCURRENCY`,
`DB_POOL_MAX`, `RATE_LIMIT_*`, `SERVE_MAX_AGE_HOURS`, `WORKER_SPEND_CAP_USD_DAILY`
(ingestion's own spend bucket, excluded from the user kill switch; set it on the **worker**
service), etc.

**Frontend (Vercel, per environment):**
- `NEXT_PUBLIC_API_URL=https://api.<domain>`
- `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY` (the `anon` key is the only
  Supabase secret the client may hold).
- `NEXT_PUBLIC_AUTH_REQUIRED=true`: flip the gates ON in prod (default off = sign in
  available but not enforced). Set together with the backend `SUPABASE_URL`.
- `NEXT_PUBLIC_TURNSTILE_SITE_KEY`.

> **CRITICAL:** Supabase **`service_role` key + JWT secret are backend only**. The browser
> gets only the project URL + `anon` key. Never expose them via `NEXT_PUBLIC_*`.

---

## 4. CI / deploy flow

- **CI gate** = `.github/workflows/ci.yml` (backend: `compileall` + `import main`; frontend:
  `tsc --noEmit`). Make it a **required status check**; configure Railway/Vercel to wait for it.
- **`main` auto deploys to STAGING.** Smoke test staging, then **manually promote to prod**
  (Railway: redeploy the prod environment from the same commit; Vercel: promote the build).
- Migrations run automatically via `preDeployCommand` (staging first by virtue of the flow).

---

## 5. Prelaunch checklist

- [ ] `alembic upgrade head` clean on staging + prod (currently at `0002_auth_tables`).
- [ ] Worker has run ≥1 pass per environment (national buckets empty until it does).
- [ ] `USE_MOCKS=false` in prod; `CORS_ORIGINS` set to the real frontend origin.
- [ ] Auth verified end to end on staging (magic link → token → `/analyze/batch` 200; anon → 401).
- [ ] Turnstile verified on staging; Cloudflare proxying `api.<domain>`.
- [ ] Anthropic Console **$50/day** cap set; app `SPEND_CAP_USD_DAILY=32`; spend alert at ~50%.
- [ ] Supabase **daily backups on + a tested restore** (verify the restore, not just that backups exist).
- [ ] Sentry receiving events from both environments.
- [ ] One **load test** vs staging (k6/locust), validates 2 replicas + the Redis Sonnet governor under concurrency.
- [ ] `/admin/killswitch` + `/admin/status` reachable with `ADMIN_TOKEN`.
- [ ] Privacy policy + ToS + data retention + account deletion path published (PII/accounts).
      _Code DONE (M10): `/privacy` + `/terms` pages (TEMPLATES, legal to finalize the text),
      `/account` page, and `DELETE /account` (set `SUPABASE_SERVICE_ROLE_KEY` for full auth user
      delete). Remaining: counsel finalizes the legal copy + contact emails._

## 6. Known accepted risks

- **LinkedIn / LinkdAPI scraping** ToS exposure, launched as is (explicit call; see brainstorm Q15).
- **Worker LLM spend isolation (M5), DONE.** The worker's Haiku parse pass spend is tracked
  in `cost_events` under a `worker:ingest` `cost_session`, which the user facing kill switch
  (`sum_spend_since`) **excludes**, ingestion can never trip the user 503. It has its own
  soft cap (`WORKER_SPEND_CAP_USD_DAILY`, default in `.env.example` = $5; 0 disables),
  enforced inside `parse_pass()`. Set it per Railway environment.
