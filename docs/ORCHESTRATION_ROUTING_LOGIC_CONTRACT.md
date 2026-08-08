# Conversational Orchestration Routing — Module Logic Contract

**Milestone:** M10 — AI Orchestrator (closing the "Intent Engine gating
graph routing" and "Remaining UI integration" deferrals recorded in
`MASTER_ROADMAP.md` §8's M10 Closure Summary)
**Status:** written before implementation, per `MASTER_ROADMAP.md` §4's
binding rule: *"No implementation may begin until its module's Logic
Contract is complete."*
**Scope of this document:** wiring the already-shipped `AgentOrchestrator`
into the two conversational entry points (Desktop Chat, Voice) that
currently bypass it, and consuming the already-shipped Intent Engine's
output (`state["intent"]`/`state["intent_confidence"]`) as a real
routing signal inside the already-compiled graph. **This is not a new
component.** No new orchestrator, no new AI Core, no new planning
logic — see the Phase 0 audit for the verified inventory of what
already exists and is being extended, not replaced.

---

## Purpose

Close two gaps M10's own Closure Summary already named and left open:
*"Intent Engine gating graph routing — today the classification is
recorded but diagnostic-only"* and *"Remaining UI integration — wiring
... a React frontend surface to `/api/v1/agent` is M8's own remaining
phases."* Both of M10's cited blockers for the first gap (M10A, M10B)
have since shipped (✅ Completed, `MASTER_ROADMAP.md` §2). This module
makes intent classification actually gate routing, and makes the two
real conversational surfaces (Chat, Voice) reach `AgentOrchestrator`
instead of `ChatService.stream()` directly — behind a feature flag,
so existing behaviour is preserved by default and the two paths can be
compared safely.

## Responsibilities

- Add one new conditional edge to the **existing, already-compiled**
  graph (`agents/graph.py`) so `intent_classifier`'s output can route
  directly to `responder`/`END` for a high-confidence `direct_answer`,
  skipping `context_engine`/`planner`/`tool_selector` entirely — the
  literal meaning of "gating," not a new decision-making component.
- Give `ConversationController` (Desktop Chat) and the voice pipeline
  (`VoiceController.transcribed` → today's same `ConversationController
  .send()`) a second code path that calls `AgentOrchestrator.stream()`
  instead of `ChatService.stream()`, selected by a settings-driven
  routing mode (`AgentSettings.conversation_routing`).
- Preserve `ChatService`/`ConversationService`'s own persistence
  contract exactly: whichever path runs, the same conversation history
  table gets the same user/assistant message rows, in the same shape,
  so switching modes never orphans or duplicates history.

**Explicitly not this module's responsibility:** replacing `ChatService`
(M0–M6 frozen — extended around, per `CLAUDE.md`, not edited for new
behaviour beyond the minimal call-site change Phase 2 requires), adding
new tool categories, changing `AgentOrchestrator`'s own public
`invoke()`/`stream()` contract, building a new Provider Manager/Context
Builder/Event Bus (all already exist — see the Phase 0 audit), or
finishing M10's other still-open deferrals (Knowledge Graph gating,
final M14 Authorization Engine integration, Learning/Feedback via M16,
`tool_selector`'s "final"-shortcut streaming limitation) — none of
which this routing work touches or depends on.

## Business logic

- Intent gating only fires for the **already-existing** `next_action`
  vocabulary's true equivalent at the intent-classifier boundary: a
  new conditional edge, `intent_classifier → (direct-route) responder`
  vs. `intent_classifier → context_engine` (today's only edge),
  keyed on `intent == "direct_answer" and intent_confidence >=
  <threshold>`. `clarification_needed` and `tool_use` (and any
  low-confidence `direct_answer`) take the existing, unchanged path
  through `context_engine → planner → tool_selector`. No new intent
  values, no new classifier — `agents/nodes/intent_classifier.py` is
  unmodified.
- The direct-route path still ends at `responder` (Decision Engine),
  which still decides `response_mode`, unchanged — gating skips
  *planning/tool-selection*, never skips the Decision Engine itself.
- Conversation routing (Chat/Voice → `ChatService` vs.
  `AgentOrchestrator`) is a single settings-driven mode, not a
  per-request heuristic: `LEGACY` (default — 100% `ChatService`,
  byte-for-byte today's behaviour), `HYBRID` (both paths run behind the
  same `ConversationController` API, selectable, for side-by-side
  verification — not "some requests randomly go one way"), `ORCHESTRATOR`
  (100% `AgentOrchestrator`). The mode is read once per call, not
  cached across the process lifetime, so a settings change takes effect
  on the next message without a restart.
- `AgentOrchestrator.stream()`'s existing `thread_id` becomes the
  bridge to `ConversationService`'s existing `conversation_id`: reused
  as the same string when both exist for one conversation (mirroring
  `SessionManager`'s own already-established pattern of two real ids
  optionally sitting side by side, per `core/lifecycle/
  session_manager.py` — not a new id space).

## Inputs

- The user's prompt text (unchanged shape: a plain string, from either
  `_chat_page.prompt.submitted` or `_voice_controller.transcribed`).
- `conversation_id` (existing, from `ConversationController`'s own
  active-conversation tracking).
- `AgentSettings.conversation_routing` (new field: `"legacy" |
  "hybrid" | "orchestrator"`, env-overridable like every other
  `AgentSettings` field, default `"legacy"`).
- `AgentSettings` intent-gating threshold (new field:
  `intent_direct_route_confidence`, default conservative enough that
  gating only fires on genuinely high-confidence classifications).

## Outputs

- Identical `ConversationController` Qt signals regardless of routing
  mode: `stream_started`, `token`, `stream_finished`, `error` — widgets
  (chat view, voice controller's token-to-speech bridge) do not know or
  care which backend produced the tokens.
- The same persisted `Message` rows via `ConversationService`, whichever
  path ran.
- `AgentStepEvent`s on the `EventBus` when the `ORCHESTRATOR`/`HYBRID`
  path runs (already published by `AgentOrchestrator.stream()`
  unchanged) — Activity Center gains real conversational step visibility
  for the first time as a side effect, with zero new event-publishing
  code.

## Dependencies

Per this project's own governing rule (`ARCHITECTURE.md` §22.18): this
work needs no provider routing, no cost control, no voice-provider
selection, no hardware profiling — it is pure composition-layer wiring
between two already-shipped components, so it does not implicate the
frozen Universal AI/API Calibration Engine and raises no blocker.
Within M10: `AgentOrchestrator` (M5A/M10, existing), `ChatService`
(M0–M6, existing, unmodified), `ConversationController`/`VoiceController`
(M2/M5, existing). M10's own formally-declared dependency on M14
(Permission Validation) is unaffected — `HYBRID`/`ORCHESTRATOR` mode
inherits `AgentOrchestrator`'s existing interim `AgentPermissionGate`
exactly as the REST endpoints already do today; this module adds no
new permission surface.

## Permission model

Unchanged. `AgentOrchestrator`'s existing `AgentPermissionGate`
(interim, per M10 AC3) already gates every tool call regardless of
caller; routing Chat/Voice through it inherits that gate for free — a
strict improvement over `ChatService.stream()`, which has no tool
access and therefore no permission surface at all today.

## State machine

Per conversation turn, `ORCHESTRATOR`/`HYBRID` mode: unchanged from
`AgentOrchestrator`'s own existing graph execution (see the Phase 0
audit's node sequence). The only new state transition is the intent
classifier's own conditional edge:
`intent_classifier → {context_engine | responder}` — a single new
branch on an existing node's existing output fields, not a new state
machine.

## Validation rules

- `AgentSettings.conversation_routing` is a closed three-value
  vocabulary (`legacy`/`hybrid`/`orchestrator`); an unrecognized value
  fails Pydantic settings validation at startup, not silently at first
  use — the same "reject a typo at construction" discipline
  `ConnectorFactoryRegistry`/`TransportFactoryRegistry` already apply.
- `intent_direct_route_confidence` is validated `0.0 <= x <= 1.0` at
  the settings layer.

## Failure behaviour

- If `AgentOrchestrator.stream()` raises in `HYBRID`/`ORCHESTRATOR`
  mode, the failure surfaces through `ConversationController.error`
  exactly as a `ChatService` failure does today — no silent fallback
  to `ChatService` mid-request that would leave the user unable to
  tell which backend actually answered. `HYBRID` mode's whole purpose
  is *visible* comparison, not silent failover between the two.
- A malformed/missing intent classification (already handled by
  `intent_classifier.py`'s own existing fallback to `tool_use`/0.5)
  routes through the unchanged `context_engine` path — the new gating
  edge never fires on a fallback classification, since `tool_use` never
  qualifies for direct-routing regardless of confidence.

## Recovery behaviour

- No new recovery mechanism. `AgentOrchestrator`'s existing checkpointer
  (`agents/checkpointer.py`) and `ChatService`'s existing persistence
  are both already durable independently; this module does not add a
  cross-path recovery story, since `LEGACY` remains the default and
  `HYBRID`/`ORCHESTRATOR` are opt-in.

## Logging

No new secrets or credentials enter this module's scope. Log lines
follow existing convention: routing-mode decisions logged at `info`
(mirrors `_build_llm_provider`'s own "which path was selected and
why" logging style), never the prompt text itself beyond what
`ChatService`/`AgentOrchestrator` already log today.

## Telemetry / Events

No new `Event` class. `AgentStepEvent` (existing, M10) is reused
as-is — `HYBRID`/`ORCHESTRATOR` mode is what newly causes it to fire
for ordinary conversation turns, not a new event this module defines.

## Tests

Fakes-first, per this project's own convention: a `ScriptedFakeLLM`
(already exists, used by M10's own AC2 verification per the M10
Closure Summary) drives intent-classifier output deterministically for
routing tests, rather than a real LLM call. Real (in-memory/temp-file)
`ConversationService` persistence throughout, matching every other
service test in this codebase — no mocked repository.

## Acceptance criteria (this module's own, distinct from M10's
milestone-level AC, which remain unchanged and unaffected)

1. A `direct_answer` classification at or above the configured
   confidence threshold skips `context_engine`/`planner`/`tool_selector`
   in the compiled graph, verified by node-visit assertions against a
   real (not mocked) `AgentState` trace.
2. A `tool_use` or low-confidence `direct_answer` classification takes
   the existing, byte-for-byte-unchanged path through
   `context_engine → planner → tool_selector`.
3. With `conversation_routing="legacy"` (the default), Desktop Chat and
   Voice behave identically to pre-existing behaviour — verified by a
   regression run, not merely asserted.
4. With `conversation_routing="orchestrator"`, both Desktop Chat and
   Voice reach `AgentOrchestrator.stream()`, and the resulting messages
   persist through `ConversationService` identically to the `legacy`
   path's own persisted shape.
5. `conversation_routing="hybrid"` makes both paths available without
   either silently replacing the other on failure.
6. Switching `conversation_routing` requires no other file to change —
   the DI composition root is the only place the mode is read.
