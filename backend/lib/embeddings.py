"""Shared Voyage AI embeddings client.

Used in two places:
  - worker/ingest.py parse pass — embed each listing ONCE (input_type="document").
  - routes/internships.py serving — embed the profile ONCE per request
    (input_type="query") to cosine-rank candidates before the slim Sonnet SELECT.

OPTIONAL by design (mirrors lib/firecrawl.py's availability guard): when VOYAGE_API_KEY
is absent or the voyageai package isn't installed, is_available() is False, the embed_*
functions return None, and callers fall back to the non-ranked path. Nothing breaks.

Vectors are NORMALIZED at both store and query time, so a serve-time cosine similarity
is a plain dot product. Stored as raw float32 bytes (to_bytes/from_bytes); the
authoritative dimension is the returned vector length, persisted per row.
"""

import os

import numpy as np

try:  # optional dep — guarded so importing this module never hard-fails the route
    import voyageai
except ImportError:  # pragma: no cover - exercised only before `pip install`
    voyageai = None

# ── Env config (captured at import, like lib/firecrawl.py; source .env before launch) ──
API_KEY     = os.getenv("VOYAGE_API_KEY", "")
EMBED_MODEL = os.getenv("EMBED_MODEL", "voyage-3.5")
_BATCH      = 128  # Voyage accepts up to 128 texts per embed request

_client = None


def _get_client():
    """Lazily build the Voyage client. Returns None when unavailable."""
    global _client
    if _client is None:
        if not is_available():
            return None
        _client = voyageai.Client(api_key=API_KEY)
    return _client


def is_available() -> bool:
    """True when a Voyage key is configured AND the SDK is importable."""
    return bool(API_KEY) and voyageai is not None


def _normalize(vec) -> np.ndarray:
    """L2-normalize to a float32 unit vector (zero-vector passes through unchanged)."""
    arr = np.asarray(vec, dtype=np.float32)
    norm = float(np.linalg.norm(arr))
    if norm > 0:
        arr = arr / norm
    return arr.astype(np.float32)


def to_bytes(vec: np.ndarray) -> bytes:
    """Serialize a vector to the raw float32 bytes stored in listing_store.embedding."""
    return np.asarray(vec, dtype=np.float32).tobytes()


def from_bytes(blob: bytes) -> np.ndarray:
    """Deserialize stored embedding bytes back to a float32 vector."""
    return np.frombuffer(blob, dtype=np.float32)


def embed_documents(texts: list[str]) -> list[np.ndarray] | None:
    """Embed listing texts (input_type="document"), normalized, order-aligned with `texts`.

    Returns None when embeddings are unavailable. Chunks into <=128/request. Raises on
    Voyage API error so the caller can decide (the worker logs + stores parse without an
    embedding rather than aborting the run)."""
    client = _get_client()
    if client is None or not texts:
        return None if client is None else []
    out: list[np.ndarray] = []
    for i in range(0, len(texts), _BATCH):
        chunk = texts[i:i + _BATCH]
        res = client.embed(chunk, model=EMBED_MODEL, input_type="document")
        out.extend(_normalize(v) for v in res.embeddings)
    return out


def embed_query(text: str) -> np.ndarray | None:
    """Embed one query text (input_type="query"), normalized. None when unavailable."""
    client = _get_client()
    if client is None:
        return None
    res = client.embed([text], model=EMBED_MODEL, input_type="query")
    return _normalize(res.embeddings[0])
