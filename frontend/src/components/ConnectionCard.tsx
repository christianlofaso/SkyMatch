import type { Connection } from "@/types/pathfinder";

const COMMONALITY_COLORS: Record<string, string> = {
  fraternity: "var(--color-fraternity)",
  school: "var(--color-school)",
  past_company: "var(--color-past_company)",
  field: "var(--color-field)",
  major: "var(--color-major)",
};

const COMMONALITY_LABELS: Record<string, string> = {
  fraternity: "Fraternity",
  school: "School",
  past_company: "Past Company",
  field: "Field",
  major: "Major",
};

export function ConnectionCard({ connection }: { connection: Connection }) {
  const color = COMMONALITY_COLORS[connection.commonality_type] ?? "var(--accent)";
  const label = COMMONALITY_LABELS[connection.commonality_type] ?? connection.commonality_type;

  return (
    <div
      className="border border-[var(--border)] flex flex-col"
      style={{ borderBottom: `4px solid ${color}` }}
    >
      {/* Main content */}
      <div className="p-4 flex flex-col gap-2 flex-1">
        <div>
          <a
            href={connection.linkedin_url}
            target="_blank"
            rel="noopener noreferrer"
            className="mono font-semibold text-base hover:underline"
            style={{ color: "var(--text-primary)" }}
          >
            {connection.name}
          </a>
          <p className="text-sm mt-0.5" style={{ color: "var(--text-secondary)" }}>
            {connection.title} · {connection.company}
          </p>
        </div>

        <p className="text-xs leading-relaxed" style={{ color: "var(--text-secondary)" }}>
          {connection.why_relevant}
        </p>
      </div>

      {/* Commonality bar */}
      <div className="px-4 py-2" style={{ background: `${color}18` }}>
        <p className="mono text-xs uppercase tracking-wider mb-0.5" style={{ color }}>
          {label}
        </p>
        <p className="text-xs" style={{ color: "var(--text-secondary)" }}>
          {connection.commonality_detail}
        </p>
      </div>
    </div>
  );
}
