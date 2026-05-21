import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Pathfinder",
  description: "LinkedIn discovery: connections and internships tailored to you.",
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
      <body>{children}</body>
    </html>
  );
}
