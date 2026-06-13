"use client";
import { useEffect, useRef } from "react";

// Scroll-reveal: watches every `.reveal` element under the returned ref and adds `.in`
// the first time it enters the viewport (ported from option-j index.html — same
// threshold/rootMargin). Reduced-motion users see content immediately via the CSS override.
export function useReveal<T extends HTMLElement>() {
  const ref = useRef<T>(null);

  useEffect(() => {
    const root = ref.current;
    if (!root) return;
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) {
            e.target.classList.add("in");
            io.unobserve(e.target);
          }
        }
      },
      { threshold: 0.12, rootMargin: "0px 0px -8% 0px" },
    );
    root.querySelectorAll(".reveal").forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, []);

  return ref;
}
