"""Domain value objects for the standardized application-state
architecture (UI overhaul, Logic Foundation phase).

Pure data -- no imports from ``infrastructure``, ``services``, ``agents``,
``ui`` or ``core.di`` -- mirroring :mod:`jarvis.domain.automation.models`
and :mod:`jarvis.domain.workflow.models`. This is the *foundation* only:
the enum, the value object, and the documented default state per module.
Wiring a real service/provider behind each module (Service Layer, API
Integration) and rendering these states in the UI (UI Rendering) are
later, separately-approved phases -- see the module docstring in
:mod:`jarvis.domain.app_state.machine` for why this ordering matters.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ConnectionState(StrEnum):
    """The one standardized lifecycle every connected module (Gmail,
    Spotify, Calendar, Finance, Weather, Smart Home, ...) reports
    through -- see :data:`MODULE_DEFAULT_STATES` for which states a
    given module actually uses in practice, and
    :mod:`jarvis.domain.app_state.machine` for the legal transitions
    between them.
    """

    NOT_INSTALLED = "not_installed"
    NOT_CONFIGURED = "not_configured"
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    AUTHENTICATING = "authenticating"
    CONNECTED = "connected"
    SYNCING = "syncing"
    READY = "ready"
    EMPTY = "empty"
    OFFLINE = "offline"
    ERROR = "error"


class ConversationTurnState(StrEnum):
    """The lifecycle of one voice or chat turn -- a different shape from
    :class:`ConnectionState` on purpose: a turn is a linear pipeline
    that runs once per user utterance/message, not a persistent
    connection. Shared between Voice (the roadmap's "remove the orb,
    replace it with a conversation timeline" requirement) and Chat
    (every message must "visibly show" each of these steps) since both
    describe the same underlying pipeline shape.
    """

    LISTENING = "listening"
    TRANSCRIBING = "transcribing"
    THINKING = "thinking"
    RESPONDING = "responding"
    SPEAKING = "speaking"  # voice only; chat goes straight to READY after RESPONDING
    READY = "ready"


@dataclass(frozen=True, slots=True)
class ModuleState:
    """A module's current lifecycle position plus why it's there --
    what :class:`~jarvis.domain.app_state.machine.ModuleStateMachine`
    holds and what the (future) UI layer renders from, verbatim, never
    substituting invented data for a state this doesn't report."""

    state: ConnectionState
    detail: str = ""
    error: str | None = None
    updated_at: datetime = field(default_factory=_utcnow)


# Every module named in the UI overhaul brief, and the state it starts
# in on a fresh install -- documented here as the single source of
# truth for "what does 'no fake data' actually mean for this module,"
# not yet wired to any real resolver (that's Service Layer / API
# Integration, later phases).
#
# Gmail / Spotify / Calendar / Finance / Weather / Smart Home: no real
# provider exists anywhere in this codebase (confirmed by repository
# audit -- only Mock* fixtures under features/integrations/mocks.py) --
# NOT_CONFIGURED is the only state consistent with reality until a real
# integration lands (M9 Integration Platform).
#
# Tasks / Schedule / Memory: local-only, no "connection" concept at
# all -- start EMPTY on a fresh install, populated only by real user/
# automation/AI action. Memory already has a real backend
# (MemoryService); Tasks and Schedule do not exist as modules yet.
MODULE_DEFAULT_STATES: dict[str, ConnectionState] = {
    "gmail": ConnectionState.NOT_CONFIGURED,
    "spotify": ConnectionState.NOT_CONFIGURED,
    "calendar": ConnectionState.NOT_CONFIGURED,
    "finance": ConnectionState.NOT_CONFIGURED,
    "weather": ConnectionState.NOT_CONFIGURED,
    "smart_home": ConnectionState.NOT_CONFIGURED,
    "tasks": ConnectionState.EMPTY,
    "schedule": ConnectionState.EMPTY,
    "memory": ConnectionState.EMPTY,
}
