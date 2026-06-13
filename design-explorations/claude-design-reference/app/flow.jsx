/* ============================================================
   SkyMatch — full-screen flows: Auth, Paste-profile, Analyzing
   ============================================================ */
const { useState: useStateFl, useEffect: useEffectFl } = React;

/* shared split-screen shell with aurora art panel */
function SplitShell({ children }) {
  return (
    <div style={{ position:"relative", zIndex:2, height:"100%", display:"grid", gridTemplateColumns:"1.05fr 1fr" }}>
      <div className="auth-art" style={{ position:"relative", overflow:"hidden", borderRight:"1px solid var(--line)" }}>
        <div className="blob ab1"/><div className="blob ab2"/><div className="blob ab3"/>
        <div style={{ position:"absolute", inset:0, padding:"48px 56px", display:"flex", flexDirection:"column", justifyContent:"space-between", zIndex:2 }}>
          <Logo size={32} wordmarkSize={23}/>
          <div>
            <span className="eyebrow" style={{ marginBottom:18, display:"inline-flex" }}>Career discovery, scored</span>
            <h1 style={{ fontSize:"clamp(34px,3.6vw,52px)", letterSpacing:"-.035em", lineHeight:1.02, maxWidth:520 }}>
              The internship that was <span style={{ background:"var(--aurora)", WebkitBackgroundClip:"text", backgroundClip:"text", color:"transparent" }}>looking for you.</span>
            </h1>
            <p style={{ color:"var(--muted)", fontSize:17, marginTop:22, maxWidth:430, lineHeight:1.55 }}>
              Paste a profile, and SkyMatch reads your real trajectory — then surfaces matched roles across startups, big tech, local, and reach.
            </p>
            <div style={{ display:"flex", gap:22, marginTop:30, flexWrap:"wrap", fontFamily:"var(--mono)", fontSize:12.5, color:"var(--faint)" }}>
              <span style={{ display:"inline-flex", alignItems:"center", gap:8 }}><i style={{ width:5, height:5, borderRadius:"50%", background:"var(--mint)", boxShadow:"0 0 10px var(--glow-mint)" }}/> No account needed</span>
              <span style={{ display:"inline-flex", alignItems:"center", gap:8 }}><i style={{ width:5, height:5, borderRadius:"50%", background:"var(--cyan)" }}/> Matches in ~30s</span>
            </div>
          </div>
          <div style={{ fontFamily:"var(--mono)", fontSize:11.5, color:"var(--faint)" }}>© 2026 SkyMatch · Free for students</div>
        </div>
      </div>
      <div className="scroll" style={{ display:"grid", placeItems:"center", padding:"40px" }}>{children}</div>
      <style>{`
        .auth-art{background:linear-gradient(160deg,var(--surface),var(--bg-2))}
        .auth-art .blob{position:absolute;border-radius:50%;filter:blur(70px)}
        .auth-art .ab1{width:440px;height:440px;right:-80px;top:-120px;background:radial-gradient(circle,var(--cyan),transparent 65%);opacity:.22}
        .auth-art .ab2{width:380px;height:380px;left:-120px;bottom:-80px;background:radial-gradient(circle,var(--mint),transparent 65%);opacity:.18}
        .auth-art .ab3{width:360px;height:360px;left:40%;top:40%;background:radial-gradient(circle,var(--iris),transparent 65%);opacity:.14}
        @media(max-width:880px){.auth-art{display:none}}
      `}</style>
    </div>
  );
}

function Auth() {
  const app = useApp();
  const mode = app.route==="auth-signup" ? "signup" : "signin";
  const isUp = mode==="signup";
  const [email, setEmail] = useStateFl("maya.chen@berkeley.edu");
  return (
    <SplitShell>
      <div className="fade-up" style={{ width:"min(380px,100%)" }}>
        <h2 style={{ fontSize:28, letterSpacing:"-.02em" }}>{isUp?"Create your account":"Welcome back"}</h2>
        <p style={{ color:"var(--muted)", fontSize:14.5, marginTop:8 }}>{isUp?"Save runs across devices and unlock the deeper analyzer.":"Sign in to pick up where you left off."}</p>

        <div style={{ display:"flex", flexDirection:"column", gap:10, margin:"26px 0 18px" }}>
          <button className="btn btn-ghost" style={{ width:"100%", justifyContent:"flex-start", gap:12, height:48 }} onClick={()=>app.go("app")}>
            <span style={{ fontFamily:"var(--display)", fontWeight:700, fontSize:17, width:20, textAlign:"center" }}>G</span> Continue with Google
          </button>
          <button className="btn btn-ghost" style={{ width:"100%", justifyContent:"flex-start", gap:12, height:48 }} onClick={()=>app.go("app")}>
            <span style={{ width:20, textAlign:"center" }}><Icon name="building" size={17}/></span> Continue with university SSO
          </button>
        </div>

        <div style={{ display:"flex", alignItems:"center", gap:12, margin:"6px 0 18px", color:"var(--faint)", fontSize:12, fontFamily:"var(--mono)" }}>
          <span style={{ flex:1, height:1, background:"var(--line)" }}/> OR <span style={{ flex:1, height:1, background:"var(--line)" }}/>
        </div>

        {isUp && (<div style={{ marginBottom:14 }}><label className="label">Full name</label><input className="field" defaultValue="Maya Chen"/></div>)}
        <div style={{ marginBottom:14 }}><label className="label">Email</label><input className="field" value={email} onChange={e=>setEmail(e.target.value)} placeholder="you@school.edu"/></div>
        <div style={{ marginBottom:20 }}><label className="label">Password</label><input className="field" type="password" defaultValue="············"/></div>

        <button className="btn btn-primary" style={{ width:"100%" }} onClick={()=>app.go(isUp?"input":"app")}>
          {isUp?"Create account":"Sign in"} <span className="arrow"><Icon name="arrowRight" size={16}/></span>
        </button>

        <div style={{ textAlign:"center", marginTop:20, fontSize:13.5, color:"var(--muted)" }}>
          {isUp?"Already have an account? ":"New to SkyMatch? "}
          <button onClick={()=>app.go(isUp?"auth-signin":"auth-signup")} style={{ color:"var(--accent)", background:"none", border:"none", fontSize:13.5, fontWeight:600 }}>{isUp?"Sign in":"Create one"}</button>
        </div>
        <div style={{ textAlign:"center", marginTop:18 }}>
          <button onClick={()=>app.go("app")} style={{ color:"var(--faint)", background:"none", border:"none", fontSize:13, display:"inline-flex", alignItems:"center", gap:6 }}>Skip — explore anonymously <Icon name="arrowRight" size={14}/></button>
        </div>
      </div>
    </SplitShell>
  );
}

/* ---------------- Paste profile ---------------- */
function InputFlow() {
  const app = useApp();
  const [val, setVal] = useStateFl("linkedin.com/in/maya-chen");
  const [tab, setTab] = useStateFl("linkedin");
  const tabs = [["linkedin","LinkedIn URL","link"],["paste","Paste text","doc"],["resume","Upload résumé","briefcase"]];
  return (
    <SplitShell>
      <div className="fade-up" style={{ width:"min(440px,100%)" }}>
        <span className="eyebrow" style={{ marginBottom:14, display:"inline-flex" }}>Step 1 of 1</span>
        <h2 style={{ fontSize:30, letterSpacing:"-.025em" }}>Let's find your matches</h2>
        <p style={{ color:"var(--muted)", fontSize:15, marginTop:10 }}>Drop in your profile — that's the whole input. Nothing to fill out.</p>

        <div style={{ display:"flex", gap:6, margin:"24px 0 16px", background:"var(--surface-2)", border:"1px solid var(--line-2)", borderRadius:12, padding:4 }}>
          {tabs.map(([k,l,ic])=>(
            <button key={k} onClick={()=>setTab(k)} style={{ flex:1, display:"flex", alignItems:"center", justifyContent:"center", gap:7, padding:"9px 8px", borderRadius:8, border:"none", fontSize:12.5, fontWeight:500,
              background: tab===k?"var(--accent-weak)":"transparent", color: tab===k?"var(--accent)":"var(--muted)" }}>
              <Icon name={ic} size={15}/> {l}
            </button>
          ))}
        </div>

        {tab==="linkedin" && (
          <div>
            <label className="label">LinkedIn profile URL</label>
            <div style={{ position:"relative" }}>
              <Icon name="link" size={16} style={{ position:"absolute", left:14, top:15, color:"var(--faint)" }}/>
              <input className="field" value={val} onChange={e=>setVal(e.target.value)} style={{ paddingLeft:40 }} placeholder="linkedin.com/in/you"/>
            </div>
          </div>
        )}
        {tab==="paste" && (
          <div>
            <label className="label">Paste your experience</label>
            <textarea className="field" placeholder="Paste your résumé text, bio, or experience here…" defaultValue={window.SM_DATA.PROFILE.summary}/>
          </div>
        )}
        {tab==="resume" && (
          <label style={{ display:"block", border:"1.5px dashed var(--line-3)", borderRadius:14, padding:"34px 20px", textAlign:"center", cursor:"pointer", background:"var(--surface-2)" }}>
            <Icon name="briefcase" size={26} style={{ color:"var(--accent)" }}/>
            <div style={{ fontSize:14, fontWeight:600, marginTop:12 }}>Drop your résumé here</div>
            <div style={{ fontSize:12.5, color:"var(--faint)", marginTop:4 }}>PDF or DOCX · or click to browse</div>
            <input type="file" style={{ display:"none" }}/>
          </label>
        )}

        <div style={{ display:"flex", gap:10, marginTop:22 }}>
          <button className="btn btn-primary" style={{ flex:1 }} onClick={()=>app.go("analyzing")}>
            <Icon name="sparkle" size={16}/> Find my matches
          </button>
          {app.hasRun && <button className="btn btn-ghost" onClick={()=>app.go("app")}>Cancel</button>}
        </div>

        <div style={{ display:"flex", gap:16, marginTop:22, flexWrap:"wrap", fontSize:12, color:"var(--faint)" }}>
          <span style={{ display:"inline-flex", alignItems:"center", gap:6 }}><Icon name="shield" size={14}/> Private — nothing stored without an account</span>
        </div>
      </div>
    </SplitShell>
  );
}

/* ---------------- Analyzing / matching loader ---------------- */
function Analyzing() {
  const app = useApp();
  const steps = [
    { t:"Reading your profile", d:"Parsing experience, skills & trajectory" },
    { t:"Building your field vector", d:"Mapping you across 6 dimensions" },
    { t:"Searching the index", d:"Scanning 12,400 live internship postings" },
    { t:"Scoring fit", d:"Ranking roles against your background" },
    { t:"Sorting into buckets", d:"Startup · Big Tech · Local · Reach" },
  ];
  const [i, setI] = useStateFl(0);
  useEffectFl(()=>{
    if(i>=steps.length){ const t=setTimeout(()=>app.finishRun(), 500); return ()=>clearTimeout(t); }
    const t=setTimeout(()=>setI(v=>v+1), i===0?700:640); return ()=>clearTimeout(t);
  }, [i]);
  const pct = Math.min(100, Math.round(i/steps.length*100));

  return (
    <div style={{ position:"relative", zIndex:2, height:"100%", display:"grid", placeItems:"center", padding:30 }}>
      <div style={{ width:"min(460px,100%)", textAlign:"center" }}>
        {/* radar sweep */}
        <div style={{ position:"relative", width:150, height:150, margin:"0 auto 36px" }}>
          {[1,2,3].map(r=><span key={r} className="an-ring" style={{ position:"absolute", inset:0, margin:"auto", width:50*r, height:50*r, border:"1px solid var(--accent-line)", borderRadius:"50%", opacity:1-(r-1)*0.28 }}/>)}
          <span className="an-sweep" style={{ position:"absolute", inset:0, borderRadius:"50%", background:"conic-gradient(from 0deg, transparent 0deg, var(--accent-weak) 40deg, transparent 80deg)" }}/>
          <span style={{ position:"absolute", inset:0, margin:"auto", width:14, height:14, borderRadius:"50%", background:"var(--accent)", boxShadow:"0 0 20px var(--accent-glow)" }}/>
        </div>

        <h2 style={{ fontSize:26, letterSpacing:"-.02em" }}>{i<steps.length?steps[i].t:"Done"}</h2>
        <p style={{ color:"var(--muted)", fontSize:14.5, marginTop:8, minHeight:22 }}>{i<steps.length?steps[i].d:"Opening your matches…"}</p>

        <div style={{ height:5, borderRadius:99, background:"var(--line-2)", overflow:"hidden", margin:"26px auto 0", maxWidth:300 }}>
          <div style={{ height:"100%", width:`${pct}%`, background:"var(--aurora)", transition:"width .5s var(--ease)" }}/>
        </div>
        <div style={{ marginTop:14, fontFamily:"var(--mono)", fontSize:11.5, color:"var(--faint)", letterSpacing:".08em" }}>{pct}% · scanning index</div>
      </div>
      <style>{`
        @keyframes anpulse{0%,100%{transform:scale(1);opacity:.7}50%{transform:scale(1.06);opacity:1}}
        .an-ring{animation:anpulse 2s ease-in-out infinite}
        .an-ring:nth-child(2){animation-delay:.3s}.an-ring:nth-child(3){animation-delay:.6s}
        @keyframes answeep{to{transform:rotate(360deg)}}
        .an-sweep{animation:answeep 1.6s linear infinite}
      `}</style>
    </div>
  );
}

Object.assign(window, { Auth, InputFlow, Analyzing });
