"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { parseResume, runPathfinderStream } from "@/lib/api";
import { type UnifiedProfile } from "@/types/pathfinder";
import { listRuns, saveRun, removeRun, type RunIndexEntry } from "@/lib/storage";
import { PreviousRuns } from "@/components/PreviousRuns";

type Tab = "url" | "paste";
type Status = "idle" | "loading" | "error";
type UploadStatus = "idle" | "uploading" | "done" | "error";
type Step = "profile" | "internships" | null;

function Pulse() {
  return (
    <span
      className="inline-block w-2 h-2 rounded-full animate-pulse"
      style={{ background: "var(--accent)" }}
    />
  );
}

const MAX_BYTES = 5 * 1024 * 1024;
const ALLOWED_EXTS = [".pdf", ".docx"];

export default function Home() {
  const router = useRouter();

  const [tab, setTab] = useState<Tab>("url");
  const [status, setStatus] = useState<Status>("idle");
  const [step, setStep] = useState<Step>(null);  // which /run phase is in flight
  const [errorMsg, setErrorMsg] = useState("");

  // LinkedIn inputs
  const [url, setUrl] = useState("");
  const [text, setText] = useState("");

  // Resume (inline section)
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState("");
  const [uploadStatus, setUploadStatus] = useState<UploadStatus>("idle");
  const [parsedProfile, setParsedProfile] = useState<UnifiedProfile | null>(null);
  const [profileId, setProfileId] = useState<string | null>(null);

  // Saved run history (localStorage) — surfaces "last results" + a "previous runs" list.
  const [runs, setRuns] = useState<RunIndexEntry[]>([]);
  useEffect(() => {
    setRuns(listRuns());
  }, []);

  function handleRemoveRun(runId: string) {
    removeRun(runId);
    setRuns(listRuns());
  }

  // ── Helpers ──────────────────────────────────────────────────────────────

  function validateFile(f: File): string {
    const ext = "." + f.name.split(".").pop()!.toLowerCase();
    if (!ALLOWED_EXTS.includes(ext)) return "Only PDF and DOCX files are accepted.";
    if (f.size > MAX_BYTES) return "File exceeds the 5 MB limit.";
    return "";
  }

  async function handleParse(f: File) {
    setUploadStatus("uploading");
    try {
      const { profile_id, profile } = await parseResume(f);
      setProfileId(profile_id);
      setParsedProfile(profile);
      setUploadStatus("done");
    } catch (err) {
      setFileError(err instanceof Error ? err.message : "Could not parse resume — try a different file.");
      setUploadStatus("error");
    }
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0] ?? null;
    if (!f) return;
    const err = validateFile(f);
    setFile(f);
    setFileError(err);
    setParsedProfile(null);
    setProfileId(null);
    if (!err) handleParse(f);
  }

  function handleFileDrop(f: File) {
    const err = validateFile(f);
    setFile(f);
    setFileError(err);
    setParsedProfile(null);
    setProfileId(null);
    setUploadStatus("idle");
    if (fileInputRef.current) fileInputRef.current.value = "";
    if (!err) handleParse(f);
  }

  function resetUpload() {
    setFile(null);
    setFileError("");
    setUploadStatus("idle");
    setParsedProfile(null);
    setProfileId(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  // ── Submit ────────────────────────────────────────────────────────────────

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const linkedinInput = tab === "url"
      ? (url.trim() ? { url: url.trim() } : {})
      : (text.trim() ? { text: text.trim() } : {});
    const resumeInput = profileId ? { profile_id: profileId } : {};
    const payload = { ...linkedinInput, ...resumeInput };
    if (!("url" in payload) && !("text" in payload) && !("profile_id" in payload)) return;

    setStatus("loading");
    setStep("profile");
    setErrorMsg("");

    const runId = Date.now().toString(36);
    try {
      let navigated = false;
      for await (const env of runPathfinderStream(payload)) {
        if (env.phase === "profile") {
          setStep("profile");
        } else if (env.phase === "internships") {
          setStep("internships");
        } else if (env.phase === "done" && env.data) {
          // env.data is already validated by RunStreamEnvelopeSchema (RunResponseSchema).
          saveRun(runId, env.data);
          navigated = true;
          router.push(`/results/${runId}`);
        } else if (env.phase === "error") {
          setErrorMsg(env.error?.message ?? "Something went wrong.");
          setStatus("error");
          setStep(null);
          return;
        }
      }
      if (!navigated) {
        setErrorMsg("Something went wrong — please try again.");
        setStatus("error");
        setStep(null);
      }
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Something went wrong.");
      setStatus("error");
      setStep(null);
    }
  }

  // ── Derived state ─────────────────────────────────────────────────────────

  const loading = status === "loading";
  const hasLinkedin = tab === "url" ? url.trim().length > 0 : text.trim().length > 0;
  const hasResume = uploadStatus === "done" && profileId !== null;
  const canSubmit = (hasLinkedin || hasResume) && !loading && uploadStatus !== "uploading";

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <main className="min-h-screen flex flex-col items-center justify-center px-6 py-20">
      <div className="w-full max-w-xl flex flex-col gap-10">

        {/* Header */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <h1 className="mono text-4xl font-semibold tracking-tight" style={{ color: "var(--text-primary)" }}>
              pathfinder
            </h1>
            <div className="flex items-center gap-3">
              {runs[0] && (
                <Link
                  href={`/results/${runs[0].runId}`}
                  className="mono text-xs font-medium px-3 py-1.5 border border-[var(--border)]
                             hover:bg-[var(--accent)] hover:text-black hover:border-[var(--accent)]
                             transition-colors"
                  style={{ color: "var(--accent)" }}
                >
                  ← last results
                </Link>
              )}
              <Link
                href="/analyze"
                className="mono text-xs"
                style={{ color: "var(--text-secondary)" }}
              >
                analyze a job →
              </Link>
            </div>
          </div>
          <p className="text-sm" style={{ color: "var(--text-secondary)" }}>
            Enter your LinkedIn URL or paste your profile text. Optionally attach a resume to enrich your results.
          </p>
        </div>

        {/* Tab switcher */}
        <div className="flex border-b" style={{ borderColor: "var(--border)" }}>
          {(["url", "paste"] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => { setTab(t); setErrorMsg(""); setStatus("idle"); }}
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
        <form onSubmit={handleSubmit} className="flex flex-col gap-6">

          {/* LinkedIn input */}
          {tab === "url" ? (
            <div className="flex flex-col gap-1.5">
              <input
                type="url"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://linkedin.com/in/yourname"
                disabled={loading}
                className="w-full bg-[var(--surface)] border border-[var(--border)] px-4 py-3 text-sm outline-none
                           placeholder:text-[var(--text-secondary)] focus:border-[var(--accent)]
                           transition-colors disabled:opacity-50"
              />
              {url.trim() && !url.includes("linkedin.com") && (
                <p className="text-xs" style={{ color: "#f59e0b" }}>
                  This doesn't look like a LinkedIn URL. Enter your profile link (linkedin.com/in/yourname) or use the Paste text tab.
                </p>
              )}
            </div>
          ) : (
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Paste your LinkedIn profile text here..."
              disabled={loading}
              rows={8}
              className="w-full bg-[var(--surface)] border border-[var(--border)] px-4 py-3 text-sm outline-none
                         placeholder:text-[var(--text-secondary)] focus:border-[var(--accent)]
                         transition-colors disabled:opacity-50 resize-none"
            />
          )}

          {/* Resume section divider */}
          <div className="flex items-center gap-3">
            <div className="flex-1 border-t" style={{ borderColor: "var(--border)" }} />
            <span className="mono text-xs" style={{ color: "var(--text-secondary)" }}>
              + add resume (optional)
            </span>
            <div className="flex-1 border-t" style={{ borderColor: "var(--border)" }} />
          </div>

          {/* Resume zone */}
          {uploadStatus === "done" && parsedProfile ? (
            /* Compact badge */
            <div
              className="flex items-center justify-between gap-3 border px-4 py-3"
              style={{ borderColor: "var(--border)", background: "var(--surface)" }}
            >
              <div className="flex items-center gap-3 min-w-0">
                <span
                  className="mono text-xs px-1.5 py-0.5 border shrink-0"
                  style={{ borderColor: "var(--accent)", color: "var(--accent)" }}
                >
                  resume
                </span>
                <span className="text-sm truncate" style={{ color: "var(--text-primary)" }}>
                  {parsedProfile.full_name}
                  {parsedProfile.headline && (
                    <span style={{ color: "var(--text-secondary)" }}> · {parsedProfile.headline}</span>
                  )}
                </span>
              </div>
              <button
                type="button"
                onClick={resetUpload}
                disabled={loading}
                className="mono text-xs shrink-0 hover:opacity-70 transition-opacity disabled:opacity-30"
                style={{ color: "var(--text-secondary)" }}
                aria-label="Remove resume"
              >
                ×
              </button>
            </div>
          ) : (
            /* Drop zone */
            <div className="flex flex-col gap-1.5">
              <label
                className="flex flex-col items-center justify-center gap-2 border-2 border-dashed
                           px-6 py-8 text-center cursor-pointer transition-colors"
                style={{
                  borderColor: fileError
                    ? "#7f1d1d"
                    : uploadStatus === "error"
                    ? "#92400e"
                    : "var(--border)",
                  background: "var(--surface)",
                }}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault();
                  const f = e.dataTransfer.files[0];
                  if (f) handleFileDrop(f);
                }}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".pdf,.docx"
                  className="sr-only"
                  onChange={handleFileChange}
                />

                {uploadStatus === "uploading" ? (
                  <>
                    <span className="text-sm" style={{ color: "var(--text-primary)" }}>
                      {file?.name}
                    </span>
                    <span className="flex items-center gap-2 text-xs" style={{ color: "var(--text-secondary)" }}>
                      <span
                        className="inline-block w-1.5 h-1.5 rounded-full animate-pulse"
                        style={{ background: "var(--accent)" }}
                      />
                      parsing...
                    </span>
                  </>
                ) : (
                  <>
                    <span className="text-sm" style={{ color: "var(--text-secondary)" }}>
                      drop your resume here or click to browse
                    </span>
                    <span className="mono text-xs" style={{ color: "var(--text-secondary)" }}>
                      PDF or DOCX · max 5 MB
                    </span>
                  </>
                )}
              </label>

              {(fileError || uploadStatus === "error") && (
                <p className="text-xs flex items-center gap-2" style={{ color: uploadStatus === "error" ? "#f59e0b" : "#ff6b6b" }}>
                  {fileError || "Could not parse resume."}
                  {uploadStatus === "error" && (
                    <button
                      type="button"
                      onClick={resetUpload}
                      className="underline hover:no-underline"
                    >
                      try again
                    </button>
                  )}
                </p>
              )}
            </div>
          )}

          {/* Submit */}
          <button
            type="submit"
            disabled={!canSubmit}
            className="mono px-5 py-3 text-sm font-medium border border-[var(--border)] bg-[var(--surface)]
                       hover:bg-[var(--accent)] hover:text-black hover:border-[var(--accent)]
                       transition-colors disabled:opacity-50"
          >
            {loading ? (
              <span className="flex items-center justify-center gap-2.5 flex-wrap">
                {/* Step 1: profile (done once internships starts) */}
                <span className="flex items-center gap-1.5">
                  {step === "internships" ? (
                    <span style={{ color: "var(--accent)" }}>✓</span>
                  ) : (
                    <Pulse />
                  )}
                  {hasLinkedin && hasResume ? "merging profile" : "analyzing profile"}
                </span>
                <span style={{ opacity: 0.4 }}>·</span>
                {/* Step 2: internships */}
                <span
                  className="flex items-center gap-1.5"
                  style={{ opacity: step === "internships" ? 1 : 0.45 }}
                >
                  {step === "internships" ? <Pulse /> : <span style={{ opacity: 0.6 }}>○</span>}
                  finding internships
                </span>
              </span>
            ) : (
              "find my path →"
            )}
          </button>
        </form>

        {/* Error */}
        {status === "error" && errorMsg && (
          <div
            className="border p-4 text-sm"
            style={{ borderColor: "#7f1d1d", color: "#ff6b6b" }}
          >
            {errorMsg}
          </div>
        )}

        {/* Previous runs (localStorage history) */}
        <PreviousRuns runs={runs} onRemove={handleRemoveRun} />

      </div>
    </main>
  );
}
