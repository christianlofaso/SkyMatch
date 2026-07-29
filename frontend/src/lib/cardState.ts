// Per-card UI state shared across the results feed (RoleCard / RoleDrawer), the results page,
// and localStorage persistence (lib/storage). Lives here (not on a component) so it survives
// component churn — the feed cards changed from InternshipCard to RoleCard/RoleDrawer during the
// option-j UI port, but this contract is the stable plumbing between page state and storage.
import type { QuickAnalysisResponse } from "@/types/skymatch";

// Eager score badge — batch-scored on load via /analyze/batch.
export type CardAnalysisState =
  | { status: "loading" }
  | { status: "ok"; data: QuickAnalysisResponse }
  | { status: "error"; message: string };

// Deferred "why you fit" content streamed by /internships/annotate (see lib/api.annotateFit),
// fetched lazily on a card's first drawer-open. `why`/`have`/`need` drive the drawer's bullets +
// skill chips; older cached entries may have empty arrays (pre-enrichment) — render defensively.
export type CardAnnotationState =
  | { status: "loading" }
  | {
      status: "ok";
      fit_explanation: string;
      why: string[];
      have: string[];
      need: string[];
      reach_gap: string | null;
    }
  | { status: "error" };
