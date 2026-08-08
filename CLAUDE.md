# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

The virtualenv is `.venv/` and is **not** auto-activated. Prefix Python commands:
`./.venv/Scripts/python.exe` (Windows/Git Bash).

### Backend (Python 3.13 / FastAPI / PySide6)
```bash
./.venv/Scripts/python.exe -m pytest tests/unit tests/integration --no-cov -q   # full suite
./.venv/Scripts/python.exe -m pytest tests/unit/test_mqtt_connector.py --no-cov  # one file
./.venv/Scripts/python.exe -m pytest tests/unit/test_x.py::test_name --no-cov    # one test
./.venv/Scripts/python.exe -m black src/ tests/
./.venv/Scripts/python.exe -m ruff check src/ tests/
./.venv/Scripts/python.exe -m mypy --config-file=pyproject.toml src/   # src/ ONLY, matches CI
python main.py                                                          # run the desktop app
```

- **Always pass `--no-cov`** when you want readable output: `pyproject.toml`'s `addopts` forces
  a full coverage report on every run, which buries the result under hundreds of lines.
- The full suite takes ~14 min and its trailing summary line is frequently **clipped by output
  buffering**. For a trustworthy pass/fail count use `--junit-xml=<path>` and read the
  `<testsuite>` header attributes; do not infer the result from a truncated tail.
- No editable install is needed — `pythonpath = ["src"]` in `pyproject.toml` lets tests import
  `jarvis` from source.

### Frontend (React 19 + Vite + TypeScript, Tauri shell)
```bash
npm --prefix frontend run test        # vitest
npm --prefix frontend run typecheck   # tsc -b --noEmit
npm --prefix frontend run lint        # oxlint
npm --prefix frontend run build       # tsc -b && vite build
```

### CI gates
`pytest` is the **only hard gate**. `ruff`, `black`, `mypy`, and `pip-audit` all run
`continue-on-error: true` because the repo carries documented pre-existing debt — a green
`ruff`/`mypy` run is not achievable repo-wide, so judge your change by *new* findings in
*touched files*, not by a clean global run.

## Architecture

Ports-and-adapters over a DI composition root. The layering is enforced by convention and is
load-bearing:

- `src/jarvis/core/interfaces/` — **ports** (Protocols). Adapters satisfy them *structurally*;
  no inheritance anywhere.
- `src/jarvis/infrastructure/` — **adapters** (LLM providers, SQLAlchemy repos, FastAPI routes).
  Vendor SDKs and wire protocols live here and nowhere else.
- `src/jarvis/services/` — orchestration over repos + event bus. Services never talk to each
  other's tables.
- `src/jarvis/core/di/container.py` — the **single composition root**. Every provider is
  registered here; `_build_*` functions use lazy imports deliberately (the repo-wide `PLC0415`
  ruff findings are this accepted pattern, not a defect).
- `src/jarvis/agents/` — LangGraph agent runtime (see below).

### Two conversational paths exist — know which one you're in
- `ChatService.stream()` — plain LLM passthrough. No tools, no planning, no intent
  classification.
- `AgentOrchestrator` (`agents/orchestrator.py`) — the compiled LangGraph `StateGraph`
  (`intent_classifier → {context_engine | responder} → planner → tool_selector →
  [permission_validator → tool_executor → critic]* → responder`). A high-confidence
  `direct_answer` intent classification now gates straight to `responder`, skipping
  `context_engine`/`planner`/`tool_selector` (M10 Conversational Orchestration Routing).

Which one Desktop Chat and Voice actually reach is decided in exactly one place —
`ConversationController.__init__` — by `AgentSettings.conversation_routing`
(`legacy`/`hybrid`/`orchestrator`, default `legacy`, preserving pre-M10-routing behaviour
byte-for-byte). Reaching `AgentOrchestrator` via REST directly (`POST /api/v1/agent/invoke`
and `/api/v1/agent/stream`) still works regardless of the flag. Do not assume a change to
one path affects the other without checking which mode is configured.

### Adding a relayed WebSocket event touches five surfaces
Adding an `Event` and forgetting the rest fails the suite in two places and silently breaks
the client. All of these must change in the same commit:
1. `core/events/events.py` — the dataclass
2. `core/lifecycle/runtime_ws_hub.py` — `EVENT_TYPE_NAMES`
3. `frontend/src/services/websocket/event-contract.generated.json` — regenerate via
   `scripts/export_ws_contract.py`
4. `frontend/src/services/websocket/types.ts` — `RELAYED_EVENTS`
5. The pinned vocabulary tests: `tests/unit/test_runtime_ws_hub.py`,
   `tests/unit/test_ws_contract_export.py`, `tests/unit/test_platform_integration.py`, and
   `frontend/src/services/websocket/__tests__/websocket-contract.test.ts`

## Testing conventions

- **Fakes, not mocks.** `tests/fakes/` holds scripted in-memory doubles (`FakeDeviceConnector`,
  `FakeOSAutomation`, `FakeMqttBroker`). Adapters are tested against a **real** local peer —
  a real `http.server`, a real `websockets` server, a real in-process MQTT broker — never a
  patched client library.
- Persistence tests use **real temp-file SQLite**, never a mocked repository.
- Network-timing tests must poll for an observable condition, never `sleep(fixed)`.

## Project conventions that will trip you up

- **Roadmap authority:** `docs/MASTER_ROADMAP.md` is the single source of truth. `docs/
  IMPLEMENTATION_ROADMAP.md` is a hand-synced mirror of the active subset; `docs/ROADMAP.md`
  is a short pointer that has drifted before. If they disagree, `MASTER_ROADMAP.md` §2 wins.
  **Never infer milestone status — read it.**
- **Logic Contract rule:** no implementation may begin until its module's Logic Contract is
  written (15 fields, per `MASTER_ROADMAP.md` §4). See
  `docs/CONNECTIVITY_LAYER_LOGIC_CONTRACT.md` for the only existing example.
- **`ARCHITECTURE.md` §22 is a freeze, not a suggestion.** Provider routing, cost control,
  voice-provider selection and hardware profiling are reserved for the (unscheduled) Universal
  AI/API Calibration Engine. A feature needing any of them must *raise a blocker*, not solve it
  locally. Do not build a competing provider manager.
- **M0–M6 are feature-frozen.** Extend around them at the composition layer; do not edit
  `chat_service.py` / `conversation_service.py` / `voice_service.py` to add behavior.
- **Version** lives only in `src/jarvis/__version__.py` + `pyproject.toml`. Recent M12 task
  groups shipped real code with **no version bump** by explicit instruction — check
  `CHANGELOG.md` before assuming a bump is expected.
- **Commit convention:** `feat(m12-b3): …` / `docs(m12-b3): …` — implementation and
  documentation ship as two separate commits, docs only after tests are green.

## Windows-specific constraint (hard-won)

The app requires asyncio's **`ProactorEventLoop`** (Windows default) because MCP's
`StdioTransport` spawns subprocesses. Any library needing `loop.add_reader`/`add_writer` —
which on Windows only `SelectorEventLoop` implements — is therefore **unusable here**. This is
why the MQTT connector uses `gmqtt` (asyncio.Protocol-based) rather than `aiomqtt`/`paho-mqtt`.
Verify event-loop compatibility against a real local server before adopting any new async
network library.
