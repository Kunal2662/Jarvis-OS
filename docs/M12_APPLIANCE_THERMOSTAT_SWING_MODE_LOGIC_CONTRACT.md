# M12 Appliance Control — Thermostat Swing Mode — Logic Contract

Status: **Implemented this session** (Task Group DD). Closes one item
the original Climate/Thermostat Slice's own Logic Contract explicitly
named and deferred (§17): "Swing mode (`set_swing_mode`) — [Own
service + own vocabulary; not in the approved slice]." Preset modes
and humidity/dehumidify remain separately deferred, unchanged.

## 1. External verification (this session, via live web search — Home
Assistant's own documentation, not recalled from training data)

- **`climate.set_swing_mode`** — sets the swing mode of a climate
  device. One parameter, **`swing_mode`**, a string whose valid values
  are device-reported (e.g. `off`/`vertical`/`horizontal`/`both`,
  platform-dependent) — the identical shape `hvac_mode`/`fan_mode`
  already have, not a fixed HA-wide enum.
  [Set thermostat swing mode — Home Assistant](https://www.home-assistant.io/actions/climate.set_swing_mode/)
- **Read attribute: `swing_mode` (current) / `swing_modes` (declared
  capability list)** — confirmed as the real attribute names.
  [Climate — Home Assistant](https://www.home-assistant.io/integrations/climate/)
- **Out of scope, deliberately not touched**: HA also exposes an
  independent `climate.set_swing_horizontal_mode`/
  `swing_horizontal_mode`/`swing_horizontal_modes` for integrations
  with separate vertical/horizontal swing control. This slice covers
  only the original (vertical/primary) `swing_mode` — the same scope
  the original Logic Contract's §17 named — not the newer horizontal
  variant, which is a separate, not-yet-evaluated feature.

## 2. Existing evidence (re-confirmed this session)

`ThermostatService`'s own Thermostat Fan Mode slice already proved the
exact shape this slice needs: `_validate_mode` is attribute-agnostic
(reused verbatim via `field_name`), `_validate_against_device` already
checks one attribute's requested value against a device-reported list
attribute, and `_translate_home_assistant`/`_translate_mqtt` already
append a mode-shaped keyword as an independent, no-ordering-dependency
wire call. Swing Mode reuses every one of these verbatim, the same way
Fan Mode reused HVAC Mode's own template. Zero connector changes —
both connectors' `send_command` already accept an arbitrary payload
dict generically.

## 3. Architecture decision

**Add `swing_mode` as a fourth optional keyword on the existing
`set_thermostat_state`, not a new method.** Matches this module's own
established shape — every thermostat attribute lives on this one
merged mutation, discriminated by which keywords are non-`None`.

**No new validator, no new device-list-check function.** `_validate_mode`
is called with `field_name="swing_mode"` (the same reuse Fan Mode
already established); `_validate_against_device` gains one more
`if swing_mode is not None:` block checking against `swing_modes`,
textually identical in shape to the existing `hvac_mode`/`fan_mode`
blocks.

**Call order**: hvac_mode, temperature, fan_mode, swing_mode — appended
last, fixed for determinism rather than meaningful, the same reasoning
`fan_mode`'s own placement already used (no evidence ties swing mode to
what any of the other three mean).

## 4. Read model addition

```python
payload["swing_mode"] = None
payload["swing_modes"] = []
```

Added to `_thermostat_payload`. `swing_modes` is a capability field
that survives unavailability (mirrors `hvac_modes`/`fan_modes` exactly
— reuses the existing `_coerce_modes` helper, no new helper needed).
`swing_mode` is a live reading, gated behind `available`, mirroring
`fan_mode`'s identical "plain attribute, not the entity's own state
string, but still gated the same way" treatment.

## 5. Write model addition

`set_thermostat_state` gains one new keyword-only parameter:
`swing_mode: str | None = None`. The empty-mutation check widens to
all four keywords. `_translate_home_assistant`/`_translate_mqtt` gain
the same keyword-only parameter (defaulting to `None`) — every
existing call site and every existing direct-call unit test assertion
(which pass `temperature=`/`hvac_mode=`/`fan_mode=` explicitly) is
unaffected.

## 6. REST / agent tools

No new route, no new agent tool — `POST /thermostats/{id}/state` and
the existing `set_thermostat_state` agent tool both gain the one new
optional field, identical to how Thermostat Fan Mode, Media Player
Shuffle/Repeat/Sound Mode, and Water Heater Away/Vacation Mode each
extended their own merged mutation without a new route or tool.

## 7. Permission / security

Unchanged. Same `core:thermostats` principal, same `smart_home` scope,
same ungated-reads/gated-mutation shape as every other thermostat
command.

## 8. Test strategy

Extends `test_m12_thermostat_service.py`, `test_m12_thermostats_route.py`,
`test_m12_thermostat_tools.py` — mirroring `fan_mode`'s own existing
test shape for `swing_mode` (denied-by-default, empty-string rejection,
device-list validation, permissive-when-no-list, standalone mutation,
combined-mutation ordering extended to all four). Combined-mutation
ordering is pinned by a direct translator unit test asserting all four
calls in the declared order when all four are supplied.

## 9. Non-goals

Preset modes, humidity/dehumidify, `dry`/`fan_only` special-casing,
aux/emergency heat, dual setpoint, scheduling/automation, energy
optimization, and multi-zone orchestration all remain deferred,
unchanged. `climate.set_swing_horizontal_mode` (the separate
horizontal-swing feature) is deliberately not built here (§1). No
connector, `DEVICE_TYPES`, or `CONNECTOR_TYPES` change.

## 10. Acceptance criteria

- `climate.set_swing_mode` name and its `swing_mode` parameter, plus
  the `swing_mode`/`swing_modes` attribute names, externally verified
  this session (§1), not recalled.
- `swing_mode` validated via the existing `_validate_mode` (non-empty
  string), then checked against the device's own reported
  `swing_modes` only when non-empty via the existing
  `_validate_against_device`, never an invented enum.
- `swing_modes` read survives unavailability like `hvac_modes`/
  `fan_modes`; `swing_mode` is gated behind `available` like
  `fan_mode`.
- Every existing `set_thermostat_state`/translator call site and
  direct-call unit test is behaviorally unchanged.
- Zero connector, `DEVICE_TYPES`, or `CONNECTOR_TYPES` changes.
- No new REST route; no new agent tool.
