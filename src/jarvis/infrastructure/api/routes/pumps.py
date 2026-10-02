"""Smart Pumps API -- Milestone 12 Smart Pumps (Switch-Backed Device
Slice).

``/api/v1/pumps/*`` -- thin REST over ``SmartPumpService``, the same
``{data, meta}`` envelope and ``Depends(get_current_session)`` Bearer
auth every resource router since M9 Task Group E uses, matching
``routes/smart_switches.py`` exactly.

**Three routes only (state / on / off), and deliberately no ``GET
/pumps`` list route.** A pump is a switch-backed device, so the existing
``GET /switches`` already enumerates every pump-controllable device --
a ``GET /pumps`` would be a byte-for-byte duplicate of it. The service
layer has no ``list_pumps`` for the same reason.

**Reads are not permission-gated here** (same as ``routes/smart_switches
.py``): a pump's on/off state carries no privacy weight, inherited from
the switch read precedent. Mutations are permission-gated by the
delegated ``SmartSwitchService``'s own ``core:smart_switch`` grant under
the shared ``smart_home`` scope; grant it via the existing generic
plugin-permissions route.

**No confirmation concept exists on the REST surface.** Interactive
confirmation for ``pump_on``/``pump_off`` is an agent-tool-level concern
(``AgentPermissionGate``, ``AgentSettings.confirm_required_tools``),
never a REST one -- identical to ``routes/sirens.py``'s ``turn_on``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Request

from jarvis.infrastructure.api.auth import Envelope, envelope, get_current_session

if TYPE_CHECKING:
    from jarvis.services.smart_pump_service import SmartPumpService

router = APIRouter(tags=["smart-pumps"], dependencies=[Depends(get_current_session)])


def _pumps(request: Request) -> SmartPumpService:
    return cast("SmartPumpService", request.app.state.container.smart_pump_service())


def _bad_request(err: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(err))


@router.get("/pumps/{device_id}", response_model=Envelope[dict[str, Any]])
async def get_pump(device_id: str, request: Request) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        state = await _pumps(request).get_state(device_id)
    except ServiceError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    return envelope(state)


@router.post("/pumps/{device_id}/on", response_model=Envelope[dict[str, Any]])
async def turn_pump_on(device_id: str, request: Request) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        result = await _pumps(request).turn_on(device_id)
    except ServiceError as err:
        raise _bad_request(err) from err
    return envelope(result, meta={"success": result["success"]})


@router.post("/pumps/{device_id}/off", response_model=Envelope[dict[str, Any]])
async def turn_pump_off(device_id: str, request: Request) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        result = await _pumps(request).turn_off(device_id)
    except ServiceError as err:
        raise _bad_request(err) from err
    return envelope(result, meta={"success": result["success"]})
