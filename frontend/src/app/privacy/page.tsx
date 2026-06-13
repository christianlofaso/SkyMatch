import Link from "next/link";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Privacy Policy — Skymatch",
};

// NOTE (M10): TEMPLATE scaffold — structure + the actual data practices are filled in, but
// the binding legal text must be reviewed/finalized by counsel before public launch. Marked
// visibly below so it can't ship as-is unnoticed.
export default function PrivacyPage() {
  return (
    <main className="min-h-screen px-6 py-16 flex justify-center">
      <article className="w-full max-w-2xl text-sm leading-relaxed" style={{ color: "var(--text-secondary)" }}>
        <Link
          href="/"
          className="mono text-[10px] uppercase tracking-widest hover:opacity-70"
          style={{ color: "var(--text-secondary)" }}
        >
          ← back
        </Link>

        <div
          className="mt-6 mono text-[10px] uppercase tracking-widest border px-3 py-2"
          style={{ borderColor: "var(--border)", color: "var(--text-secondary)" }}
        >
          Template — pending legal review. Not yet binding.
        </div>

        <h1 className="mt-6 text-2xl font-semibold" style={{ color: "var(--text-primary)" }}>
          Privacy Policy
        </h1>
        <p className="mt-1 mono text-[10px]" style={{ color: "var(--text-secondary)" }}>
          Last updated: TBD
        </p>

        <Section title="What we collect">
          <ul className="list-disc pl-5 space-y-1">
            <li>
              <strong>Profile input you provide</strong> — a LinkedIn profile URL or pasted
              profile text, and optionally an uploaded resume, used to generate your results.
            </li>
            <li>
              <strong>Account data</strong> — if you sign in, your email address and a user
              identifier (via Supabase magic-link auth).
            </li>
            <li>
              <strong>Usage records</strong> — counts of analyses/searches you run (for daily
              limits) and aggregate, approximate cost records for accounting.
            </li>
          </ul>
        </Section>

        <Section title="How we use it">
          <p>
            To produce your internship matches and job-fit analyses, to enforce per-account
            usage limits and prevent abuse, and to operate and improve the service. We do not
            sell your personal information.
          </p>
        </Section>

        <Section title="Third-party processors">
          <p>
            We share the minimum necessary data with service providers that power the product:
          </p>
          <ul className="list-disc pl-5 space-y-1 mt-2">
            <li><strong>Anthropic</strong> — AI model inference on your profile/job text.</li>
            <li><strong>Voyage AI</strong> — text embeddings for matching.</li>
            <li><strong>Firecrawl</strong> — fetching/rendering job-posting pages you submit.</li>
            <li><strong>LinkdAPI</strong> — retrieving public LinkedIn profile data you submit.</li>
            <li><strong>Supabase</strong> — authentication and database hosting.</li>
          </ul>
        </Section>

        <Section title="Data retention">
          <p>
            Account and usage data are retained while your account is active. Cached analysis
            results expire automatically (typically within 30 days). Aggregate, anonymized cost
            records may be retained longer for accounting. You can delete your account at any
            time (see below), which removes your account and usage data.
          </p>
        </Section>

        <Section title="Your choices &amp; deletion">
          <p>
            You can delete your account and associated data from the{" "}
            <Link href="/account" className="underline" style={{ color: "var(--accent)" }}>
              Account
            </Link>{" "}
            page. For other privacy requests, contact us at the address below.
          </p>
        </Section>

        <Section title="Contact">
          <p>privacy@TBD — to be finalized before launch.</p>
        </Section>

        <p className="mt-10 mono text-[10px]" style={{ color: "var(--text-secondary)" }}>
          See also our{" "}
          <Link href="/terms" className="underline" style={{ color: "var(--accent)" }}>
            Terms of Service
          </Link>
          .
        </p>
      </article>
    </main>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-8">
      <h2 className="text-sm font-semibold uppercase tracking-wide" style={{ color: "var(--text-primary)" }}>
        {title}
      </h2>
      <div className="mt-2 space-y-2">{children}</div>
    </section>
  );
}
