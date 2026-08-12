# M12 Appliance Control — Climate / Thermostat Slice — Logic Contract

Status: **Draft — Logic Contract only.** Written per the `M12 PHASE 0
POST-MODULE AUDIT` and its approval (`APPROVED — M12 APPLIANCE CONTROL:
CLIMATE / THERMOSTAT SLICE`). **Not approved for implementation** — no
source, tests, DI, routes, tools, connector, roadmap or CHANGELOG
changes accompany this file. Base: the shipped M12 Connectivity REST +
Smart Lighting (`docs/M12_CONNECTIVITY_REST_SMART_LIGHTING_LOGIC_CONTRACT.md`,
commits `48e089d`/`fcda155`) and Appliance Control Core Slice
(`docs/M12_APPLIANCE_CONTROL_LOGIC_CONTRACT.md`, commits
`5550899`/`5ac30cf`).

**Legend.** Every claim about code that exists today is marked
**(EXISTING)** with a `file:line` citation, verified against the current
working tree this session (clean, HEAD `76f81e9`). Everything marked
**(PROPOSED)** does not exist yet and must not be read as describing
current behavior.

## 1. Scope

**In scope**: a new `ThermostatService` **(PROPOSED)** over
`device_type="thermostat"` devices — read current temperature, target
temperature, HVAC mode and availability; set target temperature and/or
HVAC mode. One REST resource collection, three agent tools, one new
permission principal. **Zero connector changes, zero schema changes,
zero event changes.**

**Explicitly not this slice's job** (§17 gives the full accounting):
fan mode, swing mode, preset modes, humidity/dehumidification, aux/
emergency heat, dual-setpoint (`target_temp_high`/`target_temp_low`)
range mode, scheduling, automation, occupancy-aware HVAC, multi-zone
orchestration, thermostat scenes, predictive/AI HVAC optimization, and
energy optimization.

## 2. Phase 0 verification results

All 22 required verification points, checked directly this session:

| # | Point | Result |
|---|---|---|
| 1 | `DEVICE_TYPES` contains `thermostat` | ✅ **(EXISTING)** `domain/smart_home/models.py:53-55` — and its own comment (`:44-52`) says `thermostat` is present because it is "named explicitly in Appliance Control's own feature list" |
| 2 | HA maps `climate` → `thermostat` | ✅ **(EXISTING)** `home_assistant.py:78` — `"climate": "thermostat"` in `_DEVICE_DOMAINS` |
| 3 | MQTT maps `climate` → `thermostat` | ✅ **(EXISTING)** `mqtt.py:159` — `"climate": "thermostat"` in `_HA_COMPONENT_DEVICE_TYPES` |
| 4 | `ConnectivityService` can read raw state | ✅ **(EXISTING)** `connectivity_service.py:195` `read_raw_state(device_id) -> DeviceState \| None` |
| 5 | `ConnectivityService` can send commands | ✅ **(EXISTING)** `connectivity_service.py:214` `send_command(device_id, command, payload)` |
| 6 | Lighting attribute-merge pattern | ✅ **(EXISTING)** `smart_lighting_service.py:112-167` — `_translate_home_assistant`/`_translate_mqtt` each take every optional attribute and merge whatever is set into **one** wire command; module docstring `:13-25` gives the rationale |
| 7 | Device metadata model | ✅ **(EXISTING)** `Device.metadata_json` TEXT column (`database/models.py:1139`); `connector_type_for(device)` (`connectivity_service.py:63`) is the one shared reader |
| 8 | Availability model | ✅ **(EXISTING)** derived, not stored — `available = raw is not None and raw.status.strip().lower() not in {"offline","unavailable"}` (`appliance_service.py`, `sensor_service.py:56`) |
| 9 | Room/home relationships | ✅ **(EXISTING)** `Device.home_id` (non-null FK), `Device.room_id` (nullable FK) — `database/models.py:1122-1127` |
| 10 | `PermissionModel` | ✅ **(EXISTING)** `core/plugins/permissions.py:66` — `declare`/`is_granted`/`grant`/`deny`/`revoke`, JSON-persisted, audit-logged |
| 11 | `smart_home` scope pre-exists | ✅ **(EXISTING)** `core/plugins/sdk.py:44` in `PERMISSION_SCOPES` |
| 12 | `AgentPermissionGate` | ✅ **(EXISTING)** `agents/permission.py:46`, driven by `AgentSettings.confirm_required_tools` = `{"run_automation","unlock_device"}` (`config/settings.py:513`) |
| 13 | Tool Registry pattern | ✅ **(EXISTING)** `agents/tools/registry.py` — 17 `build_*_tools` blocks, each gated on an optional service param |
| 14 | Orchestrator four-point wiring | ✅ **(EXISTING)** `registry.py` param + `orchestrator.py` `__init__`/`start()` + `container.py` `_build_agent_orchestrator` + provider — proven six times |
| 15 | FastAPI router conventions | ✅ **(EXISTING)** `APIRouter(tags=[...], dependencies=[Depends(get_current_session)])`, `Envelope`/`envelope()` `{data, meta}` |
| 16 | DI conventions | ✅ **(EXISTING)** module-level `_build_*` with lazy import + `providers.Singleton` (`container.py:549-594`) |
| 17 | `ServiceError` hierarchy | ✅ **(EXISTING)** `core/exceptions.py`; modules define narrow local subclasses only when a route must distinguish (`SensorPermissionError`, `SecurityPermissionError`) |
| 18 | REST error handling | ✅ **(EXISTING)** plain `GET .../{id}` → 404; every action endpoint → 400 on any `ServiceError` (`routes/smart_lighting.py:10-18` documents this exact convention) |
| 19 | Smart Lighting tests | ✅ **(EXISTING)** `test_m12_smart_lighting_service.py` + route/tool siblings |
| 20 | Appliance Control tests | ✅ **(EXISTING)** `test_m12_appliance_service.py`, `test_m12_appliances_route.py`, `test_m12_appliance_tools.py` |
| 21 | Roadmap definition of Smart AC | ✅ **(EXISTING)** `MASTER_ROADMAP.md` §9 Appliance Control lists "Smart AC" (unticked); the Appliance Control contract §18 deferred Climate specifically because it is `device_type="thermostat"` with its own multi-attribute vocabulary |
| 22 | MQTT envelope/command conventions | ✅ **(EXISTING)** `mqtt_envelope.py:159-170` `build_command_envelope(device_id, command, args)` → `payload={"command": ..., "args": {...}}`; `mqtt.py:460-483` publishes it to the device's command topic, `retain=False` |

**Correction to a prior assumption, recorded here deliberately:** the
Appliance Control contract (§18) described Climate as a "future
Appliance Control slice." That framing is *architecturally* wrong in one
respect this verification settles: a thermostat is **not** a
`device_type="appliance"` device and therefore **cannot** be an
extension of `ApplianceService`. It is its own `device_type`, needing
its own service — which is exactly what this contract proposes. The
deferral decision was right; the "extend ApplianceService later"
implication was not.

## 3. Thermostat device model

A thermostat is a `Device` row (`database/models.py:1100`, unmodified)
with `device_type="thermostat"` — no new ORM model, no new table, no
new `DEVICE_TYPES` value (it is already there, §2.1).

**Simpler than Appliance Control in one specific way**: `ApplianceService`
needs `metadata["domain"]` to tell a fan from a cover because both share
`device_type="appliance"` (`appliance_service.py:133-135,221-231`).
A thermostat has its **own** `device_type`, so **no domain
discrimination is needed at all** — `_require_thermostat` checks
`device.device_type != "thermostat"` and nothing else, exactly like
`SmartLightingService._require_light` (`smart_lighting_service.py:
301-305`) and `SmartLockService._require_lock`. This module reads
`metadata_json` only through the existing shared `connector_type_for()`
(§2.7), never for sub-kind discrimination.

## 4. Normalized state model (PROPOSED)

**One coherent object**, not a separate model per attribute — per the
approving instruction and matching `_light_payload`'s own shape
(`smart_lighting_service.py:208-231`):

```
{
  "id": str, "home_id": str, "room_id": str | None, "name": str,
  "status": str,                       # Device.status -- connectivity lifecycle, unchanged meaning
  "manufacturer": str, "model": str, "external_id": str | None,
  "current_temperature": float | None, # measured room temperature
  "target_temperature": float | None,  # setpoint
  "hvac_mode": str | None,             # connector-reported, normalized to lowercase (§6)
  "hvac_modes": list[str],             # device-reported supported modes; [] when unreported
  "min_temp": float | None,            # device-reported bound; None when unreported (§7)
  "max_temp": float | None,            # device-reported bound; None when unreported (§7)
  "available": bool,
}
```

**Required vs optional.** The eight `Device`-sourced fields (`id`
through `external_id`) and `available` are **always present and
non-null** — they come from the DB row, which always exists for a device
this service can reach. All five live fields
(`current_temperature`, `target_temperature`, `hvac_mode`, `min_temp`,
`max_temp`) are **optional and default to `None`**; `hvac_modes` is
**always present** but defaults to `[]`. Nothing is ever manufactured:
a field the connector did not report is `None`/`[]`, never a guessed
default, never `0.0`, never `"off"`.

**Deliberately omitted**: `unit`. See §7.

## 5. Reading state — where each field actually comes from

**Home Assistant (EXISTING mechanism, PROPOSED field mapping).**
`HomeAssistantConnector.read_state` (`home_assistant.py:~220-228`)
returns `DeviceState(status=raw["state"], attributes=raw["attributes"],
observed_at=...)` — verified this session. For an HA `climate` entity,
**the entity's own `state` string is the HVAC mode**, and the
temperatures live in `attributes`. This is HA's documented climate-entity
shape, not an invention of this contract:

| Normalized field | Source |
|---|---|
| `hvac_mode` | `DeviceState.status` (the entity state itself), lowercased/stripped |
| `current_temperature` | `attributes["current_temperature"]` |
| `target_temperature` | `attributes["temperature"]` (HA's name for the setpoint) |
| `hvac_modes` | `attributes["hvac_modes"]` (list) |
| `min_temp` / `max_temp` | `attributes["min_temp"]` / `attributes["max_temp"]` |

**MQTT (EXISTING mechanism, PROPOSED field mapping).** The same
`DeviceState` shape reaches this module through the identical
`read_raw_state()` chokepoint. For an HA-MQTT-Discovery-sourced or
JARVIS-native climate device, `NativeState` already carries
`status: str` + `attributes: dict` (`mqtt_envelope.py:182-188`). This
module reads **the same attribute key names** as the HA path, for
cross-connector predictability — the same choice Smart Locks/Switches/
Appliances already made for their MQTT vocabularies. An MQTT device
that reports none of them yields `None`s, which is a legitimate,
documented outcome, not an error.

**Parsing rules.** Each temperature field is coerced with a `float()`
attempt; an absent, `None`, or unparseable value reports `None` —
**never** `0.0` (the same "never silently wrong zero" rule
`SensorService._parse_numeric` already enforces,
`sensor_service.py:124-128`). `hvac_modes` is accepted only if it is a
list; each element is coerced to a stripped lowercase `str`; anything
else yields `[]`.

## 6. HVAC mode semantics — decision: **Option B**

**Resolved: accept connector-provided strings with validation against
the device's own reported `hvac_modes`.** No closed enum of HVAC modes
is invented by this module.

**Why B, not A (closed enum).** The repository already has a direct
precedent for exactly this question: Sensors' `device_class` is "an
open, pass-through string, not a closed enum this module validates
against" (`M12_SENSORS_LOGIC_CONTRACT.md` §3), because HA's own
vocabulary is the authority and a closed local copy would reject real
devices over a vocabulary gap. `DEVICE_TYPES`' own comment states the
same principle explicitly: "refusing to register a real device over a
vocabulary gap is a worse failure than an imprecise category"
(`domain/smart_home/models.py:44-52`). A hardcoded mode list would also
be wrong per-device — a cooling-only AC and a heat pump genuinely
support different sets.

**Normalization rules (PROPOSED).**
- **Case**: input is `.strip().lower()`ed before validation and before
  being sent on the wire. `"HEAT"`, `" heat "` and `"heat"` are the same
  mode. Reads are normalized identically, so a round-trip is stable.
- **Validated when the device says so**: if the device reported a
  non-empty `hvac_modes` list, a requested mode **not in that list** is
  rejected with `ServiceError` before any wire call — a real, testable
  rejection using the device's own declaration, not this module's guess.
- **Permissive when it does not**: if `hvac_modes` is empty/unreported,
  any non-empty string is accepted and passed through. The connector or
  device is then the authority, and a rejection surfaces as
  `CommandResult.success=False` (§11), not as a fabricated local error.
- **Always rejected**: a non-string, an empty/whitespace-only string.
  These are malformed input, not vocabulary gaps.

**Unsupported/unknown values on read** are reported verbatim (lowercased)
in `hvac_mode` — never mapped to `None` and never coerced into a mode
this module prefers.

## 7. Temperature semantics

- **Type**: `float` throughout. Integers are accepted on input and
  coerced (`21` → `21.0`); `bool` is explicitly rejected (Python's
  `bool` is an `int` subclass — the same trap
  `_validate_brightness` already guards against,
  `smart_lighting_service.py:181`).
- **Precision**: none imposed. The value is passed through as given;
  no rounding, no quantization to any step. `target_temp_step` is
  **not** read or enforced by this slice — a device that quantizes will
  report its own quantized value back on the next read.
- **Unit**: **no unit field, no conversion, ever.** HA's climate
  entities do not reliably expose a per-entity unit (the hub reports in
  its own configured unit), so a `unit` field would be either frequently
  `None` or — worse — guessed. Converting °C↔°F on a value whose unit
  is not reliably known would produce silently wrong physical commands.
  This module therefore treats every temperature as an opaque scalar in
  **the connector's own unit**, documented as such, and performs **zero
  conversion**. (Contrast Sensors, which *does* carry `unit` — because
  HA's `sensor` entities *do* expose `unit_of_measurement`, a real
  difference between the two entity classes, not an inconsistency.)
- **Min/max validation — device-reported only.** If the device reported
  `min_temp`/`max_temp`, a requested target outside that range is
  rejected with `ServiceError` before any wire call. **If the device did
  not report them, no bound is enforced** — this contract explicitly
  invents **no** safety limits and no "reasonable AC range". There is no
  repository evidence for any such range and none is manufactured. The
  only unconditional check is that the value is a real, finite number
  (NaN and ±inf are rejected).
- **Unavailable target**: a thermostat that is unreachable or reports no
  setpoint yields `target_temperature: None`, `available: false`. A
  mutation against it is still *attempted* (the connector is the
  authority on whether it lands) and its outcome is reported honestly via
  `success` — reads and writes are not coupled.

## 8. Command / attribute-merge design (PROPOSED)

**One merged mutation**, mirroring `set_light_state`'s shape: a single
service method taking both attributes as optional keywords, translating
to the fewest wire calls that connector supports.

```
ThermostatCommand(enum.StrEnum):
    SET_TEMPERATURE = "set_temperature"
    SET_HVAC_MODE   = "set_hvac_mode"
```
(names the normalized vocabulary, exactly as `LightCommand` does —
`smart_lighting_service.py:94-104` — not the translator's dispatch key.)

**Three distinct vocabularies, never conflated** (per the approving
instruction):

**(a) JARVIS normalized API** — `set_thermostat_state(device_id, *,
temperature: float | None = None, hvac_mode: str | None = None)`. No
vendor concept appears in this signature or in §4's payload.

**(b) Home Assistant wire commands.** HA exposes climate control as two
distinct services — `climate.set_temperature` and
`climate.set_hvac_mode` — reached through the existing generic dispatcher
(`home_assistant.py:230-256`, verified this session: `domain =
external_id.split(".",1)[0]`, `POST /api/services/{domain}/{command}`,
body `{"entity_id": ..., **payload}`). For a `climate.living_room`
entity, domain resolves to `climate` with **zero connector changes**.

| Requested | HA command | HA payload |
|---|---|---|
| temperature only | `set_temperature` | `{"temperature": <float>}` |
| mode only | `set_hvac_mode` | `{"hvac_mode": "<mode>"}` |
| **both** | `set_temperature` | `{"temperature": <float>, "hvac_mode": "<mode>"}` |

The both-case relies on HA's `climate.set_temperature` accepting an
optional `hvac_mode` field. **Confidence note, stated honestly**: this
is HA's documented service schema, but — unlike every mapping in §2,
which was verified against *this repository's* source — it cannot be
verified from this repo, exactly as the Lighting contract flagged its
own `color_temp_kelvin` version dependency
(`smart_lighting_service.py:126-130`). Implementation **must** confirm
it against a real HA instance or HA's service schema before relying on
it. **If it does not hold**, the documented fallback is two sequential
wire calls (`set_hvac_mode` then `set_temperature`, mode first so the
setpoint applies to the intended mode), accepting non-atomicity and
reporting partial failure per §11. The merged form is preferred *when
confirmed* because it is atomic and avoids a visible two-step
transition — the same reasoning Lighting used.

**(c) MQTT wire command — a JARVIS-native vocabulary this module
defines.** `mqtt_envelope.build_command_envelope(device_id, command,
args)` leaves *command*/*args* deliberately free-form
(`mqtt_envelope.py:162-164`), and **no climate consumer of it exists
today** — so this is a first definition, not a guess at an existing one
(the identical situation, and identical wording, as Lighting/Locks/
Switches/Appliances). It deliberately does **not** copy HA's two-service
split, because the MQTT envelope has no such constraint:

| Requested | MQTT `command` | MQTT `args` |
|---|---|---|
| temperature only | `set_state` | `{"temperature": <float>}` |
| mode only | `set_state` | `{"hvac_mode": "<mode>"}` |
| both | `set_state` | `{"temperature": <float>, "hvac_mode": "<mode>"}` |

One command, merged args, always atomic — mirroring Lighting's own
MQTT `set_state` (`smart_lighting_service.py:151-167`). This is a case
where copying HA's wire syntax would have been *wrong*, per the
approving instruction.

**Translator registry**: `_TRANSLATORS = {"home_assistant": ...,
"mqtt": ...}`, closed to `CONNECTOR_TYPES` by construction — an
unmapped connector type raises `ServiceError`, never a silent no-op
(`smart_lighting_service.py:170-177` precedent).

**Empty mutation**: a call with **both** attributes `None` is rejected
with `ServiceError` before any wire call — there is nothing to send, and
silently succeeding would misreport a no-op as a change.

## 9. Availability

Identical derivation to every prior M12 module, re-verified this
session: `available = raw is not None and raw.status.strip().lower()
not in {"offline", "unavailable"}`. Covers both the raised-
`ConnectivityError` case (connector down — absorbed via
`contextlib.suppress`, never failing the read) and the
connector-reported-down case. **One thermostat-specific consequence**:
because an HA climate entity's `state` *is* its HVAC mode (§5), a
device reporting `"unavailable"` must **not** have that string recorded
as its `hvac_mode` — when `available` is `False`, `hvac_mode` is
`None`. This is the one genuinely new normalization subtlety in this
slice and is a required test (§18).

## 10. Permission model (PROPOSED)

- **Scope**: the existing `smart_home` (§2.11). **No new scope, no new
  permission engine.**
- **Principal**: `core:thermostats`, declared once at construction
  (`self._permissions.declare(...)`), `PENDING` by default, granted
  through the existing generic route `POST /api/v1/plugins/
  core:thermostats/permissions/smart_home/grant`. One principal per
  module — the sixth instance of a now-proven pattern.
- **Reads: UNGATED**, following Smart Lighting / Smart Locks / Smart
  Switches / Appliance Control. Not Sensors' gated-reads precedent:
  Sensors gated reads because motion/presence/occupancy reveal *who is
  home and when*. A thermostat's temperature and mode carry no
  comparable privacy weight — it is the same low-stakes class as "is the
  switch on" or "is the fan spinning", both already ungated.
- **Mutations: GATED** — `_require_permission()` on the single mutation
  method, before validation and before any wire call.
- **Confirmation: none.** No `AgentSettings.confirm_required_tools`
  entry is proposed. The existing set is `{"run_automation",
  "unlock_device"}` (§2.12) — `unlock_device` earned its place because
  unlocking a door is a *security* boundary. Changing a temperature
  setpoint is a comfort/energy change with no comparable irreversibility
  or security consequence, matching the risk profile of
  `switch_on`/`fan_on`/`cover_open`, none of which required an entry.
  Documented explicitly because the approving instruction asked for it.

## 11. Error taxonomy and failure semantics (PROPOSED)

No new local exception subclass is needed — unlike Sensors/Security,
this module's reads are ungated, so a `GET` has exactly one failure
cause and needs no 400-vs-404 disambiguation. Plain `ServiceError`
throughout, matching `routes/smart_lighting.py`'s documented convention
(§2.18):

| Case | Behavior |
|---|---|
| `GET /thermostats/{id}` — unknown id, or wrong `device_type` | `ServiceError` → **404** |
| `POST .../state` — unknown id, wrong type, invalid temperature, invalid mode, empty mutation, unmapped connector type, permission denied | `ServiceError` → **400** |
| Connector unreachable during a **read** | **Not an error** — absorbed into `available: false` + `None` live fields (200) |
| Connector rejects/fails a **command** | **Not an exception** — `CommandResult.success=False` surfaced verbatim as `{"success": false, "detail": ...}` with **200**, identical to every prior M12 command |
| Both-attribute HA fallback path (§8), first call succeeds, second fails | Reported as `success: false` with a `detail` naming which part applied — **never** reported as a full success, and never silently retried |

## 12. Service contract (PROPOSED)

```python
class ThermostatService:
    def __init__(
        self, *,
        smart_home: SmartHomeService,
        connectivity: ConnectivityService,
        permissions: PermissionModel,
    ) -> None: ...

    async def list_thermostats(
        self, *, home_id: str | None = None, room_id: str | None = None,
    ) -> list[dict[str, Any]]: ...          # DB-only, no live read (§14)

    async def get_thermostat_state(self, device_id: str) -> dict[str, Any]: ...  # §4

    async def set_thermostat_state(
        self, device_id: str, *,
        temperature: float | None = None,
        hvac_mode: str | None = None,
    ) -> dict[str, Any]: ...                # {"device_id","success","detail"}
```

Dependencies are exactly `SmartHomeService` + `ConnectivityService` +
`PermissionModel` — identical to `SmartLockService`/`SmartSwitchService`/
`ApplianceService` (`container.py:549-594`). **No `IDatabase`** (unlike
`SmartLightingService`, which takes one only because it owns the scene
table — this slice has no scenes and no persistence of its own).
**No `EventBus`** (§15). **No connector access** — every wire
interaction goes through `ConnectivityService`'s two existing
chokepoints, never `IDeviceConnector` directly.

**No duplication**: device discovery, registration, `metadata_json`
parsing and `Device` normalization all stay in `SmartHomeService`/
`ConnectivityService`/`connector_type_for()`. This module owns exactly
two things nothing else owns: climate command translation (§8) and
climate state normalization (§5).

## 13. Device-type safety (PROPOSED)

`_require_thermostat(device_id)` calls the existing
`SmartHomeService.require_device` then rejects anything whose
`device_type != "thermostat"` — so a `light`, `lock`, `switch`, `sensor`,
`camera`, `appliance` (fan/cover) or `other` id can **never** be
commanded through this API:

```
raise ServiceError(f"Device {device_id!r} is a {device.device_type!r}, not a thermostat.")
```

Mirrors `SmartLightingService._require_light`'s exact message shape
(`smart_lighting_service.py:301-305`). Enforced on **every** method,
including reads, and required as an explicit test for each foreign
device type (§18). Route mapping: **404** on `GET`, **400** on the
mutation (§11).

## 14. REST contract (PROPOSED)

Evaluated against `routes/smart_lighting.py` and adopted as the closest
precedent — a merged-attribute `POST .../state` with a Pydantic body
(`SetLightStateRequest`, `smart_lighting.py:46-50`) is exactly this
module's shape, and is preferred over Locks'/Appliances' verb endpoints
(`/lock`, `/on`, `/open`), which suit single-attribute binary devices
and cannot express "set both atomically."

| Method | Path | Behavior |
|---|---|---|
| GET | `/api/v1/thermostats` | List thermostats (`home_id`/`room_id` filters), **DB-only**, no live connector read per device — the same list/detail asymmetry every prior M12 module draws. |
| GET | `/api/v1/thermostats/{device_id}` | One thermostat's live state (§4 full payload). 404 if unknown/not a thermostat. |
| POST | `/api/v1/thermostats/{device_id}/state` | Merged mutation. 400 on any `ServiceError`. |

**Request schema** (`SetThermostatStateRequest`, Pydantic):
```
{ "temperature": float | None = None, "hvac_mode": str | None = None }
```
All three usages are supported and required: **temperature only**,
**hvac_mode only**, **both together** (§8 defines the wire behavior for
each). Both-`None` → 400 (§8).

**Response schemas.** `GET` list → `data`: list of §4 payloads with the
five live fields `None`/`[]` and `available: false` (DB-only, so no live
read has happened); `meta: {"count": int}`. `GET {id}` → `data`: full
§4 payload. `POST .../state` → `data`: `{"device_id", "success",
"detail"}`, `meta: {"success": bool}` — mirroring
`routes/smart_locks.py:73`.

**Auth**: `Depends(get_current_session)` at router level, identical to
every M12 router. **Envelope**: existing `Envelope`/`envelope()`, no new
shape. **Status codes**: 200 on both `GET`s and on the mutation
(including `success: false`); 404 per §11; 400 per §11; 401/403 for a
missing/invalid session, unchanged from the shared dependency.

## 15. Event-bus decision

**No event changes.** `ThermostatService` publishes nothing — consistent
with every prior M12 module (Lighting, Locks, Sensors, Switches,
Appliances and Security all publish nothing on command or read;
re-verified this session: zero `event_bus`/`EventBus` references in all
six service files). **No `ThermostatUpdatedEvent` is proposed** — the
repository architecture does not require one for this slice, and
inventing one would be the only event of its kind in M12.

**The known device-command event-publishing gap is deliberately not
fixed here.** It is recorded as a **BLOCKED / DEPENDENCY** for future
Home Automation, Smart Home Memory and Developer Tools' Event Viewer —
a separate architectural task, exactly as the Security & Safety slice
recorded it.

## 16. Connector-change decision

**Zero connector changes required — verified, not assumed.** Both
`_DEVICE_DOMAINS` (`home_assistant.py:78`) and
`_HA_COMPONENT_DEVICE_TYPES` (`mqtt.py:159`) already map `climate` →
`thermostat`; HA's dispatcher already derives the `climate` service
domain generically from the entity id (§8b); MQTT's `send_command`
already publishes an arbitrary command+args envelope (§8c);
`read_raw_state()` already surfaces `status` + `attributes` (§5).
Nothing in this slice needs a new connector capability, a new
`DEVICE_TYPES` entry, a new discovery field, or a new HTTP/MQTT
surface. **No connector modification is proposed, and none may be made
during implementation** — if implementation discovers a genuine gap, it
must raise it as a blocker rather than edit a connector.

## 17. Deferred scope (explicit, no placeholders)

| Item | Why deferred |
|---|---|
| Fan mode (`climate.set_fan_mode`) | Own service + own vocabulary; not in the approved slice. |
| Swing mode (`set_swing_mode`) | Same. |
| Preset modes (`set_preset_mode`, e.g. eco/away/boost) | Same; also overlaps future energy optimization. |
| Humidity / dehumidify (`set_humidity`) | Graduated control on a different axis; `humidifier` is additionally a *separate* `device_type="appliance"` domain (`home_assistant.py:85`), so it belongs to a future Appliance slice, not here. |
| `dry` / `fan_only` as *commands* | Not special-cased — they are ordinary `hvac_mode` values under §6's open-vocabulary rule if the device reports them. No dedicated surface. |
| Aux / emergency heat | HA models these as separate switches/attributes; no normalized model exists to build against. |
| Dual setpoint (`target_temp_high`/`target_temp_low`) range mode | A structurally different, two-value setpoint model; single `target_temperature` only in this slice. |
| `target_temp_step` enforcement | Read but not enforced (§7); quantization is the device's job. |
| Scheduling, automation, sunrise/sunset triggers | Home Automation's job — **blocked** on M7's Scheduler (verified unstarted) and the event gap (§15). |
| Energy optimization, occupancy-aware HVAC, predictive/AI control | Energy Management / AI Home Assistant / Smart Home Analytics — all unstarted or blocked (M20A). |
| Multi-zone orchestration, thermostat scenes | No scene/multi-device concept exists anywhere in the codebase (verified). |

**No placeholder backend architecture is added for any of these** — no
unused enum members, no reserved payload fields, no dead parameters.

## 18. Test strategy (future — described, not created)

Real components throughout, per repo convention: real temp-file SQLite
`SmartHomeService`, real `PermissionModel`, `FakeDeviceConnector`; no
mocks, no patched client libraries.

**Service** — listing (incl. filters, and that list is DB-only with no
live read); retrieval; `current_temperature`; `target_temperature`;
`hvac_mode`; `hvac_modes`; `min_temp`/`max_temp` passthrough;
availability (both the unreachable-connector and the
connector-reported-`offline`/`unavailable` cases); **`hvac_mode` is
`None`, not `"unavailable"`, when unavailable** (§9); metadata/
`connector_type` resolution; temperature-only mutation; mode-only
mutation; combined mutation; both-`None` rejection; invalid temperature
(non-numeric, `bool`, NaN, ±inf, and out-of-`min_temp`/`max_temp` when
the device reported bounds); **no bound enforced when the device reports
none**; invalid HVAC mode (non-string, empty, and not-in-`hvac_modes`
when reported); mode accepted when `hvac_modes` is unreported; case
normalization round-trip; wrong device type for **every** foreign
`device_type`; missing attributes; malformed state (unparseable
temperatures → `None`, never `0.0`); HA translation for all three
mutation shapes; MQTT translation for all three; unmapped connector type
→ `ServiceError`; `success=False` surfaced honestly; permission denial on
mutation; **reads succeed with no grant** (the ungated-reads decision,
§10).

**REST** — list; get; set temperature; set mode; combined update;
validation errors → 400; permission error → 400; not found → 404; wrong
device type → 404 on `GET` / 400 on mutation; unavailable device still
returns 200; envelope shape and `meta.success`/`meta.count`; auth
required on every route.

**Tools** — registration (present when wired, absent when not);
`list_thermostats`; `get_thermostat_state`; temperature mutation; mode
mutation; combined mutation; permission behavior; error paths return a
friendly string rather than raising.

## 19. Agent tools (PROPOSED) — **three, not four**

The approving instruction asked whether four is optimal. **It is not.**
Splitting mutation into `set_thermostat_temperature` and
`set_thermostat_mode` would (a) make the common "set it to 22 and switch
to cool" request take **two** tool calls and **two** wire calls, losing
the atomicity §8 exists to provide, and (b) diverge from the direct
repository precedent — `smart_lighting_tools.py` exposes **one**
`set_light_state` taking every optional attribute
(`smart_lighting_tools.py:76`), not one tool per attribute. Three tools:

| Tool | Purpose | Input | Output | Permission | Confirmation | Errors |
|---|---|---|---|---|---|---|
| `list_thermostats` | Find thermostats / their ids | `home_id: str = ""`, `room_id: str = ""` | JSON list of §4 payloads (DB-only), or `"No thermostats match that filter."` | Ungated | None | Caught → friendly string |
| `get_thermostat_state` | One thermostat's live reading | `device_id: str` | JSON §4 payload | Ungated | None | Caught → friendly string |
| `set_thermostat_state` | Set temperature and/or mode in one call | `device_id: str`, `temperature: float \| None = None`, `hvac_mode: str = ""` | JSON `{device_id, success, detail}` | **Gated** (`smart_home` / `core:thermostats`) | **None** (§10) | Caught → friendly string |

All three call `ThermostatService` only — never `ConnectivityService`,
never a connector. Every tool catches `Exception` and returns a readable
string, matching every M12 tool file
(`sensor_tools.py:47-51`, `smart_lock_tools.py:52-56`). `hvac_mode`
uses `""`-as-unset rather than `None` for LangChain schema
friendliness, matching `list_lights(home_id: str = "")`'s existing
convention, and is converted to `None` at the service boundary.

## 20. Acceptance criteria

- `ThermostatService` depends only on `SmartHomeService`,
  `ConnectivityService`, `PermissionModel` — no `IDatabase`, no
  `EventBus`, no connector import.
- **Zero** connector changes, `DEVICE_TYPES` additions, ORM/schema
  changes, event definitions, or new permission scopes.
- Every wire interaction goes through `ConnectivityService.send_command`
  / `read_raw_state`.
- Only `device_type="thermostat"` is reachable; every other device type
  is rejected on every method.
- No temperature limit is enforced that the device did not itself
  report; no HVAC mode vocabulary is invented.
- No manufactured values: an unreported field is `None`/`[]`, never a
  default or a zero.
- `hvac_mode` is `None` — never `"unavailable"`/`"offline"` — when the
  device is unavailable.
- Reads require no grant; every mutation requires `smart_home` for
  `core:thermostats`.
- A both-attribute update either applies atomically or reports
  `success: false` naming what applied — never a false success.
- All three mutation shapes (temperature-only, mode-only, both) work
  over both connectors.
- Full backend regression stays green (baseline: 2962 tests, 0
  failures, 1 pre-existing skip).
- No file under `frontend/` or `Jarvis-Frontend-main/frontend` is
  touched.
- This Logic Contract is reviewed and approved **before** any
  implementation begins.

## 21. Risks

1. **HA `set_temperature` + `hvac_mode` merging (§8b)** — the one claim
   in this contract not verifiable from this repo. Implementation must
   confirm it first; the two-call fallback and its partial-failure
   semantics are already specified so the discovery does not require a
   contract amendment.
2. **HA climate `state` *is* the mode** — an unusual shape versus every
   prior M12 module, where `status` meant on/off/locked. The
   `"unavailable"`-must-not-become-a-mode case (§9) is the concrete trap
   and is a required test.
3. **MQTT climate is a first definition** — no existing device speaks
   this vocabulary. Real Zigbee2MQTT-style climate devices outside HA
   Discovery are not addressed by this slice (the same limitation
   Appliance Control documented for fan/cover).
4. **Open HVAC vocabulary (§6)** means a typo'd mode reaches the device
   when `hvac_modes` is unreported. Accepted deliberately: the
   alternative — a closed enum — rejects real devices, which the
   repository's own stated principle calls the worse failure.
