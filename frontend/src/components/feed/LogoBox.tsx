"use client";
import { useState } from "react";
import { logoLetter, logoAlt } from "@/lib/logo";

// The square logo box used on feed rows AND in the drawer title. Logos are resolved + validated
// SERVER-SIDE at ingestion (backend lib/logo_resolver) and shipped as `logo_url`, so the browser
// never guesses a domain: it renders the stored URL and falls back to the CSS letter avatar on a
// load error. (The old client-side resolution chain was removed — favicon services and squatter
// domains return real/placeholder images at HTTP 200, so <img onError> couldn't detect a bad logo
// and the card locked onto garbage. Server-side resolution is the only reliable place to validate.)
export function LogoBox({ company, logoUrl }: { company: string; logoUrl?: string | null }) {
  const [err, setErr] = useState(false);
  const showImg = !!logoUrl && !err;
  const cls = `logo${logoAlt(company) ? " alt" : ""}${showImg ? " has-img" : ""}`;
  return (
    <div className={cls} aria-hidden>
      {showImg ? (
        // eslint-disable-next-line @next/next/no-img-element -- server-resolved logo, letter on error
        <img key={logoUrl} src={logoUrl!} alt="" loading="lazy" onError={() => setErr(true)} />
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
