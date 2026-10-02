# M7 Home Automation — Logic Contract

**Status: Phase 1 planning document only. Contains zero source-code
changes.** Built directly on the completed Phase 0 audit, with the two
load-bearing design questions it flagged (workflow-execution reuse,
trigger persistence) freshly re-verified against current source in
this same session before being resolved here. No implementation, test,
frontend, roadmap, or CHANGELOG change accompanies this document, and
none is authorized by it.

## 1. Purpose

Define, precisely and without implementing, how Jarvis-OS gains its
first event-triggered automation capability: "when this device's
status transitions this way, run this workflow" — by reusing existing
infrastructure end to end, adding the smallest new persistence and
matching logic the evidence supports.

## 2. Scope

This slice: a `HomeAutomationService` that subscribes to
`DeviceStateChangedEvent`, matches it against persisted, single-device,
single-transition triggers, and dispatches the matched trigger's
`WorkflowDefinition` through the identical execution machinery
Scheduler already uses — with the same fail-safe permission and
confirmation behavior, zero new authorization code, and two small new
database tables.

## 3. Explicit Non-Goals

Not in this slice: a condition engine, attribute-level triggers,
multi-device triggers, multi-trigger composition (AND/OR), MQTT/HA-
native event subscriptions, presence/geofence/camera/voice triggers,
AI-generated automations, Smart Home Memory coupling, Analytics, Event
Viewer, WebSocket relay, frontend implementation, correlation IDs, or
automatic post-command refresh. Full list in §35.

## 4. Architecture

```
HomeAutomationService
        |
   EventBus.subscribe(DeviceStateChangedEvent)
        |
   trigger matching (device_id + status transition, DB query)
        |
   WorkflowExecutionService.run_workflow(steps)   <- NEW, extracted, shared with Scheduler
        |
   existing AgentPermissionGate / PermissionGate  <- unchanged, reused
        |
   existing device-service / AutomationService execution path <- unchanged, reused
```

`AutomationService` is not extended — the Phase 0 audit already
established it is OS-automation-scoped, not a general workflow
engine — nothing here changes that boundary. No second workflow
engine, no second permission engine, no second `EventBus` is created.

## 5. Service Ownership

A new `HomeAutomationService` (`src/jarvis/services/
home_automation_service.py`, not built in this phase) owns: the
`EventBus` subscription, trigger matching, trigger CRUD, and
dispatching matched triggers. It does **not** own workflow execution
(§7/§8) — that becomes a separate, shared component both
`HomeAutomationService` and `ScheduleService` call.

## 6. Trigger Ownership

`HomeAutomationService` owns triggers exclusively. `ScheduleService`
gains no device-event awareness and is not modified to subscribe to
anything (§26).

## 7. Workflow Reuse

`WorkflowDefinition`/`WorkflowStep`/`WorkflowStepKind` are reused
completely unchanged — no new field, no new kind. A `WorkflowDefinition`
created for a Home Automation trigger is structurally identical to one
created for a Schedule; `WorkflowDefinition` has no owner-tracking
field today (confirmed by fresh re-read) and needs none added — both
`Schedule` and the new `AutomationTrigger` (§10) point *at* a
`WorkflowDefinition` via their own `workflow_id` FK, symmetrically.

## 8. Workflow Execution Extraction Decision

**Freshly re-read this session**: `ScheduleService._run_workflow`
(`schedule_service.py:656-689`), `_run_step` (691-694),
`_run_automation_step` (696-716), `_run_agent_tool_step` (718-...),
and the lazy tool-registry/gate state (`_ensure_tools_ready`,
`_tools_by_name`, `_gate`, `_tool_services`, lines 200-263). Confirmed:
these methods depend on nothing Schedule-specific — they take
`steps: list[dict]` (parsed `WorkflowDefinition.steps_json`) and
return `(status, error, step_results)`, using only `self._automation`
(`AutomationService`) and the lazily-built tool registry/
`AgentPermissionGate`. Zero reference to `Schedule`, `next_fire_at`,
misfire logic, or anything else Scheduler-specific.

**Decision: extract a new, small `WorkflowExecutionService`**
(`src/jarvis/services/workflow_execution_service.py`), constructed once
at the DI composition root exactly like every other shared service,
injected into both `ScheduleService` and `HomeAutomationService`.

Evaluated against the four options:
- **A/B (extract a shared service / move methods into a reusable
  service)** — these are the same underlying action; chosen. The lazy
  tool-registry/`AgentPermissionGate` state (`_ensure_tools_ready`)
  needs to be built and cached *once*, shared by both callers — a
  small stateful service is the natural home for that, not bare
  functions each caller would have to manage independently.
- **C (make the existing methods public on `ScheduleService`, have
  `HomeAutomationService` hold a `ScheduleService` reference)** —
  rejected: creates a backwards dependency (an event-driven service
  depending on a time-based one merely to reach execution logic they
  should both be siblings of), and contradicts the mandated
  architecture's own "shared execution owns workflow execution" layer
  (§26), which names a *third*, independent ownership boundary, not
  "Home Automation depends on Scheduler."
- **D (accept duplication for the first slice)** — rejected, explicitly
  forbidden by instruction ("do not duplicate execution logic").

**Exact extraction boundary** (specified, not implemented):

*Moves into `WorkflowExecutionService`, verbatim, unchanged internals:*
`_ensure_tools_ready` (private), `run_workflow` (public — the renamed
`_run_workflow`), `_run_step`, `_run_automation_step`,
`_run_agent_tool_step` (all private helpers of the new service).
Constructor takes the identical ~24 optional device/service references
`ScheduleService._tool_services` already threads through
`build_tool_registry`, plus `automation: AutomationService | None` and
`settings: Settings` (for `confirm_required_tools`).

*Stays in `ScheduleService`, unchanged:* `tick`, `_dispatch`,
`_finish_execution`, every Schedule-specific concern (due-schedule
lookup, misfire grace period, `has_non_terminal` duplicate-fire check,
its own semaphore, `record_fire`/`next_fire_at` computation). Its only
change: `self._run_workflow(steps)` becomes
`self._workflow_executor.run_workflow(steps)` — a one-line call-site
substitution, zero behavior change. `ScheduleService` no longer builds
its own `AgentPermissionGate`/tool registry — it receives the shared
`WorkflowExecutionService` instead; since `AgentPermissionGate` is
stateless beyond its constructor-time config (no per-call mutable
state, confirmed by fresh re-read), one shared instance behaves
identically to the two separate-but-identically-configured instances
that exist today. This is a harmless consolidation, not a behavior
change.

**Preserved exactly**: both `WorkflowStep` kinds, per-step retry/timeout
(unchanged — lives inside `AutomationService`/`ActionExecutor`, never
touched), failure aggregation (`_run_workflow`'s own succeeded/denied/
failed/partially_failed logic, moved verbatim), and permission behavior
(`confirm=None` hardcoded at both call sites, unchanged).

`_finish_execution` is **not** extracted — it is a thin, two-line
wrapper around `WorkflowExecutionRepository(sess).finish(...)`, and the
repository itself is already the reusable unit at that layer (§32
gives Home Automation its own, parallel repository/table rather than
reusing this one). Extracting a service-level wrapper around an
already-thin repository call would be over-abstraction.

## 9. Automation Persistence Model

**Decision: `AutomationTrigger` *is* the automation record — no
separate `Automation`/header table.** Mirrors `Schedule`'s own
precedent exactly: `Schedule` has no separate "Automation" wrapper
above it; it *is* the schedule record, pointing at a
`WorkflowDefinition`. The trigger owns a reference to the workflow
(`workflow_id` FK on `AutomationTrigger`), not the reverse — identical
direction to `Schedule.workflow_id`.

## 10. Trigger Persistence Model

**Not the blindly-assumed field list — traced against `Schedule`'s
exact conventions and revised.**

```
AutomationTrigger (table: automation_triggers)
    id: str                        # String(32), PK, default uuid4().hex
    workflow_id: str                # String(32), FK -> workflow_definitions.id,
                                     #   ondelete="CASCADE", NOT NULL
    device_id: str                  # String(32), NOT NULL -- MVP is single-device only
    from_status: str                # String(32), default "" -- "" means "any previous status"
    to_status: str                  # String(32), NOT NULL -- the required target status
    enabled: bool                   # Boolean, default True
    created_at: datetime            # DateTime(timezone=True), default utcnow
    updated_at: datetime            # DateTime(timezone=True), default utcnow, onupdate=utcnow
    last_fired_at: datetime | None  # DateTime(timezone=True), nullable
    last_execution_id: str | None   # String(32), FK -> automation_executions.id,
                                     #   ondelete="SET NULL", nullable

Indexes: workflow_id (FK lookup), device_id (the hot lookup path --
"find every enabled trigger matching this device_id" runs on every
DeviceStateChangedEvent), enabled (mirrors Schedule's own enabled
index).

Uniqueness: none on (workflow_id, device_id, from_status, to_status).
Two different automations legitimately reacting to the identical
transition on the same device (e.g. "log it" + "turn on the fan") are
two separate rows -- a hard uniqueness constraint would forbid a real,
unremarkable use case (§12's own "multiple matching triggers" scenario
requires this to be allowed, not prevented).

Deletion: workflow_id ondelete=CASCADE mirrors Schedule.workflow_id
exactly -- deleting a WorkflowDefinition already cascades to delete
any Schedule pointing at it; the identical guarantee applies here, so
a "stale trigger" (workflow gone, trigger remains) is structurally
impossible, matching Schedule's own existing guarantee, not a new
mechanism.
```

**`from_status`/`device_type`/`home_id`/`room_id`/`connector_type`
decision**: `from_status` is stored and matchable (required — §12's
own worked example uses it). `device_type`, `home_id`, `room_id`,
`connector_type` are **not** stored on the trigger and are **not**
matchable in this MVP — `device_id` alone is strictly more precise (a
device has exactly one home/room/type/connector at any moment), so a
device-id match already subsumes anything those fields could add;
storing them would be redundant, violating the "no unnecessary
metadata duplication" discipline both EventBus Tiers already
established. Multi-device-scoped triggers ("any light in this room")
are explicitly deferred (§35), not fabricated here.

## 11. Event Matching Contract

On every `DeviceStateChangedEvent`, `HomeAutomationService` queries
`AutomationTrigger WHERE device_id = event.device_id AND enabled = true
AND to_status = event.status AND (from_status = '' OR from_status =
event.previous_status)`. Only `device_id` and the transition pair are
matched. `event.device_type`/`home_id`/`room_id`/`connector_type` are
read from the event only for constructing the dispatched workflow's
context/logging, never for matching (§10).

## 12. Trigger Semantics

- **`previous_status` matching**: exact match against `from_status` if
  set; `from_status = ""` matches any previous status (wildcard).
- **Target status matching**: exact match against `to_status`, always
  required (no wildcard target — "fire on any change at all" is a
  materially broader feature, not evidenced as needed for this slice).
- **Missing previous status**: cannot occur — Tier 2's own "first
  observation" behavior guarantees `event.previous_status` is always
  populated, even for a device's very first observed transition.
- **Duplicate event**: Tier 2's own same-value guard already prevents
  `DeviceStateChangedEvent` from firing on a no-op refresh
  (`previous_status == status` is structurally impossible on a
  published event) — the matching contract needs no defense against
  this because the upstream event itself cannot carry it.
- **Identical status**: structurally impossible on any published
  `DeviceStateChangedEvent`, per the point above — not guarded against
  here because it cannot reach this layer.
- **Disabled automation**: excluded by the `enabled = true` clause in
  the match query itself — never reaches dispatch.
- **Deleted automation**: no longer exists to match — the query simply
  finds nothing.
- **Stale trigger**: structurally impossible, per §10's cascade
  guarantee.
- **Multiple matching triggers**: each match is dispatched
  independently — no ordering guarantee between them (matches the
  "no stronger guarantee than the architecture provides" discipline
  from both EventBus Tiers), and one match's outcome never affects
  another's.

## 13. Lifecycle

`enabled: bool` only — no draft/paused/failed automation-level status,
mirroring `Schedule`'s own deliberate choice not to add a
status/failure_count/version column ("would be a second, driftable
source of truth alongside the latest execution's own status"). Health
is derived from `last_execution_id`, identical to how a schedule's
health is read today.

## 14. Concurrency

**Reuses Scheduler's exact pattern-shape, in a separate instance, not
the same object.** Per-automation dedup: identical mechanism to
`has_non_terminal`, querying the new `AutomationExecutionRepository`
(`WHERE automation_trigger_id = X AND status IN ('queued','running')`).
Global bound: a **new, separate** `asyncio.Semaphore`, sized by a new
`HomeAutomationSettings.max_concurrent_executions` (default `2`,
mirroring `SchedulerSettings.max_concurrent_jobs`'s exact shape/
default) — not literally shared with Scheduler's own semaphore, so a
burst of device events cannot starve legitimately-running scheduled
workflows, or vice versa; two independently-tunable limiters, identical
one-line construction pattern, zero added complexity.

- **Automation already running, another matching event arrives**:
  silent skip, **no new execution row** — this precisely mirrors
  `_dispatch`'s own `has_non_terminal` early-return (`return`, no row
  created), *not* the misfire-skip pattern (which does record a row) —
  confirmed by fresh re-read this session, the two are genuinely
  different existing behaviors and this slice reuses the silent one.
- **Automation disabled while queued**: re-check `enabled` fresh after
  acquiring the concurrency slot, mirroring `_dispatch`'s own pattern
  exactly; record `"cancelled"` if it was disabled in that window.
- **Automation disabled while running**: no interruption — an
  in-flight execution runs to completion, identical to Scheduler's own
  established (and here, unchanged) behavior; disabling only prevents
  *future* dispatches.

## 15. Loop / Re-entrancy

Phase 0 established that today's Tier 2 event structurally cannot
loop through a command (`send_command()` never triggers
`refresh_device_state()`), but this contract does not rely on that as
the permanent safety mechanism, per explicit instruction.

**Execution identity**: each `AutomationExecution` row has its own
`id` (§32). **Trigger origin**: the `source` field (§24) distinguishes
`"event"` from `"manual"` — sufficient to know an execution was
event-caused without building a full causal-chain/correlation-ID
system (explicitly not introduced, §35). **Re-entry mechanism, the
smallest safe MVP choice**: a fixed per-trigger cooldown, reusing
`AutomationTrigger.last_fired_at` (already present, §10) exactly the
way `Schedule.last_fired_at` already works — before dispatching a
match, compare `now - last_fired_at` against a new
`HomeAutomationSettings.min_refire_interval_seconds` (small,
conservative default, e.g. `5.0`); if under the interval, skip silently
(same no-row behavior as §14's duplicate-execution case) rather than
dispatch again. **Future command→refresh compatibility**: this exact
cooldown mechanism, present from this slice's first implementation, is
what would remain sufficient if a future change ever makes command
execution automatically trigger a refresh (closing Phase 0's identified
gap) — it is not a today-only workaround; it is designed to keep working
once that gap closes, given a conservative default. **Duplicate-event
handling**: covered jointly by Tier 2's own same-value guard (upstream),
the per-automation `has_non_terminal` check (§14), and this cooldown —
three independent, cheap layers, no new infrastructure (no hashing, no
dedicated cache, no queue).

## 16. Duplicate / Burst Handling

No batching or rate-limiting infrastructure is introduced (not
evidenced as necessary — event volume is refresh-triggered, not
continuous, per the Phase 0 audit). A burst of independent device
events simply produces independent, individually-deduplicated dispatch
attempts, each subject to §14's concurrency bound and §15's cooldown.

## 17. Permission Model

Identical to Scheduler's own, zero new authorization code. Event
→ trigger match → `AutomationTrigger.enabled` check → (for `AGENT_TOOL`
steps) `AgentPermissionGate.authorize(tool_name, args, confirm=None)`
→ (for `AUTOMATION` steps) `AutomationService.run_command(instruction)`
→ `ActionExecutor`'s own `PermissionGate` → the target device service's
own `_require_permission()` (its literal first line, checked fresh
against the shared `PermissionModel` singleton on every call). Creation
permission (a new `HOME_AUTOMATION_PRINCIPAL = "core:home_automation"`
/ `HOME_AUTOMATION_SCOPE = "home_automation"` pair, mirroring
Scheduler's own `SCHEDULER_PRINCIPAL`/`SCHEDULER_SCOPE`, added to the
existing `PERMISSION_SCOPES` fixed vocabulary) governs only
trigger/automation CRUD — it never implies, caches, or substitutes for
the target action's own permission, which is re-evaluated fresh at
execution time exactly as this session's Phase 0 audit traced end to
end for Scheduler. If permission was revoked after trigger creation:
deny, record the execution as `"denied"` or `"failed"` (matching
whichever existing mechanism the target service's own check raises —
see §20), no device I/O — identical, evidenced-fail-safe outcome, zero
new code.

## 18. Confirmation Model

Policy A, identical to Scheduler's, zero new code: no confirm callback
is ever supplied (`confirm=None`, hardcoded, matching the two existing
call sites this slice reuses verbatim via §8's extraction). A
confirm-required action (`run_automation`, `unlock_device`,
`trigger_panic_mode`, `trigger_vacation_mode`, `turn_siren_on`,
`disarm` — confirmed unchanged) is denied, the execution records
`"denied"`, and no physical-world action occurs. `AgentPermissionGate`,
`PermissionGate`, and `AgentSettings.confirm_required_tools` are not
bypassed, modified, or reimplemented anywhere in this design.

## 19. Execution Semantics

Reuses the identical status vocabulary Scheduler already established
(`queued`/`running`/`succeeded`/`partially_failed`/`failed`/
`cancelled`/`skipped`/`denied`) on the new, parallel
`AutomationExecution` table (§32) — not the existing `WorkflowExecution`
table, to keep Scheduler's own schema completely untouched (§32
explains why). Dispatch flow: match (§11) → `queued` row created →
concurrency slot acquired (§14) → fresh `enabled` re-check → `running`
→ `WorkflowExecutionService.run_workflow(steps)` (§8) → terminal
status persisted. Identical shape to `ScheduleService._dispatch`,
minus the time-based misfire/next-fire computation, which has no
event-triggered equivalent.

## 20. Failure Semantics

Scenario mapping, traced against the exact extracted
`_run_workflow`/`_run_step` logic (§8):

| Scenario | Outcome |
|---|---|
| Trigger matched, dispatched | `queued` → `running` → terminal status from `WorkflowExecutionService.run_workflow`'s own aggregation |
| Trigger ignored (no match) | no row created |
| Disabled automation | excluded by the match query itself; no row |
| Permission denied | `"denied"` (via `_require_permission()`'s `ServiceError`, caught by the existing `try/except` around the tool call, surfacing as `"failed"` for `AGENT_TOOL` steps specifically — matching the existing, evidenced behavior exactly, not idealized) |
| Confirmation denied | `"denied"` (via `AgentPermissionGate`/`PermissionGate`, unchanged) |
| Unsupported tool | `"failed"` (`"Unknown tool: ..."`, unchanged) |
| Device/connector unavailable | `"failed"` (caught by the existing catch-all `try/except`, unchanged) |
| Action exception | `"failed"` (same catch-all) |
| Timeout | `AUTOMATION`-kind: existing per-step `ActionExecutor` timeout, unchanged. `AGENT_TOOL`-kind: no explicit timeout wraps `tool.ainvoke()` today (confirmed by fresh re-read) — this slice preserves that exact, existing characteristic rather than introducing a new timeout Scheduler itself doesn't have |
| Partial workflow failure | `"partially_failed"` (unchanged aggregation) |
| Automation deleted | cascades (§10); an in-flight execution's own row is not corrupted mid-run, matching Schedule's identical, already-accepted tradeoff |
| Automation disabled during execution | in-flight run completes unaffected (§14) |

No redundant status is introduced — every scenario maps onto the
existing eight-value vocabulary.

## 21. Manual Execution

`POST /home-automation/{id}/run` (§22) reuses the identical dispatch
path §17/§19 describe — the only difference from an event-triggered
dispatch is `source = "manual"` (§24) and the absence of a matched
event. Permission/confirmation checks are not bypassed or
pre-authorized in any way — a manual run of a `disarm`-targeting
automation is denied exactly as an event-triggered one would be.

## 22. REST API

Smallest coherent set, matching Scheduler's own 7-route precedent
exactly, plus the one genuinely new capability this slice's own MVP
scope requires (manual run) that Scheduler doesn't expose:

```
POST   /api/v1/home-automation                    create
GET    /api/v1/home-automation                     list
GET    /api/v1/home-automation/{id}                 get
POST   /api/v1/home-automation/{id}/enable
POST   /api/v1/home-automation/{id}/disable
DELETE /api/v1/home-automation/{id}
GET    /api/v1/home-automation/{id}/executions
POST   /api/v1/home-automation/{id}/run             manual test
```

No `PATCH`/update route — matching Scheduler's own precedent exactly
(no update-in-place exists for a `Schedule` either; changing an
automation means delete + recreate).

## 23. Agent Tools

Mirrors Scheduler's own 5-tool precedent, plus `run` for the same
reason REST includes it (§22):
`list_home_automations`, `get_home_automation`, `create_home_automation`,
`enable_home_automation`, `disable_home_automation`,
`run_home_automation` — 6 tools. `delete` stays REST-only, matching
Scheduler's own established precedent exactly. `run_home_automation`
does not bypass action-level authorization — it reuses the identical
dispatch path (§21), so a confirm-required or permission-gated action
is still denied exactly as any other call would be.

## 24. Execution Source

**Required, not speculative.** `automation_trigger_id` alone cannot
distinguish an event-triggered run from a manual test run of the same
automation — both would carry the identical FK. A `source: str` field
on `AutomationExecution` only (`"event"` | `"manual"`, closed
vocabulary, matching this codebase's own established closed-vocabulary
convention) resolves this with a two-value field, not a speculative
correlation-ID system. Scheduler's own `WorkflowExecution` table gains
no equivalent field — it is not touched at all (§32) — so no
retroactive labeling of existing rows is needed.

## 25. Event Publication

**Deferred — no `AutomationTriggeredEvent`/`AutomationExecutedEvent`/
`AutomationFailedEvent` is created.** No concrete consumer need was
demonstrated by the Phase 0 audit (Event Viewer does not exist; no
other subscriber was identified). If a future need is demonstrated,
such events should follow both existing Tiers' precedent exactly: safe,
closed-vocabulary fields only, declared in `UNPUBLISHED_EVENT_TYPES`
until a real consumer justifies relaying them — not decided further
here.

## 26. Scheduler Relationship

Scheduler continues to own time-based triggers exclusively and is not
modified to gain any device-event awareness (confirmed: no
`EventBus.subscribe` call exists in `schedule_service.py` today, and
none is added). Home Automation owns event-based triggers exclusively.
Workflow execution is owned by the new, shared `WorkflowExecutionService`
(§8) — neither Scheduler nor Home Automation duplicates it.
`EventBus` continues to own transport only, unmodified.

## 27. Memory Boundary

`HomeAutomationService` never calls `MemoryService`/
`SmartHomeMemoryService`, never creates automatic snapshots, never
stores device history, and never uses Memory as a condition source (no
condition engine exists in this slice at all, §3). A future Memory
integration remains an independent `EventBus` subscriber, exactly as
Tier 2's own Logic Contract already established — no coupling code
exists anywhere in this design for it to touch.

## 28. Event Viewer Boundary

Not built. No observability-specific event is added in this slice
(§25). If one is added later, it follows the same deferred-relay
treatment both existing Tiers use.

## 29. WebSocket Boundary

No `EVENT_TYPE_NAMES`/`RuntimeWebSocketHub` change. No Home Automation
event exists yet to classify either way.

## 30. Frontend Boundary

No frontend source is touched by this contract or by the backend
implementation it authorizes. Per explicit instruction, the future
`docs/M7_HOME_AUTOMATION_FRONTEND_REQUIREMENTS.md` is **not** created
in this phase — it is out of scope here, to be written only after
backend implementation is complete and verified, exactly as both
EventBus Tiers' own frontend-requirements docs were written only after
their backend slices shipped.

## 31. Security / Blast Radius

| Tier | Examples | Enforcement |
|---|---|---|
| LOW | light, switch | Existing per-device-category `_require_permission()` only |
| MEDIUM | thermostat | Same |
| HIGH | lock/unlock | Same, **plus** already in `confirm_required_tools` (`unlock_device`) |
| CRITICAL | panic/vacation/siren/disarm | Same, **plus** already in `confirm_required_tools` |

This classification is descriptive, not something Home Automation must
newly enforce — the existing `confirm_required_tools` set and
per-service permission checks already provide the CRITICAL/HIGH tier's
extra protection uniformly, regardless of caller (REST, agent tool,
Scheduler, or this new event-triggered path). Event-driven execution
never bypasses action-level permission (§17); automation-creation
permission never implies device-control permission (§17's principal/
scope separation, mirroring Scheduler's own identical, already-proven
principle).

## 32. Persistence / Schema

`Base.metadata.create_all`'s existing runtime path is sufficient — no
new migration system, matching every prior M7/M12 slice's precedent.
**Two new tables, zero changes to any existing table**:

`AutomationTrigger` (§10, full schema above) — zero coupling to
`Schedule`/`WorkflowExecution`.

`AutomationExecution` (table: `automation_executions`), mirroring
`WorkflowExecution`'s exact shape for its own, separate owner:
```
id: str                       # String(32), PK
automation_trigger_id: str     # String(32), FK -> automation_triggers.id,
                                #   ondelete="CASCADE", NOT NULL
workflow_id: str               # String(32), FK -> workflow_definitions.id,
                                #   ondelete="CASCADE", NOT NULL
source: str                    # String(16), NOT NULL -- "event" | "manual"
started_at: datetime           # DateTime(timezone=True), default utcnow
finished_at: datetime | None   # DateTime(timezone=True), nullable
status: str                    # String(32), NOT NULL -- identical vocabulary to WorkflowExecution
error: str | None              # Text, nullable
step_results_json: str         # Text, default "[]"
Indexes: automation_trigger_id, status (mirrors WorkflowExecution's own indexes exactly).
```

**Why a separate table rather than widening `WorkflowExecution`**: the
alternative (making `WorkflowExecution.schedule_id` nullable, adding a
sibling `automation_trigger_id` FK) would touch an already-shipped,
already-tested M7 table's column definition — even though backward-
compatible, it fails the "preserve existing Scheduler behavior
byte-for-byte" instruction more literally than a parallel table does. A
second table with a mirrored (not reused) shape is not the kind of
"duplicate abstraction" the project's broader discipline warns against
(that discipline targets duplicated *logic*, resolved by §8's
extraction — not a persistence table legitimately owned by a different
parent entity). `WorkflowDefinition` itself remains the one, genuinely
shared table between the two subsystems (§7).

## 33. Testing Strategy

**Architecture guards**: `HomeAutomationService` layering (subscribes
to `EventBus`, never imports connector/MQTT/HA modules); no
`AutomationService` misuse (source-scan: `HomeAutomationService` never
becomes the OS-automation engine); no Memory/Analytics/Event-Viewer/
frontend coupling (source-scan, matching the established
`test_m7_schedule_service.py` convention); `ScheduleService` gains no
`EventBus.subscribe` call (regression guard); `WorkflowExecutionService`
extraction preserves every existing `ScheduleService` test unmodified.

**Event matching**: matching transition fires exactly one dispatch;
wrong `device_id` does not match; wrong `previous_status` (when
`from_status` is set) does not match; wrong `to_status` does not match;
`from_status = ""` matches any previous status; disabled automation
never matches; deleted automation never matches (query returns
nothing); multiple matching triggers each dispatch independently.

**Execution**: `AGENT_TOOL`-kind and `AUTOMATION`-kind steps both
succeed via the identical (now-shared) path; permission denial →
`"denied"`/`"failed"` per §20's exact mapping; confirmation denial →
`"denied"`; connector/device failure → `"failed"`; partial multi-step
failure → `"partially_failed"`; `WorkflowExecutionService.run_workflow`
produces byte-for-byte identical results to the pre-extraction
`ScheduleService._run_workflow` for the same input (a direct regression
test against Scheduler's own existing fixtures).

**Concurrency**: an automation already running is not dispatched again
(no new row, §14); two events matching the same automation
concurrently result in exactly one execution; disabling while queued
→ `"cancelled"`; disabling while running does not interrupt it.

**Loop/re-entrancy**: cooldown (§15) prevents re-dispatch inside the
configured window; a hypothetical future command→refresh event does
not produce unbounded re-firing given the cooldown is in place from day
one.

**Persistence**: `AutomationTrigger`/`AutomationExecution` CRUD; the
`workflow_id`/`automation_trigger_id` cascade-delete behavior (§10/
§32); execution history ordering and retrieval.

**Security**: permission revoked after trigger creation is denied at
the next execution, not the creation-time state (mirrors the Phase 0
audit's own end-to-end-traced Scheduler test); no bypass of
`AgentPermissionGate`/`PermissionGate`; no raw event payload
(`DeviceStateChangedEvent` already carries none, §11) is ever
persisted into `AutomationExecution` beyond the existing
`step_results_json` shape Scheduler's own table already uses safely.

## 34. Acceptance Criteria

All 28 criteria from the Phase 1 instruction are satisfied by this
design: no duplicate workflow engine (§8's single shared
`WorkflowExecutionService`); no duplicate permission engine (§17/§18,
zero new authorization code); `AutomationService` remains OS-automation-
only (§4/§7); Scheduler remains time-trigger-only (§26);
`HomeAutomationService` owns event triggers (§5/§6);
`WorkflowDefinition`/`WorkflowStep`/`WorkflowExecution` reused
(`WorkflowExecution` specifically untouched, §32, by design, not by
omission); authorization evaluated at execution time (§17); confirmation
fails closed (§18); no condition engine fabricated (§3); no
attribute-level triggers fabricated (§10/§11); no raw connector event
path introduced (§11 matches on the already-sanitized
`DeviceStateChangedEvent` only); no Memory/Analytics/Event-Viewer/
frontend coupling (§27-30); loop/re-entry behavior explicitly defined
(§15); duplicate/burst behavior explicitly defined (§16); concurrency
bounded (§14); failure states reuse existing vocabulary (§20); database
changes minimal and justified (§32); REST/agent-tool scope minimal
(§22/§23); manual execution reuses the same path (§21); security
boundaries preserved (§31); Scheduler behavior unchanged (§8's one-line
call-site substitution only); Tier 1/Tier 2 unchanged (nothing in this
contract touches `events.py`, `connectivity_service.py`, or
`smart_home_service.py`); deferred capabilities documented (§35); no
speculative infrastructure (every field/table/setting introduced is
tied to a specific, evidenced requirement above).

## 35. Deferred Scope

Condition engine (AND/OR/NOT, comparisons, state matching); attribute-
level triggers (temperature/brightness/etc. changed); multi-device
triggers; complex trigger composition/multi-trigger AND-OR; MQTT push
triggers; HA-native event subscriptions; presence/geofence triggers;
camera/vision triggers; voice/NL trigger generation; AI-generated
automations; Smart Home Memory integration; Analytics; Event Viewer;
WebSocket relay; frontend implementation; correlation IDs; automatic
post-command refresh; genuinely real-time physical-device reactivity
(bounded by Tier 2's own refresh-triggered nature, not solved here);
arbitrary event-type subscriptions beyond `DeviceStateChangedEvent`.
Each has a named, correct future owner; none is silently dropped.

## 36. Risks / Known Limitations

Restating the Phase 0 audit's central finding precisely, since it
governs this entire design: `DeviceStateChangedEvent` fires only on an
explicit, on-demand refresh — Home Automation built on it inherits
that same limitation. The practical way to get anything resembling
regular automation firing today is to compose this capability *with*
Scheduler (a periodic refresh feeding the events Home Automation
reacts to) — this composition requires no new code on either side, but
it does mean "event-driven" reads, in practice, closer to "poll-driven"
until a future Tier 2 extension changes that. This is stated here as
an explicit, accepted risk for the MVP, not a defect this contract
attempts to solve.

## 37. Implementation Order

1. `WorkflowExecutionService` extraction (§8) — a pure refactor,
   `ScheduleService`'s own full regression suite must pass unmodified
   before anything else proceeds.
2. `AutomationTrigger`/`AutomationExecution` ORM models + repositories
   (§10/§32), picked up via existing `create_all`.
3. `HomeAutomationService` — `EventBus` subscription, trigger matching
   (§11/§12), dispatch via the shared `WorkflowExecutionService`,
   concurrency/cooldown (§14/§15), persistence of execution results.
4. REST routes (§22).
5. Agent tools (§23), wired into `build_tool_registry`/DI exactly like
   Scheduler's own five.
6. Full test matrix (§33).
7. Quality gates, documentation, frontend-requirements doc (§30, only
   after this point) — all future-phase work, not decided further
   here.

## 38. Final Architecture Decision

Proceed to Phase 2 implementation of exactly the MVP this contract
specifies: `WorkflowExecutionService` extraction, `AutomationTrigger`/
`AutomationExecution` persistence, `HomeAutomationService` as a new,
independent event-subscriber service, reusing every existing
permission/confirmation/execution mechanism unchanged. No component of
this design requires unimplemented capability, schema rework beyond
the two new tables specified, or any change to Tier 1, Tier 2, or
Scheduler's own observable behavior.
