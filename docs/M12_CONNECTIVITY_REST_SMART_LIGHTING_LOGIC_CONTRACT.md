# Connectivity REST Surface + Smart Lighting — Module Logic Contract

**Milestone:** M12 — Smart Home & IoT Platform (two units of work: the
Connectivity Layer's REST surface, and Smart Lighting, M12's first
device-category module).
**Status:** Written before implementation, per `MASTER_ROADMAP.md` §4's
binding rule: *"No implementation may begin until its module's Logic
Contract is complete."* Nothing described here is implemented yet.
**Scope of this document:** (A) a thin REST layer over the already-shipped
`ConnectivityService`; (B) Smart Lighting, riding that layer and the
already-shipped Smart Home Core (`SmartHomeService`) unchanged.
**Authoritative inputs:** `docs/CONNECTIVITY_LAYER_LOGIC_CONTRACT.md`
(the connector layer this document extends, never re-litigates),
`MASTER_ROADMAP.md`'s M12 section and its Smart Lighting bullet list,
and this session's own Phase 0 audit of the real, current
`ConnectivityService`/`SmartHomeService`/connector/route/test code
(cited by file:line throughout).

This follows the same 15-field list `docs/CONNECTIVITY_LAYER_LOGIC_CONTRACT.md`
uses, for the same reason it does (`MASTER_ROADMAP.md` §4 / `ARCHITECTURE.md`
§10).

---

## Purpose

Close two real gaps the Phase 0 audit confirmed, not assumed:

1. `ConnectivityService` (`services/connectivity_service.py`) is fully
   built, fully tested, and has **zero REST exposure** — no route file
   anywhere calls `connect`, `disconnect`, `run_discovery`,
   `refresh_device_state`, or `send_command`. It is real but currently
   unreachable by anything outside a Python test.
2. Smart Lighting is the first of M12's 13 unstarted device-category
   modules, and the only one with an existing, real substrate
   (Connectivity Layer + Smart Home Core) ready to ride today.

## Scope

**In scope:**
- A new REST route file exposing exactly the methods `ConnectivityService`
  already has — no more.
- A new, thin Smart Lighting orchestration layer translating a small,
  normalized lighting-command vocabulary into calls against the
  *existing* `ConnectivityService.send_command` chokepoint, plus REST
  routes over it.
- Room/Group lighting control, by fanning the same normalized command
  out over `SmartHomeService`'s *existing* room/group membership
  queries — no new grouping concept.
- Lighting scenes, scoped to **applying a stored set of target light
  states** (a device-state operation) — not a rule/trigger engine.

**Out of scope (see Non-goals for why):** connector-level state-machine
or permission-model changes (owned by `CONNECTIVITY_LAYER_LOGIC_CONTRACT.md`,
unchanged here), motion/sunrise-sunset/time-based automation triggers,
any new registry/connector abstraction/credential system/permission
system/tool-execution system, real device capability-schema discovery
beyond what a connector already reports, a real pairing handshake.

## Non-goals

- **No second connector abstraction, provider registry, credential
  store, or permission system.** Every new method in this document
  calls into exactly one of: `ConnectivityService`, `SmartHomeService`,
  `ConnectorFactoryRegistry`, `PermissionModel` — all pre-existing,
  none re-implemented.
- **No new "pairing" endpoint or handshake.** `POST /devices/{id}/pair`
  already exists (`infrastructure/api/routes/smart_home.py:441`) and
  already performs the only pairing this codebase defines — a status
  transition with no protocol handshake, by Task Group A's own
  explicit, documented design
  (`smart_home_service.py:386-393`). This document does not add a
  second, "more real" pairing flow on top.
- **No rule/trigger engine.** The roadmap's own Smart Lighting bullets
  (`MASTER_ROADMAP.md:3672-3682`) include "Adaptive Lighting," "Motion
  Activated Lighting," and "Sunrise / Sunset Automation" — these are
  automation-*trigger*-shaped, and M12's own module list separately
  names a later, still-unstarted **Home Automation** module
  (`MASTER_ROADMAP.md:3634`) as "rule engine, event/time/sensor/
  presence-based... multi-step, scene, emergency." The roadmap text
  does not resolve which module owns these three bullets. **Resolution
  (this document's own scoping decision, stated explicitly rather than
  silently assumed):** Smart Lighting owns the device-level primitives
  those triggers would eventually call (on/off, brightness, color,
  scene *application*) — it does not itself schedule, watch a motion
  sensor, or compute sunrise/sunset. Home Automation, when it exists,
  consumes Smart Lighting's primitives; Smart Lighting does not
  pre-build a rule engine to anticipate it. This mirrors the existing
  Connectivity Layer contract's own precedent of explicitly disclaiming
  "interpreting what a command means" as out of scope
  (`CONNECTIVITY_LAYER_LOGIC_CONTRACT.md:43-45`).
- **No capability-schema discovery.** Neither `IDeviceConnector` nor
  either real connector returns a supported-commands/attributes schema
  for a device (confirmed absent, Phase 0 audit §1/§3). Smart Lighting
  does not invent one; it defines its own fixed, closed command
  vocabulary (below) and validates a device supports lighting by
  `Device.device_type == "light"` only — the same coarse-but-honest
  validation approach `DEVICE_TYPES`/`CONNECTOR_TYPES` already use
  elsewhere in this codebase.

## Architecture boundary

```
REST (new)                          REST (new)
  │                                    │
  ▼                                    ▼
ConnectivityRouter               SmartLightingRouter
  │  (thin: 1 call each)             │  (thin: normalize → 1 call)
  ▼                                    ▼
ConnectivityService (existing,   SmartLightingService (new, thin
UNCHANGED)                       orchestration only)
  │                                    │
  │                          ┌─────────┼─────────┐
  │                          ▼         ▼          ▼
  │                 SmartHomeService  ConnectivityService  (both existing,
  │                 (existing,        (existing, UNCHANGED — same
  │                 UNCHANGED)        .send_command chokepoint every
  │                                   other M12 caller uses)
  ▼
IDeviceConnector (existing, UNCHANGED)
  ├── HomeAssistantConnector (existing)
  └── MqttConnector (existing)
```

`SmartLightingService` is new but is **not** "another Smart Home
service" in the sense the task brief forbids: it owns no rows, no
registry, and no connector — it is a translation/orchestration layer
exactly analogous to how M11's `IntegrationService` orchestrated
`MCPProviderManager`/`MCPAuthManager` without becoming a second
provider manager. Concretely, it does two things neither existing
service does today: (1) validates a target device is `device_type ==
"light"` before proceeding; (2) maps a normalized `LightCommand` +
parameters into the connector-specific `command`/`payload` shape
`ConnectivityService.send_command` already expects (see Business
logic) — then calls that existing method verbatim. It never talks to
a connector, a database session, or an event bus directly.

## Responsibilities

**Connectivity REST surface:**
- Expose `ConnectivityService.connected_types` + `ConnectorFactoryRegistry.
  registered_types` as one merged, read-only connector list.
- Expose `connect`/`disconnect`/`run_discovery`/`refresh_device_state`/
  `send_command` as routes, each a direct, un-embellished call to the
  existing method of the same behavior.

**Smart Lighting:**
- Own a fixed, closed vocabulary of normalized light commands and the
  per-`connector_type` translation into wire-level `command`/`payload`.
- Own scene storage (a named set of target light states) and scene
  *application* (replaying those targets through the same command
  path) — not scheduling or triggering.
- Fan a command out across a room or device group by reusing
  `SmartHomeService.list_devices(room_id=...)` /
  `list_group_members(group_id)` — filtered to `device_type == "light"`
  — never a new membership concept.

**Explicitly not this document's responsibility** (mirroring
`CONNECTIVITY_LAYER_LOGIC_CONTRACT.md:43-51`'s own pattern): automation
triggers (Home Automation module); `safety_critical` gating (M4's
`SafetyValidator`/`UndoManager`, still not wired to `send_command` by
anything — this document does not wire it either, consistent with the
connector contract's own explicit deferral); real capability discovery
(no module owns this yet); a real device-pairing handshake (none
exists anywhere in this codebase to extend).

## Business logic

- **Normalized command vocabulary** (`LightCommand`, closed enum):
  `TURN_ON`, `TURN_OFF`, `SET_BRIGHTNESS` (0-100 int), `SET_COLOR_TEMP`
  (Kelvin int, vendor-range-clamped per connector where known),
  `SET_COLOR` (RGB triple). This is the *entire* vocabulary for this
  pass — matching the roadmap's own bullet list minus the
  automation-trigger items scoped out above; scenes/group/room are
  operations *over* this vocabulary, not additional commands.
- **Per-connector translation** (new, small, explicit mapping table —
  not a new abstraction):
  - `connector_type == "home_assistant"`: `TURN_ON`/`TURN_OFF` → HA
    service calls `light.turn_on`/`light.turn_off`
    (`HomeAssistantConnector.send_command` already posts
    `command` as the HA service name, per Phase 0 audit §3);
    `SET_BRIGHTNESS`/`SET_COLOR_TEMP`/`SET_COLOR` → a single
    `light.turn_on` call with the corresponding HA service-call field
    (`brightness`, `color_temp`, `rgb_color`) in `payload` — HA's own
    documented convention, not invented here.
  - `connector_type == "mqtt"`: mapped to whatever
    `MqttEnvelope`/HA-MQTT-Discovery state-topic JSON convention the
    existing `MqttConnector` already parses for discovery
    (`_HA_COMPONENT_DEVICE_TYPES`, Phase 0 audit §3). **Open item,
    flagged rather than guessed:** the exact outbound payload field
    names (state/brightness/color keys) must be confirmed against
    `mqtt_envelope.py`'s real structure at implementation time before
    the MQTT branch of this mapping is written — this document commits
    to the *shape* of the solution (a small, explicit per-connector-type
    table, same pattern as the HA branch) without guessing byte-level
    field names it has not verified.
- A light command always targets a real `Device` row
  (`device_type == "light"`, `status == "paired"`) resolved through
  `SmartHomeService.require_device` — never a bare `external_id` or
  connector reference. Rejecting anything else is cheap and reuses the
  existing `DEVICE_STATUSES`/`DEVICE_TYPES` vocabularies, not a new one.
- Room/Group lighting: resolve member devices via the existing list
  calls, filter to `device_type == "light"`, then issue the same
  single-device command to each — partial failure per device is
  reported per device (see Failure behaviour), never all-or-nothing.
- Scenes: a scene is `{name, home_id, targets: [{device_id, command,
  params}, ...]}`. Applying one is a fan-out identical to Room/Group
  lighting, over an explicit device list instead of a room/group
  membership query.

## Inputs

- **REST callers** (session-authenticated, per existing convention):
  connector config (for `connect` — may include a secret, e.g. an HA
  token; never logged or echoed back, matching `ConnectorCredentialStore`'s
  existing discipline), `home_id` (for discovery), `device_id` +
  normalized command + parameters (for light control), room/group id
  (for fan-out), scene definitions (for scene CRUD).
- **Existing domain/connector data** — `Device` rows, `IDeviceConnector`
  responses — both already validated by the layers that produce them;
  this document adds no new untrusted-input surface beyond what those
  layers already sanitize.

## Outputs

- REST responses in the existing `{data, meta}` `Envelope` shape
  (`infrastructure/api/auth.py`'s `Envelope`/`envelope()`, the same
  pair `smart_home.py` and M11's `integrations.py` both already use).
- `CommandResult`-derived REST responses (success/failure per device,
  never a raised 500 for a single device's command failure within a
  fan-out).
- Existing events only for this pass: `DeviceUpdatedEvent`
  (`action="status_changed"`, already published by
  `SmartHomeService.report_device_state`, itself already called by
  `ConnectivityService.refresh_device_state`) and
  `ConnectivityStatusChangedEvent` (existing, for connect/disconnect
  routes). **No new event class is introduced by this document** — a
  light-command REST call's outcome is the HTTP response itself; the
  existing `DeviceUpdatedEvent` already fires if the caller follows up
  with a state refresh, which is sufficient signal for this pass
  without inventing `LightCommandExecutedEvent` or similar.

## Dependencies

Both units of work depend only on already-shipped code: `ConnectivityService`,
`SmartHomeService`, `ConnectorFactoryRegistry`, `PermissionModel`,
`EventBus`, `Envelope`/`envelope()`, `get_current_session` — **zero new
external dependencies, zero new milestone dependencies.** Per M12's own
Dependencies note, M11/M14 remain non-blocking for the same reason the
Connectivity Layer contract already established (`CONNECTIVITY_LAYER_LOGIC_CONTRACT.md:88-97`):
nothing here needs cloud-vendor OAuth or a not-yet-built Security
Platform.

## Permission model

Reuses the **already-declared** `smart_home` scope
(`core/plugins/sdk.py:44`) through the existing `PermissionModel` —
confirmed by Phase 0 audit §7 to be reserved for exactly this purpose
but never yet enforced by any code path. This document is the *first*
real enforcement point, not a new scope: every new mutating route
(`connect`, `disconnect`, `send_command`, light commands, scene
CRUD) requires `PermissionModel.is_granted(<caller>, "smart_home")` in
addition to the existing session-auth dependency; read-only routes
(connector/device listing) require session auth only, matching
`smart_home.py`'s existing routes' own posture (none of which
currently check `PermissionModel` either — session auth alone gates
them today, and this document does not retroactively add a permission
check to existing, shipped routes it isn't touching). **No new
permission scope is introduced** — the same binding rule
`CONNECTIVITY_LAYER_LOGIC_CONTRACT.md:104-106` already states.

## State machine

**Connector-level:** unchanged, owned entirely by
`CONNECTIVITY_LAYER_LOGIC_CONTRACT.md:108-116` — this document's REST
routes are thin callers of `connect`/`disconnect`, never a second state
machine.
**Device-level:** unchanged, owned by Task Group A's `DEVICE_STATUSES`.
A light command requires `status == "paired"` (see Validation rules)
but never itself transitions device status — only
`ConnectivityService.refresh_device_state` (existing) does that, via
its own existing call path.
**Light command execution** has no state machine of its own: each
command is a single, synchronous, non-retried call through
`ConnectivityService.send_command`, returning success/failure — no new
"pending/executing/complete" states are introduced.

## Validation rules

- A light-command route rejects (400) if the target device's
  `device_type != "light"` or `status != "paired"` — reusing
  `DEVICE_TYPES`/`DEVICE_STATUSES` exactly as declared, no new
  vocabulary.
- `SET_BRIGHTNESS` rejects (400) a value outside `0-100`;
  `SET_COLOR_TEMP`/`SET_COLOR` reject non-numeric/out-of-range input at
  the Pydantic request-model level, matching M11's own request-model
  validation convention.
- A connector-`connect` route rejects (400) an unregistered
  `connector_type`, mirroring `ConnectorFactoryRegistry.create`'s own
  existing `ConnectivityError` (translated to 400 the same way
  `_bad_request` already translates `ServiceError` in `smart_home.py`).
- Room/Group/scene fan-out silently skips (not rejects) any member
  device that isn't `device_type == "light"` — a non-light group member
  is not an error, it's simply not a lighting target.

## Failure behaviour

- A single device's command failure within a room/group/scene fan-out
  is reported **per device** in the response body (mirroring
  `CommandResult.success`/`detail`) — one bad light never fails the
  whole request, matching the Connectivity Layer's own established
  "one bad record doesn't abort the batch" rule
  (`CONNECTIVITY_LAYER_LOGIC_CONTRACT.md:139-143`), applied to command
  fan-out instead of discovery.
- A `ConnectivityError` from `ConnectivityService` (not-connected
  connector, transport failure) surfaces as a 400 with the existing
  `ServiceError`→`HTTPException` translation `smart_home.py` already
  uses — never a raw 500.
- No automatic retry anywhere in this document — matches the
  connector contract's own "no silent recovery that hides a real
  failure" posture (`CONNECTIVITY_LAYER_LOGIC_CONTRACT.md:134-138`).

## Recovery behaviour

- None new. Reconnection remains the connector layer's own,
  already-deferred concern (`CONNECTIVITY_LAYER_LOGIC_CONTRACT.md:145-151`).
  A failed light command is not automatically retried or queued; the
  caller decides whether to retry, exactly as the connector contract
  already establishes for `connect`.

## Logging

- Connector id, device id, and outcome only — never connector config
  secrets (HA token, MQTT credentials) passed to `connect`, matching
  `ConnectorCredentialStore`'s existing redaction discipline. Light
  command parameters (brightness/color values) are not secrets and may
  be logged.

## Telemetry / Events

No new event class (see Outputs). `DeviceUpdatedEvent` and
`ConnectivityStatusChangedEvent` are reused exactly as they already
fire today; both are already relayed over the WebSocket hub
(`runtime_ws_hub.py` `EVENT_TYPE_NAMES`, confirmed present, Phase 0
audit §8) — no new relay wiring is needed for this document's scope.

## Test strategy

Matches the conventions Phase 0 audit §9 confirmed are already
established for this exact area — no new pattern introduced:
- **Route tests:** real FastAPI app + real DI `Container` + real
  `TestClient` + real temp-file SQLite, matching
  `test_smart_home_route.py`'s own pattern exactly.
- **`SmartLightingService` orchestration tests:** real (temp-file)
  `SmartHomeService`, `FakeDeviceConnector` standing in for the
  connector — matching `test_connectivity_service.py`'s own pattern.
  Assert the exact `command`/`payload` shape `FakeDeviceConnector.
  sent_commands` records for each `LightCommand`, per connector type
  — this is how the HA/MQTT translation table gets proven correct
  without a live vendor.
- **No `unittest.mock`, no mocked HTTP/MQTT client** — identical
  discipline to every M11/M12 test so far.

## Acceptance criteria

1. `GET`/`POST` routes exist for exactly the `ConnectivityService`
   methods enumerated in Responsibilities — no route exposes a
   capability `ConnectivityService` does not itself have (no invented
   "connector health," "capability discovery," or "device details"
   endpoint beyond what a thin merge of existing calls provides).
2. No existing `ConnectivityService`, `SmartHomeService`,
   `IDeviceConnector`, `ConnectorFactoryRegistry`, or
   `ConnectorCredentialStore` method signature changes.
3. `SmartLightingService` calls only `SmartHomeService` (read-only
   membership/device lookups) and `ConnectivityService.send_command`
   (the existing chokepoint) — never a connector directly, never a
   database session directly.
4. A light command against an HA-backed device produces exactly the
   HA service-call shape `HomeAssistantConnector.send_command` already
   expects (proven via `FakeDeviceConnector`, per Test strategy).
5. A room/group/scene fan-out reports per-device success/failure and
   never raises for one failing device among several.
6. No automation trigger (motion/time/sunrise-sunset) is implemented
   anywhere in this pass.
7. No new permission scope, event class, connector abstraction,
   registry, or credential store is introduced.
8. `smart_home` permission enforcement is added to every new mutating
   route and to no existing route this document doesn't touch.

## Open questions

Per this project's own standing rule, anything not resolvable from the
existing codebase is marked `BLOCKED` rather than guessed:

1. **Not blocked, but deferred to implementation time:** the exact
   outbound MQTT payload field names for `SET_BRIGHTNESS`/`SET_COLOR_TEMP`/
   `SET_COLOR` (Business logic, MQTT branch) — the *shape* of the
   solution is fixed by this document; the literal JSON keys need a
   direct read of `mqtt_envelope.py` before that one branch of the
   translation table is written. This does not block starting the HA
   branch, the REST-over-Connectivity surface, or the room/group/scene
   fan-out logic, all of which are connector-agnostic at this layer.
2. **Resolved, not blocked** (restated from Non-goals for visibility):
   the Home Automation boundary — Smart Lighting owns device primitives
   and scene *application* only, never triggers/scheduling.

No other open architectural ambiguity remains.
