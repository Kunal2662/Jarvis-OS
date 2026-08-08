"""The generated WebSocket contract stays in step with the relay.

``frontend/src/services/websocket/event-contract.generated.json`` is what
the React client checks its own event vocabulary against. If a milestone
adds an event to ``EVENT_TYPE_NAMES`` -- or renames a field on one that is
already relayed -- and does not regenerate the file, the frontend keeps
believing the old shape and its handlers silently stop matching. That is
precisely the failure M8 Phase 2 found and fixed, so it gets a test rather
than a convention.
"""

from __future__ import annotations

import json

import pytest
from scripts.export_ws_contract import CONTRACT_PATH, build_contract, render

from jarvis.core.lifecycle.runtime_ws_hub import EVENT_TYPE_NAMES


def test_generated_contract_is_current() -> None:
    """Regenerate with ``python scripts/export_ws_contract.py``."""
    assert CONTRACT_PATH.exists(), f"{CONTRACT_PATH} is missing -- run the export script."
    assert CONTRACT_PATH.read_text(encoding="utf-8") == render(build_contract()), (
        "The checked-in WebSocket contract is stale. Run "
        "`python scripts/export_ws_contract.py` and commit the result."
    )


def test_contract_covers_every_relayed_event() -> None:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    assert set(contract["events"]) == set(EVENT_TYPE_NAMES.values())


def test_envelope_fields_are_not_payload_fields() -> None:
    """``id`` and ``occurred_at`` live on the envelope, not in ``payload``."""
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    for name, fields in contract["events"].items():
        assert "id" not in fields, name
        assert "occurred_at" not in fields, name


@pytest.mark.parametrize(
    ("event_name", "expected_fields"),
    [
        ("voice.state_changed", ["detail", "state"]),
        ("agent.step", ["detail", "node", "status", "step", "thread_id"]),
        ("automation.step", ["action", "status", "step_id"]),
        ("notification.plugin", ["message", "plugin_id", "title"]),
        ("progress.update_phase", ["message", "phase", "progress_percent", "session_id"]),
        ("health.updated", ["snapshot"]),
    ],
)
def test_payload_shapes_the_frontend_types(event_name: str, expected_fields: list[str]) -> None:
    """The six payloads M8 Phase 2 gave TypeScript interfaces.

    Pinned explicitly as well as generated: these are the ones a typed
    frontend handler destructures, so a field rename here is a compile
    error there rather than an ``undefined`` at runtime.
    """
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    assert contract["events"][event_name] == expected_fields
