import type { Metadata } from "next";
import "./globals.css";
import { AuthProvider } from "@/lib/auth-context";
import { SiteFooter } from "@/components/SiteFooter";

export const metadata: Metadata = {
  metadataBase: new URL("https://skymatch.ai"),
  title: "SkyMatch",
  description: "Paste your profile, get internships matched to your real experience — banded by how ready you are.",
  openGraph: {
    title: "SkyMatch",
    description: "Internships matched to your real experience.",
    url: "https://skymatch.ai",
    siteName: "SkyMatch",
  },
};

/** SkyMatch webfonts (option-j look): Fraunces (display) + General Sans (body) + Spline Sans Mono. */
function FontLinks() {
  return (
    <>
      <link rel="preconnect" href="https://fonts.googleapis.com" />
      <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
      <link
        href="https://api.fontshare.com/v2/css?f[]=general-sans@400,500,600&display=swap"
        rel="stylesheet"
      />
      <link
        href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,400;0,9..144,500;0,9..144,600;1,9..144,400;1,9..144,500;1,9..144,600&family=Spline+Sans+Mono:wght@400;500&display=swap"
        rel="stylesheet"
      />
    </>
  );
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <FontLinks />
      </head>
      <body>
        <AuthProvider>{children}</AuthProvider>
        <SiteFooter />
      </body>
    </html>
  );
}
