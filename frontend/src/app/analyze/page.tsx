"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { analyzeJob } from "@/lib/api";
import type { UnifiedProfile } from "@/types/pathfinder";
import { getRun, latestRunId, saveAnalysis } from "@/lib/storage";

type Tab = "url" | "paste";
type Status = "idle" | "loading" | "error";

export default function AnalyzePage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const prefilledUrl = searchParams.get("url") ?? "";

  const [profile, setProfile] = useState<UnifiedProfile | null>(null);
  const [tab, setTab] = useState<Tab>("url");
  const [url, setUrl] = useState(prefilledUrl);
  const [text, setText] = useState("");
  const [status, setStatus] = useState<Status>("idle");
  const [errorMsg, setErrorMsg] = useState("");
  const autoSubmittedRef = useRef(false);

  // On mount: pick up the profile from the most recent saved run.
  useEffect(() => {
    const id = latestRunId();
    setProfile(id ? getRun(id)?.profile ?? null : null);
  }, []);

  const runAnalysis = useCallback(
    async (input: { job_url?: string; job_text?: string }) => {
      if (!profile) return;
      setStatus("loading");
      setErrorMsg("");
      try {
        const result = await analyzeJob(profile, input, "full");
        const analysisId = Date.now().toString(36);
        saveAnalysis(analysisId, result);
        router.push(`/analyze/${analysisId}`);
      } catch (err) {
        setErrorMsg(err instanceof Error ? err.message : "Something went wrong.");
        setStatus("error");
      }
    },
    [profile, router],
  );

  // Auto-submit when arriving with ?url=... once the profile has loaded.
  useEffect(() => {
    if (!profile || !prefilledUrl || autoSubmittedRef.current) return;
    autoSubmittedRef.current = true;
    setTab("url");
    runAnalysis({ job_url: prefilledUrl });
  }, [profile, prefilledUrl, runAnalysis]);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!profile) return;
    const input = tab === "url"
      ? { job_url: url.trim() }
      : { job_text: text.trim() };
    if (!input.job_url && !input.job_text) return;
    void runAnalysis(input);
  }

  const loading = status === "loading";

  return (
    <main className="min-h-screen flex flex-col items-center justify-center px-6 py-20">
      <div className="w-full max-w-xl flex flex-col gap-10">

        {/* Header */}
        <div>
          <Link
            href="/"
            className="mono text-xs hover:opacity-70 transition-opacity"
            style={{ color: "var(--text-secondary)" }}
          >
            ← back to profile
          </Link>
          <h1 className="mono text-4xl font-semibold tracking-tight mt-4 mb-2" style={{ color: "var(--text-primary)" }}>
            analyze a job
          </h1>
          <p className="text-sm" style={{ color: "var(--text-secondary)" }}>
            Paste a job description or URL. Get a fit score, matched evidence, and a clear verdict.
          </p>
        </div>

        {/* No profile state */}
        {!profile && (
          <div
            className="border p-5 flex flex-col gap-3"
            style={{ borderColor: "var(--border)", background: "var(--surface)" }}
          >
            <p className="text-sm" style={{ color: "var(--text-secondary)" }}>
              No profile found in this session.
            </p>
            <Link
              href="/"
              className="mono text-sm font-medium"
              style={{ color: "var(--accent)" }}
            >
              run your profile first →
            </Link>
          </div>
        )}

        {/* Profile badge */}
        {profile && (
          <div
            className="flex items-center gap-3 border px-4 py-3"
            style={{ borderColor: "var(--border)", background: "var(--surface)" }}
          >
            <span
              className="mono text-xs px-1.5 py-0.5 border shrink-0"
              style={{ borderColor: "var(--accent)", color: "var(--accent)" }}
            >
              profile
            </span>
            <span className="text-sm truncate" style={{ color: "var(--text-primary)" }}>
              {profile.full_name}
              {profile.headline && (
                <span style={{ color: "var(--text-secondary)" }}> · {profile.headline}</span>
              )}
            </span>
          </div>
        )}

        {/* Form — only shown when profile is available */}
        {profile && (
          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            {/* Tab switcher */}
            <div className="flex border-b" style={{ borderColor: "var(--border)" }}>
              {(["url", "paste"] as Tab[]).map((t) => (
                <button
                  key={t}
                  type="button"
                  onClick={() => { setTab(t); setErrorMsg(""); setStatus("idle"); }}
                  className="mono px-4 py-2 text-xs uppercase tracking-widest transition-colors"
                  style={{
                    color: tab === t ? "var(--accent)" : "var(--text-secondary)",
                    borderBottom: tab === t ? "2px solid var(--accent)" : "2px solid transparent",
                    marginBottom: "-1px",
                  }}
                >
                  {t === "url" ? "Job URL" : "Paste JD"}
                </button>
              ))}
            </div>

            {tab === "url" ? (
              <input
                type="url"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://jobs.lever.co/..."
                disabled={loading}
                className="w-full bg-[var(--surface)] border border-[var(--border)] px-4 py-3 text-sm outline-none
                           placeholder:text-[var(--text-secondary)] focus:border-[var(--accent)]
                           transition-colors disabled:opacity-50"
              />
            ) : (
              <textarea
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="Paste the full job description here..."
                disabled={loading}
                rows={10}
                className="w-full bg-[var(--surface)] border border-[var(--border)] px-4 py-3 text-sm outline-none
                           placeholder:text-[var(--text-secondary)] focus:border-[var(--accent)]
                           transition-colors disabled:opacity-50 resize-none"
              />
            )}

            <button
              type="submit"
              disabled={loading || (tab === "url" ? !url.trim() : !text.trim())}
              className="mono px-5 py-3 text-sm font-medium border border-[var(--border)] bg-[var(--surface)]
                         hover:bg-[var(--accent)] hover:text-black hover:border-[var(--accent)]
                         transition-colors disabled:opacity-50"
            >
              {loading ? (
                <span className="flex items-center gap-2">
                  <span
                    className="inline-block w-2 h-2 rounded-full animate-pulse"
                    style={{ background: "var(--accent)" }}
                  />
                  analyzing fit...
                </span>
              ) : (
                "analyze fit →"
              )}
            </button>
          </form>
        )}

        {/* Error */}
        {status === "error" && errorMsg && (
          <div
            className="border p-4 text-sm"
            style={{ borderColor: "#7f1d1d", color: "#ff6b6b" }}
          >
            {errorMsg}
          </div>
        )}

      </div>
    </main>
  );
}
