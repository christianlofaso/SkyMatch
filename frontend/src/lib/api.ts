import { RunResponseSchema, type RunResponse } from "@/types/pathfinder";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function runPathfinder(input: {
  url?: string;
  text?: string;
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
