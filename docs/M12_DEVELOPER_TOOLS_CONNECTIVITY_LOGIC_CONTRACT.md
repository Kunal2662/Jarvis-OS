# M12 Developer Tools — Connectivity / Integration Health — Logic Contract

Status: **Draft — Logic Contract only.** Written per the `M12 PHASE 0
POST-TASK-GROUP-M AUDIT` and its approval (`APPROVED — PROCEED WITH
PHASE 1 ONLY`). **Not approved for implementation** — no source,
tests, DI, routes, tools, connector, permission, EventBus, roadmap,
CHANGELOG, or frontend changes accompany this file. Base: the shipped
M9 Developer Platform Tools (`infrastructure/api/routes/devtools.py`,
`core/devtools/`), the shipped M12 `ConnectivityService`/
`SmartHomeService`.

**Legend.** Every claim about code that exists today is marked
**(EXISTING)** with a `file:line` citation, verified against the
current working tree this session (clean, HEAD `58ae37d`). Everything
marked **(PROPOSED)** does not exist yet.

## 1. Scope

**In scope**: one narrow, read-only diagnostic capability —
connector-level connectivity state (which connector types are
registered/connected) plus per-home device-health counts, both
already computable from existing services with zero new data
collection.

**Explicitly not this slice's job** (§6 gives the full accounting):
MQTT Debug Console, Device Simulator, Event Viewer, command
tracing/replay, packet capture, latency/uptime/reconnect-history
metrics (none of which are tracked anywhere today), device command
history, automation/scheduler debugging, camera diagnostics,
Analytics, Memory, Remote Access, or any frontend work.

## 2. M9 Developer Tools — verified, not assumed

**(EXISTING, re-read in full this session)**
`infrastructure/api/routes/devtools.py` (195 lines) currently exposes
five capabilities, each a thin REST-read wrapper over one
`core/devtools/` component: Debug Console/Live Logs (`:65-93`),
Performance Profiler (`:99-117`), State Inspector (`:123-144`), API
Inspector (`:150-165`), and Plugin Diagnostics (`:171-195`, a combined
view over the first three, not a fourth data source).

**Authorization — verified precisely, not assumed.** Every route on
this file carries exactly one dependency: `Depends(get_current_session)`
(`:32`) — the same bare Bearer-session auth every other resource
router in this codebase uses. **There is no `PermissionModel` gate on
any of the five existing devtools capabilities.** The router's own
`_permission_model` accessor (`:58-59`) exists solely to read a
*plugin's own* historical audit-log entries inside
`get_plugin_diagnostics` (`:180`) — it never gates access to the
devtools routes themselves. Separately, `DeveloperModeService`
(`services/developer_mode_service.py`) implements a real
PBKDF2-hashed password unlock (`unlock()`/`is_unlocked()`/`lock()`) —
but it is **not wired into `routes/devtools.py` at all**; nothing in
that file depends on it. "Developer-facing, not public" (the file's
own docstring, `:13`) is therefore a **documented convention**, not a
backend-enforced authorization boundary today — Developer Mode's
password gate is a frontend/UX concept only, at the current state of
this repository. This is reported here precisely because it directly
answers §8's question, not glossed over.

**Existing service abstraction — verified, not assumed.** Each
`core/devtools/` component (`DebugConsole`, `PerformanceProfiler`,
`StateInspector`, `ApiInspector`) is a small, focused class taking
**only `core/`-layer dependencies** — re-read in full this session:
`StateInspector.__init__` takes `ServiceManager | None`,
`PluginRegistry | None`, `RuntimeManager | None`
(`core/devtools/state_inspector.py:60-69`), all three themselves
`core/lifecycle`/`core/plugins` objects; `ApiInspector` depends on
nothing but its own in-memory buffer, fed by middleware
(`core/devtools/api_inspector.py:39-40`). **Zero existing
`core/devtools/*.py` component imports anything from `services/`.**
This is the decisive finding for §5's architecture decision.

## 3. Connectivity APIs — verified, not assumed

**(EXISTING)** `ConnectivityService` (`services/connectivity_service.py`):
- `connected_types: tuple[str, ...]` (`:98-100`) — a property, `tuple(sorted(self._connectors))`: connector types that have had `connect()` called and not yet `disconnect()`-ed. **Not** the same question as the next one.
- `is_connected(connector_type: str) -> bool` (`:102-104`) — re-checks the live connector object's own `.is_connected`, so a connector that dropped without an explicit `disconnect()` call correctly reports `False` even though it still appears in `connected_types`. **Both signals are needed together**, not one or the other.
- **No uptime, no reconnect count, no error count, no latency is tracked anywhere in this class** — confirmed by reading the full file. Any such field would be fabricated; §9 marks all of them unavailable.

**(EXISTING)** `ConnectorFactoryRegistry` (`core/connectivity/registry.py`):
- `registered_types: tuple[str, ...]` (`:79-81`) — every connector type with a **factory** registered at the DI composition root, independent of whether `connect()` has ever been called. This is the "what could this build connect to" list; `ConnectivityService.connected_types` is "what has this build actually connected to." Both are needed for an honest picture (e.g. `mqtt: registered, never connected`).
- `supports(connector_type) -> bool` (`:83-84`) — equivalent boolean form.

**(EXISTING)** `SmartHomeService.metadata(home_id) -> HomeMetadata`
(`services/smart_home_service.py:125-141`) — **already the exact
device-health aggregate this slice needs**, built for Task Group A's
own Device Health Monitoring/Device Status Dashboard items, computed
live on every call (never persisted, never stale): `room_count`,
`zone_count`, `device_count`, `paired_device_count`,
`offline_device_count`, `unreachable_device_count`
(`domain/smart_home/models.py:59-85`). Raises `ServiceError` via
`require_home` if the `home_id` is unknown (`:128`). `list_homes()`
(`:89-97`) is the existing method for enumerating every home when no
single `home_id` is given.

**No credential/secret surface exists in any of the above.**
`ConnectorCredentialStore` is not imported, referenced, or needed by
any method this contract uses — `connected_types`/`is_connected`/
`registered_types`/`metadata()` return only type-name strings, booleans,
and integer counts. §10 restates this as a binding constraint, not
merely an observation.

## 4. MVP scope

### Supported in MVP
- Per-connector-type registration state (`registered_types`) and live
  connection state (`is_connected`) — every registered type, not just
  connected ones.
- Per-home device-health counts (`room_count`/`zone_count`/
  `device_count`/`paired_device_count`/`offline_device_count`/
  `unreachable_device_count`), for one home or every home.

### Deferred
Everything named in §6.

## 5. Architecture decision — resolved with evidence, not by naming

**Rejected: Option A (extend `core/devtools/` directly).** §2's finding
is decisive — every existing `core/devtools/*.py` component is
scoped to app-internal/runtime introspection and depends only on
other `core/`-layer objects. A component importing
`services.connectivity_service.ConnectivityService`/
`services.smart_home_service.SmartHomeService` directly from
`core/devtools/` would be the **first** such dependency in that
package and would invert this codebase's own established layering
(`core/` defines ports/is depended upon; `services/` orchestrates
*above* `core/`, never the reverse — `CLAUDE.md`'s own architecture
section states this explicitly).

**Rejected: Option C (fold into another existing service).**
`ConnectivityService`/`SmartHomeService` already have well-defined,
narrower responsibilities (connector lifecycle; home/device CRUD).
Neither should grow a "diagnostics aggregation" concern bolted on —
the same reasoning `ApplianceService`'s own docstring already
established for *not* growing new branches onto an existing service
when a capability is conceptually distinct (Logic Contract precedent:
every M12 appliance-category slice since Task Group I chose a sibling
service over extension for exactly this reason; Task Group M chose
extension only because it was the *same* concept, not a new one — see
`docs/M12_SECURITY_ACTION_SLICE_LOGIC_CONTRACT.md` §2 for that
distinction applied the other way).

**Resolved: Option B, with a routing refinement.** A new, small
**`services/`-layer** service — **(PROPOSED)** working name
`DevtoolsConnectivityService` — depending only on the already-shipped
`ConnectivityService` + `SmartHomeService` (+ their existing
`ConnectorFactoryRegistry`, reached the same way `ConnectivityService`
itself already holds one, not a new dependency). Its **route**,
however, is added to the **existing** `routes/devtools.py` file (not
a new router file) — this is a presentation-layer/URL-namespace
concern, not a layering one, and keeps every Developer Mode capability
discoverable under the same `/api/v1/devtools/*` prefix, matching the
roadmap's own framing ("every milestone that ships a subsystem worth
inspecting live adds its own Developer Mode section"). The route's
container accessor pulls the new **service** (DI-injected, like every
other M12 service), not a `core/devtools/` component.

## 6. Explicitly deferred, with reasons

| Item | Why deferred |
|---|---|
| MQTT Debug Console | Needs raw message inspection/subscription infrastructure that doesn't exist; a materially different, larger capability. |
| Device Simulator | Needs a fake-device generation mechanism with no current analog. |
| Event Viewer | **The EventBus device-command publishing gap remains unresolved** (re-confirmed this session: `ConnectivityService.send_command` publishes nothing; only connectivity-lifecycle and CRUD events exist anywhere in M12). An Event Viewer over a bus that carries no device-command events would be misleadingly empty for the exact events an operator would want to see. Not worked around here. |
| Command tracing/replay, packet capture, raw MQTT message inspection, connector packet logs | No such infrastructure exists in `IDeviceConnector` or either connector implementation. |
| Latency, uptime, reconnect-history metrics | Not tracked anywhere (§3) — would be fabricated. |
| Device command history | No history table exists for any device category (verified: zero schema changes across all fifteen prior M12 task groups). |
| Automation/scheduler debugging | M7's Scheduler execution layer confirmed still unshipped. |
| Camera diagnostics | `VisionService` remains a Phase-4 stub; no camera service exists. |
| Analytics, Memory | M20A unshipped; `MemoryService` has zero device coupling. |
| Remote Access | M21 unshipped. |
| Frontend dashboards/live monitoring | Explicitly frozen this session; see §12. |

**No placeholder code or schema for any of the above.**

## 7. REST contract (PROPOSED)

```
GET /api/v1/devtools/connectivity?home_id=<optional>
```

Chosen over the Phase 0 placeholder (`/devtools/smart-home/connectivity`)
to match the existing file's own flat naming convention
(`/devtools/state`, `/devtools/api-calls`), not a nested smart-home
namespace — this *is* a devtools capability first, a smart-home data
source second.

**Response shape**:
```json
{
  "data": {
    "connectors": [
      {"connector_type": "home_assistant", "registered": true, "connected": true},
      {"connector_type": "mqtt", "registered": true, "connected": false}
    ],
    "homes": [
      {
        "home_id": "home_abc",
        "room_count": 4, "zone_count": 2, "device_count": 12,
        "paired_device_count": 10, "offline_device_count": 1,
        "unreachable_device_count": 1
      }
    ]
  },
  "meta": {"connector_count": 2, "home_count": 1}
}
```

**Behavior**:
- No `home_id` → `homes` contains one entry per home from
  `list_homes()` (§3) — an empty list if no homes exist, not an error.
- `home_id` given → `homes` contains exactly that one home's
  `HomeMetadata`; unknown `home_id` → **404** (the only `ServiceError`
  source in this route, given no permission gate exists — see §8).
- No connector registered at all → `connectors: []`, not an error
  (theoretical; the DI composition root always registers
  `home_assistant`+`mqtt` factories in practice, but the contract does
  not assume that).
- A registered-but-never-connected connector → `registered: true,
  connected: false`, not omitted.
- No smart-home devices in a home → all counts `0`, not an error.

**Authentication**: `Depends(get_current_session)`, matching every
other devtools route (§8).

## 8. Permission / security — resolved with evidence

**Decision: no `PermissionModel` gate, no new principal, no
`smart_home` scope — session auth only, matching every one of M9's
five existing devtools capabilities exactly (§2).** This is a
deliberate consistency choice, not an oversight: introducing a
`smart_home`-scoped principal here (the pattern every M12 *device
control* module uses) would be the **first** devtools capability with
a stronger gate than its four siblings, for data that is strictly
less sensitive than what several of those siblings already expose
ungated (Debug Console's live application logs, State Inspector's
full service/plugin state).

**Who may access this data today, precisely stated**: any session
holding a valid Bearer token — the same population that can already
read `/devtools/logs`, `/devtools/state`, etc. There is currently no
backend-enforced "Developer Mode must be unlocked" check on any
devtools route (§2). This capability does not change that boundary in
either direction; it is recorded here as an accurate description of
the boundary being *inherited*, not newly introduced or newly
weakened by this slice.

**Privacy consideration, evaluated explicitly**: device *counts* and
connector *connection state* reveal materially less than Sensors'
motion/presence data or Security's hazard/lock status (neither of
which this capability touches) — no occupancy inference, no security
posture, no device names or locations. This is why the decision above
does not import Sensors'/Security's own "gate reads too" precedent.

**No secrets, ever — structurally, not by convention.** This slice
never imports `ConnectorCredentialStore`, never reads
`Device.metadata_json` (where a connector-specific config could
theoretically live), and never touches a connector's own
configuration object — only `connected_types`/`is_connected`/
`registered_types` (plain type-name strings and booleans) and
`HomeMetadata` (integer counts). There is no code path by which a
password, token, API key, or MQTT credential could reach this
capability's response, because none of the methods it calls ever
return one (§3).

## 9. Data model — every field sourced, nothing fabricated

| Field | Source | Classification |
|---|---|---|
| `connector_type` | `ConnectorFactoryRegistry.registered_types` | VERIFIED IN REPOSITORY |
| `registered` | `ConnectorFactoryRegistry.supports(type)` | VERIFIED IN REPOSITORY |
| `connected` | `ConnectivityService.is_connected(type)` | VERIFIED IN REPOSITORY |
| `home_id`/`room_count`/`zone_count`/`device_count`/`paired_device_count`/`offline_device_count`/`unreachable_device_count` | `SmartHomeService.metadata(home_id)` → `HomeMetadata` | VERIFIED IN REPOSITORY |
| Latency, uptime, reconnect count, error count, per-device last-seen timestamp beyond what `HomeMetadata` already aggregates | — | **UNAVAILABLE — explicitly not included, not fabricated** |

## 10. Security boundaries (restated, binding)

Read-only. No device mutation. No `send_command()` call anywhere in
this slice. No connector command execution. No `EventBus` publish or
subscribe. No connector credential/config exposure (§8). No bypass of
`get_current_session`. No new authorization mechanism that could be
mistaken for stronger protection than what actually exists (§8's
honest accounting).

## 11. EventBus

**No event changes of any kind.** No publisher, no subscriber, no new
event class, no event history, no workaround for the device-command
publishing gap. This capability reads current state on demand; it
does not attempt to reconstruct or infer history from an event stream
that doesn't carry the relevant events (§6, Event Viewer row).

## 12. Frontend implication (conceptual only — no frontend touched)

A future Developer Mode panel could eventually surface this as a
"Connectivity & Device Health" section alongside the existing Debug
Console/Performance/State/API panels — conceptually a table of
connector rows plus a per-home counts summary. No frontend
requirements document is created in this Phase 1 pass; per the
established Water Heater/Security Action precedent, that would only
be written after this backend capability is implemented and verified,
and only if/when frontend work on it is actually scheduled.

## 13. Test strategy (future Phase 2 — described, not created)

**Connectivity**: connected connector, disconnected-but-registered
connector, multiple connectors, zero connectors registered, unknown
connector type requested (n/a — this endpoint enumerates registered
types, it does not accept one as input), connector registered but
never connected vs. connected-then-disconnected (both must read
`connected: false`, verifying `is_connected` is re-checked live, not
inferred from `connected_types` alone).

**Smart-home health**: zero devices, all devices paired/available,
partially offline/unreachable, all devices offline, multiple homes
(no `home_id` → full list), single-home filter (valid and unknown
`home_id`).

**Security**: unauthenticated request → 401/403 (no session);
confirms **no** `PermissionModel` grant is required for an
authenticated session (a positive assertion, mirroring how Water
Heater/Security Action pin their own confirmation-requirement
decisions); source-level test asserting no `ConnectorCredentialStore`
import and no `metadata_json` read exist anywhere in the new service.

**API**: envelope shape, empty state (zero connectors and zero
homes), 404 for unknown `home_id`, 200 for every valid combination
including all-zero counts.

**Agent tools**: successful read for both tools, empty-result phrasing
(no connectors registered; no homes exist), error propagation as a
string (never a raised exception reaching the agent loop).

**Architecture**: source-level tests confirming no device mutation
call exists, no `EventBus` reference exists, no direct connector
import exists (only `ConnectivityService`/`SmartHomeService`), no
database/schema changes accompany this slice, and — a guard specific
to this slice's own §5 finding — no `core/devtools/` file imports
anything from `services/`.

## 14. Agent tools (PROPOSED)

Two tools, matching the two genuinely different questions an operator
or agent would ask, mirroring Security's own "one broad, one narrow"
two-tool shape rather than forcing one call to answer both:

| Tool | Wraps | Arguments |
|---|---|---|
| `get_connector_status` | Connector-level portion of §7's response | none |
| `get_device_health` | Home-metadata portion of §7's response | `home_id: str = ""` (empty → all homes) |

Both read-only, no confirmation metadata (no real reason found to
require one for a diagnostic read — restated per instruction, not
assumed).

## 15. Acceptance criteria

- `DevtoolsConnectivityService` (or its eventually-chosen name) depends
  only on `ConnectivityService` + `SmartHomeService` — no `IDatabase`
  of its own, no `EventBus`, no direct connector import, no
  `ConnectorCredentialStore`.
- No `core/devtools/*.py` file imports from `services/` — the new
  service lives in `services/`, its route lives in the existing
  `routes/devtools.py`.
- `ConnectivityService`, `SmartHomeService`, and every existing
  `core/devtools/` component are **not modified**.
- No new `PermissionModel` principal or scope is created; the route
  requires only `Depends(get_current_session)`, matching every
  existing devtools route exactly.
- Every field in the response is traceable to an existing method call
  (§9) — no latency/uptime/reconnect/error field exists anywhere in
  the implementation.
- Unknown `home_id` → 404; missing/omitted `home_id` → every home's
  metadata, never an error.
- Zero connectors/zero homes → empty lists, `200`, never an error.
- No secret, token, password, or raw connector config appears in any
  response field — enforced structurally by which methods are called
  (§8), verified by a source-level test.
- Zero `EventBus` reference, zero `send_command` call, zero schema
  change, zero frontend file touched.
- Full backend regression stays green (baseline at the time of
  writing: 3417 tests, 0 failures, 0 errors, 1 pre-existing skip).
- This Logic Contract is reviewed and approved **before** any
  implementation begins.

Every criterion above is implementable without Scheduler, Analytics,
Mobile, EventBus changes, Memory, Camera/Vision, database/schema
changes, frontend source, or connector modifications.

## 16. Git safety

Verified before writing this file and re-verified after:
- HEAD: `58ae37d` (unchanged)
- Branch: `feature/m22-task-group-c`
- Working tree: clean before and after
- Zero source, frontend, roadmap, or CHANGELOG changes
- Zero commits, zero pushes
