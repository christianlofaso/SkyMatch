"use client";
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";

// Radar-sweep "finding your matches" loader (option-j runveil). The bar climbs CONTINUOUSLY by
// easing toward a phase-scaled cap each tick (NProgress-style trickle), so it never stalls and
// never snaps: a stream phase only RAISES the cap and the same ease keeps the bar climbing
// smoothly. A guaranteed minimum creep keeps motion visible even as it nears a cap. Completion is
// hook-driven — useProfileRun navigates to /results on `done`, which unmounts this overlay (we
// never fake a finish, so the bar need not reach 100% itself).
const RV_STEPS: Array<[string, string]> = [
  ["Reading your profile", "Parsing experience, skills and trajectory"],
  ["Building your field map", "Mapping you across six dimensions"],
  ["Searching the index", "Scanning live internship postings"],
  ["Grading fit", "Sorting roles into honest bands"],
];

// pct thresholds at which the step label advances.
const STEP_AT = [0, 30, 55, 80];
const TICK_MS = 120;

export function RunVeil({ step }: { step: "profile" | "internships" | null }) {
  const [pct, setPct] = useState(0);
  // Portal to body: the veil mounts under the hero's FILLED `lift` animation (transform),
  // which would otherwise become the containing block and confine this fixed overlay.
  const [mounted, setMounted] = useState(false);
  useEffect(() => { setMounted(true); }, []);

  useEffect(() => {
    // Soft ceiling per phase: idle eases to 30, `profile` to 60, `internships` to 99. Raising the
    // cap on a phase change just lets the existing ease continue upward — no floor snap.
    const cap = step === "internships" ? 99 : step === "profile" ? 60 : 30;
    const tick = () => {
      setPct((p) => (p >= cap ? p : Math.min(p + Math.max((cap - p) * 0.04, 0.3), cap)));
    };
    tick();
    const id = setInterval(tick, TICK_MS);
    return () => clearInterval(id);
  }, [step]);

  const shown = Math.round(pct);
  let idx = 0;
  for (let i = 0; i < STEP_AT.length; i++) if (shown >= STEP_AT[i]) idx = i;
  const [title, desc] = RV_STEPS[idx];

  if (!mounted) return null;
  return createPortal(
    <div className="runveil show" aria-live="polite">
      <div style={{ width: "min(460px,100%)", textAlign: "center" }}>
        <div className="rv-radar" aria-hidden>
          <span className="rv-ring" style={{ width: 50, height: 50 }} />
          <span className="rv-ring" style={{ width: 100, height: 100, animationDelay: ".3s" }} />
          <span className="rv-ring" style={{ width: 150, height: 150, animationDelay: ".6s" }} />
          <span className="rv-sweep" />
          <span className="rv-dot" />
        </div>
        <h2 className="rv-title">{title}</h2>
        <p className="rv-desc">{desc}</p>
        <div className="rv-bar"><i style={{ width: `${shown}%` }} /></div>
        <div className="rv-pct">{shown}% · scanning index</div>
      </div>
    </div>,
    document.body,
  );
}
