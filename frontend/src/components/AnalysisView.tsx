"use client";

import { useState } from "react";
import type {
  AnalysisResponse,
  MatchItem,
  GapItem,
  Roadmap,
  RoadmapResource,
  ProjectSuggestion,
} from "@/types/skymatch";
import { BAND_LABEL_ONE, type Band } from "@/lib/bands";

// Continuous job-fit analysis, re-skinned to option-j analysis.html: six numbered sections
// (role → verdict → where you stand → full read → plan → project). Pure presentation over the
// existing AnalysisResponse — no backend/data-shape change. Used by BOTH the streaming /analyze
// inline result and the persisted /analyze/[analysisId] page.

const CATEGORY_ORDER = ["technical", "experience", "education", "domain", "soft"] as const;
const CATEGORY_LABELS: Record<string, string> = {
  technical: "Technical",
  experience: "Experience",
  education: "Education",
  domain: "Domain",
  soft: "Soft skills",
};

// verdict.call → band + the mockup's verdict call phrasing.
const VERDICT_BAND: Record<string, Band> = { apply_now: "strong", apply_after_prep: "look", skip: "stretch" };
const CALL_LABEL: Record<string, string> = { apply_now: "Apply now.", apply_after_prep: "Worth a look.", skip: "Worth prepping." };

// numeric category score → qualitative label + bar width (+ warm tint when light).
function level(score: number): { qual: string; warm: boolean } {
  if (score >= 70) return { qual: "Strong", warm: false };
  if (score >= 45) return { qual: "Solid", warm: false };
  return { qual: "Light", warm: true };
}

function BandPill({ band }: { band: Band }) {
  return (
    <span className={`band-pill band-${band}`}>
      <span className={`tier ${band}`}><i /><i /><i /></span> {BAND_LABEL_ONE[band]}
    </span>
  );
}

function Skeleton() {
  return (
    <>
      <div className="skel w50" /><div className="skel w90" /><div className="skel w80" /><div className="skel w70" />
    </>
  );
}

function ResRow({ res }: { res: RoadmapResource }) {
  const bits: Array<string> = [res.type, res.duration, res.cost].filter(Boolean) as string[];
  return (
    <a className="res-row" href={res.url} target="_blank" rel="noopener noreferrer">
      <span>{res.title}</span>
      <span className="res-tags">
        {bits.map((b, i) => (
          <span key={i}>{b === "free" ? <span className="free">free</span> : b}{i < bits.length - 1 ? " · " : ""}</span>
        ))}
      </span>
    </a>
  );
}

function RoadmapBody({ roadmap, note }: { roadmap?: Roadmap | null; note?: string | null }) {
  if (roadmap && roadmap.items.length > 0) {
    return (
      <div className="fade-in">
        <div className="rmeta">{roadmap.total_timeline}</div>
        <p className="rsummary">{roadmap.summary}</p>
        {roadmap.items.map((it, i) => (
          <div className="ritem" key={i}>
            <div className="ri-top">
              <h3>{it.skill}</h3>
              <span className={`prio ${it.priority === "must_have" ? "prio-must" : "prio-nice"}`}>
                {it.priority === "must_have" ? "must have" : "nice to have"}
              </span>
              <span className="ttl">{it.timeline}</span>
            </div>
            <p className="ri-why">{it.why_it_matters}</p>
            <div className="milestone"><span className="ml">milestone</span>{it.milestone}</div>
            {it.resources.length > 0 && (
              <div className="res-rows">{it.resources.map((r, j) => <ResRow res={r} key={j} />)}</div>
            )}
          </div>
        ))}
      </div>
    );
  }
  const text = note ?? roadmap?.summary ?? "Nothing here blocks the application. Send it this week.";
  return <p className="rsummary fade-in">{text}</p>;
}

function ProjectBody({ project }: { project: ProjectSuggestion }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="project-card fade-in">
      <h3>{project.title}</h3>
      <p className="pitch">{project.pitch}</p>
      <p className="why-role">{project.why_this_role}</p>
      <div className="sub-label">The MVP</div>
      <ol className="mvp">{project.mvp_features.map((m, i) => <li key={i}>{m}</li>)}</ol>
      <div className="sub-label">Tech stack</div>
      <div className="stack">{project.tech_stack.map((s, i) => <span className="req-chip" key={i}>{s}</span>)}</div>
      {project.stretch_goals.length > 0 && (
        <>
          <button type="button" className="stretch-toggle" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
            {open ? "Hide stretch goals ↑" : "Show stretch goals ↓"}
          </button>
          {open && <ul className="stretch-list">{project.stretch_goals.map((s, i) => <li key={i}>{s}</li>)}</ul>}
        </>
      )}
      <div className="sub-label">Talking points for the interview</div>
      <ul className="talking">{project.interview_talking_points.map((t, i) => <li key={i}>{t}</li>)}</ul>
    </div>
  );
}

interface Props {
  data: AnalysisResponse;
  /** Streaming phase flags — default true (persisted view shows everything complete). */
  roadmapDone?: boolean;
  projectDone?: boolean;
}

export default function AnalysisView({ data, roadmapDone = true, projectDone = true }: Props) {
  const { fit_score, category_scores, matches, gaps, verdict, job_summary, roadmap, roadmap_note, project_suggestion } = data;
  const band = VERDICT_BAND[verdict.call] ?? "look";
  const call = CALL_LABEL[verdict.call] ?? verdict.call;

  const bars = CATEGORY_ORDER
    .filter((c) => c in category_scores)
    .map((c) => ({ label: CATEGORY_LABELS[c], score: category_scores[c] }));

  return (
    <div className="acol" style={{ margin: "0 auto" }}>
      {/* HEADER */}
      <section className="an-head" style={{ paddingTop: 6 }}>
        <span className="eyebrow">Job fit analyzer · analyzing fit for</span>
        <h1>{job_summary.title || "This role"}</h1>
        <div className="co">
          {job_summary.company && <span>{job_summary.company}</span>}
          <BandPill band={band} />
        </div>
      </section>

      {/* 01 THE ROLE */}
      {job_summary.key_requirements.length > 0 && (
        <section className="section">
          <span className="eyebrow"><span className="sec-num">01</span> The role</span>
          <div className="sub-label">Key requirements</div>
          <div className="req-chips">{job_summary.key_requirements.map((r, i) => <span className="req-chip" key={i}>{r}</span>)}</div>
        </section>
      )}

      {/* 02 THE VERDICT */}
      <section className="section">
        <span className="eyebrow"><span className="sec-num">02</span> The verdict</span>
        <div className="verdict-block">
          <div><BandPill band={band} /></div>
          <div className="verdict-call">{call}</div>
          <p className="verdict-why">{verdict.reasoning}</p>
          <div className="phases" aria-label="Analysis phases">
            <span className="ph done"><i />verdict</span><span className="sep">·</span>
            <span className={`ph ${roadmapDone ? "done" : "working"}`}><i />roadmap</span><span className="sep">·</span>
            <span className={`ph ${projectDone ? "done" : "working"}`}><i />project</span>
          </div>
        </div>
      </section>

      {/* 03 WHERE YOU STAND */}
      {bars.length > 0 && (
        <section className="section">
          <span className="eyebrow"><span className="sec-num">03</span> Where you stand</span>
          <div className="bars">
            {bars.map((b, i) => {
              const lv = level(b.score);
              return (
                <div className="bar-row" key={i}>
                  <span className="bl">{b.label}</span>
                  <span className="bar"><i style={{ width: `${Math.max(0, Math.min(100, b.score))}%`, ...(lv.warm ? { background: "var(--warm)" } : {}) }} /></span>
                  <span className="q">{lv.qual}</span>
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* 04 THE FULL READ */}
      <section className="section">
        <span className="eyebrow"><span className="sec-num">04</span> The full read</span>
        {CATEGORY_ORDER.map((cat) => {
          const catMatches = matches.filter((m) => m.type === cat);
          const catGaps = gaps.filter((g) => g.type === cat);
          if (catMatches.length === 0 && catGaps.length === 0) return null;
          return (
            <div className="cat-group" key={cat}>
              <h3>{CATEGORY_LABELS[cat]}</h3>
              {catMatches.map((m, i) => <MatchRow match={m} key={`m${i}`} />)}
              {catGaps.map((g, i) => <GapRow gap={g} key={`g${i}`} />)}
            </div>
          );
        })}
      </section>

      {/* 05 THE PLAN */}
      <section className="section">
        <div className="sec-head">
          <span className="eyebrow"><span className="sec-num">05</span> The plan</span>
          <h2>Your prep roadmap.</h2>
        </div>
        {roadmapDone ? <RoadmapBody roadmap={roadmap} note={roadmap_note} /> : <Skeleton />}
      </section>

      {/* 06 THE PROJECT */}
      <section className="section">
        <div className="sec-head">
          <span className="eyebrow"><span className="sec-num">06</span> The project</span>
          <h2>Build this to apply.</h2>
        </div>
        {projectDone ? (project_suggestion ? <ProjectBody project={project_suggestion} /> : <p className="rsummary">No project needed — your profile already clears the bar.</p>) : <Skeleton />}
      </section>
    </div>
  );
}

function MatchRow({ match }: { match: MatchItem }) {
  return (
    <div className="match-row">
      <div className="mr-top">
        <span className="mr-req">{match.requirement}</span>
        {match.must_have && <span className="req-tag">required</span>}
        <span className={`badge b-${match.match_strength}`}>{match.match_strength}</span>
      </div>
      {match.evidence_snippet && (
        <blockquote className="ev">
          &ldquo;{match.evidence_snippet}&rdquo;
          {match.evidence_source && <cite>from your {match.evidence_source.replace(/_/g, " ")}</cite>}
        </blockquote>
      )}
    </div>
  );
}

function GapRow({ gap }: { gap: GapItem }) {
  return (
    <div className="gap-row">
      <div className="mr-top">
        <span className="mr-req">{gap.requirement}</span>
        {gap.must_have && <span className="req-tag">required</span>}
        <span className={`sev sev-${gap.severity}`}>{gap.severity}</span>
      </div>
    </div>
  );
}
