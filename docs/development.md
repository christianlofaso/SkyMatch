# Common development tasks

## Adding a field to the profile
1. Add to `ProfileAnalysis` in `backend/schemas.py`
2. Update Claude system prompt in `backend/routes/profile.py`
3. Add to `ProfileAnalysisSchema` in `frontend/src/types/pathfinder.ts`
4. Update `ProfileCard.tsx` if it should be displayed

## Adding a field to UnifiedProfile only
1. Add to `UnifiedProfile` in `backend/schemas.py`
2. Update `rich_profile_extraction.txt` prompt if it's a rich extracted field
3. Update `extract_rich_fields()` return dict
4. Update frontend Zod schema in `pathfinder.ts`

## Adding a new site handler (preferred for SPA career portals)
Vendor career platforms (Microsoft, Workday, SuccessFactors, iCIMS) that hide job
data behind a SPA but expose it via a JSON API or embedded JSON-LD get a per-domain
handler under `backend/site_handlers/`. The dispatcher runs as Attempt 0 in
`_fetch_job_content()`, before httpx/Firecrawl.

1. Create `backend/site_handlers/<vendor>.py` defining a class with:
   - `name: str`
   - `matches(self, url: str) -> bool`
   - `async def fetch(self, url: str) -> JobPosting | None`
2. At the module bottom: `register(VendorHandler())`
3. Import the module from `backend/site_handlers/__init__.py`
4. Returning `None` from `fetch()` falls through to httpx/Firecrawl — only return a
   `JobPosting` when you have a real title + description.

`backend/site_handlers/microsoft.py` is the reference (parses schema.org JSON-LD
out of the static HTML).

## Adding a new SPA portal early-exit (last resort)
Only use this when no site_handler is feasible — it's a hard 422 with paste instructions.
Add to `_SPA_SEARCH_PORTALS` in `routes/analyze.py`:
```python
_SPA_SEARCH_PORTALS["careers.example.com"] = "Site-specific paste instructions here."
```

## Adding a new internship bucket
1. Add to `Literal[...]` in `Internship.bucket` in `schemas.py`
2. Add to `InternshipBuckets` in `schemas.py`
3. Update `InternshipBucketsSchema` in `pathfinder.ts`
4. In `search_internships()` in `internships.py`: read the bucket's rows from the index (see the national/reach/local `get_listings` reads), add it to the `pools` dict, and add it to the `InternshipBuckets(...)` construction (`_select_and_build` handles the rest). Wire its index source in `worker/ingest.py` + `config/niches.py`.
5. Add `BucketSection` render in `results/[id]/page.tsx` (and to the `BUCKETS` array there)

## Adding a new closed-listing pattern
Add to `CLOSED_STRINGS` in `routes/internships.py`, then clear `url_validation_cache`.

## Tuning fit score weights
Edit `CATEGORY_WEIGHTS` in `routes/analyze.py`. Note: `"soft"` is intentionally absent — it appears in `category_scores` but is excluded from the weighted `fit_score`.

## Adding a new model constant
Add to `backend/config/models.py` and import from there. Don't inline model strings. So far only `analyze.py` has migrated to these constants — `connections.py`, `internships.py`, `profile.py` still inline `claude-opus-4-8` and will migrate in a follow-up.

## Adding a learning-resource domain to the roadmap allowlist
1. Edit `ALLOWED_DOMAINS` in `backend/config/resource_allowlist.py` (add the bare host, e.g. `"educative.io"`). Suffix matching means subdomains are accepted automatically.
2. Update the inline domain list in `backend/prompts/roadmap.txt` (under RULES — point 7) so the LLM knows it's allowed. The server is still the final authority via `is_allowlisted()`, but hinting reduces wasted retries.
3. Clear the `url_liveness_cache` table if URLs from the new domain were previously HEAD-rejected and need re-checking: `DELETE FROM url_liveness_cache`.

## Adjusting Phase 3 retry budget or item caps
- Roadmap retry count: `_ROADMAP_MAX_RETRIES` near the top of `routes/analyze.py` (default 2 additional attempts on top of the initial call).
- Items cap (currently 5) and resources-per-item cap (currently 4) are slice constants in `_run_roadmap` — search for `[:5]` and `[:4]`.
- HEAD timeout: `_HEAD_TIMEOUT_SECONDS` in `backend/lib/resource_validation.py` (default 3.0). Increasing it slows worst-case full-mode latency.

## Adjusting batch concurrency or size caps
Edit `_BATCH_LLM_CONCURRENCY` (in-flight LLM calls, default 8) or `_BATCH_MAX_JOBS` (per-batch ceiling, default 50) near the top of `routes/analyze.py`. The 50-job ceiling is enforced by pydantic `Field(max_length=...)`, not a manual check.

## Forcing a fresh batch on a results page
Open DevTools → Application → Session Storage → `http://localhost:3000` → delete the `analyses:{runId}` row. Reload `/results/{runId}`. Do NOT delete the `{runId}` row (no prefix) — that's the RunResponse the page needs to render.

## Bypassing URL validation for testing
Set `USE_MOCKS=true` to skip all API calls. To test Claude output without URL validation, comment out the validation loop and return `InternshipBuckets(**all_items)` directly.
