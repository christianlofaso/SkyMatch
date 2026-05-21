"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { runPathfinder } from "@/lib/api";

type Tab = "url" | "paste";
type Status = "idle" | "loading" | "error";

export default function Home() {
  const router = useRouter();
  const [tab, setTab] = useState<Tab>("url");
  const [url, setUrl] = useState("");
  const [text, setText] = useState("");
  const [status, setStatus] = useState<Status>("idle");
  const [errorMsg, setErrorMsg] = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const input = tab === "url" ? { url: url.trim() } : { text: text.trim() };
    if (!input.url && !input.text) return;

    setStatus("loading");
    setErrorMsg("");

    try {
      const result = await runPathfinder(input);
      const runId = Date.now().toString(36);
      sessionStorage.setItem(runId, JSON.stringify(result));
      router.push(`/results/${runId}`);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Something went wrong.");
      setStatus("error");
    }
  }

  const loading = status === "loading";

  return (
    <main className="min-h-screen flex flex-col items-center justify-center px-6 py-20">
      <div className="w-full max-w-xl flex flex-col gap-10">

        {/* Header */}
        <div>
          <h1 className="mono text-4xl font-semibold tracking-tight mb-2" style={{ color: "var(--text-primary)" }}>
            pathfinder
          </h1>
          <p className="text-sm" style={{ color: "var(--text-secondary)" }}>
            Paste your LinkedIn URL. Get 10 warm connections and internships matched to your profile.
          </p>
        </div>

        {/* Tab switcher */}
        <div className="flex border-b" style={{ borderColor: "var(--border)" }}>
          {(["url", "paste"] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className="mono px-4 py-2 text-xs uppercase tracking-widest transition-colors"
              style={{
                color: tab === t ? "var(--accent)" : "var(--text-secondary)",
                borderBottom: tab === t ? "2px solid var(--accent)" : "2px solid transparent",
                marginBottom: "-1px",
              }}
            >
              {t === "url" ? "LinkedIn URL" : "Paste text"}
            </button>
          ))}
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          {tab === "url" ? (
            <input
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://linkedin.com/in/yourname"
              required
              disabled={loading}
              className="w-full bg-[var(--surface)] border border-[var(--border)] px-4 py-3 text-sm outline-none
                         placeholder:text-[var(--text-secondary)] focus:border-[var(--accent)]
                         transition-colors disabled:opacity-50"
            />
          ) : (
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Paste your LinkedIn profile text here..."
              required
              disabled={loading}
              rows={8}
              className="w-full bg-[var(--surface)] border border-[var(--border)] px-4 py-3 text-sm outline-none
                         placeholder:text-[var(--text-secondary)] focus:border-[var(--accent)]
                         transition-colors disabled:opacity-50 resize-none"
            />
          )}

          <button
            type="submit"
            disabled={loading}
            className="mono px-5 py-3 text-sm font-medium border border-[var(--border)] bg-[var(--surface)]
                       hover:bg-[var(--accent)] hover:text-black hover:border-[var(--accent)]
                       transition-colors disabled:opacity-50"
          >
            {loading ? (
              <span className="flex items-center gap-2">
                <span
                  className="inline-block w-2 h-2 rounded-full animate-pulse"
                  style={{ background: "var(--accent)" }}
                />
                analyzing profile...
              </span>
            ) : (
              "find my path →"
            )}
          </button>
        </form>

        {/* Error */}
        {status === "error" && (
          <div
            className="border p-4 text-sm"
            style={{ borderColor: "#7f1d1d", color: "#ff6b6b" }}
          >
            {errorMsg}
          </div>
        )}
      </div>
    </main>
  );
}
