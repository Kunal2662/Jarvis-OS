# M7 Scheduler MVP — Frontend Requirements

**Status: planning/specification document only. Contains zero frontend
source code.** Derived exclusively from the shipped, fully-tested
backend implementation (`src/jarvis/services/schedule_service.py`,
`src/jarvis/infrastructure/api/routes/schedules.py`) and its
authoritative Logic Contract (`docs/M7_SCHEDULER_LOGIC_CONTRACT.md`),
written after the backend's full regression, targeted tests, and
quality gates all passed. No frontend implementation accompanies this
file, and none is authorized by it. Nothing under `frontend/` was
read, inspected, or modified to produce this document.

## 1. Backend capability summary

**SHIPPED BACKEND CAPABILITY**: a new, persistent, timezone-aware
Scheduler — interval or 5-field-cron-triggered execution of a
minimal workflow (an ordered list of `automation`/`agent_tool` steps),
with restart recovery, a bounded-grace-period misfire policy, bounded
global concurrency, and a fail-safe (never fail-open) confirmation
policy for any step that would normally require interactive
confirmation. Seven REST routes under `/api/v1/schedules`, five agent
tools. No frontend surface exists for any of this today — the
existing `/automations` nav entry (already shipped, unrelated to this
milestone) resolves to a generic placeholder screen.

## 2. Backend API → frontend mapping

| Backend endpoint | Frontend page/component | Required state | API client change |
|---|---|---|---|
| `POST /api/v1/schedules` | Schedule creation form | form fields (name, kind, interval/cron, timezone, step list); server validation errors | new `createSchedule()` client function |
| `GET /api/v1/schedules` | Schedule list view | list of schedules, `enabled_only` filter toggle | new `listSchedules()` |
| `GET /api/v1/schedules/{id}` | Schedule detail view | one schedule + its latest execution summary | new `getSchedule()` |
| `POST .../{id}/enable` / `.../disable` | Enable/disable toggle on list or detail view | optimistic or refetch-on-toggle state | new `enableSchedule()`/`disableSchedule()` |
| `DELETE /api/v1/schedules/{id}` | Delete action (detail view or list row menu) | confirmation-before-delete UX (irreversible) | new `deleteSchedule()` |
| `GET .../{id}/executions` | Execution history panel on the detail view | paginated/limited list of past runs | new `listExecutions()` |

None of these exist today (§5 of the Phase 0 frontend audit already
confirmed zero pre-existing types, client functions, or contract slots
for this feature) — every row above is new frontend surface, not an
extension of something already built.

## 3. Schedule creation form

**FRONTEND IMPLEMENTATION REQUIRED.** Fields: name, description
(optional), kind (`interval`/`cron` toggle), then either an interval
(seconds, with client-side validation matching the backend's 60s
floor for a fast fail before the round trip) or a cron expression
(5-field POSIX only — the form should not offer a 6/7-field
seconds/year extension the backend will reject), a timezone picker
(IANA names — the backend defaults to UTC if omitted, so this can be
optional), and a step-list builder. **Natural-language schedule
creation ("every morning at 8") is explicitly out of scope for this
backend slice** (Logic Contract §13/§18) — do not build a free-text
field that silently fails to parse; a structured cron/interval builder
is the only backend-supported input shape today.

## 4. Step-list builder

**FRONTEND IMPLEMENTATION REQUIRED, and the least-defined part of this
surface.** Each step is either `{"kind": "automation", "instruction":
"<natural-language line>"}` (the same instruction shape the existing,
already-shipped automation UI already collects — reuse that input
pattern if one exists) or `{"kind": "agent_tool", "tool_name": "...",
"tool_args": {...}}`. **There is no backend-provided list of available
tool names or their argument schemas exposed by this API** — a
frontend wanting a friendly tool picker (rather than requiring the
user to know exact tool names/argument shapes) would need a
separate, not-yet-built backend capability to enumerate registered
tools. Until that exists, the honest MVP frontend either restricts
step creation to `automation`-kind steps only, or exposes `agent_tool`
steps as a raw JSON/advanced field for technically confident users.

## 5. Confirmation-required step warning — the most important UX requirement

**BACKEND CAPABILITY AVAILABLE**: `POST /api/v1/schedules` returns
`contains_confirm_required_steps: bool` in its response (accurate for
`agent_tool` steps against the live `confirm_required_tools` list;
**not** computed for `automation` steps — see the Logic Contract §2's
own documented limitation). **The frontend must surface this
prominently at creation time** with copy that is honest about what it
means: a confirmation-required step will **always be denied** when
this schedule fires unattended, in this version — there is no
interactive confirmation channel for scheduled execution yet.
Recommended copy: *"This schedule includes an action that normally
requires your confirmation (e.g. unlocking a door, arming/disarming a
system). Scheduled runs cannot ask for confirmation yet, so this step
will be skipped every time this schedule fires."* Do **not** present
this as a bug or a transient error — it is the deliberate, permanent
MVP security posture (Policy A, Logic Contract §2), not something a
retry or a different input will fix.

## 6. Execution history and denied-step display

**FRONTEND IMPLEMENTATION REQUIRED.** `GET .../{id}/executions`
returns each run's `status` (one of `succeeded`/`partially_failed`/
`failed`/`cancelled`/`skipped`/`denied` — the Logic Contract §6 set,
`timed_out` deliberately excluded as redundant) and a `step_results`
array with each step's own `status`/`error`. A `denied` step's `error`
string is the real, existing gate's own message (e.g. *"Denied:
run_automation is a sensitive action and needs your confirmation."*)
— render it directly rather than replacing it with a generic error,
since it already names the reason accurately. A `skipped` execution's
`error` names the misfire it recovered from (e.g. *"Misfire: schedule
was due at ...; skipped, not caught up."*) — this is informational, not
a failure state, and should not be styled identically to `failed`.

## 7. Schedule status display

**BACKEND CAPABILITY NOT AVAILABLE, by design, not a gap.** There is
no schedule-level `status` field distinct from `enabled` — the Logic
Contract §4 explicitly considered and rejected adding one, since it
would be a second, driftable source of truth alongside the latest
execution's own status. A frontend wanting to show "is this schedule
healthy" should derive it from `GET /{id}`'s embedded
`last_execution` object (present whenever the schedule has fired at
least once) rather than expecting a dedicated status field.

## 8. Permission states

Every route requires the existing `scheduler` permission scope
(`core:scheduler` principal) — a 400 response with a message
containing `"permission"` means ungranted, not a validation failure.
The frontend should distinguish this from other 400s (e.g. a bad cron
expression) by message content, matching the pattern already
established for other M12 permission-gated resources. Granting is via
the existing generic plugin-permissions flow
(`POST /api/v1/plugins/core:scheduler/permissions/scheduler/grant`) —
no new permission-granting UI pattern is needed.

## 9. Loading / error states

Standard REST loading/error handling — no scheduler-specific
network-timing concerns. One exception: `create_schedule`'s response
includes `contains_confirm_required_steps`, which should be read and
acted on (§5) immediately on a successful create, not just on
subsequent fetches.

## 10. API endpoints (full reference)

| Endpoint | Method | Body / Query |
|---|---|---|
| `/api/v1/schedules` | `POST` | `{name, kind, steps, description?, interval_seconds?, cron_expression?, timezone?, enabled?}` |
| `/api/v1/schedules` | `GET` | `?enabled_only=` |
| `/api/v1/schedules/{id}` | `GET` | — |
| `/api/v1/schedules/{id}/enable` | `POST` | — |
| `/api/v1/schedules/{id}/disable` | `POST` | — |
| `/api/v1/schedules/{id}` | `DELETE` | — |
| `/api/v1/schedules/{id}/executions` | `GET` | `?limit=` |

## Summary classification

| Item | Classification |
|---|---|
| Seven REST routes, five agent tools | SHIPPED BACKEND CAPABILITY |
| Schedule list/detail/creation views, enable/disable toggle, delete action, execution history panel | FRONTEND IMPLEMENTATION REQUIRED (not started) |
| Honest confirmation-required-step warning UX (§5) | FRONTEND IMPLEMENTATION REQUIRED — the single highest-priority UX item, since silence here would misrepresent a permanent security posture as a bug |
| A tool picker/schema browser for `agent_tool` steps | FRONTEND IMPLEMENTATION DEFERRED — needs a not-yet-built backend tool-enumeration capability |
| Natural-language schedule creation | BACKEND CAPABILITY NOT AVAILABLE — explicitly out of MVP scope |
| Schedule-level health/status field | BACKEND CAPABILITY NOT AVAILABLE, by design — derive from latest execution instead |
| Device-event/trigger-based scheduling UI | BACKEND CAPABILITY NOT AVAILABLE — blocked on a future, separately-scoped EventBus capability |
