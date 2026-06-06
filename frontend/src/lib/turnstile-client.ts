/**
 * Cloudflare Turnstile token provider for the gated API calls.
 *
 * The backend's `verify_turnstile` dep (lib/turnstile.py) is active whenever the backend
 * `TURNSTILE_SECRET` is set, and then REQUIRES an `X-Turnstile-Token` header on the expensive
 * routes (independent of Supabase auth). This module produces a fresh token per request from a
 * single invisible widget (mounted by <TurnstileWidget/>), serialized so concurrent gated
 * requests (e.g. the results batch) don't clash the one widget. No-ops (returns null) when
 * `NEXT_PUBLIC_TURNSTILE_SITE_KEY` is unset.
 *
 * Tokens are single-use server-side, so we reset() before each execute to force a fresh one.
 */
import type { RefObject } from "react";
import type { TurnstileInstance } from "@marsidev/react-turnstile";

export function turnstileSiteKey(): string | undefined {
  return process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY || undefined;
}

export function turnstileConfigured(): boolean {
  return Boolean(turnstileSiteKey());
}

// The mounted widget's ref, registered by <TurnstileWidget/>. Accessed lazily.
let _ref: RefObject<TurnstileInstance> | null = null;

export function registerTurnstile(ref: RefObject<TurnstileInstance> | null): void {
  _ref = ref;
}

// Serialize token requests: one execute at a time (the widget holds a single challenge).
let _queue: Promise<unknown> = Promise.resolve();

// Cap how long we'll wait for a token so a slow/blocked Cloudflare can't hang a request.
const TOKEN_TIMEOUT_MS = 8000;

function withTimeout<T>(p: Promise<T>, ms: number): Promise<T | null> {
  return Promise.race([
    p,
    new Promise<null>((resolve) => setTimeout(() => resolve(null), ms)),
  ]);
}

export async function getTurnstileToken(): Promise<string | null> {
  if (!turnstileConfigured() || !_ref) return null;
  const run = _queue.then(async () => {
    const api = _ref?.current;
    if (!api) return null;
    try {
      api.reset();
    } catch {
      /* widget not ready yet — getResponsePromise still resolves once it loads */
    }
    try {
      // Bounded: on timeout/failure return null (backend decides — 403 if it requires it).
      return await withTimeout(api.getResponsePromise(), TOKEN_TIMEOUT_MS);
    } catch {
      return null;
    }
  });
  _queue = run.catch(() => undefined); // keep the chain alive even if one call throws
  return run;
}
