# M7 Recorder — Logic Contract

**Status: Phase 1 (Logic Contract). Zero implementation code accompanies
this document.** Written after a fresh, read-only Phase 0 audit of the
actual current source (not a reuse of any prior session's audit
findings) against `feature/m22-task-group-c` at commit `af71fba`. Do
not begin Phase 2 implementation until this contract is explicitly
approved.

## 1. Objective

Per `docs/MASTER_ROADMAP.md`'s M7 section, Recorder is Phase 5:
*"Automation Recorder / Macro Engine — 'watch me do this once, then
do it for me' — the natural successor to M4's manual `RecipeManager`
authoring."* With Workflow Builder (Phase 4) now shipped as the
canonical standalone workflow-authoring surface, Recorder's job is
narrower than the roadmap's evocative phrasing suggests once the
actual source is consulted: **turn a bounded window of JARVIS's own
already-executed OS-automation actions into a new, standalone
`WorkflowDefinition`**, by calling the existing
`WorkflowBuilderService.create_workflow()` — not a new authoring
surface, not a new execution engine, not a new persistence path for
workflows themselves.

## 2. Git safety at audit start

Branch `feature/m22-task-group-c`, working tree clean, `HEAD ==
origin/feature/m22-task-group-c` at
`af71fba77cae9f76e8b1e240e524d9b02384c0b5` (the M7 Workflow Builder
completion commit). Verified via `git status --short` (empty) and
`git rev-parse HEAD`/`git rev-parse origin/feature/m22-task-group-c`
(identical) immediately before this audit began.

## 3. Prerequisite audit summary — what already exists

Fresh-verified this session (not reused from any prior audit), file
and line citations throughout:

- **No Recorder/Macro infrastructure exists anywhere.** Exhaustive
  grep of `src/` for `record`/`capture`/`macro` (123 files matched)
  classified every real hit as either (a) unrelated homonyms —
  generic ORM "records" (`ScheduleRepository.record_fire()`), audio
  recording for STT (`SoundDeviceRecorder`, `IAudioRecorder`),
  screenshot capture (`ActionType.SCREENSHOT`), install-journal
  bookkeeping — or (b) execution-*history* logging, which is
  categorically distinct from action *capture-for-replay* (see next
  bullet). No class, module, or interface named `Recorder`,
  `MacroEngine`, or similar exists. Confirmed identically in
  `Jarvis-Frontend-main/frontend/src` (2 real hits, both unrelated
  doc-comment prose). The specific sentence *"no capture
  infrastructure exists anywhere in this codebase to extend"* is
  `docs/MASTER_ROADMAP.md:2723-2725`'s own words (not, as previously
  believed, `test_workflow_domain_foundation.py`'s docstring) — a
  citation correction, not a substantive one; the claim itself holds.
- **`HistoryService`** (`src/jarvis/features/automation/history.py`,
  read fresh in full) — SQLite-backed, records every `ActionExecutor`
  step unconditionally (called from `executor.py`'s `_persist()` on
  every step, success or failure, not opt-in). `record(*, plan_id,
  step_id, result, target, args)` persists the real `ActionType`
  (`action`) and the real per-step `args` dict (as `args_json`) via
  `TaskHistoryRepository.add()`. **However**, `HistoryService.
  list_recent()` -> `TaskHistoryEntry` (the dataclass this service
  actually returns) does **not** expose `args`/`args_json` back out —
  only `id, plan_id, action, target, status, result, error,
  duration_ms, created_at`. The underlying `TaskHistoryRepository.
  list_recent()` returns full ORM `TaskHistory` rows (`args_json` is
  present at that layer), but `HistoryService`'s own wrapper drops it
  when mapping to `TaskHistoryEntry`. This is a real, load-bearing gap
  — see §5.
- **`UndoManager`** (`src/jarvis/features/automation/undo.py`) — an
  in-memory, bounded `deque(maxlen=50)` of *undo* records (the reverse
  action needed to undo a step), explicitly not a durable audit trail
  by its own docstring. Wrong direction of data for "replay this
  forward" — not usable as a capture source.
- **`AutomationStepEvent`** (`src/jarvis/core/events/events.py:184-189`)
  — already exists, already published in production (`executor.py`'s
  `_publish_step_event`, called after every `ActionExecutor` step),
  already relayed over WebSocket as `"automation.step"`. Carries only
  `step_id`, `action`, `status` — **no `args`** — so it alone cannot
  reconstruct a replayable step either. A real, working precedent for
  "subscribe to learn a step just ran" (mirroring `HomeAutomationService`'s
  own `DeviceStateChangedEvent` subscription), but not sufficient on
  its own for capture fidelity, and not needed if the design queries
  `HistoryService` at stop-time instead of subscribing live (§4).
- **No raw OS-input capture exists.** `src/jarvis/infrastructure/hotkey/
  pynput_listener.py`'s `PynputHotkeyListener` only wraps `pynput.
  keyboard.GlobalHotKeys` — a pre-registered-combo trigger, not a
  keystroke/mouse stream. `IOSAutomation` (`core/interfaces/automation.py`)
  is action-only (`send_text`, `send_hotkey`, `screenshot`, ...), never
  observation. "Watch me do this once" therefore **cannot** mean
  "capture my raw input" without wholly new, materially larger capture
  machinery — out of scope for a coherent MVP, confirmed not
  speculatively assumed.
- **`WorkflowExecutionService` has zero `EventBus` involvement** —
  confirmed fresh: no `Event`/`EventBus` import anywhere in
  `src/jarvis/services/workflow_execution_service.py`; `run_workflow()`
  returns plain tuples, publishes nothing. **Agent-tool invocations
  (the `agent_tool` `WorkflowStep` kind) have no capture mechanism of
  any kind** — no event, no history entry, nothing. `AgentStepEvent`
  (a coarse per-LangGraph-node-transition event) is "not persisted
  anywhere" and does not carry tool_name/args in a replayable form.
  **`WorkflowStepEvent`/`ScheduledJobFiredEvent`** (`events.py:407-418`,
  `557-565`) remain fully unpublished today — confirmed current, not a
  stale Phase-1-era claim: neither `workflow_execution_service.py` nor
  `schedule_service.py`'s `_dispatch()` imports `EventBus`, and
  `core/lifecycle/runtime_ws_hub.py`'s `UNPUBLISHED_EVENT_TYPES` still
  lists both.
- **`RecipeManager` (M4)** — unchanged since Workflow Builder's own
  audit: feature-frozen, structurally incompatible (string-only
  steps), zero REST/agent-tool surface. Not touched, not revived, not
  a Recorder input or output.
- **`WorkflowRepository`/`WorkflowBuilderService`** (shipped this
  session, re-verified fresh at current `HEAD`) — `WorkflowRepository.
  add`/`get`/`delete`/`update`/`list_all` all confirmed present and
  unchanged (`src/jarvis/infrastructure/database/repositories/
  schedule_repository.py:21-73`). `WorkflowBuilderService.
  create_workflow(*, name, steps, description="")` (`src/jarvis/
  services/workflow_builder_service.py`) is the exact, already-shipped,
  already-tested entry point Recorder should call to persist its
  output — not a new persistence path.
- **`ActionType`** (`src/jarvis/domain/automation/models.py:26-56`) —
  ~24 discrete OS-automation actions (`OPEN_APP`, `SET_VOLUME`,
  `CLIPBOARD_COPY`, etc.). `Step.args: dict[str, Any]` is the real
  per-step argument bag; `target` (the string `HistoryService.record()`
  is separately given) is a single-string summary derived from `args`
  by the caller, not the full structured payload — relevant to §5's
  fidelity discussion.
- **Frontend** — `Jarvis-Frontend-main/frontend/src/features/
  workflowBuilder/` (shipped this session) already has the exact
  step-list-review UI (`WorkflowBuilderForm.tsx`) a "review captured
  steps before saving" flow would want to reuse — no Recorder-specific
  frontend code exists yet, confirmed.
- **Tests** — grepped `tests/` for `recorder`/`macro`/`Recording`: 7
  matches, all false positives (a generic `recorder` pytest fixture
  name for "subscribe and record bus events" in unrelated test files,
  `FakeRecorder(IAudioRecorder)` for STT tests, an MCP test double
  named `_RecordingServer`). Zero tests exercise or stub a Recorder
  feature.
- **Roadmap self-consistency check** — `docs/MASTER_ROADMAP.md:5876-5878`:
  *"Automation Recorder and Replay Engine are the Desktop Intelligence
  instance of M7's Automation Recorder / M17A's Training Studio, not a
  parallel recording mechanism"* — confirms a later milestone's own
  "Automation Recorder" mention is a forward-reference to reusing M7's
  Recorder, not a naming collision or a competing scope. `MASTER_ROADMAP.
  md:1206-1209`'s own prose independently corroborates Workflow
  Builder's Logic Contract §5 finding: *"that review [the UI Foundation
  gate] itself completed and was superseded by the decision to migrate
  the frontend to React + Tauri (M8), so M7's Phases 4-6 remain paused,
  not actively blocked on anything further."*

## 4. Critical Design Issue — what a "recording session" actually watches

- **Option A — query `HistoryService` at stop-time, bounded by a
  start/stop marker.** No new `EventBus` subscription, no new
  published event. `HistoryService.record()` already runs
  unconditionally on every `ActionExecutor` step regardless of whether
  a "recording" is active — so "starting a recording" is purely a
  bookkeeping marker (a timestamp), not a mode switch on any existing
  capture path. "Stopping" queries history rows created between the
  marker and now.
- **Option B — subscribe to `AutomationStepEvent` live**, mirroring
  `HomeAutomationService`'s own `DeviceStateChangedEvent` subscription
  pattern. Functionally near-identical outcome to Option A (the event
  itself carries no `args`, so a `HistoryService`/`TaskHistoryRepository`
  lookup by `step_id` would still be needed to get the args), for
  materially more complexity (subscription lifecycle, task
  correlation) and no clear benefit.
- **Option C — extend `AutomationStepEvent` to carry `args`.** Would
  touch an already-shipped, cross-milestone event and its WebSocket
  relay contract (consumed by the Agent Trace panel and possibly other
  UI), for a benefit Option A gets without touching it at all.
  Disqualified — not the smallest option, and edits shared
  infrastructure outside this slice's own boundary.

**Recommendation: Option A.** Zero new `EventBus` wiring, zero
modification to `AutomationStepEvent` or any other shared event.
Satisfies "do not introduce speculative event infrastructure"
trivially, and "watch" is implemented as "query what already happened,"
not a new live-observation mechanism.

## 5. Critical Design Issue — instruction-reconstruction fidelity

A captured `TaskHistoryEntry` carries `action` (an `ActionType` value)
and `target` (a lossy, single-string summary), but — per §3 — **not**
the full `args` dict, because `HistoryService.list_recent()`'s own
mapping drops it even though the underlying table stores it. Turning
a captured entry into a `WorkflowStep(kind="automation", instruction=...)`
requires a deterministic (never AI-generated — explicitly disallowed
by this phase's own instruction) `ActionType` → natural-language
template, since a `WorkflowStep` of kind `automation` is re-parsed by
`TaskPlanner` at replay time — the existing, unchanged execution path,
not a new one.

- **Option A — `action` + `target` only, zero source changes.**
  Every field needed already exists on `TaskHistoryEntry` today.
  Reduced fidelity: an action with multiple meaningful `args` beyond
  what `target` alone summarizes loses information in the round trip.
  Requires **no edit to any M0-M6 file** — `history.py` is not
  touched at all.
- **Option B — extend `HistoryService.list_recent()`/`TaskHistoryEntry`
  to also return `args_json`.** A small, purely additive change (new
  optional field, existing behavior for every other caller unchanged)
  — `history.py` lives in `src/jarvis/features/automation/`, the same
  M4 territory `RecipeManager` occupies, so this needs the same
  scrutiny that disqualified extending `RecipeManager` in the Workflow
  Builder contract. Unlike that case, this is additive (no existing
  behavior changes, no data model reshaping) rather than a
  fundamental shape change — a materially smaller edit — but it is
  still an edit to a shipped M4 file, which CLAUDE.md's freeze rule is
  written to avoid without a clear composition-layer alternative.
- **Option C — bypass `HistoryService`, have `RecorderService` query
  `TaskHistoryRepository` directly.** Avoids touching `history.py`,
  but breaks the established "a service owns its own repository
  access" layering — `RecorderService` reaching into another module's
  repository directly is arguably a worse violation of module
  boundaries than Option B's small, additive service-layer extension.

**Recommendation: Option A for this MVP**, accepted explicitly as a
known, honest fidelity limitation (documented in user-facing copy at
implementation time: a recorded step's instruction is a best-effort
reconstruction from the action type and its primary target only, not
a guaranteed byte-for-byte replay of the original arguments). Option
B is flagged as the natural, small follow-up if fidelity proves
insufficient in practice — explicitly deferred, not decided here, and
would need its own narrow approval given the M4-adjacency question
above.

## 6. Critical Design Issue — capture scope is OS-automation steps only

Per §3, only `ActionExecutor`-routed steps (i.e., actions that flowed
through `AutomationService.run_command()` / `TaskPlanner`) have any
existing capture mechanism (`HistoryService`). **Agent-tool invocations
have none** — no event carries tool_name/args in replayable form, no
history table records them. Capturing agent-tool invocations would
require genuinely new infrastructure (a new publish call site inside
the tool-executor path, or a new history table) — explicitly deferred
(§20), not built here. **Recorder's MVP therefore only ever produces
`automation`-kind `WorkflowStep`s** — a real, honestly-declared scope
limitation, not an oversight.

## 7. Persistence

One new table, `recording_sessions` — a small, dedicated marker table
(mirroring every prior M7 slice's own "one small table per new
capability" pattern), **not** a new copy of captured action data
(that stays in the pre-existing `automation_task_history` table,
untouched):

| Field | Type | Notes |
|---|---|---|
| `id` | `String(32)` PK | uuid |
| `status` | `String(16)` | `recording` / `completed` / `cancelled` |
| `started_at` | `DateTime` | |
| `stopped_at` | `DateTime \| None` | |
| `resulting_workflow_id` | `String(32) \| None` | FK `workflow_definitions.id`, `SET NULL` — set only on `completed` |

No FK from `automation_task_history` back to `recording_sessions` —
correlation is by timestamp window (`started_at` ≤ `TaskHistoryEntry.
created_at` < `stopped_at`) at stop-time, not a live join.

## 8. Recording model — start / stop / cancel semantics

- **`start_recording()`** — rejects if a session with `status ==
  "recording"` already exists (§13, single-active-session). Creates a
  `recording_sessions` row (`status="recording"`, `started_at=now`).
  No side effect on `HistoryService`/`ActionExecutor` — nothing to
  enable, since capture is always-on and unconditional already (§4).
- **`stop_recording(session_id, *, name, description="")`** — sets
  `stopped_at=now`; queries `HistoryService.list_recent()` (or a
  time-bounded equivalent — the precise call shape is a Phase 2 detail,
  not fixed here) filtered to rows within `[started_at, stopped_at)`;
  **filters out
  every entry whose `status` is not `succeeded`** (a failed or
  denied step is not something a "do this for me" macro should
  replay); converts each remaining entry into a `WorkflowStep(kind=
  "automation", instruction=<template(action, target)>, label=<raw
  "action: target" summary for user-facing transparency>)`, ordered by
  `created_at`; if zero steps result, fails with a clear error rather
  than creating an empty workflow (Workflow Builder's own
  `create_workflow` already rejects an empty `steps` list — this is
  not new validation, just surfaced honestly rather than silently
  swallowed); calls the existing `WorkflowBuilderService.
  create_workflow(name=name, steps=steps, description=description)`;
  sets `status="completed"`, `resulting_workflow_id=<created workflow
  id>`.
- **`cancel_recording(session_id)`** — sets `status="cancelled"`. No
  workflow created. No side effect on `automation_task_history` (the
  underlying history rows are not deleted — they remain as ordinary
  execution history, exactly as they would if no recording had ever
  been active).

## 9. Workflow conversion — exact mapping

`TaskHistoryEntry(action, target, status, ...)` -> one `WorkflowStep`
per **succeeded** entry:
- `kind`: always `"automation"` (§6).
- `instruction`: a deterministic per-`ActionType` template applied to
  `target` (e.g. `OPEN_APP` + `target="Chrome"` -> `"Open the Chrome
  application."`). The exact template table is an implementation
  detail for Phase 2, not enumerated here — the *mechanism* (a fixed,
  non-AI lookup keyed by `ActionType`) is the contract, not each
  string.
- `label`: the raw `"{action}: {target}"` summary, preserved
  unedited, so a reviewing user can see what was actually captured
  even though `instruction` is a reconstruction (uses the existing
  `WorkflowStep.label` field — no new field needed).
- `tool_name`/`tool_args`: always empty (never an `agent_tool` step,
  per §6).

## 10. Execution / replay boundary

**Zero new execution code.** A recorded workflow is a completely
ordinary `WorkflowDefinition` row, indistinguishable from one authored
by hand through Workflow Builder's own UI. Running it later means
calling `WorkflowBuilderService.run_workflow(workflow_id)` — the
exact, already-shipped, already-tested method, itself delegating to
the shared `WorkflowExecutionService` every M7 sibling already uses.
`RecorderService` never imports or calls `WorkflowExecutionService`
directly, never introduces a second execution path.

## 11. Permissions

Two independently-checked scopes, stacked, neither bypassed:

- **New scope `"recorder"`**, `PERMISSION_SCOPES` (`sdk.py`) — 14th
  entry, same doc-comment template as every prior M7 addition. New
  principal `core:recorder`. Gates `start_recording`/`stop_recording`/
  `cancel_recording`/`list_recordings` — the recording-*session*
  lifecycle only.
- **Existing scope `"workflow_builder"`** — `stop_recording` calls
  `WorkflowBuilderService.create_workflow()` directly, which already,
  independently, calls its own `_require_permission()` internally.
  **Recorder does not bypass, cache, or pre-check this** — a caller
  who has `recorder` granted but not `workflow_builder` will have
  their recording session's `stop` call fail with
  `WorkflowBuilderPermissionError`, exactly as it would if they called
  `create_workflow` directly. This mirrors the established principle
  ("CRUD permission never implies action permission") in its natural
  inverse form here: recording-session permission does not imply
  workflow-creation permission. Zero new authorization code beyond the
  one new scope declaration.

## 12. Confirmation behavior

Not confirmation-gated. `start_recording`/`stop_recording`/
`cancel_recording` do not execute anything — they read already-recorded
history and create a workflow row, mirroring why `create_workflow`/
`update_workflow` are not in `confirm_required_tools` either.
Confirmation remains entirely the concern of whatever later executes
the resulting workflow (`WorkflowExecutionService`'s existing,
unchanged Policy A).

## 13. Concurrency

**At most one globally-active recording session at a time.**
`start_recording()` while a `status="recording"` row exists is
rejected with a clear error. Rationale: `HistoryService`'s underlying
`automation_task_history` table has no per-session attribution column
(§7) — two concurrent sessions would both capture from the same
global stream with no way to tell which entry belongs to which
session, other than an ambiguous overlapping-timestamp heuristic.
Single-session-at-a-time avoids this ambiguity entirely rather than
solving it. Multi-session recording is explicitly deferred (§20).

## 14. Failure / recovery semantics

If the backend restarts mid-recording, the `recording_sessions` row
is left at `status="recording"` with no `stopped_at` — this is not
automatically reconciled in this MVP. `GET /api/v1/recordings` (§15)
still lists it (filterable client-side by `status`); a caller who
stops it very late captures an unexpectedly wide time window. This is
a known, accepted MVP limitation (a `cancel_recording` call is always
available to discard a stale session) rather than a solved
crash-recovery flow — automatic reconciliation on startup is
explicitly deferred (§20).

## 15. REST API

New route file `src/jarvis/infrastructure/api/routes/recorder.py`,
identical `Depends(get_current_session)` + `{data, meta}` envelope
convention:

| Endpoint | Method | Body |
|---|---|---|
| `/api/v1/recordings/start` | `POST` | — |
| `/api/v1/recordings/{id}/stop` | `POST` | `{name, description?}` |
| `/api/v1/recordings/{id}/cancel` | `POST` | — |
| `/api/v1/recordings` | `GET` | — |
| `/api/v1/recordings/{id}` | `GET` | — |

No `DELETE` route — a completed/cancelled session is an inert history
record, not something that needs its own deletion lifecycle distinct
from the workflow it may have produced (which Workflow Builder's own
`DELETE /api/v1/workflows/{id}` already covers).

## 16. Agent tools

New `src/jarvis/agents/tools/recorder_tools.py`, four tools mirroring
every prior M7 slice's minimum-coherent-surface precedent:
`start_recording`, `stop_recording`, `cancel_recording`,
`list_recordings`. None confirm-required (§12).

## 17. DI wiring

`_build_recorder_service(...)` in `core/di/container.py`, constructed
with `database, permissions, history (HistoryService), workflow_
builder (WorkflowBuilderService)` — reusing the already-registered
`workflow_builder_service` and (the already-DI-registered, via
`AutomationService`) history facility rather than constructing either
again. `recorder_service` provider registered after `workflow_
builder_service`. `AgentOrchestrator` gains a `recorder: Any | None`
param, threaded through identically to every prior M7 addition.

## 18. Security boundaries

`RecorderService` must, like every M7 sibling before it: introduce no
import of any connector class, no coupling to Memory/Analytics/
EventViewer, no raw connector payload or credential field on
`recording_sessions`. Unlike `HomeAutomationService`, it also
introduces **no `EventBus` dependency at all** (§4/§19) — a stronger
boundary than any prior M7 slice needed, since Option A requires no
subscription. Every side effect flows through two already-audited
chokepoints: `HistoryService.list_recent()` (read-only) and
`WorkflowBuilderService.create_workflow()` (already independently
permission-gated).

## 19. EventBus interaction

**None.** No new subscription, no new published event, no
modification to `AutomationStepEvent`, `WorkflowStepEvent`, or
`ScheduledJobFiredEvent`. This is a deliberate consequence of §4's
Option A, not an oversight — explicitly satisfies this phase's own
"do not introduce speculative event infrastructure" instruction.

## 20. Frontend requirements (for a future Phase 2 frontend pass — no frontend code in this contract)

Target repository: `Jarvis-Frontend-main` (confirmed unchanged target).
A record/stop affordance (start → visible "recording" indicator → stop
opens a review step); the review step should **reuse the already-shipped
`WorkflowBuilderForm.tsx`'s step-list editor**, pre-populated with the
captured (reconstructed) steps, letting the user see and edit each
step's `label` (the honest raw capture) and `instruction` (the
reconstruction that will actually execute) before committing — since
§5's fidelity limitation means the reconstructed instruction deserves
human review, not silent trust. Same mock-only architecture decision
as every prior M7 frontend slice (this frontend still has no auth
mechanism of any kind). No frontend implementation in this phase.

## 21. Testing strategy

Mirrors the established matrix: permission enforcement (both
`recorder` and, independently, `workflow_builder` scopes), single-
active-session enforcement (a second `start_recording` while one is
active is rejected), stop-with-zero-succeeded-steps is rejected
(matching `create_workflow`'s own empty-steps rule, not new
validation), the `TaskHistoryEntry` → `WorkflowStep` conversion
(succeeded-only filtering, `label` preserves the raw summary,
`instruction` is the deterministic template), delegation to
`WorkflowBuilderService.create_workflow()` (verify the resulting
workflow is genuinely visible via `list_workflows()`), cancel leaves
no workflow and leaves `automation_task_history` untouched, REST route
tests, agent tool tests, and scope guards (no `EventBus` import at
all, no connector/Memory/Analytics coupling, no `WorkflowExecutionService`
import — proving replay is always delegated through `WorkflowBuilderService`,
never a second execution path).

## 22. Deferred scope (explicit)

- Capturing agent-tool invocations — no existing capture mechanism
  (§6); would need new publish/history infrastructure.
- Raw OS-input (keystroke/mouse) capture — no existing infrastructure
  of any kind (§3); would need a materially larger, genuinely new
  subsystem.
- Extending `HistoryService`/`TaskHistoryEntry` to preserve full
  `args` fidelity (§5, Option B) — a real, small, plausible follow-up,
  not decided here.
- Multi-session concurrent recording (§13).
- Automatic crash-recovery reconciliation of orphaned `"recording"`
  sessions (§14).
- Hotkey-triggered start/stop — `PynputHotkeyListener`/`HotkeyService`
  already exist and could plausibly bind a global hotkey to
  start/stop, but wiring a new binding is a separate concern from
  Recorder's own core capability; not built here.
- AI-generated or AI-assisted instruction synthesis — explicitly
  disallowed by this phase's own governing instruction; the
  reconstruction mechanism (§5/§9) is a fixed, deterministic template,
  never a model call.
- Any frontend implementation (§20 is requirements only).
- Editing a recording session after it's stopped (the resulting
  `WorkflowDefinition` can be edited via Workflow Builder's own
  existing `PATCH` — a recording session itself is not re-opened).

## 23. Acceptance criteria

1. `HistoryService`/`TaskHistoryRepository`/`AutomationStepEvent`/
   `WorkflowExecutionService`/`WorkflowBuilderService` are all
   unmodified in behavior — proven by the full Automation, Scheduler,
   Home Automation, and Workflow Builder regressions passing
   unmodified after this slice ships.
2. A recorded workflow, once created, is completely indistinguishable
   from a hand-authored one anywhere in Workflow Builder's own API —
   same table, same shape, same execution path.
3. Every `stop_recording` call independently re-checks `workflow_builder`
   permission via the real `WorkflowBuilderService.create_workflow()`
   call — never cached, never bypassed, zero new authorization code.
4. No new `EventBus` subscription or publish call exists anywhere in
   `recorder_service.py`.
5. A second `start_recording` while one session is already active is
   rejected, never silently creates a second concurrent session.
6. No new import of any connector class, Memory, or Analytics module
   appears in `recorder_service.py`.

## 24. Hard stop conditions for Phase 2

Identical discipline to every prior M7 contract: if implementation
reveals `WorkflowBuilderService.create_workflow()`'s existing behavior
cannot be reused unmodified, if the Automation/Scheduler/Home
Automation/Workflow Builder regressions change at all, if
`HistoryService`'s existing `record`/`list_recent`/`purge_expired`/
`clear` methods need behavior changes (not just an additive,
separately-approved extension per §5 Option B), if the single-active-
session model in §13 turns out to be unenforceable without a schema
change beyond §7's one table, or if capturing agent-tool invocations
turns out to be required for a coherent MVP (contradicting §6's own
scope boundary) — stop and report rather than improvising.

## 25. Implementation order (sketch, for Phase 2 — not started)

`recording_sessions` table + repository -> `RecorderService`
(start/stop/cancel/list, `TaskHistoryEntry` -> `WorkflowStep`
conversion, delegation to `WorkflowBuilderService.create_workflow()`)
-> REST routes -> agent tools -> DI wiring -> tests -> quality gates
-> docs. No frontend step in this list; §20 governs a
separately-approved future pass.
