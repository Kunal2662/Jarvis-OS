# M12 Appliance Control — Vacuum Clean Spot + Locate — Logic Contract

Status: **Implemented this session** (Task Group GG). Closes part of
the item the Vacuum + Humidifier Core Slice's own Logic Contract named
and deferred (§18): "Spot cleaning, locate, room targeting, maps, live
map streaming, path planning — No repository infrastructure of any
kind exists for spatial/map data; inventing it here would be new
architecture, not a slice of existing capability." §1 below finds that
reasoning **does not actually apply** to spot cleaning or locate —
only to room targeting, maps, live map streaming, and path planning,
which remain deferred, unchanged. "Fan speed, cleaning mode" (the
other §18 line naming "cleaning mode") was already closed by the
Vacuum Fan Speed slice (Task Group AA); this session confirms Home
Assistant has no separate "cleaning mode" concept beyond `fan_speed` —
see §1.

## 1. External verification (this session, via live web search — Home
Assistant's own documentation, not recalled from training data)

- **`vacuum.clean_spot`** — performs a spot cleaning at the vacuum's
  current location. **No parameters** beyond the entity target — the
  robot itself decides where "the current spot" is; no coordinate, no
  map, no spatial data of any kind is passed or required.
  [Clean spot — Home Assistant](https://www.home-assistant.io/actions/vacuum.clean_spot/)
- **`vacuum.locate`** — plays a sound or flashes lights to help find
  the vacuum. **No parameters** beyond the entity target.
  [Vacuum — Home Assistant](https://www.home-assistant.io/integrations/vacuum/)
- **No separate "cleaning mode" HA feature exists.** HA's
  `VacuumEntityFeature` set is `turn_on`/`turn_off`/`stop`/`pause`/
  `return_home`/`status`/`locate`/`clean_spot`/`fan_speed`/
  `send_command`/`start`/`map` — fan speed *is* the graduated/enum
  control the original slice's §18 entry meant; there is no distinct
  wire concept "cleaning mode" sitting alongside it. `map` (spatial
  data) remains genuinely deferred, unchanged, along with room
  targeting/live map streaming/path planning, none of which this slice
  touches.

**Correction to the original slice's own reasoning**: `clean_spot`/
`locate` were grouped with room targeting/maps/path planning under one
"no spatial infrastructure exists" justification, but neither actually
carries or requires spatial data — both are zero-payload commands,
structurally identical to `start`/`stop`/`pause`/`return_to_base`
(already shipped). This slice closes that specific misclassification;
it does not relitigate genuinely spatial items (maps, room targeting,
path planning), which remain out of scope for the stated reason.

## 2. Existing evidence (re-confirmed this session)

`VacuumHumidifierService._translate_vacuum_home_assistant`/
`_translate_vacuum_mqtt` and `_send_vacuum` already prove the exact
shape this slice needs — `VacuumCommand` is a `StrEnum` of independent
commands, each translated identically by both connectors through the
existing generic dispatcher. Zero connector changes — both connectors'
`send_command` already accept an arbitrary (here, empty) payload dict
generically.

## 3. Architecture decision

**Add `CLEAN_SPOT`/`LOCATE` as two more zero-payload `VacuumCommand`
members, plus two new public methods (`clean_spot`, `locate`) — not a
new service, no changes to `set_fan_speed`'s value-bearing shape.**
Both commands need no `fan_speed`-style keyword-argument threading:
they fall through the existing "no value → `{}` payload" branch every
zero-payload command (`start`/`stop`/`pause`/`return_to_base`) already
uses, so `_translate_vacuum_home_assistant`/`_translate_vacuum_mqtt`/
`_send_vacuum` need **no signature changes at all** — this is the one
structural difference from every prior slice this session, all of
which added a value-bearing keyword.

## 4. Read model addition

**None.** `clean_spot`/`locate` are pure actions with no corresponding
device-reported attribute (HA does not report "is currently locating"
or "last spot-cleaned at" anywhere) — no field is added to
`_vacuum_payload`.

## 5. Write model addition

- `clean_spot(device_id)` — sends `clean_spot` with no payload,
  mirroring `start`/`stop`/`pause`/`return_to_base` exactly (permission
  check, then `_send_vacuum`).
- `locate(device_id)` — sends `locate` with no payload, identical
  shape.

## 6. REST / agent tools

- `POST /appliances/vacuums/{device_id}/clean_spot`
- `POST /appliances/vacuums/{device_id}/locate`
- Two new agent tools, `vacuum_clean_spot`/`vacuum_locate`, mirroring
  `vacuum_start`'s own docstring and confirm-before-calling framing.
  Neither is added to `AgentSettings.confirm_required_tools` — both
  carry the same non-safety-relevant weight the four existing vacuum
  transport commands already carry (physical movement, but confined
  and low-consequence, Logic Contract §19's own risk tier).

## 7. Permission / security

Unchanged. Same `core:vacuum_humidifier` principal, same `smart_home`
scope, same ungated-reads/gated-mutation shape as every other vacuum
command.

## 8. Test strategy

Extends `test_m12_vacuum_humidifier_service.py`, `test_m12_vacuums_
humidifiers_route.py`, `test_m12_vacuum_humidifier_tools.py` —
mirroring the existing parametrized `start`/`stop`/`pause`/
`return_to_base` test shape exactly (zero-payload HA call,
failure-surfaced-not-raised, no-recorded-connector, denied-without-
grant), extended to include `clean_spot`/`locate` in the same
parametrize lists rather than duplicating new standalone tests where
the existing parametrized tests already generalize.

## 9. Non-goals

Room targeting, maps, live map streaming, and path planning remain
genuinely deferred — no spatial/map data infrastructure exists in this
repository, and none is added here. Vendor-specific advanced modes, AI
optimization, and scheduling/automation remain deferred, unchanged. No
connector, `DEVICE_TYPES`, or `CONNECTOR_TYPES` change.

## 10. Acceptance criteria

- `vacuum.clean_spot`/`vacuum.locate` names, and the finding that
  neither carries or requires spatial data, externally verified this
  session (§1), not recalled.
- Both commands are zero-payload, added as `VacuumCommand` members
  with no signature changes to the existing translators/`_send_vacuum`.
- No read-model field added for either (no corresponding device
  attribute exists).
- Zero connector, `DEVICE_TYPES`, or `CONNECTOR_TYPES` changes.
- Two new REST routes, two new agent tools, matching exactly the two
  new methods; neither tool added to `confirm_required_tools`.
