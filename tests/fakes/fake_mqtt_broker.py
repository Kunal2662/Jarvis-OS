"""A real, minimal, in-process MQTT 3.1.1 broker -- Milestone 12 Task
Group B, Phase 3.

Every earlier connector's tests used a **real** peer, never a mocked
client: `test_mcp_transports_live.py` spins up a real `websockets`
server and a real `http.server.HTTPServer`; `test_home_assistant_
connector.py` does the same for HA's REST API. MQTT has no stdlib
broker to reuse, so this is that same discipline applied where the
standard library offers nothing: a real TCP server speaking real MQTT
wire packets to a real `gmqtt` client, not a stand-in for one.

**Scope, stated plainly.** This implements exactly the MQTT 3.1.1
surface `MqttConnector` and its tests exercise: CONNECT/CONNACK
(username/password auth), SUBSCRIBE/SUBACK and UNSUBSCRIBE/UNSUBACK
(wildcard-aware), PUBLISH both directions (QoS 0 fire-and-forget, QoS 1
with PUBACK), retained-message storage and replay-on-subscribe, Last
Will and Testament on an abnormal disconnect, and PINGREQ/PINGRESP.
No QoS 2, no MQTT 5 properties, no TLS termination (see
`MqttConnector._ssl_param`'s own docstring for why TLS is tested at
the configuration level instead of against a real cert here). This is
a test double for one connector's own protocol surface, not a
general-purpose broker.

**Test-injection surface.** `publish()` lets a test act as "an
external device" without a second real MQTT client -- it runs the
exact same fan-out/retain logic a client-originated PUBLISH would.
`disconnect_all()` lets a test simulate a dropped link for reconnect
coverage. `received_publishes()` is what a test asserts a connector's
own outgoing commands against.
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, field

# --- MQTT 3.1.1 wire encoding -------------------------------------------------

_CONNECT = 1
_CONNACK = 2
_PUBLISH = 3
_PUBACK = 4
_SUBSCRIBE = 8
_SUBACK = 9
_UNSUBSCRIBE = 10
_UNSUBACK = 11
_PINGREQ = 12
_PINGRESP = 13
_DISCONNECT = 14

_CONNACK_ACCEPTED = 0
_CONNACK_BAD_CREDENTIALS = 4
_CONNACK_NOT_AUTHORIZED = 5


def _encode_remaining_length(n: int) -> bytes:
    out = bytearray()
    while True:
        byte = n % 128
        n //= 128
        if n > 0:
            byte |= 0x80
        out.append(byte)
        if n <= 0:
            break
    return bytes(out)


async def _read_remaining_length(reader: asyncio.StreamReader) -> int:
    multiplier = 1
    value = 0
    while True:
        chunk = await reader.readexactly(1)
        byte = chunk[0]
        value += (byte & 0x7F) * multiplier
        if (byte & 0x80) == 0:
            break
        multiplier *= 128
    return value


def _encode_str(s: str) -> bytes:
    data = s.encode("utf-8")
    return len(data).to_bytes(2, "big") + data


def _decode_str(buf: bytes, offset: int) -> tuple[str, int]:
    length = int.from_bytes(buf[offset : offset + 2], "big")
    offset += 2
    return buf[offset : offset + length].decode("utf-8"), offset + length


def _encode_publish(topic: str, payload: bytes, *, qos: int, retain: bool, packet_id: int) -> bytes:
    flags = (qos << 1) | (1 if retain else 0)
    body = _encode_str(topic)
    if qos > 0:
        body += packet_id.to_bytes(2, "big")
    body += payload
    return bytes([0x30 | flags]) + _encode_remaining_length(len(body)) + body


def _encode_connack(return_code: int) -> bytes:
    return bytes([_CONNACK << 4, 0x02, 0x00, return_code])


def _encode_puback(packet_id: int) -> bytes:
    return bytes([_PUBACK << 4, 0x02]) + packet_id.to_bytes(2, "big")


def _encode_suback(packet_id: int, granted: list[int]) -> bytes:
    body = packet_id.to_bytes(2, "big") + bytes(granted)
    return bytes([_SUBACK << 4]) + _encode_remaining_length(len(body)) + body


def _encode_unsuback(packet_id: int) -> bytes:
    return bytes([_UNSUBACK << 4, 0x02]) + packet_id.to_bytes(2, "big")


_PINGRESP_PACKET = bytes([_PINGRESP << 4, 0x00])


def _topic_matches(topic_filter: str, topic: str) -> bool:
    filter_parts = topic_filter.split("/")
    topic_parts = topic.split("/")
    for i, fp in enumerate(filter_parts):
        if fp == "#":
            return True
        if i >= len(topic_parts):
            return False
        if fp != "+" and fp != topic_parts[i]:
            return False
    return len(filter_parts) == len(topic_parts)


@dataclass
class _Will:
    topic: str
    payload: bytes
    qos: int
    retain: bool


@dataclass
class _Session:
    writer: asyncio.StreamWriter
    subscriptions: list[str] = field(default_factory=list)
    will: _Will | None = None
    closed: bool = False


class FakeMqttBroker:
    """One broker, bound to ``127.0.0.1`` on an OS-assigned port."""

    def __init__(self, *, valid_credentials: dict[str, str] | None = None) -> None:
        self._valid_credentials = valid_credentials
        self._server: asyncio.AbstractServer | None = None
        self._sessions: list[_Session] = []
        self._retained: dict[str, tuple[bytes, int]] = {}
        self._received_publishes: list[tuple[str, bytes, int, bool]] = []
        self._received_subscribes: list[tuple[str, int]] = []
        self._next_broker_packet_id = 1

    @property
    def port(self) -> int:
        assert self._server is not None
        return self._server.sockets[0].getsockname()[1]  # type: ignore[union-attr]

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle_client, "127.0.0.1", 0)

    async def stop(self) -> None:
        for session in list(self._sessions):
            await self._close_session(session, fire_will=False)
        if self._server is not None:
            self._server.close()
            with contextlib.suppress(Exception):
                await self._server.wait_closed()
            self._server = None

    def received_publishes(self) -> list[tuple[str, bytes, int, bool]]:
        """Every PUBLISH this broker received from a connected client:
        ``(topic, payload, qos, retain)``, in arrival order."""
        return list(self._received_publishes)

    def received_subscribes(self) -> list[tuple[str, int]]:
        """Every SUBSCRIBE entry this broker received from a connected
        client: ``(topic_filter, requested_qos)``, in arrival order --
        what a test asserts a connector's own subscription QoS
        against, distinct from `_Session.subscriptions` (which tracks
        only the filter string, for fan-out matching)."""
        return list(self._received_subscribes)

    async def publish(
        self, topic: str, payload: bytes, *, qos: int = 0, retain: bool = False
    ) -> None:
        """Broker-side injection -- stands in for an external device
        publishing, without a second real MQTT client in the test."""
        if retain:
            if payload:
                self._retained[topic] = (payload, qos)
            else:
                self._retained.pop(topic, None)
        await self._fan_out(topic, payload, qos=qos, retain=retain)

    async def disconnect_all(self) -> None:
        """Forcibly drops every live client connection -- reconnect
        coverage without waiting for a real network failure."""
        for session in list(self._sessions):
            await self._close_session(session, fire_will=True)

    # ------------------------------------------------------------------
    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        session = _Session(writer=writer)
        try:
            if not await self._handle_connect(reader, writer, session):
                return
            self._sessions.append(session)
            while True:
                header = await reader.readexactly(1)
                packet_type = header[0] >> 4
                flags = header[0] & 0x0F
                length = await _read_remaining_length(reader)
                body = await reader.readexactly(length) if length else b""

                if packet_type == _PUBLISH:
                    await self._handle_publish(session, flags, body)
                elif packet_type == _SUBSCRIBE:
                    await self._handle_subscribe(session, body)
                elif packet_type == _UNSUBSCRIBE:
                    await self._handle_unsubscribe(session, body)
                elif packet_type == _PINGREQ:
                    writer.write(_PINGRESP_PACKET)
                    await writer.drain()
                elif packet_type == _DISCONNECT:
                    await self._close_session(session, fire_will=False)
                    return
                # PUBACK from a client (acking one of our own QoS-1
                # downstream publishes) and anything else unrecognized
                # is intentionally ignored -- see module docstring.
        except (asyncio.IncompleteReadError, ConnectionResetError, OSError):
            await self._close_session(session, fire_will=True)
        except Exception:
            await self._close_session(session, fire_will=True)
            raise

    async def _handle_connect(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, session: _Session
    ) -> bool:
        header = await reader.readexactly(1)
        if header[0] >> 4 != _CONNECT:
            writer.close()
            return False
        length = await _read_remaining_length(reader)
        body = await reader.readexactly(length)

        _protocol_name, offset = _decode_str(body, 0)
        offset += 1  # protocol level
        connect_flags = body[offset]
        offset += 1
        offset += 2  # keepalive
        _client_id, offset = _decode_str(body, offset)

        will_flag = bool(connect_flags & 0x04)
        will_qos = (connect_flags >> 3) & 0x03
        will_retain = bool(connect_flags & 0x20)
        username_flag = bool(connect_flags & 0x80)
        password_flag = bool(connect_flags & 0x40)

        if will_flag:
            will_topic, offset = _decode_str(body, offset)
            will_len = int.from_bytes(body[offset : offset + 2], "big")
            offset += 2
            will_payload = body[offset : offset + will_len]
            offset += will_len
            session.will = _Will(
                topic=will_topic, payload=will_payload, qos=will_qos, retain=will_retain
            )

        username: str | None = None
        password: str | None = None
        if username_flag:
            username, offset = _decode_str(body, offset)
        if password_flag:
            pw_len = int.from_bytes(body[offset : offset + 2], "big")
            offset += 2
            password = body[offset : offset + pw_len].decode("utf-8")
            offset += pw_len

        if self._valid_credentials is not None and (
            username not in self._valid_credentials
            or self._valid_credentials[username] != (password or "")
        ):
            writer.write(_encode_connack(_CONNACK_BAD_CREDENTIALS))
            await writer.drain()
            writer.close()
            return False

        writer.write(_encode_connack(_CONNACK_ACCEPTED))
        await writer.drain()
        return True

    async def _handle_publish(self, session: _Session, flags: int, body: bytes) -> None:
        qos = (flags >> 1) & 0x03
        retain = bool(flags & 0x01)
        topic, offset = _decode_str(body, 0)
        packet_id = 0
        if qos > 0:
            packet_id = int.from_bytes(body[offset : offset + 2], "big")
            offset += 2
        payload = body[offset:]

        self._received_publishes.append((topic, payload, qos, retain))

        if qos > 0:
            session.writer.write(_encode_puback(packet_id))
            await session.writer.drain()

        if retain:
            if payload:
                self._retained[topic] = (payload, qos)
            else:
                self._retained.pop(topic, None)

        await self._fan_out(topic, payload, qos=qos, retain=retain, exclude=session)

    async def _handle_subscribe(self, session: _Session, body: bytes) -> None:
        packet_id = int.from_bytes(body[0:2], "big")
        offset = 2
        granted: list[int] = []
        new_filters: list[str] = []
        while offset < len(body):
            topic_filter, offset = _decode_str(body, offset)
            requested_qos = body[offset]
            offset += 1
            session.subscriptions.append(topic_filter)
            new_filters.append(topic_filter)
            self._received_subscribes.append((topic_filter, requested_qos))
            granted.append(min(requested_qos, 1))

        session.writer.write(_encode_suback(packet_id, granted))
        await session.writer.drain()

        # Retained-message replay -- every stored retained message
        # matching a newly-added filter, delivered immediately, with
        # its retain flag set so the receiver can tell "last known
        # value on subscribe" apart from a live push.
        for topic, (payload, stored_qos) in list(self._retained.items()):
            for topic_filter in new_filters:
                if _topic_matches(topic_filter, topic):
                    await self._send_publish(session, topic, payload, qos=stored_qos, retain=True)
                    break

    async def _handle_unsubscribe(self, session: _Session, body: bytes) -> None:
        packet_id = int.from_bytes(body[0:2], "big")
        offset = 2
        while offset < len(body):
            topic_filter, offset = _decode_str(body, offset)
            with contextlib.suppress(ValueError):
                session.subscriptions.remove(topic_filter)
        session.writer.write(_encode_unsuback(packet_id))
        await session.writer.drain()

    async def _fan_out(
        self,
        topic: str,
        payload: bytes,
        *,
        qos: int,
        retain: bool,
        exclude: _Session | None = None,
    ) -> None:
        for session in list(self._sessions):
            if session is exclude or session.closed:
                continue
            if any(_topic_matches(f, topic) for f in session.subscriptions):
                await self._send_publish(session, topic, payload, qos=qos, retain=retain)

    async def _send_publish(
        self, session: _Session, topic: str, payload: bytes, *, qos: int, retain: bool
    ) -> None:
        packet_id = self._next_broker_packet_id
        self._next_broker_packet_id += 1
        try:
            session.writer.write(
                _encode_publish(topic, payload, qos=qos, retain=retain, packet_id=packet_id)
            )
            await session.writer.drain()
        except (ConnectionResetError, OSError):
            await self._close_session(session, fire_will=True)

    async def _close_session(self, session: _Session, *, fire_will: bool) -> None:
        if session.closed:
            return
        session.closed = True
        if session in self._sessions:
            self._sessions.remove(session)
        with contextlib.suppress(Exception):
            session.writer.close()
        if fire_will and session.will is not None:
            will = session.will
            if will.retain:
                if will.payload:
                    self._retained[will.topic] = (will.payload, will.qos)
                else:
                    self._retained.pop(will.topic, None)
            await self._fan_out(will.topic, will.payload, qos=will.qos, retain=will.retain)
