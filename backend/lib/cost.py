"""Lightweight per-call token + cost accounting — the [cost] sibling of lib/timing.py.

`record_usage(label, model, usage)` prints a `[cost]` line for one Claude call and,
when a `cost_session(name)` is active, accumulates per-call rows to print a sorted
breakdown + a rough USD total when the request finishes (mirroring timing_session).

The USD figures are ESTIMATES for relative visibility ("where does the money go?"),
NOT a billing source of truth — update _PRICE_PER_MTOK if Anthropic pricing changes.
Token counts are exact (straight from the API response).

Anthropic usage accounting (the math below depends on these):
- input_tokens                 = fresh (uncached) input, billed at the input rate.
- cache_read_input_tokens      = cache hits, billed ~0.1x the input rate.
- cache_creation_input_tokens  = cache writes, billed ~1.25x the input rate.
- output_tokens                = generated tokens, billed at the (higher) output rate.
These four are DISJOINT (input_tokens already excludes the cached counts), so summing
their costs gives the call total without double-counting.
"""
import contextvars
from contextlib import contextmanager

from config.models import MODEL_FULL, MODEL_MID, MODEL_QUICK

# Approximate USD per 1M tokens: (input, output). ESTIMATES — see module docstring.
_PRICE_PER_MTOK = {
    MODEL_FULL:  (15.0, 75.0),   # Opus
    MODEL_MID:   (3.0, 15.0),    # Sonnet
    MODEL_QUICK: (1.0, 5.0),     # Haiku
}
_CACHE_READ_MULT = 0.1    # cache hits ~10% of input price
_CACHE_WRITE_MULT = 1.25  # cache writes ~125% of input price

_rows: contextvars.ContextVar = contextvars.ContextVar("cost_rows", default=None)


def _estimate_usd(model: str, in_tok: int, out_tok: int, cache_read: int, cache_write: int) -> float:
    pin, pout = _PRICE_PER_MTOK.get(model, (0.0, 0.0))
    return (
        in_tok * pin
        + out_tok * pout
        + cache_read * pin * _CACHE_READ_MULT
        + cache_write * pin * _CACHE_WRITE_MULT
    ) / 1_000_000


def record_usage(label: str, model: str, usage) -> None:
    """Log one Claude call's token usage (+ rough USD) and record it if a session is open.
    `usage` is the SDK message.usage object; any missing field defaults to 0."""
    in_tok      = getattr(usage, "input_tokens", 0) or 0
    out_tok     = getattr(usage, "output_tokens", 0) or 0
    cache_read  = getattr(usage, "cache_read_input_tokens", 0) or 0
    cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
    usd = _estimate_usd(model, in_tok, out_tok, cache_read, cache_write)

    rows = _rows.get()
    if rows is not None:
        rows.append((label, model, in_tok, out_tok, cache_read, cache_write, usd))
    print(
        f"[cost] {label} ({model}): in={in_tok} out={out_tok} "
        f"cache_r={cache_read} cache_w={cache_write} ~${usd:.4f}"
    )


@contextmanager
def cost_session(name: str):
    """Collect every record_usage() call within and print a sorted USD breakdown.

    Safe across asyncio tasks and asyncio.to_thread workers: the contextvar binding
    is copied into each child context at task/thread creation, and they all append to
    the SAME list object (list.append is atomic under the GIL). Create the tasks INSIDE
    this block so they inherit the binding."""
    rows: list[tuple] = []
    token = _rows.set(rows)
    try:
        yield
    finally:
        _rows.reset(token)
        total_usd = sum(r[6] for r in rows)
        total_in  = sum(r[2] for r in rows)
        total_out = sum(r[3] for r in rows)
        total_cr  = sum(r[4] for r in rows)
        print(
            f"[cost] ===== {name}: ~${total_usd:.4f} over {len(rows)} calls "
            f"(in={total_in} out={total_out} cache_r={total_cr}) ====="
        )
        for label, model, in_tok, out_tok, cr, cw, usd in sorted(rows, key=lambda r: -r[6]):
            print(f"[cost]   ${usd:7.4f}  {model:18} in={in_tok:6} out={out_tok:5} cr={cr:6}  {label}")
        print("[cost] " + "=" * 45)
