"use client";

import { useState } from "react";
import type {
  AnalysisResponse,
  MatchItem,
  GapItem,
  Roadmap,
  RoadmapItem,
  RoadmapResource,
  ProjectSuggestion,
} from "@/types/pathfinder";

interface Props {
  data: AnalysisResponse;
  onBack: () => void;
}

const CATEGORY_ORDER = ["technical", "experience", "education", "domain", "soft"] as const;
const CATEGORY_LABELS: Record<string, string> = {
  technical: "Technical",
  experience: "Experience",
  education: "Education",
  domain: "Domain",
  soft: "Soft Skills",
};

const SEVERITY_COLORS: Record<string, string> = {
  critical: "#ff6b6b",
  moderate: "#f59e0b",
  minor: "var(--text-secondary)",
};

const STRENGTH_COLORS: Record<string, string> = {
  strong: "var(--accent)",
  partial: "#f59e0b",
};

const STRENGTH_LABELS: Record<string, string> = {
  strong: "✓ strong",
  partial: "~ partial",
};

const PRIORITY_COLORS: Record<string, string> = {
  must_have: "#ff6b6b",
  nice_to_have: "var(--text-secondary)",
};

const PRIORITY_LABELS: Record<string, string> = {
  must_have: "must have",
  nice_to_have: "nice to have",
};

function ResourceLink({ resource }: { resource: RoadmapResource }) {
  return (
    <a
      href={resource.url}
      target="_blank"
      rel="noopener noreferrer"
      className="flex flex-col gap-1 py-2 px-3 border hover:opacity-80 transition-opacity"
      style={{ borderColor: "var(--border)" }}
    >
      <span className="text-sm" style={{ color: "var(--accent)" }}>
        {resource.title}
      </span>
      <div className="flex gap-2 flex-wrap">
        <span
          className="mono text-xs px-1.5 py-0.5 border"
          style={{ borderColor: "var(--border)", color: "var(--text-secondary)" }}
        >
          {resource.type}
        </span>
        <span
          className="mono text-xs px-1.5 py-0.5 border"
          style={{ borderColor: "var(--border)", color: "var(--text-secondary)" }}
        >
          {resource.duration}
        </span>
        <span
          className="mono text-xs px-1.5 py-0.5 border"
          style={{
            borderColor: resource.cost === "free" ? "var(--accent)" : "var(--border)",
            color: resource.cost === "free" ? "var(--accent)" : "var(--text-secondary)",
          }}
        >
          {resource.cost}
        </span>
      </div>
    </a>
  );
}

function RoadmapItemRow({ item }: { item: RoadmapItem }) {
  return (
    <div
      className="flex flex-col gap-3 py-4 border-b"
      style={{ borderColor: "var(--border)" }}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="flex flex-col gap-1">
          <p className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>
            {item.skill}
          </p>
          <p className="text-xs" style={{ color: "var(--text-secondary)" }}>
            {item.why_it_matters}
          </p>
        </div>
        <div className="flex flex-col items-end gap-1 shrink-0">
          <span
            className="mono text-xs px-1.5 py-0.5 border uppercase"
            style={{
              borderColor: PRIORITY_COLORS[item.priority],
              color: PRIORITY_COLORS[item.priority],
            }}
          >
            {PRIORITY_LABELS[item.priority]}
          </span>
          <span className="mono text-xs" style={{ color: "var(--text-secondary)" }}>
            {item.timeline}
          </span>
        </div>
      </div>

      <blockquote
        style={{
          borderLeft: "2px solid var(--accent)",
          paddingLeft: "12px",
          marginLeft: "4px",
          color: "var(--text-primary)",
          fontSize: "13px",
          lineHeight: "1.5",
        }}
      >
        <span
          className="mono text-xs uppercase tracking-widest block mb-1"
          style={{ color: "var(--accent)" }}
        >
          milestone
        </span>
        {item.milestone}
      </blockquote>

      {item.resources.length > 0 && (
        <div className="flex flex-col gap-2 mt-1">
          {item.resources.map((r, i) => (
            <ResourceLink key={`res-${i}`} resource={r} />
          ))}
        </div>
      )}
    </div>
  );
}

function RoadmapSection({
  roadmap,
  roadmapNote,
}: {
  roadmap?: Roadmap | null;
  roadmapNote?: string | null;
}) {
  if (!roadmap && !roadmapNote) return null;

  return (
    <section>
      <div
        className="flex items-baseline gap-3 pb-2 mb-2 border-b"
        style={{ borderColor: "var(--border)" }}
      >
        <h2
          className="mono text-xs uppercase tracking-widest font-semibold"
          style={{ color: "var(--accent)" }}
        >
          Your prep roadmap
        </h2>
        {roadmap && (
          <span className="text-xs" style={{ color: "var(--text-secondary)" }}>
            {roadmap.total_timeline}
          </span>
        )}
      </div>

      {roadmapNote ? (
        <p
          className="text-sm mt-3"
          style={{ color: "var(--text-secondary)", fontStyle: "italic" }}
        >
          {roadmapNote}
        </p>
      ) : roadmap ? (
        <>
          <p
            className="text-sm mt-3 mb-2"
            style={{ color: "var(--text-secondary)" }}
          >
            {roadmap.summary}
          </p>
          {roadmap.items.map((item, i) => (
            <RoadmapItemRow key={`roadmap-${i}`} item={item} />
          ))}
        </>
      ) : null}
    </section>
  );
}

function ProjectSection({ project }: { project: ProjectSuggestion }) {
  const [showStretch, setShowStretch] = useState(false);

  return (
    <section>
      <div
        className="flex items-baseline gap-3 pb-2 mb-2 border-b"
        style={{ borderColor: "var(--border)" }}
      >
        <h2
          className="mono text-xs uppercase tracking-widest font-semibold"
          style={{ color: "var(--accent)" }}
        >
          Build this to apply
        </h2>
        <span className="text-xs" style={{ color: "var(--text-secondary)" }}>
          {project.estimated_time}
        </span>
      </div>

      <div className="flex flex-col gap-4 mt-3">
        <div className="flex flex-col gap-1">
          <h3
            className="text-base font-semibold"
            style={{ color: "var(--text-primary)" }}
          >
            {project.title}
          </h3>
          <p className="text-sm" style={{ color: "var(--text-secondary)" }}>
            {project.pitch}
          </p>
        </div>

        <p className="text-sm" style={{ color: "var(--text-primary)" }}>
          {project.why_this_role}
        </p>

        <div>
          <p
            className="mono text-xs uppercase tracking-widest mb-2"
            style={{ color: "var(--text-secondary)" }}
          >
            MVP features
          </p>
          <ul className="flex flex-col gap-1">
            {project.mvp_features.map((feat, i) => (
              <li
                key={`feat-${i}`}
                className="text-sm"
                style={{ color: "var(--text-primary)" }}
              >
                <span style={{ color: "var(--accent)" }}>›</span> {feat}
              </li>
            ))}
          </ul>
        </div>

        <div>
          <p
            className="mono text-xs uppercase tracking-widest mb-2"
            style={{ color: "var(--text-secondary)" }}
          >
            Tech stack
          </p>
          <div className="flex flex-wrap gap-2">
            {project.tech_stack.map((tech, i) => (
              <span
                key={`tech-${i}`}
                className="mono text-xs px-2 py-1 border"
                style={{ borderColor: "var(--border)", color: "var(--accent)" }}
              >
                {tech}
              </span>
            ))}
          </div>
        </div>

        {project.stretch_goals.length > 0 && (
          <div>
            <button
              type="button"
              onClick={() => setShowStretch((s) => !s)}
              className="mono text-xs uppercase tracking-widest hover:opacity-70 transition-opacity"
              style={{ color: "var(--text-secondary)" }}
            >
              {showStretch ? "▼" : "▶"} {showStretch ? "Hide" : "Show"} stretch goals
            </button>
            {showStretch && (
              <ul className="flex flex-col gap-1 mt-2">
                {project.stretch_goals.map((goal, i) => (
                  <li
                    key={`stretch-${i}`}
                    className="text-sm"
                    style={{ color: "var(--text-primary)" }}
                  >
                    <span style={{ color: "var(--accent)" }}>›</span> {goal}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        <blockquote
          style={{
            borderLeft: "2px solid var(--accent)",
            paddingLeft: "12px",
            marginLeft: "4px",
            color: "var(--text-primary)",
            fontSize: "13px",
            lineHeight: "1.6",
          }}
        >
          <span
            className="mono text-xs uppercase tracking-widest block mb-2"
            style={{ color: "var(--accent)" }}
          >
            interview talking points
          </span>
          <ul className="flex flex-col gap-1.5">
            {project.interview_talking_points.map((p, i) => (
              <li key={`talk-${i}`}>{p}</li>
            ))}
          </ul>
        </blockquote>
      </div>
    </section>
  );
}

function MatchRow({ match }: { match: MatchItem }) {
  return (
    <div className="flex flex-col gap-2 py-3 border-b" style={{ borderColor: "var(--border)" }}>
      <div className="flex items-start justify-between gap-4">
        <p className="text-sm" style={{ color: "var(--text-primary)" }}>
          {match.requirement}
          {match.must_have && (
            <span className="mono text-xs ml-2" style={{ color: "var(--text-secondary)" }}>
              required
            </span>
          )}
        </p>
        <span
          className="mono text-xs shrink-0 px-1.5 py-0.5 border"
          style={{
            borderColor: STRENGTH_COLORS[match.match_strength],
            color: STRENGTH_COLORS[match.match_strength],
          }}
        >
          {STRENGTH_LABELS[match.match_strength]}
        </span>
      </div>
      {match.evidence_snippet && (
        <blockquote
          style={{
            borderLeft: "2px solid var(--accent)",
            paddingLeft: "12px",
            marginLeft: "4px",
            fontStyle: "italic",
            color: "var(--text-secondary)",
            fontSize: "13px",
            lineHeight: "1.5",
          }}
        >
          "{match.evidence_snippet}"
          {match.evidence_source && (
            <span
              style={{
                display: "block",
                marginTop: "4px",
                fontSize: "11px",
                fontStyle: "normal",
                color: "var(--text-secondary)",
                opacity: 0.7,
              }}
            >
              from your {match.evidence_source.replace(/_/g, " ")}
            </span>
          )}
        </blockquote>
      )}
    </div>
  );
}

function GapRow({ gap }: { gap: GapItem }) {
  const color = SEVERITY_COLORS[gap.severity] ?? "var(--text-secondary)";
  return (
    <div className="flex items-start justify-between gap-4 py-3 border-b" style={{ borderColor: "var(--border)" }}>
      <p className="text-sm" style={{ color: "var(--text-primary)" }}>
        {gap.requirement}
        {gap.must_have && (
          <span className="mono text-xs ml-2" style={{ color: "var(--text-secondary)" }}>
            required
          </span>
        )}
      </p>
      <span
        className="mono text-xs shrink-0 px-1.5 py-0.5 border uppercase"
        style={{ borderColor: color, color }}
      >
        {gap.severity}
      </span>
    </div>
  );
}

export default function BreakdownView({ data, onBack }: Props) {
  const { matches, gaps, roadmap, roadmap_note, project_suggestion } = data;

  return (
    <div className="flex flex-col gap-10">
      {/* Back link */}
      <button
        type="button"
        onClick={onBack}
        className="mono text-xs hover:opacity-70 transition-opacity self-start"
        style={{ color: "var(--text-secondary)" }}
      >
        ← back to verdict
      </button>

      {CATEGORY_ORDER.map((cat) => {
        const catMatches = matches.filter((m) => m.type === cat);
        const catGaps = gaps.filter((g) => g.type === cat);
        if (catMatches.length === 0 && catGaps.length === 0) return null;

        return (
          <section key={cat}>
            {/* Category header */}
            <div className="flex items-baseline gap-3 pb-2 mb-1 border-b" style={{ borderColor: "var(--border)" }}>
              <h2
                className="mono text-xs uppercase tracking-widest font-semibold"
                style={{ color: "var(--accent)" }}
              >
                {CATEGORY_LABELS[cat]}
              </h2>
              <span className="text-xs" style={{ color: "var(--text-secondary)" }}>
                {catMatches.length} match{catMatches.length !== 1 ? "es" : ""}
                {catGaps.length > 0 && ` · ${catGaps.length} gap${catGaps.length !== 1 ? "s" : ""}`}
              </span>
            </div>

            {/* Matches */}
            {catMatches.map((m, i) => (
              <MatchRow key={`${cat}-match-${i}`} match={m} />
            ))}

            {/* Gaps */}
            {catGaps.length > 0 && (
              <>
                {catMatches.length > 0 && (
                  <p
                    className="mono text-xs uppercase tracking-widest mt-4 mb-1"
                    style={{ color: "var(--text-secondary)" }}
                  >
                    gaps
                  </p>
                )}
                {catGaps.map((g, i) => (
                  <GapRow key={`${cat}-gap-${i}`} gap={g} />
                ))}
              </>
            )}
          </section>
        );
      })}

      {(roadmap || roadmap_note) && (
        <RoadmapSection roadmap={roadmap} roadmapNote={roadmap_note} />
      )}

      {project_suggestion && <ProjectSection project={project_suggestion} />}
    </div>
  );
}
