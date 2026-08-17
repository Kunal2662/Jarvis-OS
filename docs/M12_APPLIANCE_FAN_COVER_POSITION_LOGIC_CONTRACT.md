# M12 Task Group T — Appliance Control: Fan Percentage + Cover Position — Logic Contract

**Status: Phase 1 — Logic Contract only. No implementation.** Written
after fresh, complete reads of `appliance_service.py`,
`smart_lighting_service.py` (the cited precedent), both connectors'
`send_command` implementations, `routes/appliances.py`,
`agents/tools/appliance_tools.py`, and live external verification
against Home Assistant's own current developer documentation for
`fan.set_percentage` and `cover.set_cover_position`.

## 1. Purpose

Close the one gap `appliance_service.py`'s own module docstring names
explicitly: add fan speed percentage and cover position control to
the already-shipped Core Appliance Slice (Task Group G), without
touching connectors, without creating a new service, and without
regressing the existing on/off/open/close behavior.

## 2. Current repository evidence

Read in full (not excerpted):

- **`src/jarvis/services/appliance_service.py`** — `FanCommand`
  (`TURN_ON`/`TURN_OFF`), `CoverCommand` (`OPEN`/`CLOSE`), both
  translators are bare no-op passthroughs (`return command.value, {}`
  unconditionally — no payload ever constructed today).
  `_fan_payload`/`_cover_payload` expose `on`/`state` respectively,
  plus shared identity fields and `available` — **neither reads
  `raw.attributes` at all today**; only `raw.status`.
- **`src/jarvis/services/smart_lighting_service.py`** — the cited
  precedent. `_translate_home_assistant`/`_translate_mqtt` take
  keyword attributes (`on`, `brightness`, `color_temp_kelvin`,
  `color`) and merge whichever are set into **one** wire call, because
  HA's own `light.turn_on` service is the *only* way to set brightness
  — there is no separate `light.set_brightness` service. `_light_payload`
  reads `attributes.get("brightness")` etc. directly, no transformation.
  `_validate_brightness`/`_validate_color_temp_kelvin`/`_validate_color`
  each reject `bool` explicitly (a real Python gotcha: `bool` is an
  `int` subclass) before range-checking.
- **`src/jarvis/core/connectivity/connectors/home_assistant.py`**
  (`send_command`, lines 230-255) — `body = {"entity_id": external_id,
  **payload}`, POSTed to `/api/services/{domain}/{command}`. Fully
  generic; no payload-key whitelist of any kind.
- **`src/jarvis/core/connectivity/connectors/mqtt.py`**
  (`send_command`, lines 460-483) — `build_command_envelope(external_id,
  command, payload)`, published as-is. Also fully generic.
- **`src/jarvis/infrastructure/api/routes/appliances.py`** — the
  **verb-endpoint** convention: `POST .../fans/{id}/on`, `.../off`,
  `.../covers/{id}/open`, `.../close`. Its own docstring: *"Two
  sibling resource collections, not one generic
  `/appliances/{id}/command` endpoint... a fan and a cover have
  genuinely different command vocabularies."* No request body on any
  existing appliance mutation route.
- **`src/jarvis/infrastructure/api/routes/smart_lighting.py`** — the
  one existing body-carrying M12 mutation route precedent:
  `SetLightStateRequest(BaseModel)` with plain optional typed fields,
  no Pydantic-level range constraints — range validation happens in
  the service layer (`_validate_brightness` etc.), consistently with
  every other M12 module's error-semantics convention (`ServiceError`
  → 400, not a 422 Pydantic validation error).
- **`src/jarvis/agents/tools/appliance_tools.py`** — 8 existing tools,
  none in `confirm_required_tools` (module docstring: *"neither a fan
  nor a cover is physically safety-relevant the way a lock is"*).
- **`src/jarvis/services/water_heater_service.py`** (and
  `media_player_service.py`, `thermostat_service.py`,
  `vacuum_humidifier_service.py`) — each independently defines its own
  private `_coerce_float(value) -> float | None`, rejecting `None`/
  `bool`, returning `None` on any parse failure or non-finite result.
  No shared/importable version exists.

## 3. Existing architecture (unchanged, extended in place)

```
ApplianceService
    -> SmartHomeService (require_device / list_devices)
    -> ConnectivityService (read_raw_state / send_command)
```

This contract adds two new command values, two new service methods,
two new REST routes, and two new agent tools — all inside the
existing `ApplianceService`/`appliances.py`/`appliance_tools.py` trio.
No new class, no new file beyond this contract, no connector change,
no `ApplianceService` split, no generic capability framework.

## 4. Fan capability — resolved

- **Read model**: `percentage: int | None` added to `_fan_payload`.
  `_fan_payload` must start reading `raw.attributes` (it does not
  today) — `attributes.get("percentage")`, coerced by a new local
  `_coerce_int` (mirroring the four existing `_coerce_float`
  implementations' exact defensive shape, §9).
- **Write**: a new, **separate** service method `set_fan_percentage
  (device_id, percentage)` — not an optional parameter on `fan_on`
  (§6 explains why).
- **0 is valid input, not a special case.** Externally verified:
  HA's own `fan.set_percentage` documentation states *"0 is allowed
  by the selector, but some devices may treat that as off or ignore
  it"* — device-dependent, not something this module resolves.
  `set_fan_percentage(device_id, 0)` sends a bare `set_percentage`
  command with `percentage: 0`; it never substitutes or additionally
  sends `turn_off`.
- **`turn_on`/`turn_off` are completely unchanged** — zero
  modification to `FanCommand.TURN_ON`/`TURN_OFF`, `fan_on`,
  `fan_off`, or their translation branches (§15's compatibility
  guarantee).
- **`set_fan_percentage` never implies `turn_on`.** This module does
  not fabricate a second wire command the caller didn't request — if
  a real device requires an explicit on-state first, that is between
  Home Assistant and the device, not something this service papers
  over (mirrors this codebase's consistent "never invent behavior the
  wire protocol doesn't guarantee" discipline, e.g. Siren's own
  refusal to invent tone/duration defaults).
- **Unsupported devices** (no `FanEntityFeature.SET_SPEED`, externally
  verified as the gating flag): this codebase has no way to
  pre-inspect `supported_features`, and no prior M12 module
  pre-validates capability support before sending a command (Siren,
  Water Heater alike just send and report `CommandResult` honestly).
  Same here: the command is sent; `success`/`detail` come back from
  the connector verbatim. On **read**, an unsupported fan simply never
  reports a `percentage` attribute, so `_coerce_int` naturally yields
  `None` — no fabrication needed.

## 5. Cover capability — resolved

- **Read model**: `position: int | None` added to `_cover_payload`,
  reading `attributes.get("current_cover_position")` — **not**
  `"position"` (§8's naming mismatch, verified externally, is the
  single most important fact in this contract to get right).
  `_cover_payload` must also start reading `raw.attributes`.
- **Write**: a new, separate service method `set_cover_position
  (device_id, position)`.
- **Range and meaning, externally verified**: `position` is an
  integer 0-100; **0 = fully closed, 100 = fully open** (HA's own
  `cover.set_cover_position` documentation, verbatim: *"The target
  position as a percentage, from 0 (closed) to 100 (open)"*). No
  special-cased behavior at either boundary beyond what those values
  already mean.
- **`open_cover`/`close_cover` are completely unchanged** — same
  compatibility guarantee as fans.
- **`set_cover_position` is HA's own separate, real service** —
  `cover.set_cover_position` is not a parameter of `cover.open_cover`;
  it stands alone in HA's actual service vocabulary, gated by its own
  `CoverEntityFeature.SET_POSITION` flag. Same "send honestly, report
  honestly" handling for unsupported covers as §4.

## 6. Exact command model — resolved, and why Lighting is only partly applicable

**Decision: `FanCommand` gains `SET_PERCENTAGE = "set_percentage"`;
`CoverCommand` gains `SET_POSITION = "set_cover_position"`** — both
literal HA service names, matching this module's own existing
`OPEN = "open_cover"`/`CLOSE = "close_cover"` convention of using HA's
real names as enum values.

**What is borrowed from `SmartLightingService`, precisely**: the
*translator function shape* — `(command) -> (wire_command,
payload: dict)` — extended to accept an optional carried value.

**What is deliberately NOT borrowed**: Lighting's "merge every
attribute into one `turn_on` call" *behavior*. That behavior exists
in Lighting only because HA's real API leaves it no choice — there is
no `light.set_brightness` service, brightness can *only* be set via a
`turn_on` call carrying `brightness_pct`. Fan and Cover are the
opposite: HA defines `fan.set_percentage`/`cover.set_cover_position`
as their own, genuinely separate top-level services, independent of
`turn_on`/`open_cover`. Sending a bare, standalone `set_percentage`/
`set_cover_position` command is not a shortcut this module is taking —
it is HA's own actual service boundary, followed exactly. Blindly
copying Lighting's merge-into-turn_on behavior here would send a
command HA does not define and no connector implements.

```python
def _translate_home_assistant(
    command: FanCommand | CoverCommand, *, value: int | None = None
) -> tuple[str, dict[str, Any]]:
    if value is not None:
        key = "percentage" if command is FanCommand.SET_PERCENTAGE else "position"
        return command.value, {key: value}
    return command.value, {}
```
`_translate_mqtt` gains the identical `value` parameter, same key
names (`percentage`/`position`) — no HA-specific unit conversion is
needed at all (unlike Lighting's `brightness_pct` 0-100 vs native
0-255 split): **HA's own `percentage`/`position` parameters are
already externally verified as 0-100 integers**, exactly matching
this module's own natural normalized range. Zero scale conversion.

**No new `_TRANSLATORS` dict entry** — same two keys
(`"home_assistant"`, `"mqtt"`), same two functions, both gaining the
optional `value` parameter.

## 7. Read-model changes

| Payload | New field | Source | Type |
|---|---|---|---|
| `_fan_payload` | `percentage` | `raw.attributes.get("percentage")` | `int \| None` |
| `_cover_payload` | `position` | `raw.attributes.get("current_cover_position")` | `int \| None` |

Both via a new local `_coerce_int(value) -> int | None`, mirroring
the four existing `_coerce_float` implementations' exact shape
(reject `None`/`bool` explicitly, `try: int(value) except (TypeError,
ValueError): return None`) — a **new**, small helper local to
`appliance_service.py`, not a shared import (matches the established
per-module-duplication pattern every other numeric-coercing M12
service already uses; no cross-module utility is introduced).
`list_fans`/`list_covers` remain DB-only, unchanged — neither new
field appears there (matches every prior M12 module's list/detail
asymmetry: `percentage`/`position` are live-only fields, present only
via `get_fan_state`/`get_cover_state`).

## 8. Home Assistant translation — externally verified

**Fan** (`https://www.home-assistant.io/actions/fan.set_percentage/`,
`https://developers.home-assistant.io/docs/core/entity/fan/`):
- Service: `fan.set_percentage`. Parameter: **`percentage`** (integer,
  required, 0-100). Gated by `FanEntityFeature.SET_SPEED`.
- **Read attribute: `percentage`** (same name as the write parameter)
  — per HA's own entity docs: *"The current speed percentage. Must be
  a value between 0 (off) and 100."*

**Cover**
(`https://www.home-assistant.io/actions/cover.set_cover_position/`,
`https://developers.home-assistant.io/docs/core/entity/cover/`):
- Service: `cover.set_cover_position`. Parameter: **`position`**
  (integer, required, 0-100; 0=closed, 100=open). Gated by
  `CoverEntityFeature.SET_POSITION`.
- **Read attribute: `current_cover_position`** — **verified to be a
  different name from the write parameter** (`position`). Confirmed
  directly against Home Assistant's own developer entity
  documentation, not assumed from the write-side name.

`HomeAssistantConnector.send_command` requires no change: `body =
{"entity_id": ..., **payload}` already merges an arbitrary payload
dict generically (§2), exactly as it already does for Lighting's
`brightness_pct`.

## 9. MQTT translation — resolved

No standard MQTT equivalent for `set_percentage`/`set_cover_position`
exists in any spec this repository follows — `mqtt.py` has no
`percentage`/`position` handling of any kind today, confirmed by
direct source read. Per this module's own established precedent
(`_translate_mqtt`'s own docstring: *"deliberately mirroring HA's own
service names for cross-connector predictability"*), this contract
resolves MQTT the same way Task Group G originally did for
`turn_on`/`open_cover`: **this module defines its own MQTT vocabulary**
— wire command `set_percentage`/`set_cover_position` (identical
strings to the HA service names), payload `{"percentage": N}`/
`{"position": N}` (identical key names, no scale conversion, same
reasoning as §6). `MqttConnector.send_command`/
`build_command_envelope` already accept an arbitrary payload dict
generically (§2) — **zero connector change**. This is Option 2 from
the Phase 1 brief ("existing MQTT payload conventions support the
same abstraction") — not Option 3 (exclude MQTT) or Option 4
(connector change): the connector's own generic envelope mechanism
already supports it without modification, the same way it already
supports Lighting's, Siren's, and every prior module's own
JARVIS-native MQTT vocabulary.

## 10. REST API — resolved

**Decision: Option B — two new dedicated verb endpoints**, not
optional fields merged into the existing `/on`/`/open` routes.
Evaluated against this module's own actual REST convention (§2), not
against Lighting's: `routes/appliances.py`'s own docstring already
states its design principle — *"genuinely different command
vocabularies... not one generic command endpoint"* — and `/on`/`/off`/
`/open`/`/close` today accept **no request body at all**. Retrofitting
an optional body onto them would contradict this router's own stated
design and awkwardly conflate "turn on" with "set speed" at the API
surface, even though the two are cleanly separate at the HA-service
level (§6). Two new sibling verb endpoints match the file's own
established pattern exactly.

| Endpoint | Method | Body | Response |
|---|---|---|---|
| `/api/v1/appliances/fans/{device_id}/set_percentage` | `POST` | `{"percentage": int}` | `Envelope[{device_id, success, detail}]` |
| `/api/v1/appliances/covers/{device_id}/set_position` | `POST` | `{"position": int}` | `Envelope[{device_id, success, detail}]` |

Request models, matching `SetLightStateRequest`'s own plain-field
style (no Pydantic-level range constraint — validation happens in the
service layer, consistent with every M12 module's `ServiceError` → 400
convention, not a 422):

```python
class SetFanPercentageRequest(BaseModel):
    percentage: int

class SetCoverPositionRequest(BaseModel):
    position: int
```

**Error semantics**, identical to every existing appliance mutation:
`ServiceError` (out-of-range value, wrong device type/domain, no
connector, no translation, permission denied) → `_bad_request` → 400.
Unknown device → the same `ServiceError` from `require_device` → 400
(matching the existing mutation routes' own convention — `get_fan`/
`get_cover` alone map unknown-device to 404; mutations map every
`ServiceError` to 400, unchanged). No new 404 case is introduced.
`meta={"success": result["success"]}`, matching every other appliance
mutation route exactly.

## 11. Agent tools — resolved

**Two new tools**, not optional arguments added to `fan_on`/
`cover_open` (same reasoning as §10 — the tool surface should mirror
the REST surface's own verb-per-capability shape, and an agent tool
with an optional numeric argument tacked onto "turn on" is a worse,
more ambiguous natural-language surface than a dedicated
`set_fan_percentage(device_id, percentage)` tool):

| Tool | Purpose | Confirmation | Input | Failure |
|---|---|---|---|---|
| `set_fan_percentage` | Set one fan's speed 0-100 | None (§13) | `device_id: str, percentage: int` | Try/except-and-describe, matching every other tool in this file |
| `set_cover_position` | Set one cover's position 0-100 | None (§13) | `device_id: str, position: int` | Same |

Ten tools total after this task group (8 existing + 2 new). No
duplication of `fan_on`/`fan_off`/`cover_open`/`cover_close`.

## 12. Permission model — resolved

**No new principal.** Both new methods reuse the existing
`APPLIANCE_PRINCIPAL = "core:appliances"` / `SMART_HOME_SCOPE =
"smart_home"` grant `ApplianceService` already declares at
construction — the same grant `fan_on`/`fan_off`/`cover_open`/
`cover_close` already require. No architectural reason was found to
split percentage/position into their own principal: they are the same
physical devices, the same trust boundary, and Task Group G's own
"one principal per module" reasoning (mirroring
`SMART_SWITCH_PRINCIPAL`) applies identically here. Reads
(`get_fan_state`/`get_cover_state`, now including the new fields)
remain ungated, unchanged.

## 13. Confirmation model — resolved

**No `confirm_required_tools` entry for either new tool.** Evaluated
directly against this codebase's actual established precedent
(`unlock_device`, `trigger_panic_mode`, `trigger_vacation_mode`,
`turn_siren_on`) — every one of those gates a *physical, real-world,
one-directional-risk* consequence: an unlocked door, a whole-home
action, an audible alarm. Adjusting a fan's speed or a blind's
position by a numeric amount has none of that character: it is
strictly less consequential than the *already-ungated* `fan_on`/
`cover_open` themselves (this module's own existing docstring: *"no
tool here is added to `confirm_required_tools` -- neither a fan nor a
cover is physically safety-relevant the way a lock is"*). A command
that merely changes an already-uncontroversial device's degree is not
a new risk category the existing on/off toggle doesn't already carry.
Not inherited blindly — reasoned from the actual physical-effect/
reversibility/blast-radius axis every other confirmation decision in
this codebase uses.

## 14. Error semantics

| Condition | Behavior |
|---|---|
| Unknown device | `ServiceError` from `require_device` → REST 400 (matches existing mutation convention) |
| Wrong device type/domain (not a fan/not a cover) | `ServiceError` ("is not a fan"/"is not a cover"), unchanged from `_require_fan`/`_require_cover` |
| `percentage`/`position` out of range (not 0-100 int) | New validation, `ServiceError`, message names the field and value |
| `percentage`/`position` is a `bool` | Rejected explicitly (mirrors `_validate_brightness`'s own `isinstance(value, bool)` guard against the `bool`-is-`int`-subclass gotcha) |
| No recorded connector | `ServiceError`, unchanged existing message |
| No translation for connector type | `ServiceError`, unchanged existing message (dead code today — both `CONNECTOR_TYPES` entries are covered) |
| Permission not granted | `ServiceError` from `_require_permission`, unchanged |
| Device doesn't support percentage/position (feature flag off) | Command sent anyway; `success`/`detail` reported verbatim from `CommandResult` — no pre-validation, matching every prior M12 module (§4/§5) |
| Read: attribute absent (unsupported or never reported) | `percentage`/`position` is `None` — never fabricated |

## 15. Backward compatibility — binding guarantee

- `FanCommand.TURN_ON`/`TURN_OFF`, `CoverCommand.OPEN`/`CLOSE`: **byte-
  identical enum values, unchanged.**
- `fan_on`, `fan_off`, `cover_open`, `cover_close`: **zero line
  changes** to their bodies or the translation branches they hit
  (`value=None` is the default for both translators, so existing calls
  produce the exact same `(command.value, {})` result as today).
- `_fan_payload`/`_cover_payload`: existing keys (`on`, `state`,
  `available`, identity fields) **unchanged in name, type, and
  semantics** — `percentage`/`position` are pure additions.
- Existing REST routes (`/on`, `/off`, `/open`, `/close`,
  `GET .../fans`, `GET .../fans/{id}`, etc.): **zero changes.**
- Existing agent tools (`fan_on`, `fan_off`, `cover_open`,
  `cover_close`, `list_fans`, `get_fan_state`, `list_covers`,
  `get_cover_state`): **zero changes.**
- Existing tests (`test_m12_appliance_service.py`,
  `test_m12_appliances_route.py`, `test_m12_appliance_tools.py`) must
  pass unmodified against the Phase 2 implementation — regression, not
  extension, for every currently-passing test.

## 16. EventBus boundary

Not touched. No event publication or subscription anywhere in this
slice — `_send` remains the same `ConnectivityService.send_command`
chokepoint every M12 mutation already uses, which itself does not
publish device-command events (the pre-existing, unrelated,
already-documented gap).

## 17. Scheduler boundary

Not touched. No recurring/scheduled percentage or position changes.
Both new operations are synchronous, single-call, explicitly invoked.

## 18. Analytics/Memory/AI boundary

Not touched. No trend/history capture of percentage or position
values. `SmartHomeMemoryService` (Task Group S) already supports fan/
cover snapshots via its existing Tier-2 cascade over `get_fan_state`/
`get_cover_state` — those methods now simply return a richer payload
(the new `percentage`/`position` fields) automatically, with **zero
changes required to `smart_home_memory_service.py`**, since it already
persists whatever the owning service's `get_<category>_state` returns
verbatim. No AI-generated content anywhere in this slice.

## 19. Database/schema

**Zero changes**, verified rather than assumed: `percentage`/
`position` are live connector-read attributes only, never persisted
to `Device`/any table — exactly like `brightness`/`color_temp_kelvin`
already aren't. No migration, no new column.

## 20. Testing strategy (described for Phase 2, not created now)

**Fan**: existing on/off tests unchanged and re-run as regression;
percentage read (present/absent/malformed attribute value); percentage
write (valid value, boundary 0, boundary 100, value below 0 rejected,
value above 100 rejected, `bool` rejected); write when unavailable/no
connector; HA translation (`{"percentage": N}` sent to
`fan.set_percentage`); MQTT translation (`{"percentage": N}` sent as
`set_percentage`); connector failure (`CommandResult.success=False`
surfaces honestly); permission-denied.

**Cover**: existing open/close tests unchanged and re-run as
regression; position read (present via `current_cover_position`,
absent, malformed); position write (valid, boundary 0, boundary 100,
below 0 rejected, above 100 rejected, `bool` rejected); HA translation
(`{"position": N}` sent to `cover.set_cover_position`); MQTT
translation; connector failure; permission-denied.

**Regression**: full targeted re-run of `test_m12_appliance_service.py`,
`test_m12_appliances_route.py`, `test_m12_appliance_tools.py` plus the
M12 device-category-dependent suites from Task Groups I/J/K/L/S
(Thermostat/Vacuum+Humidifier/Media Player/Water Heater/Smart Home
Memory) — none of those touch `appliance_service.py`'s own fan/cover
domain, but Smart Home Memory's own Tier-2 cascade (Task Group S)
calls `get_fan_state`/`get_cover_state` directly, so its own snapshot
tests must be re-verified green against the richer payload shape.

**Architecture guards**: AST-based, docstring-stripped source
inspection (reusing this session's established `_code_without_docstrings`
helper) confirming no `EventBus`/`Scheduler`/`Analytics` reference
anywhere in the modified files.

## 21. Security/safety considerations

No new sensitive data: `percentage`/`position` are plain integers, no
different in sensitivity from `brightness` (already exposed ungated
today). No credential, token, or PIN-code handling of any kind is
introduced by this slice (contrast with the `alarm_control_panel`
candidate this same audit found needs its own dedicated treatment for
exactly this reason). No new physical-safety consideration beyond
what already-shipped, already-ungated `fan_on`/`cover_open` carry —
§13's confirmation analysis applies unchanged.

## 22. Deferred scope

Explicitly out of this task group, no placeholder code or schema for
any of the following:

| Item | Why deferred |
|---|---|
| Fan oscillation, fan presets/speed-list modes | Not named in the approved scope; a distinct HA feature set (`FanEntityFeature.OSCILLATE`/`PRESET_MODE`) this task group does not evaluate |
| Cover tilt (`current_tilt_position`, `set_cover_tilt_position`) | A separate HA feature flag (`CoverEntityFeature.SET_TILT_POSITION`), not evaluated this pass |
| Cover `stop_cover` | A third existing HA service this slice does not add; binary open/close plus position is the approved scope |
| Climate fan-mode/swing/humidity (Thermostat's own remaining gaps) | A different service (`ThermostatService`), out of this task group's named scope |
| Scheduling/automation of percentage or position | Needs M7 Scheduler, unshipped |
| Historical percentage/position tracking, analytics/trends | M20A's job, unstarted; Smart Home Memory already captures point-in-time snapshots (§18) but performs no aggregation |
| Notifications on percentage/position change | No notification transport exists |
| Frontend implementation | Frozen this phase (§23) |

## 23. Acceptance criteria

- `FanCommand.TURN_ON`/`TURN_OFF` and `CoverCommand.OPEN`/`CLOSE`
  unchanged; every existing test in the three appliance test files
  passes unmodified (regression, §15).
- `_fan_payload`/`_cover_payload` gain exactly `percentage`/`position`
  — no other new field.
- `set_fan_percentage`/`set_cover_position` each send exactly one wire
  command, never an implicit accompanying `turn_on`/`open_cover`.
- Cover position read uses `current_cover_position`; cover position
  write uses `position` — verified distinct, never conflated.
- No connector file (`home_assistant.py`, `mqtt.py`) is modified.
- No new `PermissionModel` principal, no new scope.
- No `confirm_required_tools` entry added.
- No database/schema change.
- No `EventBus`/`Scheduler`/`AnalyticsService` reference in the new
  code (AST-guard-tested).
- No frontend source touched.
- Full M12 regression, M11+M12 regression, and full backend
  regression all green before any commit (Phase 2 requirement).
- Clean git state (this contract as the only untracked file) before
  Phase 2 implementation begins.

## 24. Implementation file list (Phase 2 — not created now)

- `src/jarvis/services/appliance_service.py` (modify)
- `src/jarvis/infrastructure/api/routes/appliances.py` (modify)
- `src/jarvis/agents/tools/appliance_tools.py` (modify)
- `tests/unit/test_m12_appliance_service.py` (extend)
- `tests/unit/test_m12_appliances_route.py` (extend)
- `tests/unit/test_m12_appliance_tools.py` (extend)
- No DI container change is anticipated — `ApplianceService`'s
  constructor and its DI wiring are unchanged; verify this holds
  during Phase 2 rather than assuming it here.

## 25. Phase 2 implementation boundary

**Not started.** This document is Logic Contract only. Implementation,
tests, quality gates, roadmap/CHANGELOG updates, commits, and push all
remain Phase 2, pending explicit approval.
