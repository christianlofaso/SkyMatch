"""Cost-protection gate for the LLM-firing routes — per-IP rate limiting + a
spend-cap kill switch, exposed as the FastAPI dependency `cost_guard`.

Why a dependency and not Starlette middleware: `BaseHTTPMiddleware` buffers/breaks
the ndjson `StreamingResponse` of /analyze/batch and /internships/annotate. A
`yield`-dependency's teardown instead runs AFTER the stream is exhausted, so the
in-flight concurrent counter is released at the right time.

State is in-process (a dict in the event-loop thread — no locks needed) and so is
SINGLE-WORKER ONLY, consistent with the existing sonnet_sem governor. A multi-worker
deploy would need a shared store (Redis); see CLAUDE.md. The manual kill switch IS
persistent (app_flags table) so an emergency halt survives a restart.

Attached to the gated routers in main.py via dependencies=[Depends(cost_guard)];
/health, /cost/summary and /admin/* are intentionally NOT gated so observability and
recovery stay reachable while a halt is active.
"""
import asyncio
import os
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from cache import get_flag, sum_spend_since


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


# Per-IP rate limit (sized so a normal session — 1 /run + 1 /analyze/batch + a few
# lazy /annotate expands — never trips). All env-tunable.
RATE_LIMIT_PER_MIN = _int_env("RATE_LIMIT_PER_MIN", 30)
RATE_LIMIT_CONCURRENT = _int_env("RATE_LIMIT_CONCURRENT", 4)
RATE_LIMIT_WINDOW_SEC = _int_env("RATE_LIMIT_WINDOW_SEC", 60)

# Spend-cap kill switch. SPEND_CAP_USD_DAILY <= 0 disables the automatic halt.
SPEND_CAP_USD_DAILY = _float_env("SPEND_CAP_USD_DAILY", 0.0)
SPEND_CAP_WINDOW_SEC = _int_env("SPEND_CAP_WINDOW_SEC", 24 * 3600)
SPEND_CACHE_TTL_SEC = _int_env("SPEND_CACHE_TTL_SEC", 30)

# In-memory per-IP state (event-loop thread only).
_window: dict[str, deque] = defaultdict(deque)   # ip -> recent request timestamps
_inflight: dict[str, int] = defaultdict(int)     # ip -> concurrent in-flight count

# Rolling-spend cache so the SUM aggregate isn't a per-request DB hit.
_spend_checked_at = 0.0
_spend_value = 0.0


def client_ip(request: Request) -> str:
    """Caller IP — first hop of X-Forwarded-For (deploy is behind a proxy) else the
    direct peer. Falls back to 'unknown' so a missing client never crashes the gate."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    client = getattr(request, "client", None)
    return getattr(client, "host", None) or "unknown"


def _over_spend_cap() -> bool:
    """True if rolling-window spend has reached the cap. Cached for SPEND_CACHE_TTL_SEC.
    Fails OPEN on a DB error — a transient cache hiccup must not 503 all traffic."""
    global _spend_checked_at, _spend_value
    if SPEND_CAP_USD_DAILY <= 0:
        return False
    now = time.time()
    if now - _spend_checked_at >= SPEND_CACHE_TTL_SEC:
        try:
            _spend_value = sum_spend_since(int(now) - SPEND_CAP_WINDOW_SEC)
        except Exception as e:
            print(f"[guard] spend-cap query failed (fail-open): {e}")
            return False
        _spend_checked_at = now
    return _spend_value >= SPEND_CAP_USD_DAILY


def _halt_reason() -> str | None:
    """Return a user-facing halt message if the kill switch is engaged, else None.
    Manual flag is read per-request (cheap PK lookup) for near-instant toggle; the
    automatic spend cap uses the cached rolling total."""
    try:
        if get_flag("kill_switch") == "on":
            return "Service is temporarily paused. Please try again later."
    except Exception as e:
        print(f"[guard] kill-switch flag read failed (fail-open): {e}")
    if _over_spend_cap():
        return "Service is temporarily paused (daily capacity reached). Please try again later."
    return None


def _reserve(ip: str) -> tuple[bool, str]:
    """Atomically (single event-loop thread) apply the rate + concurrency checks and,
    if allowed, reserve a slot. Returns (allowed, reject_detail)."""
    now = time.time()
    win = _window[ip]
    cutoff = now - RATE_LIMIT_WINDOW_SEC
    while win and win[0] < cutoff:
        win.popleft()

    if _inflight[ip] >= RATE_LIMIT_CONCURRENT:
        return False, "Too many requests in flight. Please wait a moment and retry."
    if len(win) >= RATE_LIMIT_PER_MIN:
        return False, "Rate limit exceeded. Please slow down and try again shortly."

    win.append(now)
    _inflight[ip] += 1
    return True, ""


def _release(ip: str) -> None:
    n = _inflight.get(ip, 0) - 1
    if n <= 0:
        _inflight.pop(ip, None)
        # Drop the window deque too if nothing recent, to bound memory.
        if not _window.get(ip):
            _window.pop(ip, None)
    else:
        _inflight[ip] = n


async def cost_guard(request: Request):
    """Dependency for LLM-firing routes: halt on kill switch (503), enforce per-IP
    rate + concurrency limits (429), and account for the in-flight request."""
    # _halt_reason does blocking Postgres reads (get_flag + the cached spend sum) — run it
    # off the event loop so a slow DB round-trip can't stall other in-flight requests. One
    # thread hop per gated request covers both reads. (status_snapshot stays sync: it's
    # only called from the sync /admin/status route, which FastAPI already threadpools.)
    reason = await asyncio.to_thread(_halt_reason)
    if reason:
        raise HTTPException(status_code=503, detail=reason)

    ip = client_ip(request)
    allowed, detail = _reserve(ip)
    if not allowed:
        raise HTTPException(status_code=429, detail=detail)

    try:
        yield
    finally:
        _release(ip)


def status_snapshot() -> dict:
    """Read-only view for GET /admin/status — current limits + rolling spend."""
    now = time.time()
    try:
        spend = sum_spend_since(int(now) - SPEND_CAP_WINDOW_SEC)
    except Exception as e:
        spend = -1.0
        print(f"[guard] status spend query failed: {e}")
    return {
        "kill_switch": get_flag("kill_switch") or "off",
        "spend_window_usd": round(spend, 4),
        "spend_cap_usd": SPEND_CAP_USD_DAILY,
        "spend_cap_window_sec": SPEND_CAP_WINDOW_SEC,
        "rate_limit_per_min": RATE_LIMIT_PER_MIN,
        "rate_limit_concurrent": RATE_LIMIT_CONCURRENT,
        "rate_limit_window_sec": RATE_LIMIT_WINDOW_SEC,
        "tracked_ips": len(_inflight) or len(_window),
    }
