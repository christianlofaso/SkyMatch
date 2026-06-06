"""Supabase Admin API client — the ONE place the backend talks to Supabase over HTTP
(everything else is stateless local JWT verification in lib/auth.py).

Used by the account-deletion path (M10) to delete the Supabase **auth user** itself, which
the app-side `cache.delete_user_data` can't do (it only owns our Postgres tables). Requires
the **service_role** key (admin-scoped — backend-only, NEVER exposed to the browser).

OPTIONAL, like the rest of the launch infra: with SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY
unset, `is_available()` is False and the deletion route degrades to app-data-only (the auth
user is left for manual cleanup / the frontend sign-out). So local dev + auth-off configs
keep working unchanged.
"""
import os

import httpx

_SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
_TIMEOUT = float(os.getenv("SUPABASE_ADMIN_TIMEOUT_SEC", "10"))


def is_available() -> bool:
    """True only when BOTH the project URL and the service_role key are configured."""
    return bool(_SUPABASE_URL and _SERVICE_ROLE_KEY)


async def delete_auth_user(user_id: str) -> bool:
    """Hard-delete a Supabase auth user via the Admin API. Returns True on success (or if the
    user is already gone, 404), False on any failure — the caller treats this as best-effort
    so app-side deletion still succeeds even if the admin call is down. Never raises."""
    if not is_available():
        return False
    url = f"{_SUPABASE_URL}/auth/v1/admin/users/{user_id}"
    headers = {
        # The service_role key is BOTH the apikey and the bearer for admin calls.
        "apikey": _SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {_SERVICE_ROLE_KEY}",
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.delete(url, headers=headers)
        if resp.status_code in (200, 204, 404):  # 404 = already deleted → idempotent success
            return True
        print(f"[supabase_admin] delete_auth_user {user_id} → HTTP {resp.status_code}: {resp.text[:200]}")
        return False
    except Exception as e:
        print(f"[supabase_admin] delete_auth_user {user_id} failed (non-fatal): {e}")
        return False
