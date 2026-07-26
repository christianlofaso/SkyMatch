"""Domain allowlist for learning-resource URLs in roadmap items.

Phase 3 guardrail: roadmap resources may only reference URLs whose host
is on this list. Liveness (async HEAD check) is enforced separately in
backend/lib/resource_validation.py.
"""

from urllib.parse import urlparse

# Suffix match: an entry "github.com" matches "gist.github.com" too.
# Kept deliberately tight (trusted, specific-resource-capable hosts) to prevent hallucinated
# links — but BROAD enough across CS / ML / hardware-EE / general-learning that the roadmap can
# always cite an ON-TOPIC resource. A too-narrow list was the root cause of the audit's misleading
# links: with no Autodesk/EE/ML host allowed, Opus was forced to pair a real-sounding title with a
# wrong-domain URL (a "Fusion 360 docs" link pointing at learn.microsoft.com; MDN Web Serial for a
# PCB gap). The added domains close those topic areas at the source.
ALLOWED_DOMAINS: frozenset[str] = frozenset({
    # General / web / CS
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
    "khanacademy.org",
    "geeksforgeeks.org",
    "w3schools.com",
    "leetcode.com",          # the "sharpen algorithms" gap
    "neetcode.io",
    "digitalocean.com",      # community tutorials (cloud / devops / Linux)
    # Hardware / electrical engineering (the EE-freshman gap pointed at MDN/CS50 before)
    "autodesk.com",          # Fusion 360 (was wrongly cited as a learn.microsoft.com link)
    "arduino.cc",
    "learn.sparkfun.com",
    "sparkfun.com",
    "learn.adafruit.com",
    "adafruit.com",
    "allaboutcircuits.com",
    "circuitdigest.com",
    # ML / data
    "pytorch.org",
    "tensorflow.org",
    "scikit-learn.org",
    "kaggle.com",
    "huggingface.co",
    "deeplearning.ai",
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
