import type { ReactNode } from "react";
import { type Band, BAND_LABEL } from "@/lib/bands";

// A readiness band group: the band header (label + count + rule line) over a .roles stack.
// `pending` is the transient pre-score group ("Scoring your matches") roles sit in until their
// /analyze/batch verdict lands and they move into strong/look/stretch.
export function BandSection({
  band,
  count,
  children,
}: {
  band: Band | "pending";
  count: number;
  children: ReactNode;
}) {
  const label = band === "pending" ? "Scoring your matches" : BAND_LABEL[band];
  const headClass = band === "pending" ? "" : band;
  return (
    <div className="band-group">
      <div className={`band-head ${headClass}`}>
        {label} <span className="cnt">{count}</span>
        <span className="rule" />
      </div>
      <div className="roles stagger">{children}</div>
    </div>
  );
}
