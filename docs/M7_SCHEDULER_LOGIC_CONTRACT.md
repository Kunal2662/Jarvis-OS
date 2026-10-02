# M7 Scheduler (Phase 6) — MVP Logic Contract

**Status: Phase 1 planning document only. Contains zero source-code
changes.** Written per the M7 Phase 0 Audit's recommendation (B —
narrow prerequisite/design resolution required before implementation).
No implementation accompanies this document, and none is authorized by
it. Scope is the **Scheduler MVP only** — not Workflow Builder (Phase
4) and not Recorder (Phase 5), both of which remain later M7 slices
per the Phase 0 audit's own recommended sequence.

## 0. Fresh source verification (this session, HEAD `21735fc`)

Re-read directly, not trusted from the Phase 0 report: `domain/
workflow/models.py` (`WorkflowStepKind`, `ScheduleKind`, `WorkflowStep`,
`WorkflowDefinition`, `ScheduleDefinition`), `SchedulerSettings`
(`core/config/settings.py:565-576`), `AutomationSettings`
(`core/config/settings.py:462-482`, notably
`confirmation_timeout_seconds: float = 60.0` — an existing precedent
for a confirmation-adjacent TTL concept, cited in §3), `ActionExecutor`
retry/timeout constants (`features/automation/executor.py`, `max_retries`
via `Step.max_retries`, `retry_backoff_seconds=1.5`,
`default_step_timeout_seconds=120.0`), `PERMISSION_SCOPES`
(`core/plugins/sdk.py:34-47` — closed frozenset of 10 scopes, none of
which fit "scheduler," see §13), and `routes/sensors.py` for the
current REST envelope/auth convention. **Zero discrepancy found**
against the Phase 0 audit's findings — HEAD has not moved and no file
touched by this document's subject matter has changed. One fact the
Phase 0 report did not explicitly flag, confirmed here: `ScheduleDefinition`
has **no `timezone` field today** — this contract adds one (§5).

## 1. Final MVP scope

**In scope (per the Phase 0 audit's own required list, all addressed
below):** persistent schedules, interval schedules, cron schedules,
timezone-aware scheduling, enable/disable, cancellation (interpreted
precisely in §7), schedule listing/retrieval/creation, schedule
execution, execution history, restart persistence/recovery, bounded
concurrency, execution timeout (inherited, not reimplemented, §11),
retry behavior (inherited, not reimplemented, §11),
idempotency/duplicate-fire protection, and an explicit unattended
confirmation policy (§3).

**Out of scope, explicitly:** Workflow Builder UI, Recorder,
device-event triggers, EventBus rework, Smart Home event triggers,
geofencing, natural-language schedule generation, multilingual
scheduling, AI-generated workflows, cloud scheduling, remote
scheduling, frontend implementation, M14's real confirmation-channel
implementation. Each is addressed as a documented future integration
point in §17-§21, not built here.

## 2. Unattended confirmation policy (P1 design decision #1)

**Decision: Policy A — scheduled confirm-required actions are always
denied in MVP.** Evaluated against the audit's three options:

- **A (chosen): always deny.** Zero new authorization surface. Scheduler
  calls `AutomationService.run_command`/the relevant agent tool
  exactly as every other caller does today, supplying no `confirm`
  callback — both existing gates (`PermissionGate`,
  `AgentPermissionGate`) already fail-safe to `_default_deny` with no
  callback, confirmed unchanged in §0. Scheduler adds **zero** new
  code to either gate and cannot introduce a bypass, because it
  introduces no new execution path — only a new unattended *caller* of
  the same existing paths.
- **B (evaluated, deferred, not rejected): pre-authorization at
  schedule-creation time, scoped to specific actions.** Rejected for
  MVP specifically because it requires genuinely new, persisted
  security-adjacent state (what was authorized, for which tool/action,
  whether it expires, how it's audited, how it's revoked) — a real
  feature in its own right, not a "narrow prerequisite." The correct
  home for B is once a real interactive confirmation UX exists (M14 /
  a future Human Interaction surface, §18) to make "the user granted
  this in advance" a legitimate, auditable claim rather than a
  backend-only assumption. Recorded as the natural next increment, not
  discarded.
- **C (evaluated, rejected): any other bounded policy** (e.g. a
  allowlist of specific tool+arg combinations approved once, globally)
  — rejected for the same reason as B: it is new authorization
  surface, not a design decision expressible with zero new code.

**Consequences, defined precisely, per the audit's own checklist:**
- *At schedule creation:* creation is **never blocked** by the
  presence of a confirm-required step — Scheduler is not the workflow
  authoring surface (§6) and must not silently reject content it
  didn't validate for correctness elsewhere. Instead, `create_schedule`
  performs a **best-effort, non-blocking static scan** of the
  workflow's steps against the two already-existing, unmodified
  vocabularies (`CONFIRM_REQUIRED_ACTIONS` for `AUTOMATION`-kind steps,
  `AgentSettings.confirm_required_tools` for `AGENT_TOOL`-kind steps)
  and returns a `contains_confirm_required_steps: bool` flag in the
  response so the caller is informed up front, honestly, rather than
  discovering it only at first failed execution.
- *At execution:* each due step is dispatched through the same,
  unmodified call path any other caller uses, with no `confirm=`
  supplied. A confirm-required step is denied by the existing gate,
  exactly as it would be for any other unattended caller today.
- *If a step becomes confirmation-required after schedule creation*
  (e.g. a future settings change grows `confirm_required_tools`):
  handled automatically and correctly with zero special-case code,
  because Scheduler performs no caching of confirm-required status for
  enforcement — only the non-blocking, informational scan at creation
  time (above). The live gate is always the source of truth.
- *Authorization tied to tool name / arguments / expiry / restart
  survival / change handling:* **not applicable** — no pre-authorization
  state exists under Policy A.
- *How unauthorized (denied) execution is recorded:* every denied step
  is recorded in `WorkflowExecution.step_results_json` with the
  existing gate's own denial message (`AutomationPermissionDeniedError`'s
  string, or the agent tool's `"Denied: {err}"` pattern) — reusing
  existing error text verbatim, inventing no new message format.
- *Whether the schedule remains enabled after a denied execution:*
  **yes.** A denial is a policy-correct, by-design outcome, not a
  broken schedule — auto-disabling on denial would hide the problem
  rather than surface it. The execution history entry makes the denial
  visible; the user decides whether to fix or disable it themselves.

## 3. Event-trigger exclusion (P1 design decision #2)

**Explicitly time-based only.** Supported: `interval`, `cron`.
Explicitly excluded from MVP: device state changes, EventBus triggers,
sensor triggers, smart-home event triggers, connectivity triggers,
camera triggers, presence triggers. Reason, restated from the Phase 0
audit and re-verified unchanged in §0: no event exists anywhere in
`core/events/events.py` for a device's operational state (on/off,
sensor reading) changing — only connectivity/lifecycle transitions
(`discovered→paired→offline→removed`) are observable, and command
methods across all M12 device services publish nothing on success.
Event-triggered workflows require a **future, separately-scoped
EventBus/event-normalization capability** — not attempted, not
approximated, not silently assumed possible here. No EventBus file is
touched by this document or its eventual implementation.

## 4. Schedule data model

Extends the existing `ScheduleDefinition` dataclass shape (domain
layer, unchanged) into a persisted form. Every field justified
individually, per the audit's own "avoid speculative fields" instruction:

| Field | Why it exists | Source of truth | MVP need |
|---|---|---|---|
| `id` | Primary key | Generated (`uuid4().hex`, matching the existing `_uuid()` convention) | Required |
| `workflow_id` | FK to the persisted workflow row (§5) | Set at creation | Required |
| `kind` | `interval`/`cron` — already in the domain dataclass | User input | Required |
| `interval_seconds` | Already in the domain dataclass | User input (kind=interval) | Required |
| `cron_expression` | Already in the domain dataclass, already documented as 5-field | User input (kind=cron) | Required |
| `timezone` | **New.** IANA name (e.g. `"Asia/Kolkata"`); absent from the current dataclass (§0) — cron/interval math must be unambiguous regardless of host machine locale | User input, default `"UTC"` | Required — this is the actual MVP-required "timezone-aware scheduling" |
| `enabled` | Already in the domain dataclass — user on/off intent | User input | Required |
| `created_at` | Already in the domain dataclass | Generated | Required |
| `updated_at` | **New.** The dataclass was never mutated in place; a persisted, mutable row (enable/disable) needs an audit timestamp, matching every other mutable ORM row in this codebase (`Task`, `Reminder`) | Generated on write | Required |
| `next_fire_at` | **New.** So the firing loop can query "what's due" without recomputing cron/interval math for every schedule on every poll tick | Computed after each fire / at creation | Required |
| `last_fired_at` | Already in the domain dataclass (kept under this exact name for continuity) | Updated after each fire attempt | Required |
| `last_execution_id` | **New**, nullable FK to the most recent `WorkflowExecution` row — cheap, avoids a table scan for "how did this last run" | Updated after each execution | Useful, low-risk, included |
| `status` (schedule-level) | **Considered, rejected.** Redundant with `enabled` plus the latest `WorkflowExecution.status` — a second, independently-mutable field would be a second source of truth that can drift | N/A | **Not added** — derive "is this schedule healthy" from its latest execution at read time |
| `failure_count` | **Considered, rejected for MVP.** Not required by any MVP feature (no auto-disable-on-failure policy is in scope); computable from execution history if ever needed later | N/A | **Not added** |
| `version` (optimistic concurrency) | **Considered, rejected.** Single-user, single-process local app — no concurrent-writer contention to guard against in MVP | N/A | **Not added** |
| per-schedule concurrency config | **Considered, rejected.** A single, uniform, hardcoded rule (§10: skip if already running) applies to every schedule — no per-row knob needed | N/A | **Not added** |

`SchedulerSettings` (existing, unread today — activated by this
contract's implementation, not modified here) gains two **proposed**
fields for Phase 2 (not added in this document): `default_timezone:
str = "UTC"` (seeds a schedule's `timezone` when unspecified) and
`misfire_grace_period_seconds: float = 300.0` (§9).

## 5. Workflow model boundary

**Scheduler MVP does not expose a standalone Workflow-authoring API.**
Workflow Builder (Phase 4) owns that. Instead, `create_schedule` accepts
an inline workflow payload (a name plus an ordered list of
`WorkflowStep`-shaped entries, or — as a convenience — a reference to
an existing M4 `Recipe` by name, whose instruction lines are copied
into `AUTOMATION`-kind steps at creation time) and atomically creates
**one dedicated `WorkflowDefinition` row per schedule**.

- *Can the existing dataclasses be persisted directly?* No — they are
  framework-free Python dataclasses with no ORM mapping. A minimal
  `WorkflowDefinition` ORM row is needed, mirroring their shape with
  `steps` stored as a JSON text column (`steps_json`), following this
  codebase's own established convention (`TaskHistory.args_json`,
  `Reminder.recurrence_json`, `Device.metadata_json`).
- *Is workflow versioning required for Scheduler MVP?* **No.** Because
  no edit/authoring API exists for a `WorkflowDefinition` row in MVP
  (Workflow Builder doesn't exist yet), nothing can modify a workflow
  after its schedule creates it — the "workflow modified after
  scheduling" scenario cannot occur through any surface this document
  builds. Execution therefore always reads "whatever the row currently
  contains," which is a snapshot by construction, with zero explicit
  versioning machinery needed.
- *What happens when a workflow is deleted?* Each MVP workflow row is
  1:1 with the schedule that created it (no sharing/reuse across
  schedules in MVP) — deleting a schedule deletes its own dedicated
  workflow row. No independent "delete a workflow that other schedules
  still reference" scenario exists in MVP; the FK relationship stays
  general (many-to-one) so Workflow Builder can introduce real sharing
  later without a schema change.
- *Does execution use a snapshot/version?* Yes, implicitly, by
  construction (above) — no explicit version number needed.

## 6. Execution architecture

```
Scheduler firing loop (new, this contract)
  -> due ScheduleDefinition found
  -> WorkflowExecution row created (status=queued)
  -> for each WorkflowStep, in dependency order:
       AUTOMATION kind -> AutomationService.run_command(step.instruction)
       AGENT_TOOL kind -> the same agent-tool invocation path already
                           used by AgentOrchestrator's tool_executor node
  -> per-step outcome recorded into step_results_json
  -> WorkflowExecution.status finalized
```

**`ActionExecutor` is reused, never duplicated**, for `AUTOMATION`-kind
steps — `AutomationService.run_command` already wraps
`TaskPlanner`+`ActionExecutor` end to end; Scheduler calls that single
existing entry point, unchanged. `AGENT_TOOL`-kind steps reuse the
existing tool-invocation mechanism the agent graph already uses (`tool.
ainvoke(args)`), not a new dispatch mechanism.

**Execution lifecycle — evaluated against the audit's own candidate
list, each kept or dropped with a stated reason:**

| Status | Kept for MVP? | Reason |
|---|---|---|
| `queued` | Yes | A due schedule may wait for a global concurrency slot (§10) |
| `running` | Yes | In progress |
| `succeeded` | Yes | All steps succeeded |
| `partially_failed` | Yes | Mixed outcome — mirrors `ActionExecutor`'s own existing partial-failure concept |
| `failed` | Yes | No successes, and not exclusively denials |
| `cancelled` | Yes, narrowly | Only for a still-`queued` (not yet started) execution whose schedule was disabled/deleted before its turn — MVP does **not** implement cooperative mid-run abort of an already-`running` execution (would require modifying `ActionExecutor`, out of scope) |
| `timed_out` | **Dropped** | Redundant — a step timeout already surfaces as a step-level error inside `failed`/`partially_failed`; no separate top-level status adds information |
| `skipped` | Yes | A due fire skipped because its schedule was disabled between "became due" and "its turn," or a misfire outside the grace period (§9) |
| `denied` | Yes | Distinct top-level status when **every** step in the execution was denied (zero successes, zero non-denial failures) — a common, informative MVP case (§2). A mixed outcome (some denied + some succeeded/failed) is `partially_failed`, not `denied`. |

`WorkflowExecution` fields: `id`, `schedule_id` (FK), `workflow_id`
(FK), `started_at`, `finished_at` (nullable while queued/running),
`status`, `error` (nullable top-level summary), `step_results_json`
(list of `{step_id, status, error, duration_ms}`, mirroring
`TaskHistory`'s own existing shape/conventions).

## 7. Persistence model

Three new tables, minimal, using this codebase's existing SQLAlchemy
declarative conventions exactly (`Mapped[str]` uuid4-hex PKs,
tz-aware `datetime` columns, JSON-as-`Text` columns) — **not created
in this phase**, described only:

- `WorkflowDefinition` (`id`, `name`, `description`, `steps_json`, `created_at`)
- `Schedule` (fields per §4)
- `WorkflowExecution` (fields per §6)

**Why not reuse `TaskHistory`** (M4's existing automation-history
table)? Its schema (`plan_id`/`action`/`target`) fits one automation
*instruction* run, not a multi-step scheduled *workflow* run with its
own denial/partial-failure semantics — reusing it would force an
awkward shape mismatch rather than a clean, purpose-built table.

Per the Phase 0 audit's own persistence finding, re-confirmed unchanged
in §0: new tables are picked up automatically by the existing
`Base.metadata.create_all` runtime path with **no migration-authoring
step required**. No migration is written by this document.

## 8. Cron/interval semantics

**Interval:** minimum 60 seconds (finer-grained than that risks
imprecision against `SchedulerSettings.poll_interval_seconds`'s 30s
default). No maximum. First fire is `created_at + interval_seconds`
(not an immediate T+0 fire on creation) — matches the ordinary reading
of "check every 30 minutes." `next_fire_at` recomputed as `last_fired_at
+ interval_seconds` after every fire attempt, regardless of that
attempt's success/failure/denial (a schedule always advances; MVP has
no "retry the whole slot" concept, only per-step retry within one
attempt, §11).

**Cron:** standard 5-field POSIX syntax (minute, hour, day-of-month,
month, day-of-week) — matching the *already-shipped* domain dataclass's
own comment, re-verified in §0 (`# Populated when kind is CRON (5-field
cron expression)`), not a new decision. Validated and rejected with a
clear 400 at creation time if malformed — never persisted uncomputable.
Evaluated in the schedule's own `timezone` field, converted to a
tz-aware UTC `next_fire_at` for storage and comparison. DST: **adopt
the chosen cron library's own documented DST policy** (e.g. `croniter`
skips to the next valid wall-clock occurrence across a spring-forward
gap) rather than hand-rolling DST arithmetic — the responsible,
lowest-risk choice.

**Dependency required, not installed here:** `pyproject.toml` has zero
cron-parsing library today (re-confirmed, §0). `croniter` is the
recommended addition for Phase 2 — small, single-purpose (next-occurrence
computation only, no built-in daemon of its own to conflict with this
project's asyncio execution model). **Not installed by this document.**

## 9. Misfire / restart recovery policy

**One explicit MVP policy, chosen: bounded-grace-period catch-up.**
On startup, Scheduler loads every `enabled` schedule and compares
`next_fire_at` against the current time:
- If `next_fire_at` is in the future: normal, just wait.
- If `next_fire_at` is in the past but within `misfire_grace_period_seconds`
  (proposed new `SchedulerSettings` field, default 300s/5min, §4): fire
  **exactly once**, immediately, then resume normal scheduling from the
  next natural occurrence.
- If `next_fire_at` is further in the past than the grace period
  (process was down longer): **skip** — do not catch up, do not fire
  multiple times for multiple missed occurrences, resume from the next
  natural occurrence.
- A schedule that was `enabled=False` when the process went down is
  never evaluated for misfire at all — disabled schedules are excluded
  from the startup scan entirely, no special-case code needed.

Rejected alternatives, per the audit's own required evaluation: "fire
once immediately" unconditionally (no grace bound) risks firing a
long-stale schedule at a surprising moment with no user awareness it
was overdue; "catch up all missed executions" risks firing a
desktop-automation or (via `AGENT_TOOL` steps) M12 device-control
workflow many times in rapid succession after a multi-day outage —
unacceptable for a personal-assistant context. The bounded grace
period is the standard, well-precedented middle ground (mirroring
APScheduler's own `misfire_grace_time` convention, cited for precedent,
not adopted as a dependency).

## 10. Concurrency / duplicate-fire prevention

- **Global bound:** reuses the existing, currently-unread
  `SchedulerSettings.max_concurrent_jobs` (default 2) via a bounded
  semaphore — the same `gather_with_concurrency`-style pattern
  `ActionExecutor` already uses, for consistency with established
  codebase idiom. Not a second, unrelated concurrency system.
- **Per-schedule concurrency:** a schedule with an execution still
  `queued`/`running` is **skipped**, not double-queued, if it becomes
  due again before that execution finishes. This is the sole
  duplicate-prevention mechanism and needs no separate idempotency-key
  infrastructure — claiming a fire is exactly "atomically check for no
  existing non-terminal `WorkflowExecution` row for this `schedule_id`,
  then create one."
- **Overlapping runs:** impossible by the above rule.
- **When the global ceiling is full:** a newly-due, *different*
  schedule's execution is created with `status=queued` and waits
  (bounded, FIFO) for a concurrency slot — it is not skipped and not
  dropped.

## 11. Retry / timeout — three distinguished concepts

- **Step retry:** unchanged, entirely owned by `ActionExecutor`
  (`Step.max_retries`, `retry_backoff_seconds=1.5`, a 120s default
  per-step timeout via `asyncio.wait_for`, re-verified in §0). Scheduler
  does not reimplement this — it receives whatever `ActionExecutor`/the
  agent tool call already produces.
- **Workflow execution retry:** **none in MVP.** A failed or
  partially-failed `WorkflowExecution` is **not** automatically re-run
  before the schedule's own next natural fire. This keeps behavior
  predictable and avoids inventing a second, workflow-level
  backoff/max-attempts system not clearly required by the MVP feature
  list — the "retry behavior" requirement is satisfied by correctly
  inheriting and exercising the existing step-level mechanism, not by
  building a new one.
- **Schedule misfire:** a distinct concept from both of the above —
  about the *scheduler itself* failing to evaluate a schedule on time
  (process down), not about a step or workflow failing during an
  on-time attempt. Governed entirely by §9.

## 12. Permission model

**A new principal/scope is required — none of the 10 existing
`PERMISSION_SCOPES` fit** (re-verified in §0: `network`, `filesystem`,
`hotkey`, `agent_tools`, `voice.stt`, `voice.tts`, `memory.read`,
`memory.write`, `smart_home`, `notifications`). Proposed for Phase 2
(not added here): a new scope `"scheduler"` in `core/plugins/sdk.py`'s
`PERMISSION_SCOPES`, and a new principal `SCHEDULER_PRINCIPAL =
"core:scheduler"` following the exact `core:<category>` naming
convention every M12 service already uses, declared against the
existing, unmodified `PermissionModel`.

**This principal governs exactly one thing: CRUD on the Scheduler's
own resources** — create/read/modify/enable/disable/delete a schedule,
read execution history. **It explicitly grants nothing else.**
Executing a due step is independently, separately gated by whichever
existing gate already governs that step kind (`PermissionGate` for
`AUTOMATION`, `AgentPermissionGate` for `AGENT_TOOL`) — unchanged, per
§2. This separation is the single most important design decision in
this document: **a grant of the `scheduler` scope never implies a
grant of anything a scheduled workflow step would need.**

Manual "run this schedule right now" (outside its normal cadence) is
**not** included in MVP — not clearly required, and easy to add later
as a REST-only addition without a schema change.

## 13. Agent tools — minimum coherent surface

**Chosen: `list_schedules`, `get_schedule`, `create_schedule`,
`enable_schedule`, `disable_schedule`.** **Deliberately excluded from
the agent-tool surface** (available via REST only, §14): `delete_schedule`,
`cancel_schedule`. Reasoning: `disable_schedule` already achieves "stop
this from running" *reversibly*, covering the practical agent-facing
need; destructive/irreversible schedule management (permanent delete)
stays REST/UI-driven for MVP, consistent with this project's
conservative posture toward what the agent can do unilaterally.
Natural-language schedule interpretation is **out of scope** —
`create_schedule` takes *structured* parameters (cron expression or
interval seconds, timezone, workflow steps or a Recipe name); an LLM
caller composing that JSON from conversational context is not the same
as this codebase building new NLU infrastructure.

`create_schedule` is **not** added to `AgentSettings.confirm_required_tools`
— creating a schedule does not itself execute anything immediately;
future execution is independently gated per §2/§12.
`AgentPermissionGate`/`confirm_required_tools` are **not modified** by
this document.

## 14. REST API — minimum coherent surface

```
POST   /api/v1/schedules                    create (inline workflow payload)
GET    /api/v1/schedules                    list
GET    /api/v1/schedules/{id}               retrieve (+ latest execution summary)
POST   /api/v1/schedules/{id}/enable
POST   /api/v1/schedules/{id}/disable
DELETE /api/v1/schedules/{id}                delete
GET    /api/v1/schedules/{id}/executions     execution history
```

**Deliberately dropped from the audit's own candidate list:** a
separate `.../cancel` endpoint distinct from `enable`/`disable`/`DELETE`
— per §6's narrow interpretation, "cancel" only ever matters for a
still-`queued` execution being pre-empted by its own schedule's
disable/delete, which those two verbs already cover; a distinct
"cancel this one pending execution" use case is not clearly required
and would be easy to add later without a schema change.

Every route uses the existing `{data, meta}` `Envelope[T]` and
`Depends(get_current_session)` Bearer auth — the exact convention
`routes/sensors.py` and every other M9/M12 router already uses,
re-verified in §0.

## 15. Security model

Evaluated explicitly, per instruction:

- **Schedule tampering:** mitigated identically to every other
  resource — Bearer session auth + the new `scheduler` principal/scope
  gate on every mutating route.
- **Privilege escalation:** structurally prevented, not just
  policy-prevented — §12's separation means the `scheduler` scope
  cannot, by construction, grant execution rights beyond what the
  underlying step's own existing, unmodified gate already allows.
- **Scheduled unlock / disarm / panic / siren / vacation-mode /
  automation commands:** all governed by Policy A (§2) — auto-denied at
  execution time via the existing, unmodified gates, identically to how
  every other unattended caller is treated today. Zero new risk.
- **Authorization changes:** not applicable — no pre-authorization
  state exists under Policy A.
- **Workflow modification after schedule authorization:** not
  applicable — no live-reference/edit path exists in MVP (§5); each
  schedule's workflow is captured once, at creation, and never mutated
  by anything this document builds.

**Closing statement, directly answering the audit's own framing:**
Scheduler MVP can execute *nothing* that an equivalent manual,
un-scheduled call to `AutomationService.run_command`/an agent tool
couldn't already do today with no `confirm` supplied. It introduces
zero new execution path — only a new unattended *caller* of the exact
same existing paths, inheriting the exact same existing fail-safe
defaults. No scheduled action gains privilege silently, because no
scheduled action gains privilege at all beyond what already exists.

## 16. Frontend future requirements (not implemented, not touched)

A future Scheduler UI would need: a schedule list view; a creation form
(cron/interval builder, timezone picker, a workflow-step composer or
Recipe picker); an enable/disable toggle; an execution-history view
reflecting §6's status set; and honest failure/denied-state messaging
that surfaces *why* a step was denied (sourced directly from the
existing gate's own message text, §2) rather than presenting it as a
generic error. **Nothing under `frontend/` is inspected, modified, or
implied to change by this document** — these are requirements for a
future, separate frontend task.

## 17. M14 / Human Interaction integration points (not implemented)

- Real interactive confirmation (the eventual replacement for Policy A
  with Policy B, once a genuine UX exists to make pre-authorization a
  legitimate, auditable user decision).
- Clarification during conversational schedule creation (e.g. "did you
  mean every weekday, or every day?").
- Authorization grant/revoke UX, if/when Policy B is ever built.
- Notification of a failed or denied scheduled execution, once a real
  notification channel exists.

## 18. Multilingual integration (not implemented)

Natural-language schedule creation (Hindi/English/Marathi) is
explicitly deferred — the same future seam the Phase 0 audit already
identified in `TaskPlanner`'s own eventual NLU upgrade path. No i18n
code is added here.

## 19. AI Calibration integration (not implemented)

Future schedule/workflow interpretation from natural language, and
schedule-time suggestions, would go through the existing `ILLMProvider`
port — consistent with `ARCHITECTURE.md` §22's frozen boundary. No
provider-selection or cost logic is added by Scheduler MVP.

## 20. Cloud / Remote boundary — MVP is local-only

No cloud schedule sync, remote schedule creation, or cross-instance
schedule ownership. A future cloud-facing Scheduler needs the same
missing `User`/`Account`/`Tenant` identity model the M0-M12 audit
already found absent (the `Home` table has no ownership FK) — restated
here for completeness, not new information, not addressed by this
document.

## 21. Test strategy

**Persistence:** create/retrieve/update/delete a `Schedule`; a
`Schedule` created, then re-read after simulating a process restart
(fresh service instance against the same DB), still present with
correct `next_fire_at`.

**Scheduling:** interval next-fire calculation; cron next-fire
calculation across a representative expression set; timezone
correctness (a schedule in `Asia/Kolkata` fires at the locally-correct
UTC instant); an explicit DST-transition-date test exercising the
chosen library's documented behavior; enable/disable toggles
`next_fire_at` evaluation; delete removes the schedule and its
dedicated workflow row.

**Recovery:** a schedule whose `next_fire_at` is within the grace
period fires exactly once on restart; a schedule whose `next_fire_at`
is well past the grace period is skipped, not caught up; multiple
missed occurrences never produce multiple fires.

**Execution:** all-steps-succeed → `succeeded`; a mix of success/failure
→ `partially_failed`; a mix of success/denial → `partially_failed`; a
confirm-required-only workflow → `denied`; a step timeout surfaces
inside `failed`/`partially_failed` via `ActionExecutor`'s existing
mechanism (not a new top-level status); a second due fire of a
still-running schedule is skipped, never double-executed; the global
concurrency ceiling correctly queues excess due schedules and never
exceeds `max_concurrent_jobs`. Per CLAUDE.md's own testing convention:
timing-dependent tests poll for an observable condition, never
`sleep(fixed)`.

**Security:** `create_schedule`/mutating routes denied without the
`scheduler` scope granted; a confirm-required `AUTOMATION` step is
denied at execution with the schedule remaining enabled afterward; the
identical result for a confirm-required `AGENT_TOOL` step; confirm that
granting the `scheduler` scope alone does **not** newly permit any
action the underlying gates would otherwise deny (an explicit
non-bypass regression test).

**API:** envelope shape matches every other resource router; Bearer
auth required on every route; validation-error shape for a malformed
cron expression (rejected at creation, never persisted); 404 for an
unknown schedule id.

**Scope guards (explicit, per instruction):** a dedicated test/assertion
confirming this implementation phase, when it lands, touches zero
`EventBus` publish sites for device state; adds no Recorder code; adds
no Workflow Builder authoring API; adds no multilingual/i18n code; adds
no AI-generation code; adds no cloud/remote code; and — checked at the
git-diff level during implementation, not as a unit test — zero
`frontend/` files change.

## 22. Acceptance criteria

The MVP is complete only when: schedules persist and survive a process
restart with correct `next_fire_at`; interval and cron firing both
work; the configured timezone is respected including a documented,
deterministic DST policy; the misfire policy (§9) is deterministic and
tested; duplicate execution is impossible (per-schedule and globally);
execution history is queryable per schedule; concurrency is bounded by
`SchedulerSettings.max_concurrent_jobs`; the `scheduler` permission
scope is enforced on every mutating route and read route; the
underlying step-execution gates (`PermissionGate`, `AgentPermissionGate`)
are never bypassed, with a regression test proving it; the Policy A
confirmation behavior (§2) is explicitly enforced and tested;
device-event triggers are absent from the implementation; `EventBus`,
`AutomationService`, `ActionExecutor`, `PermissionGate`, and
`AgentPermissionGate` source files are unmodified; Workflow Builder and
Recorder remain unimplemented; zero `frontend/` files change; full
backend regression passes.

## 23. Deferred scope (restated for closure)

Workflow Builder authoring UI/API (Phase 4), Recorder (Phase 5),
device-event triggers (blocked on a future EventBus capability),
manual on-demand "run now," schedule-level auto-retry, `cancel`-as-a-
distinct-verb, Policy B pre-authorization, real interactive
confirmation (M14/Human Interaction), multilingual/natural-language
schedule creation, AI-assisted schedule generation, cloud/remote
scheduling. Each has a named, correct owner (this document or a future
milestone) — none is silently dropped.
