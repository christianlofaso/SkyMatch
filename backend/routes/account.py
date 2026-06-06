"""Account self-service — currently just deletion (M10, the PII/launch-compliance path).

DELETE /account erases the signed-in user: app-side data (users + usage_counters, with the
cost_events ledger anonymized) AND, when the service_role key is configured, the Supabase
auth user itself. require_user-gated, so it needs a valid session.

Deliberately registered UNGATED by cost_guard (see main.py): it fires no LLM, and a user must
be able to delete their account even while the spend-cap kill switch is halting the LLM routes.
The user's JWT stays valid until it expires (stateless verification), so the frontend signs
out immediately after a successful delete.
"""
import asyncio

from fastapi import APIRouter, Depends, HTTPException

from cache import delete_user_data
from lib import supabase_admin
from lib.auth import User, require_user

router = APIRouter()


@router.delete("/account")
async def delete_account(user: User | None = Depends(require_user)):
    """Delete the authenticated user's account + data. Idempotent. Returns what was removed."""
    # require_user returns None only when auth is DISABLED — there's no account to delete then.
    if user is None:
        raise HTTPException(status_code=400, detail="Auth is not enabled; no account to delete.")

    # App-side data first (the source of truth we own). Blocking DB call → off the event loop.
    try:
        counts = await asyncio.to_thread(delete_user_data, user.id)
    except Exception as e:
        print(f"[account] delete_user_data failed for {user.id}: {e}")
        raise HTTPException(status_code=500, detail="Could not delete account data. Please try again.")

    # Then the Supabase auth user (best-effort — never blocks app-data deletion). Reports
    # whether it actually happened so the caller knows if a manual cleanup is still needed.
    auth_user_deleted = await supabase_admin.delete_auth_user(user.id)

    print(f"[account] deleted user {user.id}: {counts}, auth_user_deleted={auth_user_deleted}")
    return {"deleted": True, "auth_user_deleted": auth_user_deleted, **counts}
