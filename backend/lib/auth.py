"""Supabase magic-link auth + per-user daily quota — the gate layer for the
launch (milestone 3).

Verification is STATELESS and local: Supabase issues an HS256 JWT (signed with the
project's `SUPABASE_JWT_SECRET`), and we verify it ourselves (signature + `exp` + `aud`)
rather than calling Supabase per request. The `sub` claim is the user id.

OPTIONAL, like Redis/Voyage
---------------------------
Auth config is OPTIONAL. It turns ON when EITHER is set:
  - `SUPABASE_URL`        → JWKS verification of ES256/RS256 tokens (the modern Supabase
                            default — user session tokens are asymmetric, keyed by `kid`).
  - `SUPABASE_JWT_SECRET` → HS256 verification against the legacy shared secret (fallback;
                            legacy projects + self-signed test tokens).
With NEITHER set (local dev) auth is DISABLED: `optional_user`/`require_user` return None,
the quota deps no-op, and every gated route stays open. Set `SUPABASE_URL` (prod) and gating
goes live with zero code change. This is why `require_user` returns `User | None` — None just
means "auth is off", not "anonymous-but-allowed-through-a-required-gate".

NOTE: HS256-only config CANNOT verify a modern project's user tokens (they're ES256) — set
`SUPABASE_URL` for those. The shared secret correctly verifies the anon/service API keys, so
a "secret matches the anon key" check passes even when real logins would 401.

Dependency shapes (attach per-route in the route decorators)
------------------------------------------------------------
  optional_user  — the single cached worker: decodes the bearer token, upserts the user
                   row, returns User. None when auth is off OR no token; 401 on a present
                   but invalid/expired token. Everything else depends on this (FastAPI
                   caches it per request, so the decode+upsert runs once).
  require_user   — depends on optional_user; 401 when auth is ON and the caller is
                   anonymous. Use on routes that MUST have a signed-in user
                   (/analyze/batch, /internships/annotate).
  quota(kind)    — depends on optional_user; increments the user's daily counter and 429s
                   over the cap. No-op for anonymous (auth off) — the global spend cap is
                   the backstop there.

Quota mapping (see the deploy brainstorm Q6/Q10): one results-page reveal
(POST /analyze/batch) = 1 'matcher'; one full /analyze (Opus Phase 3) = 1 'analysis'.
The lazy /internships/annotate is auth-gated but NOT separately quota'd (a single page
expands many cards). Defaults: 20 matcher + 5 analyses / UTC day.
"""
import os
import time
import asyncio
from dataclasses import dataclass

import jwt
from jwt import PyJWKClient
from fastapi import Depends, HTTPException, Request

from cache import upsert_user, incr_usage


_SECRET = os.getenv("SUPABASE_JWT_SECRET", "").strip()
_ALG = os.getenv("SUPABASE_JWT_ALG", "HS256")
_AUD = os.getenv("SUPABASE_JWT_AUD", "authenticated")

# Modern Supabase projects sign USER SESSION tokens with asymmetric JWT signing keys
# (ES256, keyed by `kid`), NOT the legacy HS256 shared secret — the shared secret only
# signs the anon/service API keys. So we verify against the project's JWKS (public keys),
# selecting the key by `kid`, and keep the HS256 shared-secret path as a fallback for
# legacy projects + self-signed test tokens. JWKS URL is derived from SUPABASE_URL.
_SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
_JWKS_URL = f"{_SUPABASE_URL}/auth/v1/.well-known/jwks.json" if _SUPABASE_URL else ""
_ISSUER = f"{_SUPABASE_URL}/auth/v1" if _SUPABASE_URL else None
_JWKS_TIMEOUT = int(os.getenv("SUPABASE_JWKS_TIMEOUT_SEC", "10"))
_ASYM_ALGS = ("ES256", "RS256")

# Lazy JWKS client singleton — caches the fetched key set (refetched on an unknown kid /
# after `lifespan`), so only the first verify after boot (and post-rotation) hits the network.
_jwks_client: PyJWKClient | None = None


def _get_jwks_client() -> PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = PyJWKClient(_JWKS_URL, timeout=_JWKS_TIMEOUT)
    return _jwks_client

# Per-user daily quotas (UTC day). Env-tunable.
QUOTA_LIMITS = {
    "matcher": int(os.getenv("QUOTA_MATCHER_PER_DAY", "20")),
    "analysis": int(os.getenv("QUOTA_ANALYSIS_PER_DAY", "5")),
}


@dataclass(frozen=True)
class User:
    id: str               # Supabase auth user UUID (JWT `sub`)
    email: str | None
    role: str | None


def auth_enabled() -> bool:
    """True if EITHER the JWKS URL (asymmetric, the modern Supabase default) OR the HS256
    shared secret is configured. When False, every auth dep degrades to anonymous."""
    return bool(_JWKS_URL or _SECRET)


def _utc_day() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


def _bearer_token(request: Request) -> str | None:
    """Extract the Bearer token from the Authorization header (case-insensitive scheme)."""
    auth = request.headers.get("authorization") or ""
    parts = auth.split(None, 1)
    if len(parts) == 2 and parts[0].lower() == "bearer" and parts[1].strip():
        return parts[1].strip()
    return None


def _decode(token: str) -> User:
    """Verify + decode a Supabase JWT. Routes by the token's own `alg` header: ES256/RS256 →
    verify against the project JWKS (public key by `kid`), HS256 → verify against the shared
    secret. Raises jwt.PyJWTError on any failure (bad signature, expired, wrong audience/issuer,
    missing required claim, unknown kid, JWKS fetch error). Blocking (JWKS fetch hits the network
    on a cache miss) — call via asyncio.to_thread."""
    alg = jwt.get_unverified_header(token).get("alg", "")
    if alg in _ASYM_ALGS:
        if not _JWKS_URL:
            raise jwt.InvalidAlgorithmError(
                f"token alg={alg} requires JWKS verification but SUPABASE_URL is not set")
        signing_key = _get_jwks_client().get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token, signing_key.key, algorithms=list(_ASYM_ALGS), audience=_AUD,
            issuer=_ISSUER, options={"require": ["exp", "sub"]},
        )
    else:
        if not _SECRET:
            raise jwt.InvalidAlgorithmError(
                f"token alg={alg} requires the HS256 shared secret but SUPABASE_JWT_SECRET is not set")
        payload = jwt.decode(
            token, _SECRET, algorithms=[_ALG], audience=_AUD,
            options={"require": ["exp", "sub"]},
        )
    return User(id=payload["sub"], email=payload.get("email"), role=payload.get("role"))


async def optional_user(request: Request) -> User | None:
    """Single cached auth worker (see module docstring). None when auth is off or no token;
    401 on a present-but-invalid token; otherwise the verified User (and its row is upserted)."""
    if not auth_enabled():
        return None
    token = _bearer_token(request)
    if not token:
        return None
    try:
        # to_thread: _decode is blocking (JWKS network fetch on a cache miss).
        user = await asyncio.to_thread(_decode, token)
    except jwt.PyJWTError as e:
        # Log the SPECIFIC reason — the client only ever sees the generic message, so an
        # otherwise-opaque 401 (expired vs bad-signature vs wrong-aud vs immature/clock-skew)
        # is undiagnosable without this. ExpiredSignatureError → refresh/expiry; ImmatureSignature
        # /iat-in-future → clock skew; InvalidSignatureError → wrong secret; InvalidAudienceError → aud.
        print(f"[auth] JWT verify failed: {type(e).__name__}: {e}")
        raise HTTPException(status_code=401, detail="Invalid or expired session. Please sign in again.")
    # Upsert is a blocking DB call → off the event loop. Failure here must not 401 a valid
    # token (identity is verified already), so swallow + log.
    try:
        await asyncio.to_thread(upsert_user, user.id, user.email)
    except Exception as e:
        print(f"[auth] upsert_user failed (non-fatal): {e}")
    return user


async def require_user(user: User | None = Depends(optional_user)) -> User | None:
    """Gate that REQUIRES a signed-in user when auth is enabled. Returns None when auth is
    off (anonymous allowed — dev); 401 when auth is on and the caller is anonymous."""
    if auth_enabled() and user is None:
        raise HTTPException(status_code=401, detail="Please sign in to continue.")
    return user


async def enforce_quota(user: User | None, kind: str) -> None:
    """Increment a user's daily counter for `kind` and 429 over the cap. No-op for
    anonymous callers (auth off) — the global spend cap is the backstop there. Increments
    BEFORE the LLM fires; fails OPEN on a quota-store hiccup so it can't block a paying user.
    Call directly when the charge is conditional (e.g. only full-mode /analyze), or via the
    `quota(kind)` dependency for an unconditional route gate."""
    if user is None:
        return  # auth off / anonymous → not quota'd here
    limit = QUOTA_LIMITS[kind]
    try:
        count = await asyncio.to_thread(incr_usage, user.id, _utc_day(), kind)
    except Exception as e:
        print(f"[auth] quota incr failed (fail-open) kind={kind}: {e}")
        return
    if count > limit:
        raise HTTPException(
            status_code=429,
            detail=f"Daily limit reached ({limit} {kind} runs). Try again tomorrow.",
        )


def quota(kind: str):
    """Build an unconditional per-route quota dependency for `kind` ('matcher'|'analysis').
    Use on routes where every call should be charged (e.g. /analyze/batch, /analyze/stream)."""
    async def _enforce(user: User | None = Depends(optional_user)) -> None:
        await enforce_quota(user, kind)

    return _enforce
