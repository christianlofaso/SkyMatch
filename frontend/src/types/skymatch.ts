import { z } from "zod";

// --- Zod schemas (single source of truth — TS types are inferred from these) ---

export const ProfileAnalysisSchema = z.object({
  full_name: z.string(),
  headline: z.string(),
  location: z.string(),
  school: z.string(),
  graduation_year: z.number().nullable(),
  major: z.string().nullable(),
  fraternity_or_orgs: z.array(z.string()),
  past_companies: z.array(z.string()),
  current_company: z.string().nullable(),
  technical_skills: z.array(z.string()),
  field_of_interest: z.string(),
  key_values: z.array(z.string()),
});

export const SkillEntrySchema = z.object({
  skill: z.string(),
  context: z.string(),
});

export const EducationEntrySchema = z.object({
  school: z.string(),
  degree: z.string().nullable(),
  field_of_study: z.string().nullable(),
  start_year: z.number().nullable(),
  end_year: z.number().nullable(),
});

export const WorkEntrySchema = z.object({
  company: z.string(),
  title: z.string(),
  start_date: z.string().nullable(),
  end_date: z.string().nullable(),
  description: z.string().nullable(),
});

export const ProjectEntrySchema = z.object({
  name: z.string(),
  description: z.string(),
  technologies: z.array(z.string()),
});

export const UnifiedProfileSchema = ProfileAnalysisSchema.extend({
  skills_with_context: z.array(SkillEntrySchema).default([]),
  education: z.array(EducationEntrySchema).default([]),
  work_experience: z.array(WorkEntrySchema).default([]),
  projects: z.array(ProjectEntrySchema).default([]),
  certifications: z.array(z.string()).default([]),
  sources: z.array(z.enum(["linkedin", "resume"])).default([]),
});

export const ConnectionSchema = z.object({
  name: z.string(),
  title: z.string(),
  company: z.string(),
  linkedin_url: z.string(),
  commonality_type: z.enum(["fraternity", "school", "past_company", "field", "major"]),
  commonality_detail: z.string(),
  why_relevant: z.string(),
});

export const InternshipSchema = z.object({
  title: z.string(),
  company: z.string(),
  location: z.string(),
  company_description: z.string(),
  // Empty on the initial /run feed; filled lazily by /internships/annotate (see api.annotateFit).
  fit_explanation: z.string().default(""),
  application_url: z.string().nullable(),
  bucket: z.enum(["local", "big_tech", "startup", "reach"]),
  reach_gap: z.string().nullable(),
  // Company logo URL from the backend (lib/logos); null → render the letter avatar fallback.
  // Not yet rendered — consumed when the demo's logo-box card design is ported into the app.
  logo_url: z.string().nullish(),
  // Drawer fact-grid fields, extracted at ingestion parse; null when the listing doesn't state
  // them (the drawer then shows the company name alone / falls back to a heuristic term).
  company_size: z.string().nullish(), // headcount phrase, e.g. "650 people"
  term: z.string().nullish(),         // e.g. "Summer 2026" | "Full-time" | "Co-op"
  posted_at: z.string().nullish(),    // posted date captured at ingestion (snippet/SPA render)
});

export const InternshipBucketsSchema = z.object({
  local: z.array(InternshipSchema),
  big_tech: z.array(InternshipSchema),
  startup: z.array(InternshipSchema),
  reach: z.array(InternshipSchema),
});

export const RunResponseSchema = z.object({
  profile: UnifiedProfileSchema,
  connections: z.array(ConnectionSchema).default([]),
  internships: InternshipBucketsSchema,
});

// --- Analysis schemas ---

export const JobSummarySchema = z.object({
  title: z.string(),
  company: z.string(),
  key_requirements: z.array(z.string()),
});

export const MatchItemSchema = z.object({
  requirement: z.string(),
  type: z.enum(["technical", "experience", "education", "domain", "soft"]),
  must_have: z.boolean(),
  match_strength: z.enum(["strong", "partial"]),
  evidence_snippet: z.string().nullable(),
  evidence_source: z.string().nullable(),
});

export const GapItemSchema = z.object({
  requirement: z.string(),
  type: z.enum(["technical", "experience", "education", "domain", "soft"]),
  must_have: z.boolean(),
  severity: z.enum(["critical", "moderate", "minor"]),
});

export const VerdictSchema = z.object({
  call: z.enum(["apply_now", "apply_after_prep", "skip"]),
  reasoning: z.string(),
});

export const RoadmapResourceSchema = z.object({
  type: z.enum(["docs", "course", "tutorial", "video", "book", "roadmap"]),
  title: z.string(),
  url: z.string(),
  duration: z.string(),
  cost: z.enum(["free", "paid"]),
});

export const RoadmapItemSchema = z.object({
  skill: z.string(),
  priority: z.enum(["must_have", "nice_to_have"]),
  timeline: z.string(),
  why_it_matters: z.string(),
  milestone: z.string(),
  resources: z.array(RoadmapResourceSchema),
});

export const RoadmapSchema = z.object({
  total_timeline: z.string(),
  summary: z.string(),
  items: z.array(RoadmapItemSchema),
});

export const ProjectSuggestionSchema = z.object({
  title: z.string(),
  pitch: z.string(),
  why_this_role: z.string(),
  mvp_features: z.array(z.string()),
  tech_stack: z.array(z.string()),
  estimated_time: z.string(),
  stretch_goals: z.array(z.string()),
  interview_talking_points: z.array(z.string()),
});

export const AnalysisResponseSchema = z.object({
  fit_score: z.number().int(),
  category_scores: z.record(z.string(), z.number().int()),
  matches: z.array(MatchItemSchema),
  gaps: z.array(GapItemSchema),
  verdict: VerdictSchema,
  job_summary: JobSummarySchema,
  roadmap: RoadmapSchema.nullable().optional(),
  roadmap_note: z.string().nullable().optional(),
  project_suggestion: ProjectSuggestionSchema.nullable().optional(),
});

// --- Quick mode + batch schemas ---

export const QuickJobSummarySchema = z.object({
  title: z.string(),
  company: z.string(),
  posted_at: z.string().nullable().optional(),
  apply_url: z.string().nullable().optional(),
});

export const QuickAnalysisResponseSchema = z.object({
  fit_score: z.number().int(),
  verdict: VerdictSchema,
  job_summary: QuickJobSummarySchema,
});

export const BatchEnvelopeSchema = z.object({
  index: z.number().int(),
  status: z.enum(["ok", "error"]),
  data: QuickAnalysisResponseSchema.optional(),
  error: z
    .object({
      message: z.string(),
      code: z.enum(["FETCH_FAILED", "EXTRACTION_FAILED", "VERDICT_FAILED", "INTERNAL"]),
    })
    .optional(),
});

// Deferred per-role "why you fit" annotation streamed by POST /internships/annotate.
export const AnnotateEnvelopeSchema = z.object({
  index: z.number().int(),
  status: z.enum(["ok", "error"]),
  fit_explanation: z.string().optional(),
  why: z.array(z.string()).default([]),    // "why you fit" bullets (drawer)
  have: z.array(z.string()).default([]),   // skills the student already brings
  need: z.array(z.string()).default([]),   // skills to shore up
  reach_gap: z.string().nullable().optional(),
  error: z
    .object({
      message: z.string(),
      code: z.enum(["NOT_FOUND", "ANNOTATE_FAILED", "INTERNAL"]),
    })
    .optional(),
});

// Progressive phase envelope streamed by POST /analyze/stream (full mode). Each line
// carries one phase; the frontend merges payloads into a partial AnalysisResponse.
// Mirror of backend routes/analyze.py AnalyzeStreamEnvelope.
// Every payload field is nullable+optional: the backend serializes without exclude_none,
// so off-phase fields arrive as null (not absent), and the nested data models keep their
// own nulls (matching AnalysisResponseSchema, used by the non-streaming path too).
export const AnalyzeStreamEnvelopeSchema = z.object({
  phase: z.enum(["verdict", "roadmap", "project", "done", "error"]),
  // verdict payload
  fit_score: z.number().int().nullable().optional(),
  category_scores: z.record(z.string(), z.number().int()).nullable().optional(),
  matches: z.array(MatchItemSchema).nullable().optional(),
  gaps: z.array(GapItemSchema).nullable().optional(),
  verdict: VerdictSchema.nullable().optional(),
  job_summary: JobSummarySchema.nullable().optional(),
  // roadmap payload
  roadmap: RoadmapSchema.nullable().optional(),
  roadmap_note: z.string().nullable().optional(),
  // project payload
  project_suggestion: ProjectSuggestionSchema.nullable().optional(),
  // error payload
  error: z.object({ message: z.string(), status: z.number().int() }).nullable().optional(),
});

// Phase envelope streamed by POST /run/stream. Mirror of backend schemas.py RunStreamEnvelope.
export const RunStreamEnvelopeSchema = z.object({
  phase: z.enum(["profile", "internships", "done", "error"]),
  state: z.enum(["working", "done"]).nullable().optional(),
  data: RunResponseSchema.nullable().optional(),
  error: z.object({ message: z.string(), status: z.number().int() }).nullable().optional(),
});

// --- Inferred TypeScript types ---

export type ProfileAnalysis = z.infer<typeof ProfileAnalysisSchema>;
export type SkillEntry = z.infer<typeof SkillEntrySchema>;
export type EducationEntry = z.infer<typeof EducationEntrySchema>;
export type WorkEntry = z.infer<typeof WorkEntrySchema>;
export type ProjectEntry = z.infer<typeof ProjectEntrySchema>;
export type UnifiedProfile = z.infer<typeof UnifiedProfileSchema>;
export type Connection = z.infer<typeof ConnectionSchema>;
export type Internship = z.infer<typeof InternshipSchema>;
export type InternshipBuckets = z.infer<typeof InternshipBucketsSchema>;
export type RunResponse = z.infer<typeof RunResponseSchema>;
export type JobSummary = z.infer<typeof JobSummarySchema>;
export type MatchItem = z.infer<typeof MatchItemSchema>;
export type GapItem = z.infer<typeof GapItemSchema>;
export type Verdict = z.infer<typeof VerdictSchema>;
export type AnalysisResponse = z.infer<typeof AnalysisResponseSchema>;
export type RoadmapResource = z.infer<typeof RoadmapResourceSchema>;
export type RoadmapItem = z.infer<typeof RoadmapItemSchema>;
export type Roadmap = z.infer<typeof RoadmapSchema>;
export type ProjectSuggestion = z.infer<typeof ProjectSuggestionSchema>;
export type QuickJobSummary = z.infer<typeof QuickJobSummarySchema>;
export type QuickAnalysisResponse = z.infer<typeof QuickAnalysisResponseSchema>;
export type BatchEnvelope = z.infer<typeof BatchEnvelopeSchema>;
export type AnnotateEnvelope = z.infer<typeof AnnotateEnvelopeSchema>;
export type AnalyzeStreamEnvelope = z.infer<typeof AnalyzeStreamEnvelopeSchema>;
export type RunStreamEnvelope = z.infer<typeof RunStreamEnvelopeSchema>;
