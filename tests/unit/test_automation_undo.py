"""Unit tests for :class:`UndoManager`."""

from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.core.config.settings import Settings
from jarvis.core.exceptions import UndoNotSupportedError
from jarvis.domain.automation.models import ActionType, UndoRecord
from jarvis.features.automation.undo import UndoManager
from jarvis.infrastructure.automation.actions.base import ActionContext
from tests.fakes.fake_os_automation import FakeOSAutomation


@pytest.fixture()
def ctx(tmp_path: Path) -> ActionContext:
    return ActionContext(settings=Settings(data_dir=tmp_path), os_automation=FakeOSAutomation())


@pytest.mark.asyncio
async def test_undo_last_reverses_create_folder(ctx: ActionContext, tmp_path: Path) -> None:
    folder = tmp_path / "Work"
    folder.mkdir()
    undo = UndoManager()
    undo.push(
        UndoRecord(
            step_id="s1",
            action=ActionType.CREATE_FOLDER,
            undo_args={"path": str(folder), "pre_existing": False},
        )
    )

    record = await undo.undo_last(ctx)

    assert record is not None
    assert not folder.exists()


@pytest.mark.asyncio
async def test_undo_last_on_empty_stack_returns_none(ctx: ActionContext) -> None:
    undo = UndoManager()
    assert await undo.undo_last(ctx) is None


@pytest.mark.asyncio
async def test_undo_non_reversible_action_raises(ctx: ActionContext) -> None:
    undo = UndoManager()
    undo.push(UndoRecord(step_id="s1", action=ActionType.OPEN_APP, undo_args={}))
    with pytest.raises(UndoNotSupportedError):
        await undo.undo_last(ctx)


def test_max_size_evicts_oldest() -> None:
    undo = UndoManager(max_size=2)
    for i in range(3):
        undo.push(UndoRecord(step_id=str(i), action=ActionType.CREATE_FOLDER, undo_args={}))
    ids = [r.step_id for r in undo.history]
    assert ids == ["1", "2"]
