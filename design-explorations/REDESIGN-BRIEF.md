# SkyMatch Results-Page Redesign — Shared Builder Brief

Three results-page prototypes explore **how to make SkyMatch a place students return to**, instead of a
one-time ~15-result lookup. Each variant owns one retention mechanic. They share ONE editorial type
system + palette so the comparison is about the *mechanic*, not the skin.

- **option-k** → **New-match alerts** (saved searches + "what's new") — port **3018**
- **option-l** → **Application tracker** (saved → applied → interviewing pipeline) — port **3019**
- **option-m** → **Smarter infinite feed** (endless, learns from save/skip) — port **3020**

Scope: the **results page** (the "Matches" view) inside the app shell. Other nav items may be present
but inert.

---

## 1. HARD CONSTRAINTS — preserve these, design *around* them

- **Three readiness bands**: `Strong matches` / `Worth a look` / `Stretch`, plus a quiet collapsed
  **"Set aside"** block. Don't replace the bands; layer your retention surface around them.
- **Role detail drawer** (right slide-in): Location · Term · Company · **Why you fit** (bullets) ·
  **Skill alignment** (have ✓ / worth shoring up) · actions **Apply / Save / Full analysis**.
- **4-panel app shell**: left sidebar with **Matches / Job-fit Analyzer / Saved / Profile**, brand mark,
  "New match run" button, "Last run" card, user chip.
- **Role row anatomy**: logo · title · `company · location · posted` · 3-bar readiness tier · bookmark.
  Click the row → drawer.
- **Continuous list** (ALL variants): replace "~15 then done" with a **"Load more"** (or scroll-load)
  that appends more roles. No list ever bottoms out.

## 2. THE PROTOTYPE KIT — copy, don't reinvent

Start from **`design-explorations/option-j/`** (the current production look). Copy these into your
`option-{k,l,m}/` folder, then adapt:

- **`serve.mjs`** — copy verbatim, change only `PORT` (your port above) and the `console.log` label.
  Dependency-free; runs with `node serve.mjs`. No package.json needed.
- **`demo-data.js`** — copy `SM_ROLES`, `SM_BANDS`, the `SM` save store, `smLogoHTML`, `smRowHTML`,
  `smBindSaves`, `SMDrawer`, `smBindRows`. **Keep the drawer and row renderers** — extend, don't rewrite.
  Roles already include `band`, `type`, `title`, `company`, `meta`, `facts{location,term,co,posted,...}`,
  `why[]`, `have[]`, `need[]`, `gap?`, `note?`. Logos load from Google's favicon service.
- **`index.html`** — your results page. Base the shell + bands + toolbar on **`option-j/results.html`**
  (read it). Layer your variant's signature surface in.
- **`demo.css`** — copy `option-j/demo.css` as the base (shell `.app/.sidebar/.main`, `.role` rows,
  `.drawer`, `.band-head`, `.stat-card`, tier bars, chips), then apply the editorial type/palette below
  and add your variant's component styles.

Add a **`CONCEPT.md`**: 1 paragraph on the mechanic, what's clickable, and how it drives return visits.

`node serve.mjs` serving a clickable page at your port = done. Verify your JS parses
(`node --check demo-data.js && node --check serve.mjs`) and `index.html` is complete + self-contained.
The orchestrator will serve + screenshot all three.

## 3. SHARED EDITORIAL TYPE SYSTEM (identical in all three)

Fixes the "generic" complaint: drop General Sans/Fontshare entirely; everything below is on Google's CDN.
**Lean on Fraunces so the feed does NOT read generic** — use it for headlines, section eyebrows, AND role
titles. Inter is only for dense meta/secondary/body-UI. Spline Sans Mono for kicker labels + stat figures.

Replace the `<head>` font links with:
```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,400..900;1,9..144,400..900&family=Inter:wght@400;500;600;700&family=Spline+Sans+Mono:wght@400;500;600&display=swap" rel="stylesheet">
```
```css
--display: "Fraunces", "Hoefler Text", Georgia, "Times New Roman", serif;
--body:    "Inter", system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
--mono:    "Spline Sans Mono", ui-monospace, "SF Mono", "JetBrains Mono", Menlo, Consolas, monospace;
```
Treatments that make it editorial (apply these):
- Headlines + role titles: `font-family:var(--display)`, `font-optical-sizing:auto`,
  `font-variation-settings:"SOFT" 30,"WONK" 1`, wght 560–680, `letter-spacing:-.02em`.
- **Italic Fraunces eyebrows** on section/band labels (e.g. *Strong match*), ~14px, `font-style:italic`.
- Body/drawer: Inter 15px / line-height 1.55.
- Stat numbers + counts: Inter with `font-variant-numeric: tabular-nums` (no jitter as they tick).

### Shared palette (dark deep-space, refined — identical in all three)
```css
--bg:        #08090E;
--surface-1: #11131B;   /* cards / rows */
--surface-2: #171A24;   /* raised / drawer */
--border:    rgba(255,255,255,.08);
--text:      #ECEEF3;
--muted:     #9BA2B2;
--accent-ember: #FF8C5A;   /* primary action + kicker rule */
--accent-gold:  #FFD27A;   /* gradient terminus + stat highlight */
--accent-iris:  #8FA2FF;   /* sparing links / focus */
```
Demote mint/cyan to **data only** (readiness tier bars / score chips). Let **ember→gold** be the single
editorial signature so the palette reads intentional, not "rainbow AI."

### Signature detail — the "ember kicker rule" (use it on section headers + your new surface)
```css
.kicker { font-family:var(--mono); font-size:11px; letter-spacing:.18em; text-transform:uppercase;
  color:var(--accent-gold); display:flex; align-items:center; gap:10px; }
.kicker::before { content:""; width:22px; height:2px; border-radius:2px;
  background:linear-gradient(90deg, var(--accent-ember), var(--accent-gold)); }
```
Pair the kicker with an italic Fraunces eyebrow on the next line — that hairline + small-caps mono +
literary italic stack is the memorable fingerprint.

---

## 4. PER-VARIANT SPEC

### option-k — New-match alerts (port 3018)
- **Signature surface**: a **"Your searches" rail** pinned at the top of Matches (above Strong): 2–4
  saved-search chips (e.g. *SWE · Bay Area · Summer*, *Product · Remote*), each with a count pill of new
  roles since last visit + a persistent **"+ Save this search"**. New roles thread into the *existing
  bands* (never their own band) wearing a left accent rail + "New" dot until viewed.
- **What's new**: dismissible ribbon under the rail — `"7 new matches since Tuesday — 3 Strong."`
  Viewing a role clears its dot; empty state is calm: `"All caught up. We check every few hours."`
- **Continuous**: each chip is an infinite query; "Load more" pulls the next page for the active search.
- **Build**: extend demo-data with a `SM_SEARCHES` array + a `isNew` flag on ~6–8 roles; clicking a chip
  filters the feed to that search; the ribbon count = sum of new. Avoid fake urgency / counter inflation.

### option-l — Application tracker (port 3019)  ← retention lens's #1 pick
- **Signature surface**: a collapsible **pipeline strip** docked at the very top — four count tiles
  **Saved · Applied · Interviewing · Closed**. Bands render unchanged below. The **drawer gains a status
  selector** (Saved → Applied → Interviewing) + optional **deadline**; setting status moves the role into
  the pipeline AND tags its row in the bands (e.g. `Applied · Apr 3`). Clicking a tile filters to that stage.
- **What's new**: funnel-state ribbon — `"2 deadlines this week · 1 reply to log."` A soft **"Nudge"** on
  stale saved roles: *"Saved 9 days ago — still open?"* Never auto-mark applied; no shame metrics.
- **Continuous**: "Load more" feeds the bands = fresh intake to push into the pipeline.
- **Build**: extend the `SM` store with `status` + `deadline` per role (localStorage); render the strip,
  the drawer status control, and row status tags; tiles filter. Seed 2–3 roles into Applied/Interviewing.

### option-m — Smarter infinite feed (port 3020)
- **Signature surface**: bands stay as the **curated top tier**; below "Stretch" add a **"More for you"**
  continuous feed that re-ranks from save/skip. Each feed row gets a **"Not for me"** skip beside save and
  an optional 1-line "why" (*"Matches your Python + fintech saves"*). Honest caption: **"Tuned to your saves."**
- **What's new**: a **"Picking up where you left off"** resume marker + `"14 new roles added"` at the
  insertion point; after activity: `"Refreshed your feed from 6 recent saves."` Cold state:
  `"Save or skip a few — your feed sharpens fast."`
- **Continuous**: this IS the continuous variant — scroll-load (with a manual "Load more" fallback), no end.
- **Build**: you need MORE inventory than 15 — synthesize an extended pool of ~30–40 roles (vary company,
  title, location, band, facts) so "load more" has depth. Save/skip visibly nudges ordering. No
  engagement-bait reordering; periodically inject a labeled off-pattern "Worth a stretch" role.

## 5. Cross-cutting touches (fold in where natural)
- A **"since you were last here"** ribbon (one calm line) is the freshness anchor each variant feeds.
- A slim **"Last updated Tue 9:14am"** stamp so the page feels live.
- **Save-state continuity**: saves/skips/statuses persist (localStorage) and reflect instantly in the bands.

Make it real and clickable — drawer opens, saves toggle, your signature interaction works, "Load more"
appends. Self-contained, no build step.
