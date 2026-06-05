import Link from "next/link";
import { timeAgo, type RunIndexEntry } from "@/lib/storage";

interface Props {
  runs: RunIndexEntry[];
  onRemove: (runId: string) => void;
}

/** Home-page list of previously-saved runs (localStorage history). */
export function PreviousRuns({ runs, onRemove }: Props) {
  if (runs.length === 0) return null;

  return (
    <section className="flex flex-col gap-3">
      <div className="flex items-center gap-3">
        <span className="mono text-xs uppercase tracking-widest" style={{ color: "var(--text-secondary)" }}>
          previous runs
        </span>
        <div className="flex-1 border-t" style={{ borderColor: "var(--border)" }} />
      </div>

      <ul className="flex flex-col gap-2">
        {runs.map((r) => (
          <li
            key={r.runId}
            className="flex items-center justify-between gap-3 border px-4 py-3 transition-colors
                       hover:border-[var(--accent)]"
            style={{ borderColor: "var(--border)", background: "var(--surface)" }}
          >
            <Link href={`/results/${r.runId}`} className="flex-1 min-w-0 flex flex-col gap-0.5">
              <span className="text-sm truncate" style={{ color: "var(--text-primary)" }}>
                {r.name}
                {r.sublabel && (
                  <span style={{ color: "var(--text-secondary)" }}> · {r.sublabel}</span>
                )}
              </span>
              <span className="mono text-xs" style={{ color: "var(--text-secondary)" }}>
                {timeAgo(r.savedAt)}
              </span>
            </Link>
            <button
              type="button"
              onClick={() => onRemove(r.runId)}
              className="mono text-xs shrink-0 hover:opacity-70 transition-opacity"
              style={{ color: "var(--text-secondary)" }}
              aria-label={`Remove ${r.name} from history`}
            >
              ×
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
