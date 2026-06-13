/* ============================================================
   SkyMatch — app root: state, routing, tweaks
   ============================================================ */
const { useState: useStateApp, useEffect: useEffectApp, useCallback } = React;

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "accent": "mint",
  "theme": "dark",
  "ambient": true
}/*EDITMODE-END*/;

function App() {
  const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);

  const initScreen = (()=>{ try{ const s=new URLSearchParams(location.search).get("screen"); return ({signin:"auth-signin",signup:"auth-signup",input:"input"})[s] || "app"; }catch(e){ return "app"; } })();
  const [route, setRoute] = useStateApp(initScreen);   // app | auth-signin | auth-signup | input | analyzing
  const [tab, setTab] = useStateApp("dashboard");    // dashboard | analyzer | saved | profile
  const [view, setView] = useStateApp("list");       // list | columns
  const [openRoleId, setOpenRole] = useStateApp(null);
  const [saved, setSaved] = useStateApp(()=>new Set(["r1","r7","r12"]));
  const [hasRun, setHasRun] = useStateApp(true);
  const [analyzerSeed, setAnalyzerSeed] = useStateApp(false);
  const [analyzerPreset, setAnalyzerPreset] = useStateApp("");

  // apply theme + accent to <html>
  useEffectApp(()=>{
    document.documentElement.setAttribute("data-theme", t.theme);
    document.documentElement.setAttribute("data-accent", t.accent);
  }, [t.theme, t.accent]);

  const toggleSave = useCallback((id)=> setSaved(s=>{ const n=new Set(s); n.has(id)?n.delete(id):n.add(id); return n; }), []);

  const go = useCallback((r)=>{ setRoute(r); setOpenRole(null); if(r==="app"){} }, []);
  const goTab = useCallback((tb)=>{ setRoute("app"); setTab(tb); setOpenRole(null); }, []);
  const finishRun = useCallback(()=>{ setHasRun(true); setRoute("app"); setTab("dashboard"); }, []);

  const analyzeRole = useCallback((role)=>{ setOpenRole(null); setAnalyzerSeed(true); setRoute("app"); setTab("analyzer"); }, []);
  const clearAnalyzerSeed = useCallback(()=>setAnalyzerSeed(false), []);

  const value = {
    route, tab, view, openRoleId, saved, hasRun, analyzerSeed, analyzerPreset,
    accent: t.accent, theme: t.theme,
    go, goTab, setView, setOpenRole, toggleSave, finishRun, analyzeRole, clearAnalyzerSeed,
    setAccent:(v)=>setTweak("accent",v), setTheme:(v)=>setTweak("theme",v),
  };

  const screens = { dashboard:Dashboard, analyzer:Analyzer, saved:Saved, profile:Profile };
  const Screen = screens[tab] || Dashboard;

  let body;
  if(route==="auth-signin"||route==="auth-signup") body = <Auth/>;
  else if(route==="input") body = <InputFlow/>;
  else if(route==="analyzing") body = <Analyzing/>;
  else body = (
    <div style={{ display:"flex", height:"100%", position:"relative", zIndex:2 }}>
      <Sidebar/>
      <main key={tab} style={{ flex:1, minWidth:0, display:"flex", flexDirection:"column", height:"100%", animation:"fadeIn .35s var(--ease)" }}>
        <Screen/>
      </main>
      <RoleDrawer/>
    </div>
  );

  return (
    <AppCtx.Provider value={value}>
      {/* ambient background */}
      {t.ambient && <div className="app-bg" aria-hidden="true"><div className="mesh"/></div>}
      <div className="app-grain" aria-hidden="true">
        <svg xmlns="http://www.w3.org/2000/svg" style={{width:"100%",height:"100%"}}><filter id="ng"><feTurbulence type="fractalNoise" baseFrequency="0.8" numOctaves="2" stitchTiles="stitch"/></filter><rect width="100%" height="100%" filter="url(#ng)"/></svg>
      </div>

      {body}

      <TweaksPanel>
        <TweakSection label="Accent" />
        <TweakColor label="Aurora tone" value={ACCENT_HEX[t.accent]}
          options={["#79F2C0","#52CFEC","#8FA2FF","#FFD27A"]}
          onChange={(hex)=>setTweak("accent", HEX_ACCENT[hex] || "mint")} />
        <TweakSection label="Appearance" />
        <TweakRadio label="Theme" value={t.theme} options={["dark","light"]} onChange={(v)=>setTweak("theme",v)} />
        <TweakToggle label="Ambient glow" value={t.ambient} onChange={(v)=>setTweak("ambient",v)} />
      </TweaksPanel>
    </AppCtx.Provider>
  );
}

const ACCENT_HEX = { mint:"#79F2C0", cyan:"#52CFEC", iris:"#8FA2FF", gold:"#FFD27A" };
const HEX_ACCENT = { "#79F2C0":"mint", "#52CFEC":"cyan", "#8FA2FF":"iris", "#FFD27A":"gold" };

ReactDOM.createRoot(document.getElementById("root")).render(<App/>);
