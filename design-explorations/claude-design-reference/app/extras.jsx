/* ============================================================
   SkyMatch — Saved (shortlist) + Profile & settings
   ============================================================ */
const { useState: useStateEx } = React;

/* ---------------- Saved ---------------- */
function Saved() {
  const app = useApp();
  const roles = window.SM_DATA.ROLES.filter(r=>app.saved.has(r.id));
  const sorted = [...roles].sort((a,b)=>b.score-a.score);
  return (
    <>
      <Topbar title="Saved roles" subtitle={`${roles.length} shortlisted · ranked by fit`}>
        {roles.length>0 && <button className="btn btn-ghost btn-sm"><Icon name="external" size={15}/> Export list</button>}
      </Topbar>
      <div className="scroll" style={{ flex:1, padding:"24px 28px 40px" }}>
        {roles.length===0 ? (
          <div style={{ maxWidth:440, margin:"60px auto 0", textAlign:"center" }}>
            <span style={{ display:"inline-grid", placeItems:"center", width:64, height:64, borderRadius:18, background:"var(--surface-2)", border:"1px solid var(--line-2)", color:"var(--faint)", marginBottom:18 }}>
              <Icon name="bookmark" size={28}/>
            </span>
            <h2 style={{ fontSize:22 }}>No saved roles yet</h2>
            <p style={{ color:"var(--muted)", fontSize:15, marginTop:10 }}>Tap the bookmark on any match to build your shortlist here. Saved roles sync to your applications.</p>
            <button onClick={()=>app.goTab("dashboard")} className="btn btn-primary" style={{ marginTop:20 }}><Icon name="compass" size={16}/> Browse matches</button>
          </div>
        ) : (
          <div style={{ maxWidth:880, margin:"0 auto" }}>
            <div className="stagger" style={{ display:"flex", flexDirection:"column", gap:12 }}>
              {sorted.map(r=><RoleCard key={r.id} role={r} onOpen={app.setOpenRole}/>)}
            </div>
          </div>
        )}
      </div>
    </>
  );
}

/* ---------------- Profile & settings ---------------- */
function SettingRow({ icon, title, desc, children }) {
  return (
    <div style={{ display:"flex", alignItems:"center", gap:16, padding:"16px 0", borderBottom:"1px solid var(--line)" }}>
      <span style={{ flex:"none", width:38, height:38, borderRadius:11, display:"grid", placeItems:"center", background:"var(--surface-2)", border:"1px solid var(--line-2)", color:"var(--muted)" }}>
        <Icon name={icon} size={18}/>
      </span>
      <div style={{ flex:1, minWidth:0 }}>
        <div style={{ fontSize:14.5, fontWeight:600 }}>{title}</div>
        {desc && <div style={{ fontSize:12.5, color:"var(--muted)", marginTop:2 }}>{desc}</div>}
      </div>
      {children}
    </div>
  );
}

function Toggle({ on, onClick }) {
  return (
    <button onClick={onClick} style={{ width:46, height:27, borderRadius:99, border:"none", padding:3, cursor:"pointer",
      background: on?"var(--accent)":"var(--line-3)", transition:"background .25s", flex:"none" }}>
      <span style={{ display:"block", width:21, height:21, borderRadius:"50%", background:"#fff", transform: on?"translateX(19px)":"translateX(0)", transition:"transform .25s var(--ease-spring)", boxShadow:"0 2px 5px rgba(0,0,0,.3)" }}/>
    </button>
  );
}

function Profile() {
  const app = useApp();
  const p = window.SM_DATA.PROFILE;
  const [tab, setTab] = useStateEx("profile");
  const [prefs, setPrefs] = useStateEx({ email:true, weekly:true, reach:true, anon:false });
  const tog = k => setPrefs(s=>({ ...s, [k]:!s[k] }));

  return (
    <>
      <Topbar title="Profile" subtitle="Your trajectory and how SkyMatch reads it">
        <button onClick={()=>app.go("input")} className="btn btn-ghost btn-sm"><Icon name="refresh" size={15}/> Re-import profile</button>
      </Topbar>
      <div className="scroll" style={{ flex:1, padding:"24px 28px 40px" }}>
        <div style={{ maxWidth:980, margin:"0 auto" }}>
          {/* header card */}
          <div className="panel fade-up" style={{ padding:"26px 28px", display:"flex", gap:22, alignItems:"center", flexWrap:"wrap", marginBottom:18 }}>
            <Avatar initials={p.initials} size={72}/>
            <div style={{ flex:1, minWidth:240 }}>
              <h1 style={{ fontSize:26, letterSpacing:"-.02em" }}>{p.name}</h1>
              <div style={{ fontFamily:"var(--mono)", fontSize:13, color:"var(--muted)", marginTop:6 }}>{p.headline}</div>
              <div style={{ display:"flex", gap:16, marginTop:12, flexWrap:"wrap", fontSize:12.5, color:"var(--faint)" }}>
                <span style={{ display:"inline-flex", alignItems:"center", gap:6 }}><Icon name="building" size={14}/> {p.school}</span>
                <span style={{ display:"inline-flex", alignItems:"center", gap:6 }}><Icon name="clock" size={14}/> Grad {p.grad}</span>
                <span style={{ display:"inline-flex", alignItems:"center", gap:6 }}><Icon name="pin" size={14}/> {p.location}</span>
                <span style={{ display:"inline-flex", alignItems:"center", gap:6 }}><Icon name="chart" size={14}/> {p.level}</span>
              </div>
            </div>
          </div>

          {/* sub-tabs */}
          <div style={{ display:"flex", gap:6, marginBottom:20, borderBottom:"1px solid var(--line)" }}>
            {[["profile","Trajectory"],["settings","Preferences"]].map(([k,l])=>(
              <button key={k} onClick={()=>setTab(k)} style={{ padding:"10px 4px", marginRight:18, background:"none", border:"none", fontSize:14, fontWeight:500,
                color: tab===k?"var(--text)":"var(--muted)", borderBottom: tab===k?"2px solid var(--accent)":"2px solid transparent", marginBottom:-1 }}>{l}</button>
            ))}
          </div>

          {tab==="profile" ? (
            <div className="fade-up" style={{ display:"grid", gridTemplateColumns:"1.3fr 1fr", gap:18, alignItems:"start" }}>
              <div style={{ display:"flex", flexDirection:"column", gap:18 }}>
                <div className="panel" style={{ padding:"22px 24px" }}>
                  <div className="eyebrow" style={{ marginBottom:14 }}>Summary</div>
                  <p style={{ fontSize:14.5, color:"var(--text)", lineHeight:1.6 }}>{p.summary}</p>
                </div>
                <div className="panel" style={{ padding:"22px 24px" }}>
                  <div className="eyebrow" style={{ marginBottom:16 }}>Experience</div>
                  <div style={{ display:"flex", flexDirection:"column", gap:2 }}>
                    {p.experience.map((e,i)=>(
                      <div key={i} style={{ display:"flex", gap:14, padding:"14px 0", borderBottom: i<p.experience.length-1?"1px solid var(--line)":"none" }}>
                        <CompanyTile initial={e.org[0]} size={38} alt radius={10}/>
                        <div style={{ flex:1 }}>
                          <div style={{ fontSize:14.5, fontWeight:600 }}>{e.role}</div>
                          <div style={{ fontFamily:"var(--mono)", fontSize:12, color:"var(--muted)", marginTop:2 }}>{e.org} · {e.period}</div>
                          <div style={{ fontSize:13, color:"var(--muted)", marginTop:6, lineHeight:1.5 }}>{e.note}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
                <div className="panel" style={{ padding:"22px 24px" }}>
                  <div className="eyebrow" style={{ marginBottom:14 }}>Skills SkyMatch detected</div>
                  <div style={{ display:"flex", gap:8, flexWrap:"wrap", marginBottom:16 }}>
                    {p.skills.map(s=><span key={s} style={{ fontSize:12.5, color:"var(--text)", border:"1px solid var(--accent-line)", background:"var(--accent-weak)", padding:"6px 11px", borderRadius:99 }}>{s}</span>)}
                  </div>
                  <div style={{ fontSize:12.5, color:"var(--muted)", marginBottom:9 }}>Growing into</div>
                  <div style={{ display:"flex", gap:8, flexWrap:"wrap" }}>
                    {p.growthSkills.map(s=><span key={s} style={{ fontSize:12.5, color:"var(--muted)", border:"1px dashed var(--line-3)", padding:"6px 11px", borderRadius:99 }}>{s}</span>)}
                  </div>
                </div>
              </div>
              <div className="panel" style={{ padding:"22px 24px", position:"sticky", top:0 }}>
                <div className="eyebrow" style={{ marginBottom:6 }}>Your field map</div>
                <p style={{ fontSize:12.5, color:"var(--muted)", marginBottom:8 }}>The vector SkyMatch uses to rank roles.</p>
                <div style={{ display:"grid", placeItems:"center" }}><Radar data={p.vector} size={230}/></div>
              </div>
            </div>
          ) : (
            <div className="fade-up" style={{ maxWidth:680 }}>
              <div className="panel" style={{ padding:"6px 24px 18px" }}>
                <div className="eyebrow" style={{ margin:"18px 0 4px" }}>Appearance</div>
                <SettingRow icon={app.theme==="light"?"sun":"moon"} title="Theme" desc="Switch between deep-space dark and daylight">
                  <div style={{ display:"flex", background:"var(--surface-2)", border:"1px solid var(--line-2)", borderRadius:10, padding:3 }}>
                    {[["dark","moon"],["light","sun"]].map(([k,ic])=>(
                      <button key={k} onClick={()=>app.setTheme(k)} style={{ display:"flex", alignItems:"center", gap:6, padding:"6px 12px", borderRadius:7, border:"none", fontSize:12.5, fontWeight:500, textTransform:"capitalize",
                        background: app.theme===k?"var(--accent-weak)":"transparent", color: app.theme===k?"var(--accent)":"var(--muted)" }}><Icon name={ic} size={14}/>{k}</button>
                    ))}
                  </div>
                </SettingRow>
                <SettingRow icon="sparkle" title="Accent color" desc="Pick the aurora tone used across the app">
                  <div style={{ display:"flex", gap:8 }}>
                    {[["mint","#79F2C0"],["cyan","#52CFEC"],["iris","#8FA2FF"],["gold","#FFD27A"]].map(([k,c])=>(
                      <button key={k} onClick={()=>app.setAccent(k)} title={k} style={{ width:28, height:28, borderRadius:"50%", border: app.accent===k?"2px solid var(--text)":"2px solid transparent", background:c, cursor:"pointer", boxShadow:"0 0 0 1px var(--line-2)" }}/>
                    ))}
                  </div>
                </SettingRow>

                <div className="eyebrow" style={{ margin:"22px 0 4px" }}>Notifications</div>
                <SettingRow icon="bell" title="New strong matches" desc="Email me when a role scores 80+ for my profile">
                  <Toggle on={prefs.email} onClick={()=>tog("email")}/>
                </SettingRow>
                <SettingRow icon="clock" title="Weekly digest" desc="A Monday summary of fresh roles across buckets">
                  <Toggle on={prefs.weekly} onClick={()=>tog("weekly")}/>
                </SettingRow>
                <SettingRow icon="star" title="Include reach roles" desc="Surface deliberate stretch roles in my runs">
                  <Toggle on={prefs.reach} onClick={()=>tog("reach")}/>
                </SettingRow>

                <div className="eyebrow" style={{ margin:"22px 0 4px" }}>Privacy</div>
                <SettingRow icon="shield" title="Anonymous runs" desc="Don't store my profile between sessions">
                  <Toggle on={prefs.anon} onClick={()=>tog("anon")}/>
                </SettingRow>
                <SettingRow icon="logout" title="Sign out" desc="End this session on all devices">
                  <button onClick={()=>app.go("auth-signin")} className="btn btn-ghost btn-sm">Sign out</button>
                </SettingRow>
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  );
}

Object.assign(window, { Saved, Profile });
