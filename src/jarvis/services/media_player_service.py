"""Media Player service -- Milestone 12 Appliance Control (Media Player
Core Slice).

**Deliberately not an `ApplianceService` extension.** Same reasoning as
`VacuumHumidifierService`'s own module docstring: `media_player` shares
`device_type="appliance"` with Fan/Cover/Vacuum/Humidifier (unlike
Climate's own `device_type`), so this module mirrors
`ApplianceService`'s domain-discrimination shape rather than
`ThermostatService`'s, but still ships as its own service per
`ApplianceService`'s own explicit instruction not to grow new branches
onto it.

**The MQTT `component`/`domain` fix is local to this module.**
`MqttConnector._handle_ha_discovery` writes `metadata["component"]`,
never `metadata["domain"]` -- the same pre-existing gap
`VacuumHumidifierService` first worked around. This module's own
`_domain_for` checks `metadata["domain"]` first, falling back to
`metadata["component"]` -- MQTT's `component` segment carries the
identical domain vocabulary HA's own REST connector calls `domain`
(`_HA_COMPONENT_DEVICE_TYPES`'s keys are identical to
`_DEVICE_DOMAINS`'s keys), so this is a safe, narrow extension of the
existing "detect at use, not fabricate" discipline, not a new
mechanism. `ApplianceService`'s own identical gap is not touched here.

**Hybrid command shape** (`docs/M12_APPLIANCE_MEDIA_PLAYER_LOGIC_
CONTRACT.md` §8/§9): five independent, zero-payload transport commands
(play/pause/stop/next/previous), mirroring `VacuumCommand`'s shape --
plus one merged attribute mutation (`volume`/`muted`/`source`),
mirroring `ThermostatService.set_thermostat_state`'s shape. The two are
kept structurally separate because transport verbs and settable
attributes are different kinds of operations, never combined into one
call.

**Volume stays HA-native (`0.0`-`1.0` float) -- no 0-100 conversion.**
Unlike Smart Lighting's `brightness_pct` (a real HA-native alternate
parameter), HA's `volume_set` has no percentage sibling, so inventing
one here would be an unjustified conversion layer. The `0.0`-`1.0`
bound *is* enforced, because it is HA's own protocol-level constraint
on the parameter itself, not a guessed device limit.

**`source` is validated against the device's own reported
`source_list` only when non-empty, never against an invented enum** --
directly reusing `ThermostatService`'s `hvac_mode`/`hvac_modes`
template. Case is preserved, not lowercased, since source names are
often human-facing mixed-case labels.

**Shuffle/Repeat/Sound Mode slice**: three more keywords merged into
the same `set_media_player_state` mutation (Logic Contract §3).
`sound_mode` gets the identical `source`/`source_list` treatment.
`repeat` is the one exception to the "no invented enum" rule -- HA
defines it as a protocol-level closed vocabulary (`off`/`all`/`one`)
identical across every media player, the same justification
`_validate_volume`'s `0.0`-`1.0` bound already relies on, not a guessed
device limit. See
`docs/M12_APPLIANCE_MEDIA_PLAYER_SHUFFLE_REPEAT_SOUND_MODE_LOGIC_CONTRACT.md`.
"""

from __future__ import annotations

import contextlib
import enum
import json
import math
from typing import TYPE_CHECKING, Any

from jarvis.core.exceptions import ServiceError
from jarvis.core.interfaces.connectivity import ConnectivityError
from jarvis.services.connectivity_service import connector_type_for

if TYPE_CHECKING:
    from jarvis.core.plugins.permissions import PermissionModel
    from jarvis.infrastructure.database.models import Device
    from jarvis.services.connectivity_service import ConnectivityService
    from jarvis.services.smart_home_service import SmartHomeService

#: The `PermissionModel` identity this module declares and checks
#: against -- one principal covering both transport and state
#: mutations, mirroring `VACUUM_HUMIDIFIER_PRINCIPAL`'s naming and
#: one-principal-per-module reasoning.
MEDIA_PLAYER_PRINCIPAL = "core:media_players"

#: The pre-existing, shared scope (`core/plugins/sdk.py`'s
#: `PERMISSION_SCOPES`) -- no new scope is created.
SMART_HOME_SCOPE = "smart_home"

_APPLIANCE_DEVICE_TYPE = "appliance"
_MEDIA_PLAYER_DOMAIN = "media_player"

_OFFLINE_STATUS_VALUES = frozenset({"offline", "unavailable"})


class MediaPlayerCommand(enum.StrEnum):
    """Five independent, zero-payload transport commands -- see module
    docstring."""

    PLAY = "media_play"
    PAUSE = "media_pause"
    STOP = "media_stop"
    NEXT = "media_next_track"
    PREVIOUS = "media_previous_track"


def _translate_transport_home_assistant(command: MediaPlayerCommand) -> tuple[str, dict[str, Any]]:
    """HA's own `media_player`-domain service names -- confirmed
    against HA's public documentation this session (Logic Contract
    §8/§10); this repository carries no prior reference to any of
    them. Reached through the existing generic dispatcher
    (`HomeAssistantConnector.send_command` derives `domain` from
    `external_id.split(".", 1)[0]`) -- zero connector changes."""
    return command.value, {}


def _translate_transport_mqtt(command: MediaPlayerCommand) -> tuple[str, dict[str, Any]]:
    """A JARVIS-native vocabulary this module defines -- no prior MQTT
    consumer of media-player transport existed. Reuses the identical
    literal strings for cross-connector predictability, the same
    choice every prior module's MQTT vocabulary made."""
    return command.value, {}


_TRANSPORT_TRANSLATORS = {
    "home_assistant": _translate_transport_home_assistant,
    "mqtt": _translate_transport_mqtt,
}


def _translate_state_home_assistant(
    *,
    volume: float | None,
    muted: bool | None,
    source: str | None,
    shuffle: bool | None = None,
    repeat: str | None = None,
    sound_mode: str | None = None,
) -> list[tuple[str, dict[str, Any]]]:
    """HA's own independent single-purpose services -- `volume_set`,
    `volume_mute`, `select_source` (Logic Contract §10, verified
    externally, not repository-derived), plus `shuffle_set`/
    `repeat_set`/`select_sound_mode` (Shuffle/Repeat/Sound Mode Logic
    Contract §1). **One call per requested attribute**, in the
    contract's declared order (volume, mute, source, shuffle, repeat,
    sound_mode) -- a convention, not a discovered dependency, since
    none of the six changes what another means (unlike Thermostat's
    mode-before-temperature)."""
    calls: list[tuple[str, dict[str, Any]]] = []
    if volume is not None:
        calls.append(("volume_set", {"volume_level": volume}))
    if muted is not None:
        calls.append(("volume_mute", {"is_volume_muted": muted}))
    if source is not None:
        calls.append(("select_source", {"source": source}))
    if shuffle is not None:
        calls.append(("shuffle_set", {"shuffle": shuffle}))
    if repeat is not None:
        calls.append(("repeat_set", {"repeat": repeat}))
    if sound_mode is not None:
        calls.append(("select_sound_mode", {"sound_mode": sound_mode}))
    return calls


def _translate_state_mqtt(
    *,
    volume: float | None,
    muted: bool | None,
    source: str | None,
    shuffle: bool | None = None,
    repeat: str | None = None,
    sound_mode: str | None = None,
) -> list[tuple[str, dict[str, Any]]]:
    """The JARVIS-native MQTT vocabulary this module defines -- always
    one merged `set_state` call, mirroring `ThermostatService`'s/
    `SmartLightingService`'s own MQTT convention. Deliberately *not*
    copying HA's per-attribute service split -- the MQTT envelope has
    no such constraint."""
    args: dict[str, Any] = {}
    if volume is not None:
        args["volume"] = volume
    if muted is not None:
        args["muted"] = muted
    if source is not None:
        args["source"] = source
    if shuffle is not None:
        args["shuffle"] = shuffle
    if repeat is not None:
        args["repeat"] = repeat
    if sound_mode is not None:
        args["sound_mode"] = sound_mode
    return [("set_state", args)]


_STATE_TRANSLATORS = {
    "home_assistant": _translate_state_home_assistant,
    "mqtt": _translate_state_mqtt,
}


def _metadata(device: Device) -> dict[str, Any]:
    try:
        parsed = json.loads(device.metadata_json or "{}")
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _domain_for(device: Device) -> str | None:
    """`metadata["domain"]` first (HA REST discovery, and MQTT's own
    JARVIS-native envelope when firmware chooses to set it); falls back
    to `metadata["component"]` (MQTT HA-Discovery's own key for the
    identical domain vocabulary) -- see module docstring and Logic
    Contract §2. Local to this module by design; not shared with
    `appliance_service.py`."""
    metadata = _metadata(device)
    value = metadata.get("domain") or metadata.get("component")
    return str(value) if value else None


def _coerce_float(value: Any) -> float | None:
    """`None` for anything unparseable -- never a silently wrong `0.0`.
    `bool` is rejected explicitly since it is an `int` subclass."""
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(parsed) or math.isinf(parsed) else parsed


def _coerce_source_list(value: Any) -> list[str]:
    """The device's own reported supported-source list, stripped of
    empty/non-string entries. `[]` when unreported or not a list --
    never a fabricated default vocabulary. Case is preserved (unlike
    `ThermostatService.hvac_modes`, which lowercases -- source names
    are often human-facing mixed-case labels, Logic Contract §12)."""
    if not isinstance(value, (list, tuple)):
        return []
    return [str(entry).strip() for entry in value if isinstance(entry, str) and entry.strip()]


def _coerce_text(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _validate_volume(value: Any) -> float:
    """Rejects `bool`, non-numerics, NaN/+/-inf, and anything outside
    `0.0`-`1.0` -- HA's own protocol-level constraint on the
    `volume_level` parameter itself, not an invented device limit
    (Logic Contract §6)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ServiceError(f"volume must be a number; got {value!r}.")
    parsed = float(value)
    if math.isnan(parsed) or math.isinf(parsed):
        raise ServiceError(f"volume must be a finite number; got {value!r}.")
    if not (0.0 <= parsed <= 1.0):
        raise ServiceError(f"volume must be between 0.0 and 1.0; got {parsed!r}.")
    return parsed


def _validate_muted(value: Any) -> bool:
    if not isinstance(value, bool):
        raise ServiceError(f"muted must be a boolean; got {value!r}.")
    return value


def _validate_source(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ServiceError(f"source must be a non-empty string; got {value!r}.")
    return value.strip()


def _validate_shuffle(value: Any) -> bool:
    """Mirrors `_validate_muted` verbatim."""
    if not isinstance(value, bool):
        raise ServiceError(f"shuffle must be a boolean; got {value!r}.")
    return value


#: HA's own protocol-level closed vocabulary for `repeat` -- identical
#: across every media player, unlike `source`/`sound_mode`, which are
#: device-reported (Shuffle/Repeat/Sound Mode Logic Contract §3).
_REPEAT_VALUES = frozenset({"off", "all", "one"})


def _validate_repeat(value: Any) -> str:
    """The one exception to this module's "no invented enum" rule --
    justified the same way `_validate_volume`'s `0.0`-`1.0` bound
    already is: a protocol-level constraint, not a guessed device
    limit."""
    if not isinstance(value, str) or value not in _REPEAT_VALUES:
        raise ServiceError(f"repeat must be one of {sorted(_REPEAT_VALUES)}; got {value!r}.")
    return value


def _validate_sound_mode(value: Any) -> str:
    """Mirrors `_validate_source` verbatim -- no fixed vocabulary at
    the validation layer; the device's own reported `sound_mode_list`
    is checked separately, by `_check_sound_mode`, only when
    non-empty."""
    if not isinstance(value, str) or not value.strip():
        raise ServiceError(f"sound_mode must be a non-empty string; got {value!r}.")
    return value.strip()


def _media_player_payload(device: Device, raw: Any = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": device.id,
        "home_id": device.home_id,
        "room_id": device.room_id,
        "name": device.name,
        "status": device.status,
        "manufacturer": device.manufacturer,
        "model": device.model,
        "external_id": device.external_id,
        "state": None,
        "available": False,
        "volume_level": None,
        "is_volume_muted": None,
        "source": None,
        "source_list": [],
        "media_title": None,
        "media_artist": None,
        "shuffle": None,
        "repeat": None,
        "sound_mode": None,
        "sound_mode_list": [],
    }
    if raw is None:
        return payload

    payload["available"] = raw.status.strip().lower() not in _OFFLINE_STATUS_VALUES
    attributes = raw.attributes or {}
    # Capability fields survive unavailability -- they describe the
    # device's declared source/sound-mode lists, not a live reading
    # (mirrors ThermostatService's identical rule for hvac_modes/
    # min_temp/max_temp). `_coerce_source_list` is a generic
    # non-empty-string-list coercion despite its name -- reused here
    # for `sound_mode_list` rather than duplicated.
    payload["source_list"] = _coerce_source_list(attributes.get("source_list"))
    payload["sound_mode_list"] = _coerce_source_list(attributes.get("sound_mode_list"))
    if payload["available"]:
        # Open pass-through -- never validated against a closed
        # vocabulary; the entity's own state string IS the playback
        # state, the same shape Vacuum already has (Logic Contract §5).
        normalized = raw.status.strip().lower()
        payload["state"] = normalized or None
        payload["volume_level"] = _coerce_float(attributes.get("volume_level"))
        muted = attributes.get("is_volume_muted")
        payload["is_volume_muted"] = muted if isinstance(muted, bool) else None
        payload["source"] = _coerce_text(attributes.get("source"))
        payload["media_title"] = _coerce_text(attributes.get("media_title"))
        payload["media_artist"] = _coerce_text(attributes.get("media_artist"))
        shuffle = attributes.get("shuffle")
        payload["shuffle"] = shuffle if isinstance(shuffle, bool) else None
        # `repeat` is an open pass-through of HA's own state string,
        # like `state` itself -- never independently re-validated on
        # read (Shuffle/Repeat/Sound Mode Logic Contract §4).
        payload["repeat"] = _coerce_text(attributes.get("repeat"))
        payload["sound_mode"] = _coerce_text(attributes.get("sound_mode"))
    return payload


class MediaPlayerService:
    def __init__(
        self,
        *,
        smart_home: SmartHomeService,
        connectivity: ConnectivityService,
        permissions: PermissionModel,
    ) -> None:
        self._smart_home = smart_home
        self._connectivity = connectivity
        self._permissions = permissions
        self._permissions.declare(MEDIA_PLAYER_PRINCIPAL, [SMART_HOME_SCOPE])

    # ------------------------------------------------------------------
    # Permission
    # ------------------------------------------------------------------
    def _require_permission(self) -> None:
        if not self._permissions.is_granted(MEDIA_PLAYER_PRINCIPAL, SMART_HOME_SCOPE):
            raise ServiceError(
                "Media Player control requires the "
                f"{SMART_HOME_SCOPE!r} permission to be granted for "
                f"{MEDIA_PLAYER_PRINCIPAL!r}. Grant it via POST "
                f"/api/v1/plugins/{MEDIA_PLAYER_PRINCIPAL}/permissions/"
                f"{SMART_HOME_SCOPE}/grant."
            )

    # ------------------------------------------------------------------
    # Domain discrimination
    # ------------------------------------------------------------------
    async def _require_media_player(self, device_id: str) -> Device:
        device = await self._smart_home.require_device(device_id)
        if (
            device.device_type != _APPLIANCE_DEVICE_TYPE
            or _domain_for(device) != _MEDIA_PLAYER_DOMAIN
        ):
            raise ServiceError(f"Device {device_id!r} is not a media player.")
        return device

    # ------------------------------------------------------------------
    # Reads (ungated -- Logic Contract §20)
    # ------------------------------------------------------------------
    async def list_media_players(
        self, *, home_id: str | None = None, room_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Last-known DB records only -- no live connector read per
        device, the same list/detail asymmetry every prior M12 module
        draws."""
        devices = await self._smart_home.list_devices(
            home_id=home_id, room_id=room_id, device_type=_APPLIANCE_DEVICE_TYPE
        )
        return [_media_player_payload(d) for d in devices if _domain_for(d) == _MEDIA_PLAYER_DOMAIN]

    async def get_media_player_state(self, device_id: str) -> dict[str, Any]:
        device = await self._require_media_player(device_id)
        raw = None
        with contextlib.suppress(ConnectivityError):
            raw = await self._connectivity.read_raw_state(device_id)
        return _media_player_payload(device, raw)

    # ------------------------------------------------------------------
    # Transport commands (gated)
    # ------------------------------------------------------------------
    async def play(self, device_id: str) -> dict[str, Any]:
        self._require_permission()
        return await self._send_transport(device_id, MediaPlayerCommand.PLAY)

    async def pause(self, device_id: str) -> dict[str, Any]:
        self._require_permission()
        return await self._send_transport(device_id, MediaPlayerCommand.PAUSE)

    async def stop(self, device_id: str) -> dict[str, Any]:
        self._require_permission()
        return await self._send_transport(device_id, MediaPlayerCommand.STOP)

    async def next_track(self, device_id: str) -> dict[str, Any]:
        self._require_permission()
        return await self._send_transport(device_id, MediaPlayerCommand.NEXT)

    async def previous_track(self, device_id: str) -> dict[str, Any]:
        self._require_permission()
        return await self._send_transport(device_id, MediaPlayerCommand.PREVIOUS)

    async def _send_transport(self, device_id: str, command: MediaPlayerCommand) -> dict[str, Any]:
        device = await self._require_media_player(device_id)
        connector_type = connector_type_for(device)
        if connector_type is None:
            raise ServiceError(
                f"Device {device_id!r} has no recorded connector; it cannot be commanded."
            )
        translator = _TRANSPORT_TRANSLATORS.get(connector_type)
        if translator is None:
            raise ServiceError(
                "Media Player has no command translation for connector type " f"{connector_type!r}."
            )
        wire_command, payload = translator(command)
        result = await self._connectivity.send_command(device_id, wire_command, payload)
        return {"device_id": device_id, "success": result.success, "detail": result.detail}

    # ------------------------------------------------------------------
    # Merged state mutation (gated)
    # ------------------------------------------------------------------
    async def set_media_player_state(
        self,
        device_id: str,
        *,
        volume: float | None = None,
        muted: bool | None = None,
        source: str | None = None,
        shuffle: bool | None = None,
        repeat: str | None = None,
        sound_mode: str | None = None,
    ) -> dict[str, Any]:
        self._require_permission()
        if (
            volume is None
            and muted is None
            and source is None
            and shuffle is None
            and repeat is None
            and sound_mode is None
        ):
            raise ServiceError(
                "set_media_player_state requires at least one of 'volume', 'muted', "
                "'source', 'shuffle', 'repeat', or 'sound_mode'."
            )

        device = await self._require_media_player(device_id)
        connector_type = connector_type_for(device)
        if connector_type is None:
            raise ServiceError(
                f"Device {device_id!r} has no recorded connector; it cannot be commanded."
            )
        translator = _STATE_TRANSLATORS.get(connector_type)
        if translator is None:
            raise ServiceError(
                "Media Player has no command translation for connector type " f"{connector_type!r}."
            )

        validated_volume = None if volume is None else _validate_volume(volume)
        validated_muted = None if muted is None else _validate_muted(muted)
        validated_source = None if source is None else _validate_source(source)
        validated_shuffle = None if shuffle is None else _validate_shuffle(shuffle)
        validated_repeat = None if repeat is None else _validate_repeat(repeat)
        validated_sound_mode = None if sound_mode is None else _validate_sound_mode(sound_mode)
        if validated_source is not None:
            await self._check_source(device_id, validated_source)
        if validated_sound_mode is not None:
            await self._check_sound_mode(device_id, validated_sound_mode)

        calls = translator(
            volume=validated_volume,
            muted=validated_muted,
            source=validated_source,
            shuffle=validated_shuffle,
            repeat=validated_repeat,
            sound_mode=validated_sound_mode,
        )
        return await self._send_all(device_id, calls)

    async def _check_source(self, device_id: str, source: str) -> None:
        """Validates a requested source against the device's **own**
        reported `source_list`. Permissive when the device reports
        none -- rejecting a real device over a vocabulary gap is the
        worse failure (`DEVICE_TYPES`' own stated principle), and no
        fixed source enum is invented here (Logic Contract §12)."""
        raw = None
        with contextlib.suppress(ConnectivityError):
            raw = await self._connectivity.read_raw_state(device_id)
        if raw is None:
            return
        supported = _coerce_source_list((raw.attributes or {}).get("source_list"))
        if supported and source not in supported:
            raise ServiceError(
                f"source {source!r} is not supported by this device; it reports {supported}."
            )

    async def _check_sound_mode(self, device_id: str, sound_mode: str) -> None:
        """Mirrors `_check_source` verbatim -- permissive when the
        device reports no `sound_mode_list` (Shuffle/Repeat/Sound Mode
        Logic Contract §5)."""
        raw = None
        with contextlib.suppress(ConnectivityError):
            raw = await self._connectivity.read_raw_state(device_id)
        if raw is None:
            return
        supported = _coerce_source_list((raw.attributes or {}).get("sound_mode_list"))
        if supported and sound_mode not in supported:
            raise ServiceError(
                f"sound_mode {sound_mode!r} is not supported by this device; "
                f"it reports {supported}."
            )

    async def _send_all(
        self, device_id: str, calls: list[tuple[str, dict[str, Any]]]
    ) -> dict[str, Any]:
        """Executes each wire call in order, stopping at the first
        failure. A partially-applied combined update reports
        `success=False` naming exactly what did and did not apply --
        never a full success, never a silent retry, never claimed
        atomic (Logic Contract §9)."""
        applied: list[str] = []
        for command, payload in calls:
            result = await self._connectivity.send_command(device_id, command, payload)
            if not result.success:
                detail = result.detail
                if applied:
                    detail = (
                        f"{command} failed ({detail or 'no detail'}); "
                        f"already applied: {', '.join(applied)}."
                    )
                return {"device_id": device_id, "success": False, "detail": detail}
            applied.append(command)
        return {"device_id": device_id, "success": True, "detail": ""}
