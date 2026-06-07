"""Ingestion config for the national-vs-metro serving model. Pure data; the worker
(worker/ingest.py) iterates these and the serving path (routes/internships.py) reads them.

Three "national" buckets (startup, big_tech, reach) are metro-independent and served to
every user from one shared pool. `local` is the only per-metro pool; the worker refreshes
the metros in the rotation (cache.metro_rotation, seeded with SEED_METROS), and serving
live-fetches + promotes any uncovered metro on first request.

The scalar fields below map straight onto the ProfileAnalysis fields the scrapers actually
read (field_of_interest, major, technical_skills, location); nothing else matters to discovery.
"""
from dataclasses import dataclass

# ── National pool (startup + big_tech) ──────────────────────────────────────
# Reserved niche_key for the metro-independent startup/big_tech pool.
NATIONAL_NICHE_KEY = "_national"


@dataclass(frozen=True)
class NationalField:
    field: str                     # → profile.field_of_interest (drives scrape queries)
    major: str | None = None       # → profile.major (startup scrape; falls back to field)
    skills: tuple[str, ...] = ()    # → profile.technical_skills (first 2 used by startup scrape)


# Broadened beyond CS so the national pool isn't CS-only. The worker scrapes startup +
# big_tech once per field and unions/dedups by URL. Easily extended/edited.
NATIONAL_FIELDS: list[NationalField] = [
    NationalField("Computer Science",       "Computer Science",       ("Python", "C++")),
    NationalField("Computer Engineering",   "Computer Engineering",   ("Python", "C++")),
    NationalField("Electrical Engineering", "Electrical Engineering", ("Verilog", "C")),
    NationalField("Software Engineering",   "Computer Science",       ("Python", "JavaScript")),
    NationalField("Machine Learning",       "Computer Science",       ("Python", "PyTorch")),
    NationalField("Data Science",           "Statistics",             ("Python", "SQL")),
]

# ── Per-metro local pool ────────────────────────────────────────────────────
# Initial rotation. These are already canonical `_parse_metro` outputs, so they round-trip
# (the worker feeds each back in as a synthetic profile location). Serving promotes new
# metros into the rotation table on first request.
SEED_METROS: list[str] = [
    "Chicago", "New York", "San Francisco", "Los Angeles", "Seattle", "Boston",
    "Austin", "Denver", "Atlanta", "Miami", "Washington", "Philadelphia", "Houston",
    "Phoenix", "Portland", "Minneapolis", "Detroit", "Pittsburgh", "Raleigh", "Dallas",
    "San Diego", "San Jose", "Salt Lake City", "Orlando", "Nashville", "Charlotte",
    "Columbus", "Madison", "Indianapolis", "Kansas City",
]

# ── Reach pool ──────────────────────────────────────────────────────────────
# Reserved niche_key for the aspirational/elite pool the reach bucket draws from. Reach is
# niche-independent (the "reach" judgment is made per-user at serving time), so one shared
# pool serves everyone.
REACH_NICHE_KEY = "_reach"

# Elite companies with public Greenhouse/Lever/Ashby boards, in the (company, provider, slug)
# shape _fetch_ats_listings expects. Unknown/closed slugs simply yield nothing (handled
# gracefully), so this list is safe to extend.
#
# Each (provider, slug) below was verified live against the provider's public API. Caveats:
#   - Slugs must point at a board the public API actually serves. Snowflake (Workday/Eightfold)
#     and Ramp (Ashby board returns 0 postings) have NO usable public ATS API, so they were
#     dropped — they yielded 0 every pass. Anthropic is on GREENHOUSE ("anthropic"), not Ashby
#     (the old "ashby/Anthropic" 404'd every pass).
#   - A board returning 0 interns *right now* is normal (seasonal — e.g. Anthropic has the board
#     but no open internships this cycle); it'll yield once they post. The dead entries above
#     were 404/empty at the API level, which is different.
# To add a company: confirm its public board serves intern roles via the provider API before
# adding (don't guess the slug — a wrong slug silently yields 0, exactly the bug this replaced).
REACH_ATS_SLUGS: list[tuple[str, str, str]] = [
    ("Stripe",     "greenhouse", "stripe"),
    ("Databricks", "greenhouse", "databricks"),
    ("Palantir",   "lever",      "palantir"),
    ("Anthropic",  "greenhouse", "anthropic"),   # was ashby/"Anthropic" (404); Anthropic is on Greenhouse
    ("Cloudflare", "greenhouse", "cloudflare"),  # replaces Snowflake (no public ATS API)
    ("Verkada",    "greenhouse", "verkada"),     # replaces Ramp (Ashby board serves 0 postings)
    ("Pinterest",  "greenhouse", "pinterest"),
]
