/* ============================================================
   SkyMatch — app chrome: Sidebar, Topbar, RoleCard, RoleDrawer
   ============================================================ */
const { useState: useStateSh, useEffect: useEffectSh } = React;

/* ---------------- Sidebar ---------------- */
function Sidebar() {
  const app = useApp();
  const items = [
    { id:"dashboard", label:"Matches", icon:"compass" },
    { id:"analyzer", label:"Job-fit analyzer", icon:"target" },
    { id:"saved", label:"Saved", icon:"bookmark", badge: app.saved.size || null },
    { id:"profile", label:"Profile", icon:"user" },
  ];
  return (
    <aside style={{
      width:"var(--sidebar-w)", flex:"none", height:"100%", display:"flex", flexDirection:"column",
      borderRight:"1px solid var(--line)", background:"linear-gradient(180deg,var(--surface),var(--bg-2))",
      position:"relative", zIndex:3,
    }}>
      <div style={{ padding:"22px 20px 18px" }}>
        <Logo size={28} wordmarkSize={20}/>
      </div>

      <div style={{ padding:"0 14px" }}>
        <button className="btn btn-primary" style={{ width:"100%", marginBottom:6 }} onClick={()=>app.go("input")}>
          <Icon name="sparkle" size={17}/> New match run
        </button>
      </div>

      <nav className="scroll" style={{ flex:1, padding:"14px 14px", display:"flex", flexDirection:"column", gap:3 }}>
        {items.map(it=>{
          const on = app.tab === it.id;
          return (
            <button key={it.id} onClick={()=>app.goTab(it.id)} style={{
              display:"flex", alignItems:"center", gap:12, padding:"11px 13px", borderRadius:11, border:"1px solid transparent",
              background: on ? "var(--accent-weak)" : "transparent", color: on ? "var(--text)" : "var(--muted)",
              borderColor: on ? "var(--accent-line)" : "transparent",
              fontSize:14, fontWeight:500, textAlign:"left", width:"100%", transition:"background .2s, border-color .2s",
            }}
            onMouseEnter={e=>{ if(!on){ e.currentTarget.style.background="rgba(255,255,255,.03)"; e.currentTarget.style.color="var(--text)"; }}}
            onMouseLeave={e=>{ if(!on){ e.currentTarget.style.background="transparent"; e.currentTarget.style.color="var(--muted)"; }}}>
              <Icon name={it.icon} size={19} style={{ color: on ? "var(--accent)" : "inherit" }}/>
              <span style={{ flex:1 }}>{it.label}</span>
              {it.badge ? <span style={{ fontFamily:"var(--mono)", fontSize:11, color:"var(--accent)", background:"var(--accent-weak)", padding:"1px 7px", borderRadius:99 }}>{it.badge}</span> : null}
            </button>
          );
        })}

        <div style={{ marginTop:"auto" }}/>
        <div style={{ padding:"14px 12px", margin:"10px 2px 0", borderRadius:14, border:"1px solid var(--line)", background:"var(--surface-2)" }}>
          <div className="tag" style={{ marginBottom:8 }}>Last run</div>
          <div style={{ fontSize:13, color:"var(--muted)", lineHeight:1.5 }}>
            <b style={{ color:"var(--text)", fontWeight:600 }}>{window.SM_DATA.ROLES.length} roles</b> matched to your profile across 4 buckets.
          </div>
          <button onClick={()=>app.go("input")} style={{ marginTop:10, display:"inline-flex", alignItems:"center", gap:6, fontSize:12.5, color:"var(--accent)", background:"none", border:"none", padding:0 }}>
            <Icon name="refresh" size={14}/> Re-run match
          </button>
        </div>
      </nav>

      <div style={{ padding:"12px 14px", borderTop:"1px solid var(--line)" }}>
        <div style={{ display:"flex", alignItems:"center", gap:11, width:"100%", padding:"6px 8px", borderRadius:10 }}
          onMouseEnter={e=>e.currentTarget.style.background="rgba(255,255,255,.03)"} onMouseLeave={e=>e.currentTarget.style.background="none"}>
          <button onClick={()=>app.goTab("profile")} style={{ display:"flex", alignItems:"center", gap:11, flex:1, minWidth:0, background:"none", border:"none", padding:0 }}>
            <Avatar initials={window.SM_DATA.PROFILE.initials} size={34}/>
            <div style={{ textAlign:"left", flex:1, minWidth:0 }}>
              <div style={{ fontSize:13.5, fontWeight:600, color:"var(--text)", whiteSpace:"nowrap", overflow:"hidden", textOverflow:"ellipsis" }}>{window.SM_DATA.PROFILE.name}</div>
              <div style={{ fontSize:11.5, color:"var(--faint)", whiteSpace:"nowrap", overflow:"hidden", textOverflow:"ellipsis" }}>{window.SM_DATA.PROFILE.school}</div>
            </div>
          </button>
          <button onClick={(e)=>{ e.stopPropagation(); app.go("auth-signin"); }} className="icon-btn" style={{ width:30, height:30, flex:"none" }} title="Sign out">
            <Icon name="logout" size={15}/>
          </button>
        </div>
      </div>
    </aside>
  );
}

/* ---------------- Topbar ---------------- */
function Topbar({ title, subtitle, children }) {
  const app = useApp();
  return (
    <header style={{
      display:"flex", alignItems:"center", gap:18, padding:"18px 28px", borderBottom:"1px solid var(--line)",
      background:"color-mix(in oklab, var(--bg) 70%, transparent)", backdropFilter:"blur(12px)",
      position:"sticky", top:0, zIndex:4, minHeight:74,
    }}>
      <div style={{ minWidth:0 }}>
        <h2 style={{ fontSize:22, letterSpacing:"-.02em" }}>{title}</h2>
        {subtitle && <div style={{ fontSize:13, color:"var(--muted)", marginTop:3 }}>{subtitle}</div>}
      </div>
      <div style={{ flex:1 }}/>
      {children}
      <button className="icon-btn" title="Notifications"><Icon name="bell" size={18}/></button>
    </header>
  );
}

/* ---------------- Role card ---------------- */
function RoleCard({ role, onOpen, compact = false }) {
  const app = useApp();
  const saved = app.saved.has(role.id);
  const b = BUCKETS[role.bucket];
  return (
    <article onClick={()=>onOpen(role.id)} className="panel-flat role-card" style={{
      padding: compact ? "16px 18px" : "18px 20px", cursor:"pointer", display:"flex", alignItems:"center", gap:16,
      transition:"transform .25s var(--ease), border-color .25s, box-shadow .25s",
    }}
      onMouseEnter={e=>{ e.currentTarget.style.transform="translateY(-2px)"; e.currentTarget.style.borderColor="var(--line-3)"; e.currentTarget.style.boxShadow="var(--shadow)"; }}
      onMouseLeave={e=>{ e.currentTarget.style.transform=""; e.currentTarget.style.borderColor="var(--line)"; e.currentTarget.style.boxShadow="none"; }}>
      <CompanyTile initial={role.initial} alt={role.score < 70} size={compact?40:46}/>
      <div style={{ flex:1, minWidth:0 }}>
        <div style={{ display:"flex", alignItems:"center", gap:9, flexWrap:"wrap" }}>
          <span style={{ fontWeight:600, fontSize:compact?14.5:15.5, letterSpacing:"-.01em" }}>{role.title}</span>
          <span style={{ display:"inline-flex", alignItems:"center", gap:5, fontFamily:"var(--mono)", fontSize:10.5, color:"var(--faint)", textTransform:"uppercase", letterSpacing:".08em" }}>
            <i className={b.dot} style={{ width:6, height:6, borderRadius:"50%", display:"inline-block" }}/>{b.label}
          </span>
        </div>
        <div style={{ fontFamily:"var(--mono)", fontSize:12.5, color:"var(--muted)", marginTop:5, whiteSpace:"nowrap", overflow:"hidden", textOverflow:"ellipsis" }}>
          {role.company} · {role.location} · {role.term}
        </div>
        {!compact && (
          <div style={{ display:"flex", gap:7, marginTop:11, flexWrap:"wrap" }}>
            {role.matched.slice(0,3).map(m=>(
              <span key={m} style={{ fontSize:11.5, color:"var(--muted)", border:"1px solid var(--line)", padding:"3px 9px", borderRadius:99 }}>{m}</span>
            ))}
            {role.matched.length>3 && <span style={{ fontSize:11.5, color:"var(--faint)", padding:"3px 4px" }}>+{role.matched.length-3}</span>}
          </div>
        )}
      </div>
      <button onClick={(e)=>{ e.stopPropagation(); app.toggleSave(role.id); }} className="icon-btn"
        style={{ width:36, height:36, color: saved ? "var(--accent)" : "var(--muted)", borderColor: saved ? "var(--accent-line)" : "var(--line-2)", background: saved ? "var(--accent-weak)" : "rgba(255,255,255,.02)" }}
        title={saved?"Saved":"Save"}>
        <Icon name="bookmark" size={16} fill={saved}/>
      </button>
      <div style={{ display:"flex", flexDirection:"column", alignItems:"center", gap:7, flex:"none" }}>
        <FitRing score={role.score} size={compact?46:52} stroke={4.5}/>
        <TierBadge score={role.score}/>
      </div>
    </article>
  );
}

/* ---------------- Role detail drawer ---------------- */
function RoleDrawer() {
  const app = useApp();
  const role = window.SM_DATA.ROLES.find(r=>r.id===app.openRoleId);
  const open = !!role;
  const [mounted, setMounted] = useStateSh(false);
  useEffectSh(()=>{ if(open){ const t=setTimeout(()=>setMounted(true),10); return ()=>clearTimeout(t);} else setMounted(false); }, [open]);
  if(!open) return null;
  const saved = app.saved.has(role.id);
  const b = BUCKETS[role.bucket];
  const facts = [
    { icon:"money", label:"Stipend", val:role.pay },
    { icon:"pin", label:"Location", val:`${role.location} · ${role.remote}` },
    { icon:"clock", label:"Term", val:role.term },
    { icon:"layers", label:"Team", val:role.team },
    { icon:"building", label:"Company", val:role.size },
    { icon:"clock", label:"Posted", val:`${role.posted} ago` },
  ];
  return (
    <div style={{ position:"fixed", inset:0, zIndex:60 }}>
      <div onClick={()=>app.setOpenRole(null)} style={{ position:"absolute", inset:0, background:"rgba(4,6,10,.55)", backdropFilter:"blur(3px)", opacity:mounted?1:0, transition:"opacity .35s" }}/>
      <aside className="scroll" style={{
        position:"absolute", top:0, right:0, height:"100%", width:"min(560px,94vw)",
        background:"linear-gradient(180deg,var(--surface-2),var(--bg-2))", borderLeft:"1px solid var(--line-2)",
        boxShadow:"var(--shadow-lg)", transform:mounted?"translateX(0)":"translateX(100%)", transition:"transform .42s var(--ease)",
        display:"flex", flexDirection:"column",
      }}>
        {/* header */}
        <div style={{ padding:"22px 26px 20px", borderBottom:"1px solid var(--line)", position:"sticky", top:0, background:"color-mix(in oklab,var(--surface-2) 88%, transparent)", backdropFilter:"blur(10px)", zIndex:2 }}>
          <div style={{ display:"flex", justifyContent:"space-between", alignItems:"flex-start", marginBottom:18 }}>
            <span style={{ display:"inline-flex", alignItems:"center", gap:7, fontFamily:"var(--mono)", fontSize:11, color:"var(--faint)", textTransform:"uppercase", letterSpacing:".12em" }}>
              <i className={b.dot} style={{ width:7, height:7, borderRadius:"50%" }}/>{b.label} match
            </span>
            <button onClick={()=>app.setOpenRole(null)} className="icon-btn" style={{ width:34, height:34 }}><Icon name="x" size={17}/></button>
          </div>
          <div style={{ display:"flex", gap:16, alignItems:"flex-start" }}>
            <CompanyTile initial={role.initial} alt={role.score<70} size={56} radius={14}/>
            <div style={{ flex:1, minWidth:0 }}>
              <h2 style={{ fontSize:23, letterSpacing:"-.02em", lineHeight:1.12 }}>{role.title}</h2>
              <div style={{ fontFamily:"var(--mono)", fontSize:13, color:"var(--muted)", marginTop:6 }}>{role.company}</div>
            </div>
            <div style={{ display:"flex", flexDirection:"column", alignItems:"center", gap:8 }}>
              <FitRing score={role.score} size={66} stroke={5.5}/>
              <TierBadge score={role.score}/>
            </div>
          </div>
        </div>

        <div style={{ padding:"24px 26px 30px", display:"flex", flexDirection:"column", gap:26 }}>
          {/* facts */}
          <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:1, background:"var(--line)", border:"1px solid var(--line)", borderRadius:14, overflow:"hidden" }}>
            {facts.map((f,i)=>(
              <div key={i} style={{ background:"var(--surface)", padding:"13px 15px" }}>
                <div style={{ display:"flex", alignItems:"center", gap:7, fontSize:11, color:"var(--faint)", fontFamily:"var(--mono)", textTransform:"uppercase", letterSpacing:".08em" }}>
                  <Icon name={f.icon} size={14}/> {f.label}
                </div>
                <div style={{ fontSize:13.5, color:"var(--text)", marginTop:5, fontWeight:500 }}>{f.val}</div>
              </div>
            ))}
          </div>

          {/* why you fit */}
          <section>
            <div className="eyebrow" style={{ marginBottom:14 }}>Why you fit</div>
            <div style={{ display:"flex", flexDirection:"column", gap:10 }}>
              {role.why.map((w,i)=>(
                <div key={i} style={{ display:"flex", gap:11, alignItems:"flex-start" }}>
                  <span style={{ flex:"none", marginTop:1, width:22, height:22, borderRadius:"50%", display:"grid", placeItems:"center", background:"var(--accent-weak)", color:"var(--accent)" }}>
                    <Icon name="check" size={13} stroke={2.2}/>
                  </span>
                  <span style={{ fontSize:14.5, color:"var(--text)", lineHeight:1.5 }}>{w}</span>
                </div>
              ))}
            </div>
          </section>

          {/* skill match */}
          <section>
            <div className="eyebrow" style={{ marginBottom:14 }}>Skill alignment</div>
            <div style={{ marginBottom:14 }}>
              <div style={{ fontSize:12.5, color:"var(--muted)", marginBottom:9 }}>You already bring</div>
              <div style={{ display:"flex", gap:8, flexWrap:"wrap" }}>
                {role.matched.map(m=>(
                  <span key={m} style={{ display:"inline-flex", alignItems:"center", gap:6, fontSize:12.5, color:"var(--text)", border:"1px solid var(--accent-line)", background:"var(--accent-weak)", padding:"6px 11px", borderRadius:99 }}>
                    <Icon name="check" size={12} stroke={2.4} style={{ color:"var(--accent)" }}/>{m}
                  </span>
                ))}
              </div>
            </div>
            {role.gaps.length>0 && (
              <div>
                <div style={{ fontSize:12.5, color:"var(--muted)", marginBottom:9 }}>Worth shoring up</div>
                <div style={{ display:"flex", gap:8, flexWrap:"wrap" }}>
                  {role.gaps.map(g=>(
                    <span key={g} style={{ fontSize:12.5, color:"var(--muted)", border:"1px dashed var(--line-3)", padding:"6px 11px", borderRadius:99 }}>{g}</span>
                  ))}
                </div>
              </div>
            )}
          </section>
        </div>

        {/* sticky footer actions */}
        <div style={{ marginTop:"auto", padding:"16px 26px", borderTop:"1px solid var(--line)", display:"flex", gap:10, background:"var(--surface-2)", position:"sticky", bottom:0 }}>
          <button className="btn btn-primary" style={{ flex:1 }}><Icon name="external" size={16}/> Apply now</button>
          <button onClick={()=>app.toggleSave(role.id)} className="btn btn-ghost" style={{ color: saved?"var(--accent)":"var(--text)" }}>
            <Icon name="bookmark" size={16} fill={saved}/> {saved?"Saved":"Save"}
          </button>
          <button onClick={()=>app.analyzeRole(role)} className="btn btn-ghost" title="Open in analyzer"><Icon name="target" size={16}/></button>
        </div>
      </aside>
    </div>
  );
}

Object.assign(window, { Sidebar, Topbar, RoleCard, RoleDrawer });
