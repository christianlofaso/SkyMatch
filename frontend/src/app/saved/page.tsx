"use client";
import { useState } from "react";
import { AppShell } from "@/components/AppShell";
import { RoleCard } from "@/components/feed/RoleCard";
import { RoleDrawer } from "@/components/feed/RoleDrawer";
import { useSaved } from "@/lib/useSaved";

// Bookmarked roles (localStorage pf:saved). Saved listings carry no live score/annotation —
// they render with a neutral "Details →" affordance and the drawer shows the listing facts +
// apply link. Re-run the matcher from a card's "Full analysis" for fresh fit reasoning.
export default function SavedPage() {
  const { saved, has, toggle } = useSaved();
  const [openUrl, setOpenUrl] = useState<string | null>(null);
  const openRole = openUrl ? saved.find((r) => r.url === openUrl) ?? null : null;

  return (
    <AppShell active="saved">
      <div className="topbar">
        <div>
          <h1 className="pg">Saved</h1>
          <p className="pg-sub">Roles you bookmarked to revisit.</p>
        </div>
      </div>

      {saved.length === 0 ? (
        <p className="pg-sub" style={{ marginTop: 24 }}>
          No saved roles yet. Tap the bookmark on any role in your feed to keep it here.
        </p>
      ) : (
        <div className="roles" style={{ marginTop: 24 }}>
          {saved.map((r) => (
            <RoleCard
              key={r.url}
              internship={r.internship}
              bucket={r.bucket}
              band={null}
              noScore
              saved={has(r.url)}
              onOpen={() => setOpenUrl(r.url)}
              onToggleSave={() => toggle({ url: r.url, internship: r.internship, bucket: r.bucket })}
            />
          ))}
        </div>
      )}

      <RoleDrawer
        open={!!openRole}
        internship={openRole?.internship ?? null}
        bucket={openRole?.bucket ?? null}
        band={null}
        saved={openRole ? has(openRole.url) : false}
        onClose={() => setOpenUrl(null)}
        onToggleSave={() => { if (openRole) toggle({ url: openRole.url, internship: openRole.internship, bucket: openRole.bucket }); }}
      />
    </AppShell>
  );
}
