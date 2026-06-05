import os
from logging.config import fileConfig

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool

# Load backend/.env (alembic is run from backend/) so ALEMBIC_DATABASE_URL is available.
load_dotenv()

# Alembic Config object (reads alembic.ini).
config = context.config

# Migration connection URL: the DIRECT Supabase endpoint (port 5432), NOT the pgBouncer
# pooler (6543) — transactional DDL + prepared statements need a real session, which
# transaction-mode pooling can't provide. Falls back to DATABASE_URL for local dev (a
# single Postgres with no separate pooler). Never hard-code the URL in alembic.ini.
_url = os.getenv("ALEMBIC_DATABASE_URL") or os.getenv("DATABASE_URL")
if not _url:
    raise RuntimeError(
        "ALEMBIC_DATABASE_URL (or DATABASE_URL) must be set to run migrations"
    )
# Force the psycopg (v3) SQLAlchemy driver — psycopg2 is not installed.
if _url.startswith("postgresql://"):
    _url = "postgresql+psycopg://" + _url[len("postgresql://"):]
elif _url.startswith("postgres://"):
    _url = "postgresql+psycopg://" + _url[len("postgres://"):]
config.set_main_option("sqlalchemy.url", _url)

# Logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# The data layer is raw SQL (cache.py), not an ORM — no autogenerate. Alembic is a pure
# migration runner here.
target_metadata = None


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL without a DBAPI connection)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (connect + apply)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
