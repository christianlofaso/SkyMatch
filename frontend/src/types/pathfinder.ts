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
  fit_explanation: z.string(),
  application_url: z.string().nullable(),
  bucket: z.enum(["local", "big_tech", "startup", "reach"]),
  reach_gap: z.string().nullable(),
});

export const InternshipBucketsSchema = z.object({
  local: z.array(InternshipSchema),
  big_tech: z.array(InternshipSchema),
  startup: z.array(InternshipSchema),
  reach: z.array(InternshipSchema),
});

export const RunResponseSchema = z.object({
  profile: ProfileAnalysisSchema,
  connections: z.array(ConnectionSchema),
  internships: InternshipBucketsSchema,
});

// --- Inferred TypeScript types ---

export type ProfileAnalysis = z.infer<typeof ProfileAnalysisSchema>;
export type Connection = z.infer<typeof ConnectionSchema>;
export type Internship = z.infer<typeof InternshipSchema>;
export type InternshipBuckets = z.infer<typeof InternshipBucketsSchema>;
export type RunResponse = z.infer<typeof RunResponseSchema>;
