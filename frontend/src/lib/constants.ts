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
  apply_now: "var(--accent)",            // green
  apply_after_prep: "#f59e0b",           // amber
  skip: "var(--text-secondary)",         // muted
} as const;

export type VerdictCall = keyof typeof VERDICT_LABEL;

/** Heuristic fit-score color, shared between cards and the full view. */
export function scoreColor(score: number): string {
  if (score >= 70) return "var(--accent)";
  if (score >= 40) return "#f59e0b";
  return "#ff6b6b";
}
