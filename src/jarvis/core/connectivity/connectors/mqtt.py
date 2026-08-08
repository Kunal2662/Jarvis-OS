"""MQTT connector -- Milestone 12 Task Group B, Phase 3.

The second real `IDeviceConnector` implementation, and structurally
the more involved one: unlike `HomeAssistantConnector`'s stateless
request/response REST calls, MQTT is a long-lived, push-based
subscription -- this connector owns a persistent broker connection,
an in-memory per-device state cache, and relies on its client
library's own reconnect handling rather than a hand-rolled loop.

**Library choice, corrected during implementation, not assumed.** The
Phase 3 approval report initially named `aiomqtt` (wraps `paho-mqtt`,
the same client Home Assistant's own core integration uses) as the
preferred candidate over `gmqtt`. Empirically connecting each against
a real local broker before writing connector logic against either
-- required by this project's "audit before implementing" discipline
-- found `aiomqtt` raises `NotImplementedError` on Windows' default
`ProactorEventLoop`: `paho-mqtt`'s asyncio bridge needs
`loop.add_reader`/`add_writer`, which only `SelectorEventLoop`
implements on Windows, and `SelectorEventLoop` cannot run
`core/mcp/transports/stdio.py`'s subprocess-based `StdioTransport`,
which this project already depends on. `gmqtt` is built on
`asyncio.Protocol`/`create_connection` instead and connected cleanly
on the same `ProactorEventLoop` with zero workaround, verified the
same way. This module uses `gmqtt`; see the Phase 3 milestone report
for the full comparison.

**Callback-based, not context-manager-based.** `gmqtt.Client.connect()`
is the only coroutine among the client's core operations --
`publish()`/`subscribe()`/`unsubscribe()` are synchronous (fire the
packet, return immediately), and `on_connect`/`on_message`/
`on_disconnect` are plain callbacks gmqtt invokes directly. This
connector's own message-routing logic (HA discovery/state parsing,
JARVIS-native envelope parsing, the state cache) needs no `await`
anywhere in that path, so every handler here is a synchronous method,
not a second async surface layered on top of a synchronous one.

**Reconnection is `gmqtt`'s own, not hand-rolled.** `gmqtt.Client`
retries automatically after a drop (unlimited retries, a configurable
fixed delay) and calls `on_connect` again on every successful
(re)connect -- including the first one. This connector's `_on_connect`
always re-subscribes to every known topic unconditionally, which is
correct whether it is firing for the first connection or the tenth
automatic reconnect, and needs no separate "is this a reconnect"
branch. `is_connected` reflects `_connected`, toggled only by
`_on_connect`/`_on_disconnect` -- the same two callbacks that fire for
both a caller-driven `connect()`/`disconnect()` and any automatic
reconnect gmqtt performs on its own.

**Two device-discovery conventions, not a general adapter framework**
(see `mqtt_envelope.py`'s own module docstring for the JARVIS-native
one):
- **Home Assistant MQTT Discovery** (`<discovery_prefix>/<component>/
  [<node_id>/]<object_id>/config`, retained) -- the convention already
  spoken by Zigbee2MQTT, zwave-js-to-mqtt, Tasmota and ESPHome. Reusing
  it here means those ecosystems become reachable without a dedicated
  Zigbee/Z-Wave connector ever being built (`MASTER_ROADMAP.md`'s own
  Future Expansion reasoning, applied to the wire protocol rather than
  a vendor SDK).
- **JARVIS-native** (`mqtt_envelope.py`) -- for firmware with no reason
  to implement HA's schema, discovered via one fixed announce topic.

**State is push-based and cached, not pulled.** `HomeAssistantConnector
.read_state()` makes a live REST call every time; MQTT has no generic
"give me current state now" primitive. `read_state()` here returns the
last value this connector's own subscription received, or raises if
nothing has arrived yet -- a genuinely different, weaker guarantee,
documented rather than hidden behind the same method name.

**`send_command()`'s success means "handed to the client for
delivery," not "broker acknowledged" and not "device executed."**
MQTT 3.1.1's QoS-1 PUBACK (this connector targets 3.1.1 throughout,
matching its own test broker) carries no payload -- there is no
protocol-level rejection signal to surface even if the client library
exposed per-call ack tracking, which `gmqtt.Client.publish()`
deliberately does not (it queues and lets the library's own resend
logic handle at-least-once delivery across reconnects). `CommandResult
.success=False` is reserved for a synchronous failure calling
`publish()` itself raises -- genuinely rare once connected, and
`ConnectorNotConnectedError` (a raised exception, not a `False`
result) already covers "not connected" per the port's own contract.

**Automatic reconnection is silent to the event bus.** `is_connected`
reflects live truth with zero change to `ConnectivityService` --
`connect()`/`disconnect()` remain the only caller-driven operations it
knows about, exactly Phase 1's own Logic Contract shape. A fresh
`ConnectivityStatusChangedEvent` for a transparent internal reconnect
is a deliberate, documented scope boundary this phase does not cross,
not an oversight.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import ssl
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from jarvis.core.connectivity.connectors.mqtt_envelope import (
    EnvelopeError,
    MqttEnvelope,
    availability_from_envelope,
    build_command_envelope,
    discovery_from_envelope,
    state_from_envelope,
)
from jarvis.core.interfaces.connectivity import (
    CommandResult,
    ConnectivityError,
    ConnectorNotConnectedError,
    DeviceState,
    DiscoveredDevice,
)
from jarvis.core.logging.logger import get_logger

if TYPE_CHECKING:
    import gmqtt

_logger = get_logger("jarvis.core.connectivity.connectors.mqtt")

DEFAULT_PORT = 1883
DEFAULT_TLS_PORT = 8883
DEFAULT_KEEPALIVE_SECONDS = 60
DEFAULT_DISCOVERY_WINDOW_SECONDS = 3.0
DEFAULT_RECONNECT_DELAY_SECONDS = 5.0
DEFAULT_CONNECT_TIMEOUT_SECONDS = 10.0

#: MQTT QoS for every subscription this connector makes (discovery and
#: state). "At least once" -- a silently dropped state update is a
#: real correctness bug; QoS 2's handshake overhead buys nothing most
#: devices honor anyway. See the Phase 3 approval report §3.
SUBSCRIBE_QOS = 1

#: MQTT QoS for every command this connector publishes. A dropped
#: lock/unlock command is safety-relevant; not QoS 2, since command
#: idempotency stays an application-layer concern, matching
#: `IDeviceConnector.send_command`'s existing contract.
COMMAND_QOS = 1

#: Home Assistant discovery config topics end in this suffix, per the
#: `<prefix>/<component>/[<node_id>/]<object_id>/config` convention.
_DISCOVERY_CONFIG_SUFFIX = "/config"

#: HA MQTT Discovery component -> Task Group A's own closed
#: `DEVICE_TYPES` (`domain/smart_home/models.py`). Deliberately
#: duplicated from `home_assistant.py`'s own `_DEVICE_DOMAINS` rather
#: than imported -- the two connectors independently speak the same
#: HA-defined vocabulary for unrelated reasons (an entity_id's domain
#: prefix vs. a discovery topic's component segment), and importing
#: one from the other would couple two connectors that share nothing
#: but coincidentally agreeing with the same external spec. The same
#: reasoning `ConnectorCredentialStore` already gives for not importing
#: MCP's `CredentialStore`.
_HA_COMPONENT_DEVICE_TYPES: dict[str, str] = {
    "light": "light",
    "switch": "switch",
    "lock": "lock",
    "climate": "thermostat",
    "camera": "camera",
    "binary_sensor": "sensor",
    "sensor": "sensor",
    "fan": "appliance",
    "cover": "appliance",
    "media_player": "appliance",
    "vacuum": "appliance",
    "water_heater": "appliance",
    "humidifier": "appliance",
    "siren": "other",
    "select": "other",
    "number": "other",
    "valve": "other",
    "alarm_control_panel": "other",
}

#: HA discovery availability payloads (and this connector's own
#: JARVIS-native availability envelope) that map to "device is up."
#: Anything else -- including HA's own default "offline" -- maps to
#: down. Mirrors `connectivity_service.py`'s own
#: `_ONLINE_STATUS_HINTS`/`_OFFLINE_STATUS_HINTS` reasoning: a closed,
#: explicit set rather than "assume up unless told otherwise."
_HA_AVAILABLE_PAYLOADS = frozenset({"online", "on", "true", "1"})


class _DeviceRegistration:
    """What this connector knows about one discovered device --
    internal bookkeeping `HomeAssistantConnector` never needed, since
    its REST calls are stateless per-request. Not a dataclass: mutated
    in place as new information arrives (an availability topic learned
    after the initial discovery config, for instance)."""

    __slots__ = (
        "availability_topic",
        "command_topic",
        "device_type",
        "external_id",
        "manufacturer",
        "metadata",
        "model",
        "name",
        "state_topic",
    )

    def __init__(
        self,
        *,
        external_id: str,
        name: str,
        device_type: str,
        manufacturer: str = "",
        model: str = "",
        state_topic: str,
        command_topic: str,
        availability_topic: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.external_id = external_id
        self.name = name
        self.device_type = device_type
        self.manufacturer = manufacturer
        self.model = model
        self.state_topic = state_topic
        self.command_topic = command_topic
        self.availability_topic = availability_topic
        self.metadata = dict(metadata or {})

    def to_discovered_device(self) -> DiscoveredDevice:
        return DiscoveredDevice(
            external_id=self.external_id,
            name=self.name,
            device_type=self.device_type,
            manufacturer=self.manufacturer,
            model=self.model,
            metadata=dict(self.metadata),
        )


class MqttConnector:
    """One broker connection. Structurally satisfies `IDeviceConnector`
    -- no inheritance, matching every other adapter in this codebase."""

    connector_type = "mqtt"

    def __init__(
        self,
        host: str,
        port: int = DEFAULT_PORT,
        *,
        client_id: str = "",
        username: str = "",
        password: str = "",
        use_tls: bool = True,
        verify: bool = True,
        discovery_prefix: str = "homeassistant",
        native_prefix: str = "jarvis",
        keepalive_seconds: int = DEFAULT_KEEPALIVE_SECONDS,
        discovery_window_seconds: float = DEFAULT_DISCOVERY_WINDOW_SECONDS,
        reconnect_delay_seconds: float = DEFAULT_RECONNECT_DELAY_SECONDS,
        connect_timeout_seconds: float = DEFAULT_CONNECT_TIMEOUT_SECONDS,
    ) -> None:
        if not host:
            raise ConnectivityError("mqtt connector requires a 'host'.")
        self._host = host
        self._port = port
        self._client_id = client_id
        self._username = username
        self._password = password
        self._use_tls = use_tls
        self._verify = verify
        self._discovery_prefix = discovery_prefix.rstrip("/")
        self._native_prefix = native_prefix.rstrip("/")
        self._keepalive = keepalive_seconds
        self._discovery_window = discovery_window_seconds
        self._reconnect_delay = reconnect_delay_seconds
        self._connect_timeout = connect_timeout_seconds

        self._client: gmqtt.Client | None = None
        self._connected = False

        self._devices: dict[str, _DeviceRegistration] = {}
        self._state_cache: dict[str, DeviceState] = {}
        self._availability: dict[str, bool] = {}
        self._ha_state_topics: dict[str, str] = {}  # state_topic -> external_id
        self._ha_availability_topics: dict[str, str] = {}  # availability_topic -> external_id

    # ------------------------------------------------------------------
    # Topic helpers
    # ------------------------------------------------------------------
    @property
    def _status_topic(self) -> str:
        return f"{self._native_prefix}/connector/mqtt/status"

    @property
    def _native_discovery_topic(self) -> str:
        return f"{self._native_prefix}/discovery/announce"

    @property
    def _native_state_wildcard(self) -> str:
        return f"{self._native_prefix}/devices/+/state"

    @property
    def _native_availability_wildcard(self) -> str:
        return f"{self._native_prefix}/devices/+/availability"

    def _native_command_topic(self, external_id: str) -> str:
        return f"{self._native_prefix}/devices/{external_id}/set"

    @property
    def _discovery_wildcard(self) -> str:
        return f"{self._discovery_prefix}/+/+/+{_DISCOVERY_CONFIG_SUFFIX}"

    @property
    def _discovery_wildcard_no_node(self) -> str:
        return f"{self._discovery_prefix}/+/+{_DISCOVERY_CONFIG_SUFFIX}"

    # ------------------------------------------------------------------
    # IDeviceConnector -- lifecycle
    # ------------------------------------------------------------------
    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        if self.is_connected:
            return

        import gmqtt

        client = self._build_client()
        try:
            await asyncio.wait_for(
                client.connect(
                    self._host,
                    self._port,
                    ssl=self._ssl_param(),
                    keepalive=self._keepalive,
                    version=gmqtt.constants.MQTTv311,
                ),
                timeout=self._connect_timeout,
            )
        except (gmqtt.MQTTConnectError, OSError, TimeoutError) as err:
            raise ConnectivityError(
                f"mqtt: cannot connect to {self._host}:{self._port}: {err}"
            ) from err

        self._client = client
        _logger.info("MQTT connector connecting to {}:{}", self._host, self._port)

    async def disconnect(self) -> None:
        client = self._client
        self._client = None
        self._connected = False
        if client is not None:
            with contextlib.suppress(Exception):
                await client.disconnect()

    def _build_client(self) -> gmqtt.Client:
        import gmqtt

        will = gmqtt.Message(self._status_topic, b"offline", qos=0, retain=True)
        client = gmqtt.Client(self._client_id or None, will_message=will)
        if self._username:
            client.set_auth_credentials(self._username, self._password or None)
        client.on_connect = self._on_connect
        client.on_message = self._on_message
        client.on_disconnect = self._on_disconnect
        client.reconnect_delay = self._reconnect_delay
        return client

    def _ssl_param(self) -> bool | Any:
        """Pure(-ish), independently testable via `_use_tls`/`_verify`
        alone -- so TLS configuration can be verified without a real
        TLS-terminating broker in tests (see the Phase 3 milestone
        report on why the fake broker itself stays plaintext-only)."""
        if not self._use_tls:
            return False
        context = ssl.create_default_context()
        if not self._verify:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        return context

    # ------------------------------------------------------------------
    # gmqtt callbacks -- synchronous by design; see module docstring.
    # ------------------------------------------------------------------
    def _on_connect(self, client: Any, flags: Any, rc: Any, *_args: Any) -> None:
        """Fires on every successful (re)connect, including automatic
        ones gmqtt performs entirely on its own -- always
        re-subscribing unconditionally is correct for both cases, with
        no "is this a reconnect" branch needed."""
        self._connected = True
        client.publish(self._status_topic, b"online", qos=0, retain=True)
        client.subscribe(self._discovery_wildcard, qos=SUBSCRIBE_QOS)
        client.subscribe(self._discovery_wildcard_no_node, qos=SUBSCRIBE_QOS)
        client.subscribe(self._native_discovery_topic, qos=SUBSCRIBE_QOS)
        client.subscribe(self._native_state_wildcard, qos=SUBSCRIBE_QOS)
        client.subscribe(self._native_availability_wildcard, qos=SUBSCRIBE_QOS)
        for topic in {*self._ha_state_topics, *self._ha_availability_topics}:
            client.subscribe(topic, qos=SUBSCRIBE_QOS)
        _logger.info("MQTT connector connected: {}:{}", self._host, self._port)

    def _on_disconnect(self, client: Any, packet: Any, *_args: Any) -> None:
        self._connected = False
        _logger.warning(
            "mqtt: connection to {}:{} lost; the client will retry automatically",
            self._host,
            self._port,
        )

    def _on_message(
        self, client: Any, topic: str, payload: bytes, qos: int, properties: Any
    ) -> None:
        try:
            if topic == self._native_discovery_topic:
                self._handle_native_discovery(payload)
            elif self._is_discovery_config_topic(topic):
                self._handle_ha_discovery(topic, payload)
            elif self._is_native_state_topic(topic):
                self._handle_native_state(payload)
            elif self._is_native_availability_topic(topic):
                self._handle_native_availability(payload)
            elif topic in self._ha_state_topics:
                self._handle_ha_state(topic, payload)
            elif topic in self._ha_availability_topics:
                self._handle_ha_availability(topic, payload)
        except Exception as err:  # one bad message must not kill the loop
            _logger.warning("mqtt: skipping unreadable message on {!r}: {}", topic, err)

    # ------------------------------------------------------------------
    # IDeviceConnector -- discovery
    # ------------------------------------------------------------------
    async def discover(self) -> list[DiscoveredDevice]:
        self._require_connected()
        await asyncio.sleep(self._discovery_window)
        return [reg.to_discovered_device() for reg in self._devices.values()]

    # ------------------------------------------------------------------
    # IDeviceConnector -- state
    # ------------------------------------------------------------------
    async def read_state(self, external_id: str) -> DeviceState:
        self._require_connected()
        cached = self._state_cache.get(external_id)
        if cached is None:
            raise ConnectivityError(
                f"mqtt: no state received yet for {external_id!r}; "
                "state is push-based over MQTT, not pollable."
            )
        if self._availability.get(external_id) is False:
            return DeviceState(
                external_id=external_id,
                status="offline",
                attributes=cached.attributes,
                observed_at=cached.observed_at,
            )
        return cached

    # ------------------------------------------------------------------
    # IDeviceConnector -- commands
    # ------------------------------------------------------------------
    async def send_command(
        self, external_id: str, command: str, payload: dict[str, Any]
    ) -> CommandResult:
        client = self._require_connected()
        registration = self._devices.get(external_id)
        topic = (
            registration.command_topic
            if registration is not None
            else self._native_command_topic(external_id)
        )

        envelope = build_command_envelope(external_id, command, payload)
        try:
            client.publish(
                topic,
                envelope.to_json().encode("utf-8"),
                qos=COMMAND_QOS,
                retain=False,  # never retained -- see module docstring / §4.
            )
        except Exception as err:  # see module docstring's success semantics
            return CommandResult(
                external_id=external_id, command=command, success=False, detail=str(err)
            )
        return CommandResult(external_id=external_id, command=command, success=True)

    def _require_connected(self) -> gmqtt.Client:
        if self._client is None or not self._connected:
            raise ConnectorNotConnectedError("mqtt connector is not connected.")
        return self._client

    # ------------------------------------------------------------------
    # Message routing -- topic classification
    # ------------------------------------------------------------------
    def _is_discovery_config_topic(self, topic: str) -> bool:
        return topic.startswith(f"{self._discovery_prefix}/") and topic.endswith(
            _DISCOVERY_CONFIG_SUFFIX
        )

    def _is_native_state_topic(self, topic: str) -> bool:
        return topic.startswith(f"{self._native_prefix}/devices/") and topic.endswith("/state")

    def _is_native_availability_topic(self, topic: str) -> bool:
        return topic.startswith(f"{self._native_prefix}/devices/") and topic.endswith(
            "/availability"
        )

    # -- Home Assistant MQTT Discovery ---------------------------------
    def _handle_ha_discovery(self, topic: str, raw_payload: bytes) -> None:
        parsed = self._parse_discovery_topic(topic)
        if parsed is None:
            return
        component, _node_id, object_id = parsed
        device_type = _HA_COMPONENT_DEVICE_TYPES.get(component)
        if device_type is None:
            # Not a physical-device component (automation/script/scene/
            # zone/person/...) -- see module docstring's allowlist
            # rationale. Skipped outright, never registered as "other".
            return

        if not raw_payload:
            # Empty payload on a config topic is HA's own convention
            # for "this device was removed" -- nothing to register.
            return

        try:
            config = json.loads(raw_payload.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as err:
            raise EnvelopeError(f"malformed HA discovery config: {err}") from err
        if not isinstance(config, dict):
            raise EnvelopeError("HA discovery config must be a JSON object.")

        external_id = str(config.get("unique_id") or f"{component}_{object_id}")
        state_topic = str(config.get("state_topic") or "")
        command_topic = str(config.get("command_topic") or "")
        availability_topic = str(config.get("availability_topic") or "")
        raw_device = config.get("device")
        device_block: dict[str, Any] = raw_device if isinstance(raw_device, dict) else {}

        registration = _DeviceRegistration(
            external_id=external_id,
            name=str(config.get("name") or external_id),
            device_type=device_type,
            manufacturer=str(device_block.get("manufacturer") or ""),
            model=str(device_block.get("model") or ""),
            state_topic=state_topic,
            command_topic=command_topic,
            availability_topic=availability_topic,
            metadata={"component": component, "discovery_topic": topic},
        )
        self._register_device(registration)

    def _parse_discovery_topic(self, topic: str) -> tuple[str, str, str] | None:
        prefix = f"{self._discovery_prefix}/"
        if not topic.startswith(prefix) or not topic.endswith(_DISCOVERY_CONFIG_SUFFIX):
            return None
        middle = topic[len(prefix) : -len(_DISCOVERY_CONFIG_SUFFIX)]
        parts = [p for p in middle.split("/") if p]
        if len(parts) == 2:
            component, object_id = parts
            node_id = ""
        elif len(parts) == 3:
            component, node_id, object_id = parts
        else:
            return None
        return component, node_id, object_id

    def _handle_ha_state(self, topic: str, raw_payload: bytes) -> None:
        external_id = self._ha_state_topics.get(topic)
        if external_id is None:
            return
        text = raw_payload.decode("utf-8", errors="replace")
        status: str
        attributes: dict[str, Any] = {}
        try:
            parsed = json.loads(text)
        except ValueError:
            parsed = None
        if isinstance(parsed, dict):
            status = str(parsed.get("state", text))
            attributes = {k: v for k, v in parsed.items() if k != "state"}
        else:
            status = text
        self._state_cache[external_id] = DeviceState(
            external_id=external_id,
            status=status,
            attributes=attributes,
            observed_at=datetime.now(UTC),
        )

    def _handle_ha_availability(self, topic: str, raw_payload: bytes) -> None:
        external_id = self._ha_availability_topics.get(topic)
        if external_id is None:
            return
        text = raw_payload.decode("utf-8", errors="replace").strip().lower()
        self._availability[external_id] = text in _HA_AVAILABLE_PAYLOADS

    # -- JARVIS-native ---------------------------------------------------
    def _handle_native_discovery(self, raw_payload: bytes) -> None:
        envelope = MqttEnvelope.from_json(raw_payload)
        info = discovery_from_envelope(envelope)
        registration = _DeviceRegistration(
            external_id=envelope.device_id,
            name=info.name,
            device_type=info.device_type,
            manufacturer=info.manufacturer,
            model=info.model,
            state_topic=f"{self._native_prefix}/devices/{envelope.device_id}/state",
            command_topic=self._native_command_topic(envelope.device_id),
            availability_topic=f"{self._native_prefix}/devices/{envelope.device_id}/availability",
            metadata=info.metadata,
        )
        self._register_device(registration)

    def _handle_native_state(self, raw_payload: bytes) -> None:
        envelope = MqttEnvelope.from_json(raw_payload)
        info = state_from_envelope(envelope)
        self._state_cache[envelope.device_id] = DeviceState(
            external_id=envelope.device_id,
            status=info.status,
            attributes=info.attributes,
            observed_at=envelope.timestamp,
        )

    def _handle_native_availability(self, raw_payload: bytes) -> None:
        envelope = MqttEnvelope.from_json(raw_payload)
        info = availability_from_envelope(envelope)
        self._availability[envelope.device_id] = info.available

    # -- shared ------------------------------------------------------------
    def _register_device(self, registration: _DeviceRegistration) -> None:
        self._devices[registration.external_id] = registration
        if registration.state_topic:
            self._ha_state_topics[registration.state_topic] = registration.external_id
        if registration.availability_topic:
            self._ha_availability_topics[registration.availability_topic] = registration.external_id
        # A device discovered after the initial connect needs its own
        # topics subscribed immediately -- `_on_connect` only covers
        # what was already known at (re)connect time.
        if self._client is not None and self._connected:
            if registration.state_topic:
                self._client.subscribe(registration.state_topic, qos=SUBSCRIBE_QOS)
            if registration.availability_topic:
                self._client.subscribe(registration.availability_topic, qos=SUBSCRIBE_QOS)
