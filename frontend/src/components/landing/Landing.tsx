"use client";
import Link from "next/link";
import { ProfileInput } from "./ProfileInput";
import { NavAuth } from "@/components/NavAuth";
import { useReveal } from "@/lib/useReveal";

// SkyMatch star-burst mark (option-j). Uses a landing-local gradient id (lm-warm).
const Mark = (
  <svg className="mark" viewBox="0 0 32 32" fill="none" aria-hidden>
    <circle cx="16" cy="16" r="15" stroke="url(#lm-warm)" strokeOpacity=".4" />
    <path d="M16 3.5c.9 6.2 2.4 9.6 8.5 12.5-6.1 2.9-7.6 6.3-8.5 12.5-.9-6.2-2.4-9.6-8.5-12.5C13.6 13.1 15.1 9.7 16 3.5Z" fill="url(#lm-warm)" />
    <circle cx="16" cy="16" r="2.1" fill="#080A0F" /><circle cx="16" cy="16" r="1.1" fill="url(#lm-warm)" />
  </svg>
);

const MARQUEE = ["Stripe", "Anduril", "Ramp", "NVIDIA", "Figma", "Databricks", "Vercel", "Notion", "Plaid", "Scale"];

const STEPS = [
  { n: "STEP 01", h: "Paste your profile", p: "Drop your resume or LinkedIn URL, and that is the whole setup. Nothing to fill out.",
    ico: <><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2" /><rect x="8" y="2" width="8" height="4" rx="1" /></> },
  { n: "STEP 02", h: "We read it like a person", p: "Your coursework, projects and skills become signal, not a bag of keywords. We weigh what you've actually done against what each role needs.",
    ico: <><circle cx="11" cy="11" r="7" /><path d="m21 21-4.3-4.3" /></> },
  { n: "STEP 03", h: "Get fifteen with reasons", p: "One ranked feed from strong matches to honest stretches, every role tagged by company type and carrying a one tap “why it landed here.”",
    ico: <><path d="M9 11l3 3L22 4" /><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" /></> },
];

const BANDS = [
  { k: "strong", tag: "Strong match", h: "Ready now", p: "Your coursework and projects already clear the bar. The reasoning names the exact signals that landed, so you know what to lead with.", count: "apply this week" },
  { k: "look", tag: "Worth a look", h: "Close, with a catch", p: "A real case with one soft spot. We name the soft spot in plain words, so you decide whether to push or pass.", count: "read, then decide" },
  { k: "stretch", tag: "Stretch", h: "A gap with a plan", p: "Usually a skill or two away. Each stretch names the gap and points at a plan to close it, so the long shots come with directions.", count: "prep, then apply" },
];

const PRINCIPLES = [
  { n: "a", h: "Reasoning, not a score", p: "A real explanation beats a mystery number every time. You see why each role fits, in words you can act on." },
  { n: "b", h: "A stretch is a stretch", p: "Trust comes from being straight about the odds, not inflating them. A stretch is labeled a stretch, with the gap named and a plan attached." },
  { n: "c", h: "Bands, not false precision", p: "Fit is shown as Strong, Worth a look, or Stretch, honest tiers, not a “67” pretending to a calibration nobody has." },
];

const FAQ = [
  { q: "Do I need to make an account?", a: "Your first match run is free — paste a profile and see your full scored shortlist with the reasoning on every role, no account needed. After that, a one-tap email sign-in (magic link, no password) unlocks more runs, saves them across devices, and opens the deeper job-fit analyzer." },
  { q: "How does the matching actually work?", a: "Your profile is turned into an embedding that captures skills, level and trajectory. Each indexed role is embedded the same way, so matching compares meaning, not literal keyword overlap, then sorts fit into honest bands against your background." },
  { q: "Why bands instead of a percentage match?", a: "A two digit score implies a precision the model doesn't have. A “67” reads as measured when it isn't. Strong / Worth a look / Stretch tells you what you actually need to know: how hard to push, and where." },
  { q: "Can I still browse by company type?", a: "Yes. Every role carries a type tag: Big tech, Startup, Near you, or Selective. Chips above the feed cut the list to one type while the band order stays put. Roles near you also get a quiet boost in the ranking, because staying close is sometimes the whole point." },
  { q: "What happens to roles that are not a fit?", a: "They stay on the page. Anything graded not a fit collapses into a labeled row at the bottom of the feed, so you can see what was considered and what was set aside. Shown, not hidden." },
  { q: "Where do the roles come from?", a: "A background worker continuously gathers live postings from company career pages and ATS feeds into an index, then ranks them ahead of time. Your run serves from that index, which is why results land in seconds." },
  { q: "Is it really free?", a: "Core discovery is free for students. Heavier analyzer usage sits behind a generous daily limit once you sign in." },
];

const PREVIEW_ROLES = [
  { band: "strong", logo: "R", alt: false, ti: "Software Engineer Intern", su: "Ramp · New York, NY · Summer 2026", tag: "Startup" },
  { band: "strong", logo: "C", alt: true, ti: "Software Developer Intern", su: "CoverMyMeds · Columbus, OH · 25 min from campus", tag: "Near you" },
  { band: "look", logo: "V", alt: true, ti: "Frontend Infrastructure Intern", su: "Vercel · Remote · Summer 2026", tag: "Startup" },
  { band: "look", logo: "M", alt: false, ti: "Explore Intern, Software Engineering", su: "Microsoft · Redmond, WA · built for underclassmen", tag: "Big tech" },
  { band: "stretch", logo: "P", alt: true, ti: "Backend Intern, Payments", su: "Plaid · San Francisco, CA", tag: "Startup" },
  { band: "stretch", logo: "N", alt: false, ti: "Systems Software Intern", su: "NVIDIA · Santa Clara, CA · two skills away", tag: "Selective" },
];

export function Landing() {
  const revealRef = useReveal<HTMLDivElement>();

  return (
    <div className="lp" id="top" ref={revealRef}>
      {/* shared gradient defs for the marks */}
      <svg width="0" height="0" style={{ position: "absolute" }} aria-hidden>
        <defs>
          <linearGradient id="lm-warm" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#FF8C5A" /><stop offset="1" stopColor="#FFD27A" /></linearGradient>
        </defs>
      </svg>

      {/* ambient bg */}
      <div className="bg-fx" aria-hidden><div className="mesh" /><div className="topo" /><div className="blob b1" /><div className="blob b2" /><div className="blob b3" /></div>

      {/* NAV */}
      <header className="nav">
        <div className="nav-wrap">
          <div className="nav-inner">
            <Link href="/" className="brand">{Mark}<span className="wm">SkyMatch</span></Link>
            <nav className="nav-links" aria-label="Primary">
              <a href="#how">How it works</a>
              <a href="#bands">The three bands</a>
              <a href="#match">A real match</a>
              <a href="#faq">FAQ</a>
            </nav>
            <div className="nav-cta">
              <NavAuth className="signin" />
              <a href="#top" className="btn btn-primary">See your matches <span className="arrow">→</span></a>
            </div>
          </div>
        </div>
      </header>

      <main>
        {/* HERO */}
        <section className="hero">
          <div className="wrap hero-grid">
            <div className="hero-copy">
              <span className="badge-pill lift l1"><span className="ping" /> For CS students</span>
              <h1 className="lift l2">The shortlist that <span className="em-warm">read you right</span>.</h1>
              <p className="lede lift l3">Stop spraying applications into the void. Paste your profile and get one ranked shortlist, strong matches first, honest stretches last, each role carrying the reasoning behind it.</p>
              <div className="try lift l4">
                <div className="try-meta">
                  <span><span className="ck">✓</span> Results in under a minute</span>
                </div>
              </div>
            </div>
            <ProfileInput />
          </div>
        </section>

        {/* TRUST MARQUEE */}
        <div className="trust">
          <div className="wrap"><p className="label">Roles surfaced from where students actually intern</p></div>
          <div className="marquee-mask">
            <div className="marquee">
              {[...MARQUEE, ...MARQUEE].map((c, i) => <span className="co" key={i}>{c}</span>)}
            </div>
          </div>
        </div>

        {/* STAT BAND */}
        <section className="statband">
          <div className="wrap stat-inner">
            <div className="stat reveal"><div className="num">400</div><div className="lab">applications sent by the person who built this</div></div>
            <div className="stat reveal d1"><div className="num hot">3</div><div className="lab">interviews those 400 applications returned</div></div>
            <div className="stat reveal d2"><div className="num">0.75%</div><div className="lab">hit rate. Mass applying is broken, so we built the opposite of it</div></div>
            <p className="stat-line reveal">SkyMatch is not another place to fire off more applications. It is a way to send far fewer, to the roles that were worth it all along.</p>
          </div>
        </section>

        {/* HOW IT WORKS */}
        <section className="section" id="how">
          <div className="wrap">
            <div className="sec-head reveal">
              <span className="eyebrow"><span className="sec-num">01</span> How it works</span>
              <h2>Three steps. No spreadsheet.</h2>
              <p>The setup is paste and go. The work is in what happens after, where your profile gets read the way a sharp friend would read it.</p>
            </div>
            <div className="steps">
              {STEPS.map((s, i) => (
                <article className={`step reveal d${i + 1}`} key={s.n}>
                  <span className="num">{s.n}</span>
                  <div className="ico"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">{s.ico}</svg></div>
                  <h3>{s.h}</h3>
                  <p>{s.p}</p>
                  <span className="line" />
                </article>
              ))}
            </div>
          </div>
        </section>

        {/* THE THREE BANDS */}
        <section className="section" id="bands" style={{ paddingTop: 0 }}>
          <div className="wrap">
            <div className="sec-head reveal">
              <span className="eyebrow"><span className="sec-num">02</span> The three bands</span>
              <h2>One feed, graded honestly.</h2>
              <p>Every role lands in one ranked list, graded by your relationship to the role, not by the logo on the door. Strong matches first. Honest stretches last. Anything that is not a fit is set aside in plain sight, never quietly deleted.</p>
            </div>
            <div className="bands">
              {BANDS.map((b, i) => (
                <div className={`band-card bc-${b.k} reveal${i > 0 ? ` d${i}` : ""}`} key={b.k}>
                  <span className="tag"><span className="sq" /> {b.tag}</span>
                  <h3>{b.h}</h3>
                  <p>{b.p}</p>
                  <div className="count">{b.count}</div>
                </div>
              ))}
            </div>
            <div className="tag-note reveal d3">
              <span className="type-tag">Big tech</span>
              <span className="type-tag">Startup</span>
              <span className="type-tag">Near you</span>
              <span className="type-tag">Selective</span>
              <p>Company type still matters, so every role carries a tag and the feed filters by it. It just stopped being the headline.</p>
            </div>
          </div>
        </section>

        {/* A REAL MATCH */}
        <section className="section" id="match" style={{ paddingTop: 0 }}>
          <div className="wrap showcase">
            <div className="show-copy">
              <div className="sec-head reveal">
                <span className="eyebrow"><span className="sec-num">03</span> A real match</span>
                <h2>Every match shows its work.</h2>
                <p style={{ marginBottom: 0 }}>No mystery score. You see the band, the company type, and the exact reason a role made your list. When something is a stretch, we say so, name the gap, and point at the plan to close it.</p>
              </div>
            </div>
            <div className="show-card reveal d1">
              <div className="mf-top">
                <span className="band-pill band-stretch"><span className="tier stretch"><i /><i /><i /></span> Stretch</span>
                <span className="type-tag">Startup</span>
              </div>
              <h3>Machine Learning Intern</h3>
              <div className="co">Ramp · New York, NY · Summer 2026</div>
              <p className="why">Your two semesters of applied ML and the fraud detection class project map closely to their risk team. <b>The bar is high for a sophomore, but you are about two skills away, not ten.</b> Lead with the project, not the GPA.</p>
              {/* Honest skill split (mirrors the real role drawer's chips) — no percentage bars,
                  matching this page's own "bands, not false precision" principle. */}
              <div className="dr-sub">You already bring</div>
              <div className="dr-skills">
                <span className="req-chip ok">✓ Applied ML</span>
                <span className="req-chip ok">✓ Python</span>
                <span className="req-chip ok">✓ Fraud-detection project</span>
              </div>
              <div className="dr-sub">Worth shoring up</div>
              <div className="dr-skills">
                <span className="req-chip ghosted">Production ML pipelines</span>
                <span className="req-chip ghosted">Distributed systems</span>
              </div>
              <div className="foot"><span className="dot" /> Why this is a stretch, and the plan that closes the gap</div>
            </div>
          </div>
        </section>

        {/* PRODUCT WINDOW */}
        <section className="section" id="preview" style={{ paddingTop: 0 }}>
          <div className="wrap">
            <div className="sec-head reveal">
              <span className="eyebrow"><span className="sec-num">04</span> A look inside</span>
              <h2>Your shortlist, ranked and reasoned.</h2>
              <p>Clean, scannable, honest about fit. Strong matches open the feed, stretches close it, and anything that is not a fit waits in a labeled row at the bottom. Filter by company type without losing the order.</p>
            </div>
            <div className="preview-wrap reveal d1">
              <div className="window">
                <div className="topbar">
                  <div className="dots"><i /><i /><i /></div>
                  <span className="addr">skymatch.app/run</span>
                </div>
                <div className="body">
                  <div className="chips">
                    <span className="chip on">All <span className="cnt">15</span></span>
                    <span className="chip">Big tech <span className="cnt">5</span></span>
                    <span className="chip">Startups <span className="cnt">5</span></span>
                    <span className="chip">Near you <span className="cnt">3</span></span>
                    <span className="chip">Selective <span className="cnt">2</span></span>
                  </div>
                  <div className="roles">
                    {/* Counts sum to the "All 15" chip and reflect a realistic spread across the
                        three bands (post-recalibration the middle bands actually populate). */}
                    <div className="band-head strong"><span>Strong matches</span><span className="rule" /><span className="cnt">3</span></div>
                    {PREVIEW_ROLES.filter((r) => r.band === "strong").map((r, i) => <PreviewRole key={i} {...r} />)}
                    <div className="band-head look"><span>Worth a look</span><span className="rule" /><span className="cnt">5</span></div>
                    {PREVIEW_ROLES.filter((r) => r.band === "look").map((r, i) => <PreviewRole key={i} {...r} />)}
                    <div className="band-head stretch"><span>Stretch</span><span className="rule" /><span className="cnt">2</span></div>
                    {PREVIEW_ROLES.filter((r) => r.band === "stretch").map((r, i) => <PreviewRole key={i} {...r} />)}
                    <div className="notfit"><span>Not a fit right now · 5 roles</span><span className="hint">graded, not hidden</span></div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* PRINCIPLES */}
        <section className="section" id="why" style={{ paddingTop: 0 }}>
          <div className="wrap">
            <div className="sec-head reveal">
              <span className="eyebrow"><span className="sec-num">05</span> The bias we built in</span>
              <h2>No mystery scores. No inflated odds.</h2>
              <p>Made by someone who sent 400 applications and got three interviews. The whole product is an argument against doing that.</p>
            </div>
            <div className="principles">
              {PRINCIPLES.map((p, i) => (
                <div className={`pr reveal${i > 0 ? ` d${i}` : ""}`} key={p.n}><div className="n">{p.n}</div><h3>{p.h}</h3><p>{p.p}</p></div>
              ))}
            </div>
          </div>
        </section>

        {/* FAQ */}
        <section className="section" id="faq" style={{ paddingTop: 0 }}>
          <div className="wrap">
            <div className="sec-head reveal">
              <span className="eyebrow"><span className="sec-num">06</span> Questions</span>
              <h2>Good to know.</h2>
            </div>
            <div className="faq reveal d1">
              {FAQ.map((f, i) => (
                <details key={i} open={i === 0}>
                  <summary>{f.q} <span className="pm" /></summary>
                  <div className="ans">{f.a}</div>
                </details>
              ))}
            </div>
          </div>
        </section>

        {/* FINAL CTA */}
        <section className="section" id="start" style={{ paddingTop: 0 }}>
          <div className="wrap">
            <div className="cta-band lg reveal">
              <div className="glow" />
              <div className="dia-big" aria-hidden />
              <span className="eyebrow" style={{ justifyContent: "center" }}>Start in 30 seconds</span>
              <h2 style={{ marginTop: 16 }}>Find the fifteen that fit.</h2>
              <p>Paste your profile and read the reasoning on every role, before you spend a single application.</p>
              <div className="hero-cta">
                <a href="#top" className="btn btn-primary">See your matches <span className="arrow">→</span></a>
                <a href="#how" className="btn btn-ghost">How it works</a>
              </div>
            </div>
          </div>
        </section>
      </main>

      {/* FOOTER (rich, option-j) */}
      <footer className="site-foot">
        <div className="wrap">
          <div className="foot-grid">
            <div className="about">
              <Link href="/" className="brand">{Mark}<span className="wm">SkyMatch</span></Link>
              <p>The shortlist, not the spray. Career discovery for underclassmen who are done firing applications into the void.</p>
            </div>
            <div className="fcol"><h4>Product</h4><a href="#how">How it works</a><a href="#bands">The three bands</a><a href="#match">A real match</a><Link href="/analyze">Job fit analyzer</Link></div>
            <div className="fcol"><h4>Company</h4><a href="#why">Why it works</a><a href="#start">The 400 story</a><a href="#faq">Contact</a></div>
            <div className="fcol"><h4>Legal</h4><Link href="/privacy">Privacy</Link><Link href="/terms">Terms</Link><Link href="/account">Delete account</Link></div>
          </div>
          <div className="foot-bot">
            <p>© 2026 SkyMatch</p>
          </div>
        </div>
      </footer>
    </div>
  );
}

function PreviewRole({ logo, alt, ti, su, tag, band }: { logo: string; alt: boolean; ti: string; su: string; tag: string; band: string }) {
  return (
    <div className="role">
      <div className={`logo${alt ? " alt" : ""}`}>{logo}</div>
      <div className="meta"><div className="ti">{ti}</div><div className="su">{su} <span className="type-tag">{tag}</span></div></div>
      <div className="verdict"><span className={`tier ${band}`}><i /><i /><i /></span></div>
    </div>
  );
}
