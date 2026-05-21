import type { Internship } from "@/types/pathfinder";

export function InternshipCard({ internship }: { internship: Internship }) {
  return (
    <div className="border border-[var(--border)] p-4 flex flex-col gap-3">
      {/* Title + company */}
      <div>
        <h4 className="mono font-semibold text-sm">{internship.title}</h4>
        <p className="text-xs mt-0.5" style={{ color: "var(--text-secondary)" }}>
          {internship.company} · {internship.location}
        </p>
      </div>

      {/* Company description */}
      <p className="text-xs" style={{ color: "var(--text-secondary)" }}>
        {internship.company_description}
      </p>

      {/* Why you fit */}
      <div>
        <p className="mono text-xs uppercase tracking-wider mb-1" style={{ color: "var(--accent)" }}>
          Why you fit
        </p>
        <p className="text-xs leading-relaxed" style={{ color: "var(--text-secondary)" }}>
          {internship.fit_explanation}
        </p>
      </div>

      {/* Reach gap — only for reach bucket */}
      {internship.reach_gap && (
        <div
          className="pl-3 pt-2 text-xs leading-relaxed"
          style={{ borderLeft: "2px solid var(--accent)", color: "var(--text-secondary)" }}
        >
          <span className="mono uppercase tracking-wider text-xs" style={{ color: "var(--accent)" }}>
            Gap to close{" "}
          </span>
          {internship.reach_gap}
        </div>
      )}

      {/* Apply link */}
      {internship.application_url && (
        <a
          href={internship.application_url}
          target="_blank"
          rel="noopener noreferrer"
          className="mono text-xs self-start hover:underline"
          style={{ color: "var(--accent)" }}
        >
          Apply →
        </a>
      )}
    </div>
  );
}
