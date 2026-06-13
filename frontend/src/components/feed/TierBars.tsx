import type { Band } from "@/lib/bands";

// Three bars; the band class lights 3 (strong) / 2 (look) / 1 (stretch) via globals.css.
export function TierBars({ band }: { band: Band }) {
  return (
    <span className={`tier ${band}`} aria-hidden>
      <i />
      <i />
      <i />
    </span>
  );
}
