"""Async SQLite database adapter (SQLAlchemy 2.x + aiosqlite).

Milestone 3 will introduce Alembic migrations; for now we call
``Base.metadata.create_all`` at boot which is idempotent and safe for a
personal single-user app.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from sqlalchemy import text as _sql_text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from jarvis.core.exceptions import DatabaseError
from jarvis.core.interfaces.database import IDatabase
from jarvis.core.logging.logger import get_logger
from jarvis.infrastructure.database.models import Base

if TYPE_CHECKING:
    from jarvis.core.config.settings import DatabaseSettings

_logger = get_logger("jarvis.infrastructure.database.sqlite")


class SQLiteDatabase(IDatabase):
    """Async SQLite database.

    The engine + session factory are lazily created on the first call to
    :meth:`initialize`. Callers must invoke :meth:`initialize` once at boot
    to create tables; :meth:`session` will fail loudly if that has not
    happened.
    """

    def __init__(self, settings: DatabaseSettings) -> None:
        self._settings = settings
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None

    async def initialize(self) -> None:
        if self._engine is not None:
            return
        try:
            self._engine = create_async_engine(
                self._settings.url,
                echo=self._settings.echo,
                future=True,
            )
            self._session_factory = async_sessionmaker(
                bind=self._engine, expire_on_commit=False, class_=AsyncSession
            )
            async with self._engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            _logger.info("SQLite ready at {}", self._settings.url)
        except Exception as err:
            raise DatabaseError(f"Cannot initialise SQLite: {err}") from err

    async def dispose(self) -> None:
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None
            _logger.info("SQLite engine disposed.")

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        if self._session_factory is None:
            raise DatabaseError("Database not initialised. Call `initialize()` first.")
        async with self._session_factory() as sess:
            try:
                yield sess
                await sess.commit()
            except Exception:
                await sess.rollback()
                raise

    async def health(self) -> bool:
        if self._engine is None:
            return False
        try:
            async with self._engine.connect() as conn:
                await conn.execute(_sql_text("SELECT 1"))
            return True
        except Exception:
            return False
