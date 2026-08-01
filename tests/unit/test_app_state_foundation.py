"""UI overhaul, Logic Foundation phase -- tests for the standardized
application-state architecture.

Foundation only: the ConnectionState enum, the ModuleState value
object, and ModuleStateMachine's transition enforcement. No service,
provider, or UI wiring exists yet -- those are later, separately-
approved phases.
"""

from __future__ import annotations

import pytest

from jarvis.core.exceptions import InvalidStateTransitionError
from jarvis.domain.app_state import (
    MODULE_DEFAULT_STATES,
    ConnectionState,
    ConversationTurnState,
    ModuleState,
    ModuleStateMachine,
)

# ---------------------------------------------------------------------------
# ConnectionState / ConversationTurnState / ModuleState
# ---------------------------------------------------------------------------


def test_connection_state_has_every_documented_value() -> None:
    values = {member.value for member in ConnectionState}
    assert values == {
        "not_installed",
        "not_configured",
        "disconnected",
        "connecting",
        "authenticating",
        "connected",
        "syncing",
        "ready",
        "empty",
        "offline",
        "error",
    }


def test_conversation_turn_state_has_every_documented_value() -> None:
    values = {member.value for member in ConversationTurnState}
    assert values == {"listening", "transcribing", "thinking", "responding", "speaking", "ready"}


def test_module_state_defaults() -> None:
    state = ModuleState(state=ConnectionState.NOT_CONFIGURED)

    assert state.state is ConnectionState.NOT_CONFIGURED
    assert state.detail == ""
    assert state.error is None
    assert state.updated_at is not None


def test_module_state_carries_detail_and_error() -> None:
    state = ModuleState(
        state=ConnectionState.ERROR, detail="Token expired", error="401 Unauthorized"
    )

    assert state.detail == "Token expired"
    assert state.error == "401 Unauthorized"


# ---------------------------------------------------------------------------
# MODULE_DEFAULT_STATES
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "module",
    ["gmail", "spotify", "calendar", "finance", "weather", "smart_home"],
)
def test_unintegrated_modules_default_to_not_configured(module: str) -> None:
    # No real backend exists for any of these (confirmed by repository
    # audit -- only Mock* fixtures) -- NOT_CONFIGURED is the only state
    # consistent with reality until a real integration lands.
    assert MODULE_DEFAULT_STATES[module] is ConnectionState.NOT_CONFIGURED


@pytest.mark.parametrize("module", ["tasks", "schedule", "memory"])
def test_local_only_modules_default_to_empty(module: str) -> None:
    assert MODULE_DEFAULT_STATES[module] is ConnectionState.EMPTY


# ---------------------------------------------------------------------------
# ModuleStateMachine
# ---------------------------------------------------------------------------


def test_starts_at_the_given_initial_state() -> None:
    machine = ModuleStateMachine("gmail", initial=ConnectionState.NOT_CONFIGURED)

    assert machine.state is ConnectionState.NOT_CONFIGURED
    assert machine.module == "gmail"
    assert machine.current.state is ConnectionState.NOT_CONFIGURED


def test_defaults_to_not_configured_when_no_initial_given() -> None:
    machine = ModuleStateMachine("spotify")

    assert machine.state is ConnectionState.NOT_CONFIGURED


def test_full_connect_flow_gmail_style() -> None:
    machine = ModuleStateMachine("gmail", initial=ConnectionState.NOT_CONFIGURED)

    machine.transition_to(ConnectionState.CONNECTING)
    machine.transition_to(ConnectionState.AUTHENTICATING)
    machine.transition_to(ConnectionState.CONNECTED)
    machine.transition_to(ConnectionState.SYNCING)
    result = machine.transition_to(ConnectionState.READY, detail="12 unread")

    assert machine.state is ConnectionState.READY
    assert result.detail == "12 unread"
    assert [s.state for s in machine.history()] == [
        ConnectionState.NOT_CONFIGURED,
        ConnectionState.CONNECTING,
        ConnectionState.AUTHENTICATING,
        ConnectionState.CONNECTED,
        ConnectionState.SYNCING,
        ConnectionState.READY,
    ]


def test_empty_inbox_after_sync_is_a_legal_terminal_state() -> None:
    machine = ModuleStateMachine("gmail")
    machine.transition_to(ConnectionState.CONNECTING)
    machine.transition_to(ConnectionState.CONNECTED)

    machine.transition_to(ConnectionState.EMPTY, detail="No emails")

    assert machine.state is ConnectionState.EMPTY


def test_local_only_module_flow_tasks_style() -> None:
    """Tasks/Schedule/Memory never touch CONNECTING/AUTHENTICATING --
    they just move directly between EMPTY and READY as local data
    appears or is cleared."""
    machine = ModuleStateMachine("tasks", initial=ConnectionState.EMPTY)

    machine.transition_to(ConnectionState.READY, detail="1 task")
    assert machine.state is ConnectionState.READY

    machine.transition_to(ConnectionState.EMPTY, detail="Task completed and cleared")
    assert machine.state is ConnectionState.EMPTY


def test_same_state_transition_is_always_allowed() -> None:
    machine = ModuleStateMachine("gmail", initial=ConnectionState.READY)

    result = machine.transition_to(ConnectionState.READY, detail="Refreshed, no changes")

    assert machine.state is ConnectionState.READY
    assert result.detail == "Refreshed, no changes"


def test_error_is_reachable_from_every_connecting_stage() -> None:
    for start in (
        ConnectionState.CONNECTING,
        ConnectionState.AUTHENTICATING,
        ConnectionState.CONNECTED,
        ConnectionState.SYNCING,
        ConnectionState.READY,
        ConnectionState.EMPTY,
        ConnectionState.OFFLINE,
    ):
        machine = ModuleStateMachine("gmail", initial=start)
        machine.transition_to(ConnectionState.ERROR, error="network failure")
        assert machine.state is ConnectionState.ERROR


def test_illegal_transition_raises_and_does_not_mutate_state() -> None:
    machine = ModuleStateMachine("gmail", initial=ConnectionState.NOT_CONFIGURED)

    with pytest.raises(InvalidStateTransitionError):
        machine.transition_to(ConnectionState.SYNCING)

    # Rejected transition must not have taken effect.
    assert machine.state is ConnectionState.NOT_CONFIGURED
    assert len(machine.history()) == 1


def test_can_transition_to_reports_without_raising() -> None:
    machine = ModuleStateMachine("gmail", initial=ConnectionState.NOT_CONFIGURED)

    assert machine.can_transition_to(ConnectionState.CONNECTING) is True
    assert machine.can_transition_to(ConnectionState.SYNCING) is False


def test_history_is_a_defensive_copy() -> None:
    machine = ModuleStateMachine("gmail")
    history = machine.history()
    history.append(ModuleState(state=ConnectionState.ERROR))

    assert len(machine.history()) == 1


def test_error_can_retry_or_give_up() -> None:
    machine = ModuleStateMachine("gmail", initial=ConnectionState.ERROR)

    assert machine.can_transition_to(ConnectionState.CONNECTING) is True
    assert machine.can_transition_to(ConnectionState.DISCONNECTED) is True
    assert machine.can_transition_to(ConnectionState.NOT_CONFIGURED) is True
    assert machine.can_transition_to(ConnectionState.READY) is False


def test_offline_can_recover_without_full_reconnect() -> None:
    """A transient network drop from READY shouldn't force a full
    reconnect through CONNECTING/AUTHENTICATING -- OFFLINE can go
    straight back to READY/EMPTY once connectivity returns."""
    machine = ModuleStateMachine("gmail", initial=ConnectionState.READY)
    machine.transition_to(ConnectionState.OFFLINE, detail="Network unavailable")

    assert machine.can_transition_to(ConnectionState.READY) is True
    machine.transition_to(ConnectionState.READY, detail="Back online")
    assert machine.state is ConnectionState.READY
