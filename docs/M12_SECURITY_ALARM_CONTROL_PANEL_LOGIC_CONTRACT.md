# M12 Task Group U — Security & Safety: alarm_control_panel Integration — Logic Contract

**Status: Phase 1 — Logic Contract only. No implementation.** Written
after independent, fresh re-verification of `SecurityService`,
`SirenService` (the architectural precedent this contract mirrors),
both connectors' domain-mapping tables, `AgentPermissionGate`,
`PermissionModel`, and live external verification against Home
Assistant's own current developer documentation — not by trusting the
Phase 0 audit's own conclusions without re-checking the source.

## 1. Scope

A standalone `AlarmControlPanelService` providing exactly five
capabilities: list panels, get one panel's live state, `arm_home`,
`arm_away`, `disarm`. `arm_night`/`arm_vacation`/`arm_custom_bypass`/
`trigger`, alarm history, automatic monitoring, and any Siren/Panic
Mode/Vacation Mode coupling are explicitly out of this task group
(§21). **No PIN/code parameter exists anywhere in this task group,
permanently, not as a deferred gap** (§8).

## 2. Fresh verification — `SecurityService` boundary

Re-read `src/jarvis/services/security_service.py` in full. Confirmed
unchanged since the Phase 0 audit: it owns no device category,
composes only already-shipped services (`SensorService`,
`SmartLockService`, `SmartLightingService`, `ThermostatService`), and
`trigger_panic_mode`'s own docstring states verbatim *"never touches
thermostats/cameras/sirens."* Extending it for alarm-panel control
would contradict its own documented, tested boundary — the identical
reasoning Task Group R already applied to rule out extending it for
`SirenService`. **Decision: standalone `AlarmControlPanelService`, not
a `SecurityService` extension.**

## 3. Fresh verification — `SirenService` as architectural precedent

Re-read `src/jarvis/services/siren_service.py`,
`src/jarvis/infrastructure/api/routes/sirens.py`, and
`src/jarvis/agents/tools/siren_tools.py` in full. This contract
mirrors `SirenService`'s architecture exactly:

```
AlarmControlPanelService
    -> SmartHomeService (require_device / list_devices)
    -> ConnectivityService (read_raw_state / send_command)
```

Confirmed identical dependency shape (`smart_home`, `connectivity`,
`permissions` — no `IDatabase`, no `EventBus`), identical identity
resolution pattern (`_require_<category>` raising a plain
`ServiceError` on domain mismatch), identical read pattern
(`get_<category>_state` merges a live `read_raw_state` inside
`contextlib.suppress(ConnectivityError)`), identical command dispatch
(`connector_type_for` → `_TRANSLATORS.get(connector_type)` →
`ConnectivityService.send_command(device_id, wire_command, payload)`
→ `{"device_id", "success", "detail"}`). **No new abstraction is
introduced beyond what `SirenService` already established.**

## 4. Fresh verification — device discovery and identity

Re-read `_DEVICE_DOMAINS` in both
`src/jarvis/core/connectivity/connectors/home_assistant.py` (line 92)
and `src/jarvis/core/connectivity/connectors/mqtt.py` (line 173).
Both map `"alarm_control_panel": "other"`, byte-identical in
structure to `"siren": "other"` on the line directly above each.
`SirenService`'s own module docstring independently names
`alarm_control_panel` as a fellow member of the `device_type="other"`
bucket. **Identity is already fully captured today, confirmed by
direct source read — zero connector or `DEVICE_TYPES` change.**

**Decision: `device_type == "other"` AND (`metadata["domain"] ==
"alarm_control_panel"` OR `metadata["component"] ==
"alarm_control_panel"`)**, reusing `SirenService`'s own `_domain_for`
fallback order (`domain` first, `component` second) verbatim — no new
domain-resolution framework, no ambiguity: a device's `domain`/
`component` value is a single string, mutually exclusive with
`"siren"`/every other `"other"`-bucket member.

**Precedent-conflict check (per process rule 8): none found.** The
Phase 0 audit's identity claim is confirmed exactly as stated, with no
discrepancy against fresh source evidence.

## 5. State model — externally verified

Verified live against Home Assistant's own developer documentation
(`developers.home-assistant.io/docs/core/entity/alarm-control-panel/`):
the `AlarmControlPanelState` enum has exactly 10 values: `disarmed`,
`armed_home`, `armed_away`, `armed_night`, `armed_vacation`,
`armed_custom_bypass`, `pending`, `arming`, `disarming`, `triggered`
— plus the universal `unavailable`/`unknown` every HA entity state
carries.

**Decision: expose HA's real state string verbatim, validated against
a closed set of these 10 values; anything unrecognized reports
`state: None`.** This mirrors `ApplianceService`'s own
`_COVER_STATE_VALUES`/`_infer_cover_state` pattern exactly (a closed
frozenset of real HA values, membership-checked, `None` on no match)
— not a new state-machine invention. No JARVIS-specific enum is
created; HA's own vocabulary is already exactly as granular as this
MVP needs, and collapsing `pending`/`arming`/`disarming`/`triggered`
into fewer buckets would discard real, meaningful distinctions with no
evidenced product need.

## 6. Read model

```python
{
    "id": str, "home_id": str, "room_id": str | None, "name": str,
    "status": str, "manufacturer": str, "model": str,
    "external_id": str | None,
    "state": str | None,       # one of the 10 HA values, or None
    "available": bool,
}
```

Identical identity-field shape to `SirenService`'s own
`_siren_payload`. `available` computed the same way every prior M12
device-category service does (`raw.status.strip().lower() not in
{"offline", "unavailable"}`). `list_alarm_control_panels` remains
DB-only (`state`/`available` not populated) — the same list/detail
asymmetry every prior M12 module draws; only `get_alarm_control_panel_
state` performs a live read. `Device.metadata_json` is never read for
payload content (§18).

## 7. Actions — exactly three, HA's own service names as the wire command

| Action | Method | HA service | MQTT command | Payload |
|---|---|---|---|---|
| Arm home | `arm_home(device_id)` | `alarm_arm_home` | `arm_home` | `{}` |
| Arm away | `arm_away(device_id)` | `alarm_arm_away` | `arm_away` | `{}` |
| Disarm | `disarm(device_id)` | `alarm_disarm` | `disarm` | `{}` |

Both translators (`_translate_home_assistant`/`_translate_mqtt`)
follow `SirenService`'s own exact shape — a closed
`_TRANSLATORS = {"home_assistant": ..., "mqtt": ...}` dict, each
function a bare `return command.value, {}` passthrough. **No
value/payload parameter is threaded through at all** (unlike Task
Group T's `set_fan_percentage`/`set_cover_position`, which legitimately
carry a value) — every action here is a zero-argument command, so
there is nothing analogous to thread through, and critically, **this
is also where the code/PIN boundary lives structurally**: the
translator signature has no parameter for one, so a code could not
leak into a wire payload even by future accident without a deliberate,
visible signature change.

## 8. PIN/code security — the binding, permanent boundary

**Externally re-verified** (`home-assistant.io/actions/alarm_control_
panel.alarm_disarm/`, `developers.home-assistant.io/docs/core/entity/
alarm-control-panel/`, `home-assistant.io/integrations/alarm_control_
panel.mqtt/`): `code` is an optional plain-string parameter on every
arm/disarm service; HA's own documentation provides **zero security
guidance** on storing, logging, or transmitting it; HA's own MQTT
alarm integration explicitly warns *"When your MQTT connection is not
secured, this will send your secret code over the network
unprotected!"* when its own `REMOTE_CODE` feature is used.

**Decision, binding and permanent for this task group: no code/PIN
parameter is accepted, stored, logged, or transmitted anywhere** —
not in `AlarmControlPanelService`'s method signatures, not in REST
request bodies, not in agent-tool arguments, not in the wire payload,
not in `Device.metadata_json`, not in any log line. Every action is
sent bare (§7). HA's own documentation confirms this is a *complete,
valid* call for any panel that does not require a code (*"not every
alarm panel requires a code"*); a code-protected panel will simply
report the action failed via the existing, honest
`CommandResult.success=False` path (§14) — never silently wrong, never
a fabricated success. This mirrors `SirenService`'s own precedent of
sending a bare call and letting device-reported capability gaps
surface as an honest failure rather than being pre-validated or worked
around.

**This closes the MQTT security risk HA's own docs warn about
entirely**: since no code is ever placed in either the HA REST payload
or this module's own JARVIS-native MQTT vocabulary, the "secret code
over unprotected MQTT" scenario cannot occur in this codebase's
implementation, regardless of the underlying MQTT broker's own TLS
configuration.

## 9. MQTT translation

No standard MQTT equivalent for alarm arm/disarm exists in any spec
this repository follows (HA's own MQTT alarm_control_panel integration
is a distinct, real HA integration this codebase does not implement —
confirmed by direct source read of `mqtt.py`, which defines its own
JARVIS-native vocabulary throughout, never HA's MQTT wire protocol).
Per `SirenService`'s own established precedent, this module defines
its own vocabulary mirroring HA's service names exactly
(`arm_home`/`arm_away`/`disarm`, empty payload). Both connectors'
`send_command(external_id, command, payload)` already accept an
arbitrary payload dict generically (confirmed by direct read of
`HomeAssistantConnector.send_command` lines 230-255 and
`MqttConnector.send_command` lines 460-483 in the Phase 0 audit,
unchanged since) — **zero connector modification**.

## 10. REST design

Own top-level resource, not nested under `/security/*` — matching
`SirenService`'s own precedent exactly (`routes/sirens.py`'s own
docstring: *"its own sibling service, not a `SecurityService`
extension... follows the same top-level-resource convention"*).

| Endpoint | Method | Body | Response |
|---|---|---|---|
| `/api/v1/alarm-control-panels` | `GET` | — | `Envelope[list[dict]]` |
| `/api/v1/alarm-control-panels/{device_id}` | `GET` | — | `Envelope[dict]` |
| `/api/v1/alarm-control-panels/{device_id}/arm_home` | `POST` | — (no body) | `Envelope[{device_id, success, detail}]` |
| `/api/v1/alarm-control-panels/{device_id}/arm_away` | `POST` | — (no body) | `Envelope[{device_id, success, detail}]` |
| `/api/v1/alarm-control-panels/{device_id}/disarm` | `POST` | — (no body) | `Envelope[{device_id, success, detail}]` |

**No request body on any mutation endpoint** — no Pydantic model is
defined at all, since there is no field to carry (unlike Task Group
T's `SetFanPercentageRequest`; there is nothing analogous here,
deliberately, per §8). Status codes mirror `routes/sirens.py` exactly:
`GET .../{id}` → 404 on unknown device or wrong domain; every action
endpoint → 400 on any `ServiceError` (unknown device, wrong domain,
permission not granted alike). No generic `/action` or `/state`
endpoint; no `code` query parameter or body field of any kind.

## 11. Agent tools

Exactly five, mirroring `SirenService`'s own four-tool structure
(list/get/mutation×2) extended by one for the second ungated mutation:

| Tool | Confirmation | Permission |
|---|---|---|
| `list_alarm_control_panels` | — | ungated |
| `get_alarm_control_panel_state` | — | ungated |
| `arm_home` | No | `core:alarm_control_panels`/`smart_home` |
| `arm_away` | No | `core:alarm_control_panels`/`smart_home` |
| `disarm` | **Yes** | `core:alarm_control_panels`/`smart_home` |

No tool accepts a `code`/`pin` argument (§8) — the tool's own
LangChain-generated argument schema has no such field to fill, so an
agent cannot pass one even if a user supplied it in conversation; the
absence is structural, not a validation rule that could be bypassed.
No duplication of any existing tool.

## 12. Confirmation model — independently reasoned

**Freshly re-verified against `src/jarvis/agents/permission.py`**:
`AgentPermissionGate.authorize(tool_name, args, *, confirm=None)`
gates by `tool_name` membership in `confirm_required_tools` only —
confirmed by direct read, no argument inspection exists in this class
at all. This structurally requires `disarm` to be its own distinctly-
named tool to be independently confirmable, which it already
naturally is as a separate HA service (§7).

- **`arm_home`/`arm_away`**: **not** confirmation-gated. Reasoning,
  independently derived, not inherited: arming *adds* protection and
  is the safe direction of this binary-risk pair — the same structural
  position `lock_device` and `turn_siren_off` already occupy in this
  codebase's own established asymmetry.
- **`disarm`**: confirmation-gated, added to
  `AgentSettings.confirm_required_tools`. Reasoning: disarming
  *removes* protection — the same structural position `unlock_device`
  occupies, and this codebase has gated that exact direction every
  time an analogous binary-security pair has appeared
  (`lock_device`/`unlock_device`, `turn_siren_off`/`turn_siren_on`).

`arm_night`/`arm_vacation`/`arm_custom_bypass`/`trigger` are out of
scope (§21) and therefore have no confirmation decision to make in
this contract; a future slice adding them would need to reason about
`trigger` specifically and separately, given its materially larger and
less-bounded real-world consequence (§21).

## 13. Permission model

**New principal, no per-action granularity — confirmed necessary and
sufficient by fresh source inspection.** `PermissionModel` (re-verified
unchanged) gates by `(principal, scope)` only, with no finer-grained
per-method concept; no M12 module has ever split one principal across
its own mutations (Siren's own `core:sirens` covers both `turn_on` and
`turn_off` identically). **Decision: `core:alarm_control_panels`**
declared against the existing `smart_home` scope — reads
(`list_alarm_control_panels`, `get_alarm_control_panel_state`)
ungated; all three mutations (`arm_home`, `arm_away`, `disarm`) gated
under the same single grant. This is a documented limitation, not
worked around: `PermissionModel` cannot express "grant arm but not
disarm" without inventing a second principal this task group's own
process rules forbid inventing without stronger evidence than exists
today.

## 14. Error semantics

| Condition | Behavior |
|---|---|
| Unknown device | `ServiceError` from `require_device` → REST 404 (`GET`) / 400 (mutations) |
| Device exists but wrong `device_type`/domain | `ServiceError` ("is not an alarm control panel") → REST 404 (`GET`) / 400 (mutations) |
| Unavailable device (read) | `available: false`, `state: None` — never fails the read, mirrors every prior M12 `get_<category>_state` |
| Unrecognized/unmapped HA state string | `state: None` — never fabricated, never guessed (§5) |
| No recorded connector | `ServiceError` → REST 400 |
| No translation for connector type | `ServiceError` → REST 400 (dead code today — both `CONNECTOR_TYPES` entries covered) |
| Connector-reported command failure | `CommandResult.success=False` → REST 200 with `success: false`, `detail` populated — never an HTTP error, matches every prior M12 mutation |
| Permission not granted | `ServiceError` → REST 400 |
| Confirmation denied (agent path) | Tool call blocked before the service method is ever invoked — `AgentPermissionGate`'s own existing behavior, unchanged |
| No confirmation channel available | `auto_deny_when_unconfirmable=True` (existing, unchanged default) — denies, never silently allows |

## 15. Security/privacy audit

- `Device.metadata_json` is never read for payload content (§6) —
  identical discipline to every prior M12 module.
- No credential, token, or secret field exists anywhere in the read
  model, the request/response schema, or the wire payload.
- **No PIN/code parameter exists anywhere in this task group's own
  surface** (§8) — REST, tools, service methods, connector payload,
  persistence, and logging are all structurally incapable of carrying
  one, since none of their signatures/schemas define a field for it.
  This is not "the code is redacted before logging" (a runtime
  safeguard that could fail); it is "the code was never accepted as
  input" (a structural absence that cannot fail).
- Reads (`list`/`get`) remain **ungated**, matching `SirenService`'s
  own precedent — an alarm panel's arm/disarm *state* is comparable in
  sensitivity to a lock's locked/unlocked state (both already-shipped,
  already-ungated-for-reads categories), not to hazard-sensor data
  (which `SecurityService` itself treats specially). No new privacy
  tier is introduced.

## 16. EventBus boundary

Not used. No event subscription or publication anywhere in this
module — the same `ConnectivityService.send_command` chokepoint every
M12 mutation already uses, which itself does not publish device-
command events (the pre-existing, unrelated, already-documented gap).

## 17. Scheduler boundary

Not used. No recurring/scheduled arm or disarm. Every action is
explicit, synchronous, single-call.

## 18. Analytics/Memory boundary

Not used. No alarm history, no trend/aggregation, no
`SmartHomeMemoryService` coupling of any kind in this task group.
(`SmartHomeMemoryService`'s own Tier-2 appliance cascade is unrelated
architecture — this module lives in the `"other"` bucket, not
`"appliance"`, and is not added to any snapshot dispatch table.)

## 19. Notification boundary

Not used, and not required for `arm_home`/`arm_away`/`disarm` to be
genuinely useful — each is a direct, self-contained command to a real
device, the same as every other M12 mutation. No notification
transport exists in this repository (reconfirmed unchanged).

## 20. Siren / Panic Mode / Vacation Mode boundary

**Explicitly prohibited, reconfirmed, no coupling of any kind:**
`AlarmControlPanelService` does not call `SirenService`, is not called
by `SirenService`, and is not referenced by `SecurityService.
trigger_panic_mode`/`trigger_vacation_mode` in either direction.
Nothing in fresh source evidence found any dependency that would
justify introducing this coupling; Task Group R's own deferral of
Panic↔Siren coupling stands unchanged and is not reopened here.

## 21. Explicitly deferred scope

| Item | Why deferred |
|---|---|
| `arm_night`, `arm_vacation`, `arm_custom_bypass` | Narrower, lower-value variants of the same already-proven `arm_home`/`arm_away` mechanism — a natural, low-risk follow-on slice, not a blocker |
| `trigger` | Materially different, less-bounded real-world consequence than any action this codebase has built (may reach a monitored responder this codebase cannot see or control); also least useful without notification infrastructure, which does not exist |
| PIN/code support in any form | **Permanent boundary**, not merely unbuilt — see §8 |
| Alarm history / persistence | No schema change in this task group (§22); would need its own contract |
| Automatic alarm monitoring | Needs the still-unresolved EventBus device-command publishing gap |
| Siren coupling, Panic Mode coupling, Vacation Mode coupling | §20 |
| Notifications/escalation | No transport exists |
| Remote access | M21 unstarted, unrelated |
| Frontend implementation | Frozen this phase; a frontend requirements document (planning-only, no source) may be created after Phase 2 backend verification, following the established Siren/Fan-Cover-Position precedent — not created now |

**No placeholder code, route, tool, or field for any of the above.**

## 22. Database/schema

**Zero schema changes.** No alarm state, code, or action history is
persisted anywhere — every read is live (mirrors `SirenService`'s own
`get_siren_state`), every action result is returned once and never
stored, matching every prior M12 device-category service.

## 23. Integration/wiring (verified against the exact Siren precedent)

- **DI**: `container.py` gains a `_build_alarm_control_panel_service(*,
  smart_home_service, connectivity_service, permission_model)`
  function and an `alarm_control_panel_service = providers.Singleton(...)`
  provider, placed and shaped identically to `_build_siren_service`/
  `siren_service` (confirmed exact current shape at container.py
  lines 694-703 and 1663-1668).
- **`AgentOrchestrator`**: gains an `alarm_control_panels` optional
  constructor parameter, threaded to `build_tool_registry` inside
  `start()`, mirroring `siren`'s own wiring.
- **Tool Registry** (`agents/tools/registry.py`): gains an
  `alarm_control_panels: AlarmControlPanelService | None = None`
  parameter and a `build_alarm_control_panel_tools(...)` call inside
  an `if alarm_control_panels is not None:` block, mirroring the
  `siren` block exactly.
- **FastAPI** (`fastapi_server.py`): gains an import and
  `app.include_router(alarm_control_panel_routes.router,
  prefix="/api/v1")` line, alphabetically positioned, mirroring the
  `sirens` router registration.
- No modification to any other module's own wiring.

## 24. Testing strategy (described for Phase 2, not created now)

- **Discovery/identity**: domain-match, component-match (fallback),
  domain-takes-precedence-over-component, wrong `device_type` even
  with matching domain metadata, missing metadata, non-alarm
  `"other"`-bucket device (e.g. a siren) correctly rejected, no false
  match with any other M12 device-category service.
- **List/get**: DB-only list (no live `state`), live get for each of
  the 10 verified HA states individually, unrecognized state → `None`,
  unavailable → `state: None`/`available: false`, unknown device → 404
  (`GET`).
- **Actions**: `arm_home`/`arm_away`/`disarm` each — HA translation
  (correct service name, empty payload), MQTT translation (correct
  command, empty payload), permission-denied, connector-failure
  honesty (`success: false`, `detail` populated, never an HTTP error),
  unknown device → 400, wrong-domain device → 400, no recorded
  connector, no translation for connector type.
- **Confirmation**: `disarm` requires confirmation (approve/decline/no-
  channel-auto-deny, exercised against the real `AgentPermissionGate`,
  not a stand-in); `arm_home`/`arm_away` do not; a production-default
  assertion pinning `disarm` in and `arm_home`/`arm_away` out of
  `AgentSettings.confirm_required_tools`.
- **REST**: auth required on every route, envelope shape, 404 vs 400
  status-code matrix, no request body accepted on any mutation route
  (a body if sent is simply ignored/irrelevant, never interpreted as a
  code).
- **Security**: no `metadata_json` in any payload; a source-level
  guard (AST-based, docstring-stripped, reusing this session's
  established `_code_without_docstrings` helper) confirming zero
  reference to `code`/`pin`/`credential`/`secret` as a real parameter
  name anywhere in the module's actual code (not its explanatory
  prose, which legitimately discusses the PIN boundary at length);
  zero `EventBus`/`Scheduler`/`SmartHomeMemoryService`/`SirenService`/
  notification reference.
- **Tool Registry / DI**: registry inclusion when wired, omission when
  not, `AgentOrchestrator.__init__` signature includes
  `alarm_control_panels`, a live DI container sanity check resolving
  the new service and all five tools.
- **Regression**: full targeted re-run of every existing Security &
  Safety, Siren, and Appliance Control test file — none of them
  reference this new module, but the standing discipline is to prove
  it, not assume it.

## 25. Acceptance criteria

- `AlarmControlPanelService` depends only on `SmartHomeService` +
  `ConnectivityService` + `PermissionModel` — no `EventBus`, no
  `IDatabase`, no direct connector import, no `SirenService`/
  `SecurityService` dependency in either direction.
- Identity resolves via `device_type == "other"` +
  `domain`/`component` fallback, zero new domain-resolution framework.
- `state` is always one of the 10 verified HA values or `None` — never
  fabricated.
- Exactly three mutations exist: `arm_home`, `arm_away`, `disarm`. No
  `arm_night`/`arm_vacation`/`arm_custom_bypass`/`trigger` method,
  route, or tool exists anywhere in the implementation.
- **No method, route, tool, or connector payload anywhere in the
  implementation accepts, stores, logs, or transmits a `code`/`pin`
  value** — verified by both code review and an automated source
  guard.
- `disarm` alone is in `confirm_required_tools`; `arm_home`/`arm_away`
  are not.
- One new principal (`core:alarm_control_panels`), no new scope, reads
  ungated, mutations gated.
- Zero database/schema changes.
- Zero connector modifications (`home_assistant.py`, `mqtt.py`
  untouched).
- Zero frontend source touched.
- Full M12 regression, M11+M12 regression, and full backend regression
  all green before any commit (Phase 2 requirement, not this
  document's own claim).
- Clean git state (this contract as the only untracked file) before
  Phase 2 implementation begins.
