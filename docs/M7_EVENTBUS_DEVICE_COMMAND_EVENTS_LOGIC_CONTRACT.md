# M7 EventBus Tier 1 — Device Command Events — Logic Contract

**Status: Phase 1 planning document only. Contains zero source-code
changes.** Written per the Post-Scheduler-MVP audit's #1 recommendation
(the cheapest, lowest-risk, most immediately useful next step, and the
natural precursor to Tier 2). No implementation accompanies this
document, and none is authorized by it. Scope is Tier 1 — device
*command* events — only. Tier 2 (device *state-change* events) is a
separate, later, not-yet-designed milestone; see §16.

## 1. Fresh source verification (this session, HEAD `da8fa06`)

Re-read directly, not trusted from any prior summary: `core/events/
event_bus.py` (90 lines, in full), `core/events/events.py`'s base
`Event` class and its closest sibling events (`AutomationStepEvent`,
`IntegrationCallCompletedEvent`, `IntegrationConnectionTestEvent`,
`DeviceUpdatedEvent`, `ConnectivityStatusChangedEvent`),
`ConnectivityService.send_command()` and `_publish_status()` in full,
`CommandResult`'s exact dataclass shape (`core/interfaces/
connectivity.py:96-105`), `SmartLightingService.set_light_state`'s
exact permission-check ordering, and `container.py`'s
`_build_connectivity_service`/`connectivity_service` provider. Grepped
all 10 M12 device-command services directly for
`_connectivity.send_command` call sites. Zero discrepancy found
against this session's own prior audit findings.

## 2. Command-path trace

**Agent Tool → Device Service → ConnectivityService.send_command() →
connector.send_command()**: confirmed directly. Every agent tool
(`agents/tools/smart_lighting_tools.py` etc.) calls its own service's
public method (e.g. `SmartLightingService.set_light_state`), which
itself calls `self._connectivity.send_command(...)`
(`smart_lighting_service.py`, confirmed via grep alongside the other 9
services). No agent tool ever calls a connector directly.

**REST → Device Service → ConnectivityService.send_command() →
connector.send_command()**: confirmed directly, two convergent paths.
The normalized per-device-type routes (e.g. `routes/smart_lighting.py`)
call the same service methods agent tools call. The generic passthrough
route (`routes/connectivity.py`'s `send_device_command`) calls
`ConnectivityService.send_command()` directly. Both reach the identical
chokepoint.

**Scheduled → ScheduleService → (AutomationService.run_command | the
same tool registry's tool.ainvoke) → Device Service →
ConnectivityService.send_command()**: confirmed directly.
`ScheduleService._run_agent_tool_step` invokes the *same* `BaseTool`
object `build_tool_registry` already builds for the main agent graph —
there is no second, scheduler-specific device-command path. A scheduled
command produces the identical event Tier 1 defines, automatically,
with zero Scheduler-side code (see §14).

**The single canonical publication point is `ConnectivityService.
send_command()`** (`services/connectivity_service.py:214-230`) — not
assumed, verified: all 10 shipped M12 device-command services
(`smart_lighting_service.py`, `smart_lock_service.py`,
`smart_switch_service.py`, `appliance_service.py`,
`thermostat_service.py`, `vacuum_humidifier_service.py`,
`media_player_service.py`, `water_heater_service.py`,
`siren_service.py`, `alarm_control_panel_service.py`) route their
device mutations through this exact method, with zero bypass path
found.

## 3. Architecture decision

**Option A — publish directly inside `ConnectivityService.
send_command()` — chosen.** Evaluated against the alternatives:

- **B (publish inside each device service):** rejected — would require
  touching all 10 already-shipped services identically, duplicating
  the same three lines of code 10 times, for something one line in one
  already-shared method already covers. Directly contradicts "prefer
  the existing chokepoint if it is genuinely canonical."
- **C (publish inside connectors):** rejected — a connector's
  `send_command()` doesn't have access to `device`/`home_id`/`room_id`
  (it only sees `external_id`, a wire-level identifier); the event's
  device identity would need a second `SmartHomeService` lookup inside
  the connector layer, which currently has zero dependency on
  `SmartHomeService` at all. Would also mean two connectors (HA, MQTT)
  each need their own publish call, and any future connector inherits
  the obligation — more surface, not less.
- **D (separate command-event service/interceptor):** rejected as
  unjustified complexity — `ConnectivityService.send_command()` already
  *is* the single, already-DI-wired, already-`EventBus`-holding
  chokepoint (`container.py:1462-1467` already injects `event_bus` into
  it — confirmed fresh, zero new DI wiring required). A separate
  interceptor would duplicate this without adding anything.

**Option A requires the smallest possible change**: one new `Event`
subclass in `events.py`, one new `await self._event_bus.publish(...)`
call inside the existing method, using data (`device`, `connector_type`,
the returned `CommandResult`) already locally available at that exact
point — zero additional database lookups, zero new DI wiring.

## 4. Event semantics — resolved precisely

**The event represents: command dispatched and its outcome observed —
i.e., "a command was sent to a connector and the connector returned a
result," carrying `success: bool` to distinguish the two outcomes.**
This is deliberately **not** split into six separate concepts
(requested/authorized/dispatched/executed/succeeded/failed) because the
evidence does not support that granularity at this chokepoint:

- **"Requested"** and **"authorized"** happen *before* `send_command()`
  is ever called (see §10) — this method has no visibility into either
  step and cannot honestly represent them.
- **"Dispatched"** and **"executed"** are not separately observable
  here: `connector.send_command()` is a single `await` — this code has
  no signal for "the connector accepted the dispatch" distinct from
  "the connector finished executing it." Only the *outcome* is
  observable, in `CommandResult`.
- **"Succeeded"** and **"failed"** are the one real distinction the
  evidence supports, and `CommandResult.success` already carries it
  precisely, matching `IntegrationCallCompletedEvent.ok`'s own existing
  precedent (`events.py:822`) for exactly this shape of event.

**Naming: `DeviceCommandExecutedEvent`.** "Executed" is used in the
sense the codebase's own sibling event uses "completed"
(`IntegrationCallCompletedEvent`) — the round trip finished, with a
carried success/failure outcome — not in the stricter sense of "the
device confirmed it changed state" (that is Tier 2's job, and this
event explicitly does not claim it — see §16).

## 5. Canonical publication point

`ConnectivityService.send_command()`, immediately before its existing
`return` statement (`services/connectivity_service.py:230`) — after
`connector.send_command(...)` has returned, so the event always carries
a real, already-computed `CommandResult`. Published via `await self.
_event_bus.publish(...)`, matching `_publish_status()`'s own existing
pattern in the same class exactly (not `publish_nowait` — this method
is already `async` and already awaited by every caller, so there is no
reason to depart from the awaited form already used one method away).

## 6. Event payload

```python
@dataclass(frozen=True, slots=True)
class DeviceCommandExecutedEvent(Event):
    device_id: str = ""
    home_id: str = ""
    room_id: str = ""
    device_type: str = ""
    connector_type: str = ""
    command: str = ""
    success: bool = True
    detail: str = ""
```

`id`/`occurred_at` come free from the base `Event` class
(`events.py:15-20`) — already a UUID4 hex and a UTC timestamp on every
event in this codebase; not redeclared.

Every field justified individually:

| Field | Why it exists | Source at the publication point |
|---|---|---|
| `device_id` | Which device | `device.id` (already fetched by `require_device`) |
| `home_id` | Which home, for home-scoped consumers (a future Event Viewer's own filter, mirroring `DeviceUpdatedEvent.home_id`) | `device.home_id` |
| `room_id` | Room-scoped filtering, matching `Device`'s own nullable column shape | `device.room_id` (empty string when unset, matching every other event's `str = ""` convention — no `\| None` types appear anywhere in `events.py`) |
| `device_type` | Lets a subscriber filter/group without a second `SmartHomeService` lookup | `device.device_type` |
| `connector_type` | Which connector handled it — mirrors `ConnectivityStatusChangedEvent.connector_type` | the already-resolved local variable in `send_command()` |
| `command` | What was asked for | the `command` parameter, echoed by `CommandResult.command` |
| `success` | The one outcome distinction the evidence supports (§4) | `CommandResult.success` |
| `detail` | A human-readable outcome summary — already a *safe* summary by `CommandResult`'s own existing docstring ("`success=False` with a `detail` is a real, expected outcome... not every failure is an exception") | `CommandResult.detail` |

**Deliberately excluded**: `event_id`/`timestamp` (free from `Event`,
not redundant fields), `command_id`/`correlation_id` (§11), `session/
request identifier` (§11), the raw `payload` dict (§7).

## 7. Security / redaction decision

**The command payload dict is not carried at all — omission, not
redaction.** Evaluated against the full option set:

- Full inclusion: rejected outright — `send_command(device_id, command,
  payload)`'s `payload` is caller-supplied and unvalidated at this
  layer; nothing here can prove it never carries something sensitive.
- Selective/key-redacted inclusion: rejected — would require a
  redaction table (which keys are sensitive, per command, per
  connector) that does not exist anywhere in this codebase today, and
  building one is explicitly out of scope ("do not create an unrelated
  generic redaction framework").
- **Omission — chosen.** Directly matches this codebase's own existing
  precedent: `IntegrationCallCompletedEvent`'s docstring states
  verbatim, "**Carries no request body and no response body**... What
  travels is what an audit needs: which integration, which operation,
  what the vendor said" (`events.py:803-809`), and
  `IntegrationConnectionTestEvent` repeats the same discipline
  (`events.py:839`, "no request/response body, no header, no
  credential"). `DeviceCommandExecutedEvent` follows the identical
  rule for the identical reason.

**Concrete risk assessment, evidence-based, not assumed:** device
command payloads in this codebase carry operational parameters
(brightness, temperature, volume, tone) — connector *credentials*
(HA tokens, MQTT broker auth) flow through `ConnectivityService.
connect(connector_type, config)`, a structurally separate call, never
through `send_command`'s own `payload` argument. Neither
`smart_lock_service.py` nor `alarm_control_panel_service.py` accepts a
PIN/code parameter anywhere — confirmed this session, both already
established as "structurally, permanently, no code/PIN support of any
kind." No location-sensitive command payload was found in any of the
10 services. This lowers the *practical* risk of omission being overly
cautious, but omission is chosen regardless, on the existing-precedent
principle, not because a residual risk was found and dismissed.

**`detail` is reused, not invented**, and is already a `CommandResult`-
level safe summary by contract — it is not free-text piped from a raw
exception; `ConnectivityService.send_command()` itself never touches an
exception message directly (any `ConnectivityError` it raises
propagates *before* a `CommandResult` exists at all — see §9).

## 8. Device identification

`device_id`/`home_id`/`room_id`/`device_type` only — the four fields a
subscriber needs to identify and group by device, home, and room
without a second lookup. **`metadata_json` is never exposed** — nothing
in the existing event architecture requires it (`DeviceUpdatedEvent`,
the closest sibling, doesn't carry it either), and it is connector-
specific wire detail (domain/component keys, HA entity attributes) with
no established precedent for appearing on any event in this codebase.

## 9. Failure semantics — precisely bounded

| Scenario | Reaches `send_command()`? | Event published? |
|---|---|---|
| 1. Successful connector command | Yes | Yes, `success=True` |
| 2. Connector command failure (device offline, rejected) | Yes — `CommandResult.success=False` is a normal return, not an exception (confirmed, `CommandResult`'s own docstring) | Yes, `success=False`, `detail` carries the reason |
| 3. `ConnectivityError` (unregistered connector, not connected) | **No** — raised by `_require_connector`/`connector_type_for` *before* `connector.send_command()` is ever called (`connectivity_service.py:225-229`) | **No** — the method never reaches its own `return`, so no `CommandResult` exists to publish |
| 4. `ServiceError` (e.g. an unknown device from `require_device`) | **No** — raised before any connector resolution | **No** |
| 5. Validation failure (bad interval/cron at Scheduler creation, bad brightness value in a device service) | **No** — every M12 service validates before calling `self._connectivity.send_command` (confirmed directly this session in every one of the 10 services) | **No** |
| 6. Permission denial (`_require_permission()`) | **No** — confirmed directly: `SmartLightingService.set_light_state`'s first line is `self._require_permission()`, before any connectivity interaction (`smart_lighting_service.py:341`) — the same ordering holds in every other M12 service written this session | **No** |
| 7. Confirmation denial (`AgentPermissionGate`/`PermissionGate`) | **No** — `permission_validator_node`/`ScheduleService._run_agent_tool_step` both call `gate.authorize(...)` and return on denial *before* the underlying tool (and therefore the underlying service method and `send_command`) is ever invoked | **No** |

**Only scenarios 1 and 2 produce a `DeviceCommandExecutedEvent`.**
Scenarios 3-7 never reach the chokepoint at all — this contract makes
no claim otherwise, per the explicit instruction not to fabricate
command-execution semantics the source architecture doesn't support.

## 10. Permission / validation / confirmation boundary

Restated plainly from §9: the event's `success` field distinguishes
*connector-level* outcomes only (device reachable and command accepted
vs. device offline/rejected). It says nothing about, and is never
reached for, authorization or validation outcomes — those remain
entirely invisible to this event, exactly as the evidence requires. A
future consumer must not interpret "no event for this attempted
command" as "the command failed" — it may equally mean the command was
never authorized to attempt in the first place, a materially different
fact this event does not, and structurally cannot, distinguish.

## 11. Correlation / ordering decision

**No correlation/session/request identifier is introduced.** Verified:
`ConnectivityService.send_command(self, device_id, command, payload)`
has no session/request/correlation parameter today, and none flows in
from any of its ~11 call sites (10 services + the generic REST route).
Threading one through would require changing this method's signature
and, by extension, likely every caller — a cross-cutting change well
beyond "the smallest architecture supported by the evidence," and
explicitly out of scope ("do not introduce distributed-tracing
infrastructure"). The event's own `id` (free from the base `Event`
class) uniquely identifies the event itself; correlating multiple
events to one originating request is deferred, undecided, and not
this contract's problem to solve.

**No new ordering guarantee.** `EventBus.publish()` (verified,
`event_bus.py:66-81`) delivers to subscribers of the exact event type
first, then walks the MRO to `Event` itself, in per-type subscriber
list order — the same mechanism every one of the other 74 existing
event types already relies on. Concurrent `send_command()` calls (e.g.
two REST requests in flight, or Scheduler's own bounded concurrency)
may interleave their publish calls exactly as any other concurrent
async operation in this codebase already can; `occurred_at` remains the
only ordering signal, as it already is for every other event.

## 12. EventBus subscriber behavior

Verified directly (`event_bus.py:66-81`): `publish()` is `async`,
awaits each handler in turn, and wraps every handler call in its own
`try/except Exception` — a raising subscriber is caught, logged via
`_logger.exception`, and never re-raised. **This guarantee already
exists, unconditionally, for every event type; Tier 1 adds no new
isolation code and needs none.** Concretely: `RuntimeWebSocketHub`
already subscribes to the base `Event` type (confirmed this session,
unchanged) and will receive `DeviceCommandExecutedEvent` automatically
— but since Tier 1 deliberately does not add an `EVENT_TYPE_NAMES`
entry for it (§17), `RuntimeWebSocketHub._on_event`'s existing
`EVENT_TYPE_NAMES.get(type(event))` lookup returns nothing and the
event is silently not relayed — the exact same, already-established
behavior the 9 currently-unrelayed events (`WorkflowStepEvent`,
`ScheduledJobFiredEvent`, etc.) already rely on. Zero change to any
existing subscriber's behavior.

**Publishing cannot affect command success**, verified structurally,
not just asserted: the event is constructed *from* the already-computed
`CommandResult` and published *after* it exists, immediately before
`send_command()`'s own `return` — nothing a subscriber does can alter a
value already computed and about to be returned, and subscriber
exceptions are caught internally regardless (above). The only possible
effect of adding this publish call is added *latency* (the `await`
inside `send_command()` now also awaits every subscriber) — never a
correctness change.

## 13. Persistence decision

**No persistence.** Verified directly (`event_bus.py:1-5`): "The bus
deliberately has *no* persistence, *no* remote transport and *no*
retries." Tier 1 adds zero database tables, zero event store, zero
history table. A future Event Viewer (not built here) would need its
own decision about whether to persist what it observes — not this
contract's concern.

## 14. Scheduler interaction

**`ScheduleService` needs zero new code.** Verified by trace (§2): a
scheduled `AUTOMATION`-kind step reaches `send_command()` via
`AutomationService.run_command` → `ActionExecutor` → the relevant
action's own connectivity call (for M12-target actions, if any exist —
most `ActionType` values are OS/desktop-automation, not device
commands); a scheduled `AGENT_TOOL`-kind step reaches it via the exact
same `tool.ainvoke(...)` call path any other agent-tool caller uses.
Scheduler introduces no second event mechanism and needs none — a
scheduled device command automatically produces the identical
`DeviceCommandExecutedEvent` a REST-originated or agent-tool-originated
command would, with no way to distinguish "this fired from a schedule"
from the event alone (a real limitation, stated plainly, not solved
here — solving it would mean the correlation-id work already deferred
in §11).

## 15. M12 compatibility

Confirmed unmodified by this contract, and confirmed (fresh, this
session) that all 10 already-shipped M12 device-command services route
through the unmodified chokepoint: `smart_lighting_service.py`,
`smart_lock_service.py`, `smart_switch_service.py`,
`appliance_service.py` (Fan/Cover), `thermostat_service.py`,
`vacuum_humidifier_service.py`, `media_player_service.py`,
`water_heater_service.py`, `siren_service.py`,
`alarm_control_panel_service.py`. None require any change — the new
event fires for all 10 automatically, the moment `send_command()`
itself is extended, with zero per-service code.

## 16. Tier 2 boundary — explicit, not designed here

**Tier 1 provides:** "a command was sent and its connector-level
outcome observed." **Tier 1 does not provide, and this document does
not design:**

- Any signal that a device's *actual reported state* changed — a
  successful `CommandResult` means the connector accepted and
  attempted the command, not that the device confirmed the new state
  (HA/MQTT command acknowledgement and device state reporting are
  different protocol-level facts, already established in this
  session's own connector audits).
- Any polling/diffing of `report_device_state`/`refresh_device_state`
  results — Tier 2's own likely mechanism, not sketched further here
  per the explicit instruction not to design a "fake Tier 2" inside
  this contract.

**Consequently, Tier 1 alone does not enable:**
- **Home Automation sensor/state triggers** — these need to react to a
  device's state *changing*, which Tier 1 cannot observe (a command
  succeeding is not the same fact as a sensor's reading changing).
- **Automatic Smart Home Memory capture** (event-driven) — same
  reasoning; Tier 1 could at most tell a subscriber "a command was
  issued," never "the device's state is now different."
- **Smart Lock Auto-Lock** — this is a state-duration trigger ("N
  minutes since last unlocked"), not a command-issued event at all.
- **Presence-based automation** — presence is itself a sensor state,
  requiring the same Tier 2 capability.

## 17. Future consumers — named, not built

**Developer Tools Event Viewer**: a future consumer could subscribe to
`DeviceCommandExecutedEvent` (directly, or once wired into
`EVENT_TYPE_NAMES` for WebSocket relay) to show a live or historical
command audit trail. **Not implemented here** — and deliberately not
even wired into `EVENT_TYPE_NAMES`/`RuntimeWebSocketHub`'s relay list
in Phase 2 either, matching the exact precedent `WorkflowStepEvent`/
`ScheduledJobFiredEvent` already set (declared, published-or-not, but
left off the relay list until a real consumer exists to justify the
WS-contract surface). This is a deliberate, evidence-matched choice,
not an oversight.

**Command diagnostics/audit, future workflow observability**: same
reasoning — this event is the raw material a future consumer would
subscribe to; building that consumer is out of scope here.

## 18. Test strategy

**Persistence/wiring:**
- `ConnectivityService` still receives `event_bus` via the existing DI
  provider, unchanged — a regression guard, not new behavior.

**Emission — success path:**
- A successful `send_command()` call publishes exactly one
  `DeviceCommandExecutedEvent`, `success=True`, with correct
  `device_id`/`home_id`/`room_id`/`device_type`/`connector_type`/
  `command`/`detail`, for each of a representative sample of the 10
  M12 services (not necessarily all 10 individually — one or two
  through `ConnectivityService` directly, since the event fires at
  that shared layer regardless of which service called it).

**Emission — failure path:**
- A `CommandResult(success=False, detail=...)` (device offline/
  rejected) still publishes exactly one event, `success=False`, with
  the same `detail` string, not an exception.

**Non-emission — the critical negative-space matrix:**
- `ConnectorNotConnectedError`/`ConnectivityError` (unregistered or
  disconnected connector) → **zero** events published.
- Unknown device (`ServiceError` from `require_device`) → **zero**
  events published.
- A validation failure inside a device service (e.g. an out-of-range
  brightness) → **zero** events published (never reaches
  `send_command`).
- A permission denial (`_require_permission()`) → **zero** events
  published.
- A confirmation denial (`AgentPermissionGate`/`PermissionGate`, via
  either the main agent graph or `ScheduleService`) → **zero** events
  published.

**Payload correctness:**
- No `payload`/command-args field appears anywhere on the event,
  verified by field introspection, not just absence-of-assertion.
- `metadata_json` is never read or exposed by the publish call.

**Subscriber isolation:**
- A subscriber that raises does not affect `send_command()`'s own
  return value or raise out of it — the command's own success/failure
  is identical with and without a misbehaving subscriber attached.

**No duplicate events:**
- A single `send_command()` call publishes exactly one event, verified
  via a counting subscriber.

**Origin parity:**
- The identical event (same shape, same fields populated) is produced
  regardless of whether the call originated from a REST route, an
  agent tool, or a `ScheduleService`-dispatched step — verified by
  triggering the same underlying command through each of the three
  paths and comparing the captured event's field set.

**Regression:**
- Existing M12 device-command tests (all 10 services) continue to pass
  unmodified — this is an additive change to a shared chokepoint, not
  a signature change to any of them.
- `EventBus` itself gains no persistence, no new subscriber-isolation
  code (already existed) — a scope guard, not new functionality.
- No `EVENT_TYPE_NAMES` entry exists for this event (a scope guard
  proving Tier 1 deliberately doesn't relay yet).
- No Tier 2 code, no Home Automation code, no Smart Home Memory
  automation code exists anywhere (raw-source scope-guard tests,
  matching this session's own established convention).

## 19. Acceptance criteria

- `DeviceCommandExecutedEvent` is published from exactly one place:
  `ConnectivityService.send_command()`.
- Semantics are exactly "command dispatched, connector-level outcome
  observed" — never conflated with authorization, validation, or
  confirmation, and never claimed to represent an actual device
  state change.
- Payload contract is exactly the 8 domain fields in §6 — no raw
  command-args payload, no `metadata_json`.
- Security: payload omission verified structurally (field
  introspection), not just documented.
- Success/failure: both produce an event; the four earlier-stage
  failure modes (connectivity error, unknown device, validation,
  permission/confirmation denial) produce none.
- Subscriber isolation: a raising subscriber never changes
  `send_command()`'s own return value.
- No new ordering/correlation guarantee introduced.
- No persistence added anywhere.
- No Tier 2 (state-change detection) code exists.
- No Home Automation code exists.
- No Smart Home Memory automatic-capture code exists.
- No Event Viewer implementation exists, and no `EVENT_TYPE_NAMES`/WS-
  relay entry is added for this event.
- No Scheduler-specific duplicate event path exists — verified by the
  origin-parity test (§18).
- No connector file is modified — the event fires above the connector
  layer entirely.
- Full backend regression green, including all 10 M12 device-command
  service test suites unmodified.
- Clean git state at the end of Phase 2 (when it happens) — not
  evaluated in this Phase 1 pass.

## 20. Deferred scope

Tier 2 (device state-change detection via polling/diffing), Event
Viewer (frontend and backend consumer), automatic Smart Home Memory
capture, Home Automation triggers, Smart Lock Auto-Lock, presence-based
automation, a correlation/session identifier threaded through
`send_command()`, `EVENT_TYPE_NAMES`/WebSocket relay wiring for this
event, any connector-layer change. Each has a named, correct future
owner; none is silently dropped.
