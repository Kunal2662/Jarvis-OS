# M12 Sensors — Logic Contract

Status: Approved for implementation. Base: the shipped M12 Connectivity
REST + Smart Lighting (`docs/M12_CONNECTIVITY_REST_SMART_LIGHTING_LOGIC_CONTRACT.md`,
commits `48e089d`/`fcda155`) and M12 Smart Locks (`docs/
M12_SMART_LOCKS_LOGIC_CONTRACT.md`, commits `b6b3f36`/`e16b61a`)
implementations. Sensors is the first **read-only** M12 module — no
command translation, no `ConnectivityService.send_command` calls, and
(a deliberate, documented departure from the prior two modules) reads
themselves are permission-gated, not just mutations. See §20.

## 1. Purpose

Normalized sensor state reporting for `device_type="sensor"` devices
(motion, presence, occupancy, door, window, temperature, humidity, air
quality, water leak, smoke, gas, light level, vibration, and any other
HA/MQTT-reported sensor), over REST and as read-only agent tools.
Establishes the "normalized READ" architecture M12 has not needed
until now — Smart Lighting and Smart Locks both proved the mutation
architecture (`Smart*Service` → `ConnectivityService.send_command` →
connector); Sensors proves the read-only counterpart (`SensorService`
→ `ConnectivityService.read_raw_state()`/`list_devices()` → connector,
no command layer at all).

## 2. Sensor device model

A sensor is a `Device` row (`infrastructure/database/models.py`, Task
Group A, unmodified) with `device_type="sensor"` — no new ORM model, no
new table (matching Smart Locks' own "no new persistence" precedent;
sensors need even less, since there is no scene/schedule concept at
all here). Two connector-reported **domains** map to this one
`device_type`, per the existing, unmodified `_DEVICE_DOMAINS`
(`home_assistant.py`) / `_HA_COMPONENT_DEVICE_TYPES` (`mqtt.py`):
`binary_sensor` and `sensor`. Both already collapse to `device_type=
"sensor"` today — this module does not change that; it reads the
`"domain"` key already stored in `Device.metadata_json` at discovery
time (`ConnectivityService.run_discovery` already writes
`{"connector_type": ..., **candidate.metadata}`, and `candidate.
metadata` already includes `{"domain": domain}` for HA — verified
directly against the shipped connector this session) to know which of
the two shapes a given sensor is.

## 3. Sensor sub-types (device_class)

**Inspected, not assumed** (`home_assistant.py`/`mqtt.py`, re-read this
session): neither connector currently captures `device_class` (HA's
own real, cross-vendor discriminator for *what kind* of sensor an
entity is) into `DiscoveredDevice.metadata` — `_entity_to_discovered_
device` (HA) only extracts `friendly_name`; `_handle_ha_discovery`
(MQTT) only extracts `unique_id`/`name`/`state_topic`/`command_topic`/
`availability_topic`/`device.manufacturer`/`device.model`. In both
cases `device_class` is already present in the exact same payload
already being parsed (HA: `entity["attributes"]["device_class"]` from
the same `/api/states` response; MQTT: `config["device_class"]` from
the same discovery config JSON, `device_class` is a standard, documented
field in Home Assistant's own MQTT Discovery schema for `sensor`/
`binary_sensor` components) — capturing it costs zero new requests and
zero new protocol surface. **This Logic Contract requires both
connectors to capture it** (§15/§16) — a minimal, symmetric, additive
enhancement to already-shipped code, not a new connector or a second
discovery system.

Evaluated sub-types, mapped to HA's own real `device_class` vocabulary
(public, documented HA API — not this module's invention):

| Requested category | HA domain | HA `device_class` | Kind |
|---|---|---|---|
| Motion | `binary_sensor` | `motion` | binary |
| Presence | `binary_sensor` | `presence` | binary |
| Occupancy | `binary_sensor` | `occupancy` | binary |
| Door | `binary_sensor` | `door` | binary |
| Window | `binary_sensor` | `window` | binary |
| Water leak | `binary_sensor` | `moisture` (HA's actual class name — not "water_leak") | binary |
| Smoke | `binary_sensor` | `smoke` | binary |
| Gas | `binary_sensor` | `gas` | binary |
| Vibration | `binary_sensor` | `vibration` | binary |
| Temperature | `sensor` | `temperature` | numeric |
| Humidity | `sensor` | `humidity` | numeric |
| Light level | `sensor` | `illuminance` (HA's actual class name — not "light_level") | numeric |
| Air quality | `sensor` | **not one HA class** — HA reports specific pollutant classes (`aqi`, `pm25`, `pm10`, `carbon_dioxide`, `volatile_organic_compounds`, ...); each normalizes fine as a generic numeric sensor, but "air quality" is not unified into one category. Documented as **supported generically, not as a dedicated bucket** — not fabricated as a single class that does not exist. | numeric |

All thirteen requested categories are representable — none is flatly
unsupported — because both connectors already discover any
`binary_sensor`/`sensor` entity regardless of `device_class`, and
`device_class` (once captured, §15/§16) is an open, pass-through
string, not a closed enum this module validates against. An unknown or
absent `device_class` is not an error: it normalizes generically (see
§7's friendly-label fallback).

## 4. Capability model

Exactly one capability: **read current state**. No commands, no
capability negotiation. `kind` (`"binary"` | `"numeric"`) is derived
from the stored `"domain"` metadata (`binary_sensor` → binary, `sensor`
→ numeric); a device with no recorded domain (e.g. hand-registered, not
connector-discovered) defaults to `"numeric"` with `value=None` rather
than raising — the same "detect at use, not fabricate" posture
`SmartLightingService`/`SmartLockService` already use for a missing
connector.

## 5. State model

```
{
  "id": str, "home_id": str, "room_id": str | None, "name": str,
  "status": str,                # Device.status -- connectivity lifecycle, unchanged meaning
  "device_class": str | None,   # HA's own vocabulary, pass-through, may be None
  "kind": "binary" | "numeric",
  "state": str | None,          # human-readable label -- see §7
  "value": bool | float | None, # bool for binary, float for numeric
  "unit": str | None,           # numeric only, from attributes.unit_of_measurement
  "available": bool,
  "timestamp": str | None,      # ISO 8601, from the connector's own observed_at -- see §9
}
```

Mirrors `_light_payload`/`_lock_payload`'s shape and spirit, extended
with `kind` (the one genuinely new discriminator a sensor needs that
neither prior module did) and `timestamp` (genuinely available here,
unlike lights/locks — see §9).

## 6. Value model

`value` is `bool` for a binary sensor (`True`="on", `False`="off" — HA's
binary_sensor state is *always* the literal string `"on"`/`"off"` at
the protocol level for every device_class; the semantic label is a
presentation concern, handled in §7, not a different underlying value),
`float` for a numeric sensor (parsed from the connector's raw status
string; an unparseable value reports `value=None`, never a silently
wrong `0.0`), `None` when unread/unavailable/unparseable. **Never
forced into one artificial shape** — a binary sensor's `value` is never
a fabricated number, and a numeric sensor's `value` is never a
fabricated boolean.

## 7. Units

Numeric sensors only: `unit` is read from the connector's raw
`DeviceState.attributes.get("unit_of_measurement")` (HA's own standard
attribute key, already generically available through `read_raw_state()`,
shipped Task Group C — no connector change needed for this one, unlike
`device_class`). `None` when the connector reports no unit. Never
inferred or hardcoded from `device_class` (e.g. never assume
`"temperature"` implies `"°C"` — a real device may report `°F`).

## 8. Normalization rules (device_class → friendly label)

A small, closed, **non-exhaustive** table for `state`'s human-readable
value — covers only the device classes named in §3 explicitly; anything
else falls back to a generic label rather than guessing a pair that
was not asked for:

| `device_class` | `value=True` | `value=False` |
|---|---|---|
| `door`, `window`, `garage_door` | `"open"` | `"closed"` |
| `motion`, `smoke`, `gas`, `moisture`, `vibration` | `"detected"` | `"clear"` |
| `presence`, `occupancy` | `"occupied"` | `"unoccupied"` |
| *(anything else, binary)* | `"on"` | `"off"` |

Numeric sensors: `state` is a formatted display string —
`f"{value}{unit}"` when a unit exists (e.g. `"21.5°C"`), else
`str(value)` (e.g. `"42"`). `state=None` when `value=None`.

**This table lives entirely in `SensorService`, never in the domain
layer** (`domain/smart_home/models.py`, `SmartHomeService`) — the same
"no vendor-specific/presentation logic in the domain model" discipline
`SmartLightingService`/`SmartLockService` already keep, verified by the
same boundary test pattern (§Testing).

## 9. Availability

`available: bool`, derived, not stored — mirrors `SmartLockService.
get_lock_state`'s pattern with one addition: both connectors have a
*real*, connector-sourced "this device is down" signal beyond a raised
exception. `MqttConnector.read_state()` already returns `status=
"offline"` when its own availability-topic cache says the device is
down (verified this session, unchanged code); Home Assistant's own API
reports `state="unavailable"` for a downed entity (standard HA
behavior). `available = raw is not None and raw.status.strip().lower()
not in {"offline", "unavailable"}` — a small, module-local constant
mirroring (not importing) `connectivity_service.py`'s own private
`_OFFLINE_STATUS_HINTS`, the same "each module defines its own small
heuristic, not a shared private import" choice `SmartLockService`
already made for its own status-inference set.

## 10. Timestamp behavior

**Genuinely supported, unlike lights/locks** (their own Logic Contracts
did not claim it because neither needed it): `DeviceState.observed_at`
is already populated by both connectors — HA's `read_state()` sets it
from the entity's own `last_updated` field (`_parse_ha_timestamp`,
already shipped); MQTT's cached `DeviceState` sets it to the moment the
last state message was received. `read_raw_state()` (shipped Task
Group C) already surfaces this. `timestamp` is `raw.observed_at.
isoformat()` when a live read succeeds and the connector reported one,
else `None` — never fabricated as "now" when the connector did not
actually say so.

## 11. REST API

`/api/v1/sensors/*`, same envelope/auth/error conventions as `routes/
smart_lighting.py`/`routes/smart_locks.py`:

| Method | Path | Behavior |
|---|---|---|
| GET | `/sensors` | List sensors (`home_id`/`room_id` filters), DB-only fields plus discovery-time `device_class`/`kind` (real, not live) — see §12. |
| GET | `/sensors/{device_id}` | One sensor's live state (§5's full payload) — 404 if unknown/not a sensor. |

**`/state`, `/capabilities`, `/status` were evaluated and folded into
the single `GET /{id}`** rather than three separate routes: this
module has exactly one capability (§4) and one state shape, so
`/capabilities` would always return the same static `{"kind": ...}`
already present in `/{id}`'s own response, and `/status` would return a
strict subset of the same payload (`available`) — three routes
returning slices of one already-cheap read add surface without adding
information, unlike Smart Lighting's `/state` (a real POST with a
body) or Smart Locks' `/lock`+`/unlock` (two genuinely different
actions). **No mutation route exists anywhere in this module** — every
route is `GET`.

## 12. Request/response schemas

`GET /sensors` — query params `home_id: str | None`, `room_id: str |
None`. Response `data`: list of

```
{
  "id": str, "home_id": str, "room_id": str | None, "name": str,
  "status": str, "device_class": str | None, "kind": "binary" | "numeric",
}
```

(the DB-only subset of §5 — no live `state`/`value`/`unit`/`available`/
`timestamp`, matching `list_lights`/`list_locks`'s own list/detail
asymmetry exactly). `meta: {"count": int}`.

`GET /sensors/{id}` — no body. Response `data` is the full §5 shape.

## 13. `{data, meta}` envelope

Identical to every resource router since M9 Task Group E — `Envelope`/
`envelope()` from `infrastructure/api/auth.py`, no new envelope shape.

## 14. Error taxonomy

**Refined from the initial draft** once §20's permission-gated-reads
decision made a genuinely new case exist: unlike Lighting/Locks, a
plain `GET /sensors/{id}` here can fail for *two* structurally
different reasons — "device not found/wrong type" and "permission not
granted" — because reads themselves require `smart_home` here (§20),
not just mutations. Rather than sniff the exception's message string
(the discipline every prior M12 route already follows for its own,
single-cause case), `_require_permission()` raises a dedicated local
subclass, `SensorPermissionError(ServiceError)` — mirroring
`core/exceptions.py`'s own existing `AutomationPermissionDeniedError
(AutomationError)` precedent, kept local to `sensor_service.py` since
nothing outside it needs to catch it specifically:

- `GET /sensors/{id}` — `SensorPermissionError` → **400**; any other
  `ServiceError` (unknown device, wrong type) → **404**, the plain
  single-resource `GET` convention every other M12 `GET .../{id}`
  route still uses for its own case.
- `GET /sensors` — `SensorPermissionError` → **400** (the only
  `ServiceError` this list endpoint can raise, since a list has no
  "not found" concept).
- A connector-level failure on the live read (`ConnectivityError` —
  not connected, unreachable) is **not** an error at either route: it
  is caught inside `SensorService` and folded into
  `available=False`/`state=None` (§9), mirroring `SmartLightingService.
  get_light_state`'s own "fall back, never fail the read" behavior.
  There is no mutation to fail, so there is no action-endpoint 400
  case for a *connector* failure in this module (unlike Lighting/
  Locks, which both have one) — the only 400 case here is permission.

## 15. Home Assistant mapping

**Inspected, not guessed** (`home_assistant.py`, re-read this session):

```
HA raw entity (GET /api/states)
    -> _entity_to_discovered_device()  [discovery time]
       -> DiscoveredDevice.metadata = {"domain": domain, "device_class": <new>}
    -> read_state()  [live read, unchanged]
       -> DeviceState(status=raw["state"], attributes=raw["attributes"], observed_at=...)
    -> SensorService normalization (this module)
       -> Normalized Sensor (§5)
```

**Required connector change** (§3): `_entity_to_discovered_device` gains
one additive line — `if attributes.get("device_class"): metadata[
"device_class"] = str(attributes["device_class"])` — reading a key
already present in the same `entity["attributes"]` dict the function
already destructures for `friendly_name`. No new HTTP call, no new
domain added to `_DEVICE_DOMAINS`, no behavior change for any
non-sensor entity.

`unit_of_measurement` needs **no connector change** — already generic
in `attributes`, already reachable via `read_raw_state()` (§7).

## 16. MQTT mapping

**Inspected, not guessed** (`mqtt.py`/`mqtt_envelope.py`, re-read this
session):

- **HA MQTT Discovery path**: `_handle_ha_discovery` parses the
  retained discovery config JSON, which already may contain a
  `device_class` key (a standard, documented field in Home Assistant's
  own MQTT Discovery schema for `sensor`/`binary_sensor` components —
  the same kind of already-present, uncaptured field as the HA REST
  case). **Required connector change**: one additive line in
  `_handle_ha_discovery` — capture `config.get("device_class")` into
  `_DeviceRegistration.metadata` alongside the existing `{"component":
  component, "discovery_topic": topic}`.
- **JARVIS-native path** (`mqtt_envelope.py`'s free-form discovery
  envelope): **no connector change needed** — `NativeDiscovery.
  metadata` is already fully free-form and already flows through
  verbatim (`_handle_native_discovery` passes `info.metadata` straight
  into the registration). A native firmware that wants to report a
  `device_class`-equivalent already can, today, with zero code change;
  this module reads `metadata.get("device_class")` generically from
  whatever is already stored, documented as **best-effort,
  firmware-provided** — not a guaranteed field for native devices.
- **State**: MQTT's own `read_state()`/state-cache behavior is
  completely unchanged — this module only *reads* `DeviceState.status`/
  `.attributes`/`.observed_at` through the existing `read_raw_state()`,
  the same chokepoint Smart Lighting already reads through for light
  state.
- **Units**: no standard MQTT/HA-Discovery field guarantees
  `unit_of_measurement` the way HA's REST attributes do; when a native
  or MQTT-discovered sensor's cached `attributes` happens to include one
  (some firmware/HA MQTT discovery configs do report `unit_of_
  measurement` in the discovery config, but this module does not
  require it), it is used; otherwise `unit=None` — never invented.

## 17. Event behavior

Reuses `DeviceUpdatedEvent` verbatim — no new event class, no second
event system. This module **does not publish any event itself** — a
read (`get_sensor_state`/`list_sensors`) is not a state change, so
there is nothing to announce, mirroring `SmartLightingService`/
`SmartLockService`'s own "commands don't publish either" reasoning
taken one step further (reads obviously publish nothing). The existing
`DeviceUpdatedEvent(action="status_changed")` still fires exactly when
it already does today, from an explicit `POST /api/v1/connectivity/
devices/{id}/refresh` call (Task Group C, unrelated to this module).

## 18. Tool Registry behavior

Four read-only tools, mirroring `smart_lock_tools.py`'s structure —
`agents/tools/sensor_tools.py`, `build_sensor_tools(sensors:
SensorService) -> list[BaseTool]`. (The kickoff's own example list named
a fifth, "get sensor information" — dropped as a literal duplicate of
`get_sensor_state` once drafted; both would have returned the exact
same full payload, §5, with no distinguishing purpose. Four distinct
tools, not five with one redundant, is what actually ships.)

| Tool | Wraps |
|---|---|
| `list_sensors` | `list_sensors()` |
| `get_sensor_state` | `get_sensor_state()`, full payload (§5) — the "give me everything" tool, mirroring `get_lock_status`'s own full-payload shape |
| `get_sensor_value` | `get_sensor_state()`, returns just `value`/`unit` for a terser agent-facing answer to "what's the temperature" |
| `get_sensor_status` | `get_sensor_state()`, returns just `available`/`status` |

`get_sensor_value`/`get_sensor_status` are thin re-shapings of the same
single service call, not separate service methods — added because a
conversational agent asking "what's the temperature" benefits from a
terse answer more than the full JSON blob every other tool in this
codebase returns, and this is the first read-heavy, data-query-shaped
module where that distinction earns its keep. All five call
`SensorService`, never a connector directly — the same non-negotiable
rule Lighting/Locks already enforce. **No mutation tool exists** —
matching REST (§11), there is nothing to mutate.

## 19. Permission behavior

**Reuses the existing `PermissionModel`, `smart_home` scope, no new
scope** — new principal `core:sensors` (mirroring `core:smart_lighting`/
`core:smart_locks`'s naming), declared once at construction, `PENDING`
by default, granted through the existing generic `POST /api/v1/
plugins/{principal}/permissions/{scope}/grant` route. This is
"Option A" per the kickoff's own framing: **no new permission scope is
created.** See §20 for the one genuine departure from Lighting/Locks'
own precedent within that same existing scope.

## 20. Privacy boundaries (required decision)

**Resolved: every `SensorService` operation, including reads, requires
the `smart_home` grant.** This is a deliberate departure from
`SmartLightingService`/`SmartLockService`, where reads (`list_lights`,
`get_light_state`, `list_locks`, `get_lock_state`) are ungated and only
mutations check permission.

**Why a blanket rule, not a per-device_class one.** The kickoff
identifies presence/occupancy/motion as more privacy-sensitive than
temperature/humidity. A finer-grained rule (gate only those three
device classes) was considered and rejected: (1) it requires drawing an
arbitrary line — a bedroom temperature reading is also mildly
revealing (occupancy pattern by proxy), and the boundary between
"sensitive" and "not" is not crisp; (2) no other M12 module has
per-capability permission granularity — Smart Lighting's `smart_home`
grant already covers everything from a harmless brightness read to a
door-adjacent porch light, and Smart Locks' grant already covers the
single most consequential physical action in the platform (unlocking a
door) under the exact same scope; introducing finer granularity only
for Sensors, and only for three of thirteen device classes, would be an
inconsistent, ad-hoc split the architecture does not support elsewhere
and that this task's own instructions caution against ("do not
implement additional authorization complexity without architectural
justification"). (3) A uniform rule is trivially auditable: "has the
operator granted `smart_home` to this principal" answers the question
for every sensor, not "which specific device_classes did they mean to
allow."

**Why gate reads at all, when Lighting/Locks do not.** A light's on/off
state or a lock's locked/unlocked state does not reveal who is present
or when; sensor data — especially motion/presence/occupancy, but
plausibly any of the thirteen categories in aggregate — can. That is a
categorically different question from "should mutating my house
require permission" (obviously yes) versus "should *observing* it
require permission" (for Sensors specifically, also yes, because
observation is the entire product here, unlike a light where the
observable fact is trivial). No new scope, no new mechanism — the same
`smart_home` grant an operator already made to use Lighting/Locks now
also gates Sensors' reads.

**Net effect**: out of the box, Sensors is fully denied (`PENDING`)
until the operator makes the same single `smart_home` grant decision
they would already need for Lighting or Locks — one grant, one scope,
covering all three modules' principals independently (each has its own
`core:*` principal, so granting one does not silently grant another).

## 21. Unsupported capability behavior

No sensor type is rejected outright (§3) — an entity discovered as
`binary_sensor`/`sensor` is always representable at minimum as a
generic on/off or numeric+unit reading, even with an unrecognized
`device_class` or none at all. What is explicitly **not** attempted:
inventing a friendly label pair for a `device_class` outside §8's
table (falls back to `"on"`/`"off"` generically, never guessed), and
unifying HA's several pollutant-specific numeric classes into one
fabricated `"air_quality"` category (§3) — each reports under its own
real `device_class` string.

## 22. Connector limitations

- Neither connector guarantees `device_class` for every sensor — a
  device discovered before this Logic Contract's connector change, or
  one whose vendor integration simply omits it, reports `device_class:
  None`; `kind` still derives correctly from `domain` regardless.
- MQTT's `unit_of_measurement` is not a guaranteed field the way HA
  REST's is (§16) — `unit` may legitimately be `None` even for a real
  numeric MQTT sensor.
- No historical/trend data — this module reports only the current
  live value, never a time series. (Device History/Usage Analytics are
  explicitly Smart Home Memory's/Smart Home Analytics' job, both
  unstarted, out of scope here.)
- No polling/background refresh — a REST/tool caller gets whatever the
  connector currently has cached (MQTT) or a fresh live call returns
  (HA); nothing in this module schedules periodic reads. `POST /api/v1/
  connectivity/devices/{id}/refresh` (Task Group C, unchanged) remains
  the only way to force a state re-read, exactly as it already is for
  lights and locks.

## 23. What this module does not build (explicit carve-outs)

- Any automation/trigger behavior (motion-triggered lighting,
  leak-triggered workflows, occupancy-triggered routines, sunrise/
  sunset, schedules) — Home Automation's job, unstarted.
- Energy-specific logic (optimization, load scheduling, dashboards,
  billing) — Energy Management's job, unstarted; energy-flavored
  numeric sensors (power/energy device classes) normalize through the
  same generic numeric path as any other sensor, nothing more.
- Security response logic (intrusion response, panic mode, emergency
  workflows, safety-critical actuator control) — Security & Safety's
  job, unstarted; smoke/gas/water-leak sensors expose normalized
  *data* only, per §5, never a reaction.
- A second device registry, connector abstraction, Smart Home service,
  permission system, event system, polling framework, or Tool
  Registry — none created; every one of those is the existing M12
  Task Group A/B/C/D infrastructure, reused verbatim.
