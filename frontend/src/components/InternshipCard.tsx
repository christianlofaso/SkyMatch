import { useState } from "react";
import { useRouter } from "next/navigation";
import type { Internship, QuickAnalysisResponse } from "@/types/pathfinder";
import { VERDICT_LABEL, VERDICT_COLOR, scoreColor, type VerdictCall } from "@/lib/constants";

export type CardAnalysisState =
  | { status: "loading" }
  | { status: "ok"; data: QuickAnalysisResponse }
  | { status: "error"; message: string };

// Deferred "why you fit" text streamed by /internships/annotate (see lib/api.annotateFit).
export type CardAnnotationState =
  | { status: "loading" }
  | { status: "ok"; fit_explanation: string; reach_gap: string | null }
  | { status: "error" };

interface Props {
  internship: Internship;
  analysis?: CardAnalysisState;
  annotation?: CardAnnotationState;
  onRetry?: () => void;
  // Lazy trigger: called on the first expand of an un-annotated card to fetch its "why you fit".
  onRequestAnnotation?: () => void;
}

export function InternshipCard({ internship, analysis, annotation, onRetry, onRequestAnnotation }: Props) {
  const [expanded, setExpanded] = useState(false);
  // Prefer the freshly-streamed annotation; fall back to whatever shipped on the feed (usually "").
  const fit =
    annotation?.status === "ok" ? annotation.fit_explanation : internship.fit_explanation;
  const reachGap =
    annotation?.status === "ok" ? annotation.reach_gap : internship.reach_gap;
  const fitLoading = annotation?.status === "loading" && !internship.fit_explanation;
  const router = useRouter();

  function openFullAnalysis() {
    if (!internship.application_url) return;
    router.push(`/analyze?url=${encodeURIComponent(internship.application_url)}`);
  }

  // Whole card is a click-to-expand accordion. The "why you fit" reasoning is generated lazily
  // (one /internships/annotate call) on the FIRST expand of a card that isn't already annotated —
  // nothing fires on page load. The page-side guard dedupes, so re-expands don't refetch.
  function toggle() {
    const next = !expanded;
    setExpanded(next);
    if (next && annotation?.status !== "ok" && !internship.fit_explanation) {
      onRequestAnnotation?.();
    }
  }

  return (
    <div
      role="button"
      tabIndex={0}
      aria-expanded={expanded}
      onClick={toggle}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          toggle();
        }
      }}
      className="border border-[var(--border)] p-4 flex flex-col gap-3 cursor-pointer
                 hover:border-[var(--accent)] transition-colors focus:outline-none
                 focus-visible:ring-1 focus-visible:ring-[var(--accent)]"
    >
      {/* Title + company + badge + expand chevron */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <h4 className="mono font-semibold text-sm">{internship.title}</h4>
          <p className="text-xs mt-0.5" style={{ color: "var(--text-secondary)" }}>
            {internship.company} · {internship.location}
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {internship.application_url && (
            // stopPropagation: clicking the badge opens full analysis / retries, never toggles.
            <span onClick={(e) => e.stopPropagation()}>
              <JobAnalysisBadge analysis={analysis} onRetry={onRetry} onClick={openFullAnalysis} />
            </span>
          )}
          <span
            className="mono text-xs select-none"
            style={{ color: "var(--text-secondary)" }}
            aria-hidden
          >
            {expanded ? "▾" : "▸"}
          </span>
        </div>
      </div>

      {!expanded ? (
        // Collapsed affordance — signals the reasoning is one click away (not yet generated).
        <p className="mono text-[10px] uppercase tracking-wider" style={{ color: "var(--text-secondary)" }}>
          Why you fit →
        </p>
      ) : (
        <>
          {/* Company description */}
          <p className="text-xs" style={{ color: "var(--text-secondary)" }}>
            {internship.company_description}
          </p>

          {/* Why you fit — fetched lazily on expand by /internships/annotate. Only rendered while
              loading or once text arrives, so a failed/empty annotation doesn't leave a blank label. */}
          {(fitLoading || fit) && (
            <div>
              <p className="mono text-xs uppercase tracking-wider mb-1" style={{ color: "var(--accent)" }}>
                Why you fit
              </p>
              {fitLoading ? (
                <div className="space-y-1.5 animate-pulse" aria-label="loading fit">
                  <div className="h-2.5 rounded" style={{ background: "var(--border)", width: "100%" }} />
                  <div className="h-2.5 rounded" style={{ background: "var(--border)", width: "75%" }} />
                </div>
              ) : (
                <p className="text-xs leading-relaxed" style={{ color: "var(--text-secondary)" }}>
                  {fit}
                </p>
              )}
            </div>
          )}

          {/* Reach gap — only for reach bucket */}
          {reachGap && (
            <div
              className="pl-3 pt-2 text-xs leading-relaxed"
              style={{ borderLeft: "2px solid var(--accent)", color: "var(--text-secondary)" }}
            >
              <span className="mono uppercase tracking-wider text-xs" style={{ color: "var(--accent)" }}>
                Gap to close{" "}
              </span>
              {reachGap}
            </div>
          )}

          {/* Apply link — stopPropagation so it opens the listing instead of toggling the card. */}
          {internship.application_url && (
            <a
              href={internship.application_url}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="mono text-xs self-start hover:underline"
              style={{ color: "var(--accent)" }}
            >
              Apply →
            </a>
          )}
        </>
      )}
    </div>
  );
}

function JobAnalysisBadge({
  analysis,
  onRetry,
  onClick,
}: {
  analysis?: CardAnalysisState;
  onRetry?: () => void;
  onClick: () => void;
}) {
  if (!analysis || analysis.status === "loading") {
    return (
      <div
        className="mono text-[10px] px-2 py-1 border shrink-0 animate-pulse"
        style={{ borderColor: "var(--border)", color: "var(--text-secondary)" }}
      >
        analyzing…
      </div>
    );
  }
  if (analysis.status === "error") {
    return (
      <button
        type="button"
        onClick={onRetry}
        className="mono text-[10px] px-2 py-1 border shrink-0 hover:opacity-70"
        style={{ borderColor: "#7f1d1d", color: "#ff6b6b" }}
        title={analysis.message}
      >
        retry
      </button>
    );
  }
  const { fit_score, verdict } = analysis.data;
  const color = VERDICT_COLOR[verdict.call as VerdictCall];
  const label = VERDICT_LABEL[verdict.call as VerdictCall] ?? verdict.call;
  return (
    <button
      type="button"
      onClick={onClick}
      className="mono text-[10px] px-2 py-1 border shrink-0 flex items-center gap-1.5 hover:opacity-80 transition-opacity"
      style={{ borderColor: color, color }}
      title={`${fit_score} — open full analysis`}
    >
      <span className="font-semibold" style={{ color: scoreColor(fit_score) }}>
        {fit_score}
      </span>
      <span className="uppercase tracking-wider">{label}</span>
    </button>
  );
}
