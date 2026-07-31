"""End-to-end unit tests for :class:`AutomationService` -- Milestone 4.

Exercises the full parser -> planner -> validator -> permission ->
executor -> undo -> history pipeline through the public facade only.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
async def service(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("JARVIS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("JARVIS_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'jarvis.db'}")
    monkeypatch.setenv("JARVIS_OPENAI_ENABLED", "false")
    monkeypatch.setenv("JARVIS_OLLAMA_ENABLED", "true")

    from jarvis.core.config import settings as settings_mod

    settings_mod.load_settings.cache_clear()  # type: ignore[attr-defined]
    settings = settings_mod.load_settings()

    from jarvis.infrastructure.database.sqlite_client import SQLiteDatabase
    from jarvis.services.automation_service import AutomationService
    from tests.fakes.fake_os_automation import FakeOSAutomation

    db = SQLiteDatabase(settings.db)
    await db.initialize()

    svc = AutomationService(FakeOSAutomation(), settings, database=db)
    try:
        yield svc
    finally:
        await db.dispose()


@pytest.mark.asyncio
async def test_run_command_creates_folder_and_records_history(service, tmp_path: Path) -> None:
    target = tmp_path / "Work"
    result = await service.run_command(f"create folder named {target}")

    assert result.succeeded
    assert target.is_dir()

    history = await service.list_history()
    assert len(history) == 1
    assert history[0].action == "create_folder"
    assert history[0].status == "succeeded"


@pytest.mark.asyncio
async def test_run_command_then_undo_last_removes_folder(service, tmp_path: Path) -> None:
    target = tmp_path / "Undoable"
    await service.run_command(f"create folder named {target}")
    assert target.is_dir()

    record = await service.undo_last()

    assert record is not None
    assert not target.exists()


@pytest.mark.asyncio
async def test_dangerous_action_without_confirmation_is_denied_and_recorded(
    service, tmp_path: Path
) -> None:
    target = tmp_path / "Sensitive"
    target.mkdir()
    result = await service.run_command(f"delete folder {target}")

    assert not result.succeeded
    assert target.exists()  # never actually deleted
    history = await service.list_history()
    assert history[0].status == "denied"


@pytest.mark.asyncio
async def test_save_and_run_recipe(service, tmp_path: Path) -> None:
    from jarvis.domain.automation.models import Recipe

    target = tmp_path / "RecipeFolder"
    service.save_recipe(Recipe(name="test_recipe", steps=[f"create folder named {target}"]))

    result = await service.run_recipe("test_recipe")

    assert result.succeeded
    assert target.is_dir()


@pytest.mark.asyncio
async def test_recipes_listed_include_bundled_morning_routine(service) -> None:
    names = {r.name for r in service.list_recipes()}
    assert "morning_routine" in names
