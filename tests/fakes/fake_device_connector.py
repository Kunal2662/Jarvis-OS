"""Deterministic in-memory fake for :class:`IDeviceConnector`.

Milestone 12 Task Group B, Phase 1 -- there is no real connector yet
(Home Assistant and MQTT are later phases of this same task group), so
this fake is what ``ConnectivityService`` tests drive instead. Scripted
rather than networked: a test seeds ``devices``/``states`` up front and
asserts on ``connect_calls``/``sent_commands`` afterwards.
"""

from __future__ import annotations

from typing import Any

from jarvis.core.interfaces.connectivity import (
    CommandResult,
    ConnectorNotConnectedError,
    DeviceState,
    DiscoveredDevice,
)


class FakeDeviceConnector:
    connector_type: str = "home_assistant"

    def __init__(
        self,
        *,
        devices: list[DiscoveredDevice] | None = None,
        states: dict[str, DeviceState] | None = None,
    ) -> None:
        self._connected = False
        self.devices = list(devices or [])
        self.states = dict(states or {})
        self.connect_calls = 0
        self.disconnect_calls = 0
        self.sent_commands: list[tuple[str, str, dict[str, Any]]] = []
        #: Set by a test to make the next `send_command` report failure
        #: without raising -- a real, expected outcome per the port's
        #: own docstring, not every failure is an exception.
        self.next_command_succeeds = True

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        self.connect_calls += 1
        self._connected = True

    async def disconnect(self) -> None:
        self.disconnect_calls += 1
        self._connected = False

    async def discover(self) -> list[DiscoveredDevice]:
        if not self._connected:
            raise ConnectorNotConnectedError(f"{self.connector_type} is not connected.")
        return list(self.devices)

    async def read_state(self, external_id: str) -> DeviceState:
        if not self._connected:
            raise ConnectorNotConnectedError(f"{self.connector_type} is not connected.")
        state = self.states.get(external_id)
        if state is None:
            raise KeyError(f"No fake state seeded for {external_id!r}.")
        return state

    async def send_command(
        self, external_id: str, command: str, payload: dict[str, Any]
    ) -> CommandResult:
        if not self._connected:
            raise ConnectorNotConnectedError(f"{self.connector_type} is not connected.")
        self.sent_commands.append((external_id, command, payload))
        return CommandResult(
            external_id=external_id,
            command=command,
            success=self.next_command_succeeds,
            detail="" if self.next_command_succeeds else "fake rejection",
        )
