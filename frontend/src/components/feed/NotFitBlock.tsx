"use client";
import { useState } from "react";

// The collapsed "Not a fit right now" block (option-j results.html .notfit-block):
// skip-verdict roles stay on the page — graded, not hidden. Each expanded row shows the
// role + the quick verdict's reasoning as the one-line why.
export interface NotFitRow {
  url: string;
  title: string;
  company: string;
  location: string;
  why: string;
}

export function NotFitBlock({ rows }: { rows: NotFitRow[] }) {
  const [open, setOpen] = useState(false);
  if (rows.length === 0) return null;

  return (
    <div className="notfit-block">
      <button
        type="button"
        className="notfit"
        aria-expanded={open}
        aria-controls="notfit-list"
        onClick={() => setOpen((o) => !o)}
      >
        <span>Not a fit right now · {rows.length} role{rows.length !== 1 ? "s" : ""}</span>
        <span className="hint">graded, not hidden · {open ? "hide them ↑" : "show them ↓"}</span>
      </button>
      {open && (
        <div className="notfit-list" id="notfit-list">
          {rows.map((r) => (
            <div className="nf-row" key={r.url}>
              <div className="nf-meta">
                <b>{r.title}</b>
                <span>{r.company}{r.location ? ` · ${r.location}` : ""}</span>
              </div>
              {r.why && <p className="nf-why">{r.why}</p>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
