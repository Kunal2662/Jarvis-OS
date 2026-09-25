# M12 Appliance Control — Vacuum Fan Speed — Logic Contract

Status: **Implemented this session** (Task Group AA). Closes one item
the Vacuum + Humidifier Core Slice's own Logic Contract explicitly
named and deferred (§18): "Fan speed, cleaning mode — Graduated/enum
control — the same 'defer to a future attribute-merge pass' reasoning
Appliance Control already used for fan percentage and Thermostat used
for HVAC mode's more complex cousins." Cleaning mode, spot cleaning,
locate, room targeting, maps, and everything else in that table remain
separately deferred, unchanged.

## 1. External verification (this session, via live web search — Home
Assistant's own documentation, not recalled from training data)

- **`vacuum.set_fan_speed`** — sets the fan/power level for cleaning.
  One parameter, **`fan_speed`**, a string label (e.g. `"eco"`,
  `"turbo"`) or, on some platforms, a percentage — platform-dependent,
  no fixed HA-wide enum.
  [Set fan speed — Home Assistant](https://www.home-assistant.io/actions/vacuum.set_fan_speed/)
- **Read attributes: `fan_speed` (current) / `fan_speed_list`
  (declared capability)** — `fan_speed_list` is the device's own
  reported list of valid values; some integrations omit it entirely,
  and `fan_speed` may be `None` while the vacuum is off/idle.
  [Vacuum — Home Assistant](https://www.home-assistant.io/integrations/vacuum/)

Because HA itself defines no fixed vocabulary (unlike Cover's small,
standard state set), `fan_speed` is validated the same way
`MediaPlayerService` already validates `source` against
`source_list` — against the device's **own** reported list, only when
that list is non-empty, never against an invented enum. This is the
identical "permissive when the device reports none" rule
`ThermostatService.hvac_modes`/`fan_modes` and `MediaPlayerService.
source_list` already established.

## 2. Existing evidence (re-confirmed this session)

`VacuumHumidifierService._translate_vacuum_home_assistant`/
`_translate_vacuum_mqtt` already exist for the four zero-payload
`VacuumCommand` members and already prove both connectors are reached
identically through `ConnectivityService.send_command` — zero
connector changes needed, the same generic-payload-dict reasoning
every prior Appliance Control slice has established.
`MediaPlayerService._coerce_source_list`/`_validate_source`/
`_check_source` are the closest existing pattern for a
device-list-validated string attribute and are mirrored here under new
names local to this module (no cross-module import — every M12 module
keeps its own copy of this shape, the same convention `_domain_for` is
already duplicated under).

## 3. Architecture decision

**Add `set_fan_speed` as a new method on the existing
`VacuumHumidifierService`, not a new service.** Matches this module's
own established shape — every vacuum capability lives on this one
service, discriminated by `_domain_for`/`_require_vacuum`, never split
across services per command.

**Extend `VacuumCommand` and `_send_vacuum` to carry an optional
value, rather than bypassing the shared translator/dispatch path.**
`VacuumCommand` gains `SET_FAN_SPEED = "set_fan_speed"`, and both
`_translate_vacuum_home_assistant`/`_translate_vacuum_mqtt` gain a
keyword-only `fan_speed: str | None = None` parameter: `None` keeps
producing `{}` (the four existing zero-payload commands, unaffected),
a supplied value produces `{"fan_speed": fan_speed}`. `_send_vacuum`
gains the same keyword-only parameter and passes it straight through
to whichever translator is selected — the four existing call sites
(`start`/`stop`/`pause`/`return_to_base`) are textually unchanged,
since the new parameter defaults to `None`.

## 4. Read model addition

```python
payload["fan_speed"] = None
payload["fan_speed_list"] = []
```

Added to `_vacuum_payload`. `fan_speed_list` is a capability field
that survives unavailability (mirrors `MediaPlayerService.source_list`/
`ThermostatService.hvac_modes` — it describes the device's declared
vocabulary, not a live reading). `fan_speed` is a live reading, gated
behind `available`, read via a new local `_coerce_text` helper
(`str | None`, mirroring `MediaPlayerService._coerce_text` exactly —
`fan_speed` is a free-form label, not a number, so `_coerce_float`
does not apply).

## 5. Write model addition

- `set_fan_speed(device_id, fan_speed)` — sends exactly one
  `set_fan_speed` wire command, never an implicit accompanying
  `start`/`pause` call, mirroring `set_cover_position`'s/`set_media_
  player_state`'s own "exactly one standalone wire command" and
  "device-list-validated string" disciplines respectively. Rejects a
  non-vacuum device via the existing `_require_vacuum`. Validated via
  a new `_validate_fan_speed` (non-empty string, mirrors
  `_validate_source` verbatim) then checked against the device's own
  reported `fan_speed_list` via a new `_check_fan_speed` (mirrors
  `MediaPlayerService._check_source` verbatim — permissive when the
  device reports no list, and a read failure here is never fatal to
  the mutation).

## 6. REST / agent tools

- `POST /appliances/vacuums/{device_id}/set_fan_speed` — body
  `{"fan_speed": str}`.
- One new agent tool, `vacuum_set_fan_speed`, mirroring
  `vacuum_start`'s/`set_media_player_state`'s own docstring and
  confirm-before-calling framing. Not added to `AgentSettings.
  confirm_required_tools` — adjusting a running vacuum's fan speed
  carries the same non-safety-relevant weight `set_cover_position`/
  `set_media_player_state` already carry.

## 7. Permission / security

Unchanged. Same `core:vacuum_humidifier` principal, same `smart_home`
scope, same ungated-reads/gated-mutation shape as every other vacuum
command.

## 8. Test strategy

Extends `test_m12_vacuum_humidifier_service.py`, `test_m12_vacuums_
humidifiers_route.py`, `test_m12_vacuum_humidifier_tools.py` (all three
already exist), mirroring `set_cover_position`'s/`set_media_player_
state`'s own existing test shapes: denied-by-default, wrong-device-type
rejection (a humidifier is not a vacuum), empty-string rejection, a
supported-list acceptance case, an unsupported-value rejection case, a
permissive-when-no-list-reported case, sends exactly one wire command
never implying `start`/`pause`, failure reporting, MQTT translation,
and a read round-trip for both `fan_speed` (gated behind `available`)
and `fan_speed_list` (survives unavailability).

## 9. Non-goals

Every other item the original slice's own §18 deferred table still
names (cleaning mode, spot cleaning, locate, room targeting, maps,
scheduling, vendor-specific advanced modes, humidifier mode
control/presets, water-level automation) remains deferred, unchanged.
No connector, `DEVICE_TYPES`, or `CONNECTOR_TYPES` change.

## 10. Acceptance criteria

- `vacuum.set_fan_speed` name and its `fan_speed` parameter, plus the
  `fan_speed`/`fan_speed_list` attribute names, externally verified
  this session (§1), not recalled.
- `fan_speed` validated as a non-empty string, then checked against
  the device's own reported `fan_speed_list` only when non-empty —
  never an invented enum.
- `fan_speed_list` read survives unavailability like `hvac_modes`/
  `source_list`; `fan_speed` is gated behind `available` like `state`.
- `_send_vacuum`'s four existing call sites are behaviorally unchanged.
- Zero connector, `DEVICE_TYPES`, or `CONNECTOR_TYPES` changes.
- No new REST route beyond the one named; no new agent tool beyond the
  one named; not added to `confirm_required_tools`.
