"use client";
import { useState } from "react";
import { logoLetter, logoAlt } from "@/lib/logo";

// The square logo box used on feed rows AND in the drawer title. Renders the backend's
// logo_url as a contained <img>; on a load error (or no url) it falls back to the letter
// avatar so the box is never empty. The drawer's larger box styling comes from the
// `.dr-title .logo` parent selector — no variant prop needed.
export function LogoBox({ company, logoUrl }: { company: string; logoUrl?: string | null }) {
  const [err, setErr] = useState(false);
  const showImg = !!logoUrl && !err;
  const cls = `logo${logoAlt(company) ? " alt" : ""}${showImg ? " has-img" : ""}`;
  return (
    <div className={cls} aria-hidden>
      {showImg ? (
        // eslint-disable-next-line @next/next/no-img-element -- remote favicons, letter fallback on error
        <img src={logoUrl!} alt="" loading="lazy" onError={() => setErr(true)} />
      ) : (
        logoLetter(company)
      )}
    </div>
  );
}

export const BookmarkIcon = (
  <svg
    width="15"
    height="15"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
  >
    <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" />
  </svg>
);
