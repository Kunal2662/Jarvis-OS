"""Developer Platform Tools API -- Milestone 9 Task Group E, extended by
Milestone 12 Developer Tools (Connectivity / Integration Health Slice).

Debug Console/Live Logs, Performance Profiler, State Inspector, API
Inspector, and Plugin Diagnostics, all as thin REST reads over the real
``core/devtools/`` components -- this router owns no state of its own.
Live Logs' real-time half is the existing Runtime WebSocket API's
``devtools.log_captured`` relay (``core/lifecycle/runtime_ws_hub.py``),
not a second transport; this router only serves the bounded-history
query side.

Every route requires the same ``Depends(get_current_session)`` Bearer
auth and ``{data, meta}`` envelope as ``routes/plugins.py`` -- these are
developer-facing, not public, surfaces.

**Connectivity / Integration Health** (``docs/
M12_DEVELOPER_TOOLS_CONNECTIVITY_LOGIC_CONTRACT.md``) is a thin REST
read over ``DevtoolsConnectivityService`` (``services/
devtools_connectivity_service.py``) -- a ``services/``-layer class, not
a ``core/devtools/`` component, since it depends on ``ConnectivityService``/
``SmartHomeService`` and every existing ``core/devtools/`` component
depends only on other ``core/``-layer objects. Its route lives here
regardless, for URL-namespace consistency with every other Developer
Mode capability. No ``PermissionModel`` gate, matching this router's
other four capabilities exactly -- session auth only.

**Device Simulator** (``docs/
M12_DEVELOPER_TOOLS_DEVICE_SIMULATOR_LOGIC_CONTRACT.md``) is a thin
REST read/write over the ``SimulatorConnector`` singleton
(``core/connectivity/connectors/simulator.py``) -- the same instance
the DI composition root registers under the existing
``"home_assistant"`` connector-registry key when
``settings.devtools.simulator_enabled`` is on (Option C; see that
connector's own module docstring). These routes manage the
simulator's own in-memory device roster only -- discovery, import,
live state reads and command execution all continue to run through
the existing, unmodified generic Connectivity Layer routes
(``routes/connectivity.py``), never a simulator-specific duplicate.
No ``PermissionModel`` gate, matching every other devtools capability
-- session auth only; explicitly evaluated and not merely inherited,
see the Logic Contract §9.

**Device Diagnostics** (``docs/
M12_DEVELOPER_TOOLS_DEVICE_DIAGNOSTICS_LOGIC_CONTRACT.md``) is a single
read-only aggregate over three already-shipped calls
(``SmartHomeService.get_device``, ``ConnectivityService.
read_raw_state``, ``PermissionModel.state``), logic inline in this
route -- no new service, mirroring ``get_plugin_diagnostics``'s own
architecture in this same file exactly rather than
``DevtoolsConnectivityService``'s. Live connectivity read is
best-effort (a ``ConnectivityError`` never turns into an HTTP error,
matching every device-category service's own ``read_raw_state``
handling); the permission section resolves only the five device
categories with a single, unambiguous owning principal (light/switch/
lock/sensor/thermostat) -- ``appliance``/``camera``/every other
category reports an explicit unresolved principal rather than
duplicating any appliance service's own private domain-resolution
logic. Reported attributes are sanitized by key (never wholesale
``Device.metadata_json``) before inclusion. No ``PermissionModel`` gate
on the route itself, matching every other devtools capability --
explicitly evaluated, see the Logic Contract §8.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from jarvis.infrastructure.api.auth import Envelope, envelope, get_current_session

if TYPE_CHECKING:
    from jarvis.core.connectivity.connectors.simulator import SimulatorConnector
    from jarvis.core.devtools.api_inspector import ApiInspector
    from jarvis.core.devtools.debug_console import DebugConsole
    from jarvis.core.devtools.performance_profiler import PerformanceProfiler
    from jarvis.core.devtools.state_inspector import StateInspector
    from jarvis.core.plugins.permissions import PermissionModel
    from jarvis.core.plugins.registry import PluginRegistry
    from jarvis.services.connectivity_service import ConnectivityService
    from jarvis.services.devtools_connectivity_service import DevtoolsConnectivityService
    from jarvis.services.smart_home_service import SmartHomeService

router = APIRouter(tags=["devtools"], dependencies=[Depends(get_current_session)])

#: Milestone 12 Developer Tools (Device Diagnostics Slice). Closed to
#: exactly the five device categories with a single, unambiguous
#: owning `PermissionModel` principal -- see the Logic Contract §7 for
#: why `"appliance"`/`"camera"`/every other category is deliberately
#: left unresolved rather than guessed.
_DIAGNOSTICS_SCOPE = "smart_home"
_DEVICE_TYPE_PRINCIPALS: dict[str, str] = {
    "light": "core:smart_lighting",
    "switch": "core:smart_switch",
    "lock": "core:smart_locks",
    "sensor": "core:sensors",
    "thermostat": "core:thermostats",
}

#: Substrings (matched case-insensitively against an attribute's own
#: key) whose *value* is redacted before inclusion in a diagnostic
#: response -- Logic Contract §6/§7. Every other key/value passes
#: through verbatim; for the five categories in
#: `_DEVICE_TYPE_PRINCIPALS`'s own device types this is data already
#: reachable today through that category's own existing read route, so
#: this list is a defense-in-depth control, not the only thing standing
#: between a live read and secret exposure.
_SENSITIVE_ATTRIBUTE_KEY_SUBSTRINGS = (
    "token",
    "password",
    "secret",
    "credential",
    "api_key",
    "apikey",
    "auth",
)
_REDACTED = "<redacted>"


class DefineSimulatedDeviceRequest(BaseModel):
    """``device_class``/``binary`` apply to ``device_type="sensor"``
    only -- see ``SimulatorConnector.define_device``."""

    device_type: str
    external_id: str | None = None
    name: str | None = None
    status: str | None = None
    attributes: dict[str, Any] | None = None
    device_class: str | None = None
    binary: bool = False


class SetSimulatorFaultRequest(BaseModel):
    """All fields optional; only a supplied field changes -- an
    omitted field leaves that device's current fault state as-is."""

    unavailable: bool | None = None
    force_command_failure: bool | None = None
    failure_detail: str | None = None


# ---------------------------------------------------------------------------
# Container accessors
# ---------------------------------------------------------------------------
def _debug_console(request: Request) -> DebugConsole:
    return cast("DebugConsole", request.app.state.container.debug_console())


def _performance_profiler(request: Request) -> PerformanceProfiler:
    return cast("PerformanceProfiler", request.app.state.container.performance_profiler())


def _state_inspector(request: Request) -> StateInspector:
    return cast("StateInspector", request.app.state.container.state_inspector())


def _api_inspector(request: Request) -> ApiInspector:
    return cast("ApiInspector", request.app.state.container.api_inspector())


def _plugin_registry(request: Request) -> PluginRegistry:
    return cast("PluginRegistry", request.app.state.container.plugin_registry())


def _permission_model(request: Request) -> PermissionModel:
    return cast("PermissionModel", request.app.state.container.permission_model())


def _devtools_connectivity(request: Request) -> DevtoolsConnectivityService:
    return cast(
        "DevtoolsConnectivityService", request.app.state.container.devtools_connectivity_service()
    )


def _simulator(request: Request) -> SimulatorConnector:
    return cast("SimulatorConnector", request.app.state.container.simulator_connector())


def _smart_home(request: Request) -> SmartHomeService:
    return cast("SmartHomeService", request.app.state.container.smart_home_service())


def _connectivity(request: Request) -> ConnectivityService:
    return cast("ConnectivityService", request.app.state.container.connectivity_service())


def _sanitize_attributes(attributes: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in attributes.items():
        lowered = key.lower()
        if any(marker in lowered for marker in _SENSITIVE_ATTRIBUTE_KEY_SUBSTRINGS):
            sanitized[key] = _REDACTED
        else:
            sanitized[key] = value
    return sanitized


# ---------------------------------------------------------------------------
# Debug Console / Live Logs
# ---------------------------------------------------------------------------
@router.get("/devtools/logs", response_model=Envelope[tuple[dict[str, Any], ...]])
async def get_debug_logs(
    request: Request,
    level: str | None = None,
    logger: str | None = None,
    contains: str | None = None,
    limit: int = 200,
) -> Envelope[tuple[dict[str, Any], ...]]:
    console = _debug_console(request)
    entries = console.entries(level=level, logger=logger, contains=contains, limit=limit)
    payload = tuple(
        {
            "at": e.at.isoformat(),
            "level": e.level,
            "logger": e.logger,
            "message": e.message,
            "module": e.module,
            "function": e.function,
            "line": e.line,
        }
        for e in entries
    )
    return envelope(payload, meta={"count": len(payload), "running": console.is_running})


@router.delete("/devtools/logs", response_model=Envelope[dict[str, Any]])
async def clear_debug_logs(request: Request) -> Envelope[dict[str, Any]]:
    _debug_console(request).clear()
    return envelope({"cleared": True})


# ---------------------------------------------------------------------------
# Performance Profiler
# ---------------------------------------------------------------------------
@router.get("/devtools/performance", response_model=Envelope[dict[str, Any]])
async def get_performance_current(request: Request) -> Envelope[dict[str, Any]]:
    return envelope(_performance_profiler(request).current())


@router.get("/devtools/performance/metrics", response_model=Envelope[tuple[str, ...]])
async def list_performance_metrics(request: Request) -> Envelope[tuple[str, ...]]:
    return envelope(_performance_profiler(request).tracked_metrics)


@router.get(
    "/devtools/performance/{metric}/history", response_model=Envelope[tuple[dict[str, Any], ...]]
)
async def get_performance_history(
    metric: str, request: Request
) -> Envelope[tuple[dict[str, Any], ...]]:
    samples = _performance_profiler(request).history(metric)
    payload = tuple({"value": s.value, "at": s.at} for s in samples)
    return envelope(payload, meta={"metric": metric, "count": len(payload)})


# ---------------------------------------------------------------------------
# State Inspector
# ---------------------------------------------------------------------------
@router.get("/devtools/state", response_model=Envelope[dict[str, Any]])
async def get_state_snapshot(request: Request) -> Envelope[dict[str, Any]]:
    snapshot = _state_inspector(request).snapshot()
    payload = {
        "services": [
            {"name": s.name, "state": s.state, "dependencies": s.dependencies, "error": s.error}
            for s in snapshot.services
        ],
        "plugins": [
            {
                "plugin_id": p.plugin_id,
                "display_name": p.display_name,
                "version": p.version,
                "state": p.state,
                "error": p.error,
            }
            for p in snapshot.plugins
        ],
        "startup_hooks": snapshot.startup_hooks,
        "shutdown_hooks": snapshot.shutdown_hooks,
    }
    return envelope(payload)


# ---------------------------------------------------------------------------
# API Inspector
# ---------------------------------------------------------------------------
@router.get("/devtools/api-calls", response_model=Envelope[tuple[dict[str, Any], ...]])
async def get_recent_api_calls(
    request: Request, limit: int = 100, path_contains: str | None = None
) -> Envelope[tuple[dict[str, Any], ...]]:
    records = _api_inspector(request).recent(limit=limit, path_contains=path_contains)
    payload = tuple(
        {
            "method": r.method,
            "path": r.path,
            "status_code": r.status_code,
            "duration_ms": r.duration_ms,
            "at": r.at,
        }
        for r in records
    )
    return envelope(payload, meta={"count": len(payload)})


# ---------------------------------------------------------------------------
# Plugin Diagnostics -- one combined view, not a fourth data source.
# ---------------------------------------------------------------------------
@router.get("/devtools/plugins/{plugin_id}/diagnostics", response_model=Envelope[dict[str, Any]])
async def get_plugin_diagnostics(plugin_id: str, request: Request) -> Envelope[dict[str, Any]]:
    registry = _plugin_registry(request)
    permission_model = _permission_model(request)
    console = _debug_console(request)

    status = registry.status(plugin_id)
    health = registry.health(plugin_id)
    related_logs = console.entries(contains=plugin_id, limit=50)
    audit_entries = tuple(e for e in permission_model.audit_log if e.plugin_id == plugin_id)

    payload = {
        "plugin_id": plugin_id,
        "state": status.state,
        "detail": status.detail,
        "healthy": health.healthy,
        "health_detail": health.detail,
        "recent_logs": [
            {"at": e.at.isoformat(), "level": e.level, "message": e.message} for e in related_logs
        ],
        "permission_audit": [
            {"scope": e.scope, "action": e.action, "at": e.at.isoformat()} for e in audit_entries
        ],
    }
    return envelope(payload)


# ---------------------------------------------------------------------------
# Connectivity / Integration Health -- Milestone 12 Developer Tools
# ---------------------------------------------------------------------------
@router.get("/devtools/connectivity", response_model=Envelope[dict[str, Any]])
async def get_connectivity_health(
    request: Request, home_id: str | None = None
) -> Envelope[dict[str, Any]]:
    """Connector registration/connection state plus per-home device-
    health counts. No ``home_id`` -> every home; a given ``home_id``
    that does not exist -> 404 (the only failure mode here -- no
    permission gate exists on this route, matching every other
    devtools capability)."""
    from jarvis.core.exceptions import ServiceError

    try:
        overview = await _devtools_connectivity(request).get_overview(home_id)
    except ServiceError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    return envelope(
        overview,
        meta={"connector_count": len(overview["connectors"]), "home_count": len(overview["homes"])},
    )


# ---------------------------------------------------------------------------
# Device Diagnostics -- Milestone 12 Developer Tools (Device Diagnostics Slice)
# ---------------------------------------------------------------------------
@router.get("/devtools/devices/{device_id}/diagnostics", response_model=Envelope[dict[str, Any]])
async def get_device_diagnostics(device_id: str, request: Request) -> Envelope[dict[str, Any]]:
    """One combined view over a device's own identity, live
    connectivity state, and owning permission-principal grant status --
    mirrors ``get_plugin_diagnostics``'s own architecture in this same
    file, not ``DevtoolsConnectivityService``'s. Unknown device -> 404;
    a failed live read is never an HTTP error, reported instead via
    ``connectivity.read_error`` (Logic Contract §5/§11). ``metadata_json``
    is never read or exposed."""
    from jarvis.core.exceptions import ServiceError
    from jarvis.core.interfaces.connectivity import ConnectivityError
    from jarvis.services.connectivity_service import connector_type_for

    smart_home = _smart_home(request)
    connectivity = _connectivity(request)
    permission_model = _permission_model(request)

    try:
        device = await smart_home.require_device(device_id)
    except ServiceError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err

    device_section = {
        "id": device.id,
        "name": device.name,
        "device_type": device.device_type,
        "status": device.status,
        "home_id": device.home_id,
        "room_id": device.room_id,
        "manufacturer": device.manufacturer,
        "model": device.model,
        "external_id": device.external_id,
        "last_seen_at": device.last_seen_at.isoformat() if device.last_seen_at else None,
    }

    connectivity_section: dict[str, Any] = {
        "connector_type": connector_type_for(device),
        "read_succeeded": False,
        "status": None,
        "attributes": None,
        "read_error": None,
    }
    try:
        raw = await connectivity.read_raw_state(device_id)
    except ConnectivityError as err:
        connectivity_section["read_error"] = str(err)
    else:
        if raw is None:
            connectivity_section["read_error"] = "device has no recorded connector"
        else:
            connectivity_section["read_succeeded"] = True
            connectivity_section["status"] = raw.status
            connectivity_section["attributes"] = _sanitize_attributes(raw.attributes)

    principal = _DEVICE_TYPE_PRINCIPALS.get(device.device_type)
    if principal is None:
        if device.device_type == "appliance":
            detail = (
                "appliance device_type spans multiple principals "
                "(core:appliances / core:media_players / core:vacuum_humidifier / "
                "core:water_heaters); not resolved by this diagnostic"
            )
        else:
            detail = "no dedicated permission principal exists for this device_type"
        permission_section: dict[str, Any] = {
            "principal": None,
            "scope": None,
            "state": None,
            "detail": detail,
        }
    else:
        state = permission_model.state(principal, _DIAGNOSTICS_SCOPE)
        permission_section = {
            "principal": principal,
            "scope": _DIAGNOSTICS_SCOPE,
            "state": state.value,
            "detail": None,
        }

    payload = {
        "device": device_section,
        "connectivity": connectivity_section,
        "permission": permission_section,
    }
    return envelope(payload, meta={"device_type": device.device_type})


# ---------------------------------------------------------------------------
# Device Simulator -- Milestone 12 Developer Tools (Device Simulator Slice)
#
# Roster management only. Discovery, import, live state reads and
# command execution all run through the existing, unmodified generic
# Connectivity Layer routes (routes/connectivity.py) -- see this
# module's own docstring and the Logic Contract §10 for why no
# simulator-specific discover/import/state/command route exists here.
# ---------------------------------------------------------------------------
@router.post("/devtools/simulator/devices", response_model=Envelope[dict[str, Any]])
async def define_simulated_device(
    body: DefineSimulatedDeviceRequest, request: Request
) -> Envelope[dict[str, Any]]:
    """Defines (or fully redefines, if ``external_id`` already exists)
    one simulated device in the simulator's own in-memory roster.
    ``device_type`` must be one of the five MVP categories -- any other
    value is a 400, never a silent no-op."""
    from jarvis.core.interfaces.connectivity import ConnectivityError

    try:
        device = _simulator(request).define_device(
            device_type=body.device_type,
            external_id=body.external_id,
            name=body.name,
            status=body.status,
            attributes=body.attributes,
            device_class=body.device_class,
            binary=body.binary,
        )
    except ConnectivityError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    return envelope(device)


@router.get("/devtools/simulator/devices", response_model=Envelope[list[dict[str, Any]]])
async def list_simulated_devices(request: Request) -> Envelope[list[dict[str, Any]]]:
    """Every device currently in the simulator's own roster, with its
    current live state and fault configuration -- an empty list is a
    normal, valid state, never an error."""
    devices = _simulator(request).list_devices()
    return envelope(devices, meta={"count": len(devices)})


@router.delete("/devtools/simulator/devices/{external_id}", response_model=Envelope[dict[str, Any]])
async def delete_simulated_device(external_id: str, request: Request) -> Envelope[dict[str, Any]]:
    """Removes one device from the simulator's own roster. Does not
    touch any already-imported ``Device``/``Home`` database row --
    those are removed through the existing, unmodified generic
    ``DELETE /api/v1/devices/{id}`` route."""
    deleted = _simulator(request).delete_device(external_id)
    return envelope({"deleted": deleted})


@router.post(
    "/devtools/simulator/devices/{external_id}/fault", response_model=Envelope[dict[str, Any]]
)
async def set_simulated_device_fault(
    external_id: str, body: SetSimulatorFaultRequest, request: Request
) -> Envelope[dict[str, Any]]:
    """Deterministic, caller-controlled fault configuration -- never
    random. Unknown ``external_id`` -> 404."""
    from jarvis.core.interfaces.connectivity import ConnectivityError

    try:
        device = _simulator(request).set_fault(
            external_id,
            unavailable=body.unavailable,
            force_command_failure=body.force_command_failure,
            failure_detail=body.failure_detail,
        )
    except ConnectivityError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    return envelope(device)


@router.post("/devtools/simulator/reset", response_model=Envelope[dict[str, Any]])
async def reset_simulator(request: Request) -> Envelope[dict[str, Any]]:
    """Clears the simulator's entire in-memory roster. Never touches
    already-imported ``Device``/``Home`` database rows -- those persist
    exactly like any other device until explicitly deleted through the
    existing generic device route."""
    cleared = _simulator(request).reset()
    return envelope({"cleared": cleared})
