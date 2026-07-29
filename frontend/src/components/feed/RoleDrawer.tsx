"use client";
import { useEffect, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import type { Internship } from "@/types/skymatch";
import type { BucketKey } from "@/lib/storage";
import type { CardAnalysisState, CardAnnotationState } from "@/lib/cardState";
import { type Band, BAND_LABEL_ONE, BAND_DOT, TYPE_TAG } from "@/lib/bands";
import { LogoBox, BookmarkIcon } from "./LogoBox";
import { TierBars } from "./TierBars";

interface Props {
  open: boolean;
  internship: Internship | null;
  bucket: BucketKey | null;
  band: Band | null;
  analysis?: CardAnalysisState;
  annotation?: CardAnnotationState;
  saved: boolean;
  gated?: boolean;
  // Sample (demo) role: Apply is disabled with a hint, and Full analysis points at the
  // pre-baked canned analysis (analysisHref) instead of running a live /analyze.
  sample?: boolean;
  analysisHref?: string | null;
  onClose: () => void;
  onToggleSave: () => void;
}

// Drawer fact-grid icons — fixed 2-col × 2-row layout:
// Location | Term / Company | Posted. (All four values come from the listing itself.)
const FACT_ICON: Record<string, ReactNode> = {
  Location: <FIco><path d="M12 21s7-6 7-11a7 7 0 1 0-14 0c0 5 7 11 7 11Z" /><circle cx="12" cy="10" r="2.5" /></FIco>,
  Term: <FIco><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3.5 2" /></FIco>,
  Company: <FIco><rect x="5" y="3" width="14" height="18" rx="1.5" /><path d="M9 7h2M13 7h2M9 11h2M13 11h2M9 15h2M13 15h2" /></FIco>,
  Posted: <FIco><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3.5 2" /></FIco>,
};

function FIco({ children }: { children: ReactNode }) {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      {children}
    </svg>
  );
}

// Term shown in the fact grid. Prefer the listing's own parsed `term` (e.g. "Summer 2026",
// "Full-time"); otherwise recover it heuristically from the title/description — a season+year
// ("Summer 2026 Intern", "Fall '25"), else an employment type ("full-time"/"co-op"); "—" when
// nothing is stated.
function termOf(it: Internship): string {
  if (it.term && it.term.trim()) return it.term.trim();
  // Include the application URL: the season often survives only in the slug ("...intern-fall-2026")
  // when the title was cleaned and the stored title/description lost it. Separator allows '-'/'_'.
  const hay = `${it.title} ${it.company_description} ${it.application_url ?? ""}`;
  const m = /\b(spring|summer|fall|autumn|winter)[\s.'’_-]*((?:20)?\d{2})\b/i.exec(hay);
  if (m) {
    const season = m[1].toLowerCase() === "autumn" ? "Fall" : m[1][0].toUpperCase() + m[1].slice(1).toLowerCase();
    const year = m[2].length === 2 ? `20${m[2]}` : m[2];
    return `${season} ${year}`;
  }
  if (/\bco-?op\b/i.test(hay)) return "Co-op";
  if (/\bpart[-\s]?time\b/i.test(hay)) return "Part-time";
  if (/\bfull[-\s]?time\b/i.test(hay)) return "Full-time";
  if (/\bseasonal\b/i.test(hay)) return "Seasonal";
  return "—";
}

// React port of option-j's SMDrawer.open — a right slide-in panel built once and fed the
// currently-open role. Closes on Esc / scrim click, locks body scroll while open. Its rich
// content (why-you-fit bullets, have/need skill chips) comes from the enriched /internships/annotate
// response; facts are reduced to what the backend actually knows (location, type, score, posted).
export function RoleDrawer({
  open, internship, bucket, band, analysis, annotation, saved, gated, sample, analysisHref, onClose, onToggleSave,
}: Props) {
  // Portal target (SSR-safe). MUST render at document.body, like the mockup's SMDrawer:
  // .app .main has a FILLED transform animation (pagein), which makes it a containing block —
  // a fixed drawer rendered inside it would span the page, pushing .dr-actions off-screen.
  const [mounted, setMounted] = useState(false);
  useEffect(() => { setMounted(true); }, []);

  // Esc to close + body-scroll lock while open.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [open, onClose]);

  const it = internship;
  const ann = annotation?.status === "ok" ? annotation : null;
  const annLoading = annotation?.status === "loading";

  // Why-you-fit: prefer the enriched bullets; fall back to the single fit_explanation string.
  const fitText = ann?.fit_explanation || it?.fit_explanation || "";
  const why = ann?.why?.length ? ann.why : fitText ? [fitText] : [];
  const have = ann?.have ?? [];
  const need = ann?.need ?? [];
  const reachGap = (ann?.reach_gap ?? it?.reach_gap) || null;

  // Prefer the ingestion-captured posted date (stable, populated for SPA boards via the SPA
  // render); fall back to the per-request fetch's date when the listing didn't carry one.
  const posted = it?.posted_at || (analysis?.status === "ok" ? analysis.data.job_summary.posted_at : null);

  // Facts grid — four slots in a 2×2: Location (TL) | Term (TR) / Company+size (BL) | Posted (BR).
  // Every value comes from the listing; the Company box appends headcount only when the listing
  // stated it (company_size), and unknown values render as an honest "—".
  const companyFact = it
    ? it.company_size ? `${it.company || "—"} · ${it.company_size}` : (it.company || "—")
    : "—";
  const facts: Array<[string, string]> = it
    ? [
        ["Location", it.location || "—"],
        ["Term", termOf(it)],
        ["Company", companyFact],
        ["Posted", posted || "—"],
      ]
    : [];

  if (!mounted) return null;
  return createPortal(
    <>
      <div className={`scrim${open ? " show" : ""}`} onClick={onClose} aria-hidden />
      <aside className={`drawer${open ? " open" : ""}`} role="dialog" aria-label="Role details" aria-hidden={!open}>
        {it && (
          <>
            <div className="dr-head">
              <div className="dr-eyebrow">
                {band && <span className="dot" style={{ background: BAND_DOT[band] }} />}
                {band ? BAND_LABEL_ONE[band] : "Scoring"}{bucket ? ` · ${TYPE_TAG[bucket]}` : ""}
                <button className="dr-close" onClick={onClose} aria-label="Close details">✕</button>
              </div>
              <div className="dr-title">
                <LogoBox company={it.company} logoUrl={it.logo_url} />
                <div className="dr-name">
                  <h2>{it.title}</h2>
                  <div className="co">{it.company}</div>
                </div>
                {band && (
                  <div className="dr-band">
                    <span className={`band-pill band-${band}`}>
                      <TierBars band={band} /> {BAND_LABEL_ONE[band]}
                    </span>
                  </div>
                )}
              </div>
            </div>

            <div className="dr-body">
              {it.company_description && <p className="about">{it.company_description}</p>}

              {facts.length > 0 && (
                <div className="facts">
                  {facts.map(([l, v]) => (
                    <div className="fact" key={l}>
                      <div className="fl">{FACT_ICON[l]}{l}</div>
                      <div className="fv">{v}</div>
                    </div>
                  ))}
                </div>
              )}

              <div className="fit-label">Why you fit</div>
              {gated ? (
                <p className="grow-label">🔒 Sign in to reveal why you fit.</p>
              ) : annLoading && !why.length ? (
                <div style={{ marginTop: 8 }}>
                  <div className="skel w90" />
                  <div className="skel w70" />
                </div>
              ) : why.length ? (
                <ul className="checks">
                  {why.map((w, i) => <li key={i}>{w}</li>)}
                </ul>
              ) : (
                <p className="grow-label">Expand to generate your personalized fit.</p>
              )}

              {reachGap && (
                <div className="gap-note"><b>Gap to close:</b> {reachGap}</div>
              )}

              {(have.length > 0 || need.length > 0) && (
                <>
                  <div className="fit-label">Skill alignment</div>
                  {have.length > 0 && (
                    <>
                      <div className="dr-sub">You already bring</div>
                      <div className="dr-skills">
                        {have.map((s) => <span className="req-chip ok" key={s}>✓ {s}</span>)}
                      </div>
                    </>
                  )}
                  {need.length > 0 && (
                    <>
                      <div className="dr-sub">Worth shoring up</div>
                      <div className="dr-skills">
                        {need.map((s) => <span className="req-chip ghosted" key={s}>{s}</span>)}
                      </div>
                    </>
                  )}
                </>
              )}
            </div>

            <div className="dr-actions">
              {sample ? (
                <span
                  className="btn btn-primary"
                  aria-disabled
                  style={{ opacity: .5, cursor: "default" }}
                  title="Sample role — run your profile for live, applyable matches."
                >
                  Apply now <span className="arrow">→</span>
                </span>
              ) : it.application_url ? (
                <a className="btn btn-primary" href={it.application_url} target="_blank" rel="noopener noreferrer">
                  Apply now <span className="arrow">→</span>
                </a>
              ) : (
                <span className="btn btn-ghost" aria-disabled style={{ opacity: .5, cursor: "default" }}>
                  Apply now <span className="arrow">→</span>
                </span>
              )}
              <button className={`btn btn-ghost dr-save${saved ? " on" : ""}`} onClick={onToggleSave} aria-pressed={saved}>
                {BookmarkIcon}<span>{saved ? "Saved" : "Save"}</span>
              </button>
              {analysisHref ? (
                <a className="btn btn-ghost" href={analysisHref}>
                  Full analysis <span className="arrow">→</span>
                </a>
              ) : it.application_url ? (
                <a className="btn btn-ghost" href={`/analyze?url=${encodeURIComponent(it.application_url)}`}>
                  Full analysis <span className="arrow">→</span>
                </a>
              ) : (
                <span className="btn btn-ghost" aria-disabled style={{ opacity: .5, cursor: "default" }}>
                  Full analysis <span className="arrow">→</span>
                </span>
              )}
            </div>
          </>
        )}
      </aside>
    </>,
    document.body,
  );
}
