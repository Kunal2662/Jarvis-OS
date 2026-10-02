"""Recorder API -- M7 Recorder.

``/api/v1/recordings`` -- thin REST over ``RecorderService``, the same
``{data, meta}`` envelope and ``Depends(get_current_session)`` Bearer
auth every resource router since M9 Task Group E uses.

**Five routes**, matching the Logic Contract's own smallest-coherent-
surface decision (§15): start/stop/cancel a recording, plus list/get.
No ``DELETE`` route -- a completed/cancelled session is an inert
history record; the workflow it may have produced already has its own
`DELETE /api/v1/workflows/{id}`.

**Status-code convention, mirroring every prior M7 route file's own
exception-type dispatch**: ``RecorderPermissionError`` -> 400;
``RecordingSessionNotFoundError`` -> 404; any other ``ServiceError``
(already-active session, empty capture, session not in "recording"
state) -> 400. A ``stop`` call that fails because the caller lacks
``workflow_builder`` permission surfaces as
``WorkflowBuilderPermissionError``, which is also a ``ServiceError``
and is likewise mapped to 400 here -- Recorder never bypasses or
re-interprets that check (Logic Contract §11).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from jarvis.infrastructure.api.auth import Envelope, envelope, get_current_session

if TYPE_CHECKING:
    from jarvis.services.recorder_service import RecorderService

router = APIRouter(tags=["recorder"], dependencies=[Depends(get_current_session)])


class StopRecordingRequest(BaseModel):
    name: str
    description: str = ""


def _service(request: Request) -> RecorderService:
    return cast("RecorderService", request.app.state.container.recorder_service())


def _handle(err: Exception) -> HTTPException:
    from jarvis.services.recorder_service import (
        RecorderPermissionError,
        RecordingSessionNotFoundError,
    )

    if isinstance(err, RecorderPermissionError):
        return HTTPException(status_code=400, detail=str(err))
    if isinstance(err, RecordingSessionNotFoundError):
        return HTTPException(status_code=404, detail=str(err))
    return HTTPException(status_code=400, detail=str(err))


@router.post("/recordings/start", response_model=Envelope[dict[str, Any]])
async def start_recording(request: Request) -> Envelope[dict[str, Any]]:
    """Starts a new recording session. A second call while one is
    already active -> 400. Permission not granted -> 400."""
    from jarvis.core.exceptions import ServiceError

    try:
        result = await _service(request).start_recording()
    except ServiceError as err:
        raise _handle(err) from err
    return envelope(result, meta={"session_id": result["id"]})


@router.post("/recordings/{session_id}/stop", response_model=Envelope[dict[str, Any]])
async def stop_recording(
    session_id: str, body: StopRecordingRequest, request: Request
) -> Envelope[dict[str, Any]]:
    """Converts everything captured during this session into a new
    workflow via WorkflowBuilderService.create_workflow() -- never a
    second persistence path (Logic Contract §8/§10). Unknown session
    -> 404. Nothing supported was captured -> 400. Permission not
    granted for either "recorder" or (independently) "workflow_builder"
    -> 400."""
    from jarvis.core.exceptions import ServiceError

    try:
        result = await _service(request).stop_recording(
            session_id, name=body.name, description=body.description
        )
    except ServiceError as err:
        raise _handle(err) from err
    return envelope(result)


@router.post("/recordings/{session_id}/cancel", response_model=Envelope[dict[str, Any]])
async def cancel_recording(session_id: str, request: Request) -> Envelope[dict[str, Any]]:
    """Discards a recording session -- no workflow created, captured
    history rows are left untouched. Unknown session -> 404."""
    from jarvis.core.exceptions import ServiceError

    try:
        result = await _service(request).cancel_recording(session_id)
    except ServiceError as err:
        raise _handle(err) from err
    return envelope(result)


@router.get("/recordings", response_model=Envelope[list[dict[str, Any]]])
async def list_recordings(request: Request) -> Envelope[list[dict[str, Any]]]:
    """Permission not granted -> 400. Never a 404 -- an empty result is
    a normal, valid list."""
    from jarvis.core.exceptions import ServiceError

    try:
        rows = await _service(request).list_recordings()
    except ServiceError as err:
        raise _handle(err) from err
    return envelope(rows, meta={"count": len(rows)})


@router.get("/recordings/{session_id}", response_model=Envelope[dict[str, Any]])
async def get_recording(session_id: str, request: Request) -> Envelope[dict[str, Any]]:
    """Unknown session -> 404. Permission not granted -> 400."""
    from jarvis.core.exceptions import ServiceError

    try:
        result = await _service(request).get_recording(session_id)
    except ServiceError as err:
        raise _handle(err) from err
    return envelope(result)
