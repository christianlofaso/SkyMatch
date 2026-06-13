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
    return f"https://www.google.com/s2/favicons?domain={domain}&sz=128"


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
