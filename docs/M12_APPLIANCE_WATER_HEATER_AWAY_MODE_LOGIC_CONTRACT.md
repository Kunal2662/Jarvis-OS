# M12 Appliance Control — Water Heater Away/Vacation Mode — Logic Contract

Status: **Implemented this session** (Task Group CC). Closes one item
the Water Heater Core Slice's own Logic Contract explicitly named and
deferred (§16): "Away/vacation mode (`is_away_mode_on`, `set_away_mode`)
— Real HA feature (VERIFIED EXTERNALLY, §7's source) but out of this
MVP's named scope; no read, no write, no field anywhere." Dual setpoint
and everything else in that table remain separately deferred,
unchanged.

## 1. External verification (this session, via live web search — Home
Assistant's own documentation and source, not recalled from training
data)

- **`water_heater.set_away_mode`** — turns away mode on or off for a
  water heater. One parameter, **`away_mode`**, boolean.
  [Set water heater away mode — Home Assistant](https://www.home-assistant.io/actions/water_heater.set_away_mode)
- **Read attribute: `away_mode`** — the water heater component's own
  `ATTR_AWAY_MODE = "away_mode"` constant (confirmed against
  `home-assistant/core`'s `water_heater/__init__.py`), exposed under
  the identical key as the write parameter — the same "write parameter
  and read attribute share one name" shape `is_volume_muted` already
  has for Media Player, unlike `position`/`current_cover_position`'s
  deliberately different names.
  [core/homeassistant/components/water_heater/__init__.py](https://github.com/home-assistant/core/blob/dev/homeassistant/components/water_heater/__init__.py)

## 2. Existing evidence (re-confirmed this session)

`WaterHeaterService._translate_state_home_assistant`/`_translate_state_
mqtt` already prove the exact shape this slice needs — HA sends one
independent service call per attribute (`turn_on`/`turn_off`/
`set_operation_mode`/`set_temperature`), MQTT merges everything into
one `set_state` call. `_validate_on` already proves the plain-boolean
validation template this slice reuses. Zero connector changes — both
connectors' `send_command` already accept an arbitrary payload dict
generically.

## 3. Architecture decision

**Extend the existing merged `set_water_heater_state` with one more
optional keyword, not a new method.** `away_mode` is an attribute that
combines with `on`/`operation_mode`/`temperature` into the same "one
user intent" mutation — the identical reasoning that already grouped
those three into one call. Call order extends to on/off, mode,
temperature, away_mode (appended last, per the contract's own
declared-order convention — not a discovered HA dependency, since
nothing ties away mode to what the other three mean).

**No fixed vocabulary, no device-list check.** `away_mode` is a plain
boolean, the same shape `on` already has — there is no device-reported
capability list for it the way `operation_list`/`fan_speed_list`/
`sound_mode_list` exist for their respective enum-valued attributes.

## 4. Read model addition

```python
payload["away_mode"] = None
```

Added to `_water_heater_payload`, read from `attributes.get("away_mode")`,
gated behind `available` (a live reading, not a declared capability —
the same category `is_on`/`current_temperature` already fall into,
unlike `operation_list`/`min_temp`/`max_temp`).

## 5. Write model addition

`set_water_heater_state` gains one new keyword-only parameter:
`away_mode: bool | None = None`, validated via a new
`_validate_away_mode` (mirrors `_validate_on` verbatim — a distinct
helper per field, even with an identical body, is this module's own
established convention: `_validate_operation_mode`/`_validate_on`
already are two separate functions so that a validation error names
the field that was actually wrong). The empty-mutation check widens to
all four keywords. `_translate_state_home_assistant`/`_translate_state_
mqtt` gain the same keyword-only parameter (defaulting to `None`) —
every existing call site and every existing direct-call unit test
assertion (which pass `on=`/`operation_mode=`/`temperature=`
explicitly) is unaffected.

## 6. REST / agent tools

No new route, no new agent tool — `POST /appliances/water-heaters/{id}/
state` and the existing `set_water_heater_state` agent tool both gain
the one new optional field, identical to how Thermostat Fan Mode and
Media Player Shuffle/Repeat/Sound Mode each extended their own merged
mutation without a new route or tool.

## 7. Permission / security

Unchanged. Same `core:water_heaters` principal, same `smart_home`
scope, same ungated-reads/gated-mutation shape as every other water
heater command.

## 8. Test strategy

Extends `test_m12_water_heater_service.py`, `test_m12_water_heaters_
route.py`, `test_m12_water_heater_tools.py` — mirroring `on`'s own
existing test shape for `away_mode` (denied-by-default, non-boolean
rejection, standalone mutation, combined-mutation ordering). Combined-
mutation ordering is pinned by a direct translator unit test asserting
all four calls in the declared order when all four are supplied.

## 9. Non-goals

Every other item the original slice's own §16 deferred table still
names (dual setpoint, scheduling, energy optimization, predictive/AI
control, multi-device orchestration, scenes, leak detection, advanced
heating profiles/multi-zone control) remains deferred, unchanged. No
connector, `DEVICE_TYPES`, or `CONNECTOR_TYPES` change.

## 10. Acceptance criteria

- `water_heater.set_away_mode` name and its `away_mode` parameter, plus
  the `away_mode` read attribute name, externally verified this session
  (§1), not recalled.
- `away_mode` validated as a plain boolean via a dedicated
  `_validate_away_mode`, no device-list check (no such list exists for
  this attribute).
- `away_mode` read gated behind `available`, like `is_on`/
  `current_temperature`.
- Every existing `set_water_heater_state`/translator call site and
  direct-call unit test is behaviorally unchanged.
- Zero connector, `DEVICE_TYPES`, or `CONNECTOR_TYPES` changes.
- No new REST route; no new agent tool.
