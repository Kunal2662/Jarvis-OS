# M7 Workflow Builder — Logic Contract

**Status: Phase 1 (Logic Contract). Zero implementation code accompanies
this document.** Written after a fresh, read-only Phase 0 audit of the
actual current source (not a reuse of any prior session's audit
findings) against `feature/m22-task-group-c` at commit `89d3517`. Do
not begin Phase 2 implementation until this contract is explicitly
approved.

## 1. Objective

Per `docs/MASTER_ROADMAP.md`'s M7 section, Workflow Builder is Phase 4:
*"a visual/declarative way to author a fixed sequence of agent +
automation steps, built on the existing `RecipeManager` (M4) rather
than replacing it."* Unlike Scheduler and Home Automation — both of
which create exactly one `WorkflowDefinition` row **inline**, as a
side effect of creating a trigger, with **no edit surface afterward**
(their own ORM docstrings and REST route docstrings say this
explicitly — §3 below) — Workflow Builder's job is to be a **standalone
authoring surface**: create, list, get, edit, delete, and manually run
a `WorkflowDefinition` independent of any Schedule or
`AutomationTrigger` owning it.

## 2. Git safety at audit start

Branch `feature/m22-task-group-c`, working tree clean, `HEAD ==
origin/feature/m22-task-group-c` at `89d3517b51bede8b4c973c7199d3168643ae301c`
(the M7 Home Automation completion commit). Verified via `git status
--short` (empty) and `git rev-parse HEAD`/`git rev-parse
origin/feature/m22-task-group-c` (identical) immediately before this
audit began.

## 3. Prerequisite audit summary — what already exists

Fresh-verified this session (not reused from any prior audit), file
and line citations throughout:

- **`WorkflowStep`/`WorkflowDefinition` domain dataclasses**
  (`src/jarvis/domain/workflow/models.py:52-94`) — `WorkflowStepKind`
  is exactly `AUTOMATION`/`AGENT_TOOL`. The module docstring's claim
  that "nothing yet constructs, persists, or executes them" is **still
  literally true for the dataclasses themselves** — production code
  works with plain `dict[str, Any]` and a separate ORM class; no
  production code ever instantiates these dataclasses directly (only
  `tests/unit/test_workflow_domain_foundation.py` does, to check
  defaults).
- **ORM `WorkflowDefinition`** (`src/jarvis/infrastructure/database/models.py:1239-1261`,
  table `workflow_definitions`, fields `id`/`name`/`description`/
  `steps_json`/`created_at`) — its own docstring is explicit and
  load-bearing: *"**Not the Workflow Builder.** There is no standalone
  authoring API over this table in this phase — `ScheduleService.
  create_schedule` creates exactly one dedicated row per schedule,
  atomically, and nothing in this phase can edit a row afterward."*
- **`WorkflowRepository`** (`src/jarvis/infrastructure/database/repositories/schedule_repository.py:21-40`)
  has exactly three methods: `add`, `get`, `delete`. **No `update`, no
  `list_all`.** Confirmed by exhaustive read — this is the single
  concrete gap Workflow Builder exists to fill.
- **Structural validation** (`_validate_step`, `src/jarvis/services/schedule_service.py:135-161`,
  duplicated verbatim — by this codebase's own established
  convention, not an oversight — inside `home_automation_service.py`)
  checks `kind` is one of the two allowed values and that
  `instruction`/`tool_name` is a non-empty string. Its own docstring:
  *"Structural validation only... does not resolve whether an
  `instruction` parses or a `tool_name` is registered."* No semantic
  validation exists anywhere in this codebase today.
- **`WorkflowExecutionService`** (`src/jarvis/services/workflow_execution_service.py`,
  read fresh in full this session) — the shared executor Scheduler and
  Home Automation both dispatch through. `run_workflow(steps: list[dict]) ->
  (status, error, results)`. Sequential only (`depends_on`-based
  parallel dispatch is explicitly out of scope, unchanged from
  pre-extraction behavior — its own docstring says so). Always passes
  `confirm=None` to `AgentPermissionGate.authorize()` — Policy A,
  always deny, zero new authorization code needed to reuse it.
- **`RecipeManager` (M4)** (`src/jarvis/features/automation/recipes.py`,
  `src/jarvis/domain/automation/models.py:196-203`) — real, tested,
  complete CRUD (`list_recipes`/`get`/`save`/`delete`), but over a
  **structurally incompatible** model: `Recipe` is a frozen dataclass
  with `steps: list[str]` — raw natural-language lines, always routed
  through `TaskPlanner`, with **no `kind` discrimination and no way to
  express an `agent_tool` step at all**. File-per-recipe JSON storage,
  not the SQL `workflow_definitions` table. Not DI-registered on its
  own — only reachable via `AutomationService`'s facade methods
  (`list_recipes`/`save_recipe`/`run_recipe`,
  `src/jarvis/services/automation_service.py:119-129`). Zero REST
  surface, zero agent tools (confirmed by exhaustive grep). See §4 for
  why this rules out literal reuse.
- **`ActionExecutor`** (`src/jarvis/features/automation/executor.py`)
  — a different, lower-level primitive (`ActionType`, 24 fixed OS
  actions) reached only transitively, two layers below
  `WorkflowExecutionService`, via `AutomationService.run_command ->
  TaskPlanner.build_plan -> ActionExecutor.run_plan`. Workflow Builder
  has no reason to touch it directly, exactly like Scheduler and Home
  Automation don't.
- **`AgentPermissionGate`** (`src/jarvis/agents/permission.py`) — one
  public method, `authorize(tool_name, args, *, confirm=None) ->
  (bool, str)`, "never raises." **No dry-run/preview mode exists.** A
  create-time "this step will need confirmation" hint would have to
  replicate Scheduler's own existing, explicitly-non-authoritative ad
  hoc scan against `settings.agent.confirm_required_tools`
  (`schedule_service.py:243-248`) — an established pattern, not new
  work, but still only a heuristic, never a guarantee.
- **`PermissionModel`/`PERMISSION_SCOPES`** (`src/jarvis/core/plugins/permissions.py`,
  `src/jarvis/core/plugins/sdk.py:34-59`) — 12 scopes today,
  including `scheduler` and `home_automation`, both CRUD-only,
  execution separately gated. A 13th scope for Workflow Builder is a
  one-line addition following an exact, twice-proven template.
- **Tool Registry** (`src/jarvis/agents/tools/registry.py:47-260`) —
  `build_tool_registry()` returns a flat list of live `BaseTool`
  instances. **No enumeration/introspection REST endpoint exists** —
  confirmed still true today, matching
  `docs/M7_SCHEDULER_FRONTEND_REQUIREMENTS.md:64-65`'s own
  already-documented gap verbatim. `format_tool_descriptions()`
  (`src/jarvis/agents/prompting.py:46-60`) is a usable internal
  building block (`name(args): description` via each tool's
  `args_schema.model_json_schema()`) if a future enumeration endpoint
  is ever built — not built here.
- **Tests** — grepped `tests/` for `recipe`/`RecipeManager`/
  `workflow_builder`/`WorkflowBuilder` (case-insensitive):
  `test_automation_recipes.py`/`test_automation_service.py`'s recipe
  tests are M4-only; `test_workflow_domain_foundation.py` is Phase-1
  domain-only ("No builder, recorder, scheduler, executor, or
  agent-graph code exists yet" — its own docstring). **Zero
  Workflow-Builder-specific tests exist anywhere** — a clean slate,
  not a partially-started feature.
- **REST precedent** — `routes/schedules.py` (7 routes) and
  `routes/home_automation.py` (8 routes), both `Depends
  (get_current_session)` Bearer-auth, `{data, meta}` envelope, mounted
  in `fastapi_server.py` alongside 20+ other resource routers. Neither
  has a `PATCH` route — both explicitly document "no standalone
  authoring API in this phase" / "changing this means delete +
  recreate." This is the one precedent Workflow Builder's REST surface
  must genuinely extend, not just replicate.

## 4. Critical Design Issue — the RecipeManager relationship

The roadmap's own words assume Workflow Builder is *"built on the
existing `RecipeManager` (M4) rather than replacing it."* Four options
were evaluated:

- **Option A — standalone CRUD over the existing ORM
  `WorkflowDefinition`/`WorkflowStep` shape.** Extend
  `WorkflowRepository` with `update`/`list_all`; a new
  `WorkflowBuilderService` owns creation/editing/deletion/manual
  execution of **unowned** `workflow_definitions` rows (no
  `Schedule`/`AutomationTrigger` FK pointing at them). Zero new domain
  model — reuses the exact shape and execution path (`WorkflowExecutionService`)
  Scheduler and Home Automation already validated in production. Zero
  risk to `RecipeManager`, zero risk to Scheduler/Home Automation's
  already-shipped, already-tested create flows (neither is touched).
- **Option B — extend `RecipeManager` itself to support the
  `kind`-discriminated `WorkflowStep` shape**, making the roadmap's
  "built on RecipeManager" literally true. **Disqualified.**
  `RecipeManager` lives in `src/jarvis/features/automation/` — M4
  territory. `CLAUDE.md`'s own rule is explicit: *"M0–M6 are
  feature-frozen. Extend around them at the composition layer; do not
  edit... to add behavior."* Changing `Recipe`'s frozen dataclass
  shape, or teaching it to express `agent_tool` steps, is exactly the
  kind of edit that rule forbids — and `Recipe` is a real,
  already-shipped, already-seeded-with-bundled-examples production
  facility (`AutomationService._seed_bundled_recipes()`), not inert
  scaffolding safe to reshape.
- **Option C — a third, new domain model.** Rejected outright:
  duplicates `WorkflowStep`/`WorkflowDefinition` for no reason, the
  exact "speculative architecture" this contract is instructed to
  avoid.
- **Option D — treat Workflow Builder as blocked**, since the literal
  premise ("built on RecipeManager") can't be honored. Rejected:
  Option A satisfies the roadmap's underlying *intent* (a visual/
  declarative authoring surface for the same step model Scheduler and
  Home Automation already execute) without needing `RecipeManager` at
  all. Nothing about Option A contradicts anything already shipped.

**Recommendation: Option A.** This is a documented deviation from the
roadmap's literal "built on RecipeManager" phrasing, made necessary by
the feature-freeze rule discovered during this audit, not a
preference. `RecipeManager` remains completely untouched, available
for future work if a genuinely non-breaking bridge (e.g. a one-time,
read-only "convert this Recipe into a WorkflowDefinition" action) is
ever wanted — deferred, not designed here (§19).

## 5. Critical Design Issue — the "UI Foundation reviewed and approved" gate

`docs/MASTER_ROADMAP.md:2687-2688` lists Workflow Builder as paused:
*"not resumed until the UI overhaul work in §7's 'UI Foundation' has
been reviewed and approved."* Fresh-checked what that actually refers
to (`MASTER_ROADMAP.md:2405-2442`): a **PySide6 desktop-shell** design
pass (`ui/themes/typography.py`, `QFontDatabase`, vendored Lucide
icons, `domain/app_state/` state machine) — explicitly **not** the
separate `Jarvis-Frontend-main` React repository this session's Home
Automation slice was just integrated into. That same section's own
"Frontend migration note (Aug 2026)" states the Qt-specific rendering
half "is superseded by M8's React + Tauri rebuild... and is not
carried forward as code" — i.e. even the gate's own original referent
has since been migrated away from.

This gate, as literally worded, targets a UI stack (PySide6, or M8's
Tauri rebuild) that has no bearing on `Jarvis-Frontend-main` — the
repository the user explicitly directed all M7 frontend integration
into this session, and into which Home Automation's frontend slice
already shipped without this gate being invoked. **This Phase 0/1
produces no frontend code either way** (explicitly forbidden by this
phase's own scope), so the gate does not block writing this contract.
Whether it should gate a *future* Workflow Builder frontend phase is
flagged here for the user's attention, not resolved unilaterally.

## 6. Persistence

Two schema additions, both additive, neither touching Scheduler's or
Home Automation's existing tables:

- **`WorkflowRepository.update(workflow_id, *, name=None,
  description=None, steps_json=None) -> WorkflowDefinition | None`** —
  new method on the existing repository class (no new table). Partial
  update (only supplied fields change); returns `None` if the id
  doesn't exist (mirrors `delete`'s own `bool`-return not-found
  convention).
- **`WorkflowRepository.list_all() -> list[WorkflowDefinition]`** —
  new method; today nothing lists `workflow_definitions` at all
  (Scheduler/Home Automation only ever `.get()` a row they already
  know the id of via their own owning trigger).
- **New table `workflow_builder_executions`** — mirrors
  `AutomationExecution`'s exact shape (`id`, `workflow_id` FK
  CASCADE, `source` — always `"manual"` here, no event-triggered path
  exists for an unowned workflow — `started_at`, `finished_at`,
  `status`, `error`, `step_results_json`), **without** an owning
  trigger FK, since a Workflow-Builder-authored workflow has none. A
  parallel table, not a shared one — same reasoning `AutomationExecution`
  itself used against reusing `WorkflowExecution` (Logic Contract
  precedent: keep every owner's execution history in its own table so
  no owner's schema is ever widened for another's sake).

**Ownership model, explicit:** a `workflow_definitions` row created by
Workflow Builder is **never** referenced by a `Schedule` or
`AutomationTrigger` row, and vice versa — the two universes (trigger-owned
vs. standalone) do not intersect in this MVP. Attaching a
Workflow-Builder-authored workflow to a new Schedule or Automation
Trigger (i.e., letting `ScheduleService.create_schedule`/
`HomeAutomationService.create_automation` accept an existing
`workflow_id` instead of always creating one inline) is explicitly
**deferred** (§19) — it would require touching those two services'
already-shipped, already-tested create flows, which this contract
deliberately avoids to keep this slice's blast radius to purely new
code.

## 7. Workflow/step model usage

Identical wire shape to Scheduler/Home Automation's `steps` field:
`list[{"kind": "automation"|"agent_tool", "instruction"?, "tool_name"?,
"tool_args"?}]`, JSON-serialized into the existing `steps_json`
column — no new serialization format. `WorkflowStepKind` (the existing
`StrEnum`) is imported, not re-defined.

## 8. Validation

A third, local, deliberately-duplicated copy of `_validate_step`
inside the new `WorkflowBuilderService` — matching the established
convention (`schedule_service.py`/`home_automation_service.py` each
already have their own copy; a third stable, pure, ~15-line function
is cheaper and safer than a cross-service import). **Structural only**,
identical rules to the existing two: `kind` must be one of the two
allowed values, `instruction`/`tool_name` must be a non-empty string
matching the chosen kind. No semantic validation (tool existence,
instruction parseability) — matching the existing, explicit,
documented limitation (§3). At least one step required (empty
`steps` list rejected), matching Scheduler/Home Automation's own rule.

## 9. Execution semantics

`run_workflow(workflow_id) -> WorkflowBuilderExecution` — the only
execution path (no trigger exists to fire one automatically).
Deliberately mirrors `HomeAutomationService.run_automation`'s own
manual-test pattern: fetch the workflow, create a `queued` execution
row, call `self._workflow_executor.run_workflow(steps)` (the same
shared `WorkflowExecutionService`, zero duplication), finish the
execution with the real outcome, **await synchronously** (a manual
caller expects to wait for the result — same reasoning Home
Automation's own manual run uses). No background dispatch, no
EventBus subscription, no concurrency semaphore of its own needed —
there is no burst-of-events scenario here the way Home Automation has,
since nothing fires this automatically. Status vocabulary unchanged:
`queued`/`succeeded`/`partially_failed`/`failed`/`denied`/`cancelled`.

## 10. Failure semantics

Identical vocabulary and meaning to Scheduler/Home Automation
(§9 above) — no new failure modes introduced. A step's `denied` status
means confirmation was required and no `confirm` callback exists
(Policy A); `failed` means a real error; `partially_failed` means a
mixed-outcome multi-step workflow.

## 11. Permissions

New scope `"workflow_builder"` in `PERMISSION_SCOPES`
(`src/jarvis/core/plugins/sdk.py`) — 13th entry, same doc-comment
template as `scheduler`/`home_automation`'s own ("CRUD-only; does not
imply permission to execute the underlying action"). New principal
`core:workflow_builder`. `WorkflowBuilderService.__init__` declares it
via `self._permissions.declare(...)`, exactly like both existing
services. `_require_permission()` raises a service-specific
`WorkflowBuilderPermissionError`, same pattern.

## 12. Confirmation behavior

Policy A, always deny, **zero new authorization code** — every call
into `WorkflowExecutionService.run_workflow()` already hardcodes
`confirm=None` internally; `WorkflowBuilderService` supplies nothing
different from what Scheduler/Home Automation already supply. A
confirm-required `agent_tool` step is denied identically regardless of
which of the three services dispatched it.

## 13. REST API

New route file `src/jarvis/infrastructure/api/routes/workflow_builder.py`,
mounted in `fastapi_server.py` alongside the other 20+ resource
routers, identical `Depends(get_current_session)` + `{data, meta}`
envelope convention. Seven routes — the one genuinely new shape
relative to Scheduler/Home Automation is `PATCH` replacing
enable/disable (a standalone workflow has no "enabled" concept, since
nothing triggers it):

| Endpoint | Method | Body |
|---|---|---|
| `/api/v1/workflows` | `POST` | `{name, steps, description?}` |
| `/api/v1/workflows` | `GET` | — |
| `/api/v1/workflows/{id}` | `GET` | — |
| `/api/v1/workflows/{id}` | `PATCH` | `{name?, description?, steps?}` |
| `/api/v1/workflows/{id}` | `DELETE` | — |
| `/api/v1/workflows/{id}/run` | `POST` | — |
| `/api/v1/workflows/{id}/executions` | `GET` | — |

## 14. Agent tools

New `src/jarvis/agents/tools/workflow_builder_tools.py`, five tools
mirroring Scheduler's own selection logic (destructive `delete` stays
REST-only, matching both existing precedents exactly): `list_workflows`,
`get_workflow`, `create_workflow`, `update_workflow`, `run_workflow`.
Wired into `build_tool_registry()` (`agents/tools/registry.py`) and
`AgentOrchestrator` identically to Home Automation's own wiring this
session.

## 15. DI wiring

`_build_workflow_builder_service(...)` in `core/di/container.py`,
constructed with `database, permissions, settings,
workflow_executor=workflow_execution_service` — reusing the **same**
singleton `WorkflowExecutionService` instance Scheduler and Home
Automation already share (declared once, injected three times).
`workflow_builder_service` provider registered after
`workflow_execution_service`, alongside `schedule_service` and
`home_automation_service`. `AgentOrchestrator` gains a
`workflow_builder: Any` param, threaded through identically to
`home_automation`'s own wiring.

## 16. Security boundaries

`WorkflowBuilderService` must, like `HomeAutomationService` before it:
introduce no import of any connector class, no `EventBus` dependency
(nothing to subscribe to — no trigger, no event), no coupling to
Memory/Analytics/EventViewer, no raw connector payload or credential
field on `WorkflowBuilderExecution`, no direct device I/O of any kind
— every side effect flows through the existing, already-audited
`WorkflowExecutionService` → `AutomationService`/`AgentPermissionGate`
chokepoints, identical to both existing sibling services.

## 17. Frontend requirements (for a future Phase 2 frontend pass — no frontend code in this contract)

Target repository: `Jarvis-Frontend-main` (confirmed, per §5, to be
this milestone's correct target — the same repository Home Automation
integrated into). Fresh-reread this session:
`src/features/automations/AutomationForm.tsx` (`Jarvis-Frontend-main/frontend/`)
already has the right **interaction pattern** for a step-list editor —
a bordered section with an "Add" button, a `Select` + `Input` +
delete-`IconButton` row per item, dynamic add/remove via local
`useState`. **Its data model does not transfer**: `AutomationActionType`
is a fictional mock vocabulary (`'notify' | 'run-agent' | 'device' |
'integration'`) with no backend counterpart. A real Workflow Builder
step editor would need its own `Select` of exactly two real values
(`automation`/`agent_tool`) and, per §3's confirmed tool-enumeration
gap, would have to either restrict `agent_tool` step authoring to a
raw tool-name text field (advanced/unfriendly but honest) or omit
`agent_tool` steps from the MVP UI entirely and offer `automation`-kind
(natural-language instruction) steps only — the identical unresolved
gap `docs/M7_SCHEDULER_FRONTEND_REQUIREMENTS.md`'s own §4 already
documented, not a new problem this slice discovered. As confirmed
during Home Automation's own frontend audit this session, this
frontend has no auth mechanism anywhere yet, so any real Workflow
Builder frontend work would again ship mock-only unless auth is
solved first — that decision is out of this contract's scope to make.

## 18. Testing strategy

Mirrors the established matrix: permission enforcement (denied by
default, granted works), structural validation (empty steps rejected,
invalid `kind` rejected, missing `instruction`/`tool_name` rejected),
**new** update semantics (partial update only changes supplied fields,
updating a non-existent id reports not-found, steps re-validated on
update), list/get, manual execution outcomes (succeeded/partially
failed/failed/denied — reusing the same `WorkflowExecutionService`
already covered by its own 7 isolation tests, so this layer's tests
assert dispatch + persistence, not re-prove execution correctness),
execution history, REST route tests (mirroring
`test_m7_home_automation_route.py`'s exact fixture pattern), agent
tool tests, and scope guards (no connector/EventBus/Memory coupling —
identical assertion style to Home Automation's own three scope-guard
tests).

## 19. Deferred scope (explicit)

- Attaching a Workflow-Builder-authored workflow to a new Schedule or
  Automation Trigger (reuse-by-reference) — would require editing two
  already-shipped services' create flows; not touched here.
- Any bridge between `RecipeManager`/`Recipe` and `WorkflowDefinition`
  — `RecipeManager` is feature-frozen (M0–M6); disqualified in §4.
- A tool-enumeration/schema REST endpoint (a "tool picker") — the
  confirmed, pre-existing gap from §3; not built here.
- Semantic validation (does an `instruction` parse, does a `tool_name`
  exist) — structural-only, matching precedent.
- Multi-step parallel/dependency-graph execution exposure —
  `WorkflowExecutionService.run_workflow` is sequential-only by its
  own, unchanged design; not extended here.
- Edit history/versioning of a workflow's steps — `PATCH` overwrites,
  no revision log.
- Import/export, sharing, or AI-assisted/natural-language workflow
  generation.
- Any frontend implementation (§17 is requirements only).
- Recorder / Macro Engine (Phase 5) — explicitly out of scope per this
  phase's own instruction; not started, not referenced further.

## 20. Acceptance criteria

1. `WorkflowRepository.update`/`list_all` added; zero change to
   `add`/`get`/`delete`'s existing signatures or behavior.
2. Scheduler's full regression suite passes unmodified after this
   slice ships (proving `WorkflowRepository`'s existing three methods
   and `WorkflowExecutionService` are untouched in behavior).
3. Home Automation's full regression suite passes unmodified,
   identically.
4. A `workflow_definitions` row created via the new REST surface is
   never visible to, or reachable from, `ScheduleService` or
   `HomeAutomationService`.
5. Every `agent_tool` step dispatched through `run_workflow` with no
   `confirm` callback is denied when the tool is confirm-required —
   zero exceptions, zero new authorization code path.
6. No new import of any connector class, `EventBus`, Memory, or
   Analytics module appears in `workflow_builder_service.py`.

## 21. Hard stop conditions for Phase 2

Identical discipline to Home Automation's own contract: if
implementation reveals `WorkflowExecutionService`'s existing behavior
cannot be reused unmodified, if Scheduler's or Home Automation's
regression changes at all, if `WorkflowRepository`'s existing three
methods need behavior changes (not just new methods), if
`AgentPermissionGate`/`PermissionModel` need new capabilities beyond
what's described in §11–12, or if the ownership-separation described
in §6 turns out to be unenforceable without touching Scheduler/Home
Automation's own create flows — stop and report rather than
improvising.

## 22. Implementation order (sketch, for Phase 2 — not started)

`WorkflowRepository.update`/`list_all` → `workflow_builder_executions`
table + repository → `WorkflowBuilderService` → REST routes → agent
tools → DI wiring → tests → quality gates → docs. No frontend step in
this list; §17 governs a separately-approved future pass.
