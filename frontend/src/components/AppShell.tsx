"use client";
import type { ReactNode } from "react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useSaved } from "@/lib/useSaved";
import { getRun, activeRunId, loadAnalyses } from "@/lib/storage";
import type { UnifiedProfile } from "@/types/skymatch";
import { bandOf } from "@/lib/bands";
import { SiteFooter } from "@/components/SiteFooter";

type Active = "feed" | "saved" | "profile" | "analyzer";

// Sidebar nav icons (option-j app-shell): Matches = target, analyzer = magnifier,
// saved = bookmark, profile = person.
const ICONS: Record<Active, ReactNode> = {
  feed: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden>
      <circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="3.5" />
    </svg>
  ),
  analyzer: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <circle cx="11" cy="11" r="7" /><path d="m21 21-4.3-4.3" />
    </svg>
  ),
  saved: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" />
    </svg>
  ),
  profile: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" /><circle cx="12" cy="7" r="4" />
    </svg>
  ),
};

// SkyMatch compass mark (option-j) — shell-local gradient id so it never collides.
const Mark = (
  <svg className="mark" viewBox="0 0 32 32" fill="none" aria-hidden>
    <defs>
      <linearGradient id="as-warm" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#FF8C5A" /><stop offset="1" stopColor="#FFD27A" /></linearGradient>
    </defs>
    <circle cx="16" cy="16" r="15" stroke="url(#as-warm)" strokeOpacity=".4" />
    <path d="M16 3.5c.9 6.2 2.4 9.6 8.5 12.5-6.1 2.9-7.6 6.3-8.5 12.5-.9-6.2-2.4-9.6-8.5-12.5C13.6 13.1 15.1 9.7 16 3.5Z" fill="url(#as-warm)" />
    <circle cx="16" cy="16" r="2.1" fill="#080A0F" /><circle cx="16" cy="16" r="1.1" fill="url(#as-warm)" />
  </svg>
);

interface LastRun { roles: number; setAside: number | null; }

// Shared sidebar shell for the "app" pages (results feed, saved, profile, analyzer). Ported
// from the option-j app shell (.app/.sidebar/.main): brand, "New match run", nav, a "Last run"
// info card, and the user chip. The Matches link points at the active run (the one being
// viewed this tab — demo or real), falling back to the most recent stored run.
export function AppShell({ active, children }: { active: Active; children: ReactNode }) {
  const { count } = useSaved();
  const [feedHref, setFeedHref] = useState("/");
  const [lastRun, setLastRun] = useState<LastRun | null>(null);
  const [profile, setProfile] = useState<UnifiedProfile | null>(null);

  useEffect(() => {
    const id = activeRunId();
    setFeedHref(id ? `/results/${id}` : "/");
    if (!id) return;
    const run = getRun(id);
    if (!run) return;
    setProfile(run.profile);
    // Unique roles across buckets (the feed dedupes by application_url the same way).
    const urls = new Set<string>();
    (["local", "big_tech", "startup", "reach"] as const).forEach((b) =>
      run.internships[b].forEach((it) => { if (it.application_url) urls.add(it.application_url); }),
    );
    // Set-aside = skip verdicts from the stored scoring state (null until scored).
    const analyses = loadAnalyses(id);
    let setAside: number | null = null;
    if (analyses) {
      const seen = new Set<string>();
      let n = 0;
      (["local", "big_tech", "startup", "reach"] as const).forEach((b) =>
        run.internships[b].forEach((it, i) => {
          if (!it.application_url || seen.has(it.application_url)) return;
          seen.add(it.application_url);
          if (bandOf(analyses[b]?.[i]) === "notfit") n++;
        }),
      );
      setAside = n;
    }
    setLastRun({ roles: urls.size, setAside });
  }, []);

  const items: Array<{ key: Active; label: string; href: string; badge?: number }> = [
    { key: "feed", label: "Matches", href: feedHref },
    { key: "analyzer", label: "Job fit analyzer", href: "/analyze" },
    { key: "saved", label: "Saved", href: "/saved", badge: count || undefined },
    { key: "profile", label: "Profile", href: "/profile" },
  ];

  const initial = (profile?.full_name || "?").trim()[0]?.toUpperCase() ?? "?";

  return (
    <div className="app">
      <div className="bg-fx" aria-hidden><div className="mesh" /><div className="topo" /></div>
      <div className="grain" aria-hidden>
        <svg xmlns="http://www.w3.org/2000/svg"><filter id="as-n"><feTurbulence type="fractalNoise" baseFrequency="0.8" numOctaves="2" stitchTiles="stitch" /></filter><rect width="100%" height="100%" filter="url(#as-n)" /></svg>
      </div>
      <aside className="sidebar">
        <Link href="/" className="brand" aria-label="SkyMatch home">{Mark}<span className="wm">SkyMatch</span></Link>
        <Link href="/" className="btn btn-primary newrun">New match run</Link>
        <nav className="snav" aria-label="App">
          {items.map((it) => (
            <Link key={it.key} href={it.href} className={`sitem${active === it.key ? " on" : ""}`}>
              {ICONS[it.key]}
              <span>{it.label}</span>
              {it.badge ? <span className="badge">{it.badge}</span> : null}
            </Link>
          ))}
        </nav>
        {lastRun && (
          <div className="lastrun">
            <div className="ll">Last run</div>
            <b>{lastRun.roles} role{lastRun.roles !== 1 ? "s" : ""}</b> matched to your profile.
            {lastRun.setAside != null && lastRun.setAside > 0 ? ` ${lastRun.setAside} set aside in plain sight.` : ""}
            <a href="/">Run match again</a>
          </div>
        )}
        {/* Static profile chip — avatar + name + school. No interaction (per request). */}
        <div className="userchip" style={lastRun ? undefined : { marginTop: "auto" }}>
          {profile && <span className="avatar" aria-hidden>{initial}</span>}
          <div style={{ minWidth: 0, flex: 1 }}>
            {profile && (
              <>
                <b>{profile.full_name}</b>
                <span className="sub">{profile.school || profile.headline || ""}</span>
              </>
            )}
          </div>
        </div>
      </aside>
      {/* Footer lives INSIDE main on shell pages so the sticky sidebar reaches the true page
          bottom (no dead gap below the profile card). The global SiteFooter skips these routes. */}
      <main className="main">{children}<SiteFooter inShell /></main>
    </div>
  );
}
