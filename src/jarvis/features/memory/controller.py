"""Memory controller — Qt-facing bridge to :class:`MemoryService`.

Milestone 3.1. Mirrors the shape of
:class:`~jarvis.features.conversation.controller.ConversationController`:
the controller owns no UI state, schedules async calls on the running
qasync loop, and exposes plain Qt signals for widgets to subscribe to.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal, Slot

from jarvis.core.logging.logger import get_logger
from jarvis.utils.async_utils import fire_and_forget

if TYPE_CHECKING:
    from jarvis.services.memory_service import MemoryRecord, MemoryService

_logger = get_logger("jarvis.features.memory")


class MemoryController(QObject):
    memories_loaded = Signal(list)  # list[MemoryRecord]
    error = Signal(str)
    busy_changed = Signal(bool)

    def __init__(self, memory_service: MemoryService, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._service = memory_service
        self._task: asyncio.Task | None = None
        self._last_filters: tuple[str | None, bool, bool] = (None, False, False)

    # ------------------------------------------------------------------
    # Public slots
    # ------------------------------------------------------------------
    @Slot(str, bool, bool)
    def browse(
        self,
        memory_type: str,
        pinned_only: bool,
        include_archived: bool,
    ) -> None:
        """Refresh the timeline. ``memory_type == ""`` means "all types"."""
        self._last_filters = (memory_type or None, pinned_only, include_archived)
        fire_and_forget(self._browse(memory_type or None, pinned_only, include_archived))

    @Slot(str, bool)
    def set_pinned(self, memory_id: str, pinned: bool) -> None:
        fire_and_forget(self._set_pinned(memory_id, pinned))

    @Slot(str)
    def archive(self, memory_id: str) -> None:
        fire_and_forget(self._archive(memory_id))

    @Slot(str)
    def forget(self, memory_id: str) -> None:
        fire_and_forget(self._forget(memory_id))

    # ------------------------------------------------------------------
    # Async helpers
    # ------------------------------------------------------------------
    async def _browse(
        self,
        memory_type: str | None,
        pinned_only: bool,
        include_archived: bool,
        *,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> None:
        self.busy_changed.emit(True)
        try:
            records: list[MemoryRecord] = await self._service.browse(
                memory_type=memory_type,
                pinned_only=pinned_only,
                include_archived=include_archived,
                start_date=start_date,
                end_date=end_date,
            )
            self.memories_loaded.emit(records)
        except Exception as err:
            _logger.exception("Memory browse failed.")
            self.error.emit(str(err))
        finally:
            self.busy_changed.emit(False)

    async def _set_pinned(self, memory_id: str, pinned: bool) -> None:
        try:
            await self._service.set_pinned(memory_id, pinned=pinned)
            await self._browse(*self._last_filters)
        except Exception as err:
            _logger.exception("Pin toggle failed.")
            self.error.emit(str(err))

    async def _archive(self, memory_id: str) -> None:
        try:
            await self._service.archive_memory(memory_id)
            await self._browse(*self._last_filters)
        except Exception as err:
            _logger.exception("Archive failed.")
            self.error.emit(str(err))

    async def _forget(self, memory_id: str) -> None:
        try:
            await self._service.forget(memory_id)
            await self._browse(*self._last_filters)
        except Exception as err:
            _logger.exception("Delete failed.")
            self.error.emit(str(err))
