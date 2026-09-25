# M12 Appliance Control — Humidifier Mode Control — Logic Contract

Status: **Implemented this session** (Task Group FF). Closes one item
the Vacuum + Humidifier Core Slice's own Logic Contract explicitly
named and deferred (§8/§18): "Humidifier mode *control* — explicit
decision: READ-only, not a write surface in this MVP... A future,
separately-scoped slice can add mode control by following Thermostat's
own open-vocabulary template if real demand emerges." Presets, water-
level automation, and everything else in that table remain separately
deferred, unchanged.

## 1. External verification (this session, via live web search — Home
Assistant's own documentation, not recalled from training data)

This closes two items the original contract flagged **(UNVERIFIED)**:

- **`humidifier.set_mode`** — sets the mode for a humidifier. One
  parameter, **`mode`**, a string whose valid values are device-
  reported (e.g. `"normal"`, `"eco"`, `"away"`, `"boost"`, `"sleep"`,
  `"auto"`, `"baby"`) — platform-dependent, no fixed HA-wide enum, the
  identical shape `hvac_mode`/`fan_mode`/`swing_mode`/`preset_mode`
  already have on Thermostat.
  [Set humidifier mode — Home Assistant](https://www.home-assistant.io/actions/humidifier.set_mode/)
- **Read attributes: `mode` (current) / `available_modes` (declared
  capability list)** — `available_modes` is the real capability-list
  attribute name (requires `SUPPORT_MODES`); confirms the original
  contract's `mode` read was correct, and supplies the capability-list
  name the original contract never recorded (it excluded mode from the
  mutation surface entirely, so no capability list was needed then).
  [Humidifier — Home Assistant](https://www.home-assistant.io/integrations/humidifier/)

## 2. Existing evidence (re-confirmed this session)

`VacuumHumidifierService._translate_humidifier_home_assistant`/
`_translate_humidifier_mqtt` already prove the exact shape this slice
needs: HA sends one independent service call per attribute (`turn_on`/
`turn_off`/`set_humidity`), MQTT merges everything into one `set_state`
call. `ThermostatService`'s own `_validate_mode`/`_validate_against_
device`-shaped template (device-list validated, permissive when
absent) is the one this slice follows, the same template the original
contract's own §8 pointed to. Zero connector changes — both
connectors' `send_command` already accept an arbitrary payload dict
generically.

## 3. Architecture decision

**Add `mode` as a third optional keyword on the existing
`set_humidifier_state`, not a new method.** Matches this module's own
established merged-mutation shape (`on`/`target_humidity` already
combine into one call); `mode` becomes a third attribute of the same
one user intent.

**New validator, new device-list-check — but reusing the identical
template, not inventing a new one.** `_validate_mode` (non-empty
string) and `_check_mode` (device-list check against `available_modes`,
permissive when absent) are added locally to this module, mirroring
`MediaPlayerService._validate_source`/`_check_source` and
`ThermostatService._validate_mode`/`_validate_against_device` verbatim
in shape. No cross-module import — every M12 module keeps its own copy
of this shape, the established convention (`_domain_for` is already
duplicated per module the same way).

**Call order**: on/off first, then target_humidity, then mode —
appended last, fixed for determinism rather than meaningful (no
evidence ties mode to what the other two mean), extending the existing
`_translate_humidifier_home_assistant`'s documented on-off-first
convention.

## 4. Read model addition

```python
payload["available_modes"] = []
```

Added to `_humidifier_payload`. `mode` is **already read** by the
original slice, and (like `min_humidity`/`max_humidity`) already
survives unavailability rather than being gated behind `available` —
unchanged here. This slice adds only the `available_modes`
capability-list field, following the identical "survives
unavailability" rule, via a new local `_coerce_mode_list` helper
(mirrors `MediaPlayerService._coerce_source_list` verbatim — case
preserved, not lowercased, since humidifier mode labels are often
human-facing).

## 5. Write model addition

`set_humidifier_state` gains one new keyword-only parameter:
`mode: str | None = None`, validated via a new `_validate_mode`
(non-empty string), then checked via a new `_check_mode` against the
device's own reported `available_modes` only when non-empty. The
empty-mutation check widens to all three keywords.
`_translate_humidifier_home_assistant`/`_translate_humidifier_mqtt`
gain the same keyword-only parameter (defaulting to `None`) — every
existing call site and every existing direct-call unit test assertion
(which pass `on=`/`target_humidity=` explicitly) is unaffected.

## 6. REST / agent tools

No new route, no new agent tool — `POST /appliances/humidifiers/{id}/
state` and the existing `set_humidifier_state` agent tool both gain the
one new optional field, identical to how every prior merged-mutation
extension this pass (Fan Mode, Swing Mode, Preset Mode, Shuffle/
Repeat/Sound Mode, Away/Vacation Mode) added its keyword without a new
route or tool. The `set_humidifier_state` tool's docstring is updated
to say mode is now controllable — the original slice's own docstring
explicitly said "Mode cannot be changed through this tool -- it is
read-only", which this slice supersedes.

## 7. Permission / security

Unchanged. Same `core:vacuum_humidifier` principal, same `smart_home`
scope, same ungated-reads/gated-mutation shape as every other
humidifier command.

## 8. Test strategy

Extends `test_m12_vacuum_humidifier_service.py`,
`test_m12_vacuums_humidifiers_route.py`,
`test_m12_vacuum_humidifier_tools.py` — mirroring `source`'s/`fan_mode`'s
own existing test shape for humidifier `mode` (denied-by-default,
empty-string rejection, device-list validation, permissive-when-no-
list, standalone mutation, combined-mutation ordering extended to all
three, read gated behind `available` (unchanged), capability list
survives unavailability). Combined-mutation ordering is pinned by a
direct translator unit test asserting all three calls in the declared
order when all three are supplied. The existing pinned
`test_humidifier_mode_not_in_mutation_signature` test (which asserted
`mode` was absent from the mutation surface) is updated/removed to
reflect the new, intentional inclusion.

## 9. Non-goals

Presets, water-level automation, environmental/predictive
optimization, and multi-device orchestration all remain deferred,
unchanged. No connector, `DEVICE_TYPES`, or `CONNECTOR_TYPES` change.

## 10. Acceptance criteria

- `humidifier.set_mode` name and its `mode` parameter, plus the
  `available_modes` attribute name, externally verified this session
  (§1) — the original contract's two `(UNVERIFIED)` markers on this
  area are resolved.
- `mode` validated as a non-empty string, then checked against the
  device's own reported `available_modes` only when non-empty — never
  an invented enum.
- `available_modes` read survives unavailability like `hvac_modes`/
  `operation_list`; `mode`'s existing (already-unconditional) read is
  unchanged.
- Every existing `set_humidifier_state`/translator call site and
  direct-call unit test is behaviorally unchanged except the one
  pinned "mode not in signature" test, which is deliberately updated.
- Zero connector, `DEVICE_TYPES`, or `CONNECTOR_TYPES` changes.
- No new REST route; no new agent tool.
