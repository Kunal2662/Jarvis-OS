# M12 Appliance Control — Thermostat Fan Mode — Logic Contract

Status: **Implemented this session** (Task Group Y). Closes one of the
items the original Climate/Thermostat Slice's own Logic Contract
explicitly named and deferred: "Fan mode (`climate.set_fan_mode`) —
own service + own vocabulary; not in the approved slice" (§17). This
contract closes that gap alone — swing mode, preset modes, and
humidity/dehumidify remain deferred, unchanged, per that same table.

## 1. Purpose

Read and write a thermostat's fan mode (`auto`/`on`/`low`/`medium`/
`high`/vendor-specific values), mirroring exactly how `hvac_mode` and
`temperature` are already read and written by `ThermostatService`.
Closes a named, previously-deferred gap; does not touch swing mode,
preset modes, or humidity, which remain separately deferred.

## 2. Existing evidence (re-confirmed this session, not assumed)

**HA service name**, already researched and recorded by the original
Climate slice's own Logic Contract (§17): `climate.set_fan_mode`, one
argument, `fan_mode` — the identical shape `set_hvac_mode` already
uses (`{"hvac_mode": hvac_mode}` → `{"fan_mode": fan_mode}`). No new
external verification needed; this was already evaluated and named
before this slice existed, only deliberately not built.

**`ThermostatService`'s own existing shape** (re-read in full this
session, `services/thermostat_service.py`): `_validate_mode` is already
generic — non-empty string, normalized lowercase — with no
`hvac_mode`-specific logic inside it, so it is reused verbatim for
`fan_mode`, not duplicated. `_thermostat_payload` already draws the
"declared capability, always reported" vs. "current live reading,
gated behind `available`" distinction for `hvac_modes` (capability,
ungated) vs. `hvac_mode` (live reading, gated — because for HA the
entity's own state string *is* the HVAC mode, so an unavailable device
must never report a stale one). `fan_mode` is a plain **attribute**
(`attributes.get("fan_mode")`), not the entity's state string the way
`hvac_mode` is — but it is still a *current* reading, the same
category `current_temperature`/`target_temperature` already fall into
(both attributes, both gated behind `available`). `fan_modes` (the
supported-mode list) is a **declared capability**, the same category
`hvac_modes`/`min_temp`/`max_temp` already fall into (ungated).

**MQTT**: `_translate_mqtt` already merges every set attribute into one
`set_state` call's `args` dict — `fan_mode` is one more key in that
same dict, no new call, no new topic.

**Zero connector changes** — confirmed by the same reasoning the
original Climate slice's own §16 already established for
temperature/hvac_mode: both connectors' `send_command` already accept
an arbitrary command+payload; `climate` → `thermostat` mapping is
unchanged; no new `DEVICE_TYPES`/`CONNECTOR_TYPES` entry.

## 3. Architecture decision

**Add `fan_mode` as a third optional keyword to the existing
`set_thermostat_state`, not a new method or a new service.** Matches
this module's own established shape exactly (`temperature`/`hvac_mode`
are already both optional keywords merged into one call) — a third
attribute is additive, not a redesign. Rejected alternative: a separate
`set_thermostat_fan_mode(device_id, fan_mode)` method, mirroring the
Fan Percentage slice's own standalone `set_fan_percentage`. Rejected
because that slice's fan/cover *are* single-attribute devices with no
existing merged-update method to extend; `ThermostatService` already
has one, and adding a second, narrower mutation method beside it would
create two ways to change the same device for no reason — worse, not
better, API surface.

**Validation and translation both reuse existing generic logic.**
`_validate_mode` (already attribute-agnostic) validates `fan_mode` the
same way it validates `hvac_mode` — no new validator. Device-capability
checking (`_validate_against_device`) gains one more `if fan_mode is
not None` branch, reading `attributes.get("fan_modes")` through the
same already-generic `_coerce_modes` helper `hvac_modes` already uses —
permissive when the device declares no `fan_modes` (Logic Contract
§7's own reasoning, applied identically: rejecting a real device over
an undeclared vocabulary is the worse failure).

## 4. Read model addition

```python
payload["fan_modes"] = []          # declared capability, ungated (like hvac_modes)
payload["fan_mode"] = None         # current reading, gated behind `available` (like current_temperature)
```

`fan_modes` populated from `attributes.get("fan_modes")` via
`_coerce_modes`, always (even when unavailable). `fan_mode` populated
from `attributes.get("fan_mode")` via `_normalize_mode`, only inside
the existing `if payload["available"]:` block, alongside
`current_temperature`/`target_temperature`.

## 5. Write model addition

`set_thermostat_state(device_id, *, temperature=None, hvac_mode=None,
fan_mode=None)`. The existing "at least one of temperature or
hvac_mode" empty-mutation check widens to "at least one of
temperature, hvac_mode, or fan_mode" — the same rule, one more term.

Translator changes:
- HA: one more conditional call, `("set_fan_mode", {"fan_mode":
  fan_mode})`, appended after the existing hvac_mode/temperature
  calls — no ordering interdependency exists between fan mode and
  the other two attributes (unlike hvac_mode-before-temperature,
  which exists so a setpoint applies to the intended mode), so
  placement is arbitrary but fixed for determinism.
- MQTT: `fan_mode` merges into the existing single `args` dict, same
  as `temperature`/`hvac_mode`.

Partial-failure reporting (`_send_all`) is unchanged — it already
handles an arbitrary list of calls generically; a three-call HA update
(mode, temperature, fan) reports exactly which of the three did and
did not apply, the same mechanism already proven for two.

## 6. REST / agent tool

`POST /api/v1/thermostats/{device_id}/state` — `SetThermostatStateRequest`
gains `fan_mode: str | None = None`. `set_thermostat_state` agent tool
gains `fan_mode: str = ""` (LangChain `""`-as-unset convention, matching
`hvac_mode`'s own existing parameter exactly), converted to `None` at
the service boundary. No new route, no new tool — both existing
surfaces already pass every optional keyword through.

## 7. Permission / security

Unchanged. Same `core:thermostats` principal, same `smart_home` scope,
same ungated-reads/gated-mutation shape. `fan_mode` carries no
Sensors-grade privacy weight and no safety weight `unlock_device`/
`disarm`-style confirmation would apply to (it is airflow, not a
door or an alarm).

## 8. Test strategy

Extends `test_m12_thermostat_service.py`, `test_m12_thermostats_route.py`,
`test_m12_thermostat_tools.py` (all three already exist) rather than
new files, mirroring each file's own existing `hvac_mode` test shape
for `fan_mode`: read (available, unavailable, malformed `fan_modes`,
capability reported even when unavailable), write (single-attribute,
combined with temperature/hvac_mode producing three ordered calls,
unsupported-but-permissive vendor value, normalization, empty-string
rejection), translator unit tests (HA two-arg and three-arg shapes,
MQTT merged shape), REST body pass-through, agent tool pass-through,
partial-failure reporting across three calls.

## 9. Non-goals

Swing mode, preset modes, humidity/dehumidify — all remain deferred
per the original Climate slice's own §17 table, unchanged by this
slice. No connector modification (§2). No new `DEVICE_TYPES`/
`CONNECTOR_TYPES` entry. No new REST route, no new agent tool.

## 10. Acceptance criteria

- `fan_mode` readable via `GET /thermostats/{id}` (gated by
  `available`) and `fan_modes` (declared capability, ungated).
- `fan_mode` writable via the existing `POST /thermostats/{id}/state`
  and the existing `set_thermostat_state` agent tool, alongside
  `temperature`/`hvac_mode` in one call.
- `_validate_mode` reused verbatim for `fan_mode` — no duplicate
  validator.
- Device-reported `fan_modes` permissively checked, same posture as
  `hvac_modes`.
- HA translator emits `("set_fan_mode", {"fan_mode": ...})`; MQTT
  translator merges `fan_mode` into its existing single call.
- Zero connector, `DEVICE_TYPES`, or `CONNECTOR_TYPES` changes.
- Zero new REST route, zero new agent tool.
