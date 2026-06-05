"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import type { AnalysisResponse } from "@/types/pathfinder";
import VerdictCard from "@/components/VerdictCard";
import BreakdownView from "@/components/BreakdownView";
import { getAnalysis, latestRunId } from "@/lib/storage";

export default function AnalysisResultPage() {
  const { analysisId } = useParams<{ analysisId: string }>();
  const [data, setData] = useState<AnalysisResponse | null>(null);
  const [error, setError] = useState("");
  const [showBreakdown, setShowBreakdown] = useState(false);
  const [runId, setRunId] = useState<string | null>(null);

  useEffect(() => {
    setRunId(latestRunId());
    if (!analysisId) return;
    const analysis = getAnalysis(analysisId);
    if (!analysis) {
      setError("Couldn't find that analysis — it may have been cleared.");
      return;
    }
    setData(analysis);
  }, [analysisId]);

  if (error) {
    return (
      <main className="min-h-screen flex flex-col items-center justify-center px-6 py-20">
        <div className="w-full max-w-xl flex flex-col gap-6">
          <p className="text-sm" style={{ color: "#ff6b6b" }}>{error}</p>
          <Link
            href="/analyze"
            className="mono text-sm"
            style={{ color: "var(--accent)" }}
          >
            ← new analysis
          </Link>
        </div>
      </main>
    );
  }

  if (!data) {
    return (
      <main className="min-h-screen flex items-center justify-center">
        <span
          className="inline-block w-2 h-2 rounded-full animate-pulse"
          style={{ background: "var(--accent)" }}
        />
      </main>
    );
  }

  return (
    <main className="min-h-screen flex flex-col items-center px-6 py-20">
      <div className="w-full max-w-xl flex flex-col gap-8">

        {/* Nav */}
        <div className="flex items-center gap-3 flex-wrap">
          {runId && (
            <Link
              href={`/results/${runId}`}
              className="mono text-xs font-medium px-3 py-1.5 border border-[var(--border)]
                         hover:bg-[var(--accent)] hover:text-black hover:border-[var(--accent)]
                         transition-colors"
              style={{ color: "var(--accent)" }}
            >
              ← back to results
            </Link>
          )}
          <Link
            href="/analyze"
            className="mono text-xs hover:opacity-70 transition-opacity"
            style={{ color: "var(--text-secondary)" }}
          >
            new analysis
          </Link>
          <Link
            href="/"
            className="mono text-xs hover:opacity-70 transition-opacity"
            style={{ color: "var(--text-secondary)" }}
          >
            start over
          </Link>
        </div>

        {/* Verdict or breakdown */}
        {showBreakdown ? (
          <BreakdownView data={data} onBack={() => setShowBreakdown(false)} />
        ) : (
          <VerdictCard data={data} onShowBreakdown={() => setShowBreakdown(true)} />
        )}

      </div>
    </main>
  );
}
