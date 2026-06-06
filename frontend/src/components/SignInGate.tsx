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

  const pad = compact ? "p-4" : "p-5";

  if (state === "sent") {
    return (
      <div
        className={`border ${pad} flex flex-col gap-2`}
        style={{ borderColor: "var(--accent)", background: "var(--surface)" }}
      >
        <p className="mono text-xs uppercase tracking-widest" style={{ color: "var(--accent)" }}>
          Check your email
        </p>
        <p className="text-sm" style={{ color: "var(--text-secondary)" }}>
          We sent a magic link to <span style={{ color: "var(--text-primary)" }}>{email}</span>.
          Open it on this device to continue.
        </p>
      </div>
    );
  }

  return (
    <form
      onSubmit={submit}
      className={`border ${pad} flex flex-col gap-3`}
      style={{ borderColor: "var(--border)", background: "var(--surface)" }}
    >
      {title && (
        <p className="mono text-xs uppercase tracking-widest" style={{ color: "var(--accent)" }}>
          {title}
        </p>
      )}
      {subtitle && (
        <p className="text-sm" style={{ color: "var(--text-secondary)" }}>
          {subtitle}
        </p>
      )}
      <input
        type="email"
        required
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        placeholder="you@email.com"
        disabled={state === "sending"}
        className="w-full bg-[var(--bg)] border border-[var(--border)] px-3 py-2 text-sm outline-none
                   placeholder:text-[var(--text-secondary)] focus:border-[var(--accent)]
                   transition-colors disabled:opacity-50"
      />
      <button
        type="submit"
        disabled={state === "sending" || !email.trim()}
        className="mono px-4 py-2 text-xs uppercase tracking-widest font-medium border border-[var(--border)]
                   bg-[var(--surface)] hover:bg-[var(--accent)] hover:text-black hover:border-[var(--accent)]
                   transition-colors disabled:opacity-50"
      >
        {state === "sending" ? "sending…" : "send magic link"}
      </button>
      {state === "error" && error && (
        <p className="text-xs" style={{ color: "#ff6b6b" }}>
          {error}
        </p>
      )}
    </form>
  );
}
