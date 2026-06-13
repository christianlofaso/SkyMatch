/* ============================================================
   SkyMatch — data layer (realistic fake content)
   Exposed on window as SM_DATA.
   ============================================================ */

const PROFILE = {
  name: "Maya Chen",
  handle: "maya-chen",
  headline: "CS @ UC Berkeley · Aspiring SWE",
  school: "UC Berkeley",
  grad: "May 2027",
  location: "Berkeley, CA",
  initials: "MC",
  level: "Junior · 3rd year",
  summary: "Computer Science undergrad with two prior internships, a strong systems foundation, and shipped side projects in React and Go. Looking for a Summer 2026 SWE internship.",
  skills: ["React","TypeScript","Python","Go","PostgreSQL","Distributed Systems","REST APIs","Git","Docker","Data Structures"],
  growthSkills: ["Kubernetes","gRPC","Rust","System Design"],
  experience: [
    { role:"Software Engineering Intern", org:"Brex", period:"Summer 2025 · 12 wks", note:"Shipped a ledger-reconciliation service in Go handling 4M+ daily events." },
    { role:"Undergraduate Researcher", org:"Berkeley RISELab", period:"2024 – 2025", note:"Built benchmarking tooling for distributed query engines." },
    { role:"SWE Intern", org:"Local fintech (seed)", period:"Summer 2024 · 10 wks", note:"Owned the React dashboard and a Stripe billing integration." },
  ],
  vector: [ // radar dimensions 0-100
    { k:"Frontend", v:82 },
    { k:"Backend", v:88 },
    { k:"Systems", v:74 },
    { k:"Data", v:66 },
    { k:"Product", v:71 },
    { k:"ML", v:48 },
  ],
};

// tier helper from score
const tierOf = (s)=> s>=80 ? {label:"Strong", cls:"strong"} : s>=62 ? {label:"Stretch", cls:"stretch"} : {label:"Reach", cls:"reach"};

const ROLES = [
  // ---------- STARTUP ----------
  { id:"r1", bucket:"startup", company:"Ramp", initial:"R", title:"Software Engineer Intern", location:"New York, NY", term:"Summer 2026", remote:"Hybrid", pay:"$9,500/mo", posted:"2d", score:88, team:"Payments Platform",
    why:["Your Brex ledger work maps almost 1:1 to Ramp's reconciliation stack","Go + PostgreSQL are core to this team's services","Fintech domain experience moves you ahead of the median applicant"],
    matched:["Go","PostgreSQL","REST APIs","Distributed Systems"], gaps:["Kafka","Temporal"], size:"650 people · Series D" },
  { id:"r2", bucket:"startup", company:"Linear", initial:"L", title:"Product Engineering Intern", location:"Remote (US)", term:"12 weeks", remote:"Remote", pay:"$8,800/mo", posted:"4d", score:81, team:"Core Product",
    why:["React + TypeScript are exactly Linear's frontend stack","Your shipped dashboards show product-minded engineering","Small team means high ownership — a fit for your seed-stage experience"],
    matched:["React","TypeScript","REST APIs"], gaps:["GraphQL","Electron"], size:"60 people · Series B" },
  { id:"r3", bucket:"startup", company:"Vercel", initial:"V", title:"Frontend Infrastructure Intern", location:"Remote (US)", term:"Summer 2026", remote:"Remote", pay:"$8,500/mo", posted:"1w", score:73, team:"Build Output",
    why:["Strong React foundation transfers to framework-level work","Infra exposure from RISELab is relevant","This role leans deeper into bundlers than your current depth"],
    matched:["React","TypeScript","Git"], gaps:["Rust","Webpack internals","Edge runtimes"], size:"500 people · Series E" },
  { id:"r4", bucket:"startup", company:"Notion", initial:"N", title:"Backend Engineering Intern", location:"San Francisco, CA", term:"Summer 2026", remote:"Hybrid", pay:"$9,200/mo", posted:"3d", score:78, team:"Sync & Storage",
    why:["Distributed systems coursework + RISELab tooling fit the sync team","Postgres depth is directly applicable","Block-model data work is a new but adjacent domain"],
    matched:["PostgreSQL","Distributed Systems","Python"], gaps:["CRDTs","Elixir"], size:"800 people · Series C" },
  { id:"r5", bucket:"startup", company:"Plaid", initial:"P", title:"Backend Intern, Payments", location:"San Francisco, CA", term:"Summer 2026", remote:"Hybrid", pay:"$9,000/mo", posted:"5d", score:64, team:"Money Movement",
    why:["Fintech background is a clear signal","Core stack overlaps on Go and APIs","Bar leans toward candidates with prior payments-rails depth"],
    matched:["Go","REST APIs"], gaps:["ACH rails","Bank integrations"], size:"1,200 people · Series D" },
  { id:"r6", bucket:"startup", company:"Retool", initial:"R", title:"Full-Stack Intern", location:"San Francisco, CA", term:"12 weeks", remote:"Hybrid", pay:"$8,700/mo", posted:"6d", score:76, team:"App Platform",
    why:["Full-stack profile matches the team's generalist need","React + Postgres are day-one tools here","Internal-tools product sense pairs with your dashboard work"],
    matched:["React","TypeScript","PostgreSQL","REST APIs"], gaps:["Query engines"], size:"350 people · Series C" },

  // ---------- BIG TECH ----------
  { id:"r7", bucket:"bigtech", company:"Stripe", initial:"S", title:"Software Engineer Intern", location:"Seattle, WA", term:"Summer 2026", remote:"Hybrid", pay:"$10,200/mo", posted:"1d", score:84, team:"Payments Infrastructure",
    why:["Brex fintech internship is a near-perfect signal for Stripe","Go services at scale match your reconciliation project","Strong DS&A foundation clears the technical bar"],
    matched:["Go","PostgreSQL","Distributed Systems","Data Structures"], gaps:["Ruby","Large-scale on-call"], size:"8,000+ · Public-track" },
  { id:"r8", bucket:"bigtech", company:"Databricks", initial:"D", title:"Software Engineer Intern", location:"Mountain View, CA", term:"Summer 2026", remote:"Hybrid", pay:"$10,500/mo", posted:"2d", score:79, team:"Query Engine",
    why:["RISELab query-engine benchmarking is directly on-topic","Distributed systems strength is a major plus","Scala/Spark internals are new ground for you"],
    matched:["Distributed Systems","Python","Data Structures"], gaps:["Scala","Spark internals","JVM tuning"], size:"7,000+ · Pre-IPO" },
  { id:"r9", bucket:"bigtech", company:"Snowflake", initial:"S", title:"Backend SWE Intern", location:"San Mateo, CA", term:"Summer 2026", remote:"Hybrid", pay:"$10,000/mo", posted:"4d", score:71, team:"Storage Engine",
    why:["Database depth from Postgres + research is relevant","Systems coursework aligns with the storage team","C++ systems work is a meaningful stretch"],
    matched:["PostgreSQL","Distributed Systems"], gaps:["C++","Columnar storage"], size:"7,000+ · Public" },
  { id:"r10", bucket:"bigtech", company:"Airbnb", initial:"A", title:"Frontend Engineer Intern", location:"San Francisco, CA", term:"Summer 2026", remote:"Hybrid", pay:"$9,800/mo", posted:"3d", score:80, team:"Guest Web",
    why:["React + TypeScript are the core of Airbnb web","Product-minded dashboard work transfers cleanly","Design-system fluency would push this even higher"],
    matched:["React","TypeScript","REST APIs"], gaps:["Design systems at scale"], size:"6,000+ · Public" },
  { id:"r11", bucket:"bigtech", company:"Nvidia", initial:"N", title:"Software Intern, Developer Tools", location:"Santa Clara, CA", term:"Summer 2026", remote:"On-site", pay:"$9,600/mo", posted:"1w", score:62, team:"Developer Platform",
    why:["Tooling experience from RISELab is relevant","Python automation overlaps with the role","CUDA / GPU exposure is largely new for you"],
    matched:["Python","Git"], gaps:["CUDA","C++","GPU profiling"], size:"25,000+ · Public" },

  // ---------- LOCAL ----------
  { id:"r12", bucket:"local", company:"Asana", initial:"A", title:"Software Engineer Intern", location:"San Francisco, CA", term:"Summer 2026", remote:"Hybrid · 25mi", pay:"$9,400/mo", posted:"2d", score:83, team:"Work Graph",
    why:["20-minute commute from Berkeley","React + TypeScript front-end stack matches exactly","Graph-data model is adjacent to your systems work"],
    matched:["React","TypeScript","REST APIs","Data Structures"], gaps:["Luna framework"], size:"1,800 · Public" },
  { id:"r13", bucket:"local", company:"Chan Zuckerberg Initiative", initial:"C", title:"Engineering Intern, Science", location:"Redwood City, CA", term:"10 weeks", remote:"Hybrid · 30mi", pay:"$8,900/mo", posted:"5d", score:74, team:"Open Science",
    why:["Python + data tooling fit the science platform","Research background resonates with the mission","Bioinformatics domain is new but learnable"],
    matched:["Python","PostgreSQL","Git"], gaps:["Bioinformatics","Pandas at scale"], size:"900 · Nonprofit" },
  { id:"r14", bucket:"local", company:"Sutter Health Labs", initial:"S", title:"Software Developer Intern", location:"Oakland, CA", term:"Summer 2026", remote:"On-site · 8mi", pay:"$7,800/mo", posted:"1w", score:69, team:"Data Platform",
    why:["Right next door in Oakland","Backend + SQL skills map to the data platform","Healthcare compliance work is unfamiliar territory"],
    matched:["PostgreSQL","Python","REST APIs"], gaps:["HIPAA","HL7/FHIR"], size:"Enterprise · Health" },
  { id:"r15", bucket:"local", company:"Berkeley Lab (LBNL)", initial:"B", title:"Computing Sciences Intern", location:"Berkeley, CA", term:"Summer 2026", remote:"On-site · 2mi", pay:"$7,500/mo", posted:"3d", score:77, team:"Scientific Data",
    why:["Walking distance from campus","RISELab research is squarely relevant","HPC scheduling is a natural extension of your systems work"],
    matched:["Distributed Systems","Python","Git"], gaps:["MPI","Slurm","HPC"], size:"Government Lab" },

  // ---------- REACH ----------
  { id:"r16", bucket:"reach", company:"OpenAI", initial:"O", title:"Software Engineer Intern, Platform", location:"San Francisco, CA", term:"Summer 2026", remote:"On-site", pay:"$11,500/mo", posted:"1d", score:58, team:"Inference Platform",
    why:["Distributed systems strength is a real asset here","Go + infra work is directly relevant","Bar expects deeper large-scale inference experience"],
    matched:["Distributed Systems","Go","Python"], gaps:["GPU orchestration","Triton","Ray at scale"], size:"2,500 · Frontier lab" },
  { id:"r17", bucket:"reach", company:"Anthropic", initial:"A", title:"Software Engineer Intern", location:"San Francisco, CA", term:"Summer 2026", remote:"Hybrid", pay:"$11,800/mo", posted:"2d", score:55, team:"Model Serving",
    why:["Systems + reliability mindset fits the serving team","Python tooling is part of the day-to-day","ML-systems depth is the main gap to close"],
    matched:["Python","Distributed Systems"], gaps:["ML systems","Rust","Large-scale serving"], size:"1,000 · Frontier lab" },
  { id:"r18", bucket:"reach", company:"Jane Street", initial:"J", title:"Software Engineer Intern", location:"New York, NY", term:"Summer 2026", remote:"On-site", pay:"$16,000/mo", posted:"4d", score:52, team:"Trading Systems",
    why:["Strong DS&A and systems foundation is the right shape","Low-latency systems are an exciting stretch","OCaml + quant finance are entirely new domains"],
    matched:["Data Structures","Distributed Systems"], gaps:["OCaml","Low-latency","Quant finance"], size:"2,000 · Private" },
  { id:"r19", bucket:"reach", company:"Figma", initial:"F", title:"Software Engineer Intern, Multiplayer", location:"San Francisco, CA", term:"Summer 2026", remote:"Hybrid", pay:"$10,800/mo", posted:"6d", score:60, team:"Multiplayer",
    why:["Frontend + systems combo is exactly multiplayer's shape","React depth is a strong base","CRDT and WebGL internals are the reach factor"],
    matched:["React","TypeScript","Distributed Systems"], gaps:["CRDTs","WebGL","C++/WASM"], size:"1,500 · Pre-IPO" },
];

// analyzer sample (paste-a-posting result)
const ANALYZER_SAMPLE = {
  company:"Stripe", title:"Software Engineer Intern — Payments Infrastructure", location:"Seattle, WA · Summer 2026",
  verdict:"Strong fit", score:84, tier:"strong",
  summary:"Your fintech internship and Go systems work line up closely with this role. Two gaps stand between you and a top-decile application — both closable before the deadline.",
  haves:[
    { k:"Go service development", note:"Directly demonstrated at Brex" },
    { k:"PostgreSQL & data modeling", note:"Used across all three internships" },
    { k:"Distributed systems fundamentals", note:"Coursework + RISELab research" },
    { k:"Payments domain context", note:"Reconciliation service experience" },
  ],
  gaps:[
    { k:"Ruby familiarity", sev:"minor", note:"Stripe's monolith is Ruby — read-level fluency is enough to start" },
    { k:"Production on-call exposure", sev:"moderate", note:"No prior paging / incident experience on your profile" },
  ],
  plan:[
    { wk:"Week 1", task:"Ship a small Ruby + Sinatra service to get read/write fluency", done:false },
    { wk:"Week 2", task:"Rebuild your Brex reconciliation project write-up as a systems-design doc", done:false },
    { wk:"Week 3", task:"Run a mock on-call: instrument a service with alerts + a runbook", done:false },
    { wk:"Week 4", task:"Do 2 payments-systems mock interviews; tailor résumé to the JD", done:false },
  ],
};

window.SM_DATA = { PROFILE, ROLES, ANALYZER_SAMPLE, tierOf };
window.SM_TIER = tierOf;
