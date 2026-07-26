/* demo-data.js — shared role data + save/status store + drawer for the SkyMatch "Application tracker" demo (option-l).
   Loaded by index.html. Extends the option-j base with a per-role application STATUS
   (saved / applied / interviewing / closed) and an optional DEADLINE, both persisted to
   localStorage. The status drives the pipeline strip tiles, the per-row status tag, and the
   "deadlines this week" / "Nudge" funnel surfaces. Honest mechanics only: status is never
   auto-advanced (the user sets it in the drawer), deadlines are user-entered, no countdowns. */

const SM_ROLES = [
  {
    id: "ramp-swe", band: "strong", bandLabel: "Strong match", type: "startup", typeLabel: "Startup",
    logo: "R", alt: false,
    title: "Software Engineer Intern", company: "Ramp", meta: "Ramp · New York, NY · Summer 2026",
    about: "Ramp builds finance automation software, corporate cards and the risk engine that watches every swipe.",
    why: [
      "Your fraud detection project is a small version of what their risk team ships",
      "Two semesters of applied ML plus Python and React match the posted stack",
      "They take sophomores seriously and interns ship in week one"
    ],
    facts: { stipend: "$9,500/mo", location: "New York, NY · Hybrid", term: "Summer 2026", team: "Risk Platform", co: "650 people · Series D", posted: "2d ago" },
    have: ["Python", "React", "SQL", "Applied ML"], need: [],
    analysis: "ramp-swe"
  },
  {
    id: "covermymeds", band: "strong", bandLabel: "Strong match", type: "near", typeLabel: "Near you",
    logo: "C", alt: true,
    title: "Software Developer Intern", company: "CoverMyMeds", meta: "CoverMyMeds · Columbus, OH · 25 min from campus",
    about: "Healthcare software that automates prescription approvals, one of the biggest tech employers in Columbus.",
    why: [
      "Python services on a stack you already know",
      "A real internship program that hires Ohio State sophomores every year",
      "25 minutes from campus, so you keep your apartment"
    ],
    facts: { stipend: "$5,400/mo", location: "Columbus, OH · On site", term: "Summer 2026", team: "Platform Services", co: "1,300 people · McKesson", posted: "5d ago" },
    have: ["Python", "SQL"], need: []
  },
  {
    id: "root", band: "strong", bandLabel: "Strong match", type: "near", typeLabel: "Near you",
    logo: "R", alt: false,
    title: "Software Engineering Intern", company: "Root Insurance", meta: "Root Insurance · Columbus, OH · 15 min from campus",
    about: "Columbus based insurtech that prices car insurance from driving data instead of credit scores.",
    why: [
      "Pricing and fraud models are applied ML on tabular data, your exact coursework",
      "Fifteen minutes from campus with a small intern class",
      "Real model work, not shadowing"
    ],
    facts: { stipend: "$6,000/mo", location: "Columbus, OH · Hybrid", term: "Summer 2026", team: "Pricing and Fraud", co: "900 people · Public", posted: "1w ago" },
    have: ["Python", "Applied ML", "SQL"], need: []
  },
  {
    id: "sardine", band: "strong", bandLabel: "Strong match", type: "startup", typeLabel: "Startup",
    logo: "S", alt: true,
    title: "Software Engineer Intern, Risk Platform", company: "Sardine", meta: "Sardine · Remote (US)",
    about: "Fraud and compliance infrastructure for fintechs, a remote first team of about 150.",
    why: [
      "The whole product is your class project at industrial scale",
      "A working fraud detection demo is the warmest intro you could ask for",
      "Remote first, so geography is not a filter"
    ],
    facts: { stipend: "$8,000/mo", location: "Remote (US)", term: "Summer 2026", team: "Risk Scoring", co: "150 people · Series B", posted: "3d ago" },
    have: ["Python", "Applied ML"], need: []
  },
  {
    id: "vercel", band: "look", bandLabel: "Worth a look", type: "startup", typeLabel: "Startup",
    logo: "V", alt: true,
    title: "Frontend Infrastructure Intern", company: "Vercel", meta: "Vercel · Remote · Summer 2026",
    about: "The company behind Next.js, building the deploy and hosting layer for frontend teams.",
    why: [
      "Your React work is real and they hire interns remote",
      "The framework you learn on is the product they build"
    ],
    note: "The catch: this is infrastructure, and your frontend experience is product coursework, not tooling depth.",
    facts: { stipend: "$8,500/mo", location: "Remote (US)", term: "Summer 2026", team: "Frontend Infra", co: "600 people · Series E", posted: "4d ago" },
    have: ["React"], need: ["Tooling depth"]
  },
  {
    id: "msft-explore", band: "look", bandLabel: "Worth a look", type: "bigtech", typeLabel: "Big tech",
    logo: "M", alt: false,
    title: "Explore Intern, Software Engineering", company: "Microsoft", meta: "Microsoft · Redmond, WA · built for underclassmen",
    about: "A rotational internship built specifically for first and second year students, no prior internship expected.",
    why: [
      "The Explore program exists for exactly your year",
      "Rotations across the stack, no prior internship expected"
    ],
    note: "The catch: applications open early and close fast, so timing matters more than polish.",
    facts: { stipend: "$7,800/mo", location: "Redmond, WA · On site", term: "Summer 2026", team: "Explore rotation", co: "220,000 people · Public", posted: "1d ago" },
    have: ["Python", "C++ basics"], need: []
  },
  {
    id: "jpmc", band: "look", bandLabel: "Worth a look", type: "near", typeLabel: "Near you",
    logo: "J", alt: true,
    title: "Software Engineer Intern", company: "JPMorgan Chase", meta: "JPMorgan Chase · Columbus, OH · Polaris campus, 20 min away",
    about: "The Polaris campus is one of the bank's largest technology sites, with a big summer intern intake.",
    why: [
      "One of the biggest local intern intakes anywhere near campus",
      "Your Python fits their data tooling"
    ],
    note: "The catch: they prefer juniors, but Columbus sophomores land it every year.",
    facts: { stipend: "$6,200/mo", location: "Columbus, OH · On site", term: "Summer 2026", team: "Data Engineering", co: "300,000 people · Public", posted: "6d ago" },
    have: ["Python", "SQL"], need: []
  },
  {
    id: "google-step", band: "look", bandLabel: "Worth a look", type: "selective", typeLabel: "Selective",
    logo: "G", alt: false,
    title: "STEP Intern", company: "Google", meta: "Google · Mountain View, CA · first and second years",
    about: "Google's internship for first and second years, built around mentorship and a paired project.",
    why: [
      "STEP is built for first and second years",
      "Mentorship plus a paired project, sized to your coursework level"
    ],
    note: "The catch: the funnel is brutal. Treat it as a lottery ticket worth buying.",
    facts: { stipend: "$8,700/mo", location: "Mountain View, CA · On site", term: "Summer 2026", team: "STEP cohort", co: "180,000 people · Public", posted: "2w ago" },
    have: ["Python", "C++ basics"], need: []
  },
  {
    id: "amazon", band: "look", bandLabel: "Worth a look", type: "bigtech", typeLabel: "Big tech",
    logo: "A", alt: true,
    title: "SDE Intern", company: "Amazon", meta: "Amazon · Seattle, WA",
    about: "The largest intern program in tech, thousands of SDE seats across every org.",
    why: [
      "Thousands of seats, the volume works in your favor",
      "A consistent bar that strong coursework can clear"
    ],
    note: "The catch: the online assessment gauntlet rewards grinding, and little of your ML background gets used.",
    facts: { stipend: "$8,200/mo", location: "Seattle, WA · On site", term: "Summer 2026", team: "SDE generalist pool", co: "1.5M people · Public", posted: "3d ago" },
    have: ["Python"], need: []
  },
  {
    id: "oracle", band: "look", bandLabel: "Worth a look", type: "bigtech", typeLabel: "Big tech",
    logo: "O", alt: false,
    title: "Software Engineer Intern", company: "Oracle", meta: "Oracle · Austin, TX",
    about: "Cloud infrastructure and enterprise software, with a large Austin intern cohort.",
    why: [
      "A solid generalist fit for your stack",
      "Large cohort with steady conversion to return offers"
    ],
    note: "The catch: nothing on your profile pulls it above the line, and nothing rules it out.",
    facts: { stipend: "$7,200/mo", location: "Austin, TX · Hybrid", term: "Summer 2026", team: "OCI Tooling", co: "160,000 people · Public", posted: "1w ago" },
    have: ["Python", "SQL"], need: []
  },
  {
    id: "notion", band: "look", bandLabel: "Worth a look", type: "startup", typeLabel: "Startup",
    logo: "N", alt: true,
    title: "Software Engineer Intern", company: "Notion", meta: "Notion · San Francisco, CA",
    about: "The connected workspace product, built by a small team that sweats the interface.",
    why: [
      "React matches and the product is loved",
      "Small intern class with real surface ownership"
    ],
    note: "The catch: they want shipped UI craft, and your portfolio shows models, not interfaces.",
    facts: { stipend: "$8,800/mo", location: "San Francisco, CA · On site", term: "Summer 2026", team: "Product Engineering", co: "700 people · Private", posted: "5d ago" },
    have: ["React"], need: ["UI craft"]
  },
  {
    id: "plaid", band: "stretch", bandLabel: "Stretch", type: "startup", typeLabel: "Startup",
    logo: "P", alt: true,
    title: "Backend Intern, Payments", company: "Plaid", meta: "Plaid · San Francisco, CA",
    about: "The API layer connecting bank accounts to fintech apps, processing billions of transactions.",
    why: [
      "Your fintech interest and Python are real signal",
      "The fraud project speaks their language"
    ],
    gap: "Distributed systems beyond classwork. Their payments core runs at API scale, and your projects have not touched that yet.",
    facts: { stipend: "$9,000/mo", location: "San Francisco, CA · Hybrid", term: "Summer 2026", team: "Payments Core", co: "1,100 people · Private", posted: "4d ago" },
    have: ["Python"], need: ["Distributed systems", "API scale"]
  },
  {
    id: "nvidia-systems", band: "stretch", bandLabel: "Stretch", type: "selective", typeLabel: "Selective",
    logo: "N", alt: false,
    title: "Systems Software Intern", company: "NVIDIA", meta: "NVIDIA · Santa Clara, CA · two skills away",
    about: "The systems software group builds the drivers, tools and runtime between the silicon and everything else.",
    why: [
      "The drone firmware proves you can think close to hardware",
      "That instinct is rarer than you think"
    ],
    gap: "Modern C++ at systems scale and any GPU surface at all. Two skills, both closable by summer.",
    facts: { stipend: "$9,200/mo", location: "Santa Clara, CA · On site", term: "Summer 2026", team: "Systems Software", co: "30,000 people · Public", posted: "2d ago" },
    have: ["C++ basics", "Firmware", "Linux"], need: ["CUDA", "Modern C++"],
    analysis: "nvidia-systems"
  },
  {
    id: "meta-ml", band: "stretch", bandLabel: "Stretch", type: "bigtech", typeLabel: "Big tech",
    logo: "M", alt: true,
    title: "Software Engineer Intern, ML", company: "Meta", meta: "Meta · Menlo Park, CA",
    about: "ML powers ranking, integrity and ads across apps used by three billion people.",
    why: [
      "Two semesters of applied ML is a real foundation",
      "The fraud project shows you can finish"
    ],
    gap: "ML infrastructure depth. You have trained models; they want interns who have served them.",
    facts: { stipend: "$9,400/mo", location: "Menlo Park, CA · On site", term: "Summer 2026", team: "ML Infra", co: "70,000 people · Public", posted: "1w ago" },
    have: ["Python", "Applied ML"], need: ["ML infra", "Serving at scale"]
  },
  {
    id: "apple-coreos", band: "stretch", bandLabel: "Stretch", type: "bigtech", typeLabel: "Big tech",
    logo: "A", alt: false,
    title: "Software Engineering Intern, Core OS", company: "Apple", meta: "Apple · Cupertino, CA",
    about: "Core OS owns the kernel, drivers and low level frameworks under every Apple product.",
    why: [
      "Firmware curiosity is the right raw material for this team",
      "They know sophomores rarely arrive finished"
    ],
    gap: "OS internals coursework is still ahead of you. The firmware instinct is real, the kernel vocabulary is not there yet.",
    facts: { stipend: "$8,900/mo", location: "Cupertino, CA · On site", term: "Summer 2026", team: "Core OS", co: "160,000 people · Public", posted: "3d ago" },
    have: ["C++ basics", "Firmware"], need: ["OS internals"]
  }
];

/* ---- "Load more" intake pool ----
   Fresh roles that have NOT entered the pipeline yet. "Load more" at the feed bottom
   appends the next batch into the bands, giving the student new candidates to push into
   Saved/Applied. Keeps the list from ever bottoming out. */
const SM_MORE_ROLES = [
  {
    id: "stripe-risk", band: "strong", bandLabel: "Strong match", type: "startup", typeLabel: "Startup",
    logo: "S", alt: true,
    title: "Software Engineer Intern, Risk", company: "Stripe", meta: "Stripe · Remote (US) · Summer 2026",
    about: "Payments infrastructure for the internet; the Risk org keeps fraud off the network at planetary scale.",
    why: [
      "Risk is exactly the fraud-detection problem from your project, at scale",
      "Python and applied ML are the daily tools on this team",
      "Remote-friendly intern class with real ownership"
    ],
    facts: { stipend: "$9,300/mo", location: "Remote (US)", term: "Summer 2026", team: "Risk Intelligence", co: "8,000 people · Private", posted: "1d ago" },
    have: ["Python", "Applied ML", "SQL"], need: []
  },
  {
    id: "huntington", band: "strong", bandLabel: "Strong match", type: "near", typeLabel: "Near you",
    logo: "H", alt: false,
    title: "Data Engineering Intern", company: "Huntington Bank", meta: "Huntington · Columbus, OH · downtown, 10 min",
    about: "A regional bank headquartered in Columbus with a growing data and analytics practice.",
    why: [
      "Ten minutes from campus with a steady, structured intern program",
      "Your SQL and Python map directly to their data tooling",
      "Hires Ohio State underclassmen every cycle"
    ],
    facts: { stipend: "$5,200/mo", location: "Columbus, OH · On site", term: "Summer 2026", team: "Data & Analytics", co: "20,000 people · Public", posted: "2d ago" },
    have: ["Python", "SQL"], need: []
  },
  {
    id: "datadog", band: "look", bandLabel: "Worth a look", type: "startup", typeLabel: "Startup",
    logo: "D", alt: true,
    title: "Software Engineer Intern", company: "Datadog", meta: "Datadog · New York, NY · Summer 2026",
    about: "Monitoring and observability for cloud applications, with a large and growing engineering org.",
    why: [
      "Strong generalist backend fit for your Python background",
      "A big, well-run intern program with mentorship"
    ],
    note: "The catch: observability is a new domain for you, so expect a ramp on the concepts.",
    facts: { stipend: "$8,600/mo", location: "New York, NY · Hybrid", term: "Summer 2026", team: "Platform", co: "5,000 people · Public", posted: "4d ago" },
    have: ["Python"], need: ["Observability"]
  },
  {
    id: "ibm", band: "look", bandLabel: "Worth a look", type: "bigtech", typeLabel: "Big tech",
    logo: "I", alt: false,
    title: "Software Developer Intern", company: "IBM", meta: "IBM · Austin, TX · Summer 2026",
    about: "Enterprise software and cloud, with one of the longest-running internship programs in tech.",
    why: [
      "A broad program that takes underclassmen across many teams",
      "Your stack is a clean fit for their cloud tooling"
    ],
    note: "The catch: team assignment is luck of the draw, so the work varies a lot.",
    facts: { stipend: "$6,800/mo", location: "Austin, TX · Hybrid", term: "Summer 2026", team: "Cloud", co: "280,000 people · Public", posted: "1w ago" },
    have: ["Python", "SQL"], need: []
  },
  {
    id: "databricks", band: "stretch", bandLabel: "Stretch", type: "selective", typeLabel: "Selective",
    logo: "D", alt: false,
    title: "Software Engineer Intern", company: "Databricks", meta: "Databricks · San Francisco, CA",
    about: "The data and AI platform built on Apache Spark, used by data teams at thousands of companies.",
    why: [
      "Your applied ML coursework is the right starting instinct",
      "Data-heavy product that rewards your Python depth"
    ],
    gap: "Distributed data systems at production scale. Spark internals and big-data tooling are still ahead of your coursework.",
    facts: { stipend: "$9,600/mo", location: "San Francisco, CA · On site", term: "Summer 2026", team: "Compute", co: "6,000 people · Private", posted: "3d ago" },
    have: ["Python", "Applied ML"], need: ["Distributed data", "Spark"]
  }
];

const SM_BANDS = [
  { key: "strong", label: "Strong matches" },
  { key: "look", label: "Worth a look" },
  { key: "stretch", label: "Stretch" }
];

/* ---- application pipeline stages (the tracker's spine) ---- */
const SM_STAGES = [
  { key: "saved", label: "Saved" },
  { key: "applied", label: "Applied" },
  { key: "interviewing", label: "Interviewing" },
  { key: "closed", label: "Closed" }
];
const SM_STAGE_LABEL = Object.fromEntries(SM_STAGES.map(s => [s.key, s.label]));
/* the drawer only offers forward steps the student confirms — Closed is set via its own control */
const SM_STAGE_PICKER = ["saved", "applied", "interviewing"];

/* "today" for the demo, fixed so seeded deadlines stay meaningful across reloads */
const SM_TODAY = new Date(2026, 5, 19); // 2026-06-19 (month is 0-indexed)

/* ---- date helpers (deadlines + applied-on tags) ---- */
function smISO(d) {
  const z = n => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${z(d.getMonth() + 1)}-${z(d.getDate())}`;
}
function smOffsetISO(days) { const d = new Date(SM_TODAY); d.setDate(d.getDate() + days); return smISO(d); }
const SM_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
function smFmtDate(iso) {
  if (!iso) return "";
  const p = iso.split("-").map(Number);
  if (p.length !== 3) return iso;
  return `${SM_MONTHS[p[1] - 1]} ${p[2]}`;
}
/* whole-day distance from "today"; negative = past */
function smDaysUntil(iso) {
  if (!iso) return null;
  const p = iso.split("-").map(Number);
  const d = new Date(p[0], p[1] - 1, p[2]);
  return Math.round((d - SM_TODAY) / 86400000);
}
function smDeadlineSoon(iso) { const n = smDaysUntil(iso); return n !== null && n >= 0 && n <= 7; }

/* ---- save + status store (localStorage) ----
   `saved` is the legacy id list (kept for the sidebar badge + Saved page parity).
   `pipe` maps id → { status, deadline?, appliedAt?, savedAt? }. Saving a role with no
   status seeds it at "saved"; setting a later status records appliedAt the first time it
   crosses into Applied/Interviewing. Nothing here auto-advances — the user drives every move. */
const SM = {
  KEY: "sm:saved",
  PKEY: "sm:pipe",
  _read() {
    try { const v = JSON.parse(localStorage.getItem(this.KEY)); return Array.isArray(v) ? v : null; }
    catch (e) { return null; }
  },
  _readPipe() {
    try { const v = JSON.parse(localStorage.getItem(this.PKEY)); return (v && typeof v === "object") ? v : null; }
    catch (e) { return null; }
  },
  _writePipe(p) { localStorage.setItem(this.PKEY, JSON.stringify(p)); },
  list() {
    let v = this._read();
    if (v === null) { v = ["ramp-swe", "covermymeds", "nvidia-systems", "sardine", "msft-explore", "amazon"]; localStorage.setItem(this.KEY, JSON.stringify(v)); }
    return v;
  },
  /* seed a believable pipeline on first load: a couple applied, one interviewing, two near-term deadlines */
  pipe() {
    let p = this._readPipe();
    if (p === null) {
      p = {
        "ramp-swe":       { status: "interviewing", appliedAt: smOffsetISO(-12), savedAt: smOffsetISO(-16) },
        "sardine":        { status: "applied",      appliedAt: smOffsetISO(-5),  savedAt: smOffsetISO(-8), deadline: smOffsetISO(4) },
        "msft-explore":   { status: "applied",      appliedAt: smOffsetISO(-2),  savedAt: smOffsetISO(-3), deadline: smOffsetISO(2) },
        "covermymeds":    { status: "saved",        savedAt: smOffsetISO(-9) },   // stale → triggers a Nudge
        "nvidia-systems": { status: "saved",        savedAt: smOffsetISO(-1) },
        "amazon":         { status: "saved",        savedAt: smOffsetISO(-4) }
      };
      this._writePipe(p);
    }
    return p;
  },
  entry(id) { return this.pipe()[id] || null; },
  status(id) { const e = this.entry(id); return e ? e.status : null; },
  deadline(id) { const e = this.entry(id); return e ? (e.deadline || "") : ""; },
  has(id) { return this.list().includes(id); },
  /* set/clear a pipeline status. status===null removes the role from the pipeline entirely.
     Crossing into applied/interviewing stamps appliedAt once; saving stamps savedAt once. */
  setStatus(id, status) {
    const p = this.pipe();
    if (status === null) {
      delete p[id];
      this._writePipe(p);
      this._syncSaved(id, false);
      this.badge();
      return;
    }
    const e = p[id] || {};
    e.status = status;
    if (!e.savedAt) e.savedAt = smISO(SM_TODAY);
    if ((status === "applied" || status === "interviewing") && !e.appliedAt) e.appliedAt = smISO(SM_TODAY);
    p[id] = e;
    this._writePipe(p);
    // any tracked role (except an explicitly-closed one) counts as saved for the sidebar badge
    this._syncSaved(id, status !== "closed");
    this.badge();
  },
  setDeadline(id, iso) {
    const p = this.pipe();
    const e = p[id] || { status: "saved", savedAt: smISO(SM_TODAY) };
    if (iso) e.deadline = iso; else delete e.deadline;
    p[id] = e;
    this._writePipe(p);
  },
  _syncSaved(id, on) {
    let v = this.list();
    const has = v.includes(id);
    if (on && !has) v = [...v, id];
    if (!on && has) v = v.filter(x => x !== id);
    localStorage.setItem(this.KEY, JSON.stringify(v));
  },
  /* bookmark toggle = enter/leave the pipeline at "saved" (or clear it) */
  toggle(id) {
    const tracked = !!this.entry(id);
    if (tracked) { this.setStatus(id, null); return false; }
    this.setStatus(id, "saved");
    return true;
  },
  badge() {
    const n = this.list().length;
    document.querySelectorAll("[data-saved-count]").forEach(el => {
      el.textContent = String(n);
      el.style.display = n ? "" : "none";
    });
  },
  /* live counts per stage, for the pipeline tiles */
  counts() {
    const c = { saved: 0, applied: 0, interviewing: 0, closed: 0 };
    const p = this.pipe();
    for (const id in p) { const s = p[id].status; if (s in c) c[s]++; }
    return c;
  },
  /* roles whose user-set deadline falls within the next 7 days (excludes closed) */
  deadlinesSoon() {
    const p = this.pipe(), out = [];
    for (const id in p) { const e = p[id]; if (e.status !== "closed" && smDeadlineSoon(e.deadline)) out.push(id); }
    return out;
  },
  /* saved (not yet applied) for more than the stale threshold → eligible for a Nudge */
  STALE_DAYS: 7,
  isStale(id) {
    const e = this.entry(id);
    if (!e || e.status !== "saved" || !e.savedAt) return false;
    const age = -smDaysUntil(e.savedAt);
    return age >= this.STALE_DAYS;
  },
  staleAge(id) { const e = this.entry(id); return e && e.savedAt ? -smDaysUntil(e.savedAt) : 0; },
  role(id) { return ALL_ROLES.find(r => r.id === id); }
};

/* ---- company logos ----
   Per-role domain → logo. The demo uses Google's keyless favicon service, which
   returns crisp square brand icons that suit the square box. In production each
   listing would carry a precomputed logo_url; smLogoSrc is the one swap point. */
const SM_LOGO_DOMAINS = {
  "ramp-swe": "ramp.com", "covermymeds": "covermymeds.com", "root": "joinroot.com",
  "sardine": "sardine.ai", "vercel": "vercel.com", "msft-explore": "microsoft.com",
  "jpmc": "jpmorganchase.com", "google-step": "google.com", "amazon": "amazon.com",
  "oracle": "oracle.com", "notion": "notion.so", "plaid": "plaid.com",
  "nvidia-systems": "nvidia.com", "meta-ml": "meta.com", "apple-coreos": "apple.com",
  "stripe-risk": "stripe.com", "huntington": "huntington.com", "datadog": "datadoghq.com",
  "ibm": "ibm.com", "databricks": "databricks.com"
};
function smLogoSrc(domain) { return `https://www.google.com/s2/favicons?domain=${domain}&sz=128`; }
function smLogoHTML(r) {
  const cls = `logo${r.alt ? " alt" : ""}`;
  const domain = SM_LOGO_DOMAINS[r.id];
  if (!domain) return `<div class="${cls}">${r.logo}</div>`;
  // on error: drop the image styling and restore the letter avatar
  const fallback = `this.parentNode.classList.remove('has-img');this.parentNode.textContent='${r.logo}'`;
  return `<div class="${cls} has-img"><img src="${smLogoSrc(domain)}" alt="${r.company} logo" loading="lazy" onerror="${fallback}"></div>`;
}

/* all roles known to the store = curated feed + intake pool (drawer/lookup needs both) */
const ALL_ROLES = SM_ROLES.concat(SM_MORE_ROLES);

/* ---- shared row renderer ---- */
const BOOKMARK_SVG = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/></svg>';

/* drawer fact-row icons (money / pin / clock / layers / building) */
const _fIco = (p) => `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${p}</svg>`;
const SM_FACT_ICONS = {
  Stipend: _fIco('<rect x="3" y="6" width="18" height="12" rx="2"/><circle cx="12" cy="12" r="2.5"/>'),
  Location: _fIco('<path d="M12 21s7-6 7-11a7 7 0 1 0-14 0c0 5 7 11 7 11Z"/><circle cx="12" cy="10" r="2.5"/>'),
  Term: _fIco('<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.5 2"/>'),
  Team: _fIco('<path d="m12 3 9 5-9 5-9-5 9-5Z"/><path d="m3 13 9 5 9-5"/>'),
  Company: _fIco('<rect x="5" y="3" width="14" height="18" rx="1.5"/><path d="M9 7h2M13 7h2M9 11h2M13 11h2M9 15h2M13 15h2"/>'),
  Posted: _fIco('<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.5 2"/>'),
};
/* small clock/flag glyph for the deadline field label */
const SM_DEADLINE_ICO = _fIco('<path d="M4 22V4h12l-2 4 2 4H6"/>');

/* a role's pipeline tag for the row: e.g. "Applied · Apr 3", "Interviewing", "Saved 9d" */
function smStatusTagHTML(r) {
  const e = SM.entry(r.id);
  if (!e) return "";
  const s = e.status;
  let txt = SM_STAGE_LABEL[s];
  if ((s === "applied" || s === "interviewing") && e.appliedAt) {
    txt = `${SM_STAGE_LABEL[s]} · ${smFmtDate(e.appliedAt)}`;
  } else if (s === "saved" && e.savedAt) {
    const age = -smDaysUntil(e.savedAt);
    if (age >= 1) txt = `Saved ${age}d ago`;
  }
  return `<span class="status-tag st-${s}" data-status-tag="${r.id}"><i class="sd"></i>${txt}</span>`;
}

/* a soft, dismissible-feeling "Nudge" pill for stale saved roles (honest, no shame metric) */
function smNudgeHTML(r) {
  if (!SM.isStale(r.id)) return "";
  return `<span class="nudge" data-nudge="${r.id}" title="Saved ${SM.staleAge(r.id)} days ago — still open?">
    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.7 21a2 2 0 0 1-3.4 0"/></svg>
    Nudge</span>`;
}

function smRowHTML(r) {
  const tracked = !!SM.entry(r.id);
  return `
  <article class="role${tracked ? " is-tracked" : ""}" data-band="${r.band}" data-type="${r.type}" data-stage="${SM.status(r.id) || ""}" id="${r.id}">
    <button class="role-head" data-open="${r.id}" aria-haspopup="dialog">
      ${smLogoHTML(r)}
      <div class="meta">
        <div class="ti">${r.title}</div>
        <div class="su">${r.meta} · ${r.facts.posted} <span class="type-tag">${r.typeLabel}</span></div>
        <div class="rowtags">${smStatusTagHTML(r)}${smNudgeHTML(r)}</div>
      </div>
      <div class="verdict"><span class="tier ${r.band}"><i></i><i></i><i></i></span><span class="aff">Details →</span></div>
    </button>
    <button class="savebtn${SM.has(r.id) ? " on" : ""}" data-save="${r.id}" aria-label="Save ${r.title} at ${r.company}" aria-pressed="${SM.has(r.id)}">${BOOKMARK_SVG}</button>
  </article>`;
}

function smBindSaves(scope) {
  (scope || document).querySelectorAll("[data-save]").forEach(btn => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const on = SM.toggle(btn.dataset.save);
      document.querySelectorAll(`[data-save="${btn.dataset.save}"]`).forEach(b => {
        b.classList.toggle("on", on);
        b.setAttribute("aria-pressed", String(on));
        if (b.classList.contains("btn")) b.querySelector("span").textContent = on ? "Saved" : "Save";
      });
      if (typeof window.smOnPipeChange === "function") window.smOnPipeChange(btn.dataset.save);
    });
  });
}

/* ---- drawer (built once, filled per role) ---- */
const SMDrawer = {
  el: null, scrim: null,
  init() {
    if (this.el) return;
    this.scrim = document.createElement("div");
    this.scrim.className = "scrim";
    this.el = document.createElement("aside");
    this.el.className = "drawer";
    this.el.setAttribute("role", "dialog");
    this.el.setAttribute("aria-label", "Role details");
    document.body.append(this.scrim, this.el);
    this.scrim.addEventListener("click", () => this.close());
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") this.close(); });
  },
  open(id) {
    const r = SM.role(id);
    if (!r) return;
    this.init();
    const dot = { strong: "var(--mint)", look: "var(--cyan)", stretch: "var(--gold)" }[r.band];
    const factRows = [
      ["Stipend", r.facts.stipend], ["Location", r.facts.location],
      ["Term", r.facts.term], ["Team", r.facts.team],
      ["Company", r.facts.co], ["Posted", r.facts.posted]
    ].map(([l, v]) => `<div class="fact"><div class="fl">${SM_FACT_ICONS[l] || ""}${l}</div><div class="fv">${v}</div></div>`).join("");
    const saved = SM.has(r.id);
    const cur = SM.status(r.id);             // null | saved | applied | interviewing | closed
    const dl = SM.deadline(r.id);
    const closed = cur === "closed";

    // status selector — the tracker's core control. Saved → Applied → Interviewing as confirmable
    // steps; a quiet "Mark closed" / "Not tracking" footer. Never auto-advances.
    const segBtns = SM_STAGE_PICKER.map(s =>
      `<button class="stseg-btn${cur === s ? " on" : ""} stage-${s}" data-set-status="${s}" aria-pressed="${cur === s}">${SM_STAGE_LABEL[s]}</button>`
    ).join('<span class="stseg-arrow" aria-hidden="true">→</span>');

    this.el.innerHTML = `
      <div class="dr-head">
        <div class="dr-eyebrow"><span class="dot" style="background:${dot}"></span> ${r.bandLabel} · ${r.typeLabel}
          <button class="dr-close" aria-label="Close details">✕</button></div>
        <div class="dr-title">
          ${smLogoHTML(r)}
          <div class="dr-name"><h2>${r.title}</h2><div class="co">${r.company}</div></div>
          <div class="dr-band"><span class="band-pill band-${r.band}"><span class="tier ${r.band}"><i></i><i></i><i></i></span> ${r.bandLabel}</span></div>
        </div>
      </div>
      <div class="dr-body">
        <p class="about">${r.about}</p>
        <div class="facts">${factRows}</div>

        <div class="fit-label">Application status</div>
        <div class="trackbox${closed ? " is-closed" : ""}" data-trackbox>
          <div class="stseg" role="group" aria-label="Set application stage">${segBtns}</div>
          <div class="track-row">
            <label class="dl-field">
              <span class="dl-lab">${SM_DEADLINE_ICO} Deadline</span>
              <input type="date" class="dl-input" data-deadline value="${dl}">
            </label>
            <div class="track-foot">
              ${cur && !closed ? `<button class="track-mini" data-set-status="closed">Mark closed</button>` : ""}
              ${closed ? `<span class="closed-tag">Closed</span> <button class="track-mini" data-set-status="saved">Reopen</button>` : ""}
              ${cur ? `<button class="track-mini ghost" data-set-status="__none">Not tracking</button>` : `<span class="track-hint">Set a stage to track this role.</span>`}
            </div>
          </div>
        </div>

        <div class="fit-label">Why you fit</div>
        <ul class="checks">${r.why.map(w => `<li>${w}</li>`).join("")}</ul>
        ${r.gap ? `<div class="gap-note"><b>Gap to close:</b> ${r.gap}</div>` : ""}
        ${r.note ? `<p class="dr-note">${r.note}</p>` : ""}
        <div class="fit-label">Skill alignment</div>
        ${r.have.length ? `<div class="dr-sub">You already bring</div><div class="dr-skills">${r.have.map(s => `<span class="req-chip ok">✓ ${s}</span>`).join("")}</div>` : ""}
        ${r.need.length ? `<div class="dr-sub">Worth shoring up</div><div class="dr-skills">${r.need.map(s => `<span class="req-chip ghosted">${s}</span>`).join("")}</div>` : ""}
      </div>
      <div class="dr-actions">
        <a class="btn btn-primary" href="#">Apply now <span class="arrow">→</span></a>
        <button class="btn btn-ghost dr-save${saved ? " on" : ""}" data-save="${r.id}" aria-pressed="${saved}">${BOOKMARK_SVG}<span>${saved ? "Saved" : "Save"}</span></button>
        <a class="btn btn-ghost" href="#">Full analysis <span class="arrow">→</span></a>
      </div>`;

    this.el.querySelector(".dr-close").addEventListener("click", () => this.close());
    smBindSaves(this.el);
    this._bindStatus(r.id);
    requestAnimationFrame(() => { this.scrim.classList.add("show"); this.el.classList.add("open"); });
    document.body.style.overflow = "hidden";
  },
  /* wire the status segment + deadline field; re-render the box in place and notify the page */
  _bindStatus(id) {
    const box = this.el.querySelector("[data-trackbox]");
    if (!box) return;
    box.querySelectorAll("[data-set-status]").forEach(btn => {
      btn.addEventListener("click", () => {
        const v = btn.dataset.setStatus;
        const cur = SM.status(id);
        if (v === "__none") SM.setStatus(id, null);
        else if (v === cur && v !== "closed") SM.setStatus(id, null); // toggle the active stage off
        else SM.setStatus(id, v);
        this._refreshTrack(id);
        // keep the drawer Save button in sync (tracking ⇒ saved)
        const nowSaved = SM.has(id);
        this.el.querySelectorAll(`.dr-save[data-save="${id}"]`).forEach(b => {
          b.classList.toggle("on", nowSaved);
          b.setAttribute("aria-pressed", String(nowSaved));
          b.querySelector("span").textContent = nowSaved ? "Saved" : "Save";
        });
        if (typeof window.smOnPipeChange === "function") window.smOnPipeChange(id);
      });
    });
    const dlInput = box.querySelector("[data-deadline]");
    if (dlInput) dlInput.addEventListener("change", () => {
      SM.setDeadline(id, dlInput.value || "");
      if (typeof window.smOnPipeChange === "function") window.smOnPipeChange(id);
    });
  },
  /* rebuild just the status control after a change (cheap, keeps the drawer open) */
  _refreshTrack(id) {
    const r = SM.role(id);
    const box = this.el.querySelector("[data-trackbox]");
    if (!box || !r) return;
    const cur = SM.status(id), dl = SM.deadline(id), closed = cur === "closed";
    const segBtns = SM_STAGE_PICKER.map(s =>
      `<button class="stseg-btn${cur === s ? " on" : ""} stage-${s}" data-set-status="${s}" aria-pressed="${cur === s}">${SM_STAGE_LABEL[s]}</button>`
    ).join('<span class="stseg-arrow" aria-hidden="true">→</span>');
    box.classList.toggle("is-closed", closed);
    box.innerHTML = `
      <div class="stseg" role="group" aria-label="Set application stage">${segBtns}</div>
      <div class="track-row">
        <label class="dl-field">
          <span class="dl-lab">${SM_DEADLINE_ICO} Deadline</span>
          <input type="date" class="dl-input" data-deadline value="${dl}">
        </label>
        <div class="track-foot">
          ${cur && !closed ? `<button class="track-mini" data-set-status="closed">Mark closed</button>` : ""}
          ${closed ? `<span class="closed-tag">Closed</span> <button class="track-mini" data-set-status="saved">Reopen</button>` : ""}
          ${cur ? `<button class="track-mini ghost" data-set-status="__none">Not tracking</button>` : `<span class="track-hint">Set a stage to track this role.</span>`}
        </div>
      </div>`;
    this._bindStatus(id);
  },
  close() {
    if (!this.el) return;
    this.scrim.classList.remove("show");
    this.el.classList.remove("open");
    document.body.style.overflow = "";
  }
};

function smBindRows(scope) {
  (scope || document).querySelectorAll("[data-open]").forEach(b =>
    b.addEventListener("click", () => SMDrawer.open(b.dataset.open)));
}
