from dotenv import load_dotenv
load_dotenv()

import os
import traceback

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from cache import init_db
from lib import redis_client
from lib.guard import cost_guard

# --- Sentry (optional) -------------------------------------------------------
# Wired only when SENTRY_DSN is set (prod); import-guarded so a missing sentry-sdk or
# unset DSN never affects local dev. `_sentry` is the live module (or None) — the global
# exception handler uses it to capture unhandled errors.
_sentry = None
_SENTRY_DSN = os.getenv("SENTRY_DSN", "").strip()
if _SENTRY_DSN:
    try:
        import sentry_sdk as _sentry
        _sentry.init(
            dsn=_SENTRY_DSN,
            traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
            environment=os.getenv("ENVIRONMENT", "production"),
        )
        print("[sentry] initialized")
    except Exception as e:  # bad DSN / missing package must not crash startup
        _sentry = None
        print(f"[sentry] init skipped: {e}")
from routes.run import router as run_router
from routes.profile import router as profile_router
from routes.connections import router as connections_router
from routes.internships import router as internships_router
from routes.resume import router as resume_router
from routes.analyze import router as analyze_router
from routes.cost import router as cost_router
from routes.admin import router as admin_router
from routes.account import router as account_router

app = FastAPI(title="Pathfinder API")

# Allowed browser origins. Comma-separated CORS_ORIGINS in prod (e.g. "https://app.example.com");
# defaults to localhost for dev. MUST be set to the deployed frontend origin before launch.
_CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    init_db()


@app.on_event("shutdown")
async def shutdown():
    # Close the Redis pool (best-effort; no-op when Redis was never used).
    await redis_client.aclose()


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Backstop for any UNHANDLED exception that escapes a route: log it with a traceback
    and return a clean 500 (no raw exception text leaks to the client). FastAPI's built-in
    handlers for HTTPException + RequestValidationError run first and don't reach here; the
    streaming routes (/analyze/batch, /internships/annotate) carry their own per-job
    envelopes, so this only catches route-level failures."""
    print(f"[error] unhandled {request.method} {request.url.path}: {exc!r}")
    traceback.print_exc()
    if _sentry is not None:
        _sentry.capture_exception(exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Something went wrong on our end. Please try again."},
    )


# cost_guard (lib/guard.py) gates the LLM-firing routers: per-IP rate/concurrency
# limits + the spend-cap kill switch. cost_router and admin_router are intentionally
# UNGATED so observability and recovery stay reachable while a halt is active.
_GATED = [Depends(cost_guard)]
app.include_router(run_router, dependencies=_GATED)
app.include_router(profile_router, dependencies=_GATED)
app.include_router(connections_router, dependencies=_GATED)
app.include_router(internships_router, dependencies=_GATED)
app.include_router(resume_router, dependencies=_GATED)
app.include_router(analyze_router, dependencies=_GATED)
app.include_router(cost_router)
app.include_router(admin_router)
# Account self-service (deletion) — UNGATED on purpose: no LLM, and a user must be able to
# delete their account even while the kill switch is halting the LLM routes. Auth-protected
# by require_user inside the route.
app.include_router(account_router)


@app.get("/health")
def health():
    return {"status": "ok"}
