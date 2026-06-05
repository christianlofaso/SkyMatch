"""Lenient JSON parsing for Claude responses.

Shared by routes/internships.py (Sonnet selection/annotation) and lib/listing_parser.py
(Haiku listing parse). Both ask for "ONLY JSON" but Sonnet (and occasionally Haiku) wrap
the answer in reasoning prose or markdown fences; parse_json_with_context recovers the
embedded value instead of failing at char 0.
"""

import json
import re


def strip_fences(raw: str) -> str:
    """Strip a leading ```/```json fence and trailing commas before } or ]."""
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()
    # Claude sometimes emits trailing commas before } or ] which is invalid JSON
    raw = re.sub(r",\s*([}\]])", r"\1", raw)
    return raw


def extract_json_value(raw: str) -> dict | list | None:
    """Recover the first JSON array/object embedded anywhere in `raw`, or None.

    Models (notably Sonnet) sometimes wrap the answer in reasoning prose —
    "Looking at the listings:\\n\\n1. **Robinhood**..." then the JSON array — despite the
    "respond with ONLY JSON" instruction, which makes a plain json.loads fail at char 0.
    We scan for each '['/'{' and let json's raw_decode try to parse a value there,
    returning the first that succeeds. raw_decode is used (not a bracket-counter) so
    brackets inside string values don't mis-split the document, and any trailing prose
    after the JSON is ignored.
    """
    decoder = json.JSONDecoder()
    for i, ch in enumerate(raw):
        if ch in "[{":
            try:
                obj, _end = decoder.raw_decode(raw, i)
            except json.JSONDecodeError:
                continue  # '[' was inside prose (e.g. a markdown link) — keep scanning
            if isinstance(obj, (list, dict)):
                return obj
    return None


def parse_json_with_context(raw: str, label: str) -> dict | list:
    """json.loads with a prose-recovery fallback; logs context + re-raises if both fail."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        # Fall back to extracting JSON out of prose-wrapped output before giving up.
        recovered = extract_json_value(raw)
        if recovered is not None:
            print(f"[{label}] recovered JSON from prose-wrapped response")
            return recovered
        start = max(0, e.pos - 80)
        end = min(len(raw), e.pos + 80)
        print(f"[{label}] JSON parse error at char {e.pos}: {e.msg}")
        print(f"[{label}] context: ...{raw[start:end]!r}...")
        raise
