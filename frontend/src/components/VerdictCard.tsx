"use client";

import type { AnalysisResponse } from "@/types/pathfinder";
import { VERDICT_LABEL, VERDICT_COLOR, scoreColor, type VerdictCall } from "@/lib/constants";

interface Props {
  data: AnalysisResponse;
  onShowBreakdown: () => void;
}

const CATEGORY_LABELS: Record<string, string> = {
  technical: "Technical",
  experience: "Experience",
  education: "Education",
  domain: "Domain",
  soft: "Soft Skills",
};

export default function VerdictCard({ data, onShowBreakdown }: Props) {
  const { fit_score, verdict, job_summary, category_scores } = data;
  const color = scoreColor(fit_score);
  const categoryEntries = Object.entries(category_scores).filter(
    ([cat]) => CATEGORY_LABELS[cat]
  );

  return (
    <div className="flex flex-col gap-8">
      {/* Job title + company */}
      <div>
        <p className="mono text-xs uppercase tracking-widest mb-1" style={{ color: "var(--text-secondary)" }}>
          analyzing fit for
        </p>
        <p className="text-base font-semibold" style={{ color: "var(--text-primary)" }}>
          {job_summary.title}
          {job_summary.company && (
            <span style={{ color: "var(--text-secondary)", fontWeight: 400 }}>
              {" "}· {job_summary.company}
            </span>
          )}
        </p>
      </div>

      {/* Score + verdict call */}
      <div
        className="border p-8 flex flex-col items-center gap-4 text-center"
        style={{ borderColor: "var(--border)", background: "var(--surface)" }}
      >
        <p
          className="mono font-semibold"
          style={{ fontSize: "72px", lineHeight: 1, color }}
        >
          {fit_score}
        </p>
        <p
          className="mono text-xl font-semibold tracking-widest"
          style={{ color: VERDICT_COLOR[verdict.call as VerdictCall] ?? color }}
        >
          {VERDICT_LABEL[verdict.call as VerdictCall] ?? verdict.call}
        </p>
        <p
          className="text-sm max-w-sm leading-relaxed"
          style={{ color: "var(--text-primary)" }}
        >
          {verdict.reasoning}
        </p>
      </div>

      {/* Category breakdown */}
      {categoryEntries.length > 0 && (
        <div>
          <p className="mono text-xs uppercase tracking-widest mb-3" style={{ color: "var(--text-secondary)" }}>
            category breakdown
          </p>
          <div className="grid grid-cols-2 gap-2">
            {categoryEntries.map(([cat, score]) => (
              <div
                key={cat}
                className="flex items-center justify-between border px-3 py-2"
                style={{ borderColor: "var(--border)", background: "var(--surface)" }}
              >
                <span className="text-xs" style={{ color: "var(--text-secondary)" }}>
                  {CATEGORY_LABELS[cat] ?? cat}
                </span>
                <span
                  className="mono text-sm font-semibold"
                  style={{ color: scoreColor(score) }}
                >
                  {score}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Key requirements chips */}
      {job_summary.key_requirements.length > 0 && (
        <div>
          <p className="mono text-xs uppercase tracking-widest mb-2" style={{ color: "var(--text-secondary)" }}>
            key requirements
          </p>
          <div className="flex flex-wrap gap-2">
            {job_summary.key_requirements.map((req) => (
              <span
                key={req}
                className="mono text-xs px-2 py-1 border"
                style={{ borderColor: "var(--border)", color: "var(--text-secondary)" }}
              >
                {req}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Expand button */}
      <button
        type="button"
        onClick={onShowBreakdown}
        className="mono px-5 py-3 text-sm font-medium border border-[var(--border)] bg-[var(--surface)]
                   hover:bg-[var(--accent)] hover:text-black hover:border-[var(--accent)]
                   transition-colors"
      >
        see full breakdown →
      </button>
    </div>
  );
}
