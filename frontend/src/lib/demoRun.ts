// Static "sample shortlist" — a fully self-contained demo run, ported from option-j's
// demo-data.js. Clicking "Or browse a sample shortlist" on the landing seeds this into
// localStorage and navigates to /results/<DEMO_RUN_ID>. Everything is pre-scored and
// pre-annotated, so the demo renders the real feed UI with ZERO backend calls (no cost,
// instant, works logged-out). The results page bypasses the sign-in gate for this id.
//
// Source of truth for the role copy is design-explorations/option-j/demo-data.js (SM_ROLES).
import type {
  RunResponse,
  UnifiedProfile,
  Internship,
  QuickAnalysisResponse,
  AnalysisResponse,
  MatchItem,
  GapItem,
  RoadmapResource,
} from "@/types/skymatch";
import {
  saveRunPayloadOnly,
  saveAnalyses,
  saveAnnotations,
  saveAnalysisPayloadOnly,
  type AnalysesByBucket,
  type AnnotationsByBucket,
  type BucketKey,
} from "@/lib/storage";
import type { CardAnalysisState, CardAnnotationState } from "@/lib/cardState";

// "demo" decodes (base-36) to a tiny number, so the results page's refreshedLabel() floors
// it to "today" — exactly what we want for an evergreen sample.
export const DEMO_RUN_ID = "demo";

type DemoBand = "strong" | "look" | "stretch";

interface DemoRole {
  company: string;
  domain: string; // for the favicon logo + a plausible apply URL
  title: string;
  location: string;
  about: string;
  bucket: BucketKey;
  band: DemoBand;
  score: number; // bands: strong→apply_now (band by call); look ≥58; stretch 45–57
  posted: string; // shown on the card + the drawer's "Posted" fact
  reasoning: string; // quick-verdict reasoning (drives the verdict text)
  why: string[]; // "why you fit" bullets (drawer)
  have: string[]; // skills already brought
  need: string[]; // skills worth shoring up
  gap?: string; // "Gap to close" note (stretch roles)
}

// The synthetic student the sample is matched against (header strip + "X's profile" copy).
const DEMO_PROFILE: UnifiedProfile = {
  full_name: "Alex Rivera",
  headline: "CS sophomore · applied ML & fraud detection",
  location: "Columbus, OH",
  school: "Ohio State University",
  graduation_year: 2028,
  major: "Computer Science",
  fraternity_or_orgs: ["ACM Student Chapter"],
  past_companies: [],
  current_company: null,
  technical_skills: ["Python", "React", "SQL", "Applied ML", "C++ basics", "Firmware", "Linux"],
  field_of_interest: "Software engineering · machine learning",
  key_values: ["impact", "learning fast", "shipping"],
  skills_with_context: [],
  education: [
    { school: "Ohio State University", degree: "B.S.", field_of_study: "Computer Science", start_year: 2024, end_year: 2028 },
  ],
  work_experience: [],
  projects: [
    {
      name: "Fraud detection class project",
      description: "Trained a tabular ML model to flag fraudulent transactions for an applied-ML course.",
      technologies: ["Python", "Applied ML"],
    },
    {
      name: "Drone flight-controller firmware",
      description: "Wrote low-level firmware for a quadcopter flight controller.",
      technologies: ["C++ basics", "Firmware", "Linux"],
    },
  ],
  certifications: [],
  sources: ["resume"],
};

// One ordered list; partitioned into buckets below (order within a bucket = its array index,
// which the analyses/annotations maps key off — they're built together so they can't drift).
const DEMO_ROLES: DemoRole[] = [
  {
    company: "Ramp", domain: "ramp.com", title: "Software Engineer Intern", location: "New York, NY",
    about: "Ramp builds finance automation software, corporate cards and the risk engine that watches every swipe.",
    bucket: "startup", band: "strong", score: 92, posted: "2d ago",
    reasoning: "Your fraud-detection project and applied-ML coursework map directly onto their risk team's stack — a strong, apply-now fit.",
    why: [
      "Your fraud detection project is a small version of what their risk team ships",
      "Two semesters of applied ML plus Python and React match the posted stack",
      "They take sophomores seriously and interns ship in week one",
    ],
    have: ["Python", "React", "SQL", "Applied ML"], need: [],
  },
  {
    company: "Sardine", domain: "sardine.ai", title: "Software Engineer Intern, Risk Platform", location: "Remote (US)",
    about: "Fraud and compliance infrastructure for fintechs, a remote-first team of about 150.",
    bucket: "startup", band: "strong", score: 90, posted: "3d ago",
    reasoning: "The whole product is your class project at industrial scale, and remote-first means geography isn't a filter — apply now.",
    why: [
      "The whole product is your class project at industrial scale",
      "A working fraud detection demo is the warmest intro you could ask for",
      "Remote first, so geography is not a filter",
    ],
    have: ["Python", "Applied ML"], need: [],
  },
  {
    company: "Vercel", domain: "vercel.com", title: "Frontend Infrastructure Intern", location: "Remote (US)",
    about: "The company behind Next.js, building the deploy and hosting layer for frontend teams.",
    bucket: "startup", band: "look", score: 72, posted: "4d ago",
    reasoning: "Your React work is real and they hire interns remote, but this is infrastructure depth rather than product UI.",
    why: [
      "Your React work is real and they hire interns remote",
      "The framework you learn on is the product they build",
    ],
    have: ["React"], need: ["Tooling depth"],
  },
  {
    company: "Notion", domain: "notion.so", title: "Software Engineer Intern", location: "San Francisco, CA",
    about: "The connected workspace product, built by a small team that sweats the interface.",
    bucket: "startup", band: "look", score: 60, posted: "5d ago",
    reasoning: "React matches and the product is loved, but they want shipped UI craft and your portfolio shows models, not interfaces.",
    why: [
      "React matches and the product is loved",
      "Small intern class with real surface ownership",
    ],
    have: ["React"], need: ["UI craft"],
  },
  {
    company: "Plaid", domain: "plaid.com", title: "Backend Intern, Payments", location: "San Francisco, CA",
    about: "The API layer connecting bank accounts to fintech apps, processing billions of transactions.",
    bucket: "startup", band: "stretch", score: 55, posted: "4d ago",
    reasoning: "Your fintech interest and Python are real signal, but their payments core runs at a scale your projects haven't touched yet.",
    why: [
      "Your fintech interest and Python are real signal",
      "The fraud project speaks their language",
    ],
    have: ["Python"], need: ["Distributed systems", "API scale"],
    gap: "Distributed systems beyond classwork. Their payments core runs at API scale, and your projects have not touched that yet.",
  },
  {
    company: "CoverMyMeds", domain: "covermymeds.com", title: "Software Developer Intern", location: "Columbus, OH",
    about: "Healthcare software that automates prescription approvals, one of the biggest tech employers in Columbus.",
    bucket: "local", band: "strong", score: 88, posted: "5d ago",
    reasoning: "Python services on a stack you already know, a program that hires Ohio State sophomores, and 25 minutes from campus — apply now.",
    why: [
      "Python services on a stack you already know",
      "A real internship program that hires Ohio State sophomores every year",
      "25 minutes from campus, so you keep your apartment",
    ],
    have: ["Python", "SQL"], need: [],
  },
  {
    company: "Root Insurance", domain: "joinroot.com", title: "Software Engineering Intern", location: "Columbus, OH",
    about: "Columbus-based insurtech that prices car insurance from driving data instead of credit scores.",
    bucket: "local", band: "strong", score: 87, posted: "1w ago",
    reasoning: "Pricing and fraud models are applied ML on tabular data — your exact coursework — with real model work 15 minutes from campus.",
    why: [
      "Pricing and fraud models are applied ML on tabular data, your exact coursework",
      "Fifteen minutes from campus with a small intern class",
      "Real model work, not shadowing",
    ],
    have: ["Python", "Applied ML", "SQL"], need: [],
  },
  {
    company: "JPMorgan Chase", domain: "jpmorganchase.com", title: "Software Engineer Intern", location: "Columbus, OH",
    about: "The Polaris campus is one of the bank's largest technology sites, with a big summer intern intake.",
    bucket: "local", band: "look", score: 68, posted: "6d ago",
    reasoning: "One of the biggest local intern intakes near campus and your Python fits their data tooling — they prefer juniors, but Columbus sophomores land it.",
    why: [
      "One of the biggest local intern intakes anywhere near campus",
      "Your Python fits their data tooling",
    ],
    have: ["Python", "SQL"], need: [],
  },
  {
    company: "Microsoft", domain: "microsoft.com", title: "Explore Intern, Software Engineering", location: "Redmond, WA",
    about: "A rotational internship built specifically for first- and second-year students, no prior internship expected.",
    bucket: "big_tech", band: "look", score: 70, posted: "1d ago",
    reasoning: "The Explore program exists for exactly your year with rotations across the stack — timing matters more than polish here.",
    why: [
      "The Explore program exists for exactly your year",
      "Rotations across the stack, no prior internship expected",
    ],
    have: ["Python", "C++ basics"], need: [],
  },
  {
    company: "Amazon", domain: "amazon.com", title: "SDE Intern", location: "Seattle, WA",
    about: "The largest intern program in tech, thousands of SDE seats across every org.",
    bucket: "big_tech", band: "look", score: 64, posted: "3d ago",
    reasoning: "Thousands of seats and a consistent bar that strong coursework can clear — though the online-assessment gauntlet rewards grinding.",
    why: [
      "Thousands of seats, the volume works in your favor",
      "A consistent bar that strong coursework can clear",
    ],
    have: ["Python"], need: [],
  },
  {
    company: "Oracle", domain: "oracle.com", title: "Software Engineer Intern", location: "Austin, TX",
    about: "Cloud infrastructure and enterprise software, with a large Austin intern cohort.",
    bucket: "big_tech", band: "look", score: 62, posted: "1w ago",
    reasoning: "A solid generalist fit for your stack with steady conversion to return offers — nothing pulls it above the line, nothing rules it out.",
    why: [
      "A solid generalist fit for your stack",
      "Large cohort with steady conversion to return offers",
    ],
    have: ["Python", "SQL"], need: [],
  },
  {
    company: "Meta", domain: "meta.com", title: "Software Engineer Intern, ML", location: "Menlo Park, CA",
    about: "ML powers ranking, integrity and ads across apps used by three billion people.",
    bucket: "big_tech", band: "stretch", score: 50, posted: "1w ago",
    reasoning: "Two semesters of applied ML is a real foundation, but they want interns who have served models at scale, not just trained them.",
    why: [
      "Two semesters of applied ML is a real foundation",
      "The fraud project shows you can finish",
    ],
    have: ["Python", "Applied ML"], need: ["ML infra", "Serving at scale"],
    gap: "ML infrastructure depth. You have trained models; they want interns who have served them.",
  },
  {
    company: "Apple", domain: "apple.com", title: "Software Engineering Intern, Core OS", location: "Cupertino, CA",
    about: "Core OS owns the kernel, drivers and low-level frameworks under every Apple product.",
    bucket: "big_tech", band: "stretch", score: 47, posted: "3d ago",
    reasoning: "Your firmware curiosity is the right raw material, but the kernel vocabulary and OS-internals coursework are still ahead of you.",
    why: [
      "Firmware curiosity is the right raw material for this team",
      "They know sophomores rarely arrive finished",
    ],
    have: ["C++ basics", "Firmware"], need: ["OS internals"],
    gap: "OS internals coursework is still ahead of you. The firmware instinct is real, the kernel vocabulary is not there yet.",
  },
  {
    company: "Google", domain: "google.com", title: "STEP Intern", location: "Mountain View, CA",
    about: "Google's internship for first and second years, built around mentorship and a paired project.",
    bucket: "reach", band: "look", score: 66, posted: "2w ago",
    reasoning: "STEP is built for first- and second-years with mentorship sized to your level — the funnel is brutal, so treat it as a lottery ticket worth buying.",
    why: [
      "STEP is built for first and second years",
      "Mentorship plus a paired project, sized to your coursework level",
    ],
    have: ["Python", "C++ basics"], need: [],
  },
  {
    company: "NVIDIA", domain: "nvidia.com", title: "Systems Software Intern", location: "Santa Clara, CA",
    about: "The systems software group builds the drivers, tools and runtime between the silicon and everything else.",
    bucket: "reach", band: "stretch", score: 53, posted: "2d ago",
    reasoning: "Your drone firmware proves you can think close to hardware — rarer than you'd think — but you're two skills (CUDA, modern C++) away.",
    why: [
      "The drone firmware proves you can think close to hardware",
      "That instinct is rarer than you think",
    ],
    have: ["C++ basics", "Firmware", "Linux"], need: ["CUDA", "Modern C++"],
    gap: "Modern C++ at systems scale and any GPU surface at all. Two skills, both closable by summer.",
  },
];

const BUCKETS: BucketKey[] = ["local", "big_tech", "startup", "reach"];
const favicon = (domain: string) => `https://www.google.com/s2/favicons?domain=${domain}&sz=128`;

// Headcounts for the drawer's Company box (from the option-j dataset). On real runs this comes
// from the listing parse (Internship.company_size); the sample carries it inline.
const COMPANY_SIZE: Record<string, string> = {
  "ramp.com": "650 people", "sardine.ai": "150 people", "vercel.com": "600 people",
  "notion.so": "700 people", "plaid.com": "1,100 people", "covermymeds.com": "1,300 people",
  "joinroot.com": "900 people", "jpmorganchase.com": "300,000 people", "microsoft.com": "220,000 people",
  "amazon.com": "1.5M people", "oracle.com": "160,000 people", "meta.com": "70,000 people",
  "apple.com": "160,000 people", "google.com": "180,000 people", "nvidia.com": "30,000 people",
};

function toInternship(r: DemoRole): Internship {
  return {
    title: r.title,
    company: r.company,
    location: r.location,
    company_description: r.about,
    fit_explanation: "",
    application_url: `https://${r.domain}/careers`,
    bucket: r.bucket,
    reach_gap: r.gap ?? null,
    logo_url: favicon(r.domain),
    company_size: COMPANY_SIZE[r.domain] ?? null,
    term: "Summer 2026", // every sample role is a Summer 2026 internship
    posted_at: r.posted, // surfaced directly (drawer/card prefer Internship.posted_at)
  };
}

// verdict.call by band. The feed bands by SCORE (apply_now→strong, else ≥58 look / ≥45 stretch),
// but the full-analysis view bands by CALL — so stretch maps to "skip" to keep both consistent.
const CALL_BY_BAND = { strong: "apply_now", look: "apply_after_prep", stretch: "skip" } as const;

function toAnalysis(r: DemoRole): CardAnalysisState {
  const data: QuickAnalysisResponse = {
    fit_score: r.score,
    verdict: { call: CALL_BY_BAND[r.band], reasoning: r.reasoning },
    job_summary: { title: r.title, company: r.company, posted_at: r.posted, apply_url: `https://${r.domain}/careers` },
  };
  return { status: "ok", data };
}

function toAnnotation(r: DemoRole): CardAnnotationState {
  return {
    status: "ok",
    fit_explanation: r.why[0] ?? r.reasoning,
    why: r.why,
    have: r.have,
    need: r.need,
    reach_gap: r.gap ?? null,
  };
}

// ── Canned "Full analysis" (AnalysisResponse) ─────────────────────────────────
// Synthesized from each role's have/need/score so the /analyze/[id] view renders a full,
// believable breakdown with ZERO backend. The slug keys the stored analysis + the drawer link.

type Cat = MatchItem["type"];

/** Map a skill name onto an AnalysisView category (mostly technical; ML reads as domain). */
function skillCat(skill: string): Cat {
  const s = skill.toLowerCase();
  if (s.includes("ml") || s.includes("applied ml") || s.includes("serving")) return "domain";
  return "technical";
}

const clamp = (n: number) => Math.max(8, Math.min(96, Math.round(n)));

// Profile-grounded evidence for skills the demo student actually demonstrates.
const EVIDENCE: Record<string, { snippet: string; source: string }> = {
  Python: { snippet: "Built a tabular fraud-detection model in Python for an applied-ML course.", source: "project" },
  "Applied ML": { snippet: "Two semesters of applied ML, including a fraud classifier on transaction data.", source: "project" },
  React: { snippet: "Shipped a React frontend for a course project.", source: "project" },
  SQL: { snippet: "Used SQL across coursework and the fraud project.", source: "coursework" },
  "C++ basics": { snippet: "Wrote C++ firmware for a quadcopter flight controller.", source: "project" },
  Firmware: { snippet: "Built and flashed flight-controller firmware on real hardware.", source: "project" },
  Linux: { snippet: "Developed the firmware toolchain on Linux.", source: "project" },
};

function buildMatches(r: DemoRole): MatchItem[] {
  return r.have.map((skill, i) => {
    const ev = EVIDENCE[skill];
    return {
      requirement: skill,
      type: skillCat(skill),
      must_have: i < 2,
      match_strength: r.band === "strong" || i === 0 ? "strong" : "partial",
      evidence_snippet: ev?.snippet ?? null,
      evidence_source: ev?.source ?? null,
    };
  });
}

function buildGaps(r: DemoRole): GapItem[] {
  return r.need.map((skill) => ({
    requirement: skill,
    type: skillCat(skill),
    must_have: r.band === "stretch",
    severity: r.band === "stretch" ? "moderate" : "minor",
  }));
}

function categoryScores(r: DemoRole): Record<string, number> {
  return {
    technical: clamp(r.score + 6),
    experience: clamp(r.score - 26), // sophomore — light on shipped experience
    education: 72,
    domain: clamp(r.score - 4),
  };
}

// A single, free, self-paced resource per gap skill (specific where it's obvious, generic otherwise).
const RESOURCE: Record<string, RoadmapResource> = {
  CUDA: { type: "docs", title: "NVIDIA CUDA C++ Programming Guide", url: "https://docs.nvidia.com/cuda/", duration: "3–4 weeks", cost: "free" },
  "Modern C++": { type: "course", title: "learncpp.com — Modern C++", url: "https://www.learncpp.com/", duration: "4–6 weeks", cost: "free" },
  "OS internals": { type: "book", title: "OSTEP — Operating Systems: Three Easy Pieces", url: "https://pages.cs.wisc.edu/~remzi/OSTEP/", duration: "6–8 weeks", cost: "free" },
  "Distributed systems": { type: "course", title: "MIT 6.824 Distributed Systems (lectures)", url: "https://pdos.csail.mit.edu/6.824/", duration: "6–8 weeks", cost: "free" },
  "ML infra": { type: "roadmap", title: "MLOps roadmap on roadmap.sh", url: "https://roadmap.sh/mlops", duration: "self-paced", cost: "free" },
};

function resourceFor(skill: string): RoadmapResource {
  return (
    RESOURCE[skill] ?? {
      type: "roadmap",
      title: `${skill} — roadmap.sh track`,
      url: "https://roadmap.sh",
      duration: "self-paced",
      cost: "free",
    }
  );
}

function buildAnalysis(r: DemoRole): AnalysisResponse {
  const hasGaps = r.need.length > 0;
  const timeline = r.band === "stretch" ? "8–10 weeks" : "3–4 weeks";

  return {
    fit_score: r.score,
    category_scores: categoryScores(r),
    matches: buildMatches(r),
    gaps: buildGaps(r),
    verdict: { call: CALL_BY_BAND[r.band], reasoning: r.reasoning },
    job_summary: {
      title: r.title,
      company: r.company,
      key_requirements: [...r.have, ...r.need],
    },
    roadmap: hasGaps
      ? {
          total_timeline: timeline,
          summary: `Close ${r.need.length === 1 ? "the one gap" : `the ${r.need.length} gaps`} between you and the ${r.company} bar before you apply.`,
          items: r.need.map((skill) => ({
            skill,
            priority: r.band === "stretch" ? "must_have" : "nice_to_have",
            timeline,
            why_it_matters: `${r.company}'s ${r.title.toLowerCase()} leans on ${skill}; it's the clearest thing standing between your profile and the bar.`,
            milestone: `Ship one small thing that uses ${skill} end-to-end, and write up what you learned.`,
            resources: [resourceFor(skill)],
          })),
        }
      : null,
    roadmap_note: hasGaps ? null : "Nothing here blocks the application — send it this week.",
    project_suggestion: hasGaps
      ? {
          title: `A ${r.need[0]}-shaped build for ${r.company}`,
          pitch: `A small but real project that turns ${r.need.join(" and ")} from a gap on paper into a story you can walk through.`,
          why_this_role: `It targets exactly what ${r.company} is screening for, so it doubles as your strongest interview talking point.`,
          mvp_features: [
            `A working core that exercises ${r.need[0]} on real (or realistic) data`,
            `One slice that connects it back to your ${r.have[0]} foundation`,
            "A short writeup of the design decisions and trade-offs",
          ],
          tech_stack: [...r.have, ...r.need],
          estimated_time: timeline,
          stretch_goals: [
            `Push ${r.need[0]} past the toy version toward something closer to production`,
            "Add a small benchmark or test suite that proves it works",
          ],
          interview_talking_points: [
            `Why you chose this approach to ${r.need[0]}`,
            `The hardest bug and how you tracked it down`,
          ],
        }
      : null,
  };
}

// Stable per-role slug → analysis id (`demo-ramp`, `demo-covermymeds`, …). Derived from the
// domain so the drawer link and the seeded analysis always agree.
const slugOf = (domain: string) => domain.split(".")[0];
export const demoAnalysisId = (domain: string) => `demo-${slugOf(domain)}`;

/** The /analyze/[id] href for a demo role, derived from its application_url, or null if not a demo url. */
export function demoAnalysisIdFromUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  try {
    return demoAnalysisId(new URL(url).hostname);
  } catch {
    return null;
  }
}

function buildDemo(): { run: RunResponse; analyses: AnalysesByBucket; annotations: AnnotationsByBucket } {
  const internships = { local: [] as Internship[], big_tech: [] as Internship[], startup: [] as Internship[], reach: [] as Internship[] };
  const analyses: AnalysesByBucket = { local: {}, big_tech: {}, startup: {}, reach: {} };
  const annotations: AnnotationsByBucket = { local: {}, big_tech: {}, startup: {}, reach: {} };

  for (const bucket of BUCKETS) {
    DEMO_ROLES.filter((r) => r.bucket === bucket).forEach((r, idx) => {
      internships[bucket].push(toInternship(r));
      analyses[bucket][idx] = toAnalysis(r);
      annotations[bucket][idx] = toAnnotation(r);
    });
  }

  const run: RunResponse = { profile: DEMO_PROFILE, connections: [], internships };
  return { run, analyses, annotations };
}

/** Seed the static sample run into localStorage (idempotent). Call right before navigating
 *  to /results/{DEMO_RUN_ID}. Re-seeds every time so format/copy fixes always propagate.
 *  Also seeds each role's canned "Full analysis" (payload-only, so it never evicts the
 *  user's real standalone analyses). */
export function seedDemoRun(): void {
  const { run, analyses, annotations } = buildDemo();
  saveRunPayloadOnly(DEMO_RUN_ID, run);
  saveAnalyses(DEMO_RUN_ID, analyses);
  saveAnnotations(DEMO_RUN_ID, annotations);
  for (const r of DEMO_ROLES) saveAnalysisPayloadOnly(demoAnalysisId(r.domain), buildAnalysis(r));
}
