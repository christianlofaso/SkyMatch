"""Postgres connection pool + config — the single DB boundary for the backend.

Replaces the old sqlite3 ``get_db()``/``init_db()`` that used to live in ``cache.py``.
``cache.py`` re-exports ``get_db``/``init_db`` from here, and ``main.py`` +
``worker/ingest.py`` import them from ``cache``, so no call site changes.

Runtime connections use ``DATABASE_URL`` — the Supabase pgBouncer **pooler** endpoint
(port 6543, transaction mode). Alembic migrations use a separate ``ALEMBIC_DATABASE_URL``
(the **direct** endpoint, port 5432) — see ``alembic/env.py`` — because transactional DDL
and prepared statements need a real session, which transaction-mode pooling can't give.

Two pgBouncer-transaction-mode constraints are encoded here:
  * ``prepare_threshold=None`` disables psycopg3's implicit server-side prepared
    statements (a reused prepare across pooled backends → ``prepared statement "..."
    does not exist``). This MUST stay set against the pooler.
  * ``row_factory=dict_row`` makes rows behave like the old ``sqlite3.Row`` for every
    cache.py caller (``row["col"]`` and ``dict(row)`` both keep working).
"""
import os

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

DATABASE_URL = os.getenv("DATABASE_URL", "")

# Pool sizing: budget Supabase's backend cap (~60 on small tiers) across 2 web replicas
# + 1 worker. Env-tunable. min_size keeps a warm connection; max_size bounds in-flight
# DB concurrency (each checked-out conn maps to a transient server backend under
# transaction pooling, so this — not WAL — is the concurrency knob now).
DB_POOL_MIN = int(os.getenv("DB_POOL_MIN", "1"))
DB_POOL_MAX = int(os.getenv("DB_POOL_MAX", "5"))

# Constructed un-opened (open=False) so importing this module never blocks on a network
# connect; init_db() opens + waits at app/worker startup (fail fast on a bad URL).
pool = ConnectionPool(
    conninfo=DATABASE_URL,
    min_size=DB_POOL_MIN,
    max_size=DB_POOL_MAX,
    open=False,
    kwargs={"row_factory": dict_row, "prepare_threshold": None},
    name="pathfinder",
)

_opened = False


def get_db():
    """Check out a pooled connection. Use as ``with get_db() as conn:`` — psycopg commits
    on clean block exit and rolls back on exception, matching the sqlite3 ``with conn:``
    semantics every cache.py function relies on. ``conn.execute(sql, params)`` returns a
    cursor you can ``.fetchone()/.fetchall()`` on, exactly like the old code."""
    return pool.connection()


def init_db() -> None:
    """Open + warm the connection pool (fail fast on a bad DATABASE_URL). Idempotent.

    Schema is owned by **Alembic** (``alembic upgrade head`` at deploy), NOT created here —
    unlike the old sqlite ``init_db`` which ran all the DDL + seeds. Both ``main.py``
    (FastAPI startup) and ``worker/ingest.py`` import and call this."""
    global _opened
    if _opened:
        return
    pool.open(wait=True, timeout=10)
    _opened = True
