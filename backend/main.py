from dotenv import load_dotenv
load_dotenv()

import traceback

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from cache import init_db
from lib.guard import cost_guard
from routes.run import router as run_router
from routes.profile import router as profile_router
from routes.connections import router as connections_router
from routes.internships import router as internships_router
from routes.resume import router as resume_router
from routes.analyze import router as analyze_router
from routes.cost import router as cost_router
from routes.admin import router as admin_router

app = FastAPI(title="Pathfinder API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    init_db()


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Backstop for any UNHANDLED exception that escapes a route: log it with a traceback
    and return a clean 500 (no raw exception text leaks to the client). FastAPI's built-in
    handlers for HTTPException + RequestValidationError run first and don't reach here; the
    streaming routes (/analyze/batch, /internships/annotate) carry their own per-job
    envelopes, so this only catches route-level failures."""
    print(f"[error] unhandled {request.method} {request.url.path}: {exc!r}")
    traceback.print_exc()
    # SENTRY: sentry_sdk.capture_exception(exc) here once SENTRY_DSN is wired (deferred).
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


@app.get("/health")
def health():
    return {"status": "ok"}
