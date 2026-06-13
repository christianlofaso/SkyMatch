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
