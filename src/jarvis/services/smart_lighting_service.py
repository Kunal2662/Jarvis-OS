"""Smart Lighting service -- Milestone 12 Connectivity REST + Smart
Lighting.

The thin orchestration layer the Logic Contract
(``docs/M12_CONNECTIVITY_REST_SMART_LIGHTING_LOGIC_CONTRACT.md``)
requires: normalized light commands in, wire-format commands out,
through :meth:`ConnectivityService.send_command` -- the same chokepoint
every other M12 caller already uses, never a second execution path.
This module owns exactly two things neither existing service owns:
command translation (below) and lighting scenes (stored here, since
neither ``SmartHomeService`` nor ``ConnectivityService`` models one).

**Why translation takes keyword attributes, not one ``LightCommand`` at
a time.** Home Assistant's own ``light.turn_on`` service natively
accepts brightness, color temperature and color together in one call --
setting two attributes at once is one HTTP request, not two. Dispatching
per-:class:`LightCommand` would force two separate wire commands for
"turn on at 50% brightness in blue", which is both slower and, for a
real device, a visible two-step flicker instead of one change.
:func:`_translate_home_assistant`/:func:`_translate_mqtt` therefore each
take every optional attribute and merge whatever is set into one wire
command. :class:`LightCommand` still names the vocabulary this module
supports -- used in docstrings and by callers that want to know what a
light command *is* -- it is just not the translation functions' own
dispatch key.

**MQTT command vocabulary is this module's own.** ``mqtt_envelope.py``'s
``build_command_envelope(device_id, command, args)`` deliberately leaves
*command*/*args* free-form -- "the command's own parameters" -- because
no MQTT-side consumer existed before this module. ``turn_off`` and
``set_state`` (below) are that vocabulary's first real definition, not a
guess at an existing, undocumented one.

**Permission enforcement reuses the existing Permission Engine, not a
new one.** Every side-effecting method here checks the same
``PermissionModel`` (``core/plugins/permissions.py``) M9's Plugin
Platform and M11's Integration Platform already use, under one fixed
principal, :data:`SMART_LIGHTING_PRINCIPAL`, declared once at
construction. Out of the box this scope is ``PENDING`` (denied) --
identical to how a freshly-installed M11 integration's own permissions
start, and to how any plugin's manifest-declared scope starts -- until
an operator grants it through the *existing*, already-shipped generic
grant route: ``POST /api/v1/plugins/{principal}/permissions/{scope}/
grant`` (``infrastructure/api/routes/plugins.py``). No new grant surface
is added here; ``plugin_id`` in that route is an opaque principal
string, and this module's principal is simply not a plugin's.
"""

from __future__ import annotations

import contextlib
import enum
import json
from typing import TYPE_CHECKING, Any

from jarvis.core.exceptions import ServiceError
from jarvis.core.interfaces.connectivity import ConnectivityError
from jarvis.infrastructure.database.repositories.smart_lighting_repository import SceneRepository
from jarvis.services.connectivity_service import connector_type_for

if TYPE_CHECKING:
    from collections.abc import Sequence

    from jarvis.core.interfaces.database import IDatabase
    from jarvis.core.plugins.permissions import PermissionModel
    from jarvis.infrastructure.database.models import Device
    from jarvis.services.connectivity_service import ConnectivityService
    from jarvis.services.smart_home_service import SmartHomeService

#: The `PermissionModel` identity this module declares and checks
#: against. Fixed and singular -- unlike an M11 integration (one
#: principal per installed vendor) or an MCP peer (one per connection),
#: Smart Lighting is one capability with one gate, not a per-instance
#: one.
SMART_LIGHTING_PRINCIPAL = "core:smart_lighting"

#: The pre-existing, pre-declared scope (`core/plugins/sdk.py`'s
#: `PERMISSION_SCOPES`) this module is the first real enforcer of.
SMART_HOME_SCOPE = "smart_home"

#: The device type this service operates on -- Task Group A's own
#: closed `DEVICE_TYPES` vocabulary (`domain/smart_home/models.py`).
_LIGHT_DEVICE_TYPE = "light"

#: Status strings a connector's raw state report (`DeviceState.status`)
#: uses to mean "the light is on"/"off" -- best-effort, since neither
#: connector's own state vocabulary is closed the way `DEVICE_STATUSES`
#: is; an unrecognized string reports `on: None` (unknown) rather than
#: guessing.
_ON_STATUS_VALUES = frozenset({"on", "true", "1"})
_OFF_STATUS_VALUES = frozenset({"off", "false", "0"})


class LightCommand(enum.StrEnum):
    """The normalized command vocabulary this module supports -- see
    module docstring for why translation itself works on keyword
    attributes rather than dispatching one of these at a time."""

    TURN_ON = "turn_on"
    TURN_OFF = "turn_off"
    SET_BRIGHTNESS = "set_brightness"
    SET_COLOR_TEMP = "set_color_temp"
    SET_COLOR = "set_color"


#: A scene target's recognized keys -- exactly `set_light_state`'s own
#: optional keyword attributes, so `apply_scene` can pass a stored
#: target straight through as `**kwargs`.
_SCENE_TARGET_ATTRS = ("on", "brightness", "color_temp_kelvin", "color")


def _translate_home_assistant(
    *,
    on: bool | None,
    brightness: int | None,
    color_temp_kelvin: int | None,
    color: Sequence[int] | None,
) -> tuple[str, dict[str, Any]]:
    """HA service-call mapping, per the Logic Contract: ``turn_on``/
    ``turn_off`` alone for a bare on/off, otherwise a single
    ``turn_on`` call carrying every changed attribute.

    ``brightness_pct`` (0-100), not ``brightness`` (HA's native 0-255
    scale) -- this module's own normalized brightness is already 0-100,
    and HA's `light.turn_on` service accepts `brightness_pct` directly,
    so no lossy rounding conversion is needed. ``color_temp_kelvin``
    requires a reasonably current Home Assistant core version (older
    releases only understood `color_temp` in mireds) -- an accepted,
    documented scope choice, not an oversight; see the Logic Contract's
    own "confidence" framing for the HA translation.
    """
    if on is False and brightness is None and color_temp_kelvin is None and color is None:
        return "turn_off", {}
    payload: dict[str, Any] = {}
    if brightness is not None:
        payload["brightness_pct"] = brightness
    if color_temp_kelvin is not None:
        payload["color_temp_kelvin"] = color_temp_kelvin
    if color is not None:
        payload["rgb_color"] = list(color)
    return "turn_on", payload


def _translate_mqtt(
    *,
    on: bool | None,
    brightness: int | None,
    color_temp_kelvin: int | None,
    color: Sequence[int] | None,
) -> tuple[str, dict[str, Any]]:
    """The JARVIS-native MQTT light vocabulary this module defines --
    see module docstring. ``turn_off`` alone for a bare off; otherwise
    ``set_state`` carrying every changed attribute, mirroring the HA
    translator's own "one merged call" shape for firmware that wants to
    apply several changes atomically too."""
    if on is False and brightness is None and color_temp_kelvin is None and color is None:
        return "turn_off", {}
    payload: dict[str, Any] = {}
    if on is True:
        payload["on"] = True
    if brightness is not None:
        payload["brightness"] = brightness
    if color_temp_kelvin is not None:
        payload["color_temp_kelvin"] = color_temp_kelvin
    if color is not None:
        payload["color"] = list(color)
    return "set_state", payload


#: Connector type -> translator. Closed to `CONNECTOR_TYPES`
#: (`core/interfaces/connectivity.py`) by construction -- a connector
#: type with no entry here is a real, reportable gap (`set_light_state`
#: raises `ServiceError`), never a silent no-op.
_TRANSLATORS = {
    "home_assistant": _translate_home_assistant,
    "mqtt": _translate_mqtt,
}


def _validate_brightness(value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not (0 <= value <= 100):
        raise ServiceError(f"brightness must be an integer 0-100; got {value!r}.")


def _validate_color_temp_kelvin(value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ServiceError(f"color_temp_kelvin must be a positive integer; got {value!r}.")


def _validate_color(value: Sequence[int]) -> None:
    if (
        not isinstance(value, (tuple, list))
        or len(value) != 3
        or not all(isinstance(c, int) and not isinstance(c, bool) and 0 <= c <= 255 for c in value)
    ):
        raise ServiceError(f"color must be an (r, g, b) tuple of 0-255 integers; got {value!r}.")


def _infer_on(status: str) -> bool | None:
    normalized = status.strip().lower()
    if normalized in _ON_STATUS_VALUES:
        return True
    if normalized in _OFF_STATUS_VALUES:
        return False
    return None


def _light_payload(device: Device, raw: Any = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": device.id,
        "home_id": device.home_id,
        "room_id": device.room_id,
        "name": device.name,
        "status": device.status,
        "manufacturer": device.manufacturer,
        "model": device.model,
        "external_id": device.external_id,
        "on": None,
        "brightness": None,
        "color_temp_kelvin": None,
        "color": None,
    }
    if raw is not None:
        attributes = raw.attributes or {}
        payload["on"] = _infer_on(raw.status)
        payload["brightness"] = attributes.get("brightness")
        payload["color_temp_kelvin"] = attributes.get("color_temp_kelvin") or attributes.get(
            "color_temp"
        )
        payload["color"] = attributes.get("rgb_color") or attributes.get("color")
    return payload


def _clean_scene_target(target: dict[str, Any]) -> dict[str, Any]:
    device_id = target.get("device_id")
    if not isinstance(device_id, str) or not device_id:
        raise ServiceError("Every scene target requires a non-empty 'device_id'.")
    cleaned: dict[str, Any] = {"device_id": device_id}
    if "on" in target and target["on"] is not None:
        if not isinstance(target["on"], bool):
            raise ServiceError(f"Scene target 'on' must be a boolean; got {target['on']!r}.")
        cleaned["on"] = target["on"]
    if "brightness" in target and target["brightness"] is not None:
        _validate_brightness(target["brightness"])
        cleaned["brightness"] = target["brightness"]
    if "color_temp_kelvin" in target and target["color_temp_kelvin"] is not None:
        _validate_color_temp_kelvin(target["color_temp_kelvin"])
        cleaned["color_temp_kelvin"] = target["color_temp_kelvin"]
    if "color" in target and target["color"] is not None:
        _validate_color(target["color"])
        cleaned["color"] = list(target["color"])
    if len(cleaned) == 1:
        raise ServiceError(
            f"Scene target for {device_id!r} sets none of on/brightness/" "color_temp_kelvin/color."
        )
    return cleaned


def _scene_payload(scene: Any) -> dict[str, Any]:
    return {
        "id": scene.id,
        "home_id": scene.home_id,
        "name": scene.name,
        "targets": json.loads(scene.targets_json or "[]"),
        "created_at": scene.created_at.isoformat() if scene.created_at else None,
        "updated_at": scene.updated_at.isoformat() if scene.updated_at else None,
    }


class SmartLightingService:
    def __init__(
        self,
        *,
        database: IDatabase,
        smart_home: SmartHomeService,
        connectivity: ConnectivityService,
        permissions: PermissionModel,
    ) -> None:
        self._db = database
        self._smart_home = smart_home
        self._connectivity = connectivity
        self._permissions = permissions
        self._permissions.declare(SMART_LIGHTING_PRINCIPAL, [SMART_HOME_SCOPE])

    # ------------------------------------------------------------------
    # Permission
    # ------------------------------------------------------------------
    def _require_permission(self) -> None:
        if not self._permissions.is_granted(SMART_LIGHTING_PRINCIPAL, SMART_HOME_SCOPE):
            raise ServiceError(
                "Smart Lighting control requires the "
                f"{SMART_HOME_SCOPE!r} permission to be granted for "
                f"{SMART_LIGHTING_PRINCIPAL!r}. Grant it via POST "
                f"/api/v1/plugins/{SMART_LIGHTING_PRINCIPAL}/permissions/"
                f"{SMART_HOME_SCOPE}/grant."
            )

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------
    async def _require_light(self, device_id: str) -> Device:
        device = await self._smart_home.require_device(device_id)
        if device.device_type != _LIGHT_DEVICE_TYPE:
            raise ServiceError(f"Device {device_id!r} is a {device.device_type!r}, not a light.")
        return device

    async def list_lights(
        self, *, home_id: str | None = None, room_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Last-known DB records only -- no live connector read per
        light, the same list/detail asymmetry `SmartHomeService.
        list_devices`/`get_device` already draw. Call `get_light_state`
        for one light's live attributes."""
        devices = await self._smart_home.list_devices(
            home_id=home_id, room_id=room_id, device_type=_LIGHT_DEVICE_TYPE
        )
        return [_light_payload(d) for d in devices]

    async def get_light_state(self, device_id: str) -> dict[str, Any]:
        device = await self._require_light(device_id)
        raw = None
        # Connector unreachable/not connected -- report last-known DB
        # state rather than fail the read; see module docstring's "fail
        # safely" framing.
        with contextlib.suppress(ConnectivityError):
            raw = await self._connectivity.read_raw_state(device_id)
        return _light_payload(device, raw)

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------
    async def set_light_state(
        self,
        device_id: str,
        *,
        on: bool | None = None,
        brightness: int | None = None,
        color_temp_kelvin: int | None = None,
        color: Sequence[int] | None = None,
    ) -> dict[str, Any]:
        self._require_permission()
        return await self._set_one(
            device_id,
            on=on,
            brightness=brightness,
            color_temp_kelvin=color_temp_kelvin,
            color=color,
        )

    async def apply_room(
        self,
        room_id: str,
        *,
        on: bool | None = None,
        brightness: int | None = None,
        color_temp_kelvin: int | None = None,
        color: Sequence[int] | None = None,
    ) -> list[dict[str, Any]]:
        self._require_permission()
        lights = await self._smart_home.list_devices(
            room_id=room_id, device_type=_LIGHT_DEVICE_TYPE
        )
        return [
            await self._safe_set(
                light.id,
                on=on,
                brightness=brightness,
                color_temp_kelvin=color_temp_kelvin,
                color=color,
            )
            for light in lights
        ]

    async def apply_group(
        self,
        group_id: str,
        *,
        on: bool | None = None,
        brightness: int | None = None,
        color_temp_kelvin: int | None = None,
        color: Sequence[int] | None = None,
    ) -> list[dict[str, Any]]:
        self._require_permission()
        members = await self._smart_home.list_group_members(group_id)
        return [
            await self._safe_set(
                light.id,
                on=on,
                brightness=brightness,
                color_temp_kelvin=color_temp_kelvin,
                color=color,
            )
            for light in members
            if light.device_type == _LIGHT_DEVICE_TYPE
        ]

    async def _safe_set(self, device_id: str, **kwargs: Any) -> dict[str, Any]:
        """Used by fan-out only, after the caller's own
        `_require_permission()` already passed -- a per-device fault
        (unknown device, non-light, connector down) is reported inline
        rather than aborting the whole room/group, so one offline bulb
        does not block the rest. Permission is deliberately checked
        once by the caller, not per device: re-raising it here would
        turn one authorization gap into N misleading "device failed"
        entries."""
        try:
            return await self._set_one(device_id, **kwargs)
        except ServiceError as err:
            return {"device_id": device_id, "success": False, "detail": str(err)}

    async def _set_one(
        self,
        device_id: str,
        *,
        on: bool | None = None,
        brightness: int | None = None,
        color_temp_kelvin: int | None = None,
        color: Sequence[int] | None = None,
    ) -> dict[str, Any]:
        if on is None and brightness is None and color_temp_kelvin is None and color is None:
            raise ServiceError(
                "set_light_state requires at least one of on/brightness/" "color_temp_kelvin/color."
            )
        if on is False and (
            brightness is not None or color_temp_kelvin is not None or color is not None
        ):
            raise ServiceError("Cannot combine on=False with brightness/color_temp_kelvin/color.")
        if brightness is not None:
            _validate_brightness(brightness)
        if color_temp_kelvin is not None:
            _validate_color_temp_kelvin(color_temp_kelvin)
        if color is not None:
            _validate_color(color)

        device = await self._require_light(device_id)
        connector_type = connector_type_for(device)
        if connector_type is None:
            raise ServiceError(
                f"Device {device_id!r} has no recorded connector; it cannot be commanded."
            )
        translator = _TRANSLATORS.get(connector_type)
        if translator is None:
            raise ServiceError(
                f"Smart Lighting has no command translation for connector type {connector_type!r}."
            )
        wire_command, payload = translator(
            on=on, brightness=brightness, color_temp_kelvin=color_temp_kelvin, color=color
        )
        result = await self._connectivity.send_command(device_id, wire_command, payload)
        return {"device_id": device_id, "success": result.success, "detail": result.detail}

    # ------------------------------------------------------------------
    # Scenes
    # ------------------------------------------------------------------
    async def create_scene(
        self, home_id: str, name: str, targets: list[dict[str, Any]]
    ) -> dict[str, Any]:
        self._require_permission()
        name = (name or "").strip()
        if not name:
            raise ServiceError("Cannot create a scene with an empty name.")
        if not targets:
            raise ServiceError("A scene requires at least one target.")
        await self._smart_home.require_home(home_id)
        cleaned = [_clean_scene_target(t) for t in targets]
        async with self._db.session() as sess:
            scene = await SceneRepository(sess).add(  # type: ignore[arg-type]
                home_id, name, targets_json=json.dumps(cleaned)
            )
            scene_id = scene.id
        return await self.require_scene(scene_id)

    async def get_scene(self, scene_id: str) -> dict[str, Any] | None:
        async with self._db.session() as sess:
            scene = await SceneRepository(sess).get(scene_id)  # type: ignore[arg-type]
        return _scene_payload(scene) if scene is not None else None

    async def require_scene(self, scene_id: str) -> dict[str, Any]:
        scene = await self.get_scene(scene_id)
        if scene is None:
            raise ServiceError(f"Scene {scene_id!r} does not exist.")
        return scene

    async def list_scenes(self, *, home_id: str | None = None) -> list[dict[str, Any]]:
        async with self._db.session() as sess:
            rows = await SceneRepository(sess).list_scenes(home_id=home_id)  # type: ignore[arg-type]
        return [_scene_payload(s) for s in rows]

    async def delete_scene(self, scene_id: str) -> bool:
        self._require_permission()
        async with self._db.session() as sess:
            return await SceneRepository(sess).delete(scene_id)  # type: ignore[arg-type]

    async def apply_scene(self, scene_id: str) -> list[dict[str, Any]]:
        self._require_permission()
        scene = await self.require_scene(scene_id)
        results = []
        for target in scene["targets"]:
            kwargs = {k: target[k] for k in _SCENE_TARGET_ATTRS if k in target}
            results.append(await self._safe_set(target["device_id"], **kwargs))
        return results
