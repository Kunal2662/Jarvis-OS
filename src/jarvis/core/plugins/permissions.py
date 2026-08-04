"""Permission Model -- Milestone 9 Task Group D, Phase 5.

The real implementation of :class:`~jarvis.core.plugins.sdk.
IPermissionChecker` the Extension API (Phase 4) depends on the shape
of. A manifest *declaring* a permission (``docs/ARCHITECTURE.md``
section 10) is a request, never an automatic grant -- least-privilege
default, matching this project's own "Plugin Safe Core Architecture"
requirement (``docs/MASTER_ROADMAP.md`` section 8's Plugin Platform
module): every declared scope starts ``PENDING`` and stays denied
(:meth:`is_granted` returns ``False``) until an explicit :meth:`grant`
call.

**User approval workflow, honestly scoped.** This task group has no
attached interactive UI (Developer Mode's real approval dialog is
frontend work, M8/M9 Task Group E's Developer Platform Tools). What's
real here is the *workflow itself*: declare -> pending -> grant/deny
(each a real, persisted state transition with an audit trail and a
published event) -- :meth:`pending` is the actual queue a future
approval surface reads from and calls :meth:`grant`/:meth:`deny`
against; nothing about the mechanism is faked, only its visual
front-end is future work.

Grants persist across restarts (``config_dir`` convention, the same
one ``CrashRecoveryManager``/``ApiCenterService`` already use) --
re-declaring a plugin's permissions on every startup never resets a
user's prior decision.
"""

from __future__ import annotations

import enum
import json
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from jarvis.core.events.events import PluginPermissionDeniedEvent, PluginPermissionGrantedEvent
from jarvis.core.logging.logger import get_logger

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from jarvis.core.events.event_bus import EventBus

_logger = get_logger("jarvis.core.plugins.permissions")

DEFAULT_AUDIT_LOG_SIZE = 500


class PermissionState(enum.StrEnum):
    PENDING = "pending"
    GRANTED = "granted"
    DENIED = "denied"


@dataclass(frozen=True, slots=True)
class PermissionAuditEntry:
    plugin_id: str
    scope: str
    action: str  # "declared" | "granted" | "denied" | "revoked" | "denied_check"
    at: datetime


class PermissionModel:
    def __init__(
        self,
        event_bus: EventBus,
        *,
        store_path: Path,
        audit_log_size: int = DEFAULT_AUDIT_LOG_SIZE,
    ) -> None:
        self._event_bus = event_bus
        self._store_path = store_path
        self._grants: dict[str, dict[str, PermissionState]] = {}
        self._audit: deque[PermissionAuditEntry] = deque(maxlen=audit_log_size)
        self._load()

    # ---- Declaration ------------------------------------------------------
    def declare(self, plugin_id: str, scopes: Sequence[str]) -> None:
        """Registers each of *scopes* as ``PENDING`` if this plugin has
        no prior recorded decision for it. Safe to call on every
        startup/reload -- an existing GRANTED/DENIED decision is never
        reset by re-declaring the same scope."""
        plugin_grants = self._grants.setdefault(plugin_id, {})
        changed = False
        for scope in scopes:
            if scope not in plugin_grants:
                plugin_grants[scope] = PermissionState.PENDING
                self._audit_add(plugin_id, scope, "declared")
                changed = True
        if changed:
            self._save()

    # ---- Checking (IPermissionChecker) -------------------------------------
    def is_granted(self, plugin_id: str, scope: str) -> bool:
        state = self._grants.get(plugin_id, {}).get(scope, PermissionState.PENDING)
        granted = state is PermissionState.GRANTED
        if not granted:
            self._audit_add(plugin_id, scope, "denied_check")
        return granted

    def state(self, plugin_id: str, scope: str) -> PermissionState:
        return self._grants.get(plugin_id, {}).get(scope, PermissionState.PENDING)

    def pending(self) -> tuple[tuple[str, str], ...]:
        """Every ``(plugin_id, scope)`` pair still awaiting a decision
        -- the real, live queue a future approval surface polls."""
        return tuple(
            (plugin_id, scope)
            for plugin_id, scopes in self._grants.items()
            for scope, state in scopes.items()
            if state is PermissionState.PENDING
        )

    # ---- Decisions ------------------------------------------------------
    async def grant(self, plugin_id: str, scope: str) -> None:
        self._set_state(plugin_id, scope, PermissionState.GRANTED)
        self._audit_add(plugin_id, scope, "granted")
        self._save()
        await self._event_bus.publish(
            PluginPermissionGrantedEvent(plugin_id=plugin_id, scope=scope)
        )

    async def deny(self, plugin_id: str, scope: str) -> None:
        self._set_state(plugin_id, scope, PermissionState.DENIED)
        self._audit_add(plugin_id, scope, "denied")
        self._save()
        await self._event_bus.publish(PluginPermissionDeniedEvent(plugin_id=plugin_id, scope=scope))

    async def revoke(self, plugin_id: str, scope: str) -> None:
        """Returns a previously-decided scope to ``PENDING`` -- a
        revoke is never a silent re-denial; it requires a fresh
        decision, the same least-privilege default a never-declared
        scope gets."""
        self._set_state(plugin_id, scope, PermissionState.PENDING)
        self._audit_add(plugin_id, scope, "revoked")
        self._save()

    def _set_state(self, plugin_id: str, scope: str, state: PermissionState) -> None:
        self._grants.setdefault(plugin_id, {})[scope] = state

    # ---- Audit ------------------------------------------------------------
    @property
    def audit_log(self) -> tuple[PermissionAuditEntry, ...]:
        return tuple(self._audit)

    def _audit_add(self, plugin_id: str, scope: str, action: str) -> None:
        self._audit.append(
            PermissionAuditEntry(
                plugin_id=plugin_id, scope=scope, action=action, at=datetime.now(UTC)
            )
        )

    # ---- Persistence ------------------------------------------------------
    def _load(self) -> None:
        if not self._store_path.exists():
            return
        try:
            raw = json.loads(self._store_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as err:
            _logger.warning("Could not read permission store {}: {}", self._store_path, err)
            return
        valid_values = {state.value for state in PermissionState}
        for plugin_id, scopes in raw.items():
            self._grants[plugin_id] = {
                scope: PermissionState(state)
                for scope, state in scopes.items()
                if state in valid_values
            }

    def _save(self) -> None:
        try:
            self._store_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                plugin_id: {scope: state.value for scope, state in scopes.items()}
                for plugin_id, scopes in self._grants.items()
            }
            self._store_path.write_text(json.dumps(payload), encoding="utf-8")
        except OSError as err:
            _logger.warning("Could not write permission store {}: {}", self._store_path, err)
