# M12 Developer Tools — Device Simulator — Logic Contract

Status: **Draft — Logic Contract only.** Written per `M12 TASK GROUP P
— PHASE 1 ONLY` approval, following the `M12 PHASE 0 POST-TASK-O
AUDIT` (delivered in-conversation; no `docs/
M12_PHASE_0_POST_TASK_O_AUDIT.md` file exists on disk — every prior
Phase 0 audit this session was likewise chat-only, never committed).
**Not approved for implementation** — no source, tests, DI, routes,
tools, connector, `CONNECTOR_TYPES`, settings, roadmap, CHANGELOG, or
frontend changes accompany this file. Every claim below about existing
code is freshly re-verified against the current working tree this
session (clean, HEAD `7f57854`), not carried over from the Phase 0
audit unchecked.

## 1. Scope

An in-process, deterministic device simulator for **local development
and testing only** — it lets a developer exercise the full, real M12
stack (discovery, `SmartHomeService`, every device-category service's
read *and* mutation path, REST, agent tools) without a real Home
Assistant instance or MQTT broker. It is not a product feature, not
reachable by an end user, and not part of any AI Home Assistant
conversation.

## 2. Architecture decision — three options evaluated, not assumed

**Option A — a genuine third `IDeviceConnector`, registered under a
new `CONNECTOR_TYPES` entry (e.g. `"simulator"`).** Evaluated and
**rejected**. Structurally clean at first glance, but a decisive
problem surfaces on closer inspection of the actual mutation path:
every M12 device-category service's own `_TRANSLATORS` dict
(`smart_lighting_service.py:174-177`, `smart_switch_service.py:97-100`,
`thermostat_service.py:142-145`, `smart_lock_service.py:95-98`) is a
**closed, two-key dict** — `{"home_assistant": ..., "mqtt": ...}` —
looked up by `connector_type_for(device)`. A device whose
`metadata["connector_type"] == "simulator"` would make **every**
mutation call (`set_light_state`, `turn_on`/`turn_off`,
`set_thermostat_state`, lock/unlock) raise `ServiceError("...has no
command translation for connector type 'simulator'.")` *before* ever
reaching `ConnectivityService.send_command` — only read paths would
work. Making mutation paths work under Option A would require adding a
third `"simulator"` entry to **four already-shipped service files**,
directly against this project's own standing discipline of not
modifying previously-shipped device-category services without strong
justification. Also carries a real isolation weakness (§8): a new,
independent registry key means a real `HomeAssistantConnector` and a
new `SimulatorConnector` could both be connected *simultaneously* in
the same process, making it structurally possible to run simulator
discovery against a real home while a real HA connection is also live.

**Option B — a connector-less synthetic device layer**, fabricating
`Device` rows directly through `SmartHomeService.
register_discovered_device()` without ever being a registered
connector. Evaluated and **rejected** for a decisive reason: without a
registered connector, `connector_type_for(device)` resolves to
`None` for such a device (no `metadata["connector_type"]` matching any
live connector), so `ConnectivityService.read_raw_state`/`send_command`
can never reach it — `_require_connector` has nothing to find. Every
M12 device-category service's `get_X_state()` already treats a
connector-read failure as "report last-known/unavailable, never
raise" (`contextlib.suppress(ConnectivityError)`), so a connector-less
simulated device would simply read as permanently unavailable forever
— unable to exercise a single mutation path. To deliver the live-read/
mutation-path value this task group actually wants, Option B would
have to reimplement a connector's read/write loop in parallel anyway —
at which point it has not avoided the connector architecture, it has
duplicated it in a less consistent shape. **Option B either collapses
into Option A, or delivers negligible value beyond what `POST /api/v1/
devices` with a hand-set `metadata_json` already provides today, with
zero new code.**

**Option C — reuse an existing `CONNECTOR_TYPES` slot via an explicit,
process-wide DI-time swap. Chosen.** `ConnectorFactoryRegistry.
register(connector_type, factory)` (`core/connectivity/registry.py:
63-69`) is a plain dict assignment (`self._factories[connector_type] =
factory`) with no duplicate-registration guard — whichever factory is
registered under `"home_assistant"` is what `connect("home_assistant")`
instantiates. **This is precisely the pattern this repository's own
test suite already uses successfully, extensively, and without
incident**: every M12 service/route test this session touched
registers `tests/fakes/fake_device_connector.py`'s `FakeDeviceConnector`
(`connector_type: str = "home_assistant"`, confirmed by direct read)
under the `"home_assistant"` key (`registry.register("home_assistant",
lambda config: fake_connector)`). A richer, devtools-owned evolution of
that exact shape — satisfying `IDeviceConnector` structurally, with
real command→state mutation the test fake deliberately does not have
— registered under `"home_assistant"` **only when an explicit devtools
"simulator mode" setting is on** (checked once, at DI composition
root, deciding which factory gets registered for that slot) delivers
everything Option A wanted with **zero `CONNECTOR_TYPES` change and
zero existing-service modification**, because `_TRANSLATORS[
"home_assistant"]` already exists in every relevant service, unmodified.
Confirmed by direct trace that nothing in `ConnectivityService` or
`routes/connectivity.py` ever reads a connector *instance's* own
`.connector_type` attribute externally — every lookup uses the
registry-key string the caller supplied, so the simulator's registered
key is the only thing that matters for translator compatibility.

## 3. `CONNECTOR_TYPES` decision

**No.** `CONNECTOR_TYPES` (`core/interfaces/connectivity.py:44-49`) is
**not modified**. Option C makes this unnecessary — it is the decisive
reason Option C was chosen over Option A. No file in
`core/interfaces/connectivity.py` or `core/connectivity/registry.py`
needs to change for this task group.

## 4. Isolation model — the load-bearing safety property

Because Option C is a **whole-process, explicit configuration choice**
(a single settings flag checked once at composition root, not a
per-call or per-device decision), it gives a **stronger** isolation
guarantee than Option A's per-device approach would have: a real
`HomeAssistantConnector` and the simulator factory can never both be
registered under `"home_assistant"` in the same running process —
turning simulator mode on structurally prevents the real connector
from ever being instantiated at all in that process, not merely
discourages using it. There is therefore no "accidentally ran
simulator discovery against my real home while also connected to real
HA" failure mode Option C needs to defend against — that scenario
cannot occur in a single process by construction. The residual,
honestly-stated boundary: simulator mode is a whole-instance setting,
not a per-request toggle — a developer must not run a JARVIS instance
in simulator mode against a database they also use for a real home.
This is a deployment/configuration discipline (documented, not
enforced by new code), identical in kind to every other
environment-profile discipline this project already relies on (e.g.
test settings pointing at a temp-file SQLite database, never the real
one).

**No dedicated "simulator home" is needed** — a further simplification
Option C enables that Option A would have required: since simulator
mode structurally replaces the real connector for the whole process,
there is no real device data at risk in that process in the first
place. A developer/test uses whatever home (typically a throwaway test
home) they already would.

## 5. Simulated device scope (MVP)

**Light, switch, thermostat, lock, sensor.** Deliberately not every
`DEVICE_TYPES` value, and not chosen by default. These five are
exactly the set with a unique `device_type` requiring no domain/
component-fallback resolution — the same "simple dispatch" boundary
Task Group O independently arrived at for an unrelated reason (Memory
Snapshot scope), confirming it as a real, recurring architectural
seam in this codebase, not a coincidence specific to one task group.
The `device_type="appliance"` categories (fan, cover, vacuum,
humidifier, media_player, water_heater) are deliberately deferred —
supporting them would require the simulator to also replicate each
service's own `metadata["domain"]`/`["component"]` fallback discovery
logic, a real added-complexity axis this MVP does not need to prove
the concept.

Sensor and Lock are included here for a reason distinct from, and not
contradicting, Task Group O's exclusion of them from Memory Snapshot:
that exclusion was about *persisting real device state* into a
browsable memory store (an occupancy/security-posture privacy
concern). A simulator's readings are never real — there is nothing to
persist and nothing to observe about anyone's actual home. The two
decisions do not conflict.

**State vocabulary**: the simulator reports state in Home Assistant's
own status/attribute shape — the exact vocabulary every device-
category service's `_light_payload`/`_switch_payload`/
`_thermostat_payload`/`_lock_payload`/sensor-normalization logic
already expects and is tested against (`_infer_on`/`_infer_locked`
status strings; `brightness`/`color_temp_kelvin`/`current_temperature`/
`target_temperature`/`hvac_mode` attribute keys) — deliberately not a
third, simulator-specific vocabulary invented from nothing.

## 6. Discovery/creation model

Simulated devices are defined through a **devtools-only** REST surface
(§9), never automatically, never in an arbitrary real home:

1. A developer defines one or more fake devices in the simulator's own
   **pre-discovery roster** (an in-memory list the simulator's
   `discover()` implementation reports) via
   `POST /api/v1/devtools/simulator/devices`.
2. The developer then uses the **already-existing**, unmodified,
   generic `POST /api/v1/connectivity/discover` (with
   `connector_type="home_assistant"`, per §2) to import those fake
   devices into a real `Home`/`Device` row through the same code path
   every real device already uses (`ConnectivityService.
   run_discovery` → `SmartHomeService.register_discovered_device`) —
   no new import mechanism.
3. From that point, every existing M12 REST route/agent tool for that
   device category works completely unmodified, reading/mutating the
   simulator's own in-memory state.

## 7. Command/state model

**Deterministic mutation, plus deterministic (never random) configurable
failure — Option C from your own framing.**

- **Default**: `send_command(external_id, command, payload)` looks up
  the command against a small, closed table per simulated device_type
  (mirroring each real service's own `_translate_home_assistant`
  output exactly: light `turn_on`/`turn_off` with optional
  `brightness_pct`/`color_temp_kelvin`/`rgb_color`; switch `turn_on`/
  `turn_off`; thermostat `set_hvac_mode`/`set_temperature`; lock
  `lock`/`unlock`, verified directly against `smart_lock_service.py:
  67-98`), mutates that device's own in-memory `DeviceState`
  deterministically, and returns `CommandResult(success=True)`. A
  subsequent `read_state`/`get_X_state` call reflects the mutation —
  the actual round-trip this task group exists to prove.
- **Configurable failure**: a caller can mark a specific simulated
  device to fail its next command (or every command) with a
  caller-supplied `detail` string, via the fault-configuration
  endpoint (§9) — deterministic because the *caller* decides when and
  how, never the simulator's own randomness. No `random`/time-based
  jitter anywhere.
- **Unavailable device**: a caller can mark a device unavailable;
  reads then report the same `available: false`/`None`-field shape a
  real disconnected device already produces (§5's shared vocabulary),
  and commands return `CommandResult(success=False, detail="device
  unavailable")`.
- **Unsupported/malformed command**: an unrecognized command name for
  a device's own type returns `CommandResult(success=False)` with a
  descriptive detail — **never raises**, matching `IDeviceConnector.
  send_command`'s own documented contract ("Never raises for a command
  the device itself rejects").
- **No latency simulation in this MVP** — zero-latency, fully
  synchronous-feeling responses only, precisely because your own
  instruction rules out flaky/random behavior; a fixed, caller-
  configured (never random) delay is a plausible future extension, not
  built here.

## 8. Failure/isolation edge cases, named explicitly

- Sending a command to a simulated device that was never defined
  (unknown `external_id`): the simulator raises the same
  `ConnectorNotConnectedError`-family behavior a real connector would
  for an unknown entity — never silently succeeds.
- Simulator mode left on against a database that also holds real
  Home Assistant-sourced devices from a prior, non-simulator run: those
  existing `Device` rows remain in the database (rows are never
  deleted by a mode switch) but their live reads report unavailable
  until real connector mode resumes — an honestly-disclosed limitation,
  not a silent data loss.

## 9. Permission/security model

**No new `PermissionModel` principal — session auth only, matching
every existing devtools route exactly (`routes/devtools.py:45`,
re-verified this session). Explicitly assessed, not defaulted.**
Unlike Smart Home Memory (§10 of its own contract: persistent,
cumulative privacy weight) or Security & Safety (home-wide blast
radius across real devices), the simulator's mutations are structurally
confined to synthetic, in-process, developer-owned state that never
represents a real device or a real home's real data — under simulator
mode there is no real smart-home state in the process to put at risk
in the first place (§4). This is the same category of capability as
the already-shipped, already-ungated `DELETE /devtools/logs` (Debug
Console can already clear real log history without a permission gate)
— a devtools-internal, developer-facing mutation, not a smart-home
action. The residual "don't run simulator mode against your real
database" discipline (§4) is a deployment concern a `PermissionModel`
grant cannot address at all, since it is a whole-process configuration
choice made before any request is ever made, not a per-call
authorization.

## 10. REST design (devtools-only; smallest coherent surface)

```
POST   /api/v1/devtools/simulator/devices              -- define/update one fake device (also sets its current state directly, for test setup)
GET    /api/v1/devtools/simulator/devices               -- list every fake device currently in the simulator's own roster, with live state
DELETE /api/v1/devtools/simulator/devices/{external_id}  -- remove one fake device from the roster
POST   /api/v1/devtools/simulator/devices/{external_id}/fault -- configure deterministic failure/unavailability
POST   /api/v1/devtools/simulator/reset                 -- clear the simulator's entire in-memory roster/state (never touches already-imported Device/Home DB rows -- see §11)
```

**Deliberately not built**: a devtools "send simulated command"
endpoint — already fully covered by the existing, generic `POST
/api/v1/connectivity/devices/{device_id}/command` passthrough
(confirmed present, `routes/connectivity.py:166`), and by every
device-category service's own mutation route; a second path would
duplicate it. A "connect" endpoint specific to the simulator — the
existing generic `POST /api/v1/connectivity/connectors/home_assistant/
connect` already works unmodified under simulator mode (§2). A
single-device `GET` — the list response already includes full state.

## 11. Agent tools decision

**None.** This is a local development/testing capability with no
end-user or AI-Home-Assistant conversational use case — nothing a
natural-language request would ever need to invoke ("simulate a fake
light" is not a real user request). Building tools here would be
exactly the "tools because other modules have tools" anti-pattern this
task's own instructions warn against.

## 12. EventBus decision

**No EventBus dependency or publish call in the simulator's own code.**
One narrow, pre-existing, unavoidable exception, named explicitly
rather than hidden: `ConnectivityService.connect()`/`disconnect()`
already publish a connector-agnostic `ConnectivityStatusChangedEvent`
(`services/connectivity_service.py:235-244`) whenever *any* connector
type connects/disconnects, including `"home_assistant"` under
simulator mode — this is pre-existing `ConnectivityService` behavior
that applies uniformly today, requires zero new code, and is about
connector *connection* status, not a device-command event. The
device-command EventBus publishing gap this project has repeatedly
confirmed open is untouched and unaddressed by this task group.

## 13. Scheduler decision

No dependency, no scheduled simulation, no recurring behavior of any
kind.

## 14. Analytics decision

No dependency, no telemetry, no history/trend computation over
simulated data.

## 15. Memory decision

No `MemoryService` dependency. The simulator never creates memories or
snapshots automatically — consistent with Smart Home Memory's own
binding "manual, on-demand only" naming boundary, which a simulator
auto-recording itself would quietly violate if it were ever added.

## 16. Database/persistence decision

**In-memory, ephemeral, for the simulator's own pre-discovery roster
and live state cache** — mirroring the exact precedent
`MqttConnector`'s own `_state_cache: dict[str, DeviceState]` already
establishes for a connector's live state (push-based, cached,
documented as "genuinely weaker... rather than hidden" on reconnect).
No new table, no schema change. Once a fake device is imported through
the generic discovery flow (§6), the resulting `Device`/`Home` rows
persist through the **existing, unmodified** `smart_home_devices`
table exactly like any other device — the registry side of this
feature needs no new persistence because it produces perfectly
ordinary `Device` rows.

## 17. Testing strategy (future Phase 2 — described, not created)

Connector registration under simulator mode resolves to the simulator
factory, not `HomeAssistantConnector` (a settings-flag-driven DI test);
`CONNECTOR_TYPES` is unchanged and contains exactly `{"home_assistant",
"mqtt"}`; discovery reports exactly the roster defined via the devtools
endpoint; device creation/listing/deletion in the roster; command→state
mutation for each of the five MVP categories, verified by a
read-after-write round trip through the **real, unmodified**
`SmartLightingService`/`SmartSwitchService`/`ThermostatService`/
`SmartLockService`/`SensorService`; unsupported command returns
`success=False`, never raises; configured fault triggers deterministically
on the next call, never randomly; unavailable-device reads/commands;
reset clears the roster and leaves already-imported `Device` DB rows
untouched; isolation — a source-level guard confirming the simulator
module never imports `httpx`/`gmqtt`/`HomeAssistantConnector`/
`MqttConnector`/`ConnectorCredentialStore`; permission boundary —
confirming the devtools simulator routes require only session auth,
pinned by a negative test (no grant needed); source-level guards
confirming zero `EventBus`/Scheduler/Analytics/`MemoryService`
reference in the simulator's own code (the one narrow, pre-existing
`ConnectivityStatusChangedEvent` exception is `ConnectivityService`'s,
not the simulator's, and needs no guard against code that doesn't
exist here); confirming no real network call is ever attempted (no
`httpx`/`gmqtt` import, no credential store read); every §19 deferred
item has zero corresponding route/field/scaffold.

## 18. Deferred scope

| Item | Why deferred |
|---|---|
| Appliance-domain simulated categories (fan/cover/vacuum/humidifier/media_player/water_heater) | Needs the domain/component-fallback resolution complexity this MVP deliberately avoids (§5) |
| MQTT-mode simulation | MVP covers only the `"home_assistant"` registry-slot swap (§2); an MQTT-slot swap is a separately-justifiable future extension |
| Latency/jitter simulation | Rejected for this MVP per the explicit no-flakiness instruction (§7) |
| A "send simulated command" devtools endpoint | Already covered by the existing generic connectivity command passthrough (§10) |
| Any frontend surface | **Future frontend requirement — backend-only phase.** No frontend work in this or any adjacent phase without separate approval. |
| Agent tools | Explicitly evaluated and rejected (§11) |
| Persistent/replayable fixture scenarios | No evidence this MVP needs more than deterministic, caller-defined per-session state (§16) |

## 19. Acceptance criteria

- `CONNECTOR_TYPES` unchanged — still exactly `{"home_assistant",
  "mqtt"}`.
- No existing device-category service file
  (`smart_lighting_service.py`, `smart_switch_service.py`,
  `thermostat_service.py`, `smart_lock_service.py`, `sensor_service.py`)
  is modified.
- No existing `ConnectivityService`/`ConnectorFactoryRegistry`/
  `SmartHomeService` code is modified — only the DI composition root's
  own factory-registration wiring changes, gated by a new settings
  flag, under simulator mode.
- Simulator mode is off by default; the real `HomeAssistantConnector`
  is what gets registered unless the flag is explicitly set.
- The simulator's own module never imports `httpx`, `gmqtt`,
  `HomeAssistantConnector`, `MqttConnector`, or
  `ConnectorCredentialStore` — pinned by a source-level guard test.
- Command→state mutation is real and deterministic for all five MVP
  categories, verified through each category's own unmodified,
  real service.
- No randomness anywhere in failure/latency simulation.
- Devtools simulator routes require session auth only — no
  `PermissionModel` grant needed, pinned by a negative test.
- Zero `EventBus`/Scheduler/Analytics/`MemoryService` reference in the
  simulator's own code.
- Zero database schema change.
- Zero agent tools created.
- Zero frontend file touched.
- Every §18 deferred item has zero corresponding code.
- This Logic Contract is reviewed and approved **before** any
  implementation begins.

## 20. Git safety verification

`git status --short`: exactly one new untracked file (`docs/
M12_DEVELOPER_TOOLS_DEVICE_SIMULATOR_LOGIC_CONTRACT.md`), zero tracked
changes. `HEAD` = `7f57854` — unchanged. `origin/feature/
m22-task-group-c` = `7f57854` — synchronized, unchanged. No commit
made, no push performed.
