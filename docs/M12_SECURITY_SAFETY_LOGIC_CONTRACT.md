# M12 Security & Safety — Read-Only Status Slice — Logic Contract

Status: **Draft — Logic Contract only.** Written per the `JARVIS CORE —
M12 POST-TASK-G NEXT MODULE AUDIT` and its explicit approval (`APPROVED
— PROCEED WITH SECURITY & SAFETY LOGIC CONTRACT ONLY`). **Not approved
for implementation** — no code, tests, or other documentation changes
accompany this file; implementation is explicitly gated on a separate,
later approval. Base: the shipped M12 Sensors (`docs/
M12_SENSORS_LOGIC_CONTRACT.md`, commits `9aff3f2`/`1fadb0a`) and Smart
Locks (`docs/M12_SMART_LOCKS_LOGIC_CONTRACT.md`, commits
`b6b3f36`/`e16b61a`) implementations — this module adds no new device
category and no new connector surface; it is a read-only aggregation
**over** those two already-shipped services.

**Legend.** Every claim about code that exists today is marked
**(EXISTING)** and cites `file:line`, verified against the current
working tree this session (clean, `5ac30cf`, no drift since Task Group
G). Every interface, field, model, endpoint, service, or tool described
below that does not exist yet is marked **(PROPOSED)** — none of it has
been implemented, and this document must not be read as describing
current behavior for anything so marked.

## 1. Scope

**In scope**: a new, read-only `SecurityService` **(PROPOSED)** that
aggregates already-normalized state from two already-shipped services —
`SensorService` **(EXISTING**, `services/sensor_service.py`**)** and
`SmartLockService` **(EXISTING**, `services/smart_lock_service.py`**)**
— into one home-security status view: one REST endpoint, two agent
tools, no new persistence, no new connector code, no new `DEVICE_TYPES`
value.

**Strictly out of scope, per the approving instruction** — none of the
following is designed, stubbed, or implemented by this contract or any
future one it authorizes: Panic Mode, Vacation Mode, Emergency response,
automatic emergency actions, lock/unlock actions, light/switch actions,
fan/cover actions, multi-device scenes, automated remediation, Scheduler
integration, event-driven automation, notifications, analytics, Smart
Home Memory integration, Home Automation, camera streaming, vision
processing, TTS/voice changes, and frontend work of any kind. §21 gives
the full accounting of why each is deferred, not merely unmentioned.

## 2. Data sources — verified this session

**(EXISTING)** `SensorService` exposes thirteen `device_class` values
across `device_type="sensor"` devices (`sensor_service.py:66-77`,
re-read this session), of which this module consumes a subset (§4).
Two public methods are the only surface `SecurityService` is permitted
to call — **never a connector, never `ConnectivityService`, never
`SmartHomeService` directly** (the approving instruction's explicit
"pull-based aggregation... do not bypass these services" constraint):

- `list_sensors(*, home_id=None, room_id=None) -> list[dict]`
  (`sensor_service.py:226-236`) — DB-only roster, each row carrying
  `id, home_id, room_id, name, status, device_class, kind` (no live
  value — `_sensor_list_payload`, `sensor_service.py:144-153`).
- `get_sensor_state(device_id) -> dict` (`sensor_service.py:238-247`) —
  one sensor's live reading: adds `state, value, unit, available,
  timestamp` (`_sensor_full_payload`, `sensor_service.py:156-194`).
  **Requires the `smart_home` grant for `core:sensors`** — every call,
  including this one, per Sensors' own Logic Contract §20 (see §14).

**(EXISTING)** `SmartLockService` exposes:

- `list_locks(*, home_id=None, room_id=None) -> list[dict]`
  (`smart_lock_service.py:163-172`) — DB-only roster; `_lock_payload`
  called with `raw=None`, so **every row's `locked` is always `None`
  and `available` is always `False`** (`smart_lock_service.py:
  110-125,121`) — this is not a bug this contract works around, it is
  the same list/detail asymmetry Sensors already has (§2 of the
  Sensors contract), verified by re-reading the source this session.
- `get_lock_state(device_id) -> dict` (`smart_lock_service.py:174-182`)
  — one lock's live `locked: bool | None`, `available: bool`. **Not
  gated** — `list_locks`/`get_lock_state` never call `_require_
  permission()` (verified: zero references in either method body,
  `smart_lock_service.py:163-182`); only `lock()`/`unlock()` do
  (`smart_lock_service.py:187-193`).

**Consequence (PROPOSED aggregation pattern)**: because neither list
method returns live values, `SecurityService` must call `list_sensors`/
`list_locks` once each to enumerate device ids and (for sensors)
`device_class`, then call `get_sensor_state`/`get_lock_state` per
matched device id for the live reading actually needed to compute a
status. This is an N+1 read pattern — the same one implicit in every
prior M12 list/detail split, just performed by a caller outside the
service that owns the split for the first time. No new list/detail
asymmetry is invented; this module only calls the two that already
exist.

## 3. Two independent permission gates compose

**(EXISTING, load-bearing finding)**: `SecurityService` calling into
`SensorService.list_sensors`/`get_sensor_state` **still trips
`SensorService`'s own `_require_permission()` independently**
(`sensor_service.py:210-218`) — granting the new `core:security`
principal (§14) does **not** implicitly grant `core:sensors`. An
operator must grant both `core:sensors` (to let `SensorService` release
sensor data at all) and `core:security` (to let this module release the
aggregate) before hazard/status sections populate. `SmartLockService`
reads are ungated, so no equivalent second grant is needed for lock
data. **`SecurityService` does not catch and suppress a propagated
`SensorPermissionError`** — it is allowed to surface as a generic
`ServiceError` up through the REST layer (§12), because this module has
no legitimate way to report a truthful security status while missing
the sensor data it is built on; swallowing it would silently under-
report hazards, which §17's safety boundary forbids more strongly than
an honest 400 would.

## 4. Alert semantics — deterministic, non-inferred mapping (PROPOSED)

**Central design decision, directly answering the approving
instruction's requirement.** Sensor `device_class` values (§2, already
normalized by `SensorService`) split into exactly two buckets. The
split is fixed and closed — no future device_class is added to either
bucket by this contract without its own justification:

**Hazard bucket — the only classes that can raise `overall_status`
above NORMAL.** Chosen because HA's own definition of these three
`device_class` values *is* "hazard detected" — reporting `value=True`
as an alert restates what the sensor's own vocabulary already means,
it does not add inference:

| `device_class` | `value=True` | `value=False` |
|---|---|---|
| `smoke` | **ACTIVE** (alert) | CLEAR |
| `gas` | **ACTIVE** (alert) | CLEAR |
| `moisture` (water leak — HA's real class name, per Sensors §3) | **ACTIVE** (alert) | CLEAR |

**Status bucket — reported factually, never elevated to an alert and
never affects `overall_status`.** This is the direct implementation of
the approving instruction's "door/window open should NOT automatically
become intrusion" and "motion/presence should NOT automatically equal
intrusion" rules — applied uniformly to every contextual class, not
decided case-by-case:

| `device_class` | Reported as (from `SensorService`'s own `state` label, §8 of Sensors contract) |
|---|---|
| `door`, `window`, `garage_door` | `"open"` / `"closed"` |
| `motion` | `"detected"` / `"clear"` |
| `presence`, `occupancy` | `"occupied"` / `"unoccupied"` |
| `vibration` | `"detected"` / `"clear"` |

Lock state (`locked: bool | None`, §2) is treated identically to the
status bucket for the same reason — an unlocked door is contextual, not
an unconditional alert — and also never affects `overall_status` (§6).
Any sensor `device_class` outside both tables above (temperature,
humidity, illuminance, energy, and every other numeric class Sensors
already normalizes) is **not part of this module's aggregate at all** —
no security semantic applies to a temperature reading itself, and
including it would be scope creep into Sensors' own domain.

## 5. Per-signal state vocabulary (PROPOSED)

For each hazard-bucket sensor, derived only from fields `SensorService.
get_sensor_state` already returns — no new inference:

- **`ACTIVE`** — `available is True and value is True`.
- **`CLEAR`** — `available is True and value is False`.
- **`UNKNOWN`** — `available is False`, **or** `available is True and
  value is None` (an unparseable/unread raw status — `_parse_binary`
  already returns `None` for this, `sensor_service.py:115-121`).
  **`UNKNOWN` is never coalesced into `CLEAR`** — this is the direct
  implementation of "unavailable data must never be interpreted as
  safe."

Status-bucket sensors and locks are **not** run through this
ACTIVE/CLEAR/UNKNOWN reduction — they are passed through verbatim as
`SensorService`'s own `state`/`available` (or `SmartLockService`'s own
`locked`/`available`) fields, because collapsing "door is open" into a
security-flavored vocabulary is exactly the kind of invented
classification §4 rules out.

## 6. Overall status vocabulary and precedence (PROPOSED)

```
overall_status: "CRITICAL" | "WARNING" | "UNKNOWN" | "NORMAL"
```

Computed **only** from the hazard bucket's per-signal states (§5) —
status-bucket sensors and lock state never participate, by the same
uniform rule as §4:

1. **`CRITICAL`** — at least one hazard sensor's signal is `ACTIVE`.
2. **`WARNING`** — no hazard sensor is `ACTIVE`, but at least one
   hazard sensor exists **and** its signal is `UNKNOWN` (a real, known
   gap in coverage right now — a hazard sensor is paired but cannot
   currently be read).
3. **`UNKNOWN`** — no hazard-bucket sensor is paired in the queried
   home/room scope at all (nothing to evaluate — distinct from §6.2,
   which requires at least one paired-but-unreadable hazard sensor).
4. **`NORMAL`** — at least one hazard sensor exists, and every one of
   them is `CLEAR`.

Precedence `CRITICAL > WARNING > UNKNOWN > NORMAL` (highest listed
first wins). Rationale for `UNKNOWN` ranking above `NORMAL`: a home
with zero monitored hazard points is not equivalent to, and must not
be presented as reassuringly as, a home whose hazard sensors are all
confirmed clear — collapsing "nothing is being monitored" into
`NORMAL` would misstate confidence the aggregate does not have. This
is the same "unavailable/unknown must never read as safe" principle
applied one level up, from individual sensors to the whole-home
summary.

## 7. Aggregate response shape (PROPOSED)

```
{
  "home_id": str | None,
  "room_id": str | None,
  "overall_status": "CRITICAL" | "WARNING" | "UNKNOWN" | "NORMAL",
  "active_alerts": [
    {"device_id": str, "name": str, "room_id": str | None,
     "device_class": str, "timestamp": str | None}
    # hazard-bucket sensors with signal == "ACTIVE" only
  ],
  "hazard_sensors": [
    {"device_id": str, "name": str, "room_id": str | None,
     "device_class": str, "signal": "ACTIVE" | "CLEAR" | "UNKNOWN",
     "available": bool, "timestamp": str | None}
    # every hazard-bucket sensor, full roster, §5
  ],
  "status_sensors": [
    {"device_id": str, "name": str, "room_id": str | None,
     "device_class": str, "state": str | None, "available": bool,
     "timestamp": str | None}
    # every status-bucket sensor, §4, informational only
  ],
  "locks": [
    {"device_id": str, "name": str, "room_id": str | None,
     "locked": bool | None, "available": bool}
  ],
  "unavailable_count": int,   # count of UNKNOWN hazard signals + unavailable locks, combined
  "generated_at": str         # ISO 8601, this service's own wall-clock time -- see §9
}
```

`room_id` is passed through verbatim, never resolved to a room *name*
— matching every other M12 payload's precedent (`SensorService`,
`SmartLockService`, `ApplianceService` all return raw `room_id`, none
resolves it via `SmartHomeService.get_room` **(EXISTING**,
`services/smart_home_service.py:221`**)**; this module does not
introduce a new convention for itself).

## 8. Filtering behavior (PROPOSED)

`home_id`/`room_id` are optional filters, mirroring `list_sensors`/
`list_locks`'s own signatures exactly (§2). **Not required** — omitting
`home_id` aggregates across every home, the same filter semantics
every other M12 list endpoint already has, documented here rather than
silently inherited. An unknown/non-existent `home_id` or `room_id` is
**not an error** — `list_sensors`/`list_locks` do not validate
filter-id existence (they are query filters, not resource lookups), so
a bogus filter simply yields empty hazard/status/lock lists and
`overall_status="UNKNOWN"` (§6.3), inherited behavior, not a new
validation rule this module adds.

## 9. Timestamp behavior (PROPOSED)

`generated_at` is this service's own wall-clock time at the moment the
aggregate is assembled — legitimate to state as "now" (unlike a
device-reported field) because it describes when the *aggregation*
ran, not a claim about when any device last reported. Each individual
hazard/status sensor entry's `timestamp` is passed through from
`SensorService.get_sensor_state`'s own `timestamp` field verbatim,
including `None` when the connector reported none (Sensors contract
§10) — never fabricated. Lock entries carry no timestamp — `_lock_
payload` does not include one (`smart_lock_service.py:110-125`,
re-verified this session), and this module does not invent one for
locks.

## 10. REST API (PROPOSED)

One route only. `/capabilities`/`/alerts`-as-a-separate-route were
evaluated and rejected for the same reason Sensors' own Logic Contract
rejected `/capabilities`/`/status` (§11 of that contract): `active_
alerts` is already a field of the one aggregate response, so a second
route would return a slice of an already-cheap read, not new
information.

| Method | Path | Behavior |
|---|---|---|
| GET | `/security/status` | Returns §7's aggregate. Query params `home_id: str \| None`, `room_id: str \| None`. |

`{data, meta}` envelope, `Depends(get_current_session)` Bearer auth —
identical to every M12 route since M9 Task Group E. `meta` carries
`{"overall_status": ...}` (mirroring how mutation routes already put
`{"success": ...}` in `meta`, e.g. `routes/smart_locks.py:73`), so a
caller can read the headline status without parsing `data`.

**No 404 case exists in this module** — a genuine first for M12's REST
surface: every prior module's single-resource `GET .../{id}` can 404
on an unknown id, but this route has no single-resource identity to be
"not found" (§8). The only failure mode is permission (§12).

## 11. Tool Registry (PROPOSED)

Two read-only tools, `agents/tools/security_tools.py`,
`build_security_tools(security: SecurityService) -> list[BaseTool]`,
mirroring `sensor_tools.py`'s "terse re-shaping of one underlying call"
precedent (§18 of the Sensors contract) rather than inventing a new
tool-design pattern:

| Tool | Wraps | Justification |
|---|---|---|
| `get_security_status` | Full §7 aggregate | The "give me everything" tool, mirroring `get_sensor_state`/`get_lock_status`'s own full-payload shape. |
| `list_active_security_alerts` | Same underlying call, returns only the `active_alerts` slice (or a friendly "No active alerts." string when empty, matching `list_sensors`'/`list_locks`'s own empty-result convention) | Justified by the exact precedent `get_sensor_value`/`get_sensor_status` already established: a conversational agent asking "is anything wrong at home" benefits from a terse alert-only answer more than the full JSON blob. **Evaluated per the approving instruction's "only include if it proves useful" condition** — kept because it is not a duplicate of `get_security_status` (different projection of the same call, same non-duplication test Sensors' own kickoff applied when it dropped a fifth, redundant tool). |

Both call `SecurityService` only, never `SensorService`/`SmartLockService`
directly — the tool layer does not bypass the service layer any more
than the REST layer does. **No mutation tool** — nothing in this
module can be commanded; matches Sensors' own "nothing to gate behind
confirmation" reasoning exactly. No `AgentSettings.confirm_required_
tools` **(EXISTING**, `core/config/settings.py:513`**)** entry is
proposed — there is no action to confirm.

## 12. Error taxonomy (PROPOSED)

Simpler than Sensors' own split (§14 of that contract), because this
module has no 404 case at all (§10): `GET /security/status` — any
`ServiceError` (this module's own `SecurityPermissionError`, or a
`SensorPermissionError` propagated from the nested `SensorService`
call per §3) → **400**. No other status code is possible from this
route besides `200`. A connector-level failure on any individual
device's live read is **not** an error at this layer either — it is
already caught inside `SensorService.get_sensor_state`/`SmartLockService.
get_lock_state` (both wrap the live read in `contextlib.suppress
(ConnectivityError)`, `sensor_service.py:245`/`smart_lock_service.py:
180`) and folded into `available=False`/`signal="UNKNOWN"` before it
ever reaches `SecurityService`.

## 13. Service contract (PROPOSED)

```python
class SecurityService:
    def __init__(
        self, *,
        sensors: SensorService,
        smart_lock: SmartLockService,
        permissions: PermissionModel,
    ) -> None: ...

    async def get_security_status(
        self, *, home_id: str | None = None, room_id: str | None = None,
    ) -> dict[str, Any]: ...  # §7

    async def list_active_alerts(
        self, *, home_id: str | None = None, room_id: str | None = None,
    ) -> list[dict[str, Any]]: ...  # thin slice of get_security_status, §11
```

Dependencies are **exactly** `SensorService` + `SmartLockService` +
`PermissionModel` — no `ConnectivityService`, no `SmartHomeService`, no
`EventBus` dependency, per the approving instruction's explicit
constraint. `SecurityService` does not re-implement `_parse_binary`/
`_infer_locked`/`_binary_state_label`/any of `SensorService`'s or
`SmartLockService`'s own normalization logic (`sensor_service.py:
115-141`, `smart_lock_service.py:101-107`) — it only calls their
public methods and classifies the already-normalized results per §4-6.
This is the acceptance test for "does not duplicate SensorService or
SmartLockService logic."

## 14. Permission decision — resolved, with rationale (PROPOSED)

**Resolved: gated, reusing the existing `smart_home` scope, one new
principal `core:security`.** Not the Lighting/Locks/Switches/Appliances
"ungated reads" precedent — the Sensors precedent, extended.

**Why not ungated (the Locks precedent).** A lock's own on/off-shaped
state carries no comparable privacy weight to what it reveals in
isolation (Appliance Control's Logic Contract §14 made the identical
argument for fan/cover state). This module is different in kind: its
entire output is either (a) hazard alerts, or (b) a recombination of
the exact sensor categories — motion, presence, occupancy — that
Sensors' own Logic Contract §20 already singled out as the reason
*that* module gates reads at all. An aggregate that restates gated
data through an ungated endpoint would be a real, exploitable
permission bypass of Sensors' own established boundary, not a
harmless convenience — an operator who has denied `core:sensors` would
otherwise still learn "is anyone home" through this module's `status_
sensors` field. Gating closes that gap; it does not invent a new
concern.

**Why one new principal, not zero.** Every M12 module to date declares
its own fixed principal under the shared `smart_home` scope
(`core:sensors`, `core:smart_locks`, `core:smart_switch`, `core:
appliances`) rather than reusing another module's — `core:security`
follows the identical, now five-times-proven pattern. **No new scope**
is created (`PERMISSION_SCOPES` **(EXISTING**, `core/plugins/sdk.py:
34-44`**)** already contains `"smart_home"`; nothing is added to it).

**Declaration/grant mechanics** — identical to every prior module:
`self._permissions.declare("core:security", ["smart_home"])` at
construction, `PENDING` by default, granted through the existing
generic `POST /api/v1/plugins/core:security/permissions/smart_home/
grant` route. **Net effect**: `core:security` and `core:sensors` are
independently grantable — an operator must grant both for the hazard/
status portions of the aggregate to populate (§3); lock data requires
only `core:security` (locks themselves stay ungated at the
`SmartLockService` layer, per §2).

**Confirmation behavior**: none. Nothing in this module is an action;
no `confirm_required_tools` entry applies (§11).

**REST/tool behavior**: REST maps any resulting `ServiceError` to
`400` (§12); both tools catch `Exception` broadly and return a
friendly string, matching every other M12 tool file's convention
(`sensor_tools.py:47-51`, `smart_lock_tools.py:52-56`) — a denied
principal gets a readable failure, not a stack trace, from either
surface.

## 15. Event-bus decision — explicitly not fixed (PROPOSED / policy)

**This contract does not touch the `DeviceUpdatedEvent`-publishing gap**
the approving audit identified (`SmartLightingService`, `SmartLockService`,
`SensorService`, `SmartSwitchService`, `ApplianceService` never call
`event_bus.publish` on a command or state read — verified again this
session, unchanged). `SecurityService` **publishes no event of its
own** — a read is not a state change, the same "nothing to announce"
reasoning Sensors' own Logic Contract §17 already applied one level
down. **Consequence, stated plainly**: `/security/status` is
poll-only. There is no push notification, no live-updating dashboard
feed, and no way for a caller to be told "smoke was just detected"
without calling this endpoint again. Fixing the publishing gap is
explicitly out of scope for this module (it is the prerequisite for
Home Automation, Smart Home Memory, and Developer Tools' Event Viewer
instead, per the approving audit's dependency graph) and is not
attempted here even partially.

## 16. AgentOrchestrator integration (PROPOSED)

`security` threaded through the same four-point pattern already proven
five times (`agents/tools/registry.py`'s `build_tool_registry`,
`AgentOrchestrator.__init__`/`.start()`, and `core/di/container.py`'s
`_build_agent_orchestrator` + `agent_orchestrator` provider). DI:
a `security_service` singleton **(PROPOSED)** in `container.py`,
depending on the already-registered `sensor_service`, `smart_lock_
service`, `permission_model` providers — the same shape as `_build_
sensor_service`/`_build_smart_lock_service` **(EXISTING**, `core/di/
container.py:549-568`**)**, one level higher in the composition graph.
No new orchestration path, no new LLM logic, no new planner.

## 17. Safety boundary (required statement)

**This module is informational only.** It reports what already-shipped
sensors and locks currently say, aggregated and classified per §4-6.
It does **not** guarantee physical safety, and it does **not** replace:
alarms, certified security systems, emergency services, human
judgment, or physical safety mechanisms. **No automatic action is
permitted anywhere in this MVP** — there is no mutation route, no
mutation tool, and no code path in `SecurityService` that calls
`SmartLockService.lock`/`unlock`, `SmartLightingService`, `SmartSwitchService`,
or `ApplianceService`. A `CRITICAL` `overall_status` is a report, not a
response — what a human or a future, separately-scoped and separately-
approved module does with that report is explicitly not this
contract's concern.

## 18. Validation rules

- `home_id`/`room_id`, when provided, are passed through as opaque
  filter strings to `SensorService`/`SmartLockService` — no existence
  validation is performed by `SecurityService` itself (§8); it inherits
  whatever those two already do (nothing, for list filters).
- No request body exists anywhere in this module (pure `GET`) — no
  schema validation surface beyond FastAPI's own query-param typing.

## 19. Failure and recovery behavior

- A denied/pending permission at either gate (§3, §14) surfaces as a
  `ServiceError` → `400` — never a silent empty result, so a caller
  cannot mistake "not authorized" for "confirmed no alerts."
- A single device's connector failure never fails the aggregate — it
  is already absorbed into `available=False`/`UNKNOWN` before
  `SecurityService` sees it (§12).
- No background refresh, no polling, no caching beyond what `Sensor
  Service`/`SmartLockService` already do — the same "no polling
  framework" carve-out Sensors' own Logic Contract §22 already states,
  inherited rather than re-decided. `POST /api/v1/connectivity/
  devices/{id}/refresh` **(EXISTING**, Task Group C, unchanged**)**
  remains the only way to force a fresher underlying read before
  calling `/security/status` again.

## 20. Logging and telemetry

Reuses `core.logging.logger.get_logger` **(EXISTING)** — the tool
layer logs `_logger.warning(...)` on any caught exception, matching
`sensor_tools.py`/`smart_lock_tools.py` verbatim. **No telemetry**:
verified no metrics/telemetry emission exists in `sensor_service.py`
or `smart_lock_service.py` today; this module does not introduce
telemetry infrastructure unilaterally for itself alone.

## 21. Explicitly deferred / out-of-scope, with reasons

| Item | Why deferred |
|---|---|
| Panic Mode, Vacation Mode, Emergency response | Action-taking, multi-device; needs a "scene" concept that does not exist anywhere in the codebase (verified by the approving audit) and `safety_critical` gating design this MVP does not attempt. |
| Automatic remediation, lock/unlock/light/switch/fan/cover actions | This module has no mutation surface at all (§17) — any actuation belongs to the already-shipped per-category services, called by a human or a future, separately-approved module, never by `SecurityService`. |
| Multi-device scenes | No scene/workflow concept exists in the codebase (confirmed by the approving audit's grep — only a decorative, unwired UI button). |
| Scheduler / event-driven automation | M7 Scheduler does not exist (confirmed unstarted by the approving audit); this module is poll-only by design (§15). |
| Notifications | No notification/alert delivery mechanism exists; this module produces a queryable status, not a push. |
| Analytics | M20A does not exist; no analytics platform is built or duplicated here. |
| Smart Home Memory integration | `MemoryService` is not called by this module — no event exists to feed it (§15), and wiring history storage is a separate, unstarted module's job. |
| Home Automation | Not built on, not extended — this module has no trigger/condition/action concept. |
| Camera streaming, vision processing | No camera/vision infrastructure exists (confirmed by the approving audit); entirely untouched. |
| TTS/voice changes | Not touched anywhere in this contract. |
| Frontend work | Zero frontend files referenced, read, or proposed — see §22. |

## 22. Frontend independence

This Logic Contract describes a backend-only module: one service, one
REST route, two agent tools, one new permission principal. Nothing in
it reads, references, or requires any change under `frontend/` or
`Jarvis-Frontend-main/frontend`. **Backend-only viable: YES** — the
proposed REST endpoint and tools deliver the full MVP value without
any UI, consistent with every M12 module shipped to date.

## 23. Test plan (future — described, not created)

Per the approving instruction, no tests are created by this document.
A future implementation would need, at minimum (mirroring the "fakes,
not mocks" discipline — real `PermissionModel`, `FakeDeviceConnector`-
backed `SensorService`/`SmartLockService` instances reused from their
own existing test fixtures, no new fake required since `SecurityService`
only calls already-tested public methods):

- Normal state (all hazard sensors `CLEAR` → `NORMAL`).
- Smoke alert, gas alert, water-leak alert (each hazard class
  independently → `CRITICAL`, appears in `active_alerts`).
- Mixed states — one hazard `ACTIVE` alongside others `CLEAR` →
  `CRITICAL` still wins (precedence, §6).
- Open door, open window, motion, presence, occupancy — each reported
  in `status_sensors`, **none** elevates `overall_status` or appears
  in `active_alerts` (the negative test directly enforcing §4).
- Lock state: locked, unlocked, unknown (`locked=None`) — reported in
  `locks`, none affects `overall_status`.
- Unavailable hazard sensor → `UNKNOWN` signal → `WARNING` overall
  (given at least one other hazard sensor exists) — and the boundary
  case where it is the *only* hazard sensor.
- Unavailable lock → `available=False`, `locked=None`, still
  informational only.
- Empty home (zero devices of any kind) → `UNKNOWN` overall, all
  lists empty, `unavailable_count=0`.
- No hazard sensors paired but status sensors/locks exist → `UNKNOWN`
  overall (§6.3), status/lock data still populated.
- Multiple rooms — `room_id` filter correctness, and unfiltered
  aggregation spanning rooms.
- Deterministic ordering — every pairwise/combination test needed to
  pin `CRITICAL > WARNING > UNKNOWN > NORMAL` (§6) against regression.
- Permission behavior — `core:security` denied → 400 at both REST and
  tools; `core:security` granted but `core:sensors` denied → hazard/
  status sections fail per §3, not silently empty; both granted →
  full aggregate.
- REST behavior — envelope shape, query param filtering, `meta.
  overall_status`, absence of any 404 case (§10).
- Tool behavior — both tools' happy path and their `except Exception`
  friendly-string path.

## 24. Acceptance criteria

- `SecurityService` depends only on `SensorService`, `SmartLockService`,
  `PermissionModel` — no `ConnectivityService`/`SmartHomeService`/
  `EventBus` reference anywhere in it (§13).
- Zero connector code changes, zero new `DEVICE_TYPES` entries, zero
  new ORM tables/columns.
- Zero new permission scope — one new principal (`core:security`) only.
- Zero events published by this module.
- Zero mutation surface — REST and both tools are 100% read-only.
- `overall_status` precedence (§6) is deterministic and does not
  depend on iteration order of the underlying device lists.
- Door/window/garage_door/motion/presence/occupancy/vibration/lock
  state never appear in `active_alerts` and never move `overall_
  status` off what the hazard bucket alone determines (§4 enforced as
  a structural invariant, not a convention).
- An `UNKNOWN` hazard-sensor signal never allows `overall_status=
  NORMAL` (§6, §17's "unavailable is never safe" principle).
- No file under `frontend/`/`Jarvis-Frontend-main/frontend` is touched
  by whatever implementation eventually follows this contract.
- `docs/M12_SECURITY_SAFETY_LOGIC_CONTRACT.md` exists and is reviewed/
  approved **before** any of the above is implemented — satisfied by
  this document, pending the separate approval this session's
  instruction reserves.
