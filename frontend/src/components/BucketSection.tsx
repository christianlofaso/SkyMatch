import type { Internship } from "@/types/pathfinder";
import { InternshipCard } from "./InternshipCard";

const BUCKET_LABELS: Record<string, string> = {
  local: "Local",
  big_tech: "Big Tech",
  startup: "Startup",
  reach: "Reach",
};

export function BucketSection({
  bucket,
  internships,
}: {
  bucket: string;
  internships: Internship[];
}) {
  const label = BUCKET_LABELS[bucket] ?? bucket;

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
          {internships.map((internship, i) => (
            <InternshipCard key={i} internship={internship} />
          ))}
        </div>
      )}
    </div>
  );
}
