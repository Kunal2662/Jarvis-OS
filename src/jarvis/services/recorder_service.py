"""Recorder service -- M7 Recorder.

The single, DI-registered orchestration entry point for turning a
bounded window of JARVIS's own already-executed OS-automation actions
into a new, standalone ``WorkflowDefinition``. See
``docs/M7_RECORDER_LOGIC_CONTRACT.md`` for the full design -- this
docstring only summarizes the load-bearing decisions:

**"Watching" is querying, not subscribing (§4).** Capture is always
on, unconditionally, via the pre-existing ``HistoryService`` --
``start_recording`` is purely a timestamp marker, never a mode switch
on anything. ``stop_recording`` queries history bounded by that
marker. Zero new ``EventBus`` subscription or publish call exists
anywhere in this module.

**Reconstruction is deterministic, never AI-generated (§5/§9).** A
captured ``TaskHistoryEntry``'s ``action``/``target`` are mapped
through a fixed, hardcoded lookup table into a natural-language
``instruction`` -- the same field a hand-authored ``automation``-kind
``WorkflowStep`` already uses, re-parsed by the existing
``TaskPlanner`` at replay time, not a new execution path. The raw
``"{action}: {target}"`` summary is preserved unedited in the step's
own ``label`` field so a reviewing user can see what was actually
captured.

**Capture scope is OS-automation steps only (§6).** Only
``ActionExecutor``-routed steps have any existing capture mechanism.
Agent-tool invocations are never captured -- explicitly deferred, not
built here.

**Persistence and execution are entirely delegated (§7/§10).** This
module owns exactly one new table, ``recording_sessions`` -- a
bookkeeping marker, not a copy of captured data (that stays in the
pre-existing ``automation_task_history`` table, untouched). The
resulting workflow is created via the existing, already-tested
``WorkflowBuilderService.create_workflow()`` -- never a second
persistence path. Replay is exclusively
``WorkflowBuilderService.run_workflow()`` -- never a second execution
engine; this module never imports ``WorkflowExecutionService``.

**Permission separation (§11), stacked, not bypassed.**
``RECORDER_PRINCIPAL``/``RECORDER_SCOPE`` gate the recording-session
lifecycle only. ``stop_recording`` calls
``WorkflowBuilderService.create_workflow()`` directly, which
independently, separately re-checks its own ``workflow_builder``
permission every time -- recording permission never implies
workflow-creation permission.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

from jarvis.core.exceptions import ServiceError
from jarvis.core.logging.logger import get_logger
from jarvis.domain.automation.models import ActionType
from jarvis.infrastructure.database.repositories.recorder_repository import (
    RecordingSessionRepository,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from jarvis.core.interfaces.database import IDatabase
    from jarvis.core.plugins.permissions import PermissionModel
    from jarvis.features.automation.history import HistoryService
    from jarvis.infrastructure.database.models import RecordingSession
    from jarvis.services.workflow_builder_service import WorkflowBuilderService

_logger = get_logger("jarvis.services.recorder")

#: The `PermissionModel` identity this module declares and checks
#: against -- mirrors every prior M7 addition's exact naming
#: convention. Governs the recording-*session* lifecycle only; never
#: implies permission to create the resulting workflow (see module
#: docstring).
RECORDER_PRINCIPAL = "core:recorder"

#: Added to `core/plugins/sdk.py`'s `PERMISSION_SCOPES` this phase.
RECORDER_SCOPE = "recorder"


class RecorderPermissionError(ServiceError):
    """Raised by `_require_permission()` specifically -- a distinct
    subclass, matching every prior M7 service's own precedent, so the
    REST route can tell "not granted" apart from "not found" by
    exception type."""


class RecordingSessionNotFoundError(ServiceError):
    """A distinct subclass so the REST route can map this to 404
    specifically, matching every prior M7 service's own precedent."""


def _aware_utc(value: datetime) -> datetime:
    """SQLite round-trips a stored timestamp naive -- see
    `schedule_service._aware_utc`'s identical reasoning. This module
    keeps its own copy rather than importing a private helper across
    services."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


#: Deterministic ActionType -> instruction template (Logic Contract
#: §5/§9). Never AI-generated -- a fixed lookup, nothing else. Each
#: template receives the captured `target` string (may be empty).
#: An `ActionType` not present here (including `UNKNOWN`, and any
#: future/unrecognized action string) is treated as an unsupported
#: history entry and silently excluded from conversion, never raises.
_INSTRUCTION_TEMPLATES: dict[str, Any] = {
    ActionType.OPEN_APP.value: lambda t: (
        f"Open the {t} application." if t else "Open an application."
    ),
    ActionType.CLOSE_APP.value: lambda t: (
        f"Close the {t} application." if t else "Close an application."
    ),
    ActionType.LAUNCH_URL.value: lambda t: (
        f"Open {t} in the browser." if t else "Open a URL in the browser."
    ),
    ActionType.SEARCH_GOOGLE.value: lambda t: f"Search Google for {t}." if t else "Search Google.",
    ActionType.SEARCH_YOUTUBE.value: lambda t: (
        f"Search YouTube for {t}." if t else "Search YouTube."
    ),
    ActionType.SCREENSHOT.value: lambda t: "Take a screenshot.",
    ActionType.CLIPBOARD_COPY.value: lambda t: (
        f"Copy {t} to the clipboard." if t else "Copy the current selection to the clipboard."
    ),
    ActionType.CLIPBOARD_PASTE.value: lambda t: "Paste from the clipboard.",
    ActionType.CREATE_FOLDER.value: lambda t: (
        f"Create the folder {t}." if t else "Create a folder."
    ),
    ActionType.DELETE_FOLDER.value: lambda t: (
        f"Delete the folder {t}." if t else "Delete a folder."
    ),
    ActionType.RENAME.value: lambda t: f"Rename {t}." if t else "Rename a file or folder.",
    ActionType.MOVE.value: lambda t: f"Move {t}." if t else "Move a file or folder.",
    ActionType.COPY.value: lambda t: f"Copy {t}." if t else "Copy a file or folder.",
    ActionType.OPEN_EXPLORER.value: lambda t: "Open File Explorer.",
    ActionType.OPEN_DOWNLOADS.value: lambda t: "Open the Downloads folder.",
    ActionType.OPEN_DOCUMENTS.value: lambda t: "Open the Documents folder.",
    ActionType.EMPTY_RECYCLE_BIN.value: lambda t: "Empty the Recycle Bin.",
    ActionType.SET_VOLUME.value: lambda t: f"Set the volume to {t}." if t else "Set the volume.",
    ActionType.MUTE.value: lambda t: "Mute the volume.",
    ActionType.SET_BRIGHTNESS.value: lambda t: (
        f"Set the screen brightness to {t}." if t else "Set the screen brightness."
    ),
    ActionType.SHUTDOWN.value: lambda t: "Shut down the computer.",
    ActionType.RESTART.value: lambda t: "Restart the computer.",
    ActionType.SLEEP.value: lambda t: "Put the computer to sleep.",
    ActionType.LOCK_PC.value: lambda t: "Lock the computer.",
    ActionType.OPEN_SETTINGS.value: lambda t: "Open Settings.",
    ActionType.TERMINAL_COMMAND.value: lambda t: (
        f"Run the terminal command: {t}." if t else "Run a terminal command."
    ),
}


class RecorderService:
    def __init__(
        self,
        *,
        database: IDatabase,
        permissions: PermissionModel,
        history: HistoryService,
        workflow_builder: WorkflowBuilderService,
    ) -> None:
        self._db = database
        self._permissions = permissions
        self._history = history
        self._workflow_builder = workflow_builder
        self._permissions.declare(RECORDER_PRINCIPAL, [RECORDER_SCOPE])

    # ------------------------------------------------------------------
    # Permission
    # ------------------------------------------------------------------
    def _require_permission(self) -> None:
        if not self._permissions.is_granted(RECORDER_PRINCIPAL, RECORDER_SCOPE):
            raise RecorderPermissionError(
                "Recorder management requires the "
                f"{RECORDER_SCOPE!r} permission to be granted for "
                f"{RECORDER_PRINCIPAL!r}. Grant it via POST "
                f"/api/v1/plugins/{RECORDER_PRINCIPAL}/permissions/"
                f"{RECORDER_SCOPE}/grant."
            )

    # ------------------------------------------------------------------
    # Recording session lifecycle
    # ------------------------------------------------------------------
    async def start_recording(self) -> dict[str, Any]:
        self._require_permission()
        async with self._db.session() as sess:
            sess = cast("AsyncSession", sess)
            repo = RecordingSessionRepository(sess)
            if await repo.get_active() is not None:
                raise ServiceError(
                    "A recording is already active. Stop or cancel it before " "starting a new one."
                )
            row = await repo.add()
        return self._session_payload(row)

    async def get_recording(self, session_id: str) -> dict[str, Any]:
        self._require_permission()
        async with self._db.session() as sess:
            sess = cast("AsyncSession", sess)
            row = await RecordingSessionRepository(sess).get(session_id)
            if row is None:
                raise RecordingSessionNotFoundError(
                    f"Recording session {session_id!r} does not exist."
                )
        return self._session_payload(row)

    async def list_recordings(self) -> list[dict[str, Any]]:
        self._require_permission()
        async with self._db.session() as sess:
            sess = cast("AsyncSession", sess)
            rows = await RecordingSessionRepository(sess).list_all()
        return [self._session_payload(r) for r in rows]

    async def cancel_recording(self, session_id: str) -> dict[str, Any]:
        self._require_permission()
        now = datetime.now(UTC)
        async with self._db.session() as sess:
            sess = cast("AsyncSession", sess)
            existing = await RecordingSessionRepository(sess).get(session_id)
            if existing is None:
                raise RecordingSessionNotFoundError(
                    f"Recording session {session_id!r} does not exist."
                )
            row = await RecordingSessionRepository(sess).finish(
                session_id, status="cancelled", stopped_at=now
            )
        assert row is not None
        return self._session_payload(row)

    async def stop_recording(
        self, session_id: str, *, name: str, description: str = ""
    ) -> dict[str, Any]:
        """Converts everything captured during this session into a new
        standalone workflow (Logic Contract §8/§9). Does not
        pre-authorize or cache the `workflow_builder` permission check
        `WorkflowBuilderService.create_workflow()` performs internally
        -- it is re-evaluated fresh, every time (§11)."""
        self._require_permission()
        async with self._db.session() as sess:
            sess = cast("AsyncSession", sess)
            session_row = await RecordingSessionRepository(sess).get(session_id)
            if session_row is None:
                raise RecordingSessionNotFoundError(
                    f"Recording session {session_id!r} does not exist."
                )
            if session_row.status != "recording":
                raise ServiceError(
                    f"Recording session {session_id!r} is not active "
                    f"(status={session_row.status!r})."
                )
            started_at = _aware_utc(session_row.started_at)

        stopped_at = datetime.now(UTC)
        entries = await self._history.list_recent(limit=500)
        captured = [
            e
            for e in entries
            if started_at <= _aware_utc(e.created_at) < stopped_at and e.status == "succeeded"
        ]
        captured.sort(key=lambda e: e.created_at)

        steps: list[dict[str, Any]] = []
        for entry in captured:
            template = _INSTRUCTION_TEMPLATES.get(entry.action)
            if template is None:
                # Unsupported/unrecognized action -- excluded, not an
                # error (Logic Contract §5/§9's deterministic-only
                # mechanism has no fallback for an action it doesn't
                # know).
                continue
            steps.append(
                {
                    "kind": "automation",
                    "instruction": template(entry.target),
                    "label": f"{entry.action}: {entry.target or ''}",
                }
            )

        if not steps:
            raise ServiceError(
                "Nothing supported was captured during this recording -- no "
                "workflow was created."
            )

        workflow = await self._workflow_builder.create_workflow(
            name=name, steps=steps, description=description
        )

        async with self._db.session() as sess:
            sess = cast("AsyncSession", sess)
            row = await RecordingSessionRepository(sess).finish(
                session_id,
                status="completed",
                stopped_at=stopped_at,
                resulting_workflow_id=workflow["id"],
            )
        assert row is not None
        payload = self._session_payload(row)
        payload["resulting_workflow"] = workflow
        return payload

    # ------------------------------------------------------------------
    # Payload builders
    # ------------------------------------------------------------------
    def _session_payload(self, row: RecordingSession) -> dict[str, Any]:
        return {
            "id": row.id,
            "status": row.status,
            "started_at": _aware_utc(row.started_at).isoformat(),
            "stopped_at": (_aware_utc(row.stopped_at).isoformat() if row.stopped_at else None),
            "resulting_workflow_id": row.resulting_workflow_id,
        }
