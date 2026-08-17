# M12 Appliance Control — Water Heater Core Slice — Logic Contract

Status: **Draft — Logic Contract only.** Written per the `M12
POST-TASK-GROUP-K PHASE 0 AUDIT` and its approval (`APPROVED —
PROCEED WITH PHASE 1 ONLY`). **Not approved for implementation** — no
source, tests, DI, routes, tools, connector, permission, EventBus,
roadmap or CHANGELOG changes accompany this file. Base: the shipped
M12 Appliance Control Core Slice (`docs/
M12_APPLIANCE_CONTROL_LOGIC_CONTRACT.md`, commits `5550899`/`5ac30cf`),
Climate/Thermostat Slice (`docs/M12_APPLIANCE_CLIMATE_LOGIC_CONTRACT.md`,
commits `7db0528`/`db0d21f`), Vacuum + Humidifier Core Slice (`docs/
M12_APPLIANCE_VACUUM_HUMIDIFIER_LOGIC_CONTRACT.md`, commits
`3b5cb8e`/`2856bff`), and Media Player Core Slice (`docs/
M12_APPLIANCE_MEDIA_PLAYER_LOGIC_CONTRACT.md`, commits
`b6242ef`/`179962b`, HEAD at the time of writing).

**Legend.** Every claim about code that exists today is marked
**(EXISTING)** with a `file:line` citation, verified against the
current working tree this session (clean, HEAD `179962b`). Everything
marked **(PROPOSED)** does not exist yet. Anything checked against
Home Assistant's real public/developer documentation this session is
marked **(VERIFIED EXTERNALLY)**, cited by URL, never presented as
repository evidence. Anything this session found **no** repository or
external evidence for is marked **(UNVERIFIED — MUST VERIFY DURING
PHASE 2)**, naming exactly what must be checked before implementation.

## 1. Scope

**In scope**: one new dedicated service, `WaterHeaterService`, covering
read state + one merged attribute mutation (temperature / operation
mode / on-off) for `device_type="appliance"` devices whose domain is
`water_heater`.

**Explicitly not this slice's job** (§16 gives the full accounting):
away/vacation mode, scheduling, automation, energy optimization/
analytics, predictive/AI control, multi-device orchestration, scenes,
leak detection, safety alerting, notifications, advanced heating
profiles, multi-zone control, dual setpoints (`target_temperature_high`/
`target_temperature_low`), Smart Kitchen functionality, or any other
M12 module's scope.

## 2. Device model and identity — confirmed, not re-decided

**(EXISTING, re-verified this session)**: `water_heater` →
`device_type="appliance"` in both `_DEVICE_DOMAINS`
(`src/jarvis/core/connectivity/connectors/home_assistant.py:86`) and
`_HA_COMPONENT_DEVICE_TYPES` (`src/jarvis/core/connectivity/
connectors/mqtt.py:167`) — the identical Fan/Cover/Vacuum/Humidifier/
Media Player pattern, not Climate's own-`device_type` pattern. **No
new `DEVICE_TYPES` entry** (`domain/smart_home/models.py:53-55` is
unchanged: `{"light", "lock", "sensor", "camera", "switch",
"thermostat", "appliance", "other"}`). No new ORM model, no new table.

**Domain discrimination invariant**: every `WaterHeaterService`
operation requires **both**:
1. `device.device_type == "appliance"`
2. the device's resolved domain equals `"water_heater"`

**Resolution order**: `metadata["domain"]` first, falling back to
`metadata["component"]` when absent — the identical, now
three-times-shipped pattern `VacuumHumidifierService._domain_for`
established (`src/jarvis/services/vacuum_humidifier_service.py:175-184`)
and `MediaPlayerService._domain_for` reused verbatim
(`src/jarvis/services/media_player_service.py:169-178`). **This
fallback is implemented once, locally, inside `WaterHeaterService`'s
own domain-lookup helper — it does not touch `ApplianceService` or any
connector**, per explicit instruction. `ApplianceService`'s own
identical, still-unfixed gap (Fan/Cover) remains untouched and is not
this task group's job.

## 3. Architecture (PROPOSED)

```
WaterHeaterService
    ↓
ConnectivityService (read_raw_state / send_command)
    ↓
HomeAssistantConnector / MqttConnector
```

Dependencies: `SmartHomeService` + `ConnectivityService` +
`PermissionModel` only — the identical shape `ApplianceService`/
`ThermostatService`/`VacuumHumidifierService`/`MediaPlayerService` all
share.

**Explicitly prohibited**, per instruction and matching every prior
module's own acceptance criteria:
- **No `IDatabase`** — no scenes/persistence of its own.
- **No `EventBus`** — see §14.
- **No `MemoryService`** — see §15.
- **No Analytics dependency** — see §15.
- **No Scheduler dependency** — nothing in this slice is time- or
  trigger-driven.
- **No direct connector import** — all wire traffic goes through
  `ConnectivityService`'s two existing chokepoints, re-verified
  unchanged this session: `read_raw_state`
  (`src/jarvis/services/connectivity_service.py:195`), `send_command`
  (`:214`).
- **No frontend dependency** — see §10 of the Phase 0 audit; zero
  appliance-category-specific frontend code exists anywhere in
  `frontend/src`, re-confirmed this session.

**(EXISTING, re-confirmed this session)**: `ApplianceService`'s own
module docstring already states the rule this module follows: *"a
future appliance category (climate, media_player, vacuum,
water_heater, humidifier) gets its own Logic Contract and, per that
contract, likely its own service — not a new branch bolted onto this
one"* (`src/jarvis/services/appliance_service.py:19-20`).
`WaterHeaterService` is **deliberately not an `ApplianceService`
extension**, to be enforced by the same source-level negative test
every prior slice used (§17).

## 4. Normalized read model (PROPOSED)

```
{
  "id": str, "home_id": str, "room_id": str | None, "name": str,
  "status": str, "manufacturer": str, "model": str, "external_id": str | None,
  "available": bool,
  "state": str | None,               # open pass-through -- see §7
  "is_on": bool | None,               # derived from state -- see §7
  "current_temperature": float | None,
  "target_temperature": float | None,
  "operation_mode": str | None,       # see §6
  "operation_list": list[str],        # [] when unreported -- see §6
  "min_temp": float | None,
  "max_temp": float | None,
}
```

**Per-field behavior — missing / malformed / unavailable / null /
unsupported**, stated once here so no field's handling is ambiguous:

| Field | Source | Missing/malformed | When unavailable |
|---|---|---|---|
| `state` | entity status string | `None` if stripped result is empty | forced `None`, never the literal `"unavailable"`/`"offline"` string (§7) |
| `is_on` | derived from `state` | `None` if `state` isn't a recognizable on/off token | `None` (state itself is `None`) |
| `current_temperature` | `attributes.get("current_temperature")` | `None` if absent/non-numeric/NaN/±inf | `None` (live reading, gated on availability — §5) |
| `target_temperature` | `attributes.get("temperature")` | `None` if absent/non-numeric/NaN/±inf | `None` (live reading, gated on availability) |
| `operation_mode` | entity status string | `None` if unavailable/empty | forced `None` when unavailable (§6) |
| `operation_list` | `attributes.get("operation_list")` | `[]` if absent/not a list/entries not strings | **survives unavailability** — a declared capability, not a live reading (mirrors `hvac_modes`/`source_list`) |
| `min_temp` / `max_temp` | `attributes.get("min_temp"/"max_temp")` | `None` if absent/non-numeric/NaN/±inf | **survive unavailability** — declared capability (mirrors Thermostat's identical rule, `thermostat_service.py:215-220`) |

**No fabricated values anywhere**: every field above defaults to
`None`/`[]` when unreported — never a guessed default, never `0.0` for
an unparseable number, matching every prior M12 module's discipline.
**No unit conversion**: temperatures pass through in whatever unit the
device/connector reports, identical to `ThermostatService`'s own
documented choice (`agents/tools/thermostat_tools.py:77`: *"Temperature
is in the device's own unit — no conversion is performed"*) — this
module makes the identical choice for the identical reason (no
JARVIS-invented conversion where none is needed to operate correctly).

## 5. Temperature semantics

**(UNVERIFIED — MUST VERIFY DURING PHASE 2, repository evidence)**: a
repo-wide search this session (`grep -rn "water_heater" src/ tests/`)
found `water_heater` referenced only in the two connector domain-
mapping dicts (§2) and in `appliance_service.py`'s/
`vacuum_humidifier_service.py`'s own forward-looking module docstrings
— **zero** water-heater-specific service/attribute code exists
anywhere in this repository. `docs/M12_APPLIANCE_CONTROL_LOGIC_
CONTRACT.md:355` (the Task Group G contract) already flagged
`set_temperature`/`set_operation_mode` as the expected vocabulary, but
that line is itself a prior contract's own forward-looking note, not
executable repository evidence, and is cited here as context only, not
as proof.

**(VERIFIED EXTERNALLY, `developers.home-assistant.io/docs/core/
entity/water-heater/`, fetched this session)**: `WaterHeaterEntity`
exposes `current_temperature: float | None`, `target_temperature:
float | None`, `target_temperature_high: float | None`,
`target_temperature_low: float | None`, `target_temperature_step:
float | None`, `temperature_unit: str` (Celsius/Fahrenheit/Kelvin,
platform-defined, no `NotImplementedError` default), `min_temp: float`
(base-class default **110°F**), `max_temp: float` (base-class default
**140°F**). The **`TARGET_TEMPERATURE`** `WaterHeaterEntityFeature`
flag gates whether temperature is settable at all — not every water
heater integration supports it.

**Decision: single `target_temperature` only — no dual setpoint.**
`target_temperature_high`/`target_temperature_low` exist in HA's real
entity model (heat-pump-style water heaters with a range) but are
**explicitly deferred** (§16) — mirrors Thermostat's own MVP scope
decision to support one setpoint, not HVAC's dual-setpoint mode, for
the identical reason: a second setpoint is a materially different
mutation shape this contract does not attempt to design blind.

**Validation rules (PROPOSED)**, mirroring `ThermostatService.
_validate_temperature` (`thermostat_service.py:179-189`) and
`VacuumHumidifierService._validate_target_humidity`
(`vacuum_humidifier_service.py:208-218`) exactly:
- Accepted: `int` or `float`, coerced to `float`.
- **Rejected**: `bool` (an `int` subclass), `NaN`, `+inf`, `-inf` —
  `ServiceError` before any wire call.
- **No range of its own is imposed.** Bounds are enforced **only**
  when the device itself reports `min_temp`/`max_temp` — identical to
  Thermostat's `_validate_against_device`
  (`thermostat_service.py:332-365`). **No safety limit is invented**
  where the device reports none, per explicit instruction — see §18
  Risk 4 for the scald-risk implication of this choice.
- **Precision**: passed through as a plain `float`, no rounding, no
  truncation — identical to every prior numeric field in this module
  family.
- **Unit**: no conversion (§4). If a real device's `min_temp`/
  `max_temp` default (110°F/140°F, per the external verification
  above) is reported in Fahrenheit while another reports Celsius, this
  module does not detect or reconcile that — it is not equipped to,
  the same limitation `ThermostatService` already accepts.

## 6. Operation mode — resolved, not blindly copied

**Repository evidence**: none (§5). **External evidence (VERIFIED
EXTERNALLY, same source as §5)**: `WaterHeaterEntity.current_operation:
str | None`, `operation_list: list[str] | None`, gated by the
**`OPERATION_MODE`** feature flag; `async_set_operation_mode()`
"Sets operational mode (must be in `operation_list`)".

**Decision: writable, validated against the device-reported
`operation_list` — mirroring `ThermostatService`'s `hvac_mode`/
`hvac_modes` template (§12 of the Climate contract), *not*
`VacuumHumidifierService`'s read-only `mode`.** This is a deliberate
choice between two existing precedents, not a default inheritance:
Humidifier's `mode` was made read-only because that contract found
**no** HA service that sets it; here, external verification found a
real, documented `async_set_operation_mode()` method explicitly
described as validated against `operation_list` — the same shape
Thermostat's `hvac_mode` already has proven repository code for. The
evidence, not convenience, selects the template.

**Validation rules (PROPOSED)**, mirroring `ThermostatService.
_validate_mode`/`_validate_against_device`'s hvac_mode branch
(`thermostat_service.py:327-330`, `:367-373`):
- Accepted: non-empty `str`, normalized `.strip().lower()`.
- **When the device reports a non-empty `operation_list`**: a
  requested mode not in that list is rejected with `ServiceError`
  before any wire call.
- **When `operation_list` is absent/empty**: any non-empty string is
  accepted and passed through — the device/connector remains the
  authority, matching the "rejecting a real device over a vocabulary
  gap is the worse failure" principle `DEVICE_TYPES`' own comment
  states.
- **No fixed operation-mode enum is invented anywhere.**
- Case: normalized to lowercase, mirroring `hvac_mode`'s treatment
  (operation modes are short, enum-like tokens — `eco`/`electric`/
  `gas`/`heat_pump`/`high_demand`/`off`/`performance`, per the
  external doc's own example list — not human-facing mixed-case
  labels the way Media Player's `source` is; this is the deliberate,
  stated difference between the two templates).

**(UNVERIFIED — MUST VERIFY DURING PHASE 2)**: the exact wire-level
payload key `water_heater.set_operation_mode` expects. The entity
method signature (`async_set_operation_mode(self, operation_mode:
str)`) strongly implies a payload key of `operation_mode` — consistent
with `climate.set_hvac_mode`'s own `hvac_mode` key, which this
repository's `ThermostatService` already exercises successfully
(`thermostat_service.py:110`) — but this specific service's payload
schema has not been checked against HA's actual `services.yaml` and
must be before implementation.

## 7. On/off and playback... state semantics

**(VERIFIED EXTERNALLY, same source as §5)**: `async_turn_on()` /
`async_turn_off()` exist, gated by the **`ON_OFF`**
`WaterHeaterEntityFeature` flag — **on/off support is optional, not
universal**, unlike a light or lock. The doc also states current
operation state display commonly includes `"On"`, `"Off"`, `"Eco"`,
`"Electric"`, `"Performance"`, `"High demand"`, `"Heat pump"`, `"Gas"`,
in addition to `"Unavailable"`/`"Unknown"` — i.e. **the entity's own
state string can be either a plain on/off token or an operation-mode
token**, depending on which features a given integration supports.

**Decision: `state` stays an open pass-through, exactly like Vacuum's
and Media Player's `state`** — never validated against a closed
vocabulary, because a real device may report either shape. **A
separate derived `is_on: bool | None` field** is computed the same way
`VacuumHumidifierService._infer_on` already does
(`vacuum_humidifier_service.py:199-205`): `True`/`False` when the
lowercased state string is a recognized on/off token (`"on"`/`"true"`/
`"1"` vs `"off"`/`"false"`/`"0"`), `None` otherwise (including when the
state is an operation-mode token like `"eco"` — an operation mode
being reported does not, by itself, prove the device is powered on).

**Normalization rules**, mirroring §5 of the Media Player contract
exactly:
- `state` is `raw.status.strip().lower()`, or `None` if the stripped
  result is empty.
- **Unavailable → `state = None`**, never the literal
  `"unavailable"`/`"offline"` string.
- Unknown/unrecognized tokens pass through verbatim, lowercased —
  never coerced to `None`, never rejected.

**On/off command (PROPOSED)**: `on: bool | None` is a field of the
merged mutation (§9), mirroring `VacuumHumidifierService.
set_humidifier_state`'s own `on` parameter shape
(`vacuum_humidifier_service.py:410-421`) — **not** a separate pair of
zero-payload transport tools the way Media Player's five transport
verbs are, because on/off here is one settable attribute among three
(temperature, mode, on/off), not an independent momentary action.

## 8. HA translation (PROPOSED)

| Normalized | HA service | Payload | Evidence |
|---|---|---|---|
| `on = True` | `turn_on` | `{}` | VERIFIED EXTERNALLY (§7) |
| `on = False` | `turn_off` | `{}` | VERIFIED EXTERNALLY (§7) |
| `operation_mode` | `set_operation_mode` | `{"operation_mode": <str>}` | Method name VERIFIED EXTERNALLY (§6); payload key UNVERIFIED — MUST VERIFY DURING PHASE 2 |
| `temperature` | `set_temperature` | `{"temperature": <float>}` | Method name VERIFIED EXTERNALLY (§5); payload key UNVERIFIED — MUST VERIFY DURING PHASE 2, by direct analogy to `climate.set_temperature`'s repository-proven `{"temperature": ...}` shape (`thermostat_service.py:112`) |

All reached through the existing generic dispatcher
(`HomeAssistantConnector.send_command` derives `domain` from
`external_id.split(".", 1)[0]`; a `water_heater.*` entity id already
routes to `POST /api/services/water_heater/{service}` with **zero
connector changes**, the same mechanism every prior slice relies on,
re-verified unchanged this session).

**Three independent, single-purpose HA services** (`turn_on`/
`turn_off`, `set_operation_mode`, `set_temperature`) — the same
three-independent-services shape Media Player's `volume_set`/
`volume_mute`/`select_source` already established, not Thermostat's
two-service shape. A combined update is therefore **up to three
sequential calls** (§9).

## 9. MQTT translation (PROPOSED)

**A first-definition JARVIS-native vocabulary** — a repo-wide search
this session found zero prior MQTT consumer for water-heater control,
the identical situation every prior M12 module's own MQTT vocabulary
was in.

**One merged `set_state` call**, mirroring Thermostat's/Humidifier's/
Media Player's own MQTT convention (deliberately *not* copying HA's
three-service split, since the MQTT envelope has no such constraint):

| Requested | MQTT `command` | MQTT `args` |
|---|---|---|
| `on` only | `set_state` | `{"on": <bool>}` |
| `operation_mode` only | `set_state` | `{"operation_mode": <str>}` |
| `temperature` only | `set_state` | `{"temperature": <float>}` |
| any combination | `set_state` | merged dict of whichever above are set |

**Domain resolution**: `metadata["domain"]` first,
`metadata["component"]` fallback — §2's local helper, reused for
MQTT-discovered water heaters exactly as for HA-discovered ones. **No
connector modification.**

## 10. Merged state mutation (PROPOSED)

```python
async def set_water_heater_state(
    self, device_id: str, *,
    temperature: float | None = None,
    operation_mode: str | None = None,
    on: bool | None = None,
) -> dict[str, Any]: ...
```

**Empty mutation**: all three `None` → `ServiceError` before any wire
call, identical to every prior merged-mutation module's rule.

**Validation order** (fails fast, before any wire call): device-type/
domain check → per-field type/range validation (§5/§6) →
`operation_mode` against device-reported `operation_list` when
non-empty (§6) → `temperature` against device-reported `min_temp`/
`max_temp` when reported (§5) → wire dispatch.

**Command ordering — resolved: on/off, then operation mode, then
temperature.** This is a **stated convention, not a discovered HA
behavior** (explicitly flagged here so it is never later mistaken for
one, mirroring Media Player §9's identical disclaimer): unlike
Thermostat's mode-before-temperature (where HVAC mode changes what a
temperature setpoint *means* — heating vs. cooling), this contract
found no equivalent documented dependency between water-heater
operation mode and its temperature setpoint. On/off is ordered first
for the same readability reason Humidifier's on/off-first ordering
used — powering the device before/while changing its settings reads
more naturally — not because HA requires it.

**Partial failure semantics**: identical to every prior merged
mutation — each requested call executes in order, stopping at the
first failure; `success: false` names exactly which calls already
applied. Given this module can sequence **up to three** calls (the
same ceiling Media Player's merged mutation already exercises), the
detail message may need to name up to two already-applied calls.

**Response**: `{"device_id": str, "success": bool, "detail": str}` —
identical shape to every prior M12 command result.

## 11. Permission decision — evaluated, not inherited

**Scope**: existing `smart_home` — no new scope (`PERMISSION_SCOPES`,
`core/plugins/sdk.py:34-47`, re-verified unchanged this session).
**Principal**: `core:water_heaters`, declared once at construction,
`PENDING` by default, granted through the existing generic route
`POST /api/v1/plugins/core:water_heaters/permissions/smart_home/
grant` — the tenth instance of this now-fully-proven pattern.
**Reads: UNGATED.** **Mutation: GATED**, following every prior
appliance-category module.

**Confirmation — explicitly evaluated, per instruction, not
auto-inherited from Thermostat.** The physical-safety argument for
gating `set_water_heater_state` behind `confirm_required_tools` is
real and materially different from every prior appliance setpoint:
setting a water heater's temperature high enough creates a genuine
scald-injury mechanism from *ordinary* subsequent use (a shower), not
misuse — a category no prior M12 setpoint (thermostat comfort
temperature, humidity, media volume) shares. This was weighed
seriously, not dismissed:

**Arguments for gating**: real bodily-harm mechanism; the first M12
setpoint with one.

**Arguments against gating, which this contract finds control**:
1. This module invents no safety limit of its own (§5) — it enforces
   only the device's *own* reported `min_temp`/`max_temp`, and HA's
   base entity class defaults `max_temp` to 140°F (§5, VERIFIED
   EXTERNALLY) — most real integrations will therefore already reject
   an extreme value before it reaches the wire, when they report
   bounds at all.
2. Unlike `unlock_device`'s instantaneous, irreversible-in-the-moment
   consequence (a door is unlocked the instant the command succeeds),
   a water heater's thermal mass means a new setpoint takes real time
   to propagate — reducing the "immediate harm" character that
   justified gating `unlock_device` specifically
   (`config/settings.py:513`, re-verified unchanged this session:
   `{"run_automation", "unlock_device"}`).
3. Every prior M12 setpoint mutation (temperature, humidity, volume)
   chose no confirmation; `confirm_required_tools` has stayed a short,
   deliberately narrow list across all thirteen shipped task groups,
   and diluting it with every setpoint that has *some* plausible risk
   erodes that property for every future module too.

**Decision: no confirmation requirement is added.** This is recorded
as the closest call of any M12 appliance module to date, not a
reflexive default — see §18 Risk 4 for the condition under which this
decision should be revisited (if Phase 2 finds most real integrations
report no `min_temp`/`max_temp` at all, the first mitigating argument
above weakens materially).

## 12. REST contract (PROPOSED)

Under the existing `/appliances` prefix, matching every prior
category's own convention:

| Method | Path | Behavior |
|---|---|---|
| GET | `/appliances/water-heaters` | List (DB-only, no live read). |
| GET | `/appliances/water-heaters/{id}` | Live state (§4). 404 if unknown/not a water heater. |
| POST | `/appliances/water-heaters/{id}/state` | Body `{"temperature"?: float, "operation_mode"?: str, "on"?: bool}`. Empty body → 400. |

Chosen over Vacuum's/Media Player's verb-endpoint shape because,
unlike those modules, **water heater control has no independent
zero-payload transport action at all** — every command here is an
attribute mutation, the identical shape Thermostat's/Humidifier's own
single merged `/state` endpoint already covers.

`{data, meta}` envelope, `Depends(get_current_session)` — identical to
every M12 router (mirrors `infrastructure/api/routes/thermostats.py`
exactly). **Error taxonomy**, matching Thermostat's/Humidifier's/Media
Player's convention exactly: reads ungated, so no permission-driven
400-vs-404 split. Plain `GET .../{id}`: unknown/wrong-type → **404**.
`POST .../state`: any `ServiceError` (invalid value, empty mutation,
wrong type/domain, permission not granted, unsupported by device)
→ **400**. `success: false` is **200**, never an error. Unavailable
device on a successful read is still **200** (all live fields `None`,
`available: false`).

## 13. Agent tools (PROPOSED)

**Three tools, mirroring `ThermostatService`'s exact shape, not Media
Player's eight** — there being no independent transport verb here
(§12), splitting the mutation into per-attribute tools would only cost
extra round-trips for the common "turn it on and set it to 55°" intent,
the identical reasoning `thermostat_tools.py:5-11`'s own module
docstring already states.

| Tool | Wraps |
|---|---|
| `list_water_heaters` | `list_water_heaters()` |
| `get_water_heater_state` | `get_water_heater_state()` |
| `set_water_heater_state` | `set_water_heater_state(temperature?, operation_mode?, on?)` |

All three call `WaterHeaterService` only, never `ConnectivityService`
or a connector directly — both REST and tool callers trip the
identical permission check. Reads ungated; `set_water_heater_state`
requires the `smart_home` grant for `core:water_heaters`. **Not**
added to `confirm_required_tools`, per §11's evaluated decision. Every
tool catches `Exception` broadly and returns a friendly string,
matching every M12 tool file's convention.

## 14. EventBus decision

**No event changes, prohibited explicitly.** `WaterHeaterService`
publishes nothing. No `WaterHeaterUpdatedEvent`, no subscriptions, no
workers, no event-driven automation. Poll-based only, matching all
nine prior M12 modules (re-verified this session: zero
`event_bus`/`EventBus` references remain the pattern across every
service file, `EventBus` itself unchanged at `core/events/
event_bus.py`). The pre-existing device-command event-publishing gap
(`MASTER_ROADMAP.md:405,883,4232`) remains untouched — not fixed here,
still recorded as a separate architectural dependency for Home
Automation/Smart Home Memory/Developer Tools, exactly as every prior
contract recorded it. This task group does not attempt to solve Home
Automation, Smart Home Memory, or Developer Tools' dependencies.

## 15. Database / Memory / Analytics decision

**None required.** No new table, no new column, no `DEVICE_TYPES`
addition. **No `MemoryService` integration** — `MemoryService.
remember()` exists and is generic (`services/memory_service.py:109`)
but is Smart Home Memory's own still-unstarted integration point, not
this slice's job. **No Analytics integration.** **No history/
telemetry persistence of any kind.** Explicitly deferred, not stubbed:
energy usage history, cost/optimization dashboards, predictive
maintenance — all Smart Home Analytics'/M20A's job, both unstarted.

## 16. Explicitly deferred scope (explicit, no placeholders)

| Item | Why deferred |
|---|---|
| Away/vacation mode (`is_away_mode_on`, `set_away_mode`) | Real HA feature (VERIFIED EXTERNALLY, §7's source) but out of this MVP's named scope; no read, no write, no field anywhere. |
| Dual setpoint (`target_temperature_high`/`target_temperature_low`) | A materially different mutation shape (heat-pump-style range) this contract does not attempt to design blind — same discipline Thermostat applied to its own single-setpoint MVP. |
| Scheduling, automation | Home Automation's/M7's job — M7's Scheduler execution layer confirmed still unshipped this session (`MASTER_ROADMAP.md:10738`: "Workflow Builder / Scheduler / Recorder (Phases 4–6) remain pending"). |
| Energy optimization, energy usage history/analytics | Smart Home Analytics'/M20A's job, both unstarted. |
| Predictive/AI control | AI Home Assistant's job, unstarted. |
| Multi-device orchestration | No repository modeling exists for it beyond static Room/Group. |
| Scenes | Smart Lighting's own scene mechanism is lighting-specific; a cross-category scene system does not exist. |
| Leak detection, safety alerting, notifications | Security & Safety's job — that module's own action-taking half is itself still entirely deferred (Phase 0 audit §3). |
| Advanced heating profiles, multi-zone control | No HA-standard vocabulary found for either; would need fresh design, not attempted here. |
| Smart Kitchen functionality | A different, currently-blocked appliance category (Phase 0 audit §6/§11) — unrelated to Water Heater. |
| Any other M12 module | Out of this task group's scope by definition. |

**No placeholder backend architecture, no scaffolding, no dead
parameters, no reserved-but-unused payload fields for any of these.**

## 17. Test strategy (future Phase 2 — described, not created)

Phase 1 creates **zero tests**. The following matrix is what Phase 2
must cover, real components throughout (`FakeDeviceConnector`, real
temp-file SQLite, real `PermissionModel`) — no mocks, matching every
prior M12 module's discipline:

- **Domain/discrimination**: `_domain_for` resolves via `"domain"`
  then `"component"` fallback; rejects a device with neither. Wrong
  `device_type` (every foreign type) and wrong appliance-domain
  (fan/cover/vacuum/humidifier/media_player ids passed to water-heater
  endpoints, and vice versa) rejected on every method, including
  reads.
- **State/on-off**: full payload; unavailable → all live fields
  `None`/`available=False`, never the literal `"unavailable"` string;
  unknown/unrecognized state tokens pass through verbatim; `is_on`
  correctly inferred for on/off tokens and `None` for operation-mode
  tokens; missing/malformed attributes → `None`/`[]`, never
  fabricated.
- **Temperature**: valid values accepted; `bool` rejected; `NaN`/
  `+inf`/`-inf` rejected; bounds enforced only when device-reported;
  permissive when `min_temp`/`max_temp` absent; missing on read →
  `None`; no unit conversion attempted anywhere.
- **Operation mode**: accepted when in device-reported
  `operation_list`; rejected when not; permissive when
  `operation_list` empty/absent; case-normalized to lowercase; missing
  on read → `None`; `operation_list` itself survives unavailability.
- **HA translation**: `turn_on`/`turn_off` zero-payload;
  `set_operation_mode`/`set_temperature` payload shapes (pending Phase
  2's own live/documentation re-verification of the exact payload
  keys, §6/§8).
- **MQTT translation**: single merged `set_state` call for every
  combination of the three fields.
- **Merged mutation**: on-only, mode-only, temperature-only, every
  pairwise and full-triple combination; ordering verified (on/off →
  mode → temperature); empty mutation rejected; partial failure
  reports exactly what applied, for both two-call and three-call
  cases.
- **Permission**: reads ungated with no grant; mutation denied without
  `core:water_heaters`/`smart_home`.
- **Confirmation**: `set_water_heater_state` is **not** present in
  `AgentSettings.confirm_required_tools` — a pinned negative
  assertion, mirroring how `unlock_device`'s presence is pinned
  elsewhere.
- **REST**: list/get/state; validation → 400; permission → 400; not
  found → 404; wrong type → 404 (GET)/400 (action); unavailable device
  still 200; envelope shape; empty body → 400.
- **Tools**: registration; all three tools' happy path and error path.
- **Cross-cutting**: source-level test proving `ApplianceService`
  carries no water-heater functional symbol; source-level test proving
  no `EventBus` reference and no direct connector import exist in the
  new service.
- **No fabricated values**: explicit assertion sweep over every field.
- **Deferred functionality absent**: explicit negative tests confirming
  every §16 item has no route, tool, field, or enum value anywhere in
  the implementation (mirrors Media Player's own §21 discipline).
- **No database/schema changes**: no new table/column exists post-
  implementation.
- **No connector modification** unless Phase 2 finds and documents an
  actual, verified blocker — not assumed here.

## 18. Risks

1. **Repository evidence gap is total** (§5) — every HA service name
   and payload shape in §8 rests on external documentation, not
   repository-proven code, a materially lower confidence tier than
   §2's connector-mapping claims (which *are* repository-verified).
   Phase 2 must re-verify against a real HA instance or its
   `services.yaml` before relying on exact payload keys, especially
   `set_operation_mode`'s and `set_temperature`'s.
2. **MQTT is a first-definition vocabulary** with no prior consumer to
   cross-check against — the fifth time an M12 module's own MQTT
   translator has been in this position.
3. **Operation-mode write semantics** (§6) — the decision to make it
   writable rests on the `OPERATION_MODE` feature flag's documented
   existence, not on having exercised a real device; a real
   integration that reports `operation_list` but silently rejects
   `set_operation_mode` would surface only as a `success: false` at
   runtime, never a local false negative (by design — §6's
   permissive-when-unreported rule), but this has not been observed.
4. **Physical safety / scalding risk** (§11) — evaluated and resolved
   against adding a confirmation requirement, but flagged as the
   closest call of any M12 module to date. **Revisit condition,
   stated explicitly**: if Phase 2 implementation or real-device
   testing finds that a substantial share of integrations report no
   `min_temp`/`max_temp` at all (removing this contract's primary
   mitigating argument), this decision should be re-opened, not
   silently kept.
5. **Merged-command partial failure** — up to three sequential wire
   calls, the same ceiling Media Player's own merged mutation already
   proved out; the detail message must correctly name up to two
   already-applied calls.
6. **Domain/component metadata ambiguity** — inherits the same,
   already-three-times-shipped local fallback; not a new risk, but
   restated because it is this module's own first exercise of it.
7. **Unavailable-state semantics** — `state` can legitimately be either
   an on/off token or an operation-mode token depending on the real
   device's supported features (§7); `is_on`'s `None`-when-ambiguous
   behavior has not been checked against a real mixed-feature device.
8. **Scope creep into automation/energy/safety systems** — §16's away-
   mode and scheduling items are the most likely "just this once"
   requests during implementation, given how closely they sit to this
   module's own read/write surface; excluded explicitly and by name.

## 19. Acceptance criteria

- `WaterHeaterService` depends only on `SmartHomeService`,
  `ConnectivityService`, `PermissionModel` — no `IDatabase`, no
  `EventBus`, no `MemoryService`, no Analytics dependency, no Scheduler
  dependency, no direct connector import.
- `ApplianceService` is **not** modified, extended, or branched into.
- Domain discrimination correctly resolves both HA-REST-sourced
  (`"domain"`) and MQTT-HA-Discovery-sourced (`"component"` fallback)
  devices, implemented locally in the new service only.
- Zero connector code changes, zero `DEVICE_TYPES` additions, zero
  schema changes, zero new permission scope, zero events published.
- No fabricated values anywhere: every unreported field is `None`/`[]`;
  `state` is `None`, never the literal `"unavailable"`/`"offline"`
  string, when the device is unavailable.
- No unit conversion exists anywhere in the implementation.
- `operation_mode` is validated against device-reported
  `operation_list` only when non-empty; no fixed enum exists.
- Temperature bounds are enforced only when the device itself reports
  `min_temp`/`max_temp`; no invented safety limit exists.
- The merged mutation rejects the empty (all-`None`) case and reports
  partial failure honestly, naming exactly what already applied, for
  every combination up to the full three-field case.
- `set_water_heater_state` does **not** appear in
  `AgentSettings.confirm_required_tools`, per §11's evaluated decision
  — pinned by a negative test.
- Every item in §16's deferred table has zero corresponding route,
  tool, field, enum value, or scaffold anywhere in whatever
  implementation eventually follows this contract.
- No mutation-tool split beyond the three tools named in §13; reads
  remain ungated; the mutation requires `core:water_heaters`/
  `smart_home`.
- Full backend regression stays green (baseline at the time of writing:
  3274 tests, 0 failures, 0 errors, 1 pre-existing skip).
- No file under `frontend/` is touched.
- Every §8/§9 wire-level claim marked UNVERIFIED in this contract is
  re-verified — against a real HA instance, its `services.yaml`, or
  equivalently authoritative evidence — before the corresponding code
  is written, and the result (confirmed or corrected) is recorded in
  the implementation commit, not silently assumed.
- This Logic Contract is reviewed and approved **before** any
  implementation begins.

Every criterion above is implementable without new schema, EventBus,
frontend, a new milestone dependency, connector-wide refactoring,
`ApplianceService` modification, or any change to previously shipped
M12 behavior.

## 20. Evidence ledger (summary)

| Claim | Classification | Source |
|---|---|---|
| `water_heater` → `device_type="appliance"` in both connectors | **VERIFIED IN REPOSITORY** | `home_assistant.py:86`, `mqtt.py:167` |
| `metadata["domain"]`→`["component"]` fallback pattern | **VERIFIED IN REPOSITORY** | `vacuum_humidifier_service.py:175-184`, reused by `media_player_service.py:169-178` |
| `ConnectivityService` chokepoints unchanged | **VERIFIED IN REPOSITORY** | `connectivity_service.py:195,214` |
| `ApplianceService`'s own "future category gets its own service" instruction | **VERIFIED IN REPOSITORY** | `appliance_service.py:19-20` |
| `confirm_required_tools` unchanged | **VERIFIED IN REPOSITORY** | `config/settings.py:513` |
| `turn_on`/`turn_off`/`set_temperature`/`set_operation_mode`/`set_away_mode` service names exist | **VERIFIED EXTERNALLY** | `home-assistant.io/integrations/water_heater/`, fetched this session |
| `WaterHeaterEntity` property names, `WaterHeaterEntityFeature` flags (`TARGET_TEMPERATURE`, `OPERATION_MODE`, `AWAY_MODE`, `ON_OFF`), `min_temp`/`max_temp` defaults (110°F/140°F) | **VERIFIED EXTERNALLY** | `developers.home-assistant.io/docs/core/entity/water-heater/`, fetched this session |
| Exact `set_temperature`/`set_operation_mode` service **payload keys** | **UNVERIFIED — MUST VERIFY DURING PHASE 2** | Check HA's `services.yaml` for the `water_heater` domain, or a live HA instance, before implementation |
| Whether a real integration's `state` string doubles as operation mode vs. plain on/off in practice | **UNVERIFIED — MUST VERIFY DURING PHASE 2** | Exercise against `FakeDeviceConnector`-shaped fixtures modeling both cases; if possible, cross-check one real HA demo instance |
| Any water-heater-specific repository code prior to this contract | **NONE FOUND** | `grep -rn "water_heater" src/ tests/ docs/`, this session — confined to connector domain-mapping dicts and forward-looking docstrings only |
