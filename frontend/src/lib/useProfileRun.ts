"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { parseResume, runPathfinderStream } from "@/lib/api";
import { type UnifiedProfile } from "@/types/pathfinder";
import { saveRun } from "@/lib/storage";

// All of the profile→run behaviour (LinkedIn URL / paste / résumé upload → /run/stream →
// /results), with NO markup. The landing's ProfileInput component renders the option-j UI
// on top of this shared hook.

export type RunTab = "url" | "paste";
type Status = "idle" | "loading" | "error";
type UploadStatus = "idle" | "uploading" | "done" | "error";
type Step = "profile" | "internships" | null;

const MAX_BYTES = 5 * 1024 * 1024;
const ALLOWED_EXTS = [".pdf", ".docx"];

export function useProfileRun() {
  const router = useRouter();

  const [tab, setTab] = useState<RunTab>("url");
  const [status, setStatus] = useState<Status>("idle");
  const [step, setStep] = useState<Step>(null);
  const [errorMsg, setErrorMsg] = useState("");

  const [url, setUrl] = useState("");
  const [text, setText] = useState("");

  const fileInputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState("");
  const [uploadStatus, setUploadStatus] = useState<UploadStatus>("idle");
  const [parsedProfile, setParsedProfile] = useState<UnifiedProfile | null>(null);
  const [profileId, setProfileId] = useState<string | null>(null);

  function switchTab(t: RunTab) {
    setTab(t);
    setErrorMsg("");
    setStatus("idle");
  }

  function validateFile(f: File): string {
    const ext = "." + f.name.split(".").pop()!.toLowerCase();
    if (!ALLOWED_EXTS.includes(ext)) return "Only PDF and DOCX files are accepted.";
    if (f.size > MAX_BYTES) return "File exceeds the 5 MB limit.";
    return "";
  }

  async function parse(f: File) {
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

  function onFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0] ?? null;
    if (!f) return;
    const err = validateFile(f);
    setFile(f);
    setFileError(err);
    setParsedProfile(null);
    setProfileId(null);
    if (!err) parse(f);
  }

  function onFileDrop(f: File) {
    const err = validateFile(f);
    setFile(f);
    setFileError(err);
    setParsedProfile(null);
    setProfileId(null);
    setUploadStatus("idle");
    if (fileInputRef.current) fileInputRef.current.value = "";
    if (!err) parse(f);
  }

  function pickFile() {
    fileInputRef.current?.click();
  }

  function resetUpload() {
    setFile(null);
    setFileError("");
    setUploadStatus("idle");
    setParsedProfile(null);
    setProfileId(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  async function submit(e: React.FormEvent) {
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

  const loading = status === "loading";
  const hasLinkedin = tab === "url" ? url.trim().length > 0 : text.trim().length > 0;
  const hasResume = uploadStatus === "done" && profileId !== null;
  const canSubmit = (hasLinkedin || hasResume) && !loading && uploadStatus !== "uploading";

  return {
    // state
    tab, url, text, file, fileError, uploadStatus, parsedProfile, status, step, errorMsg,
    // derived
    loading, hasLinkedin, hasResume, canSubmit,
    // refs + actions
    fileInputRef, switchTab, setUrl, setText, onFileChange, onFileDrop, pickFile, resetUpload, submit,
  };
}
