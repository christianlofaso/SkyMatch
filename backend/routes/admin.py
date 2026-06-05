"""Admin controls for the cost-protection kill switch. NOT gated by cost_guard, so
these stay reachable while a halt is active. Guarded instead by a shared secret:
the X-Admin-Token header must equal env ADMIN_TOKEN (unset => all admin calls 403)."""
import os

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from cache import set_flag
from lib.guard import status_snapshot

router = APIRouter()


class KillSwitchRequest(BaseModel):
    on: bool


def _require_admin(token: str | None) -> None:
    expected = os.getenv("ADMIN_TOKEN")
    # Fail closed: with no ADMIN_TOKEN configured the endpoints are unusable (not open).
    if not expected or token != expected:
        raise HTTPException(status_code=403, detail="Forbidden.")


@router.post("/admin/killswitch")
def killswitch(req: KillSwitchRequest, x_admin_token: str | None = Header(default=None)):
    _require_admin(x_admin_token)
    set_flag("kill_switch", "on" if req.on else "off")
    return {"kill_switch": "on" if req.on else "off"}


@router.get("/admin/status")
def admin_status(x_admin_token: str | None = Header(default=None)):
    _require_admin(x_admin_token)
    return status_snapshot()
