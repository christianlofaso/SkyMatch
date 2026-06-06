import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";
import { AuthProvider } from "@/lib/auth-context";

export const metadata: Metadata = {
  title: "Pathfinder",
  description: "LinkedIn discovery: internships tailored to you.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link
          href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=Inter:wght@400;500;600&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>
        <AuthProvider>{children}</AuthProvider>
        <SiteFooter />
      </body>
    </html>
  );
}

function SiteFooter() {
  return (
    <footer
      className="mono text-[10px] uppercase tracking-widest flex justify-center gap-5 py-6"
      style={{ color: "var(--text-secondary)" }}
    >
      <Link href="/privacy" className="hover:opacity-70">Privacy</Link>
      <Link href="/terms" className="hover:opacity-70">Terms</Link>
      <Link href="/account" className="hover:opacity-70">Account</Link>
    </footer>
  );
}
