# Logging conventions (backend)

```
[error] ...             # Unhandled exception caught by the global handler (main.py), "[error] unhandled {METHOD} {path}: {exc!r}" + traceback, then a clean 500 to the client
[serve] ...             # Internship serving, index sizes, ranking, freshness fallback, and skipped-malformed-row notices
[ingest] ...            # Worker run + bounded-DDG-query bail notices
[profile] ...           # Profile extraction + rich fields
[profile/from-resume]   # Resume upload: chars extracted, file name
[connections] ...       # Connection search and Claude call
[ats] greenhouse ...    # ATS API hit (slug + URL found)
[startup-listings] ...  # DDG scrape results (startup)
[bigtech-listings] ...  # DDG scrape results (big_tech)
[local-listings] ...    # DDG scrape results (local) + city used
[startup-claude] ...    # Startup Claude call result
[bigtech-claude] ...    # Big-tech Claude call result
[local-claude] ...      # Local Claude call result
[internships] ...       # Main Claude call response (reach + fallbacks)
[validate] ...          # Per-URL validation result (PASS/DROP + reason)
[validate-summary] ...  # Per-bucket summary (candidates / passed / dropped)
[analyze] ...           # Job-fit pipeline, fetch path, extraction status, step A/B counts
[profile-rich] ...      # Rich field extraction counts (skills, work entries, projects)
[timing] ...            # Per-stage wall-clock; ends with "[timing] ===== /run: total Nms =====" sorted breakdown
```

**Global error handler:** `main.py` registers `@app.exception_handler(Exception)` as a backstop, any unhandled exception that escapes a route logs `[error] unhandled …` + a full `traceback.print_exc()` and returns a clean `500 {"detail": "Something went wrong on our end. Please try again."}` (no raw exception text leaks). FastAPI's built-in `HTTPException` / `RequestValidationError` handlers run first and never reach it; the streaming routes carry their own per-job envelopes. It has a `# SENTRY:` hook comment for when a DSN is wired (deferred). Logging stays `print()`-based (host captures stdout in prod).

**Timing/observability:** `backend/lib/timing.py` provides `timing_session(name)` (collects spans, prints a sorted % breakdown on exit), `timed(label)` (async ctx mgr), and `timed_call(label, coro)` (await a coro under a span, handy inside `asyncio.gather`). `/run` is wrapped in a session; profile, connections (search + claude), and internships (`/1` scrapes → `/2` claude calls → `/3` url-finding → `/4` validation, each sub-timed) all emit spans. Parallel spans overlap, so per-span ms sum to more than the session total, the **total is the real latency**; the % is each branch's share of wall-clock.

Key `[analyze]` and `[batch]` log lines:
```
[analyze] site_handler:microsoft success (N chars)
[analyze] direct fetch succeeded (N chars)
[analyze] direct fetch returned N chars (JS shell), trying Firecrawl
[analyze] direct fetch returned N chars (too large, SPA/search page), trying Firecrawl
[analyze] Firecrawl basic: extraction=YES (N reqs), markdown=N chars
[analyze] fetch path=firecrawl_basic json_extracted=True
[analyze] job_id=url:https://...
[analyze] user_cache=hit/miss mode=quick|full key=...
[analyze] requirements_cache=hit/miss job=...
[analyze] extracted N requirements from job listing
[analyze] quick: fit=N verdict=apply_now
[analyze] step B: N matches, N gaps, verdict=apply_now
[analyze] full headline reconciled from quick cache: full-computed=N/X -> quick=N/X
[analyze] self-healing stale full cache: N/X -> N/X
[analyze] no quick cache for this job_id; full headline unreconciled
[analyze] roadmap attempt N: dropped K/M URLs
[analyze] roadmap: K items under 2 valid resources; retrying
[analyze] roadmap generation failed: <exc>
[analyze] project_suggestion failed: <exc>
[analyze] phase3 backfill: roadmap=yes|no project=yes|no
[analyze/stream] job_id=... | user_cache=hit/miss | step B: N matches, N gaps, verdict=...
[analyze/stream] roadmap|project generation failed: <exc>
[run/stream] unexpected error resolving profile: <exc>
[batch] user_cache=hit key=...
[batch] job[i] failed code=FETCH_FAILED msg=...
```

**Streaming-endpoint session names:** the four ndjson streamers open their `timing_session`/`cost_session` INSIDE the generator (so spend + timing are captured after the route returns). Session names: `/analyze/batch (N jobs)`, `/internships/annotate (N jobs)`, `/run/stream`, and, for `/analyze/stream`, **two** sessions: `"/analyze/stream prelude"` (extract + match spend, runs before the StreamingResponse) and `"/analyze/stream phase3"` (roadmap + project spend, inside the generator). So a single `/analyze/stream` request prints **two `[cost]` ledgers** by design, a single `with` can't straddle the route's `return` of the StreamingResponse.

Frontend console (from `/results/[id]`):
```
[results] all N cards cached, skipping batch
[results] N/M cards cached, fetching K
```
