// Readiness bands — a FRONTEND-only grouping. The backend returns 4 sourcing buckets
// (local/big_tech/startup/reach); a role's band comes from its /analyze/batch verdict + score.
// Mapping (post-audit recalibration):
//   verdict skip            → notfit (collapsed block, shown with the verdict's reasoning)
//   verdict apply_after_prep→ look (score ≥ 55) / stretch (below) — the model already judged
//                             "prep needed", so it ALWAYS routes to a middle band (a score in the
//                             60s no longer overrides it into looking like a clean match)
//   verdict apply_now, reach bucket  → look  — a "Selective"/reach role is aspirational by
//                             definition; it must NEVER show as a top "Strong / apply this week"
//                             match, which directly contradicted the card's own reach_gap note
//   verdict apply_now, other buckets → strong
// This keeps the three visible bands populated instead of collapsing to one giant "Strong" pile,
// and makes the badge consistent with the drawer's "Gap to close" text on reach roles.
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
// Split an apply_after_prep verdict (model band ~58-71) into Worth-a-look (closer, fewer gaps)
// vs Stretch (more to prep). Midpoint of the prep band so BOTH middle tiers populate instead of
// everything piling into "look".
const PREP_LOOK_MIN = 65;

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

/** The band for a card's analysis state — null until it has a finished score (still "Scoring…").
 *  `bucket` lets a reach/"Selective" role be capped below "strong" (see the mapping note above);
 *  it's optional so non-feed callers (e.g. the Saved page) still get sane bands. */
export function bandOf(analysis: CardAnalysisState | undefined, bucket?: BucketKey): Band | null {
  if (analysis?.status !== "ok") return null;
  const call = analysis.data.verdict.call;
  const score = analysis.data.fit_score;
  if (call === "skip") return "notfit";
  if (call === "apply_after_prep") return score >= PREP_LOOK_MIN ? "look" : "stretch";
  if (call === "apply_now") {
    // Reach roles are aspirational — never the top "Strong" tier (consistency with reach_gap).
    return bucket === "reach" ? "look" : "strong";
  }
  // Defensive fallback for any unexpected verdict value.
  if (score >= LOOK_MIN_SCORE) return "look";
  if (score >= STRETCH_MIN_SCORE) return "stretch";
  return "notfit";
}

/** Fit score for ordering within a band (descending); -1 when not yet scored. */
export function fitScoreOf(analysis: CardAnalysisState | undefined): number {
  return analysis?.status === "ok" ? analysis.data.fit_score : -1;
}
