"""MqttConnector tests against a **real** local MQTT 3.1.1 broker --
Milestone 12 Task Group B, Phase 3.

Mirrors `test_home_assistant_connector.py`'s own discipline: a real
peer (`tests/fakes/fake_mqtt_broker.py`'s `FakeMqttBroker`, a genuine
TCP server speaking real MQTT wire packets), not a mocked `gmqtt`
client. `FakeMqttBroker.publish()` stands in for an external device;
`received_publishes()` is what a connector's own outgoing commands are
asserted against; `disconnect_all()` drives the reconnect suite.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from jarvis.core.connectivity.connectors.mqtt import MqttConnector
from jarvis.core.interfaces.connectivity import ConnectivityError, ConnectorNotConnectedError
from tests.fakes.fake_mqtt_broker import FakeMqttBroker

_HA_LIGHT_CONFIG = {
    "name": "Kitchen Light",
    "unique_id": "kitchen_light_1",
    "state_topic": "zigbee2mqtt/kitchen_light",
    "command_topic": "zigbee2mqtt/kitchen_light/set",
    "availability_topic": "zigbee2mqtt/bridge/state",
    "device": {"manufacturer": "IKEA", "model": "TRADFRI bulb"},
}


@pytest.fixture
async def broker():
    b = FakeMqttBroker()
    await b.start()
    yield b
    await b.stop()


@pytest.fixture
def connector(broker: FakeMqttBroker):
    c = MqttConnector(
        "127.0.0.1",
        broker.port,
        use_tls=False,
        discovery_window_seconds=0.3,
        reconnect_delay_seconds=0.05,
    )
    return c


async def _wait_until(predicate, *, timeout: float = 3.0, interval: float = 0.02) -> bool:
    elapsed = 0.0
    while elapsed < timeout:
        if predicate():
            return True
        await asyncio.sleep(interval)
        elapsed += interval
    return predicate()


async def _wait_for_subscription(broker: FakeMqttBroker, topic_filter: str, **kw) -> bool:
    """A SUBSCRIBE this connector issues is sent over a real socket --
    it is not visible to the broker synchronously. Tests that publish a
    *non-retained* message depending on a subscription already being
    active (unlike the retained-replay tests, which are immune to this
    by construction) must wait for the broker to have actually received
    it first, or the publish races the subscribe and is lost forever."""
    return await _wait_until(lambda: topic_filter in dict(broker.received_subscribes()), **kw)


async def _wait_for_publish(broker: FakeMqttBroker, topic: str, **kw) -> bool:
    """Symmetric to `_wait_for_subscription` for the outbound
    direction: `client.publish()` queues bytes on the transport and
    returns immediately -- the broker only sees them after a real
    network round trip."""
    return await _wait_until(lambda: any(p[0] == topic for p in broker.received_publishes()), **kw)


# --- construction ---------------------------------------------------------------


def test_requires_a_host() -> None:
    with pytest.raises(ConnectivityError, match="host"):
        MqttConnector("")


def test_connector_type_and_initial_state(connector: MqttConnector) -> None:
    assert connector.connector_type == "mqtt"
    assert connector.is_connected is False


# --- connect / disconnect --------------------------------------------------------


@pytest.mark.asyncio
async def test_connect_succeeds(connector: MqttConnector) -> None:
    try:
        await connector.connect()
        assert connector.is_connected is True
    finally:
        await connector.disconnect()


@pytest.mark.asyncio
async def test_connect_is_idempotent(connector: MqttConnector) -> None:
    try:
        await connector.connect()
        await connector.connect()
        assert connector.is_connected is True
    finally:
        await connector.disconnect()


@pytest.mark.asyncio
async def test_connect_unreachable_host_fails() -> None:
    connector = MqttConnector("127.0.0.1", 9, use_tls=False, connect_timeout_seconds=1.0)
    with pytest.raises(ConnectivityError, match="cannot connect"):
        await connector.connect()
    assert connector.is_connected is False


@pytest.mark.asyncio
async def test_disconnect_is_idempotent(connector: MqttConnector) -> None:
    await connector.connect()
    await connector.disconnect()
    await connector.disconnect()
    assert connector.is_connected is False


@pytest.mark.asyncio
async def test_disconnect_before_connect_is_safe() -> None:
    connector = MqttConnector("127.0.0.1", 1883, use_tls=False)
    await connector.disconnect()
    assert connector.is_connected is False


# --- authentication ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_connect_with_valid_credentials_succeeds() -> None:
    broker = FakeMqttBroker(valid_credentials={"jarvis": "s3cret"})
    await broker.start()
    connector = MqttConnector(
        "127.0.0.1", broker.port, use_tls=False, username="jarvis", password="s3cret"
    )
    try:
        await connector.connect()
        assert connector.is_connected is True
    finally:
        await connector.disconnect()
        await broker.stop()


@pytest.mark.asyncio
async def test_connect_with_wrong_credentials_fails() -> None:
    broker = FakeMqttBroker(valid_credentials={"jarvis": "s3cret"})
    await broker.start()
    connector = MqttConnector(
        "127.0.0.1", broker.port, use_tls=False, username="jarvis", password="wrong"
    )
    try:
        with pytest.raises(ConnectivityError, match="cannot connect"):
            await connector.connect()
        assert connector.is_connected is False
    finally:
        await connector.disconnect()
        await broker.stop()


# --- TLS configuration (no live TLS handshake -- see MqttConnector._ssl_param) ------


def test_ssl_param_is_false_when_tls_disabled() -> None:
    connector = MqttConnector("127.0.0.1", 1883, use_tls=False)
    assert connector._ssl_param() is False


def test_ssl_param_builds_a_verifying_context_by_default() -> None:
    connector = MqttConnector("127.0.0.1", 8883, use_tls=True, verify=True)
    context = connector._ssl_param()
    assert context is not False
    assert context.check_hostname is True


def test_ssl_param_disables_verification_when_asked() -> None:
    connector = MqttConnector("127.0.0.1", 8883, use_tls=True, verify=False)
    context = connector._ssl_param()
    assert context is not False
    assert context.check_hostname is False


# --- discovery: Home Assistant MQTT Discovery ---------------------------------------


@pytest.mark.asyncio
async def test_discover_requires_a_connection(connector: MqttConnector) -> None:
    with pytest.raises(ConnectorNotConnectedError):
        await connector.discover()


@pytest.mark.asyncio
async def test_discover_parses_ha_discovery_config(
    broker: FakeMqttBroker, connector: MqttConnector
) -> None:
    try:
        await connector.connect()
        await broker.publish(
            "homeassistant/light/livingroom/kitchen_light/config",
            json.dumps(_HA_LIGHT_CONFIG).encode(),
            retain=True,
        )

        devices = await connector.discover()

        assert len(devices) == 1
        device = devices[0]
        assert device.external_id == "kitchen_light_1"
        assert device.name == "Kitchen Light"
        assert device.device_type == "light"
        assert device.manufacturer == "IKEA"
        assert device.model == "TRADFRI bulb"
    finally:
        await connector.disconnect()


@pytest.mark.asyncio
async def test_discover_supports_two_segment_topics_without_node_id(
    broker: FakeMqttBroker, connector: MqttConnector
) -> None:
    """HA's own convention allows `<prefix>/<component>/<object_id>/config`
    (no node_id segment) as well as the three-segment form."""
    try:
        await connector.connect()
        await broker.publish(
            "homeassistant/lock/front_door/config",
            json.dumps(
                {
                    "name": "Front Door",
                    "unique_id": "front_door_lock",
                    "state_topic": "locks/front_door/state",
                    "command_topic": "locks/front_door/set",
                }
            ).encode(),
            retain=True,
        )

        [device] = await connector.discover()

        assert device.external_id == "front_door_lock"
        assert device.device_type == "lock"
    finally:
        await connector.disconnect()


@pytest.mark.asyncio
async def test_discover_skips_unrecognized_domains_without_registering_them(
    broker: FakeMqttBroker, connector: MqttConnector
) -> None:
    try:
        await connector.connect()
        await broker.publish(
            "homeassistant/automation/morning_routine/config",
            json.dumps({"name": "Morning Routine"}).encode(),
            retain=True,
        )

        devices = await connector.discover()

        assert devices == []
    finally:
        await connector.disconnect()


@pytest.mark.asyncio
async def test_discover_fault_isolation_on_a_malformed_config(
    broker: FakeMqttBroker, connector: MqttConnector
) -> None:
    """One malformed discovery payload must not prevent a valid one
    published alongside it from being discovered."""
    try:
        await connector.connect()
        await broker.publish("homeassistant/light/bad/config", b"not valid json{{{", retain=True)
        await broker.publish(
            "homeassistant/light/livingroom/kitchen_light/config",
            json.dumps(_HA_LIGHT_CONFIG).encode(),
            retain=True,
        )

        devices = await connector.discover()

        assert len(devices) == 1
        assert devices[0].external_id == "kitchen_light_1"
    finally:
        await connector.disconnect()


@pytest.mark.asyncio
async def test_discover_empty_payload_removes_nothing_new(
    broker: FakeMqttBroker, connector: MqttConnector
) -> None:
    """HA's own convention: an empty payload on a config topic means
    "this device was removed" -- it must not register a device."""
    try:
        await connector.connect()
        await broker.publish("homeassistant/light/gone/config", b"", retain=True)

        devices = await connector.discover()

        assert devices == []
    finally:
        await connector.disconnect()


@pytest.mark.asyncio
async def test_discover_falls_back_to_a_synthesized_id_without_unique_id(
    broker: FakeMqttBroker, connector: MqttConnector
) -> None:
    try:
        await connector.connect()
        await broker.publish(
            "homeassistant/sensor/node1/temp/config",
            json.dumps({"name": "Temp", "state_topic": "sensors/node1/temp"}).encode(),
            retain=True,
        )

        [device] = await connector.discover()

        assert device.external_id == "sensor_temp"

    finally:
        await connector.disconnect()


# --- discovery: JARVIS-native --------------------------------------------------------


@pytest.mark.asyncio
async def test_discover_parses_native_discovery_envelope(
    broker: FakeMqttBroker, connector: MqttConnector
) -> None:
    try:
        await connector.connect()
        await _wait_for_subscription(broker, "jarvis/discovery/announce")
        await broker.publish(
            "jarvis/discovery/announce",
            json.dumps(
                {
                    "schema_version": 1,
                    "device_id": "esp32-garage-1",
                    "type": "discovery",
                    "timestamp": "2026-08-07T12:00:00+00:00",
                    "payload": {
                        "name": "Garage Door Sensor",
                        "device_type": "sensor",
                        "manufacturer": "JARVIS",
                        "model": "ESP32-S1",
                    },
                }
            ).encode(),
        )

        [device] = await connector.discover()

        assert device.external_id == "esp32-garage-1"
        assert device.name == "Garage Door Sensor"
        assert device.device_type == "sensor"
        assert device.manufacturer == "JARVIS"
    finally:
        await connector.disconnect()


@pytest.mark.asyncio
async def test_native_discovery_fault_isolation_on_a_malformed_envelope(
    broker: FakeMqttBroker, connector: MqttConnector
) -> None:
    try:
        await connector.connect()
        await _wait_for_subscription(broker, "jarvis/discovery/announce")
        await broker.publish("jarvis/discovery/announce", b"not json at all")

        devices = await connector.discover()

        assert devices == []
    finally:
        await connector.disconnect()


# --- state cache ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_read_state_requires_a_connection(connector: MqttConnector) -> None:
    with pytest.raises(ConnectorNotConnectedError):
        await connector.read_state("kitchen_light_1")


@pytest.mark.asyncio
async def test_read_state_before_any_message_raises(
    broker: FakeMqttBroker, connector: MqttConnector
) -> None:
    try:
        await connector.connect()
        with pytest.raises(ConnectivityError, match="no state received yet"):
            await connector.read_state("kitchen_light_1")
    finally:
        await connector.disconnect()


@pytest.mark.asyncio
async def test_read_state_reflects_a_json_state_push(
    broker: FakeMqttBroker, connector: MqttConnector
) -> None:
    try:
        await connector.connect()
        await broker.publish(
            "homeassistant/light/livingroom/kitchen_light/config",
            json.dumps(_HA_LIGHT_CONFIG).encode(),
            retain=True,
        )
        await connector.discover()

        await broker.publish(
            "zigbee2mqtt/kitchen_light", json.dumps({"state": "ON", "brightness": 128}).encode()
        )
        await _wait_until(lambda: "kitchen_light_1" in connector._state_cache)

        state = await connector.read_state("kitchen_light_1")

        assert state.status == "ON"
        assert state.attributes == {"brightness": 128}
    finally:
        await connector.disconnect()


@pytest.mark.asyncio
async def test_read_state_reflects_a_plain_string_state_push(
    broker: FakeMqttBroker, connector: MqttConnector
) -> None:
    """Not every HA-discovery device publishes JSON -- a bare string
    state (e.g. "ON"/"21.5") must be read as the status directly."""
    try:
        await connector.connect()
        await broker.publish(
            "homeassistant/light/livingroom/kitchen_light/config",
            json.dumps(_HA_LIGHT_CONFIG).encode(),
            retain=True,
        )
        await connector.discover()

        await broker.publish("zigbee2mqtt/kitchen_light", b"ON")
        await _wait_until(lambda: "kitchen_light_1" in connector._state_cache)

        state = await connector.read_state("kitchen_light_1")

        assert state.status == "ON"
        assert state.attributes == {}
    finally:
        await connector.disconnect()


@pytest.mark.asyncio
async def test_read_state_reflects_a_native_state_push(
    broker: FakeMqttBroker, connector: MqttConnector
) -> None:
    try:
        await connector.connect()
        await _wait_for_subscription(broker, "jarvis/devices/+/state")
        await broker.publish(
            "jarvis/devices/esp32-1/state",
            json.dumps(
                {
                    "schema_version": 1,
                    "device_id": "esp32-1",
                    "type": "state",
                    "timestamp": "2026-08-07T12:00:00+00:00",
                    "payload": {"status": "on", "attributes": {"humidity": 42}},
                }
            ).encode(),
        )
        await _wait_until(lambda: "esp32-1" in connector._state_cache)

        state = await connector.read_state("esp32-1")

        assert state.status == "on"
        assert state.attributes == {"humidity": 42}
    finally:
        await connector.disconnect()


# --- availability --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_read_state_reports_offline_when_ha_availability_says_unavailable(
    broker: FakeMqttBroker, connector: MqttConnector
) -> None:
    try:
        await connector.connect()
        await broker.publish(
            "homeassistant/light/livingroom/kitchen_light/config",
            json.dumps(_HA_LIGHT_CONFIG).encode(),
            retain=True,
        )
        await connector.discover()
        await broker.publish("zigbee2mqtt/kitchen_light", b"ON")
        await _wait_until(lambda: "kitchen_light_1" in connector._state_cache)

        await broker.publish("zigbee2mqtt/bridge/state", b"offline")
        await _wait_until(lambda: connector._availability.get("kitchen_light_1") is False)

        state = await connector.read_state("kitchen_light_1")

        assert state.status == "offline"
    finally:
        await connector.disconnect()


@pytest.mark.asyncio
async def test_availability_recovers_to_the_real_state_when_back_online(
    broker: FakeMqttBroker, connector: MqttConnector
) -> None:
    try:
        await connector.connect()
        await broker.publish(
            "homeassistant/light/livingroom/kitchen_light/config",
            json.dumps(_HA_LIGHT_CONFIG).encode(),
            retain=True,
        )
        await connector.discover()
        await broker.publish("zigbee2mqtt/kitchen_light", b"ON")
        await broker.publish("zigbee2mqtt/bridge/state", b"offline")
        await _wait_until(lambda: connector._availability.get("kitchen_light_1") is False)

        await broker.publish("zigbee2mqtt/bridge/state", b"online")
        await _wait_until(lambda: connector._availability.get("kitchen_light_1") is True)

        state = await connector.read_state("kitchen_light_1")

        assert state.status == "ON"
    finally:
        await connector.disconnect()


@pytest.mark.asyncio
async def test_native_availability_envelope_is_honored(
    broker: FakeMqttBroker, connector: MqttConnector
) -> None:
    try:
        await connector.connect()
        await _wait_for_subscription(broker, "jarvis/devices/+/state")
        await broker.publish(
            "jarvis/devices/esp32-1/state",
            json.dumps(
                {
                    "schema_version": 1,
                    "device_id": "esp32-1",
                    "type": "state",
                    "timestamp": "2026-08-07T12:00:00+00:00",
                    "payload": {"status": "on"},
                }
            ).encode(),
        )
        await _wait_until(lambda: "esp32-1" in connector._state_cache)

        await broker.publish(
            "jarvis/devices/esp32-1/availability",
            json.dumps(
                {
                    "schema_version": 1,
                    "device_id": "esp32-1",
                    "type": "availability",
                    "timestamp": "2026-08-07T12:00:01+00:00",
                    "payload": {"available": False},
                }
            ).encode(),
        )
        await _wait_until(lambda: connector._availability.get("esp32-1") is False)

        state = await connector.read_state("esp32-1")

        assert state.status == "offline"
    finally:
        await connector.disconnect()


# --- retained-message handling --------------------------------------------------------


@pytest.mark.asyncio
async def test_retained_discovery_config_is_replayed_on_subscribe(
    broker: FakeMqttBroker,
) -> None:
    """A retained discovery config published *before* the connector
    ever subscribes must still be discovered -- that is the entire
    point of HA's retained-discovery convention."""
    await broker.publish(
        "homeassistant/light/livingroom/kitchen_light/config",
        json.dumps(_HA_LIGHT_CONFIG).encode(),
        retain=True,
    )

    connector = MqttConnector("127.0.0.1", broker.port, use_tls=False, discovery_window_seconds=0.3)
    try:
        await connector.connect()
        devices = await connector.discover()
        assert len(devices) == 1
        assert devices[0].external_id == "kitchen_light_1"
    finally:
        await connector.disconnect()


@pytest.mark.asyncio
async def test_send_command_never_retains(broker: FakeMqttBroker, connector: MqttConnector) -> None:
    """A retained command would replay on every future subscribe/
    reconnect and re-execute against the device -- a real safety
    hazard for anything like a lock. Must never be retain=True."""
    try:
        await connector.connect()
        await connector.send_command("some_device", "toggle", {})
        await _wait_for_publish(broker, "jarvis/devices/some_device/set")

        publishes = broker.received_publishes()
        [command_publish] = [p for p in publishes if p[0] == "jarvis/devices/some_device/set"]
        _topic, _payload, _qos, retain = command_publish
        assert retain is False
    finally:
        await connector.disconnect()


@pytest.mark.asyncio
async def test_an_empty_retained_payload_clears_the_retained_store(
    broker: FakeMqttBroker,
) -> None:
    await broker.publish(
        "homeassistant/light/livingroom/kitchen_light/config",
        json.dumps(_HA_LIGHT_CONFIG).encode(),
        retain=True,
    )
    await broker.publish("homeassistant/light/livingroom/kitchen_light/config", b"", retain=True)

    connector = MqttConnector("127.0.0.1", broker.port, use_tls=False, discovery_window_seconds=0.3)
    try:
        await connector.connect()
        devices = await connector.discover()
        assert devices == []
    finally:
        await connector.disconnect()


# --- QoS -------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_discovery_subscriptions_request_qos_1(
    broker: FakeMqttBroker, connector: MqttConnector
) -> None:
    """Subscriptions must not silently accept QoS 0 -- a dropped
    discovery/state update is a real correctness bug, per the Phase 3
    approval report §3."""
    try:
        await connector.connect()
        await asyncio.sleep(0.1)

        subscribes = dict(broker.received_subscribes())
        assert subscribes["jarvis/discovery/announce"] == 1
        assert subscribes["jarvis/devices/+/state"] == 1
        assert subscribes["jarvis/devices/+/availability"] == 1
    finally:
        await connector.disconnect()


@pytest.mark.asyncio
async def test_ha_state_subscription_requests_qos_1(
    broker: FakeMqttBroker, connector: MqttConnector
) -> None:
    try:
        await connector.connect()
        await broker.publish(
            "homeassistant/light/livingroom/kitchen_light/config",
            json.dumps(_HA_LIGHT_CONFIG).encode(),
            retain=True,
        )
        await connector.discover()

        subscribes = dict(broker.received_subscribes())
        assert subscribes["zigbee2mqtt/kitchen_light"] == 1
    finally:
        await connector.disconnect()


@pytest.mark.asyncio
async def test_send_command_publishes_at_qos_1(
    broker: FakeMqttBroker, connector: MqttConnector
) -> None:
    try:
        await connector.connect()
        await connector.send_command("some_device", "toggle", {})
        await _wait_for_publish(broker, "jarvis/devices/some_device/set")

        [publish] = [
            p for p in broker.received_publishes() if p[0] == "jarvis/devices/some_device/set"
        ]
        _topic, _payload, qos, _retain = publish
        assert qos == 1
    finally:
        await connector.disconnect()


# --- commands --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_command_requires_a_connection(connector: MqttConnector) -> None:
    with pytest.raises(ConnectorNotConnectedError):
        await connector.send_command("d1", "toggle", {})


@pytest.mark.asyncio
async def test_send_command_routes_to_a_discovered_devices_command_topic(
    broker: FakeMqttBroker, connector: MqttConnector
) -> None:
    try:
        await connector.connect()
        await broker.publish(
            "homeassistant/light/livingroom/kitchen_light/config",
            json.dumps(_HA_LIGHT_CONFIG).encode(),
            retain=True,
        )
        await connector.discover()

        result = await connector.send_command("kitchen_light_1", "turn_off", {})
        await _wait_for_publish(broker, "zigbee2mqtt/kitchen_light/set")

        assert result.success is True
        assert result.external_id == "kitchen_light_1"
        assert result.command == "turn_off"
        [publish] = [
            p for p in broker.received_publishes() if p[0] == "zigbee2mqtt/kitchen_light/set"
        ]
        topic, payload, _qos, _retain = publish
        assert topic == "zigbee2mqtt/kitchen_light/set"
        body = json.loads(payload)
        assert body["device_id"] == "kitchen_light_1"
        assert body["type"] == "command"
        assert body["payload"] == {"command": "turn_off", "args": {}}
    finally:
        await connector.disconnect()


@pytest.mark.asyncio
async def test_send_command_to_an_unknown_device_uses_the_native_command_topic(
    broker: FakeMqttBroker, connector: MqttConnector
) -> None:
    """A device this connector has never discovered still gets a
    best-effort JARVIS-native command topic -- an operator may know a
    device id ahead of discovery."""
    try:
        await connector.connect()

        result = await connector.send_command("esp32-unknown", "reboot", {})
        await _wait_for_publish(broker, "jarvis/devices/esp32-unknown/set")

        assert result.success is True
        [publish] = [
            p for p in broker.received_publishes() if p[0] == "jarvis/devices/esp32-unknown/set"
        ]
        assert publish[0] == "jarvis/devices/esp32-unknown/set"
    finally:
        await connector.disconnect()


@pytest.mark.asyncio
async def test_send_command_forwards_the_payload_as_args(
    broker: FakeMqttBroker, connector: MqttConnector
) -> None:
    try:
        await connector.connect()
        await connector.send_command("d1", "set_brightness", {"brightness": 77})
        await _wait_for_publish(broker, "jarvis/devices/d1/set")

        [publish] = [p for p in broker.received_publishes() if p[0] == "jarvis/devices/d1/set"]
        body = json.loads(publish[1])
        assert body["payload"] == {"command": "set_brightness", "args": {"brightness": 77}}
    finally:
        await connector.disconnect()


# --- reconnect ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reconnects_automatically_after_a_dropped_connection(
    broker: FakeMqttBroker, connector: MqttConnector
) -> None:
    try:
        await connector.connect()
        assert connector.is_connected is True

        await broker.disconnect_all()
        await _wait_until(lambda: connector.is_connected is False, timeout=1.0)
        assert connector.is_connected is False

        reconnected = await _wait_until(lambda: connector.is_connected is True, timeout=5.0)
        assert reconnected is True
    finally:
        await connector.disconnect()


@pytest.mark.asyncio
async def test_resubscribes_after_reconnecting_and_still_receives_state(
    broker: FakeMqttBroker, connector: MqttConnector
) -> None:
    """The whole point of resubscription: a state push sent *after* an
    automatic reconnect must still reach the connector's cache."""
    try:
        await connector.connect()
        await broker.publish(
            "homeassistant/light/livingroom/kitchen_light/config",
            json.dumps(_HA_LIGHT_CONFIG).encode(),
            retain=True,
        )
        await connector.discover()
        subscribes_before = broker.received_subscribes().count(("zigbee2mqtt/kitchen_light", 1))

        await broker.disconnect_all()
        await _wait_until(lambda: connector.is_connected is True, timeout=5.0)
        # `is_connected` flips true as soon as `_on_connect` starts, but
        # the resubscribe it issues still needs a real round trip to
        # reach the broker -- wait for a *second* SUBSCRIBE of this
        # topic (the first was the original connect's), not just any.
        await _wait_until(
            lambda: broker.received_subscribes().count(("zigbee2mqtt/kitchen_light", 1))
            > subscribes_before,
            timeout=3.0,
        )

        await broker.publish("zigbee2mqtt/kitchen_light", b"ON")
        received = await _wait_until(
            lambda: "kitchen_light_1" in connector._state_cache,
            timeout=3.0,
        )

        assert received is True
        state = await connector.read_state("kitchen_light_1")
        assert state.status == "ON"
    finally:
        await connector.disconnect()


@pytest.mark.asyncio
async def test_a_newly_discovered_devices_topics_are_subscribed_immediately(
    broker: FakeMqttBroker, connector: MqttConnector
) -> None:
    """A device discovered mid-session (not at connect time) must not
    have to wait for the next reconnect to have its topics subscribed
    -- `_register_device` subscribes it right away."""
    try:
        await connector.connect()
        await broker.publish(
            "homeassistant/light/livingroom/kitchen_light/config",
            json.dumps(_HA_LIGHT_CONFIG).encode(),
            retain=True,
        )
        await connector.discover()

        await broker.publish("zigbee2mqtt/kitchen_light", b"ON")
        received = await _wait_until(lambda: "kitchen_light_1" in connector._state_cache)

        assert received is True
    finally:
        await connector.disconnect()
