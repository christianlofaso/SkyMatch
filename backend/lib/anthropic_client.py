"""Shared Anthropic client + a Sonnet concurrency governor (Redis-distributed, with an
in-process fallback).

Why this module exists
----------------------
Sonnet (MODEL_MID) is the one model that maxes the org's per-minute rate limits
(input-TPM / output-TPM / RPM). The dominant consumer is /run: profile.py (~2 calls)
+ internships.py (~24-30, fanned out concurrently). Two levers tame it:

1. SDK backoff — the Anthropic SDK already does exponential backoff with jitter that
   honors the Retry-After header. We just raise `max_retries` above the default(2) so
   429 bursts recover instead of failing. One shared client means every route gets it
   (previously only internships.py raised it; analyze/profile/connections sat at 2).

2. `sonnet_slot()` — a cap on IN-FLIGHT Sonnet calls. Acquire it in the async layer
   around every Sonnet messages.create (before handing a sync call to a thread):
   `async with sonnet_slot(): ...`. It staggers a run's Sonnet work across 2-3 minutes
   so one /run can't dump ~56K input tokens into a single minute; the SDK backoff absorbs
   the unavoidable overflow (one run's input inherently exceeds the 30K/min cap, so it
   MUST span >=2 min).

   Sonnet-ONLY by design: Haiku (the /analyze/batch + results path) and Opus (roadmap)
   have rate-limit headroom and stay ungated, so the latency-sensitive batch path is
   untouched.

Distributed vs in-process
--------------------------
SONNET_MAX_CONCURRENCY is the GLOBAL cap on concurrent Sonnet calls across ALL web
replicas. When REDIS_URL is set, the slot is held in a SELF-HEALING Redis ZSET semaphore:
each held slot is stamped with its acquire time and reclaimed once older than
SONNET_SLOT_TTL_SEC, so a crashed replica's slots auto-expire and can never deadlock the
governor (this is why we use a TTL'd ZSET, not a plain INCR/DECR counter or a BLPOP token
list — both leak the slot on a holder crash). Acquire polls a tiny atomic Lua try-acquire
every SONNET_POLL_SEC until a slot frees, giving up after SONNET_MAX_WAIT_SEC and
proceeding un-slotted (the SDK 429 backoff is the safety net — better than hanging a
request forever). When Redis is absent/unhealthy the slot degrades to a per-process
asyncio.Semaphore (the old single-worker behaviour; under N replicas the effective global
cap becomes N * SONNET_MAX_CONCURRENCY until Redis returns).

Tunables (env): SONNET_MAX_CONCURRENCY (default 6), ANTHROPIC_MAX_RETRIES (default 8),
SONNET_SLOT_TTL_SEC, SONNET_POLL_SEC, SONNET_MAX_WAIT_SEC.
"""
import os
import asyncio
import uuid
import time

import anthropic

from lib import redis_client

# SDK retry IS exponential backoff w/ jitter honoring Retry-After. Raise the ceiling
# from the default(2) so 429 bursts recover instead of surfacing as errors.
_MAX_RETRIES = int(os.getenv("ANTHROPIC_MAX_RETRIES", "8"))
# Per-request timeout (the SDK default is a loose 600s). Bound a genuine API hang while
# leaving headroom for the longest call we make — the Opus roadmap (max_tokens 4096),
# which can run ~1-2 min. Keep this comfortably ABOVE that or roadmap calls get cut +
# retried. Tune via ANTHROPIC_TIMEOUT_SEC.
_TIMEOUT_SEC = float(os.getenv("ANTHROPIC_TIMEOUT_SEC", "180"))
client = anthropic.Anthropic(max_retries=_MAX_RETRIES, timeout=_TIMEOUT_SEC)

# Global cap on concurrent Sonnet (MODEL_MID) calls (across all replicas when Redis-backed).
# Default 6 balances single-run latency against burst safety: a lone /run fans out faster
# (~5 annotation waves vs 7 at 4), but TWO overlapping runs can briefly exceed the org's
# 30k Sonnet input-tokens/min cap — the SDK's Retry-After backoff absorbs the residual.
# Drop toward 4 (sustained rate sits just under the cap) if 429s resurface under real
# concurrent load; raise it if usage is single-user. Tune via SONNET_MAX_CONCURRENCY.
SONNET_CONCURRENCY = int(os.getenv("SONNET_MAX_CONCURRENCY", "6"))

# Redis ZSET semaphore knobs. SLOT_TTL must exceed the longest Sonnet call so a still-live
# holder's slot is never reclaimed out from under it; keep it >= ANTHROPIC_TIMEOUT_SEC.
_SLOT_TTL_SEC = float(os.getenv("SONNET_SLOT_TTL_SEC", "200"))
_POLL_SEC = float(os.getenv("SONNET_POLL_SEC", "0.1"))
_MAX_WAIT_SEC = float(os.getenv("SONNET_MAX_WAIT_SEC", "120"))
_SLOTS_KEY = "sonnet:slots"

# Per-process fallback used when Redis is absent/unhealthy (the old single-worker governor).
_local_sem = asyncio.Semaphore(SONNET_CONCURRENCY)

# Atomic try-acquire: trim slots older than the TTL (self-heal crashed holders), then add
# this token iff under the cap. Returns 1 (acquired) or 0 (full).
_ACQUIRE_LUA = """
local now = tonumber(ARGV[1])
local ttl = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local token = ARGV[4]
redis.call('ZREMRANGEBYSCORE', KEYS[1], 0, now - ttl)
local held = redis.call('ZCARD', KEYS[1])
if held < limit then
  redis.call('ZADD', KEYS[1], now, token)
  redis.call('EXPIRE', KEYS[1], math.ceil(ttl))
  return 1
end
return 0
"""


async def _acquire_redis_slot() -> str | None:
    """Try to hold a global Sonnet slot via the Redis ZSET semaphore. Returns the slot
    token on success, or None to signal "use the in-process semaphore instead" (Redis
    unconfigured/unhealthy). Polls until a slot frees, then gives up after MAX_WAIT and
    proceeds un-slotted (returns the token anyway; the SDK backoff is the net)."""
    if not redis_client.is_configured():
        return None
    token = uuid.uuid4().hex
    waited = 0.0
    while True:
        res = await redis_client.eval_script(
            "sonnet_acquire", _ACQUIRE_LUA, keys=[_SLOTS_KEY],
            args=[time.time(), _SLOT_TTL_SEC, SONNET_CONCURRENCY, token],
        )
        if res is None:
            return None  # Redis went away mid-acquire → caller falls back to local sem
        if int(res) == 1:
            return token
        if waited >= _MAX_WAIT_SEC:
            print(f"[sonnet] slot wait exceeded {_MAX_WAIT_SEC:g}s - proceeding (SDK backoff is the net)")
            return token  # un-slotted; release ZREM no-ops harmlessly
        await asyncio.sleep(_POLL_SEC)
        waited += _POLL_SEC


class _SonnetSlot:
    """Per-acquire async context manager. A FRESH instance per `async with sonnet_slot():`
    so the held token/flag live on this object, never on a shared singleton (the 6 call
    sites enter this concurrently — storing acquire state on one shared object would race)."""
    __slots__ = ("_token", "_local_held")

    async def __aenter__(self):
        self._token = await _acquire_redis_slot()
        self._local_held = self._token is None
        if self._local_held:
            await _local_sem.acquire()
        return self

    async def __aexit__(self, *exc):
        if self._local_held:
            _local_sem.release()
        else:
            # Best-effort release; if Redis is down the slot self-heals via its TTL.
            await redis_client.call("zrem", _SLOTS_KEY, self._token)
        return False


def sonnet_slot() -> _SonnetSlot:
    """Acquire a global Sonnet concurrency slot: `async with sonnet_slot(): ...`.
    Redis-distributed when REDIS_URL is set, per-process otherwise (see module docstring)."""
    return _SonnetSlot()
