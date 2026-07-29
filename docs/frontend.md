# Frontend patterns

## Pages
- **`/` (page.tsx)**: Profile input (URL/paste tabs), resume upload, "find my path →". Shows a **`← last results`** button (top-right) and a **"Previous runs"** list (`components/PreviousRuns.tsx`) of saved runs from `localStorage` (durable across tab close; see `lib/storage.ts`). Each list entry links to `/results/{runId}`; the `×` removes it. Full submission calls `/run`.
- **`/analyze` (analyze/page.tsx)**: Job-fit analyzer form. Accepts a `?url=<encoded>` deeplink: when present (and a profile is in sessionStorage), auto-submits in full mode on first render via a `ref`-guarded effect.
- **`/analyze/[analysisId]`**: Analysis results page. Reads via `getAnalysis(id)` (`localStorage` `pf:analysis:{id}`), renders `VerdictCard` + `BreakdownView`. Nav row: **`← back to results`** (`latestRunId()` from `lib/storage`), `new analysis`, `start over`.
- **`/results/[id]`**: Run results page. Reads `RunResponse` via `getRun(id)` (`localStorage` `pf:run:{runId}`). The `/run` feed is zero-LLM so cards paint instantly; the page then fires **two parallel ndjson streams** on mount over the deduped `application_url` set: **`POST /analyze/batch`** (score badge) and **`POST /internships/annotate`** (the deferred "why you fit" text the feed ships empty). Per-card analyses persist to `pf:analyses:{runId}` and annotations to `pf:annotations:{runId}` so return visits hydrate instantly with no skeleton flash. A score badge that errored (transient fetch/LLM failure) shows a **"retry"** pill → `retryJob(bucket, idx)` re-fires `/analyze/batch` for just that url and fans the result to every slot sharing it. Sort toggle (by fit / by recency) in the section header, client-side reorder, no refetch. Nav row: **`← start over`** + `analyze a job →`.

## Components
- `VerdictCard`: fit score (large number), verdict pill (label + color from `lib/constants.ts`), category breakdown grid, verdict reasoning
- `BreakdownView`: matches (with evidence snippets) + gaps (with severity colors), plus two Phase 3 sections at the bottom: **"Your prep roadmap"** (renders each `RoadmapItem` with skill, priority chip, timeline, why-it-matters, milestone callout, and clickable resource cards with type/duration/cost badges; falls back to `roadmap_note` inline when gaps are empty) and **"Build this to apply"** (project title, pitch, why-this-role, MVP feature list, tech-stack chips, collapsible stretch goals via `useState`, interview-talking-points callout). Resource links open in a new tab.
- `ProfileCard`: name, headline, school, skills, key values
- `ConnectionCard`: name, title, commonality colored bar + detail, why_relevant
- `InternshipCard`: title, company, fit_explanation, reach_gap, Apply link, **plus a `JobAnalysisBadge` slot top-right** (analyzing pulse / score+verdict pill clickable to full / retry on error). `fit_explanation`/`reach_gap` arrive **lazily** via the `annotation` prop (`CardAnnotationState`): a skeleton shows in the "Why you fit" block while it streams, then the text; prefers the streamed annotation, falls back to whatever shipped on the feed.
- `BucketSection`: bucket header + grid of InternshipCards; sorts indices by `sort` prop (`fit` or `recency`)

## Auth + gating (Supabase magic-link)

OPTIONAL, two-switch design mirroring the backend (`lib/auth.py`):
- **`authConfigured()`** (`lib/supabase.ts`) = `NEXT_PUBLIC_SUPABASE_URL` + `NEXT_PUBLIC_SUPABASE_ANON_KEY` present → the client + sign-in UI exist.
- **`authRequired()`** = `NEXT_PUBLIC_AUTH_REQUIRED === "true"` → the **gates enforce**. Default off, so sign-in is available but not mandatory and the current flow is unchanged (a signed-in session's token is still attached). Flip it on **with** the backend `SUPABASE_JWT_SECRET`.

- **`lib/supabase.ts`**: singleton browser client (`null` when unconfigured) + the two switches.
- **`lib/auth-context.tsx`**: `AuthProvider` (wraps `{children}` in `layout.tsx`) + `useAuth()` → `{ session, user, loading, authConfigured, authRequired, signInWithOtp, signOut }` (via `getSession` + `onAuthStateChange`). Renders a **floating top-right chip** (sign in popover / email + sign out) when configured, and mounts the global `<TurnstileWidget/>`.
- **`components/SignInGate.tsx`**: reusable email→magic-link panel (`idle/sending/sent/error`); `signInWithOtp` uses `emailRedirectTo: window.location.href` so the link returns the user in place. **Supabase dashboard must allowlist the redirect origin** (Authentication → URL Configuration) or the link won't return.
- **The two-rule gate (frontend side):**
  - **Results (`/results/[id]`)**: *teaser*: listings render, but when `authRequired && !session` the batch-scoring + annotate effects **don't fire**; a `<SignInGate>` banner shows and cards get `gated` → a "🔒 sign in" pill instead of a score. Effects rerun when `session` appears (it's in their deps).
  - **Analyzer (`/analyze`)**: *one free, then gate*: `hasUsedFreeAnalysis()`/`markFreeAnalysisUsed()` (`lib/storage.ts`, `pf:free_analysis_used`); the 2nd anonymous run shows `<SignInGate>`.
- **Token injection**: `lib/api.ts` `gatedHeaders()` = `Authorization: Bearer <session token>` + `X-Turnstile-Token` (see below), merged into the **4 gated fetches** (`analyzeJob`, `analyzeBatch`, `annotateFit`, `analyzeJobStream`); the open fetches (`runSkyMatch*`, `parseResume`) are untouched. A `401` maps to a friendly "session expired, sign in again".
- **Cloudflare Turnstile**: `components/TurnstileWidget.tsx` (one invisible widget, mounted globally by `AuthProvider`) + `lib/turnstile-client.ts` (`getTurnstileToken()`: serialized `reset()`+`getResponsePromise()`, 8s timeout → null). The backend requires `X-Turnstile-Token` whenever its `TURNSTILE_SECRET` is set (independent of sign-in), so it's attached to every gated call. No-ops without `NEXT_PUBLIC_TURNSTILE_SITE_KEY`.

## Constants and shared helpers
- `lib/constants.ts` is the canonical source for `VERDICT_LABEL` ("Apply Now" / "Worth Prepping" / "Probably Not a Fit"), `VERDICT_COLOR`, and `scoreColor()`. Never inline verdict labels in components.
- `lib/api.ts` exports four ndjson async generators over `Content-Type: application/x-ndjson`, `analyzeBatch(profile, jobs, signal?)`, `annotateFit(profile, jobs, signal?)`, `analyzeJobStream(profile, {job_url|job_text}, signal?)`, and `runSkyMatchStream({url?,text?,profile_id?}, signal?)`. All share one pattern: `getReader()` + `TextDecoder({stream:true})` + line split, each yielded line schema-validated (`BatchEnvelopeSchema` / `AnnotateEnvelopeSchema` / `AnalyzeStreamEnvelopeSchema` / `RunStreamEnvelopeSchema`). `annotateFit` jobs are `{url, bucket}`. The single-shot `runSkyMatch` + `analyzeJob` stay for non-streaming callers (e.g. quick mode, detail-page cache re-reads); a thrown error (non-200 before the stream starts) carries the server's friendly message.

## Theme
All colors are CSS variables in `globals.css`. Never hardcode colors, always use `var(--accent)`, `var(--border)`, etc.
- `--bg` `--surface` `--border`, backgrounds
- `--text-primary` `--text-secondary`, text
- `--accent` `--accent-dim`, interactive blue
- `--color-fraternity` `--color-school` `--color-past_company` `--color-field` `--color-major`, commonality bars

## Fonts
- Body: Inter (`font-sans` / default body)
- Monospace: IBM Plex Mono (`.mono` utility class in globals.css)

## Storage (`lib/storage.ts`), durable run history
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
**Run flow:** `page.tsx` → `runSkyMatchStream()` → a 2-step progress indicator advances on the `profile`→`internships` phase envelopes → on the `done` envelope, `saveRun(runId, env.data)` → `router.push('/results/{runId}')` (reads via `getRun()`). An `error` envelope sets the same error message UX as before. (`runSkyMatch` still exists for non-streaming callers.)
**Batch quick-analysis flow:** `/results/{runId}` on mount → `analyzeBatch()` → each envelope writes via `saveAnalyses()` and into per-card React state. Return visits hydrate from storage instantly (no batch refetch).
**Deferred annotation flow:** `/results/{runId}` on mount (parallel to scoring) → `annotateFit()` over the same deduped urls → each envelope writes via `saveAnnotations()` and into per-card annotation state, filling the "Why you fit" blurb. A url is skipped if its card already shipped a nonempty `fit_explanation` (older runs) or is already cached.
**Analyze flow:** card click → `/analyze?url=…` → auto-submit `analyzeJobStream(profile, {job_url})` → the page assembles a partial `AnalysisResponse` from the phase envelopes and renders **in-place, progressively**: `VerdictCard` paints on the `verdict` envelope, then `BreakdownView`'s roadmap/project sections fill in on the `roadmap`/`project` envelopes (a phase strip shows ✓/pulse per phase). On `done`, `saveAnalysis(analysisId, full)` so the `/analyze/{analysisId}` detail route + run history still work (it reads via `getAnalysis()`). `AnalyzePage` is wrapped in `<Suspense>` (required because it uses `useSearchParams`). Headline matches the card because full reuses the quick `fit_score` + `verdict.call` from `user_analysis_cache`. The single-shot `analyzeJob` stays for any non-streaming use.
**Resume upload:** `parseResume()` → `POST /profile/from-resume` → returns `{profile_id, profile}` immediately; `profile_id` is passed to `/run` for the full call.

No server-side state, history is per-browser only (no cross-device sync without accounts). Calling `removeRun(runId)` (or the home-page `×`) deletes a run and its `pf:analyses:` + `pf:annotations:` caches; deleting only `pf:analyses:{runId}` / `pf:annotations:{runId}` forces a fresh `/analyze/batch` / `/internships/annotate` on the next visit.

## Type safety
`src/types/skymatch.ts` is the **single source of truth** for frontend types. Zod schemas validate at API boundary in `lib/api.ts`. When backend schema changes, update both `schemas.py` and `skymatch.ts`.
