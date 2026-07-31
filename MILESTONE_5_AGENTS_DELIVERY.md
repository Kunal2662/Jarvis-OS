# Milestone 5-Agents — Agent Runtime (LangGraph): Delivery Summary

> Renumbered slot: this is the "Agent Runtime" originally planned as
> Milestone 5, before that label shipped the Official UI & Frontend
> Framework instead (see `MILESTONE_5_DELIVERY.md` and
> `docs/MASTER_ROADMAP.md` §1's scope note). Version bumped `0.3.0` →
> `0.4.0` on this delivery.
>
> **Update — pre-merge validation pass (Jul 2026):** this milestone was
> subsequently installed into a real venv, statically analyzed, and run
> end-to-end for the first time (see `AUDIT_REPORT_M5-AGENTS.md`).
> Every code-level finding from that pass is folded into this doc's
> §1/§2 below; the one runtime bug it found — a real
> `langgraph-checkpoint-sqlite`/`aiosqlite` incompatibility that made
> the *default* checkpointer path (`checkpoint_enabled=True`) fail on
> the first real graph invocation — is fixed (`aiosqlite` pinned
> `<0.21` in `pyproject.toml`/`requirements.txt`) and covered by a new
> regression test (`test_invoke_with_real_sqlite_checkpointer`). See
> `AUDIT_REPORT_M5-AGENTS.md` for the full validation report.

## 1. Files Created

**Agent runtime core (`src/jarvis/agents/`)**
- `state.py` — `AgentState`, the `TypedDict` threaded through every node.
- `prompting.py` — shared node-prompt helpers: `safe_complete` (never
  raises), `parse_json_object` (tolerant JSON extraction), tool/history
  formatters, and `UNTRUSTED_TOOL_OUTPUT_NOTICE` (prompt-injection
  fencing for tool output).
- `checkpointer.py` — `AgentCheckpointer`, owns the LangGraph
  checkpoint saver's lifecycle (SQLite via `AsyncSqliteSaver`, or an
  in-memory fallback).
- `graph.py` — `build_agent_graph()`: compiles the `StateGraph`.

**Nodes (`src/jarvis/agents/nodes/`)** — one factory function each:
`planner.py`, `tool_selector.py`, `tool_executor.py`, `critic.py`,
`responder.py`.

**Tools (`src/jarvis/agents/tools/`)** — one module per source service:
`memory_tools.py`, `automation_tools.py`, `browser_tools.py`,
`system_tools.py`, `voice_tools.py`, `chat_tools.py`, plus
`registry.py` (`build_tool_registry`).

**UI**
- `src/jarvis/ui/views/developer/agent_trace_view.py` — the Developer
  Mode "Agent Trace" section.

**Tests**
- `tests/fakes/fake_scripted_llm.py` — `ScriptedFakeLLM`, a
  substring-keyed fake `ILLMProvider` that can drive a whole multi-node
  graph run deterministically (unlike `FakeLLM`'s single canned answer).
- `tests/unit/test_system_service.py`
- `tests/unit/test_agent_prompting.py`
- `tests/unit/test_agent_nodes.py`
- `tests/unit/test_agent_tools_registry.py`
- `tests/unit/test_agent_checkpointer.py`
- `tests/integration/test_agent_orchestrator.py`

**Docs**
- This file.

## 2. Files Modified

- `src/jarvis/agents/orchestrator.py` — full rewrite:
  `AgentOrchestrator.start/stop/invoke/stream` now real (were
  `NotImplementedError`); constructor widened with optional
  `chat`/`voice`/`system`/`event_bus`.
- `src/jarvis/agents/__init__.py`, `agents/nodes/__init__.py`,
  `agents/tools/__init__.py` — docstrings updated; `tools/__init__.py`
  now re-exports `build_tool_registry`.
- `src/jarvis/services/system_service.py` — `status()` implemented for
  real (was a stub since Milestone 1).
- `src/jarvis/core/exceptions.py` — added `AgentStepLimitExceededError`,
  `ToolExecutionError`, `CheckpointError` (all under `AgentError`).
- `src/jarvis/core/events/events.py` — added `AgentStepEvent`.
- `src/jarvis/core/config/constants.py` — added
  `DEFAULT_AGENT_CHECKPOINT_DB_FILE`.
- `src/jarvis/core/config/paths.py` — added `agent_checkpoint_db_path()`.
- `src/jarvis/core/config/settings.py` — `app_version` `0.3.0` → `0.4.0`
  (no `AgentSettings` field changes — `max_steps`/`timeout_seconds`/
  `checkpoint_enabled` already existed and were sufficient).
- `src/jarvis/core/di/container.py` — `agent_orchestrator` provider now
  also wires `chat=chat_service, voice=voice_service,
  system=system_service, event_bus=event_bus`.
- `src/jarvis/services/settings_service.py` — added
  `JARVIS_AGENT_MAX_STEPS` / `JARVIS_AGENT_TIMEOUT_SECONDS` /
  `JARVIS_AGENT_CHECKPOINT_ENABLED` to the writable-key whitelist.
- `src/jarvis/ui/views/developer/developer_dashboard.py` — new "Agent
  Trace" nav section wired to `AgentTraceView`.
- `src/jarvis/ui/main_window.py` — `agent_orchestrator.stop()`
  registered with `ShutdownManager` at `PRIORITY_EARLY`.
- `pyproject.toml` / `requirements.txt` — added
  `langgraph-checkpoint-sqlite>=1.0,<3.0`; version bumped to `0.4.0`
  in `pyproject.toml`.
- `src/jarvis/__version__.py` — `0.3.0` → `0.4.0`.
- `docs/MASTER_ROADMAP.md` — Milestone 5-Agents marked done throughout
  (§1, §2, §3 feature tables, §9 version timeline, §10 technical debt).
- `CHANGELOG.md` — new `[0.4.0]` entry.

## 3. Architecture

```
Developer Mode "Agent Trace" view ──┐
                                     ▼
                      AgentOrchestrator (IAgentOrchestrator)
                      ─────────────────────────────────────
                      start()/stop()  →  AgentCheckpointer
                      invoke()/stream() → compiled StateGraph
                                     │
        ┌────────────────────────────────────────────────────┐
        │  planner → tool_selector ─┬→ tool_executor → critic │
        │      ▲                    │        │           │   │
        │      │                    └───(final)→ responder   │
        │      └──────────────(loop back)──────────┘         │
        └────────────────────────────────────────────────────┘
                                     │
                     agents/tools/registry.build_tool_registry()
                                     │
        MemoryService · AutomationService · BrowserService ·
        SystemService · VoiceService · ChatService
                    (existing services — unchanged)
```

Every LLM call in the graph goes through the existing `ILLMProvider`
port via `agents/prompting.py::safe_complete` — no second,
langchain-native chat-model port was introduced. `langchain_core.tools`
is used only to give each tool a name/description/JSON-schema and a
uniform `.ainvoke(args)` call surface; tool *selection* is a
structured-JSON decision parsed out of a normal `ILLMProvider.complete()`
call (see `agents/prompting.py`'s module docstring for the full
reasoning). LangGraph's `StateGraph` + checkpointer is where this
milestone's declared dependencies earn their keep.

## 4. Request Flow — one `invoke()` call, end to end

1. `AgentOrchestrator.invoke(AgentRequest(prompt=...))` calls
   `start()` (idempotent) — opens the checkpointer, builds the tool
   registry, compiles the graph.
2. `planner` asks the LLM for a short numbered plan given the prompt +
   available tool descriptions.
3. `tool_selector` asks the LLM (structured JSON) whether to call a
   tool next or answer directly. An unrecognized tool name is never
   trusted through — falls back to "final" with an empty answer rather
   than crashing.
4. If a tool was chosen: `tool_executor` calls
   `tool.ainvoke(args)`, appends `{tool, args, result|error}` to
   `tool_calls`, increments `step`.
5. `critic` asks the LLM (structured JSON) whether the request is now
   satisfied. If not, and `step < max_steps`, loops back to
   `tool_selector` for another round. `max_steps` (clamped against
   `constants.MAX_AGENT_STEPS_HARD_CAP = 200`) is a hard stop
   regardless of what the critic says.
6. `responder` composes the final answer from the plan + tool results
   — unless `tool_selector` already wrote one directly (the
   no-tool-needed path), in which case it's a no-op pass-through.
7. `AgentOrchestrator` publishes one `AgentStepEvent` (for `invoke()`;
   `stream()` publishes one per node transition) and returns an
   `AgentResponse(text, thread_id, steps, metadata={tool_calls, plan,
   critique})`.

## 5. Remaining Work

- **Vision tool** — deliberately deferred to Milestone 6, where a real
  screen-capture + multimodal-`ChatService` pipeline is already scoped.
  Building a one-off version here would have meant redoing it there.
- **Chat integration** — the existing Chat view still calls
  `ChatService` directly; the agent is a standalone, independently
  invokable system (Developer Mode's Agent Trace panel today). Wiring
  a chat-facing "Agent Mode" is future work, kept out of this
  milestone to avoid risking the stable Milestone 1 chat flow.
- **True token-level streaming** — `stream()` re-chunks the
  already-composed final answer word-by-word; it does not stream real
  LLM tokens from inside the responder node's own LLM call. Building
  that would mean restructuring the responder node around
  `ILLMProvider.stream()` and threading tokens back out through the
  graph — deferred rather than built against an unverified LangGraph
  message-streaming API surface in a no-network authoring environment.
- **No per-step timings** — the Agent Trace panel shows step number,
  node, status and a short detail string, but no `duration_ms`;
  `AgentState` doesn't record one. Would follow the same pattern as
  `automation`'s `StepResult.duration_ms`.
- **No checkpoint-resume UI** — the checkpointer persists state keyed
  by `thread_id` and survives a restart, but the Agent Trace panel
  always starts a fresh thread (`AgentRequest(prompt=...)` with no
  `thread_id`). Nothing in the UI yet lets a user pick "resume thread
  X." Plumbing is done; exposing it is follow-up work.
- **No automation confirmation path** — `automation_tools.run_automation`
  never passes a `ConfirmationCallback`, so per
  `AutomationSettings.auto_deny_when_unconfirmable` any action needing
  interactive confirmation is auto-denied. Safe by default, but means
  the agent can't complete a task that legitimately needs user
  confirmation without a real UI hook for that.
- **`SystemService.status()` de-duplication** — System Information and
  Performance Monitor's Developer Mode views still call `psutil`
  directly rather than through the now-real `SystemService.status()`.
  Left as-is to keep this milestone's diff scoped to what the agent
  tool needed; still a nice-to-have cleanup.
- **No dedicated Agents Settings page** — `max_steps` /
  `timeout_seconds` / `checkpoint_enabled` are on the writable-key
  whitelist but have no Settings UI page yet (not called for by this
  milestone's own feature list, unlike Milestone 6's explicit "Vision
  settings page").
- ~~Tests not executed in the authoring environment~~ — **cleared by
  the pre-merge validation pass**: real venv, `pip install -e
  ".[dev]"`, full suite run. 308/309 passing (1 pre-existing,
  documented `pytest-aiohttp`-extra exclusion, unrelated to this
  milestone). See `AUDIT_REPORT_M5-AGENTS.md`.
- **Known CVE in `langgraph-checkpoint-sqlite` 2.0.11**
  (`CVE-2025-67644`, SQL injection via unvalidated checkpoint-metadata
  *filter keys* in `.list()`/`get_state_history()`). **Not exploitable
  by anything shipped in this milestone** — nothing here ever calls a
  checkpoint search/list/history API with filter keys, let alone
  untrusted ones (`AgentOrchestrator` only calls `ainvoke`/`astream`
  with a fixed `{"configurable": {"thread_id": ...}}` config). Flagged
  as a hard constraint for the "checkpoint-resume UI" item above: if
  that's ever built, filter *keys* must never come from user input
  without an allowlist, even after upgrading past the patched version.
- **`aiosqlite` pinned `<0.21`** (`pyproject.toml`/`requirements.txt`)
  — `langgraph-checkpoint-sqlite` 2.0.11's `AsyncSqliteSaver.setup()`
  calls `self.conn.is_alive()`, which only exists because older
  `aiosqlite` `Connection` subclassed `threading.Thread`; `aiosqlite`
  0.21+ dropped that base class. Without the pin, `AgentCheckpointer.
  open()` still succeeds (the bug is inside `setup()`, called lazily on
  first real use) but the *first actual graph invocation* with the
  default `checkpoint_enabled=True` raises `AttributeError`. Found via
  a live end-to-end smoke run outside pytest, since the original unit
  tests only covered `open()`/`close()`, never a real invocation
  through the SQLite path — closed by a new regression test,
  `test_invoke_with_real_sqlite_checkpointer`.

## 6. Manual Testing Checklist

Once dependencies are installed (`pip install -e ".[dev]"`,
`python -m playwright install chromium` if browser tools will be
exercised) and at least one LLM provider is configured:

1. `pytest -m unit` — all new unit tests pass.
2. `pytest -m integration` — `test_agent_orchestrator.py` passes
   against the real compiled graph (still with `ScriptedFakeLLM`, not
   a live LLM).
3. Launch the app (`python -m jarvis`), open Developer Mode ▸ **Agent
   Trace**, enter a prompt that doesn't need a tool (e.g. "What is 2 +
   2?") — expect a direct answer with no tool-trace rows beyond
   planner/tool_selector/responder.
4. Enter a prompt that should use the memory tool (e.g. "Remember that
   my favorite color is blue") — expect a `remember` tool-trace row
   and a confirmation in the final answer.
5. Enter a prompt that should use the automation tool (e.g. "open
   notepad") — expect a `run_automation` tool-trace row; confirm the
   dangerous-action auto-deny path by asking for something the safety
   validator would normally gate (e.g. deleting a system folder) and
   confirm it's denied, not silently run.
6. Restart the app and reopen Agent Trace — confirm no crash on
   `AgentOrchestrator` construction (checkpointer file at
   `<data_dir>/db/agent_checkpoints.db` should now exist if
   `JARVIS_AGENT_CHECKPOINT_ENABLED` wasn't set to `false`).
7. Quit the app via the tray/menu and via the OS window-close button —
   confirm no "Task was destroyed but it is pending!" warnings and that
   the checkpointer file isn't left in a corrupted state on next boot.

## 7. Example Usage (programmatic)

```python
from jarvis.core.interfaces.agent import AgentRequest

orchestrator = container.agent_orchestrator()
response = await orchestrator.invoke(
    AgentRequest(prompt="Search for today's top headline and remember it.")
)
print(response.text)
print(response.steps, response.metadata["tool_calls"])
```
