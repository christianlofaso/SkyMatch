"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

// App-shell routes (AppShell pages) render this footer INSIDE their main column (inShell) so the
// sticky sidebar can reach the true page bottom. The GLOBAL instance must therefore skip them —
// else it both double-renders AND leaves a dead gap below the sidebar (a below-.app footer band).
const isShellRoute = (p: string) =>
  p === "/saved" || p === "/profile" || p === "/analyze" || p.startsWith("/results/");

// Minimal site-wide legal footer. The landing ("/") renders its own rich option-j footer,
// so this one hides there to avoid a double footer; it stays on every other route for
// legal/account reachability.
export function SiteFooter({ inShell = false }: { inShell?: boolean }) {
  const pathname = usePathname();
  // The global instance hides on the landing and on app-shell routes (those render it inShell).
  if (!inShell && (pathname === "/" || isShellRoute(pathname))) return null;

  return (
    <footer
      className="mono text-[10px] uppercase tracking-widest flex items-center justify-center gap-5 py-6"
      style={{ color: "var(--text-secondary)" }}
    >
      <Link href="/" className="hover:opacity-70" style={{ color: "var(--text-primary)" }}>
        Skymatch
      </Link>
      <span style={{ opacity: 0.4 }}>·</span>
      <Link href="/privacy" className="hover:opacity-70">Privacy</Link>
      <Link href="/terms" className="hover:opacity-70">Terms</Link>
      <Link href="/account" className="hover:opacity-70">Account</Link>
    </footer>
  );
}
