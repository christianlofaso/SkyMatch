"use client";

import Link from "next/link";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { analyzeJobStream } from "@/lib/api";
import {
  AnalysisResponseSchema,
  type AnalysisResponse,
  type UnifiedProfile,
} from "@/types/pathfinder";
import AnalysisView from "@/components/AnalysisView";
import { AppShell } from "@/components/AppShell";
import { SignInGate } from "@/components/SignInGate";
import { useAuth } from "@/lib/auth-context";
import { getRun, activeRunId, saveAnalysis, hasUsedFreeAnalysis, markFreeAnalysisUsed } from "@/lib/storage";

// "loading" = waiting for the verdict (fetch+extract+match); "streaming" = verdict shown,
// Phase 3 filling in; "done" = stream complete; "error" = failed.
type Status = "idle" | "loading" | "streaming" | "done" | "error";

const AZ_STEPS = ["Reading the posting", "Extracting requirements", "Matching your evidence", "Writing the verdict"];

// option-j checklist loader — a visual cadence over the real stream (settles when the verdict arrives).
function AzLoader() {
  const [i, setI] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setI((p) => Math.min(p + 1, AZ_STEPS.length - 1)), 520);
    return () => clearInterval(t);
  }, []);
  return (
    <div className="azload" aria-live="polite">
      <div className="az-spinner" aria-hidden />
      <div className="az-steps">
        {AZ_STEPS.map((s, n) => (
          <div className={`az-step${n <= i ? " on" : ""}`} key={n}><span className="ad" /> {s}</div>
        ))}
      </div>
      <div className="az-bar"><i style={{ width: `${(Math.min(i + 1, AZ_STEPS.length) / AZ_STEPS.length) * 100}%` }} /></div>
    </div>
  );
}

function AnalyzePageInner() {
  const searchParams = useSearchParams();
  const prefilledUrl = searchParams.get("url") ?? "";

  const [profile, setProfile] = useState<UnifiedProfile | null>(null);
  const [box, setBox] = useState(prefilledUrl);
  const [status, setStatus] = useState<Status>("idle");
  const [errorMsg, setErrorMsg] = useState("");
  const [result, setResult] = useState<AnalysisResponse | null>(null);
  const [roadmapDone, setRoadmapDone] = useState(false);
  const [projectDone, setProjectDone] = useState(false);
  const autoSubmittedRef = useRef(false);

  // Auth gate: standalone analyzer = "one free, then sign in". Anonymous users get one run;
  // the second is gated (best-effort localStorage flag — backend's 5/day quota is the real cap).
  const { session, authRequired, loading: authLoading, signInWithOtp } = useAuth();
  const mustGate = authRequired && !session && !authLoading && hasUsedFreeAnalysis();

  // On mount: pick up the profile from the active run (the one being viewed this tab).
  useEffect(() => {
    const id = activeRunId();
    setProfile(id ? getRun(id)?.profile ?? null : null);
  }, []);

  const runAnalysis = useCallback(
    async (input: { job_url?: string; job_text?: string }) => {
      if (!profile) return;
      // Hard gate (defense-in-depth): an anonymous user who already used their free run must
      // NEVER fire a request — even if `mustGate` hasn't settled (auth still resolving).
      if (authRequired && !session && hasUsedFreeAnalysis()) return;
      if (authRequired && !session) markFreeAnalysisUsed();
      setStatus("loading");
      setErrorMsg("");
      setResult(null);
      setRoadmapDone(false);
      setProjectDone(false);

      const analysisId = Date.now().toString(36);
      let acc: AnalysisResponse | null = null;

      try {
        for await (const env of analyzeJobStream(profile, input)) {
          if (env.phase === "verdict") {
            acc = {
              fit_score: env.fit_score ?? 0,
              category_scores: env.category_scores ?? {},
              matches: env.matches ?? [],
              gaps: env.gaps ?? [],
              verdict: env.verdict ?? { call: "skip", reasoning: "" },
              job_summary: env.job_summary ?? { title: "", company: "", key_requirements: [] },
            };
            setResult(acc);
            setStatus("streaming");
          } else if (env.phase === "roadmap") {
            if (!acc) continue;
            const merged: AnalysisResponse = { ...acc, roadmap: env.roadmap ?? null, roadmap_note: env.roadmap_note ?? null };
            acc = merged;
            setResult(merged);
            setRoadmapDone(true);
          } else if (env.phase === "project") {
            if (!acc) continue;
            const merged: AnalysisResponse = { ...acc, project_suggestion: env.project_suggestion ?? null };
            acc = merged;
            setResult(merged);
            setProjectDone(true);
          } else if (env.phase === "done") {
            setRoadmapDone(true);
            setProjectDone(true);
            if (acc) {
              const parsed = AnalysisResponseSchema.safeParse(acc);
              const final = parsed.success ? parsed.data : acc;
              saveAnalysis(analysisId, final);
              setResult(final);
            }
            setStatus("done");
          } else if (env.phase === "error") {
            setErrorMsg(env.error?.message ?? "Something went wrong.");
            setStatus("error");
            return;
          }
        }
        setStatus((s) => (s === "streaming" ? "done" : s === "loading" ? "error" : s));
      } catch (err) {
        setErrorMsg(err instanceof Error ? err.message : "Something went wrong.");
        setStatus("error");
      }
    },
    [profile, authRequired, session],
  );

  // Auto-submit when arriving with ?url=... once profile AND auth have resolved (unless gated).
  useEffect(() => {
    if (!profile || !prefilledUrl || autoSubmittedRef.current || authLoading || mustGate) return;
    autoSubmittedRef.current = true;
    runAnalysis({ job_url: prefilledUrl });
  }, [profile, prefilledUrl, runAnalysis, mustGate, authLoading]);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!profile || authLoading || mustGate) return;
    const v = box.trim();
    if (!v) return;
    // Single box accepts a URL or pasted text (option-j UX): route by whether it looks like a URL.
    const input = /^https?:\/\//i.test(v) ? { job_url: v } : { job_text: v };
    void runAnalysis(input);
  }

  function submitSample(text: string) {
    setBox(text);
    void runAnalysis({ job_text: text });
  }

  function reset() {
    setStatus("idle");
    setResult(null);
    setErrorMsg("");
    setBox("");
  }

  const loading = status === "loading";
  const showResults = result !== null && (status === "streaming" || status === "done");

  return (
    <AppShell active="analyzer">
      <div className="topbar">
        <div>
          <h1 className="pg">Job fit analyzer</h1>
          <p className="pg-sub">Paste any posting · get a verdict, a gap map, and a plan</p>
        </div>
      </div>

      {showResults && result ? (
        <div style={{ paddingTop: 8 }}>
          <AnalysisView data={result} roadmapDone={roadmapDone} projectDone={projectDone} />
          <div className="acol" style={{ margin: "0 auto" }}>
            <div className="bottom-strip">
              <button type="button" onClick={reset} className="btn btn-ghost">← Analyze another job</button>
            </div>
          </div>
        </div>
      ) : (
        <div className="azwrap">
          <div className="az-ico" aria-hidden>
            <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="11" cy="11" r="7" /><path d="m21 21-4.3-4.3" />
            </svg>
          </div>
          <h1>Analyze any <span className="em-warm">job posting</span>.</h1>
          <p className="sub">Paste a link or the full description. We grade your fit, map the gaps, and build a plan to close them.</p>

          {!profile && (
            <div className="azcard" style={{ textAlign: "center" }}>
              <p style={{ color: "var(--muted)" }}>No profile found in this session.</p>
              <Link href="/" style={{ color: "var(--ember-soft)", fontFamily: "var(--mono)", fontSize: 13.5 }}>Run your profile first →</Link>
            </div>
          )}

          {profile && authLoading && (
            <div className="azcard"><div className="azload"><div className="az-spinner" /></div></div>
          )}

          {profile && !authLoading && mustGate && (
            <div style={{ marginTop: 18 }}>
              <SignInGate
                onSubmit={signInWithOtp}
                title="Sign in to keep analyzing"
                subtitle="You've used your free analysis. Sign in (one-tap magic link) to run more."
              />
            </div>
          )}

          {profile && !authLoading && !mustGate && (
            <>
              <div className="azcard">
                {loading ? (
                  <AzLoader />
                ) : (
                  <form onSubmit={handleSubmit}>
                    <label htmlFor="azbox">Job URL or pasted description</label>
                    <textarea
                      id="azbox"
                      className="azbox"
                      value={box}
                      onChange={(e) => setBox(e.target.value)}
                      placeholder="https://stripe.com/jobs/... or paste the full posting text here"
                    />
                    <div className="az-actions">
                      <button type="submit" className="btn btn-primary" style={{ "--bh": "46px", fontSize: 14.5 } as React.CSSProperties} disabled={!box.trim()}>
                        Analyze fit <span className="arrow">→</span>
                      </button>
                      <span className="az-meta">graded against {profile.full_name}&rsquo;s profile</span>
                    </div>
                    {status === "error" && errorMsg && (
                      <div className="az-meta" style={{ color: "var(--danger)", marginTop: 12 }}>{errorMsg}</div>
                    )}
                  </form>
                )}
              </div>

              <div className="az-samples">
                <div className="ll">Or try a recent posting</div>
                <div className="sample-row">
                  <button type="button" className="sample-chip" onClick={() => submitSample("Ramp · Software Engineer Intern")}>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><path d="M14 2v6h6" /></svg>
                    Ramp · Software Engineer Intern
                  </button>
                  <button type="button" className="sample-chip" onClick={() => submitSample("NVIDIA · Systems Software Intern")}>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><path d="M14 2v6h6" /></svg>
                    NVIDIA · Systems Software Intern
                  </button>
                </div>
              </div>
            </>
          )}
        </div>
      )}
    </AppShell>
  );
}

export default function AnalyzePage() {
  return (
    <Suspense fallback={<main style={{ minHeight: "60vh", display: "grid", placeItems: "center" }}><span className="az-spinner" /></main>}>
      <AnalyzePageInner />
    </Suspense>
  );
}
