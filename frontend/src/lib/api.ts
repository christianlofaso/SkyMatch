import {
  RunResponseSchema,
  UnifiedProfileSchema,
  AnalysisResponseSchema,
  BatchEnvelopeSchema,
  AnnotateEnvelopeSchema,
  type RunResponse,
  type UnifiedProfile,
  type AnalysisResponse,
  type BatchEnvelope,
  type AnnotateEnvelope,
} from "@/types/pathfinder";

type AnnotateJob = { url: string; bucket: "local" | "big_tech" | "startup" | "reach" };

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function parseResume(file: File): Promise<{ profile_id: string; profile: UnifiedProfile }> {
  const form = new FormData();
  form.append("file", file);

  const res = await fetch(`${API_BASE}/profile/from-resume`, {
    method: "POST",
    body: form,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Unknown error" }));
    throw new Error(err.detail ?? `HTTP ${res.status}`);
  }

  const raw = await res.json();
  const parsed = UnifiedProfileSchema.safeParse(raw.profile);
  if (!parsed.success) {
    throw new Error(`Unexpected profile shape: ${parsed.error.message}`);
  }

  return { profile_id: raw.profile_id, profile: parsed.data };
}

export async function runPathfinder(input: {
  url?: string;
  text?: string;
  profile_id?: string;
}): Promise<RunResponse> {
  const res = await fetch(`${API_BASE}/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Unknown error" }));
    throw new Error(err.detail ?? `HTTP ${res.status}`);
  }

  const raw = await res.json();

  // Validate shape at the API boundary — same pattern as dossier
  const parsed = RunResponseSchema.safeParse(raw);
  if (!parsed.success) {
    throw new Error(`Unexpected API shape: ${parsed.error.message}`);
  }

  return parsed.data;
}

export async function analyzeJob(
  profile: UnifiedProfile,
  input: { job_url?: string; job_text?: string },
  mode: "full" | "quick" = "full",
): Promise<AnalysisResponse> {
  const res = await fetch(`${API_BASE}/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ profile, mode, ...input }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Unknown error" }));
    throw new Error(err.detail ?? `HTTP ${res.status}`);
  }

  const raw = await res.json();
  const parsed = AnalysisResponseSchema.safeParse(raw);
  if (!parsed.success) {
    throw new Error(`Unexpected API shape: ${parsed.error.message}`);
  }
  return parsed.data;
}

/**
 * POSTs a batch of {url|text} jobs and yields BatchEnvelope objects in
 * completion order as the server streams them (ndjson, one JSON per line).
 */
export async function* analyzeBatch(
  profile: UnifiedProfile,
  jobs: { url?: string; text?: string }[],
  signal?: AbortSignal,
): AsyncGenerator<BatchEnvelope, void, void> {
  const res = await fetch(`${API_BASE}/analyze/batch`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ profile, jobs }),
    signal,
  });

  if (!res.ok || !res.body) {
    const err = await res.json().catch(() => ({ detail: "Unknown error" }));
    throw new Error(err.detail ?? `HTTP ${res.status}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let nl: number;
    while ((nl = buf.indexOf("\n")) >= 0) {
      const line = buf.slice(0, nl).trim();
      buf = buf.slice(nl + 1);
      if (!line) continue;
      try {
        const env = BatchEnvelopeSchema.parse(JSON.parse(line));
        yield env;
      } catch (e) {
        // Skip malformed lines but log — server shouldn't emit them
        console.warn("[analyzeBatch] skipped malformed line", line, e);
      }
    }
  }
}

/**
 * POSTs a batch of {url, bucket} served listings and yields AnnotateEnvelope objects in
 * completion order as the server streams them (ndjson) — the deferred "why you fit" text
 * that the /run feed leaves empty. Same streaming shape as analyzeBatch.
 */
export async function* annotateFit(
  profile: UnifiedProfile,
  jobs: AnnotateJob[],
  signal?: AbortSignal,
): AsyncGenerator<AnnotateEnvelope, void, void> {
  const res = await fetch(`${API_BASE}/internships/annotate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ profile, jobs }),
    signal,
  });

  if (!res.ok || !res.body) {
    const err = await res.json().catch(() => ({ detail: "Unknown error" }));
    throw new Error(err.detail ?? `HTTP ${res.status}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let nl: number;
    while ((nl = buf.indexOf("\n")) >= 0) {
      const line = buf.slice(0, nl).trim();
      buf = buf.slice(nl + 1);
      if (!line) continue;
      try {
        const env = AnnotateEnvelopeSchema.parse(JSON.parse(line));
        yield env;
      } catch (e) {
        console.warn("[annotateFit] skipped malformed line", line, e);
      }
    }
  }
}
