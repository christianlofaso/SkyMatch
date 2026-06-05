"""Cost-protection gate for the LLM-firing routes — per-IP rate limiting + a
spend-cap kill switch, exposed as the FastAPI dependency `cost_guard`.

Why a dependency and not Starlette middleware: `BaseHTTPMiddleware` buffers/breaks
the ndjson `StreamingResponse` of /analyze/batch and /internships/annotate. A
`yield`-dependency's teardown instead runs AFTER the stream is exhausted, so the
in-flight concurrent counter is released at the right time.

Distributed vs in-process
-------------------------
The per-IP rate/concurrency limiter and the rolling spend-cap cache are SHARED across web
replicas via Redis (lib/redis_client.py) so >1 replica limits correctly. When REDIS_URL is
unset or Redis is unhealthy, every path FALLS BACK to the original in-process
implementation (the dicts below) — local dev needs no Redis, and a Redis outage degrades to
per-replica limiting (looser, never tighter) instead of 503-ing all traffic. Spend-cap and
kill-switch reads BOTH fail open: a DB/Redis hiccup must never halt every request.

The manual kill switch lives in Postgres (`app_flags`), not Redis — it must survive a
restart and toggle near-instantly; it is read per-request (cheap PK lookup).

Attached to the gated routers in main.py via dependencies=[Depends(cost_guard)];
/health, /cost/summary and /admin/* are intentionally NOT gated so observability and
recovery stay reachable while a halt is active.
"""
import asyncio
import os
import time
import uuid
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from cache import get_flag, sum_spend_since
from lib import redis_client


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
# Max lifetime of an in-flight slot in the Redis concurrency set. A crashed replica can't
# run its release teardown, so its slots must self-expire or they'd permanently shrink an
# IP's concurrency budget. Keep comfortably above the longest gated request. (Unused by the
# in-process path, which releases deterministically in `finally`.)
RATE_LIMIT_INFLIGHT_TTL_SEC = _int_env("RATE_LIMIT_INFLIGHT_TTL_SEC", 120)

# Spend-cap kill switch. SPEND_CAP_USD_DAILY <= 0 disables the automatic halt.
SPEND_CAP_USD_DAILY = _float_env("SPEND_CAP_USD_DAILY", 0.0)
SPEND_CAP_WINDOW_SEC = _int_env("SPEND_CAP_WINDOW_SEC", 24 * 3600)
SPEND_CACHE_TTL_SEC = _int_env("SPEND_CACHE_TTL_SEC", 30)

# Redis keys.
_SPEND_KEY = "guard:spend"


def _rl_key(ip: str) -> str:
    return f"guard:rl:{ip}"   # sliding-window zset (request timestamps)


def _cc_key(ip: str) -> str:
    return f"guard:cc:{ip}"   # in-flight concurrency zset (held slot tokens)


# In-process per-IP state — the fallback when Redis is unavailable (event-loop thread only).
_window: dict[str, deque] = defaultdict(deque)   # ip -> recent request timestamps
_inflight: dict[str, int] = defaultdict(int)     # ip -> concurrent in-flight count

# In-process rolling-spend cache. Doubles as a throttle on the SUM aggregate even when
# Redis is the shared cache — bounds how often each replica recomputes from Postgres.
_spend_checked_at = 0.0
_spend_value = 0.0

# Atomic reserve: trim both zsets (window by age, concurrency by crash-TTL), then admit iff
# under BOTH the concurrency cap and the rate cap, recording this request's token in each.
# Returns {1,''} on admit or {0,'concurrent'|'rate'} on reject.
_RESERVE_LUA = """
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local rate_limit = tonumber(ARGV[3])
local conc_limit = tonumber(ARGV[4])
local cc_ttl = tonumber(ARGV[5])
local token = ARGV[6]
redis.call('ZREMRANGEBYSCORE', KEYS[1], 0, now - window)
redis.call('ZREMRANGEBYSCORE', KEYS[2], 0, now - cc_ttl)
local inflight = redis.call('ZCARD', KEYS[2])
if inflight >= conc_limit then return {0, 'concurrent'} end
local cnt = redis.call('ZCARD', KEYS[1])
if cnt >= rate_limit then return {0, 'rate'} end
redis.call('ZADD', KEYS[1], now, token)
redis.call('ZADD', KEYS[2], now, token)
redis.call('EXPIRE', KEYS[1], math.ceil(window))
redis.call('EXPIRE', KEYS[2], math.ceil(cc_ttl))
return {1, ''}
"""

_REJECT_CONCURRENT = "Too many requests in flight. Please wait a moment and retry."
_REJECT_RATE = "Rate limit exceeded. Please slow down and try again shortly."


def client_ip(request: Request) -> str:
    """Caller IP — first hop of X-Forwarded-For (deploy is behind a proxy) else the
    direct peer. Falls back to 'unknown' so a missing client never crashes the gate."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    client = getattr(request, "client", None)
    return getattr(client, "host", None) or "unknown"


# ── Spend cap ──────────────────────────────────────────────────────────────────────────
async def _over_spend_cap() -> bool:
    """True if rolling-window spend has reached the cap. Reads a shared Redis cache first
    (cross-replica), recomputing from Postgres at most once per SPEND_CACHE_TTL_SEC per
    replica and re-publishing to Redis. Fails OPEN on any error — a transient hiccup must
    not 503 all traffic."""
    global _spend_checked_at, _spend_value
    if SPEND_CAP_USD_DAILY <= 0:
        return False
    now = time.time()

    # 1. Shared Redis cache (cross-replica). ok=False => Redis unavailable; ok=True,val=None => miss.
    ok, val = await redis_client.call("get", _SPEND_KEY)
    if ok and val is not None:
        try:
            return float(val) >= SPEND_CAP_USD_DAILY
        except (TypeError, ValueError):
            pass  # corrupt cache value → recompute below

    # 2. (Re)compute, throttled in-process so a Redis miss/outage doesn't SUM on every request.
    if now - _spend_checked_at < SPEND_CACHE_TTL_SEC:
        return _spend_value >= SPEND_CAP_USD_DAILY
    try:
        _spend_value = await asyncio.to_thread(sum_spend_since, int(now) - SPEND_CAP_WINDOW_SEC)
    except Exception as e:
        print(f"[guard] spend-cap query failed (fail-open): {e}")
        return False
    _spend_checked_at = now

    # 3. Publish to the shared cache so other replicas read it (best-effort; no-op without Redis).
    await redis_client.call("setex", _SPEND_KEY, SPEND_CACHE_TTL_SEC, str(_spend_value))
    return _spend_value >= SPEND_CAP_USD_DAILY


async def _halt_reason() -> str | None:
    """Return a user-facing halt message if the kill switch is engaged, else None. The
    Postgres reads (manual flag + the SUM fallback) run off the event loop via to_thread so
    a slow DB round-trip can't stall other in-flight requests; the Redis cache read awaits
    directly."""
    try:
        if await asyncio.to_thread(get_flag, "kill_switch") == "on":
            return "Service is temporarily paused. Please try again later."
    except Exception as e:
        print(f"[guard] kill-switch flag read failed (fail-open): {e}")
    if await _over_spend_cap():
        return "Service is temporarily paused (daily capacity reached). Please try again later."
    return None


# ── Per-IP rate + concurrency ────────────────────────────────────────────────────────────
def _reserve_local(ip: str) -> tuple[bool, str]:
    """In-process reserve (fallback when Redis is unavailable). Atomic by virtue of the
    single event-loop thread. Returns (allowed, reject_detail)."""
    now = time.time()
    win = _window[ip]
    cutoff = now - RATE_LIMIT_WINDOW_SEC
    while win and win[0] < cutoff:
        win.popleft()

    if _inflight[ip] >= RATE_LIMIT_CONCURRENT:
        return False, _REJECT_CONCURRENT
    if len(win) >= RATE_LIMIT_PER_MIN:
        return False, _REJECT_RATE

    win.append(now)
    _inflight[ip] += 1
    return True, ""


def _release_local(ip: str) -> None:
    n = _inflight.get(ip, 0) - 1
    if n <= 0:
        _inflight.pop(ip, None)
        # Drop the window deque too if nothing recent, to bound memory.
        if not _window.get(ip):
            _window.pop(ip, None)
    else:
        _inflight[ip] = n


async def _reserve(ip: str) -> tuple[bool, str, str | None]:
    """Apply the rate + concurrency checks and reserve a slot. Tries the shared Redis path,
    falling back to in-process. Returns (allowed, reject_detail, token) — token is the Redis
    slot id to release later, or None when the in-process path was used (release uses that
    to pick the matching teardown)."""
    now = time.time()
    token = f"{now:.6f}:{uuid.uuid4().hex}"   # unique zset member
    res = await redis_client.eval_script(
        "guard_reserve", _RESERVE_LUA, keys=[_rl_key(ip), _cc_key(ip)],
        args=[now, RATE_LIMIT_WINDOW_SEC, RATE_LIMIT_PER_MIN,
              RATE_LIMIT_CONCURRENT, RATE_LIMIT_INFLIGHT_TTL_SEC, token],
    )
    if res is None:  # Redis unavailable → in-process fallback
        allowed, detail = _reserve_local(ip)
        return allowed, detail, None
    if int(res[0]) == 1:
        return True, "", token
    detail = _REJECT_CONCURRENT if res[1] == "concurrent" else _REJECT_RATE
    return False, detail, None


async def _release(ip: str, token: str | None) -> None:
    """Release the slot reserved by `_reserve`. token=None => the in-process path was used;
    a str => remove it from the Redis concurrency zset (best-effort — if Redis is now down,
    the slot self-heals via its crash-TTL). The rate-window entry is intentionally left to
    age out on its own."""
    if token is None:
        _release_local(ip)
        return
    await redis_client.call("zrem", _cc_key(ip), token)


async def cost_guard(request: Request):
    """Dependency for LLM-firing routes: halt on kill switch (503), enforce per-IP
    rate + concurrency limits (429), and account for the in-flight request."""
    reason = await _halt_reason()
    if reason:
        raise HTTPException(status_code=503, detail=reason)

    ip = client_ip(request)
    allowed, detail, token = await _reserve(ip)
    if not allowed:
        raise HTTPException(status_code=429, detail=detail)

    try:
        yield
    finally:
        await _release(ip, token)


def status_snapshot() -> dict:
    """Read-only view for GET /admin/status — current limits + rolling spend. Synchronous
    (the /admin/status route is sync and FastAPI threadpools it). `tracked_ips` reflects only
    the in-process fallback dicts; under Redis the authoritative per-IP counters live there."""
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
        "redis_enabled": redis_client.is_configured(),
        "tracked_ips_inprocess": len(_inflight) or len(_window),
    }
