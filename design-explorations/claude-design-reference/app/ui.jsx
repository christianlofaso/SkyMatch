/* ============================================================
   SkyMatch — shared UI primitives
   Exported to window for use across screen scripts.
   ============================================================ */
const { useState, useEffect, useRef, useMemo } = React;

/* ---- Brand mark (north-star / compass node from the landing page) ---- */
function Logo({ size = 30, withWordmark = true, wordmarkSize = 21 }) {
  return (
    <span className="brand" style={{ display:"inline-flex", alignItems:"center", gap:11 }}>
      <svg width={size} height={size} viewBox="0 0 32 32" fill="none" style={{ flex:"none" }}>
        <circle cx="16" cy="16" r="15" stroke="url(#aur)" strokeOpacity=".35"/>
        <path d="M16 3.5c.9 6.2 2.4 9.6 8.5 12.5-6.1 2.9-7.6 6.3-8.5 12.5-.9-6.2-2.4-9.6-8.5-12.5C13.6 13.1 15.1 9.7 16 3.5Z" fill="url(#aur)"/>
        <circle cx="16" cy="16" r="2.1" fill="var(--bg)"/>
        <circle cx="16" cy="16" r="1.1" fill="url(#aur)"/>
      </svg>
      {withWordmark && (
        <span style={{ fontFamily:"var(--display)", fontWeight:600, fontSize:wordmarkSize, letterSpacing:"-.02em", color:"var(--text)" }}>
          SkyMatch
        </span>
      )}
    </span>
  );
}

/* ---- Icon set ---- */
const ICONS = {
  compass: <><circle cx="12" cy="12" r="9"/><path d="m15.5 8.5-2 5-5 2 2-5z"/></>,
  grid: <><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></>,
  target: <><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/></>,
  bookmark: <path d="M6 4h12a1 1 0 0 1 1 1v15l-7-4-7 4V5a1 1 0 0 1 1-1Z"/>,
  user: <><circle cx="12" cy="8" r="4"/><path d="M5 20c0-3.5 3-6 7-6s7 2.5 7 6"/></>,
  search: <><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></>,
  arrowRight: <path d="M5 12h14m-6-6 6 6-6 6"/>,
  arrowLeft: <path d="M19 12H5m6 6-6-6 6-6"/>,
  arrowUpRight: <path d="M7 17 17 7m0 0H8m9 0v9"/>,
  check: <path d="M5 12.5 10 17 19 7"/>,
  checkCircle: <><circle cx="12" cy="12" r="9"/><path d="m8.5 12 2.5 2.5 4.5-5"/></>,
  x: <path d="M6 6l12 12M18 6 6 18"/>,
  plus: <path d="M12 5v14M5 12h14"/>,
  minus: <path d="M5 12h14"/>,
  sparkle: <path d="M12 3c.8 5 2 7 7 8-5 1-6.2 3-7 8-.8-5-2-7-7-8 5-1 6.2-3 7-8Z"/>,
  bolt: <path d="M13 2 4 14h6l-1 8 9-12h-6l1-8Z"/>,
  pin: <><path d="M12 21s7-6 7-11a7 7 0 1 0-14 0c0 5 7 11 7 11Z"/><circle cx="12" cy="10" r="2.5"/></>,
  building: <><rect x="5" y="3" width="14" height="18" rx="1.5"/><path d="M9 7h2M13 7h2M9 11h2M13 11h2M9 15h2M13 15h2"/></>,
  rocket: <path d="M5 15c-1 2-1 4-1 4s2 0 4-1m1.5-2.5 7-7c2-2 2.5-4.5 2.5-5.5 0 0-3.5 0-5.5 2.5l-7 7s1 1 1 1l1 1Z"/>,
  clock: <><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.5 2"/></>,
  money: <><rect x="3" y="6" width="18" height="12" rx="2"/><circle cx="12" cy="12" r="2.5"/></>,
  chart: <><path d="M4 20V4M4 20h16"/><path d="M8 16v-4M12 16V8M16 16v-7"/></>,
  filter: <path d="M4 5h16l-6 7v6l-4 2v-8L4 5Z"/>,
  sliders: <><path d="M4 8h10M18 8h2M4 16h2M10 16h10"/><circle cx="15" cy="8" r="2"/><circle cx="8" cy="16" r="2"/></>,
  bell: <><path d="M6 9a6 6 0 1 1 12 0c0 5 2 6 2 6H4s2-1 2-6Z"/><path d="M10 19a2 2 0 0 0 4 0"/></>,
  logout: <><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="M16 17l5-5-5-5M21 12H9"/></>,
  external: <><path d="M14 4h6v6"/><path d="M20 4 10 14"/><path d="M19 13v6a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h6"/></>,
  doc: <><path d="M6 3h8l4 4v14a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z"/><path d="M14 3v4h4M8 13h8M8 17h6"/></>,
  link: <><path d="M9 15 15 9"/><path d="M11 6.5 13 4.5a4 4 0 0 1 6 6l-2 2"/><path d="M13 17.5l-2 2a4 4 0 0 1-6-6l2-2"/></>,
  eye: <><path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/></>,
  flag: <><path d="M5 21V4M5 4h11l-2 4 2 4H5"/></>,
  layers: <><path d="m12 3 9 5-9 5-9-5 9-5Z"/><path d="m3 13 9 5 9-5"/></>,
  list: <><path d="M8 6h13M8 12h13M8 18h13"/><circle cx="3.5" cy="6" r="1"/><circle cx="3.5" cy="12" r="1"/><circle cx="3.5" cy="18" r="1"/></>,
  columns: <><rect x="3" y="4" width="7" height="16" rx="1.5"/><rect x="14" y="4" width="7" height="16" rx="1.5"/></>,
  star: <path d="M12 3.5l2.6 5.3 5.9.9-4.3 4.1 1 5.8-5.2-2.7-5.2 2.7 1-5.8L4.5 9.7l5.9-.9L12 3.5Z"/>,
  briefcase: <><rect x="3" y="7" width="18" height="13" rx="2"/><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M3 12h18"/></>,
  send: <path d="M22 2 11 13M22 2l-7 20-4-9-9-4 20-7Z"/>,
  moon: <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z"/>,
  sun: <><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4 12H2M22 12h-2M5 5l1.5 1.5M17.5 17.5 19 19M19 5l-1.5 1.5M6.5 17.5 5 19"/></>,
  chevronDown: <path d="m6 9 6 6 6-6"/>,
  chevronRight: <path d="m9 6 6 6-6 6"/>,
  trending: <path d="M3 17 9 11l4 4 8-8m0 0h-5m5 0v5"/>,
  shield: <path d="M12 3 5 6v5c0 4.5 3 7.5 7 10 4-2.5 7-5.5 7-10V6l-7-3Z"/>,
  refresh: <><path d="M3 12a9 9 0 0 1 15-6.7L21 8M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-15 6.7L3 16M3 21v-5h5"/></>,
};
function Icon({ name, size = 20, stroke = 1.7, fill = false, style, className }) {
  const p = ICONS[name] || ICONS.compass;
  return (
    <svg width={size} height={size} viewBox="0 0 24 24"
      fill={fill ? "currentColor" : "none"} stroke={fill ? "none" : "currentColor"}
      strokeWidth={stroke} strokeLinecap="round" strokeLinejoin="round"
      className={className} style={style} aria-hidden="true">
      {p}
    </svg>
  );
}

/* ---- Bucket meta ---- */
const BUCKETS = {
  startup: { label:"Startup", icon:"rocket", dot:"dot-mint", hue:"var(--mint)", blurb:"High-ownership roles at fast-moving teams" },
  bigtech: { label:"Big Tech", icon:"building", dot:"dot-cyan", hue:"var(--cyan)", blurb:"Scale, mentorship, and brand-name leverage" },
  local:   { label:"Local", icon:"pin", dot:"dot-gold", hue:"var(--gold)", blurb:"Close to home in the Bay Area" },
  reach:   { label:"Reach", icon:"star", dot:"dot-iris", hue:"var(--iris)", blurb:"A deliberate stretch worth the shot" },
};

/* ---- Company logo tile (initial on tinted ground) ---- */
function CompanyTile({ initial, size = 44, alt = false, radius = 11 }) {
  return (
    <div style={{
      width:size, height:size, borderRadius:radius, flex:"none", display:"grid", placeItems:"center",
      fontFamily:"var(--display)", fontWeight:600, fontSize:size*0.42, color:"var(--text)",
      background: alt
        ? "radial-gradient(circle at 30% 25%,rgba(143,162,255,.28),rgba(82,207,236,.10))"
        : "radial-gradient(circle at 30% 25%,rgba(121,242,192,.26),rgba(82,207,236,.12))",
      border:"1px solid var(--line-2)",
    }}>{initial}</div>
  );
}

/* ---- Avatar ---- */
function Avatar({ initials, size = 38 }) {
  return (
    <div style={{
      width:size, height:size, borderRadius:"50%", flex:"none", display:"grid", placeItems:"center",
      fontFamily:"var(--display)", fontWeight:600, fontSize:size*0.38, color:"var(--accent-ink)",
      background:"var(--aurora)", boxShadow:"0 4px 14px -6px var(--glow-cyan)",
    }}>{initials}</div>
  );
}

/* ---- Fit ring ---- */
function FitRing({ score, size = 60, stroke = 5, showLabel = true, animate = true }) {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const [dash, setDash] = useState(animate ? 0 : score);
  useEffect(() => { if (animate){ const t = setTimeout(() => setDash(score), 80); return () => clearTimeout(t); } }, [score, animate]);
  const color = score >= 80 ? "var(--mint)" : score >= 62 ? "var(--gold)" : "var(--iris)";
  return (
    <div style={{ position:"relative", width:size, height:size, flex:"none" }}>
      <svg width={size} height={size} style={{ transform:"rotate(-90deg)" }}>
        <circle cx={size/2} cy={size/2} r={r} stroke="var(--line-2)" strokeWidth={stroke} fill="none"/>
        <circle cx={size/2} cy={size/2} r={r} stroke={color} strokeWidth={stroke} fill="none" strokeLinecap="round"
          strokeDasharray={c} strokeDashoffset={c - (dash/100)*c}
          style={{ transition:"stroke-dashoffset 1s cubic-bezier(.22,.61,.30,1)" }}/>
      </svg>
      {showLabel && (
        <span style={{ position:"absolute", inset:0, display:"grid", placeItems:"center",
          fontFamily:"var(--display)", fontWeight:600, fontSize:size*0.30, color:"var(--text)" }}>{score}</span>
      )}
    </div>
  );
}

/* ---- Tier badge ---- */
function TierBadge({ score }) {
  const t = window.SM_TIER(score);
  const map = { strong:{ c:"var(--mint)", bg:"rgba(121,242,192,.10)" }, stretch:{ c:"var(--gold)", bg:"rgba(255,210,122,.10)" }, reach:{ c:"var(--iris)", bg:"rgba(143,162,255,.10)" } };
  const s = map[t.cls];
  return (
    <span style={{ fontFamily:"var(--mono)", fontSize:10, letterSpacing:".14em", textTransform:"uppercase",
      color:s.c, background:s.bg, border:`1px solid ${s.c}33`, padding:"4px 9px", borderRadius:999, whiteSpace:"nowrap" }}>
      {t.label}
    </span>
  );
}

/* ---- Tiny sparkline radar (profile vector) ---- */
function Radar({ data, size = 180 }) {
  const cx = size/2, cy = size/2, R = size/2 - 26;
  const n = data.length;
  const pt = (i, v) => {
    const a = (Math.PI * 2 * i) / n - Math.PI/2;
    const rr = (v/100) * R;
    return [cx + rr*Math.cos(a), cy + rr*Math.sin(a)];
  };
  const poly = data.map((d,i)=>pt(i,d.v).join(",")).join(" ");
  return (
    <svg width={size} height={size}>
      {[0.33,0.66,1].map((f,gi)=>(
        <polygon key={gi} points={data.map((_,i)=>pt(i,100*f).join(",")).join(" ")}
          fill="none" stroke="var(--line-2)" strokeWidth="1"/>
      ))}
      {data.map((_,i)=>{ const [x,y]=pt(i,100); return <line key={i} x1={cx} y1={cy} x2={x} y2={y} stroke="var(--line)" strokeWidth="1"/>; })}
      <polygon points={poly} fill="var(--accent-weak)" stroke="var(--accent)" strokeWidth="1.6"/>
      {data.map((d,i)=>{ const [x,y]=pt(i,d.v); return <circle key={i} cx={x} cy={y} r="3" fill="var(--accent)"/>; })}
      {data.map((d,i)=>{ const [x,y]=pt(i,118); return (
        <text key={i} x={x} y={y} fontSize="9.5" fontFamily="var(--mono)" fill="var(--faint)"
          textAnchor="middle" dominantBaseline="middle" style={{textTransform:"uppercase",letterSpacing:".06em"}}>{d.k}</text>
      ); })}
    </svg>
  );
}

Object.assign(window, { Logo, Icon, ICONS, FitRing, TierBadge, CompanyTile, Avatar, Radar, BUCKETS });
