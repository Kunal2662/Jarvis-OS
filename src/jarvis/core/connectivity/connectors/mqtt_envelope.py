"""JARVIS-native MQTT message envelope -- Milestone 12 Task Group B,
Phase 3.

The canonical wire format for any device that speaks to JARVIS over
MQTT without adopting Home Assistant's own discovery/state convention
-- the format a future JARVIS-native ESP32 sketch (or any other
bespoke firmware) targets. `MqttConnector` (`mqtt.py`) is the only
reader/writer of this format today; it is specified here, on its own,
because it is meant to outlive this one connector and be referenced by
firmware that has never seen this codebase.

**Shape.** One envelope, one discriminator, one flexible body -- not
five unrelated payload shapes:

    {
      "schema_version": 1,
      "device_id": "<the device's own stable identifier>",
      "type": "state" | "command" | "discovery" | "availability" | "error",
      "timestamp": "<ISO 8601, UTC, e.g. 2026-08-07T12:34:56.789012+00:00>",
      "payload": { ... type-specific, see the ``build_*`` functions below ... }
    }

**Versioning.** ``schema_version`` is a plain integer, not a semver
string -- this is a device-to-cloud wire format for constrained
firmware, not a library API. A breaking change to the envelope's own
shape (not a payload's) bumps the integer; `SUPPORTED_SCHEMA_VERSIONS`
names every version this build still reads. An additive field inside
``payload`` (a new optional key a newer firmware sends, an older one
omits) does **not** need a version bump -- every parser here already
treats missing optional keys as absent, not as an error, the same
tolerance `DiscoveredDevice`'s own optional fields already have.
Encountering an envelope whose ``schema_version`` is not in
`SUPPORTED_SCHEMA_VERSIONS` is a parse failure (`EnvelopeError`), not a
best-effort partial read -- a firmware speaking a version this build
does not understand should fail loudly during development, not have
its state silently misread.

**Timestamp.** ISO 8601, UTC, with an explicit ``+00:00`` offset --
the same shape `datetime.now(UTC).isoformat()` already produces
throughout this codebase (`core/connectivity/credential_store.py`'s
`EncryptionMetadata`, for one). Parsing also accepts a trailing ``Z``
defensively, since a constrained device's own JSON serializer is more
likely to emit that than a timezone offset.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

#: Every schema version this build can still read. One entry today;
#: a future breaking change adds a new one rather than replacing it,
#: so a fleet of not-yet-updated devices does not go dark the moment
#: JARVIS itself updates.
SUPPORTED_SCHEMA_VERSIONS: frozenset[int] = frozenset({1})

#: The version this build writes when JARVIS is the sender (commands).
CURRENT_SCHEMA_VERSION = 1

#: The closed set of envelope discriminators. Closed by design, the
#: same reasoning `CONNECTOR_TYPES`/`DEVICE_TYPES` already apply
#: elsewhere in this module: a typo'd type should fail parsing, not
#: silently become an unrecognized no-op.
ENVELOPE_TYPES: frozenset[str] = frozenset(
    {"state", "command", "discovery", "availability", "error"}
)


class EnvelopeError(Exception):
    """Raised for any envelope that cannot be trusted: malformed JSON,
    a missing required field, an unsupported ``schema_version``, or a
    ``type`` outside `ENVELOPE_TYPES`. The caller (`MqttConnector`)
    catches this per-message, so one malformed envelope on the wire
    never takes down the subscription loop -- the same fault isolation
    `ConnectorCredentialStore` already applies to its own records."""


@dataclass(frozen=True, slots=True)
class MqttEnvelope:
    """One parsed (or about-to-be-published) envelope. ``payload``'s
    shape depends on ``type`` -- see the ``build_*``/``*_from_envelope``
    function pairs below for each type's own contract."""

    device_id: str
    type: str
    timestamp: datetime
    payload: dict[str, Any] = field(default_factory=dict)
    schema_version: int = CURRENT_SCHEMA_VERSION

    def to_json(self) -> str:
        return json.dumps(
            {
                "schema_version": self.schema_version,
                "device_id": self.device_id,
                "type": self.type,
                "timestamp": self.timestamp.isoformat(),
                "payload": self.payload,
            }
        )

    @classmethod
    def from_json(cls, raw: bytes | str) -> MqttEnvelope:
        text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        try:
            data = json.loads(text)
        except ValueError as err:
            raise EnvelopeError(f"envelope is not valid JSON: {err}") from err
        if not isinstance(data, dict):
            raise EnvelopeError("envelope must be a JSON object.")

        schema_version = data.get("schema_version")
        if not isinstance(schema_version, int) or schema_version not in SUPPORTED_SCHEMA_VERSIONS:
            raise EnvelopeError(
                f"unsupported or missing schema_version {schema_version!r}; "
                f"supported: {sorted(SUPPORTED_SCHEMA_VERSIONS)}"
            )

        envelope_type = data.get("type")
        if envelope_type not in ENVELOPE_TYPES:
            raise EnvelopeError(f"unknown envelope type {envelope_type!r}")

        device_id = data.get("device_id")
        if not isinstance(device_id, str) or not device_id:
            raise EnvelopeError("envelope is missing a non-empty 'device_id'.")

        timestamp = _parse_timestamp(data.get("timestamp"))

        payload = data.get("payload")
        if payload is None:
            payload = {}
        if not isinstance(payload, dict):
            raise EnvelopeError("envelope 'payload' must be a JSON object.")

        return cls(
            device_id=device_id,
            type=envelope_type,
            timestamp=timestamp,
            payload=payload,
            schema_version=schema_version,
        )


def _parse_timestamp(value: Any) -> datetime:
    if not value:
        raise EnvelopeError("envelope is missing a 'timestamp'.")
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as err:
        raise EnvelopeError(f"envelope 'timestamp' is not valid ISO 8601: {value!r}") from err


# ---------------------------------------------------------------------------
# Builders -- JARVIS is the sender (used for outgoing commands).
# ---------------------------------------------------------------------------


def build_command_envelope(
    device_id: str, command: str, args: dict[str, Any] | None = None
) -> MqttEnvelope:
    """Required: ``command`` (str). Optional: ``args`` (object,
    default ``{}``) -- the command's own parameters, e.g.
    ``{"brightness": 128}``."""
    return MqttEnvelope(
        device_id=device_id,
        type="command",
        timestamp=datetime.now(UTC),
        payload={"command": command, "args": dict(args or {})},
    )


# ---------------------------------------------------------------------------
# Readers -- a device is the sender (used for incoming state/discovery/
# availability/error messages). Each raises `EnvelopeError` on a
# structurally invalid payload for its own type -- caught by the same
# per-message try/except `MqttConnector` already applies to every
# incoming message, never left to propagate out of the read loop.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class NativeState:
    """``payload`` contract for ``type="state"``: required ``status``
    (str); optional ``attributes`` (object, default ``{}``)."""

    status: str
    attributes: dict[str, Any]


def state_from_envelope(envelope: MqttEnvelope) -> NativeState:
    if envelope.type != "state":
        raise EnvelopeError(f"expected a 'state' envelope, got {envelope.type!r}.")
    status = envelope.payload.get("status")
    if not isinstance(status, str) or not status:
        raise EnvelopeError("state envelope is missing a non-empty 'status'.")
    attributes = envelope.payload.get("attributes") or {}
    if not isinstance(attributes, dict):
        raise EnvelopeError("state envelope 'attributes' must be a JSON object.")
    return NativeState(status=status, attributes=dict(attributes))


@dataclass(frozen=True, slots=True)
class NativeDiscovery:
    """``payload`` contract for ``type="discovery"``: required
    ``name`` (str). Optional: ``device_type`` (str, default
    ``"other"`` -- validated against Task Group A's own closed
    `DEVICE_TYPES` by the caller, not here, since this module knows
    nothing about the smart-home domain), ``manufacturer``, ``model``
    (str, default ``""``), ``metadata`` (object, default ``{}``)."""

    name: str
    device_type: str
    manufacturer: str
    model: str
    metadata: dict[str, Any]


def discovery_from_envelope(envelope: MqttEnvelope) -> NativeDiscovery:
    if envelope.type != "discovery":
        raise EnvelopeError(f"expected a 'discovery' envelope, got {envelope.type!r}.")
    name = envelope.payload.get("name")
    if not isinstance(name, str) or not name:
        raise EnvelopeError("discovery envelope is missing a non-empty 'name'.")
    metadata = envelope.payload.get("metadata") or {}
    if not isinstance(metadata, dict):
        raise EnvelopeError("discovery envelope 'metadata' must be a JSON object.")
    return NativeDiscovery(
        name=name,
        device_type=str(envelope.payload.get("device_type") or "other"),
        manufacturer=str(envelope.payload.get("manufacturer") or ""),
        model=str(envelope.payload.get("model") or ""),
        metadata=dict(metadata),
    )


@dataclass(frozen=True, slots=True)
class NativeAvailability:
    """``payload`` contract for ``type="availability"``: required
    ``available`` (bool)."""

    available: bool


def availability_from_envelope(envelope: MqttEnvelope) -> NativeAvailability:
    if envelope.type != "availability":
        raise EnvelopeError(f"expected an 'availability' envelope, got {envelope.type!r}.")
    available = envelope.payload.get("available")
    if not isinstance(available, bool):
        raise EnvelopeError("availability envelope 'available' must be a boolean.")
    return NativeAvailability(available=available)


@dataclass(frozen=True, slots=True)
class NativeError:
    """``payload`` contract for ``type="error"``: required ``code``,
    ``message`` (str). A device reporting its own fault -- logged by
    the connector, never raised as a Python exception, the same "a
    protocol-level report is real information, not a connector
    failure" reasoning `CommandResult.success=False` already applies."""

    code: str
    message: str


def error_from_envelope(envelope: MqttEnvelope) -> NativeError:
    if envelope.type != "error":
        raise EnvelopeError(f"expected an 'error' envelope, got {envelope.type!r}.")
    code = envelope.payload.get("code")
    message = envelope.payload.get("message")
    if not isinstance(code, str) or not code:
        raise EnvelopeError("error envelope is missing a non-empty 'code'.")
    if not isinstance(message, str):
        raise EnvelopeError("error envelope is missing a 'message'.")
    return NativeError(code=code, message=message)
