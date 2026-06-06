"use client";

import { useEffect, useRef } from "react";
import { Turnstile, type TurnstileInstance } from "@marsidev/react-turnstile";
import { registerTurnstile, turnstileSiteKey } from "@/lib/turnstile-client";

/**
 * One invisible Turnstile widget, mounted once globally (by AuthProvider). It registers its
 * ref so lib/turnstile-client.getTurnstileToken() can pull a fresh token per gated request.
 * Renders nothing visible. No-ops when no site key is configured.
 */
export function TurnstileWidget() {
  const ref = useRef<TurnstileInstance>(null);
  const siteKey = turnstileSiteKey();

  useEffect(() => {
    registerTurnstile(ref);
    return () => registerTurnstile(null);
  }, []);

  if (!siteKey) return null;
  // Invisible + default "render" execution: the widget auto-runs on mount and re-runs on
  // reset(), so getTurnstileToken()'s reset()+getResponsePromise() yields a fresh token without
  // an explicit execute() call.
  return <Turnstile ref={ref} siteKey={siteKey} options={{ size: "invisible" }} />;
}
