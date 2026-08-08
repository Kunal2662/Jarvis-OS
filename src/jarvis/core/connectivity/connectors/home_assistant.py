"""Home Assistant connector -- Milestone 12 Task Group B, Phase 2.

The first real implementation of `IDeviceConnector`
(`core/interfaces/connectivity.py`). Speaks Home Assistant's REST API
over `httpx` -- already this project's HTTP client everywhere else,
the same dependency `core/mcp/transports/http.py` uses -- rather than
the WebSocket API: every operation this connector's port requires
(reachability, entity listing, single-entity state, service calls) has
a stateless REST endpoint, and Home Assistant's WebSocket API exists
for push-style subscriptions this port does not ask for. Reaching for
it here would be protocol surface with nothing pulling it, not
foundation for a future need.

**"Connected" means the same thing `HttpTransport` already decided it
means for a stateless protocol.** `connect()` opens a pooled
`httpx.AsyncClient` and performs a real reachability probe (`GET
/api/`, Home Assistant's own health/auth-check endpoint) rather than
optimistically reporting success -- an unreachable host or a rejected
token must fail here, not silently at first use. `disconnect()` closes
the pool.

**Entity-to-device mapping is a deliberate allowlist, not a
blocklist.** Home Assistant exposes automations, scripts, scenes,
zones, persons and dozens of other non-physical entities through the
same `/api/states` endpoint as real devices. Registering
`automation.morning_routine` as a `Device` would be actively wrong, not
merely imprecise -- so `_DEVICE_DOMAINS` is a closed set of entity
domains that represent real hardware; anything outside it is skipped
by `discover()`, never registered under a fallback category. This is
distinct from the Logic Contract's "unrecognized device type maps to
`other`" rule, which governs a domain this connector *does* consider a
device but cannot categorize precisely (e.g. `select`, `number`) --
those still map to `"other"`, matching Task Group A's own closed
`DEVICE_TYPES` vocabulary.

**Manufacturer and model are left blank.** Home Assistant's REST
`/api/states` response carries no such fields -- that data lives in the
Device Registry, reachable only over the WebSocket API's
`config/device_registry/list` command, which this phase does not
build. Reporting an empty string here is the honest answer; guessing
would not be.
"""

from __future__ import annotations

import contextlib
from datetime import datetime
from typing import TYPE_CHECKING, Any

from jarvis.core.interfaces.connectivity import (
    CommandResult,
    ConnectivityError,
    ConnectorNotConnectedError,
    DeviceState,
    DiscoveredDevice,
)
from jarvis.core.logging.logger import get_logger

if TYPE_CHECKING:
    import httpx

_logger = get_logger("jarvis.core.connectivity.connectors.home_assistant")

DEFAULT_REQUEST_TIMEOUT_SECONDS = 10.0

#: Entity domains this connector treats as physical devices, mapped onto
#: Task Group A's own closed `DEVICE_TYPES` vocabulary
#: (`domain/smart_home/models.py`). A domain reached through this map
#: but with no more precise category (`select`, `number`, `valve`,
#: `siren`, `alarm_control_panel`) lands on `"other"`, per the Logic
#: Contract's own validation rule -- distinct from a domain absent from
#: this map entirely, which `discover()` skips outright (see module
#: docstring).
_DEVICE_DOMAINS: dict[str, str] = {
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


class HomeAssistantConnector:
    """One Home Assistant instance, addressed by base URL and a
    long-lived access token. Structurally satisfies `IDeviceConnector`
    -- no inheritance, matching every other adapter in this codebase."""

    connector_type = "home_assistant"

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
        verify: bool = True,
    ) -> None:
        if not base_url:
            raise ConnectivityError("home_assistant connector requires a 'base_url'.")
        if not token:
            raise ConnectivityError("home_assistant connector requires a 'token'.")
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._timeout = request_timeout_seconds
        self._verify = verify
        self._client: httpx.AsyncClient | None = None

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def is_connected(self) -> bool:
        return self._client is not None

    async def connect(self) -> None:
        if self.is_connected:
            return

        import httpx

        client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=self._timeout,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
            },
            verify=self._verify,
        )
        try:
            response = await client.get("/api/")
            response.raise_for_status()
        except httpx.HTTPError as err:
            with contextlib.suppress(Exception):
                await client.aclose()
            raise ConnectivityError(
                f"home_assistant: cannot reach {self._base_url}: {err}"
            ) from err

        self._client = client
        _logger.info("Home Assistant connector connected: {}", self._base_url)

    async def disconnect(self) -> None:
        client = self._client
        self._client = None
        if client is not None:
            with contextlib.suppress(Exception):
                await client.aclose()

    async def discover(self) -> list[DiscoveredDevice]:
        client = self._require_client()

        import httpx

        try:
            response = await client.get("/api/states")
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as err:
            raise ConnectivityError(f"home_assistant: discovery failed: {err}") from err
        except ValueError as err:
            raise ConnectivityError(
                f"home_assistant: discovery returned invalid JSON: {err}"
            ) from err

        if not isinstance(payload, list):
            raise ConnectivityError("home_assistant: /api/states did not return a list.")

        devices: list[DiscoveredDevice] = []
        for entity in payload:
            try:
                device = _entity_to_discovered_device(entity)
            except (KeyError, TypeError, ValueError) as err:
                # One unreadable record must not abort the whole
                # discovery batch -- the same fault isolation the Logic
                # Contract requires and `ConnectorCredentialStore`
                # already applies to its own records.
                _logger.warning("home_assistant: skipping unreadable entity record: {}", err)
                continue
            if device is not None:
                devices.append(device)
        return devices

    async def read_state(self, external_id: str) -> DeviceState:
        client = self._require_client()

        import httpx

        try:
            response = await client.get(f"/api/states/{external_id}")
        except httpx.HTTPError as err:
            raise ConnectivityError(
                f"home_assistant: read_state({external_id!r}) failed: {err}"
            ) from err
        if response.status_code == 404:
            raise ConnectivityError(f"home_assistant: unknown entity {external_id!r}.")
        try:
            response.raise_for_status()
            raw = response.json()
        except httpx.HTTPError as err:
            raise ConnectivityError(
                f"home_assistant: read_state({external_id!r}) failed: {err}"
            ) from err
        except ValueError as err:
            raise ConnectivityError(
                f"home_assistant: read_state({external_id!r}) returned invalid JSON: {err}"
            ) from err

        return DeviceState(
            external_id=external_id,
            status=str(raw.get("state", "")),
            attributes=dict(raw.get("attributes") or {}),
            observed_at=_parse_ha_timestamp(raw.get("last_updated")),
        )

    async def send_command(
        self, external_id: str, command: str, payload: dict[str, Any]
    ) -> CommandResult:
        client = self._require_client()
        domain = external_id.split(".", 1)[0] if "." in external_id else ""
        if not domain:
            raise ConnectivityError(
                f"home_assistant: {external_id!r} is not a valid Home Assistant entity id."
            )

        import httpx

        body = {"entity_id": external_id, **payload}
        try:
            response = await client.post(f"/api/services/{domain}/{command}", json=body)
        except httpx.HTTPError as err:
            raise ConnectivityError(
                f"home_assistant: send_command({command!r}) transport failure: {err}"
            ) from err

        if response.status_code >= 400:
            detail = response.text.strip()[:200] or f"HTTP {response.status_code}"
            return CommandResult(
                external_id=external_id, command=command, success=False, detail=detail
            )
        return CommandResult(external_id=external_id, command=command, success=True)

    def _require_client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise ConnectorNotConnectedError("home_assistant connector is not connected.")
        return self._client


def _entity_to_discovered_device(entity: dict[str, Any]) -> DiscoveredDevice | None:
    entity_id = entity["entity_id"]
    if not isinstance(entity_id, str) or "." not in entity_id:
        raise ValueError(f"malformed entity_id: {entity_id!r}")

    domain = entity_id.split(".", 1)[0]
    device_type = _DEVICE_DOMAINS.get(domain)
    if device_type is None:
        # Not a physical-device domain (automation/script/scene/zone/
        # person/...) -- see module docstring's allowlist rationale.
        return None

    attributes = entity.get("attributes") or {}
    if not isinstance(attributes, dict):
        attributes = {}
    name = str(attributes.get("friendly_name") or entity_id)

    return DiscoveredDevice(
        external_id=entity_id,
        name=name,
        device_type=device_type,
        metadata={"domain": domain},
    )


def _parse_ha_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
