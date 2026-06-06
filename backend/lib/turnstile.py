"""Cloudflare Turnstile verification — bot protection on the expensive endpoints.

OPTIONAL, like the rest of the launch plumbing: when `TURNSTILE_SECRET` is unset the
`verify_turnstile` dependency is a no-op (every request passes), so local dev and the
current flow are unchanged. Set the secret (prod) and the gated routes start requiring a
valid Turnstile token in the `X-Turnstile-Token` header.

Failure policy:
  * Enabled + missing/empty token            -> 403 (the client must solve the challenge).
  * Enabled + Cloudflare says success=false  -> 403 (fail CLOSED on a definitive reject).
  * Enabled + network/timeout to Cloudflare  -> PASS (fail OPEN + log; a siteverify outage
    must not 403 real users — the per-IP rate limit + spend cap + auth still backstop).
"""
import os

import httpx
from fastapi import HTTPException, Request

_SECRET = os.getenv("TURNSTILE_SECRET", "").strip()
_VERIFY_URL = os.getenv(
    "TURNSTILE_VERIFY_URL", "https://challenges.cloudflare.com/turnstile/v0/siteverify"
)
_TIMEOUT_SEC = float(os.getenv("TURNSTILE_TIMEOUT_SEC", "5"))


def is_enabled() -> bool:
    return bool(_SECRET)


def _client_ip(request: Request) -> str | None:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    client = getattr(request, "client", None)
    return getattr(client, "host", None)


async def verify_turnstile(request: Request) -> None:
    """FastAPI dependency. No-op when disabled; otherwise validates the X-Turnstile-Token
    header against Cloudflare siteverify (see module docstring for the failure policy)."""
    if not is_enabled():
        return
    token = (request.headers.get("x-turnstile-token") or "").strip()
    if not token:
        raise HTTPException(status_code=403, detail="Bot check required. Please refresh and try again.")

    data = {"secret": _SECRET, "response": token}
    ip = _client_ip(request)
    if ip:
        data["remoteip"] = ip
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SEC) as client:
            resp = await client.post(_VERIFY_URL, data=data)
        ok = bool(resp.json().get("success"))
    except Exception as e:
        # Fail OPEN: don't let a siteverify outage 403 everyone.
        print(f"[turnstile] siteverify error (fail-open): {e}")
        return
    if not ok:
        raise HTTPException(status_code=403, detail="Bot check failed. Please refresh and try again.")
