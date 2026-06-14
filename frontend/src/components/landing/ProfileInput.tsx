"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { useProfileRun } from "@/lib/useProfileRun";
import { seedDemoRun, DEMO_RUN_ID } from "@/lib/demoRun";
import { RunVeil } from "./RunVeil";

// The hero run input, styled as option-j's upload card: a resume dropzone + a LinkedIn-URL
// pill + "Get matched →". Paste-text is intentionally not surfaced here (the hook/backend
// still accept it). All behaviour comes from the shared useProfileRun hook; on submit we show
// the radar run veil, and the hook navigates to /results on completion.
export function ProfileInput() {
  const r = useProfileRun();
  const router = useRouter();
  const [drag, setDrag] = useState(false);

  // "Browse a sample shortlist" — seed the static demo run + go straight to its results page
  // (no backend call). Lets a logged-out visitor see the real feed before pasting anything.
  function browseSample() {
    seedDemoRun();
    router.push(`/results/${DEMO_RUN_ID}`);
  }

  const ready = r.uploadStatus === "done";
  const dzTitle =
    r.uploadStatus === "uploading" ? "Parsing resume…"
      : ready ? (r.file?.name ?? "Resume added")
      : r.fileError ? r.fileError
      : "Upload your resume";
  const dzSub =
    r.uploadStatus === "uploading" ? "reading your background…"
      : ready ? "looks good · ready to match"
      : "Drag & drop or browse · PDF or DOCX · max 5 MB";

  return (
    <>
      {r.loading && <RunVeil step={r.step} />}

      <div className="visual lift l5">
        <form className="upload-card" onSubmit={r.submit}>
          <label
            className={`dropzone${drag || ready ? " ready" : ""}`}
            onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
            onDragLeave={() => setDrag(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDrag(false);
              const f = e.dataTransfer.files?.[0];
              if (f) r.onFileDrop(f);
            }}
          >
            <input
              ref={r.fileInputRef}
              type="file"
              className="sr-only"
              accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
              onChange={r.onFileChange}
            />
            <div className="up-ico" aria-hidden>
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 16V4" /><path d="m6 10 6-6 6 6" /><path d="M4 20h16" />
              </svg>
            </div>
            <div className="up-title">{dzTitle}</div>
            <div className="up-sub">{dzSub}</div>
          </label>

          <div className="or-divider">Or use your LinkedIn</div>

          <div className="input-shell">
            <svg className="lk" width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
              <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
              <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
            </svg>
            <input
              type="text"
              placeholder="linkedin.com/in/yourname"
              aria-label="LinkedIn URL"
              value={r.url}
              onChange={(e) => r.setUrl(e.target.value)}
            />
          </div>

          <button type="submit" className="btn btn-primary" disabled={!r.canSubmit}>
            {r.loading ? "Finding your matches…" : <>Get matched <span className="arrow">→</span></>}
          </button>

          {r.errorMsg && (
            <div className="up-sub" style={{ color: "var(--danger)", marginTop: 12, textAlign: "center" }}>{r.errorMsg}</div>
          )}

          <button type="button" className="sample-link" onClick={browseSample}>
            Or browse a sample shortlist <span className="arrow">→</span>
          </button>
        </form>
      </div>
    </>
  );
}
