// Logo box helpers. The backend resolves + validates each company's logo SERVER-SIDE at ingestion
// (lib/logo_resolver) and ships it as Internship.logo_url; the frontend renders that as an <img>
// and falls back to the letter avatar on a load error. No client-side domain resolution lives here
// anymore — favicon services and squatter domains return real/placeholder images at HTTP 200, so a
// browser <img onError> chain can't tell a good logo from a bad one (it locks onto garbage). That's
// why resolution + validation moved to the server (see backend/lib/logo_resolver).

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
