"use client";
import { useCallback, useEffect, useState } from "react";
import type { Internship } from "@/types/skymatch";
import type { BucketKey } from "@/lib/storage";

// Bookmarked roles, persisted to localStorage (pf:saved). We store the FULL listing (+ its
// bucket) keyed by application_url, so the Saved page can render a card without the originating
// run still being around. Ported from option-j's SM save store, but keyed by url (the stable
// production identifier) instead of the demo's synthetic role ids.
export interface SavedRole {
  url: string;
  internship: Internship;
  bucket: BucketKey;
  savedAt: number;
}

const KEY = "pf:saved";
const EVT = "pf:saved-change"; // same-tab cross-component sync (storage event only fires cross-tab)

function read(): SavedRole[] {
  if (typeof window === "undefined") return [];
  try {
    const v = JSON.parse(window.localStorage.getItem(KEY) || "[]");
    return Array.isArray(v) ? v : [];
  } catch {
    return [];
  }
}

function write(list: SavedRole[]): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(KEY, JSON.stringify(list));
  } catch {
    /* quota / disabled storage — best effort */
  }
  window.dispatchEvent(new Event(EVT));
}

export function useSaved() {
  const [list, setList] = useState<SavedRole[]>([]);

  useEffect(() => {
    const sync = () => setList(read());
    sync();
    window.addEventListener(EVT, sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener(EVT, sync);
      window.removeEventListener("storage", sync);
    };
  }, []);

  const has = useCallback((url: string) => list.some((r) => r.url === url), [list]);

  const toggle = useCallback((role: Omit<SavedRole, "savedAt">) => {
    const cur = read();
    const exists = cur.some((r) => r.url === role.url);
    write(exists ? cur.filter((r) => r.url !== role.url) : [...cur, { ...role, savedAt: Date.now() }]);
    return !exists;
  }, []);

  const remove = useCallback((url: string) => {
    write(read().filter((r) => r.url !== url));
  }, []);

  return { saved: list, has, toggle, remove, count: list.length };
}
