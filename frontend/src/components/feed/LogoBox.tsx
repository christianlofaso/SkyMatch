"use client";
import { useEffect, useMemo, useState } from "react";
import { logoLetter, logoAlt, companySlug, resolveCompanyDomain, faviconUrl } from "@/lib/logo";

const unavatar = (domain: string) => `https://unavatar.io/${encodeURIComponent(domain)}`;

// The square logo box used on feed rows AND in the drawer title. It resolves the company NAME to
// its real domain (Clearbit autocomplete, see resolveCompanyDomain) and walks an ordered chain of
// logo sources — backend logo_url → unavatar(resolved domain) → unavatar(<slug>.com guess) — render-
// ing the first that loads and advancing on each load error; when the chain is exhausted it shows
// the CSS letter avatar, so the box is never empty AND never stuck on a generic placeholder. The
// drawer's larger box styling comes from the `.dr-title .logo` parent selector.
export function LogoBox({ company, logoUrl }: { company: string; logoUrl?: string | null }) {
  // undefined = still resolving the name→domain; string = resolved domain; null = no confident match.
  const [domain, setDomain] = useState<string | null | undefined>(undefined);
  useEffect(() => {
    let alive = true;
    const ctrl = new AbortController();
    resolveCompanyDomain(company, ctrl.signal).then((d) => { if (alive) setDomain(d); }).catch(() => {});
    return () => { alive = false; ctrl.abort(); };
  }, [company]);

  const sources = useMemo(() => {
    const out: string[] = [];
    if (logoUrl) out.push(logoUrl);
    // While resolving, show only a backend logo (else the letter) — avoids flashing a guess.
    if (domain !== undefined) {
      // Confident name-resolved domain → reliable Google favicon. Uncertain <slug>.com → unavatar,
      // whose honest error lets the chain fall through to the letter (Google would globe a wrong guess).
      if (domain) out.push(faviconUrl(domain));
      const slug = companySlug(company);
      if (slug) out.push(unavatar(`${slug}.com`));
    }
    // Dedupe: identical URLs would stall the onError chain (same key → no remount → no re-error).
    return Array.from(new Set(out));
  }, [company, logoUrl, domain]);

  const [i, setI] = useState(0);
  const sig = sources.join("|");
  // Restart the chain at the most-preferred source whenever the list changes (e.g. the async
  // domain just resolved, prepending a better source).
  useEffect(() => { setI(0); }, [sig]);

  const src = i < sources.length ? sources[i] : null;
  const cls = `logo${logoAlt(company) ? " alt" : ""}${src ? " has-img" : ""}`;
  return (
    <div className={cls} aria-hidden>
      {src ? (
        // eslint-disable-next-line @next/next/no-img-element -- remote logos, advances/letters on error
        <img key={src} src={src} alt="" loading="lazy" onError={() => setI((n) => n + 1)} />
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
