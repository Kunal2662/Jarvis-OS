# M12 Security & Safety — Manual/On-Demand Action Slice — Logic Contract

Status: **Draft — Logic Contract only.** Written per the `M12
PHASE 0 POST-WATER-HEATER AUDIT` and its approval (`PROCEED WITH PHASE
1 ONLY`). **Not approved for implementation** — no source, tests, DI,
routes, tools, connector, permission, EventBus, roadmap, CHANGELOG, or
frontend changes accompany this file. Base: the shipped M12 Security &
Safety Read-Only Alert/Status Slice (`docs/
M12_SECURITY_SAFETY_LOGIC_CONTRACT.md`, `SecurityService`), and the
already-shipped `SmartLockService`, `SmartLightingService`,
`ThermostatService`, `PermissionModel`, `SmartHomeService`.

**Legend.** Every claim about code that exists today is marked
**(EXISTING)** with a `file:line` citation, verified against the
current working tree this session (clean, HEAD `767f382`). Everything
marked **(PROPOSED)** does not exist yet.

## 1. Scope

**In scope**: two new on-demand, synchronous, home-scoped orchestration
actions on the existing `SecurityService` — **Panic Mode** (lock every
lock, turn on every light) and **Vacation Mode** (lock every lock, turn
off every light, best-effort eco-adjust every thermostat that reports
the capability). Both are single-shot: triggered once, run once,
return once.

**Explicitly not this slice's job** (§12 gives the full accounting):
scheduling, randomized presence simulation, geofencing, emergency
alerts/notifications of any kind, sirens/alarm panels, camera
integration, Home Automation, the EventBus device-command gap, and
every other M12 module.

## 2. Architecture decision — extend `SecurityService`, not a new service

**Independently evaluated, not inherited from the Phase 0 audit's
proposal.**

**Option A — extend `SecurityService`.** **Option B — new
`SecurityActionService`.** **Option C — fold into `SmartLockService`/
`SmartLightingService` directly.** Option C is rejected outright:
neither service owns "home security posture" as a concept, and
splitting Panic Mode's lock half into `SmartLockService` and its light
half into `SmartLightingService` would mean no single place could
report one coherent result for one user action — exactly the
fragmentation `SecurityService`'s own read-only slice already exists
to avoid for status.

Between A and B, **A is the correct choice, decided on architectural
grounds, not convenience**: Appliance Control's own sibling-service
precedent (Thermostat, Vacuum+Humidifier, Media Player, Water Heater
each becoming a *new* service) exists because each is a **genuinely
different device category** with its own domain, its own connector
mapping, its own read model. Panic Mode and Vacation Mode are not a
new device category — they are a second **capability** (act) over the
same concept the read-only slice already owns (observe). The
roadmap's own module list (`MASTER_ROADMAP.md` §8, Security & Safety)
names "Read-Only Alert/Status Slice" and the action-taking items as
**one module**, not two. `SecurityService` (EXISTING,
`security_service.py:101-225`) already composes other services
read-only (`SensorService`, `SmartLockService`); extending it to also
*command* `SmartLockService`/`SmartLightingService`/`ThermostatService`
is the same compositional pattern, not a new one — it is simply the
write-side mirror of what the class already does on the read side.

**Consequence for Phase 2** (not performed here): `SecurityService`'s
own module docstring, currently titled "(Read-Only Alert/Status
Slice)" (`security_service.py:2`), will need updating to reflect the
module now spans both slices. This is a documentation-accuracy item,
not a design blocker.

**New constructor dependencies required** (beyond what the Phase 0
audit assumed): `SmartLockService` (**already a dependency**,
`security_service.py:106`), plus **newly required**:
`SmartLightingService`, `ThermostatService`, and — a refinement this
Phase 1 pass found that Phase 0 did not — **`SmartHomeService`**,
needed to validate a `home_id` actually exists before attempting
anything (§4). `SecurityService` currently has no `SmartHomeService`
dependency at all (EXISTING, `security_service.py:101-112`); this is a
real, new addition Phase 2 must wire.

## 3. Verified existing service APIs (grounded in current source, not assumed)

**(EXISTING)** `SmartLockService` (`smart_lock_service.py`):
`list_locks(*, home_id=None, room_id=None) -> list[dict]` (rows keyed
`id`, `home_id`, `room_id`, `name`, `status`, `locked`, `available`;
`:163-172`); `lock(device_id) -> dict` / `unlock(device_id) -> dict`
(each `_require_permission()` then `_send()`, returning `{"device_id",
"success", "detail"}`; `:187-193`). **No home-wide or bulk method
exists** — confirmed by reading the full file; every command method is
single-device.

**(EXISTING)** `SmartLightingService` (`smart_lighting_service.py`):
`list_lights(*, home_id=None, room_id=None) -> list[dict]` (rows keyed
`id`, `home_id`, `room_id`, `name`, `status`, `on`, `brightness`,
`color_temp_kelvin`, `color`; `:307-317`); `set_light_state(device_id,
*, on=None, brightness=None, color_temp_kelvin=None, color=None) ->
dict` (`:332-348`); `apply_room(room_id, ...)` / `apply_group(group_id,
...)` (`:350-395`) — **room/group-scoped only, no home-wide
equivalent**. **Important, directly relevant finding**: `apply_room`/
`apply_group` already use exactly the fan-out pattern this slice
needs — `_safe_set` (`:397-409`) catches `ServiceError` per device and
returns `{"device_id", "success": False, "detail": str(err)}` inline
**"so one offline bulb does not block the rest"** — the literal
precedent for "continue after individual device failure." This
contract's new orchestration code adapts that same pattern locally (it
cannot call `apply_room`/`apply_group` directly — wrong scope — and
this contract does not modify `SmartLightingService` to add a
home-wide method, keeping the change surface to `SecurityService`
alone).

**Verified discrepancy, directly relevant to §6**: `SmartLockService.
_lock_payload` includes `"available": raw is not None` (`:120-121`).
**`SmartLightingService._light_payload` has no `available` key at
all** (`:208-222`, confirmed by reading the full function) — only
`on`/`brightness`/`color_temp_kelvin`/`color`, all `None` when
unreachable, with no boolean signal distinguishing "connector
unreachable" from "reachable but attributes unparseable." This
asymmetry is not fixed here (fixing `SmartLightingService` is out of
this slice's scope, mirroring every prior contract's "don't fix an
unrelated existing gap" discipline) — §6 designs around it.

**(EXISTING)** `ThermostatService` (`thermostat_service.py`):
`list_thermostats(*, home_id=None, room_id=None) -> list[dict]`
(`:269-278`) — **DB-only, never populates `hvac_modes` for list rows**
(`_thermostat_payload` returns early with `hvac_modes: []` whenever
`raw is None`, which is always true on the list path, `:192-211`).
`get_thermostat_state(device_id) -> dict` (`:280-288`) does a **live**
read and is the only way to see a device's real `hvac_modes`/
`available`. `set_thermostat_state(device_id, *, temperature=None,
hvac_mode=None) -> dict` (`:293-325`), validated against device-
reported `hvac_modes` when non-empty (`:367-373`).

**(EXISTING)** `SecurityService` (`security_service.py`):
constructor takes `sensors`, `smart_lock`, `permissions` only
(`:102-112`); `SECURITY_PRINCIPAL = "core:security"` (`:44`);
`_require_permission()` raises `SecurityPermissionError` (`:117-125`,
a `ServiceError` subclass); `get_security_status`/`list_active_alerts`
are the only two public methods, both read-only.

**(EXISTING)** `PermissionModel` (`core/plugins/permissions.py`):
`declare(plugin_id, scopes)` (`:81-94`, idempotent, safe to call every
construction); `is_granted(plugin_id, scope) -> bool` (`:97-102`);
`state(plugin_id, scope) -> PermissionState` (`:104-105`). No per-call
"require" helper beyond what each service writes itself.

**(EXISTING)** `SmartHomeService.require_home(home_id) -> Home`
(`smart_home_service.py:83-87`) raises `ServiceError` if unknown — the
mechanism §4 uses to make `home_id` mandatory-and-validated.

## 4. Panic Mode — resolved semantics

**On-demand, home-scoped, synchronous.** `home_id` is **mandatory**
(unlike the read-only slice's optional `home_id`) — deliberately
stricter, because a bulk lock/light action against a mistyped or
nonexistent home must not silently no-op; it must fail loudly.

**Validation order**: `_require_permission()` (`core:security`) first
— **zero wire calls attempted if this fails**, identical to the
read-only slice's own gate. Then `smart_home.require_home(home_id)` —
`ServiceError` (→ 404 at REST, §9) if the home does not exist. Then
proceed to orchestration.

**Orchestration, deterministic order: locks first, then lights.**
Stated as a **convention, not a discovered dependency** (mirroring
every prior merged-mutation contract's identical disclaimer) — there
is no functional coupling between locking a door and turning on a
light; locks are ordered first because establishing physical security
is the module's core concern and lights are the secondary, cosmetic/
deterrent action.

**Per-category algorithm** (locks, then lights — same shape for both):
1. `list_locks(home_id=home_id)` (or `list_lights`). This is the
   **complete requested set**.
2. For each device, classify **unavailable** using `Device.status`
   (present in both `_lock_payload`/`_light_payload` as `"status"`)
   against the connectivity-lifecycle offline values
   (`{"offline", "unreachable"}`) — the one signal reliably present
   for **both** categories despite `SmartLightingService`'s missing
   `available` field (§3). Unavailable devices are **not** sent a wire
   command; they are recorded with `success: false`, `detail:
   "device unavailable"`.
3. Every remaining device is **attempted**: `lock(device_id)` /
   `set_light_state(device_id, on=True)`. **Continues past individual
   failure** — mirrors `SmartLightingService._safe_set`'s proven
   pattern, reimplemented locally (not called into) since it is
   room/group-scoped, not home-scoped.
4. A caught `ServiceError` from the nested call (including a nested
   permission denial — §7) is recorded as `success: false`, `detail:
   str(err)` — **never re-raised**, **never aborts the remaining
   devices**.

**No confirmation of "already locked"/"already on"** — the command is
sent unconditionally; an idempotent connector treats it as a no-op,
the same "don't over-model, let the connector be the authority"
principle every prior contract uses.

**Empty-home behavior**: zero locks **and** zero lights found →
`status: "NO_TARGETS"` — not an error, a legitimate empty result
(§6).

**Overall success determination** (§6 gives the full status enum):
Panic Mode is `SUCCESS` only if every attempted device (locks + lights
combined) succeeded; `PARTIAL_SUCCESS` if some succeeded and some
failed/were unavailable; `FAILED` if at least one device was found but
none succeeded; `NO_TARGETS` if none were found at all.

## 5. Vacation Mode — resolved semantics

Same mandatory-`home_id`, same permission-then-home-validation order,
same per-device continue-past-failure discipline as Panic Mode.
**Deterministic order: locks, then lights, then thermostats** — the
same convention-not-dependency framing; thermostats are ordered last
because they are the **best-effort, optional** tier (§ below).

**Locks**: identical to Panic Mode — lock every lock.

**Lights**: identical to Panic Mode's algorithm, except `on=False`
(turn off every light) instead of `on=True`.

**Thermostats — "eco-adjacent," resolved with real evidence, nothing
invented:**

**(VERIFIED IN REPOSITORY, this session)**: `ThermostatService`'s
normalized read model exposes exactly `hvac_mode`/`hvac_modes`/
`current_temperature`/`target_temperature`/`min_temp`/`max_temp` — it
does **not** expose `preset_mode`/`preset_modes` at all (deferred by
the Climate/Thermostat Logic Contract). Home Assistant's real climate
domain has a separate, standard `preset_mode` vocabulary that includes
a literal `"eco"` value — but **this repository's `ThermostatService`
cannot see it**, because that attribute was never surfaced. Extending
`ThermostatService` to add `preset_mode` support would fix this
properly, but doing so is **out of this slice's scope** — modifying
`ThermostatService` is not what this task group is for, and doing so
would silently expand this contract's blast radius into a second
already-shipped module.

**Resolved mechanism, using only what `ThermostatService` already
exposes**: for each thermostat, call `get_thermostat_state(device_id)`
(the only source of live `hvac_modes` — §3) and check whether the
device's own reported `hvac_modes` list contains a case-insensitive
**exact-token** match for `"eco"` (not a substring match, to avoid a
false positive against an unrelated mode name). **If found**: attempt
`set_thermostat_state(device_id, hvac_mode="eco")`. **If not found**:
**skip** this thermostat entirely — no wire call, recorded as
`skipped: true`, `skip_reason: "device does not report an
eco-adjacent hvac_mode"`.

**No temperature fallback exists.** Explicitly rejected: adjusting a
target temperature by some invented offset (e.g. "+2°") when no
`hvac_mode="eco"` is reported would be fabricating a capability the
device never declared — directly against instruction and against
every prior contract's "no invented safety limit/capability"
discipline. **No preset-mode use** — not exposed by the current
service (see above).

**Honest limitation, stated plainly, not hidden**: because standard HA
climate integrations expose "eco" as a `preset_mode`, not an
`hvac_mode`, this mechanism is expected to **skip most real
thermostats** in practice today. It is still implemented as designed
because it uses only real, device-reported data and never fabricates
one — the alternative (inventing a temperature offset) would violate
the explicit instruction. §12 records extending `ThermostatService`
with real preset support as a deferred, separate future improvement.

**Thermostat availability**: unlike locks/lights, thermostats already
require a **live** per-device read for `hvac_modes` detection, so this
slice uses that same live read's own `available` field (EXISTING,
`_thermostat_payload`'s computed `available`, more accurate than the
DB-cached `Device.status` proxy locks/lights use) rather than a second
signal. An unavailable thermostat is recorded `success: false, detail:
"device unavailable"` with **no** wire attempt, mirroring locks/
lights.

**Thermostats are optional for overall success** — a skipped or
unavailable thermostat **never** blocks `SUCCESS`; only an *attempted*
thermostat that fails counts against the overall status, exactly like
a failed lock/light. This is the explicit resolution of "whether
thermostat changes are optional or required": **optional to attempt
(best-effort, honestly reported), but any attempt that is made is held
to the same success/failure accounting as locks/lights.**

**Empty-home behavior**: zero locks, zero lights, **and** zero
thermostats found → `NO_TARGETS`.

## 6. Result model — deliberately new, not copied from the 2–3-field merged-mutation shape

```python
{
  "home_id": str,
  "mode": "panic" | "vacation",
  "status": "SUCCESS" | "PARTIAL_SUCCESS" | "FAILED" | "NO_TARGETS",
  "locks": [
    {"device_id": str, "name": str, "success": bool, "detail": str}
  ],
  "lights": [
    {"device_id": str, "name": str, "success": bool, "detail": str}
  ],
  "thermostats": [
    # empty list for Panic Mode; for Vacation Mode, one entry per
    # thermostat found, whether attempted, skipped, or unavailable
    {
      "device_id": str, "name": str,
      "success": bool | None,   # None when skipped/unavailable (never attempted)
      "detail": str,
      "skipped": bool,
      "skip_reason": str | None,
    }
  ],
  "requested_count": int,     # total devices found across all attempted categories
  "attempted_count": int,     # requested minus unavailable minus skipped
  "succeeded_count": int,
  "failed_count": int,
  "unavailable_count": int,
  "skipped_count": int,       # thermostats only; always 0 for locks/lights
  "generated_at": str,        # ISO 8601, UTC
}
```

**Status derivation** (computed over the union of locks + lights +
*attempted* thermostats — skipped/unavailable thermostats never
participate):
- `NO_TARGETS`: `requested_count == 0`.
- `SUCCESS`: `requested_count > 0` and `failed_count == 0` and
  `unavailable_count == 0` (every attempted device succeeded; skipped
  thermostats do not prevent `SUCCESS`).
- `FAILED`: at least one device was requested, but `succeeded_count
  == 0` among attempted devices.
- `PARTIAL_SUCCESS`: everything else (a mix of success and failure/
  unavailability).

**No atomicity is ever claimed** — the top-level `status` string and
the per-device arrays together are the entire contract; nothing about
this response implies rollback, retry, or that a `FAILED` status
means nothing happened (some devices may well have succeeded even
under `FAILED` if... no — by construction `FAILED` means zero
successes, so this specific ambiguity does not arise, but
`PARTIAL_SUCCESS` explicitly signals "some devices are now in the new
state, others are not").

## 7. Security boundary — nested permission checks are never bypassed

**Explicit design principle, directly answering the instruction**:
`SecurityService`'s new action methods call `SmartLockService.lock()`/
`SmartLightingService.set_light_state()`/`ThermostatService.
set_thermostat_state()` **exactly as any other caller would** — they
do not reach into `ConnectivityService` or a connector directly (that
remains forbidden, per every prior M12 module's own architecture
rule), and they do **not** pre-check or short-circuit those services'
own `_require_permission()` calls.

**Consequence**: if `core:smart_locks`/`smart_home` is not granted,
every `lock()` call inside Panic Mode/Vacation Mode raises its own
`ServiceError` — caught by this slice's per-device try/except (§4) and
recorded as an ordinary **failure**, not specially detected or
reported as "permission." This is a deliberate design choice, directly
mirroring the read-only slice's own established precedent: `get_
security_status` does **not** catch or suppress a nested
`SensorPermissionError` from `core:sensors` not being granted — it
lets it propagate honestly (`security_service.py:135-139`). The action
slice applies the identical principle in the shape appropriate to a
multi-device operation: instead of one propagated exception aborting
the whole call (which would defeat "continue past individual
failure"), a missing nested grant surfaces as **every device in that
category failing**, each with `detail` naming the underlying
permission error verbatim — the operator sees exactly what's wrong
from the per-device details, without this slice inventing a second,
redundant "permission" status field.

**Only the top-level `core:security` check is special-cased** — that
one gate runs once, before any device is touched, and its failure is a
top-level `ServiceError` (→ 400 at REST, §9), not a per-device entry.

## 8. EventBus — untouched, gap preserved

**No event changes of any kind.** No publish, no subscribe, no new
event class, no worker, no background task. Panic Mode/Vacation Mode
are synchronous request/response calls that return their complete
result to the caller — nothing about them is deferred or
asynchronous. The pre-existing device-command event-publishing gap
(re-confirmed at the source level this session: `send_command` publishes
nothing, only `report_device_state`/`_publish_status` touch the bus,
and neither fires for a command's real effect) remains exactly as
found. This slice does not need it and does not attempt to close it.

## 9. REST (PROPOSED)

```
POST /api/v1/security/panic-mode
POST /api/v1/security/vacation-mode
```

Both: body `{"home_id": str}` — **required** field (Pydantic-level
`422` if missing/wrong type, mirroring every prior M12 mutation body's
own validation-before-service-layer precedent). `{data, meta}`
envelope; `meta: {"status": <the same status string>}`.

**Status-code table**:

| Condition | HTTP |
|---|---|
| `core:security` not granted | 400 |
| Unknown `home_id` | 404 |
| Missing/malformed `home_id` in body | 422 |
| Any valid trigger, regardless of `SUCCESS`/`PARTIAL_SUCCESS`/`FAILED`/`NO_TARGETS` | **200** |

`FAILED` and `PARTIAL_SUCCESS` are **not** HTTP errors — identical in
spirit to every prior "`success: false` is 200, never an error"
precedent, generalized from a boolean to this slice's own status enum.

## 10. Agent tools (PROPOSED)

Two tools only, exactly matching the two actions — no per-category
split (no `lock_all_doors`/`turn_on_all_lights` tools), since Panic
Mode/Vacation Mode are each already one coherent user intent:

| Tool | Wraps | Confirmation |
|---|---|---|
| `trigger_panic_mode` | `trigger_panic_mode(home_id)` | **Required — see §11** |
| `trigger_vacation_mode` | `trigger_vacation_mode(home_id)` | **Required — see §11** |

Both call `SecurityService` only. Both return the full result JSON
(clipped per the established `_MAX_RESULT_CHARS` convention), so a
caller sees per-device detail, not just the top-level status — the
contract explicitly requires this (§ instruction 10: "whether tools
should expose partial failures directly" — **yes**, verbatim).

## 11. Permission and confirmation — independently evaluated, not inherited

**Permission**: reuses **`core:security`** / **`smart_home`** — no new
principal, no new scope. Both new methods call the *same*
`_require_permission()` (`security_service.py:117-125`) the read path
already uses. This is the "prefer the existing principal unless a
strong reason exists otherwise" default, and no such reason was found:
these actions are conceptually security actions, and an operator who
already trusts `core:security` with reading hazard/lock/sensor status
is the same trust boundary for triggering a security response.

**Confirmation — a genuinely new decision, not copied from any prior
module.** Every prior M12 mutation (Thermostat's temperature,
Humidifier's humidity, Media Player's volume, Water Heater's
temperature/mode/on-off) landed on **no confirmation**, each reasoning
independently that its own blast radius was one device. This slice is
different in kind, not just degree: **one call affects every lock and
every light in an entire home** (Vacation Mode: every thermostat too).

**Resolved: YES — both `trigger_panic_mode` and `trigger_vacation_mode`
require confirmation.** Reasoning, weighed explicitly rather than
assumed:
1. **Blast radius is the deciding factor, independent of any single
   constituent action's own risk tier.** Locking is individually
   unattended-friendly (Smart Locks' own precedent: only `unlock_
   device` needed gating) and turning lights on/off carries no
   individual risk — but composing dozens of such actions into one
   irreversible-in-the-moment call is a materially different
   consequence class than any single-device mutation shipped so far.
2. **The cost of gating is low here.** These are rare, deliberate,
   high-stakes actions (an operator invoking "panic mode" is not a
   routine adjustment the way setting a thermostat is) — unlike
   gating something routine, which would create disproportionate
   friction, a confirmation step here matches how infrequently and
   how deliberately these would actually be triggered.
3. **This is the first addition to `confirm_required_tools` since
   Smart Locks' `unlock_device`** (`config/settings.py:513`,
   currently `{"run_automation", "unlock_device"}`) — a real,
   precedent-setting change this contract makes explicitly and
   flags for your review rather than burying.

**Consequence for Phase 2**: `AgentSettings.confirm_required_tools`
gains two new entries: `"trigger_panic_mode"`, `"trigger_vacation_
mode"`. This must be implemented as an actual settings change, not
assumed to already cover it.

## 12. Scope exclusions (explicit, no placeholders)

| Item | Why deferred |
|---|---|
| Scheduled Panic/Vacation Mode | Needs M7's Scheduler execution layer, confirmed still unshipped (Phases 4–6 pending). |
| Randomized presence simulation | Not attempted — would need a time-based engine this slice deliberately does not build. |
| Geofencing / occupancy-triggered activation | Needs Home Automation's own trigger substrate, unstarted. |
| Emergency Alerts / SMS / email / push notifications | No notification transport exists for smart home today (blocked on M21/M11). |
| Sirens / alarm panels | `device_type="other"` has zero service built against it (`siren`/`alarm_control_panel` both map there) — a real, separate gap, not touched here. |
| Camera/vision integration | `VisionService` confirmed still a stub (only Phase-3 mocks); out of scope regardless. |
| Home Automation, Scheduler, EventBus | Explicitly untouched — §8. |
| AI optimization / predictive behavior | AI Home Assistant's job, unstarted. |
| Multi-home orchestration | One `home_id` per call, by design — no fan-out across homes. |
| Scenes | Smart Lighting's scene mechanism is lighting-only; not reused or extended here. |
| User-defined routines | No authoring surface exists for this; out of scope. |
| Automatic remediation | This slice always requires an explicit trigger — never a reaction to a condition. |
| Emergency-service integration | Explicitly a §11-adjacent safety boundary — see next section. |
| `preset_mode`/`preset_modes` support on `ThermostatService` | Real, would improve eco-detection materially, but modifying `ThermostatService` is out of this slice's scope (§5). |

**No placeholder code or schema for any of the above.**

## 13. Safety statement

This slice is informational/control software layered over existing
smart-home device integrations. **It is not, and does not replace, a
certified alarm system, emergency services, a life-safety system, a
professional security system, or human judgment.** It does not detect
intrusion, does not contact emergency services, and does not take any
action automatically — every action requires an explicit, confirmed,
on-demand trigger (§11). Nothing about "Panic Mode" in this contract
implies a certified panic-button product; the name describes the
shipped behavior (lock + light) precisely and should not be marketed
or represented as more than that.

## 14. Frontend implication (conceptual only — no frontend touched)

This slice will eventually need two UI trigger points (Panic Mode,
Vacation Mode — likely on the Security dashboard the read-only slice
already implies), a confirmation step matching §11's decision, home
selection, and a result display capable of showing the §6 per-device
breakdown (locks/lights/thermostats, including the skipped/unavailable
buckets, not just a single success/fail flag). Per instruction, no
Markdown frontend-requirements document is created in this Phase 1
pass — that follows the Water Heater precedent: created only after
Phase 2's backend implementation is complete and verified.

## 15. Test strategy (future Phase 2 — described, not created)

Phase 1 creates **zero tests**. Phase 2 must cover: empty home
(`NO_TARGETS`), one lock, multiple locks, multiple lights, multiple
thermostats, mixed success/failure within one category, mixed success/
failure across categories (`PARTIAL_SUCCESS`), all-fail (`FAILED`),
unavailable locks/lights (via `Device.status`), unavailable
thermostats (via live `available`), permission failure at the
top-level `core:security` gate (aborts before any device is touched),
nested permission failure from `core:smart_locks`/`core:smart_lighting`/
`core:thermostats` (surfaces as per-device failures, not a top-level
error — §7), unknown `home_id` (404), missing `home_id` in body (422),
deterministic execution order (locks → lights[→ thermostats]),
thermostat eco-detection: device reports `hvac_modes` containing
`"eco"` (attempted) vs. not containing it (skipped, correct
`skip_reason`), no temperature-fallback code path exists anywhere,
malformed/no-connector devices surfacing as ordinary per-device
failures (not crashes), source-level test confirming no `EventBus`
reference in the new code, source-level test confirming no direct
connector import, source-level tests confirming every §12 deferred
item has no route/tool/field/scaffold, and a pinned test asserting
`trigger_panic_mode`/`trigger_vacation_mode` **are** present in
`confirm_required_tools` (the inverse of Water Heater's own pinned
negative test — this is the first M12 module needing the positive
assertion).

## 16. Acceptance criteria

- `SecurityService` gains `SmartLightingService`, `ThermostatService`,
  and `SmartHomeService` as new constructor dependencies; no other
  service is modified.
- `SmartLockService`, `SmartLightingService`, `ThermostatService` are
  **not** modified — this slice calls their existing public methods
  only.
- No nested service's own permission check is bypassed; a nested
  denial surfaces as a per-device failure, never a silently-succeeded
  device.
- `home_id` is mandatory on both actions; an unknown `home_id` is a
  404, not a silent `NO_TARGETS`.
- Every device attempted is accounted for in exactly one of: succeeded,
  failed, unavailable, skipped — no device is silently dropped.
- Thermostat eco-adjustment only ever uses a device-reported
  `hvac_modes` entry equal to `"eco"` — no temperature fallback, no
  invented preset, exists anywhere in the implementation.
- `trigger_panic_mode`/`trigger_vacation_mode` are present in
  `AgentSettings.confirm_required_tools`.
- Zero `EventBus` publish/subscribe exists anywhere in the new code.
- Zero direct connector import exists anywhere in the new code.
- Zero schema/migration changes accompany this slice.
- Every item in §12's deferred table has zero corresponding route,
  tool, field, enum value, or scaffold in whatever implementation
  eventually follows this contract.
- No file under `frontend/` is touched by the backend implementation.
- Full backend regression stays green (baseline at the time of
  writing: 3372 tests, 0 failures, 0 errors, 1 pre-existing skip).
- This Logic Contract is reviewed and approved **before** any
  implementation begins.

Every criterion above is implementable without new schema, EventBus
changes, frontend work, a new milestone dependency, connector changes,
or modification to any previously shipped M12 service's own public
behavior (only `SecurityService` itself gains new methods and
dependencies).
