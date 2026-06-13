/**
 * Single source of truth for verdict → friendly label + color.
 * API responses only contain machine values (apply_now / apply_after_prep / skip).
 * Add new verdict variants here, not inline.
 */
export const VERDICT_LABEL = {
  apply_now: "Apply Now",
  apply_after_prep: "Worth Prepping",
  skip: "Probably Not a Fit",
} as const;

export const VERDICT_COLOR = {
  apply_now: "var(--accent)",            // brand accent
  apply_after_prep: "var(--warn)",       // amber (theme-tokenized for light/dark)
  skip: "var(--text-secondary)",         // muted
} as const;

export type VerdictCall = keyof typeof VERDICT_LABEL;

/** Heuristic fit-score color, shared between cards and the full view. */
export function scoreColor(score: number): string {
  if (score >= 70) return "var(--accent)";
  if (score >= 40) return "var(--warn)";
  return "var(--danger)";
}
