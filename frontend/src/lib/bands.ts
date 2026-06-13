// Readiness bands — a FRONTEND-only grouping. The backend returns 4 sourcing buckets
// (local/big_tech/startup/reach); a role's band comes from its /analyze/batch verdict + score
// (4-tier, mirroring the option-j mockup). Below apply_now the split is SCORE-driven — the
// quick verdict skews binary (apply_now or skip), so banding on the verdict alone emptied the
// middle bands; the score spreads roles across look/stretch and reserves the collapsed
// "Not a fit right now" block for genuinely poor fits:
//   apply_now      → strong
//   fit_score ≥ 58 → look
//   fit_score ≥ 45 → stretch
//   else           → notfit (collapsed block, shown with the verdict's reasoning)
import type { BucketKey } from "@/lib/storage";
import type { CardAnalysisState } from "@/lib/cardState";

export type Band = "strong" | "look" | "stretch" | "notfit";

// The three VISIBLE feed bands — notfit renders separately as the collapsed block.
export const BAND_KEYS: Band[] = ["strong", "look", "stretch"];

export const BAND_LABEL: Record<Band, string> = {
  strong: "Strong matches",
  look: "Worth a look",
  stretch: "Stretch",
  notfit: "Not a fit right now",
};

// Singular form for the drawer eyebrow / pill.
export const BAND_LABEL_ONE: Record<Band, string> = {
  strong: "Strong match",
  look: "Worth a look",
  stretch: "Stretch",
  notfit: "Not a fit right now",
};

// Score split points below apply_now (see banding rule above).
const LOOK_MIN_SCORE = 58;
const STRETCH_MIN_SCORE = 45;

// The dot color used in the drawer eyebrow per band (mirrors the tier-bar colors).
export const BAND_DOT: Record<Band, string> = {
  strong: "var(--mint)",
  look: "var(--cyan)",
  stretch: "var(--gold)",
  notfit: "var(--faint)",
};

// Bucket → the quiet "company provenance" tag shown on each row (option-j type-tag).
export const TYPE_TAG: Record<BucketKey, string> = {
  local: "Near you",
  big_tech: "Big tech",
  startup: "Startup",
  reach: "Selective",
};

/** The band for a card's analysis state — null until it has a finished score (still "Scoring…"). */
export function bandOf(analysis: CardAnalysisState | undefined): Band | null {
  if (analysis?.status !== "ok") return null;
  if (analysis.data.verdict.call === "apply_now") return "strong";
  const score = analysis.data.fit_score;
  if (score >= LOOK_MIN_SCORE) return "look";
  if (score >= STRETCH_MIN_SCORE) return "stretch";
  return "notfit";
}

/** Fit score for ordering within a band (descending); -1 when not yet scored. */
export function fitScoreOf(analysis: CardAnalysisState | undefined): number {
  return analysis?.status === "ok" ? analysis.data.fit_score : -1;
}
