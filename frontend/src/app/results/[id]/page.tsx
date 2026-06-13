"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { type RunResponse } from "@/types/pathfinder";
import { analyzeBatch, annotateFit } from "@/lib/api";
import { SignInGate } from "@/components/SignInGate";
import { useAuth } from "@/lib/auth-context";
import { AppShell } from "@/components/AppShell";
import { RoleCard } from "@/components/feed/RoleCard";
import { RoleDrawer } from "@/components/feed/RoleDrawer";
import { BandSection } from "@/components/feed/BandSection";
import { NotFitBlock } from "@/components/feed/NotFitBlock";
import { type Band, BAND_KEYS, bandOf, fitScoreOf } from "@/lib/bands";
import { useSaved } from "@/lib/useSaved";
import { DEMO_RUN_ID, demoAnalysisIdFromUrl } from "@/lib/demoRun";
import type { CardAnalysisState } from "@/lib/cardState";
import {
  getRun,
  loadAnalyses,
  saveAnalyses,
  loadAnnotations,
  saveAnnotations,
  setActiveRunId,
  type AnalysesByBucket,
  type AnnotationsByBucket,
  type BucketKey,
} from "@/lib/storage";

const BUCKETS: BucketKey[] = ["local", "big_tech", "startup", "reach"];
const EMPTY_ANALYSES: AnalysesByBucket = { local: {}, big_tech: {}, startup: {}, reach: {} };
const EMPTY_ANNOTATIONS: AnnotationsByBucket = { local: {}, big_tech: {}, startup: {}, reach: {} };

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

function cloneAnalyses(a: AnalysesByBucket): AnalysesByBucket {
  return { local: { ...a.local }, big_tech: { ...a.big_tech }, startup: { ...a.startup }, reach: { ...a.reach } };
}
function cloneAnnotations(a: AnnotationsByBucket): AnnotationsByBucket {
  return { local: { ...a.local }, big_tech: { ...a.big_tech }, startup: { ...a.startup }, reach: { ...a.reach } };
}

interface FeedItem { url: string; bucket: BucketKey; idx: number; }

type Filter = "all" | BucketKey;
type Sort = "best" | "new";

// Filter chips — mockup labels, mapped onto the sourcing buckets.
const FILTER_CHIPS: Array<{ f: Filter; label: string }> = [
  { f: "all", label: "All" },
  { f: "big_tech", label: "Big tech" },
  { f: "startup", label: "Startups" },
  { f: "local", label: "Near you" },
  { f: "reach", label: "Selective" },
];

// "Newest" sort rank from job_summary.posted_at — handles ISO dates and "2d ago"/"1w ago"
// style strings; unknown/unscored sink to the bottom.
function postedRank(analysis: CardAnalysisState | undefined): number {
  if (analysis?.status !== "ok") return -Infinity;
  const s = analysis.data.job_summary.posted_at;
  if (!s) return -Infinity;
  const t = Date.parse(s);
  if (!Number.isNaN(t)) return t;
  const m = /(\d+)\s*([hdw])/i.exec(s);
  if (m) {
    const n = +m[1];
    const ms = m[2].toLowerCase() === "h" ? n * 3600_000 : m[2].toLowerCase() === "d" ? n * 86_400_000 : n * 7 * 86_400_000;
    return Date.now() - ms;
  }
  return -Infinity;
}

// "refreshed today / yesterday / Nd ago" from the base-36 timestamp runId.
function refreshedLabel(id: string): string {
  const ts = parseInt(id, 36);
  // Sanity floor (2020-01-01): non-timestamp ids decode to tiny numbers → absurd day counts.
  if (!Number.isFinite(ts) || ts < 1_577_836_800_000) return "today";
  const days = Math.floor((Date.now() - ts) / 86_400_000);
  if (days <= 0) return "today";
  if (days === 1) return "yesterday";
  return `${days}d ago`;
}

export default function ResultsPage() {
  const { id } = useParams<{ id: string }>();
  const [data, setData] = useState<RunResponse | null>(null);
  const [error, setError] = useState("");
  // Hydrate caches from localStorage so a return visit paints instantly (no "scoring" flash).
  const [analyses, setAnalyses] = useState<AnalysesByBucket>(() => loadAnalyses(id) ?? EMPTY_ANALYSES);
  const [annotations, setAnnotations] = useState<AnnotationsByBucket>(() => loadAnnotations(id) ?? EMPTY_ANNOTATIONS);
  const [openUrl, setOpenUrl] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [sort, setSort] = useState<Sort>("best");
  // True while the live first-pass /analyze/batch is running, so the feed shows ONE loader and the
  // full ranked feed reveals together (not card-by-card). Stays false on the cached-hydrate path.
  const [scoring, setScoring] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const { has: isSaved, toggle: toggleSaved } = useSaved();

  // Auth gate: the results "reveal" (scores via /analyze/batch + "why you fit" via
  // /internships/annotate) requires sign-in when enforcement is on. Listings still render
  // as a teaser; only the LLM-fired scores/annotations are gated.
  const { session, authRequired, loading: authLoading, signInWithOtp } = useAuth();
  // The static sample shortlist is fully pre-scored/annotated; it must render for logged-out
  // visitors, so it bypasses the sign-in gate (and never fires the scoring/annotate backends).
  const isDemo = id === DEMO_RUN_ID;
  const needsSignIn = authRequired && !session && !isDemo;

  useEffect(() => {
    const run = getRun(id);
    if (!run) {
      setError("Couldn't find that run — it may have been cleared.");
      return;
    }
    // Mark this as the in-tab "current run" so the shell nav (Matches/Profile) stays on it —
    // critical for the demo, which is intentionally absent from the run-history index.
    setActiveRunId(id);
    setData(run);
  }, [id]);

  // Deduped job list (unique application_url) + the (bucket, idx) slots that share each url.
  // The same listing can appear in multiple buckets; we score/annotate each url ONCE and fan
  // the result to every slot. The first slot is the feed's representative for that url.
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

  // One feed row per unique url (the representative = first slot).
  const feedItems: FeedItem[] = useMemo(
    () => jobs.map((job, ji) => ({ url: job.url, bucket: jobSlots[ji][0].bucket, idx: jobSlots[ji][0].idx })),
    [jobs, jobSlots],
  );

  const autoRetriedRef = useRef<Set<string>>(new Set());
  useEffect(() => { autoRetriedRef.current = new Set(); }, [id]);

  // Score a SINGLE url and fan the result to every slot sharing it (auto-retry + first pass).
  const scoreUrl = useCallback(
    (url: string, opts?: { delayMs?: number }) => {
      if (!data) return;
      const slots: Array<{ bucket: BucketKey; idx: number }> = [];
      for (const b of BUCKETS) {
        data.internships[b].forEach((it, i) => { if (it.application_url === url) slots.push({ bucket: b, idx: i }); });
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
            apply(env.status === "ok" && env.data ? { status: "ok", data: env.data } : { status: "error", message: env.error?.message ?? "Analysis failed" });
          }
          if (!got) apply({ status: "error", message: "No result" });
        } catch (err) {
          apply({ status: "error", message: (err as Error).message || "Retry failed" });
        }
      })();
    },
    [data, id],
  );

  const maybeAutoRetry = useCallback(
    (url: string) => {
      if (autoRetriedRef.current.has(url)) return;
      autoRetriedRef.current.add(url);
      scoreUrl(url, { delayMs: 800 });
    },
    [scoreUrl],
  );

  // Auto-fire the batch only for jobs NOT already covered by stored analyses.
  useEffect(() => {
    if (!data || jobs.length === 0) return;
    if (isDemo) return; // sample run is pre-scored — never call /analyze/batch
    if (needsSignIn) return; // gated — don't fire scoring until signed in

    const stored = loadAnalyses(id);
    const missingJobs: number[] = [];
    for (let i = 0; i < jobs.length; i++) {
      const anyUncovered = jobSlots[i].some((s) => {
        const cur = stored?.[s.bucket]?.[s.idx];
        return !cur || cur.status === "loading";
      });
      if (anyUncovered) missingJobs.push(i);
    }
    if (missingJobs.length === 0) {
      if (stored) setAnalyses(stored);
      return;
    }

    setScoring(true);
    setAnalyses((prev) => {
      const next = cloneAnalyses(prev);
      missingJobs.forEach((i) => jobSlots[i].forEach((s) => { next[s.bucket][s.idx] = { status: "loading" }; }));
      return next;
    });

    const jobsToSend = missingJobs.map((i) => jobs[i]);
    const controller = new AbortController();
    abortRef.current = controller;

    (async () => {
      const received = new Set<number>();
      const failedUrls = new Set<string>();
      // Buffer every envelope into a local copy and commit ONCE at the end, so the whole ranked
      // feed reveals together instead of cards flipping in one-by-one as results stream back.
      const buffered = cloneAnalyses(stored ?? EMPTY_ANALYSES);
      missingJobs.forEach((i) => jobSlots[i].forEach((s) => { buffered[s.bucket][s.idx] = { status: "loading" }; }));
      let aborted = false;
      try {
        for await (const env of analyzeBatch(data.profile, jobsToSend, controller.signal)) {
          const jobIdx = missingJobs[env.index];
          const targetSlots = jobIdx !== undefined ? jobSlots[jobIdx] : undefined;
          if (jobIdx === undefined || !targetSlots) continue;
          received.add(jobIdx);
          if (!(env.status === "ok" && env.data)) failedUrls.add(jobs[jobIdx].url);
          targetSlots.forEach((s) => {
            buffered[s.bucket][s.idx] = env.status === "ok" && env.data
              ? { status: "ok", data: env.data }
              : { status: "error", message: env.error?.message ?? "Analysis failed" };
          });
        }
      } catch (err) {
        if ((err as Error).name === "AbortError") { aborted = true; return; }
        console.error("[results] batch stream failed", err);
      } finally {
        if (!aborted) {
          // Orphans (never received) → mark errored so they don't hang on "loading" past the reveal.
          const orphans = missingJobs.filter((j) => !received.has(j));
          orphans.forEach((jobIdx) => jobSlots[jobIdx].forEach((s) => {
            if (buffered[s.bucket][s.idx]?.status === "loading") buffered[s.bucket][s.idx] = { status: "error", message: "No result" };
          }));
          orphans.forEach((j) => failedUrls.add(jobs[j].url));
          setAnalyses(buffered);
          saveAnalyses(id, buffered);
          setScoring(false);
          // Failed roles auto-retry AFTER the bulk reveal — a stray card patches in later.
          failedUrls.forEach((url) => maybeAutoRetry(url));
        }
      }
    })();

    return () => controller.abort();
  }, [id, data, jobs, jobSlots, maybeAutoRetry, needsSignIn]);

  // Deferred "why you fit" — LAZY: fired on a card's first drawer-open (not on page load).
  // Annotate each url ONCE, fan to every slot, persist on each envelope.
  const annotateRequestedRef = useRef<Set<string>>(new Set());
  const annotateControllersRef = useRef<Set<AbortController>>(new Set());
  useEffect(() => { annotateRequestedRef.current = new Set(); }, [id]);
  useEffect(() => {
    const controllers = annotateControllersRef.current;
    return () => { controllers.forEach((c) => c.abort()); controllers.clear(); };
  }, [id]);

  const annotateUrl = useCallback(
    (url: string | null | undefined) => {
      if (!data || !url) return;
      if (isDemo) return; // sample run is pre-annotated — never call /internships/annotate
      if (needsSignIn) return;
      if (annotateRequestedRef.current.has(url)) return;

      const slots: Array<{ bucket: BucketKey; idx: number }> = [];
      for (const b of BUCKETS) {
        data.internships[b].forEach((it, i) => { if (it.application_url === url) slots.push({ bucket: b, idx: i }); });
      }
      if (slots.length === 0) return;

      const alreadyOk = slots.some((s) => {
        const cur = annotations[s.bucket]?.[s.idx];
        const it = data.internships[s.bucket]?.[s.idx];
        return cur?.status === "ok" || !!it?.fit_explanation;
      });
      if (alreadyOk) return;

      annotateRequestedRef.current.add(url);
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
                    why: env.why ?? [],
                    have: env.have ?? [],
                    need: env.need ?? [],
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
            setAnnotations((prev) => {
              const next = cloneAnnotations(prev);
              slots.forEach((s) => { if (next[s.bucket][s.idx]?.status === "loading") next[s.bucket][s.idx] = { status: "error" }; });
              saveAnnotations(id, next);
              return next;
            });
          }
          annotateRequestedRef.current.delete(url);
        } finally {
          annotateControllersRef.current.delete(controller);
        }
      })();
    },
    [data, id, annotations, needsSignIn],
  );

  const openRole = useCallback((url: string) => { setOpenUrl(url); annotateUrl(url); }, [annotateUrl]);

  // Visible items under the active company-type filter (a deduped row filters by its
  // representative bucket — the same bucket its type-tag shows).
  const visibleItems = useMemo(
    () => (filter === "all" ? feedItems : feedItems.filter((i) => i.bucket === filter)),
    [feedItems, filter],
  );

  // Group VISIBLE feed items into bands (pending = not yet scored; notfit = skip verdicts,
  // routed to the collapsed block), sorted by fit within each band.
  const groups = useMemo(() => {
    const g: Record<Band | "pending", FeedItem[]> = { strong: [], look: [], stretch: [], notfit: [], pending: [] };
    for (const item of visibleItems) {
      const band = bandOf(analyses[item.bucket]?.[item.idx]);
      g[band ?? "pending"].push(item);
    }
    BAND_KEYS.forEach((b) => {
      g[b].sort((x, y) => fitScoreOf(analyses[y.bucket]?.[y.idx]) - fitScoreOf(analyses[x.bucket]?.[x.idx]));
    });
    return g;
  }, [visibleItems, analyses]);

  // Flat "Newest" ordering (excludes notfit — those stay in the collapsed block).
  const newestItems = useMemo(() => {
    const rows = visibleItems.filter((i) => bandOf(analyses[i.bucket]?.[i.idx]) !== "notfit");
    return [...rows].sort((x, y) => postedRank(analyses[y.bucket]?.[y.idx]) - postedRank(analyses[x.bucket]?.[x.idx]));
  }, [visibleItems, analyses]);

  const renderCard = (item: FeedItem, delayIdx = 0) => {
    const it = data!.internships[item.bucket][item.idx];
    const analysis = analyses[item.bucket]?.[item.idx];
    return (
      <RoleCard
        key={item.url}
        internship={it}
        bucket={item.bucket}
        band={needsSignIn ? null : bandOf(analysis)}
        analysis={analysis}
        saved={isSaved(item.url)}
        gated={needsSignIn}
        pending={scoring}
        style={{ animationDelay: `${delayIdx * 45}ms` }}
        onOpen={() => openRole(item.url)}
        onToggleSave={() => toggleSaved({ url: item.url, internship: it, bucket: item.bucket })}
      />
    );
  };

  if (error) {
    return (
      <AppShell active="feed">
        <div className="topbar"><div><h1 className="pg">Run not found</h1><p className="pg-sub">{error}</p></div></div>
      </AppShell>
    );
  }
  if (!data) {
    return (
      <AppShell active="feed">
        <div style={{ display: "grid", placeItems: "center", minHeight: "50vh" }}>
          <span className="az-spinner" />
        </div>
      </AppShell>
    );
  }

  const { profile } = data;
  const initial = (profile.full_name || "?").trim()[0]?.toUpperCase() ?? "?";
  const firstName = (profile.full_name || "your").trim().split(/\s+/)[0];
  const openItem = openUrl ? feedItems.find((i) => i.url === openUrl) ?? null : null;
  const openInternship = openItem ? data.internships[openItem.bucket][openItem.idx] : null;
  const openAnalysis = openItem ? analyses[openItem.bucket]?.[openItem.idx] : undefined;
  const openAnnotation = openItem ? annotations[openItem.bucket]?.[openItem.idx] : undefined;
  // Demo roles link "Full analysis" to their pre-baked canned analysis page (no live /analyze).
  const openAnalysisId = isDemo ? demoAnalysisIdFromUrl(openInternship?.application_url) : null;
  const openAnalysisHref = openAnalysisId ? `/analyze/${openAnalysisId}` : null;

  // Stat-card numbers — global (unfiltered), live as scoring lands.
  const bandsAll = feedItems.map((i) => bandOf(analyses[i.bucket]?.[i.idx]));
  const strongCount = bandsAll.filter((b) => b === "strong").length;
  const notfitAll = feedItems.filter((_, i) => bandsAll[i] === "notfit");
  const top = feedItems.reduce<{ company: string; band: Band; score: number } | null>((acc, item, i) => {
    const band = bandsAll[i];
    if (!band || band === "notfit") return acc;
    const s = fitScoreOf(analyses[item.bucket]?.[item.idx]);
    if (acc && acc.score >= s) return acc;
    return { company: data.internships[item.bucket][item.idx].company, band, score: s };
  }, null);
  const chipCount = (f: Filter) => (f === "all" ? feedItems.length : feedItems.filter((i) => i.bucket === f).length);
  const notfitRows = groups.notfit.map((item) => {
    const it = data.internships[item.bucket][item.idx];
    const a = analyses[item.bucket]?.[item.idx];
    return {
      url: item.url,
      title: it.title,
      company: it.company,
      location: it.location,
      why: a?.status === "ok" ? a.data.verdict.reasoning : "",
    };
  });

  // Cumulative stagger across the banded view so rows rise in one page-wide sequence.
  let delayCursor = 0;
  const takeDelay = () => delayCursor++;

  return (
    <AppShell active="feed">
      <div className="topbar">
        <div>
          <h1 className="pg">Your matches</h1>
          <p className="pg-sub">{feedItems.length} roles ranked to {firstName}&rsquo;s profile · refreshed {refreshedLabel(id)}</p>
        </div>
      </div>

      {/* Profile strip */}
      <div className="profile-strip">
        <div className="avatar">{initial}</div>
        <div className="who">
          <b>{profile.full_name}</b>
          <span className="who-sub">{profile.headline || profile.field_of_interest}</span>
        </div>
        <div className="run-meta">{profile.school}{profile.major ? ` · ${profile.major}` : ""}</div>
      </div>

      {/* Stat cards (option-j results.html) — hidden while scoring (would show zeros / "—"). */}
      {!needsSignIn && !scoring && (
        <div className="stats">
          <div className="stat-card">
            <div className="sl">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden><circle cx="12" cy="12" r="9" /><path d="m15.5 8.5-2 5-5 2 2-5z" /></svg>
              Roles matched
            </div>
            <div className="sv">{feedItems.length}</div>
          </div>
          <div className="stat-card">
            <div className="sl strong">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d="M3 17 9 11l4 4 8-8m0 0h-5m5 0v5" /></svg>
              Strong matches
            </div>
            <div className="sv">{strongCount}</div>
          </div>
          <div className="stat-card">
            <div className="sl">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden><rect x="3" y="4" width="18" height="4" rx="1" /><path d="M5 8v11a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8" /><path d="M10 12h4" /></svg>
              Set aside
            </div>
            <div className="sv">{notfitAll.length} <span className="hint2">graded, not hidden</span></div>
          </div>
          <div className="stat-card">
            <div className="sl">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d="M12 3.5l2.6 5.3 5.9.9-4.3 4.1 1 5.8-5.2-2.7-5.2 2.7 1-5.8L4.5 9.7l5.9-.9L12 3.5Z" /></svg>
              Top match
            </div>
            <div className="sv">{top?.company ?? "—"}{top && <span className="hint2">{top.band === "look" ? "worth a look" : top.band}</span>}</div>
          </div>
        </div>
      )}

      {/* Toolbar: company-type filter chips + sort segment — hidden until scoring completes. */}
      {!needsSignIn && !scoring && (
        <div className="toolbar">
          <div className="chips" role="group" aria-label="Filter by company type">
            {FILTER_CHIPS.map((c) => (
              <button key={c.f} className={`chip${filter === c.f ? " on" : ""}`} onClick={() => setFilter(c.f)}>
                {c.label} <span className="cnt">{chipCount(c.f)}</span>
              </button>
            ))}
          </div>
          <div className="sortrow">
            Sort{" "}
            <span className="seg">
              <button className={sort === "best" ? "on" : ""} onClick={() => setSort("best")}>Best fit</button>
              <button className={sort === "new" ? "on" : ""} onClick={() => setSort("new")}>Newest</button>
            </span>
          </div>
        </div>
      )}

      <section className="feed" style={{ paddingTop: needsSignIn ? 34 : 18 }}>
        {needsSignIn && !authLoading && (
          <div style={{ marginBottom: 22 }}>
            <SignInGate
              onSubmit={signInWithOtp}
              title="Sign in to reveal your match scores"
              subtitle="Your roles are ready below. Sign in (one-tap magic link) to rank them by fit and see why you match each one."
            />
          </div>
        )}

        {needsSignIn ? (
          <div className="roles">{feedItems.map((i) => renderCard(i))}</div>
        ) : scoring ? (
          <>
            <div className="feed-loading">
              <span className="az-spinner" />
              <span>Scoring your {feedItems.length} match{feedItems.length === 1 ? "" : "es"}…</span>
            </div>
            <div className="roles">{feedItems.map((i, n) => renderCard(i, n))}</div>
          </>
        ) : (
          <div key={`${sort}-${filter}`}>
            {sort === "best" ? (
              <>
                {BAND_KEYS.map((b) =>
                  groups[b].length > 0 ? (
                    <BandSection key={b} band={b} count={groups[b].length}>
                      {groups[b].map((i) => renderCard(i, takeDelay()))}
                    </BandSection>
                  ) : null,
                )}
                {groups.pending.length > 0 && (
                  <BandSection band="pending" count={groups.pending.length}>
                    {groups.pending.map((i) => renderCard(i, takeDelay()))}
                  </BandSection>
                )}
              </>
            ) : (
              <div className="roles stagger">{newestItems.map((i, n) => renderCard(i, n))}</div>
            )}
            {filter === "all" && <NotFitBlock rows={notfitRows} />}
            {visibleItems.length === 0 && (
              <p className="pg-sub" style={{ marginTop: 24 }}>
                {feedItems.length === 0 ? "No roles found for this run." : "No roles of this type — try another filter."}
              </p>
            )}
          </div>
        )}
      </section>

      <RoleDrawer
        open={!!openItem}
        internship={openInternship}
        bucket={openItem?.bucket ?? null}
        band={openAnalysis ? bandOf(openAnalysis) : null}
        analysis={openAnalysis}
        annotation={openAnnotation}
        saved={openItem ? isSaved(openItem.url) : false}
        gated={needsSignIn}
        sample={isDemo}
        analysisHref={openAnalysisHref}
        onClose={() => setOpenUrl(null)}
        onToggleSave={() => { if (openItem && openInternship) toggleSaved({ url: openItem.url, internship: openInternship, bucket: openItem.bucket }); }}
      />
    </AppShell>
  );
}
