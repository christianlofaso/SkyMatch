"""Supabase magic-link auth + per-user daily quota — the gate layer for the
launch (milestone 3).

Verification is STATELESS and local: Supabase issues an HS256 JWT (signed with the
project's `SUPABASE_JWT_SECRET`), and we verify it ourselves (signature + `exp` + `aud`)
rather than calling Supabase per request. The `sub` claim is the user id.

OPTIONAL, like Redis/Voyage
---------------------------
`SUPABASE_JWT_SECRET` is OPTIONAL. When it is unset (local dev / current setup) auth is
DISABLED: `optional_user`/`require_user` return None, the quota deps no-op, and every
gated route stays open exactly as before. Set the secret (prod) and gating goes live with
zero code change. This is why `require_user` returns `User | None` — None just means
"auth is off", not "anonymous-but-allowed-through-a-required-gate".

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
from fastapi import Depends, HTTPException, Request

from cache import upsert_user, incr_usage


_SECRET = os.getenv("SUPABASE_JWT_SECRET", "").strip()
_ALG = os.getenv("SUPABASE_JWT_ALG", "HS256")
_AUD = os.getenv("SUPABASE_JWT_AUD", "authenticated")

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
    """True if a JWT secret is configured. When False, every auth dep degrades to anonymous."""
    return bool(_SECRET)


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
    """Verify + decode a Supabase JWT. Raises jwt.PyJWTError on any failure (bad signature,
    expired, wrong audience, missing required claim)."""
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
        user = _decode(token)
    except jwt.PyJWTError:
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
