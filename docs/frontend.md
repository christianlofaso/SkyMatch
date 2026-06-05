# Frontend patterns

## Pages
- **`/` (page.tsx)** — Profile input (URL/paste tabs), resume upload, "find my path →". Shows a **`← last results`** button (top-right) and a **"Previous runs"** list (`components/PreviousRuns.tsx`) of saved runs from `localStorage` (durable across tab close; see `lib/storage.ts`). Each list entry links to `/results/{runId}`; the `×` removes it. Full submission calls `/run`.
- **`/analyze` (analyze/page.tsx)** — Job-fit analyzer form. Accepts a `?url=<encoded>` deeplink: when present (and a profile is in sessionStorage), auto-submits in full mode on first render via a `ref`-guarded effect.
- **`/analyze/[analysisId]`** — Analysis results page. Reads via `getAnalysis(id)` (`localStorage` `pf:analysis:{id}`), renders `VerdictCard` + `BreakdownView`. Nav row: **`← back to results`** (`latestRunId()` from `lib/storage`), `new analysis`, `start over`.
- **`/results/[id]`** — Run results page. Reads `RunResponse` via `getRun(id)` (`localStorage` `pf:run:{runId}`). The `/run` feed is zero-LLM so cards paint instantly; the page then fires **two parallel ndjson streams** on mount over the deduped `application_url` set: **`POST /analyze/batch`** (score badge) and **`POST /internships/annotate`** (the deferred "why you fit" text the feed ships empty). Per-card analyses persist to `pf:analyses:{runId}` and annotations to `pf:annotations:{runId}` so return visits hydrate instantly with no skeleton flash. A score badge that errored (transient fetch/LLM failure) shows a **"retry"** pill → `retryJob(bucket, idx)` re-fires `/analyze/batch` for just that url and fans the result to every slot sharing it. Sort toggle (by fit / by recency) in the section header — client-side reorder, no refetch. Nav row: **`← start over`** + `analyze a job →`.

## Components
- `VerdictCard` — fit score (large number), verdict pill (label + color from `lib/constants.ts`), category breakdown grid, verdict reasoning
- `BreakdownView` — matches (with evidence snippets) + gaps (with severity colors), plus two Phase 3 sections at the bottom: **"Your prep roadmap"** (renders each `RoadmapItem` with skill, priority chip, timeline, why-it-matters, milestone callout, and clickable resource cards with type/duration/cost badges; falls back to `roadmap_note` inline when gaps are empty) and **"Build this to apply"** (project title, pitch, why-this-role, MVP feature list, tech-stack chips, collapsible stretch goals via `useState`, interview-talking-points callout). Resource links open in a new tab.
- `ProfileCard` — name, headline, school, skills, key values
- `ConnectionCard` — name, title, commonality colored bar + detail, why_relevant
- `InternshipCard` — title, company, fit_explanation, reach_gap, Apply link, **plus a `JobAnalysisBadge` slot top-right** (analyzing pulse / score+verdict pill clickable to full / retry on error). `fit_explanation`/`reach_gap` arrive **lazily** via the `annotation` prop (`CardAnnotationState`): a skeleton shows in the "Why you fit" block while it streams, then the text; prefers the streamed annotation, falls back to whatever shipped on the feed.
- `BucketSection` — bucket header + grid of InternshipCards; sorts indices by `sort` prop (`fit` or `recency`)

## Constants and shared helpers
- `lib/constants.ts` is the canonical source for `VERDICT_LABEL` ("Apply Now" / "Worth Prepping" / "Probably Not a Fit"), `VERDICT_COLOR`, and `scoreColor()`. Never inline verdict labels in components.
- `lib/api.ts` exports `analyzeBatch(profile, jobs, signal?)` and `annotateFit(profile, jobs, signal?)` — async generators over `Content-Type: application/x-ndjson`. Pattern: `getReader()` + `TextDecoder({stream:true})` + line split. Each yielded line is schema-validated (`BatchEnvelopeSchema` / `AnnotateEnvelopeSchema`). `annotateFit` jobs are `{url, bucket}`.

## Theme
All colors are CSS variables in `globals.css`. Never hardcode colors — always use `var(--accent)`, `var(--border)`, etc.
- `--bg` `--surface` `--border` — backgrounds
- `--text-primary` `--text-secondary` — text
- `--accent` `--accent-dim` — interactive blue
- `--color-fraternity` `--color-school` `--color-past_company` `--color-field` `--color-major` — commonality bars

## Fonts
- Body: Inter (`font-sans` / default body)
- Monospace: IBM Plex Mono (`.mono` utility class in globals.css)

## Storage (`lib/storage.ts`) — durable run history
All run/analysis persistence is centralized in **`src/lib/storage.ts`**, backed by **`localStorage`** (survives tab close / restart), with Zod-validated reads and SSR guards. Keys are namespaced under `pf:`:

| Key | Stores |
|-----|--------|
| `pf:runs` | Run-history **index**: `{ runId, name, sublabel, savedAt }[]`, newest-first, capped at `MAX_RUNS` (10) |
| `pf:run:{runId}` | Full `RunResponse` |
| `pf:analyses:{runId}` | Per-card quick-analysis cache for a run |
| `pf:annotations:{runId}` | Per-card deferred "why you fit" text (`fit_explanation`/`reach_gap`) for a run |
| `pf:analysis_ids` / `pf:analysis:{id}` | Index + payloads for standalone job analyses, capped at `MAX_ANALYSES` (20) |

Exports: `saveRun`/`getRun`/`listRuns`/`removeRun`/`latestRunId`, `loadAnalyses`/`saveAnalyses`, `loadAnnotations`/`saveAnnotations`, `saveAnalysis`/`getAnalysis`, `timeAgo`, and `RunIndexEntry`/`AnalysesByBucket`/`AnnotationsByBucket`/`BucketKey` types. `saveRun` upserts the index then evicts the oldest run **and its `pf:analyses:` + `pf:annotations:` caches** beyond the cap; writes degrade silently on quota (one prune-and-retry). `savedAt` decodes from the base-36 `runId`.

## Data flow
**Run flow:** `page.tsx` → `runPathfinder()` → `saveRun(runId, result)` → `/results/{runId}` reads via `getRun()`.
**Batch quick-analysis flow:** `/results/{runId}` on mount → `analyzeBatch()` → each envelope writes via `saveAnalyses()` and into per-card React state. Return visits hydrate from storage instantly (no batch refetch).
**Deferred annotation flow:** `/results/{runId}` on mount (parallel to scoring) → `annotateFit()` over the same deduped urls → each envelope writes via `saveAnnotations()` and into per-card annotation state, filling the "Why you fit" blurb. A url is skipped if its card already shipped a non-empty `fit_explanation` (older runs) or is already cached.
**Analyze flow:** card click → `/analyze?url=…` → auto-submit `analyzeJob(profile, {job_url}, "full")` → `saveAnalysis(analysisId, result)` → `/analyze/{analysisId}` reads via `getAnalysis()`. Headline matches the card because full reuses the quick `fit_score` + `verdict.call` from `user_analysis_cache`.
**Resume upload:** `parseResume()` → `POST /profile/from-resume` → returns `{profile_id, profile}` immediately; `profile_id` is passed to `/run` for the full call.

No server-side state — history is per-browser only (no cross-device sync without accounts). Calling `removeRun(runId)` (or the home-page `×`) deletes a run and its `pf:analyses:` + `pf:annotations:` caches; deleting only `pf:analyses:{runId}` / `pf:annotations:{runId}` forces a fresh `/analyze/batch` / `/internships/annotate` on the next visit.

## Type safety
`src/types/pathfinder.ts` is the **single source of truth** for frontend types. Zod schemas validate at API boundary in `lib/api.ts`. When backend schema changes, update both `schemas.py` and `pathfinder.ts`.
