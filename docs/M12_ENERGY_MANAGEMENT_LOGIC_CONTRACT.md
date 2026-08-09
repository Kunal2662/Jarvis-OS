# M12 Energy Management — Core Energy Slice — Logic Contract

Status: Approved for implementation (`M12 — APPROVED: ENERGY MANAGEMENT
CORE SLICE`). Base: the shipped M12 Smart Locks (`docs/
M12_SMART_LOCKS_LOGIC_CONTRACT.md`, commits `b6b3f36`/`e16b61a`) and
Sensors (`docs/M12_SENSORS_LOGIC_CONTRACT.md`, commits `9aff3f2`/
`1fadb0a`) implementations. This is **not** the full Energy Management
module — it is the Core Energy Slice the dependency audit (`M12
POST-SENSORS — ENERGY MANAGEMENT DEPENDENCY AUDIT`) identified as the
only genuinely unblocked piece.

## 1. Scope

**In scope**: Smart Switch / Smart Plug **control** — list, get, state,
availability, turn on, turn off — for `device_type="switch"` devices.
Structurally a near-exact mirror of Smart Locks, reduced to the same
single-binary-attribute shape.

**Explicitly not this slice's job, and not built**: any form of energy
*reading* infrastructure (already shipped — see §11), consumption
history, energy dashboards/analytics/trends, energy optimization,
automatic power saving, load scheduling, or any energy-triggered
automation. See §12 for the full accounting and why each is deferred.

## 2. Smart Switch model

A switch is a `Device` row (`infrastructure/database/models.py`, Task
Group A, unmodified) with `device_type="switch"` — no new ORM model, no
new table, matching Smart Locks' own "no new persistence" precedent.
**No combined "SmartPlug" entity is created.** A physical smart plug
that also reports power/energy is, in this data model, one `switch`
`Device` row for control plus one or more sibling `sensor` `Device`
rows (`device_class="power"`/`"energy"`/...) for readings — exactly how
Task Group A's per-entity model already represents every other
multi-facet HA device, and exactly what the approved scope requires
("do not create a combined SmartPlug entity unless the existing
architecture explicitly requires it" — it does not).

## 3. Supported operations

Exactly two mutating capabilities (`turn_on`, `turn_off`) plus state
read — the same fixed, closed shape Smart Locks defined for
`lock`/`unlock`. No capability negotiation, no per-device capability
discovery, no dimming/metering/scheduling capability of any kind.

## 4. Switch state model

```
{
  "id": str, "home_id": str, "room_id": str | None, "name": str,
  "status": str,          # Device.status -- connectivity lifecycle, unchanged meaning
  "manufacturer": str, "model": str, "external_id": str | None,
  "on": bool | None,      # None = unknown/unreadable
  "available": bool,
}
```

A structural mirror of `SmartLockService`'s own `_lock_payload`
(`locked` → `on`), reduced to the one attribute a switch has, following
the same "detect at use, not fabricate" default when unread.

## 5. Availability

Identical derivation to `SmartLockService.get_lock_state`: `available =
raw is not None and raw.status.strip().lower() not in {"offline",
"unavailable"}` — both the raised-`ConnectivityError` case and the
connector-reported-down-status case (MQTT's own `read_state()` already
returns literally `"offline"`; HA reports `"unavailable"`), verified
against both shipped connectors, unchanged since Sensors' own
verification of the same fact this session.

## 6. Connector mapping

**Verified against the current working tree this session** (clean
tree, no drift since Sensors shipped): both `HomeAssistantConnector.
_DEVICE_DOMAINS` (`home_assistant.py:76`) and `MqttConnector.
_HA_COMPONENT_DEVICE_TYPES` (`mqtt.py:157`) already map `"switch":
"switch"`, unchanged, already shipped in Task Group B. **No connector
code change is required for this slice** — unlike Sensors, which
needed a discovery-time `device_class` capture enhancement, a switch
has no comparable sub-type variance worth normalizing (on/off is on/off
regardless of whether HA privately tags it `device_class="outlet"` vs
generic `"switch"`).

### Home Assistant
`HomeAssistantConnector.send_command(external_id, command, payload)`
does `POST /api/services/{domain}/{command}` with body
`{"entity_id": external_id, **payload}`, domain derived from
`external_id.split(".", 1)[0]` — unchanged, re-verified this session.
For `switch.living_room_plug`, domain=`switch`. HA's own switch-domain
services are `switch.turn_on`/`switch.turn_off` — no attributes, no
payload fields, identical shape to the lock-domain services Smart Locks
already uses.

| Normalized | HA command | HA payload |
|---|---|---|
| `TURN_ON` | `"turn_on"` | `{}` |
| `TURN_OFF` | `"turn_off"` | `{}` |

### MQTT
`MqttConnector.send_command` calls `build_command_envelope(external_id,
command, payload)` (`mqtt_envelope.py`, unchanged, re-verified this
session), free-form as always. **This module defines its own two-command
vocabulary**, choosing `"turn_on"`/`"turn_off"` specifically to mirror
HA's own switch-domain service names — the same "mirror HA's service
names for cross-connector predictability" reasoning Smart Locks applied
choosing `"lock"`/`"unlock"`. (Smart Lighting's own MQTT vocabulary
defined `"turn_off"` alone plus a merged `"set_state"` for multi-attribute
changes; a switch has no attribute-merge case, so `"set_state"` does not
apply here — a bare `"turn_on"` is unambiguous for a device with exactly
one property.)

| Normalized | MQTT `command` | MQTT `args` |
|---|---|---|
| `TURN_ON` | `"turn_on"` | `{}` |
| `TURN_OFF` | `"turn_off"` | `{}` |

If MQTT switch control is ever found not to work through this existing
abstraction for a real device, that is a documented limitation to
raise, not a reason to invent a parallel protocol — none was found;
the existing `send_command`/envelope path already supports this
uninterpreted passthrough for any device type, switches included.

## 7. REST API

`/api/v1/switches/*`, matching the exact conventions established by
`routes/smart_locks.py`:

| Method | Path | Behavior |
|---|---|---|
| GET | `/switches` | List switches (`home_id`/`room_id` filters), DB-only, no live read. |
| GET | `/switches/{device_id}` | One switch's live state — 404 if unknown/not a switch. |
| POST | `/switches/{device_id}/on` | Turns the device on. |
| POST | `/switches/{device_id}/off` | Turns the device off. |

No separate `/state` route beyond `GET /{id}` (a switch has one binary
attribute, same reasoning Smart Locks already gave for skipping a
merged body-driven endpoint). No pairing endpoint — reuses `POST
/devices/{id}/pair` verbatim. `{data, meta}` envelope, `Depends(
get_current_session)` auth — identical to every other M12 route.

## 8. Tool Registry

Four tools, mirroring `smart_lock_tools.py`'s exact structure —
`agents/tools/smart_switch_tools.py`, `build_smart_switch_tools
(switches: SmartSwitchService) -> list[BaseTool]`:

| Tool | Wraps |
|---|---|
| `list_switches` | `list_switches()` |
| `get_switch_state` | `get_switch_state()` |
| `switch_on` | `turn_on()` |
| `switch_off` | `turn_off()` |

`get_switch_status` (a fifth, availability-only tool) was evaluated and
**not added** — `get_switch_state`'s payload is already small (§4, six
fields) and a separate terse tool would only earn its keep for a
larger payload the way Sensors' `get_sensor_value`/`get_sensor_status`
did against a bigger reading-shaped blob; here it would be a near-
duplicate, the same reasoning that dropped Sensors' redundant fifth
tool during that module's own design. All four call `SmartSwitchService`
only, never a connector directly.

**No energy-reading tool is added here.** `list_energy_devices` (§11)
is evaluated as an optional convenience and, per the approved
instruction, only added if it has clear architectural value; this
Logic Contract's own judgment (§11) is that it does not clear that bar
for this pass and is deferred, not built.

## 9. Permission behavior

**Mutations**: reuse the existing `PermissionModel`, `smart_home` scope
(the same shared scope every M12 module uses — switches are not
separately scoped), new principal `core:smart_switch` (mirroring
`core:smart_locks`/`core:sensors`'s naming), declared once at
construction, `PENDING` by default, granted through the existing
generic `POST /api/v1/plugins/{principal}/permissions/{scope}/grant`
route.

**Reads — resolved: ungated**, following the Smart Lighting/Smart Locks
precedent, **not** Sensors' precedent. Reasoning: Sensors gated reads
because *observing* is the entire product and several categories
(motion/presence/occupancy) can reveal who is home and when. A switch's
on/off state carries no comparable privacy weight — "is the porch light
plug powered" is exactly as low-stakes as "is the porch light on"
(already ungated) or "is the door locked" (already ungated). Applying
Sensors' stricter rule here would be inconsistent with the two
directly-analogous mutation-shaped modules and is not justified by any
new privacy consideration this device category actually introduces. No
new permission scope was created either way.

## 10. AgentOrchestrator integration

`switches` threaded through the exact same four-point pattern already
proven three times (`integrations`, `smart_lighting`, `smart_lock`,
`sensors`): `agents/tools/registry.py`'s `build_tool_registry`,
`AgentOrchestrator.__init__`/`.start()`, and `core/di/container.py`'s
`_build_agent_orchestrator` + `agent_orchestrator` provider. No new
orchestration path.

## 11. Energy-monitoring reuse through Sensors — do not duplicate

**Power Monitoring, Energy Monitoring and Load Monitoring are already
fully provided by the shipped `SensorService`, wherever the underlying
connector exposes the corresponding numeric sensor data.** HA's own
numeric `sensor`-domain device classes for this (`power`, `energy`,
`voltage`, `current`, `power_factor`, `apparent_power`,
`reactive_power`, and battery/solar/generator-flavored numeric
sensors) all normalize through `SensorService`'s existing, fully
generic numeric branch — no device_class-specific table exists there
(unlike binary sensors), so nothing about this slice needs to add one.
`SensorService.list_sensors()`/`get_sensor_state()` already return
these devices today; this Logic Contract adds no new service
(`EnergySensorService`/`EnergyTelemetryService`/`EnergyRegistry`/
`EnergyPollingService` are explicitly **not created**), no duplicate
normalization, and no duplicate connector handling.

**`list_energy_devices` convenience tool/filter: evaluated, not built
this pass.** It would filter `SensorService.list_sensors()`'s own
output by a known set of energy-related `device_class` strings — a
thin, optional filter over an existing call, never a new read path.
Deferred because the four existing sensor tools (`list_sensors` with
its `device_class` field already visible in the payload,
`get_sensor_value` for a specific reading) already cover the same need
today without it; adding a second entry point for the identical data
is not justified by a concrete gap, matching this task's own "only if
it has clear architectural value" bar. A future pass may add it purely
as a UX convenience without touching `SensorService` at all.

## 12. Deferred functionality

| Item | Deferred to | Why |
|---|---|---|
| Consumption History | Smart Home Memory (unstarted) | No time-series store exists anywhere in this codebase; the roadmap already assigns "Energy Usage History" to this module via `MemoryService.remember()`, not a new Energy-specific store. |
| Energy Dashboard / Analytics / Trends | Smart Home Analytics / M20A (unstarted) | Roadmap's own note: "surfaces through M20A's Analytics Platform dashboard once that milestone exists." |
| Energy Optimization, Automatic Power Saving, Energy-based Automations | Home Automation (unstarted) | Rule-engine-shaped; Home Automation's own module, not a device-control concern. |
| Load Scheduling, time-based energy automation | Home Automation + M7 Scheduler | M7's Scheduler phase remains unshipped (re-verified this session against `MASTER_ROADMAP.md`'s own status note, unchanged since the Home Automation audit). |

No placeholder backend architecture is added for any of these.

## 13. Error taxonomy

Matches `routes/smart_locks.py`'s own convention exactly (reads are
ungated here, so the Sensors-specific 400-vs-404 permission split does
not apply): `GET /switches/{id}` unknown/wrong-type device →
`ServiceError` → **404** (plain single-resource `GET` convention).
`POST .../on` / `POST .../off` — any `ServiceError` (unknown device,
wrong type, permission not granted) → **400**, the same
message-agnostic `pair_device` precedent Smart Locks already follows.
`CommandResult.success=False` is not an error — 200 with `success:
false`, identical framing to every other M12 command.

## 14. Security boundaries

- Every mutation requires the `smart_home` grant (§9); REST and tools
  both funnel through `SmartSwitchService`, the only caller of
  `_require_permission()`.
- `CommandResult.success=False` is always surfaced as `success: false`
  — never reported as if it succeeded, never raised in its place.
- No credential or connector-internal detail is ever included in any
  response — the payload shape (§4) carries only `Device` fields
  already public through `routes/smart_home.py`.
- No new pairing/handshake claim — a "paired" switch is exactly as
  weakly-verified as any other M12 device today.
- Unlike Smart Locks, no interactive-confirmation addition to
  `AgentSettings.confirm_required_tools` is made — a smart plug is not
  physically safety-relevant the way a door lock is; `switch_on`/
  `switch_off` carry the same risk profile as `set_light_state`, which
  also required no confirmation entry.

## 15. Future extension points

- `list_energy_devices` (§11) — a pure filter over `SensorService`,
  addable without touching this module's own architecture.
- Consumption History / Analytics / Optimization / Scheduling (§12) —
  each lands in its own already-designated module; this slice's
  `Device` rows (both the `switch` control entity and its sibling
  `sensor` entities) are exactly what those future modules will
  consume, unchanged.
- A `device_class`-aware label (e.g. `"outlet"` vs generic `"switch"`)
  could mirror Sensors' own discovery-time capture enhancement if a
  real need for that distinction ever arises; not needed for this
  slice's fixed on/off scope.
