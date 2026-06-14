"use client";
import { analyzeBatch } from "@/lib/api";
import type { UnifiedProfile, InternshipBuckets } from "@/types/pathfinder";
import type { AnalysesByBucket, BucketKey } from "@/lib/storage";
import type { CardAnalysisState } from "@/lib/cardState";

const BUCKETS: BucketKey[] = ["local", "big_tech", "startup", "reach"];

// Batch-score a run's internships into an AnalysesByBucket (the same dedup-by-url, fan-to-slots
// logic the results page uses). Extracted so the home run flow can PRE-score during the run
// veil — the results page then hydrates the cached analyses and lands fully graded instead of
// showing its own "Scoring…" pass. Each unique application_url is scored once and the verdict
// fanned to every (bucket, idx) slot that shares it; orphans/errors resolve to an error state
// so the feed never hangs on "loading".
export async function scoreRunInternships(
  profile: UnifiedProfile,
  internships: InternshipBuckets,
  signal?: AbortSignal,
): Promise<AnalysesByBucket> {
  const analyses: AnalysesByBucket = { local: {}, big_tech: {}, startup: {}, reach: {} };

  const jobs: { url: string }[] = [];
  const jobSlots: Array<Array<{ bucket: BucketKey; idx: number }>> = [];
  const urlToJob = new Map<string, number>();
  for (const bucket of BUCKETS) {
    internships[bucket].forEach((it, idx) => {
      if (!it.application_url) return;
      let ji = urlToJob.get(it.application_url);
      if (ji === undefined) {
        ji = jobs.length;
        urlToJob.set(it.application_url, ji);
        jobs.push({ url: it.application_url });
        jobSlots.push([]);
      }
      jobSlots[ji].push({ bucket, idx });
    });
  }
  if (jobs.length === 0) return analyses;

  const received = new Set<number>();
  for await (const env of analyzeBatch(profile, jobs, signal)) {
    const slots = jobSlots[env.index];
    if (!slots) continue;
    received.add(env.index);
    const state: CardAnalysisState =
      env.status === "ok" && env.data
        ? { status: "ok", data: env.data }
        : { status: "error", message: env.error?.message ?? "Analysis failed" };
    slots.forEach((s) => { analyses[s.bucket][s.idx] = state; });
  }
  // Orphans (a job that never streamed back) → error, so no slot is left on "loading".
  jobs.forEach((_, ji) => {
    if (received.has(ji)) return;
    jobSlots[ji].forEach((s) => {
      if (!analyses[s.bucket][s.idx]) analyses[s.bucket][s.idx] = { status: "error", message: "No result" };
    });
  });
  return analyses;
}
