"""auth + per-user quota tables (milestone 3)

Adds the identity/usage layer for Supabase magic-link auth:
  * users            — one row per Supabase auth user (keyed by the JWT `sub`).
  * usage_counters   — per (user, UTC-day, kind) counters enforcing the daily quota
                       (kind = 'matcher' | 'analysis'); incremented before LLM fire.
  * cost_events.user_id — per-user spend attribution on the existing ledger.

Auth is OPTIONAL at runtime: when SUPABASE_JWT_SECRET is unset the app never reads
these tables (every route stays anonymous), but the schema exists so enabling auth is a
config flip, not a migration. Table is `usage_counters` (not `usage`) to dodge the
Postgres USAGE keyword.

Revision ID: 0002_auth_tables
Revises: 0001_initial
Create Date: 2026-06-05
"""
from alembic import op

revision = "0002_auth_tables"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


_UPGRADE = [
    """
    CREATE TABLE IF NOT EXISTS users (
        id          TEXT PRIMARY KEY,                 -- Supabase auth user UUID (JWT sub)
        email       TEXT,
        plan        TEXT NOT NULL DEFAULT 'free',
        created_at  BIGINT NOT NULL,
        last_seen   BIGINT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS usage_counters (
        user_id  TEXT NOT NULL,
        day      TEXT NOT NULL,                        -- 'YYYY-MM-DD' (UTC)
        kind     TEXT NOT NULL,                        -- 'matcher' | 'analysis'
        count    INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (user_id, day, kind)
    )
    """,
    "ALTER TABLE cost_events ADD COLUMN IF NOT EXISTS user_id TEXT",
    "CREATE INDEX IF NOT EXISTS idx_cost_events_user ON cost_events(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_usage_user_day ON usage_counters(user_id, day)",
]

_DOWNGRADE = [
    "DROP INDEX IF EXISTS idx_usage_user_day",
    "DROP INDEX IF EXISTS idx_cost_events_user",
    "ALTER TABLE cost_events DROP COLUMN IF EXISTS user_id",
    "DROP TABLE IF EXISTS usage_counters",
    "DROP TABLE IF EXISTS users",
]


def upgrade() -> None:
    for ddl in _UPGRADE:
        op.execute(ddl)


def downgrade() -> None:
    for ddl in _DOWNGRADE:
        op.execute(ddl)
