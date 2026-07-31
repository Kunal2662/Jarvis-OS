"""Structured-storage (SQL) port."""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from typing import Protocol, runtime_checkable


@runtime_checkable
class IDatabase(Protocol):
    """Abstract async database. Adapters return a session/connection object."""

    async def initialize(self) -> None: ...

    async def dispose(self) -> None: ...

    def session(self) -> AbstractAsyncContextManager[object]: ...

    async def health(self) -> bool: ...
