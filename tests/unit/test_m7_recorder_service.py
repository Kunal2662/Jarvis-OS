"""RecorderService tests -- M7 Recorder.

Real (temp-file) SQLite throughout, matching every M7 service test's
own pattern -- ``PermissionModel``, ``AutomationService``,
``HistoryService``, ``WorkflowExecutionService``, ``WorkflowBuilderService``,
and ``RecorderService`` itself are all real; only ``FakeOSAutomation``
(the OS-automation side-effect boundary) is faked. Real automation
steps are actually run through ``AutomationService.run_command`` so
captured history is genuine, not seeded directly -- matching this
repo's own "fakes, not mocks" testing convention. See
``docs/M7_RECORDER_LOGIC_CONTRACT.md`` §21 for the required test
matrix this file implements.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.core.exceptions import ServiceError
from jarvis.services.recorder_service import (
    RECORDER_PRINCIPAL,
    RECORDER_SCOPE,
    RecorderPermissionError,
    RecorderService,
    RecordingSessionNotFoundError,
)
from jarvis.services.workflow_builder_service import (
    WORKFLOW_BUILDER_PRINCIPAL,
    WORKFLOW_BUILDER_SCOPE,
    WorkflowBuilderService,
)
from jarvis.services.workflow_execution_service import WorkflowExecutionService


def _settings(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("JARVIS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("JARVIS_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'jarvis.db'}")

    from jarvis.core.config import settings as settings_mod

    settings_mod.load_settings.cache_clear()  # type: ignore[attr-defined]
    return settings_mod.load_settings()


@pytest.fixture
async def db(tmp_path: Path, monkeypatch):
    settings = _settings(tmp_path, monkeypatch)
    from jarvis.infrastructure.database.sqlite_client import SQLiteDatabase

    database = SQLiteDatabase(settings.db)
    await database.initialize()
    try:
        yield database
    finally:
        await database.dispose()


@pytest.fixture
def settings(tmp_path: Path, monkeypatch):
    return _settings(tmp_path, monkeypatch)


@pytest.fixture
def permissions(tmp_path: Path):
    from jarvis.core.events.event_bus import EventBus
    from jarvis.core.plugins.permissions import PermissionModel

    return PermissionModel(EventBus(), store_path=tmp_path / "permissions.json")


@pytest.fixture
def automation(settings, db):
    from jarvis.services.automation_service import AutomationService
    from tests.fakes.fake_os_automation import FakeOSAutomation

    return AutomationService(FakeOSAutomation(), settings, database=db)


@pytest.fixture
def history(db):
    from jarvis.features.automation.history import HistoryService

    return HistoryService(db)


@pytest.fixture
def workflow_executor(settings, automation) -> WorkflowExecutionService:
    return WorkflowExecutionService(settings=settings, automation=automation)


@pytest.fixture
def workflow_builder(db, permissions, workflow_executor) -> WorkflowBuilderService:
    return WorkflowBuilderService(
        database=db, permissions=permissions, workflow_executor=workflow_executor
    )


@pytest.fixture
def service(db, permissions, history, workflow_builder) -> RecorderService:
    return RecorderService(
        database=db, permissions=permissions, history=history, workflow_builder=workflow_builder
    )


async def _grant_recorder(permissions) -> None:
    await permissions.grant(RECORDER_PRINCIPAL, RECORDER_SCOPE)


async def _grant_workflow_builder(permissions) -> None:
    await permissions.grant(WORKFLOW_BUILDER_PRINCIPAL, WORKFLOW_BUILDER_SCOPE)


async def _grant_both(permissions) -> None:
    await _grant_recorder(permissions)
    await _grant_workflow_builder(permissions)


async def _run_real_screenshot_step(workflow_executor: WorkflowExecutionService) -> None:
    """Actually executes a real automation step (via the real
    AutomationService/ActionExecutor/FakeOSAutomation chain), so
    HistoryService genuinely records it -- not a seeded fixture."""
    status, _error, _results = await workflow_executor.run_workflow(
        [{"kind": "automation", "instruction": "take a screenshot"}]
    )
    assert status == "succeeded"


# --- Permission ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_denied_without_grant(service: RecorderService) -> None:
    with pytest.raises(RecorderPermissionError):
        await service.start_recording()


@pytest.mark.asyncio
async def test_permission_declared_pending_at_construction(permissions) -> None:
    assert permissions.state(RECORDER_PRINCIPAL, RECORDER_SCOPE).value == "pending"


@pytest.mark.asyncio
async def test_list_denied_without_grant(service) -> None:
    with pytest.raises(RecorderPermissionError):
        await service.list_recordings()


# --- Session creation / start --------------------------------------------------------


@pytest.mark.asyncio
async def test_start_recording_creates_a_session(service, permissions) -> None:
    await _grant_recorder(permissions)
    session = await service.start_recording()
    assert session["status"] == "recording"
    assert session["stopped_at"] is None
    assert session["resulting_workflow_id"] is None


@pytest.mark.asyncio
async def test_start_recording_while_active_is_rejected(service, permissions) -> None:
    await _grant_recorder(permissions)
    await service.start_recording()
    with pytest.raises(ServiceError, match="already active"):
        await service.start_recording()


@pytest.mark.asyncio
async def test_get_recording_unknown_id_raises(service, permissions) -> None:
    await _grant_recorder(permissions)
    with pytest.raises(RecordingSessionNotFoundError):
        await service.get_recording("no-such-id")


@pytest.mark.asyncio
async def test_list_recordings(service, permissions) -> None:
    await _grant_recorder(permissions)
    assert await service.list_recordings() == []
    created = await service.start_recording()
    rows = await service.list_recordings()
    assert len(rows) == 1
    assert rows[0]["id"] == created["id"]


# --- Cancel ------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_recording(service, permissions) -> None:
    await _grant_recorder(permissions)
    session = await service.start_recording()
    cancelled = await service.cancel_recording(session["id"])
    assert cancelled["status"] == "cancelled"
    assert cancelled["resulting_workflow_id"] is None


@pytest.mark.asyncio
async def test_cancel_creates_no_workflow_and_leaves_history_untouched(
    service, permissions, workflow_builder, workflow_executor, history
) -> None:
    await _grant_both(permissions)
    session = await service.start_recording()
    await _run_real_screenshot_step(workflow_executor)
    await service.cancel_recording(session["id"])

    assert await workflow_builder.list_workflows() == []
    # The captured history row is still there, untouched, exactly as it
    # would be with no recording ever active.
    entries = await history.list_recent(limit=10)
    assert len(entries) == 1
    assert entries[0].status == "succeeded"


@pytest.mark.asyncio
async def test_cancel_unknown_id_raises(service, permissions) -> None:
    await _grant_recorder(permissions)
    with pytest.raises(RecordingSessionNotFoundError):
        await service.cancel_recording("no-such-id")


@pytest.mark.asyncio
async def test_after_start_can_start_again_once_cancelled(service, permissions) -> None:
    await _grant_recorder(permissions)
    first = await service.start_recording()
    await service.cancel_recording(first["id"])
    second = await service.start_recording()  # must not raise
    assert second["status"] == "recording"


# --- Stop / conversion / workflow creation --------------------------------------------


@pytest.mark.asyncio
async def test_stop_recording_with_zero_captured_steps_is_rejected(service, permissions) -> None:
    await _grant_both(permissions)
    session = await service.start_recording()
    with pytest.raises(ServiceError, match="Nothing supported"):
        await service.stop_recording(session["id"], name="Empty")


@pytest.mark.asyncio
async def test_stop_recording_unknown_id_raises(service, permissions) -> None:
    await _grant_both(permissions)
    with pytest.raises(RecordingSessionNotFoundError):
        await service.stop_recording("no-such-id", name="x")


@pytest.mark.asyncio
async def test_stop_recording_creates_a_workflow_via_workflow_builder(
    service, permissions, workflow_builder, workflow_executor
) -> None:
    await _grant_both(permissions)
    session = await service.start_recording()
    await _run_real_screenshot_step(workflow_executor)

    result = await service.stop_recording(session["id"], name="My Macro", description="desc")

    assert result["status"] == "completed"
    workflow = result["resulting_workflow"]
    assert workflow["name"] == "My Macro"
    assert workflow["description"] == "desc"
    assert len(workflow["steps"]) == 1
    step = workflow["steps"][0]
    assert step["kind"] == "automation"
    assert "screenshot" in step["instruction"].lower()
    assert step["label"] == "screenshot: "

    # Genuinely visible through Workflow Builder's own API -- not a
    # parallel persistence path (Logic Contract §10/Acceptance §2).
    listed = await workflow_builder.list_workflows()
    assert len(listed) == 1
    assert listed[0]["id"] == workflow["id"]


@pytest.mark.asyncio
async def test_stop_recording_sets_resulting_workflow_id_on_session(
    service, permissions, workflow_executor
) -> None:
    await _grant_both(permissions)
    session = await service.start_recording()
    await _run_real_screenshot_step(workflow_executor)
    result = await service.stop_recording(session["id"], name="x")

    fetched = await service.get_recording(session["id"])
    assert fetched["status"] == "completed"
    assert fetched["resulting_workflow_id"] == result["resulting_workflow"]["id"]


@pytest.mark.asyncio
async def test_stop_recording_excludes_steps_outside_the_time_window(
    service, permissions, workflow_executor
) -> None:
    """A step run BEFORE start_recording must never be captured --
    proves the boundary is genuinely time-windowed, not "everything in
    history ever"."""
    await _grant_both(permissions)
    await _run_real_screenshot_step(workflow_executor)  # before the window

    session = await service.start_recording()
    with pytest.raises(ServiceError, match="Nothing supported"):
        await service.stop_recording(session["id"], name="x")


@pytest.mark.asyncio
async def test_stop_recording_captures_multiple_steps_in_order(
    service, permissions, workflow_executor
) -> None:
    await _grant_both(permissions)
    session = await service.start_recording()
    await _run_real_screenshot_step(workflow_executor)
    await _run_real_screenshot_step(workflow_executor)

    result = await service.stop_recording(session["id"], name="x")
    assert len(result["resulting_workflow"]["steps"]) == 2


@pytest.mark.asyncio
async def test_stop_recording_permission_denied_for_workflow_builder(
    service, permissions, workflow_executor
) -> None:
    """Recording permission alone is NOT enough to create the
    resulting workflow -- workflow_builder is independently,
    separately re-checked every time (Logic Contract §11, Acceptance
    §3). This is the single most important permission-boundary test
    in this file."""
    await _grant_recorder(permissions)  # "workflow_builder" deliberately NOT granted
    session = await service.start_recording()
    await _run_real_screenshot_step(workflow_executor)

    from jarvis.services.workflow_builder_service import WorkflowBuilderPermissionError

    with pytest.raises(WorkflowBuilderPermissionError):
        await service.stop_recording(session["id"], name="x")


@pytest.mark.asyncio
async def test_stopping_an_already_completed_session_is_rejected(
    service, permissions, workflow_executor
) -> None:
    await _grant_both(permissions)
    session = await service.start_recording()
    await _run_real_screenshot_step(workflow_executor)
    await service.stop_recording(session["id"], name="x")

    with pytest.raises(ServiceError, match="not active"):
        await service.stop_recording(session["id"], name="y")


# --- Unsupported / failed history entries ---------------------------------------------


@pytest.mark.asyncio
async def test_unsupported_action_type_is_silently_excluded_not_an_error(
    service, permissions, db
) -> None:
    """An unrecognized `action` string in history must never crash
    conversion -- it's simply excluded, matching the deterministic-
    only, no-fallback mechanism (Logic Contract §5/§9)."""
    await _grant_both(permissions)
    session = await service.start_recording()

    from jarvis.infrastructure.database.repositories.task_history_repository import (
        TaskHistoryRepository,
    )

    async with db.session() as sess:
        await TaskHistoryRepository(sess).add(  # type: ignore[arg-type]
            plan_id="p1",
            action="some_future_action_type_this_build_does_not_know",
            target="x",
            status="succeeded",
        )

    with pytest.raises(ServiceError, match="Nothing supported"):
        await service.stop_recording(session["id"], name="x")


@pytest.mark.asyncio
async def test_failed_history_entry_is_excluded(service, permissions, db) -> None:
    """A failed step must never be replayed -- only `succeeded`
    entries are converted (Logic Contract §8)."""
    await _grant_both(permissions)
    session = await service.start_recording()

    from jarvis.infrastructure.database.repositories.task_history_repository import (
        TaskHistoryRepository,
    )

    async with db.session() as sess:
        await TaskHistoryRepository(sess).add(  # type: ignore[arg-type]
            plan_id="p1", action="screenshot", target=None, status="failed"
        )

    with pytest.raises(ServiceError, match="Nothing supported"):
        await service.stop_recording(session["id"], name="x")


@pytest.mark.asyncio
async def test_denied_history_entry_is_excluded(service, permissions, db) -> None:
    await _grant_both(permissions)
    session = await service.start_recording()

    from jarvis.infrastructure.database.repositories.task_history_repository import (
        TaskHistoryRepository,
    )

    async with db.session() as sess:
        await TaskHistoryRepository(sess).add(  # type: ignore[arg-type]
            plan_id="p1", action="screenshot", target=None, status="denied"
        )

    with pytest.raises(ServiceError, match="Nothing supported"):
        await service.stop_recording(session["id"], name="x")


# --- Fidelity (Logic Contract §5, Option A: action + target only) --------------------


@pytest.mark.asyncio
async def test_reconstructed_instruction_uses_action_and_target_only(
    service, permissions, db
) -> None:
    """Proves the deterministic template genuinely only ever sees
    `action`/`target` -- never the raw `args_json` a history row may
    also carry (Logic Contract §5 Option A, the accepted fidelity
    limitation)."""
    await _grant_both(permissions)
    session = await service.start_recording()

    from jarvis.infrastructure.database.repositories.task_history_repository import (
        TaskHistoryRepository,
    )

    async with db.session() as sess:
        await TaskHistoryRepository(sess).add(  # type: ignore[arg-type]
            plan_id="p1",
            action="open_app",
            target="Chrome",
            status="succeeded",
            # A richer args payload than `target` alone captures --
            # must NOT leak into the reconstructed instruction.
            args_json='{"name": "Chrome", "window_mode": "maximized", "profile": "work"}',
        )

    result = await service.stop_recording(session["id"], name="x")
    instruction = result["resulting_workflow"]["steps"][0]["instruction"]
    assert "Chrome" in instruction
    assert "maximized" not in instruction
    assert "profile" not in instruction
    assert result["resulting_workflow"]["steps"][0]["label"] == "open_app: Chrome"


# --- Concurrency ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_start_attempts_only_one_succeeds(service, permissions) -> None:
    import asyncio

    await _grant_recorder(permissions)
    results = await asyncio.gather(
        service.start_recording(), service.start_recording(), return_exceptions=True
    )
    succeeded = [r for r in results if not isinstance(r, Exception)]
    failed = [r for r in results if isinstance(r, Exception)]
    assert len(succeeded) == 1
    assert len(failed) == 1
    assert isinstance(failed[0], ServiceError)


# --- Scope guards --------------------------------------------------------------------


def test_recorder_service_introduces_no_forbidden_coupling() -> None:
    import inspect

    from jarvis.services import recorder_service

    source = inspect.getsource(recorder_service)
    for forbidden in (
        "MqttConnector",
        "HomeAssistantConnector",
        "from jarvis.core.events.event_bus import EventBus",
        "import schedule_service",
        "from jarvis.services.schedule_service",
        "import home_automation_service",
        "from jarvis.services.home_automation_service",
        "from jarvis.services.workflow_execution_service",
        "MemoryService",
        "SmartHomeMemoryService",
        "AnalyticsService",
        "RecipeManager",
    ):
        assert forbidden not in source


def test_recorder_service_never_imports_event_viewer() -> None:
    import importlib.util

    for module_name in (
        "jarvis.services.event_viewer_service",
        "jarvis.services.home_automation_analytics_service",
    ):
        assert importlib.util.find_spec(module_name) is None


def test_recorder_service_never_supplies_a_confirm_callback() -> None:
    import inspect

    from jarvis.services import recorder_service

    source = inspect.getsource(recorder_service)
    assert "_always_allow" not in source
    assert "auto_deny_when_unconfirmable=False" not in source


def test_recorder_service_never_imports_workflow_execution_service_directly() -> None:
    """Replay is exclusively WorkflowBuilderService.run_workflow() --
    RecorderService must never import WorkflowExecutionService itself
    (Logic Contract §10/Acceptance §criteria)."""
    import inspect

    from jarvis.services import recorder_service

    source = inspect.getsource(recorder_service)
    assert "from jarvis.services.workflow_execution_service" not in source
    assert "import workflow_execution_service" not in source
