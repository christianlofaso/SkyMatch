/* demo-data.js — shared role data + save store + drawer for the SkyMatch "New-match alerts" demo (option-k).
   Extends the option-j base with: an SM_SEARCHES array of saved searches, an isNew flag + searchable
   tags on roles, an SMSeen store ("viewing a role clears its New dot"), and a row renderer that paints a
   left accent rail + "New" dot on fresh, unseen rows. Class names the CSS depends on (.role, .drawer,
   .tier, .band-head, .savebtn …) are preserved. */

const SM_ROLES = [
  {
    id: "ramp-swe", band: "strong", bandLabel: "Strong match", type: "startup", typeLabel: "Startup",
    logo: "R", alt: false, isNew: true, tags: ["swe", "remote", "summer", "fintech"],
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
    logo: "C", alt: true, tags: ["swe", "near", "summer"],
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
    logo: "R", alt: false, isNew: true, tags: ["swe", "near", "summer", "fintech"],
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
    logo: "S", alt: true, isNew: true, tags: ["swe", "remote", "summer", "fintech"],
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
    logo: "V", alt: true, tags: ["swe", "remote", "summer", "frontend"],
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
    logo: "M", alt: false, isNew: true, tags: ["swe", "bay", "summer"],
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
    logo: "J", alt: true, tags: ["swe", "near", "summer", "fintech"],
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
    logo: "G", alt: false, isNew: true, tags: ["swe", "bay", "summer"],
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
    logo: "A", alt: true, isNew: true, tags: ["swe", "bay", "summer"],
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
    logo: "O", alt: false, tags: ["swe", "summer"],
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
    logo: "N", alt: true, tags: ["swe", "bay", "summer", "frontend"],
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
    logo: "P", alt: true, isNew: true, tags: ["swe", "bay", "summer", "fintech"],
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
    logo: "N", alt: false, tags: ["swe", "bay", "summer"],
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
    logo: "M", alt: true, tags: ["swe", "bay", "summer"],
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
    logo: "A", alt: false, tags: ["swe", "bay", "summer"],
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

/* ---- "Load more" overflow pool ----
   Extra inventory appended (per active search) when "Load more" is pressed. These rows thread into the
   existing bands like any other role; a couple are flagged isNew so a fresh page still surfaces alerts. */
const SM_MORE_ROLES = [
  {
    id: "stripe-risk", band: "strong", bandLabel: "Strong match", type: "startup", typeLabel: "Startup",
    logo: "S", alt: true, isNew: true, tags: ["swe", "bay", "summer", "fintech"],
    title: "Software Engineer Intern, Risk", company: "Stripe", meta: "Stripe · San Francisco, CA · Summer 2026",
    about: "Payments infrastructure for the internet; the Risk org fights fraud across millions of businesses.",
    why: [
      "Their Radar product is your fraud-detection project at planetary scale",
      "Python plus applied ML is exactly the posted stack",
      "Interns own a shipped surface, not a sandbox"
    ],
    facts: { stipend: "$9,600/mo", location: "San Francisco, CA · Hybrid", term: "Summer 2026", team: "Risk", co: "8,000 people · Private", posted: "1d ago" },
    have: ["Python", "Applied ML", "SQL"], need: []
  },
  {
    id: "huntington", band: "strong", bandLabel: "Strong match", type: "near", typeLabel: "Near you",
    logo: "H", alt: false, tags: ["swe", "near", "summer", "fintech"],
    title: "Technology Intern", company: "Huntington Bank", meta: "Huntington Bank · Columbus, OH · 10 min from campus",
    about: "One of Columbus's anchor employers, with a sizable summer technology intern program downtown.",
    why: [
      "Ten minutes from campus, a downtown cohort that hires Ohio State students",
      "Python and SQL slot straight into their data tooling"
    ],
    facts: { stipend: "$5,200/mo", location: "Columbus, OH · On site", term: "Summer 2026", team: "Enterprise Data", co: "20,000 people · Public", posted: "4d ago" },
    have: ["Python", "SQL"], need: []
  },
  {
    id: "linear", band: "look", bandLabel: "Worth a look", type: "startup", typeLabel: "Startup",
    logo: "L", alt: true, tags: ["swe", "remote", "summer", "frontend"],
    title: "Product Engineer Intern", company: "Linear", meta: "Linear · Remote (US) · Summer 2026",
    about: "The issue tracker beloved by engineers, built by a small, craft-obsessed remote team.",
    why: [
      "Remote-first, so geography is not a filter",
      "Your React work matches their product surface"
    ],
    note: "The catch: a tiny intern class and a very high craft bar.",
    facts: { stipend: "$8,400/mo", location: "Remote (US)", term: "Summer 2026", team: "Product", co: "60 people · Series B", posted: "2d ago" },
    have: ["React"], need: ["UI craft"]
  },
  {
    id: "ibm", band: "look", bandLabel: "Worth a look", type: "bigtech", typeLabel: "Big tech",
    logo: "I", alt: false, tags: ["swe", "summer"],
    title: "Software Developer Intern", company: "IBM", meta: "IBM · Austin, TX · Summer 2026",
    about: "Enterprise software and cloud, with a large, structured summer intern program.",
    why: [
      "A steady generalist fit for your stack",
      "Big cohort, predictable onboarding"
    ],
    note: "The catch: little of your ML background gets exercised here.",
    facts: { stipend: "$6,800/mo", location: "Austin, TX · Hybrid", term: "Summer 2026", team: "Hybrid Cloud", co: "280,000 people · Public", posted: "1w ago" },
    have: ["Python", "SQL"], need: []
  },
  {
    id: "datadog", band: "stretch", bandLabel: "Stretch", type: "startup", typeLabel: "Startup",
    logo: "D", alt: true, tags: ["swe", "remote", "summer"],
    title: "Software Engineer Intern, Data", company: "Datadog", meta: "Datadog · New York, NY · Summer 2026",
    about: "Observability for cloud applications, ingesting trillions of events a day.",
    why: [
      "Your Python is real signal for their data tooling",
      "High-volume pipelines are a natural stretch from your coursework"
    ],
    gap: "Streaming systems at scale. You have batch ML, not the always-on pipelines they run.",
    facts: { stipend: "$9,100/mo", location: "New York, NY · Hybrid", term: "Summer 2026", team: "Data Platform", co: "5,000 people · Public", posted: "3d ago" },
    have: ["Python"], need: ["Streaming", "Distributed systems"]
  },
  {
    id: "snowflake", band: "stretch", bandLabel: "Stretch", type: "bigtech", typeLabel: "Big tech",
    logo: "S", alt: false, tags: ["swe", "bay", "summer"],
    title: "Software Engineer Intern", company: "Snowflake", meta: "Snowflake · San Mateo, CA · Summer 2026",
    about: "The cloud data platform; interns work close to the query engine and storage layer.",
    why: [
      "Strong CS fundamentals and Python are a real foundation",
      "SQL fluency maps to the product"
    ],
    gap: "Database internals and systems C++. A reach, but a coherent one given your trajectory.",
    facts: { stipend: "$9,300/mo", location: "San Mateo, CA · On site", term: "Summer 2026", team: "Query Engine", co: "7,000 people · Public", posted: "5d ago" },
    have: ["Python", "SQL"], need: ["DB internals", "Systems C++"]
  }
];

const SM_BANDS = [
  { key: "strong", label: "Strong matches" },
  { key: "look", label: "Worth a look" },
  { key: "stretch", label: "Stretch" }
];

/* ---- saved searches (option-k signature surface) ----
   Each saved search is an infinite query over the inventory. `tags` are ALL-match required tags; the
   chip's new-count = roles that are isNew, still unseen, AND match this search. The "all" pseudo-search
   is the default (no filter). Counts are computed live in newCountFor() so dismissing a dot updates them. */
const SM_SEARCHES = [
  { id: "all",     name: "All matches",        summary: "Every role in this run",        tags: [] },
  { id: "swe-bay", name: "SWE · Bay Area",      summary: "Software engineering · Bay Area · Summer", tags: ["swe", "bay"] },
  { id: "fintech", name: "Risk & Fintech",      summary: "Fraud / risk / payments · Summer",         tags: ["fintech"] },
  { id: "near",    name: "Near campus",         summary: "Columbus · within 30 min · Summer",        tags: ["near"] }
];

/* date the "since you were last here" copy reads against (demo: last visit was Tuesday). */
const SM_LAST_VISIT = "Tuesday";

/* ---- save store (localStorage) ---- */
const SM = {
  KEY: "sm:saved",
  _read() {
    try { const v = JSON.parse(localStorage.getItem(this.KEY)); return Array.isArray(v) ? v : null; }
    catch (e) { return null; }
  },
  list() {
    let v = this._read();
    if (v === null) { v = ["ramp-swe", "covermymeds", "nvidia-systems"]; localStorage.setItem(this.KEY, JSON.stringify(v)); }
    return v;
  },
  has(id) { return this.list().includes(id); },
  toggle(id) {
    let v = this.list();
    v = v.includes(id) ? v.filter(x => x !== id) : [...v, id];
    localStorage.setItem(this.KEY, JSON.stringify(v));
    this.badge();
    return v.includes(id);
  },
  badge() {
    const n = this.list().length;
    document.querySelectorAll("[data-saved-count]").forEach(el => {
      el.textContent = String(n);
      el.style.display = n ? "" : "none";
    });
  },
  role(id) { return ALL_ROLES.find(r => r.id === id); }
};

/* ---- "seen" store (localStorage) — viewing a role clears its New dot ----
   Mirrors the SM save-store pattern. Opening the drawer marks a role seen; the dot + accent rail clear
   on next render and the saved-search counts recompute. Honest mechanic: nothing decays on its own. */
const SMSeen = {
  KEY: "sm:seen",
  _read() {
    try { const v = JSON.parse(localStorage.getItem(this.KEY)); return Array.isArray(v) ? v : null; }
    catch (e) { return null; }
  },
  list() { const v = this._read(); return v === null ? [] : v; },
  has(id) { return this.list().includes(id); },
  mark(id) {
    const v = this.list();
    if (!v.includes(id)) { v.push(id); localStorage.setItem(this.KEY, JSON.stringify(v)); }
    return v;
  },
  // a role shows its "New" badge only while it is flagged isNew AND has not yet been opened
  isFresh(r) { return !!r.isNew && !this.has(r.id); }
};

/* all roles currently in play (base + any "Load more" pages that have been appended) */
let ALL_ROLES = [...SM_ROLES];

/* does a role satisfy a saved search? (ALL required tags must be present; empty tags = match all) */
function smRoleMatchesSearch(r, searchId) {
  const s = SM_SEARCHES.find(x => x.id === searchId) || SM_SEARCHES[0];
  if (!s.tags.length) return true;
  const t = r.tags || [];
  return s.tags.every(tag => t.includes(tag));
}

/* live new-count for a saved search across the roles currently loaded */
function smNewCountFor(searchId) {
  return ALL_ROLES.filter(r => SMSeen.isFresh(r) && smRoleMatchesSearch(r, searchId)).length;
}

/* ---- company logos ----
   Per-role domain → logo. The demo uses Google's keyless favicon service, which returns crisp square
   brand icons. Any load failure falls back to the original letter avatar. */
const SM_LOGO_DOMAINS = {
  "ramp-swe": "ramp.com", "covermymeds": "covermymeds.com", "root": "joinroot.com",
  "sardine": "sardine.ai", "vercel": "vercel.com", "msft-explore": "microsoft.com",
  "jpmc": "jpmorganchase.com", "google-step": "google.com", "amazon": "amazon.com",
  "oracle": "oracle.com", "notion": "notion.so", "plaid": "plaid.com",
  "nvidia-systems": "nvidia.com", "meta-ml": "meta.com", "apple-coreos": "apple.com",
  "stripe-risk": "stripe.com", "huntington": "huntington.com", "linear": "linear.app",
  "ibm": "ibm.com", "datadog": "datadoghq.com", "snowflake": "snowflake.com"
};
function smLogoSrc(domain) { return `https://www.google.com/s2/favicons?domain=${domain}&sz=128`; }
function smLogoHTML(r) {
  const cls = `logo${r.alt ? " alt" : ""}`;
  const domain = SM_LOGO_DOMAINS[r.id];
  if (!domain) return `<div class="${cls}">${r.logo}</div>`;
  const fallback = `this.parentNode.classList.remove('has-img');this.parentNode.textContent='${r.logo}'`;
  return `<div class="${cls} has-img"><img src="${smLogoSrc(domain)}" alt="${r.company} logo" loading="lazy" onerror="${fallback}"></div>`;
}

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

function smRowHTML(r) {
  const fresh = SMSeen.isFresh(r);
  const newDot = fresh ? '<span class="newdot" title="New since your last visit">New</span>' : "";
  return `
  <article class="role${fresh ? " is-new" : ""}" data-band="${r.band}" data-type="${r.type}" data-tags="${(r.tags || []).join(" ")}" id="${r.id}">
    <button class="role-head" data-open="${r.id}" aria-haspopup="dialog">
      ${smLogoHTML(r)}
      <div class="meta"><div class="ti">${r.title}${newDot}</div><div class="su">${r.meta} · ${r.facts.posted} <span class="type-tag">${r.typeLabel}</span></div></div>
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
      if (typeof window.smOnSaveChange === "function") window.smOnSaveChange();
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
    // viewing a role clears its "New" dot — mark seen, then let the host page re-render the feed
    const wasFresh = SMSeen.isFresh(r);
    SMSeen.mark(id);
    if (wasFresh && typeof window.smOnSeenChange === "function") window.smOnSeenChange();
    const dot = { strong: "var(--mint)", look: "var(--cyan)", stretch: "var(--gold)" }[r.band];
    const factRows = [
      ["Stipend", r.facts.stipend], ["Location", r.facts.location],
      ["Term", r.facts.term], ["Team", r.facts.team],
      ["Company", r.facts.co], ["Posted", r.facts.posted]
    ].map(([l, v]) => `<div class="fact"><div class="fl">${SM_FACT_ICONS[l] || ""}${l}</div><div class="fv">${v}</div></div>`).join("");
    const saved = SM.has(r.id);
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
    requestAnimationFrame(() => { this.scrim.classList.add("show"); this.el.classList.add("open"); });
    document.body.style.overflow = "hidden";
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
