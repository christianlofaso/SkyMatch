"""Shared Anthropic client + a process-wide Sonnet concurrency cap.

Why this module exists
----------------------
Sonnet (MODEL_MID) is the one model that maxes the org's per-minute rate limits
(input-TPM / output-TPM / RPM). The dominant consumer is /run: profile.py (~2 calls)
+ internships.py (~24-30, fanned out concurrently). Two levers tame it:

1. SDK backoff — the Anthropic SDK already does exponential backoff with jitter that
   honors the Retry-After header. We just raise `max_retries` above the default(2) so
   429 bursts recover instead of failing. One shared client means every route gets it
   (previously only internships.py raised it; analyze/profile/connections sat at 2).

2. `sonnet_sem` — a process-wide cap on IN-FLIGHT Sonnet calls. Acquire it in the async
   layer around every Sonnet messages.create (before handing a sync call to a thread).
   It staggers a run's Sonnet work across 2-3 minutes so one /run can't dump ~56K input
   tokens into a single minute; the SDK backoff absorbs the unavoidable overflow (one
   run's input inherently exceeds the 30K/min cap, so it MUST span >=2 min).

   Sonnet-ONLY by design: Haiku (the /analyze/batch + results path) and Opus (roadmap)
   have rate-limit headroom and stay ungated, so the latency-sensitive batch path is
   untouched.

Caveat — per-process: this semaphore bounds Sonnet globally only under a SINGLE uvicorn
worker (the dev setup: one event loop). A multi-worker deploy would need each worker's
budget divided, or a shared external limiter. Revisit before scaling out.

Tunables (env): SONNET_MAX_CONCURRENCY (default 4), ANTHROPIC_MAX_RETRIES (default 8).
"""
import os
import asyncio

import anthropic

# SDK retry IS exponential backoff w/ jitter honoring Retry-After. Raise the ceiling
# from the default(2) so 429 bursts recover instead of surfacing as errors.
_MAX_RETRIES = int(os.getenv("ANTHROPIC_MAX_RETRIES", "8"))
# Per-request timeout (the SDK default is a loose 600s). Bound a genuine API hang while
# leaving headroom for the longest call we make — the Opus roadmap (max_tokens 4096),
# which can run ~1-2 min. Keep this comfortably ABOVE that or roadmap calls get cut +
# retried. Tune via ANTHROPIC_TIMEOUT_SEC.
_TIMEOUT_SEC = float(os.getenv("ANTHROPIC_TIMEOUT_SEC", "180"))
client = anthropic.Anthropic(max_retries=_MAX_RETRIES, timeout=_TIMEOUT_SEC)

# Process-wide cap on concurrent Sonnet (MODEL_MID) calls. Constructing an
# asyncio.Semaphore at import time is safe on 3.12 (it binds to the running loop lazily).
# Default 6 balances single-run latency against burst safety: a lone /run fans out faster
# (~5 annotation waves vs 7 at 4), but TWO overlapping runs can briefly exceed the org's
# 30k Sonnet input-tokens/min cap — the SDK's Retry-After backoff absorbs the residual.
# Drop toward 4 (sustained rate sits just under the cap) if 429s resurface under real
# concurrent load; raise it if usage is single-user. Tune via SONNET_MAX_CONCURRENCY.
SONNET_CONCURRENCY = int(os.getenv("SONNET_MAX_CONCURRENCY", "6"))
sonnet_sem = asyncio.Semaphore(SONNET_CONCURRENCY)
