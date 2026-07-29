"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import type { AnalysisResponse } from "@/types/skymatch";
import AnalysisView from "@/components/AnalysisView";
import { getAnalysis, activeRunId } from "@/lib/storage";
import { DEMO_RUN_ID } from "@/lib/demoRun";

export default function AnalysisResultPage() {
  const { analysisId } = useParams<{ analysisId: string }>();
  const [data, setData] = useState<AnalysisResponse | null>(null);
  const [error, setError] = useState("");
  const [runId, setRunId] = useState<string | null>(null);

  useEffect(() => {
    // Canned demo analyses (`demo-*`) belong to the sample run — send "Back to results" there.
    setRunId(analysisId?.startsWith("demo-") ? DEMO_RUN_ID : activeRunId());
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
      <main className="wrap" style={{ paddingTop: 60 }}>
        <p style={{ color: "var(--danger)" }}>{error}</p>
        <Link href="/analyze" style={{ color: "var(--ember-soft)", fontFamily: "var(--mono)", fontSize: 13 }}>← New analysis</Link>
      </main>
    );
  }

  if (!data) {
    return (
      <main style={{ minHeight: "60vh", display: "grid", placeItems: "center" }}>
        <span className="az-spinner" />
      </main>
    );
  }

  return (
    <main className="wrap" style={{ paddingBottom: 80 }}>
      <div className="bg-fx"><div className="mesh" /><div className="topo" /></div>

      <div className="acol" style={{ margin: "0 auto", paddingTop: 24 }}>
        {/* Nav */}
        <div style={{ display: "flex", gap: 18, flexWrap: "wrap", marginBottom: 18 }}>
          {runId && <Link href={`/results/${runId}`} className="signin" style={{ paddingLeft: 0 }}>← Back to results</Link>}
          <Link href="/analyze" className="signin" style={{ paddingLeft: 0 }}>New analysis</Link>
          <Link href="/" className="signin" style={{ paddingLeft: 0 }}>Start over</Link>
        </div>

        <AnalysisView data={data} />
      </div>
    </main>
  );
}
