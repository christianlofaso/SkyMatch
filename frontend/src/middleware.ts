import { NextRequest, NextResponse } from "next/server";

/**
 * Edge Basic-Auth wall for non-public environments (e.g. staging).
 *
 * Why this exists: the app-level magic-link sign-in is OPEN self-signup, so it is
 * friction, not access control — anyone can register their own email and get in,
 * and the page is reachable by anyone with the URL. This puts a single shared
 * username/password in front of the WHOLE site at the edge, before any app code runs.
 *
 * It is gated entirely on env vars: if BASIC_AUTH_USER / BASIC_AUTH_PASS are unset,
 * the middleware is a no-op. So set them ONLY in the environment you want private
 * (staging) — local dev and prod stay open unless you explicitly set them there too.
 */
export function middleware(req: NextRequest) {
  const USER = process.env.BASIC_AUTH_USER;
  const PASS = process.env.BASIC_AUTH_PASS;

  // Not configured for this environment → don't gate anything.
  if (!USER || !PASS) return NextResponse.next();

  const header = req.headers.get("authorization");
  if (header?.startsWith("Basic ")) {
    // atob is available in the Edge runtime; decode "user:pass".
    const decoded = atob(header.slice(6));
    const sep = decoded.indexOf(":");
    const user = decoded.slice(0, sep);
    const pass = decoded.slice(sep + 1);
    if (user === USER && pass === PASS) return NextResponse.next();
  }

  return new NextResponse("Authentication required.", {
    status: 401,
    headers: { "WWW-Authenticate": 'Basic realm="SkyMatch staging", charset="UTF-8"' },
  });
}

export const config = {
  // Gate everything except Next internals + the favicon so the prompt fires on first load.
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
