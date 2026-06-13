/* ============================================================
   SkyMatch — Dashboard (matches across 4 buckets)
   List view + column (kanban) view toggle.
   ============================================================ */
const { useState: useStateDash, useMemo: useMemoDash } = React;

function StatStrip() {
  const roles = window.SM_DATA.ROLES;
  const avg = Math.round(roles.reduce((a,r)=>a+r.score,0)/roles.length);
  const strong = roles.filter(r=>r.score>=80).length;
  const top = [...roles].sort((a,b)=>b.score-a.score)[0];
  const stats = [
    { label:"Roles matched", val:roles.length, icon:"compass" },
    { label:"Strong fits", val:strong, icon:"trending", accent:true },
    { label:"Avg fit score", val:avg, icon:"chart" },
    { label:"Top match", val:`${top.score} · ${top.company}`, icon:"star", small:true },
  ];
  return (
    <div className="stagger" style={{ display:"grid", gridTemplateColumns:"repeat(4,1fr)", gap:14, marginBottom:22 }}>
      {stats.map((s,i)=>(
        <div key={i} className="panel" style={{ padding:"16px 18px" }}>
          <div style={{ display:"flex", alignItems:"center", gap:8, color:"var(--faint)", marginBottom:10 }}>
            <Icon name={s.icon} size={16} style={{ color: s.accent?"var(--accent)":"var(--faint)" }}/>
            <span style={{ fontFamily:"var(--mono)", fontSize:10.5, textTransform:"uppercase", letterSpacing:".1em" }}>{s.label}</span>
          </div>
          <div style={{ fontFamily:"var(--display)", fontWeight:600, fontSize: s.small?18:30, letterSpacing:"-.02em", color: s.accent?"var(--accent)":"var(--text)" }}>{s.val}</div>
        </div>
      ))}
    </div>
  );
}

function BucketTabs({ active, onChange, counts }) {
  const order = ["all","startup","bigtech","local","reach"];
  return (
    <div style={{ display:"flex", gap:8, flexWrap:"wrap" }}>
      {order.map(k=>{
        const meta = k==="all" ? { label:"All", dot:null } : BUCKETS[k];
        const on = active===k;
        return (
          <button key={k} onClick={()=>onChange(k)} className="chip" style={{
            height:38, padding:"0 16px", fontSize:13.5,
            borderColor: on?"var(--accent-line)":"var(--line-2)", background: on?"var(--accent-weak)":"rgba(255,255,255,.025)",
            color: on?"var(--text)":"var(--muted)",
          }}>
            {meta.dot && <i className={meta.dot}/>}
            {meta.label}
            <span style={{ fontFamily:"var(--mono)", fontSize:11, color: on?"var(--accent)":"var(--faint)" }}>{counts[k]}</span>
          </button>
        );
      })}
    </div>
  );
}

function ListView({ roles }) {
  const app = useApp();
  if(!roles.length) return <Empty/>;
  return (
    <div className="stagger" style={{ display:"flex", flexDirection:"column", gap:12 }}>
      {roles.map(r=><RoleCard key={r.id} role={r} onOpen={app.setOpenRole}/>)}
    </div>
  );
}

function ColumnsView({ rolesByBucket }) {
  const app = useApp();
  const order = ["startup","bigtech","local","reach"];
  return (
    <div className="scroll" style={{ display:"grid", gridTemplateColumns:"repeat(4,minmax(260px,1fr))", gap:16, overflowX:"auto", paddingBottom:8 }}>
      {order.map(k=>{
        const b = BUCKETS[k];
        const list = rolesByBucket[k]||[];
        return (
          <div key={k} style={{ display:"flex", flexDirection:"column", minWidth:0 }}>
            <div style={{ display:"flex", alignItems:"center", gap:9, padding:"0 4px 14px" }}>
              <span style={{ width:30, height:30, borderRadius:9, display:"grid", placeItems:"center", background:"var(--surface-2)", border:"1px solid var(--line-2)", color:b.hue }}>
                <Icon name={b.icon} size={16}/>
              </span>
              <span style={{ fontWeight:600, fontSize:14.5 }}>{b.label}</span>
              <span style={{ fontFamily:"var(--mono)", fontSize:11.5, color:"var(--faint)" }}>{list.length}</span>
            </div>
            <div className="stagger" style={{ display:"flex", flexDirection:"column", gap:10 }}>
              {list.map(r=>(
                <article key={r.id} onClick={()=>app.setOpenRole(r.id)} className="panel-flat" style={{ padding:14, cursor:"pointer", transition:"transform .2s, border-color .2s" }}
                  onMouseEnter={e=>{ e.currentTarget.style.transform="translateY(-2px)"; e.currentTarget.style.borderColor="var(--line-3)"; }}
                  onMouseLeave={e=>{ e.currentTarget.style.transform=""; e.currentTarget.style.borderColor="var(--line)"; }}>
                  <div style={{ display:"flex", justifyContent:"space-between", alignItems:"flex-start", gap:10, marginBottom:10 }}>
                    <CompanyTile initial={r.initial} alt={r.score<70} size={36} radius={10}/>
                    <FitRing score={r.score} size={42} stroke={4} showLabel/>
                  </div>
                  <div style={{ fontWeight:600, fontSize:14, letterSpacing:"-.01em", lineHeight:1.25 }}>{r.title}</div>
                  <div style={{ fontFamily:"var(--mono)", fontSize:11.5, color:"var(--muted)", marginTop:5 }}>{r.company}</div>
                  <div style={{ fontFamily:"var(--mono)", fontSize:11, color:"var(--faint)", marginTop:3 }}>{r.location}</div>
                </article>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function Empty() {
  return (
    <div style={{ padding:"60px 20px", textAlign:"center", color:"var(--faint)" }}>
      <Icon name="search" size={28} style={{ opacity:.5 }}/>
      <div style={{ marginTop:12, fontSize:14 }}>No roles in this view yet.</div>
    </div>
  );
}

function Dashboard() {
  const app = useApp();
  const [bucket, setBucket] = useStateDash("all");
  const [sort, setSort] = useStateDash("fit");
  const [q, setQ] = useStateDash("");
  const roles = window.SM_DATA.ROLES;

  const counts = useMemoDash(()=>{
    const c = { all:roles.length, startup:0, bigtech:0, local:0, reach:0 };
    roles.forEach(r=>c[r.bucket]++);
    return c;
  }, [roles]);

  const filtered = useMemoDash(()=>{
    let list = roles;
    if(bucket!=="all") list = list.filter(r=>r.bucket===bucket);
    if(q.trim()){ const s=q.toLowerCase(); list = list.filter(r=>(r.title+r.company+r.location+r.matched.join(" ")).toLowerCase().includes(s)); }
    list = [...list].sort((a,b)=> sort==="fit" ? b.score-a.score : (parseInt(a.posted)-parseInt(b.posted)));
    return list;
  }, [roles, bucket, q, sort]);

  const byBucket = useMemoDash(()=>{
    const g = { startup:[], bigtech:[], local:[], reach:[] };
    filtered.forEach(r=>g[r.bucket]?.push(r));
    return g;
  }, [filtered]);

  return (
    <>
      <Topbar title="Your matches" subtitle={`${counts.all} roles ranked to ${window.SM_DATA.PROFILE.name.split(" ")[0]}'s profile · refreshed today`}>
        <div style={{ position:"relative", width:240 }}>
          <Icon name="search" size={16} style={{ position:"absolute", left:13, top:"50%", transform:"translateY(-50%)", color:"var(--faint)" }}/>
          <input className="field" value={q} onChange={e=>setQ(e.target.value)} placeholder="Search roles, skills…" style={{ padding:"10px 13px 10px 36px", fontSize:13.5, height:42 }}/>
        </div>
      </Topbar>

      <div className="scroll" style={{ flex:1, padding:"24px 28px 40px" }}>
        <StatStrip/>

        <div style={{ display:"flex", alignItems:"center", gap:14, marginBottom:20, flexWrap:"wrap" }}>
          <BucketTabs active={bucket} onChange={setBucket} counts={counts}/>
          <div style={{ flex:1 }}/>
          {/* sort */}
          <div style={{ display:"flex", alignItems:"center", gap:8 }}>
            <span style={{ fontSize:12, color:"var(--faint)", fontFamily:"var(--mono)", textTransform:"uppercase", letterSpacing:".08em" }}>Sort</span>
            <div style={{ display:"flex", background:"var(--surface-2)", border:"1px solid var(--line-2)", borderRadius:10, padding:3 }}>
              {[["fit","Best fit"],["recent","Newest"]].map(([k,l])=>(
                <button key={k} onClick={()=>setSort(k)} style={{ padding:"6px 12px", borderRadius:7, border:"none", fontSize:12.5, fontWeight:500,
                  background: sort===k?"var(--accent-weak)":"transparent", color: sort===k?"var(--accent)":"var(--muted)" }}>{l}</button>
              ))}
            </div>
          </div>
          {/* view toggle */}
          <div style={{ display:"flex", background:"var(--surface-2)", border:"1px solid var(--line-2)", borderRadius:10, padding:3 }}>
            {[["list","list"],["columns","columns"]].map(([k,ic])=>(
              <button key={k} onClick={()=>app.setView(k)} title={k==="list"?"List":"Columns"} style={{ width:34, height:30, display:"grid", placeItems:"center", borderRadius:7, border:"none",
                background: app.view===k?"var(--accent-weak)":"transparent", color: app.view===k?"var(--accent)":"var(--muted)" }}>
                <Icon name={ic} size={16}/>
              </button>
            ))}
          </div>
        </div>

        {app.view==="list" || bucket!=="all"
          ? <ListView roles={filtered}/>
          : <ColumnsView rolesByBucket={byBucket}/>}
      </div>
    </>
  );
}

Object.assign(window, { Dashboard });
