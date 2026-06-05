"""Lightweight request timing / profiling.

Wrap a block with `timed(label)` (async) or `timed_sync(label)` to log its
wall-clock duration as `[timing] <label>: <ms>ms`. Open a `timing_session(name)`
at the top of a request to ALSO collect every span and print a sorted,
percentage breakdown when the request finishes — so you can see where the time
goes across parallel branches at a glance.

Notes:
- Spans are wall-clock and parallel branches OVERLAP, so per-span ms will sum to
  MORE than the session total. The total is the real request latency; the per-span
  percentages show each branch's share of that wall-clock (a branch can be >100%
  of nothing — read the absolute ms together with the total).
- `timed`/`timed_sync` also work with no active session (they just log the line).
- Always wrap timing at the async/orchestration level (around `await`/`gather`),
  not inside an `asyncio.to_thread` worker, so span recording stays on the event
  loop thread (no cross-thread races on the shared list).
"""
import time
import contextvars
from contextlib import asynccontextmanager, contextmanager

_spans: contextvars.ContextVar = contextvars.ContextVar("timing_spans", default=None)


def _record(label: str, ms: float) -> None:
    spans = _spans.get()
    if spans is not None:
        spans.append((label, ms))
    print(f"[timing] {label}: {ms:.0f}ms")


@asynccontextmanager
async def timed(label: str):
    t0 = time.perf_counter()
    try:
        yield
    finally:
        _record(label, (time.perf_counter() - t0) * 1000)


@contextmanager
def timed_sync(label: str):
    t0 = time.perf_counter()
    try:
        yield
    finally:
        _record(label, (time.perf_counter() - t0) * 1000)


async def timed_call(label: str, coro):
    """Await `coro` under a timing span — convenient inside asyncio.gather(...)."""
    async with timed(label):
        return await coro


@contextmanager
def timing_session(name: str):
    """Collect every `timed` span opened within and print a sorted breakdown."""
    spans: list[tuple[str, float]] = []
    token = _spans.set(spans)
    t0 = time.perf_counter()
    try:
        yield
    finally:
        total = (time.perf_counter() - t0) * 1000
        _spans.reset(token)
        print(f"[timing] ===== {name}: total {total:.0f}ms ({len(spans)} spans) =====")
        for label, ms in sorted(spans, key=lambda x: -x[1]):
            pct = (ms / total * 100) if total else 0
            print(f"[timing]   {ms:8.0f}ms  {pct:5.1f}%  {label}")
        print("[timing] " + "=" * 45)
