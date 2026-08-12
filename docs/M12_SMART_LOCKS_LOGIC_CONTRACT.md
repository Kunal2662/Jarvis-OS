# M12 Smart Locks — Logic Contract

Status: Approved for implementation. Base: the shipped M12 Connectivity
REST + Smart Lighting implementation (`docs/
M12_CONNECTIVITY_REST_SMART_LIGHTING_LOGIC_CONTRACT.md`, commits
`48e089d`/`fcda155`). Smart Locks reuses that implementation's exact
architecture — `ConnectivityService`/`SmartHomeService`/`PermissionModel`/
Tool Registry/`AgentOrchestrator` — and adds nothing new to any of them
except the same kind of thin orchestration service and REST/tool surface
Smart Lighting already proved.

## 1. Purpose

Normalized lock/unlock control and state reporting for `device_type=
"lock"` devices, over REST and as agent tools, converging on the same
`ConnectivityService.send_command` chokepoint every other M12 command
already uses. First of M12's remaining device-category modules to ship
after Smart Lighting (Task Group C).

## 2. Responsibilities

- Translate two normalized commands (`lock`, `unlock`) into each
  connector's wire format.
- Report a lock's live state (locked/unlocked/unknown) by reading
  through the connector, never by inventing a health check.
- Enforce the existing `smart_home` permission scope on both mutating
  operations.
- Expose the above over REST and as agent tools, both calling the same
  service so neither path is privileged over the other.

**Explicitly not this module's job** (unchanged from Smart Lighting's
own carve-outs, applied here): device discovery (already `Connectivity
Service.run_discovery`), device pairing (already `SmartHomeService.
pair_device`), a real physical handshake behind pairing (still doesn't
exist — see §12), guest access codes / temporary PIN management
(no schema exists for this and none is added — see §11), automation
("Auto Lock" triggers) — deferred to the unstarted Home Automation
module, matching Smart Lighting's own "no automation triggers" carve-out.

## 3. Normalized lock device model

A lock is a `Device` row (`infrastructure/database/models.py`, Task
Group A, unmodified) with `device_type="lock"` — no new ORM model, no
new table. Its REST/tool-facing payload:

```
{
  "id": str,               # Device.id
  "home_id": str,
  "room_id": str | None,
  "name": str,
  "status": str,            # Device.status -- connectivity lifecycle
                             # (paired/offline/unreachable/...), NOT
                             # locked/unlocked -- see Smart Lighting's
                             # own Device.status vs on/off distinction.
  "manufacturer": str,
  "model": str,
  "external_id": str | None,
  "locked": bool | None,    # None = unknown/unreadable
  "available": bool,        # derived: True unless the live read failed
                             # AND no prior state exists
}
```

This is a structural mirror of Smart Lighting's own `_light_payload`
(`on`/`brightness`/`color_temp_kelvin`/`color`), reduced to the one
attribute a lock actually has.

## 4. Lock / unlock states

Two normalized commands, `LockCommand.LOCK` / `LockCommand.UNLOCK`
(`StrEnum`, mirroring `LightCommand`) — no merge case exists (a lock has
exactly one attribute), so unlike Smart Lighting's translators there is
no "combine several changed attributes into one wire call" concern.

`locked: bool | None` is derived from a connector's raw `DeviceState.
status` string via the same best-effort heuristic pattern `_infer_on`
already established for lights — not a guess at a new closed
vocabulary:
- `{"locked", "true", "1"}` → `locked=True`
- `{"unlocked", "false", "0"}` → `locked=False`
- anything else (`"jammed"`, `"locking"`, `"unlocking"`, or an unread
  value) → `locked=None` ("unknown/transitional"), never invented as a
  new closed state. **Only locked/unlocked are modeled as real states**,
  per the kickoff's own "support additional lock states only if already
  represented by the existing connector/device model" instruction —
  neither `HomeAssistantConnector` nor `MqttConnector` normalizes
  `jammed`/`locking`/`unlocking` into anything today (both simply pass
  a connector's raw state string through unchanged), so this module
  does not invent handling for states the connector layer itself does
  not represent.

## 5. Availability

`available: bool` in the REST/tool payload is derived, not stored:
`True` unless `get_lock_state`'s live read raised `ConnectivityError`
(connector unreachable/not connected) **and** no state was ever
readable — mirrors `get_light_state`'s own "fall back to last-known
state, never fail the read" behavior exactly. Never a live health
check beyond the read this operation already performs.

## 6. Capabilities

Fixed, closed, exactly two mutating capabilities (`lock`, `unlock`) plus
state read — no capability negotiation, no per-device capability
discovery. If a device claims `device_type="lock"` it is assumed to
support both; a connector/vendor that genuinely cannot lock (only
unlock, e.g. some smart latches) is out of scope — nothing in
`DEVICE_TYPES` or either connector's discovery distinguishes that today,
and inventing a distinction neither connector reports would violate
the "do not invent capabilities the connectors cannot provide" rule.

## 7. REST endpoints

`/api/v1/smart-locks/*`, same envelope/auth/error conventions as
`routes/smart_lighting.py`:

| Method | Path | Behavior |
|---|---|---|
| GET | `/smart-locks` | List locks (`home_id`/`room_id` filters), DB-only, no live read — mirrors `list_lights`. |
| GET | `/smart-locks/{device_id}` | One lock's live state (`get_lock_state`) — 404 if unknown/not a lock. |
| POST | `/smart-locks/{device_id}/lock` | Locks the device. |
| POST | `/smart-locks/{device_id}/unlock` | Unlocks the device. |

**No pairing endpoint** — reuses the existing `POST /devices/{id}/pair`
verbatim, per the kickoff's explicit instruction. **No `/state` PATCH
endpoint** (unlike Smart Lighting's merged `/state`) — a lock has one
binary attribute with no merge benefit, so two explicit action verbs
(`lock`/`unlock`) are clearer than a body-driven `{"locked": bool}`
endpoint and match the kickoff's own enumerated operations exactly.

## 8. Request/response schemas

`POST .../lock` and `POST .../unlock` take **no request body** — there
is nothing to parametrize (unlike Smart Lighting's brightness/color
fields). Response (both, `{data, meta}`):

```
data: {"device_id": str, "success": bool, "detail": str}
meta: {"success": bool}
```

`GET /smart-locks/{id}` response `data` is the §3 payload shape.
`GET /smart-locks` response `data` is a list of that shape, `meta:
{"count": int}`.

## 9. `{data, meta}` envelope

Identical to every resource router since M9 Task Group E — `Envelope`/
`envelope()` from `infrastructure/api/auth.py`, no new envelope shape.

## 10. Error taxonomy

Identical mapping convention to `routes/smart_lighting.py` (itself
matching `routes/smart_home.py`'s `pair_device` precedent):
- `GET /smart-locks/{id}` unknown/wrong-type device → `ServiceError` →
  **404** (plain single-resource `GET` convention).
- `POST .../lock` / `POST .../unlock` — any `ServiceError` (unknown
  device, wrong type, permission not granted) → **400** (action-endpoint
  convention, message-agnostic, exactly `pair_device`'s own choice).
- A connector-level failure (not connected, no recorded connector) is
  also a `ServiceError` at this layer (`SmartLockService` raises it
  directly, mirroring `SmartLightingService`'s own "no recorded
  connector" `ServiceError`, rather than leaking `ConnectivityError`)
  → 400.
- `CommandResult.success=False` (the device itself rejected the
  command) is **not** an error — 200 with `success: false` in the body,
  identical to Smart Lighting's own "a real, expected outcome" framing.

## 11. Connector mapping

### Home Assistant

`HomeAssistantConnector.send_command(external_id, command, payload)`
does `POST /api/services/{domain}/{command}` with body
`{"entity_id": external_id, **payload}`, domain derived from
`external_id.split(".", 1)[0]` — unchanged, verified against the shipped
connector this same session. For an entity id `lock.front_door`,
domain=`lock`. Home Assistant's own lock domain services are `lock.lock`
and `lock.unlock` — no attributes, no payload fields.

| Normalized | HA command | HA payload |
|---|---|---|
| `LOCK` | `"lock"` | `{}` |
| `UNLOCK` | `"unlock"` | `{}` |

No merge case exists (§4) — every call is a single wire command.

### MQTT

`MqttConnector.send_command` calls `build_command_envelope(external_id,
command, payload)` (`mqtt_envelope.py`, unchanged, re-verified this
session), which is deliberately free-form — `{"command": command, "args":
dict(payload)}` inside the standard envelope, published to the device's
`command_topic` (or the native fallback topic). No lock consumer of
this vocabulary existed before this module, exactly the same "this
module defines it" situation Smart Lighting's own MQTT translation was
in for `turn_off`/`set_state`. Rather than reusing Smart Lighting's
`set_state` (which exists to merge multiple attributes — a lock never
has more than one), this module defines its own two-command vocabulary,
mirroring HA's own service names for cross-connector predictability:

| Normalized | MQTT `command` | MQTT `args` |
|---|---|---|
| `LOCK` | `"lock"` | `{}` |
| `UNLOCK` | `"unlock"` | `{}` |

## 12. Permission requirements

Identical mechanism to Smart Lighting, not a new one: the existing
`PermissionModel` (`core/plugins/permissions.py`), scope `smart_home`
(same pre-declared, shared scope — locks and lights are not separately
scoped; `PERMISSION_SCOPES` has one `smart_home` entry, not one per
device category). New fixed principal `core:smart_locks` (mirrors
`core:smart_lighting`'s naming exactly), declared once at
`SmartLockService` construction (`PENDING` by default). Both `lock` and
`unlock` require `is_granted(SMART_LOCK_PRINCIPAL, "smart_home")`;
reads (`list_locks`, `get_lock_state`) do not. Granted through the
*existing* generic route, `POST /api/v1/plugins/{principal}/
permissions/{scope}/grant` — no new grant surface, exactly Smart
Lighting's own reuse.

**Not pretending pairing is a real handshake.** `SmartHomeService.
pair_device` remains a bare `discovered`→`paired` status transition
with no protocol handshake behind it — reused verbatim here (§7), and
this module does not claim otherwise for locks either, matching Task
Group A's own honest framing.

## 13. Agent/Tool Registry integration

Four tools, mirroring `smart_lighting_tools.py`'s structure exactly —
`agents/tools/smart_lock_tools.py`, `build_smart_lock_tools(smart_lock:
SmartLockService) -> list[BaseTool]`:

| Tool | Wraps | Mutating? |
|---|---|---|
| `list_locks` | `list_locks()` | No |
| `get_lock_status` | `get_lock_state()` | No |
| `lock_device` | `lock()` | Yes |
| `unlock_device` | `unlock()` | Yes |

Named `lock_device`/`unlock_device` rather than the bare verbs `lock`/
`unlock` the kickoff message names informally — bare single-word tool
names read ambiguously in a shared registry the way every other tool
here uses a verb+object shape (`set_light_state`, `apply_scene`), and
this keeps `confirm_required_tools` entries (§14) unambiguous in
`AgentSettings`. Wired into `agents/tools/registry.py`'s
`build_tool_registry(smart_lock=...)`, `AgentOrchestrator.__init__`/
`.start()`, and `core/di/container.py`'s `_build_agent_orchestrator` +
`agent_orchestrator` provider — the same four-point pattern already
threaded for `smart_lighting`. No parallel execution path: REST and
tools both call `SmartLockService`, which is the only caller of
`ConnectivityService.send_command` for locks.

## 14. Confirmation requirements

**Resolved: `unlock_device` is added to `AgentSettings.
confirm_required_tools`'s default set; `lock_device` is not.**

Reuses the existing `AgentPermissionGate.confirm_required_tools`
mechanism exactly as it already works for `run_automation` — no new
confirmation system, no change to `AgentPermissionGate` itself, only an
addition to the curated default `frozenset` in
`core/config/settings.py` (`confirm_required_tools: frozenset[str] =
frozenset({"run_automation", "unlock_device"})`), an operator-overridable
setting, not a hardcoded gate.

**Why unlock only, not lock too:** unlocking is the direction with real
security consequence (an agent or a misfired voice command unlocking a
door is the failure mode worth a human "yes"); locking is the
fail-safe direction the roadmap's own "Auto Lock" feature (unstarted,
Home Automation-adjacent) explicitly expects to happen unattended —
requiring interactive confirmation for every lock action would make
that future feature pointless and adds friction to the common,
low-risk case ("lock the front door") for no safety benefit. This
mirrors `confirm_required_tools`'s own existing precedent: a small,
deliberately curated set of specifically named high-risk tools, not a
blanket category-wide gate.

This confirmation gate applies **only to the agent-tool path** — the
REST endpoints (§7) are not gated by `AgentPermissionGate` (that gate
sits in the LangGraph tool-execution node, not in FastAPI); REST callers
are already behind `Depends(get_current_session)` Bearer auth plus the
`smart_home` `PermissionModel` grant (§12), the same two-layer posture
every other M12 REST surface has. This is a deliberate, existing
asymmetry (the agent path adds an extra interactive-confirmation layer
because it can act autonomously; a REST caller is already an
authenticated, explicit human/client action) — not a gap.

## 15. Event behavior

Reuses `DeviceUpdatedEvent` verbatim — no new event class. **Neither
`lock()`/`unlock()` publishes one directly**, mirroring
`SmartLightingService.set_light_state`'s own behavior exactly (it does
not call `SmartHomeService.report_device_state` either) — a command's
`CommandResult.success=True` means "handed to the connector," not "the
DB's view of this device changed," so there is nothing new to publish.
`DeviceUpdatedEvent(action="status_changed")` still fires exactly when
it already does today: when something calls
`ConnectivityService.refresh_device_state()` (a separate, existing
operation — `POST /api/v1/connectivity/devices/{id}/refresh`, already
shipped in Task Group C, not a Smart Locks concern to rebuild).

## 16. Access-history behavior

**Not built.** Per the kickoff's own explicit instruction, a table is
only justified if genuinely required, and it is not: no existing
mechanism captures "who locked/unlocked when" as a queryable trail.
`lock()`/`unlock()` do not write to the DB or publish an event (§15);
the only events that exist are `status_changed` events from an explicit
`refresh_device_state()` call, which is poll-driven, not push-driven —
there is no webhook/subscription today that would proactively record
every physical lock event as it happens. Building genuine access
history would require either (a) a new table plus writes from
`lock()`/`unlock()` (out of scope — no requirement demonstrates this is
needed for an MVP), or (b) each connector proactively reporting every
state change as an event (a Connectivity Layer-level capability neither
`HomeAssistantConnector` nor `MqttConnector` has today, out of this
module's scope to add). Documented here as a real, honest gap — not
silently omitted.

## 17. Idempotency expectations

`lock()` on an already-locked device (or `unlock()` on an
already-unlocked one) is **not specially detected or short-circuited**
— it sends the same wire command every time, exactly like
`ConnectivityService.send_command`'s own documented behavior for every
other M12 command (no command deduplication or state-diffing exists
anywhere in the Connectivity Layer). Whether the *underlying device
operation* is itself idempotent depends on the vendor (HA's `lock.lock`
service is idempotent by HA's own contract; MQTT's `lock`/`unlock`
being idempotent depends on the receiving firmware, which is outside
this module's control). `CommandResult.success` reflects only "was
this handed to the connector for delivery" (HA: the HTTP call
succeeded; MQTT: `publish()` did not raise) — never a device-side
confirmation, matching the existing `IDeviceConnector.send_command`
contract exactly.

## 18. Safety boundaries

- Every mutating operation requires the `smart_home` permission grant
  (§12) — no bypass path; REST and tools both funnel through the same
  `SmartLockService` methods, which are the only things that call
  `_require_permission()`.
- `unlock_device` additionally requires interactive confirmation on the
  agent-tool path (§14) when a confirmation channel is available;
  `auto_deny_when_unconfirmable=True` (the existing `AgentPermissionGate`
  default, unchanged) means an unconfirmable context **denies**, never
  silently allows.
- `CommandResult.success=False` is always surfaced as `success: false`
  in both REST and tool responses — never reported as if it succeeded,
  and never raises in its place (a failed command is a real, expected
  outcome, not swallowed and not embellished).
- No credential or connector-internal detail (tokens, MQTT broker
  auth, HA base URL) is ever included in any Smart Locks response —
  the payload shape (§3) carries only `Device` fields already public
  through `routes/smart_home.py` plus the derived `locked`/`available`
  fields.
- No new pairing/handshake claim (§12) — a "paired" lock is exactly as
  weakly-verified as any other M12 device today, not specially trusted
  because it is safety-relevant.

## 19. What this module does not build (explicit carve-outs)

- Guest access codes, temporary PINs, NFC/fingerprint enrollment — no
  schema exists for any of it; `MASTER_ROADMAP.md`'s Smart Locks feature
  list names these but this task group's approved scope (per the
  kickoff message) is lock/unlock/state/availability only.
- Auto Lock, geofenced unlock, or any trigger-based behavior — Home
  Automation's job, unstarted, same carve-out Smart Lighting already
  established for its own automation-adjacent items.
- A second device registry, connector abstraction, permission engine,
  command executor, or pairing system — none created; every one of
  those is the existing M12 Task Group A/B/C infrastructure, reused
  verbatim.
