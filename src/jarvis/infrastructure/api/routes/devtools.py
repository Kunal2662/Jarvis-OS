"""Developer Platform Tools API -- Milestone 9 Task Group E.

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
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from fastapi import APIRouter, Depends, Request

from jarvis.infrastructure.api.auth import Envelope, envelope, get_current_session

if TYPE_CHECKING:
    from jarvis.core.devtools.api_inspector import ApiInspector
    from jarvis.core.devtools.debug_console import DebugConsole
    from jarvis.core.devtools.performance_profiler import PerformanceProfiler
    from jarvis.core.devtools.state_inspector import StateInspector
    from jarvis.core.plugins.permissions import PermissionModel
    from jarvis.core.plugins.registry import PluginRegistry

router = APIRouter(tags=["devtools"], dependencies=[Depends(get_current_session)])


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
