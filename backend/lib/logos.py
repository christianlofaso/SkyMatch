"""Company logo resolution for internship feed cards — profile-independent, no LLM, no key.

Each card's `logo_url` is built here from the resolved company name + the listing's application
URL. This module only constructs a URL STRING — it makes no network call; the browser fetches
the actual image via the <img> tag, and the frontend falls back to a letter avatar whenever
logo_url is null OR the image fails to load.

Strategy — curated map + safe fallback (no wrong logos, no API key):
  1. Curated company -> domain map for the companies we ship in the big_tech + reach pools
     (config/niches.py) plus the universally-known mega-caps. These get a real, correct logo.
  2. Otherwise, if the listing's OWN host is a company-owned career page (NOT a known ATS or
     aggregator), use that host's favicon — a careers.acme.com / jobs.acme.com host IS the
     company, so its favicon is the company's logo.
  3. Otherwise None. The ATS-host trap: boards.greenhouse.io / jobs.lever.co / *.myworkdayjobs.com
     favicons are the PLATFORM's logo, never the hiring company's — so we decline and let the
     letter avatar show rather than display a wrong logo.

Logos come from Google's keyless favicon service, which returns crisp square brand icons that
suit a square avatar box. To upgrade quality later (transparent logos, name-based lookup) swap
`_favicon` for a logo.dev / Brandfetch URL — this is the single call site.
"""
from urllib.parse import urlsplit


def _favicon(domain: str) -> str:
    # Google's favicon service is RELIABLE for confident/real domains (returns the brand favicon);
    # it only substitutes a globe for an UNRESOLVABLE domain, which a confident domain isn't. We use
    # it for the curated map + listing-extracted domains. (unavatar was tried but returns a 0-byte
    # 200 for some real domains, e.g. adobe.com → a broken image; it's reserved for the frontend's
    # uncertain slug-guess, where its honest error lets the chain fall through to the letter avatar.)
    return f"https://www.google.com/s2/favicons?domain={domain}&sz=128"


def favicon_url(domain: str) -> str:
    """Public logo URL for a CONFIDENT (real) domain — the curated map or a listing-extracted
    company domain. See _favicon for why Google (not unavatar) is used for confident domains."""
    return _favicon(domain)


def registrable_domain(url: str | None) -> str | None:
    """The registrable domain of a URL ("https://www.terminal.io/careers" → "terminal.io"), or
    None. Used to turn a company's OWN website (recovered from the listing page) into a logo
    domain — the exact signal a name-search can't guess for a generic name like "Terminal"."""
    host = _host(url)
    if not host:
        return None
    parts = host.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


# Curated company -> primary domain. Keyed by the lowercased company name AS IT APPEARS on our
# listings (config/niches.py: REACH_ATS_SLUGS + WORKDAY_CONFIG), plus the mega-caps users
# recognize. Extend freely — a missing entry just falls through to the safe URL-host path.
_COMPANY_DOMAINS: dict[str, str] = {
    # reach pool (REACH_ATS_SLUGS)
    "stripe": "stripe.com",
    "databricks": "databricks.com",
    "palantir": "palantir.com",
    "anthropic": "anthropic.com",
    "cloudflare": "cloudflare.com",
    "verkada": "verkada.com",
    "pinterest": "pinterest.com",
    # big_tech Workday pool (WORKDAY_CONFIG)
    "nvidia": "nvidia.com",
    "intel": "intel.com",
    "analog devices": "analog.com",
    "applied materials": "appliedmaterials.com",
    "micron": "micron.com",
    "adobe": "adobe.com",
    "autodesk": "autodesk.com",
    "kla": "kla.com",
    "cisco": "cisco.com",
    "broadcom": "broadcom.com",
    "crowdstrike": "crowdstrike.com",
    "salesforce": "salesforce.com",
    "paypal": "paypal.com",
    "workday": "workday.com",
    # mega-caps reachable via amazon.jobs / other big_tech config + universally known
    "amazon": "amazon.com",
    "apple": "apple.com",
    "microsoft": "microsoft.com",
    "google": "google.com",
    "meta": "meta.com",
    "oracle": "oracle.com",
    "ibm": "ibm.com",
    "intuit": "intuit.com",
    "qualcomm": "qualcomm.com",
    "amd": "amd.com",
    "netflix": "netflix.com",
    "snowflake": "snowflake.com",
    "servicenow": "servicenow.com",
    "palo alto networks": "paloaltonetworks.com",
    "synopsys": "synopsys.com",
    "texas instruments": "ti.com",
    "lam research": "lamresearch.com",
    "fortinet": "fortinet.com",
}


# Hosts that are ATS boards or job aggregators — their favicon is the PLATFORM's logo, never the
# hiring company's. When the listing URL sits on one of these we decline (return None) rather than
# show a wrong logo. Matched as an exact host OR a registrable-domain suffix (so every subdomain
# of, e.g., greenhouse.io is covered).
_ATS_AGGREGATOR_HOSTS: frozenset[str] = frozenset({
    "greenhouse.io", "lever.co", "ashbyhq.com",
    "myworkdayjobs.com", "myworkdaysite.com",
    "icims.com", "smartrecruiters.com", "eightfold.ai", "avature.net",
    "oraclecloud.com", "taleo.net", "jobvite.com", "breezy.hr",
    "workatastartup.com", "wellfound.com", "angel.co",
    "linkedin.com", "indeed.com", "glassdoor.com", "ziprecruiter.com",
    "simplyhired.com", "dice.com", "builtin.com", "lensa.com", "jobright.ai",
    "google.com", "duckduckgo.com", "bing.com",   # search-result URLs
    "amazon.jobs",   # Amazon is curated above; block the raw host so a non-curated path can't favicon the ATS
})


def _host(url: str | None) -> str | None:
    if not url:
        return None
    try:
        host = (urlsplit(url).hostname or "").lower()
    except Exception:
        return None
    if host.startswith("www."):
        host = host[4:]
    return host or None


def _is_ats_or_aggregator(host: str) -> bool:
    return any(host == h or host.endswith("." + h) for h in _ATS_AGGREGATOR_HOSTS)


# Generic trailing corporate tokens dropped (one at a time, from the right) when an exact
# curated lookup misses — so "Palantir Technologies" / "Cisco Systems Inc" still hit the map.
# A stripped candidate is accepted ONLY if it is itself a curated key, so this never mangles a
# legitimately multi-word entry like "Analog Devices" or "Palo Alto Networks".
_GENERIC_CORP_TOKENS: frozenset[str] = frozenset({
    "technologies", "technology", "labs", "inc", "inc.", "corp", "corp.", "corporation",
    "co", "co.", "llc", "ltd", "ltd.", "limited", "plc", "holdings", "group", "systems",
    "software", "global",
})


def curated_domain(company: str | None) -> str | None:
    """The curated primary domain for a known company, or None. Exposed for the server-side
    logo resolver (lib/logo_resolver) as the trusted-domain source between the listing-extracted
    domain and a logo.dev name search.

    Falls back to dropping trailing generic corporate tokens ("Palantir Technologies" ->
    "palantir") so the big curated names resolve WITHOUT depending on the logo.dev search key —
    accepting a shortened form only when it is itself curated, so a multi-word entry like
    "Analog Devices" is never mangled."""
    key = (company or "").strip().lower()
    if not key:
        return None
    if key in _COMPANY_DOMAINS:
        return _COMPANY_DOMAINS[key]
    tokens = key.split()
    while len(tokens) > 1 and tokens[-1] in _GENERIC_CORP_TOKENS:
        tokens = tokens[:-1]
        cand = " ".join(tokens)
        if cand in _COMPANY_DOMAINS:
            return _COMPANY_DOMAINS[cand]
    return None


def logo_url_for(company: str | None, application_url: str | None = None) -> str | None:
    """Best-effort logo URL for a feed card, or None to fall back to the letter avatar.

    Curated company -> domain first; else the listing's own host when it's a company-owned
    career page (not an ATS/aggregator); else None. Never returns a known-wrong (ATS) logo.
    """
    domain = _COMPANY_DOMAINS.get((company or "").strip().lower())
    if domain:
        return _favicon(domain)
    host = _host(application_url)
    if host and not _is_ats_or_aggregator(host):
        return _favicon(host)
    return None
