"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { deleteAccount } from "@/lib/api";

const CONFIRM_WORD = "DELETE";

export default function AccountPage() {
  const router = useRouter();
  const { session, user, loading, authConfigured, signOut } = useAuth();
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleDelete() {
    setError(null);
    setBusy(true);
    try {
      await deleteAccount();
      // Identity is gone server-side; drop the local session and leave.
      await signOut();
      router.replace("/");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not delete your account.");
      setBusy(false);
    }
  }

  return (
    <main className="min-h-screen px-6 py-16 flex justify-center">
      <div className="w-full max-w-xl">
        <Link
          href="/"
          className="mono text-[10px] uppercase tracking-widest hover:opacity-70"
          style={{ color: "var(--text-secondary)" }}
        >
          ← back
        </Link>

        <h1 className="mt-6 text-2xl font-semibold" style={{ color: "var(--text-primary)" }}>
          Account
        </h1>

        {loading ? (
          <p className="mt-6 mono text-xs" style={{ color: "var(--text-secondary)" }}>
            loading…
          </p>
        ) : !authConfigured ? (
          <p className="mt-6 text-sm" style={{ color: "var(--text-secondary)" }}>
            Accounts aren&apos;t enabled in this environment.
          </p>
        ) : !session ? (
          <p className="mt-6 text-sm" style={{ color: "var(--text-secondary)" }}>
            You&apos;re not signed in. Use the “sign in” control in the top-right corner.
          </p>
        ) : (
          <>
            <p className="mt-6 text-sm" style={{ color: "var(--text-secondary)" }}>
              Signed in as{" "}
              <span style={{ color: "var(--text-primary)" }}>{user?.email ?? "your account"}</span>.
            </p>

            <section
              className="mt-10 border p-5"
              style={{ borderColor: "var(--border)", background: "var(--surface)" }}
            >
              <h2 className="text-sm font-semibold uppercase tracking-wide" style={{ color: "var(--danger, #c0392b)" }}>
                Delete account
              </h2>
              <p className="mt-2 text-sm" style={{ color: "var(--text-secondary)" }}>
                Permanently deletes your account and removes your saved data (profile usage
                counts and sign-in record). Aggregate, anonymized billing records are retained
                for accounting. This cannot be undone.
              </p>

              <label className="mt-4 block mono text-[10px] uppercase tracking-widest" style={{ color: "var(--text-secondary)" }}>
                Type {CONFIRM_WORD} to confirm
              </label>
              <input
                type="text"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                disabled={busy}
                className="mt-1 w-full border px-3 py-2 mono text-sm bg-transparent"
                style={{ borderColor: "var(--border)", color: "var(--text-primary)" }}
                placeholder={CONFIRM_WORD}
                autoComplete="off"
              />

              {error && (
                <p className="mt-3 text-sm" style={{ color: "var(--danger, #c0392b)" }}>
                  {error}
                </p>
              )}

              <button
                type="button"
                onClick={handleDelete}
                disabled={busy || confirm !== CONFIRM_WORD}
                className="mt-4 mono text-[11px] uppercase tracking-widest border px-4 py-2 disabled:opacity-40 hover:opacity-80"
                style={{ borderColor: "var(--danger, #c0392b)", color: "var(--danger, #c0392b)" }}
              >
                {busy ? "deleting…" : "delete my account"}
              </button>
            </section>
          </>
        )}
      </div>
    </main>
  );
}
