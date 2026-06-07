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

# ── Workday big-tech pool ────────────────────────────────────────────────────
# Large-cap tech companies whose internships live on Workday (the majority of the
# mega-cap set — Apple/Microsoft are on proprietary portals with no public API and are
# intentionally excluded). These feed the SAME national big_tech bucket as _BIGTECH_ATS_CONFIG.
#
# Workday exposes an UNAUTHENTICATED public JSON API ("CXS"):
#   POST https://{tenant}.{wdN}.myworkdayjobs.com/wday/cxs/{tenant}/{siteId}/jobs
#   body {"appliedFacets":{},"limit":20,"offset":0,"searchText":"intern"}
# → {total, jobPostings[{title, externalPath, locationsText, ...}]}. lib.ingest_core
# ._fetch_workday_listings iterates these. The public job URL is
#   https://{tenant}.{wdN}.myworkdayjobs.com/{siteId}{externalPath}.
#
# Each (company, tenant, wdN, siteId) below was VERIFIED live against the CXS jobs endpoint.
# A wrong tenant/wdN/siteId silently yields 0 (same trap as a wrong REACH_ATS_SLUGS slug) —
# never guess; confirm with scripts/discover_workday_tenants.py (it prints a tuple only on a
# live 200). wdN (the shard, wd1/wd3/wd5/...) and siteId vary per company and can drift.
# NOTE: the CXS response's `total` field is unreliable (some tenants report 0 while still
# returning real postings), and `searchText="intern"` is honored by some tenants but ignored by
# others (they return the whole board) — so _fetch_workday_listings always client-filters titles
# and bounds pages scanned. The intern counts below are point-in-time (verified June 2026); a
# real board with 0 interns now is seasonal and will populate when a cohort posts.
WORKDAY_CONFIG: list[tuple[str, str, str, str]] = [
    # — producing CS/eng intern roles now —
    ("Nvidia",          "nvidia",        "wd5",  "NvidiaExternalCareerSite"),  # ~27
    ("Intel",           "intel",         "wd1",  "External"),                  # ~31
    ("Analog Devices",  "analogdevices", "wd1",  "External"),                  # ~20
    ("Applied Materials","amat",         "wd1",  "External"),                  # ~9
    ("Micron",          "micron",        "wd1",  "External"),                  # ~5
    ("Adobe",           "adobe",         "wd5",  "external_experienced"),      # ~4 (external_university is empty)
    ("Autodesk",        "autodesk",      "wd1",  "uni"),                       # ~4 (university board)
    ("KLA",             "kla",           "wd1",  "Search"),                    # ~2
    ("Cisco",           "cisco",         "wd5",  "Cisco_Careers"),             # ~1
    # — real boards, 0 interns this cycle (seasonal — will populate on next cohort) —
    ("Broadcom",        "broadcom",      "wd1",  "External_Career"),
    ("CrowdStrike",     "crowdstrike",   "wd5",  "CrowdStrikeCareers"),
    ("Salesforce",      "salesforce",    "wd12", "External_Career_Site"),
    ("PayPal",          "paypal",        "wd1",  "jobs"),
    ("Workday",         "workday",       "wd5",  "workday"),
    # NOT reachable via Workday (excluded): Apple/Microsoft (proprietary, no public API);
    # AMD (iCIMS), Lam Research (Eightfold), Palo Alto Networks + ServiceNow (SmartRecruiters),
    # Synopsys (Avature), Oracle + Fortinet + Texas Instruments (Oracle Cloud HCM), IBM + Intuit +
    # Snowflake (custom portals). Qualcomm is on Workday but its public siteId returns 0 postings —
    # re-resolve with scratch/discover_workday_tenants.py if it should be added.
]
