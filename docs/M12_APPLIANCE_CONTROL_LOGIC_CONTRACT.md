# M12 Appliance Control — Core Appliance Slice — Logic Contract

Status: Approved for implementation (`JARVIS CORE — M12 APPLIANCE CONTROL
— CORE APPLIANCE SLICE: FANS + COVERS — IMPLEMENTATION APPROVED`). Base:
the shipped M12 Smart Locks (`docs/M12_SMART_LOCKS_LOGIC_CONTRACT.md`,
commits `b6b3f36`/`e16b61a`), Sensors (`docs/M12_SENSORS_LOGIC_CONTRACT.md`,
commits `9aff3f2`/`1fadb0a`) and Energy Management Core Slice (`docs/
M12_ENERGY_MANAGEMENT_LOGIC_CONTRACT.md`, commits `865532c`/`ac012c9`)
implementations. This is **not** the full Appliance Control module — it
is the Core Appliance Slice the post-Energy-Management audit (`JARVIS
CORE — M12 POST-ENERGY MANAGEMENT NEXT MODULE AUDIT`) identified as the
only genuinely low-complexity, zero-connector-change piece of a module
that spans seven structurally different HA domains.

## 1. Scope

**In scope**: Fan control (list, get, state, availability, turn on, turn
off) and Cover/Blind/Curtain control (list, get, state, availability,
open, close) for `device_type="appliance"` devices whose discovery-time
`metadata["domain"]` is `"fan"` or `"cover"` respectively. Structurally a
near-exact mirror of Smart Switches, doubled: two independent
binary-shaped capabilities sharing one `device_type` and one connector
mapping, distinguished at the service layer rather than at the domain
model.

**Explicitly not this slice's job, and not built**: Climate/AC, Media
Players/Smart TVs, Vacuum, Water Heater/Geysers, Humidifier, Smart
Pumps/Irrigation, Smart Kitchen Devices, fan percentage/speed control,
cover position control, any form of appliance-triggered automation,
scenes, or safety-critical behavior. See §18 for the full accounting.

## 2. Fan model

A fan is a `Device` row (`infrastructure/database/models.py`, Task Group
A, unmodified) with `device_type="appliance"` and
`metadata_json["domain"]="fan"` — no new ORM model, no new table, no new
`DEVICE_TYPES` value, matching every prior M12 module's "no new
persistence" precedent. The kickoff's own audit finding governs this
choice: `HomeAssistantConnector._DEVICE_DOMAINS` (`home_assistant.py:82`)
and `MqttConnector._HA_COMPONENT_DEVICE_TYPES` (`mqtt.py:163`) already
map HA's `fan` entity domain to `device_type="appliance"`, and both
connectors already write `metadata["domain"]="fan"` at discovery time
(`home_assistant.py:280`, `mqtt.py:538` — the same mechanism Sensors
reused for `binary_sensor` vs `sensor`, predating this slice). No new
`DEVICE_TYPES` entry (`"fan"`) is created — the kickoff explicitly
requires this not be introduced unless the architecture absolutely
requires it, and it does not: `metadata["domain"]` alone is sufficient.

## 3. Cover model

A cover (blind/curtain) is a `Device` row with `device_type="appliance"`
and `metadata_json["domain"]="cover"` — identical shape to §2, verified
against the same two connector mapping tables (`"cover": "appliance"` at
`home_assistant.py:83` / `mqtt.py:164`). No `DEVICE_TYPES` entry `"cover"`
is created, for the same reason as §2.

## 4. Domain discrimination

`ApplianceService` distinguishes a fan from a cover the same way
`SensorService._kind_for` distinguishes `binary_sensor` from `sensor`
(`sensor_service.py:103`): read `metadata_json["domain"]` off the
`Device` row, once, at the point a call needs to know. A private
`_domain_for(device) -> str | None` helper (parsing `metadata_json`
exactly like `SensorService._metadata`/`SmartSwitchService` do not need
to, since a switch has only one domain — this module's first case with
two) backs `_require_fan`/`_require_cover`, each of which raises
`ServiceError` if the device is not `device_type="appliance"` **or** its
`domain` does not match the expected capability — this is what makes
"wrong appliance domain" (a cover id passed to a fan endpoint) a real,
tested 400/404, not a silent misroute.

`SmartHomeService.list_devices` has no metadata filter (`smart_home_
service.py:422`), so `list_fans`/`list_covers` fetch every
`device_type="appliance"` device and filter by domain in Python — the
same shape `SensorService.list_sensors` would need if it ever had to
split by `kind` at the list level (it doesn't, today, since it returns
both kinds through one endpoint; this slice's two separate endpoints,
§12, make the split necessary here).

## 5. Capabilities

Exactly two mutating capabilities per device kind — `turn_on`/`turn_off`
for fans, `open`/`close` for covers — plus one state read each. No
capability negotiation, no per-device capability discovery, matching
Smart Switches' §3 "no capability negotiation" precedent exactly. Fan
percentage/speed and cover position are evaluated in §10 and explicitly
deferred, not silently omitted.

## 6. State model

Fan (`_fan_payload`, mirrors `SmartSwitchService._switch_payload` with
`on` in place of `on`, unchanged field-for-field):

```
{
  "id": str, "home_id": str, "room_id": str | None, "name": str,
  "status": str,          # Device.status -- connectivity lifecycle, unchanged meaning
  "manufacturer": str, "model": str, "external_id": str | None,
  "on": bool | None,      # None = unknown/unreadable
  "available": bool,
}
```

Cover (`_cover_payload`) — a fan has exactly one binary property, but a
cover's real-world state is not binary (a blind mid-travel is neither
"on" nor "off"), so this payload carries a closed-vocabulary `state`
string instead of a boolean, the same "detect at use, not fabricate"
discipline `SmartLockService._infer_locked` already applies to a
non-`True`/`False`/`None` raw reading:

```
{
  "id": str, "home_id": str, "room_id": str | None, "name": str,
  "status": str, "manufacturer": str, "model": str, "external_id": str | None,
  "state": str | None,    # one of "open"/"closed"/"opening"/"closing", or None = unknown/unreadable
  "available": bool,
}
```

## 7. Availability

Identical derivation to `SmartSwitchService.get_switch_state`/
`SmartLockService.get_lock_state`: `available = raw is not None and
raw.status.strip().lower() not in {"offline", "unavailable"}` — both the
raised-`ConnectivityError` case (connector unreachable) and the
connector-reported-down-status case, re-verified against both shipped
connectors this session (MQTT's `read_state()` returns `"offline"` when
its availability cache says so; HA reports `"unavailable"`). Applies
identically to fans and covers.

## 8. Fan commands

`FanCommand(enum.StrEnum)`: `TURN_ON = "turn_on"`, `TURN_OFF =
"turn_off"` — chosen to be HA's own real `fan`-domain service names
(`fan.turn_on`/`fan.turn_off`, the same public HA service scheme
`switch.turn_on`/`switch.turn_off` already proven for Smart Switches),
not guessed: `HomeAssistantConnector.send_command` (`home_assistant.py:
230`) derives `domain` from `external_id.split(".", 1)[0]` and calls
`POST /api/services/{domain}/{command}` with body `{"entity_id":
external_id, **payload}` — unchanged, re-verified this session, the same
generic mechanism every prior M12 mutation module already routes
through. For a fan entity (`fan.living_room_fan`), domain=`fan`, so
`command="turn_on"` reaches `POST /api/services/fan/turn_on` — HA's real
endpoint for turning a fan on, no payload fields.

| Normalized | HA command | HA payload |
|---|---|---|
| `TURN_ON` | `"turn_on"` | `{}` |
| `TURN_OFF` | `"turn_off"` | `{}` |

MQTT: no fan consumer of `mqtt_envelope.py`'s free-form command/args
existed before this slice, so this module **defines** a JARVIS-native
vocabulary — mirroring HA's own service names for cross-connector
predictability, the same choice Smart Locks/Smart Switches already made
for their own MQTT vocabularies. Reuses the identical `"turn_on"`/
`"turn_off"` literals (no per-connector difference), verified against
the shipped `MqttConnector.send_command`/`build_command_envelope`
(`mqtt.py:460`) this session.

| Normalized | MQTT `command` | MQTT `args` |
|---|---|---|
| `TURN_ON` | `"turn_on"` | `{}` |
| `TURN_OFF` | `"turn_off"` | `{}` |

## 9. Cover commands

`CoverCommand(enum.StrEnum)`: `OPEN = "open_cover"`, `CLOSE =
"close_cover"` — HA's own real `cover`-domain service names
(`cover.open_cover`/`cover.close_cover`), reached through the identical
generic `send_command` mechanism as §8, no payload fields. `cover.
stop_cover` is a real, distinct HA service but is **not** in this
slice's approved scope (open/close only — see §1); no `STOP` command
value is defined.

| Normalized | HA command | HA payload |
|---|---|---|
| `OPEN` | `"open_cover"` | `{}` |
| `CLOSE` | `"close_cover"` | `{}` |

MQTT: same reasoning as §8 — a new, defined-not-guessed JARVIS-native
vocabulary reusing the identical `"open_cover"`/`"close_cover"` literals
for cross-connector predictability.

| Normalized | MQTT `command` | MQTT `args` |
|---|---|---|
| `OPEN` | `"open_cover"` | `{}` |
| `CLOSE` | `"close_cover"` | `{}` |

## 10. Position handling (fan percentage, cover position)

Both evaluated per the kickoff's explicit instruction; both **deferred**,
not blocked and not silently omitted.

**Fan `set_percentage`** exists as a real HA fan-domain service
(`fan.set_percentage`, payload `{"percentage": int}`). The existing
architecture *could* carry it — `SmartLightingService`'s own translators
already prove a "merge several changed attributes into one wire call"
shape (brightness alongside on/off) works in this codebase — so this is
not an architectural blocker. It is deferred because the approved Core
Slice scope (§1) is fixed to binary on/off, and adding a graduated
numeric command now would expand the wire vocabulary, REST surface and
tool surface beyond what was approved for this pass — exactly the
"do not over-expand the first implementation" instruction. A future,
separately-scoped pass can add it by following Smart Lighting's own
merge-translator template (§20).

**Cover `set_cover_position`** exists as a real HA cover-domain service
(`cover.set_cover_position`, payload `{"position": int}`, 0–100). Same
finding as fan percentage: architecturally supportable via the Lighting
merge-translator template, deliberately deferred to keep this slice to
open/close only, for the identical "do not over-expand" reasoning. No
`position` field is added to §6's cover payload in this slice — reading
a value this module cannot yet act on would be a half-finished surface,
not a genuine simplification.

## 11. Connector mapping

**Verified against the current working tree this session** (clean tree,
no drift since Energy Management shipped): both `HomeAssistantConnector.
_DEVICE_DOMAINS` (`home_assistant.py:74`) and `MqttConnector.
_HA_COMPONENT_DEVICE_TYPES` (`mqtt.py:155`) already map `"fan":
"appliance"` and `"cover": "appliance"`, unchanged, already shipped in
Task Group B. **Zero connector code changes are required for this
slice** — both discovery-time sub-kind disambiguation (§4's
`metadata["domain"]`, already captured for every entity, not only
sensors — `home_assistant.py:280`/`mqtt.py:538`) and command dispatch
(§8/§9's generic domain-derived `send_command`) already work for `fan`
and `cover` exactly as they do for `switch`/`lock`/`light`. This was the
central, evidence-grounded finding of the approving audit, and is
reconfirmed here rather than assumed.

## 12. REST API

`/api/v1/appliances/*`, split into two sibling resource collections
rather than one generic `/appliances/{id}/command` endpoint — a fan and
a cover have genuinely different command vocabularies (§8 vs §9), and a
single generic verb endpoint would need capability negotiation to know
which vocabulary applies to a given id, which §5 explicitly rules out.
Matches the exact conventions established by `routes/smart_switches.py`
per collection:

| Method | Path | Behavior |
|---|---|---|
| GET | `/appliances/fans` | List fans (`home_id`/`room_id` filters), DB-only, no live read. |
| GET | `/appliances/fans/{device_id}` | One fan's live state — 404 if unknown/not a fan. |
| POST | `/appliances/fans/{device_id}/on` | Turns the fan on. |
| POST | `/appliances/fans/{device_id}/off` | Turns the fan off. |
| GET | `/appliances/covers` | List covers (`home_id`/`room_id` filters), DB-only, no live read. |
| GET | `/appliances/covers/{device_id}` | One cover's live state — 404 if unknown/not a cover. |
| POST | `/appliances/covers/{device_id}/open` | Opens the cover. |
| POST | `/appliances/covers/{device_id}/close` | Closes the cover. |

`{data, meta}` envelope, `Depends(get_current_session)` auth — identical
to every other M12 route. No pairing endpoint — reuses `POST
/devices/{id}/pair` verbatim, same as every prior module.

## 13. Tool Registry

Eight tools, mirroring `smart_switch_tools.py`'s exact structure per
capability — `agents/tools/appliance_tools.py`, `build_appliance_tools
(appliances: ApplianceService) -> list[BaseTool]`:

| Tool | Wraps |
|---|---|
| `list_fans` | `list_fans()` |
| `get_fan_state` | `get_fan_state()` |
| `fan_on` | `fan_on()` |
| `fan_off` | `fan_off()` |
| `list_covers` | `list_covers()` |
| `get_cover_state` | `get_cover_state()` |
| `cover_open` | `cover_open()` |
| `cover_close` | `cover_close()` |

All eight call `ApplianceService` only, never a connector directly. No
availability-only terse tool is added for either capability — same
reasoning Smart Switches already gave for skipping one: both state
payloads (§6) are already small.

## 14. Permission behavior

**Mutations**: reuse the existing `PermissionModel`, `smart_home` scope
(the same shared scope every M12 module uses), one new principal
`core:appliances` covering both fan and cover commands — one principal
per module, mirroring how `core:smart_switch` covers the whole Energy
Management Core Slice rather than splitting per device kind. Declared
once at construction, `PENDING` by default, granted through the
existing generic `POST /api/v1/plugins/{principal}/permissions/
{scope}/grant` route.

**Reads — resolved: ungated**, following the Smart Lighting/Smart
Locks/Smart Switches precedent, **not** Sensors' precedent. Reasoning:
Sensors gated reads because several sensor categories
(motion/presence/occupancy) can reveal who is home and when — the
observation itself is privacy-sensitive. Whether a fan is spinning or a
blind is open carries no comparable privacy weight; "is the fan on" is
exactly as low-stakes as "is the switch on" (already ungated) or "is the
door locked" (already ungated, and arguably more security-sensitive than
either fan or cover state). No new permission scope is created either
way.

## 15. AgentOrchestrator integration

`appliances` threaded through the exact same four-point pattern already
proven four times (`integrations`, `smart_lighting`, `smart_lock`,
`sensors`, `smart_switch`): `agents/tools/registry.py`'s
`build_tool_registry`, `AgentOrchestrator.__init__`/`.start()`, and
`core/di/container.py`'s `_build_agent_orchestrator` + `agent_
orchestrator` provider. No new orchestration path, no new LLM logic, no
new planner.

## 16. Error taxonomy

Matches `routes/smart_switches.py`'s own convention exactly (reads are
ungated here, so the Sensors-specific 400-vs-404 permission split does
not apply): `GET /appliances/fans/{id}` (or `.../covers/{id}`)
unknown/wrong-type/wrong-domain device → `ServiceError` → **404** (plain
single-resource `GET` convention — a cover id given to the fans route,
or vice versa, is "not a fan"/"not a cover", handled identically to
"not a switch"). `POST .../on` / `.../off` / `.../open` / `.../close` —
any `ServiceError` (unknown device, wrong type, wrong domain, permission
not granted) → **400**. `CommandResult.success=False` is not an error —
200 with `success: false`, identical framing to every other M12 command.

## 17. Security boundaries

- Every mutation requires the `smart_home` grant (§14); REST and tools
  both funnel through `ApplianceService`, the only caller of
  `_require_permission()`.
- `CommandResult.success=False` is always surfaced as `success: false`
  — never reported as if it succeeded, never raised in its place.
- No credential or connector-internal detail is ever included in any
  response — the payload shapes (§6) carry only `Device` fields already
  public through `routes/smart_home.py`.
- No interactive-confirmation addition to `AgentSettings.confirm_
  required_tools` is made for `fan_on`/`fan_off`/`cover_open`/`cover_
  close` — neither carries the physical-safety weight `unlock_device`
  does; the risk profile matches `switch_on`/`switch_off`, which also
  required no confirmation entry. No safety-critical fan behavior
  (emergency ventilation), emergency cover behavior, panic mode or
  vacation mode is implemented — those remain out of scope for Security
  & Safety/Home Automation, per the kickoff's own boundary.
- No automation trigger of any kind (motion→fan, temperature→fan,
  sunrise→cover, schedule→cover) is implemented — Home Automation's own
  job, and still blocked on the event-publishing gap this session's
  audit surfaced (none of Lighting/Locks/Switches' commands publish an
  event today; this slice does not change that).

## 18. Deferred appliance categories

| Item | Deferred to | Why |
|---|---|---|
| Climate / AC | Future Appliance Control slice | Own HA domain (`climate`), own `device_type="thermostat"`, own multi-attribute vocabulary (`set_temperature`/`set_hvac_mode`/`set_fan_mode`) — genuinely different shape from fan/cover's binary commands, not a drop-in extension of this service. |
| Media Players / Smart TVs | Future Appliance Control slice | `media_player` domain's vocabulary (play/pause/volume/source) has no binary-command precedent anywhere in M12 today. |
| Vacuum | Future Appliance Control slice | `vacuum` domain's vocabulary (start/stop/return_to_base) is a distinct, non-binary command set. |
| Water Heater / Geysers | Future Appliance Control slice | `water_heater` domain's vocabulary (`set_temperature`/`set_operation_mode`) mirrors Climate's complexity, not Fan/Cover's. |
| Humidifier | Future Appliance Control slice | Closest in shape to Switches (on/off + `set_humidity`), but `set_humidity` is graduated control (§10's reasoning applies) — deferred with the rest rather than special-cased in. |
| Smart Pumps / Irrigation | Blocked on connector mapping | HA's `valve` domain — the natural mapping for irrigation valves — currently maps to `device_type="other"`, **not** `"appliance"` (`home_assistant.py:91`/`mqtt.py:172`, re-verified this session, unchanged). Supporting it as a real appliance category would need a `DEVICE_TYPES`/domain-map change this slice was not asked to make. |
| Smart Kitchen Devices | Blocked — no consistent domain model | No single HA/MQTT domain represents "kitchen appliance" as a category; vendor-specific integrations expose these through `switch`/`sensor`/`select`/vendor-custom domains inconsistently. No normalized model exists to build against without guessing one. |

No placeholder backend architecture is added for any of these.

## 19. Connector limitations

- `valve` (irrigation) and `siren`/`select`/`number`/`alarm_control_
  panel` all map to `device_type="other"`, not `"appliance"` — a real,
  documented gap in today's connector mapping, not something this
  slice's service layer can work around.
- No percentage/position control (§10) — a real, deliberate scope
  boundary, not a connector limitation; the connectors themselves can
  carry `fan.set_percentage`/`cover.set_cover_position` payloads exactly
  as they carry `light.turn_on`'s brightness attribute today.
- MQTT fan/cover control uses a newly-*defined* (not previously
  existing) JARVIS-native vocabulary, per §8/§9 — real devices speaking
  a different MQTT schema for fan/cover control (e.g. Zigbee2MQTT's own
  device-specific payloads outside HA Discovery) are not addressed by
  this slice; HA MQTT Discovery-sourced fan/cover devices work today
  because discovery already normalizes them into the same `Device`
  model this service reads.

## 20. Future extension strategy

- Fan percentage / cover position (§10) as separately-scoped follow-on
  slices, each reusing `SmartLightingService`'s existing merge-
  translator template (multiple changed attributes → one wire call)
  rather than inventing a new pattern.
- Climate, media_player, vacuum, water_heater, humidifier (§18) as
  independent future Appliance Control slices, each requiring its own
  Logic Contract and its own normalized command model — never folded
  into `ApplianceService` as generic capability flags, matching the
  kickoff's explicit "do not create a large generic ApplianceService
  abstraction merely for future categories" instruction.
- Smart Pumps/Irrigation unblocks only if a future task group
  deliberately extends the `valve` domain mapping (`device_type="other"`
  → a new or reused category) with its own justification — not a side
  effect of this slice.
- A `device_class`-aware label refinement (mirroring Sensors' own
  discovery-time capture enhancement) could distinguish sub-flavors of
  fan/cover (e.g. `device_class="awning"` vs `"blind"` vs `"curtain"`
  within the `cover` domain) if a real need for that distinction ever
  arises; not needed for this slice's fixed open/close scope.
