"""Async SQLite database adapter (SQLAlchemy 2.x + aiosqlite).

Milestone 3 will introduce Alembic migrations; for now we call
``Base.metadata.create_all`` at boot which is idempotent and safe for a
personal single-user app.

**Foreign keys are enforced** (Aug 2026 database integrity pass). SQLite
ships with ``PRAGMA foreign_keys`` *off* by default and the setting is
per-connection, not per-database -- so every ``ON DELETE``/``ON UPDATE``
clause declared in ``models.py`` was decorative until this module turned
it on. The pragma is issued from a single ``connect`` event listener
(:func:`_enable_sqlite_foreign_keys`) rather than by each repository,
because a rule that has to be remembered at every call site is a rule
that will be forgotten at one of them.

The consequence worth knowing: a delete that would orphan a row now
raises ``IntegrityError`` instead of silently succeeding. That is the
point -- but it means deletion *order* matters where an ORM relationship
does not already cascade for you.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from sqlalchemy import event
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


def _enable_sqlite_foreign_keys(dbapi_connection: Any, connection_record: Any) -> None:
    """Issue ``PRAGMA foreign_keys=ON`` on every new DBAPI connection.

    SQLAlchemy's documented pattern for this: a ``connect`` event on the
    *sync* engine underneath the async one, using the DBAPI cursor
    directly. It has to be per-connection because SQLite scopes the
    pragma that way -- a connection pool that recycles or grows would
    otherwise hand out connections with enforcement off, which is worse
    than never enabling it because the failure would be intermittent.

    Registered against one engine at its single construction point; not
    a global ``event.listens_for(Engine, ...)``, which would also fire
    for any engine a test or a future adapter creates for its own
    reasons.
    """
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


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
            # Guarded on the dialect rather than assumed: ``db.url`` is
            # user-configurable, and pointing it at a non-SQLite backend
            # should make this a no-op rather than an error on every
            # connect. Those backends enforce foreign keys natively
            # anyway, so there is nothing to turn on.
            if self._engine.dialect.name == "sqlite":
                event.listen(self._engine.sync_engine, "connect", _enable_sqlite_foreign_keys)
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
