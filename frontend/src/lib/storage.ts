/**
 * Durable browser-side store for Pathfinder runs and analyses.
 *
 * Backed by localStorage (survives tab close / browser restart) so the home page
 * can show a "Previous runs" history. Replaces the old sessionStorage approach
 * that wiped on tab close.
 *
 * All keys are namespaced under `pf:`:
 *   pf:runs               → run-history INDEX (array, newest-first, capped)
 *   pf:run:{runId}        → full RunResponse
 *   pf:analyses:{runId}   → per-card quick-analysis cache for a run
 *   pf:annotations:{runId}→ per-card deferred "why you fit" text for a run
 *   pf:analysis_ids       → index of standalone job-analysis ids (capped)
 *   pf:analysis:{id}      → full job AnalysisResponse
 *
 * Eviction: keep the most recent MAX_RUNS runs (oldest run + its cached analyses
 * are deleted together) and the most recent MAX_ANALYSES standalone analyses.
 * Every write is SSR-safe and degrades silently on quota/privacy-mode errors.
 */

import { z } from "zod";
import {
  RunResponseSchema,
  AnalysisResponseSchema,
  QuickAnalysisResponseSchema,
  type RunResponse,
  type AnalysisResponse,
} from "@/types/pathfinder";
import type { CardAnalysisState, CardAnnotationState } from "@/components/InternshipCard";

// ── Tunables ─────────────────────────────────────────────────────────────────
const MAX_RUNS = 10;       // history cap (decided with user)
const MAX_ANALYSES = 20;   // standalone job-analysis cap (quota safety)

// ── Key helpers ──────────────────────────────────────────────────────────────
const RUNS_KEY = "pf:runs";
const ANALYSIS_IDS_KEY = "pf:analysis_ids";
const runKey = (id: string) => `pf:run:${id}`;
const analysesKey = (id: string) => `pf:analyses:${id}`;
const annotationsKey = (id: string) => `pf:annotations:${id}`;
const analysisKey = (id: string) => `pf:analysis:${id}`;

function ls(): Storage | null {
  return typeof window !== "undefined" ? window.localStorage : null;
}

/** Raw setItem with a one-shot quota recovery: prune the oldest run, then retry. */
function safeWrite(key: string, value: string): boolean {
  const store = ls();
  if (!store) return false;
  try {
    store.setItem(key, value);
    return true;
  } catch {
    // Likely QuotaExceededError — evict the oldest run and retry once.
    const idx = readRunIndex();
    if (idx.length > 0) {
      const oldest = idx[idx.length - 1];
      deleteRunData(oldest.runId);
      writeRunIndex(idx.slice(0, -1));
    }
    try {
      store.setItem(key, value);
      return true;
    } catch {
      return false; // Give up silently; hydration just misses next time.
    }
  }
}

// ── Run-history index ─────────────────────────────────────────────────────────

export const RunIndexEntrySchema = z.object({
  runId: z.string(),
  name: z.string(),
  sublabel: z.string(),
  savedAt: z.number(),
});
export type RunIndexEntry = z.infer<typeof RunIndexEntrySchema>;

const RunIndexSchema = z.array(RunIndexEntrySchema);

function readRunIndex(): RunIndexEntry[] {
  const store = ls();
  if (!store) return [];
  const raw = store.getItem(RUNS_KEY);
  if (!raw) return [];
  try {
    const parsed = RunIndexSchema.safeParse(JSON.parse(raw));
    return parsed.success ? parsed.data : [];
  } catch {
    return [];
  }
}

function writeRunIndex(idx: RunIndexEntry[]): void {
  const store = ls();
  if (!store) return;
  try {
    store.setItem(RUNS_KEY, JSON.stringify(idx));
  } catch {
    // Index is tiny; if even this fails, nothing else will help.
  }
}

/** Delete a run's payload + cached card analyses + annotations (NOT the index entry). */
function deleteRunData(runId: string): void {
  const store = ls();
  if (!store) return;
  store.removeItem(runKey(runId));
  store.removeItem(analysesKey(runId));
  store.removeItem(annotationsKey(runId));
}

/** Decode the run timestamp from its base-36 id; fall back to now. */
function decodeSavedAt(runId: string): number {
  const n = parseInt(runId, 36);
  return Number.isFinite(n) && n > 0 ? n : Date.now();
}

// ── Public: runs ────────────────────────────────────────────────────────────

export function saveRun(runId: string, result: RunResponse): void {
  if (!safeWrite(runKey(runId), JSON.stringify(result))) return;

  const p = result.profile;
  const entry: RunIndexEntry = {
    runId,
    name: p.full_name || "Untitled run",
    sublabel: p.headline || p.school || p.current_company || "",
    savedAt: decodeSavedAt(runId),
  };

  // Upsert (drop any existing entry for this runId), newest-first, then cap.
  const next = [entry, ...readRunIndex().filter((e) => e.runId !== runId)].sort(
    (a, b) => b.savedAt - a.savedAt,
  );
  const kept = next.slice(0, MAX_RUNS);
  for (const evicted of next.slice(MAX_RUNS)) deleteRunData(evicted.runId);
  writeRunIndex(kept);
}

export function getRun(runId: string): RunResponse | null {
  const store = ls();
  if (!store) return null;
  const raw = store.getItem(runKey(runId));
  if (!raw) return null;
  try {
    const parsed = RunResponseSchema.safeParse(JSON.parse(raw));
    return parsed.success ? parsed.data : null;
  } catch {
    return null;
  }
}

export function listRuns(): RunIndexEntry[] {
  return readRunIndex();
}

export function removeRun(runId: string): void {
  deleteRunData(runId);
  writeRunIndex(readRunIndex().filter((e) => e.runId !== runId));
}

export function latestRunId(): string | null {
  return readRunIndex()[0]?.runId ?? null;
}

// ── Public: per-run card analyses (moved from results/[id]/page.tsx) ──────────

export type BucketKey = "local" | "big_tech" | "startup" | "reach";
export type AnalysesByBucket = Record<BucketKey, Record<number, CardAnalysisState>>;

const CardAnalysisStateSchema: z.ZodType<CardAnalysisState> = z.discriminatedUnion("status", [
  z.object({ status: z.literal("loading") }),
  z.object({ status: z.literal("ok"), data: QuickAnalysisResponseSchema }),
  z.object({ status: z.literal("error"), message: z.string() }),
]);

const StoredAnalysesSchema = z.object({
  results: z.object({
    local: z.record(z.string(), CardAnalysisStateSchema),
    big_tech: z.record(z.string(), CardAnalysisStateSchema),
    startup: z.record(z.string(), CardAnalysisStateSchema),
    reach: z.record(z.string(), CardAnalysisStateSchema),
  }),
  saved_at: z.number(),
});

export function loadAnalyses(runId: string): AnalysesByBucket | null {
  const store = ls();
  if (!store) return null;
  const raw = store.getItem(analysesKey(runId));
  if (!raw) return null;
  try {
    const parsed = StoredAnalysesSchema.safeParse(JSON.parse(raw));
    return parsed.success ? (parsed.data.results as AnalysesByBucket) : null;
  } catch {
    return null;
  }
}

export function saveAnalyses(runId: string, analyses: AnalysesByBucket): void {
  safeWrite(analysesKey(runId), JSON.stringify({ results: analyses, saved_at: Date.now() }));
}

// ── Public: per-run card annotations (deferred "why you fit" text) ────────────

export type AnnotationsByBucket = Record<BucketKey, Record<number, CardAnnotationState>>;

const CardAnnotationStateSchema: z.ZodType<CardAnnotationState> = z.discriminatedUnion("status", [
  z.object({ status: z.literal("loading") }),
  z.object({
    status: z.literal("ok"),
    fit_explanation: z.string(),
    reach_gap: z.string().nullable(),
  }),
  z.object({ status: z.literal("error") }),
]);

const StoredAnnotationsSchema = z.object({
  results: z.object({
    local: z.record(z.string(), CardAnnotationStateSchema),
    big_tech: z.record(z.string(), CardAnnotationStateSchema),
    startup: z.record(z.string(), CardAnnotationStateSchema),
    reach: z.record(z.string(), CardAnnotationStateSchema),
  }),
  saved_at: z.number(),
});

export function loadAnnotations(runId: string): AnnotationsByBucket | null {
  const store = ls();
  if (!store) return null;
  const raw = store.getItem(annotationsKey(runId));
  if (!raw) return null;
  try {
    const parsed = StoredAnnotationsSchema.safeParse(JSON.parse(raw));
    return parsed.success ? (parsed.data.results as AnnotationsByBucket) : null;
  } catch {
    return null;
  }
}

export function saveAnnotations(runId: string, annotations: AnnotationsByBucket): void {
  safeWrite(annotationsKey(runId), JSON.stringify({ results: annotations, saved_at: Date.now() }));
}

// ── Public: standalone job analyses ───────────────────────────────────────────

function readAnalysisIds(): string[] {
  const store = ls();
  if (!store) return [];
  const raw = store.getItem(ANALYSIS_IDS_KEY);
  if (!raw) return [];
  try {
    const parsed = z.array(z.string()).safeParse(JSON.parse(raw));
    return parsed.success ? parsed.data : [];
  } catch {
    return [];
  }
}

export function saveAnalysis(analysisId: string, data: AnalysisResponse): void {
  if (!safeWrite(analysisKey(analysisId), JSON.stringify(data))) return;
  const store = ls();
  if (!store) return;
  // newest-first id index; cap and evict the oldest analyses' payloads.
  const next = [analysisId, ...readAnalysisIds().filter((id) => id !== analysisId)];
  for (const evicted of next.slice(MAX_ANALYSES)) store.removeItem(analysisKey(evicted));
  try {
    store.setItem(ANALYSIS_IDS_KEY, JSON.stringify(next.slice(0, MAX_ANALYSES)));
  } catch {
    // ignore
  }
}

export function getAnalysis(analysisId: string): AnalysisResponse | null {
  const store = ls();
  if (!store) return null;
  const raw = store.getItem(analysisKey(analysisId));
  if (!raw) return null;
  try {
    const parsed = AnalysisResponseSchema.safeParse(JSON.parse(raw));
    return parsed.success ? parsed.data : null;
  } catch {
    return null;
  }
}

// ── Misc ──────────────────────────────────────────────────────────────────────

const rtf = typeof Intl !== "undefined" && "RelativeTimeFormat" in Intl
  ? new Intl.RelativeTimeFormat("en", { numeric: "auto" })
  : null;

/** "2 hours ago", "yesterday", … from an epoch-ms timestamp. */
export function timeAgo(ms: number): string {
  const diff = ms - Date.now(); // negative = past
  const sec = Math.round(diff / 1000);
  const abs = Math.abs(sec);
  const units: Array<[Intl.RelativeTimeFormatUnit, number]> = [
    ["year", 31536000],
    ["month", 2592000],
    ["week", 604800],
    ["day", 86400],
    ["hour", 3600],
    ["minute", 60],
  ];
  for (const [unit, secs] of units) {
    if (abs >= secs) {
      const value = Math.round(sec / secs);
      return rtf ? rtf.format(value, unit) : `${Math.abs(value)} ${unit}${Math.abs(value) === 1 ? "" : "s"} ago`;
    }
  }
  return rtf ? rtf.format(sec, "second") : "just now";
}
