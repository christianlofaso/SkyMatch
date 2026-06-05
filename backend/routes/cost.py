"""GET /cost/summary — read the cost_events ledger (written by lib/cost.py) and report
actual Claude spend, estimated cache savings, and per-model / per-search breakdowns over a
window. All USD figures are approximate (price table + hit estimates live in lib/cost.py)."""
import time

from fastapi import APIRouter

from cache import query_cost_events

router = APIRouter()


@router.get("/cost/summary")
def cost_summary(days: int = 7):
    days = max(1, min(days, 365))
    since = int(time.time()) - days * 24 * 3600
    rows = query_cost_events(since)

    calls = [r for r in rows if r["kind"] == "call"]
    hits = [r for r in rows if r["kind"] == "hit"]

    total_spend = sum(r["usd"] for r in calls)
    total_saved = sum(r["est_saved_usd"] for r in hits)

    # Actual spend grouped by model and by search (cost_session name).
    by_model: dict[str, dict] = {}
    by_session: dict[str, dict] = {}
    for r in calls:
        m = by_model.setdefault(r["model"] or "unknown", {"model": r["model"] or "unknown", "usd": 0.0, "calls": 0})
        m["usd"] += r["usd"]; m["calls"] += 1
        s = by_session.setdefault(r["session"] or "(none)", {"session": r["session"] or "(none)", "usd": 0.0, "calls": 0})
        s["usd"] += r["usd"]; s["calls"] += 1

    # Full-call cache avoidance grouped by what was avoided (annotate / analysis:quick / …).
    hits_by_label: dict[str, dict] = {}
    for r in hits:
        h = hits_by_label.setdefault(r["label"] or "(none)", {"label": r["label"] or "(none)", "hits": 0, "saved_usd": 0.0})
        h["hits"] += 1; h["saved_usd"] += r["est_saved_usd"]

    # Prompt-cache efficiency: share of input tokens served from the ephemeral cache.
    cache_read = sum(r["cache_read_tokens"] for r in calls)
    fresh_in = sum(r["input_tokens"] for r in calls)
    denom = cache_read + fresh_in
    pct_from_cache = round(100 * cache_read / denom, 1) if denom else 0.0

    def _round(items, key):
        for it in items:
            it[key] = round(it[key], 4)
        return sorted(items, key=lambda x: -x[key])

    return {
        "window_days": days,
        "total_spend_usd": round(total_spend, 4),
        "total_saved_usd": round(total_saved, 4),
        "calls": len(calls),
        "hits": len(hits),
        "by_model": _round(list(by_model.values()), "usd"),
        "by_session": _round(list(by_session.values()), "usd"),
        "hits_by_label": _round(list(hits_by_label.values()), "saved_usd"),
        "prompt_cache": {
            "cache_read_tokens": cache_read,
            "input_tokens": fresh_in,
            "pct_from_cache": pct_from_cache,
        },
    }
