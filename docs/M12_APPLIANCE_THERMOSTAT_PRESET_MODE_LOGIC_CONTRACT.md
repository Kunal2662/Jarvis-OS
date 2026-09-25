# M12 Appliance Control — Thermostat Preset Modes — Logic Contract

Status: **Implemented this session** (Task Group EE). Closes one item
the original Climate/Thermostat Slice's own Logic Contract explicitly
named and deferred (§17): "Preset modes (`set_preset_mode`, e.g.
eco/away/boost) — Same [own service + own vocabulary; not in the
approved slice]; also overlaps future energy optimization." Humidity/
dehumidify and everything else in that table remain separately
deferred, unchanged.

## 1. Scope note on "overlaps future energy optimization"

The original contract flagged this only as a *reason the item wasn't in
the first slice*, the identical phrasing already applied to Fan Mode
("own service + own vocabulary; not in the approved slice") and Swing
Mode ("Same") before both were closed as thin pass-throughs. This slice
builds nothing beyond the same pass-through: it sends the device's own
requested `preset_mode` string and reports the device's own reported
value back — no scheduling, no automatic preset selection, no energy
calculation of any kind. It therefore does not encroach on Energy
Management's own (unstarted) optimization scope, `ARCHITECTURE.md` §22's
frozen provider-routing/cost-control scope, or Home Automation's
scheduling scope — none of which this slice touches, imports, or
depends on.

## 2. External verification (this session, via live web search — Home
Assistant's own documentation, not recalled from training data)

- **`climate.set_preset_mode`** — sets the preset mode of a climate
  device. One parameter, **`preset_mode`**, a string (e.g. `"eco"`,
  `"away"`, `"boost"`) whose valid values are device-reported —
  platform-dependent, no fixed HA-wide enum. The identical shape
  `hvac_mode`/`fan_mode`/`swing_mode` already have.
  [Set thermostat preset mode — Home Assistant](https://www.home-assistant.io/actions/climate.set_preset_mode/)
- **Read attribute: `preset_mode` (current) / `preset_modes` (declared
  capability list)** — confirmed as the real attribute names via HA's
  own developer tools description.
  [Climate — Home Assistant](https://www.home-assistant.io/integrations/climate/)

## 3. Existing evidence (re-confirmed this session)

`ThermostatService`'s own Fan Mode and Swing Mode slices already prove
the exact shape this slice needs, twice over: `_validate_mode` is
attribute-agnostic (reused verbatim via `field_name`),
`_validate_against_device` already checks a requested value against a
device-reported list attribute for two other keywords, and both
translators already append a mode-shaped keyword as an independent,
no-ordering-dependency wire call. Preset Mode reuses every one of these
verbatim. Zero connector changes — both connectors' `send_command`
already accept an arbitrary payload dict generically.

## 4. Architecture decision

**Add `preset_mode` as a fifth optional keyword on the existing
`set_thermostat_state`, not a new method.** Matches this module's own
established shape — every thermostat attribute lives on this one
merged mutation, discriminated by which keywords are non-`None`.

**No new validator, no new device-list-check function.** `_validate_mode`
is called with `field_name="preset_mode"`; `_validate_against_device`
gains one more `if preset_mode is not None:` block checking against
`preset_modes`, textually identical in shape to the existing
`hvac_mode`/`fan_mode`/`swing_mode` blocks.

**Call order**: hvac_mode, temperature, fan_mode, swing_mode,
preset_mode — appended last, fixed for determinism rather than
meaningful, the same reasoning `fan_mode`'s and `swing_mode`'s own
placement already used (no evidence ties preset mode to what any of
the other four mean).

## 5. Read model addition

```python
payload["preset_mode"] = None
payload["preset_modes"] = []
```

Added to `_thermostat_payload`. `preset_modes` is a capability field
that survives unavailability (mirrors `hvac_modes`/`fan_modes`/
`swing_modes` exactly — reuses the existing `_coerce_modes` helper, no
new helper needed). `preset_mode` is a live reading, gated behind
`available`, mirroring `fan_mode`/`swing_mode`'s identical "plain
attribute, not the entity's own state string, but still gated the same
way" treatment.

## 6. Write model addition

`set_thermostat_state` gains one new keyword-only parameter:
`preset_mode: str | None = None`. The empty-mutation check widens to
all five keywords. `_translate_home_assistant`/`_translate_mqtt` gain
the same keyword-only parameter (defaulting to `None`) — every
existing call site and every existing direct-call unit test assertion
is unaffected.

## 7. REST / agent tools

No new route, no new agent tool — `POST /thermostats/{id}/state` and
the existing `set_thermostat_state` agent tool both gain the one new
optional field, identical to how Fan Mode, Swing Mode, Media Player
Shuffle/Repeat/Sound Mode, and Water Heater Away/Vacation Mode each
extended their own merged mutation without a new route or tool.

## 8. Permission / security

Unchanged. Same `core:thermostats` principal, same `smart_home` scope,
same ungated-reads/gated-mutation shape as every other thermostat
command.

## 9. Test strategy

Extends `test_m12_thermostat_service.py`, `test_m12_thermostats_route.py`,
`test_m12_thermostat_tools.py` — mirroring `fan_mode`'s/`swing_mode`'s
own existing test shape for `preset_mode` (denied-by-default,
empty-string rejection, device-list validation, permissive-when-no-
list, standalone mutation, combined-mutation ordering extended to all
five, read gated behind `available`, capability list survives
unavailability). Combined-mutation ordering is pinned by a direct
translator unit test asserting all five calls in the declared order
when all five are supplied.

## 10. Non-goals

Humidity/dehumidify, `dry`/`fan_only` special-casing, aux/emergency
heat, dual setpoint, scheduling/automation, energy optimization, and
multi-zone orchestration all remain deferred, unchanged. No connector,
`DEVICE_TYPES`, or `CONNECTOR_TYPES` change.

## 11. Acceptance criteria

- `climate.set_preset_mode` name and its `preset_mode` parameter, plus
  the `preset_mode`/`preset_modes` attribute names, externally verified
  this session (§2), not recalled.
- `preset_mode` validated via the existing `_validate_mode` (non-empty
  string), then checked against the device's own reported
  `preset_modes` only when non-empty via the existing
  `_validate_against_device`, never an invented enum.
- `preset_modes` read survives unavailability like `hvac_modes`/
  `fan_modes`/`swing_modes`; `preset_mode` is gated behind `available`
  like `fan_mode`/`swing_mode`.
- Every existing `set_thermostat_state`/translator call site and
  direct-call unit test is behaviorally unchanged.
- Zero connector, `DEVICE_TYPES`, or `CONNECTOR_TYPES` changes.
- No new REST route; no new agent tool.
