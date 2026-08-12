"""JARVIS-native MQTT envelope tests -- Milestone 12 Task Group B,
Phase 3."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from jarvis.core.connectivity.connectors.mqtt_envelope import (
    CURRENT_SCHEMA_VERSION,
    EnvelopeError,
    MqttEnvelope,
    availability_from_envelope,
    build_command_envelope,
    discovery_from_envelope,
    error_from_envelope,
    state_from_envelope,
)

# --- MqttEnvelope round-trip -----------------------------------------------------


def test_to_json_then_from_json_round_trips() -> None:
    original = MqttEnvelope(
        device_id="esp32-1",
        type="state",
        timestamp=datetime(2026, 8, 7, 12, 34, 56, tzinfo=UTC),
        payload={"status": "on", "attributes": {"brightness": 128}},
    )

    restored = MqttEnvelope.from_json(original.to_json())

    assert restored == original


def test_from_json_accepts_bytes() -> None:
    raw = MqttEnvelope(
        device_id="d1",
        type="availability",
        timestamp=datetime.now(UTC),
        payload={"available": True},
    ).to_json()

    restored = MqttEnvelope.from_json(raw.encode("utf-8"))

    assert restored.device_id == "d1"


def test_missing_payload_defaults_to_empty_dict() -> None:
    raw = json.dumps(
        {
            "schema_version": 1,
            "device_id": "d1",
            "type": "availability",
            "timestamp": "2026-08-07T12:00:00+00:00",
        }
    )

    envelope = MqttEnvelope.from_json(raw)

    assert envelope.payload == {}


# --- Validation --------------------------------------------------------------------


def test_rejects_invalid_json() -> None:
    with pytest.raises(EnvelopeError, match="not valid JSON"):
        MqttEnvelope.from_json("not json")


def test_rejects_a_non_object_top_level() -> None:
    with pytest.raises(EnvelopeError, match="JSON object"):
        MqttEnvelope.from_json("[1, 2, 3]")


def test_rejects_missing_schema_version() -> None:
    raw = json.dumps({"device_id": "d1", "type": "state", "timestamp": "2026-08-07T00:00:00+00:00"})
    with pytest.raises(EnvelopeError, match="schema_version"):
        MqttEnvelope.from_json(raw)


def test_rejects_an_unsupported_schema_version() -> None:
    raw = json.dumps(
        {
            "schema_version": 999,
            "device_id": "d1",
            "type": "state",
            "timestamp": "2026-08-07T00:00:00+00:00",
            "payload": {"status": "on"},
        }
    )
    with pytest.raises(EnvelopeError, match="unsupported"):
        MqttEnvelope.from_json(raw)


def test_rejects_an_unknown_type() -> None:
    raw = json.dumps(
        {
            "schema_version": 1,
            "device_id": "d1",
            "type": "not_a_real_type",
            "timestamp": "2026-08-07T00:00:00+00:00",
        }
    )
    with pytest.raises(EnvelopeError, match="unknown envelope type"):
        MqttEnvelope.from_json(raw)


def test_rejects_a_missing_device_id() -> None:
    raw = json.dumps(
        {"schema_version": 1, "type": "state", "timestamp": "2026-08-07T00:00:00+00:00"}
    )
    with pytest.raises(EnvelopeError, match="device_id"):
        MqttEnvelope.from_json(raw)


def test_rejects_a_missing_timestamp() -> None:
    raw = json.dumps({"schema_version": 1, "device_id": "d1", "type": "state"})
    with pytest.raises(EnvelopeError, match="timestamp"):
        MqttEnvelope.from_json(raw)


def test_rejects_an_unparseable_timestamp() -> None:
    raw = json.dumps(
        {
            "schema_version": 1,
            "device_id": "d1",
            "type": "state",
            "timestamp": "not-a-timestamp",
        }
    )
    with pytest.raises(EnvelopeError, match="ISO 8601"):
        MqttEnvelope.from_json(raw)


def test_accepts_a_trailing_z_timestamp() -> None:
    raw = json.dumps(
        {
            "schema_version": 1,
            "device_id": "d1",
            "type": "state",
            "timestamp": "2026-08-07T12:00:00Z",
            "payload": {"status": "on"},
        }
    )
    envelope = MqttEnvelope.from_json(raw)
    assert envelope.timestamp == datetime(2026, 8, 7, 12, 0, 0, tzinfo=UTC)


def test_rejects_a_non_object_payload() -> None:
    raw = json.dumps(
        {
            "schema_version": 1,
            "device_id": "d1",
            "type": "state",
            "timestamp": "2026-08-07T00:00:00+00:00",
            "payload": "not an object",
        }
    )
    with pytest.raises(EnvelopeError, match="payload"):
        MqttEnvelope.from_json(raw)


# --- build_command_envelope --------------------------------------------------------


def test_build_command_envelope_shape() -> None:
    envelope = build_command_envelope("d1", "turn_on", {"brightness": 200})

    assert envelope.device_id == "d1"
    assert envelope.type == "command"
    assert envelope.schema_version == CURRENT_SCHEMA_VERSION
    assert envelope.payload == {"command": "turn_on", "args": {"brightness": 200}}


def test_build_command_envelope_defaults_args_to_empty_dict() -> None:
    envelope = build_command_envelope("d1", "toggle")
    assert envelope.payload["args"] == {}


# --- state_from_envelope -----------------------------------------------------------


def test_state_from_envelope() -> None:
    envelope = MqttEnvelope(
        device_id="d1",
        type="state",
        timestamp=datetime.now(UTC),
        payload={"status": "on", "attributes": {"brightness": 5}},
    )
    state = state_from_envelope(envelope)
    assert state.status == "on"
    assert state.attributes == {"brightness": 5}


def test_state_from_envelope_defaults_attributes() -> None:
    envelope = MqttEnvelope(
        device_id="d1", type="state", timestamp=datetime.now(UTC), payload={"status": "on"}
    )
    assert state_from_envelope(envelope).attributes == {}


def test_state_from_envelope_requires_status() -> None:
    envelope = MqttEnvelope(device_id="d1", type="state", timestamp=datetime.now(UTC), payload={})
    with pytest.raises(EnvelopeError, match="status"):
        state_from_envelope(envelope)


def test_state_from_envelope_rejects_wrong_type() -> None:
    envelope = MqttEnvelope(
        device_id="d1", type="command", timestamp=datetime.now(UTC), payload={"command": "x"}
    )
    with pytest.raises(EnvelopeError, match="expected a 'state'"):
        state_from_envelope(envelope)


# --- discovery_from_envelope --------------------------------------------------------


def test_discovery_from_envelope() -> None:
    envelope = MqttEnvelope(
        device_id="d1",
        type="discovery",
        timestamp=datetime.now(UTC),
        payload={
            "name": "Kitchen Sensor",
            "device_type": "sensor",
            "manufacturer": "JARVIS",
            "model": "ESP32-S1",
            "metadata": {"firmware": "1.2.3"},
        },
    )
    info = discovery_from_envelope(envelope)
    assert info.name == "Kitchen Sensor"
    assert info.device_type == "sensor"
    assert info.manufacturer == "JARVIS"
    assert info.model == "ESP32-S1"
    assert info.metadata == {"firmware": "1.2.3"}


def test_discovery_from_envelope_defaults_device_type_to_other() -> None:
    envelope = MqttEnvelope(
        device_id="d1", type="discovery", timestamp=datetime.now(UTC), payload={"name": "Thing"}
    )
    info = discovery_from_envelope(envelope)
    assert info.device_type == "other"
    assert info.manufacturer == ""
    assert info.model == ""
    assert info.metadata == {}


def test_discovery_from_envelope_requires_name() -> None:
    envelope = MqttEnvelope(
        device_id="d1", type="discovery", timestamp=datetime.now(UTC), payload={}
    )
    with pytest.raises(EnvelopeError, match="name"):
        discovery_from_envelope(envelope)


# --- availability_from_envelope -----------------------------------------------------


def test_availability_from_envelope() -> None:
    envelope = MqttEnvelope(
        device_id="d1",
        type="availability",
        timestamp=datetime.now(UTC),
        payload={"available": False},
    )
    assert availability_from_envelope(envelope).available is False


def test_availability_from_envelope_requires_a_boolean() -> None:
    envelope = MqttEnvelope(
        device_id="d1",
        type="availability",
        timestamp=datetime.now(UTC),
        payload={"available": "yes"},
    )
    with pytest.raises(EnvelopeError, match="boolean"):
        availability_from_envelope(envelope)


# --- error_from_envelope -------------------------------------------------------------


def test_error_from_envelope() -> None:
    envelope = MqttEnvelope(
        device_id="d1",
        type="error",
        timestamp=datetime.now(UTC),
        payload={"code": "SENSOR_FAULT", "message": "temperature sensor disconnected"},
    )
    info = error_from_envelope(envelope)
    assert info.code == "SENSOR_FAULT"
    assert info.message == "temperature sensor disconnected"


def test_error_from_envelope_requires_code() -> None:
    envelope = MqttEnvelope(
        device_id="d1", type="error", timestamp=datetime.now(UTC), payload={"message": "oops"}
    )
    with pytest.raises(EnvelopeError, match="code"):
        error_from_envelope(envelope)
