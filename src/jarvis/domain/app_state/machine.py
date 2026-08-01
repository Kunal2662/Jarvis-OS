"""Generic, reusable lifecycle state machine (UI overhaul, Logic
Foundation phase).

Build order for every future module, per the UI overhaul brief:

    1. Business Logic   -- what determines a module's state, in prose
                            (see the per-module notes in
                            MODULE_DEFAULT_STATES).
    2. State Machine     -- this file: enforce that a module can only
                            move through states its lifecycle actually
                            allows.
    3. Service Layer     -- a real class (GmailService, SpotifyService,
                            ...) that *uses* this machine.
    4. API / Provider
       Integration       -- the real OAuth/API client behind that
                            service.
    5. UI Rendering      -- a view that reads ModuleStateMachine.current
                            and renders it, never inventing data.

This file is step 2 only. It holds no reference to any service,
provider, DI container, or Qt widget -- pure logic, unit-testable with
zero mocking, exactly like domain/automation and domain/workflow.
"""

from __future__ import annotations

from jarvis.core.exceptions import InvalidStateTransitionError
from jarvis.domain.app_state.models import ConnectionState, ModuleState

# Legal next states per current state. Self-transitions (re-entering the
# same state, e.g. re-confirming READY after a no-op refresh) are always
# allowed and handled in code below, not listed here.
_TRANSITIONS: dict[ConnectionState, frozenset[ConnectionState]] = {
    ConnectionState.NOT_INSTALLED: frozenset({ConnectionState.NOT_CONFIGURED}),
    ConnectionState.NOT_CONFIGURED: frozenset({ConnectionState.CONNECTING}),
    ConnectionState.CONNECTING: frozenset(
        {ConnectionState.AUTHENTICATING, ConnectionState.CONNECTED, ConnectionState.ERROR}
    ),
    ConnectionState.AUTHENTICATING: frozenset({ConnectionState.CONNECTED, ConnectionState.ERROR}),
    ConnectionState.CONNECTED: frozenset(
        {
            ConnectionState.SYNCING,
            ConnectionState.READY,
            ConnectionState.EMPTY,
            ConnectionState.ERROR,
        }
    ),
    ConnectionState.SYNCING: frozenset(
        {
            ConnectionState.READY,
            ConnectionState.EMPTY,
            ConnectionState.ERROR,
            ConnectionState.OFFLINE,
        }
    ),
    ConnectionState.READY: frozenset(
        {
            ConnectionState.SYNCING,
            ConnectionState.EMPTY,
            ConnectionState.OFFLINE,
            ConnectionState.ERROR,
            ConnectionState.DISCONNECTED,
        }
    ),
    ConnectionState.EMPTY: frozenset(
        {
            ConnectionState.SYNCING,
            ConnectionState.READY,
            ConnectionState.OFFLINE,
            ConnectionState.ERROR,
            ConnectionState.DISCONNECTED,
        }
    ),
    ConnectionState.OFFLINE: frozenset(
        {
            ConnectionState.CONNECTING,
            ConnectionState.SYNCING,
            ConnectionState.READY,
            ConnectionState.EMPTY,
            ConnectionState.DISCONNECTED,
            ConnectionState.ERROR,
        }
    ),
    ConnectionState.ERROR: frozenset(
        {
            ConnectionState.CONNECTING,
            ConnectionState.DISCONNECTED,
            ConnectionState.NOT_CONFIGURED,
        }
    ),
    ConnectionState.DISCONNECTED: frozenset(
        {ConnectionState.CONNECTING, ConnectionState.NOT_CONFIGURED}
    ),
}


class ModuleStateMachine:
    """Owns one module's :class:`ModuleState`, and refuses to move it to
    a state the lifecycle graph above doesn't allow from wherever it
    currently is. Every future module's Service Layer (step 3) holds
    one of these rather than a bare ``ConnectionState`` field, so
    "the UI must never invent data" has a single enforcement point:
    if a service tries an illegal jump (e.g. NOT_CONFIGURED straight to
    SYNCING, skipping CONNECTING), this raises instead of silently
    letting the UI render a state that was never actually reached.
    """

    def __init__(
        self, module: str, *, initial: ConnectionState = ConnectionState.NOT_CONFIGURED
    ) -> None:
        self._module = module
        self._current = ModuleState(state=initial)
        self._history: list[ModuleState] = [self._current]

    @property
    def module(self) -> str:
        return self._module

    @property
    def current(self) -> ModuleState:
        return self._current

    @property
    def state(self) -> ConnectionState:
        return self._current.state

    def can_transition_to(self, target: ConnectionState) -> bool:
        if target == self._current.state:
            return True
        return target in _TRANSITIONS.get(self._current.state, frozenset())

    def transition_to(
        self, target: ConnectionState, *, detail: str = "", error: str | None = None
    ) -> ModuleState:
        if not self.can_transition_to(target):
            raise InvalidStateTransitionError(
                f"{self._module}: cannot move from "
                f"{self._current.state.value!r} to {target.value!r}"
            )
        self._current = ModuleState(state=target, detail=detail, error=error)
        self._history.append(self._current)
        return self._current

    def history(self) -> list[ModuleState]:
        """Every state this machine has been in, oldest first --
        diagnostic/testing use, not meant to drive application logic."""
        return list(self._history)
