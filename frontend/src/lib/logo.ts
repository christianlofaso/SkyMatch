// Logo box helpers, ported from option-j demo-data.js (smLogoHTML). The backend now ships
// Internship.logo_url (lib/logos.logo_url_for); when present we render it as an <img> contained
// in the box, and on load error we fall back to the letter avatar — so the box never goes empty.

/** First letter of the company, for the letter-avatar fallback. */
export function logoLetter(company: string): string {
  const c = (company || "").trim();
  return c ? c[0].toUpperCase() : "?";
}

/** Deterministic alt-gradient parity (iris/cyan vs ember/gold) so the feed isn't all one color.
 *  Keyed off the company name so the same company is always the same color. */
export function logoAlt(company: string): boolean {
  let h = 0;
  const s = company || "";
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
  return (h & 1) === 1;
}

/** Normalize a company name to a comparable slug ("Palantir Technologies" → "palantir"). */
export function companySlug(company: string): string | null {
  const slug = _norm(company);
  return slug.length >= 2 ? slug : null;
}

/** Logo URL for a CONFIDENT (real) domain — a name-resolved domain (resolveCompanyDomain).
 *  Google's favicon service is reliable for real domains (returns the brand favicon) and only
 *  globes on an unresolvable domain, which a confident domain isn't. (unavatar returns a 0-byte
 *  200 for some real domains, e.g. adobe.com, so it's reserved for the uncertain slug-guess.) */
export function faviconUrl(domain: string): string {
  return `https://www.google.com/s2/favicons?domain=${domain}&sz=128`;
}

function _norm(s: string): string {
  return (s || "")
    .toLowerCase()
    .replace(/&/g, "and")
    .replace(/\b(inc|llc|ltd|corp|corporation|company|technologies|technology|labs|holdings)\b\.?/g, " ")
    .replace(/[^a-z0-9]+/g, "");
}

const DOMAIN_CACHE_PREFIX = "pf:logodomain:";

/** Resolve a company NAME → its real primary domain via Clearbit's keyless autocomplete API
 *  (CORS-enabled, designed for client-side use). This is what gets the long tail right — it
 *  returns the EXACT domain including non-.com TLDs ("Sardine" → sardine.ai, "Notion" → notion.so)
 *  that a `<slug>.com` guess can't.
 *
 *  Confidence guard: only accept a suggestion whose normalized name OR domain-slug EXACTLY matches
 *  the company. This is deliberate — a generic name like "Terminal" returns many unrelated hits
 *  (Terminal Lance, Terminal X, …); without an exact match we return null and let the letter avatar
 *  show, rather than render the WRONG company's logo. Cached per-name in localStorage; any network/
 *  CORS/rate-limit failure resolves to null (graceful — the caller falls back to the slug guess /
 *  letter), so this never regresses below the prior behavior. */
export async function resolveCompanyDomain(company: string, signal?: AbortSignal): Promise<string | null> {
  const want = _norm(company);
  if (want.length < 2) return null;

  if (typeof window !== "undefined") {
    try {
      const cached = window.localStorage.getItem(DOMAIN_CACHE_PREFIX + want);
      if (cached !== null) return cached || null; // "" sentinel = resolved-to-nothing
    } catch { /* private mode */ }
  }

  let domain: string | null = null;
  try {
    const res = await fetch(
      `https://autocomplete.clearbit.com/v1/companies/suggest?query=${encodeURIComponent(company)}`,
      { signal },
    );
    if (res.ok) {
      const list = (await res.json()) as Array<{ name?: string; domain?: string }>;
      let nameHit: string | null = null;
      let domHit: string | null = null;
      for (const r of Array.isArray(list) ? list : []) {
        if (!r.domain) continue;
        const dom = r.domain.toLowerCase();
        const domSlug = dom.split(".")[0].replace(/[^a-z0-9]/g, "");
        if (!nameHit && _norm(r.name || "") === want) nameHit = dom;
        if (!domHit && domSlug === want) domHit = dom;
      }
      domain = nameHit || domHit;
    }
  } catch { /* network / CORS / abort — leave null */ }

  if (typeof window !== "undefined") {
    try { window.localStorage.setItem(DOMAIN_CACHE_PREFIX + want, domain || ""); } catch { /* ignore */ }
  }
  return domain;
}
