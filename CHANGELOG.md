# Changelog

All notable changes to JARVIS OS are documented here. Format loosely
follows [Keep a Changelog](https://keepachangelog.com/).

## M7: Workflow Builder MVP

**No version bump**, unchanged from `0.38.0`. Standalone workflow
authoring — Phase 4, resumed and completed — approved by a dedicated
Phase 0 audit and a Logic Contract
(`docs/M7_WORKFLOW_BUILDER_LOGIC_CONTRACT.md`).

A new `WorkflowBuilderService` provides create/list/get/edit/delete
CRUD over a `WorkflowDefinition` (name, description, an ordered step
list), completely independent of any Schedule or Automation Trigger —
never attached to one in this MVP. The one genuinely new capability
relative to both sibling services: **editing**. `WorkflowRepository`
gained `update`/`list_all` methods; its pre-existing `add`/`get`/
`delete` are unchanged (verified via the full Scheduler and Home
Automation regressions passing unmodified). Execution reuses the
identical shared `WorkflowExecutionService` Scheduler and Home
Automation already dispatch through — not a second execution engine.
Manual "run now" is the only execution path (a standalone workflow has
no trigger), awaited synchronously, mirroring Home Automation's own
manual-run reasoning exactly.

Persisted in a new table, `workflow_builder_executions` — deliberately
separate from `WorkflowExecution`/`AutomationExecution`, so neither
sibling's own already-shipped schema is ever widened. Seven REST
routes under `/api/v1/workflows`, including a `PATCH` route — the
first partial-update endpoint in this milestone's trigger-based
family, since neither Scheduler's nor Home Automation's own
inline-created workflow rows ever needed one. Five agent tools. New
`workflow_builder` permission scope, strictly CRUD-only, identical
separation principle as `scheduler`/`home_automation`. Same fail-safe
(never fail-open) confirmation policy — zero new authorization code.

**Does not literally "build on `RecipeManager`" as originally scoped.**
A fresh audit found `RecipeManager` (M4) models a structurally
incompatible, string-only, agent-tool-free step shape, and lives in
this project's feature-frozen M0–M6 territory — extending it would
violate that freeze rule. Standalone CRUD was built directly over the
existing `WorkflowDefinition`/`WorkflowStep` ORM shape instead (the
same shape Scheduler and Home Automation already execute), satisfying
the roadmap's underlying intent without touching `RecipeManager`,
which remains completely untouched. See
`docs/M7_WORKFLOW_BUILDER_LOGIC_CONTRACT.md` §4 for the full,
evaluated design-option comparison.

A mock-only frontend surface (`src/features/workflowBuilder/` in the
separate `Jarvis-Frontend-main` repository) ships alongside this,
matching Home Automation's own established mock-adapter precedent —
not wired to this REST API in this pass, for the identical
pre-existing auth gap.

51 dedicated backend tests (creation/validation, CRUD, update
semantics, manual execution, ownership separation, scope guards). 30
dedicated frontend tests (list/create/edit/run/delete interactions,
including dedicated partial-update-merge semantics tests, loading/
empty/error states, mock+core adapter unit tests, route registration)
— full frontend suite (590 tests across 80 files) verified, plus a
clean lint/typecheck/build. A handful of full-suite runs showed a
different, unrelated set of pre-existing tests failing each time
(confirmed as environment/load-related flakiness — the same tests
pass reliably in isolation and on the unmodified base branch); all 30
new Workflow Builder tests passed on every run.

## M7: Home Automation MVP

**No version bump**, unchanged from `0.38.0`. Event-triggered
automation, approved by a dedicated Phase 0 audit and a Logic Contract
(`docs/M7_HOME_AUTOMATION_LOGIC_CONTRACT.md`), built directly on
EventBus Tier 2's `DeviceStateChangedEvent`.

A new `HomeAutomationService` subscribes once at startup and matches
each event's `device_id`/`status` against persisted triggers (a
device transitioning to a required `to_status`, from an optional
`from_status` — blank matches any previous status). A match dispatches
the trigger's workflow as a background task, so `EventBus.publish()`
is never blocked on execution. Manual "run now" testing dispatches
synchronously instead, since a manual caller expects to wait for the
result.

**Execution is delegated, not duplicated.** A new
`WorkflowExecutionService` was extracted verbatim from
`ScheduleService`'s former private `_run_workflow` (behavior verified
byte-for-byte via the full pre-existing Scheduler regression run
immediately after the extraction) and is now the single shared
executor both Scheduler and Home Automation dispatch through — not a
second execution engine. Loop/re-entrancy protection is a real,
structural guard here (a `min_refire_interval_seconds` cooldown plus a
non-terminal-execution check on every dispatch attempt), not the
incidental absence of a trigger path Scheduler happened to rely on.
Own bounded concurrency (`HomeAutomationSettings.
max_concurrent_executions`), a separate semaphore from Scheduler's own
— a device-event burst cannot starve scheduled workflows or vice
versa. Same fail-safe (never fail-open) confirmation policy as
Scheduler: a confirm-required step is always denied, never
auto-approved, for both event-triggered and manual dispatch.

Persisted in two new tables, `automation_triggers` /
`automation_executions` — deliberately separate from Scheduler's own
`Schedule`/`WorkflowExecution` tables, so Scheduler's already-shipped
persistence is completely untouched. Eight REST routes under
`/api/v1/home-automation` (including a manual test-run route
Scheduler's own surface doesn't have) and six agent tools. New
`home_automation` permission scope, strictly CRUD-only.

**Scoped strictly to a device's `status` field** — no condition
engine, no attribute-level triggers (brightness/temperature/etc.), no
multi-device conditions, no presence/camera/MQTT-native triggers, no
AI-generated automations, no multi-step workflow authoring in this
slice's own creation surface (the shared executor already supports
multi-step workflows; only single-step trigger authoring ships here).
All confirmed absent by a dedicated Phase 0 audit before this slice
was scoped.

A mock-only frontend surface (`src/features/homeAutomation/` in the
separate `Jarvis-Frontend-main` repository) ships alongside this,
matching that repository's own established convention (every feature
there is backed by an in-memory mock adapter — none has real backend
integration yet, since that frontend has no auth mechanism of any
kind). It is not wired to this REST API in this pass; a
`coreHomeAutomationAdapter` stub is included so real wiring later is a
mechanical swap.

51 dedicated backend tests (trigger matching, cooldown/re-entry,
concurrency, permission/confirmation, lifecycle subscription safety,
persistence, REST, tools, scope guards). 28 dedicated frontend tests
(list/create/enable/disable/run/history/delete interactions, loading/
empty/error states, mock+core adapter unit tests, route registration)
— full frontend suite (588 tests across 80 files) verified green
alongside them, plus a clean lint/typecheck/build. A pre-existing bug
in that repository's shared `Drawer` primitive (used by the
already-shipped `Automations` feature's own detail view, not
introduced by this slice) was found during manual verification and
flagged separately — the drawer never visually slides into view in a
real browser, though the underlying interactions it hosts (run now,
execution history) work correctly regardless.

## M7: EventBus Tier 2 — Device State-Changed Event

**No version bump**, unchanged from `0.38.0`. A single infrastructure
slice, not a new milestone -- approved by a dedicated Phase 0 audit
and a Logic Contract
(`docs/M7_EVENTBUS_DEVICE_STATE_CHANGED_LOGIC_CONTRACT.md`), following
directly from Tier 1's own "device state changed" is a materially
different fact from "a command executed" boundary.

`SmartHomeService.report_device_state()` -- the only place a device's
previous lifecycle status was already fetched into scope (previously
discarded) -- now publishes a new `DeviceStateChangedEvent` whenever
`previous_status != status`: a genuine lifecycle transition
(`discovered`/`pairing`/`paired`/`offline`/`unreachable`/`removed`),
never a same-value no-op refresh. Availability transitions
(offline/unreachable/paired) flow through this identical event, not a
separate type. **Zero new DI wiring**: `SmartHomeService` already held
a live `EventBus` reference. **Zero schema change**: the previous
status value was already being fetched by the existing code, just
discarded; capturing it costs nothing extra.

**Purely additive, by explicit design decision.** The pre-existing
`DeviceUpdatedEvent` -- already shipped, already relayed over
WebSocket as `"device.updated"` -- has its own, separate,
unconditional-publish behavior on this exact code path (it fires on
every call, including no-op refreshes, a real but pre-existing gap
against its own docstring's stated intent). This slice's Logic
Contract explicitly evaluated fixing that behavior in place against
adding a new, independently-guarded event, and chose the latter: any
frontend or backend consumer already relying on `DeviceUpdatedEvent`'s
existing frequency and meaning is completely unaffected -- verified by
the full pre-existing `test_smart_home_service.py` suite passing
unmodified. The `DeviceUpdatedEvent` gap itself remains open,
documented, and available as a separate, future, low-risk fix -- not
resolved by this slice.

Scoped strictly to the generic lifecycle status field -- **not**
per-category device attributes (brightness, temperature, humidity,
etc.), none of which is persisted anywhere in this codebase for such
an event to read. No raw connector payload, no `metadata_json`, no
credentials. Connector-agnostic: touches neither the MQTT nor the Home
Assistant connector, and remains reachable only via the existing
on-demand `POST /connectivity/devices/{id}/refresh` route -- no
polling loop or automatic refresh was introduced.

**Deliberately not relayed over WebSocket yet** -- declared in
`UNPUBLISHED_EVENT_TYPES` (`core/lifecycle/runtime_ws_hub.py`),
matching Tier 1's own deferred-relay treatment, until a real consumer
(a future Event Viewer) exists to justify the surface.

114 targeted tests (emission/non-emission, previous/current status
correctness, first-observation and availability-transition behavior,
subscriber-exception isolation, no-duplicate-events, REST-refresh
parity, payload-structure guards, and `DeviceUpdatedEvent`
compatibility guards, plus the existing WebSocket-relay pinned
vocabulary tests) plus 99 M7 tests, 1414 combined M11+M12 tests, and
the full backend regression (4044 tests, 1 pre-existing unrelated
skip) all green; Black clean, Ruff shows only the codebase's own
already-accepted local-import pattern (`PLC0415`) plus one now-fixed
`contextlib.suppress` finding, Mypy's error set is byte-for-byte
identical to the pre-implementation baseline (262 errors, 64 files).
See
`docs/M7_EVENTBUS_DEVICE_STATE_CHANGED_FRONTEND_REQUIREMENTS.md` for
why there is currently nothing for a frontend to build against this
event.

## M7: EventBus Tier 1 — Device Command Events

**No version bump**, unchanged from `0.38.0`. A single infrastructure
slice, not a new milestone -- approved by a dedicated Post-Scheduler-MVP
Phase 0 audit and a Logic Contract
(`docs/M7_EVENTBUS_DEVICE_COMMAND_EVENTS_LOGIC_CONTRACT.md`).

`ConnectivityService.send_command()` -- confirmed the single chokepoint
every shipped M12 device-command service (Smart Lighting, Smart Locks,
Smart Switch, Appliance, Thermostat, Vacuum/Humidifier, Media Player,
Water Heater, Siren, Alarm Control Panel) already routes through, and
the one a scheduled step reaches identically via the same
authorize-then-invoke tool path -- now publishes a new
`DeviceCommandExecutedEvent` on the existing `EventBus` after a
connector-level result is known. **Zero new DI wiring**:
`ConnectivityService` already held a live `EventBus` reference (used
today only for connector connect/disconnect); this is one new publish
call in an already-injected dependency, not a new abstraction.

Semantics are deliberately narrow: "a command was dispatched to a
connector and its connector-level outcome was observed"
(`success`/`detail`, both already `CommandResult`'s own fields) --
**not** authorization, **not** confirmation, and **not** a claim that
the device's real state changed. Permission denials, validation
failures, and confirmation denials all occur before this chokepoint
and produce no event, verified directly by test, not by inspection
alone. No raw command payload is carried -- matching
`IntegrationCallCompletedEvent`'s own existing "no request/response
body" precedent -- and no correlation/session identifier was
introduced (none exists anywhere in `send_command()`'s current call
chain to thread through). `EventBus.publish()`'s own existing
subscriber-exception isolation (unchanged, verified by test) means a
misbehaving subscriber can never turn a successful command into a
failed one.

**Deliberately not relayed over WebSocket yet** -- the event is
declared in `UNPUBLISHED_EVENT_TYPES`
(`core/lifecycle/runtime_ws_hub.py`), the same "published, relay
deferred" treatment already given to `IntegrationConnectionTestEvent`
and its three siblings, until a real consumer (a future Developer
Tools Event Viewer) exists to justify wiring the frontend WS contract.
No Event Viewer, no Home Automation trigger, no automatic Smart Home
Memory capture, and no device state-change detection ("Tier 2") were
built or designed here -- this event cannot honestly support any of
them, since none observes an actual device state change, only a
command's dispatch outcome.

167 targeted tests plus 11 existing `EventBus` tests, 99 M7 tests, 1264
M12 tests, 1411 combined M11+M12 tests, and the full backend regression
(4027 tests, 1 pre-existing unrelated skip) all green; Black clean,
Ruff shows only the codebase's own already-accepted local-import
pattern (`PLC0415`) plus one now-fixed keyword-only-argument finding,
Mypy's error set is byte-for-byte identical to the pre-implementation
baseline (262 errors, 64 files) -- zero new findings. See
`docs/M7_EVENTBUS_DEVICE_COMMAND_EVENTS_FRONTEND_REQUIREMENTS.md` for
why there is currently nothing for a frontend to build against this
event.

## M7: Workflow Intelligence — Scheduler MVP (Phase 6)

**No version bump**, unchanged from `0.38.0`. M7 as a whole remains
in-progress (Phase 3 deferred, Phases 4-5 still pending) — this entry
records Phase 6 only, following a dedicated Phase 0 audit and an
approved Logic Contract (`docs/M7_SCHEDULER_LOGIC_CONTRACT.md`).

Ships a persistent, timezone-aware Scheduler: interval and 5-field-cron
triggers (`croniter`-backed), executing an ordered `automation`/
`agent_tool` step list by reusing `AutomationService.run_command` and
the same authorize-then-invoke path the agent graph's own
`permission_validator`/`tool_executor` nodes already use — **no second
execution engine**. Bounded-grace-period misfire recovery, per-schedule
duplicate-fire prevention, globally bounded concurrency
(`SchedulerSettings.max_concurrent_jobs`), and full restart recovery
(no in-memory-only state) verified directly, including a test that
constructs a second `ScheduleService` instance against the same
database to simulate a process restart.

**Security-critical design decision, verified by dedicated tests**: any
step that would normally require interactive confirmation
(`unlock_device`, `disarm`, `trigger_panic_mode`, a `shutdown`
instruction, etc.) is **always denied** when fired unattended — no
`confirm` callback is ever supplied, so both existing permission gates
(`PermissionGate`, `AgentPermissionGate`) fall through to their own
existing fail-safe denial, exactly as they already do for every other
unattended caller. Zero new authorization code; a scheduled action can
execute nothing a manual, unscheduled call couldn't already do today.

**Explicitly time-based only** — device-event/state-change triggers
remain out of scope, blocked on a still-unresolved EventBus gap (no
event exists anywhere in this codebase for a device's *operational*
state changing, only connectivity/lifecycle transitions), confirmed by
a dedicated Phase 0 audit before this slice was ever scoped, not
discovered mid-implementation.

New surface: `/api/v1/schedules` (7 REST routes), 5 agent tools
(`list_schedules`/`get_schedule`/`create_schedule`/`enable_schedule`/
`disable_schedule` — `delete_schedule`/`cancel_schedule` deliberately
REST-only), a new `scheduler` permission scope strictly limited to
schedule CRUD (never implies permission to execute a scheduled step's
own action — that stays independently gated at execution time, always).
Three new tables (`WorkflowDefinition`, `Schedule`, `WorkflowExecution`),
picked up automatically via the existing `Base.metadata.create_all`
runtime path, no migration needed. 97 new tests; full M7 regression
(129 tests), M11+M12 regression (1387 tests), and the full backend
regression (4007 tests, 1 pre-existing unrelated skip) all green;
Black/Ruff clean against baseline, Mypy exactly matches the
pre-implementation baseline (262 errors, 64 files) with zero new
findings across 6 new source files.

**Deliberately not shipped in this slice** (each with a named owner):
Workflow Builder authoring UI/API (Phase 4), Recorder (Phase 5),
device-event triggers (a future EventBus capability), a real
interactive confirmation channel (M14 Authorization Engine / a future
Human Interaction surface — Policy A is the correct MVP posture until
one exists), natural-language schedule creation, AI-assisted schedule
generation, cloud/remote scheduling, and any frontend implementation —
see `docs/M7_SCHEDULER_FRONTEND_REQUIREMENTS.md` for the (planning-only,
no code) frontend requirements this slice's API surface implies.

## M12: Final Exit Assessment fix — Appliance MQTT domain fallback (P1-1)

**No version bump**, unchanged from `0.38.0`. Not a new task group --
a single targeted fix approved by a dedicated M12 Final Exit
Assessment (which reviewed all twenty-five shipped task groups and
found exactly one P1 finding, zero P0). `ApplianceService._domain_for`
(`src/jarvis/services/appliance_service.py`) read only
`metadata["domain"]`, unlike every sibling `device_type="appliance"`/
`"other"` service (`SirenService`, `AlarmControlPanelService`, the
Water Heater service, `MediaPlayerService`, `VacuumHumidifierService`),
which already fall back to `metadata["component"]` --
`MqttConnector._handle_ha_discovery` writes `component`, never
`domain`, so an MQTT-discovered Fan or Cover device was silently
unidentifiable. Fixed by adding the same `domain`-first,
`component`-fallback lookup already used by every sibling service;
Home-Assistant-discovered behavior (which always sets `domain`) is
unchanged. 9 new regression tests. Full M12 regression (1252 tests),
M11+M12 regression (1399 tests), and full backend regression (3903
tests, 1 pre-existing unrelated skip) all green; Black/Ruff/Mypy
unchanged against baseline. Zero frontend, connector, EventBus,
Scheduler, or database/schema changes. **Closes M12's
feature-development phase** -- the structured M0-M12 rework phase this
assessment also considered is a separate, not-yet-approved next step.

## M12: Security & Safety — Siren Advanced Controls Slice (Task Group W)

**No version bump**, matching this project's own established
precedent for a task-group-scoped pass; unchanged from `0.38.0`.

Closes M12's own **Siren Advanced Controls Slice** scope -- **not
Security & Safety complete, not Siren Integration "complete again",
not siren history, not pattern/waveform support (no corresponding
Home Assistant capability exists to build)**. Preceded by a Logic
Contract (`docs/M12_SECURITY_SIREN_ADVANCED_CONTROLS_LOGIC_CONTRACT.md`),
written and approved before any code, itself grounded in a fresh M12
Phase 0 audit's own #1 recommendation. Extends the existing
`SirenService.turn_on`/`POST /sirens/{id}/turn_on`/`turn_siren_on`
agent tool in place with three optional parameters -- `tone`,
`duration` (seconds), `volume_level` (`0.0`-`1.0`) -- Home Assistant's
own verbatim `siren.turn_on` parameters, externally verified against
Home Assistant's own current developer documentation this task
group's own Phase 1: `SirenEntityFeature` has exactly five flags
(`TURN_ON`/`TURN_OFF`/`TONES`/`DURATION`/`VOLUME_SET`) -- **no
pattern/waveform flag exists in Home Assistant's siren platform at
all**, so the roadmap's own recurring "tone/duration/volume/pattern"
phrase names a capability with nothing to build; recorded here rather
than silently corrected. No new command, no new method, no new REST
endpoint, no new agent tool -- mirrors `SmartLightingService`'s own
"merge optional attributes into one wire call" shape, not
`ApplianceService`'s separate-endpoint shape, because these are
optional parameters of the *same* HA service, not separate ones.
`tone` is validated against the device's own live-reported
`available_tones` when non-empty, mirroring
`MediaPlayerService._check_source`'s own precedent for an
open-vocabulary parameter, permissive otherwise. `duration`/
`volume_level` are format/range-validated locally only -- Home
Assistant's own base platform already silently filters a parameter an
entity does not support before it reaches the integration, verified
directly from Home Assistant's own developer documentation, so no
local capability pre-check duplicates that. No read-back of any of
the three exists in Home Assistant's own siren state model, so none
is added here -- a pure write-capability expansion, never history or
persisted state. Existing bare `turn_on()`/`turn_off()` calls, existing
permissions (`core:sirens`/`smart_home`), and the existing
`turn_siren_on` confirmation requirement (`AgentPermissionGate` gates
by tool name only, confirmed unaffected by richer arguments) are all
byte-for-byte unchanged. 93 new/updated tests, 0 failures, 0 errors;
Security/AlarmControlPanel/SmartHomeMemory sibling regression 195
tests green; M12 regression 1243 tests green; M11+M12 regression 1390
tests green; full backend regression 3894 tests green, 1 pre-existing
skip.

### Added
- **`SirenService.turn_on`** gains three optional keyword parameters:
  `tone: str | None`, `duration: int | None`, `volume_level: float |
  None`. `turn_off` is completely unchanged -- HA's own `siren.
  turn_off` takes no parameters.
- **`_validate_tone`/`_validate_duration`/`_validate_volume_level`**
  (`services/siren_service.py`) -- format/range validation.
  `volume_level` reuses `media_player_service._validate_volume`'s
  exact `0.0`-`1.0` logic (bool/NaN/inf rejection included). `duration`
  rejects `bool`/non-`int`/negative; no maximum enforced (HA defines
  none). `tone` rejects non-string/empty; the "is this tone actually
  supported" question is answered live, not by a fixed enum.
- **`_check_tone_supported`** -- a live connector read validating a
  requested `tone` against the device's own reported `available_tones`
  attribute, permissive when the device reports none. Mirrors
  `MediaPlayerService._check_source` verbatim.
- **HA/MQTT translators** extended to build `{"tone": ..., "duration":
  ..., "volume_level": ...}` only from whichever parameters are set --
  an omitted parameter is absent from the payload, never `null`.
- **`TurnSirenOnRequest`** (`infrastructure/api/routes/sirens.py`) --
  an all-optional Pydantic body on the existing `POST .../turn_on`
  route; a missing or empty body produces the exact bare call this
  route has always made.
- **`turn_siren_on` agent tool** gains the same three optional
  arguments, using the existing `home_id: str = ""`-style sentinel
  convention already used elsewhere in this same tool file.
- **Frontend requirements document** -- `docs/
  M12_SECURITY_SIREN_ADVANCED_CONTROLS_FRONTEND_REQUIREMENTS.md`,
  planning/specification only, written after the backend was fully
  verified.

### Not changed
- `SirenCommand` enum, `turn_off`, `list_sirens`, `get_siren_state`,
  `_siren_payload` -- byte-identical, zero behavior change. No `tone`/
  `duration`/`volume_level`/`available_tones` key was added to the
  read model.
- Both connectors (`home_assistant.py`, `mqtt.py`) -- **not
  modified**. Both already accept an arbitrary payload dict
  generically.
- `DEVICE_TYPES`, `CONNECTOR_TYPES` -- unmodified.
- No new `PermissionModel` principal -- reuses the existing
  `core:sirens`/`smart_home` grant. No new `confirm_required_tools`
  entry -- `turn_siren_on` was already gated; `AgentPermissionGate`
  gates by tool name only, confirmed unaffected by richer arguments.
- `EventBus`, Scheduler, Analytics, `MemoryService`, `SecurityService`,
  `AlarmControlPanelService` -- untouched. No database/schema changes.

### Explicitly out of scope
- Siren pattern/custom waveform control -- confirmed no corresponding
  Home Assistant `SirenEntityFeature` exists; nothing to build.
- `alarm_control_panel` actions of any kind.
- Siren activation/state history beyond Smart Home Memory's own
  existing, unmodified on-demand snapshot (Task Group V).
- Notifications, automation, scheduled sirens.
- Panic Mode / Vacation Mode coupling, in either direction.
- A future `GET`-side capability read (`available_tones` surfaced in
  `get_siren_state`) -- a real, legitimate possible follow-on,
  deliberately not bundled into this write-only task group.
- Every other M12 module (Smart Cameras, Home Automation, AI Home
  Assistant, Remote Access, Smart Home Analytics).

## M12: Smart Home Memory — Security Device-Category Expansion Slice (Task Group V)

**No version bump**, matching this project's own established
precedent for a task-group-scoped pass; unchanged from `0.38.0`.

Closes M12's own **Smart Home Memory Security Device-Category
Expansion Slice** scope -- **not the full Smart Home Memory module,
not automatic/event-driven history, not Sensor/Lock snapshots**.
Preceded by a Logic Contract (`docs/
M12_SMART_HOME_MEMORY_SECURITY_DEVICE_EXPANSION_LOGIC_CONTRACT.md`),
written and approved before any code, itself grounded in a fresh M12
Phase 0 audit's own recommendation. A third application of the same
dispatch pattern Task Group S already proved twice: a new Tier-3
cascade in `SmartHomeMemoryService._read_state`, gated on
`device_type=="other"`, tries `SirenService.get_siren_state` then
`AlarmControlPanelService.get_alarm_control_panel_state` in turn,
catching each one's own `ServiceError` as "not this category" -- the
identical idiom Tier 2 already established, with zero private
`_domain_for` duplicated and zero new shared domain-resolution
abstraction introduced. `snapshot_home` required zero code change of
its own to pick up the two new categories, confirmed behaviorally (it
has no per-category logic -- it simply calls the now-extended
`_read_state`). Two pre-existing tests had inverted assertions,
corrected explicitly, not silently: a parametrize case asserting Siren
is unsupported (Task Group R's own scope had left it that way) was
replaced with a genuinely still-unsupported `domain="valve"` case, and
a deferred-functionality guard asserting `"alarm_control_panel"` never
appears in source was updated, since this slice's own import and
reader-tuple key legitimately introduce it. No REST endpoint or agent
tool changed -- both layers were already category-agnostic by
construction, confirmed by fresh read before any code was written. An
alarm_control_panel snapshot can persist a real security-posture
history point (including `state: "triggered"`) -- accepted as
explicit, approved scope, distinct from the still-permanently-excluded
Sensor/Lock categories. 82 new/updated tests (two pre-existing
assertions corrected as above), 0 failures, 0 errors; Smart Home
Memory/Siren/alarm_control_panel/Appliance/Security sibling regression
426 tests green; M12 regression 1198 tests green; M11+M12 regression
1345 tests green; full backend regression 3849 tests green, 1
pre-existing skip.

### Added
- **Tier-3 dispatch** (`services/smart_home_memory_service.py`) --
  `_OTHER_DEVICE_TYPE = "other"`, `self._security_readers` ordered
  cascade (`siren` before `alarm_control_panel`, matching ship order),
  a new branch in `_read_state` mirroring Tier 2's own shape exactly.
- **`SmartHomeMemoryService.__init__`** gains two new required keyword
  parameters: `siren: SirenService`, `alarm_control_panels:
  AlarmControlPanelService`.
- **`UnsupportedSnapshotCategoryError`'s** message text now enumerates
  eleven categories instead of nine.
- **DI wiring** (`core/di/container.py`) -- `_build_smart_home_memory_service`
  gains two new parameters, threading the already-existing
  `siren_service`/`alarm_control_panel_service` providers through; no
  new provider created. Live DI sanity check passed.
- **Frontend requirements document** -- `docs/
  M12_SMART_HOME_MEMORY_SECURITY_DEVICE_EXPANSION_FRONTEND_
  REQUIREMENTS.md`, planning/specification only, written after the
  backend was fully verified.

### Not changed
- `routes/smart_home_memory.py`, `agents/tools/smart_home_memory_tools.py`
  -- **not modified**. Both already dispatch generically through
  `snapshot_device`/`snapshot_home`/`list_snapshots`/`delete_snapshot`
  with zero per-category branching.
- `SirenService`, `AlarmControlPanelService` -- untouched. This module
  only calls their own already-public, already-shipped read methods.
- `snapshot_home`, `delete_snapshot`, the snapshot data model, `memory_type`/
  `source="device_snapshot"` -- byte-identical, zero behavior change.
- `DEVICE_TYPES`, `CONNECTOR_TYPES`, both connectors -- unmodified.
- Sensor/Lock exclusion -- unchanged, reaffirmed, not reopened.
- `EventBus`, Scheduler, Analytics, AI/LLM generation -- untouched. No
  database/schema changes.

### Explicitly out of scope
- Sensor and Smart Lock snapshots -- permanently excluded on
  privacy/security grounds, not revisited.
- Camera snapshots -- no `CameraService` exists.
- Automatic/event-driven/scheduled snapshot capture of any category --
  still blocked on the EventBus device-command publishing gap.
- Diff/trend/analytics views over snapshot history -- M20A's job,
  unstarted.
- Any coupling between a snapshot and Siren on/off control,
  alarm_control_panel arm/disarm, Panic Mode, or Vacation Mode.
- Every other M12 module (Smart Cameras, Home Automation, AI Home
  Assistant, Remote Access, Smart Home Analytics).

## M12: Security & Safety — alarm_control_panel Integration Slice (Task Group U)

**No version bump**, matching this project's own established
precedent for a task-group-scoped pass; unchanged from `0.38.0`.

Closes M12's own **alarm_control_panel Integration Slice** scope --
**not the full Security & Safety module, not alarm history/logging,
not any coupling to Siren/Panic/Vacation Mode**. Preceded by a Logic
Contract (`docs/M12_SECURITY_ALARM_CONTROL_PANEL_LOGIC_CONTRACT.md`),
written and approved before any code. A second application of Task
Group R's own `device_type="other"` discrimination pattern: both
connectors already map HA's `alarm_control_panel` domain (and MQTT
Discovery's own `component`) there unconditionally, so an alarm
control panel was already fully identifiable with zero connector or
`DEVICE_TYPES` change -- this slice adds only the read/write service
that acts on that already-captured identity, via a new, standalone
`AlarmControlPanelService` (not an extension of `SecurityService` or
`SirenService` -- `SecurityService.trigger_panic_mode`'s own docstring
already disclaims touching sirens, the identical reasoning that ruled
out extending it here). Exactly three mutations --
`arm_home`/`arm_away`/`disarm` -- never `arm_night`/`arm_vacation`/
`arm_custom_bypass`/`trigger`; `disarm` alone was added to
`AgentSettings.confirm_required_tools`, mirroring
`turn_siren_on`/`unlock_device`'s own directional-risk asymmetry
(`arm_home`/`arm_away` stay ungated as the safe direction). **The
central architectural finding**: Home Assistant's own service
documentation gives zero security guidance on storing, logging, or
transmitting an alarm code, and its own MQTT alarm integration
explicitly warns that an unprotected connection sends a code over the
network in the clear (both externally verified against Home
Assistant's own current developer documentation) -- so this slice
never accepts, stores, logs, or transmits a code/PIN anywhere,
**structurally, not as a deferred gap**: no method, request body, tool
argument, or wire payload in the entire slice has a parameter that
could carry one. Every action is sent as a bare, zero-payload command
-- Home Assistant's own documentation confirms this is a complete,
valid call for any panel that does not require a code; a code-protected
panel simply reports the action failed, honestly, via the same
`CommandResult` path every other M12 mutation already uses. Permission:
a new `core:alarm_control_panels` principal against the existing,
unmodified `smart_home` scope; reads ungated, mutations gated, matching
every prior M12 device-category service's own authorization shape.
REST lives at its own top-level resource, `/api/v1/alarm-control-
panels/*` -- not nested under `/security/*` or `/sirens/*`, following
Siren's own established convention for a sibling service. 73 new
tests, 0 failures, 0 errors; Security/Siren/Smart-Home-Memory/Appliance
sibling regression 340 tests green; M12 regression 1185 tests green;
M11+M12 regression 1332 tests green; full backend regression 3836
tests green, 1 pre-existing skip.

### Added
- **`AlarmControlPanelService`** (`services/alarm_control_panel_service.py`)
  -- `list_alarm_control_panels`, `get_alarm_control_panel_state`,
  `arm_home`, `arm_away`, `disarm`. Identity: `device_type=="other"`
  plus `metadata["domain"]`/`["component"]` fallback resolving to
  `"alarm_control_panel"`, reusing `SirenService._domain_for`'s own
  fallback order verbatim. Read model reports one of Home Assistant's
  own ten verified `AlarmControlPanelState` values (or `None` if
  unrecognized/unavailable) -- never fabricated.
- **HA/MQTT command translation**: HA sends
  `alarm_arm_home`/`alarm_arm_away`/`alarm_disarm` (HA's own real
  service names, externally verified); MQTT sends a JARVIS-native
  `arm_home`/`arm_away`/`disarm` vocabulary mirroring HA's own naming,
  the same choice `SirenService`'s own `_translate_mqtt` already made.
  Every payload, on both connectors, is an empty dict -- no `code`
  field, ever.
- **`GET /api/v1/alarm-control-panels`, `GET .../{device_id}`,
  `POST .../{device_id}/arm_home`, `POST .../{device_id}/arm_away`,
  `POST .../{device_id}/disarm`**
  (`infrastructure/api/routes/alarm_control_panels.py`) -- same
  `{data, meta}` envelope and 404-on-read/400-on-mutation status
  convention `routes/sirens.py` already established.
- **Five agent tools**: `list_alarm_control_panels`,
  `get_alarm_control_panel_state`, `arm_home`, `arm_away`, `disarm`
  (`agents/tools/alarm_control_panel_tools.py`), each wired through the
  same `core:alarm_control_panels`/`smart_home` permission check the
  REST routes use. No tool's generated argument schema has a
  `code`/`pin` field to fill.
- **`"disarm"` added to `AgentSettings.confirm_required_tools`**
  (`core/config/settings.py`) -- `arm_home`/`arm_away` deliberately are
  not, the same asymmetry `turn_siren_on`/`unlock_device` already
  established.
- **Frontend requirements document** -- `docs/
  M12_SECURITY_ALARM_CONTROL_PANEL_FRONTEND_REQUIREMENTS.md`,
  planning/specification only, written after the backend was fully
  verified. Explicitly documents that no code/PIN UI may ever be
  built for this feature.

### Not changed
- `SirenService`, `SecurityService` -- untouched. `AlarmControlPanelService`
  is a new sibling, not an extension of either.
- Both connectors (`home_assistant.py`, `mqtt.py`) -- **not modified**.
  Both already capture `alarm_control_panel`'s own domain/component
  into device metadata unconditionally, for every device, since Task
  Group B.
- `DEVICE_TYPES`, `CONNECTOR_TYPES` -- unmodified.
- `EventBus`, Scheduler, Analytics, `MemoryService`,
  `SmartHomeMemoryService` -- untouched. No database/schema changes.

### Explicitly out of scope
- Any code/PIN entry, storage, logging, or transmission -- permanent,
  not deferred; the absence is structural.
- `arm_night`, `arm_vacation`, `arm_custom_bypass`, and any `trigger`
  action -- narrower variants of an already-proven mechanism, deferred
  as a future, separately-scoped slice if ever needed.
- Alarm history/logging of past arm/disarm events.
- Any coupling to Siren, Panic Mode, or Vacation Mode.
- Scheduled or automatic arm/disarm of any kind.
- Any notification channel on state change (including `triggered`).
- Every other M12 module (Smart Cameras, Home Automation, AI Home
  Assistant, Remote Access, Smart Home Analytics).

## M12: Appliance Control — Fan Percentage + Cover Position Slice (Task Group T)

**No version bump**, matching this project's own established
precedent for a task-group-scoped pass; unchanged from `0.38.0`.

Closes M12's own **Appliance Control — Fan Percentage + Cover
Position Slice** scope -- **not the full Appliance Control module,
not fan oscillation/presets, not cover tilt**. Preceded by a Logic
Contract (`docs/M12_APPLIANCE_FAN_COVER_POSITION_LOGIC_CONTRACT.md`),
written and approved before any code, which independently re-verified
rather than blindly followed the Phase 0 audit's own recommendation:
fresh reads of `appliance_service.py` and the cited
`SmartLightingService` precedent found that only the *translator
function shape* -- `(command) -> (wire_command, payload)` -- was
applicable, not Lighting's own "merge every attribute into one
`turn_on` call" *behavior*, since HA defines `fan.set_percentage` and
`cover.set_cover_position` as their own separate, standalone services,
unlike brightness (which HA only ever accepts as a `turn_on`
parameter). `set_fan_percentage`/`set_cover_position` therefore each
send exactly one standalone wire command, never an implicit
accompanying `turn_on`/`open_cover`. Home Assistant's own
`fan.set_percentage`/`cover.set_cover_position` services were verified
live against Home Assistant's own current developer documentation:
both take a 0-100 integer parameter (`percentage`/`position`
respectively, 0=closed/100=open for covers) with no scale conversion
needed against this module's own normalized range. The single most
important fact this contract found: the cover's **read** attribute is
`current_cover_position`, genuinely different from the **write**
parameter name `position` -- confirmed directly against Home
Assistant's own developer entity documentation, not assumed from the
write-side name. MQTT has no standard equivalent for either service in
any spec this repository follows, so this module defines its own
vocabulary, mirroring HA's own command/payload names exactly -- the
same choice Task Group G's own `turn_on`/`open_cover` already made.
Zero connector changes: both connectors' `send_command` already accept
an arbitrary payload dict generically. Two new dedicated REST verb
endpoints and two new dedicated agent tools, matching this router's
and this tool file's own established one-capability-per-endpoint/tool
convention rather than an optional parameter merged into the existing
on/off/open/close surface. 142 new/updated tests (one pre-existing
Task Group G test was corrected, not merely extended, since its own
"exactly these methods" assertion was inverted by this task group's
approved scope), 0 failures, 0 errors; M12 regression 1112 tests
green; M11+M12 regression 1259 tests green; full backend regression
3763 tests green, 1 pre-existing skip.

### Added
- **`set_fan_percentage(device_id, percentage)`**,
  **`set_cover_position(device_id, position)`**
  (`services/appliance_service.py`) -- each sends exactly one
  standalone wire command (`set_percentage`/`set_cover_position`),
  0-100 integer validated, `bool` explicitly rejected (mirrors
  `smart_lighting_service._validate_brightness`'s own guard against
  the `bool`-is-`int`-subclass gotcha). `0` is a valid, literal
  percentage value, never substituted for `turn_off`.
- **Read-model additions**: `percentage` on `_fan_payload`
  (`attributes.get("percentage")`), `position` on `_cover_payload`
  (`attributes.get("current_cover_position")` -- deliberately not
  `"position"`). Both `None` when unavailable or unreported, never
  fabricated.
- **`POST /api/v1/appliances/fans/{device_id}/set_percentage`,
  `POST /api/v1/appliances/covers/{device_id}/set_position`**
  (`infrastructure/api/routes/appliances.py`).
- **Two new agent tools**: `set_fan_percentage`, `set_cover_position`
  (`agents/tools/appliance_tools.py`), alongside the eight already-
  shipped tools. The tool-factory function was split into
  `_build_fan_tools`/`_build_cover_tools` internal helpers purely to
  keep each one's own statement count manageable -- the public
  `build_appliance_tools` signature and behavior are unchanged.
- **Frontend requirements document** -- `docs/
  M12_APPLIANCE_FAN_COVER_POSITION_FRONTEND_REQUIREMENTS.md`,
  planning/specification only, written after the backend was fully
  verified.

### Not changed
- `FanCommand.TURN_ON`/`TURN_OFF`, `CoverCommand.OPEN`/`CLOSE`,
  `fan_on`, `fan_off`, `cover_open`, `cover_close` -- byte-identical,
  zero behavior change. Every existing test in the three Appliance
  Control test files passes unmodified.
- Both connectors (`home_assistant.py`, `mqtt.py`) -- **not
  modified**. Both already accept an arbitrary payload dict
  generically.
- `DEVICE_TYPES`, `CONNECTOR_TYPES` -- unmodified.
- No new `PermissionModel` principal -- reuses the existing
  `core:appliances`/`smart_home` grant. No `confirm_required_tools`
  entry.
- `EventBus`, Scheduler, Analytics, `MemoryService`,
  `SmartHomeMemoryService` -- untouched. No database/schema changes.
  `SmartHomeMemoryService`'s own Tier-2 cascade (Task Group S)
  automatically picks up the richer `get_fan_state`/`get_cover_state`
  payload with zero code changes of its own, verified by regression.

### Explicitly out of scope
- Fan oscillation, fan preset/speed-list modes.
- Cover tilt control, `stop_cover`.
- Climate's own remaining gaps (fan mode/swing/humidity), Humidifier
  presets, Media Player `play_media`, Water Heater away-mode -- each a
  separate service, out of this task group's named scope.
- Scheduling/automation of percentage or position -- needs M7
  Scheduler, unshipped.
- Historical percentage/position tracking, analytics/trends -- M20A's
  job, unstarted.
- Every other M12 module (Smart Cameras, Home Automation, AI Home
  Assistant, Remote Access, Smart Home Analytics).

## M12: Smart Home Memory — Device-Category Expansion Slice (Task Group S)

**No version bump**, matching this project's own established
precedent for a task-group-scoped pass; unchanged from `0.38.0`.

Closes M12's own **Smart Home Memory — Device-Category Expansion
Slice** scope -- **not the full Smart Home Memory module, not
automatic/event-driven history**. Preceded by a Logic Contract
(`docs/M12_SMART_HOME_MEMORY_EXPANSION_LOGIC_CONTRACT.md`), written
and approved before any code, which independently re-verified rather
than blindly followed the Phase 0 audit's own proposed scope: Task
Group O's own Logic Contract already excluded Sensor and Smart Lock
snapshots on **privacy/security** grounds (occupancy-signal risk,
security-posture-history risk), not architectural ones -- this
contract upholds that exclusion permanently rather than reopening it,
directly overriding the audit's own suggestion to add both. The six
already-shipped appliance-domain categories (Fan, Cover, Vacuum,
Humidifier, Media Player, Water Heater) are added instead -- exactly
the expansion Task Group O's own text anticipated once dispatch was
resolved, without the shared domain-resolution utility it envisioned:
a new Tier-2 mechanism tries each category's own already-public
`get_<category>_state` method in turn, catching that service's own
"not this category" `ServiceError`, safe because device existence is
already confirmed before the cascade runs -- zero private
`_domain_for` duplicated, zero new shared abstraction. Also corrects a
factual error found in Task Group O's own Logic Contract (it claimed
no memory-deletion capability existed anywhere in the repository;
`MemoryService.forget()` already did) and builds a safely-scoped
`delete_snapshot` on top of it -- confirming a target id is actually a
`"device_snapshot"`-type record via the same `browse()` retrieval
already uses, before ever calling `forget()`, so a caller holding only
this module's own grant can never delete an unrelated memory. A new
`snapshot_home` operation snapshots every supported-category device in
one home sequentially, partial-success semantics identical in shape to
Task Group M's own Panic/Vacation Mode response convention -- read-only
against devices, so, unlike Panic/Vacation Mode, no confirmation is
required. 92 new/updated tests (three pre-existing Task Group O tests
were corrected, not merely extended, since their own assertions were
inverted by this task group's approved scope), 0 failures, 0 errors;
M12 regression 1040 tests green; M11+M12 regression 1187 tests green;
full backend regression 3691 tests green, 1 pre-existing skip.

### Added
- **Tier-2 appliance dispatch** (`services/smart_home_memory_service.py`)
  -- `fan`/`cover`/`vacuum`/`humidifier`/`media_player`/`water_heater`
  snapshot support via an ordered cascade over each owning service's
  own public read method. Nine supported categories total.
- **`delete_snapshot(memory_id)`** -- scoped deletion, confirms the
  target is a real snapshot before calling the existing, unmodified
  `MemoryService.forget()`. A new `SnapshotNotFoundError` covers an
  unknown id, a non-snapshot id, and an already-deleted id alike,
  deliberately indistinguishable.
- **`snapshot_home(home_id)`** -- snapshots every supported device in
  a home in one sequential call; unsupported categories are skipped,
  per-device failures never abort the batch. Returns
  `requested_count`/`attempted_count`/`succeeded_count`/
  `failed_count`/`skipped_count` plus full per-device results.
- **`DELETE /api/v1/smart-home/memory/snapshots/{memory_id}`,
  `POST /api/v1/smart-home/memory/snapshots/home/{home_id}`**
  (`infrastructure/api/routes/smart_home_memory.py`).
- **Two new agent tools**: `delete_device_snapshot`, `snapshot_home`
  (`agents/tools/smart_home_memory_tools.py`), alongside the two
  already-shipped `snapshot_device_state`/`list_device_snapshots`.
- **DI wiring** -- `SmartHomeMemoryService` gains four new required
  dependencies (`ApplianceService`, `VacuumHumidifierService`,
  `MediaPlayerService`, `WaterHeaterService`) in `core/di/container.py`.
- **Frontend requirements document** -- `docs/
  M12_SMART_HOME_MEMORY_EXPANSION_FRONTEND_REQUIREMENTS.md`,
  planning/specification only, written after the backend was fully
  verified.

### Not changed
- Sensor and Smart Lock snapshot support -- **permanently excluded**,
  not merely unbuilt (privacy/security grounds, unchanged from Task
  Group O).
- Siren and Camera snapshot support -- out of this task group's named
  scope; not privacy-excluded, simply not requested.
- `MemoryService` -- used unmodified. No new public method added to
  this M0-M6-feature-frozen service; deletion scoping is built entirely
  inside `SmartHomeMemoryService` using `browse()` + `forget()`, both
  already public.
- `DEVICE_TYPES`, `CONNECTOR_TYPES`, the four appliance services
  themselves -- unmodified. No private `_domain_for` duplicated.
- `EventBus`, Scheduler, Analytics -- untouched. No automatic capture,
  no scheduled snapshots, no trend/diff computation.
- No new `PermissionModel` principal, no new scope, no
  `confirm_required_tools` entry.
- No database/schema changes.

### Explicitly out of scope
- Automatic/event-driven device history -- the device-command EventBus
  gap remains unresolved.
- Scheduled/recurring snapshots -- needs M7's Scheduler, unshipped.
- Diff/trend/comparison views over snapshots -- M20A Analytics' job,
  unstarted.
- Device-wide or home-wide snapshot *deletion* -- single-snapshot
  scope only.
- AI-generated snapshot summaries.
- Every other M12 module (Smart Cameras, Home Automation, AI Home
  Assistant, Remote Access, Smart Home Analytics).

## M12: Security & Safety — Siren Integration Slice (Task Group R)

**No version bump**, matching this project's own established
precedent for a task-group-scoped pass; unchanged from `0.38.0`.

Closes M12's own **Security & Safety — Siren Integration Slice**
scope -- **not the full Security & Safety module, not
`alarm_control_panel`, not Panic Mode integration**. Preceded by a
Logic Contract (`docs/M12_SECURITY_SIREN_INTEGRATION_LOGIC_CONTRACT.md`),
written and approved before any code, which independently re-verified
(rather than trusted) the Phase 0 audit's own claims: a direct trace
of `home_assistant.py:_entity_to_discovered_device` and
`mqtt.py:_handle_ha_discovery` confirmed both connectors already
capture a discovered entity's own HA domain / MQTT Discovery
component into `metadata["domain"]`/`["component"]` **unconditionally,
for every device, regardless of `device_type`** -- a siren living
under the generic `device_type="other"` bucket is therefore already
fully identifiable today, with zero connector or `DEVICE_TYPES`
change. A new, standalone `SirenService` (not an extension of
`SmartSwitchService` or `SecurityService` -- the latter's own
docstring already disclaims touching sirens) applies the same
domain/component fallback every appliance-domain service already
established for `device_type="appliance"`, here for the first time to
`device_type="other"`. Two explicit mutations, `turn_on`/`turn_off`,
never a merged `set_siren_state` -- `turn_siren_on` alone requires
agent-layer confirmation (`AgentSettings.confirm_required_tools`),
mirroring `unlock_device`'s own directional-risk asymmetry (turning a
siren on is loud, disruptive, and can draw an unwanted emergency
response; turning one off is always the safe direction). Home
Assistant's own `siren.turn_on`/`turn_off` services were verified
directly against Home Assistant's own developer documentation during
Phase 1: `tone`/`duration`/`volume_level` are each optional and gated
behind device-specific `SirenEntityFeature` flags, confirming a bare,
payload-free call is a complete, valid command for any siren. 50 new
tests, 0 failures, 0 errors; M12 regression 1004 tests green; M11+M12
regression 1151 tests green; full backend regression 3655 tests
green, 1 pre-existing skip.

### Added
- **`SirenService`** (`services/siren_service.py`) -- `list_sirens`,
  `get_siren_state` (ungated reads), `turn_on`/`turn_off` (gated on
  the `smart_home` scope for a new `core:sirens` principal). Identity:
  `device_type == "other"` AND (`metadata["domain"] == "siren"` OR,
  falling back, `metadata["component"] == "siren"`) -- resolved
  entirely in this module; no generic domain-resolution framework was
  introduced.
- **`GET /api/v1/sirens`, `GET /api/v1/sirens/{id}`,
  `POST /api/v1/sirens/{id}/turn_on`, `POST /api/v1/sirens/{id}/
  turn_off`** (`infrastructure/api/routes/sirens.py`) -- its own
  top-level resource, the same `{data, meta}` envelope and
  `Depends(get_current_session)` auth every resource router uses.
  Mutation endpoints send no request body -- HA's `tone`/`duration`/
  `volume_level` parameters are never sent by this MVP.
- **Four agent tools** (`agents/tools/siren_tools.py`): `list_sirens`,
  `get_siren_state`, `turn_siren_on`, `turn_siren_off`. `turn_siren_on`
  added to `AgentSettings.confirm_required_tools`; `turn_siren_off` is
  not.
- **Normalized read model** -- exactly nine fields (`id`, `home_id`,
  `room_id`, `name`, `status`, `manufacturer`, `model`, `external_id`,
  `on`, `available`); `Device.metadata_json` is never included.
  `list_sirens` reports last-known DB fields only (`on: null`,
  `available: false` by construction) -- `get_siren_state` attempts a
  real live connector read, falling back to the same DB-only shape on
  `ConnectivityError`, the same list/detail asymmetry every prior M12
  device-category service already establishes.
- **DI wiring** -- `siren_service` provider in `core/di/container.py`;
  `siren` parameter threaded through `AgentOrchestrator` and
  `build_tool_registry`; `sirens.router` mounted in
  `infrastructure/api/fastapi_server.py`.
- **Frontend requirements document** -- `docs/
  M12_SECURITY_SIREN_INTEGRATION_FRONTEND_REQUIREMENTS.md`,
  planning/specification only, written after the backend was fully
  verified.

### Not changed
- `SmartSwitchService`, `SecurityService` -- **not extended**. Siren
  control is a standalone sibling service.
- Both connectors (`home_assistant.py`, `mqtt.py`) -- **not
  modified**. Siren identity was already captured, unconditionally,
  before this task group.
- `DEVICE_TYPES`, `CONNECTOR_TYPES`, the `Device` schema -- unmodified.
- `EventBus` -- untouched. No coupling to `alarm_control_panel`, Panic
  Mode, or Vacation Mode of any kind.
- `PermissionModel` -- used unmodified; no new scope, only a new
  principal (`core:sirens`) declared against the existing `smart_home`
  scope.

### Explicitly out of scope
- Tone, duration, volume-level, or flashing/strobe pattern control.
- A merged `set_siren_state` mutation.
- Any `alarm_control_panel` integration, Panic Mode/Vacation Mode
  coupling, activation history/logging, or notification on trigger.
- MQTT-native siren discovery beyond the existing, unmodified
  `component` metadata fallback.
- Every other M12 module (Smart Cameras, Home Automation, AI Home
  Assistant, Remote Access, Smart Home Analytics).

## M12: Developer Tools — Device Diagnostics Slice (Task Group Q)

**No version bump**, matching this project's own established
precedent for a task-group-scoped pass; unchanged from `0.38.0`.

Closes M12's own **Developer Tools — Device Diagnostics Slice** scope
-- **not the full Developer Tools module**. Preceded by a Phase 0
audit (`M12 PHASE 0 POST-TASK-P AUDIT`) that found this endpoint the
only remaining candidate needing zero touch to any shared/foundational
class, and directly closing a named, previously-unbuilt roadmap item.
Preceded by a Logic Contract (`docs/
M12_DEVELOPER_TOOLS_DEVICE_DIAGNOSTICS_LOGIC_CONTRACT.md`), written
and approved before any code, which resolved its architecture by
mirroring an existing precedent already in the same file
(`get_plugin_diagnostics`) rather than creating a new service, and
found a genuine, non-obvious defect risk to avoid:
`PermissionModel.is_granted()` carries an audit-log side effect a
passive diagnostic read must never trigger. 37 new tests, 0 failures,
0 errors; M12 regression 956 tests green; M11+M12 regression 1084
tests green; full backend regression 3607 tests green, 1 pre-existing
skip.

### Added
- **`GET /api/v1/devtools/devices/{device_id}/diagnostics`**
  (`infrastructure/api/routes/devtools.py`) -- logic inline in the
  route handler, aggregating three already-shipped calls:
  `SmartHomeService.get_device`, `ConnectivityService.
  read_raw_state`, and `PermissionModel.state` (never `is_granted`).
  Three response sections: `device` (identity, never
  `Device.metadata_json`), `connectivity` (`connector_type`,
  `read_succeeded`, `status`, sanitized `attributes`, `read_error`),
  `permission` (`principal`, `scope`, `state`, `detail`).
- **A failed live connectivity read is never an HTTP error.** Unknown
  device -> 404; a `ConnectivityError` from the live read (no recorded
  connector, connector not connected, or a connector-specific failure)
  -> 200 with `read_succeeded: false` and an explanatory `read_error`,
  the device/permission sections still fully populated -- mirroring
  the same best-effort pattern every device-category service's own
  `read_raw_state` handling already uses.
- **Permission resolution closed to five categories** -- light
  (`core:smart_lighting`), switch (`core:smart_switch`), lock
  (`core:smart_locks`), sensor (`core:sensors`), thermostat
  (`core:thermostats`). `appliance` (which genuinely spans four
  separate principals -- `core:appliances`/`core:media_players`/
  `core:vacuum_humidifier`/`core:water_heaters` -- disambiguated only
  by each appliance service's own private domain-resolution logic) and
  `camera`/every other category report an explicit `principal: null`
  with an explanatory `detail`, never a guessed or duplicated
  principal.
- **Key-based attribute redaction.** Any attribute key (case-
  insensitive) containing `token`/`password`/`secret`/`credential`/
  `api_key`/`apikey`/`auth` has its value replaced with
  `"<redacted>"`; every other key/value passes through verbatim. For
  the five resolvable categories this closes no new exposure surface
  -- the same data is already reachable today through each category's
  own existing read route; the redaction is defense-in-depth, most
  load-bearing for `camera`, which has no shipped read service of its
  own at all.
- **No `PermissionModel` gate on the route itself** -- session auth
  only, matching every other devtools capability, explicitly reasoned:
  unlike Smart Home Memory/Security, this endpoint exposes no real
  device mutation and no credential.
- **Frontend requirements document** -- `docs/
  M12_DEVELOPER_TOOLS_DEVICE_DIAGNOSTICS_FRONTEND_REQUIREMENTS.md`,
  planning/specification only, written after the backend was fully
  verified.

### Not changed
- `SmartHomeService`, `ConnectivityService`, `PermissionModel`, and
  every device-category service -- **not modified**. This slice calls
  their existing public methods only.
- `DEVICE_TYPES`, `CONNECTOR_TYPES` -- unmodified.
- No database/schema changes. No new agent tool. No new permission
  scope.
- `EventBus` -- untouched. No connector was touched.

### Explicitly out of scope
- Appliance sub-domain principal resolution -- would duplicate four
  services' own private domain-resolution logic.
- Any general `device_type -> principal` registry mechanism beyond
  this endpoint's own small, closed, five-row table.
- Device command execution, command history/logging, Event Viewer,
  MQTT Debug Console, automation debugging.
- Historical diagnostics, uptime/latency analytics, automatic health
  monitoring, notifications.
- Every other M12 module (Smart Cameras, Home Automation, AI Home
  Assistant, Remote Access, Smart Home Analytics).

## M12: Developer Tools — Device Simulator Slice (Task Group P)

**No version bump**, matching this project's own established
precedent for a task-group-scoped pass; unchanged from `0.38.0`.

Closes M12's own **Developer Tools — Device Simulator Slice** scope --
**not the full Developer Tools module**. Preceded by a Phase 0 audit
(`M12 PHASE 0 POST-TASK-O AUDIT`) that, for the first time this
milestone, found no zero-architectural-risk candidate left anywhere in
M12 and ranked Device Simulator the strongest of three viable
candidates requiring a real design decision. Preceded by a Logic
Contract (`docs/M12_DEVELOPER_TOOLS_DEVICE_SIMULATOR_LOGIC_CONTRACT.
md`), written and approved before any code, which evaluated three
connector architectures and found a decisive problem with the
seemingly-obvious one (a new `CONNECTOR_TYPES` entry): every
device-category service's own closed `_TRANSLATORS` dict would reject
every mutation command with "no command translation" for a genuinely
new connector-type string, since none of those already-shipped
services carry a third key. 66 new tests, 0 failures, 0 errors,
including a *behavioral* (not flag-only) proof that simulator mode
never instantiates the real `HomeAssistantConnector`; M12 regression
919 tests green; M11+M12 regression 1047 tests green; full backend
regression 3570 tests green, 1 pre-existing skip.

### Added
- **`SimulatorConnector`** (`core/connectivity/connectors/
  simulator.py`) -- structurally satisfies the existing
  `IDeviceConnector` port exactly like `HomeAssistantConnector`/
  `MqttConnector`. Never imports `httpx`, `gmqtt`,
  `HomeAssistantConnector`, `MqttConnector`, or
  `ConnectorCredentialStore` -- every command terminates inside its
  own in-memory state, pinned by a source-level guard.
- **Option C architecture: a DI-time factory swap, not a new connector
  type.** A new, off-by-default `settings.devtools.simulator_enabled`
  flag decides which factory the composition root registers under the
  *existing* `"home_assistant"` connector-registry key -- the real
  `HomeAssistantConnector`'s factory (unchanged, verified
  byte-identical to before this slice existed), or
  `SimulatorConnector`'s. **`CONNECTOR_TYPES` is unmodified** -- still
  exactly `{"home_assistant", "mqtt"}` -- and **no existing
  device-category service was touched**; every one of
  `smart_lighting_service.py`/`smart_switch_service.py`/
  `thermostat_service.py`/`smart_lock_service.py`/`sensor_service.py`'s
  own `_TRANSLATORS` dict still contains exactly `{"home_assistant",
  "mqtt"}`, pinned by a test. The `"mqtt"` registry key is never
  affected by simulator mode.
- **Five MVP device categories** -- light, switch, thermostat, lock,
  sensor -- the same "unique `device_type`, no domain/component
  fallback needed" boundary Task Group O (Smart Home Memory)
  independently identified. Deterministic command→state mutation in
  Home Assistant's own wire vocabulary (`turn_on`/`turn_off`,
  `set_hvac_mode`/`set_temperature`, `lock`/`unlock`), proven against
  the real, unmodified device-category services, not a
  simulator-specific shortcut.
- **Deterministic, caller-configured fault simulation** --
  `unavailable`/`force_command_failure`, sticky until explicitly
  cleared. Zero randomness, zero latency simulation anywhere.
- **Five devtools-only roster-management REST endpoints**
  (`infrastructure/api/routes/devtools.py`) -- define/update, list,
  delete a simulated device; configure its fault state; reset the
  whole roster. **No simulator-specific discover/import/state/command
  route** -- those already run through the existing, unmodified
  generic Connectivity Layer (`routes/connectivity.py`), proven by a
  full REST-level round-trip test. **No `PermissionModel` gate**,
  matching every other devtools capability -- explicitly evaluated,
  not defaulted: a simulated device's mutations never touch real
  device or real home data.
- **A behavioral isolation proof, not a flag assertion.** A test
  monkeypatches the real `HomeAssistantConnector.connect` to raise if
  ever called, then runs a full simulator-mode discover/command flow
  to completion without tripping it -- direct evidence the real
  connector is never instantiated while simulator mode is on, not an
  inferred guarantee.
- **Frontend requirements document** -- `docs/
  M12_DEVELOPER_TOOLS_DEVICE_SIMULATOR_FRONTEND_REQUIREMENTS.md`,
  planning/specification only, written after the backend was fully
  verified.

### Not changed
- `smart_lighting_service.py`, `smart_switch_service.py`,
  `thermostat_service.py`, `smart_lock_service.py`,
  `sensor_service.py` -- **not modified**, including their own
  `_TRANSLATORS` dicts.
- `ConnectivityService`, `ConnectorFactoryRegistry`, `SmartHomeService`
  -- **not modified**. Only the DI composition root's own factory-
  registration wiring changes, gated by the new settings flag.
- `HomeAssistantConnector`, `MqttConnector` -- **not modified**; the
  real Home Assistant connector's behavior is byte-identical to before
  this slice existed when simulator mode is off.
- `CONNECTOR_TYPES` -- unmodified, still exactly `{"home_assistant",
  "mqtt"}`.
- `EventBus` -- untouched by the simulator's own code. (The
  pre-existing, unrelated `ConnectivityStatusChangedEvent` publish
  already fires for any connector type, including the simulator, as
  inherited `ConnectivityService` behavior -- not new code.)
- No database/schema changes. No new permission scope, no new
  principal. No agent tools.

### Explicitly out of scope
- MQTT-slot simulation -- only the `"home_assistant"` registry slot is
  ever swapped.
- Latency/jitter simulation, random/probabilistic failures.
- A devtools "send simulated command" endpoint -- already covered by
  the existing generic `POST /api/v1/connectivity/devices/{id}/
  command` passthrough.
- Appliance-domain simulated categories (fan/cover/vacuum/humidifier/
  media_player/water_heater).
- Persistent/replayable fixture scenarios -- the simulator's own
  roster is ephemeral, in-memory only.
- Every other M12 module (Smart Cameras, Home Automation, AI Home
  Assistant, Remote Access, Smart Home Analytics).

## M12: Smart Home Memory — Manual/On-Demand Device Snapshot Slice (Task Group O)

**No version bump**, matching this project's own established
precedent for a task-group-scoped pass; unchanged from `0.38.0`.

Closes M12's own **Smart Home Memory — Manual/On-Demand Device
Snapshot Slice** scope -- **not the full Smart Home Memory module**.
Preceded by a Phase 0 audit (`M12 POST-TASK-N READINESS / DEPENDENCY
AUDIT`) that re-evaluated Developer Tools, Security, Energy
Management, AI Home Assistant, Smart Home Memory, Smart Cameras, and
Remote Access for further independently-buildable slices and ranked
this one #1. Preceded by a Logic Contract (`docs/
M12_SMART_HOME_MEMORY_SNAPSHOT_LOGIC_CONTRACT.md`), written and
approved before any code, which fixed an absolute naming boundary up
front: this is **Manual/On-Demand Device Snapshot**, never "Device
History," "Continuous Device Monitoring," "Automatic State Tracking,"
or "Event-Driven Memory" -- a snapshot exists only because
`SmartHomeMemoryService.snapshot_device()` was explicitly called,
never automatically. 58 new tests, 0 failures, 0 errors; M12
regression 855 tests green; M11+M12 regression 983 tests green; full
backend regression 3506 tests green, 1 pre-existing skip.

### Added
- **`SmartHomeMemoryService`** (`services/smart_home_memory_service.
  py`) -- a `services/`-layer class composing the already-shipped
  `SmartHomeService` + `SmartLightingService` + `SmartSwitchService` +
  `ThermostatService` + `MemoryService`. No `IDatabase` of its own, no
  `EventBus`, no direct connector import, never reads
  `Device.metadata_json` -- snapshot content/metadata are built only
  from each device-category service's own already-normalized read
  model.
- **`snapshot_device(device_id)`** -- captures a device's current
  state into memory, once, because this call was made. A deterministic
  (no LLM-generated) content sentence plus structured metadata
  (`device_id`, `device_type`, `home_id`, `room_id`, `device_name`,
  `snapshot_at`, `state`) is persisted through the existing
  `MemoryService.remember()`, tagged `memory_type=source=
  "device_snapshot"` -- a plain string, **no `MemoryType` enum value
  added**, exactly as `MemoryType`'s own docstring documents as safe.
  An unavailable device still produces an honest snapshot -- the
  owning service's own read already reports `available: false`/`None`
  live fields rather than raising, and this method persists whatever
  it returns verbatim, never fabricating a substitute.
- **`list_snapshots(device_id?, limit=50)`** -- reuses the already-
  shipped `MemoryService.browse(memory_type="device_snapshot")`
  verbatim, most-recent-first, with a documented client-side
  `device_id` filter. **No new persistence layer, repository, or query
  subsystem** -- `browse()`'s existing filtered listing was already
  sufficient.
- **Device-category scope fixed at light/switch/thermostat only** --
  not every shipped category, and not chosen by default. Sensors and
  Smart Locks are excluded on privacy/security grounds (a persisted,
  browsable snapshot history of occupancy- or security-posture-
  revealing state is a materially larger risk than either category's
  own already-gated live read); every `device_type="appliance"`
  category (Vacuum, Humidifier, Media Player, Water Heater, Fan,
  Cover) is excluded on architectural grounds (no shared, public
  device-to-owning-service resolution utility exists for that shared
  device type today).
- **`POST /api/v1/smart-home/memory/snapshots`** / **`GET
  /api/v1/smart-home/memory/snapshots`** --
  `infrastructure/api/routes/smart_home_memory.py`. Exception-type
  dispatch mirroring `routes/security.py`'s own precedent:
  `SmartHomeMemoryPermissionError` -> 400,
  `UnsupportedSnapshotCategoryError` -> 400 (distinct from an
  unknown-device 404), plain `ServiceError` -> 404. No `PUT`/`PATCH`/
  `DELETE`, no single-snapshot `GET .../{id}`, no batch/home-wide
  route.
- **Two agent tools** -- `snapshot_device_state`, `list_device_snapshots`
  (`agents/tools/smart_home_memory_tools.py`). No third tool
  duplicating the already-generic `recall_memory` tool. Wired through
  `agents/tools/registry.py` and `agents/orchestrator.py`'s existing
  optional-service pattern.
- **Permission gates both directions -- a deliberate departure from
  most M12 modules' "reads ungated" precedent.** Both
  `snapshot_device` and `list_snapshots` require the same
  `core:smart_home_memory`/`smart_home` grant, since a persisted,
  browsable snapshot history carries more cumulative privacy weight
  than any single live device read. No confirmation requirement -- a
  snapshot touches one device and writes one memory row, never a
  physical device.
- **Frontend requirements document** -- `docs/
  M12_SMART_HOME_MEMORY_SNAPSHOT_FRONTEND_REQUIREMENTS.md`,
  planning/specification only, written after the backend was fully
  verified.

### Not changed
- `SmartHomeService`, `SmartLightingService`, `SmartSwitchService`,
  `ThermostatService`, `MemoryService` -- **not modified**. This slice
  calls their existing public methods only.
- `MemoryType` (`core/types.py`) -- **not modified**. The plain-string
  path it already documents as safe is used instead.
- `EventBus` -- untouched. The pre-existing device-command
  event-publishing gap remains unfixed; this slice is deliberately
  scoped around it, not through it.
- Both connectors -- zero code changes.
- No database/schema/migration changes.

### Explicitly out of scope
- Automatic/scheduled/event-driven capture of any kind.
- Sensor, Smart Lock, camera, and every appliance-domain-category
  (Vacuum, Humidifier, Media Player, Water Heater, Fan, Cover)
  snapshot support -- deferred on privacy/security or architectural
  grounds respectively, not merely unbuilt.
- Snapshot deletion -- no memory-deletion capability of any kind is
  exposed via REST or agent tool anywhere in this repository today;
  `MemoryService.forget()` already exists generically and was
  deliberately not newly exposed for this slice.
- Diff-against-previous-snapshot, trend, or analytics views over
  snapshots.
- Home-wide/batch snapshotting -- single-device only.
- Memory-triggered automation, notifications.
- Every other M12 module (Smart Cameras, Home Automation, AI Home
  Assistant, Remote Access, Smart Home Analytics).

## M12: Developer Tools — Connectivity / Integration Health Slice (Task Group N)

**No version bump**, matching this project's own established
precedent for a task-group-scoped pass; unchanged from `0.38.0`.

Closes M12's own **Developer Tools — Connectivity / Integration
Health Slice** scope -- **not the full Developer Tools module**.
Preceded by a Phase 0 audit (`M12 PHASE 0 POST-TASK-GROUP-M AUDIT`)
that found Appliance Control's device-category expansion exhausted
and Security & Safety's own two named slices both shipped, ranking
this slice #1 for reusing a proven M9 Developer Platform Tools
pattern. Preceded by a Logic Contract (`docs/
M12_DEVELOPER_TOOLS_CONNECTIVITY_LOGIC_CONTRACT.md`), written and
approved before any code, which **freshly re-read** M9's actual
`routes/devtools.py` and all four `core/devtools/*.py` components
rather than assuming their shape from naming, and found two things
worth recording precisely: none of M9's five existing devtools
capabilities carries a `PermissionModel` gate (session auth only),
and every `core/devtools/` component depends only on other
`core/`-layer objects, never `services/`. Both findings resolved the
contract's architecture decision. 44 new tests, 0 failures, 0 errors,
plus the pre-existing M9 devtools test suite re-verified green
unmodified.

### Added
- **`DevtoolsConnectivityService`**
  (`services/devtools_connectivity_service.py`) -- a `services/`-layer
  class, deliberately **not** a `core/devtools/` component (every
  existing one depends only on `core/`-layer objects; adding this
  dependency there would have inverted this codebase's own
  core-to-services layering). Depends only on the already-shipped
  `ConnectivityService` + `ConnectorFactoryRegistry` +
  `SmartHomeService` -- no `IDatabase` of its own, no `EventBus`, no
  direct connector import, no `ConnectorCredentialStore`, no
  `Device.metadata_json` read.
- **`GET /api/v1/devtools/connectivity`** -- added to the existing
  `infrastructure/api/routes/devtools.py` file (URL-namespace
  consistency with M9's other four capabilities, not a layering
  concern). Composes two already-shipped read paths never previously
  exposed together over REST: `ConnectorFactoryRegistry.
  registered_types`/`ConnectivityService.is_connected` for connector
  registration/connection state, and `SmartHomeService.
  metadata(home_id)` -- the `HomeMetadata` aggregate Task Group A
  built for Device Health Monitoring and no route had used until now
  -- for per-home device-health counts (`room_count`/`zone_count`/
  `device_count`/`paired_device_count`/`offline_device_count`/
  `unreachable_device_count`). Optional `home_id` filter; omitted ->
  every home.
- **No `PermissionModel` gate, matching M9's own precedent exactly.**
  Session authentication only (`Depends(get_current_session)`) -- a
  deliberate consistency choice, not an oversight: this is diagnostic
  data materially less sensitive than several of M9's own already-
  ungated capabilities (live application logs, full service/plugin
  state).
- **No fabricated telemetry.** Latency, uptime, reconnect counts, and
  error counts are not tracked anywhere in `ConnectivityService` or
  either connector -- none of them appear in the response. Only what
  the existing methods already compute is returned.
- **Structural secret-exposure prevention.** The new service never
  imports `ConnectorCredentialStore` and never reads
  `Device.metadata_json` -- there is no code path by which a
  password, token, API key, or MQTT credential could reach a
  response, verified by both a source-level guard and a REST-response
  text scan in the test suite.
- **Frontend requirements document** -- `docs/
  M12_DEVELOPER_TOOLS_CONNECTIVITY_FRONTEND_REQUIREMENTS.md`,
  planning/specification only, written after the backend was fully
  verified.

### Not changed
- `ConnectivityService`, `SmartHomeService`, `ConnectorFactoryRegistry`
  -- **not modified**. This slice calls their existing public methods
  only.
- Every existing `core/devtools/*.py` component (`DebugConsole`,
  `PerformanceProfiler`, `StateInspector`, `ApiInspector`) -- **not
  modified**, and none of them was extended to depend on
  `services/`.
- The pre-existing M9 devtools test suite (`test_devtools_route.py`)
  -- not modified, re-run and confirmed still green.
- `EventBus` -- untouched. The pre-existing device-command
  event-publishing gap remains unfixed, re-confirmed at the source
  level this session.
- Both connectors -- zero code changes; every required field was
  already reachable through existing service methods.
- No new permission scope, no new principal.
- No database/schema changes.

### Explicitly out of scope
- MQTT Debug Console, Device Simulator -- both need infrastructure
  (raw message inspection, fake-device generation) that doesn't exist.
- **Event Viewer -- explicitly blocked, not merely deferred** -- the
  device-command EventBus publishing gap remains unresolved.
- Command tracing/replay, packet capture, raw MQTT message inspection.
- Latency/uptime/reconnect-history metrics -- not tracked anywhere.
- Device command history, automation/scheduler debugging, camera
  diagnostics, Analytics, Memory, Remote Access, any frontend
  dashboard.
- Every other M12 device-category module (Smart Cameras, Home
  Automation, AI Home Assistant, Remote Access, Smart Home Memory,
  Smart Home Analytics).

## M12: Security & Safety — Manual/On-Demand Action Slice (Task Group M)

**No version bump**, matching this project's own established
precedent for a task-group-scoped pass; unchanged from `0.38.0`.

Closes M12's own **Security & Safety — Manual/On-Demand Action Slice**
scope -- **not the full Security & Safety module**. Preceded by a
Phase 0 audit (`M12 PHASE 0 POST-WATER-HEATER AUDIT`) that found
Appliance Control's device-category expansion exhausted and
recommended Security & Safety's remaining action-taking scope over
Smart Home Memory (blocked on the same device-command event-publishing
gap this session re-confirmed at the source level). Preceded by a
Logic Contract (`docs/M12_SECURITY_ACTION_SLICE_LOGIC_CONTRACT.md`),
written and approved before any code, which independently evaluated
three architectures (extend `SecurityService`, a new
`SecurityActionService` sibling, or fold into
`SmartLockService`/`SmartLightingService` directly) and chose to
**extend the already-shipped `SecurityService`** — the first M12 task
group whose own decision is "extend a previously-shipped class," not
"add a new sibling," because Panic Mode/Vacation Mode are a second
capability over the same "home security posture" concept the read-only
slice already owns, not a new device category. 98 new tests, 0
failures, 0 errors, against real components throughout
(`FakeDeviceConnector`, real temp-file SQLite, real `PermissionModel`).

### Added
- **Two new `SecurityService` methods** —
  `trigger_panic_mode(home_id)` (locks every lock, then turns on every
  light) and `trigger_vacation_mode(home_id)` (locks every lock, turns
  off every light, then best-effort eco-adjusts every thermostat whose
  own reported `hvac_modes` contains an `"eco"` token). Both
  synchronous, on-demand, home-scoped, single-shot -- never scheduled,
  randomized, or event-driven.
- **A genuinely new multi-device result model** -- `status`
  (`SUCCESS`/`PARTIAL_SUCCESS`/`FAILED`/`NO_TARGETS`, derived
  deterministically), `requested_count`/`attempted_count`/
  `succeeded_count`/`failed_count`/`unavailable_count`/
  `skipped_count`, and full per-device detail for locks, lights, and
  (Vacation Mode only) thermostats -- deliberately not a copy of the
  existing 2--3-field merged-mutation shape, since this is the first
  M12 action operating over an unbounded device list rather than a
  handful of fixed fields. No atomicity is ever claimed.
- **A real, directly-verified read-model asymmetry found and worked
  around.** `SmartLockService`'s read model exposes `available`;
  `SmartLightingService`'s does not, at all. Worked around by using
  `Device.status` (present on both) as the uniform unavailability
  signal for locks/lights, while thermostats use their own live-read
  `available` (already needed for eco-detection) -- fixed locally,
  inside the action slice's own orchestration code only. Neither
  `SmartLockService` nor `SmartLightingService` was modified; the
  identical fix for `SmartLightingService`'s own missing `available`
  field is recorded as a separate, narrower follow-up, not decided
  here.
- **Honest eco-detection, nothing invented.** HA's real "eco" value is
  a `preset_mode`, which `ThermostatService` does not expose today
  (deferred by that module's own Logic Contract). Rather than
  extending `ThermostatService` (out of this slice's scope) or
  inventing a temperature-offset fallback (explicitly rejected -- would
  fabricate a capability no device reported), Vacation Mode checks
  each thermostat's own reported `hvac_modes` for a case-insensitive
  exact-token `"eco"` match; a thermostat without one is honestly
  **skipped**, never defaulted.
- **Nested permission boundary preserved.** A missing
  `core:smart_locks`/`core:smart_lighting`/`core:thermostats` grant is
  never bypassed and never aborts the whole call -- it surfaces as an
  ordinary per-device failure, mirroring the read-only slice's own
  "propagate honestly, never swallow" precedent for a missing
  `core:sensors` grant.
- **Security Action REST** -- `POST /api/v1/security/panic-mode` and
  `POST /api/v1/security/vacation-mode` under the existing
  `/api/v1/security` prefix. `infrastructure/api/routes/security.py`.
- **Two agent tools** -- `agents/tools/security_tools.py`:
  `trigger_panic_mode`, `trigger_vacation_mode`.
- **Confirmation requirement, independently evaluated.** Unlike every
  prior M12 setpoint mutation (each reasoning its own blast radius was
  one device), Panic Mode/Vacation Mode affect every lock/light (and,
  for Vacation Mode, every eco-capable thermostat) in an entire home
  at once. `AgentSettings.confirm_required_tools` gains
  `"trigger_panic_mode"`/`"trigger_vacation_mode"` -- the first
  addition since Smart Locks' `unlock_device`.
- **DI** -- `security_service`'s existing provider extended with three
  new dependencies (`SmartLightingService`, `ThermostatService`,
  `SmartHomeService`); no new provider.
- **Frontend requirements document** -- `docs/
  M12_SECURITY_ACTION_SLICE_FRONTEND_REQUIREMENTS.md`, planning/
  specification only, written after the backend was fully verified.

### Not changed
- `SmartLockService`, `SmartLightingService`, `ThermostatService` --
  **not modified**. This slice calls their existing public methods
  only.
- `EventBus` -- untouched. No new event class, no subscriptions, no
  background worker. The pre-existing device-command event-publishing
  gap remains unfixed, re-confirmed at the source level this session
  across all ten prior device-category services.
- Both connectors -- zero code changes.
- No new permission scope, no new principal -- reuses the existing
  `core:security` principal under `smart_home`.
- No database/schema changes.

### Explicitly out of scope
- Scheduled or recurring Panic/Vacation Mode; randomized presence
  simulation; geofencing or occupancy-triggered activation.
- Emergency Alerts, SMS, email, push notifications -- no notification
  transport exists for smart home today.
- Siren/alarm-panel integration -- `device_type="other"` has zero
  service built against it, a real, separate, still-unaddressed gap.
- Camera/vision integration, AI optimization/predictive behavior,
  multi-home orchestration, scenes, user-defined routines, automatic
  remediation, emergency-service integration.
- `preset_mode` support on `ThermostatService`.
- Every other M12 device-category module (Smart Cameras, Home
  Automation, AI Home Assistant, Remote Access, Smart Home Memory,
  Smart Home Analytics, Developer Tools).

## M12: Appliance Control — Water Heater Core Slice (Task Group L)

**No version bump**, matching this project's own established
precedent for a task-group-scoped pass; unchanged from `0.38.0`.

Closes M12's own **Appliance Control — Water Heater Core Slice**
scope -- **not the full Appliance Control module**. Preceded by a
Phase 0 audit (`M12 POST-TASK-GROUP-K PHASE 0 AUDIT`) that re-audited
the current repository state from scratch, re-verified `water_heater`
maps to `device_type="appliance"` in both connectors (the Fan/Cover/
Vacuum/Humidifier/Media Player pattern, not Climate's own-`device_type`
pattern), and confirmed it is the **last** Appliance Control category
not already blocked on the current connector domain mapping (Smart
Kitchen and Smart Pumps/Irrigation both remain blocked). Preceded by a
Logic Contract (`docs/M12_APPLIANCE_WATER_HEATER_LOGIC_CONTRACT.md`),
written and approved before any code, which classified every
protocol-specific claim as verified-in-repository, verified-externally,
or explicitly unverified pending Phase 2 confirmation -- Phase 2 then
verified the two flagged HA wire details directly against HA's actual
`services.yaml` before writing the translator. 98 new tests, 0
failures, 0 errors, against real components throughout
(`FakeDeviceConnector`, real temp-file SQLite, real `PermissionModel`).

### Added
- **`WaterHeaterService`** (`services/water_heater_service.py`) -- one
  service covering read state and one merged on/off + operation-mode +
  temperature mutation, distinguishing water heaters from every other
  appliance sharing `device_type="appliance"` via
  `Device.metadata_json["domain"]` (falling back to `["component"]`
  for MQTT HA-Discovery-sourced devices, reusing Vacuum + Humidifier's
  own template). Depends only on `SmartHomeService` +
  `ConnectivityService` + `PermissionModel` -- no `IDatabase`, no
  `EventBus`.
- **Operation mode, resolved as writable.** HA's real
  `water_heater.set_operation_mode` service (payload key
  `operation_mode`, confirmed against HA's actual `services.yaml` this
  session) validates against the device's own reported
  `operation_list` -- the same template `ThermostatService`'s
  `hvac_mode`/`hvac_modes` already established, chosen deliberately
  over Vacuum + Humidifier's read-only `mode` precedent because real
  evidence supported a settable mechanism here. No fixed operation-mode
  enum is invented anywhere; case is normalized to lowercase (modes are
  short enum-like tokens, unlike Media Player's mixed-case `source`).
- **Temperature** -- `current_temperature`/`target_temperature` pass
  through in whatever unit/precision the device reports, with no
  conversion performed anywhere. `min_temp`/`max_temp` bounds are
  enforced only when the device itself reports them -- no invented
  safety limit, matching every prior M12 numeric field's discipline.
- **On/off**, verified as HA's `turn_on`/`turn_off` services (zero
  payload, confirmed against HA's actual `services.yaml`). `state` is
  an open pass-through string that can be either a plain on/off token
  or an operation-mode token depending on which features a real
  integration supports; a derived `is_on: bool | None` convenience
  field is inferred only when `state` is a recognizable on/off token.
- **Merged mutation** -- `set_water_heater_state(temperature?,
  operation_mode?, on?)`, mirroring `ThermostatService`'s shape. HA
  translation sequences up to three independent single-purpose
  services (`turn_on`/`turn_off`, `set_operation_mode`,
  `set_temperature`, all confirmed against HA's actual `services.yaml`)
  in a stated-convention order -- on/off, then mode, then temperature
  -- stopping at the first failure and naming exactly what already
  applied. MQTT translation stays one merged `set_state` call.
- **Water Heater REST** -- under the existing `/appliances` prefix:
  `/api/v1/appliances/water-heaters/*` with one merged `/state`
  endpoint (matching Thermostat/Humidifier/Media Player's merged-
  mutation shape -- no independent transport verb exists for this
  module). `infrastructure/api/routes/water_heaters.py`.
- **Three agent tools** -- `agents/tools/water_heater_tools.py`:
  `list_water_heaters`, `get_water_heater_state`,
  `set_water_heater_state` (one merged tool, matching Thermostat's
  shape, not Media Player's per-verb shape), wired into the existing
  Tool Registry and `AgentOrchestrator`.
- **Permission enforcement (mutation only)** -- existing
  `PermissionModel`, `smart_home` scope, new principal
  `core:water_heaters`. **Reads are ungated**, following every prior
  Appliance Control category's precedent.
- **Confirmation requirement, explicitly evaluated and rejected.**
  Unlike every prior M12 setpoint, water heater temperature carries a
  real, named scald-injury mechanism from ordinary use -- this was
  weighed seriously against `unlock_device`'s precedent, not
  dismissed, and the Logic Contract records why it still landed on no
  confirmation: no invented safety limit exists (only device-reported
  bounds are enforced), and a setpoint's thermal lag lacks unlock's
  immediate-consequence character. Recorded as the closest call of any
  M12 appliance module to date.
- **DI** -- `water_heater_service` singleton in `core/di/container.py`.
- **Frontend requirements document** -- `docs/
  M12_WATER_HEATER_FRONTEND_REQUIREMENTS.md`, a planning/specification
  artifact derived from the verified backend contract. Contains no
  frontend source code and authorizes no frontend implementation.

### Not changed
- `ApplianceService` -- **not extended**. A source-level test pins
  that it contains no water-heater functional symbol.
- `SmartHomeService`, `ConnectivityService`, `PermissionModel` --
  reused verbatim. No new `DEVICE_TYPES` entry, no new ORM table/column.
- `EventBus` -- untouched. No `WaterHeaterUpdatedEvent`, no
  subscriptions, no background workers. The pre-existing device-command
  event-publishing gap remains unfixed.
- Both connectors -- zero code changes; `water_heater` was already
  mapped to `device_type="appliance"` in both, and
  `metadata["domain"]`/`["component"]` were already captured at
  discovery.
- **Frontend** -- zero files touched under `frontend/` or
  `Jarvis-Frontend-main/frontend`. No component, API client, route,
  state management, hook, type, CSS, test, dependency, or
  configuration change of any kind.

### Explicitly out of scope
- Away/vacation mode (`set_away_mode`/`is_away_mode_on`) -- a real HA
  feature, deliberately excluded from this MVP.
- Dual/secondary setpoint (`target_temperature_high`/`_low`).
- Scheduling, automation (blocked on M7's Scheduler, confirmed still
  unstarted, and the event-publishing gap), energy optimization/
  analytics, predictive/AI control, multi-device orchestration, scenes,
  leak detection, safety alerting, notifications, advanced heating
  profiles, multi-zone control.
- Smart Kitchen Devices -- a different, still-blocked appliance
  category (no consistent HA/MQTT domain model).
- Every other M12 device-category module (Smart Cameras, Home
  Automation, AI Home Assistant, Remote Access, Smart Home Memory,
  Smart Home Analytics, Developer Tools).

## M12: Appliance Control — Media Player Core Slice (Task Group K)

**No version bump**, matching this project's own established
precedent for a task-group-scoped pass; unchanged from `0.38.0`.

Closes M12's own **Appliance Control — Media Player Core Slice**
scope -- **not the full Appliance Control module**. Preceded by a
Phase 0 audit (`M12 PHASE 0 AUDIT — Media Player`) that re-verified
`media_player` maps to `device_type="appliance"` in both connectors
(the Fan/Cover/Vacuum/Humidifier pattern, not Climate's own-`device_type`
pattern). Preceded by a Logic Contract
(`docs/M12_APPLIANCE_MEDIA_PLAYER_LOGIC_CONTRACT.md`), written and
approved before any code, which resolved the slice's two open design
questions: volume stays HA-native `0.0`–`1.0` (no `brightness_pct`-style
0–100 conversion exists for `volume_set`), and `source` validates
against the device's own reported `source_list` only when non-empty,
directly reusing Thermostat's `hvac_mode`/`hvac_modes` template. 117
new tests, 0 failures, 0 errors, against real components throughout
(`FakeDeviceConnector`, real temp-file SQLite, real `PermissionModel`).

### Added
- **`MediaPlayerService`** (`services/media_player_service.py`) -- one
  service covering the full slice, distinguishing media players via
  `Device.metadata_json["domain"]` (falling back to
  `metadata["component"]` for MQTT HA-Discovery-sourced devices,
  reusing Vacuum + Humidifier's own local fallback template).
  Depends only on `SmartHomeService` + `ConnectivityService` +
  `PermissionModel` -- no `IDatabase`, no `EventBus`, no direct
  connector import.
- **Reads** -- normalized payload: `state` (open pass-through string,
  never a closed vocabulary, forced to `None` -- never the literal
  `"unavailable"` string -- when the device is unavailable, mirroring
  Vacuum's identical rule), `available`, `volume_level` (HA-native
  `0.0`-`1.0` float), `is_volume_muted`, `source`, `source_list`, and
  `media_title`/`media_artist` (read-only, zero-cost informational
  fields -- the highest conversational value ("what's playing") for
  the lowest implementation cost). Every unreported field defaults to
  `None`/`[]` -- never a fabricated value.
- **Transport** -- five independent, zero-payload commands (`play`/
  `pause`/`stop`/`next`/`previous`), mirroring `VacuumCommand`'s
  shape.
- **Merged state mutation** -- one merged `set_media_player_state(
  volume?, muted?, source?)`, mirroring `ThermostatService`'s shape.
  HA has three independent single-purpose services here
  (`volume_set`/`volume_mute`/`select_source`), so a combined update
  sends up to three sequential calls in declared order (volume, mute,
  source -- a convention, not a discovered dependency, since none of
  the three changes what another means), stopping at the first
  failure and naming exactly what already applied. MQTT's own
  envelope stays one merged `set_state` call. Volume is validated as
  a finite `0.0`-`1.0` float (`bool`, `NaN`, `+inf`/`-inf` rejected --
  HA's own protocol-level constraint on the parameter itself, not an
  invented device limit). `source` is validated against the device's
  own reported `source_list` only when non-empty -- permissive
  otherwise, no fixed source enum invented, case preserved (not
  lowercased, unlike `hvac_mode`).
- **Media Player REST** -- under the existing `/appliances` prefix:
  `/api/v1/appliances/media-players/*` (five verb-style transport
  endpoints -- `play`/`pause`/`stop`/`next`/`previous`, matching
  Vacuum -- plus one merged `/state` endpoint, matching Thermostat/
  Humidifier). `infrastructure/api/routes/media_players.py`.
- **Eight agent tools** -- `agents/tools/media_player_tools.py`:
  `list_media_players`, `get_media_player_state`, five transport
  tools (one per verb, matching Vacuum's tool shape), and
  `set_media_player_state` (merged mutation, matching Thermostat's
  tool shape), wired into the existing Tool Registry and
  `AgentOrchestrator`.
- **Permission enforcement (mutations only)** -- existing
  `PermissionModel`, `smart_home` scope, new principal
  `core:media_players`. **Reads are ungated**, following Fan/Cover/
  Switch/Thermostat/Vacuum/Humidifier's precedent. No confirmation
  requirement -- ordinary playback control carries no comparable risk
  to `unlock_device`.
- **DI** -- `media_player_service` singleton in `core/di/container.py`.

### Not changed
- `ApplianceService` -- **not extended**. A source-level test pins
  that it contains no media-player functional symbol (its own
  pre-existing docstring already, legitimately, names it as a future
  deferred category).
- `SmartHomeService`, `ConnectivityService`, `PermissionModel` --
  reused verbatim. No new `DEVICE_TYPES` entry, no new ORM table/column.
- `EventBus` -- untouched. No `MediaPlayerUpdatedEvent`, no
  subscriptions, no background workers. The pre-existing
  device-command event-publishing gap remains unfixed.
- Both connectors -- zero code changes; `media_player` was already
  mapped to `device_type="appliance"` in both, and
  `metadata["domain"]`/`["component"]` were already captured at
  discovery.

### Explicitly out of scope
- `play_media` / arbitrary media-URI or content dispatch.
- `join`/`unjoin` / dynamic multi-speaker grouping.
- Shuffle, repeat, sound mode.
- Album, duration, playback position (+ its staleness timestamp).
- Media content ID/type, artwork/image URL.
- Queue/playlist management.
- Room/output synchronization beyond the existing static Room/Group.
- Vendor-specific controls.
- Scheduling, automation (blocked on M7's Scheduler, confirmed
  unstarted, and the event-publishing gap), AI recommendations,
  playback history, analytics.
- Every other M12 device-category module (Smart Cameras, Home
  Automation, AI Home Assistant, Remote Access, Smart Home Memory,
  Smart Home Analytics, Developer Tools).

## M12: Appliance Control — Vacuum + Humidifier Core Slice (Task Group J)

**No version bump**, matching this project's own established
precedent for a task-group-scoped pass; unchanged from `0.38.0`.

Closes M12's own **Appliance Control — Vacuum + Humidifier Core
Slice** scope -- **not the full Appliance Control module**. Preceded
by a Phase 0 audit (`M12 PHASE 0 AUDIT — Vacuum + Humidifier`) that
re-verified both domains map to `device_type="appliance"` in both
connectors (the Fan/Cover pattern, not Climate's own-`device_type`
pattern) and found `metadata["domain"]`/`metadata["component"]` already
captured at discovery -- zero connector changes required. Preceded by a
Logic Contract (`docs/M12_APPLIANCE_VACUUM_HUMIDIFIER_LOGIC_CONTRACT.md`),
written and approved before any code, which corrected a prior
assumption: `ApplianceService`'s own docstring already says a future
category like vacuum/humidifier "likely" needs its own service, so
this slice ships `VacuumHumidifierService`, **not** an
`ApplianceService` extension. 105 new tests, 0 failures, 0 errors,
against real components throughout (`FakeDeviceConnector`, real
temp-file SQLite, real `PermissionModel`).

### Added
- **`VacuumHumidifierService`** (`services/vacuum_humidifier_service.py`)
  -- one service covering both capabilities, distinguishing vacuum from
  humidifier via `Device.metadata_json["domain"]`, the same
  domain-discrimination mechanism `ApplianceService._domain_for`
  established for Fan/Cover. Depends only on `SmartHomeService` +
  `ConnectivityService` + `PermissionModel` -- no `IDatabase`, no
  `EventBus`.
- **A real, pre-existing MQTT gap found and locally worked around.**
  `MqttConnector._handle_ha_discovery` writes
  `metadata["component"]`, never `metadata["domain"]` -- a
  latent gap in already-shipped `ApplianceService._domain_for` too,
  unaddressed there. This module's own domain lookup reads
  `metadata["domain"]`, falling back to `metadata["component"]` (MQTT's
  `component` carries the identical domain vocabulary HA's own REST
  connector calls `domain`) -- fixed locally, once, inside this new
  service only. `ApplianceService` itself was deliberately **not**
  touched; the identical fix for Fan/Cover is recorded as a separate,
  narrower follow-up for future approval.
- **Vacuum** -- four independent, zero-payload commands (`start`/
  `stop`/`pause`/`return_to_base`), mirroring `FanCommand`/
  `CoverCommand`'s shape. `state` is an open pass-through string, never
  validated against a closed vocabulary (unlike Cover's small,
  HA-standard set) -- Vacuum's real state vocabulary has zero
  repository evidence beyond HA's public documentation, verified this
  session (`docked`/`cleaning`/`paused`/`returning`/`error`/`idle`,
  `start`/`stop`/`pause`/`return_to_base` services). `battery_level`
  read when device-reported, `None` otherwise -- never fabricated.
- **Humidifier** -- one merged mutation, `set_humidifier_state(on?,
  target_humidity?)`, mirroring `ThermostatService`'s shape. No known
  HA service accepts on/off and a humidity setpoint together, so a
  combined update sends two sequential calls, **on/off first** (the
  opposite of Thermostat's mode-first ordering -- a humidifier's on/off
  state doesn't change what a humidity setpoint means, so the order is
  a readability convention, not a correctness requirement). `mode` is
  reported when the device provides it but is **read-only** in this
  MVP -- mode-switching is adjacent to presets, already deferred, and
  would need the same device-reported-vocabulary validation complexity
  Thermostat's `hvac_mode` needed. `min_humidity`/`max_humidity`
  enforced only when the device itself reports them -- no invented
  limits.
- **Vacuum+Humidifier REST** -- under the existing `/appliances`
  prefix: `/api/v1/appliances/vacuums/*` (verb-style: `start`/`stop`/
  `pause`/`dock`, matching Fan/Cover) and
  `/api/v1/appliances/humidifiers/*` (merged `/state`, matching
  Thermostat). `infrastructure/api/routes/vacuums_humidifiers.py`.
- **Nine agent tools** -- `agents/tools/vacuum_humidifier_tools.py`:
  six vacuum tools (one per verb, matching Fan/Cover's tool shape) and
  three humidifier tools (merged mutation, matching Thermostat's tool
  shape), wired into the existing Tool Registry and `AgentOrchestrator`.
- **Permission enforcement (mutations only)** -- existing
  `PermissionModel`, `smart_home` scope, new principal
  `core:vacuum_humidifier` (named precisely, not the vaguer
  `core:home_appliances` originally proposed, to avoid confusion with
  the existing `core:appliances`). **Reads are ungated**, following
  Fan/Cover/Switch/Thermostat's precedent. No confirmation requirement
  -- neither capability rises to `unlock_device`'s risk tier.
- **DI** -- `vacuum_humidifier_service` singleton in
  `core/di/container.py`.

### Not changed
- `ApplianceService` -- **not extended**. A source-level test pins
  that it contains no vacuum/humidifier functional symbol (its own
  pre-existing docstring already, legitimately, names both as future
  deferred categories -- unchanged since Task Group G).
- `SmartHomeService`, `ConnectivityService`, `PermissionModel` --
  reused verbatim. No new `DEVICE_TYPES` entry, no new ORM table/column.
- `EventBus` -- untouched. No `VacuumUpdatedEvent`/
  `HumidifierUpdatedEvent`, no subscriptions, no background workers.
  The pre-existing device-command event-publishing gap remains
  unfixed.
- Both connectors -- zero code changes; `vacuum`/`humidifier` were
  already mapped to `device_type="appliance"` in both, and
  `metadata["domain"]`/`["component"]` were already captured at
  discovery.

### Explicitly out of scope
- Vacuum: fan speed, cleaning mode, spot cleaning, locate, room
  targeting, maps, live map streaming, path planning, vendor-specific
  advanced modes, AI optimization.
- Humidifier: mode *control*, presets, fan mode, water-level
  automation.
- Both: scheduling, automation (blocked on M7's Scheduler, confirmed
  unstarted, and the event-publishing gap), environmental/predictive
  optimization, multi-device orchestration, energy optimization.
- Every other M12 device-category module (Smart Cameras, Home
  Automation, AI Home Assistant, Remote Access, Smart Home Memory,
  Smart Home Analytics, Developer Tools).

## M12: Appliance Control — Climate / Thermostat Slice (Task Group I)

**No version bump**, matching this project's own established
precedent for a task-group-scoped pass; unchanged from `0.38.0`.

Closes M12's own **Appliance Control — Climate / Thermostat Slice**
scope -- **not the full Appliance Control module**. Preceded by a
Phase 0 post-Security audit (`M12 PHASE 0 POST-MODULE AUDIT`) that
re-evaluated all seven remaining M12 modules and identified Climate as
the highest-value fully-buildable candidate: `device_type="thermostat"`
was already reserved in `DEVICE_TYPES`, and both connectors already map
HA's `climate` domain to it -- zero connector changes required. Preceded
by a Logic Contract (`docs/M12_APPLIANCE_CLIMATE_LOGIC_CONTRACT.md`),
written and approved before any code, which corrected a prior
assumption: Climate is **not** an `ApplianceService` extension (a
thermostat is its own `device_type`, not a `device_type="appliance"`
device distinguished by `metadata["domain"]`), so this slice ships its
own `ThermostatService`. 90 new tests, 0 failures, 0 errors, against
real components throughout (`FakeDeviceConnector`, real temp-file
SQLite, real `PermissionModel`).

### Added
- **`ThermostatService`** (`services/thermostat_service.py`) -- reads
  current temperature, target temperature, HVAC mode, the device's own
  supported-mode list, and its own reported min/max bounds; one merged
  mutation, `set_thermostat_state(temperature?, hvac_mode?)`, covering
  temperature-only, mode-only, and combined updates. Depends only on
  `SmartHomeService` + `ConnectivityService` + `PermissionModel` -- no
  `IDatabase` (no scenes to persist), no `EventBus`, no direct connector
  import.
- **Two wire translations, deliberately different shapes.** Home
  Assistant models climate as two distinct services
  (`climate.set_hvac_mode`/`climate.set_temperature`); the repository
  carries no evidence `set_temperature` accepts an optional `hvac_mode`
  (searched this session -- zero prior references anywhere in `src/`
  or `tests/`), so a combined update sends two sequential calls, mode
  first, through the existing generic `ConnectivityService.
  send_command` chokepoint -- no connector change needed. MQTT's own
  envelope has no such constraint, so this module defines a first,
  JARVIS-native vocabulary: always one merged `set_state` call,
  deliberately *not* copying HA's two-service split.
- **Honest partial failure.** A combined HA update that applies the
  mode but fails the temperature reports `success: false` naming
  exactly what already applied -- never a false full success, never a
  silent retry.
- **No invented limits or vocabulary.** Temperature bounds are enforced
  only when the device itself reports `min_temp`/`max_temp`; HVAC mode
  is validated against the device's own reported `hvac_modes` when
  present, and accepted permissively when the device declares none --
  no fixed HVAC enum, no manufactured safety range.
- **The one genuinely new normalization case in M12**: because an HA
  climate entity's own state string *is* its HVAC mode, an unavailable
  thermostat reports `hvac_mode: null` -- never the literal
  `"unavailable"`/`"offline"` string.
- **Thermostat REST** -- `GET /api/v1/thermostats`,
  `GET /api/v1/thermostats/{id}`, `POST /api/v1/thermostats/{id}/state`
  (merged body: `temperature?`, `hvac_mode?`; empty body rejected).
  `infrastructure/api/routes/thermostats.py`.
- **Three agent tools** -- `agents/tools/thermostat_tools.py`:
  `list_thermostats`, `get_thermostat_state`, `set_thermostat_state`
  (merged, not split into separate temperature/mode tools -- preserves
  one user intent and avoids two sequential tool/wire calls), wired
  into the existing Tool Registry and `AgentOrchestrator`.
- **Permission enforcement (mutation only)** -- existing
  `PermissionModel`, `smart_home` scope, new principal
  `core:thermostats`. **Reads are ungated**, following Smart Lighting/
  Smart Locks/Smart Switches/Appliance Control's precedent -- a
  thermostat's temperature/mode carries no Sensors-grade privacy
  weight. No confirmation requirement -- a setpoint change has no
  security consequence comparable to `unlock_device`.
- **DI** -- `thermostat_service` singleton in `core/di/container.py`.

### Not changed
- `ApplianceService` -- **not extended**. A source-level test pins that
  it contains no `thermostat`/`hvac` reference of any kind.
- `SmartHomeService`, `ConnectivityService`, `PermissionModel` -- reused
  verbatim. No new `DEVICE_TYPES` entry (`thermostat` was already
  reserved), no new ORM table/column.
- `EventBus` -- untouched. No `ThermostatUpdatedEvent`, no
  subscriptions, no background workers. The pre-existing device-command
  event-publishing gap remains unfixed, a separate architectural task
  for Home Automation/Smart Home Memory/Developer Tools' Event Viewer.
- Both connectors (`HomeAssistantConnector`, `MqttConnector`) -- zero
  changes; `climate` was already mapped to `device_type="thermostat"`
  in both.

### Explicitly out of scope
- Fan mode, swing mode, preset modes, humidity/dehumidification,
  auxiliary/emergency heat, dual setpoint (`target_temp_high`/
  `target_temp_low`) range mode, `target_temp_step` enforcement -- each
  deferred to a future, separately-scoped Appliance Control slice.
- Scheduling, automation, occupancy-aware HVAC, predictive/AI HVAC
  optimization, multi-zone orchestration, thermostat scenes -- Home
  Automation/AI Home Assistant/Smart Home Analytics' job, all unstarted
  or blocked.
- Every other M12 device-category module (Smart Cameras, Home
  Automation, AI Home Assistant, Remote Access, Smart Home Memory,
  Smart Home Analytics, Developer Tools).

## M12: Security & Safety — Read-Only Alert/Status Slice (Task Group H)

**No version bump**, matching this project's own established
precedent for a task-group-scoped pass; unchanged from `0.38.0`.

Closes M12's own **Security & Safety — Read-Only Alert/Status Slice**
scope -- **not the full Security & Safety module**. Preceded by a
read-only post-Task-G next-module audit that re-evaluated all eight
remaining M12 candidates and found Security & Safety the only 🟢
fully-buildable one: its entire data substrate (motion, presence,
occupancy, door, window, smoke, gas, water-leak via `SensorService`;
lock state via `SmartLockService`) already shipped in Task Groups D/E,
and a **pull-based** read-only aggregate needs neither M7's Scheduler
(unstarted) nor the device-command event-publishing gap (unchanged)
that block Home Automation, Smart Home Memory and Developer Tools'
Event Viewer. **Does not close M12**, and does not close Security &
Safety as a whole; see `docs/IMPLEMENTATION_ROADMAP.md` §5H. Preceded
by a Logic Contract (`docs/M12_SECURITY_SAFETY_LOGIC_CONTRACT.md`),
written and separately approved before any code, per this project's own
standing rules. 53 new tests, 0 failures, 0 errors, against real
components throughout (`FakeDeviceConnector`, real temp-file SQLite,
real `PermissionModel`, real `SensorService`/`SmartLockService` --
never a mocked dependency).

### Added
- **`SecurityService`** (`services/security_service.py`) -- a
  **pull-based aggregation** over two already-shipped services,
  depending on `SensorService` + `SmartLockService` + `PermissionModel`
  only. Deliberately takes **no** `ConnectivityService`,
  `SmartHomeService` or `EventBus` dependency: it never reaches a
  connector, and it re-implements none of either service's
  normalization (`_parse_binary`/`_infer_locked`/`_binary_state_label`
  stay where they already live) -- enforced by a source-level test.
- **Closed, non-inferred alert semantics** -- only `smoke`, `gas` and
  `moisture` (HA's real `device_class` name for water leak), whose
  `value=True` reading *is* HA's own literal "hazard detected" meaning,
  can produce an active alert or move the overall status.
  `door`/`window`/`garage_door`/`motion`/`presence`/`occupancy`/
  `vibration` and lock state are reported as **factual status only** --
  never auto-classified as intrusion, never elevated to an alert. No
  detection algorithm, heuristic or probabilistic inference exists
  anywhere in this module.
- **Four-value overall status** -- `CRITICAL > WARNING > UNKNOWN >
  NORMAL`, deterministic precedence, computed from the hazard bucket
  alone. `UNKNOWN` ranks **above** `NORMAL`: an unreadable hazard
  sensor (`WARNING`) and a home with no hazard monitoring at all
  (`UNKNOWN`) are both distinct from, and never collapsed into, a
  confirmed-clear home. **Unavailable/offline/unparseable data is never
  interpreted as safe.**
- **Security & Safety REST** -- `GET /api/v1/security/status`, one
  route only (`infrastructure/api/routes/security.py`), optional
  `home_id`/`room_id` filters, `{data, meta}` envelope with
  `meta.overall_status`. **No 404 case exists** -- a first for M12's
  REST surface, since the endpoint has no single-resource identity;
  permission is the only failure mode (400).
- **Security agent tools** -- `agents/tools/security_tools.py`, two
  read-only tools (`get_security_status`,
  `list_active_security_alerts`) wired into the existing Tool Registry
  and `AgentOrchestrator`. **No mutation tool**, and no
  `AgentSettings.confirm_required_tools` entry -- there is no action to
  confirm.
- **Permission enforcement (reads gated)** -- existing
  `PermissionModel`, existing `smart_home` scope, new principal
  `core:security`. Follows **Sensors'** gated-reads precedent, not
  Lighting/Locks/Switches/Appliances' ungated one: this module's output
  recombines the exact motion/presence/occupancy data Sensors already
  gates, so an ungated aggregate would be a real bypass of that
  boundary.
- **DI** -- `security_service` singleton in `core/di/container.py`.

### Two independent permission gates compose
`core:security` and `core:sensors` remain **independently grantable** --
granting one never grants the other. A caller holding `core:security`
alone still trips `SensorService`'s own check the moment a hazard or
status sensor is read, and the resulting `SensorPermissionError` is
**deliberately not caught** by `SecurityService`: it propagates to a
400. Swallowing it would silently under-report hazards as an empty
"all clear", which the safety boundary forbids more strongly than an
honest failure. Covered by dedicated service, REST and tool tests.

### Safety boundary
**Informational only.** This module does not guarantee physical safety
and does not replace alarms, certified security systems, emergency
services, human judgment or physical safety mechanisms. **No automatic
action is possible**: there is no mutation route, no mutation tool, and
no code path calling `SmartLockService.lock`/`unlock`,
`SmartLightingService`, `SmartSwitchService` or `ApplianceService`. A
`CRITICAL` status is a report, not a response.

### Not changed
- `SensorService`, `SmartLockService`, `SmartLightingService`,
  `SmartSwitchService`, `ApplianceService`, `SmartHomeService`,
  `ConnectivityService`, `PermissionModel` -- reused verbatim, zero
  behavior changes.
- **`EventBus` untouched.** No `SecurityAlertEvent`, no new
  subscriptions, no background worker, no polling. This module
  publishes nothing (a read is not a state change), so
  `/security/status` is **poll-only** -- there is no push notification
  and no live feed. The pre-existing device-command event-publishing
  gap (Lighting/Locks/Sensors/Switches/Appliances never publish
  `DeviceUpdatedEvent` on a command) is **deliberately not fixed here**
  -- it remains a separate architectural task, prerequisite to Home
  Automation/Smart Home Memory/Developer Tools' Event Viewer.
- **Connectors untouched** -- no `HomeAssistantConnector`/
  `MqttConnector` change, no new `DEVICE_TYPES` value, no new ORM
  table or column, no new permission scope.

### Explicitly out of scope (deferred, not stubbed)
- Panic Mode, Vacation Mode, Emergency Alerts, emergency response,
  automatic remediation, any actuator command -- all action-taking;
  several also need a multi-device "scene" concept that does not exist
  anywhere in the codebase.
- Scene/multi-device response, event-driven security automation,
  scheduler-based security automation -- blocked on M7's Scheduler
  (unstarted) and the event-publishing gap above.
- Notifications (no delivery mechanism exists), Analytics (M20A
  unshipped), Smart Home Memory (unstarted), Home Automation
  (unstarted), camera/vision integration (no camera or media
  infrastructure exists).
- Frontend of any kind -- this slice is backend-only.

## M12: Appliance Control — Core Appliance Slice (Task Group G)

**No version bump**, matching this project's own established
precedent for a task-group-scoped pass; unchanged from `0.38.0`.

Closes M12's own **Appliance Control — Core Appliance Slice** scope --
**not the full Appliance Control module**. Preceded by a read-only
next-module audit that re-evaluated all nine remaining M12 candidates
and gave special attention to Appliance Control's own per-domain
buildability, finding Fan and Cover control genuinely unblocked and
low-complexity -- both domains already map to `device_type="appliance"`
in both connectors, and both already have their sub-kind captured via
the existing `metadata["domain"]` discovery field, so **zero connector
code changes were required**. Climate, media_player, vacuum,
water_heater and humidifier were each found to need a structurally
different, non-binary command vocabulary (own future slices); Smart
Pumps/Irrigation was found blocked (HA's `valve` domain maps to
`device_type="other"`, not `"appliance"`); Smart Kitchen Devices was
found blocked (no consistent HA/MQTT domain model). **Does not close
M12**, and does not close Appliance Control as a whole; see
`docs/IMPLEMENTATION_ROADMAP.md` §5H. Preceded by a Logic Contract
(`docs/M12_APPLIANCE_CONTROL_LOGIC_CONTRACT.md`), per this project's own
standing rules. 70 new tests, 0 failures, 0 errors, against real
components throughout (`FakeDeviceConnector`, real temp-file SQLite,
real `PermissionModel`).

### Added
- **`ApplianceService`** (`services/appliance_service.py`) -- one
  service covering both Fan and Cover control (not two services, and
  not a generic multi-category abstraction), distinguishing fan from
  cover via `Device.metadata_json["domain"]`, the same
  domain-discrimination mechanism `SensorService` already established
  for `binary_sensor` vs `sensor`. Home Assistant translation:
  `fan.turn_on`/`fan.turn_off`, `cover.open_cover`/`cover.close_cover`,
  no payload -- HA's own real service names. MQTT translation: a new
  JARVIS-native vocabulary this task group defines, reusing the
  identical literals for cross-connector predictability. No connector
  code changes needed -- both connectors already map HA's `fan`/`cover`
  domains to `device_type="appliance"` and already capture
  `metadata["domain"]`, unchanged since Task Group B/Sensors.
- **Appliance Control REST** -- `/api/v1/appliances/*`, split into two
  sibling resource collections: `GET/POST .../fans[/...]` (list/get/
  on/off) and `GET/POST .../covers[/...]` (list/get/open/close).
  `infrastructure/api/routes/appliances.py`.
- **Appliance agent tools** -- `agents/tools/appliance_tools.py`, eight
  tools (`list_fans`, `get_fan_state`, `fan_on`, `fan_off`,
  `list_covers`, `get_cover_state`, `cover_open`, `cover_close`) wired
  into the existing Tool Registry and `AgentOrchestrator`.
- **Permission enforcement (mutations only)** -- existing
  `PermissionModel`, `smart_home` scope, new principal
  `core:appliances` (one principal covering both capabilities),
  granted through the existing generic grant route. **Reads are
  ungated**, following Smart Lighting/Smart Locks/Smart Switches'
  precedent -- fan/cover state carries no comparable privacy weight to
  sensor data.
- **DI** -- `appliance_service` singleton in `core/di/container.py`.

### Not changed
- `ConnectivityService`, `SmartHomeService`, `SensorService`,
  `PermissionModel` -- reused verbatim. No new `DEVICE_TYPES` entries
  (`"fan"`/`"cover"`) were created -- `device_type="appliance"` plus
  `metadata["domain"]` was sufficient.
- No new pairing endpoint -- reuses the existing `POST /devices/{id}/pair`.
- No `AgentSettings.confirm_required_tools` entry -- neither a fan nor
  a cover is physically safety-relevant.

### Position handling
`fan.set_percentage`/`cover.set_cover_position` were both evaluated
(both architecturally supportable via `SmartLightingService`'s existing
attribute-merge translator pattern) and **deliberately deferred**, kept
out of this pass's approved scope -- no percentage/position field
exists anywhere in this task group's payloads.

### Explicitly out of scope
- Climate/AC, Media Players/Smart TVs, Vacuum, Water Heater/Geysers,
  Humidifier -- each deferred to a future, separately-scoped Appliance
  Control slice; each spans a structurally different HA domain and
  command vocabulary.
- Smart Pumps/Irrigation -- blocked on the `valve` → `device_type=
  "other"` connector mapping.
- Smart Kitchen Devices -- blocked on no consistent HA/MQTT domain
  model.
- Every other M12 device-category module (Smart Cameras, Home
  Automation, AI Home Assistant, Security & Safety, Remote Access,
  Smart Home Memory, Smart Home Analytics, Developer Tools).

## M12: Energy Management — Core Energy Slice (Task Group F)

**No version bump**, matching this project's own established
precedent for a task-group-scoped pass; unchanged from `0.38.0`.

Closes M12's own **Energy Management — Core Energy Slice** scope --
**not the full Energy Management module**. Preceded by a read-only
dependency audit that evaluated all ten items in the roadmap's own
Energy Management feature list separately and found only Smart Plug/
Switch control genuinely unblocked and worth new code -- Power/
Energy/Load Monitoring were found already fully provided by the
shipped Sensors module, and Consumption History/Analytics/
Optimization/Scheduling all found blocked on Smart Home Memory, Smart
Home Analytics/M20A, or Home Automation/M7 (all still unstarted/
unshipped). **Does not close M12**, and does not close Energy
Management as a whole; see `docs/IMPLEMENTATION_ROADMAP.md` §5H.
Preceded by a read-only Logic Contract (`docs/
M12_ENERGY_MANAGEMENT_LOGIC_CONTRACT.md`), per this project's own
standing rules. 36 new tests, 0 failures, 0 errors, against real
components throughout (`FakeDeviceConnector`, real temp-file SQLite,
real `PermissionModel`).

### Added
- **`SmartSwitchService`** (`services/smart_switch_service.py`) --
  normalized on/off control and state/availability reporting for
  `device_type="switch"` devices, mirroring `SmartLockService`'s
  architecture exactly (single-attribute device, no attribute-merge
  case). Home Assistant translation: `switch.turn_on`/
  `switch.turn_off`, no payload. MQTT translation: a new JARVIS-native
  `turn_on`/`turn_off` command vocabulary this task group defines,
  mirroring HA's own service names. No connector code changes needed
  -- both connectors already map HA's `switch` domain, unchanged since
  Task Group B.
- **Smart Switches REST** -- `/api/v1/switches/*`: list/get/on/off.
  `infrastructure/api/routes/smart_switches.py`.
- **Smart Switch agent tools** -- `agents/tools/smart_switch_tools.py`,
  four tools (`list_switches`, `get_switch_state`, `switch_on`,
  `switch_off`) wired into the existing Tool Registry and
  `AgentOrchestrator`.
- **Permission enforcement (mutations only)** -- existing
  `PermissionModel`, `smart_home` scope, new principal
  `core:smart_switch`, granted through the existing generic grant
  route. **Reads are ungated**, deliberately following Smart Lighting/
  Smart Locks' precedent rather than Sensors' -- a switch's on/off
  state carries no comparable privacy weight to sensor data.
- **DI** -- `smart_switch_service` singleton in `core/di/container.py`.

### Not changed
- `ConnectivityService`, `SmartHomeService`, `SensorService`,
  `PermissionModel` -- reused verbatim. No `EnergySensorService`/
  `EnergyTelemetryService`/`EnergyRegistry`/`EnergyPollingService` was
  created; Power/Energy/Load Monitoring continue through the existing,
  unmodified Sensors module.
- No new pairing endpoint -- reuses the existing `POST /devices/{id}/pair`.
- No `AgentSettings.confirm_required_tools` entry -- unlike
  `unlock_device`, a switch is not physically safety-relevant.

### Data model note
A physical smart plug is represented as one `switch` `Device` row
(control, this task group) plus one or more sibling `sensor` `Device`
rows (`device_class="power"`/`"energy"`/..., already covered by
Sensors) -- never a combined "SmartPlug" entity. This is the existing
per-entity model, unchanged.

### Explicitly out of scope
- Consumption History -- Smart Home Memory, unstarted.
- Energy Dashboard, Energy Analytics, Energy Trends -- Smart Home
  Analytics / M20A, unstarted/nonexistent.
- Energy Optimization, Automatic Power Saving, Energy-based
  Automations -- Home Automation, unstarted.
- Load Scheduling -- Home Automation + M7 Scheduler, both unstarted/
  unshipped.
- Every other M12 device-category module (Smart Cameras, Appliance
  Control, Home Automation, AI Home Assistant, Security & Safety,
  Remote Access, Smart Home Memory, Smart Home Analytics, Developer
  Tools).

## M12: Sensors (Task Group E)

**No version bump**, matching this project's own established
precedent for a task-group-scoped pass; unchanged from `0.38.0`.

Closes M12's own **Sensors** scope -- the third of M12's
device-category modules to ship, and the first **read-only** one,
following a second read-only dependency audit that re-ranked Sensors
first (ahead of Energy Management and Appliance Control) once Smart
Locks shipped. **Does not close M12** -- ten device-category modules
remain unstarted; see `docs/IMPLEMENTATION_ROADMAP.md` §5H. Preceded by
a read-only Logic Contract (`docs/M12_SENSORS_LOGIC_CONTRACT.md`), per
this project's own standing rules. 57 new tests, 0 failures, 0 errors,
against real components throughout (`FakeDeviceConnector`, real
temp-file SQLite, real `PermissionModel`).

### Added
- **`SensorService`** (`services/sensor_service.py`) -- normalized
  state reporting for `device_type="sensor"` devices: motion,
  presence, occupancy, door, window, temperature, humidity, air
  quality, water leak, smoke, gas, light level, vibration, keyed by
  Home Assistant's own real `device_class` vocabulary (`moisture` for
  water leak, `illuminance` for light level -- not invented names). No
  command translation anywhere in this module -- exactly one
  capability (read current state), so unlike Lighting/Locks there is
  no wire-format table at all.
- **Connector enhancement** -- `HomeAssistantConnector`/`MqttConnector`
  both gained one small, symmetric, additive line capturing
  `device_class` (already present in the same discovery payload each
  already parses) into `Device.metadata_json`. No new request, no new
  topic, no behavior change for any non-sensor entity.
- **Sensors REST** -- `/api/v1/sensors/*`: `GET /sensors` (list),
  `GET /sensors/{id}` (full live reading). No mutation route anywhere
  -- sensors are read-only. `infrastructure/api/routes/sensors.py`.
- **Sensor agent tools** -- `agents/tools/sensor_tools.py`, four
  read-only tools (`list_sensors`, `get_sensor_state`,
  `get_sensor_value`, `get_sensor_status`) wired into the existing Tool
  Registry and `AgentOrchestrator`.
- **Permission behavior, deliberately different from Lighting/Locks**
  -- every operation, including reads, requires the existing
  `PermissionModel`'s `smart_home` scope (new principal
  `core:sensors`), because for a sensor *observing* is the entire
  product (motion/presence/occupancy data can reveal who is home and
  when), unlike a light or lock's comparatively low-stakes observable
  state. No new permission scope was created, and a finer
  per-device-class split was explicitly considered and rejected as
  architecturally inconsistent with every other M12 module. New local
  `SensorPermissionError(ServiceError)` lets the REST route distinguish
  "permission not granted" (400) from "not found" (404) by exception
  type, not by message-sniffing -- mirroring `core/exceptions.py`'s own
  `AutomationPermissionDeniedError` precedent.
- **DI** -- `sensor_service` singleton in `core/di/container.py`.

### Not changed
- `ConnectivityService`, `SmartHomeService`, `PermissionModel` --
  reused verbatim, no second connectivity service, no second
  permission engine, no polling framework.
- No new event class -- this module publishes nothing (a read is not a
  state change); `DeviceUpdatedEvent` remains untouched.

### Explicitly out of scope
- Any automation/trigger logic (motion-triggered lighting,
  leak-triggered workflows, sunrise/sunset, schedules) -- Home
  Automation's job, unstarted.
- Energy-specific logic (optimization, load scheduling, dashboards,
  billing) -- Energy Management's job, unstarted.
- Security response logic (intrusion response, panic mode, emergency
  workflows, safety-critical actuator control) -- Security & Safety's
  job, unstarted; smoke/gas/water-leak sensors expose normalized data
  only, never a reaction.
- Every other M12 device-category module (Smart Cameras, Energy
  Management, Appliance Control, Home Automation, AI Home Assistant,
  Security & Safety, Remote Access, Smart Home Memory, Smart Home
  Analytics, Developer Tools).

## M12: Smart Locks (Task Group D)

**No version bump**, matching this project's own established
precedent for a task-group-scoped pass; unchanged from `0.38.0`.

Closes M12's own **Smart Locks** scope -- the second of M12's
device-category modules to ship, following a read-only dependency
audit that ranked Smart Locks, Sensors and Energy Management as the
only unblocked candidates among the twelve remaining modules (Home
Automation, AI Home Assistant, Security & Safety, Remote Access and
Smart Home Analytics were each found genuinely blocked on an unshipped
cross-milestone dependency). **Does not close M12** -- eleven
device-category modules remain unstarted; see
`docs/IMPLEMENTATION_ROADMAP.md` §5H. Preceded by a read-only Logic
Contract (`docs/M12_SMART_LOCKS_LOGIC_CONTRACT.md`), per this project's
own standing rules. 39 new tests, 0 failures, 0 errors, against real
components throughout (`FakeDeviceConnector`, real temp-file SQLite,
real `PermissionModel`, real `AgentPermissionGate`).

### Added
- **`SmartLockService`** (`services/smart_lock_service.py`) --
  normalized lock/unlock control and state/availability reporting for
  `device_type="lock"` devices, mirroring `SmartLightingService`'s own
  architecture exactly, reduced to a single-attribute device (no
  attribute-merge case exists for a binary lock). Home Assistant
  translation: `lock.lock`/`lock.unlock`, no payload. MQTT translation:
  a new JARVIS-native `lock`/`unlock` command vocabulary this task
  group defines, mirroring HA's own service names.
- **Smart Locks REST** -- `/api/v1/smart-locks/*`: list/get/lock/unlock.
  No body-driven `/state` endpoint (unlike Smart Lighting's merged
  one) -- two explicit action verbs are clearer for a single binary
  attribute. `infrastructure/api/routes/smart_locks.py`.
- **Smart Lock agent tools** -- `agents/tools/smart_lock_tools.py`,
  four tools (`list_locks`, `get_lock_status`, `lock_device`,
  `unlock_device`) wired into the existing Tool Registry and
  `AgentOrchestrator`, converging on the same `SmartLockService`
  methods the REST route calls.
- **Permission enforcement** -- every side-effecting operation requires
  the existing `PermissionModel`'s `smart_home` scope, under a new
  fixed principal `core:smart_locks`, granted through the existing
  generic `POST /api/v1/plugins/{id}/permissions/{scope}/grant` route
  -- no new authorization mechanism.
- **Safety: `unlock_device` added to `AgentSettings.
  confirm_required_tools`'s default set** (`core/config/settings.py`)
  -- reuses `AgentPermissionGate`'s existing confirmation mechanism, no
  new confirmation system. `lock_device` is deliberately not included
  (locking is the fail-safe direction; an unattended future "Auto Lock"
  feature would be pointless otherwise). This gate applies only to the
  agent-tool path -- REST callers are already behind session auth plus
  the `PermissionModel` grant.
- **DI** -- `smart_lock_service` singleton in `core/di/container.py`.

### Not changed
- `ConnectivityService`, `SmartHomeService`, `PermissionModel`,
  `AgentPermissionGate` -- reused verbatim, no second connectivity
  service, no second permission engine, no second confirmation system.
- No new pairing endpoint -- reuses the existing `POST /devices/{id}/pair`.
- No new WebSocket event class -- reuses `DeviceUpdatedEvent`.

### Explicitly out of scope
- Guest access codes, temporary PINs, NFC/fingerprint enrollment -- no
  schema exists for any of it.
- Access history -- no existing mechanism captures a queryable "who
  locked/unlocked when" trail without new infrastructure this task
  group was not asked to add; `lock()`/`unlock()` do not write to the
  DB or publish an event, matching `SmartLightingService.
  set_light_state`'s own behavior.
- Auto Lock or any other trigger-based behavior -- deferred to the
  unstarted Home Automation module.
- Every other M12 device-category module (Sensors, Smart Cameras,
  Energy Management, Appliance Control, Home Automation, AI Home
  Assistant, Security & Safety, Remote Access, Smart Home Memory, Smart
  Home Analytics, Developer Tools).

## M12: Connectivity REST + Smart Lighting (Task Group C)

**No version bump**, matching this project's own established
precedent for a task-group-scoped pass; unchanged from `0.38.0`.

Closes M12's own **Connectivity REST + Smart Lighting** scope -- the
first of M12's thirteen still-unstarted device-category modules to
ship, plus REST exposure of the already-shipped `ConnectivityService`
(Task Group B). **Does not close M12** -- twelve device-category
modules remain unstarted; see `docs/IMPLEMENTATION_ROADMAP.md` §5H.
Preceded by a read-only Phase 0 audit and a Logic Contract
(`docs/M12_CONNECTIVITY_REST_SMART_LIGHTING_LOGIC_CONTRACT.md`), per
this project's own standing rules. 59 new tests, 0 failures, 0 errors,
0 skipped, against real components throughout (`FakeDeviceConnector`,
real temp-file SQLite, real `PermissionModel`, real FastAPI
`TestClient` + DI container).

### Added
- **`ConnectivityService` REST exposure** -- `/api/v1/connectivity/*`:
  connector connect/disconnect, discovery, device state refresh, and a
  generic uninterpreted `send_command` passthrough.
  `infrastructure/api/routes/connectivity.py`.
- **`ConnectivityService.read_raw_state()`** -- a new method returning
  a connector's unmapped `DeviceState` (real attributes), distinct from
  the existing `refresh_device_state()` which only writes Task Group
  A's lifecycle vocabulary onto `Device.status`.
  `connector_type_for()` promoted from a private staticmethod to a
  module-level function so a second caller (Smart Lighting) can reuse
  it without duplicating `Device.metadata_json` parsing.
- **`SmartLightingService`** (`services/smart_lighting_service.py`) --
  normalized on/off, brightness (0-100), color temperature (Kelvin)
  and RGB color control; room/group fan-out with per-device fault
  isolation; lighting scenes (new `LightingScene` ORM model +
  `SceneRepository`). Translates into Home Assistant (a single merged
  `light.turn_on` service call) and MQTT (a new JARVIS-native
  `turn_off`/`set_state` command vocabulary this task group defines)
  through the existing `ConnectivityService.send_command` chokepoint --
  no second execution path.
- **Smart Lighting REST** -- `/api/v1/smart-lighting/*`: lights
  (list/get/set-state), room/group fan-out, scenes (create/list/get/
  delete/apply). `infrastructure/api/routes/smart_lighting.py`.
- **Smart Lighting agent tools** -- `agents/tools/
  smart_lighting_tools.py`, seven tools wired into the existing Tool
  Registry and `AgentOrchestrator` (`smart_lighting` param threaded
  through `build_tool_registry`, `AgentOrchestrator.__init__`/
  `.start()`, and the DI composition root) -- converges on the same
  `SmartLightingService` methods the REST route calls, so both trip the
  same permission gate.
- **Permission enforcement** -- every side-effecting Smart Lighting
  operation requires the existing `PermissionModel`'s `smart_home`
  scope (pre-declared since M9, never enforced before this task group),
  under a new fixed principal `core:smart_lighting`, granted through
  the existing generic `POST /api/v1/plugins/{id}/permissions/{scope}/
  grant` route (M9 Task Group E) -- no new authorization mechanism.
- **DI** -- `smart_lighting_service` singleton in
  `core/di/container.py`.

### Not changed
- `SmartHomeService`, `ConnectivityService`'s existing methods,
  `IDeviceConnector`, `ConnectorFactoryRegistry`, `PermissionModel` --
  reused verbatim (plus the one additive `read_raw_state()` method),
  no second connectivity service, no second permission engine.
- No new pairing endpoint -- reuses the existing `POST /devices/{id}/pair`.
- No new WebSocket event class -- reuses `DeviceUpdatedEvent`/
  `ConnectivityStatusChangedEvent`.

### Explicitly out of scope
- Motion-activated lighting, sunrise/sunset automation, scheduled
  lighting -- deferred to the separate, unstarted Home Automation
  module.
- Every other M12 device-category module (Smart Locks, Sensors, Smart
  Cameras, Energy Management, Appliance Control, AI Home Assistant,
  Security & Safety, Remote Access, Smart Home Memory, Smart Home
  Analytics, Developer Tools).

## M11: API Center Architecture module

**No version bump**, matching this project's own established
precedent for a task-group-scoped pass; unchanged from `0.38.0`.

Closes M11's "API Center Architecture" module -- the roadmap's own
lifecycle-management design for M11's `core/integrations/` engine,
previously "Planning only; no implementation exists yet"
(`MASTER_ROADMAP.md`). Scoped throughout to *catalogued external
vendor integrations* (Google Workspace today) -- never `ILLMProvider`,
AI/voice/vision provider routing, or the unscheduled AI/API Calibration
Engine, which this module never touches. Preceded by a read-only Phase
0 audit and a Logic Contract (`docs/M11_API_CENTER_ARCHITECTURE_DECISIONS.md`,
`docs/M11_API_CENTER_SCOPE_MATRIX.md`, `docs/M11_API_CENTER_LOGIC_CONTRACT.md`),
per this project's own standing rules. Implemented as seven internal
Task Groups (A-G, distinct from M11's own Task Groups A-F), each with
its own audit-first read → design → implement → test → verify pass.
410 tests, 0 failures, 0 errors, 0 skipped.

### Added
- **`IntegrationService.health()`** (Task Group C) -- local-only status
  read, never a vendor request; rides the existing `mcp` `HealthMonitor`
  collector rather than a second one. `GET /integrations/{id}/health`.
- **`IntegrationService.test_connection()`** (Task Group B) -- the
  first M11 capability permitted to make a real, bounded, read-only
  vendor request; supersedes the mock validator as this module's own
  production validation path (M5's own separate `MockApiValidator`
  wiring is untouched -- still open). `ApiGateway` gained per-call
  `timeout_seconds`/`single_attempt` (no silent retry).
  `POST /integrations/{id}/test-connection`.
- **`IntegrationService.switch()` / `invoke_with_failover()`**
  (Task Group E) -- user-triggered Runtime Switching and
  single-candidate, caller-named vendor Failover, both restricted to
  already-installed, capability-compatible, credentialed catalogued
  integrations. Never chains, never loops, never touches credentials.
  `POST /integrations/switch`, `GET /integrations/failover/history`.
- **`IntegrationService.discover()`** (Task Group F) -- enumerates
  `core/integrations/catalogue.py` and registers unregistered entries
  through the existing `install()`; discover + register only, never
  auto-activate, never contacts a vendor.
  `POST /integrations/discover`.
- **`IntegrationService.observability_snapshot()`** (Task Group G) --
  consolidated, secret-free operational counters across the whole
  module. `GET /integrations/observability`.
- New events: `IntegrationConnectionTestEvent`, `IntegrationSwitchEvent`,
  `IntegrationFailoverEvent`, `IntegrationDiscoveryEvent` -- published
  today, WebSocket relay deliberately deferred (a frontend-touching
  contract change outside this module's backend-only scope; see
  `runtime_ws_hub.py`'s `UNPUBLISHED_EVENT_TYPES`).

### Not changed
- M5's `ApiCenterService` and its `MockApiValidator` default (separate,
  still-open item).
- `core/mcp/providers/registry.py`, `core/mcp/providers/manager.py`,
  `core/mcp/auth/*` -- reused verbatim throughout, no second registry,
  provider manager, or credential store introduced.
- `ILLMProvider`, `infrastructure/llm/`, and every AI Calibration
  Engine concept -- structurally never referenced (verified by test).
- Version-compatibility policy for discovered integrations and global
  API rate limiting -- both remain open, explicitly deferred
  architecture decisions.

## M10: Conversational Orchestration Routing

**No version bump**, matching this project's own established
precedent for a task-group-scoped pass; `0.38.0` is unchanged.

Closes two items M10's own Closure Summary explicitly recorded as
deferred: "Intent Engine gating graph routing" (cited M10A/M10B as
blockers -- both have since shipped) and "Remaining UI integration"
(Chat/Voice reaching `AgentOrchestrator`). Preceded by a read-only
Phase 0 audit and a Logic Contract
(`docs/ORCHESTRATION_ROUTING_LOGIC_CONTRACT.md`), per this project's
own standing rules. **Not a new orchestrator, AI Core, or planning
logic** -- every change extends an already-shipped M10/M5A/M0-M6
component.

### Added
- **Intent gating** (`agents/graph.py`) -- one new conditional edge,
  `intent_classifier → {context_engine | responder}`, consuming the
  already-computed `state["intent"]`/`state["intent_confidence"]`. A
  high-confidence `direct_answer` skips context/planning/tool-selection
  entirely; everything else takes the existing, unchanged path.
  Threshold is `AgentSettings.intent_direct_route_confidence` (default
  `0.85`).
- **`AgentSettings.conversation_routing`** -- new
  `Literal["legacy", "hybrid", "orchestrator"]` flag, default
  `"legacy"` (today's behaviour, byte-for-byte unchanged). Read in
  exactly one place: `ConversationController.__init__`.
- **`ConversationController`** (`features/conversation/controller.py`)
  -- gained a settings-driven branch between `ChatService.stream()`
  (existing) and a new `AgentOrchestrator.stream()` path. The
  orchestrator path persists through `ConversationService` itself
  (which `AgentOrchestrator` has no dependency on) and reuses the
  conversation id as the agent's `thread_id`. Fails at construction,
  not first use, if `conversation_routing="orchestrator"` has no
  orchestrator provided.
- **`ui/main_window.py`** -- one call site updated to pass `settings`
  and the existing `container.agent_orchestrator()` singleton to
  `ConversationController`. Voice needed no wiring change -- it
  already fed into the same `send()` this re-routes.
- **`docs/ORCHESTRATION_ROUTING_LOGIC_CONTRACT.md`** -- the Logic
  Contract, written before implementation per this project's own rule.
- **22 new tests** -- `test_agent_graph_routing.py` (8, the routing
  function in isolation), 4 new cases in
  `test_agent_orchestrator.py` (direct-route bypass verified via
  `ScriptedFakeLLM.calls` never reaching the planner, confidence
  thresholding, `tool_use` never gating, real token streaming on the
  direct-routed path), `test_conversation_controller.py` (10:
  legacy/orchestrator/hybrid routing, persisted-message parity with
  the legacy path, thread-id reuse, construction-time validation, no
  silent fallback on orchestrator failure) -- real temp-file SQLite
  throughout, no mocked repository.

### Notes
- **`ChatService`/`ConversationService`/`VoiceService` (M0-M6,
  frozen) are unmodified.** `AgentOrchestrator`'s own public
  `invoke()`/`stream()` contract is unchanged; only its internal graph
  gained the new conditional edge.
- Full backend regression: **2499 passed, 1 skipped (pre-existing), 0
  failed** (2500 collected). Frontend unaffected -- zero frontend
  files touched.
- Default (`conversation_routing="legacy"`) preserves pre-existing
  behaviour byte-for-byte; `"orchestrator"`/`"hybrid"` are opt-in.

## M12 Task Group B, Phase 3: MQTT Connector

**No version bump**, matching Task Group A and Phases 1-2's own
precedent; `0.38.0` is unchanged.

Phase 2 shipped the first real `IDeviceConnector` (Home Assistant, REST
over `httpx`). Phase 3, approved the same day on direct, separate
instruction preceded by its own 17-point read-only architectural
audit, builds the second: an MQTT connector, closing this task group's
three-phase implementation plan.

### Added
- **Library selection, corrected during implementation** — the audit's
  originally-preferred `aiomqtt` (wraps `paho-mqtt`) was replaced with
  `gmqtt` after connecting each against a real local broker found
  `aiomqtt` raises `NotImplementedError` on Windows' default
  `ProactorEventLoop` (needs `loop.add_reader`/`add_writer`, which only
  `SelectorEventLoop` implements on Windows -- and `SelectorEventLoop`
  cannot run this project's existing subprocess-based MCP
  `StdioTransport`). `gmqtt` connected cleanly on the same loop with no
  workaround. `requirements.txt`/`requirements-lock.txt`/`pyproject.toml`
  updated to `gmqtt>=0.7,<1.0`, zero `aiomqtt`/`paho-mqtt` remnants.
- **JARVIS-native message envelope** (`core/connectivity/connectors/
  mqtt_envelope.py`) -- the canonical protocol for future JARVIS-native
  devices (ESP32 and similar): one JSON shape (`schema_version`,
  `device_id`, `type`, `timestamp`, `payload`) covering state/command/
  discovery/availability/error, with explicit schema versioning.
- **`MqttConnector`** (`core/connectivity/connectors/mqtt.py`) -- the
  second real `IDeviceConnector`. Speaks Home Assistant MQTT Discovery
  (interoperating with Zigbee2MQTT/zwave-js-to-mqtt/Tasmota/ESPHome
  with no dedicated connector for any of them) and the JARVIS-native
  envelope. State is push-based and cached, not pulled. Commands
  publish at QoS 1, never retained. Reconnection is `gmqtt`'s own
  automatic retry paired with unconditional resubscription on every
  `on_connect`.
- **`build_mqtt_connector`** (`core/connectivity/connectors/factory.py`)
  -- registered into `build_default_connector_registry()` alongside
  Home Assistant. Both `CONNECTOR_TYPES` entries are now registered.
- **`tests/fakes/fake_mqtt_broker.py`** -- a real, hand-written,
  in-process MQTT 3.1.1 broker (no stdlib broker exists to reuse,
  unlike Phases 1-2's `http.server`/`websockets`), supporting
  CONNECT/CONNACK auth, SUBSCRIBE/UNSUBSCRIBE with wildcards, PUBLISH
  at QoS 0/1 with PUBACK, retained-message replay, and Last Will and
  Testament.
- **68 new tests** -- envelope round-trip/validation (26), connector
  coverage across connect/disconnect, auth, TLS config, HA + native
  discovery, state cache, availability, retained-message handling, QoS,
  commands, and automatic reconnect-with-resubscription (42), plus MQTT
  factory tests -- all against the real fake broker, no mocked `gmqtt`
  client.

### Notes
- **`CONNECTOR_TYPES` fully realized.** `home_assistant` and `mqtt` are
  both registered; Task Group B's three-phase plan is closed.
- Full backend regression: **2477 passed, 1 skipped (pre-existing), 0
  failed.** Full frontend: **750/750**, plus a clean `tsc`/`oxlint`.
- **M12 is still 🟡 Active, not Complete** -- Smart Home Core and
  Connectivity Layer are two modules of fifteen; thirteen remain
  entirely unstarted.

## M12 Task Group B, Phase 2: Home Assistant Connector

**No version bump**, matching Task Group A and Phase 1's own
precedent; `0.38.0` is unchanged.

Phase 1 shipped the port/adapter foundation with no protocol code
behind it. Phase 2, approved the same day on direct, separate
instruction per Phase 1's own recommendation, builds the first real
`IDeviceConnector`: a Home Assistant connector speaking REST over
`httpx`.

### Added
- **`HomeAssistantConnector`** (`core/connectivity/connectors/
  home_assistant.py`) — `connect()`/`disconnect()` manage a pooled
  `httpx.AsyncClient` with a real reachability probe (`GET /api/`),
  the same "fail at connect, not at first use" discipline
  `HttpTransport` established for MCP. `discover()` lists
  `/api/states` and maps each entity onto a `DiscoveredDevice` through
  a closed allowlist of eighteen physical-device domains (onto Task
  Group A's own `DEVICE_TYPES`); a domain outside the allowlist
  (`automation`, `script`, `scene`, `zone`, `person`, ...) is skipped,
  never registered as a device. `read_state()` reads
  `/api/states/{entity_id}`. `send_command()` posts to
  `/api/services/{domain}/{service}`, reporting a device-level
  rejection as `CommandResult.success=False` rather than raising.
- **`core/connectivity/connectors/factory.py`** — `build_home_assistant_
  connector` (validates `base_url`/`token` at construction) and
  `build_default_connector_registry()`, mirroring
  `build_default_transport_registry()`. Registers `home_assistant`
  only; `mqtt` stays unregistered.
- **DI wiring** — `_build_connectivity_registry` now calls
  `build_default_connector_registry()` instead of constructing an
  empty registry directly.
- **26 new tests** — `test_home_assistant_connector.py` against a real
  local `http.server.HTTPServer` (no mocked `httpx` client, matching
  `test_mcp_transports_live.py`'s own convention for MCP's network
  transports) and `test_connectivity_connector_factory.py` for the
  factory/registration surface.

### Notes
- **Still no MQTT code.** `CONNECTOR_TYPES` continues to name `mqtt`;
  Phase 3 (MQTT) remains a separate, later, individually-approved
  pass.
- **No frontend or event changes.** Phase 1 wired
  `ConnectivityStatusChangedEvent` into the WebSocket relay; this phase
  reuses it unchanged and adds no REST route — `ConnectivityService`
  still has no HTTP caller, by design (a later M12 module's job).
- **M12 is still 🟡 Active, not Complete** — Connectivity Layer now has
  one of its two approved protocol adapters; thirteen of fifteen
  modules remain entirely unstarted.

## M12 Task Group B, Phase 1: Connectivity Layer Foundation

**No version bump**, matching Task Group A's own precedent; `0.38.0`
is unchanged.

An approved five-step plan (audit, connectivity-technology analysis,
architecture design, phased plan, risk analysis — no code) broke this
task group into three separately-approved phases. Phase 1 builds the
port/adapter foundation every later phase plugs into; it talks to no
real device and ships no protocol adapter.

### Added
- **`IDeviceConnector` port** (`core/interfaces/connectivity.py`) plus
  `DiscoveredDevice`/`DeviceState`/`CommandResult` value objects —
  mirrors `IMCPTransport`'s own shape. `CONNECTOR_TYPES` deliberately
  narrow: `home_assistant`, `mqtt` — only this task group's approved
  scope, not the milestone's full connectivity vocabulary.
- **`ConnectorFactoryRegistry`** (`core/connectivity/registry.py`) —
  mirrors `TransportFactoryRegistry`; empty of real connectors.
- **`ConnectorCredentialStore`** (`core/connectivity/credential_store.py`)
  — Fernet-encrypted-at-rest, refuses to persist without a real key. A
  structural sibling of MCP's own `CredentialStore`, not a shared
  instance.
- **`ConnectivityService`** (`services/connectivity_service.py`) —
  idempotent connect/disconnect, discovery idempotent by home +
  external id, state refresh mapped onto Task Group A's closed device
  statuses, and `send_command` — the single chokepoint a later M12
  module will gate safety-critical devices against.
- **`SmartHomeService` extensions** — `register_discovered_device`
  gained a `metadata` kwarg (written to the existing
  `Device.metadata_json` column, no schema change),
  `get_device_by_external_id`, `report_device_state`.
- **DI wiring** — `connectivity_registry`, `connectivity_credential_
  store`, `connectivity_service` singletons.
- **`ConnectivityStatusChangedEvent`** — new WebSocket relay event,
  wired into `runtime_ws_hub.py`, the generated contract, frontend
  `RELAYED_EVENTS`, and both pinned relay-vocabulary tests in the same
  change.
- **107 new/affected tests** — `FakeDeviceConnector` plus three new
  suites (registry, credential store, service) and extended
  `SmartHomeService` coverage, all against real (temp-file) SQLite or
  real file-backed credential storage.

### Notes
- **No protocol code.** `CONNECTOR_TYPES` names `home_assistant` and
  `mqtt`; neither has an implementation. Phase 2 (Home Assistant) and
  Phase 3 (MQTT) are separate, later, individually-approved passes.
- Full backend regression: **2379 passed, 1 skipped (pre-existing), 0
  failed.** Full frontend: **750/750**, plus a clean `tsc`/`oxlint`/
  production build.
- **M12 is still 🟡 Active, not Complete** — Smart Home Core and
  Connectivity Layer's own foundation are two modules of fifteen;
  thirteen remain entirely unstarted.

## M12 Task Group A: Smart Home Core

**No version bump, by explicit instruction.** Unlike M22's own task
groups (each of which bumped the version for its own shipped code),
this one did not; `0.38.0` is unchanged. An earlier draft of this
entry briefly described a `0.39.0` bump that was reverted before
commit — this entry describes what actually shipped, at the real,
unchanged version.

A roadmap audit (`MASTER_ROADMAP.md`, `IMPLEMENTATION_ROADMAP.md`)
found M12 — Smart Home & IoT Platform is the next milestone actually
marked Not Started in the M9→M21 resumption order: M10 is Partial and
M11 is Active (Task Groups A–F shipped, not closed), so neither
qualifies even though both precede M12 numerically. Started while M22
remains open — a second deliberate exception to "one active milestone
at a time," on direct instruction.

### Added
- **Smart Home domain** (`domain/smart_home/models.py`) — closed
  vocabularies for home status, device status and device type, plus
  derived `HomeMetadata` (never stored, computed on read).
- **Five ORM models** (`infrastructure/database/models.py`) — `Home`
  → `Zone` → `Room` → `Device`, plus `DeviceGroup` /
  `DeviceGroupMember` as a cross-cutting grouping independent of that
  hierarchy.
- **`SmartHomeService`** — lifecycle CRUD for all five entities,
  derived home metadata (Device Health Monitoring / Status Dashboard),
  event publishing, search hooks. Device Discovery and Pairing are
  modeled as domain status transitions
  (`register_discovered_device` / `pair_device`) — neither talks to
  real hardware; no Connectivity Layer exists yet.
- **REST** — `/api/v1/homes`, `/api/v1/devices`,
  `/api/v1/smart-home/{zones,rooms,device-groups}`, plus
  `/homes/{id}/metadata`, device-group membership routes, and
  `POST /devices/{id}/pair`.
- **Two new search sources** (`homes`, `devices`) registered on M10A's
  existing provider registry.
- **Two new WebSocket relay events** (`home.updated`,
  `device.updated`), wired into `runtime_ws_hub.py`'s relay mapping
  and both sides of the WebSocket contract (backend
  `event-contract.generated.json` regenerated; frontend
  `RELAYED_EVENTS` updated to match).
- **89 tests** across service, repository, REST and contract-
  consistency layers, all against real (temp-file) SQLite — no mocked
  repository.

### Fixed
- Two pinned search-source-vocabulary tests
  (`test_platform_integration.py`, `test_knowledge_route.py`) and two
  pinned relay-vocabulary tests (`test_platform_integration.py`,
  `test_runtime_ws_hub.py`) hadn't been extended for the new sources
  and events — found by actually running the full suite, not assumed.
- `IMPLEMENTATION_ROADMAP.md`'s top-level milestone status table
  incorrectly read "M11 onward: Planned, not started," contradicting
  its own §5G section. M11 is Active (backend shipped across six task
  groups; not closed — the React/Tauri UI half waits on M8).

### Notes
- **Scope boundary, drawn the same way M11 Task Group B drew one
  around `Reminder`:** this task group builds the domain layer only.
  No real device talks to it. Fourteen of M12's fifteen modules
  (starting with Connectivity Layer, which real discovery/pairing
  depends on) are separate, later task groups.
- M10 and M11's own open status is reported, not resolved, by this
  entry — see `MILESTONE_REPORT.md`'s M12 Task Group A entry for the
  full roadmap audit.
- **M12 is now 🟡 Active, not Complete** — Task Group A is one module
  of fifteen; fourteen remain unstarted.

## M22 Task Group F: Final Build Verification, Cross-Platform Readiness & Release Validation

**No version bump.** Consistent with this project's own precedent
(the governance documentation pass, `11a8f6f`): a verification and
documentation pass with no shipped application change does not bump
the version. Version remains `0.38.0`.

**Status: Implementation Complete — Build Verification Pending**, for
the same reason 0.36.0 through 0.38.0 carry it: no Rust toolchain
exists on this build machine, so nothing gated on a real `tauri build`
has been proven. What this pass adds is everything that *doesn't* need
one, run for real rather than assumed.

### Verified for real (no Rust toolchain required)
- **Fresh installation, resume, and existing-installation detection**
  — `python -m jarvis.installer provision` run against a real scratch
  directory: genuinely created the directory tree, wrote a real
  config file, completed three real steps, then failed at
  `model_download` exactly as expected (this environment's download
  source registry ships empty by design). Re-running the same command
  correctly skipped the three completed steps rather than redoing
  them.
- **Interrupted installation recovery** — the provisioning journal was
  deliberately truncated mid-write to simulate a crash. Confirmed
  correct, intentional behavior (`journal.py`'s own documented
  design: an unreadable journal is treated as absent, and every step
  is idempotent, so starting over is safe) rather than a defect.
- **Repair and verification workflows, together** — a real
  installation's config file was deleted; `verify` correctly reported
  it failed and repairable; `repair configuration` recreated it; a
  second `verify` immediately confirmed the fix, re-verifying after
  acting rather than trusting its own result.
- **Dependency verification** — ran against this machine's real,
  live-probed state (Python, Git, DirectML, CUDA), not a fixture.

### Fixed
- **`docs/PACKAGING.md`'s icon paragraph and Build Verification Task 5
  were stale**, still describing Task Group E's branding work as
  unstarted after Task Group E had shipped it — a documentation
  regression from that file being outside Task Group E's own
  documentation sync list. Corrected to describe the real, current
  two-variant/hybrid-ICO state.

### Added
- **`docs/PACKAGING.md` "Cross-platform readiness" section** — an
  evidence-based audit of every Windows-specific assumption in the
  codebase (found by reading every `#[cfg(windows)]`, `wmic` call and
  hardcoded path, not by guessing) and a concrete migration checklist
  for a future Linux/macOS task group. Nothing in it was implemented —
  this task group's own brief was explicit that it audits and
  documents, and does not build Linux or macOS support.
- **Two new Build Verification Tasks** (now twelve total, in
  `docs/PACKAGING.md`): watching the startup animation actually run in
  a real compositing browser (still not possible in this session's
  sandboxed preview pane), and generating and committing
  `frontend/src-tauri/Cargo.lock`, which does not exist yet because
  `cargo` has never run against this repository.

### Notes
- **M22 cannot be marked Complete.** Per `MASTER_ROADMAP.md` §18, all
  of TG-C, TG-D, TG-E and TG-F must reach Build Verification Passed —
  none of the twelve Build Verification Tasks is checked. This is the
  same blocker TG-C's own first report named, now confirmed to still
  be the single blocking factor across four task groups at once.
- Full audit findings, the complete real-CLI verification evidence,
  and the itemized remaining-risk list are in `MILESTONE_REPORT.md`'s
  Task Group F entry.

## [0.38.0] — M22 Task Group E: Windows Packaging & Installer Distribution

**Status: Implementation Complete — Build Verification Pending**, for
the same reason 0.36.0 and 0.37.0 carry that status: no Rust toolchain
exists on the build machine, so nothing new in `src-tauri/` has been
compiled.

An audit before implementation found most of this task group's
nineteen-item brief already built by Task Groups A–D: NSIS
configuration, installer/uninstaller/Add-Remove-Programs registration,
version metadata, installation logging, launch-after-install, and
open-installation-folder are all real, shipped capability, not new
work. What was genuinely missing was the application's actual branding
— every icon in the repository was still Tauri's own placeholder logo
— and that gap became directly actionable mid-task-group when the
user supplied and approved the official JARVIS master logo.

### Added
- **The approved master logo**, integrated as the project's brand
  identity: `frontend/src-tauri/icons/master-logo.png` (the source of
  truth), a full production icon set (16 through 1024px PNG, `.ico`,
  `.icns`), and `frontend/public/branding/premium/` for future in-app
  use (About, Settings, notifications — none of which exist yet in
  this codebase; nothing was invented to house them early).
- **A second, simplified icon variant**, hand-authored specifically
  for the sizes where the master's metallic gradients stop reading —
  confirmed empirically: the master rasterized to plain 32×32 renders
  as a near-illegible dark blur. `frontend/src-tauri/icons/small-icon-
  source.svg` is a bold, high-contrast reinterpretation of the same
  ring-and-blade silhouette, used for 16–48px contexts (taskbar, system
  tray, Explorer, window title bar) and `frontend/public/branding/
  small-icon/`.
- **A hybrid multi-resolution `icon.ico`**, built by a small
  hand-written PNG-in-ICO packer (no Pillow/ImageMagick available):
  small frames (16/24/32/48) from the simplified variant, large frames
  (128/256) from the master, so the one file Windows actually reads is
  legible at every size it gets asked to render, not just the large
  ones.
- **The startup animation's logo recreated as SVG** (`components/
  startup/jarvis-logo.tsx`), replacing the earlier hexagon placeholder
  with the approved logo's own geometry, animated with Framer Motion
  across the existing `assembling`/`pulsing` phases — ring channels
  drawing, the outer ring fading in, the center blade rising, the side
  blades sliding up, a glow igniting, a pulse travelling outward, one
  soft breathing cycle. Every animated property is opacity, a
  transform translate/scale, or SVG `pathLength` — never a
  layout-triggering property — so this composites on the GPU without
  forcing layout.
- **The browser-tab favicon replaced** (`public/favicon.svg`) — was an
  unrelated purple abstract mark (a Vite/template-era placeholder, not
  even the same shape family as the hexagon logo elsewhere), found only
  by checking `index.html` directly rather than assuming the favicon
  was already covered by the icon work.
- **`packaging/verify_tauri_build.ps1`**, a new build-verification
  script that turns part of Task Group C's manual Build Verification
  Tasks list into mechanical pass/fail checks: the installer artifact
  exists, its version metadata matches this project's single source of
  truth, its product/publisher fields are real, and the shipped icon is
  provably not Tauri's placeholder. Run for real against this
  project's current (unbuilt) state — correctly reports the one
  failure that should exist (no installer yet) and passes every check
  that does not depend on a build existing.
- **11 new packaging/branding contract tests** plus a rewritten
  `jarvis-logo.tsx` test suite (7 tests, up from 4) — 750 tests total
  in the frontend suite, up from 736.

### Fixed
- **A verification heuristic that broke on its own first real input.**
  The build-verification script's original icon check asserted "small
  enough to be the real icon" against an early placeholder; Task Group
  E's actual hybrid `.ico` is a multi-resolution file that ended up
  *larger* than the Tauri placeholder it replaced, not smaller,
  immediately failing that heuristic against genuinely correct output.
  Replaced with a negative match against the placeholder's own known,
  fixed byte size — a check that does not need updating every time this
  project's real artwork does.
- **A double hyphen inside an SVG comment**, twice, while authoring
  `small-icon-source.svg` — XML forbids `--` inside comment text and
  Tauri's icon generator enforces it strictly, panicking with a parse
  error rather than a readable message. Found by actually running the
  generator against the file before treating it as done, not by
  inspecting the SVG source and assuming it would parse.
- **A compounding double-opacity animation** in `jarvis-logo.tsx`'s
  first draft — a parent group and its child paths each independently
  animated `opacity` toward 1, which compose multiplicatively rather
  than additively, producing a slower, muddier fade than either
  animation alone intended. Found on review, not by observation (see
  Notes); fixed by leaving opacity solely to the paths that actually
  need it and letting the group own only the shared translate.

### Notes
- **Roadmap scope, resolved further.** Prior documentation described
  "Task Groups E–F" as an undivided Linux/macOS-packaging-and-QA block
  with the letter split undecided. Task Group E is now resolved
  specifically to Windows Packaging & Installer Distribution; that
  packaging/QA scope moves entirely to Task Group F, which absorbs
  what would have been split between the two.
- **Live browser animation verification was not possible in this
  session's environment.** The sandboxed Browser pane used for
  UI verification does not composite frames at all —
  `requestAnimationFrame` was confirmed, directly, to never fire in
  that tab — which explains why `computer.screenshot` also failed
  independent of timing. This is a property of that specific pane, not
  evidence the animation code is broken: Framer Motion's engine is
  itself driven by `requestAnimationFrame`, so nothing animated in that
  session regardless of which component was involved. What *was*
  verified without a working compositor: correct DOM/SVG structure,
  Framer Motion correctly initializing every element's `initial` state
  (including SVG-specific `transform-box`/`transform-origin` handling),
  zero console errors across several real mounts, and a careful manual
  review that found and fixed the compounding-opacity bug above. See
  `MILESTONE_REPORT.md`'s Task Group E entry for the full account.
- **Two deviations from what a strict reading of "Windows Packaging &
  Installer Distribution" would cover**, both directly instructed:
  integrating branding into the startup animation and favicon reaches
  slightly beyond "installer distribution" into general app branding;
  and file associations were evaluated and found not applicable — this
  project has no custom file format — documented as N/A rather than
  invented to fill a checklist item.

## [0.37.0] — M22 Task Group D: Universal Installation Experience

**Status: Implementation Complete — Build Verification Pending**, for
the same reason 0.36.0 carries that status: this task group adds five
commands to `src-tauri/src/installer.rs`, and there is still no Rust
toolchain on the build machine to compile them. One `tauri build`
proves both this task group's Rust and Task Group C's.

TG-D's brief listed fifteen items. The audit that preceded this release
found ten of them already real, shipped by Task Groups A–C and this
milestone's own installer UI pass: the progress framework, the download
manager UI, byte-level resume, retry-via-journal, seven-category
failure classification, and a completion screen. What was missing was
narrower — the backend already had a nine-check post-install verifier,
a `repair()` engine method, and a `status`/`verify`/`dependencies` CLI
surface, none of it wired to the frontend. This release is that wiring.

### Added
- **Five Rust bridge commands** (`check_dependencies`,
  `get_installation_status`, `verify_installation`,
  `repair_installation`, `open_log_folder`), additive to Task Group C's
  surface the same way `cancel_provisioning` was — the documented
  four-command contract is a floor, not a ceiling. Each wraps an
  **already-shipped, unmodified** CLI subcommand; zero Python files
  changed.
- **Component verification, on screen.** The completion step now shows
  all nine post-install checks, not only their warnings, each with a
  Repair button when the underlying failure is repairable.
- **Repair**, wired end to end: a click invalidates and re-runs the
  named step through the engine's own `repair()`, then **re-verifies**
  rather than trusting the repair's own result — a repair can complete
  having failed a *later* step (a blocked download) without the
  originally-failed check ever running again.
- **Installer diagnostics.** A dialog, reachable from any step, showing
  whether an installation already exists at the chosen location, its
  journal progress, a dependency report (Python, Git, CUDA, DirectML,
  ONNX Runtime, Visual C++), and the same verification-with-repair view
  the completion screen uses — reused, not duplicated.
- **Update preparation.** The wizard now detects an existing or
  partially-completed installation automatically, as soon as a location
  is chosen, and says so — "An installation already exists at this
  location. Continuing will update it — anything already set up is
  kept."
- **`open_log_folder`**, revealing the log directory Task Group C's
  logger has written to, unreachable by any UI, since v0.36.0.
- **57 new tests** (190 total in the installer suite, up from 129),
  including 13 new Rust/TypeScript contract checks and a dependency
  contract test mirroring the existing plan-payload one.

### Fixed
- **A real inconsistency, found by testing against a genuine
  partially-completed status fixture rather than only a fresh one.**
  The proactive wizard-wide notice and the diagnostics dialog's own
  "Existing installation" field checked different things — one looked
  at manifest-or-journal-progress, the other at manifest alone — so an
  interrupted install read as "found" on one screen and "none found" on
  the other for the same location. Both now call one shared
  `installationPresence()` classification (`none` / `partial` /
  `complete`).

### Notes
- **Roadmap scope, made explicit.** Prior documentation described
  "Task Groups D–F" as an undivided block of Linux/macOS packaging and
  cross-platform QA. This release resolves TG-D specifically to
  Universal Installation Experience; that packaging and QA scope is not
  dropped — it moves to Task Groups E/F, whose own letter-to-content
  assignment remains open. See `MASTER_ROADMAP.md` §19 (Roadmap
  Governance) for why this is a documented decision, not a silent
  redefinition.
- **What repair cannot yet show:** the CLI's `repair` subcommand has no
  `--stream` flag, and adding one means editing Task Group B's
  `__main__.py`, which this task group's brief reserves for a genuine
  defect. A repair that re-downloads a large artefact therefore blocks
  with an honest, indeterminate "Repairing…" state, not a percentage
  this bridge cannot produce.
- **Not verified**, same gate as v0.36.0: no `cargo build`, no
  `tauri build`, nothing in `src-tauri/` compiled. See
  `MILESTONE_REPORT.md`'s Task Group D entry for what is and is not
  proven without a toolchain.

## [0.36.0] — M22 Task Group C: Windows Packaging & Host Bridge

**Status: Implementation Complete — Build Verification Pending.**

Implements the host side of the transport contract v0.35.0 defined, and
configures the Windows installer. **Not one payload, command name or
event name changed** — the contract was written first so the UI would
need no edit on the day the host landed, and it needed none.

There is no Rust toolchain on the build machine, so nothing in
`src-tauri/` has been compiled, no `tauri build` has run, and no
installer has been produced. Ten Build Verification Tasks — build the
installer, confirm it builds, confirm the desktop and Start Menu
shortcuts, replace Tauri's default logo with real JARVIS branding
(unstarted, not just unverified), confirm installer metadata, the
uninstall entry, Launch JARVIS, Open Installation Folder, and the
provisioning bridge inside the packaged app — gate this task group to
Complete; none has run. See Notes and `MILESTONE_REPORT.md` §9
for the full list.

### Added
- **`src-tauri/src/installer.rs`** — the Windows host bridge. Spawns
  `python -m jarvis.installer`, relays stdout, captures stderr, and
  implements the four contract commands: `run_provisioning`,
  `load_installation_plan`, `launch_application`,
  `open_installation_folder`.
- **`cancel_provisioning`**, additive to the contract, plus the Cancel
  control that calls it. The UI has modelled a cancelled run since
  v0.35.0 — classifier, label, icon — with nothing able to trigger it;
  Task Group C's scope names cancellation, so the state is now
  reachable instead of decorative.
- **Interpreter discovery** — `JARVIS_PYTHON`, then a runtime bundled
  beside the executable, then the project virtual environment, then
  `PATH`. Returns "Python unavailable" rather than failing later with an
  opaque spawn error.
- **Windows packaging configuration** — NSIS target, per-user install
  (no elevation), publisher, copyright, descriptions, icons.
- **Unconditional structured logging** to the platform log directory,
  not debug-only: an installer failing on a user's machine is where a
  log is worth most, and that machine runs a release build.
- **A Rust/TypeScript contract suite** (13 tests) pinning command names,
  argument arity and the event name. It reads the Rust as *text*, so it
  needs no toolchain and runs in the ordinary `vitest` pass.
- **`tauri.conf.json` is now version-checked** against `__version__`.
  This is the first milestone producing a packaged artifact, so it is
  the first where that file's version is something a user reads — in
  Add/Remove Programs, while `/api/v1/health` reports the other one.

### Fixed
- **An inactivity timeout that could not fire.** It was checked *after*
  reading a line from stdout, so a process that hung producing no output
  — precisely the case it exists for — blocked forever in the read and
  never reached the check. stdout now feeds a channel and the loop waits
  with a timeout, which also makes cancellation prompt rather than
  dependent on the child saying something first.
- **A process that outlived the installer.** Rust's `Child` detaches on
  drop rather than killing, so closing the window mid-run left Python
  downloading gigabytes with no window and no way to stop it.
- **`launch_application` took an argument no caller sends.** Written as
  `(location: String)` while the frontend invokes it with none — a clean
  compile on both sides and a guaranteed runtime failure the first time
  a user pressed the button on the completion screen. The host now
  remembers where it installed, which keeps the documented no-argument
  contract intact. Found by the new contract suite.
- **Cancelling reported "the installer process disappeared."** The
  cancel path clears the child handle, and the exit-status branch ran
  first, so an ordinary cancel surfaced as an error — and missed the
  word "cancel" that the failure classifier matches on.

### Notes
- **`@tauri-apps/plugin-shell` was not added, and planning to add it was
  the error.** A `#[tauri::command]` spawning `std::process::Command`
  needs no plugin. The shell plugin exists to let *JavaScript* spawn
  processes — a strictly larger capability than this needs, on the
  surface with the largest attack area. The roadmap line item is closed
  by deciding against it.
- **What is unproven.** No compilation, no `tauri build`, no installer,
  no shortcut or icon observed, and the desktop/Start Menu shortcuts are
  left to Tauri's default NSIS template rather than forced through an
  untested `.nsh` hook. What *is* checked without a toolchain: both JSON
  configs parse, every referenced icon exists, the NSIS keys used are
  real keys in the bundled `config.schema.json`, and the contract suite
  above. `MILESTONE_REPORT.md` carries the full split.
- **The application icon is still Tauri's default logo**, not JARVIS
  branding — found by opening the PNG, not by checking the files exist.
  This is unstarted work, not a verification gap: it needs real artwork
  before it can even be checked.
- **Ten Build Verification Tasks gate this task group to Fully
  Complete**, none run: build the installer; confirm it builds; confirm
  the desktop shortcut; confirm the Start Menu shortcut; replace Tauri's
  branding with JARVIS's; confirm installer metadata; confirm the
  uninstall entry; confirm Launch JARVIS; confirm Open Installation
  Folder; confirm the provisioning bridge inside the packaged app. See
  `MILESTONE_REPORT.md` §9. Task Group D does not begin until all ten
  pass and that is explicitly approved.

## [0.35.0] — M22: Installer UI & Provisioning Integration

Connects the installer wizard to the provisioning engine. The engine
itself is unchanged: pytest, black, ruff and mypy are identical to
0.34.0, and TG-B's 30 engine tests pass untouched.

### Added
- **Provisioning event stream.** `provision --stream` emits
  newline-delimited JSON — one `progress` event per engine callback, then
  a final `result`. Without the flag the output is byte-identical to
  0.34.0. The brief asked the UI to "support the provisioning events
  already emitted by the backend"; those events existed only as a Python
  callback, so a UI could not show live progress for a multi-gigabyte
  download from a value it received once the download was over.
- **`DownloadState.VERIFYING`**, emitted around the checksum pass.
  Checksumming a large file takes long enough that leaving the state on
  "running" reads as a hang.
- **`kind` on `DownloadProgress`**, so the UI can group Models and Voices
  without inspecting an id it is not permitted to display.
- **Installation screen** — phase in the backend's own §22.12 wording,
  overall progress, steps, bytes, speed, time remaining, and a per-item
  download list with all seven states (waiting, downloading, checking,
  ready, already installed, failed, cancelled), each carried by text
  *and* an accessible label rather than by colour.
- **Resume, failure and completion screens.** Failures map the engine's
  own error text onto the seven required categories and show copy that
  names no internal cause — "Connection lost", never "URLError". Retry
  is worded "Continue installation" because the journal makes it a
  resume.
- **`/install` route.** TG-A and TG-B left the wizard mounted nowhere.
  It sits *outside* `DesktopShell`: rendering an installer inside the
  sidebar and header of the application it is installing is incoherent
  and invites navigating away mid-run.
- **Host-bridge contract** (`provisioning-transport.ts`) — see Notes.

### Fixed
- **A React render loop.** `selectDownloadsByKind` built a new object per
  call, and zustand compares selector results by reference, so using it
  as a hook selector made every render look like a state change until
  React aborted with "Maximum update depth exceeded". Grouping is now a
  `useMemo` over the stable array.
- **`defaultLocation` defaulted to `""`**, permanently disabling
  Continue on the Location step with no explanation. The route now
  proposes `%LOCALAPPDATA%\JARVIS` (or `~/.jarvis`), and the step says
  "Enter a folder to continue" while the field is blank.
- **A group headed "Local AI" containing an item also called "Local
  AI"** — groups renamed to Models / Voices / Assets.

### Notes
- **Speed and time remaining are derived in the UI, not emitted by the
  engine.** A rate is a property of an observer over an interval, not a
  fact about a download; a stopwatch in the engine would report
  different numbers to two consumers. They are derived from the
  authoritative byte counts, smoothed over 3s, and are `null` rather
  than `0` until there is signal — "0 B/s" reads as stalled where "—"
  reads as not yet known.
- **The host bridge is intentionally deferred to Task Group C.**
  `@tauri-apps/plugin-shell` is not a dependency and no Rust command
  exists to spawn the Python process. Rather than adding a dependency to
  make a screen look finished, the transport *defines the contract* — one
  command (`run_provisioning`), one event (`provisioning://event`) — and
  rejects with a readable reason when the host cannot provide it, which
  the failure classifier turns into friendly copy with a Retry. A stub
  that resolved quietly, or emitted invented progress, would make the
  installer look complete while installing nothing.
- **81 tests added**, including a contract suite driven by a *captured
  real stream* rather than a hand-written approximation, and assertions
  that no model id, registry key or URL reaches a personal payload.

## [0.34.0] — M22 Task Group B: Runtime Provisioning

Task Group A planned an installation; this performs one. Dependency
detection, a resumable checksum-verified download manager, a durable
provisioning journal, parallel verification, first-run preparation and an
`installation.json` manifest — behind one engine that is simultaneously
install, resume and repair.

The success path runs end to end: a real provisioning against a `file://`
mirror completes all eight steps and writes a manifest; a second run
skips all eight.

**Backend untouched.** No route, model, schema, event or contract
changed; the installer package still imports no service, repository or
container.

### Added
- **`sources.py`** — download-source abstraction. **No URL exists
  anywhere in the package.** The registry ships empty: with nothing
  configured it names the environment variable to set rather than
  falling back to a vendor host, because a silent fallback would defeat
  the abstraction on the one path that matters.
- **`download.py`** — queued, **byte-level resumable** (HTTP `Range`),
  checksum-verified downloads with pause, cancel, retry and source
  failover. A file lands in `.part`, is verified there, and is renamed
  last — so a file under its final name is *by construction* one that
  passed.
- **`dependencies.py`** — Python, Git, Visual C++, CUDA, DirectML, ONNX
  Runtime. It has **no code path that writes**, which is how "never
  silently overwrite" is enforced rather than merely promised.
- **`journal.py`** — durable, fsynced, atomically-replaced provisioning
  record. Only *completions* are written, so an interrupted step is
  re-run and a finished one skipped.
- **`verification.py`** — nine checks in parallel; **`manifest.py`** —
  `installation.json` as the migration contract; **`first_run.py`**,
  **`provisioning.py`**, **`atomic.py`**.
- CLI: `dependencies`, `provision`, `verify`, `repair <step>`, `status`.

### Fixed *(all four found by running it end to end)*
- **A model id is not a filename.** `qwen2.5:14b` is a valid registry id
  and an impossible Windows filename — NTFS reads the colon as a drive
  qualifier — so every model download would have failed on the primary
  platform. `key` now addresses the source; `filename` is the sanitised
  on-disk name, and sources gained a `{filename}` placeholder because a
  `file://` mirror cannot store a file named after the raw key.
- **The same confusion, a second time:** verification looked artefacts up
  by `key` while the downloader wrote them under `filename`, reporting a
  correctly-downloaded model as missing.
- **A source spec that looked like it worked.** Commas separated both
  entries and `kinds`, so `mirror|url|model,voice|0` split into a
  model-only source plus an unparseable fragment — model downloads
  worked, voice downloads found no source. Entries are now
  semicolon-separated.
- **A §22.12 leak in the progress payload**: personal progress carried
  the model id. It now carries a display name; the id is
  administrator-only.

### Notes
- **There is no separate resume command.** `provision` skips whatever the
  journal records as complete, so resuming *is* running it again — a
  resume on its own code path would be the least-exercised and most
  often broken.
- **Unverifiable is not verified.** No upstream source is wired, so no
  checksums are published; downloads are reported as *present but
  unverifiable* rather than as verified.
- **The installer does not create the database schema.** It prepares the
  location; the application's `initialize()` creates the schema on first
  launch through the frozen code that owns it.
- **No packaging** — no MSI, EXE or code signing, per the brief.
  *(Superseded by 0.35.0: this entry originally said the wizard's Install
  step was unchanged and that wiring it required the Tauri bridge. The
  wiring shipped in 0.35.0 without that bridge — the UI reaches the
  engine through an injected transport, and only the transport's host
  implementation waits on packaging.)*
- Ruff rose to 33 categories on the new code and was brought back to the
  21-category baseline — `StrEnum`, an `Error` suffix, a named opener,
  `ClassVar` annotations, and a shared `atomic.py` that removed two
  `SIM115` violations by removing the duplication behind them.

## [0.33.0] — M22 Task Group A: Universal Installer Foundation

The installer experience and the hardware calibration that drives it.
Eleven-step wizard, real hardware detection, an AI Capability Score, a
local-model recommendation, a voice plan and seven pre-installation
checks — verified against this machine's actual hardware.

**Backend untouched.** The installer is a new, isolated package that
imports no service, no repository and no container. It has to be: it
runs *before* JARVIS is installed, on a machine where none of those
exist yet. No route, model, schema or contract changed.

### Added
- **`src/jarvis/installer/`** — hardware detection (CPU, RAM, storage,
  GPU/VRAM, battery, temperature, internet, NPU), AI calibration,
  model tiers, voice planning and pre-flight validation. Zero mypy
  errors across seven new modules.
- **`python -m jarvis.installer`** — a JSON-emitting CLI (`detect`,
  `plan`, `validate`). **A CLI rather than a REST route**: an installer
  cannot call an API served by the application it is installing, and
  adding a route would have modified a frozen contract.
- **`src/features/installer/`** — the eleven-step wizard, its store, and
  types pinned against real CLI output by a contract test.

### Fixed *(all three found by running on real hardware)*
- **Free space was measured on the wrong drive.** `detect_storage` fell
  back to the current working directory when the target did not exist —
  which is the *normal* case during installation. On Windows the
  installer is routinely launched from a different volume, so a machine
  with a full target drive would have passed the disk-space check.
- **A 16 GB machine could never reach the 16 GB tier.** RAM is sold in
  decimal GB: a "16 GB" machine has 16 × 10⁹ bytes = 15.7 *GiB*.
  Comparing against a binary threshold meant every 16 GB machine missed
  its tier and was offered the 8 GB one. Detection on this laptop
  returned 15.7 and recommended Small.
- **The wizard's scan effect cancelled every scan it started.**
  `beginScan()` sets `scanning`, which was an effect dependency, so
  starting a scan re-ran the effect, whose cleanup cancelled the request
  it had just started — and the guard then refused to retry. Replaced
  with a request-id ref.
- The Location step's Continue was dead unless the user retyped the path
  already shown; each account card's accessible name was ~40 words and
  ambiguous between the two options.

### Notes
- **The governing rule:** a field is either measured or `null` — never
  estimated or defaulted to something plausible. The UI renders "Not
  detected", `notes` explains why, and `missing_inputs` records what the
  recommendation did not know. On this machine three fields came back
  `null` (no temperature sensors on Windows, no probeable GPU) and the
  installer says so rather than showing zeros.
- **§22.11/§22.12 are enforced at the payload**, not in the UI: a
  personal plan genuinely does not contain model ids, score components,
  resource limits or provider names. A test asserts the serialised
  personal payload contains none of `piper`, `whisper`, `elevenlabs`,
  `llama`, `qwen`, `openai`, `gemini`, `groq` — and that it still
  carries everything that affects the user.
- **Nothing is downloaded, and no installation is performed.** The
  modules know no download URL at all. The Install step says so on
  screen rather than animating a progress bar that measures nothing;
  Test Voice and Launch JARVIS are disabled with a reason on hover.
  Windows packaging (MSI, shortcuts, auto-start, portable, signing) is
  Task Group B.

## [0.32.0] — M8 Phase 7: Production Readiness

An audit milestone, run against a **live backend** rather than by
reading code — the real FastAPI app with a real DI container and a real
health poll, driven from the React client, with the backend killed
mid-session and restarted.

That found **four defects code review had missed**. No new
functionality; no backend change beyond the version constant.

### Fixed
- **Version drift, three releases deep.** `GET /api/v1/health` reported
  `0.28.0` while `pyproject.toml` said `0.31.0` —
  `src/jarvis/__version__.py`, whose docstring calls itself "single
  source of truth for the package version", had not been bumped since
  v0.28.0. That constant is what the health endpoint returns and what
  `jarvis --version` prints, so an installation was misreporting its own
  version by three releases. Both now `0.32.0`, with
  `tests/unit/test_version_consistency.py` asserting they can never
  diverge again — nothing compared them before, which is why they drifted.
- **A dead-end user journey.** Five dashboard widgets shipped in Phase 5
  say "Bind this workspace to a JARVIS workspace to see its tasks", and
  no control anywhere could do it: `bindBackendWorkspace` had only tests
  calling it and `workspacesApi` had no caller at all. The binding
  control now exists in the workspace toolbar, wiring the store action,
  the typed endpoint and the widgets that were already built.
- **A status selector reporting a fault that did not exist.** Memory and
  Knowledge Graph showed Degraded amber on a healthy system:
  `selectSourceStatus` conflated "the collector is not reporting at all"
  with "it is reporting and this source is missing". Only the second is
  a degradation.
- **Two stories for one condition.** While offline the health widgets
  said "Waiting for the backend to report…" — implying a report was
  coming — beside REST-backed widgets correctly saying "Offline".
- **A footgun in the shared fetch hook.** `useBackendResource`'s default
  emptiness check did not understand the `Page<T>` shape most endpoints
  return, so empty collections rendered as an empty list rather than an
  empty state. Three callers had already worked around it; a fourth
  forgot. Fixed at the default and the workarounds deleted.

### Added
- **An executable guard for `ARCHITECTURE.md` §22.12.**
  `restricted-surface.test.ts` scans every source file: any module
  reading provider names, routing or debug state must also consult the
  audience gate. The behavioural tests check *existing* surfaces; this
  catches a **new** one added later that never gets a gate — precisely
  how the Phase 3 Activity Center leak survived a milestone.
  Mutation-tested: removing a gate makes it fail by filename.

### Removed
- `healthApi` (a stub documenting a decision a comment documents
  better), `useWideLayout`/`WIDE_MIN_WIDTH` (never called), and
  duplicated skeleton markup. Each verified as having zero importers.

### Notes
- **Verified live:** real health values flowing over `health.updated`;
  **no stale numbers survive a backend outage** (the pre-outage snapshot
  is dropped, not shown as current); **automatic reconnection without a
  page reload**; "connected but no snapshot yet" correctly distinguished
  from offline.
- **TanStack Query is mounted and never used** — no `useQuery` anywhere
  — costing 24.5 kB (7.28 kB gzipped) in the initial bundle. Flagged
  rather than removed: dropping an approved dependency is an
  architecture change this milestone forbids.
- **Not done, and it matters:** no cross-browser testing (Chromium
  only — the Tauri shell uses WebKit/WebView2), no screen-reader pass,
  no contrast-ratio measurement.
- **Eleven modules remain placeholders.** The brief asked to confirm "no
  placeholder routes for completed modules"; the accurate finding is
  that those modules are *not completed*, so their placeholders are
  correct rather than a regression.

## [0.31.0] — M8 Phase 5 + Phase 6: Module Integration & Production UX

Phase 5 turned the workspace into the JARVIS operating environment;
Phase 6 hardened it. Delivered as one milestone.

**Backend untouched** — no route, model, schema, event or contract
changed. pytest, black, ruff and mypy are byte-identical to v0.30.0,
which is the evidence rather than the assertion that the freeze held.

**The milestone began with an API audit, and the audit changed the
plan.** All 172 REST operations the frozen backend exposes were
enumerated before any UI was written. Three findings shaped everything
after.

### Added
- **AI Dashboard — 11 widgets, every one on real backend data**, joining
  the *existing* `dashboardWidgetRegistry`: System Overview, Subsystem
  Status, Performance, Knowledge Graph, Suggestions (M10B's real
  engine), Recent Tasks, Projects, Pinned Notes, Recent Files, Upcoming
  Calendar, Notification Summary.
- **Developer Dashboard** (Developer Mode only) — providers & routing,
  outbound API counters, API inspector, performance metrics, agent
  trace, the relay's 61-event vocabulary, runtime state.
- **Administrator Dashboard** (Administrator only) — six panels with a
  real API, plus one naming the seven that have none.
- **Plugins** and **Diagnostics** panels, joining the existing
  `panelRegistry`.
- **`core/user-mode.ts` + `stores/user-mode.store.ts`** — one audience
  gate for §22.11/§22.12: three modes, seven restricted classes of
  information. Derived from Developer Mode's existing session unlock
  rather than a second flag; two flags that can disagree about whether
  provider names may be shown will eventually disagree permissively.
- **`useBackendResource` + `ResourceView`** — one fetch hook and one set
  of honest loading / empty / offline / error states, replacing what
  would have been fifteen hand-rolled `useEffect` triples. Connection
  recovery is free at the widget level because `isLive` is a dependency.
- **Skeleton loaders** shaped like the content they replace, not a
  generic grey box that makes the layout jump.
- **`installConnectionRecovery()`** — re-runs ping → session → socket.
  The socket's own retry reuses a token that a *restarted* backend will
  refuse forever, which is the most common real outage.

### Fixed
- **A §22.12 leak shipped in M8 Phase 3.** The Activity Center rendered
  `agent.step`'s raw `node` field — `planner`, `tool_executor`,
  `critic` — to every audience. The Phase 3 milestone report flagged it
  as a gating requirement before a personal-user build ships; this is
  that gate. Personal users now see §22.12's mandated progress
  vocabulary, with step count, ordering and status identical in both
  modes — fewer *words*, not less truth.

### Notes
- **`GET /health` is a bare liveness probe** (`{status, version}`). The
  rich subsystem data every "… Status" widget needs is published as the
  `health.updated` **WebSocket** event, which nothing on the frontend
  was reading. The dashboards subscribe rather than poll — no new
  endpoint, and the numbers move on their own.
- **Seven Administrator panels have no backend and are named, not
  mocked**: users, daily/monthly budgets, provider priority, calibration
  status, analytics, synchronization. All are `ARCHITECTURE.md` §22 —
  approved and not built. An administrator seeing "Budget: $0.00" would
  reasonably conclude nothing had been spent.
- **Two AI Dashboard widgets from the brief have no data source.**
  *Recent Conversations* — no conversation-history route exists.
  *Pinned Projects* — `Project` has no `pinned` column; `Note` and
  `Workspace` do, so **Pinned Notes** ships in its place and projects
  surface by their real `status` field.
- **Provider Status moved to the Developer Dashboard.** Real data, but
  §22.12 puts provider names off-limits to personal users. That is the
  architecture decision winning over the brief's widget list,
  deliberately.
- **Six separate "… Status" widgets ship as one.** They share a data
  source and a presentation; six cards showing one light each would be
  six copies of four lines, and worse for the question a user actually
  asks.
- **Two gates, not one.** Restricted panels are filtered from the panel
  menu *and* refused by the dashboard components — a workspace layout
  can be exported from a developer's machine and imported on a personal
  one. This is a render gate, not a security boundary: the backend
  authenticates, the frontend decides what to show.
- **A correction to the Phase 3 report**, which claimed the Status Bar's
  "AI Provider" item names a provider. It does not — it renders "Not
  configured" and never leaked.

## [Unreleased] — Documentation: approved architecture decisions

Documentation only. **No application code changed** — no backend, no
frontend, no version bump. The application version stays `0.30.0`;
`MASTER_ROADMAP.md`'s own document version moves 3.0 → 3.1.

Records eighteen approved architecture decisions as the binding target
architecture, and the development freeze that accompanies them.

### Added
- **`docs/ARCHITECTURE.md` §22 — Approved architecture decisions (Aug
  2026)**, eighteen subsections covering Local AI First (§22.1), the
  Universal AI/API Calibration Engine (§22.2), the AI Cost Optimizer
  (§22.3), the three-tier AI strategy (§22.4), the Oracle Cloud role
  (§22.5), the voice platform (§22.6), AI providers (§22.7), hardware
  calibration (§22.8), the Universal Performance Engine (§22.9), the
  installation platform (§22.10), Personal/Administrator accounts
  (§22.11), hidden backend operations (§22.12), cross-agent
  collaboration (§22.13), the AI Health Dashboard (§22.14),
  cross-platform distribution (§22.15), JARVIS Core Intelligence's
  deferral (§22.16), recommended free infrastructure (§22.17), and where
  the rest gets built (§22.18).

### Changed
- **`docs/MASTER_ROADMAP.md`** — the development-policy freeze at the
  top; a note at the head of §8 Future Roadmap making §22 binding across
  every milestone; §13 AI Provider Roadmap reframed as available
  providers reached *through* the Calibration Engine rather than a
  selection menu; **Cross-Platform Distribution added to M22**, filed
  there because the OS abstraction layer is the same substrate M22's
  hardware backends need.
- **`docs/IMPLEMENTATION_ROADMAP.md`** — the same freeze, stated as a
  pre-flight check before starting a phase, plus an explicit note that
  none of §22 is in any checklist in that document.
- **`README.md`** — a pointer to §22 and the freeze.

### Notes
- **Approved is not built.** Every decision in §22 is signed off as the
  target architecture and **none of it exists in code**. The section is
  written as a contract for future work, and says so in its first line,
  so it cannot be misread as a description of the running system.
- **Two places where §22 constrains what already exists** are called out
  rather than left to be discovered later: today's configuration-driven
  provider selection (`JARVIS_LLM_DEFAULT_PROVIDER`) becomes an *input*
  to the Calibration Engine rather than a competing mechanism (§22.1);
  and the Status Bar's "AI Provider" item plus the Activity Center's
  agent node names both leak routing detail that §22.12 forbids to
  personal users — acceptable while Developer Mode is the audience, and
  now a tracked gating requirement before a personal-user build ships.
- **Nothing was scheduled** beyond M22. The rest awaits milestone
  assignment under `ARCHITECTURE.md` §20's governance process;
  `MASTER_ROADMAP.md` stays the single source of truth for sequencing.

## [0.30.0] — M8 Phase 3: Universal Workspace Framework

Panels. The frontend gains a dockable, resizable, persistable workspace
in which any module's content can sit alongside any other's, plus the
three shell-level panels that framework existed to make possible.

Backend untouched: no route, model, schema or contract changed. Every
Python gate is byte-identical to v0.29.0's, which is the intended result
of a frontend-only milestone rather than a coincidence.

### Added
- **Universal Workspace Layout** — four dock zones (`left`, `main`,
  `right`, `bottom`) plus a floating layer, each zone collapsing out of
  the layout entirely when empty, so a one-panel workspace looks like a
  single-pane app rather than a grid with three blank cells.
- **Panel system** — every panel supports the seven required operations:
  open, close, resize, collapse, detach, move, restore.
  `core/panel-registry.ts` is a `ContributionRegistry` instance, not a
  fourth hand-rolled registry — the generic mechanism exists for exactly
  this.
- **Multi-workspace support** — create, rename, delete, duplicate, reset,
  import, export, switch, and restore-on-launch. Layouts persist to
  `localStorage` under the established `jarvis.<name>` key convention.
- **Notification Center** — the persistent panel over
  `core/notification-framework.ts`'s already-real data. Listed in
  `IMPLEMENTATION_ROADMAP.md` Phase 3 and deferred since Phase 1 because
  it had nowhere to live; `notification-layer.tsx` has been a reserved
  `return null` anchor all along. The header's notification bell finally
  has a handler, for the same reason.
- **Activity Center** — one timeline merging background tasks, `agent.step`
  and `automation.step`. It merges live store reads rather than keeping a
  fourth copy of the same facts.
- **Global Search** — backed by the real `POST /api/v1/search` (M10A's
  13 registered sources). Distinct from the Command Palette, which
  navigates the app locally and instantly; this searches content over the
  network, and says so plainly when the backend is unreachable rather
  than returning an empty list that looks like "no results".
- **Responsive layout** — `hooks/use-responsive-layout.ts` shares the
  Sidebar's existing 768px breakpoint. Below it the rails are dropped and
  `main` fills, rather than three rails being squeezed to unusability.
- **Performance** — route splitting (`routes/lazy-routes.ts`), lazily
  imported panels, `<Suspense>` at both boundaries with one shared
  fallback, `memo` on `PanelFrame`, and `components/common/virtual-list.tsx`
  for the two unbounded lists. The build now emits eight feature chunks
  where it previously emitted one bundle.

### Notes
- **"Workspace" now means three things, deliberately kept apart.**
  `WorkspaceManager`/`workspace.store.ts` is which *module* the route has
  mounted; the backend `Workspace` (M11 Task Group A) is a data scope
  owning projects, notes, tasks and files; and this phase's
  `workspace-layout.store.ts` is a named *arrangement of panels*. The
  third links to the second through `backendWorkspaceId` — an id, never a
  copy of backend data — and does not touch the first.
- **Layouts persist locally, and that is not a compromise.** There is no
  endpoint for panel geometry and the backend contract is frozen; a
  layout is also genuinely per-device state, since an arrangement that
  suits a 34" monitor is wrong on a laptop.
- **Detached panels float inside the viewport, not in OS windows.** A
  real second window needs Tauri's multi-window API — its own React root,
  store bridge and IPC — which is `IMPLEMENTATION_ROADMAP.md` Phase 3's
  separate, still-open "Window management" item. The store's `frame`
  geometry is already in the shape that work would need.
- **Nine modules deliberately register no panel.** Conversation, Memory,
  Automation, Files, Browser, Coding, Finance, Smart Home, Calendar,
  Gmail and Spotify still render `PlaceholderRoute` — they have no real
  content. Wrapping "this module hasn't been built yet" in a title bar
  with resize handles would dress an unbuilt module up as a working one.
  They register on the day they have something to show; the framework
  needs no change when they do.
- **`skipHydration` on the layout store.** Zustand rehydrates on import,
  which can precede panel registration; since rehydration drops panels
  whose contribution is unknown, a layout restored at that moment would
  come back empty and the user would have lost their arrangement to an
  import-order accident. The startup sequence registers panels and *then*
  rehydrates, explicitly.

## [0.29.0] — M8 Phase 2: Universal Application Framework & Logic

The React client stops being a self-contained shell and starts talking to
the Python process. Most of this phase was not writing new frameworks —
Phase 1 built those — but connecting them to a backend that had moved on
underneath them, and finding that in three places the client's idea of
the backend was simply wrong.

**The recurring defect: a client written against the spec, not the
server.** Phase 1 shipped its REST and WebSocket layers before the
backend routes existed, using `ARCHITECTURE.md`'s illustrative examples
as the contract. The examples were illustrative. Every drift below is the
same mistake, and the fix is the same idea in each case — assert against
the running server, not the document.

### Security
- **`SettingsService.snapshot()` leaked OAuth client secrets.** Pydantic
  redacts a `SecretStr` on dump, which covers `openai.api_key` and its
  neighbours. It does not cover a secret inside a plain container, and
  `integrations.clients` (added by M11 Task Group E) is a
  `dict[str, dict[str, str]]` whose `client_secret` entries dump
  verbatim. The leak was latent — the only caller was the in-process
  PySide6 Configuration Manager — but adding a settings API is precisely
  the change that would have made it live, and it would have shipped a
  route that published Google OAuth client secrets to any authenticated
  caller. `public_snapshot()` now redacts by *key name* (the only check
  that catches a secret whose type says nothing about it), and the REST
  route serves that and never `snapshot()`. Two methods rather than one
  with a flag, matching `Credential.to_storage_dict`/`to_public_dict`:
  a method callers must remember to sanitise is one somebody forgets.

### Fixed
- **Eleven of the client's fourteen WebSocket event names did not
  exist.** `ai.token`, `ai.step`, `ai.complete`,
  `voice.transcript_partial`, `voice.transcript_final`,
  `automation.step_started`, `automation.step_completed`,
  `automation.workflow_finished`, `progress.update`,
  `notification.created` and `runtime.module_state_changed` were never
  emitted by anything. A handler registered for any of them would never
  fire — silently, with no error anywhere. The vocabulary is now the real
  61 names from `EVENT_TYPE_NAMES`, and three of the six payload
  interfaces this phase types had wrong field names too
  (`AutomationStepPayload` and `PluginNotificationPayload` were
  invented; `UpdatePhasePayload` was missing `session_id`).
- **The REST client discarded every error message the backend sent.** It
  understood only the `{"error": {...}}` envelope from `ARCHITECTURE.md`
  §9, which no route produces — every route raises `HTTPException`, which
  serialises as `{"detail": "..."}`. So a real "Workspace not found"
  surfaced as "Request failed with status 404". Both shapes are handled,
  `detail` first because it is the one that occurs.
- **The REST client expected cursor pagination.** It read
  `meta.next_cursor`; the backend ships offset paging
  (`{count, limit, offset, has_more}`) as of M11 Task Group F, which
  recorded that divergence rather than hiding it. `apiList` follows the
  server.
- **A 2xx with a non-envelope body threw a bare `TypeError`** from inside
  the client, naming nothing. It now raises `MALFORMED_RESPONSE` naming
  the route, and flows through the normal error path. Found by a test.
- **`notification.created` in `notifications.store.ts`** — a comment
  documenting an event that has never existed. The real one is
  `notification.plugin`.

### Added
- **A generated WebSocket contract, asserted from both sides.**
  `scripts/export_ws_contract.py` writes
  `frontend/src/services/websocket/event-contract.generated.json` from
  `EVENT_TYPE_NAMES` and each event's dataclass fields.
  `tests/unit/test_ws_contract_export.py` fails if the checked-in file is
  stale; `websocket-contract.test.ts` fails if the TypeScript disagrees
  with it. Neither side can drift without something going red — which is
  the only durable fix for the class of defect above.
- **`GET /api/v1/settings` and `/api/v1/settings/{dotted_key}`** —
  read-only, session-authenticated, `{data, meta}` envelope, secrets
  redacted. Read-only deliberately: writing a setting means writing
  `.env`, which is a privilege-escalation surface belonging with M14's
  Security Platform, not with a frontend phase whose job is to read real
  values.
- **Frontend service layer** — `services/api/client.ts` (typed REST,
  configurable base URL via `VITE_API_BASE_URL`),
  `services/api/session.ts` (the authentication flow; the token is
  deliberately not persisted), `services/api/endpoints.ts` (typed
  helpers for every M9–M11 surface the client reads),
  `services/backend-connection.ts` (the ping → session → socket
  ordering, in one place), `services/realtime-bridge.ts` (every
  WebSocket subscription, installed once at startup rather than inside
  component effects), `services/permissions-sync.ts`,
  `services/error-reporting.ts`.
- **Stores and hooks** — `connection.store.ts`, `settings.store.ts`,
  `agent-activity.store.ts`, `use-backend-status.ts`.
- **`npm run typecheck`** as a permanent quality gate. It runs
  `tsc -b --noEmit`, not `tsc --noEmit`: the root `tsconfig.json` is a
  solution file (`"files": []`), so plain `tsc --noEmit` type-checks zero
  files and exits 0 — a gate that always passes. Verified with
  `--listFilesOnly` before choosing build mode. It caught six real errors
  on its first run.

### Notes
- **Offline is an explicit state, never fake data.** `BackendState`
  distinguishes `unreachable` (the process is not answering) from
  `unauthenticated` (it is, but refused a session), because collapsing
  them produces a UI that says "something went wrong" when the truth is
  "JARVIS isn't running". A failed request while offline deliberately
  does *not* toast — the condition is already on screen persistently.
- **Permissions are surfaced from M9's `PermissionModel`.** The roadmap
  files this under "the backend's Authorization Engine (M14)"; M14 does
  not exist. The Authorization Engine that does exist owns the same
  ten-scope vocabulary `core/permission-framework.ts` already mirrors, so
  Phase 2 surfaces that one and `services/api/endpoints.ts` is the single
  place that repoints if M14 supersedes it.
- **Storage needed no new work.** `core/storage-framework.ts` already
  implements the four sensitivity tiers ARCHITECTURE.md §12 specifies,
  including refusing client-side encryption rather than pretending to
  offer it. Verified, not rebuilt.
- **The "API Integration Rework" sub-block is not included.** Those ten
  items (Real API Activation, Provider Registry, Runtime Provider
  Registration, failover, …) are backend provider-lifecycle work tied to
  M11's API Center Architecture module, not frontend framework work, and
  they are not honestly completable in this phase. They remain unchecked
  in `IMPLEMENTATION_ROADMAP.md` with this note.

## [0.28.0] — M11 Task Group F: Platform Integration & Closure

An audit of every cross-cutting surface M11 built, and the fixes the
audit turned up. Four defects were real; the rest of the platform was
already consistent, and this entry says which is which rather than
implying everything needed work.

**What was audited, with evidence.** 170 REST routes, 1 WebSocket route,
66 event classes, 88 DI providers, 13 search sources, 37 settings
sections. Findings are pinned as tests in
`tests/unit/test_platform_integration.py`, so the invariants cannot
quietly regress.

### Security
- **A session could be read and closed by anyone who learned its id.**
  `GET`/`DELETE /api/v1/sessions/{id}` took the id in the URL path and
  required nothing else — but a session id *is* the Bearer token for
  the rest of this API, so anyone who saw one in a proxy log, a browser
  history entry or a `Referer` header could confirm it was live and,
  worse, close it, logging the real holder out. Both routes now require
  the Bearer token **and** check it names the same session as the path.
  A caller can only read or close its own. Cross-session access returns
  `404`, not `403`, so a valid token for one session cannot be used to
  discover whether another exists. (RFC 6750 §2.3 is the general rule
  this violated.)

### Fixed
- **Collections truncated silently.** Every repository already capped
  its queries (200 on the workspace tables, 500 on files and links),
  nothing above them exposed the cap, and `meta` reported only `count`
  — so a workspace holding 250 notes returned 200, said `"count": 200`,
  and gave the caller no way to tell a complete answer from a truncated
  one nor any way to reach the rest. The cap was right; its invisibility
  was the bug. All nine M11 collections now take `limit`/`offset` and
  report `{count, limit, offset, has_more}` through one shared helper
  (`infrastructure/api/pagination.py`), not a parameter invented per
  router.
- **`memory_recall_hook` was registered twice in the DI container.** An
  earlier `NoopMemoryRecall` binding that the real
  `SemanticMemoryRecallHook` silently replaced. Behaviour was correct —
  the last binding wins — but a reader following the first one would
  have concluded the chat pipeline ran with recall disabled. The dead
  registration and its now-unreferenced factory are gone.
- **M11's subsystems reported nothing to `HealthMonitor`.** Task Groups
  A–E shipped five subsystems and none of them appeared in `/health`,
  in the `health.updated` relay, or in Developer Mode: a file storage
  root that had become unwritable, or an integration gateway failing
  every outbound call, was invisible. One new collector
  (`workspace_platform`) closes that on the extension point that
  already exists.

### Added
- `infrastructure/api/pagination.py` — `Page`, `page_params`,
  `page_meta`. Over-fetch by one to answer `has_more` exactly, rather
  than a `COUNT(*)` beside every listing that would double the queries
  and still be racy.
- `offset` on the nine list repositories that already took `limit`, and
  `limit`/`offset` pass-through on their services.
- `tests/unit/test_pagination.py` and
  `tests/unit/test_platform_integration.py` — the audit invariants as
  tests.

### Notes — what the audit found already correct
These were checked and needed no change; they are recorded so a future
audit knows they were verified rather than skipped:
- **Auth coverage.** 170 routes; exactly six are session-free, and all
  six are deliberate: `/health`, `/ready`, `POST /sessions` (how a token
  is obtained), the two session routes above (now token-checked), and
  the OAuth callback (a browser redirect carries no header; its
  single-use `state` is the defence).
- **Response envelope.** Every resource route returns `{data, meta}`.
  The five exceptions are `/health`, `/ready` (flat by design for
  probes) and `/agent/stream` (SSE).
- **Error handling.** 14 probes across every M11 domain: unknown id →
  `404`, invalid input → `400`, zero deviations.
- **Events.** 66 declared, 61 relayed, 5 absent and all 5 on the
  documented exception list. No duplicate relay names; every name is
  `<category>.<event>` lowercase; every relayed event is really
  published.
- **Search.** 13 sources, each registered exactly once, none missing —
  and every service `search*` method sits behind exactly one of them.
- **Dependency injection.** 88 providers, 84 singletons and 3 factories
  (all deliberate), no two providers building the same target.
- **Settings.** 37 sections, every one under `JARVIS_`, no duplicate
  prefixes, every one constructible from defaults — so a fresh install
  with no `.env` starts.
- **Workspace isolation.** Cross-workspace writes are refused with a
  `400` naming the reason: a note cannot join another workspace's
  project, a file cannot attach to another workspace's task, and
  workspace-scoped listings do not leak.
- 49 new tests (2136 → 2185). mypy 263 → **262** (the deleted legacy
  factory carried an untyped parameter), ruff 21 categories unchanged.

### Remaining
- **The React/Tauri workspace UI is not built.** The original M11 Task
  Group F brief paired "UI Integration" with "Platform Closure"; the
  frontend half belongs to M8, which is deferred, and this task group
  delivered the backend integration only. No UI work is claimed.
- OpenAPI descriptions are uneven — routes carry docstrings where the
  reasoning mattered and not elsewhere. Cosmetic, and mass-adding
  summaries would be noise rather than documentation.

## [0.27.0] — M11 Task Group E: Integration Platform

The outbound half of M11: OAuth2, one audited egress point, and vendor
connectors that run as MCP providers. Built entirely on M10.5's MCP
platform — every connector is registered in the same provider registry,
driven by the same lifecycle, gated by the same permission model and
reported by the same health collector.

Google Workspace ships (11 integrations, 65 operations). Phases 2–6 of
the brief are catalogue entries against the same engine and are **not**
built — see Notes.

### Added
- **OAuth2, closing M10.5's deferral** — `core/mcp/auth/oauth2.py`: the
  authorization-code grant with **mandatory PKCE** (S256), the
  client-credentials grant, `OAuthFlowStore` (single-use, expiring
  `state`; the PKCE verifier never leaves the server), and
  `BoundOAuth2Strategy` for per-provider refresh and remote revoke. Both
  register into the **existing** `AuthStrategyRegistry` — the one call
  Task Group D's docstring predicted.
- **API Gateway** — `core/integrations/gateway.py`: the single audited
  egress point. One `httpx` pool, retry for idempotent methods only,
  bounded `Retry-After` handling, and a short account-keyed response
  cache that any mutation invalidates.
- **Connectors as data** — `core/integrations/models.py`:
  `IntegrationSpec` / `OperationSpec` / `AuthSpec`, validated at
  registration, with path rendering and parameter splitting as the
  security boundary.
- **`RestIntegrationProvider`** — an `IMCPProvider` for vendor REST
  APIs. Same `MCPProviderRegistry`, same `MCPProviderManager`, same
  events, same `MCPCapabilityRegistry`, same `PermissionModel`, same
  health collector.
- **Google Workspace (Phase 1)** — Gmail, Calendar, Meet, Drive, Docs,
  Sheets, Slides, Contacts, Tasks, Keep, Photos.
- **`IntegrationService`** — catalogue, install, the two-step OAuth
  flow, invoke, preview, per-vendor search, gateway stats.
- **REST** — `/api/v1/integrations/*`: catalogue, install/uninstall,
  connect/disconnect, `oauth/authorize`, `oauth/callback`,
  `invoke`, `preview`, `search`, `gateway/stats`.
- **Search** — one `ISearchSource` per connected integration, added to
  M10A's registry on connect and removed on disconnect. No change to
  `SearchService`.
- **Agent tools** — `list_integrations`, `describe_integration`,
  `search_integration`, `invoke_integration`, on the existing registry.
- **Event** — `IntegrationCallCompletedEvent`, relayed as
  `integration.call_completed`.
- **Settings** — `JARVIS_INTEGRATIONS_*`, including per-vendor OAuth
  clients (`CLIENTS__GOOGLE__CLIENT_ID`) and the redirect URI.

### Changed
- **`MCPProviderManager.install` gained an optional `provider=`** — the
  seam `core/interfaces/mcp.py` promised in prose, made real by the
  first integration that needed it. Defaulted, so every existing call
  site is unchanged.
- **`MCPAuthManager` gained `auth_header`, `needs_refresh` and
  `bind_strategy`.** The first is the single sanctioned route a token
  takes out of the auth subsystem (a formatted header, never a bare
  token). The last exists because the shared registry keys on *method*
  while OAuth2 refresh needs a token endpoint and client id —
  configuration, which a `Credential` deliberately does not carry.

### Fixed
- **`IntegrationError` reached the REST layer as a 500.** An undeclared
  parameter or a duplicate install was refused correctly but reported
  as a server fault. `IntegrationService` now translates the `MCPError`
  family into `ServiceError` at the boundary, through one context
  manager rather than a try/except per method — the same class of gap
  Task Group C found with attachments.

### Security
- **A caller supplies parameters, never a path.** Every path
  placeholder is percent-encoded with `safe=""`, so `..` or `/` in a
  value becomes one literal segment instead of changing the endpoint. A
  parameter the spec does not declare is refused rather than forwarded.
- **Mutating calls are never retried.** A retried send sends twice.
- **Exactly one route is session-free** — the OAuth callback, because a
  browser redirect carries no `Authorization` header. Its `state` is
  generated with `secrets`, single-use and expiring; unknown, replayed
  and stale values are all refused (RFC 6749 §10.12). It lives on its
  own router so the exception is visible in review.
- **Two permission gates per call**, and the refusal names which one
  said no: the operator's grant in the shared `PermissionModel`, and the
  vendor scopes the token actually carries. Checked per call, so
  revoking a grant bites on the next call.
- **No token appears in a response, an event, a log line or a preview.**
  The audit payload carries query *keys*, never values, and never a body.
- **Vendor scopes are the narrow ones** where a narrow one exists —
  `drive.file` over `drive`, `gmail.readonly` over `mail.google.com`.
- **HTTPS is required** for every endpoint; loopback is allowed so the
  engine can be tested against a local server.

### Notes
- **Phases 2–6 are not built.** Microsoft 365, GitHub/GitLab,
  Slack/Discord/Teams, Notion/Jira/Trello/ClickUp/Linear/Asana and
  Dropbox/Box run on this engine as spec data. They were deliberately
  not written from memory: a subtly wrong endpoint path or scope name
  ships a connector that fails at the first real call, and a wrong
  catalogue entry is worse than an absent one because it claims to work.
- **No two-way sync** for Google Tasks or Keep. Pull and push
  operations ship; a *sync* needs a conflict policy and a scheduler
  (M7 Phase 6). One-directional import that works beats a mirror that
  silently loses an edit.
- **Google Keep is Workspace-only** and says so in its
  `availability_note`, so the REST surface reports it before a caller
  spends an OAuth round trip.
- **Google Meet has no scheduling API** — a Meet link is
  `conferenceData` on a Calendar event, so that lives on the Calendar
  spec; `google_meet` exposes the conference *records* the Meet API
  actually offers.
- **Also absent:** webhooks and inbound delivery, a durable outbound
  queue, resumable/multipart upload (simple upload ships, correct to
  5 MB), and Oracle Cloud sync.
- 200 new tests (1936 → 2136). mypy 263 → 263, ruff 21 categories, both
  unchanged.

## [0.26.0] — M11 Task Group D: AI Workspace

The AI layer over the substrate Task Groups A–C shipped: a real
workspace↔knowledge association, a budgeted context a model can be given
whole, retrieval scoped to one workspace, and grounded assistance
reachable from REST and from the existing agent. On-demand only — nothing
here schedules anything, and no assist call is persisted.

### Added
- **Domain** — `domain/ai_workspace/models.py`: `ContextItem`,
  `ContextSection`, `WorkspaceContext`, the greedy `pack()` and its
  character budget, `clip()`, `order_sections()`, `render_results()` and
  `build_assist_prompt()`, plus the four closed vocabularies
  (`SECTION_ORDER`, `LINK_TARGETS`, `LINK_SOURCES`, `ASSIST_MODES`).
  Pure: no database, no service, no provider.
- **Schema** — one table, `workspace_knowledge_links`: workspace +
  entity, four nullable narrow foreign keys (project/note/task/file),
  `source` (`extracted` | `manual`) and `confidence`. The association
  table Task Group A's `WorkspaceManager.context` explicitly declined to
  invent until this task group had said what it needed.
- **Repository** — `WorkspaceLinkRepository`, with an exact-match `find`
  (nulls compared, so "this note is about Ada" and "this workspace is
  about Ada" stay distinct rows), `delete_extracted_for_target`, and an
  aggregate `entities_for_workspace` join.
- **Services** — `WorkspaceKnowledgeService` (link/unlink, idempotent
  linking with extracted→manual promotion, and ingestion over a
  workspace's own text, its notes and its files' index records) and
  `WorkspaceAssistantService` (`summarize` / `ask` / `next_actions`,
  grounded, with citations).
- **Managers** — `WorkspaceContextManager` (the budgeted context across
  every M11 subsystem plus Knowledge and Memory) and `WorkspaceRetriever`
  (workspace-scoped retrieval over the shared `SearchService`).
- **Agent tools** — `list_workspaces`, `workspace_context`,
  `search_workspace`, `ask_workspace`, `summarize_workspace`, on the
  **existing** registry via `build_tool_registry`'s new optional
  `workspace_assistant` argument.
- **Events** — `WorkspaceKnowledgeLinkedEvent` and
  `WorkspaceAssistCompletedEvent`, relayed as
  `workspace.knowledge_linked` and `workspace.assisted`.
- **REST** — `/api/v1/workspace-ai/{id}/context`, `/retrieve`,
  `/assist`, `/ingest`, `/entities`, plus `/api/v1/knowledge-links`
  (create/list/read/delete). Same Bearer auth and `{data, meta}`
  envelope as every resource router.
- **Settings** — `JARVIS_AI_WORKSPACE_*`: `context_budget_chars`,
  `context_section_items`, `context_item_chars`, `retrieval_top_k`,
  `retrieval_overfetch`, `ingest_max_targets`.

### Changed
- **`WorkspaceManager.context` gained `linked_knowledge`** alongside the
  existing `related_knowledge`. The two answer different questions —
  what this workspace's text *produced* versus what merely shares a word
  with its name — and both are kept, because a brand-new workspace has
  produced nothing yet. Additive: nothing that was in the payload moved.
- **`ExtractionResult` gained `entity_ids`** (M10A). The counts alone
  cannot say *which* entities a text is about: one mentioning an entity
  the graph already knows creates nothing and looks, from the counts,
  like a text about nothing. Defaulted and last, so every existing
  construction site and assertion is unchanged.

### Fixed
- **Tasks with no due date were missing from the assembled context.**
  `TaskManager.agenda` answers "what is due", which is right for a badge
  and wrong for a context — an undated task is neither overdue nor due
  soon, and most tasks are undated. The tasks section now lists open
  tasks as a third group; the urgency judgement still comes from the
  manager that owns it.

### Notes
- **No second anything.** Retrieval narrows M10A's `SearchService` by
  the `workspace_id` its sources already publish, rather than building a
  workspace index — widening `ISearchSource.search` would change all
  thirteen registered sources, most of which have no workspace concept.
  Extraction is `KnowledgeService.learn_from_text`, called. The agent is
  M10's `AgentOrchestrator`, reached as tools; this milestone runs no
  graph of its own.
- **No search source was registered** — the first M11 task group not to
  add three. Knowledge entities are already searchable through
  `KnowledgeSearchSource`, and a second source over the same rows would
  return one entity twice with no way to tell the hits apart.
- **Re-ingestion replaces what it extracted and never what a person
  asserted.** An edited note stops claiming entities its text no longer
  mentions; a `manual` link survives. Asserting a link the extractor had
  already found promotes it rather than duplicating it.
- **The budget is in characters, and truncation is reported.**
  `pack()` is greedy in a fixed section order, so the tail is what is
  dropped under pressure, and every section keeps its pre-packing
  `total` — a section holding three of forty tasks says so. Characters
  rather than tokens because tokenization belongs to a provider.
- **The assistant degrades instead of failing.** No reachable provider
  returns the assembled context verbatim with `synthesized=false` — the
  posture `KnowledgeService.ask` already set, and the only one
  compatible with an offline-first product.
- **Nothing is scheduled, and no assist call is stored.** Ingestion runs
  on demand (M7 Phase 6 owns scheduling); an assist returns its answer
  and publishes an event, and `ConversationService` remains the only
  transcript store. `workspace.assisted` deliberately carries no answer
  text.
- **No embeddings over workspace content.** Retrieval is the shared
  keyword index narrowed by workspace, not a vector search; semantic
  indexing needs the vector-store work Task Group C deferred.
- 199 new tests (1737 → 1936). mypy 263 → 263, ruff 21 categories, both
  unchanged.

## [0.25.0] — M11 Task Group C: File Platform

A local file subsystem hanging off the Workspace substrate Task Group A
shipped: folders, files, tags, extensible metadata, plain-text indexing,
and attachments to five workspace entities. Local files only — no
Drive, no Dropbox, no OneDrive, no cloud sync.

### Added
- **Domain** — `domain/files/models.py`: `safe_join` (the single place
  path containment is decided), `validate_name`, `extract_text`, the MIME
  and extension helpers, and the closed vocabularies
  (`TEXT_EXTRACTABLE_EXTENSIONS`, `INDEX_STATUSES`, `ATTACHMENT_TARGETS`).
- **Schema** — six tables: `folders` (self-referential, with a
  denormalized `relative_path` cache), `files`, `file_tags` (a real join
  table), `file_metadata` (key/value rows), `file_index_records` (1:1
  with a file, four-way status), `workspace_attachments` (five nullable
  foreign keys, one per target kind).
- **Repositories** — `FolderRepository`, `FileRepository`,
  `MetadataRepository`, `AttachmentRepository`.
- **Services** — `FolderService` (create/rename/move/delete with cycle
  prevention and subtree path rewriting), `FileService` (CRUD, move,
  rename, tags, metadata, indexing, stats, search), `AttachmentService`.
- **Managers** — `FolderManager` (tree with depths, file counts and
  unfiled files), `FileManager` (context and workspace overview),
  `AttachmentManager` (both directions of the link).
- **Events** — `FileUpdatedEvent`, `FolderUpdatedEvent`,
  `AttachmentUpdatedEvent`, relayed as `file.updated`, `folder.updated`,
  `attachment.updated`.
- **Search** — `FileSearchSource`, `FolderSearchSource`,
  `AttachmentSearchSource`, registered through M10A's provider registry.
  `files` is the first source whose corpus includes extracted document
  text rather than only stored fields.
- **REST** — `/api/v1/files`, `/api/v1/folders`, `/api/v1/attachments`,
  same Bearer auth and `{data, meta}` envelope as every resource router.
- **Settings** — `JARVIS_FILES_*`: `storage_dir` (defaults to
  `<data_dir>/files`), `index_enabled`, `index_max_bytes`,
  `max_upload_bytes`.

### Security
- **The storage root is a hard boundary.** Every path resolves through
  `safe_join`, which resolves both sides before comparing so a symlink
  out of the root is caught as well as a literal `..`, and which raises
  rather than clamping. It runs at construction *and* again on every
  read. The REST API accepts no path fragment at all — callers name a
  folder by id — so the input class that could escape is not part of the
  surface.
- **Attachment targets are validated before the insert.** Foreign keys
  already refuse a fabricated parent, but as an `IntegrityError` that
  reaches the caller as a 500. `AttachmentService` now returns a 400
  naming what is missing, and additionally rejects an attachment
  spanning two workspaces — the one rule a foreign key cannot express.

### Notes
- **Indexing reads seven extensions and nothing else** (`.txt`, `.md`,
  `.json`, `.yaml`, `.yml`, `.csv`, `.xml`), bounded at 1 MiB per file.
  No OCR, no PDF parsing, no embeddings, no summarisation. `skipped` is
  a successful catalogue entry, not a failure — which is why
  `IndexRecord.status` has four values rather than a boolean.
- **Deleting a non-empty folder requires `recursive=true`.** The
  database cascade would take the subtree happily; that is the wrong
  default for a destructive operation on real bytes.
- **Detaching is not deleting.** Removing an attachment leaves the file
  untouched; deleting the *target* removes only the link.
- File bytes travel as base64 inside the envelope rather than as
  multipart, because `python-multipart` is not a declared dependency of
  this project and building a shipped endpoint on a transitive package
  is a break waiting for someone else's lockfile.
- 116 new tests (1621 → 1737). mypy 263 → 263, ruff 21 categories,
  both unchanged.

## [0.24.1] — Database integrity: SQLite foreign-key enforcement

A stabilization patch, ahead of M11 Task Group C introducing more
relational models (folders, files, attachments, indexing).

### Fixed
- **Foreign keys are now enforced.** SQLite ships with
  `PRAGMA foreign_keys` off and scopes it per *connection*, so every
  `ON DELETE`/`ON UPDATE` clause in `models.py` had been decorative
  since M1. `SQLiteDatabase` now issues the pragma from a single
  `connect` event listener on the engine — SQLAlchemy's documented
  pattern — rather than per repository or per session.
- **`POST /api/v1/sessions` accepted an unvalidated foreign key.**
  `conversation_id` went straight from the request body into a real FK
  column; an unknown id silently created a session pointing at nothing
  and still returned `201`. `SessionManager.create` now checks the
  conversation exists and the route returns `400`. `thread_id` is
  deliberately still unchecked — it is not a foreign key (LangGraph's
  checkpointer owns that id space).
- Three tests were fabricating parent ids (`"mem-1"`, `"conv-1"`) that
  no row matched. They now seed real rows; the assertions are unchanged.

### Added
- `tests/unit/test_database_integrity.py` — pins the pragma across
  pooled connections, proves an orphan insert is rejected and a valid
  one still works, proves a declared `ON DELETE CASCADE` now actually
  fires through raw SQL (no ORM cascade involved), and covers the new
  session validation on both the reject and accept paths.

### Notes
- **Nullable foreign keys are unaffected.** `ON DELETE SET NULL`
  columns stay optional — an unfiled note, a session with no
  conversation. Enforcement rejects what is broken, not what is unset.
- `ondelete=` and the ORM's `cascade=` remain two mechanisms, both now
  live. See `ARCHITECTURE.md` §12 for which governs what.
- 1613 → 1621 tests, all passing. mypy 263 → 263; ruff 21 categories
  unchanged; black clean. No roadmap milestone was modified.

## [0.24.0] — M11 Task Group B, Productivity Core

Tasks, the local Calendar engine, and Reminders — the three domains
that hang off Task Group A's Workspace substrate. None of them invented
a container, which was the argument for building A first.

### Added
- **Task domain** — `Task` model, `TaskRepository`, `TaskService`,
  `TaskManager`. Status, priority, due dates, normalized tags, and an
  agenda (overdue / due-soon / status counts) with an injectable clock.
- **Local Calendar engine** — `Calendar`, `CalendarEvent`,
  `CalendarRepository`, `CalendarService`, `CalendarManager`. Event
  CRUD, categories, metadata, per-workspace default calendar, and
  recurrence **rules**.
- **`RecurrenceRule`** — a small explicit subset of RFC 5545 (four
  frequencies, interval, one of count/until) with bounded, pure
  expansion. Month arithmetic clamps: the 31st plus one month is the
  28th, not the 3rd.
- **`CalendarManager.occurrences`** — expands stored rules into the
  concrete datetimes in a window. The capability no single service call
  provides, because the repository can only filter on an event's
  *stored* start.
- **Reminder domain** — `Reminder`, `ReminderRepository`,
  `ReminderService`, `ReminderManager`. Scheduling metadata, status
  transitions, target resolution across Tasks and Calendar.
- **Four relay events** — `task.updated`, `calendar.updated`,
  `calendar.event_updated`, `reminder.updated`, each one class with an
  `action` field.
- **Three search sources** — `tasks`, `calendar`, `reminders`, through
  M10A's provider registry with no change to `SearchService`.
- **REST** — `/api/v1/tasks`, `/api/v1/calendar/*`, `/api/v1/reminders`
  plus `/tasks/agenda`, `/calendar/occurrences`, `/reminders/due` and
  per-entity `/context`.
- DI singletons for all three services and all three managers.

### Fixed
- **The workspace cascade did not reach any Task Group B table.**
  `ON DELETE CASCADE` is declared on every foreign key, but SQLite
  ignores it unless `PRAGMA foreign_keys=ON` is set and this
  application never sets it — so Task Group A's cascade had been
  working purely through SQLAlchemy's ORM-level `cascade` on
  `Workspace.projects`/`notes`. New child tables silently survived
  their parent. Fixed by adding the relationships, and documented in
  `models.py` so the next task group does not rediscover it.
- `ReminderService.next_occurrence_after` returned the naive datetime
  SQLite hands back, which would raise on comparison against
  `datetime.now(UTC)`. Now always aware.

### Notes
- **Nothing in this task group fires a reminder.** `due_before()` and
  `/reminders/due` *report*; there is no loop, no timer, no queue, and
  deliberately no `reminder.fired` event. Delivery is M7's Scheduler
  (Phase 6). Three tests assert the boundary at the service, manager
  and HTTP layers.
- **Local calendar only** — no Google, no Outlook, no synchronization.
  Those are Task Group E.
- Not built: File Manager/Search (C), workspace AI context (D), every
  external integration (E), the React UI (F).
- 1516 → 1613 tests, all passing. mypy 263 → 263; ruff 21 categories
  unchanged; black clean.

## [0.23.0] — M11 Task Group A, Workspace Foundation

The first implementation pass on M11, and the substrate the rest of the
milestone hangs off. M11 was restructured into six task groups (A–F)
before any code was written: the original "Integrations & Cloud
Platform" brief is now Task Group E, sitting on top of a shared
Workspace model rather than each integration inventing its own
container. No milestone was renumbered.

### Added
- **Workspace domain** — `Workspace`, `Project` and `Note` ORM models,
  plus `WorkspaceSettings` (a value object serialized into one JSON
  column) and `WorkspaceMetadata` (derived on read, never stored).
- **Three repositories** — `WorkspaceRepository`, `ProjectRepository`,
  `NoteRepository`, following `IntelligenceRepository`'s shape exactly.
- **`WorkspaceService`** — lifecycle, CRUD, settings, metadata, search
  hooks and event publishing. Shaped like `IntelligenceService`: an
  `IDatabase` per call, repository inside the session, optional
  `EventBus`.
- **`WorkspaceManager`** — composes the service with Knowledge, Search
  and Memory. Collects and never computes; every collaborator optional.
- **Three relay events** — `workspace.updated`, `project.updated`,
  `note.updated`, each one class carrying an `action` field, the shape
  `memory.updated`/`goal.updated` established.
- **Three search sources** — registered through M10A's provider
  registry with no change to `SearchService` itself.
- **REST** — `/api/v1/workspaces`, `/api/v1/projects`, `/api/v1/notes`
  (CRUD), plus `/workspaces/{id}/metadata`, `/overview` and `/context`.
- DI singletons `workspace_service` and `workspace_manager`.

### Notes
- **A note belongs to a workspace and only optionally to a project** —
  a thought worth capturing rarely arrives already filed. Consequently
  deleting a project *keeps* its notes, moving them back to the
  workspace, rather than letting the ORM cascade take them. Deleting a
  workspace does cascade, because that is an explicit "remove all of
  this".
- **Not built, by scope:** Tasks, Calendar, Reminders (TG-B); File
  Manager and File Search (TG-C); workspace AI context beyond a
  deterministic text match (TG-D); every external integration (TG-E);
  the React workspace UI (TG-F). No collaboration, sharing or sync
  endpoints — those need an identity model and a conflict story that do
  not exist yet.
- 1460 → 1516 tests, all passing. mypy 263 → 263; ruff 21 categories
  unchanged; black clean.

## [0.22.0] — Final Backlog Completion Pass (pre-M11)

The second and last backlog pass before M11. Where `0.21.0` closed the
§15 items the roadmap had written down, this one closed what the
roadmap had *not* — three Settings pages and one spoken greeting that
had quietly become false as the milestones behind them shipped.

### Fixed
- **The startup greeting invented the user's day.** `build_context` fed
  the LLM an invented task list, invented calendar events, an invented
  "recent achievement", a fabricated temperature and a fabricated
  now-playing track — then the greeting was *spoken aloud* as fact.
  Work context now comes from M10B's real Goal Manager (open goals,
  completed goals); calendar, weather, music and smart-home stay empty
  until M11/M12 give them a real source, and the prompt simply drops
  what it has no context for. `features/greeting/mock_context.py` is
  deleted.
- **Three Settings pages advertised milestones that had already
  shipped.** "Browser Automation" and "Desktop Automation" read *Coming
  in Milestone 4 — Automation* while `BrowserSettings` and
  `WindowsAutomationSettings` were real and consumed by shipped
  services; "Plugins" read *Coming in Milestone 5 — Agents* while the
  whole Plugin Platform shipped in M9. All three are now real pages
  over the settings that already existed.
- **Home dashboard service cards showed a green "connected" light over
  invented data.** Gmail, Spotify, Weather, Finance and Smart Home read
  as genuine readings of the user's inbox, music and local weather.
  They now render a `preview` state: offline indicator plus a visible
  "Preview — no integration connected yet" note. The illustrative data
  stays (it is what M5 shipped and what proves the widget works); the
  claim to be connected does not.

### Added
- `BrowserAutomationPage`, `DesktopAutomationPage` (M4 settings) and
  `PluginsPage` (M9 settings) — 15 real Settings pages now, 2
  placeholders.
- A `preview` key in `ServiceWidget`'s refresh contract, which forces
  the offline indicator regardless of what the payload claims.

### Changed
- The two remaining Settings placeholders name the milestone that
  actually owns them (M12 Smart Home & IoT, M14 Security) instead of
  the retired "Milestone 6 — Ecosystem" grouping.
- `GreetingService` takes an optional `intelligence_service`, wired by
  DI. Absent or failing, the greeting loses its work context and
  nothing else — same best-effort contract every other context source
  in that method already had.

### Notes
- Sweep found **zero** `TODO`/`FIXME`/`HACK`/`XXX` in `src/`, zero dead
  routes (all nine routers mounted), and zero unwired DI services.
- Remaining stand-ins are all owned by unstarted milestones and are
  now labelled as such: the integration providers (M11/M12), the vision
  and OCR providers (M6's remainder, already reporting themselves
  unavailable), the module registry (no module hot-reload machinery
  exists), and the Automations workspace placeholder.
- 1451 → 1460 tests, all passing. mypy 265 → 263; ruff 22 → 21
  categories; black clean.

## [0.21.0] — Backlog Completion & Stabilization Pass (pre-M11)

Not a milestone. A pass over the documented backlog of milestones that
are already complete, plus the UI/runtime audit that surfaced two
places where a screen was showing invented data next to a working
backend.

### Fixed
- **The desktop Plugin Manager rendered fabricated plugins.** It was
  still wired to an M5-era `MockPluginProvider` that seeded two invented
  entries ("Weather Widget", "Spotify Connector") and a three-item
  invented marketplace. M9 Task Group C shipped the real Plugin Platform
  — registry, loader, sandbox, permission model, marketplace — and this
  view was simply never rewired. It now reads the live `PluginRegistry`
  through a new `PluginRegistryProvider`; Enable/Disable/Reload perform
  real lifecycle transitions, a failed plugin shows its actual error,
  and an install with no plugins shows an empty state. The mock was
  deleted rather than left beside the real thing.
- **The Module Manager invented update availability.** `check_update`
  rolled `random.random() < 0.3` and fabricated a bumped version number
  when it came up, so the same click told the user a different story
  each time. There is no module update channel; the button now says
  "No update channel" instead of the equally untrue "Up to Date".
- Install/Uninstall/Update tooltips in the Plugin Manager claimed "no
  plugin loader exists yet", which stopped being true at M9. They now
  name the real reason (each needs a source directory this surface does
  not ask for) and point at the REST route that does the job.

### Added
- **Five WebSocket relay categories that were published but never
  relayed** (`MASTER_ROADMAP.md` §15, M9 Task Group B): `voice.state_changed`,
  `automation.step`, `progress.update_phase`, `notification.plugin` and
  `plugin.custom`. Every one had a real publisher; only the
  `EVENT_TYPE_NAMES` entry was missing, so no subscriber could ever see
  them. `UNPUBLISHED_EVENT_TYPES` now names the four event classes still
  deliberately absent, and a test fails if one of them gains a publisher
  without gaining a relay entry.
- **Disk metrics in the health snapshot** (§15, M9 Task Group C):
  `disk_percent`, `disk_free_bytes`, `disk_total_bytes`, as flat
  top-level keys so `ResourceManager.register_budget()` can target them
  — which was the whole point of tracking the item. GPU stays
  unimplemented and unfaked: it needs a vendor library this project does
  not depend on.
- `/api/v1/health` and `/api/v1/ready` (§15): the paths
  `docs/ARCHITECTURE.md` has always documented. The original
  `/api/health` and `/api/ready` keep working — one router, mounted
  twice, with a test pinning that both return identical bodies.

### Changed
- **BREAKING — `/api/v1/sessions` now returns the `{data, meta}`
  envelope** (§15). It was the last route outside the envelope
  `ARCHITECTURE.md` §5 mandates; §15 deferred the change until a second
  resource route existed to prove the shape, and six now do. Callers
  read `response.json()["data"]["session_id"]`. The route keeps its
  separate authentication exemption — it is what issues the token every
  other route needs.
- `HealthMonitor` takes a `disk_path`, wired by DI to the data directory
  — the volume JARVIS can actually fill.

### Notes
- **M8's deferred backlog is untouched, deliberately.** Notification
  Center, Context Menu system, Workspace views, window management,
  responsive/DPI/multi-monitor, Phases 2/5/6/7 — that is the M8
  milestone itself, not stabilization, and M8 is an *active* frontend
  migration whose PySide6 surfaces are slated for replacement. Building
  them in the outgoing stack would be work thrown away twice.
- M7's Scheduler, M10A's File Search, M10B's scheduled briefing, M10's
  Learning/Feedback and M10.5's two partial acceptance criteria all
  remain open with named owners (M7 Phase 6, M11B, M15, M16, M14, M11).
  Each is blocked on a milestone that has not started, not on effort.
- 1433 → 1451 tests, all passing. mypy 266 → 265; ruff category list
  unchanged at 22; black clean.

## [0.20.0] — M10.5 Task Group E, SDK, Developer Experience & Milestone Closure

The last task group of M10.5. It ships nothing a *user* sees and
everything an integration *author* needs, then closes the milestone.
Still no real provider, no OAuth flow and no vendor integration — those
were always M11's scope.

### Added
- **MCP SDK** (`core/mcp/sdk/`) — `CapabilityBuilder`,
  `ProviderBuilder`, `TransportBuilder`, `AuthBuilder` and
  `ConfigBuilder`, each producing the **existing** runtime model rather
  than a new type. `build()` validates and raises with the whole problem
  list, so a bad permission scope surfaces while the provider is being
  written rather than at first connect. The dataclasses stay public and
  directly constructible — the builders are a convenience, not a gate.
- **Registry helpers** — `register_provider` validates metadata and
  config *together* before anything enters the registry;
  `expose_capabilities` is all-or-nothing, so a batch with one bad entry
  never leaves the server half-published.
- **Validation framework** (`core/mcp/sdk/validation.py`) —
  `ValidationReport` / `ValidationIssue` with stable codes and
  ERROR/WARNING severity, plus validators for capabilities, provider
  metadata, provider config, transport config, authentication and
  **registry consistency**: the cross-object checks (a transport nothing
  registered, an auth method no strategy implements, a scope still
  awaiting a grant) that no single model can make about itself.
- **`jarvis mcp` developer CLI** (`infrastructure/cli/mcp_cli.py`) —
  `status`, `validate`, `list`, `inspect`, `capabilities`, `transports`,
  `providers`, `auth`, `connections`, with `--json` and `--config`.
  Dispatched from `main.py` before the run-mode parser, so inspecting an
  install never launches it.
- **Example implementations** (`core/mcp/sdk/examples.py`) — a
  capability, provider, config, transport and auth strategy, all
  self-contained and all imported by tests, so they cannot rot the way a
  code sample in a document does.
- **`MCPDiagnostics`** (`core/mcp/diagnostics.py`) — one read-only
  aggregator over every MCP subsystem, including `inspect_provider`,
  which answers "why will this provider not work" across registration,
  connection, authentication and health in a single call.
- Read-only REST: `GET /api/v1/mcp/diagnostics`, `GET /api/v1/mcp/validate`.
- DI singleton `mcp_diagnostics`, resolved by both the CLI and the REST
  layer.

### Changed
- `AuthBuilder` coerces a string method to `AuthMethod`, so
  `AuthBuilder("bearer_tokn")` fails on the typo rather than several
  calls later.
- `routes/mcp.py` documented as complete and deliberately read-only;
  provider *management* endpoints land with M11's first real provider.

### Fixed
- Stale comment on `TRANSPORT_TYPES` claiming only `in_process` had a
  shipped implementation — Task Group B shipped the other four.
- Dead `SessionState` import in `core/mcp/auth/manager.py`, left by Task
  Group D.

### Security
- **Diagnostics and the CLI expose no credential.** Every read goes
  through `MCPAuthManager.public_snapshot` / `status`, which carry
  metadata only. Asserted against raw serialized output — the full
  diagnostics report, every CLI command in both formats, and the REST
  response text — rather than a parsed field, so a leak through an
  unexpected key cannot slip past.
- **Read-only by construction.** Nothing in the diagnostics aggregator
  or the CLI connects, authenticates, installs or mutates; a test runs
  every read twice with the world captured either side to prove that
  inspecting changes nothing.
- `AuthBuilder` redacts its secret in `repr`/`str`, the same rule
  `Credential` follows.

### Notes
- **Final Runtime Review** found no duplicate registry, lifecycle
  manager, permission system, health system or authentication system.
  One `PermissionModel`, one `HealthMonitor` collector named `mcp`, one
  `MCPAuthManager`, one `CredentialStore`; four registries each holding
  a distinct kind of thing. Full findings in `MASTER_ROADMAP.md`'s Task
  Group E addendum.
- **M10.5 is closed** across five task groups, `0.16.0`–`0.20.0`. Two
  acceptance criteria remain 🟡 and are named with where they land:
  Agent Trace integration for MCP tool calls, and a server-side network
  listener — both M11.
- 137 new tests across six files; suite 1296 → 1433, all passing. mypy
  266 → 266 unchanged; ruff category list identical to the baseline's 22
  (`F401` improved 3 → 2).

## [0.19.0] — M10.5 Task Group D, Authentication & Provider Integration Foundation

The authentication framework every future MCP provider uses.
Infrastructure only: **no real providers**, no vendor code, and **no
OAuth flow** — that needs an authorization server and a callback
endpoint, neither of which this task group ships.

### Added
- **`AuthMethod`** vocabulary — `api_key`, `bearer_token`,
  `personal_access_token`, `oauth2`, `client_credentials`, and `none`
  (a real state: a local stdio peer needs no credential, and modelling
  that honestly avoids a fake empty credential standing in for it).
- **`Credential`** — access/refresh tokens, expiry, scopes, provider id,
  account id and encryption metadata. Frozen, so a failed refresh cannot
  leave a half-updated credential behind.
- **`CredentialStore`** — encrypted at rest via the existing Fernet
  helpers, in the existing `config/` convention. Rotation-ready: each
  record carries the `key_id` that encrypted it, and `rotate()` re-writes
  every record under a new key.
- **`AuthStrategyRegistry`** + `StaticTokenStrategy` / `NoAuthStrategy` —
  one strategy per method, in a registry a future method plugs into.
- **`ProviderSession`** — per-provider authentication state, counters and
  runtime status.
- **`MCPAuthManager`** — authenticate / refresh / revoke / validate /
  expire / reconnect, plus the permission bridge and the health payload.
- **`mcp.auth_changed`** relay event carrying an `action` field for all
  eight documented transitions.
- Read-only REST: `GET /api/v1/mcp/auth`, `/auth/methods`,
  `/auth/{provider}`, `/auth/{provider}/status`.
- DI singletons `mcp_credential_store`, `mcp_auth_strategies`,
  `mcp_auth_manager`.

### Security
- **Tokens are never exposed.** `Credential` redacts its own `repr`/`str`;
  storage and public serializers are separate methods so "safe to show"
  is a deliberate choice, not something to remember. Tests assert against
  raw REST response text, raw event payloads, the raw health snapshot and
  the raw on-disk file.
- **Refuses plaintext persistence.** Unlike `ApiCenterService` (which
  writes plaintext when no key is configured — acceptable for mostly
  non-secret API metadata), this store raises rather than writing a token
  unencrypted, and writes no file at all. In-memory operation still works,
  with the caveat recorded on the session, so an unconfigured install can
  authenticate for the session and simply will not remember it.
- **Revoking clears the tokens**, not just a flag — a revoked credential
  still holding its secret is a credential waiting to leak.

### The permission bridge
Two independent gates, deliberately not conflated: the **JARVIS-side**
scope the operator granted (M9's `PermissionModel`, namespaced
`mcp:<provider_id>`) and the **provider-side** scope the token actually
carries. `authorize_capability` names which gate refused, because the
two call for completely different fixes. No new permission vocabulary
and no second permission store.

### Reused, not duplicated
`utils/crypto.py`'s Fernet helpers, the `config/` storage convention,
M9's `PermissionModel`, `HealthMonitor.register_collector` (expiry
detection rides the existing poll rather than a second timer), the
`EventBus`, and the DI singleton pattern. M9's `SessionManager` is
untouched — it owns *user* sessions; this owns *provider* sessions.

### Deferred
The OAuth2 and client-credentials flows (listed in the vocabulary and
reported as unsupported rather than half-implemented); login and OAuth
callback endpoints; write endpoints; every vendor integration (M11).

### Testing
101 new tests across five files, including on-disk encryption
verification, a restart round trip, both permission gates, expiry,
refresh, revoke, reconnect and failure paths, and an end-to-end suite
through the real DI container with events verified over the real
WebSocket relay. mypy 266 → 266, unchanged, zero errors in any new file;
ruff category list identical to the baseline's 22.

## [0.18.0] — M10.5 Task Group C, MCP Provider Framework

The generic framework every future MCP integration plugs into **without
modifying the MCP runtime**. Infrastructure only: **no real providers**,
no OAuth, no authentication, no vendor code — those are Task Group D and
M11.

### Added
- **`IMCPProvider`** (`core/interfaces/mcp.py`) — a transport-independent
  provider port whose six lifecycle methods mirror `IService` exactly,
  plus `suspend`/`resume`, the two moves an integration genuinely needs
  that a service does not.
- **`ProviderMetadata` / `ProviderConfig`** — inert, validated
  dataclasses separating *what a provider is* from *how this install
  runs it*, so a deployment can move a provider stdio → websocket
  without editing the provider. Config carries `enabled`, transport,
  runtime options, and reconnect/retry/heartbeat policies.
- **`MCPProviderRegistry`** — register/unregister/lookup/enumerate plus
  `discover()` filtered by transport, capability, state, protocol,
  permission scope and enabled-ness, combining with AND. Registration
  is **inert**: no transport built, no subprocess spawned — which is
  what makes discovery side-effect free.
- **`MCPProviderManager`** — install/initialize/connect/disconnect/
  suspend/resume/shutdown/remove, with fault-isolated batch operations
  (`connect_all` never lets one provider's failure stop another's).
- **`TransportBackedProvider`** — the generic implementation covering
  every "point at an MCP server with this transport config" case, which
  is every integration M11 currently anticipates.
- **`mcp.provider_changed`** relay event carrying an `action` field for
  all eight documented transitions, plus the resting `state` — the two
  genuinely differ for `resumed`, which lands in `connected`.
- Read-only REST: `GET /api/v1/mcp/providers` (with the registry's
  discovery filters as query params), `/providers/{id}`,
  `/providers/{id}/health`, `/providers/{id}/metadata`.
- DI singletons `mcp_provider_registry` and `mcp_provider_manager`.

### Reused, not duplicated
Connection management delegates to Task Group A's `MCPClientRuntime`;
transport construction to Task Group B's `TransportFactoryRegistry`;
permissions to M9's `PermissionModel` (namespaced `mcp:<provider_id>`,
**no new scope vocabulary** — a provider may only request scopes the
plugin platform already defines); health to
`HealthMonitor.register_collector`; shutdown ordering to
`RuntimeManager` hooks. No second registry, lifecycle manager, health
subsystem or permission system.

### Security note
`ProviderConfig.as_dict()` reports option **key names only, never
values** — those will carry credentials once M11's providers exist, and
the reporting surface is built for that now rather than retrofitted.

### Deferred
Real providers, authentication and OAuth (Task Group D); GitHub, Gmail,
Slack, Calendar, Drive and every other vendor integration (M11);
create/update/delete provider endpoints.

### Testing
84 new tests across five files, including a full end-to-end lifecycle
against a **real stdio peer subprocess** through the real DI container
and real `PermissionModel`, with lifecycle events verified over the real
WebSocket relay. mypy 266 → 266, unchanged, zero errors in any new file;
ruff category list identical to the baseline's 22.

## [0.17.0] — M10.5 Task Group B, MCP Transport Layer & Runtime Connectivity

Fills the seam Task Group A left: all four transports the milestone
names are now real. **Still not the whole milestone** — no provider
integration ships, and OAuth/cloud sync remain M11's scope.

### Added
- **Stdio transport** — spawns a peer process, speaks newline-delimited
  JSON-RPC over its stdin/stdout, and shuts it down gracefully (close
  stdin, wait, escalate to kill).
- **WebSocket transport** — persistent outbound JSON-RPC over
  `websockets`. Distinct from `RuntimeWebSocketHub`, which serves
  JARVIS's *own* event relay inbound; they share a wire technology and
  nothing else.
- **HTTP transport** — stateless JSON-RPC over POST, with an honest
  `connect` that distinguishes an unreachable host from a peer-level
  error (see Fixed).
- **IPC transport** — a Windows named pipe or a Unix domain socket, not
  loopback TCP: a TCP socket would occupy a port, be reachable by any
  local process, and carry none of the OS-level access control the real
  primitives do.
- `JsonRpcStreamChannel` — newline framing plus request/response
  correlation over an asyncio stream pair, shared by `stdio` and `ipc`
  (which differ only in how they obtain that pair). `websocket` does
  not reuse it — a WebSocket already delivers discrete messages.
- **Transport factory** — builds any transport from plain config and
  registers all five into Task Group A's registry at the DI composition
  root, which is exactly what that registry was left empty for.
- **Transport discovery/query** — `discover()`, `describe()`,
  `describe_all()` on the existing registry, backed by declarative
  traits so a transport can be described without constructing one.
- **`MCPHeartbeatMonitor`** — one loop over every connected peer
  (mirroring `HealthMonitor`, not a timer per peer), riding the
  `request` primitive rather than a new port method, so a future
  transport gets heartbeat for free. `ping` was registered on the
  server through Task Group A's own `register_method` seam.
- Four new relay events — `mcp.handshake_completed`,
  `mcp.negotiation_completed`, `mcp.transport_failed`, `mcp.heartbeat`
  — deliberately distinct: a transport failure is a connectivity
  problem, whereas a permission denial or negotiation rejection is the
  protocol working correctly.
- `MCPConnectionState.RECONNECTING`, so a subscriber can tell recovery
  from initial setup without tracking prior state.
- REST (still read-only) — `GET /api/v1/mcp/transports` now returns one
  descriptor per transport; `GET /api/v1/mcp/transports/{id}` adds the
  connections using it; `GET /api/v1/mcp/heartbeat` reports the last
  probe per peer without ever forcing one.

### Fixed
- `HttpTransport.connect` routed its reachability probe through
  `request`, which wraps every `httpx` failure as `MCPTransportError` —
  so an unreachable host was swallowed and the transport reported
  itself connected. Caught by a functional test against a real closed
  port; the probe now uses `httpx` directly, and only a genuine
  transport failure fails the connect.

### Reused, not duplicated
Reconnect, handshake, discovery and negotiation stay
`MCPClientRuntime`'s; permission enforcement stays
`MCPServerRuntime`'s; health rides `HealthMonitor.register_collector`;
lifecycle rides `RuntimeManager` hooks. No second connection manager,
no transport base class — every transport satisfies the Protocol
structurally.

### Deferred
Provider integrations, OAuth and cloud sync (M11); MCP tools surfaced
through the agent Tool Registry / Agent Trace; a server-side network
listener (Task Group B ships the outbound/client half of all four
transports); write endpoints for provider management.

### Testing
100 new tests across eight files, against **real** peers throughout: a
real subprocess for stdio, a real `websockets` server, a real HTTP
server, and a real named pipe / Unix socket for IPC. mypy 266 → 266,
unchanged, zero errors in any MCP file; ruff's category list identical
to the baseline's 22 after fixing the two genuinely-new findings this
pass introduced.

## [0.16.0] — M10.5 Task Group A, MCP & Integration Platform (core runtime)

The first implementation pass on M10.5. Ships the **MCP runtime
foundation only** — no network transport and no provider integration —
so the milestone stays 🟡 Active, not complete. Every piece plugs into
something that already exists rather than adding a parallel runtime.

### Added
- MCP Capability Registry -- `core/mcp/capabilities.py`, mirroring
  `SearchService`'s M10A provider-registry shape
  (`register`/`unregister`/`get`/`list_capabilities`), with one
  deliberate divergence: a duplicate capability name is an error unless
  `replace=True`, because a capability shadowing another's name would
  silently change what an existing permission grant authorizes.
- Transport abstraction -- `IMCPTransport` in `core/interfaces/mcp.py`
  plus `TransportFactoryRegistry` in `core/mcp/transport.py`.
  `stdio`/`websocket`/`http`/`ipc` are *named* in `TRANSPORT_TYPES` but
  deliberately **not implemented**; `GET /api/v1/mcp/transports`
  reports the known-versus-registered gap honestly. One reference
  transport ships: `InProcessTransport`, how JARVIS consumes its own
  MCP server.
- MCP Client Runtime -- `core/mcp/client.py`: connection management,
  handshake, capability discovery, health, and bounded-retry reconnect.
  Lifecycle only; no provider implementations.
- MCP Server Runtime -- `core/mcp/server.py`: capability exposure,
  permission enforcement, protocol dispatch
  (`initialize`/`capabilities/list`/`capabilities/call`, extensible via
  `register_method`), and an `IService`-shaped lifecycle.
- Capability negotiation -- `core/mcp/negotiation.py`: pure functions,
  no I/O. Version mismatch fails the negotiation; an unsupported kind
  or ungranted scope is rejected per-capability and never fails the
  connection. Graceful fallback to an older shared protocol revision.
- `mcp` WebSocket category on the existing Runtime relay --
  `mcp.connection_changed` (one relay name, `state` payload field),
  `mcp.capabilities_changed`, `mcp.permission_denied`.
- `infrastructure/api/routes/mcp.py` -- `GET /api/v1/mcp/status`,
  `/capabilities`, `/connections`, `/transports`. Read-only by design:
  registering/connecting/granting is a later task group's surface, so
  every route is a `GET` and the write endpoints land additively.
- `MCPSettings` (`JARVIS_MCP_*`) and DI wiring for all three runtimes.

### Reused, not duplicated
- **Permissions**: M9's `PermissionModel` outright — same store, same
  persisted grants, same audit log, same `PENDING`-until-granted
  default. MCP principals are namespaced `mcp:<client_id>` so an MCP
  peer and a plugin cannot collide while both stay in the one
  `pending()` queue. **No new permission vocabulary** — capabilities
  declare scopes from the existing `PERMISSION_SCOPES`.
- **Health**: `HealthMonitor.register_collector`, the extension point
  M9 built for exactly this and that nothing had used until now. One
  health channel, not a second.
- **Lifecycle**: plain DI singletons with their own `start`/`stop`, the
  same class `MemoryService`/`KnowledgeService` occupy. No new
  lifecycle manager, no background supervisor, no `RuntimeManager`
  change beyond registering hooks.

### Deferred (documented, not silently dropped)
- Network transports (`stdio`, `websocket`, `http`, `ipc`) -- later
  task groups; the registry seam is ready for each.
- Provider integrations, OAuth, cloud sync -- M11's scope throughout.
- MCP tools surfaced through the agent Tool Registry / Agent Trace --
  a later task group.
- Write endpoints for provider management -- Task Group B.

### Testing
89 new tests across seven files, covering the registry, negotiation,
transports, both lifecycles, permission enforcement against the *real*
`PermissionModel` on a real temp-file store, DI construction, the REST
surface, and the real WebSocket relay. mypy 266 -> 266, unchanged,
zero errors in any MCP file. Ruff's category list is identical to the
baseline's 22 categories (growth is entirely `PLC0415`, the established
lazy-import convention) after fixing the three genuinely-new findings
this pass introduced.

## [0.15.0] — M10B, Intelligence Layer (complete)

M10B extends the M10A Universal Search & Knowledge Platform rather than
introducing a parallel system: `IntelligenceService` mirrors
`KnowledgeService`'s exact architecture (same `database`/`event_bus`
constructor shape, same repository-per-session pattern, same lazy
event-import idiom), `IntelligenceRepository` mirrors
`KnowledgeRepository`, and Goal Manager registers into `SearchService`'s
existing provider registry as a fourth source (`GoalSearchSource`) with
zero changes to `SearchService` itself -- the extensibility M10A's
registry design was built for. No RuntimeManager changes, no new
lifecycle manager, no background scheduler.

### Added
- Goal Manager -- `Goal` (self-referential parent/child hierarchy) in
  `infrastructure/database/models.py`; `IntelligenceRepository` CRUD +
  hierarchy + progress + status + search; `IntelligenceService` auto-
  completes a goal at >=100% progress and publishes `goal.updated`
  (`action`: created/progress_updated/completed/deleted).
- Routine Learning -- deterministic, direct-observation reinforcement
  (not LLM-driven pattern mining): `Routine` rows keyed by
  hour-of-day/day-of-week wildcards, `IntelligenceRepository.
  reinforce_routine()` increments `observation_count` and confidence on
  a repeated observation; a routine only surfaces in suggestions once
  it crosses `_ROUTINE_SUGGESTION_MIN_OBSERVATIONS`.
- Preference Learning -- a structured `Preference` key-value store,
  separate from M3's freeform `MemoryType.PREFERENCE` memories; a
  `suggestion_boost_keyword` preference multiplies a matching
  suggestion's score, giving Predictive Suggestions a second,
  independent way to change from learned signal (plain keyword-boost
  logic, not an LLM reranker -- consistent with M10A's own deferred AI
  reranking).
- Context Awareness -- `IntelligenceService.get_context_signals()`
  (hour of day, day of week, recent memory snippets via
  `MemoryService.browse()`, active conversation id); intentionally
  *not* wired into the agent graph's `context_engine.py` node, since
  it answers a different question (time/activity signals for
  suggestions) than that node's LLM-prompt context assembly. No
  location signal -- no location provider exists anywhere in the
  codebase yet, documented rather than faked.
- Predictive Suggestions -- `IntelligenceService.predict_suggestions()`
  combines due-soon goals, reinforced routines, and the preference-
  boost pass into a single ranked list.
- Daily Briefing -- `IntelligenceService.generate_daily_briefing()`,
  on-demand only, publishes `briefing.generated`. **Automatic scheduled
  delivery is explicitly deferred**, the same gap M10A left with
  Scheduled Reflection: M7's Scheduler (Phase 6) does not exist yet
  (`SchedulerSettings` has been declared for forward compatibility only
  since Phase 1) -- this route/tool is the only way to produce one
  today.
- Agent integration -- `agents/tools/intelligence_tools.py`
  (`create_goal`/`list_goals`/`update_goal_progress`/`get_suggestions`/
  `get_daily_briefing`).
- `infrastructure/api/routes/intelligence.py` -- `POST/GET /api/v1/goals`,
  `GET /api/v1/goals/{id}`, `PATCH /api/v1/goals/{id}/progress`,
  `POST /api/v1/goals/{id}/complete`, `DELETE /api/v1/goals/{id}`,
  `GET /api/v1/intelligence/context|suggestions|briefing`,
  `POST/GET /api/v1/intelligence/preferences`. Same Bearer auth +
  envelope convention as `routes/knowledge.py`.
- `goal`/`briefing` WebSocket categories on the Runtime WebSocket relay
  -- `goal.updated`, `briefing.generated`.
- Universal Search -- `GoalSearchSource` registered as a fourth
  provider (`memory`, `knowledge`, `goals`, `commands`).

### Deferred (documented, not silently dropped)
- Automatic scheduled Daily Briefing delivery -- needs M7's Scheduler
  (Phase 6), not started; Daily Briefing is on-demand only today.
- Location-aware Context Signals -- no location provider exists in the
  codebase.
- AI reranking of Predictive Suggestions -- plain keyword-boost logic
  only, matching M10A's own deferred AI reranking of search results.

### Permissions
No new scopes introduced. Reuses M10A's existing `memory.read`/
`memory.write` scopes; no `goal.read`/`goal.write` introduced.

### Testing
936/936 tests passing (+48), zero regressions -- one integration test
per Acceptance Criterion (AC1 goal persistence + progress tracking over
REST and the real WebSocket relay, AC2 a learned routine measurably
changing a future Predictive Suggestion, AC3 Daily Briefing generation
relayed over the real WebSocket), each against a real temp-file SQLite
database and the real DI container. One pre-existing M10A test
(`test_search_returns_envelope`) asserted an exact 3-source set; updated
to the now-correct 4-source set rather than treated as a regression, since
Goal Manager registering a fourth provider is the exact extensibility
the Search Provider Registry was designed for. mypy diffed against a
clean baseline via `git stash -u`: 266 -> 266, byte-for-byte unchanged
after removing 14 genuinely-unnecessary `type: ignore` comments from
`intelligence_service.py`. Ruff findings proportional to the
pre-existing accepted baseline (665 -> 720, +55, entirely `PLC0415`
lazy-import lines matching `KnowledgeService`'s already-accepted
pattern) -- zero new categories introduced.

## [0.14.0] — M10A, Universal Search & Knowledge Platform (complete)

Unlike M10, M10A's own declared dependencies (M3 Memory Platform, M5A
Agent Orchestrator exposure) were both already shipped, so this
milestone was buildable to near-full completion in one pass. Every new
component extends an existing one rather than introducing a parallel
system: `RuntimeManager`, `ServiceManager`, `MemoryService`,
`ChromaVectorStore`, `AgentOrchestrator`, Context Engine, `EventBus`,
the Runtime WebSocket Hub, `PluginRegistry`, and the Tool Registry are
all reused as-is. **One key feature is explicitly deferred, not
dropped:** File Search needs M11B's File Manager surface, which
doesn't exist yet.

### Added
- Knowledge Graph / Relationship Graph -- `KnowledgeEntity` /
  `KnowledgeRelationship` / `KnowledgeEntityMemory` in the existing
  `infrastructure/database/models.py`; `KnowledgeRepository` mirrors
  `MemoryRepository`'s shape. LLM-driven entity/relationship
  extraction reuses the agent nodes' existing JSON-decision pattern
  (relocated to `jarvis/utils/llm_json.py` so `services/` could reuse
  it without creating a `services -> agents` dependency;
  `agents/prompting.py` re-exports both names unchanged).
- Persistent Memory -- reuses `MemoryService.set_pinned` rather than a
  second durability mechanism.
- Reflection Foundation -- `KnowledgeService.learn_from_recent_memories()`,
  on-demand only (REST or agent tool), never a scheduled background
  job.
- Correction / scoped Learning (Acceptance Criterion 3) --
  `KnowledgeService.correct()` supersedes the prior relationship and
  inserts a higher-confidence replacement rather than deleting
  history.
- Universal Search / Search Provider Registry --
  `services/search_service.py`'s `SearchService` owns
  `register_source`/`unregister_source`/`get_sources`
  (`core/interfaces/search.py`'s `ISearchSource` protocol); three
  sources registered today (`MemorySearchSource`,
  `KnowledgeSearchSource`, `CommandSearchSource` -- agent tools +
  live-read plugin commands). `SearchResult` is deliberately
  extensible: `confidence`/`reason` fields exist now, unpopulated, for
  a future AI-reranking milestone.
- ChromaDB integration -- reuses the single existing collection,
  tagged `record_type: "knowledge_entity"` metadata; no second vector
  store.
- Agent integration -- `agents/tools/knowledge_tools.py`
  (`ask_knowledge`/`search_knowledge`); `context_engine.py` gained an
  optional `knowledge` parameter, closing M10's own documented
  Context Engine knowledge-graph deferral.
- `infrastructure/api/routes/knowledge.py` -- `POST /api/v1/search`,
  `GET /api/v1/knowledge/entities/{name}`, `GET /api/v1/knowledge/ask`,
  `POST /api/v1/knowledge/correct`, `POST /api/v1/knowledge/learn`,
  `GET/POST /api/v1/knowledge/export|import`. Same Bearer auth +
  envelope convention as `routes/plugins.py`/`routes/devtools.py`/
  `routes/agent.py`.
- `memory`/`knowledge` WebSocket categories on the Runtime WebSocket
  relay -- `memory.updated`/`memory.recalled` finally realize the
  category `docs/ARCHITECTURE.md` §6 has documented as a target since
  before the Milestone 9 managers existed; `knowledge.entity_updated`/
  `knowledge.correction_applied` are new. `MemoryService` gained an
  optional `event_bus` constructor parameter to publish these.

### Deferred (documented, not silently dropped)
- File Search -- needs M11B's File Manager surface (not started).
- AI reranking -- `SearchResult.confidence`/`.reason` exist but are
  unpopulated.
- Scheduled Reflection -- `learn_from_recent_memories()` is on-demand
  only; M7 Scheduler integration is future work.
- A full, general-purpose Learning Engine -- `correct()` is a scoped
  primitive, not that engine.

### Permissions
No new scopes introduced. Plugin access reuses M9's existing
`memory.read`/`memory.write` Plugin SDK scopes.

### Testing
888/888 tests passing (+49), zero regressions -- one integration test
per Acceptance Criterion (AC1 `ask()` synthesis, AC2 export/import
round-trip, AC3 correction relayed over the real WebSocket, AC4
Universal Search spanning ≥2 real source types), each against a real
temp-file SQLite database and the real DI container. mypy diffed
against a clean baseline via `git stash -u`: 266 -> 266, byte-for-byte
unchanged after two real fixes in `knowledge_service.py`. Ruff
findings proportional to the pre-existing accepted baseline -- zero
new categories left unresolved.

## [0.13.0] — M10, AI Orchestrator (partial -- buildable-now scope)

Milestone 10 formally depends on M10A (Universal Search & Knowledge
Platform) and M14 (Authorization Engine), neither of which has started.
Rather than block, this release ships the full subset of M10 buildable
without them -- extending M5A's `AgentOrchestrator` graph directly, no
rewrite -- and documents the M10A/M14/M16-dependent remainder as
explicitly deferred, the same "Completed / Deferred with a documented
reason" discipline this project has applied since the M0-M9 audit.
**M10 is not 100% complete; see Deferred below.**

### Added
- Intent Engine -- `agents/nodes/intent_classifier.py`, a new node
  before `planner` classifying the request into `tool_use` /
  `direct_answer` / `clarification_needed` with a confidence score.
  Diagnostic only in this release (does not yet gate graph routing).
- Context Engine (scoped) -- `agents/nodes/context_engine.py`, assembles
  context from M3 Memory before planning. The M10A knowledge-graph half
  of Context Engine is deferred (see below); this is the M3-only subset
  that's real today.
- Parallel tool dispatch -- Milestone 10 Acceptance Criterion 1, also
  absorbing M7 Phase 3's deferred cross-tool-parallelism scope.
  `tool_selector` gained a `tool_parallel` decision shape alongside the
  existing `tool`/`final` ones; `tool_executor` dispatches independent
  calls concurrently via the existing `gather_with_concurrency`, bounded
  by `AgentSettings.max_parallel_steps` (declared in M7, unread by any
  code until now). The single-tool path is unchanged, byte-for-byte.
- Permission Validation (interim) -- Milestone 10 Acceptance Criterion 3.
  `agents/permission.py`'s `AgentPermissionGate` + a new
  `permission_validator` node inserted between tool selection and
  execution: the one enforcement point every proposed tool call (single
  or parallel) now passes through, replacing the pre-M10 gap where only
  `run_automation` had any permission awareness at all, and that only
  internal to `AutomationService`. Interim and explicitly documented as
  such -- M10's own spec routes this through M14's Authorization Engine
  "once that milestone ships"; `AgentPermissionGate` is a single, narrow
  class so that swap means replacing its `authorize()` body, not the
  graph wiring. `AgentSettings.confirm_required_tools` (default
  `{"run_automation"}`) is the interim policy.
- Real token-level streaming -- Milestone 10 Acceptance Criterion 2.
  `AgentOrchestrator.stream()` now yields real per-token output from
  `ILLMProvider.stream()` for the dominant path (an answer composed from
  tool results), via a second, responder-less compiled graph variant
  (`build_agent_graph(..., include_responder=False)`) and a prompt
  builder (`agents/nodes/responder.py`'s `build_final_response_prompt`)
  shared with the non-streaming path so the two can't drift. One path
  remains a documented, scoped exception: `tool_selector`'s "final"
  shortcut (no tool needed) still composes its answer inside a JSON
  decision object and replays it in the pre-M10 chunked style, since
  token-streaming JSON-embedded text cleanly would mean restructuring
  tool selection itself.
- Decision Engine -- `responder` node gained `response_mode`
  (`"direct"` / `"composed"`) in `AgentState`, per M10's description of
  it as "the responder node's successor, deciding final response shape
  and routing."
- `agent.step` added to the Runtime WebSocket API's event relay
  (`core/lifecycle/runtime_ws_hub.py`) -- real-time Agent Trace
  visibility over the same `/api/v1/ws` transport M9 built, not a
  second channel.
- `infrastructure/api/routes/agent.py` -- `POST /api/v1/agent/invoke`
  (blocking, `{data, meta}` envelope) and `POST /api/v1/agent/stream`
  (real token-level Server-Sent Events -- a documented, scoped exception
  to the envelope rule, the same way `/api/v1/sessions` already is).
  Same `Depends(get_current_session)` Bearer auth as `routes/plugins.py`
  / `routes/devtools.py`.

### Fixed
- None -- Task Group D/E's Windows architecture-normalization fix
  shipped in 0.12.0; no regression found in this release.

### Deferred (documented, not silently dropped)
- Context Engine's knowledge-graph half -- needs M10A (not started).
- Learning / Feedback closing through M16's Reflection Engine -- needs
  M16 (not started).
- Permission Validation's final form routed through M14's Authorization
  Engine -- needs M14 (not started); `AgentPermissionGate` is the
  interim single enforcement point in the meantime.
- Intent Engine gating graph routing (vs. diagnostic-only today) --
  revisit once M10A/M10B give the classifier real signal to act on.
- `tool_selector`'s "final" shortcut path's real token streaming -- see
  Added, above.
- PySide6 Agent Trace view / React frontend wiring to `/api/v1/agent` --
  M8's own remaining phases, unchanged by this release.

### Testing
839/839 tests passing (unit + integration), zero regressions -- up from
815 in 0.12.0 (+24: node/permission/route unit tests, three new
orchestrator integration tests exercising parallel dispatch, permission
denial, and real streaming end-to-end). Ruff/mypy findings proportional
to the pre-existing accepted baseline; zero new categories introduced.

## [0.12.0] — M9, Task Group E (Developer Platform Tools) — closes out Milestone 9

The last of M9's modules. **Milestone 9 (Runtime & Core Services) is
now 100% complete** across all five task groups (A: Runtime Core: B:
Service/Session/Configuration Manager, Health Monitor, Runtime
WebSocket API; C: Reliability; D: Plugin Platform; E: this release).
Architecture unchanged -- Python + FastAPI + Tauri, no migration.

### Added
- `core/devtools/` -- Debug Console + Live Logs (`debug_console.py`,
  a real loguru sink with a bounded, filterable buffer), Performance
  Profiler (`performance_profiler.py`, real time-series history over
  `HealthMonitor`'s existing poll-tick snapshots), State Inspector
  (`state_inspector.py`, a unified view combining `ServiceManager`,
  `PluginRegistry`, and `RuntimeManager`'s own real state), API
  Inspector (`api_inspector.py`, a real Starlette middleware recording
  this app's own `/api/v1/*` request/response metadata -- method,
  path, status, duration only, never bodies or headers).
- `infrastructure/api/auth.py` -- the real `Depends(get_current_session)`
  Bearer-auth dependency and `{data, meta}` `Envelope` helper
  `docs/ARCHITECTURE.md` section 5 has referenced by name since Task
  Group B but that no route had ever actually used until now.
- `infrastructure/api/routes/plugins.py` -- the real "Plugin
  Marketplace Foundation" + Permission Management REST API: full
  plugin lifecycle (list/get/enable/disable/install/uninstall/update),
  permission management (per-plugin grant/deny/revoke, pending queue,
  audit log), and marketplace browse/search/categories/get/reviews --
  all thin routes over Task Group D's real domain classes. The first
  real resource routes to follow `docs/ARCHITECTURE.md` section 5's
  full contract (envelope + Bearer auth), resolving the two documented
  exceptions `/api/v1/sessions` needed.
- `infrastructure/api/routes/devtools.py` -- REST reads over the new
  `core/devtools/` components, plus Plugin Diagnostics (one combined
  view: a plugin's status, health, recent related logs, and permission
  audit trail).
- Fourteen new `plugin.*`/`devtools.*` relay categories: eleven
  `plugin.*` events (Task Group D's event types, now actually relayed
  -- see the 0.11.0 entry) plus `devtools.log_captured` extend
  `RuntimeWebSocketHub.EVENT_TYPE_NAMES`.
- `DevToolsSettings` (`core/config/settings.py`) --
  `debug_console_enabled`, `debug_console_level`,
  `debug_console_max_entries`, `performance_history_size`,
  `api_inspector_enabled`, `api_inspector_max_records`.
- 74 new unit/integration tests across nine files, including a real
  end-to-end test (`tests/integration/test_devtools_platform_e2e.py`)
  proving the new REST API genuinely drives Task Group D's
  `PluginRegistry`/`PermissionModel` *and* that the result is relayed
  over the real Runtime WebSocket API -- install over REST, watch
  `plugin.installed`/`plugin.load_failed` arrive over the socket; grant
  a permission over REST, watch `plugin.permission_granted` arrive;
  enable over REST, watch `plugin.loaded`/`plugin.enabled` arrive.

### Fixed
- **A real, Windows-first-breaking bug in Task Group D**, found by
  these same end-to-end tests running for the first time against a
  genuine Windows machine (Task Group D's own tests only ever used a
  hardcoded-`"x86_64"` test double): `platform.machine()` reports
  `"AMD64"` on Windows, not `"x86_64"` -- every plugin manifest's
  *default* `supported_arch` list (`["x86_64", "arm64", "x86"]`) was
  silently rejecting every real Windows x86_64 plugin install.
  `infrastructure/platform/adapter.py`'s `DefaultPlatformAdapter.info()`
  now normalizes the OS-reported architecture string to this project's
  own canonical vocabulary at the Platform Abstraction Layer boundary
  -- exactly what that layer exists for.

### Changed
- `app.py` gained `_register_task_group_e_hooks`: Debug Console and
  Performance Profiler bookend every other startup/shutdown hook
  (startup priority -1, one before Configuration Manager; shutdown
  priority 8, one after Crash Recovery's mark-clean) so they capture as
  much of the real lifecycle as observability tooling reasonably can.
- `core/di/container.py` gained `debug_console`, `performance_profiler`,
  `state_inspector`, and `api_inspector` providers.
- `infrastructure/api/fastapi_server.py` mounts the two new routers and
  conditionally attaches the API Inspector middleware.

### Known limitations (documented, not silently implied otherwise)
- Debug Console's real-time relay publishes one `EventBus` event per
  captured log line via `publish_nowait`'s no-running-loop fallback
  (loguru's `enqueue=True` sink runs on its own background thread) --
  a real per-line cost, acceptable for a developer-only, opt-in tool,
  not free.
- Performance Profiler's "per-service" data is honestly process-wide
  (service **state** is per-service; CPU/memory are not -- the same
  limit `core/plugins/sandbox.py` already documents for the same
  underlying `psutil.Process` reason).
- API Inspector never records request/response bodies or headers
  (secrets-handling boundary, `docs/ARCHITECTURE.md` section 17) --
  method/path/status/duration only.

Full suite: 815 passed (up from 741 at 0.11.0), zero regressions;
frontend unaffected (this release is backend-only). mypy/ruff/black
diffed against a clean pre-task-group `git stash -u` baseline: zero
new findings outside the same accepted `PLC0415` lazy-import pattern
every prior task group's own tests already carry (every other finding
category's count is byte-for-byte unchanged).

## [0.11.0] — M9, Task Group D (Plugin Platform)

Closes out M9's Plugin Platform module in full, preserving the
original scope unchanged. Architecture unchanged -- Python + FastAPI +
Tauri, no migration. Only Task Group E (Developer Platform Tools)
remains open in M9.

### Added
- `core/plugins/` -- the full Plugin Platform: `sdk.py` (`IPlugin`
  lifecycle hooks, the fixed 10-scope permission vocabulary, a
  hand-rolled semver/range comparator), `manifest.py` (`PluginManifest`,
  extended with the Universal Compatibility fields `supported_os`,
  `supported_arch`, `required_capabilities`, `min_jarvis_version`),
  `loader.py` (discovery, Kahn's-algorithm dependency ordering, version/
  platform compatibility checks, real hot reload), `sandbox.py`
  (in-process fault-isolated + timeout-bounded execution, plus an
  opt-in out-of-process `multiprocessing` tier with `psutil`-based
  resource-budget monitoring), `extension_api.py` (`PluginContext`:
  permission-gated filesystem/network/hotkeys/notifications,
  unrestricted events/commands scoped to the plugin's own declared
  surface, config, platform capability queries), `permissions.py` (the
  real `IPermissionChecker` -- least-privilege declare -> pending ->
  grant/deny, persisted and audited), `registry.py` (`PluginRegistry`:
  enable/disable/install/uninstall/update with real rollback support),
  `store.py` (directory/`.zip` package staging, SHA-256 integrity
  checks, real Ed25519 signature verification), `marketplace.py`
  (`IPluginRepository` abstraction, `LocalPluginRepository`, search/
  categories, in-memory ratings/reviews).
- `core/interfaces/platform.py` + `infrastructure/platform/adapter.py`
  -- a new Platform Abstraction Layer for Universal Compatibility;
  Windows is the only implemented adapter today, but nothing above
  `IPlatformAdapter` branches on OS directly.
- Fourteen new events (`core/events/events.py`): `PluginDiscoveredEvent`,
  `PluginLoadedEvent`, `PluginLoadFailedEvent`, `PluginUnloadedEvent`,
  `PluginCrashedEvent`, `PluginEnabledEvent`, `PluginDisabledEvent`,
  `PluginPermissionGrantedEvent`, `PluginPermissionDeniedEvent`,
  `PluginInstalledEvent`, `PluginUninstalledEvent`, `PluginUpdatedEvent`,
  `PluginCustomEvent`, `PluginNotificationEvent` -- eleven of which
  (excluding the plugin-authored `PluginCustomEvent`/
  `PluginNotificationEvent`, and `PluginCrashedEvent`, not yet published
  anywhere) are relayed over the Runtime WebSocket API.
- `PluginSettings` (`core/config/settings.py`) -- `enabled`,
  `sandbox_mode`, `hook_timeout_seconds`, `max_cpu_percent`,
  `max_memory_mb`, `allow_unsigned_packages`, `marketplace_index_path`.
- `tests/fixtures/plugins/hello_world/` -- a real reference plugin
  (registers a slash command and a hotkey) used by a new end-to-end
  integration test, `tests/integration/test_plugin_platform_e2e.py`,
  proving this module's own acceptance criterion against the real
  Loader -> Sandbox -> Permission Model -> Registry stack, including
  the full least-privilege permission workflow.
- 199 new unit/integration tests across twelve files.

### Changed
- `app.py` gained `_register_task_group_d_hooks`, wiring `PluginRegistry`
  into `RuntimeManager` as the outermost layer over an already-running
  core: plugins start last (priority 12, after Task Group C's 10-11)
  and stop first (priority -1, before Task Group B's own chain). A
  no-op when `settings.plugins.enabled` is false.
- `core/lifecycle/runtime_ws_hub.py`'s `EVENT_TYPE_NAMES` gained eleven
  `plugin.*` entries.
- `core/config/constants.py`/`paths.py` gained `PLUGINS_SUBDIR` and a
  `plugins_dir()` helper, included in `ensure_runtime_dirs()`.
- `core/di/container.py` gained `platform_adapter`, `plugin_loader`,
  `plugin_sandbox`, `permission_model`, `plugin_registry`,
  `plugin_store`, and `marketplace` providers.

### Known limitations (documented, not silently implied otherwise)
- Process-isolated plugins receive a minimal `MinimalPluginContext` in
  `on_load`, not the full in-process `PluginContext` -- a live
  `EventBus` reference cannot cross a process boundary by value. A real
  IPC-relayed Extension API for that tier is future work.
- The `network` permission scope is a declaration check only -- this
  platform does not yet mediate or quota a plugin's actual outbound
  HTTP calls.
- No hosted, signed Plugin Store index exists yet (`LocalPluginRepository`
  is the real, complete v1 implementation of the roadmap's own "no
  hosted infra for v1" design); a `GitHubPluginRepository`/
  `CloudPluginRepository` is a second `IPluginRepository`
  implementation away, not a redesign.
- Ratings/reviews (`InMemoryReviewStore`) do not persist across a
  restart and have no real user-identity system beyond a
  caller-supplied reviewer string.
- The permission-approval *workflow* (declare/pending/grant/deny,
  persisted and audited) is real; an interactive approval UI is Task
  Group E's Developer Platform Tools to build.

Full suite: 741 passed (up from 542 at 0.10.0), zero regressions;
frontend: 293 passed, unaffected (this release is backend-only).
mypy/ruff/black diffed against a clean pre-task-group `git stash -u`
baseline: zero new findings outside the same pre-existing,
already-accepted `providers.Singleton` annotation and `PLC0415`
lazy-import patterns `MASTER_ROADMAP.md` §15 documents.

## [0.10.0] — M9, Task Group C (Background Task Manager, Crash Recovery, Resource Manager)

Closes out M9's Reliability module in full (Health Monitor's
foundational slice already shipped under Task Group B). Follows the
Aug 2026 roadmap reconciliation pass (docs-only, no source changes).
Architecture unchanged -- Python + FastAPI + Tauri, no migration.

### Added
- `core/lifecycle/background_task_manager.py` -- `BackgroundTaskManager`:
  a bounded-concurrency (`asyncio.Semaphore`) task queue with per-task
  fault isolation. `submit()`/`cancel()`/`stop()` (graceful drain). A
  done-callback fallback handles a task cancelled before its
  coroutine's first scheduling turn -- Python never enters an unstarted
  coroutine's own body to run its `except CancelledError`, so `_run()`'s
  in-body handler alone can't catch that case.
- `core/lifecycle/crash_recovery.py` -- `CrashRecoveryManager`: a
  "mark dirty at start, mark clean at end" on-disk marker
  (`runtime_state.json`, existing `config_dir` JSON-config-store
  convention) detects an unclean previous shutdown and publishes
  `CrashRecoveredEvent`. Does not claim to auto-respawn a crashed
  process -- real, separate, future work.
- `core/lifecycle/resource_manager.py` -- `ResourceManager`: CPU/
  memory budget tracking (new `ResourceSettings`,
  `core/config/settings.py`), subscribing to `HealthMonitor`'s existing
  `HealthUpdatedEvent` instead of polling `psutil` a second time.
  Publishes `ResourceBudgetExceededEvent` only on the transition into
  violation.
- Five new events (`core/events/events.py`): `TaskStartedEvent`,
  `TaskCompletedEvent`, `TaskFailedEvent`, `CrashRecoveredEvent`,
  `ResourceBudgetExceededEvent` -- all relayed over the Runtime
  WebSocket API (`runtime.crash_recovered`,
  `task.started/completed/failed`, `resource.budget_exceeded`).
- 29 new tests across three files covering bounded concurrency, fault
  isolation, both cancellation code paths (mid-run and
  pre-first-scheduling-turn), crash detection across independent
  marker-file instances, corrupt-marker resilience, and
  budget-transition-only event publishing.

### Changed
- `app.py` gained `_register_task_group_c_hooks`, wiring all three new
  managers into `RuntimeManager`: Crash Recovery's dirty-check runs
  immediately after Configuration Manager (before Service Manager);
  Background Task Manager and Resource Manager join at the end of
  startup. Shutdown reverses this, with Crash Recovery marking the run
  clean *last of all*. Task Group B's own five shutdown-hook priorities
  were renumbered (0-4 -> 2-6, in-place, no migration concern) to make
  room.
- `core/lifecycle/runtime_ws_hub.py`'s `EVENT_TYPE_NAMES` gained five
  more entries for the events above.

### Fixed (Project Completion Audit, ahead of M9 Task Group D)
- **Version drift** — `pyproject.toml`, `Settings.app_version`, and
  `src/jarvis/__version__.py` were still `"0.5.2"` despite this
  changelog already being at `0.10.0`; all three now read `"0.10.0"`
  in lockstep. The same drift this project's own `MASTER_ROADMAP.md`
  §15 previously recorded as "Resolved" during the M5A pass had
  quietly recurred.

### Documentation (Project Completion Audit)
- Full-repository sweep for TODOs, placeholders, mocks, deprecated
  code, doc/implementation mismatches, and missing tests across M0–M9.
  Found: three stale "M8" labels on Plugin-Platform-related
  `MASTER_ROADMAP.md` §15 Future items (relabeled M9 Task Group D --
  scope never changed, only the label, from before the Aug 2026
  retitling); §16's development-order table using the pre-reconciliation
  🟢/no-symbol convention on the M7/M8/M9 rows (now 🟡 Active,
  consistent with §2/§14); `docs/ARCHITECTURE.md` §5 still saying "no
  FastAPI layer exists yet" (false since M9 Task Group B); two
  undocumented, real exceptions to §5's own contract
  (`/api/v1/sessions`'s response isn't wrapped in the `{data, meta}`
  envelope; the real health router mounts at `/api/health`, not
  `/api/v1/health`, since M0) -- both now documented in place rather
  than left as silent drift; `README.md`'s "Roadmap" section still
  claiming only M0–M2 and the core of M3 were implemented, and its
  project-layout diagram missing `frontend/` entirely.
- `MASTER_ROADMAP.md` §15 Pending gained a consolidated "M8/M9-era
  items" entry cross-referencing M8's Deferred Backlog and M9 Task
  Group B/C's own Future Work notes, plus the two new API-contract
  exceptions and the health-router prefix mismatch above -- so §15
  remains the one place every open item in the repository is tracked,
  not just M0–M7's.
- No new source-code behavior changed beyond the version-string fix
  above; `pytest`/`mypy`/`ruff`/`black` re-verified against the same
  baseline M9 Task Group C already validated.

## [0.9.0] — M9, Task Group B (Service/Session/Configuration Manager, Health Monitor, Runtime WebSocket API)

Second and final Runtime Core deliverable, closing out every M9
Runtime Core bullet Task Group A deferred. Architecture unchanged from
Task Group A's own addendum -- Python + FastAPI + Tauri, no migration;
this entry documents implementation only.

### Added
- `core/interfaces/service.py` -- `IService` Protocol
  (`docs/ARCHITECTURE.md` §8) made real code for the first time, plus
  `HealthStatus`/`ServiceStatus` frozen dataclasses.
- `core/lifecycle/service_manager.py` -- `ServiceManager`: dependency-
  ordered startup/shutdown, `restart()`, health polling, fault
  isolation. Wraps `ConversationService`/`ChatService`/`MemoryService`/
  `ThemeService` in thin `IService` adapters (composition, not a
  retrofit of the wrapped services themselves).
- `core/lifecycle/session_manager.py` -- `SessionManager` and a new
  `runtime_sessions` table (`infrastructure/database/models.py`,
  `RuntimeSessionRepository`): persisted session creation/close,
  dangling-session recovery after an unclean shutdown, optional
  (nullable) links to `Conversation.id` and the agent orchestrator's
  LangGraph `thread_id`.
- `core/lifecycle/configuration_manager.py` -- `ConfigurationManager`:
  live `reload()` restricted to a `SAFE_RELOAD_SECTIONS` allowlist
  (`ui`, `voice_announce`, `memory`, `update`, `dev_mode`), publishing
  `ConfigurationUpdatedEvent` with the changed dotted keys only.
- `core/lifecycle/health_monitor.py` -- `HealthMonitor`: non-blocking
  `psutil`-based CPU/RAM/uptime/startup-duration/service-health/
  restart-count polling, `HealthUpdatedEvent` per tick,
  `register_collector()` extension point for future metrics.
- `core/lifecycle/runtime_ws_hub.py` + `infrastructure/api/routes/
  runtime_ws.py` -- `RuntimeWebSocketHub`, the first real
  implementation of `docs/ARCHITECTURE.md` §6's WebSocket standard at
  `/api/v1/ws`: envelope, 30s heartbeat, `resume`/60s replay buffer,
  relaying all eleven new events (`runtime.started/ready/stopping/
  shutdown`, `service.started/stopped/failed`,
  `configuration.updated`, `session.created/closed`,
  `health.updated`).
- `infrastructure/api/routes/sessions.py` -- `POST`/`GET`/`DELETE
  /api/v1/sessions` -- issues the session id used as the WebSocket
  `token` query param, the real `Depends(get_current_session)`
  mechanism §5/§6 reference.
- `infrastructure/api/embedded_server.py` -- `EmbeddedApiServer` embeds
  the FastAPI app inside the existing PySide6/qasync loop so the
  WebSocket relay is reachable from the app's one real running process.
- Nine new events (`core/events/events.py`): `RuntimeStartedEvent`,
  `RuntimeShutdownCompleteEvent`, `ServiceStartedEvent`,
  `ServiceStoppedEvent`, `ServiceFailedEvent`, `SessionCreatedEvent`,
  `SessionClosedEvent`, `ConfigurationUpdatedEvent`,
  `HealthUpdatedEvent`.
- 58 new tests across six files covering dependency ordering, restart
  behavior, failure isolation, session persistence/recovery, safe
  live-reload, non-blocking health polling, and the real FastAPI
  WebSocket transport end-to-end (auth, relay, resume/replay) via
  `TestClient` against a real SQLite database.

### Changed
- `core/lifecycle/runtime_manager.py`'s `RuntimeManager` gained an
  optional `event_bus` constructor parameter (every existing zero-arg
  call site unaffected) so `startup()`/`shutdown()` publish
  `RuntimeStartedEvent`/`RuntimeShutdownCompleteEvent` at the very
  start/end of each sequence.
- `app.py`'s `_run_gui()` wires all five new managers into
  `RuntimeManager` via a new `_register_task_group_b_hooks` method
  (split out to keep `_run_gui`'s statement count readable) in
  deterministic order -- Configuration Manager -> Service Manager ->
  Session Manager -> Health Monitor/WebSocket relay/embedded API
  server -> Application Ready -- shutdown reverse. The `memory_policies`
  startup hook that lived directly in `app.py` since Task Group A moved
  into `MemoryServiceAdapter.start()`.
- `infrastructure/api/fastapi_server.py`'s `create_app()` now accepts
  an optional DI `Container`, mounting the new session/WebSocket
  routers only when one is supplied.

### Documentation (roadmap reconciliation pass, ahead of M9 Task Group C)
- `MASTER_ROADMAP.md` §2 ("Current status") was stale since before M8
  even started (`0.5.2`, "In progress: M7", no mention of M8/M9) --
  corrected to `0.9.0` with real M7/M8/M9 status.
- `MASTER_ROADMAP.md` §14 (version timeline): every milestone now
  carries exactly one of four states (✅ Completed, 🟡 Active, 🟠
  Deferred, 🔴 Planned) instead of a `🟡` used ambiguously for both
  "active" (M8) and "fully unstarted" (M10-M23B).
- `MASTER_ROADMAP.md` §8 M8 gained a **Deferred Backlog** subsection
  (Notification Center, Context Menu system, Background Task Manager,
  Workspace views, Window management, Responsive/DPI/Multi-monitor,
  Settings & User Profiles, Developer Mode's 9 read-only viewers,
  Premium UI Polish, Optimization & QA) -- verified against the actual
  repository (`notification-layer.tsx`/`context-menu-layer.tsx` are
  real, empty, reserved anchors; `background-tasks.store.ts` is
  display-only), not assumed from prior notes. **M8 remains explicitly
  not 100% complete.**
- `MASTER_ROADMAP.md` §8 M9's Reliability/Plugin Platform/Developer
  Platform Tools modules gained explicit Task Group C/D/E labels.
- `IMPLEMENTATION_ROADMAP.md` gained a matching §6 Deferred Backlog
  (checklist-level detail) and explicit Task Group C/D/E entries under
  §5; Phase 3's checklist gained the three previously-undocumented
  items (Notification Center, Context Menu system, Background Task
  Manager) it was missing.
- No source code changed in this pass -- `pytest`/`mypy`/`ruff`/`black`
  re-verified clean against the same baseline M9 Task Group B already
  validated.

## [0.8.0] — M9, Task Group A (Runtime Manager & Application Lifecycle)

First real M9 (Runtime & Core Services) deliverable, consuming the
Version Timeline's reserved `0.8` slot. Follows an architecture review
the user requested and then explicitly closed: keep Python + FastAPI +
Tauri as the official architecture, unchanged — see
`docs/MASTER_ROADMAP.md`'s own changelog addendum for the full
reasoning. Scopes only Runtime Core's first two bullets (Runtime
Manager, Application Lifecycle), not all of M9.

### Added
- `stt_provider.preload()`-style startup work now registers with
  `RuntimeManager` instead of a hand-written `try`/`except` block in
  `app.py` -- memory-policy enforcement and Whisper preload both
  converted, matching the exact "must never block boot" guarantee
  their existing comments already promised, now enforced by
  `RuntimeManager` itself.
- `AppReadyEvent`/`ShutdownRequestedEvent` (`core/events/events.py`)
  now genuinely publish on the real `EventBus` -- previously declared
  but unused "placeholder examples for milestone authors."
  `AppReadyEvent` fires once every registered `RuntimeManager` startup
  hook has run; `ShutdownRequestedEvent` fires at the start of
  `MainWindow._graceful_quit()`, before any resource releases.
- `tests/unit/test_runtime_manager.py` -- extends the original
  `test_shutdown_manager.py` one-for-one (regression coverage for the
  rename) plus new startup-side and cross-direction-independence
  coverage.

### Changed
- `core/lifecycle/shutdown_manager.py`'s `ShutdownManager` (Milestone
  5.5) renamed and generalized to `core/lifecycle/runtime_manager.py`'s
  `RuntimeManager` -- the shutdown-side API (`register`/`unregister`/
  `shutdown`) is behavior-unchanged, just renamed alongside a new,
  symmetric startup-side API. The DI container's `shutdown_manager`
  provider is renamed to `runtime_manager`; every real call site
  across `src/` and `tests/` updated to match.

## [0.7.5] — M8 Phase 4, Task Group L (Dashboard widget drag-and-drop)

Fifth and final task group of the Premium UI & Voice Experience
initiative. Ships real mouse-driven drag-to-reorder for Dashboard
widgets, additive alongside the existing Move up/down buttons.

### Added
- `stores/dashboard-layout.store.ts`'s `reorderPeers(peerIds, pinned)`
  -- applies a full drag-produced permutation of one pin group, leaving
  the opposite pin group and hidden widgets' positions untouched.
  Additive alongside the existing `moveWidget()`; both operate on the
  same `order` array.
- `features/dashboard/dashboard-grid.tsx` -- two `motion/react`
  `Reorder.Group` instances (one per pin group, `Reorder.Item` per
  widget) with a dedicated drag handle (`dragListener={false}` +
  `useDragControls()`) so dragging doesn't conflict with the card's own
  five buttons or its real content. Dragging only ever reorders a
  widget among its own pin-group peers, matching the Move buttons'
  existing constraint.
- `e2e/dashboard-widgets.spec.ts` -- real, mouse-driven Playwright
  verification (`page.mouse`) that the drag gesture actually reorders
  widgets and persists to the real store, plus a regression test
  confirming Move up/down still work unchanged.

## [0.7.4] — M8 Phase 4, Task Group K (Accessibility settings)

Fourth task group of the Premium UI & Voice Experience initiative.
Ships a real Settings > Accessibility page for the preferences `[0.7.2]`
and `[0.7.3]` already made real, and adds a genuine third one.

### Added
- `features/settings/settings-page.tsx` -- the Settings module's real
  route element, replacing its `PlaceholderRoute`. An Accessibility
  section with three real, working toggles (Skip startup animation,
  Reduced motion, Disable glass effects), the first non-Developer-Mode
  surface for these preferences.
- `reducedMotion` -- a new, real, persisted preference: an app-level
  override on top of the OS-level `prefers-reduced-motion` `MotionConfig`
  already honors, for users whose OS setting doesn't (or can't)
  express it.
- `providers/app-providers.tsx`'s `AccessibleMotionConfig` feeds the
  real preference into `MotionConfig`'s own `reducedMotion` prop, so
  every declarative Motion animation in the app (`DesktopShell`'s
  stagger reveal, `JarvisLogo`'s pulse, etc.) respects it automatically.
- Developer Mode's Startup Preview panel gained a matching "Reduced
  motion" toggle alongside its existing two.

### Changed
- `stores/startup-preferences.store.ts` renamed to `stores/
  accessibility-preferences.store.ts` (`useStartupPreferencesStore` ->
  `useAccessibilityPreferencesStore`, persist key `jarvis.startup-
  preferences` -> `jarvis.accessibility-preferences`) -- it now backs
  real, app-wide UI, not just the startup sequence, and the old name
  had become misleading.

### Fixed
- **`startup-gate.tsx` and `voice-waveform-renderer.tsx` ignored the
  new `reducedMotion` preference entirely.** Both called Motion's
  public `useReducedMotion()` hook, which only ever reads the OS-level
  media query and completely ignores `MotionConfig`'s own
  `reducedMotion` context value -- the app preference had zero effect
  on either real call site. Fixed by switching both to Motion's own
  `useReducedMotionConfig()`, the hook Motion itself uses internally to
  combine the OS query and the `MotionConfig` value.
- `e2e/app-shell.spec.ts` was still seeding the old, now-stale
  `jarvis.startup-preferences` localStorage key, silently falling back
  to the real ~4.2s startup animation on every test run instead of
  skipping it. Updated to seed the renamed key.

## [0.7.3] — M8 Phase 4, Task Group J (Glass design system)

Third task group of the Premium UI & Voice Experience initiative.
Ships real glassmorphism on the three surfaces the brief names —
Sidebar, Card, Command Palette — all wired to the `disableGlassEffects`
preference `[0.7.2]` already shipped, making it genuinely app-wide for
the first time.

### Added
- `hooks/use-glass-effects.ts` -- `useGlassEffectsEnabled()`, a thin
  wrapper around the real, persisted `disableGlassEffects` preference
  so UI primitives can read it under a name that makes sense outside a
  startup context.
- `components/layout/desktop-shell.tsx` -- a subtle, static ambient
  glow behind the shell (two blurred accent/primary blobs, `aria-hidden`,
  skipped entirely when glass effects are disabled) so the new glass
  surfaces have real visual content to blur.
- Sidebar: `bg-card/70 backdrop-blur-xl`, falling back to solid
  `bg-card`.
- `components/ui/card.tsx`: a conservative `bg-card/85 backdrop-blur-md`
  on the shared primitive every dashboard widget/dialog/panel already
  builds on -- lighter blur than Sidebar/Command Palette since Cards
  hold dense text at every size.
- Command Palette: `bg-popover/70 backdrop-blur-2xl`, scoped to
  `CommandDialog`'s own `DialogContent` override in `components/ui/
  command.tsx` -- the shared `Dialog`/`Command` primitives other real
  dialogs render through are untouched.

### Changed
- `stores/startup-preferences.store.ts`'s `disableGlassEffects` now
  gates every real glass surface in the app, not just the startup
  sequence's own glow -- one real preference, not a second one that
  could drift out of sync.

## [0.7.2] — M8 Phase 4, Task Group I (Startup Experience & Lazy Loading)

Second task group of the Premium UI & Voice Experience initiative.
Reuses `[0.7.0]`/`[0.7.1]`'s Voice String as the centerpiece of a new
cinematic startup sequence, per the brief's explicit instruction not to
redesign or replace it.

### Added
- **Startup sequence** (`components/startup/startup-sequence.tsx`) --
  a choreographed ~4.2s animation: energy point, ripple, logo assemble/
  pulse (`components/startup/jarvis-logo.tsx`), morph into the Voice
  String, Voice String activation and expansion, then a center-outward
  glass reveal. Drives the real `voice-state.store.ts` (`wake` then
  `idle`) at the relevant phases -- the Voice String shown during
  startup is the exact same store-driven component used everywhere
  else. The reveal is a real animated CSS `mask-image:
  radial-gradient(...)` (`useMotionTemplate`/`useMotionValue`), not an
  opacity approximation. No startup text ever renders -- only an
  `sr-only role="status"` string for assistive tech.
- `core/startup-orchestrator.ts` -- the real work the animation hides.
  `STARTUP_TASKS` maps the brief's High/Medium/Low tiers onto this
  codebase's actual registration calls (`registerCoreStatusBarItems`,
  `registerCoreDashboardWidgets`, `registerPlaceholderModules`), moved
  here from `main.tsx`. `low` has no real task yet -- left honestly
  empty rather than padded with a fabricated delay. `runStartupSequence()`
  is idempotent (caches its own promise), so any number of callers
  share one real execution.
- `components/startup/startup-gate.tsx` -- reveals the real app only
  once both the real orchestrator work and the animation finish.
  Skips straight to the dashboard when the new persisted
  `skipStartupAnimation` preference (`stores/startup-preferences.store.ts`)
  is set, or when `useReducedMotion()` reports a system preference.
- Developer Mode's **Startup Preview** section
  (`features/developer/startup-preview.tsx`) -- replays the real
  `StartupSequence` on demand and toggles both real preferences, for
  QA without restarting the app.
- `components/layout/desktop-shell.tsx` gained an additive staggered
  fade/rise for its Sidebar/Header/Status-Bar/Dock regions on first
  mount -- since the real dashboard only mounts once startup is truly
  done, this stagger doubles as the brief's "Dashboard Reveal"
  sequence.

### Fixed
- **React `<StrictMode>` double-invoke hang**: `StartupGate`'s
  initializing effect runs twice in development by design; the second
  call to `registerPlaceholderModules()` threw (a module can't
  register with `ApplicationRegistry` twice), and the resulting
  unhandled promise rejection silently stalled the reveal forever.
  Fixed by making `runStartupSequence()` idempotent at its source
  rather than guarding each call site.
- `StoreProvider` was missing the new `useStartupPreferencesStore` from
  its persisted-store hydration gate, which could let `StartupGate`
  read the stale default before rehydration completed. Added it to the
  `persistedStores` array.

## [0.7.1] — Voice String revision (real-time multi-bar waveform)

Same-day revision of `[0.7.0]`'s Voice String, once the Premium UI &
Voice Experience brief asked specifically for a "premium real-time
voice waveform" (many animated bars, matching modern voice-assistant
quality) rather than a single sine-path line.

### Changed
- **Voice String** is now a glassmorphism panel of 40 independently-
  animated bars, not a single SVG path. Split into
  `components/voice/voice-waveform-renderer.tsx` (the pure renderer --
  zero store dependency, accepts `voiceState`, `microphoneLevel`,
  `ttsLevel`, `intensity` as props) and `components/voice/voice-
  string.tsx` (now just the thin layer wiring real store state in) --
  direct answer to the brief's "separate rendering from state
  management" and "design it so the future voice backend can stream
  real audio amplitudes directly into the renderer" requirements.
- Each bar derives its height from one shared `useTime()` clock via
  `useTransform` (one requestAnimationFrame loop feeding many cheap
  derived values, bound straight to the DOM, `transform`-only --
  GPU-compositable, no layout shifts) rather than 40 independent RAF
  subscriptions.
- Per-state "envelope" shapes implement the brief's state-by-state spec
  directly: Wake's center-outward pulse, Thinking's slow traveling
  wave (distinct from Listening), Listening/Speaking's reactive look
  (two overlapping deterministic sine terms per bar -- a fixed
  per-bar phase seed, not `Math.random()`, for "smooth interpolation,
  no jitter" rather than actual jitter).
- Glass-panel styling (blurred translucent background, soft
  state-colored bloom) uses this app's existing semantic color tokens,
  not new hardcoded hex values, for the brief's "cyan/blue gradient"
  look.

### Added
- `stores/voice-audio-levels.store.ts` -- real `microphoneLevel`/
  `ttsLevel` fields, always `0` today (no audio pipeline exists),
  additively boosting the renderer's procedural ambient motion once
  real, with bars nearer the panel's center reacting more strongly.
- Developer Mode's Voice State Preview panel now drives the raw
  renderer directly, with manual mic/TTS level sliders (writing to the
  real store above) and a local intensity control, so the renderer's
  full prop surface can be QA'd before either real backend exists.

## [0.7.0] — M8 Phase 4, Task Group H (Voice State Architecture)

First task group of the Premium UI & Voice Experience initiative.

### Added
- **Voice String** (`components/voice/voice-string.tsx`) -- JARVIS's
  voice identity, replacing the Orb concept (never built in this
  frontend to begin with). A continuous animated wave whose color,
  speed, and amplitude communicate Idle/Wake/Listening/Thinking/
  Speaking/Success/Error -- no visible state label ("Listening...")
  ever renders; an `aria-label` carries the state name for screen
  readers only. Respects `useReducedMotion()` directly, since it's a
  continuous `useTime()`/`useTransform` loop, not a discrete `animate`
  transition `MotionConfig`'s app-wide `reducedMotion="user"` already
  covers.
- `core/voice-state-machine.ts` -- a real, validated state machine
  (mirrors `core/module-lifecycle.ts`'s established pattern: fixed
  states, a transition graph, a typed `InvalidVoiceStateTransitionError`
  on an illegal jump) for the full 7-state set.
- `stores/voice-state.store.ts` -- the single source of truth. Starts
  and stays `idle`: no real voice backend exists yet
  (`core/interfaces/voice-integration.ts` only covers command
  bindings; no WebSocket voice event relay exists). The one real entry
  point, `transition()`, is exactly what a future voice pipeline will
  call.
- **Live Transcript** (`components/voice/live-transcript.tsx` +
  `stores/voice-transcript.store.ts`) -- streaming word-by-word,
  fades 4s after the last word. Starts and stays empty until a real
  STT stream exists.
- **Developer Mode's Voice State Preview** panel
  (`features/developer/voice-state-preview.tsx`) -- manually drives or
  auto-cycles the real `useVoiceStateStore`, for animation QA only.
  Disabled by default, never an end-user surface. Manual buttons only
  ever offer legal next states, so a click can never hit the store's
  own validation and throw.
- `voice` module now has a real route element
  (`features/voice/voice-page.tsx`), replacing its `PlaceholderRoute`.

## [0.6.4] — M8 Phase 3, Task Group G (Command Palette)

### Added
- **Command Palette** -- fills in `components/layout/command-palette-
  layer.tsx`, the DesktopShell region reserved since Phase 3's own
  foundation pass. Opens on `Ctrl+K` **and** `Ctrl+Shift+P`
  (`providers/command-palette-provider.tsx`) -- the roadmap's canonical
  binding is `Ctrl+Shift+P`, but the header's Search button has
  visually promised "Ctrl+K" since Phase 1; both are honored so neither
  promise is silently broken.
- "Navigate" entries: real, registry- and enablement-driven module
  links (`ApplicationRegistry` + `ModuleEnablementStore`), the same
  data Sidebar/Dock already read.
- "Commands" entries: `getAllCommandPaletteEntries()`
  (`core/interfaces/navigation-interface.ts`, M8 Phase 2) -- confirmed
  real, already-wired infrastructure (every module's mount/unmount
  already calls `registerNavigation()` via `BaseApplication`), not dead
  code. **No new `ContributionRegistry` instance was built for this** --
  reusing the mechanism that already exists rather than duplicating it.

### Fixed
- `components/ui/command.tsx`'s `CommandDialog` never wrapped its
  `children` in cmdk's own `<Command>` root -- any `CommandInput`/
  `CommandList`/`CommandItem` rendered inside it threw at render time
  ("Cannot read properties of undefined (reading 'subscribe')"), since
  there was no cmdk context above them. Never caught before because
  nothing had used `CommandDialog` until this task group. Fixed at the
  primitive.
- Added a `scrollIntoView` no-op stub to `test/setup.ts` -- jsdom
  doesn't implement it and cmdk's list uses it internally; same
  category as the existing `ResizeObserver`/`matchMedia` stubs already
  there.

## [0.6.3] — M8 Phase 3, Task Group F (Dashboard Widget Grid)

### Added
- **Dashboard (Home) view** is now a real page
  (`features/dashboard/dashboard-grid.tsx`), replacing
  `PlaceholderRoute` for the `home` module -- registry- and
  enablement-driven, the same pattern Sidebar/Dock/Status Bar
  establish. Widgets support add/remove, resize (4 fixed grid
  footprints: 1×1, 2×1, 1×2, 2×2), move (reorder among same-pinned-
  state peers), pin/unpin, and layout export/import as one validated
  JSON document.
- `stores/dashboard-layout.store.ts` (new, persisted) -- the grid's own
  preference layer (visible/size/order/pinned per widget id), kept
  separate from `DashboardWidgetRegistry`'s "what widgets exist," the
  same split `dock.store.ts`/`application-registry.ts` already
  establish.
- `DashboardWidgetContribution` gained `isCore`, matching
  `StatusBarContribution.isCore`'s reasoning (Core JARVIS's widgets
  register under the reserved `moduleId: "core"`, which isn't a real
  `ApplicationRegistry` entry an enablement check could resolve
  `isCore` from otherwise).
- Core JARVIS's 4 built-in widgets, all backed by real state: **Notifications**
  (the notification center), **Recent Activity** (a merged timeline of
  notifications and background task completions/failures, sorted by
  real timestamps), **Quick Actions** (real navigation links to core
  modules), **System Status** (real connection status, background task
  state, and honest "Not configured" for AI Provider/Voice/Automation,
  reusing the exact same labels as the Status Bar via the new shared
  `lib/connection-status-display.ts`).
- `BackgroundTask` gained a `timestamp` field (set internally on every
  status transition, never caller-supplied) so Recent Activity has a
  real ordering signal.

### Fixed
- The root `.gitignore`'s Python-oriented `lib/`/`lib64/` patterns
  (unanchored) were silently matching `frontend/src/lib/` too --
  `icon-registry.ts`, `motion.ts`, and `utils.ts` had **never actually
  been committed to `origin/main`** despite being depended on
  throughout the frontend since Phase 1; a fresh clone would not have
  built. Anchored both patterns to the repo root (`/lib/`, `/lib64/`)
  and committed the previously-invisible files.

### Not shipped (documented, not faked)
- **Tasks, Calendar, and Notes widgets were not built.** No real
  backing store, data model, or backend endpoint exists anywhere in
  this codebase for any of the three -- a widget with a title but no
  real feature behind it would be exactly the fake/placeholder
  implementation this project's standing rule forbids. Each becomes a
  real widget once its own feature ships (see `MASTER_ROADMAP.md`'s
  Task Group F addendum for the reasoning and target milestones).
  `DashboardWidgetRegistry` places no cap on widget count, so this is
  additive later, not a rework.

## [0.6.2] — M8 Phase 3, Task Group E (Status Bar)

### Added
- **Status Bar** is now `ContributionRegistry`-driven -- a fourth named
  instance (`statusBarRegistry`, `core/interfaces/status-bar-interface.ts`)
  alongside Navigation and Dashboard Widgets, not a new bespoke
  registry. No hardcoded status items anywhere in
  `components/layout/status-bar.tsx`.
- Core JARVIS's 9 built-in items, registered through the same path a
  future plugin's own status item would use: left (Current Workspace,
  Active Module), center (Current Running Task, Background Task
  Progress), right (AI Provider, Voice Status, Automation Status,
  Internet/Offline, Notification Indicator). Six are real data today
  (`WorkspaceManager`, `background-tasks.store.ts`,
  `notifications.store.ts`, the existing WebSocket connection hook);
  three (AI Provider, Voice Status, Automation Status) have no real
  backend data source yet and honestly show "Not configured" rather
  than fabricated values.

### Changed
- `DashboardWidgetContribution.render` retyped from `() => unknown` to
  a real component reference, matching `StatusBarContribution.render`'s
  contract -- building an actual consumer (the Status Bar) clarified
  the correct shape: each contribution renders as its own element and
  manages its own reactivity, which calling a plain callback inside a
  `.map()` over a variable-length list cannot do without violating
  React's Rules of Hooks.

## [0.6.1] — M8 Phase 3, Task Group D (Dock) + Contribution Registry unification

### Fixed
- `DashboardWidgetRegistry`, added in `[0.6.0]`, was its own bespoke
  class mirroring `ApplicationRegistry`'s pattern -- exactly the
  "multiple unrelated registries" anti-pattern to avoid. Extracted the
  shared mechanism into `core/contribution-registry.ts`'s generic
  `ContributionRegistry<T>`; `DashboardWidgetRegistry` is now a thin
  named instance of it. `NavigationContribution`'s internal storage
  (previously its own raw `Map`) migrated onto the same class. Both
  public APIs are unchanged -- no consuming code needed to change.

### Added
- **Phase 3, Task Group D — Dock**: registry- and enablement-driven,
  same pattern as Sidebar (Task Group C) -- pinned modules only render
  if also registered *and* enabled; a pinned-but-disabled module
  disappears from the Dock. Active-state highlighting from
  `WorkspaceManager`, not the route. `routes/nav-items.ts` is now read
  by nothing in the app.
- Test coverage for `core/contribution-registry.ts` (the canonical
  suite every contribution-holding registry's own tests now stay thin
  against) and `core/interfaces/navigation-interface.ts` (had none
  before this pass).

## [0.6.0] — Milestone 8 (in progress): React Frontend Foundation & Desktop Workspace

Consolidated entry -- M8's earlier phases (React Foundation, Universal
Application Framework) and Phase 3's first three task groups shipped
across several prior sessions without individual `CHANGELOG.md`
entries; this is a single retroactive summary of where M8 actually
stands today, not a claim that everything below landed at once.
Milestone is **not** complete -- see `docs/IMPLEMENTATION_ROADMAP.md`
for the live, checkbox-level status.

### Added
- **Phase 1 — React Foundation**: `frontend/` scaffolded (React 19,
  TypeScript, Vite, Tauri shell), Tailwind + shadcn/ui + Radix + Motion
  + Lucide, design tokens ported from the real `Typography`/palette
  Python source, base layout components, React Router, Zustand store
  scaffold, API/WebSocket client architecture, Vitest + Playwright
  testing foundation.
- **Phase 2 — Universal Application Framework**: `BaseApplication`,
  `ApplicationRegistry`, `ModuleManifest`, `ModuleLifecycle`
  (TypeScript port of the backend `ModuleStateMachine`), Permission/
  Settings/Storage/Notification Frameworks, AI/Voice/Automation/API/
  Window/Navigation interfaces -- the framework every module (first-
  party or, eventually, plugin) is built on.
- **Phase 3, Task Group A — Foundation**: the 14 workspace modules
  converted from a static nav array into real, registered
  `ApplicationRegistry` entries.
- **Phase 3, Task Group B — Desktop Shell**: `DesktopShell`'s 8 named
  layout regions, `WorkspaceManager` (route -> real module mount/
  unmount lifecycle), Workspace Routing.
- **Phase 3, Task Group C — Dynamic Sidebar**: registry-driven
  Sidebar, initially with flat category grouping, then revised the
  same session per the UI Architecture Update review (below) to a
  minimal core taxonomy with a nested "AI" group and enablement
  gating.
- **UI Architecture Update** *(this session)*: `ModuleManifest.isCore`/
  `parentGroup` fields; `ModuleEnablementStore` (installed-vs-enabled
  state, distinct from registration); `DashboardWidgetRegistry` +
  `DashboardWidgetContribution` (foundation only -- no widget grid UI
  yet); Sidebar's default nav reduced to 7 core modules (Dashboard,
  AI [Conversation/Voice/Memory], Automation, Files, Settings), every
  other module (Browser, Coding, Finance, Smart Home, Calendar, Gmail,
  Spotify) now disabled by default and hidden until a user enables it.
  Full design in `docs/MASTER_ROADMAP.md` §8 M8/M9's Aug 2026 UI
  Architecture Update addendum.

### Fixed
- `ApplicationRegistry.getAll()` returned a fresh array on every call,
  which broke `useSyncExternalStore` consumers (`ModuleStateInspector`)
  with a real, reproduced-in-browser "Maximum update depth exceeded"
  crash once the registry held real data -- now cached, invalidated
  only on `register()`/`unregister()`.
- Sidebar's collapsed (icon-only) mode rendered every nav link with no
  accessible name at all (icon `aria-hidden`, label hidden) -- fixed
  with an explicit `aria-label` on every link, in both states.
- `Header`/`router.tsx` still read the retired `routes/nav-items.ts`
  static list after Sidebar moved off it, which would have shown
  stale labels ("Home" instead of "Dashboard") the moment Sidebar's
  taxonomy changed -- both now read `modules/module-definitions.ts`/
  `WorkspaceManager` directly, the same source Sidebar uses.

### Known gaps (tracked, not regressions)
- `components/layout/dock.tsx` is the one remaining reader of
  `routes/nav-items.ts` -- its own registry-driven rewrite is Phase 3
  Task Group D.
- Dashboard Widget Grid's actual UI (built-in widgets, drag/resize/
  pin, layout persistence) is foundation-only as of this entry -- see
  `docs/IMPLEMENTATION_ROADMAP.md` Phase 3.

## [0.5.2] — Critical Architecture Fix: DI container lazy loading

Out-of-band architecture fix — no roadmap change, no feature addition, no
API/interface change. Fixes the #1 Critical technical-debt item flagged by
the repository stabilization pass's performance baseline: `Container()`
construction cost ~2.5–2.9s, ~99% of which was import time, not
instantiation.

### Root cause
`dependency_injector`'s string-path provider form
(`providers.Singleton("dotted.path.Class", ...)`) resolves and imports its
target **eagerly, at class-declaration time** — contradicting
`container.py`'s own docstring claim that importing it "stays cheap and
side-effect-free." Most application services used this form. The worst
offender was `agent_orchestrator`, which pulled in
`jarvis.agents.graph` → LangGraph/LangChain/LangSmith (~1.6s alone) on
every `import jarvis.core.di.container`, whether or not the agent was ever
used in that process.

### Changed
- `src/jarvis/core/di/container.py`: converted 4 of 20 string-path
  providers to the existing `_build_*` lazy-callable pattern (already used
  by all 14 infrastructure adapters), each confirmed by direct measurement
  — not assumption — to justify the conversion:
  - `agent_orchestrator` (highest priority: ~1.6s, LangGraph/LangChain/
    LangSmith; confirmed never resolved during app boot in
    `app.py`/`main_window.py`, only on first agent/chat use)
  - `memory_service` (~1.07s; makes the cost conditional on
    `settings.memory.enabled` instead of always-paid)
  - `automation_service` (~1.07s; `Factory`-based, genuinely on-demand)
  - `conversation_service` (~0.89s; keeps bare `import container.py`
    cheap for tests/tooling)
  - The other 16 string-path services were measured and left unchanged —
    each within ~0.1s of the shared `Settings`+logger import floor the
    container pays regardless, so converting them would add boilerplate
    for no measurable benefit. See `docs/DEPENDENCY_INJECTION.md` §6 for
    the full before/after and the rule for classifying future services.
- `pyproject.toml`: added a `[tool.ruff.lint.per-file-ignores]` entry
  scoping `PLC0415` (import-not-at-top-level) off for `container.py` —
  the whole file's design requires function-local imports for laziness;
  same treatment already given to `PLE1205`/`N802` elsewhere in this
  config for the same "principled exception" reason.
- `docs/DEPENDENCY_INJECTION.md`: documented the two provider forms'
  opposite import timing, which providers are lazy today and why, and the
  measured before/after.
- Version bumped `0.5.1` → `0.5.2` — a PATCH release per
  `docs/MASTER_ROADMAP.md` §6's policy, not a milestone-driven MINOR bump.

### Performance (measured, same machine, back-to-back runs)
| Metric | Before | After | Change |
|---|---|---|---|
| `import jarvis.core.di.container` | 2.940s | 1.595s | **−45.7%** |
| `Container()` construction | ~4.19s\* | 1.735s | **−58.6%**\* |
| Resolve a cheap service (`settings_service`) | ~3.46s\* | 1.613s | **−53.3%**\* |
| RSS at that checkpoint | ~101MB\* | 55.5MB | **−45.1%**\* |
| Resolve `agent_orchestrator` (first AI/chat use) | 5.503s | 5.425s | ~unchanged (expected) |
| RSS after resolving `agent_orchestrator` | 106.1MB | 106.1MB | unchanged (expected) |

\*Measured via a controlled, verbatim pre-fix copy of the container run
back-to-back with the fixed version, since this is a from-source
(non-git) checkout with no prior commit to diff against.

The "first AI request" cost did not disappear — it correctly moved from
"paid unconditionally at every process start" to "paid once, on first
actual use," which is the intended effect of lazy loading, not a
regression.

### Verified
- Full regression suite: 402 tests collected (unchanged), exit code 0 on
  two independent full runs — zero failures, zero errors.
- `ruff`: `container.py` clean (0 findings). Repo-wide PLC0415 findings
  (446, across test files with function-local imports) confirmed
  pre-existing and unrelated via a controlled before/after comparison —
  out of scope for this fix.
- `black`: `container.py` unchanged, already formatted.
- `mypy`: `container.py` errors reduced 21 → 17 (confirmed via a
  controlled before/after comparison) — converting 4 providers to typed
  callables incidentally fixed 4 pre-existing `var-annotated` gaps that
  mypy cannot infer through the string-path form. Zero new errors.
  Remaining 17 are pre-existing, on providers this fix intentionally did
  not touch.
- `pip check`: no broken requirements.

## [0.5.1] — Security: `cryptography` dependency upgrade

Dependency-only patch release — no application code, feature, or
roadmap change. Follows the repository stabilization pass's security
review, which flagged `cryptography` 43.0.3 as carrying 5 known
vulnerabilities and recommended a dedicated upgrade pass rather than a
same-PR bump.

### Changed
- `cryptography` upgraded `43.0.3` → `48.0.1` (`pyproject.toml`,
  `requirements.txt`, `requirements-lock.txt`). Resolves all 5 known
  advisories against the previous version: `PYSEC-2026-35`,
  `PYSEC-2026-1284`, `PYSEC-2026-2141`, `GHSA-537c-gmf6-5ccf`, and one
  additional CVE fixed in an intermediate release
  (`CVE-2026-39892`, non-contiguous-buffer overflow, fixed in
  `46.0.7`). Confirmed via `pip-audit`: `cryptography` no longer
  appears in the vulnerability report (24 → 19 total findings across
  the repo, all 5 removed entries were `cryptography`'s).
  - Target version chosen deliberately below the very latest release
    (`50.0.0`, published the day before this upgrade, effectively
    unfield-tested) — `48.0.1` is the minimum version resolving every
    known advisory and has ~7 weeks of real-world usage.
  - Reviewed the full upstream changelog from `43.0.3` through
    `48.0.1`: every breaking change in that range (Python 3.8 support
    removal, X.509 CRL/elliptic-curve/OpenSSL-version changes, stricter
    key-loading error types) is in code paths this app never
    exercises. `utils/crypto.py` uses only `Fernet`/`InvalidToken`,
    whose API and on-disk token format are unaffected.
  - Version bumped `0.5.0` → `0.5.1` (`pyproject.toml`,
    `__version__.py`, `Settings.app_version`) — a PATCH release per
    `docs/MASTER_ROADMAP.md` §6's policy ("reserved for out-of-band
    fixes shipped between milestones"), not a milestone-driven MINOR
    bump.

### Fixed
- Regenerated the editable-install package metadata
  (`jarvis_os.egg-info`), which had gone stale after the Milestone 6
  version bump and was still advertising the old
  `cryptography<44.0,>=43.0` constraint — `pip` flagged this as a
  self-referential dependency conflict the moment `cryptography` was
  upgraded. `pip check` now reports no broken requirements.

### Verified
- Full regression suite: 402/402 passing, zero failures, zero errors
  (identical to the pre-upgrade baseline).
- `ruff`/`black`/`mypy`: identical finding counts to the pre-upgrade
  baseline (438 / 0 / 264) — zero new findings anywhere in the repo.
- Fernet round-trip (`test_api_center_service.py::test_secrets_are_encrypted_at_rest`,
  which encrypts with one service instance and decrypts with a fresh
  one to simulate an app restart) passes.
- Manual verification: key generation, `encrypt()`/`decrypt()`
  round-trip, invalid-key error handling, and invalid-token error
  handling all behave identically to before the upgrade; the Fernet
  token format (`gAAA...` prefix) is unchanged.

## [0.5.0] — Milestone 6: Vision & Multimodal (Architecture Layer)

See `MILESTONE_6_VISION_DELIVERY.md` for full detail. This release
ships M6's **provider-abstraction layer only** — the Ports & Adapters
plumbing, not real vision/OCR capability. No vision/OCR dependency
was added; no capture, OCR, or image-processing code exists yet.

### Added
- `IVisionProvider` / `IOCRProvider` ports (`core/interfaces/`) —
  mirror `ILLMProvider`'s shape (`name: str`, `async health()`),
  deliberately minimal until a real backend exists to validate a
  fuller method surface against.
- `VisionSettings` / `OCRSettings` — `enabled: bool = False` by
  default; `JARVIS_VISION_ENABLED` / `JARVIS_OCR_ENABLED` added to
  the Settings-UI writable key whitelist.
- `MockVisionProvider` / `MockOCRProvider` — the only concretes wired
  in; both honestly report `enabled=False, healthy=False` rather than
  simulating capability. New `infrastructure/vision/` and
  `infrastructure/ocr/` packages, each with a provider factory
  (no backend-selection logic yet — nothing to select between).
- `VisionService.status()` — reports both providers' health as a
  plain dict; no other methods exposed.
- `VisionProviderStatusEvent` — defined on the `EventBus`, matching
  `AgentStepEvent`'s shape; not yet published anywhere.
- Agent tool `vision_status` (`agents/tools/vision_tools.py`) —
  reports provider availability only, registered in
  `agents/tools/registry.py` behind the existing optional-service
  pattern.
- Developer Mode **Vision Status** section (status-only, no
  image/screenshot/OCR-text/camera-feed/trace content) and a real
  **Vision** Settings page (two toggles, clearly labelled
  "unavailable / not yet implemented," replacing the pre-existing
  placeholder page).
- `vision_provider`, `ocr_provider`, `vision_service` registered as
  DI Singletons.
- 92 new tests across 7 phases (interfaces, settings, mock providers,
  service, agent tool/orchestrator wiring, Developer Mode view,
  Settings page), all passing.

### Changed
- `AgentOrchestrator` gained one additive, backward-compatible
  optional constructor kwarg, `vision: VisionService | None = None`
  (mirroring how `chat`/`voice`/`system` were added in M5A), threaded
  into its existing `build_tool_registry()` call — required because
  that call has exactly one call site, inside `AgentOrchestrator`
  itself. Defaults to `None`; an orchestrator built exactly as before
  this release behaves identically (regression-tested).
- `core/di/container.py`'s `agent_orchestrator` Singleton now also
  receives `vision=vision_service`.
- Version bumped `0.4.0` → `0.5.0` (`pyproject.toml`,
  `__version__.py`, `Settings.app_version`), per this milestone's
  entry in `docs/MASTER_ROADMAP.md` §6 Versioning policy.

### Known limitations (see `MILESTONE_6_VISION_DELIVERY.md` for the full list)
- No real vision or OCR provider exists — both mock providers always
  report unavailable.
- No screen capture, camera capture, clipboard image support, or
  drag-and-drop image input.
- No Image Question Answering; no multimodal chat.
- `ChatMessage.content` remains `str`-only — the message-model fork
  needed for multimodal chat was deliberately left as an open
  decision for whenever real vision input is built, not resolved now.
- No image preprocessing, compression, or bounded temp storage (the
  already-scaffolded `paths.cache_dir()` hook remains unclaimed).

## [0.4.0] — Milestone 5-Agents: Agent Runtime (LangGraph)

See `MILESTONE_5_AGENTS_DELIVERY.md` for full detail.

### Added
- `AgentOrchestrator` (`agents/orchestrator.py`) — a real, compiled
  LangGraph `StateGraph`: `planner → tool_selector → tool_executor →
  critic → responder`, with a loop-back edge from critic to
  tool-selector for multi-step tasks and a hard `max_steps` stop.
  Previously every method raised `NotImplementedError`.
- Tool registry (`agents/tools/`) — `MemoryService`, `AutomationService`,
  `BrowserService`, `SystemService`, `VoiceService` and `ChatService`
  auto-exposed as `langchain_core` structured tools; tool *selection*
  is driven by structured-JSON prompts over the existing `ILLMProvider`
  port, not a second langchain-native chat-model port.
- SQLite checkpointer (`agents/checkpointer.py`,
  `langgraph-checkpoint-sqlite`) — a thread's agent state survives an
  app restart when `AgentSettings.checkpoint_enabled` is true; falls
  back to an in-memory saver otherwise.
- `SystemService.status()` — real `psutil`-backed CPU/memory/disk/
  process/uptime snapshot (was a `NotImplementedError` stub since
  Milestone 1).
- `AgentStepEvent` (`core/events/events.py`) and a new Developer Mode
  **Agent Trace** section (`ui/views/developer/agent_trace_view.py`) —
  run an ad-hoc prompt through the orchestrator and watch each graph
  step arrive live.
- Prompt-injection mitigation: tool output is now fenced with an
  explicit `<<<TOOL_OUTPUT>>>...<<<END_TOOL_OUTPUT>>>` marker plus an
  instruction telling the model never to treat that text as
  instructions (`agents/prompting.py`'s `UNTRUSTED_TOOL_OUTPUT_NOTICE`)
  — closes the gap flagged during the Milestone 5.5 audit before this
  runtime existed.
- `JARVIS_AGENT_MAX_STEPS` / `JARVIS_AGENT_TIMEOUT_SECONDS` /
  `JARVIS_AGENT_CHECKPOINT_ENABLED` added to the Settings-UI writable
  key whitelist.
- ~40 new tests (`unit/test_system_service.py`,
  `unit/test_agent_prompting.py`, `unit/test_agent_nodes.py`,
  `unit/test_agent_tools_registry.py`, `unit/test_agent_checkpointer.py`,
  `integration/test_agent_orchestrator.py`) and a new `ScriptedFakeLLM`
  test double.

### Fixed (found during pre-merge validation — see `AUDIT_REPORT_M5-AGENTS.md`)
- **Reliability**: the default agent configuration
  (`checkpoint_enabled=True`) crashed on the *first real graph
  invocation* with `AttributeError: 'Connection' object has no
  attribute 'is_alive'` — a real incompatibility between
  `langgraph-checkpoint-sqlite==2.0.11` and `aiosqlite>=0.21` (which
  dropped the `Thread`-based `Connection` class that method depended
  on). `open()`/`close()` alone never triggered it, which is why the
  original unit tests missed it; only found via a live end-to-end
  smoke run through the real DI container. Fixed by pinning
  `aiosqlite>=0.20,<0.21`; covered going forward by a new regression
  test, `test_invoke_with_real_sqlite_checkpointer`.
- Two pre-existing tests
  (`test_main_window_registers_shutdown_hooks_in_correct_order`,
  `test_developer_dashboard_builds_all_thirteen_sections` → renamed
  `..._fourteen_sections`) updated for this milestone's own intentional
  changes (a new shutdown hook, a 14th Developer Mode section) — not
  regressions, just stale hardcoded expectations.

### Changed
- Version bumped `0.3.0` → `0.4.0` (`pyproject.toml`, `__version__.py`,
  `Settings.app_version`) — closes the version-drift note tracked in
  `docs/MASTER_ROADMAP.md` §10 since Milestone 3.1.
- `Container.agent_orchestrator` now also receives `chat`, `voice`,
  `system` and `event_bus` (previously only `settings`, `llm`,
  `memory`, `automation`, `browser`).
- `AgentOrchestrator.stop()` registered with `ShutdownManager` at
  `PRIORITY_EARLY` (`ui/main_window.py`), alongside `voice_service`.

### Known limitations (see `MILESTONE_5_AGENTS_DELIVERY.md` for the full list)
- Vision tool deliberately deferred to Milestone 6.
- The existing Chat view still talks to `ChatService` directly; the
  agent is not yet wired into the primary chat UI.
- `stream()` re-chunks the fully-composed final answer rather than
  streaming real LLM tokens from inside the responder node.
- No per-step timings in the Agent Trace panel.
- `run_automation` never passes a confirmation callback — any action
  needing interactive confirmation is auto-denied rather than asked.

## [0.3.0] — Milestone 5.5 Production Stabilization Pass (unreleased)

Not a feature milestone -- a stabilization pass over Milestones 0-5,
following an evidence-based audit (see `AUDIT_REPORT_M0-M5.md`).

### Fixed
- **Reliability**: 55 sites across 22 files where a fire-and-forget
  async task had no stored reference and could be garbage-collected
  mid-execution -- root cause of "Task was destroyed but it is pending!"
  warnings seen throughout the test suite. Fixed via a shared
  `fire_and_forget()` helper (`jarvis.utils.async_utils`).
- **Reliability**: app shutdown (both the tray/menu Quit action and the
  OS window-close button) now releases every real resource
  (voice/browser/hotkeys/database) via a new `ShutdownManager`
  (`core.lifecycle.shutdown_manager`) instead of a hand-sequenced,
  partially-incomplete inline sequence. The window-close path previously
  bypassed resource cleanup entirely.
- **Reliability**: a corrupted/binary-garbage `.env` config file (e.g.
  from a power loss mid-write) previously crashed startup with an
  uncaught `UnicodeDecodeError`. Now falls back to defaults with a clear
  warning instead of refusing to start.
- **Security**: `DeveloperModeService` password verification used a
  non-constant-time string comparison (`==`); switched to
  `hmac.compare_digest`.
- **Security**: browser automation's `LAUNCH_URL` action had no URL
  scheme validation -- `file://`/`javascript:`/`data:` URIs would have
  been auto-allowed with no confirmation. Added scheme validation to
  `SafetyValidator` (denylist-based, specifically to avoid a false
  positive on ordinary `localhost:8080`-style local-dev URLs that a
  naive allowlist approach would have wrongly flagged).
- **Architecture**: `ThemeService` had a hardcoded accent-color dict
  that duplicated values already defined in `ui/themes/palette.py`,
  which existed but was never wired in. Now derives from `palette.py`
  directly.
- **Accessibility**: buttons (sidebar nav, quick actions, dialogs) had
  no visible keyboard-focus indicator -- only text inputs did. Added a
  `QPushButton:focus` rule to all three themes.
- **Performance**: all 9 workspace modules were imported eagerly at
  `main_window` import time regardless of whether a user ever visited
  them (measured: ~358ms, ~20% of that module's import chain). Fixed at
  both the `main_window.py` call site and the root cause (a
  `ui/views/workspaces/__init__.py` package `__init__.py` that itself
  eagerly re-exported all 9, silently defeating the first fix). Measured
  result: `MainWindow` construction time dropped from ~256ms to ~109ms.
- Removed 4 files of dead, milestone-superseded scaffolding
  (`agents/base_agent.py`, `agents/state.py`,
  `infrastructure/database/base_repository.py`,
  `infrastructure/stt/whisper_provider.py`) -- each explicitly labeled
  "Implementation deferred to Milestone N" for milestones later
  completed via different, real implementations. Verified zero
  references before removal.

### Added
- Packaging foundation: `packaging/jarvis.spec` (PyInstaller),
  `packaging/build_windows.ps1` (build + optional code signing),
  `packaging/jarvis_installer.iss` (Inno Setup). None yet
  build-verified on real Windows hardware -- see `docs/PACKAGING.md`.
- `docs/PACKAGING.md`, this changelog.
- ~65 new regression/reliability/security tests across the areas above.

### Known gaps (see `docs/PACKAGING.md` and the RC1 audit report for full detail)
- No real Windows build has been produced or tested.
- No application icon exists yet.
- No first-run/onboarding wizard.
- Coverage gaps remain concentrated in Settings-page UI wiring code.

## [Earlier history]

Milestones 0 through 5 (architecture scaffolding through the official
PySide6 UI, Developer Mode, Update Center, and the 9 feature
workspaces) predate this changelog's introduction and are documented in
`MILESTONE_5_DELIVERY.md` and `AUDIT_REPORT_M0-M5.md` rather than
retroactively reconstructed here.
