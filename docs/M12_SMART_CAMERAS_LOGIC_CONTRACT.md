# M12 Smart Cameras — Core Camera Slice — Logic Contract

Status: **Implemented this session** (Task Group HH). Opens M12's
previously entirely-unstarted Smart Cameras module with a deliberately
narrow MVP, following the exact "Core Slice" pattern every other M12
device-category module used to open (Core Appliance Slice, Core Energy
Slice, Read-Only Alert/Status Slice, etc.): the generic, connector-
agnostic surface first, with every genuinely infrastructure-heavy item
explicitly and permanently deferred, not half-built.

## 1. Scope

Normalized read (state, availability, motion-detection status) and two
independent zero-payload mutations (on/off, motion-detection toggle)
for `device_type="camera"` devices, over REST and as agent tools,
converging on the same `ConnectivityService.send_command`/
`read_raw_state` chokepoints every other M12 module already uses.

**Explicitly not this module's job**: Live Streaming, Recording
Management, Event Recording, Snapshot Capture, Motion/Person/Package/
Vehicle Detection (the ML-driven kind), and Face Recognition — see §9.

## 2. Device model and identity — confirmed, not re-decided

`device_type="camera"` is **already reserved** in `DEVICE_TYPES`
(`domain/smart_home/models.py:54`) and **already mapped** by both
connectors — `HomeAssistantConnector`'s `_DEVICE_DOMAINS`
(`home_assistant.py:79`, `"camera": "camera"`) and `MqttConnector`'s
equivalent (`mqtt.py:207`) both already route a `camera`-domain entity
to `device_type="camera"` today. **Zero connector changes required** —
this is the same "the mapping already exists, only the service layer
is missing" condition every prior M12 module-opening slice (Water
Heater, Media Player, Vacuum + Humidifier) started from.

A camera is a `Device` row (unmodified), discriminated by
`device_type` alone (no domain-discrimination needed — unlike Fan/
Cover, a camera has no sibling category sharing `device_type="camera"`),
mirroring `SmartLockService`/`SensorService`'s exact shape rather than
`ApplianceService`'s.

## 3. External verification (this session, via live web search and
direct GitHub source read of `home-assistant/core`'s `camera/
__init__.py` and `camera/const.py` — not recalled from training data)

- **`camera.turn_on`/`camera.turn_off`** — real, generic HA services.
  Zero payload.
- **`camera.enable_motion_detection`/`camera.disable_motion_detection`**
  — real, generic HA services. Zero payload. Not every camera
  integration implements them (HA itself documents this), so a
  `ConnectivityError`/failed `CommandResult` from an unsupporting
  device is an ordinary, expected outcome — never specially detected
  or pre-validated against a capability flag this repository has no
  way to read reliably.
- **Camera `state`** is itself the entity's live status —
  `CameraState` enum: `idle` / `recording` / `streaming` (from HA
  core's own `const.py`), plus `unavailable`/`offline` for a downed
  entity. This is an **open pass-through**, mirroring Vacuum's
  identical "no closed vocabulary, HA's own state string is read as-is"
  treatment — not Cover's small fixed set, since a custom or unlisted
  integration could report something else.
  [Camera — Home Assistant](https://www.home-assistant.io/integrations/camera/)
- **Read attribute: `motion_detection`** (boolean) — HA's own
  `CameraEntityStateAttribute.MOTION_DETECTION = "motion_detection"`
  constant, confirmed directly against `home-assistant/core`'s
  `camera/const.py`. **Conditionally present**: HA's own
  `state_attributes` property only adds this key when
  `motion_detection_enabled` is truthy (`if motion_detection_enabled :=
  self.motion_detection_enabled: attrs[...] = ...`) — confirmed
  directly against `camera/__init__.py`'s source. This module therefore
  reads it as `bool | None` (present-and-`True` → `True`; **absent** →
  `None`, meaning "unknown/unsupported", not "confirmed off" — the
  same "never fabricate a `False` the connector didn't actually report"
  discipline `ThermostatService`/`MediaPlayerService` already apply to
  every optional attribute).
- **`camera.snapshot`** (parameter `filename`, a full path on the *HA
  host's own filesystem*, subject to HA's directory-allowlist config) —
  confirmed to require a server-side file write target, not a
  self-contained value this API could proxy or return as bytes without
  inventing a new storage/security model. This is why Snapshot Capture
  is deferred (§9), not merely unresearched.

## 4. Architecture decision

**One new service, `CameraService`, mirroring `SmartLockService`'s
shape exactly**: single `device_type`, no domain discrimination, two
independent zero-payload commands dispatched through one `_send`
helper. Not an `ApplianceService`/`VacuumHumidifierService` extension
— cameras are their own reserved `device_type`, the same reasoning
`ThermostatService` already established for its own reserved type.

**Reads are permission-gated, following `SensorService`'s precedent —
not the ungated-reads convention Lock/Switch/Appliance/Thermostat use.**
Whether a camera is currently recording/streaming, and whether its
motion detection is armed, is itself security- and privacy-sensitive
information — arguably more so than a generic sensor reading, since it
reveals the state of a home's own surveillance posture. The same
`smart_home` scope is reused (no new scope invented), under a new
principal `core:cameras`, declared once at construction like every
other M12 principal.

## 5. Normalized read model

```
{
  "id": str,
  "home_id": str,
  "room_id": str | None,
  "name": str,
  "status": str,             # Device.status -- connectivity lifecycle,
                              # NOT the camera's own idle/recording/
                              # streaming state.
  "manufacturer": str,
  "model": str,
  "external_id": str | None,
  "state": str | None,       # open pass-through: "idle"/"recording"/
                              # "streaming"/whatever HA reports; None
                              # when unavailable or unread.
  "motion_detection": bool | None,  # None = unknown/unsupported/
                                     # unreachable, never a fabricated
                                     # False.
  "available": bool,
}
```

## 6. Write model

- `turn_on(device_id)` / `turn_off(device_id)` — `camera.turn_on`/
  `camera.turn_off`, zero payload.
- `enable_motion_detection(device_id)` / `disable_motion_detection
  (device_id)` — `camera.enable_motion_detection`/
  `camera.disable_motion_detection`, zero payload.

No merged mutation method — like `SmartLockService`, these are four
independent, single-purpose verbs, not attributes that combine.

## 7. HA / MQTT translation

Identical shape to `SmartLockService._translate_home_assistant`/
`_translate_mqtt`: a `CameraCommand` `StrEnum` (`TURN_ON`, `TURN_OFF`,
`ENABLE_MOTION_DETECTION`, `DISABLE_MOTION_DETECTION`), each translated
to `(command.value, {})` by both connectors — HA's own generic
dispatcher already routes a `camera.*` entity correctly
(`domain = external_id.split(".", 1)[0]`); MQTT gets the identical
JARVIS-native vocabulary every prior module's first MQTT consumer
defines for itself (mirroring HA's own service names for cross-
connector predictability).

## 8. Permission / confirmation

- New principal `core:cameras`, same `smart_home` scope. **All
  operations, including reads, require the grant** — see §4.
- `turn_off`/`disable_motion_detection` are added to
  `AgentSettings.confirm_required_tools` (the existing mechanism, not a
  new one) — both **reduce** a home's surveillance posture, the same
  risk tier `unlock_device`/`turn_siren_on`/`disarm` already occupy.
  `turn_on`/`enable_motion_detection` (which **increase** it) need no
  confirmation, mirroring `lock_device`/`arm_home` never needing it
  either.

## 9. Explicitly deferred scope (explicit, no placeholders)

| Item | Why deferred |
|---|---|
| Live Streaming | Serving or proxying an actual video/RTSP stream through this API is new transport infrastructure this repository has never built for any module; a URL-only "proxy" would still need a security/access model this contract does not invent. |
| Recording Management, Event Recording, Snapshot Capture | `camera.record`/`camera.snapshot` write to a file path on the **HA host's own filesystem** (§3) — proxying, storing, or serving that binary data needs new storage schema and a security design (path handling, retention, access control) no existing M12 module needed; the same class of gap Smart Lock guest/temporary access codes hit this session. |
| Motion/Person/Package/Vehicle Detection (the ML/CV kind) | Distinct from the `motion_detection` **enabled/disabled** boolean this slice reads (an on/off toggle, not a detection *event* feed) — no event-publishing pipeline for camera detection events exists, and building person/package/vehicle classification is a computer-vision capability this repository does not have. |
| Face Recognition | Named in the roadmap itself as "optional, off by default" for privacy reasons — a dedicated, separately-evidenced privacy/security design is required before any code, not assumed here. |
| Camera Integration (device discovery/pairing specifics) | Already works today via the existing generic `ConnectivityService.run_discovery`/`SmartHomeService.pair_device` — no new discovery mechanism needed or built. |

**No placeholder backend architecture is added for any of these** — no
unused enum members, no reserved payload fields, no dead parameters,
no schema for binary storage.

## 10. Database / schema decision

**None required.** No new table, no new column, no `DEVICE_TYPES`
addition (already reserved), no `MemoryService`/Analytics/scheduler/
Home Automation dependency — identical conclusion to every prior M12
module. **Not wired into `SmartHomeMemoryService`** — that service's
own Device-Category Expansion Slice permanently excluded Sensor/Lock
snapshots on privacy/security grounds; a camera's live surveillance
state is at least as privacy-sensitive, so it is excluded the same way,
not added as a tenth category.

**Not wired into `SecurityService`** — that service's own
`trigger_panic_mode` docstring already states it never touches
cameras, an explicit carve-out recorded before this slice existed.

## 11. REST contract

- `GET /api/v1/cameras` — list, `{data: [...], meta: {count}}`.
- `GET /api/v1/cameras/{device_id}` — single camera, 404 on unknown/
  wrong-type (mirrors `routes/sensors.py`'s exact status-code
  convention, since reads are gated the same way).
- `POST /api/v1/cameras/{device_id}/turn_on`
- `POST /api/v1/cameras/{device_id}/turn_off`
- `POST /api/v1/cameras/{device_id}/enable_motion_detection`
- `POST /api/v1/cameras/{device_id}/disable_motion_detection`

All under `Depends(get_current_session)`, the same Bearer-session
pattern every M9-and-later resource router uses.

## 12. Agent tools

Six tools: `list_cameras`, `get_camera_state`, `camera_turn_on`,
`camera_turn_off`, `enable_camera_motion_detection`,
`disable_camera_motion_detection` — one tool per verb, mirroring
`smart_lock_tools.py`'s exact one-tool-per-command shape (a camera has
independent verbs, not attributes that combine, so no merged mutation
tool). `camera_turn_off`/`disable_camera_motion_detection` are the two
tool names added to `confirm_required_tools` (§8).

## 13. Test strategy

New `test_m12_camera_service.py`, `test_m12_cameras_route.py`,
`test_m12_camera_tools.py`, mirroring `test_m12_smart_locks_service.py`
et al.'s established shape: domain/device-type safety, permission
gating on **every** operation including reads (the one structural
difference from Lock/Switch), state normalization (open pass-through,
unavailable handling, `motion_detection`'s "absent means None, not
False" rule specifically), zero-payload command dispatch for all four
verbs, HA/MQTT translator unit tests, REST route tests (401/403 without
session, 400 without grant on every operation including `GET`, 404 for
unknown/wrong-type), and agent-tool tests including confirmation-
metadata pins for the two gated tools.

## 14. Non-goals

Everything in §9. No connector change, no `DEVICE_TYPES` change
(already reserved), no new permission scope (reuses `smart_home`), no
new database schema.

## 15. Acceptance criteria

- `camera.turn_on`/`turn_off`/`enable_motion_detection`/
  `disable_motion_detection` names, the `motion_detection` attribute's
  exact key and its "conditionally present" read semantics, and
  `camera.snapshot`'s file-path requirement, all externally verified
  this session (§3), not recalled — the `motion_detection` finding
  confirmed directly against `home-assistant/core` source, not a blog
  or forum post.
- Reads permission-gated like Sensors, not ungated like Lock/Switch/
  Appliance — a deliberate, justified departure (§4), not a copy-paste
  oversight.
- `motion_detection` is `None` (not `False`) when the device does not
  report it.
- `turn_off`/`disable_motion_detection` added to
  `confirm_required_tools`; `turn_on`/`enable_motion_detection` are not.
- Zero connector, `DEVICE_TYPES`, or `CONNECTOR_TYPES` changes.
- Not wired into `SmartHomeMemoryService` or `SecurityService`.
- Live Streaming/Recording/Snapshot/ML Detection/Face Recognition
  remain entirely unbuilt — no placeholder code of any kind.
