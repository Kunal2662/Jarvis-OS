# M12 Developer Tools — Device Diagnostics — Logic Contract

Status: **Draft — Logic Contract only.** Written per `M12 TASK GROUP Q
— PHASE 1` approval, following the `M12 PHASE 0 POST-TASK-P AUDIT`
(delivered in-conversation; no audit file exists on disk — consistent
with every prior Phase 0 audit this session). **Not approved for
implementation** — no source, tests, DI, routes, roadmap, CHANGELOG,
or frontend changes accompany this file. Every claim about existing
code below is freshly re-verified against the current working tree
this session (clean, HEAD `ad3f2a3`), not carried over from the Phase
0 audit unchecked. Labeled per the requested convention:
**[REPO]** = verified directly by reading the current source this
turn; **[EXTERNAL]** = not verified against any live external source
this turn (none was fetched); **[UNVERIFIED]** = must be confirmed
during Phase 2 before relying on it.

## 1. Purpose

A single, thin, read-only devtools endpoint that answers "why isn't
this device working?" in one call — today a developer must separately
check `GET /devices/{id}` (identity), the device's own category route
(live state, if one exists), and a plugin-permissions call (grant
status) to get the same picture. Closes the still-unbuilt "Device
Diagnostics" item named explicitly in `MASTER_ROADMAP.md`'s own
Developer Tools feature list **[REPO]**.

## 2. Current source evidence

**[REPO]** `routes/devtools.py:234-256` — `get_plugin_diagnostics`,
the pattern this contract mirrors: no dedicated service, aggregation
logic lives directly in the route handler, calling three existing
accessors (`_plugin_registry`, `_permission_model`, `_debug_console`)
and assembling one plain dict. No error handling beyond what those
three calls themselves need (none of them raise for an unknown
`plugin_id` — `PluginRegistry.status`/`.health` return a
not-found-shaped status object rather than raising, confirmed by this
route's own absence of any `try`/`except`).

**[REPO]** `SmartHomeService.get_device(device_id) -> Device | None`
(`services/smart_home_service.py:412-414`) and
`.require_device(device_id) -> Device` (`:416-420`, raises plain
`ServiceError` for an unknown id). `Device`
(`infrastructure/database/models.py:1100-1150`) confirmed fields:
`id, home_id, room_id (nullable), name, device_type, status,
manufacturer, model, external_id (nullable), metadata_json,
created_at, updated_at, last_seen_at (nullable)`. `metadata_json` is a
real, readable ORM attribute — nothing prevents a careless caller from
serializing it; the safety property here is *behavioral discipline in
the response-building code*, not a structural guarantee, exactly the
same posture every existing device-category service's own
`_X_payload()` helper already relies on (each hand-picks fields, none
does `vars(device)`/`__dict__`).

**[REPO]** `ConnectivityService.read_raw_state(device_id) ->
DeviceState | None` (`services/connectivity_service.py:195-212`) —
re-traced this turn: returns `None` (not an error) when the device has
no `external_id` or no recorded `connector_type` in
`metadata_json["connector_type"]`; otherwise calls
`self._require_connector(connector_type)`, which **raises
`ConnectorNotConnectedError`** (a `ConnectivityError` subclass) if that
connector type is registered but not currently connected; then calls
`connector.read_state(external_id)`, which can raise a
connector-specific `ConnectivityError` subclass (e.g. the simulator's
own "unknown device", or a real connector's own reachability failure).
**Every existing device-category service already wraps this exact call
in `with contextlib.suppress(ConnectivityError): raw = await
connectivity.read_raw_state(device_id)`** (`smart_lighting_service.py`,
`smart_switch_service.py`, `thermostat_service.py`,
`smart_lock_service.py`, `sensor_service.py` — reconfirmed this turn)
— this contract reuses that identical, already-proven pattern rather
than inventing new error handling.

**[REPO]** `connector_type_for(device) -> str | None`
(`services/connectivity_service.py:63-79`) — reads
`metadata_json["connector_type"]` only; already the single existing
place this lookup happens, reused here rather than re-derived.

**[REPO]** `PermissionModel` (`core/plugins/permissions.py`, read in
full this turn) — confirmed **principal-based**, not literally
plugin-specific despite every parameter being named `plugin_id`
throughout the class; every M12 device-category service already
passes its own service-identifying string (`"core:smart_lighting"`,
`"core:security"`, ...) into that same parameter. Two read methods
exist: `is_granted(principal, scope) -> bool` and
`state(principal, scope) -> PermissionState`. **Decisive difference,
re-verified this turn**: `is_granted()` has a **side effect** —
`:97-102` shows it appends a `"denied_check"` `PermissionAuditEntry`
to `self._audit` every time it returns `False`. Calling it from a
passive diagnostic read would pollute another principal's own audit
trail (the same `audit_log` `get_plugin_diagnostics` itself reads) as
a side effect of a *read*. **`state()` has no side effect** — a plain
dict lookup with a `PermissionState.PENDING` default. This contract
uses `state()` only.

**[REPO]** Every declared M12 principal, re-enumerated this turn via
direct grep of every `services/*.py` file's own `*_PRINCIPAL = "core:
..."` constant:

| device_type | Owning service | Principal |
|---|---|---|
| `light` | `SmartLightingService` | `core:smart_lighting` |
| `switch` | `SmartSwitchService` | `core:smart_switch` |
| `lock` | `SmartLockService` | `core:smart_locks` |
| `sensor` | `SensorService` | `core:sensors` |
| `thermostat` | `ThermostatService` | `core:thermostats` |
| `appliance` | **four different services**, disambiguated only by `metadata["domain"]`/`["component"]` | `core:appliances` (fan/cover) / `core:media_players` / `core:vacuum_humidifier` / `core:water_heaters` |
| `camera` | none exists | none |
| `other` | none exists | none |

**No central `device_type -> principal` registry exists anywhere in
this codebase.** This is the single most important finding of this
contract (§8).

## 3. Architecture decision

**Option C — logic directly inside `routes/devtools.py`, mirroring
`get_plugin_diagnostics` exactly. Chosen over two alternatives, both
evaluated and rejected:**

- **Option A (new `services/`-layer service)** — rejected. The
  aggregation here (one device row + one live read + one permission
  lookup) is comparably simple to Plugin Diagnostics' own aggregation
  (registry status + health + logs + audit), which itself lives inline
  in the route with **no** dedicated service. Creating one here would
  be inconsistent with the one directly-comparable precedent in this
  exact file, and would be exactly the kind of "generic diagnostic
  framework" §17 of the implementation prompt warns against building
  prematurely.
- **Extending `DevtoolsConnectivityService`** — rejected. That
  service's own justification (Task Group N) was a genuinely compound,
  multi-home aggregation (`get_overview`) worth its own tested unit.
  Device Diagnostics' aggregation is a single-device, three-call
  lookup — closer in shape to Plugin Diagnostics than to Connectivity
  Health. Bolting an unrelated single-device method onto a service
  named for connector/home-level health would blur that service's own
  scope for no architectural gain.
- **Option C — chosen.** Two new thin accessors,
  `_smart_home(request)`/`_connectivity(request)`, added to
  `routes/devtools.py` in exactly the same one-line-`cast()` shape
  `_permission_model(request)` already uses. `PermissionModel` is
  reused via the **existing** `_permission_model(request)` accessor
  unchanged.

## 4. Diagnostic data model

```python
class DeviceSection(TypedDict):
    id: str
    name: str
    device_type: str
    status: str            # Device's own DB lifecycle status
    home_id: str
    room_id: str | None
    manufacturer: str
    model: str
    external_id: str | None
    last_seen_at: str | None   # ISO 8601, or null


class ConnectivitySection(TypedDict):
    connector_type: str | None   # e.g. "home_assistant"; null if none recorded
    read_succeeded: bool         # did the live read attempt itself complete
    status: str | None           # connector's raw status string; only when read_succeeded
    attributes: dict | None      # sanitized (see §7); only when read_succeeded
    read_error: str | None       # populated only when read_succeeded is False


class PermissionSection(TypedDict):
    principal: str | None
    scope: str | None
    state: str | None       # "pending" | "granted" | "denied"; null when principal unknown
    detail: str | None      # explanatory note when principal is null/ambiguous
```

**Deliberately excluded from the `Device` section**: `metadata_json`
in any form — never included wholesale, never partially, never even a
filtered subset of it (§7 explains why `connector_type` still appears,
sourced through `connector_type_for()`, not by exposing the raw JSON
field it reads from).

## 5. Connectivity / live read decision

**Best-effort, matching every existing device-category service's own
established pattern (§2) — not a new decision, a reuse of one already
proven correct across five shipped modules.** The route wraps
`connectivity.read_raw_state(device_id)` in the identical
`try`/`except ConnectivityError` shape those services already use, and
distinguishes three cases precisely, none of which collapses into a
generic 500:

1. **No connector recorded** (`read_raw_state` returns `None`) →
   `read_succeeded: false`, `read_error: "device has no recorded
   connector"`.
2. **Connector recorded but read raised** (not connected, or a
   connector-specific failure) → `read_succeeded: false`, `read_error`
   set to the caught exception's own message.
3. **Read succeeded** — including when the connector's own reported
   `status` is itself `"unavailable"`/`"offline"` — → `read_succeeded:
   true`, `status`/`attributes` populated verbatim (sanitized, §7).
   **`read_succeeded` intentionally does not mean "device is online"**
   — it means "the read attempt itself completed." Whether the
   *device* is online is exactly what the returned `status` string
   already tells the caller, the same distinction every other
   device-category service's own `available` field already draws.
   This contract does not reuse the word `available` for
   `read_succeeded`'s meaning, specifically to avoid colliding with
   that already-established, differently-scoped term.

## 6. Raw-state security decision

See §7 for the mechanism; the decision itself: **raw state is exposed,
sanitized by key, not withheld wholesale**, for a reason grounded in
existing behavior, not asserted from convenience: **for every
already-shipped, single-service device category (light, switch, lock,
sensor, thermostat, and every `appliance` sub-domain), this exact
attribute data is already reachable today** through that category's
own existing `GET .../{id}` route (e.g. `SmartLightingService.
get_light_state` already returns `brightness`/`color_temp_kelvin` from
the same `read_raw_state` call). Diagnostics does not open a new
exposure surface for those six categories — it aggregates data already
public through an existing, already-tested route. The one case where
this reasoning does **not** already apply is `camera` (no shipped
read service exists for it at all), which is exactly why §7's
key-based redaction exists as a real, load-bearing control rather than
pure formality.

## 7. Permission model

Uses `PermissionModel.state(principal, scope)` only (never
`is_granted()`, §2's side-effect finding). The `device_type ->
principal` table is the five-row, single-service subset of §2's table
only:

```python
_DEVICE_TYPE_PRINCIPALS: dict[str, str] = {
    "light": "core:smart_lighting",
    "switch": "core:smart_switch",
    "lock": "core:smart_locks",
    "sensor": "core:sensors",
    "thermostat": "core:thermostats",
}
```

**`appliance`, `camera`, `other` are deliberately left unresolved, not
guessed.** For `appliance`, resolving the correct one of four
principals would require replicating each appliance-domain service's
own private `metadata["domain"]`/`["component"]` fallback logic — the
exact complexity Task Group O (Smart Home Memory) and Task Group P
(Device Simulator) each independently declined to duplicate, for the
same reason. Building that resolution here, just to serve one field of
one diagnostic endpoint, would be precisely the kind of "generic
device capability registry" §17 forbids. For `appliance`, the
response reports `principal: null, scope: null, state: null, detail:
"appliance device_type spans multiple principals (core:appliances /
core:media_players / core:vacuum_humidifier / core:water_heaters);
not resolved by this diagnostic"`. For `camera`/`other` (and any
future `device_type` this table does not yet name), `detail: "no
dedicated permission principal exists for this device_type"`. Neither
case is an error — the response is still `200`, honestly reporting
"unresolved," never a fabricated guess.

## 6 (continued). Raw-state sanitization mechanism

`attributes` from a successful read is copied key-by-key; any key
whose lowercased name contains any of `token`, `password`, `secret`,
`credential`, `api_key`, `apikey`, or `auth` has its **value** replaced
with the literal string `"<redacted>"` — the key itself still appears
(so a developer can see *that* such an attribute exists, without its
value). Every other key/value passes through verbatim. **[EXTERNAL,
UNVERIFIED]** — informed by general, non-repository-sourced knowledge
that Home Assistant's own `camera` entity conventionally reports an
`access_token` attribute (used to authenticate snapshot/stream URLs);
this was not re-verified against live Home Assistant documentation
this session and must be treated as a motivating example only, not a
confirmed fact about this repository's own connector behavior — Phase
2 must independently confirm (or safely assume-worst-case regardless
of) this before relying on the redaction list being complete for
camera entities specifically.

## 8. Authentication

**Session authentication only — no `PermissionModel` gate on the route
itself.** Freshly re-verified, not assumed: `router = APIRouter(...,
dependencies=[Depends(get_current_session)])` at `routes/devtools.py:
63` applies uniformly to every route in the file including this one;
none of the file's existing eight routes (soon nine) carries any
additional gate. Explicitly reasoned, not inherited by default: this
endpoint is read-only, exposes no credential (§6/§7), and its most
sensitive-adjacent field (permission `state`) is a `PENDING`/
`GRANTED`/`DENIED` enum value about *another* principal's own grant
status — informational, not an action, and no more sensitive than
`get_plugin_diagnostics`'s own already-shipped, already-ungated
exposure of `permission_audit` entries for a plugin. Matches every one
of this router's other eight capabilities' own precedent exactly.

## 9. REST endpoint

```
GET /api/v1/devtools/devices/{device_id}/diagnostics
```

Lives in `routes/devtools.py`, placed after the Connectivity Health
section (grouping with device/connectivity-adjacent devtools
capabilities), before the Device Simulator section. No query
parameters — no `home_id` (the response's own `device.home_id` already
answers that; a filter would be meaningless for a single-resource
lookup), no `live`/`refresh` toggle (the live read already degrades
gracefully on failure, so a toggle would protect against a failure
mode that does not exist; a single-device read is cheap). No
`device_type` restriction — this is a read-only diagnostic, not a
control surface, so it works for **every** `DEVICE_TYPES` value
including `camera`/`other`, deliberately unlike Smart Home Memory/
Device Simulator's own narrower, control-oriented category scopes.

Response envelope matches every other route: `{data, meta}`, `data`
= `{device: DeviceSection, connectivity: ConnectivitySection,
permission: PermissionSection}`, `meta = {"device_type": ...}`.

## 10. Agent tool decision

**None.** No end-user or AI Home Assistant conversational use case
exists for a developer-facing diagnostic aggregate — nobody asks
JARVIS in natural language "give me the raw connectivity/permission
diagnostic for device X." Matches Device Simulator's own identical
reasoning (Logic Contract §11) exactly. No `Tool Registry` change, no
`AgentOrchestrator` change.

## 11. EventBus / Scheduler / Analytics / Memory

**None of the four.** Verified by tracing the exact three calls this
endpoint makes (`SmartHomeService.get_device`,
`ConnectivityService.read_raw_state`, `PermissionModel.state`) — none
touches `EventBus`, and this route adds no publish/subscribe of its
own. `Scheduler`/`Analytics` remain entirely absent from this
repository (re-confirmed via `find src/jarvis -iname "*scheduler*"`/
`"*analytics*"` this session — zero results). `MemoryService` is not
referenced or needed.

## 12. Database / schema

**None.** No new table, no new column, no migration. Every field in
§4 is either an existing `Device` column, an existing
`ConnectivityService`/connector return value, or an existing
`PermissionModel` state — nothing new is persisted.

## 13. Error semantics

| Condition | Behavior |
|---|---|
| Unknown `device_id` | `SmartHomeService.require_device`'s own plain `ServiceError` → 404, matching every other M12 `GET .../{id}` route's own convention |
| Live read fails/unavailable/no connector | **Not an HTTP error** — 200, `connectivity.read_succeeded: false` with `read_error` explaining why (§5) |
| Unsupported/unknown `device_type` for permission resolution | **Not an error** — 200, `permission.principal: null` with an explanatory `detail` (§7) |
| Permission lookup itself | Cannot fail — `PermissionModel.state()` never raises, always returns a `PermissionState` (default `PENDING`) |
| Malformed request | N/A — path parameter only, no request body; ordinary FastAPI path-param handling applies, nothing custom needed |
| Unexpected internal failure | Propagates unhandled as a genuine 500, exactly as every other unexpected exception in this codebase is treated — never silently swallowed |

## 14. Test strategy (future Phase 2 — described, not created)

Happy path (valid device, with and without live state, with a known
permission principal); every unique `device_type` including
`appliance` and an unsupported/synthetic type; unknown device → 404;
live-read failure paths (no connector recorded, connector not
connected, connector read error) each producing the correct
`read_succeeded`/`read_error` shape, not an HTTP error; permission
paths (`pending`/`granted`/`denied` for a known principal; `null` for
`appliance`/`camera`/unknown types); security tests confirming
`metadata_json` is never present in the response text, confirming a
seeded attribute key like `access_token`/`password` is redacted while
an ordinary key like `brightness` passes through; REST envelope shape;
session-only auth boundary (no grant needed); and architecture guards
mirroring every prior slice's own pattern — no `EventBus`/`Scheduler`/
`Analytics`/`MemoryService` reference, no schema change, no new
`CONNECTOR_TYPES`/`DEVICE_TYPES` entry, no frontend file touched, no
agent tool created, and (using the same AST-docstring-stripping guard
established in Task Groups M/N/O) confirming `is_granted` is never
called by this route's own code.

## 15. Deferred scope

Device command execution, command history/logging, Event Viewer, MQTT
Debug Console, automation debugging, EventBus integration, historical
diagnostics, uptime/latency analytics, automatic health monitoring,
notifications, frontend implementation, agent tools, and — explicitly
— **appliance sub-domain principal resolution** (§7) and any general
`device_type -> principal` registry mechanism beyond this endpoint's
own small, closed, five-row table. No placeholder code or scaffold for
any of the above.

## 16. Risks

- The redaction key-list (§7's "continued" section) is a deny-list,
  not a formal schema — a not-yet-anticipated sensitive key name could
  theoretically slip through. Mitigated, not eliminated: for the six
  already-shipped device categories this is not a *new* exposure
  (§6); for `camera`/`other` it is the primary safeguard, and its
  completeness for HA's own camera-entity conventions specifically is
  **[UNVERIFIED]** (§7) — Phase 2 must confirm or treat camera
  attribute exposure more conservatively if it cannot.
- `appliance`'s unresolved-principal response is a real, visible gap
  (a developer diagnosing a water heater gets `principal: null`) —
  accepted deliberately rather than duplicating four services' own
  private domain-resolution logic; documented, not hidden.

## 17. Acceptance criteria

- `GET /api/v1/devtools/devices/{device_id}/diagnostics` implemented
  directly in `routes/devtools.py`, no new service, no new `core/
  devtools/` component.
- `metadata_json` never appears in the response, in whole or in part,
  under any field name — pinned by a text-scan test.
- `is_granted()` is never called by this endpoint's own code —
  `state()` only, pinned by a source-level (docstring-stripped) guard.
- The `device_type -> principal` table contains exactly the five rows
  in §7 — no `appliance`/`camera`/`other` entry, no invented principal.
- No existing service (`SmartHomeService`, `ConnectivityService`,
  `PermissionModel`, or any device-category service) is modified.
- No `CONNECTOR_TYPES`/`DEVICE_TYPES` change.
- No database/schema change.
- No `PermissionModel` gate on the route — session auth only, pinned
  by a test.
- No agent tool, no `Tool Registry`/`AgentOrchestrator` change.
- Zero `EventBus`/Scheduler/Analytics/`MemoryService` reference.
- Zero frontend file touched.
- Unknown device → 404; live-read failure → 200 with an explanatory
  `read_error`, never a 500.
- This Logic Contract is reviewed and approved **before** any
  implementation begins.

## 18. Git safety (to be re-verified after writing)

Expected: exactly one new untracked file (this document), zero tracked
modifications, HEAD unchanged at `ad3f2a3`, origin unchanged at
`ad3f2a3`, no commit, no push.
