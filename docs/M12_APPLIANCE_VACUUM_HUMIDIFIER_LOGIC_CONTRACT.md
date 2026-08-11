# M12 Appliance Control — Vacuum + Humidifier Slice — Logic Contract

Status: **Draft — Logic Contract only.** Written per the `PHASE 0 AUDIT
— M12 Appliance Control: Vacuum + Humidifier` and its approval
(`APPROVED — PROCEED TO PHASE 1 ONLY`). **Not approved for
implementation** — no source, tests, DI, routes, tools, connector,
permission, EventBus, roadmap or CHANGELOG changes accompany this file.
Base: the shipped M12 Appliance Control Core Slice (`docs/
M12_APPLIANCE_CONTROL_LOGIC_CONTRACT.md`, commits `5550899`/`5ac30cf`)
and Climate/Thermostat Slice (`docs/M12_APPLIANCE_CLIMATE_LOGIC_CONTRACT.md`,
commits `7db0528`/`db0d21f`).

**Legend.** Every claim about code that exists today is marked
**(EXISTING)** with a `file:line` citation, verified against the
current working tree this session (clean, HEAD `db0d21f`). Everything
marked **(PROPOSED)** does not exist yet. Anything not verifiable from
this repository is marked **(UNVERIFIED — implementation-time check
required)** and is never presented as a fact.

## 1. Scope

**In scope**: one new task group, two capabilities — Vacuum and
Humidifier — one new dedicated service. **In scope's exact boundary**:

- Vacuum: read state/availability/battery level; command start, stop,
  pause, return-to-base.
- Humidifier: read on/off, current humidity, target humidity, mode
  (read-only), min/max humidity, availability; command on/off and
  target humidity (merged).

**Explicitly not this slice's job** (§17 gives the full accounting):
fan speed, cleaning mode, spot cleaning, locate, room targeting, maps,
live map streaming, path planning, scheduling, automation, vendor
advanced modes, AI optimization (vacuum); mode *control*, presets, fan
mode, water-level automation, scheduling, environmental/predictive
optimization, multi-device orchestration, energy optimization
(humidifier).

## 2. Phase 0 re-verification — device type and connector mapping

**(EXISTING, re-confirmed this session, not merely carried over from
the audit)**:

- `vacuum` → `device_type="appliance"` in both `_DEVICE_DOMAINS`
  (`home_assistant.py:87`) and `_HA_COMPONENT_DEVICE_TYPES`
  (`mqtt.py:167`).
- `humidifier` → `device_type="appliance"` in both maps
  (`home_assistant.py:88`, `mqtt.py:168`).
- **This is the Fan/Cover pattern, not the Climate pattern.** No new
  `DEVICE_TYPES` entry is proposed or needed — `"appliance"` already
  covers both.
- `HomeAssistantConnector._entity_to_discovered_device`
  (`home_assistant.py:263-295`) writes `metadata: {"domain": domain}`
  **unconditionally for every entity**, vacuum/humidifier included —
  zero connector changes needed for HA REST-discovered devices.
- `ConnectivityService.read_raw_state`/`send_command`
  (`connectivity_service.py:195-230`) and
  `HomeAssistantConnector.send_command`
  (`home_assistant.py:230-256`, domain derived from
  `external_id.split(".",1)[0]`) are fully generic — zero connector
  changes needed for reads or command dispatch on either connector.

## 3. The critical MQTT decision (required by the approving instruction)

**Verified gap, re-confirmed this session, not assumed from the prior
audit alone**: `MqttConnector._handle_ha_discovery`
(`mqtt.py:507-556`) writes `metadata: {"component": component,
"discovery_topic": topic}` (`mqtt.py:538`) — the key is **`"component"`**,
never `"domain"`. `ApplianceService._domain_for` (`appliance_service.py:
133-135`), the only existing precedent for this kind of discrimination,
reads `metadata.get("domain")`. These do not match.
`tests/unit/test_m12_appliance_service.py` (`:107,119,249`) hand-sets
`metadata={"domain": "fan"}` directly via `register_discovered_device`
in every test — the real `_handle_ha_discovery` path has never been
exercised for Fan/Cover. **This is real, pre-existing, currently-latent
debt in already-shipped Task Group G code**, not something this slice
introduces.

**Three options were evaluated, per the approving instruction:**

1. **Fix the MQTT discovery metadata key globally** (add `"domain":
   component` alongside `"component"` in `_handle_ha_discovery`, or
   rename it). Correct long-term, but this **modifies a shared
   connector file already relied on by four shipped modules**
   (Sensors, Smart Locks, Smart Switches, Appliance Control) and is
   explicitly forbidden in this contract-only phase ("do NOT modify
   connectors"). **Rejected for this contract, recommended separately
   — see §3.1.**
2. **Have the new service safely recognize the existing key** — read
   `metadata.get("domain")`, falling back to `metadata.get("component")`
   when absent. **Chosen.** Reasoning below.
3. **Declare the MQTT path unsupported for this slice until corrected
   elsewhere.** Rejected: it would silently under-deliver on a
   connector this contract's own §2 already proves is otherwise fully
   capable (generic read/command dispatch works identically for MQTT),
   over a one-key naming mismatch that has a safe, local fix.

**Why option 2 is safe, not a silent workaround.** `_HA_COMPONENT_
DEVICE_TYPES`'s key set is **identical** to `_DEVICE_DOMAINS`'s key set
(re-verified this session, both dicts share the same 19 keys/values) —
MQTT's `component` segment (the discovery topic's own component,
`mqtt.py:511-512`) **is populated with literally the same domain
vocabulary** HA's own REST connector calls `domain`. Falling back to
`component` is not guessing a different concept; it is reading the
same value under the name the MQTT connector happens to have given it.
This mirrors the repository's own explicit "detect at use, not
fabricate" discipline (`SensorService`'s domain-default behavior,
`DEVICE_TYPES`'s own "an unknown type should be accepted... not
rejected" principle) applied to a metadata *key* lookup rather than a
*value* lookup for the first time — a natural, narrow extension of an
already-established pattern, not a new one. **This fallback is
implemented once, locally, inside the new service's own domain-lookup
helper (§9) — it does not touch `appliance_service.py` or any
connector.**

### 3.1 Recommended separate follow-up (explicitly out of scope here)

`ApplianceService._domain_for` (Fan/Cover) carries the **identical**
latent gap for MQTT-HA-Discovery-sourced fan/cover devices, unaddressed
by Task Group G and unaddressed by this contract. A future,
separately-approved, minimal fix should either (a) add the same
`domain`-then-`component` fallback to `appliance_service.py`'s own
`_domain_for`, or (b) fix `mqtt.py`'s `_handle_ha_discovery` to also
write `"domain": component` alongside `"component"`, closing the gap
at its source for every current and future consumer at once. **Not
decided or implemented here** — flagged for your review as a distinct,
narrowly-scoped follow-up.

## 4. Vacuum device model (PROPOSED)

A vacuum is a `Device` row with `device_type="appliance"` and
`metadata_json["domain"]` (or, per §3, `["component"]`) `="vacuum"` —
no new ORM model, no new table, no new `DEVICE_TYPES` value.

```
{
  "id": str, "home_id": str, "room_id": str | None, "name": str,
  "status": str, "manufacturer": str, "model": str, "external_id": str | None,
  "state": str | None,           # open pass-through -- see §5, never fabricated
  "battery_level": float | None, # device-reported only -- see §5
  "available": bool,
}
```

## 5. Vacuum state normalization

**`state` is an open pass-through string** (lowercased, stripped),
**not** validated against a closed vocabulary. This is a deliberate
departure from `ApplianceService._infer_cover_state`'s closed
`{"open","closed","opening","closing"}` set: that set is HA's own
small, universally-standard, already-relied-upon cover vocabulary.
**Vacuum's real state vocabulary has zero repository evidence** — this
contract does not invent one. Marked **(UNVERIFIED — implementation-time
check required)**: the commonly-documented HA vacuum states
(`docked`/`cleaning`/`paused`/`returning`/`error`/`idle`) are widely
known but appear nowhere in this repository; implementation must not
assume this list is exhaustive or even confirmed correct without
checking a real HA instance or HA's current entity schema.

**The same "unavailable must never leak into a semantic field" rule
the Thermostat contract established for `hvac_mode`** applies here
identically, because — like a climate entity — a vacuum's own entity
`status` *is* its state, not a separate on/off flag: when
`available=False`, `state` is `None`, **never** the literal
`"unavailable"`/`"offline"` string.

**`battery_level`** — read from `attributes.get("battery_level")`
**(UNVERIFIED key name — implementation-time check required)**,
coerced to `float`, `None` when absent or unparseable — never a
fabricated `0.0` or `100.0`. Genuinely optional: many real vacuum
integrations may not report it, and its absence is not an error.

## 6. Vacuum commands (PROPOSED)

```
VacuumCommand(enum.StrEnum):
    START = "start"
    STOP = "stop"
    PAUSE = "pause"
    RETURN_TO_BASE = "return_to_base"
```

Four independent, zero-payload commands — mirroring `FanCommand`/
`CoverCommand`'s exact shape (`appliance_service.py:70-81`), **not**
Thermostat's merged-attribute shape: these are four distinct verbs, not
attributes that combine into one user intent, so a merged mutation
method would not "preserve one intent" the way Thermostat's did — it
would just be four booleans awkwardly packed into one call.

**HA wire commands — (UNVERIFIED, implementation-time check required).**
The following are HA's commonly-documented `vacuum`-domain service
names, reached through the existing generic dispatcher
(`home_assistant.py:230-256`, domain resolves to `vacuum` from
`vacuum.*` entity ids, zero connector changes) — **not verified against
this repository**, since zero prior reference to any of them exists
anywhere in `src/`/`tests/`:

| Normalized | Candidate HA service | Payload |
|---|---|---|
| `START` | `vacuum.start` | `{}` |
| `STOP` | `vacuum.stop` | `{}` |
| `PAUSE` | `vacuum.pause` | `{}` |
| `RETURN_TO_BASE` | `vacuum.return_to_base` | `{}` |

Implementation **must** confirm these against a real HA instance or
HA's current service schema before relying on them — the same
verification discipline the Thermostat contract required for its own
HA assumption.

**MQTT — a JARVIS-native vocabulary this module would define**, no
prior consumer exists. Reuses the identical literal strings for
cross-connector predictability, matching Fan/Cover/Thermostat's own
choice: `"start"`/`"stop"`/`"pause"`/`"return_to_base"`, `{}` payload
each, one wire call per command (no merge needed — these commands never
combine).

## 7. Humidifier device model (PROPOSED)

A humidifier is a `Device` row with `device_type="appliance"` and
`metadata_json["domain"]` (or `["component"]`, §3) `="humidifier"` — no
new ORM model, no new table, no new `DEVICE_TYPES` value.

```
{
  "id": str, "home_id": str, "room_id": str | None, "name": str,
  "status": str, "manufacturer": str, "model": str, "external_id": str | None,
  "on": bool | None,                  # entity state, same shape as Fan -- see §8
  "current_humidity": float | None,
  "target_humidity": float | None,
  "mode": str | None,                 # READ-ONLY in this MVP -- see §8
  "min_humidity": float | None,
  "max_humidity": float | None,
  "available": bool,
}
```

## 8. Humidifier state normalization and the mode decision

**Unlike Vacuum/Climate, a humidifier's entity `status` is its on/off
state**, not a mode or a status string — structurally the same shape
as `Fan` (`ApplianceService._infer_on`, `appliance_service.py:138-144`),
not Thermostat's "state is the mode" shape. `on` is derived from
`raw.status` via the identical `_ON_VALUES`/`_OFF_VALUES` inference
every prior binary module already uses.

**Mode — explicit decision: READ-only, not a write surface in this
MVP.** `mode` is reported when the device provides it (from
`attributes.get("mode")` **(UNVERIFIED key name)**), purely
informational. It is **not** included in `set_humidifier_state`'s
mutation surface. Reasoning: mode-switching on a humidifier
(`"auto"`/`"sleep"`/`"baby"`, whatever a given device supports) is
adjacent to preset selection — already on the deferred list (§17) — and
making it mutable would require the same device-reported-vocabulary
validation complexity `hvac_mode` needed on Thermostat (§6 of that
contract), which is disproportionate for a slice whose core intent is
binary on/off plus a single numeric setpoint. A future, separately-
scoped slice can add mode control by following Thermostat's own
open-vocabulary template if real demand emerges. **No fixed mode enum
is invented anywhere in this contract.**

**Current/target humidity** — `current_humidity` from
`attributes.get("current_humidity")`, `target_humidity` from
`attributes.get("humidity")` (HA's own real attribute name for a
setpoint, mirroring how Thermostat found `attributes["temperature"]` to
be HA's setpoint key — **(UNVERIFIED for humidifier specifically)**,
both coerced to `float`, `None` when absent/unparseable.

**`min_humidity`/`max_humidity`** — read from device-reported
attributes only, exactly Thermostat's `min_temp`/`max_temp` rule (§7 of
that contract, reapplied here): **enforced only when the device itself
reports them; no invented default range.**

**Unavailable device**: `on`, `current_humidity`, `target_humidity` are
all `None` when `available=False` — `mode`/`min_humidity`/`max_humidity`
survive unavailability (they describe the device's declared capability,
not its live reading), mirroring Thermostat's exact "capability fields
survive unavailability" rule (§9 of that contract).

## 9. Humidifier commands (PROPOSED)

```python
async def set_humidifier_state(
    self, device_id: str, *,
    on: bool | None = None,
    target_humidity: float | None = None,
) -> dict[str, Any]: ...
```

Merged, mirroring `ThermostatService.set_thermostat_state`'s exact
shape — `on`/`target_humidity` can combine into one user intent ("turn
it on and set it to 45%"), unlike Vacuum's four independent verbs.
Both-`None` rejected before any wire call, identical to Thermostat's
empty-mutation rule.

**HA wire commands — (UNVERIFIED, implementation-time check required)**:

| Normalized | Candidate HA service | Payload |
|---|---|---|
| `on=True` | `humidifier.turn_on` | `{}` |
| `on=False` | `humidifier.turn_off` | `{}` |
| `target_humidity` | `humidifier.set_humidity` | `{"humidity": <int>}` |

**Combined update — two sequential calls**, the identical fallback
Thermostat established for its own merged-call uncertainty (this
repository contains zero evidence any HA service accepts on/off and a
humidity setpoint together). **Order: on/off first, then humidity** —
the reverse of Thermostat's mode-first ordering, and deliberately so:
HVAC mode changes what a temperature setpoint *means* (Thermostat's
reason for mode-first), but a humidifier's on/off state does not change
what a humidity setpoint means — there is no correctness dependency
either direction. On/off-first is chosen for readability (matches the
natural phrasing "turn it on and set it to 45%"), not because the
opposite order would be wrong. A partial failure reports `success:
false` naming exactly what already applied, identical to Thermostat's
honesty rule.

**MQTT — one merged `set_state` call**, mirroring Thermostat's/
Lighting's own MQTT convention, a first JARVIS-native definition:

| Requested | MQTT `command` | MQTT `args` |
|---|---|---|
| on/off only | `set_state` | `{"on": <bool>}` |
| humidity only | `set_state` | `{"target_humidity": <float>}` |
| both | `set_state` | `{"on": <bool>, "target_humidity": <float>}` |

## 10. Availability (both categories)

Identical derivation to every prior M12 module, unchanged:
`available = raw is not None and raw.status.strip().lower() not in
{"offline", "unavailable"}`.

## 11. REST contract (PROPOSED)

**Path prefix**: `/api/v1/appliances/vacuums/*` and
`/api/v1/appliances/humidifiers/*` — under the existing `/appliances`
prefix, matching `/api/v1/appliances/fans`/`/api/v1/appliances/covers`'s
own convention exactly, **not** a bare top-level `/api/v1/vacuums`.
Reasoning: these are siblings of Fan/Cover in every architectural
respect (same `device_type`, same domain-discrimination shape, same
"Appliance Control" roadmap module) even though they live in their own
service — the URL should reflect that family relationship the way the
module boundary already does.

**Vacuum — verb-style endpoints**, matching Fan/Cover's binary-command
shape, not a merged `/state` body:

| Method | Path | Behavior |
|---|---|---|
| GET | `/appliances/vacuums` | List (DB-only, no live read). |
| GET | `/appliances/vacuums/{id}` | Live state. 404 if unknown/not a vacuum. |
| POST | `/appliances/vacuums/{id}/start` | |
| POST | `/appliances/vacuums/{id}/stop` | |
| POST | `/appliances/vacuums/{id}/pause` | |
| POST | `/appliances/vacuums/{id}/dock` | Maps to `RETURN_TO_BASE` — `dock` chosen over `return-to-base` for the URL segment as the shorter, equally-clear REST verb; the normalized command name itself stays `RETURN_TO_BASE`. |

**Humidifier — one merged `/state` endpoint**, matching Thermostat's
shape since on/off and target humidity combine into one intent:

| Method | Path | Behavior |
|---|---|---|
| GET | `/appliances/humidifiers` | List (DB-only). |
| GET | `/appliances/humidifiers/{id}` | Live state. 404 if unknown/not a humidifier. |
| POST | `/appliances/humidifiers/{id}/state` | Body `{"on"?: bool, "target_humidity"?: float}`. Empty body → 400. |

`{data, meta}` envelope, `Depends(get_current_session)` — identical to
every M12 router. **Error taxonomy**: matches `routes/smart_switches.py`/
`routes/thermostats.py`'s convention exactly — reads are ungated (§13),
so no permission-driven 400-vs-404 split applies. Plain `GET .../{id}`:
unknown/wrong-type → **404**. Every action endpoint: any `ServiceError`
(unknown device, wrong type/domain, permission not granted, empty
mutation) → **400**. `CommandResult.success=False` is not an error —
**200** with `success: false`, identical to every prior M12 command.

## 12. Agent tools (PROPOSED)

**Vacuum — six tools**, one per verb, mirroring Fan/Cover's own
one-tool-per-command shape (no merged tool — four independent verbs,
per §6):

| Tool | Wraps |
|---|---|
| `list_vacuums` | `list_vacuums()` |
| `get_vacuum_state` | `get_vacuum_state()` |
| `vacuum_start` | `start()` |
| `vacuum_stop` | `stop()` |
| `vacuum_pause` | `pause()` |
| `vacuum_dock` | `return_to_base()` |

**Humidifier — three tools**, merged mutation mirroring Thermostat's
shape:

| Tool | Wraps |
|---|---|
| `list_humidifiers` | `list_humidifiers()` |
| `get_humidifier_state` | `get_humidifier_state()` |
| `set_humidifier_state` | `set_humidifier_state(on?, target_humidity?)` |

All nine call the new service only, never `ConnectivityService` or a
connector directly. No mutation tool requires confirmation (§13). Every
tool catches `Exception` broadly and returns a friendly string,
matching every M12 tool file's convention.

## 13. Permission decision (PROPOSED)

- **Scope**: existing `smart_home` — no new scope.
- **Principal — decided: `core:vacuum_humidifier`**, not the proposed
  `core:home_appliances`. Rejected `core:home_appliances` as too
  generic: every existing M12 principal is named precisely after the
  module/service it gates (`core:sensors`, `core:smart_locks`,
  `core:smart_lighting`, `core:smart_switch`, `core:appliances`,
  `core:thermostats`, `core:security`) — an operator can tell exactly
  what granting any of them means. `core:home_appliances` would be
  needlessly vague and, worse, easy to confuse with the
  **already-existing** `core:appliances` (Fan/Cover) — two
  similarly-named principals gating different device sets is a real
  usability hazard this contract avoids by naming the new principal
  after exactly what it covers, matching the file it will live in
  (`vacuum_humidifier_service.py`).
- **Reads: UNGATED** — following Fan/Cover/Switch/Thermostat's
  precedent. A vacuum's docked state or a humidifier's humidity reading
  carries no Sensors-grade privacy weight.
- **Mutations: GATED** on `core:vacuum_humidifier`/`smart_home`.
- **Confirmation: none.** Neither vacuum movement (confined, low
  physical consequence — a robot bumping furniture, not a
  safety-critical actuator) nor humidifier on/off/humidity (no water-
  level signal exists anywhere in the connector layer to reason a
  higher risk tier from) rises to `unlock_device`'s security-consequence
  tier. This matches the identical risk-tier reasoning Appliance
  Control's own contract already gave for `fan_on`/`cover_open` and
  Thermostat gave for `set_thermostat_state` — none required a
  `confirm_required_tools` entry.

## 14. Service contract (PROPOSED)

```python
class VacuumHumidifierService:
    def __init__(
        self, *,
        smart_home: SmartHomeService,
        connectivity: ConnectivityService,
        permissions: PermissionModel,
    ) -> None: ...

    # Vacuum -- reads ungated
    async def list_vacuums(self, *, home_id=None, room_id=None) -> list[dict[str, Any]]: ...
    async def get_vacuum_state(self, device_id: str) -> dict[str, Any]: ...
    # Vacuum -- commands, gated
    async def start(self, device_id: str) -> dict[str, Any]: ...
    async def stop(self, device_id: str) -> dict[str, Any]: ...
    async def pause(self, device_id: str) -> dict[str, Any]: ...
    async def return_to_base(self, device_id: str) -> dict[str, Any]: ...

    # Humidifier -- reads ungated
    async def list_humidifiers(self, *, home_id=None, room_id=None) -> list[dict[str, Any]]: ...
    async def get_humidifier_state(self, device_id: str) -> dict[str, Any]: ...
    # Humidifier -- command, gated
    async def set_humidifier_state(
        self, device_id: str, *, on: bool | None = None, target_humidity: float | None = None,
    ) -> dict[str, Any]: ...
```

**One service, two capabilities** — mirroring `ApplianceService`'s own
Fan+Cover shape exactly, **not** two services and **not** an
`ApplianceService` extension, per that module's own explicit docstring
instruction (`appliance_service.py:17-20`: "a future appliance category
... gets its own Logic Contract and, per that contract, likely its own
service — not a new branch bolted onto this one"). Dependencies are
exactly `SmartHomeService` + `ConnectivityService` + `PermissionModel`
— identical shape to `ApplianceService`/`SmartSwitchService`/
`ThermostatService`. No `IDatabase` (no scenes), no `EventBus` (§16).

**Domain discrimination (local, not shared)**: a private
`_domain_for(device) -> str | None` reads `metadata.get("domain") or
metadata.get("component")` (§3) — this module's own copy, not imported
from `appliance_service.py`, matching the repository's own "each module
defines its own small heuristic" precedent. `_require_vacuum`/
`_require_humidifier` check `device_type == "appliance"` **and**
`_domain_for(device) in {"vacuum"}`/`{"humidifier"}`, raising
`ServiceError(f"Device {device_id!r} is not a vacuum.")` (or
`"...humidifier."`) — the exact message shape `_require_fan`/
`_require_cover` already use.

## 15. Device-type safety (PROPOSED)

Every vacuum method rejects anything that is not `device_type=
"appliance"` with `domain`/`component` `== "vacuum"` — a `light`,
`lock`, `sensor`, `switch`, `thermostat`, `camera`, `other`, or **a fan/
cover/humidifier appliance** is rejected identically (the last three
share `device_type="appliance"` but fail the domain check). Symmetric
for humidifier. Enforced on every method, including reads, and required
as an explicit test for every foreign type and every foreign
appliance-domain (§21).

## 16. EventBus decision

**No event changes.** `VacuumHumidifierService` publishes nothing —
consistent with all seven prior M12 modules (re-verified this session:
zero `event_bus`/`EventBus` references remain the pattern). No
`VacuumUpdatedEvent`/`HumidifierUpdatedEvent` is proposed. The
pre-existing device-command event-publishing gap is **not** touched —
recorded, as in every prior contract, as a separate architectural
dependency for Home Automation/Smart Home Memory/Developer Tools' Event
Viewer.

## 17. Database / schema decision

**None required.** No new table, no new column, no `DEVICE_TYPES`
addition, no `MemoryService`/Analytics/history/scheduler/Home Automation
dependency — identical conclusion to every prior module.

## 18. Deferred scope (explicit, no placeholders)

| Item | Category | Why deferred |
|---|---|---|
| Fan speed, cleaning mode | Vacuum | Graduated/enum control — the same "defer to a future attribute-merge pass" reasoning Appliance Control already used for fan percentage and Thermostat used for HVAC mode's more complex cousins. |
| Spot cleaning, locate, room targeting, maps, live map streaming, path planning | Vacuum | No repository infrastructure of any kind exists for spatial/map data; inventing it here would be new architecture, not a slice of existing capability. |
| Scheduling, automation | Vacuum, Humidifier | Home Automation's job — blocked on M7's Scheduler (confirmed unstarted) and the event-publishing gap. |
| Vendor-specific advanced modes, AI optimization | Vacuum | No normalized model exists to build against; vendor-specific by definition. |
| Humidifier mode *control* | Humidifier | §8's explicit decision — read-only in this MVP. |
| Presets, fan mode | Humidifier | Adjacent to mode control; same reasoning. |
| Water-level automation, environmental/predictive optimization, multi-device orchestration, energy optimization | Humidifier | No water-level signal exists in any connector; predictive/multi-device control is AI Home Assistant's/Smart Home Analytics' job, both unstarted. |

**No placeholder backend architecture is added for any of these** — no
unused enum members, no reserved payload fields, no dead parameters.

## 19. Safety assessment

**Vacuum**: physical movement, but confined and low-consequence — the
same risk tier as a fan spinning up, not a safety-critical actuator
like a lock. Existing `PermissionModel` mutation gate is sufficient; no
confirmation warranted.

**Humidifier**: continuous water-based operation, but **no water-level
signal exists anywhere in the connector layer today** — this is stated
plainly rather than papered over. If water-level-driven safety concerns
become a real requirement, that is a **future, separately-evidenced**
decision (once a connector actually surfaces such a signal), not
something this contract invents a safety mechanism for now. No new
safety framework is proposed; the existing gate is sufficient for the
approved on/off/humidity-setpoint surface.

## 20. Frontend independence

Zero frontend files referenced, read, or required. **Backend-only
viable: YES** — REST + tools deliver full MVP value without any UI,
consistent with every M12 module to date.

## 21. Test strategy (future — described, not created)

Real components throughout (`FakeDeviceConnector`, real temp-file
SQLite, real `PermissionModel`), matching every prior M12 module's own
discipline — no mocks.

**Domain discrimination / discovery** — `_domain_for` resolves from
`"domain"` when present; falls back to `"component"` when `"domain"`
is absent (the §3 fix, tested directly with a device whose metadata
only has `"component"`); rejects a device with neither key.
**Wrong-appliance-domain rejection**: a fan/cover id passed to the
vacuum/humidifier API, and vice versa — the new "shares `device_type`
with a sibling category" case this contract introduces that Thermostat
never needed.

**Vacuum** — listing; retrieval; each of the four commands, HA and
MQTT translation; state normalization (open pass-through, never a
fabricated closed-set value); **unavailable → `state=None`, never the
literal `"unavailable"` string** (the Thermostat-precedent trap,
re-applied); battery level present/absent/malformed; wrong device type
for every foreign type including fan/cover/humidifier specifically;
permission gating on mutations; ungated reads.

**Humidifier** — listing; retrieval; on/off-only mutation; humidity-only
mutation; combined mutation (on/off-first ordering verified); empty
mutation rejected; mode reported but never mutable; min/max humidity
enforced only when device-reported, and explicitly **not** enforced
when absent; unavailable → `on`/`current_humidity`/`target_humidity`
all `None`, capability fields (`mode`/`min_humidity`/`max_humidity`)
survive; malformed attributes → `None`, never `0.0`; wrong device type
for every foreign type; permission gating; ungated reads.

**REST** — list/get/action-verbs (vacuum) and list/get/merged-state
(humidifier); validation errors → 400; permission errors → 400; not
found → 404; wrong device type → 404 (`GET`) / 400 (action); unavailable
device still 200; envelope shape.

**Tools** — registration; all nine tools' happy path and error path.

**Cross-cutting** — source-level test proving `ApplianceService` is
untouched (no `vacuum`/`humidifier` reference introduced into it,
mirroring the exact test pattern the Thermostat contract's
implementation used for its own "not extended" proof); source-level
test proving no `EventBus` reference exists in the new service.

## 22. Acceptance criteria

- `VacuumHumidifierService` depends only on `SmartHomeService`,
  `ConnectivityService`, `PermissionModel` — no `IDatabase`, no
  `EventBus`, no direct connector import.
- `ApplianceService` is **not** modified, extended, or branched into.
- Domain discrimination correctly resolves both HA-REST-sourced
  (`"domain"`) and MQTT-HA-Discovery-sourced (`"component"` fallback)
  devices — the §3 fix is implemented and tested.
- Zero connector code changes, zero `DEVICE_TYPES` additions, zero
  schema changes, zero new permission scope, zero events published.
- No fabricated values anywhere: every unreported field is `None`
  (never `0.0`/`False`/a guessed default); vacuum `state` and
  humidifier's live fields are `None`, never the literal
  `"unavailable"`/`"offline"` string, when the device is unavailable.
- Humidifier `mode` is reported but never mutable; no fixed HVAC-style
  enum is invented for either category.
- Min/max humidity bounds are enforced only when the device itself
  reports them.
- Reads ungated; mutations gated on `core:vacuum_humidifier`/
  `smart_home`; no confirmation requirement added.
- Every deferred item in §18 remains entirely absent from the
  implementation — no placeholder fields, enums, or routes.
- No file under `frontend/`/`Jarvis-Frontend-main/frontend` is touched.
- This Logic Contract is reviewed and approved **before** any of the
  above is implemented.

## 23. Risks

1. **Zero repository evidence for exact HA service/attribute names**
   (weaker starting position than even Thermostat had) — every HA wire
   name in §6/§9 is marked unverified and must be confirmed against a
   real HA instance or current HA service schema before implementation
   relies on it.
2. **The MQTT `component`/`domain` fallback (§3)** is a new pattern
   (key-level fallback, not value-level) — must be tested explicitly,
   not assumed correct by analogy alone.
3. **`ApplianceService`'s own identical latent gap (§3.1)** remains
   unfixed; Fan/Cover devices discovered via real MQTT HA Discovery
   remain silently unreachable until that separate follow-up is
   approved and shipped. This contract does not fix it, by instruction,
   but the risk should stay visible.
4. **Humidifier's on/off-first ordering (§9)** is a convention choice,
   not a correctness requirement discovered from evidence — flagged so
   it isn't later mistaken for a verified HA behavior the way
   Thermostat's mode-first ordering was.
