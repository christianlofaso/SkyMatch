import type { Internship } from "@/types/pathfinder";
import { InternshipCard, type CardAnalysisState, type CardAnnotationState } from "./InternshipCard";

const BUCKET_LABELS: Record<string, string> = {
  local: "Local",
  big_tech: "Big Tech",
  startup: "Startup",
  reach: "Reach",
};

export type SortMode = "fit" | "recency";

interface Props {
  bucket: string;
  internships: Internship[];
  analyses?: Record<number, CardAnalysisState>;  // keyed by original index in `internships`
  annotations?: Record<number, CardAnnotationState>;  // keyed by original index in `internships`
  sort?: SortMode;
  gated?: boolean;  // auth gate active → cards show a locked score pill, no LLM fired
  onRetry?: (origIndex: number) => void;
  onRequestAnnotation?: (origIndex: number) => void;
}

function sortIndices(
  internships: Internship[],
  analyses: Record<number, CardAnalysisState> | undefined,
  sort: SortMode,
): number[] {
  const indices = internships.map((_, i) => i);
  if (sort === "fit") {
    indices.sort((a, b) => fitOf(analyses?.[b]) - fitOf(analyses?.[a]));
  } else {
    indices.sort((a, b) => postedAt(analyses?.[b]).localeCompare(postedAt(analyses?.[a])));
  }
  return indices;
}

function fitOf(s: CardAnalysisState | undefined): number {
  return s?.status === "ok" ? s.data.fit_score : -1;
}

function postedAt(s: CardAnalysisState | undefined): string {
  return (s?.status === "ok" && s.data.job_summary.posted_at) || "";
}

export function BucketSection({ bucket, internships, analyses, annotations, sort = "fit", gated, onRetry, onRequestAnnotation }: Props) {
  const label = BUCKET_LABELS[bucket] ?? bucket;
  const order = sortIndices(internships, analyses, sort);

  return (
    <div className="flex flex-col gap-4">
      {/* Section header */}
      <div className="flex items-baseline gap-3 border-b pb-2" style={{ borderColor: "var(--border)" }}>
        <h3 className="mono text-sm font-semibold uppercase tracking-widest" style={{ color: "var(--accent)" }}>
          {label}
        </h3>
        <span className="mono text-xs" style={{ color: "var(--text-secondary)" }}>
          {internships.length} role{internships.length !== 1 ? "s" : ""}
        </span>
      </div>

      {internships.length === 0 ? (
        <p className="text-xs" style={{ color: "var(--text-secondary)" }}>
          No roles found for this bucket.
        </p>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {order.map((i) => (
            <InternshipCard
              key={i}
              internship={internships[i]}
              analysis={analyses?.[i]}
              annotation={annotations?.[i]}
              gated={gated}
              onRetry={onRetry ? () => onRetry(i) : undefined}
              onRequestAnnotation={onRequestAnnotation ? () => onRequestAnnotation(i) : undefined}
            />
          ))}
        </div>
      )}
    </div>
  );
}
