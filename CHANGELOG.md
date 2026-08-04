# Changelog

All notable changes to JARVIS OS are documented here. Format loosely
follows [Keep a Changelog](https://keepachangelog.com/).

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
