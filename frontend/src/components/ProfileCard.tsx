import type { ProfileAnalysis } from "@/types/skymatch";

export function ProfileCard({ profile }: { profile: ProfileAnalysis }) {
  return (
    <div className="border border-[var(--border)] p-6 flex flex-col gap-4">
      {/* Name + headline */}
      <div>
        <p className="mono text-xs uppercase tracking-widest mb-1" style={{ color: "var(--text-secondary)" }}>
          Profile
        </p>
        <h2 className="mono text-2xl font-semibold tracking-tight">{profile.full_name}</h2>
        <p className="text-sm mt-1" style={{ color: "var(--text-secondary)" }}>{profile.headline}</p>
      </div>

      {/* Meta row */}
      <div className="flex flex-wrap gap-4 text-sm" style={{ color: "var(--text-secondary)" }}>
        <span>📍 {profile.location}</span>
        <span>🎓 {profile.school}{profile.graduation_year ? ` '${String(profile.graduation_year).slice(2)}` : ""}</span>
        {profile.major && <span>📚 {profile.major}</span>}
        {profile.current_company && <span>🏢 {profile.current_company}</span>}
      </div>

      {/* Key values chips */}
      <div>
        <p className="mono text-xs uppercase tracking-widest mb-2" style={{ color: "var(--accent)" }}>
          Key values
        </p>
        <div className="flex flex-wrap gap-2">
          {profile.key_values.map((v) => (
            <span
              key={v}
              className="mono text-xs px-2 py-1 border"
              style={{ borderColor: "var(--accent)", color: "var(--accent)" }}
            >
              {v}
            </span>
          ))}
        </div>
      </div>

      {/* Skills */}
      {profile.technical_skills.length > 0 && (
        <div>
          <p className="mono text-xs uppercase tracking-widest mb-2" style={{ color: "var(--text-secondary)" }}>
            Skills
          </p>
          <div className="flex flex-wrap gap-2">
            {profile.technical_skills.map((s) => (
              <span
                key={s}
                className="mono text-xs px-2 py-1 border"
                style={{ borderColor: "var(--border)", color: "var(--text-secondary)" }}
              >
                {s}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
