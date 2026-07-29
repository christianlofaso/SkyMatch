"use client";
import type { Internship } from "@/types/skymatch";
import type { BucketKey } from "@/lib/storage";
import type { CardAnalysisState } from "@/lib/cardState";
import { type Band, TYPE_TAG } from "@/lib/bands";
import { LogoBox, BookmarkIcon } from "./LogoBox";
import { TierBars } from "./TierBars";

interface Props {
  internship: Internship;
  bucket: BucketKey;
  band: Band | null;            // null = not yet scored ("Scoring…")
  analysis?: CardAnalysisState; // drives the scoring/error affordance
  saved: boolean;
  gated?: boolean;
  pending?: boolean;            // batch scoring in flight → render no verdict (the feed-level loader speaks for it)
  noScore?: boolean;            // no scoring context (e.g. Saved page) → show "Details →", not "Scoring…"
  style?: React.CSSProperties;  // stagger animation-delay from the feed
  onOpen: () => void;
  onToggleSave: () => void;
}

// One feed row (ported from option-j smRowHTML): logo + title/meta + a verdict signal
// (tier bars once scored, else "Scoring…") + a bookmark save button. Clicking the head
// opens the detail drawer.
export function RoleCard({ internship, bucket, band, analysis, saved, gated, pending, noScore, style, onOpen, onToggleSave }: Props) {
  const posted = internship.posted_at || (analysis?.status === "ok" ? analysis.data.job_summary.posted_at : null);
  const verdict = gated ? (
    <span className="aff" title="Sign in to reveal your match">🔒 sign in</span>
  ) : pending ? (
    null
  ) : band ? (
    <>
      <TierBars band={band} />
      <span className="aff">Details →</span>
    </>
  ) : noScore || analysis?.status === "error" ? (
    <span className="aff">Details →</span>
  ) : (
    <span className="aff">Scoring…</span>
  );

  return (
    <article className="role" data-band={band ?? undefined} style={style}>
      <button className="role-head" onClick={onOpen} aria-haspopup="dialog">
        <LogoBox company={internship.company} logoUrl={internship.logo_url} />
        <div className="meta">
          <div className="ti">{internship.title}</div>
          <div className="su">
            {internship.company} · {internship.location}{posted ? ` · ${posted}` : ""}
            <span className="type-tag">{TYPE_TAG[bucket]}</span>
          </div>
        </div>
        <div className="verdict">{verdict}</div>
      </button>
      <button
        className={`savebtn${saved ? " on" : ""}`}
        onClick={(e) => {
          e.stopPropagation();
          onToggleSave();
        }}
        aria-label={`Save ${internship.title} at ${internship.company}`}
        aria-pressed={saved}
      >
        {BookmarkIcon}
      </button>
    </article>
  );
}
