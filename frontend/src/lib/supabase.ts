/**
 * Supabase browser client + the two auth feature switches.
 *
 * OPTIONAL, mirroring the backend (lib/auth.py) and the Voyage/Redis pattern:
 *   - authConfigured() — URL + anon key present → the client + sign-in UI exist.
 *   - authRequired()   — NEXT_PUBLIC_AUTH_REQUIRED === "true" → the gates ENFORCE
 *                        (results scores gated, analyzer one-free-then-gate).
 *
 * Decoupling "sign-in available" from "sign-in mandatory" keeps local dev frictionless:
 * with the URL+anon set (so a session can be created) but AUTH_REQUIRED off, the current
 * flow is unchanged and a signed-in session's token is still attached to requests. Flip
 * NEXT_PUBLIC_AUTH_REQUIRED on together with the backend SUPABASE_JWT_SECRET to go live.
 *
 * NEXT_PUBLIC_* are inlined at build time, so these reads are static per build.
 */
import { createClient, type SupabaseClient } from "@supabase/supabase-js";

const URL = process.env.NEXT_PUBLIC_SUPABASE_URL;
const ANON = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

export function authConfigured(): boolean {
  return Boolean(URL && ANON);
}

export function authRequired(): boolean {
  return process.env.NEXT_PUBLIC_AUTH_REQUIRED === "true";
}

/** The shared browser client, or null when auth isn't configured (everything no-ops). */
export const supabase: SupabaseClient | null =
  URL && ANON
    ? createClient(URL, ANON, {
        auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true },
      })
    : null;
