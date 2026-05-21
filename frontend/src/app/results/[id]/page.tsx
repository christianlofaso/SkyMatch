"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { RunResponseSchema, type RunResponse } from "@/types/pathfinder";
import { ProfileCard } from "@/components/ProfileCard";
import { ConnectionCard } from "@/components/ConnectionCard";
import { BucketSection } from "@/components/BucketSection";

export default function ResultsPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [data, setData] = useState<RunResponse | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const raw = sessionStorage.getItem(id);
    if (!raw) {
      setError("Session expired — go back and try again.");
      return;
    }
    const parsed = RunResponseSchema.safeParse(JSON.parse(raw));
    if (!parsed.success) {
      setError("Could not load results. Please try again.");
      return;
    }
    setData(parsed.data);
  }, [id]);

  if (error) {
    return (
      <main className="min-h-screen flex items-center justify-center px-6">
        <div className="text-center flex flex-col gap-4">
          <p className="text-sm" style={{ color: "var(--text-secondary)" }}>{error}</p>
          <button
            onClick={() => router.push("/")}
            className="mono text-xs uppercase tracking-widest"
            style={{ color: "var(--accent)" }}
          >
            ← Back
          </button>
        </div>
      </main>
    );
  }

  if (!data) {
    return (
      <main className="min-h-screen flex items-center justify-center">
        <span
          className="inline-block w-3 h-3 rounded-full animate-pulse"
          style={{ background: "var(--accent)" }}
        />
      </main>
    );
  }

  const { profile, connections, internships } = data;

  return (
    <main className="min-h-screen px-6 py-12 flex flex-col items-center gap-12">
      <div className="w-full max-w-3xl flex flex-col gap-12">

        {/* Back link */}
        <button
          onClick={() => router.push("/")}
          className="mono text-xs uppercase tracking-widest self-start"
          style={{ color: "var(--text-secondary)" }}
        >
          ← New search
        </button>

        {/* 1. Profile summary */}
        <ProfileCard profile={profile} />

        {/* 2. Connections */}
        <section className="flex flex-col gap-6">
          <div>
            <h2 className="mono text-lg font-semibold uppercase tracking-widest" style={{ color: "var(--text-primary)" }}>
              Suggested Connections
            </h2>
            <p className="text-xs mt-1" style={{ color: "var(--text-secondary)" }}>
              10 people who share a strong commonality with your background
            </p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {connections.map((c, i) => (
              <ConnectionCard key={i} connection={c} />
            ))}
          </div>
        </section>

        {/* 3. Internship buckets */}
        <section className="flex flex-col gap-10">
          <div>
            <h2 className="mono text-lg font-semibold uppercase tracking-widest" style={{ color: "var(--text-primary)" }}>
              Internship Opportunities
            </h2>
            <p className="text-xs mt-1" style={{ color: "var(--text-secondary)" }}>
              Matched to your profile across 4 buckets
            </p>
          </div>
          <BucketSection bucket="local" internships={internships.local} />
          <BucketSection bucket="big_tech" internships={internships.big_tech} />
          <BucketSection bucket="startup" internships={internships.startup} />
          <BucketSection bucket="reach" internships={internships.reach} />
        </section>

      </div>
    </main>
  );
}
