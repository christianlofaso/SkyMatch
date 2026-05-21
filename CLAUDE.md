# Pathfinder — CLAUDE.md

Career discovery tool: paste a LinkedIn profile URL or raw text and get 10 warm connection recommendations + personalized internship listings across 4 buckets.

---

## Architecture

```
frontend (Next.js 14)  →  POST /run  →  backend (FastAPI)
                                              ├── /profile/analyze    (Claude)
                                              ├── /connections/suggest (LinkdAPI + Claude)
                                              └── /internships/search  (Claude + ATS APIs + DDG)
```

**Backend stack:** Python 3.12, FastAPI, Anthropic SDK (`claude-opus-4-5`), httpx (async HTTP), LinkdAPI, DuckDuckGo (`ddgs`), SQLite (caching), Pydantic v2

**Frontend stack:** Next.js 14 App Router, React 18, TypeScript, Tailwind CSS, Zod (runtime validation)

---

## Running the project

### Backend
```
cd backend
py -3.12 -m venv venv          # first time only
venv\Scripts\activate
pip install -r requirements.txt  # first time only
uvicorn main:app --reload --port 8000
```

### Frontend
```
cd frontend
npm install    # first time only
npm run dev    # runs on http://localhost:3000
```

### Environment
Copy `.env.example` to `.env` in `backend/` and fill in:
```
ANTHROPIC_API_KEY=...   # Claude API (required)
LINKDAPI_KEY=...        # LinkdAPI key (required)
USE_MOCKS=true          # Return hardcoded mock data — set false for real calls
```

Frontend env (optional, defaults to localhost:8000):
```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

## Project structure

```
pathfinder/
├── CLAUDE.md
├── backend/
│   ├── main.py                  # FastAPI app + CORS + router registration + init_db()
│   ├── schemas.py               # All Pydantic models (single source of truth for data shapes)
│   ├── linkd.py                 # Async LinkdAPI client
│   ├── cache.py                 # SQLite caching helpers (5 tables, per-table TTLs)
│   ├── requirements.txt
│   ├── .env                     # DO NOT COMMIT — real API keys
│   ├── .env.example
│   ├── pathfinder_cache.db      # Auto-created on startup; safe to delete to reset
│   ├── mocks/
│   │   └── run_response.json    # Hardcoded response (Marcus Chen) used when USE_MOCKS=true
│   └── routes/
│       ├── run.py               # POST /run — orchestrator
│       ├── profile.py           # POST /profile/analyze — Claude extraction
│       ├── connections.py       # POST /connections/suggest — LinkdAPI + Claude
│       └── internships.py       # POST /internships/search — Claude + URL validation
└── frontend/
    ├── package.json
    ├── tailwind.config.ts
    └── src/
        ├── app/
        │   ├── layout.tsx           # IBM Plex Mono + Inter fonts, metadata
        │   ├── globals.css          # CSS variables (dark theme, commonality colors)
        │   ├── page.tsx             # Home — URL/text input, two tabs, submit
        │   └── results/[id]/
        │       └── page.tsx         # Results — reads sessionStorage, renders 3 sections
        ├── components/
        │   ├── ProfileCard.tsx      # Name, headline, school, skills, key values
        │   ├── ConnectionCard.tsx   # Name, title, commonality bar, why_relevant
        │   ├── InternshipCard.tsx   # Title, fit_explanation, reach_gap, Apply link
        │   └── BucketSection.tsx    # Bucket header + grid of InternshipCards
        ├── lib/
        │   └── api.ts               # runPathfinder() — POST /run, validates with Zod
        └── types/
            └── pathfinder.ts        # Zod schemas + inferred TS types (source of truth)
```

---

## Data models

Defined in `backend/schemas.py` (Pydantic) and mirrored in `frontend/src/types/pathfinder.ts` (Zod). **Keep both in sync when adding fields.**

### ProfileAnalysis
```python
full_name: str
headline: str
location: str
school: str
graduation_year: int | None
major: str | None
fraternity_or_orgs: list[str]
past_companies: list[str]
current_company: str | None
technical_skills: list[str]
field_of_interest: str
key_values: list[str]          # 3-5 noun phrases, Claude-extracted
```

### Connection
```python
name: str
title: str
company: str
linkedin_url: str
commonality_type: Literal["fraternity", "school", "past_company", "field", "major"]
commonality_detail: str        # specific, e.g. "UIUC ECE Class of 2022, also Phi Delt"
why_relevant: str              # one sentence
```

### Internship
```python
title: str
company: str
location: str
company_description: str       # one factual sentence
fit_explanation: str           # must reference specific profile fields
application_url: str | None    # null until URL-finding step; stays null if no valid URL found
bucket: Literal["local", "big_tech", "startup", "reach"]
reach_gap: str | None          # only set for reach bucket
```

### InternshipBuckets
```python
local: list[Internship]        # max 5 after validation
big_tech: list[Internship]     # max 5
startup: list[Internship]      # max 5
reach: list[Internship]        # max 5
```

---

## API endpoints

| Method | Path | Request | Response |
|--------|------|---------|----------|
| POST | `/run` | `{url?, text?}` | `RunResponse` |
| POST | `/profile/analyze` | `{url?, text?}` | `ProfileAnalysis` |
| POST | `/connections/suggest` | `ProfileAnalysis` | `list[Connection]` (10) |
| POST | `/internships/search` | `ProfileAnalysis` | `InternshipBuckets` |
| GET | `/health` | — | `{"status": "ok"}` |

`RunRequest` requires at least one of `url` or `text`.

---

## Route details

### `routes/run.py` — POST /run
Orchestrator: calls `analyze_profile` then fans out to `suggest_connections` + `search_internships` in parallel.

Run cache is **disabled during development** (commented out). Re-enable by uncommenting the `get_run_cache` / `set_run_cache` calls before shipping.

`USE_MOCKS=true` skips all API calls and returns `mocks/run_response.json`.

### `routes/profile.py` — POST /profile/analyze
Extracts `ProfileAnalysis` from raw LinkedIn data using Claude. If a `url` is provided, fetches profile via `LinkdClient.get_profile()` first. Result is cached permanently (no TTL) keyed by URL or text hash.

Claude call: `claude-opus-4-5`, max 1024 tokens.

### `routes/connections.py` — POST /connections/suggest
Runs 3-5 parallel LinkdAPI `search_people` queries using different keyword combinations:
- Frat + school (up to 3 frats)
- Past company + school (up to 2 companies)
- School + field
- School + major

Deduplicates by `linkedin_url`, takes up to 15 candidates, sends to Claude.
Claude returns exactly 10 `Connection` objects. People-search results cached 7 days.

Key debugging: if Claude returns empty response, check for JSON truncation (candidates × fields exceeding `max_tokens=3000`). The 15-candidate cap exists specifically to prevent this.

### `routes/internships.py` — POST /internships/search
Most complex route. Two parallel Claude calls after a DDG scrape:

**Startup bucket (search-first):**
1. `_scrape_startup_listings(profile)` — 6 concurrent DDG `site:workatastartup.com` / `site:wellfound.com/jobs` queries, returns up to 30 real listings with numeric job IDs in URLs
2. `_generate_startup_internships_sync(profile, listings)` — separate Claude call using `STARTUP_SYSTEM`, Claude picks best matches and writes fit explanations, copies URLs verbatim

**All other buckets (Claude-generates → URL-find → validate):**
1. Main Claude call using `INTERNSHIPS_SYSTEM` generates local, big_tech, reach candidates (startup skipped via `_SKIP_STARTUP_ADDENDUM` when real listings exist)
2. URL-finding: `_find_via_ats()` (Greenhouse/Lever/Ashby public APIs) → `_find_job_url()` (DuckDuckGo)
3. Validation: 6-rule DROP POLICY

Both Claude calls run in parallel via `asyncio.to_thread` (the Anthropic SDK is synchronous).

---

## URL validation DROP POLICY

Defined in `validate_job_url()` in `routes/internships.py`. Rules checked in order, cheapest first:

1. **No URL** → `no_url` (no HTTP call)
2. **Generic URL pattern** → various reasons (`no_job_id_in_url`, `careers_subdomain_root`, `application_form_url`, etc.) — no HTTP call
3. **HTTP status ≥ 400** → `http_404` etc.
4. **Redirects to generic URL** → `redirect_to_{reason}`
5. **Closed listing string in body** → `closed: {string}` (see `CLOSED_STRINGS`)
6. **Title tokens not found in body** → `title_not_found` (requires ≥70% of title tokens)

**Key rule:** any URL without a 5+ digit number or UUID in the path fails rule 2 as `no_job_id_in_url`. This is enforced by `_JOB_ID_RE`. Real ATS listing URLs always contain job IDs; generic careers pages and university landing pages do not.

Results cached for **24 hours** in `url_validation_cache`.

**Important constants:**
```python
_PROPRIETARY_ATS = {"google", "meta", "apple", "microsoft", "amazon", "netflix", "tesla", "linkedin"}
# These companies don't have Greenhouse/Lever/Ashby boards; skip ATS lookup entirely.

BLOCKED_DOMAINS = ["linkedin.com", "facebook.com", "twitter.com", "instagram.com"]
# DuckDuckGo results from these domains are always skipped.
```

---

## Caching

All caching is in `cache.py` using `pathfinder_cache.db` (SQLite, auto-created).

| Table | Key | TTL | Stores |
|-------|-----|-----|--------|
| `profile_cache` | `linkedin_url` | None | `ProfileAnalysis` dict |
| `people_search_cache` | `filter_hash` | 7 days | list of LinkedIn people results |
| `jobs_search_cache` | `filter_hash` | 1 day | list of LinkedIn job results |
| `run_cache` | `url` | 1 day | `RunResponse` dict (disabled in dev) |
| `url_validation_cache` | `url` | 1 day | `{"is_valid": bool, "reason": str}` |

**All tables use a single `data TEXT NOT NULL` column** (JSON-serialized). The generic `_get`/`_set` helpers always select `data, created_at` — never add separate columns to a cache table or the helpers will break with `no such column: data`.

**To clear a cache table** (e.g. after changing validation logic):
```
py -3.12 -c "import sqlite3; conn=sqlite3.connect(r'C:\Users\chris\Desktop\pathfinder\backend\pathfinder_cache.db'); conn.execute('DELETE FROM url_validation_cache'); conn.commit(); conn.close(); print('cleared')"
```

**To fully reset:** delete `pathfinder_cache.db`. It recreates on next server start.

---

## Frontend patterns

### Theme
All colors are CSS variables in `globals.css`. Never hardcode colors in components — always use `var(--accent)`, `var(--border)`, etc. The full palette:
- `--bg` `--surface` `--border` — backgrounds
- `--text-primary` `--text-secondary` — text
- `--accent` `--accent-dim` — interactive blue
- `--color-fraternity` `--color-school` `--color-past_company` `--color-field` `--color-major` — commonality bar colors

### Fonts
- Body: Inter (`font-sans` in Tailwind / default body)
- Monospace: IBM Plex Mono (applied via `.mono` utility class in globals.css)

### Data flow
Home page → `runPathfinder()` in `lib/api.ts` → result stored in `sessionStorage` by timestamp key → navigate to `/results/{timestamp}` → results page reads from `sessionStorage`, validates with Zod, renders.

No server-side state. If the user refreshes the results page with an expired session, they see an error and a back button.

### Type safety
`src/types/pathfinder.ts` is the **single source of truth** for frontend types. Zod schemas validate at the API boundary in `lib/api.ts`. TypeScript types are inferred from the schemas (`z.infer<typeof ...>`). When the backend schema changes, update both `schemas.py` and `pathfinder.ts`.

---

## Logging conventions (backend)

All routes print structured logs with a bracketed prefix. Look for these in the uvicorn terminal:

```
[profile] ...           # Profile extraction
[connections] ...       # Connection search and Claude call
[ats] greenhouse ...    # ATS API hit (slug + URL found)
[startup-listings] ...  # DDG scrape results count
[startup-claude] ...    # Startup Claude call result
[internships] ...       # Main Claude call response
[startup-boards] ...    # Legacy per-company DDG search (still used for fallback)
[validate] ...          # Per-URL validation result (PASS/DROP + reason)
[validate-summary] ...  # Per-bucket summary (candidates / passed / dropped)
[validate] WARNING ...  # Fewer than 3 passed in a bucket
```

---

## Common development tasks

### Adding a field to the profile
1. Add to `ProfileAnalysis` in `backend/schemas.py`
2. Update the Claude system prompt in `backend/routes/profile.py` to extract it
3. Add to `ProfileAnalysisSchema` in `frontend/src/types/pathfinder.ts`
4. Update any component that should display it (likely `ProfileCard.tsx`)

### Adding a new internship bucket
1. Add to `Literal[...]` in `Internship.bucket` in `schemas.py`
2. Add to `InternshipBuckets` in `schemas.py`
3. Update `InternshipBucketsSchema` in `pathfinder.ts`
4. Add to `all_items` dict in `search_internships()` in `internships.py`
5. Add `BucketSection` render in `results/[id]/page.tsx`

### Adding a new closed-listing pattern
Add to `CLOSED_STRINGS` in `routes/internships.py`, then clear `url_validation_cache` so already-cached results get re-evaluated.

### Changing the number of results shown per bucket
The cap is `[:5]` in the validation loop in `search_internships()` and enforced by `InternshipBuckets` validators. Change both places.

### Bypassing URL validation for testing
Set `USE_MOCKS=true` to skip all API calls entirely. To test just the Claude output without URL validation, temporarily comment out the validation loop and return `InternshipBuckets(**all_items)` directly.

---

## Known constraints and gotchas

- **`ai.messages.create` is synchronous.** Always wrap in `asyncio.to_thread()` if you need to run it alongside other async work. Calling it directly in an `async def` blocks the entire event loop.

- **DDGS is synchronous and not thread-safe.** Each `asyncio.to_thread` call that uses DDGS must instantiate its own `DDGS()` object. Never share a DDGS instance across threads.

- **`max_tokens` budget.** The main internships Claude call uses 8192 tokens. At 10 candidates per bucket × 4 buckets × ~80 tokens per item, you're around 3200 tokens of output. Don't increase candidates per bucket above 10 without bumping `max_tokens` or you risk JSON truncation mid-object.

- **Wellfound blocks GET requests.** The URL validation body check (rule 6) often fails for `wellfound.com` because they return a login wall to headless clients. Wellfound URLs will often drop on `title_not_found` or `get_failed`. `workatastartup.com` is accessible.

- **The run cache is disabled.** `routes/run.py` has `get_run_cache` / `set_run_cache` calls commented out. Re-enable before any production deployment.

- **CORS is localhost-only.** `main.py` allows `http://localhost:3000` only. Update `allow_origins` before deploying.

- **SessionStorage is ephemeral.** Results disappear on tab close. Not a bug, by design for now.
