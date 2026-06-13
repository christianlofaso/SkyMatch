"use client";

import { useState } from "react";

interface Props {
  /** Send the magic link. Returns `{ error }` (null on success). Wired to useAuth().signInWithOtp. */
  onSubmit: (email: string) => Promise<{ error: string | null }>;
  title?: string;
  subtitle?: string;
  /** Tighter padding for the floating-chip popover. */
  compact?: boolean;
}

type State = "idle" | "sending" | "sent" | "error";

/**
 * Reusable magic-link sign-in panel: email → "send link" → "check your email". Stateless
 * w.r.t. auth (the caller passes onSubmit), so it's shared by the floating auth chip, the
 * results-reveal gate, and the analyzer one-free-then-gate without an import cycle.
 */
export function SignInGate({ onSubmit, title, subtitle, compact }: Props) {
  const [email, setEmail] = useState("");
  const [state, setState] = useState<State>("idle");
  const [error, setError] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const addr = email.trim();
    if (!addr || state === "sending") return;
    setState("sending");
    setError("");
    const { error } = await onSubmit(addr);
    if (error) {
      setError(error);
      setState("error");
    } else {
      setState("sent");
    }
  }

  const cardCls = `signin-card${compact ? " compact" : ""}`;

  if (state === "sent") {
    return (
      <div className={cardCls}>
        <p className="signin-title accent">Check your email</p>
        <p className="signin-sub">
          We sent a magic link to <b>{email}</b>. Open it on this device to continue.
        </p>
      </div>
    );
  }

  return (
    <form onSubmit={submit} className={cardCls}>
      {title && <p className="signin-title">{title}</p>}
      {subtitle && <p className="signin-sub">{subtitle}</p>}
      <input
        type="email"
        required
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        placeholder="you@email.com"
        disabled={state === "sending"}
        className="signin-input"
      />
      <button type="submit" disabled={state === "sending" || !email.trim()} className="signin-submit">
        {state === "sending" ? "Sending…" : "Send magic link"}
      </button>
      {state === "error" && error && <p className="signin-error">{error}</p>}
    </form>
  );
}
