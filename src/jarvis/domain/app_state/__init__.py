"""Standardized application-state architecture (UI overhaul, Logic
Foundation phase).

Everything in :mod:`jarvis.domain.app_state` is a plain, framework-free
value object plus one pure-logic state machine, mirroring
:mod:`jarvis.domain.automation` and :mod:`jarvis.domain.workflow`.
Foundation only -- no service, provider, or UI wiring exists yet; that's
later, separately-approved phases (see machine.py's module docstring).
"""

from __future__ import annotations

from jarvis.domain.app_state.machine import ModuleStateMachine
from jarvis.domain.app_state.models import (
    MODULE_DEFAULT_STATES,
    ConnectionState,
    ConversationTurnState,
    ModuleState,
)

__all__ = [
    "MODULE_DEFAULT_STATES",
    "ConnectionState",
    "ConversationTurnState",
    "ModuleState",
    "ModuleStateMachine",
]
