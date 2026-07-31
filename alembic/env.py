"""Alembic environment — Milestone 3.1.

Resolves the database URL from JARVIS's own :func:`load_settings` (so
``.env`` / ``JARVIS_DB_URL`` stay the single source of truth instead of a
second, hand-maintained URL living in ``alembic.ini``) and runs
migrations against the async SQLAlchemy engine JARVIS already uses.
"""
from __future__ import annotations

import asyncio

# Make `src/` importable when Alembic is invoked from the repo root
# without a prior `pip install -e .`.
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from jarvis.core.config.settings import load_settings
from jarvis.infrastructure.database.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _resolve_db_url() -> str:
    settings = load_settings()
    return settings.db.url


def run_migrations_offline() -> None:
    """Emit SQL to stdout without a live DB connection (``--sql``)."""
    url = _resolve_db_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations against the real (async) engine JARVIS uses."""
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = _resolve_db_url()

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(_do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
