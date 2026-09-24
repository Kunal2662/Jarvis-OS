"""Workflow Builder API -- M7 Workflow Builder.

``/api/v1/workflows`` -- thin REST over ``WorkflowBuilderService``, the
same ``{data, meta}`` envelope and ``Depends(get_current_session)``
Bearer auth every resource router since M9 Task Group E uses.

**Seven routes**, matching the Logic Contract's own smallest-coherent-
surface decision (§13): create/list/retrieve/update/delete a workflow,
plus its execution history, plus a manual run. ``PATCH`` replaces
Scheduler/Home Automation's enable/disable pair -- a standalone
workflow has no "enabled" concept, since nothing triggers it.

**Status-code convention, mirroring ``routes/home_automation.py``'s
own exception-type dispatch**: ``WorkflowBuilderPermissionError`` ->
400; ``WorkflowNotFoundError`` -> 404; any other ``ServiceError`` (a
malformed step, an empty name, an empty steps list) -> 400.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from jarvis.infrastructure.api.auth import Envelope, envelope, get_current_session

if TYPE_CHECKING:
    from jarvis.services.workflow_builder_service import WorkflowBuilderService

router = APIRouter(tags=["workflows"], dependencies=[Depends(get_current_session)])


class WorkflowStepRequest(BaseModel):
    kind: str
    instruction: str = ""
    tool_name: str = ""
    tool_args: dict[str, Any] = {}
    depends_on: list[str] = []
    label: str = ""


class CreateWorkflowRequest(BaseModel):
    name: str
    steps: list[WorkflowStepRequest]
    description: str = ""


class UpdateWorkflowRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    steps: list[WorkflowStepRequest] | None = None


def _service(request: Request) -> WorkflowBuilderService:
    return cast("WorkflowBuilderService", request.app.state.container.workflow_builder_service())


def _handle(err: Exception) -> HTTPException:
    from jarvis.services.workflow_builder_service import (
        WorkflowBuilderPermissionError,
        WorkflowNotFoundError,
    )

    if isinstance(err, WorkflowBuilderPermissionError):
        return HTTPException(status_code=400, detail=str(err))
    if isinstance(err, WorkflowNotFoundError):
        return HTTPException(status_code=404, detail=str(err))
    return HTTPException(status_code=400, detail=str(err))


@router.post("/workflows", response_model=Envelope[dict[str, Any]])
async def create_workflow(
    body: CreateWorkflowRequest, request: Request
) -> Envelope[dict[str, Any]]:
    """Creates one standalone workflow. Permission not granted, an
    empty name, or a malformed/empty step list -> 400."""
    from jarvis.core.exceptions import ServiceError

    try:
        result = await _service(request).create_workflow(
            name=body.name,
            steps=[s.model_dump() for s in body.steps],
            description=body.description,
        )
    except ServiceError as err:
        raise _handle(err) from err
    return envelope(result, meta={"workflow_id": result["id"]})


@router.get("/workflows", response_model=Envelope[list[dict[str, Any]]])
async def list_workflows(request: Request) -> Envelope[list[dict[str, Any]]]:
    """Permission not granted -> 400. Never a 404 -- an empty result is
    a normal, valid list."""
    from jarvis.core.exceptions import ServiceError

    try:
        rows = await _service(request).list_workflows()
    except ServiceError as err:
        raise _handle(err) from err
    return envelope(rows, meta={"count": len(rows)})


@router.get("/workflows/{workflow_id}", response_model=Envelope[dict[str, Any]])
async def get_workflow(workflow_id: str, request: Request) -> Envelope[dict[str, Any]]:
    """Unknown workflow -> 404. Permission not granted -> 400."""
    from jarvis.core.exceptions import ServiceError

    try:
        result = await _service(request).get_workflow(workflow_id)
    except ServiceError as err:
        raise _handle(err) from err
    return envelope(result)


@router.patch("/workflows/{workflow_id}", response_model=Envelope[dict[str, Any]])
async def update_workflow(
    workflow_id: str, body: UpdateWorkflowRequest, request: Request
) -> Envelope[dict[str, Any]]:
    """Partial update -- only supplied fields change. Unknown workflow
    -> 404. A supplied, malformed/empty step list -> 400."""
    from jarvis.core.exceptions import ServiceError

    try:
        result = await _service(request).update_workflow(
            workflow_id,
            name=body.name,
            description=body.description,
            steps=[s.model_dump() for s in body.steps] if body.steps is not None else None,
        )
    except ServiceError as err:
        raise _handle(err) from err
    return envelope(result)


@router.delete("/workflows/{workflow_id}", response_model=Envelope[dict[str, Any]])
async def delete_workflow(workflow_id: str, request: Request) -> Envelope[dict[str, Any]]:
    """Unknown workflow -> 404. Permission not granted -> 400."""
    from jarvis.core.exceptions import ServiceError

    try:
        deleted = await _service(request).delete_workflow(workflow_id)
    except ServiceError as err:
        raise _handle(err) from err
    return envelope({"workflow_id": workflow_id, "deleted": deleted})


@router.post("/workflows/{workflow_id}/run", response_model=Envelope[dict[str, Any]])
async def run_workflow(workflow_id: str, request: Request) -> Envelope[dict[str, Any]]:
    """Manual run -- the only execution path (Logic Contract §9). Does
    not bypass action-level permission/confirmation. Unknown workflow
    -> 404. Permission not granted -> 400."""
    from jarvis.core.exceptions import ServiceError

    try:
        result = await _service(request).run_workflow(workflow_id)
    except ServiceError as err:
        raise _handle(err) from err
    return envelope(result)


@router.get("/workflows/{workflow_id}/executions", response_model=Envelope[list[dict[str, Any]]])
async def list_executions(
    workflow_id: str, request: Request, limit: int = 50
) -> Envelope[list[dict[str, Any]]]:
    """Unknown workflow -> 404. Permission not granted -> 400."""
    from jarvis.core.exceptions import ServiceError

    try:
        rows = await _service(request).list_executions(workflow_id, limit=limit)
    except ServiceError as err:
        raise _handle(err) from err
    return envelope(rows, meta={"count": len(rows)})
