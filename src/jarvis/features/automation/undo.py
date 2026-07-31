"""Undo manager -- reverses reversible steps, most-recent-first.

In-memory only (a bounded deque): undo is meant for "oops, put that back"
within the current session, not a durable audit trail -- that's what
:mod:`~jarvis.features.automation.history` (SQLite) is for. Every
:class:`UndoRecord` still gets attached to its :class:`StepResult` in
history, so *what* was reversible is always visible even after the
in-memory stack is gone.
"""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

from jarvis.core.exceptions import UndoNotSupportedError
from jarvis.core.logging.logger import get_logger
from jarvis.domain.automation.models import UndoRecord
from jarvis.infrastructure.automation.actions.registry import get_action

if TYPE_CHECKING:
    from jarvis.infrastructure.automation.actions.base import ActionContext

_logger = get_logger("jarvis.features.automation.undo")


class UndoManager:
    def __init__(self, *, max_size: int = 50) -> None:
        self._stack: deque[UndoRecord] = deque(maxlen=max_size)

    def push(self, record: UndoRecord) -> None:
        self._stack.append(record)

    def peek(self) -> UndoRecord | None:
        return self._stack[-1] if self._stack else None

    @property
    def history(self) -> list[UndoRecord]:
        return list(self._stack)

    def clear(self) -> None:
        self._stack.clear()

    async def undo_last(self, ctx: ActionContext) -> UndoRecord | None:
        """Pop and reverse the most recent reversible step. Returns the
        record that was undone, or ``None`` if the stack was empty."""
        if not self._stack:
            return None
        record = self._stack.pop()
        await self._undo_record(ctx, record)
        return record

    async def undo_step(self, ctx: ActionContext, step_id: str) -> bool:
        """Undo a specific step by id, wherever it sits in the stack."""
        for record in reversed(self._stack):
            if record.step_id == step_id:
                await self._undo_record(ctx, record)
                self._stack.remove(record)
                return True
        return False

    async def _undo_record(self, ctx: ActionContext, record: UndoRecord) -> None:
        action = get_action(record.action)
        try:
            await action.undo(ctx, record.undo_args)
            _logger.info("Undid step {} ({}).", record.step_id, record.action.value)
        except NotImplementedError as err:
            raise UndoNotSupportedError(f"{record.action.value} is not undoable.") from err
