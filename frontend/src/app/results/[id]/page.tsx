"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { type RunResponse } from "@/types/pathfinder";
import { ProfileCard } from "@/components/ProfileCard";
import { BucketSection, type SortMode } from "@/components/BucketSection";
import type { CardAnalysisState } from "@/components/InternshipCard";
import { analyzeBatch, annotateFit } from "@/lib/api";
import {
  getRun,
  loadAnalyses,
  saveAnalyses,
  loadAnnotations,
  saveAnnotations,
  type AnalysesByBucket,
  type AnnotationsByBucket,
  type BucketKey,
} from "@/lib/storage";

const BUCKETS: BucketKey[] = ["local", "big_tech", "startup", "reach"];
const EMPTY_ANALYSES: AnalysesByBucket = { local: {}, big_tech: {}, startup: {}, reach: {} };
const EMPTY_ANNOTATIONS: AnnotationsByBucket = { local: {}, big_tech: {}, startup: {}, reach: {} };

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

function cloneAnalyses(a: AnalysesByBucket): AnalysesByBucket {
  return {
    local:    { ...a.local },
    big_tech: { ...a.big_tech },
    startup:  { ...a.startup },
    reach:    { ...a.reach },
  };
}

function cloneAnnotations(a: AnnotationsByBucket): AnnotationsByBucket {
  return {
    local:    { ...a.local },
    big_tech: { ...a.big_tech },
    startup:  { ...a.startup },
    reach:    { ...a.reach },
  };
}

export default function ResultsPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [data, setData] = useState<RunResponse | null>(null);
  const [error, setError] = useState("");
  // Hydrate from storage (localStorage via lib/storage) on first render so cached
  // cards paint instantly, with no "analyzing…" flash on a return visit.
  const [analyses, setAnalyses] = useState<AnalysesByBucket>(
    () => loadAnalyses(id) ?? EMPTY_ANALYSES,
  );
  const [annotations, setAnnotations] = useState<AnnotationsByBucket>(
    () => loadAnnotations(id) ?? EMPTY_ANNOTATIONS,
  );
  const [sort, setSort] = useState<SortMode>("fit");
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const run = getRun(id);
    if (!run) {
      setError("Couldn't find that run — it may have been cleared.");
      return;
    }
    setData(run);
  }, [id]);

  // Build a DEDUPED job list (unique application_url) plus, for each job, the list
  // of (bucket, idx) slots that share that url. The same listing can legitimately
  // appear in multiple buckets (e.g. a big_tech role that's also a reach). Scoring
  // is per (profile, job) and bucket-independent, so we score each url ONCE and fan
  // the result out to every slot — saving the duplicate Claude calls.
  const { jobs, jobSlots } = useMemo(() => {
    const jobs: { url: string }[] = [];
    const jobSlots: Array<Array<{ bucket: BucketKey; idx: number }>> = [];
    if (!data) return { jobs, jobSlots };
    const urlToJob = new Map<string, number>();
    for (const bucket of BUCKETS) {
      data.internships[bucket].forEach((it, idx) => {
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
    return { jobs, jobSlots };
  }, [data]);

  // Guards the once-per-url auto-retry. A ref (not state) so it survives re-renders
  // without re-triggering effects; reset when viewing a different run.
  const autoRetriedRef = useRef<Set<string>>(new Set());
  useEffect(() => {
    autoRetriedRef.current = new Set();
  }, [id]);

  // Score a SINGLE url and fan the result to every slot that shares it. Shared by the
  // auto-retry (transient failures) and the manual "retry" badge. `delayMs` adds backoff
  // before re-firing (auto-retry uses it; manual is immediate). Defined ABOVE the scoring
  // effect so that effect can list maybeAutoRetry in its deps without a TDZ error.
  const scoreUrl = useCallback(
    (url: string, opts?: { delayMs?: number }) => {
      if (!data) return;
      const slots: Array<{ bucket: BucketKey; idx: number }> = [];
      for (const b of BUCKETS) {
        data.internships[b].forEach((it, i) => {
          if (it.application_url === url) slots.push({ bucket: b, idx: i });
        });
      }
      if (slots.length === 0) return;

      const apply = (state: CardAnalysisState) =>
        setAnalyses((prev) => {
          const next = cloneAnalyses(prev);
          slots.forEach((s) => { next[s.bucket][s.idx] = state; });
          saveAnalyses(id, next);
          return next;
        });

      apply({ status: "loading" });

      (async () => {
        try {
          if (opts?.delayMs) await sleep(opts.delayMs);
          let got = false;
          for await (const env of analyzeBatch(data.profile, [{ url }])) {
            got = true;
            apply(
              env.status === "ok" && env.data
                ? { status: "ok", data: env.data }
                : { status: "error", message: env.error?.message ?? "Analysis failed" },
            );
          }
          if (!got) apply({ status: "error", message: "No result" });
        } catch (err) {
          apply({ status: "error", message: (err as Error).message || "Retry failed" });
        }
      })();
    },
    [data, id],
  );

  // Auto-retry a failed url at most ONCE (with backoff) before the user ever sees a
  // manual "retry" badge. The ref guard guarantees a single auto attempt per url.
  const maybeAutoRetry = useCallback(
    (url: string) => {
      if (autoRetriedRef.current.has(url)) return;
      autoRetriedRef.current.add(url);
      scoreUrl(url, { delayMs: 800 });
    },
    [scoreUrl],
  );

  // Manual "retry" badge handler — immediate re-score of the clicked card's url. The
  // backend now falls back to an index-based score when the live fetch fails, so a served
  // internship's retry resolves to a real score instead of re-failing on the same flaky url.
  const retryJob = useCallback(
    (bucket: BucketKey, idx: number) => {
      const url = data?.internships[bucket]?.[idx]?.application_url;
      if (url) scoreUrl(url);
    },
    [data, scoreUrl],
  );

  // Auto-fire the batch only for jobs NOT already covered by stored analyses.
  // If every slot is cached → no skeleton, no /analyze/batch call.
  useEffect(() => {
    if (!data || jobs.length === 0) return;

    // Re-read storage to determine coverage (state may already be hydrated).
    const stored = loadAnalyses(id);
    // A unique job needs (re)scoring if ANY of its slots lacks a finished result.
    const missingJobs: number[] = [];
    for (let i = 0; i < jobs.length; i++) {
      const anyUncovered = jobSlots[i].some((s) => {
        const cur = stored?.[s.bucket]?.[s.idx];
        return !cur || cur.status === "loading";
      });
      if (anyUncovered) missingJobs.push(i);
    }

    const totalSlots = jobSlots.reduce((n, ss) => n + ss.length, 0);

    if (missingJobs.length === 0) {
      // Fully cached. If state hasn't synced yet (e.g. hydrated mid-render), sync it.
      if (stored) setAnalyses(stored);
      console.log("[results] all", totalSlots, "cards cached — skipping batch");
      return;
    }

    console.log(
      `[results] ${jobs.length - missingJobs.length}/${jobs.length} unique jobs cached, ` +
        `fetching ${missingJobs.length} (covering ${totalSlots} cards)`,
    );

    // Seed every slot of each missing job to "loading" (cached cards keep their state).
    setAnalyses((prev) => {
      const next = cloneAnalyses(prev);
      missingJobs.forEach((i) =>
        jobSlots[i].forEach((s) => {
          next[s.bucket][s.idx] = { status: "loading" };
        }),
      );
      return next;
    });

    const jobsToSend = missingJobs.map((i) => jobs[i]);
    const controller = new AbortController();
    abortRef.current = controller;

    (async () => {
      const received = new Set<number>();   // job indices that produced an envelope
      const failedUrls = new Set<string>(); // urls whose score failed (retry candidates)
      try {
        for await (const env of analyzeBatch(data.profile, jobsToSend, controller.signal)) {
          // env.index is the position in jobsToSend → map back to the unique job,
          // then fan the result out to EVERY slot that shares its url.
          const jobIdx = missingJobs[env.index];
          const targetSlots = jobIdx !== undefined ? jobSlots[jobIdx] : undefined;
          if (jobIdx === undefined || !targetSlots) continue;
          received.add(jobIdx);
          if (!(env.status === "ok" && env.data)) failedUrls.add(jobs[jobIdx].url);
          setAnalyses((prev) => {
            const next = cloneAnalyses(prev);
            targetSlots.forEach((s) => {
              if (env.status === "ok" && env.data) {
                next[s.bucket][s.idx] = { status: "ok", data: env.data };
              } else {
                next[s.bucket][s.idx] = {
                  status: "error",
                  message: env.error?.message ?? "Analysis failed",
                };
              }
            });
            // Persist on every envelope so partial progress survives tab-close.
            saveAnalyses(id, next);
            return next;
          });
        }
      } catch (err) {
        if ((err as Error).name === "AbortError") return; // navigated away — leave state as-is
        console.error("[results] batch stream failed", err);
      }

      // Safety net: any job that never produced an envelope (stream ended early or a
      // network error mid-flight) must NOT hang on the "analyzing…" skeleton forever.
      // Flip its still-loading slots to a (retryable) error so retry can fire.
      const orphans = missingJobs.filter((j) => !received.has(j));
      if (orphans.length) {
        setAnalyses((prev) => {
          const next = cloneAnalyses(prev);
          orphans.forEach((jobIdx) =>
            jobSlots[jobIdx].forEach((s) => {
              if (next[s.bucket][s.idx]?.status === "loading") {
                next[s.bucket][s.idx] = { status: "error", message: "No result" };
              }
            }),
          );
          saveAnalyses(id, next);
          return next;
        });
        orphans.forEach((j) => failedUrls.add(jobs[j].url));
      }

      // Auto-retry each failed url ONCE (with backoff) before any manual "retry" shows.
      failedUrls.forEach((url) => maybeAutoRetry(url));
    })();

    return () => controller.abort();
  }, [id, data, jobs, jobSlots, maybeAutoRetry]);

  // Deferred "why you fit" is now LAZY: nothing fires on page load. Expanding a card calls
  // annotateUrl for that role's url (the feed ships an empty fit_explanation). We still annotate
  // each url ONCE and fan the result to every slot that shares it (a listing can be big_tech AND
  // reach), persisting on each envelope. reach_gap only applies to reach slots.
  const annotateRequestedRef = useRef<Set<string>>(new Set());
  const annotateControllersRef = useRef<Set<AbortController>>(new Set());
  // Reset the per-url guard when switching runs (mirror autoRetriedRef).
  useEffect(() => {
    annotateRequestedRef.current = new Set();
  }, [id]);
  // Abort any in-flight annotate streams on unmount / when switching runs.
  useEffect(() => {
    const controllers = annotateControllersRef.current;
    return () => {
      controllers.forEach((c) => c.abort());
      controllers.clear();
    };
  }, [id]);

  const annotateUrl = useCallback(
    (url: string | null | undefined) => {
      if (!data || !url) return;
      if (annotateRequestedRef.current.has(url)) return; // in-flight or already done

      // Collect every slot sharing this url (same loop shape as scoreUrl).
      const slots: Array<{ bucket: BucketKey; idx: number }> = [];
      for (const b of BUCKETS) {
        data.internships[b].forEach((it, i) => {
          if (it.application_url === url) slots.push({ bucket: b, idx: i });
        });
      }
      if (slots.length === 0) return;

      // Already satisfied? Any slot with an ok annotation, or a feed-shipped fit_explanation
      // (older runs predate the deferred pass) — nothing to fetch.
      const alreadyOk = slots.some((s) => {
        const cur = annotations[s.bucket]?.[s.idx];
        const it = data.internships[s.bucket]?.[s.idx];
        return cur?.status === "ok" || !!it?.fit_explanation;
      });
      if (alreadyOk) return;

      annotateRequestedRef.current.add(url);
      // Prefer a reach slot so reach_gap is computed when any slot is a reach card.
      const bucket: BucketKey = slots.some((s) => s.bucket === "reach") ? "reach" : slots[0].bucket;

      setAnnotations((prev) => {
        const next = cloneAnnotations(prev);
        slots.forEach((s) => { next[s.bucket][s.idx] = { status: "loading" }; });
        return next;
      });

      const controller = new AbortController();
      annotateControllersRef.current.add(controller);

      (async () => {
        try {
          for await (const env of annotateFit(data.profile, [{ url, bucket }], controller.signal)) {
            setAnnotations((prev) => {
              const next = cloneAnnotations(prev);
              slots.forEach((s) => {
                if (env.status === "ok") {
                  next[s.bucket][s.idx] = {
                    status: "ok",
                    fit_explanation: env.fit_explanation ?? "",
                    reach_gap: s.bucket === "reach" ? env.reach_gap ?? null : null,
                  };
                } else {
                  next[s.bucket][s.idx] = { status: "error" };
                }
              });
              saveAnnotations(id, next);
              return next;
            });
          }
        } catch (err) {
          if ((err as Error).name !== "AbortError") {
            console.error("[results] annotate stream failed", err);
            // Don't leave the card stuck on the skeleton — flip still-loading slots to error.
            setAnnotations((prev) => {
              const next = cloneAnnotations(prev);
              slots.forEach((s) => {
                if (next[s.bucket][s.idx]?.status === "loading") {
                  next[s.bucket][s.idx] = { status: "error" };
                }
              });
              saveAnnotations(id, next);
              return next;
            });
          }
          // Drop the guard so a later re-expand can retry this url.
          annotateRequestedRef.current.delete(url);
        } finally {
          annotateControllersRef.current.delete(controller);
        }
      })();
    },
    [data, id, annotations],
  );

  if (error) {
    return (
      <main className="min-h-screen flex items-center justify-center px-6">
        <div className="text-center flex flex-col gap-4">
          <p className="text-sm" style={{ color: "var(--text-secondary)" }}>{error}</p>
          <button
            onClick={() => router.push("/")}
            className="mono text-xs uppercase tracking-widest"
            style={{ color: "var(--accent)" }}
          >
            ← Back
          </button>
        </div>
      </main>
    );
  }

  if (!data) {
    return (
      <main className="min-h-screen flex items-center justify-center">
        <span
          className="inline-block w-3 h-3 rounded-full animate-pulse"
          style={{ background: "var(--accent)" }}
        />
      </main>
    );
  }

  const { profile, internships } = data;

  return (
    <main className="min-h-screen px-6 py-12 flex flex-col items-center gap-12">
      <div className="w-full max-w-3xl flex flex-col gap-12">

        {/* Nav row */}
        <div className="flex items-center justify-between">
          <button
            onClick={() => router.push("/")}
            className="mono text-xs font-medium px-3 py-1.5 border border-[var(--border)]
                       hover:bg-[var(--accent)] hover:text-black hover:border-[var(--accent)]
                       transition-colors"
            style={{ color: "var(--accent)" }}
          >
            ← start over
          </button>
          <Link
            href="/analyze"
            className="mono text-xs font-medium px-3 py-1.5 border border-[var(--border)]
                       hover:bg-[var(--accent)] hover:text-black hover:border-[var(--accent)]
                       transition-colors"
            style={{ color: "var(--accent)" }}
          >
            analyze a job →
          </Link>
        </div>

        {/* 1. Profile summary */}
        <ProfileCard profile={profile} />

        {/* 2. Internship buckets */}
        <section className="flex flex-col gap-10">
          <div className="flex items-end justify-between gap-3 flex-wrap">
            <div>
              <h2 className="mono text-lg font-semibold uppercase tracking-widest" style={{ color: "var(--text-primary)" }}>
                Internship Opportunities
              </h2>
              <p className="text-xs mt-1" style={{ color: "var(--text-secondary)" }}>
                Matched to your profile across 4 buckets · live fit analysis
              </p>
            </div>
            <div
              className="mono text-[10px] uppercase tracking-widest flex border"
              style={{ borderColor: "var(--border)" }}
            >
              {(["fit", "recency"] as SortMode[]).map((m) => (
                <button
                  key={m}
                  type="button"
                  onClick={() => setSort(m)}
                  className="px-3 py-1.5 transition-colors"
                  style={{
                    color: sort === m ? "var(--accent)" : "var(--text-secondary)",
                    background: sort === m ? "var(--surface)" : "transparent",
                  }}
                >
                  {m === "fit" ? "By fit" : "By recency"}
                </button>
              ))}
            </div>
          </div>
          {BUCKETS.map((b) => (
            <BucketSection
              key={b}
              bucket={b}
              internships={internships[b]}
              analyses={analyses[b]}
              annotations={annotations[b]}
              sort={sort}
              onRetry={(idx) => retryJob(b, idx)}
              onRequestAnnotation={(idx) => annotateUrl(internships[b]?.[idx]?.application_url)}
            />
          ))}
        </section>

      </div>
    </main>
  );
}
