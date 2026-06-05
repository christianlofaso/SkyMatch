"""Domain allowlist for learning-resource URLs in roadmap items.

Phase 3 guardrail: roadmap resources may only reference URLs whose host
is on this list. Liveness (async HEAD check) is enforced separately in
backend/lib/resource_validation.py.
"""

from urllib.parse import urlparse

# Suffix match: an entry "github.com" matches "gist.github.com" too.
ALLOWED_DOMAINS: frozenset[str] = frozenset({
    "react.dev",
    "developer.mozilla.org",
    "freecodecamp.org",
    "fastapi.tiangolo.com",
    "learn.microsoft.com",
    "docs.python.org",
    "roadmap.sh",
    "github.com",
    "youtube.com",
    "coursera.org",
    "edx.org",
    "udemy.com",
    "frontendmasters.com",
    "pluralsight.com",
    "refactoring.guru",
    "joshwcomeau.com",
    "kentcdodds.com",
    "fullstackopen.com",
    "theodinproject.com",
    "cs50.harvard.edu",
    "ocw.mit.edu",
})


def is_allowlisted(url: str) -> bool:
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return False
    if not host:
        return False
    if host.startswith("www."):
        host = host[4:]
    if host in ALLOWED_DOMAINS:
        return True
    return any(host.endswith("." + d) for d in ALLOWED_DOMAINS)
