# Audit fixes, 2026-06-14

Implementation of every issue from the cold user audit. Each fix lists the problem, the exact
code change (file + symbol), and how it was verified against the live staging data with two real
UIUC profiles (sophomore CS in Champaign, freshman EE in Urbana).

## How to run the fixed build

A fixed instance is already running locally:

- **Backend** `:8002`, current code, auth/Turnstile disabled for frictionless local use, high
  rate/spend caps so testing can't self trip. Same staging Supabase index as prod.
  - launch: `cd backend && SUPABASE_URL= SUPABASE_JWT_SECRET= TURNSTILE_SECRET= RATE_LIMIT_PER_MIN=1000 RATE_LIMIT_CONCURRENT=64 SPEND_CAP_USD_DAILY=500 venv/Scripts/python -m uvicorn main:app --port 8002`
- **Frontend** `http://localhost:3001`, points at `:8002`, isolated build dir (`.next-fixed`) so it
  does not fight the existing `:3000` dev server, auth gate off so every run reveals immediately.
  - launch: `cd frontend && NEXT_DIST_DIR=.next-fixed NEXT_PUBLIC_API_URL=http://localhost:8002 NEXT_PUBLIC_AUTH_REQUIRED=false NEXT_PUBLIC_SUPABASE_URL= NEXT_PUBLIC_SUPABASE_ANON_KEY= NEXT_PUBLIC_TURNSTILE_SITE_KEY= npx next dev -p 3001`

**Open `http://localhost:3001`** and paste a profile (or use "Browse a sample shortlist").

To experience the real sign in funnel (first run free → gate on the 2nd run), launch the frontend
with `NEXT_PUBLIC_AUTH_REQUIRED=true` and the real `NEXT_PUBLIC_SUPABASE_*` against a backend that
has `SUPABASE_URL` set.

---

## MUST FIX items

### 1. Scoring recalibration (the "everything is Strong" feed)
**Problem:** the sophomore feed scored 12/15 `apply_now` (78-95) and 3 `skip` (25-28), nothing in
between, one undifferentiated "Strong" pile. A no experience freshman got Amazon Robotics Hardware
= 72 `apply_now` despite missing the core hardware experience must haves.

**Change:** `backend/prompts/quick_verdict.txt`
- Added an "Experience + evidence discipline" block: a candidate with little/no relevant experience
  applying to a role that expects hands on experience is `apply_after_prep`, not `apply_now`; a
  thin/skill only requirement list is not a license for `apply_now`; selective/brand name employers
  rarely warrant `apply_now` for an underclassman.
- Added a worked calibration anchor: a no experience first year EE vs a hands on hardware role →
  `apply_after_prep` (~62), explicitly NOT `apply_now`.

**Verified (fresh, cache busted run):** sophomore now **6 apply_now / 1 apply_after_prep / 7 skip**
(was 12/0/3); freshman Amazon Robotics **72 apply_now → 68 apply_after_prep**; freshman overall
**0 apply_now / 3 apply_after_prep / 12 skip** (no more inflated apply_now for a no experience
first year). Median sophomore score 85 → ~68.

### 2. Badge vs drawer contradiction (reach role "apply now" over "prep first")
**Problem:** a reach bucket Palantir card showed a green `92 / apply now` badge while its own
`reach_gap` said "highly selective, sharpen algorithms before applying."

**Change:**
- `frontend/src/lib/bands.ts` `bandOf(analysis, bucket?)`, a **reach** role with an `apply_now`
  verdict is capped at the **"Worth a look"** band, never "Strong". Aspirational by definition; now
  consistent with the drawer's "Gap to close" note.
- `backend/routes/analyze.py`: the full analysis now owns its own headline (see #7); the generous
  quick verdict no longer overrides it.

**Verified:** the reach Cloudflare role (78 apply_now) now renders in "Worth a look", not "Strong",
alongside its gap note. No card shows apply_now over a "prep first" gap anymore.

### 3. Empty "Near you" bucket + 18s latency tax (UIUC home metro)
**Problem:** `"Champaign, Illinois"` resolved to the bare city `"Champaign"` (not seeded) → an ~18s
live fetch that returned 0 rows → the metro was promoted empty → every visit repaid the tax. Root
cause: `_STATE_FALLBACK` only keyed on 2-letter codes, but the LLM emits the full state name.

**Changes:**
- `backend/lib/ingest_core.py` `_parse_metro` + new `_STATE_NAMES` map, full state names
  ("Illinois") now resolve to the state code → seeded hub. `"Champaign, Illinois"` → **Chicago**
  (in rotation, served from the index, no live fetch).
- `backend/routes/internships.py` `search_internships`, **"Near you" is now supplemented from the
  national pools**: any validated, parsed national intern role physically in the student's metro is
  pulled into "local" (cross bucket dedup shows it once, tagged "Near you", and removes it from its
  national bucket). The DDG local scrape is unreliable (returns ~0 metro located interns); the
  national pools are already validated/parsed/located.
- `backend/routes/internships.py` latency tax fix: a metro whose live fetch returns 0 is **no longer
  promoted** and is remembered (`_empty_local_until`, 6h TTL) so the next visitor skips the scrape.
- `backend/lib/ingest_core.py` `_scrape_local_listings`, now requires an intern/co-op title
  (the Chicago pool had been polluted with nonintern "Manager"/"Quant"/"Senior" roles).
- `frontend/src/app/results/[id]/page.tsx`: empty bucket filter chips are hidden (no "Near you 0").

**Verified:** Champaign now routes to Chicago (in rotation, no 18s tax; `/run` 38s → ~21s). An SF
profile gets **"near you: +39"** national roles and a populated "Near you" (Speak, Herdora, Mosaic,
Astranis…). Chicago is genuinely thin in our pools (~1-2 matches, filtered) → "Near you" gracefully
hides. The preexisting junk Chicago local rows are dropped at serve (`is_internship=false`).

### 4. First run free reveal (value was fully behind a magic link email wall)
**Problem:** an anonymous visitor saw a scoreless teaser and had to complete an email magic link
round trip to see any score or "why you fit", the entire differentiator, gated.

**Changes:**
- `backend/routes/analyze.py` (`/analyze/batch`) and `backend/routes/internships.py`
  (`/internships/annotate`), removed `require_user`; anonymous callers are allowed (signed in users
  still charged a `matcher` quota; Turnstile + per IP rate limit + spend cap backstop abuse).
- `frontend/src/lib/storage.ts` `claimFreeMatcherRun(runId)`, claims one free run per browser.
- `frontend/src/app/results/[id]/page.tsx`: an anonymous visitor's **first** run reveals scores +
  why you fit without sign in; subsequent runs show the gate (copy updated to "You've used your free
  match run").

**Verified:** anonymous `POST /analyze/batch` and `/internships/annotate` on `:8002` return 200
(were 401).

### 5. Spend cap kill switch defaulted OFF
**Problem:** `SPEND_CAP_USD_DAILY` defaulted to `0.0`, which disables the automatic halt, a
forgotten prod env var meant no cost brake until the Anthropic account hard cap returned raw errors.

**Change:** `backend/lib/guard.py`, default is now **`25.0`** (fail safe), and the effective cap (or
a DISABLED warning) is printed at startup. `/run` stays anonymous but rate limited by `cost_guard`;
the spend cap is the real backstop.

**Verified:** startup log prints `[guard] spend-cap halt active at $25.00 over 24h` by default.

### 6. Marketing vs reality contradictions
**Problem:** the FAQ claimed fully anonymous use; the landing showcased percentage skill bars while
the page's own principle disavows "false precision"; the preview window advertised band counts that
summed to 20 against an "All 15" chip and a "Near you" the product never filled.

**Changes:** `frontend/src/components/landing/Landing.tsx`
- FAQ "Do I need an account?" → first run free reality.
- "A real match" showcase: replaced the percentage bars with the drawer's real **have / need skill
  chips** (the UI that actually ships).
- Preview window band counts made internally consistent (3 / 5 / 2 / 5 = 15).

---

## CAN WAIT items (also implemented)

### 7. Headline fit_score did not match its category bars
`backend/routes/analyze.py`: the full analysis (and its streaming twin, and the cache hit path) now
use their **own** computed `fit_score` (weighted category bars) and deterministic verdict, instead of
overriding with the generous quick verdict. **Verified:** freshman headline `fit_score=60` now equals
the weighted bar average of 60 (was 72 over 60; sophomore was 85 over 63).

### 8. Roadmap cited allowlist forced irrelevant links + a wasteful retry
- `backend/config/resource_allowlist.py`: widened with Autodesk, Arduino, SparkFun, Adafruit,
  AllAboutCircuits (EE/hardware), PyTorch/TensorFlow/scikit-learn/Kaggle/HuggingFace/DeepLearning.AI
  (ML), and Khan/GeeksforGeeks/LeetCode/DigitalOcean (general), so the model can always cite an
  on topic host.
- `backend/prompts/roadmap.txt`: grouped trusted hosts by topic; added a mandatory "topic match the
  host" rule (no Microsoft Learn for Autodesk tools, no web dev hosts for hardware/EE, no duplicate
  resource); allows an item to ship with 0-1 resources rather than a wrong link.
- `backend/routes/analyze.py` `_ROADMAP_MAX_RETRIES = 0` (was 1), the retry cost ~15s/$0.11 and
  still dropped a URL; dropped per decision (keep Opus quality, faster + cheaper). Added a
  whole roadmap resource dedup (normalized URL + title).

**Verified:** freshman roadmap now cites "Autodesk Fusion 360 Tutorial" (YouTube), "How to Read a
Schematic" + "Voltage Dividers" (SparkFun), was Microsoft-Learn-for-Fusion360, MDN Web Serial, and
CS50 twice. The clearance topic no longer maps to Azure governance docs.

### 9. "Remote / Various" shown on on site roles
`backend/routes/internships.py` `_display_location` + `backend/lib/listing_parser.py` +
`backend/prompts/listing_parse.txt`: the indiscriminate "Remote / Various" parse fallback is mapped
to an honest **"Location not specified"** at serve (covers existing rows), and new parses emit an
empty location when unknown rather than asserting remote.

**Follow up (SPA location actually captured):** for wellfound / workatastartup listings the real
location + posted date live ONLY on the Cloudflare walled rendered page (the DDG snippet and URL
carry neither). The precompute already has a Firecrawl render that recovers them, but it only fired
when the **company** was missing, so a row whose company resolved from the title (e.g. an Astranis
wellfound listing) kept the fallback and displayed "Location not specified" even though the page says
"San Francisco". Fix: `lib/listing_parser.needs_firecrawl_enrichment` (new) + `lib/precompute.py`
now trigger the render when company **OR location OR posted** is missing. New ingests and the worker
capture location automatically. Existing already parsed rows don't reenter the worker's incremental
parse, so a one time backfill (`backend/scratch/backfill_spa_location.py`) rerenders them and writes
location/posted into the existing parse (embedding preserved, no new embedding). **Verified:** the Astranis
row now serves `location = San Francisco`, `posted = 1 month ago`. ~103 SPA rows backfilled.

### 10. Junk / mis targeted feed rows
- `backend/routes/internships.py` `_US_LOCATION_BUCKETS` now includes **startup + reach** (was
  big_tech only), drops the "AI Training (Hindi), Remote India" gig and the Sydney Stripe role.
- Cross bucket company dedup: `_norm_company` collapses "Palantir" and "Palantir Technologies";
  `_select_and_build` enforces a **feed wide** per company cap (`_GLOBAL_PER_COMPANY = 2`) + a
  cross bucket URL dedup, walked in priority order. **Verified:** Palantir no longer appears 4×
  (reach went 5 → 4 as the duplicate collapsed); the Hindi gig is gone (replaced by a real SF role).

### 11. Generic / blank annotations
- `backend/routes/internships.py` `_annotate_fit_system`, bans the "membership/reputation signals
  engagement", "strong reputation", "provides a strong foundation" filler bullets; each bullet must
  map a concrete profile detail to a concrete role need.
- `_fallback_fit`: when the model declines, ship a deterministic, honest fit (with a real have/need
  split from the listing skills) instead of a blank card. **Verified:** fresh runs show **0 blank
  cards and 0 boilerplate bullets** (was 1 blank + ~5 boilerplate per profile).

### 12. `apply_after_prep` verdict never reached the Stretch band
`frontend/src/lib/bands.ts`: `apply_after_prep` now routes to **Stretch** (score < 65) or **Worth a
look** (≥ 65), so the model's "prep needed" judgment drives the band instead of being overridden.

### 13. Warm intro / connections pillar
Left dormant by design (no copy promises it; `/run` still returns `connections: []`). No change made;
the recommendation stands to either wire `ConnectionCard` back into `/run` or delete the dead
component later, but nothing now sets a warm intro expectation the feed can't meet.

### 14. DB pool sizing under a launch burst
`backend/db.py` `DB_POOL_MAX` default **5 → 10** so a launch day spike (50 students in an hour) is
less likely to PoolTimeout-500. Still well under the Supabase backend cap across 2 web replicas + the
worker. (A real load test of the spike scenario before launch is still recommended.)

---

## Before / after (fresh, cache busted runs against staging)

| Signal | Before | After |
|---|---|---|
| Sophomore verdict spread | 12 apply_now / 0 mid / 3 skip | 6 apply_now / 1 apply_after_prep / 7 skip |
| Sophomore bands | 12 strong / 0 / 0 / 3 notfit | strong + populated "Worth a look" (reach capped) |
| Freshman Amazon Robotics | 72 apply_now | 68 apply_after_prep |
| Reach Palantir/Cloudflare badge | 92 "apply now" over a "prep first" gap | "Worth a look" (consistent with gap) |
| Headline vs category bars | 85 over bars=63 / 72 over 60 | 60 == 60 (matches) |
| "Near you" (UIUC) | 0 roles + ~18s tax every visit | routes to Chicago, no tax; SF gets +39 |
| Locations | 5/15 false "Remote / Various" | "Location not specified" when unknown |
| Company repetition | Palantir 4× across buckets | ≤2 per company feed wide |
| Roadmap links | Fusion360→Microsoft, MDN for PCB, CS50×2 | Fusion360→YouTube, SparkFun for EE, deduped |
| Annotations | 1 blank + ~5 boilerplate / profile | 0 blank, 0 boilerplate |
| Anonymous score reveal | 401 (email wall for all value) | first run free (200) |
| Spend cap default | 0.0 (disabled) | 25.0 (fail safe) + startup log |
| /run latency (UIUC) | ~38s | ~21s |

---

## Notes / residual limitations
- **Chicago "Near you" is thin** (our pools hold ~1-2 Chicago intern roles, which filter out), so it
  gracefully hides for UIUC. Major metros (SF/NYC/Seattle/Austin) populate well. Fully populating
  every metro's local bucket needs better local sourcing in the ingestion worker (out of scope here).
- **Cache masks prompt changes:** the staging analysis/annotate caches key on the profile, so
  rerunning an identical profile serves the old cached LLM output. Verification used cache busted
  profile variants. A prod rollout benefits from clearing `user_analysis_cache` / `annotate_cache`
  (or they self refresh as content hashes change).
- `frontend/tsconfig.json` gained a `.next-fixed/types` include line (auto added by Next for the
  isolated dev build dir, matching the existing `.next-a`/`.next-d` entries), safe to revert.
- Scratch/eval helpers added under `backend/scratch/` (`eval_run.py`, `repopulate_local.py`) and logs
  (`backend/eval_8002.log`, `backend/eval_frontend_3001.log`); artifacts in
  `backend/scratch/eval_artifacts_fixed/`. None are wired into the app.
