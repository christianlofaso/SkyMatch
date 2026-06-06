import {
  RunResponseSchema,
  UnifiedProfileSchema,
  AnalysisResponseSchema,
  BatchEnvelopeSchema,
  AnnotateEnvelopeSchema,
  AnalyzeStreamEnvelopeSchema,
  RunStreamEnvelopeSchema,
  type RunResponse,
  type UnifiedProfile,
  type AnalysisResponse,
  type BatchEnvelope,
  type AnnotateEnvelope,
  type AnalyzeStreamEnvelope,
  type RunStreamEnvelope,
} from "@/types/pathfinder";

import { supabase } from "@/lib/supabase";
import { getTurnstileToken } from "@/lib/turnstile-client";

type AnnotateJob = { url: string; bucket: "local" | "big_tech" | "startup" | "reach" };

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/**
 * Authorization header for the GATED routes. Returns the current Supabase session's bearer
 * token, or {} when not signed in / auth unconfigured (the backend treats that as anonymous
 * — and only 401s when its own gate is enabled). Attached to /analyze, /analyze/stream,
 * /analyze/batch, /internships/annotate; the open routes (/run*, /profile*) don't use it.
 */
async function authHeaders(): Promise<Record<string, string>> {
  if (!supabase) return {};
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/**
 * Headers for a GATED route: the bearer token (above) PLUS a fresh Cloudflare Turnstile
 * token (X-Turnstile-Token) when Turnstile is configured. The backend requires the Turnstile
 * token whenever its TURNSTILE_SECRET is set — independent of sign-in — so this is attached
 * to every gated call, signed in or not.
 */
async function gatedHeaders(): Promise<Record<string, string>> {
  const headers = await authHeaders();
  const turnstile = await getTurnstileToken();
  if (turnstile) headers["X-Turnstile-Token"] = turnstile;
  return headers;
}

/** Friendly error for an auth failure on a gated route — pages prompt re-sign-in. */
function authError(status: number): Error | null {
  if (status === 401) return new Error("Your session has expired — please sign in again.");
  return null;
}

/**
 * Permanently delete the signed-in user's account + data (DELETE /account). Sends the bearer
 * token; the backend require_user-gates it. Returns the server's summary (what was removed +
 * whether the Supabase auth user was deleted). Callers should sign out + redirect after.
 */
export async function deleteAccount(): Promise<{
  deleted: boolean;
  auth_user_deleted: boolean;
}> {
  const res = await fetch(`${API_BASE}/account`, {
    method: "DELETE",
    headers: await authHeaders(),
  });
  if (!res.ok) {
    const authErr = authError(res.status);
    if (authErr) throw authErr;
    const err = await res.json().catch(() => ({ detail: "Unknown error" }));
    throw new Error(err.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

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
    headers: { "Content-Type": "application/json", ...(await gatedHeaders()) },
    body: JSON.stringify({ profile, mode, ...input }),
  });

  if (!res.ok) {
    const authErr = authError(res.status);
    if (authErr) throw authErr;
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
    headers: { "Content-Type": "application/json", ...(await gatedHeaders()) },
    body: JSON.stringify({ profile, jobs }),
    signal,
  });

  if (!res.ok || !res.body) {
    const authErr = authError(res.status);
    if (authErr) throw authErr;
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
    headers: { "Content-Type": "application/json", ...(await gatedHeaders()) },
    body: JSON.stringify({ profile, jobs }),
    signal,
  });

  if (!res.ok || !res.body) {
    const authErr = authError(res.status);
    if (authErr) throw authErr;
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

/**
 * POSTs a full-mode analyze and yields AnalyzeStreamEnvelope objects as the server
 * streams them (ndjson): "verdict" first, then "roadmap"/"project" in completion order,
 * then "done". The page assembles them into a partial AnalysisResponse and renders
 * progressively. Pre-stream failures (bad fetch / no requirements) surface as a thrown
 * Error with the server's friendly message, same as analyzeJob. Same streaming shape as
 * analyzeBatch. The single-shot analyzeJob() stays for cache re-reads + quick mode.
 */
export async function* analyzeJobStream(
  profile: UnifiedProfile,
  input: { job_url?: string; job_text?: string },
  signal?: AbortSignal,
): AsyncGenerator<AnalyzeStreamEnvelope, void, void> {
  const res = await fetch(`${API_BASE}/analyze/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(await gatedHeaders()) },
    body: JSON.stringify({ profile, mode: "full", ...input }),
    signal,
  });

  if (!res.ok || !res.body) {
    const authErr = authError(res.status);
    if (authErr) throw authErr;
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
        const env = AnalyzeStreamEnvelopeSchema.parse(JSON.parse(line));
        yield env;
      } catch (e) {
        console.warn("[analyzeJobStream] skipped malformed line", line, e);
      }
    }
  }
}

/**
 * POSTs /run and yields RunStreamEnvelope objects as the server streams the phases
 * (ndjson): profile(working→done) → internships(working) → done(full RunResponse), or
 * an "error" envelope carrying the friendly message. The home page shows a 2-step
 * progress indicator and navigates on "done". Same streaming shape as analyzeBatch.
 * The single-shot runPathfinder() stays for any non-streaming caller.
 */
export async function* runPathfinderStream(
  input: { url?: string; text?: string; profile_id?: string },
  signal?: AbortSignal,
): AsyncGenerator<RunStreamEnvelope, void, void> {
  const res = await fetch(`${API_BASE}/run/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
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
        const env = RunStreamEnvelopeSchema.parse(JSON.parse(line));
        yield env;
      } catch (e) {
        console.warn("[runPathfinderStream] skipped malformed line", line, e);
      }
    }
  }
}
