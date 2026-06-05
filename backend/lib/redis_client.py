"""Shared async Redis client + a circuit breaker, for the multi-replica coordination
state (per-IP rate limiter, rolling spend cache, Sonnet concurrency governor).

Why this module exists
----------------------
Three pieces of guard/governor state used to live in process memory and were therefore
SINGLE-WORKER ONLY (see lib/guard.py + lib/anthropic_client.py). To run >1 web replica
correctly that state must be SHARED. This module is the thin Redis layer the guard and
the Sonnet governor sit on.

Optional, exactly like Voyage (lib/embeddings.py)
-------------------------------------------------
`REDIS_URL` is OPTIONAL. When it is unset (local dev) OR the `redis` package is missing
OR Redis is unreachable at runtime, every helper here returns a "no Redis" sentinel
(`eval_script` -> None, `call` -> (False, None)) and the CALLER falls back to its existing
in-process implementation. So:
  - no REDIS_URL  -> pure in-process behaviour (the old single-worker path) — local dev
                     needs no Redis running.
  - REDIS_URL set -> shared state across replicas; a transient Redis hiccup degrades to
                     per-replica in-process limiting (looser, never tighter), never a 503.

Circuit breaker
---------------
A dead Redis must not make every gated request wait out a connection timeout. On any
Redis error we TRIP the breaker for REDIS_RETRY_COOLDOWN_SEC: subsequent calls skip Redis
entirely (instant fall back to in-process) until the cooldown elapses and we probe again.
Short socket timeouts (2s) bound the first failing call.
"""
import os
import time

try:  # import-guarded so a missing package never crashes a route (Voyage pattern)
    import redis.asyncio as aioredis
except Exception:  # pragma: no cover - exercised only when redis isn't installed
    aioredis = None


_URL = os.getenv("REDIS_URL", "").strip()
# How long to skip Redis after a failure before probing again. Bounds the blast radius of
# a Redis outage to one slow call per cooldown rather than one per request.
_COOLDOWN_SEC = float(os.getenv("REDIS_RETRY_COOLDOWN_SEC", "10"))

_client = None                 # lazy redis.asyncio.Redis (a connection pool under the hood)
_scripts: dict[str, object] = {}   # name -> registered AsyncScript (EVALSHA-cached)
_unhealthy_until = 0.0         # circuit breaker: skip Redis while now < this


def is_configured() -> bool:
    """True if Redis is even an option (URL provided AND the package importable). Callers
    use this to decide whether to attempt the Redis path at all."""
    return bool(_URL) and aioredis is not None


def _circuit_open() -> bool:
    return time.time() < _unhealthy_until


def _trip(err: Exception) -> None:
    global _unhealthy_until
    _unhealthy_until = time.time() + _COOLDOWN_SEC
    print(f"[redis] unavailable - falling back to in-process for {_COOLDOWN_SEC:g}s: {err!r}")


def _get_client():
    global _client
    if _client is None:
        # Short timeouts so a dead Redis trips the breaker fast instead of hanging a request.
        # decode_responses=True → Lua/str results come back as str, ints as int.
        _client = aioredis.from_url(
            _URL,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
            health_check_interval=30,
        )
    return _client


async def eval_script(name: str, script: str, keys: list, args: list):
    """Run a cached Lua script (registered once per name, then EVALSHA). Returns the Lua
    result, or None when Redis is unavailable/unhealthy — None means "fall back to
    in-process". Any Redis error trips the circuit breaker and returns None."""
    if not is_configured() or _circuit_open():
        return None
    try:
        client = _get_client()
        sc = _scripts.get(name)
        if sc is None:
            sc = client.register_script(script)
            _scripts[name] = sc
        return await sc(keys=keys, args=args)
    except Exception as e:
        _trip(e)
        return None


async def call(method: str, *args):
    """Run a single client command (e.g. "get"/"setex"/"zrem"). Returns (ok, value):
    ok=False means Redis was unavailable (caller falls back); ok=True with value from
    Redis. Any error trips the circuit breaker."""
    if not is_configured() or _circuit_open():
        return False, None
    try:
        client = _get_client()
        value = await getattr(client, method)(*args)
        return True, value
    except Exception as e:
        _trip(e)
        return False, None


async def aclose() -> None:
    """Close the pool on shutdown (best-effort). Safe to call when never connected."""
    global _client
    if _client is not None:
        try:
            await _client.aclose()
        except Exception:
            pass
        _client = None
