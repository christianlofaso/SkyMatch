# Load test (M9)

Validates the production shape under concurrency: the **2-replica** web service, the
**Redis backed guard** (per IP rate + concurrency limiter), and the **org wide Sonnet
governor** (`SONNET_MAX_CONCURRENCY`) holding across replicas. Run it against **staging**,
never prod.

Built on [Locust](https://locust.io/) (Python, fits the backend venv; no extra binary).

## Install (one time, into the backend venv)

```
cd backend
venv\Scripts\activate
pip install -r loadtest/requirements-loadtest.txt
```

Kept out of `requirements.txt` on purpose, so load test deps never ship in the prod image.

## Scenarios (choose cost with `--tags`)

| `--tags`    | Endpoint                 | LLM cost | What it validates |
|-------------|--------------------------|----------|-------------------|
| `smoke`     | `GET /health`            | none     | LB / routing across both replicas, health |
| `serve`     | `POST /internships/search` | none   | Replicas + Postgres pool + embedding rank under load (zero LLM serve path) |
| `guard`     | `POST /internships/search` (no wait) | none | Per IP rate limiter returns clean **429** (not 5xx) under burst |
| `governor`  | `POST /analyze` (full)   | **REAL $** | `SONNET_MAX_CONCURRENCY` cap holds across replicas, **paid Sonnet + Opus** |

**Default (no `--tags`)** runs `smoke` + `serve` + `guard`, everything except the paid
`governor` scenario, so an accidental run never burns Anthropic budget.

`429` (rate limited) and `503` (kill switch / spend cap) are **expected** under load and are
counted as successes; only unexpected statuses fail the run.

## Run

Headless example, free scenarios against staging, 50 users, 5/s ramp, 2 min:

```
locust -f loadtest/locustfile.py \
  --host https://api-staging.<domain> \
  --headless -u 50 -r 5 -t 2m \
  --tags smoke serve
```

Web UI (interactive ramp + charts): drop `--headless` and open http://localhost:8089.

### Validating the rate limiter (`guard`)

Run with many users and a high spawn rate so one host's request rate exceeds
`RATE_LIMIT_PER_MIN`; confirm the excess returns `429` and the service stays healthy:

```
locust -f loadtest/locustfile.py --host https://api-staging.<domain> \
  --headless -u 200 -r 50 -t 1m --tags guard
```

### Validating throughput (`serve`)

The per IP limiter will cap a single host run fast. To measure real serve throughput,
**temporarily raise `RATE_LIMIT_PER_MIN` / `RATE_LIMIT_CONCURRENT` on the staging web
service** (or run distributed Locust workers across hosts), then run `--tags serve`.

### Validating the Sonnet governor (`governor`), costs money

1. Sign in to the staging frontend, grab the Supabase access token (JWT).
2. Export it (and a Turnstile token if `TURNSTILE_SECRET` is set on staging):
   ```
   set PF_AUTH_TOKEN=eyJ...           &  :: Windows
   set PF_TURNSTILE_TOKEN=...
   ```
3. Run a modest concurrency (the governor caps in flight Sonnet at `SONNET_MAX_CONCURRENCY`,
   default 6, you want enough VUs to exceed that):
   ```
   locust -f loadtest/locustfile.py --host https://api-staging.<domain> \
     --headless -u 20 -r 5 -t 2m --tags governor
   ```
4. Watch the staging logs: Sonnet calls should queue at the governor (never exceeding the
   cap concurrently across both replicas), and `GET /cost/summary` / the spend cap should
   track the spend. Stop early if spend climbs unexpectedly.

## Env vars

| Var | Purpose |
|-----|---------|
| `PF_AUTH_TOKEN` | Bearer token (Supabase user JWT) for the `governor` scenario |
| `PF_TURNSTILE_TOKEN` | `X-Turnstile-Token` value, if Turnstile is enabled on the target |

## Sanity check the file without firing traffic

```
locust -f loadtest/locustfile.py --host http://localhost:8000 --list
```
Lists the user class + tasks if the file parses under Locust.
