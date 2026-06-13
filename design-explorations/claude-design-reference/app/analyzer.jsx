/* ============================================================
   SkyMatch — Job-fit analyzer
   Input -> analyzing -> verdict + gaps + 30-day plan
   ============================================================ */
const { useState: useStateAz, useEffect: useEffectAz } = React;

function GapMap({ haves, gaps }) {
  const sevColor = { minor:"var(--gold)", moderate:"var(--coral)" };
  return (
    <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:16 }}>
      <div className="panel" style={{ padding:"20px 22px" }}>
        <div style={{ display:"flex", alignItems:"center", gap:8, marginBottom:16 }}>
          <span style={{ width:26, height:26, borderRadius:8, display:"grid", placeItems:"center", background:"var(--accent-weak)", color:"var(--accent)" }}><Icon name="check" size={15} stroke={2.3}/></span>
          <h3 style={{ fontSize:16 }}>You already have</h3>
        </div>
        <div style={{ display:"flex", flexDirection:"column", gap:13 }}>
          {haves.map((h,i)=>(
            <div key={i}>
              <div style={{ fontSize:14, fontWeight:600, color:"var(--text)" }}>{h.k}</div>
              <div style={{ fontSize:12.5, color:"var(--muted)", marginTop:2 }}>{h.note}</div>
            </div>
          ))}
        </div>
      </div>
      <div className="panel" style={{ padding:"20px 22px" }}>
        <div style={{ display:"flex", alignItems:"center", gap:8, marginBottom:16 }}>
          <span style={{ width:26, height:26, borderRadius:8, display:"grid", placeItems:"center", background:"rgba(255,158,138,.12)", color:"var(--coral)" }}><Icon name="flag" size={14} stroke={2}/></span>
          <h3 style={{ fontSize:16 }}>Gaps to close</h3>
        </div>
        <div style={{ display:"flex", flexDirection:"column", gap:13 }}>
          {gaps.map((g,i)=>(
            <div key={i}>
              <div style={{ display:"flex", alignItems:"center", gap:9 }}>
                <span style={{ fontSize:14, fontWeight:600, color:"var(--text)" }}>{g.k}</span>
                <span style={{ fontFamily:"var(--mono)", fontSize:9.5, textTransform:"uppercase", letterSpacing:".1em", color:sevColor[g.sev], border:`1px solid ${sevColor[g.sev]}40`, padding:"2px 7px", borderRadius:99 }}>{g.sev}</span>
              </div>
              <div style={{ fontSize:12.5, color:"var(--muted)", marginTop:3 }}>{g.note}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function Plan({ plan }) {
  const [done, setDone] = useStateAz(plan.map(p=>p.done));
  const pct = Math.round(done.filter(Boolean).length/done.length*100);
  return (
    <div className="panel" style={{ padding:"22px 24px" }}>
      <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", marginBottom:18 }}>
        <div style={{ display:"flex", alignItems:"center", gap:10 }}>
          <span style={{ width:30, height:30, borderRadius:9, display:"grid", placeItems:"center", background:"var(--accent-weak)", color:"var(--accent)" }}><Icon name="rocket" size={17}/></span>
          <h3 style={{ fontSize:18 }}>Your 30-day plan to close the gap</h3>
        </div>
        <span style={{ fontFamily:"var(--mono)", fontSize:12, color:"var(--accent)" }}>{pct}% done</span>
      </div>
      <div style={{ height:5, borderRadius:99, background:"var(--line-2)", overflow:"hidden", marginBottom:20 }}>
        <div style={{ height:"100%", width:`${pct}%`, background:"var(--aurora)", transition:"width .4s var(--ease)" }}/>
      </div>
      <div style={{ display:"flex", flexDirection:"column", gap:10 }}>
        {plan.map((p,i)=>(
          <button key={i} onClick={()=>setDone(d=>d.map((x,j)=>j===i?!x:x))} style={{
            display:"flex", alignItems:"center", gap:14, padding:"14px 16px", borderRadius:12, textAlign:"left", width:"100%",
            border:"1px solid var(--line)", background: done[i]?"var(--accent-weak)":"var(--surface-2)", transition:"all .2s" }}>
            <span style={{ flex:"none", width:24, height:24, borderRadius:"50%", display:"grid", placeItems:"center",
              border: done[i]?"none":"1.5px solid var(--line-3)", background: done[i]?"var(--accent)":"transparent", color:"var(--accent-ink)" }}>
              {done[i] && <Icon name="check" size={14} stroke={2.6}/>}
            </span>
            <div style={{ flex:1 }}>
              <span style={{ fontFamily:"var(--mono)", fontSize:10.5, color:"var(--faint)", textTransform:"uppercase", letterSpacing:".1em" }}>{p.wk}</span>
              <div style={{ fontSize:14, color: done[i]?"var(--muted)":"var(--text)", marginTop:3, textDecoration: done[i]?"line-through":"none" }}>{p.task}</div>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

function AnalyzerInput({ onAnalyze, presetUrl }) {
  const [val, setVal] = useStateAz(presetUrl || "");
  const samples = ["Stripe — SWE Intern, Payments","Figma — Multiplayer Intern","Notion — Backend Intern"];
  return (
    <div className="scroll" style={{ flex:1, display:"grid", placeItems:"center", padding:"30px" }}>
      <div className="fade-up" style={{ width:"min(680px,100%)" }}>
        <div style={{ textAlign:"center", marginBottom:30 }}>
          <span style={{ display:"inline-grid", placeItems:"center", width:60, height:60, borderRadius:16, background:"var(--accent-weak)", border:"1px solid var(--accent-line)", color:"var(--accent)", marginBottom:18 }}>
            <Icon name="target" size={28}/>
          </span>
          <h1 style={{ fontSize:34, letterSpacing:"-.03em" }}>Analyze any job posting</h1>
          <p style={{ color:"var(--muted)", fontSize:16, marginTop:12, maxWidth:440, marginInline:"auto" }}>
            Paste a link or the full description. We'll score your fit, map the gaps, and build a plan to close them.
          </p>
        </div>
        <div className="panel" style={{ padding:22 }}>
          <label className="label">Job URL or pasted description</label>
          <textarea className="field" value={val} onChange={e=>setVal(e.target.value)} placeholder="https://stripe.com/jobs/...  — or paste the full posting text here" style={{ minHeight:120 }}/>
          <div style={{ display:"flex", alignItems:"center", gap:12, marginTop:16, flexWrap:"wrap" }}>
            <button className="btn btn-primary" disabled={!val.trim()} onClick={()=>onAnalyze(val)}><Icon name="sparkle" size={16}/> Analyze fit</button>
            <span style={{ fontSize:12.5, color:"var(--faint)", fontFamily:"var(--mono)" }}>· scored against {window.SM_DATA.PROFILE.name}'s profile</span>
          </div>
        </div>
        <div style={{ marginTop:22, textAlign:"center" }}>
          <div style={{ fontSize:12, color:"var(--faint)", fontFamily:"var(--mono)", textTransform:"uppercase", letterSpacing:".1em", marginBottom:12 }}>Or try a recent posting</div>
          <div style={{ display:"flex", gap:10, justifyContent:"center", flexWrap:"wrap" }}>
            {samples.map(s=><button key={s} className="chip" onClick={()=>onAnalyze(s)}><Icon name="doc" size={13}/>{s}</button>)}
          </div>
        </div>
      </div>
    </div>
  );
}

function AnalyzerLoading() {
  const steps = ["Parsing the posting","Extracting required skills","Comparing to your profile","Scoring fit & mapping gaps","Drafting your 30-day plan"];
  const [i, setI] = useStateAz(0);
  useEffectAz(()=>{ const t=setInterval(()=>setI(v=>Math.min(v+1,steps.length-1)), 520); return ()=>clearInterval(t); }, []);
  return (
    <div style={{ flex:1, display:"grid", placeItems:"center", padding:30 }}>
      <div style={{ width:"min(420px,100%)" }}>
        <div style={{ display:"grid", placeItems:"center", marginBottom:28 }}>
          <span className="az-spin" style={{ width:54, height:54, borderRadius:"50%", border:"3px solid var(--line-2)", borderTopColor:"var(--accent)", display:"block" }}/>
        </div>
        <div style={{ display:"flex", flexDirection:"column", gap:11 }}>
          {steps.map((s,j)=>(
            <div key={j} style={{ display:"flex", alignItems:"center", gap:12, opacity: j<=i?1:.35, transition:"opacity .3s" }}>
              <span style={{ flex:"none", width:22, height:22, borderRadius:"50%", display:"grid", placeItems:"center",
                background: j<i?"var(--accent)":"transparent", border: j<i?"none":"1.5px solid var(--line-3)", color:"var(--accent-ink)" }}>
                {j<i ? <Icon name="check" size={13} stroke={2.6}/> : j===i ? <span className="az-pulse" style={{ width:7, height:7, borderRadius:"50%", background:"var(--accent)" }}/> : null}
              </span>
              <span style={{ fontSize:14, color: j<=i?"var(--text)":"var(--faint)" }}>{s}</span>
            </div>
          ))}
        </div>
      </div>
      <style>{`@keyframes azspin{to{transform:rotate(360deg)}} .az-spin{animation:azspin .9s linear infinite} @keyframes azpulse{0%,100%{opacity:1}50%{opacity:.3}} .az-pulse{animation:azpulse 1s ease-in-out infinite}`}</style>
    </div>
  );
}

function AnalyzerResult({ data, onReset }) {
  return (
    <div className="scroll" style={{ flex:1, padding:"24px 28px 40px" }}>
      <div className="fade-up" style={{ maxWidth:980, margin:"0 auto", display:"flex", flexDirection:"column", gap:18 }}>
        {/* verdict header */}
        <div className="panel" style={{ padding:"26px 28px", display:"flex", gap:22, alignItems:"center", flexWrap:"wrap", position:"relative", overflow:"hidden" }}>
          <div style={{ position:"absolute", inset:0, background:"radial-gradient(60% 120% at 88% -20%, var(--accent-weak), transparent 60%)", pointerEvents:"none" }}/>
          <FitRing score={data.score} size={92} stroke={7}/>
          <div style={{ flex:1, minWidth:240, position:"relative" }}>
            <div style={{ display:"flex", alignItems:"center", gap:10, marginBottom:8 }}>
              <h1 style={{ fontSize:26, letterSpacing:"-.02em" }}>{data.verdict}</h1>
              <TierBadge score={data.score}/>
            </div>
            <div style={{ fontFamily:"var(--mono)", fontSize:13, color:"var(--muted)", marginBottom:10 }}>{data.company} · {data.title}</div>
            <p style={{ fontSize:14.5, color:"var(--text)", lineHeight:1.55, maxWidth:600 }}>{data.summary}</p>
          </div>
          <button onClick={onReset} className="btn btn-ghost btn-sm"><Icon name="refresh" size={15}/> New analysis</button>
        </div>
        <GapMap haves={data.haves} gaps={data.gaps}/>
        <Plan plan={data.plan}/>
      </div>
    </div>
  );
}

function Analyzer() {
  const app = useApp();
  const [phase, setPhase] = useStateAz(app.analyzerSeed ? "loading" : "input");
  const data = window.SM_DATA.ANALYZER_SAMPLE;

  useEffectAz(()=>{
    if(app.analyzerSeed){ setPhase("loading"); app.clearAnalyzerSeed(); }
  }, [app.analyzerSeed]);

  useEffectAz(()=>{
    if(phase==="loading"){ const t=setTimeout(()=>setPhase("result"), 2700); return ()=>clearTimeout(t); }
  }, [phase]);

  return (
    <>
      <Topbar title="Job-fit analyzer" subtitle="Paste any posting — get a verdict, a gap map, and a plan">
        {phase==="result" && <button onClick={()=>setPhase("input")} className="btn btn-ghost btn-sm"><Icon name="plus" size={15}/> New</button>}
      </Topbar>
      {phase==="input" && <AnalyzerInput presetUrl={app.analyzerPreset} onAnalyze={()=>setPhase("loading")}/>}
      {phase==="loading" && <AnalyzerLoading/>}
      {phase==="result" && <AnalyzerResult data={data} onReset={()=>setPhase("input")}/>}
    </>
  );
}

Object.assign(window, { Analyzer });
