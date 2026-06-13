"use client";

import { useState } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { SignInGate } from "@/components/SignInGate";

/**
 * Nav-bar auth control — the single sign-in entry point (replaces the old fixed
 * top-right AuthChip). Logged out → "Sign in" opens a magic-link popover; logged in
 * → "Account" opens a popover with the account link + sign out. `className` styles
 * the trigger so each brand's nav can theme it.
 */
export function NavAuth({ className = "" }: { className?: string }) {
  const { session, user, loading, authConfigured, signInWithOtp, signOut } = useAuth();
  const [open, setOpen] = useState(false);

  // Auth not configured → just link to the account page; nothing to pop over.
  if (!authConfigured) {
    return <Link href="/account" className={className}>Sign in</Link>;
  }
  if (loading) return null;

  return (
    <div style={{ position: "relative" }}>
      <button type="button" className={className} onClick={() => setOpen((o) => !o)}>
        {session ? "Account" : "Sign in"}
      </button>

      {open && (
        <>
          {/* click-away backdrop */}
          <button
            type="button"
            aria-hidden
            tabIndex={-1}
            onClick={() => setOpen(false)}
            style={{ position: "fixed", inset: 0, zIndex: 40, background: "transparent", border: "none", cursor: "default" }}
          />
          <div style={{ position: "absolute", right: 0, top: "calc(100% + 12px)", zIndex: 50, width: 272 }}>
            {session ? (
              <div className="signin-card compact text-sm">
                <span className="truncate" style={{ color: "var(--text-primary)" }}>{user?.email ?? "signed in"}</span>
                <div className="flex items-center justify-between">
                  <Link href="/account" onClick={() => setOpen(false)} className="hover:opacity-70" style={{ color: "var(--text-secondary)" }}>
                    Account
                  </Link>
                  <button type="button" onClick={() => { signOut(); setOpen(false); }} className="font-medium hover:opacity-70" style={{ color: "var(--accent)" }}>
                    Sign out
                  </button>
                </div>
              </div>
            ) : (
              <SignInGate onSubmit={signInWithOtp} compact title="Sign in" subtitle="We'll email you a one-tap magic link." />
            )}
          </div>
        </>
      )}
    </div>
  );
}
