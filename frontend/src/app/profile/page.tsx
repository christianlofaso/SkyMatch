"use client";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { getRun, activeRunId } from "@/lib/storage";
import type { UnifiedProfile } from "@/types/skymatch";

// Six skill axes for the radar. Axis scores are an ILLUSTRATIVE derivation from the profile's
// skills (keyword buckets) — not a backend metric. They give the chart shape; don't read them
// as a precise assessment.
const AXES: Array<{ label: string; kw: string[] }> = [
  { label: "Frontend", kw: ["react", "frontend", "css", "html", "javascript", "typescript", "ui", "next", "tailwind", "vue", "svelte"] },
  { label: "Backend", kw: ["node", "python", "java", "go ", "golang", "api", "django", "flask", "backend", "express", "rust", "ruby", "php"] },
  { label: "Systems", kw: ["c++", "c ", "rust", "systems", "linux", "firmware", "kernel", "embedded", "os", "cuda", "assembly"] },
  { label: "Data", kw: ["sql", "data", "pandas", "spark", "etl", "analytics", "warehouse", "bigquery", "postgres", "database"] },
  { label: "Product", kw: ["product", "design", "figma", "ux", "user research", "prototyp"] },
  { label: "ML", kw: ["ml", "machine learning", "pytorch", "tensorflow", "model", "nlp", "deep learning", "scikit", "neural", "ai"] },
];

function radarValues(skills: string[]): number[] {
  const hay = skills.map((s) => s.toLowerCase());
  return AXES.map((axis) => {
    const count = hay.filter((s) => axis.kw.some((k) => s.includes(k))).length;
    if (count === 0) return 0.18; // a faint floor so the polygon stays a hexagon, not a spike
    return Math.min(1, 0.42 + 0.2 * count);
  });
}

function Radar({ skills }: { skills: string[] }) {
  const vals = radarValues(skills);
  const cx = 150, cy = 150, R = 108;
  const pt = (i: number, r: number) => {
    const a = (-90 + i * 60) * (Math.PI / 180);
    return [cx + Math.cos(a) * r, cy + Math.sin(a) * r];
  };
  const ring = (frac: number) => AXES.map((_, i) => pt(i, R * frac).join(",")).join(" ");
  const dataPoly = vals.map((v, i) => pt(i, R * v).join(",")).join(" ");
  return (
    <svg viewBox="0 0 300 300" role="img" aria-label="Skill profile radar">
      {[0.25, 0.5, 0.75, 1].map((f) => (
        <polygon key={f} points={ring(f)} fill="none" stroke="var(--line)" strokeWidth="1" />
      ))}
      {AXES.map((_, i) => {
        const [x, y] = pt(i, R);
        return <line key={i} x1={cx} y1={cy} x2={x} y2={y} stroke="var(--line)" strokeWidth="1" />;
      })}
      <polygon points={dataPoly} fill="rgba(255,140,90,.16)" stroke="var(--ember)" strokeWidth="2" />
      {vals.map((v, i) => {
        const [x, y] = pt(i, R * v);
        return <circle key={i} cx={x} cy={y} r="3" fill="var(--ember)" />;
      })}
      {AXES.map((axis, i) => {
        const [x, y] = pt(i, R + 18);
        return (
          <text
            key={axis.label}
            x={x}
            y={y}
            fill="var(--faint)"
            fontSize="10"
            fontFamily="var(--mono)"
            textAnchor={x < cx - 5 ? "end" : x > cx + 5 ? "start" : "middle"}
            dominantBaseline="middle"
          >
            {axis.label}
          </text>
        );
      })}
    </svg>
  );
}

export default function ProfilePage() {
  const [profile, setProfile] = useState<UnifiedProfile | null>(null);
  const [missing, setMissing] = useState(false);

  useEffect(() => {
    const id = activeRunId();
    const run = id ? getRun(id) : null;
    if (run?.profile) setProfile(run.profile as UnifiedProfile);
    else setMissing(true);
  }, []);

  const allSkills = useMemo(() => {
    if (!profile) return [];
    const fromCtx = (profile.skills_with_context ?? []).map((s) => s.skill);
    const fromProj = (profile.projects ?? []).flatMap((p) => p.technologies ?? []);
    return Array.from(new Set([...(profile.technical_skills ?? []), ...fromCtx, ...fromProj]));
  }, [profile]);

  if (missing) {
    return (
      <AppShell active="profile">
        <div className="topbar"><div><h1 className="pg">Profile</h1></div></div>
        <p className="pg-sub" style={{ marginTop: 24 }}>
          No profile yet. <Link href="/" style={{ color: "var(--ember-soft)" }}>Run your profile</Link> to populate this page.
        </p>
      </AppShell>
    );
  }
  if (!profile) {
    return (
      <AppShell active="profile">
        <div style={{ display: "grid", placeItems: "center", minHeight: "50vh" }}><span className="az-spinner" /></div>
      </AppShell>
    );
  }

  const initial = (profile.full_name || "?").trim()[0]?.toUpperCase() ?? "?";

  return (
    <AppShell active="profile">
      <div className="topbar"><div><h1 className="pg">Profile</h1><p className="pg-sub">What SkyMatch read from your background.</p></div></div>

      <div className="pcard">
        <div className="avatar">{initial}</div>
        <div>
          <h2>{profile.full_name}</h2>
          <div className="pline">{profile.headline || profile.field_of_interest}</div>
          <div className="pmeta">
            {profile.location && <span>📍 {profile.location}</span>}
            {profile.school && <span>🎓 {profile.school}{profile.major ? ` · ${profile.major}` : ""}</span>}
            {profile.graduation_year && <span>🗓 Class of {profile.graduation_year}</span>}
          </div>
        </div>
      </div>

      <div className="pgrid">
        {/* Left: summary + experience */}
        <div>
          {profile.key_values?.length > 0 && (
            <div className="pblock">
              <div className="fit-label">Summary</div>
              <p className="ptext">{profile.key_values.join(" · ")}</p>
            </div>
          )}

          <div className="pblock">
            <div className="fit-label">Experience</div>
            {(profile.work_experience ?? []).length === 0 && (profile.projects ?? []).length === 0 ? (
              <p className="ptext" style={{ color: "var(--muted)" }}>No experience parsed.</p>
            ) : (
              <>
                {(profile.work_experience ?? []).map((w, i) => (
                  <div className="xp" key={`w${i}`}>
                    <div className="logo">{(w.company || "?").trim()[0]?.toUpperCase()}</div>
                    <div>
                      <div className="xt">{w.title}</div>
                      <div className="xs">{w.company}{w.start_date ? ` · ${w.start_date}${w.end_date ? `–${w.end_date}` : ""}` : ""}</div>
                      {w.description && <p>{w.description}</p>}
                    </div>
                  </div>
                ))}
                {(profile.projects ?? []).map((p, i) => (
                  <div className="xp" key={`p${i}`}>
                    <div className="logo">⚙</div>
                    <div>
                      <div className="xt">{p.name}</div>
                      <div className="xs">{(p.technologies ?? []).join(" · ")}</div>
                      {p.description && <p>{p.description}</p>}
                    </div>
                  </div>
                ))}
              </>
            )}
          </div>
        </div>

        {/* Right: skills + radar */}
        <div>
          <div className="pblock">
            <div className="fit-label">Skills SkyMatch detected</div>
            <div className="skill-chips">
              {allSkills.length === 0 ? (
                <span className="grow-label">No skills parsed.</span>
              ) : (
                allSkills.map((s) => <span className="req-chip on" key={s}>{s}</span>)
              )}
            </div>
          </div>

          <div className="pblock">
            <div className="fit-label">Field map</div>
            <div className="radar-wrap">
              <Radar skills={allSkills} />
              <div className="rsub">Illustrative — shape derived from your detected skills.</div>
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
