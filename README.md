# JARVIS OS

> Local-first, production-grade personal AI operating system for Windows 11.

JARVIS OS is a desktop AI assistant that lives on your machine. It orchestrates
LLMs (both local via **Ollama** and cloud via **OpenAI**), remembers what you
tell it (**SQLite** + **ChromaDB**), talks (**OpenAI TTS**) and listens
(**Whisper**), automates your desktop (**pywinauto**) and your browser
(**Playwright**), and exposes a control-plane HTTP API (**FastAPI**) — all
behind a modern **PySide6** UI driven by **LangGraph** agents.

This repository contains the complete production-ready architecture and
scaffolding, plus the Milestone 5 official UI: a full PySide6 desktop shell
(Home dashboard, Chat, 9 feature workspaces, Developer Mode, Update Center,
API Center) built on that foundation. Several integrations (Gmail, Spotify,
Weather, Finance, Smart Home, third-party plugins) are intentionally UI-complete
but data-mocked pending real credentials/backends — see
[`MILESTONE_5_DELIVERY.md`](MILESTONE_5_DELIVERY.md) for the exact real-vs-mock
breakdown and [`docs/FUTURE_INTEGRATION_GUIDE.md`](docs/FUTURE_INTEGRATION_GUIDE.md)
for how to swap a mock provider for a real one.

---

## Vision

JARVIS OS is not a desktop application with an AI feature bolted on —
it is an **AI Operating System**. The UI (PySide6 today, React + Tauri
from M8 onward) is one replaceable layer; the Python runtime
underneath — AI orchestration, Memory, Knowledge, Automation, Voice,
Vision, Plugins, Integrations — is the actual product, and does not
change shape because the UI's rendering technology changed. The
long-term direction is a single, local-first assistant that grows a
real memory (M3), a real knowledge graph and universal search over
everything it knows (M10A), a real goal/routine/preference-learning
intelligence layer (M10B), and eventually genuine proactive and
reflective capability (M15 Personality Engine, M16 Reflection Engine,
M17 Companion Intelligence) — reachable from the desktop, the browser,
mobile, and wearables (M21) alike, all talking to the same backend
through the same REST/WebSocket contract. See
[Future vision](#future-vision) below and
[`docs/MASTER_ROADMAP.md`](docs/MASTER_ROADMAP.md) §8 for the full,
milestone-by-milestone plan.

**Engineering philosophy** — the rules every milestone follows,
not just the ones convenient for it (full detail:
[`docs/MASTER_ROADMAP.md`](docs/MASTER_ROADMAP.md) §4,
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) §1):

- **Local-first, offline-first.** JARVIS runs with zero cloud
  dependency by default — local LLMs via Ollama, local storage via
  SQLite, local vector memory via ChromaDB. Cloud (Oracle Cloud today;
  MongoDB sync, planned) is additive, opt-in, and never required.
- **Modular, plugin-first.** Every capability is a self-contained
  module behind a manifest (`docs/ARCHITECTURE.md` §10); third-party
  plugins use the exact same extension points first-party modules do.
- **Event-driven.** Cross-cutting state changes flow through the
  `EventBus`, relayed to clients over one multiplexed WebSocket — not
  direct callbacks across layer boundaries.
- **Dependency injection everywhere.** No service ever imports a
  concrete adapter directly, only its port (`core/di/container.py`).
- **SOLID, composition over inheritance.** One responsibility per
  class/module; behavior is composed from small services, not built up
  through deep inheritance hierarchies.
- **Single source of truth.** `docs/MASTER_ROADMAP.md` for scope and
  status, `docs/ARCHITECTURE.md` for standards, `docs/TECH_STACK.md`
  for technology choices — one authoritative document per question,
  cross-referenced, never duplicated and left to drift.
- **Security by design.** Every tool invocation passes through
  Permission Validation before executing; least-privilege by
  construction, not bolted on after the fact (`docs/ARCHITECTURE.md`
  §17).
- **Backward compatibility, incremental evolution.** A milestone
  extends the public surface; it does not silently break an existing
  one. Reuse existing systems instead of building parallel
  implementations — the single rule most consistently enforced across
  every milestone in this repository's history.
- **Shared runtime, not per-feature reinvention.** One `RuntimeManager`,
  one `EventBus`, one DI container, one plugin system — every new
  capability plugs into them rather than shipping its own copy.

## Highlights

- **Clean, layered SOLID architecture** — `core` / `services` /
  `infrastructure` / `features` / `ui`, with strict dependency direction.
- **Modular monolith** — each capability (conversation, voice, memory,
  automation, settings) is a self-contained feature module.
- **Ports & adapters at the edges** — every external system (LLM, STT, TTS,
  DB, vector store, browser, OS automation) is defined as an abstract
  interface in `core/interfaces` and implemented once per provider in
  `infrastructure`.
- **First-class dependency injection** via `dependency-injector`.
- **Config as code** — `pydantic-settings` unifies `.env`, environment
  variables and OS keyring; providers can be enabled/disabled without code
  changes.
- **Structured logging** — `loguru` + `structlog`, JSON in production, pretty
  console in dev, rotating file sink.
- **Theming** — QSS themes (`dark`, `light`, `jarvis`) selected at runtime by
  a `ThemeManager` service.
- **Async everywhere** — Qt event loop bridged to `asyncio` with `qasync`.
- **Cross-platform where sensible** — Windows-only functionality
  (`pywinauto`) is isolated behind interfaces and pluggable adapters.
- **Type-checked** — full `mypy --strict`, `ruff`, `black`, pre-commit hooks.

## Tech stack

| Concern           | Choice                                          |
|-------------------|-------------------------------------------------|
| Language          | **Python 3.13**                                 |
| Desktop UI        | **PySide6 6.7+** (+ `qasync`)                   |
| API surface       | **FastAPI** + Uvicorn                           |
| Structured store  | **SQLite** via SQLAlchemy 2.x + `aiosqlite`     |
| Vector store      | **ChromaDB**                                    |
| Agent runtime     | **LangGraph** + LangChain                       |
| Local LLM         | **Ollama**                                      |
| Cloud LLM         | **OpenAI**                                      |
| STT               | **Whisper** (local) / OpenAI Whisper API        |
| TTS               | **OpenAI TTS**                                  |
| Browser control   | **Playwright**                                  |
| Windows control   | **pywinauto**                                   |
| Config            | `pydantic-settings`                             |
| Logging           | `loguru` + `structlog`                          |
| DI                | `dependency-injector`                           |
| Packaging         | `pyproject.toml`, `pip`, PyInstaller            |

## Architecture at a glance

```
UI (PySide6)  →  Features  →  Services  →  Agents (LangGraph)  →  core.interfaces
                                                                        ▲
                                              Infrastructure ───────────┘
                                     (OpenAI, Ollama, Whisper, Chroma, SQLite,
                                      Playwright, pywinauto, FastAPI)
```

**Dependency rule**: `ui → features → services → agents → core.interfaces`;
`infrastructure → core.interfaces` (never the other way).

Deep-dive on the as-shipped architecture above:
[`docs/ARCHITECTURE_LEGACY.md`](docs/ARCHITECTURE_LEGACY.md). For the
Aug 2026 forward-looking architecture standard (React + Tauri +
FastAPI, M8 onward), see [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

### Domain architecture

Where each capability actually lives, and whether it's real yet — the
full table (every domain, status, owning milestone, source location)
is [`docs/ARCHITECTURE.md` §21 — Domain architecture map](docs/ARCHITECTURE.md#21-domain-architecture-map).
The short version:

| Domain | Status | Detail |
|---|---|---|
| Runtime & Dependency Injection | ✅ Real | `core/lifecycle/`, `core/di/container.py` |
| Plugin Architecture | ✅ Real | `core/plugins/` — SDK, Loader, Sandbox, Permission Model, Marketplace Foundation |
| Memory Architecture | ✅ Real | `services/memory_service.py` — Working/Conversation/Episodic/Semantic/Preference/Knowledge/Vector Memory |
| Knowledge Graph & Universal Search | ✅ Real | `services/knowledge_service.py`, `services/search_service.py` |
| AI Orchestrator | 🟡 Partial | `agents/graph.py` — Intent, Planning, parallel tool dispatch, interim Permission Validation |
| Intelligence Layer | ✅ Real | `services/intelligence_service.py` — Goal Manager, Routine/Preference Learning, Daily Briefing |
| Workspace, Productivity & Files | 🟡 Partial | `services/workspace_service.py`, `task_service.py`, `calendar_service.py`, `reminder_service.py`, `file_service.py` — M11 Task Groups A–C. Local only: no cloud storage, no calendar sync, no scheduler execution |
| AI Workspace | 🟡 Partial | `services/workspace_ai_service.py`, `workspace_ai_managers.py` — M11 Task Group D: workspace↔knowledge links, budgeted workspace context, workspace-scoped retrieval over the shared search index, grounded summarize/ask/next-actions, five agent tools. On-demand only: nothing schedules ingestion, and no embeddings over workspace content |
| MCP Architecture | ✅ Real | `core/mcp/` — M10.5 complete: registry, client/server runtimes, negotiation, heartbeat, diagnostics; `transports/` (stdio, websocket, http, ipc); `providers/` (registry, lifecycle, health); `auth/` (credentials, encrypted store, strategies, permission bridge); `sdk/` (builders, validators, examples); plus `jarvis mcp` and `/api/v1/mcp/*`. M11 Task Group E added the OAuth2 grants and the first real providers |
| Integration Platform | 🟡 Partial | `core/integrations/` — M11 Task Group E: OAuth2 authorization-code + PKCE, client-credentials, one audited API gateway (retry, cache, rate limits), and connectors as declarative specs running as MCP providers. Google Workspace (11 integrations, 65 operations) ships; Microsoft 365, GitHub/GitLab, Slack/Discord, Notion/Jira/Trello/ClickUp/Linear/Asana and Dropbox/Box are catalogue work, not built |
| Self-Healing Architecture | 🔴 Planned | M13B (foundation) → M18 (full platform) |

## Project layout

```
jarvis-os/
├── src/jarvis/                    # main package (src-layout)
│   ├── app.py                     # ApplicationBootstrapper
│   ├── main.py                    # PySide6 entry point
│   ├── core/                      # config, logging, DI, interfaces, runtime lifecycle (M9)
│   ├── infrastructure/            # concrete adapters (OpenAI, Ollama, ...) + FastAPI routes
│   ├── services/                  # application services
│   ├── agents/                    # LangGraph orchestrator
│   ├── features/                  # feature modules (modular monolith)
│   ├── ui/                        # PySide6 UI + ThemeManager (current shipping UI)
│   └── utils/
├── frontend/                      # React 19 + Vite + Tauri UI (M8, in progress --
│   │                               # see docs/TECH_STACK.md; not yet the primary UI)
│   └── src/
├── docs/                          # architecture & developer docs
├── scripts/                       # bootstrap, dev-run, build
├── resources/                     # QSS themes, icons, fonts, assets
├── data/                          # runtime data (db, vectors, logs, cache)
├── tests/                         # unit / integration / e2e
├── pyproject.toml
├── requirements.txt
├── requirements-dev.txt
├── .env.example
└── README.md
```

## Getting started

### Prerequisites

- Windows 11 (production target); Linux/macOS work for development except
  Windows-specific automation.
- **Python 3.13**
- [Ollama](https://ollama.com) running locally (optional).

### Install

```bash
git clone <repo> jarvis-os
cd jarvis-os

python -m venv .venv
# Windows
.\.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install --upgrade pip
pip install -e ".[dev]"
python -m playwright install chromium

cp .env.example .env      # then edit
python -m jarvis          # launches the PySide6 app
```

The internal FastAPI control-plane server listens on
`http://127.0.0.1:8765` (see `JARVIS_API_PORT`).

## Configuration

See [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md).

## Development workflow

```bash
ruff check src tests
black --check src tests
mypy src

pytest -m unit
pytest -m integration
pytest -m "not windows"      # skip Windows-only tests
pre-commit install
```

Full setup, day-to-day commands, and Alembic migration workflow:
[`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md).

### Coding standards

Clean Architecture layering (`ui → features → services → agents →
core.interfaces`, `infrastructure → core.interfaces`, never the other
way), dependency injection for every new adapter, `EventBus` for
cross-cutting notifications, `mypy --strict` typing, no fake or
simulated data in a production code path — a loading state, an empty
state, or a real value, never a placeholder dressed up to look real.
Full standard: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md),
[`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) §5.

### Testing strategy

Every new port ships with a fake in `tests/fakes/` in the same pass it
ships in; a milestone that reduces the passing test count, or removes
a test without replacing its coverage, does not ship. Unit tests
(`pytest -m unit`) exercise services/repositories against a real
temp-file SQLite database and fakes for external providers (LLM,
vector store); integration tests (`pytest -m integration`) exercise
one full flow per Acceptance Criterion end-to-end — real DI container,
real `TestClient`, real WebSocket relay where applicable — never
doubles of the unit tests. See
[`docs/MASTER_ROADMAP.md`](docs/MASTER_ROADMAP.md) §5 (Validation
gate) and §4 (Engineering standards).

### Git workflow

Feature branches: `feat/<milestone>-<short-name>`. Every milestone's
commit follows the pattern `feat(<milestone>): <summary>` /
`docs(<milestone>): <summary>`, validated (Black clean, Ruff/mypy
baseline unchanged, full suite passing) before it merges to `main`.
See [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) §8.

## Roadmap

**Current version:** `0.31.0` · **Current milestone:** M8 — React
Frontend & Desktop Experience (🟡 active; Phase 1 React Foundation,
Phase 2 Universal Application Framework & Logic, Phase 3's Universal
Workspace Framework, Phase 4 Voice Experience & Motion, Phase 5 AI
Workspace & Module Integration, and Phase 6's production-UX half
shipped).

M11 — Intelligent Workspace & Productivity completed across six task
groups (A Workspace Foundation, B Productivity Core, C File Platform,
D AI Workspace, E Integration Platform, F Platform Integration) at
`0.28.0`; M10.5 completed across five. `0.21.0` and `0.22.0` were
backlog completion passes over already-completed milestones, and
`0.24.1` was a database integrity pass that turned on SQLite
foreign-key enforcement.

`0.29.0` connected the React client to the FastAPI backend — and found
that the client's REST and WebSocket layers, written in Phase 1 against
`ARCHITECTURE.md`'s *illustrative* examples before the routes existed,
had drifted from the running server in three places. `0.30.0` built the
workspace framework the UI arranges itself in. `0.31.0` filled it: three
audience-specific dashboards (AI, Developer, Administrator) on real
backend data, and the §22.12 gate that keeps provider names, routing and
internal agent names out of a personal user's JARVIS.

Full, current milestone plan and status in
[`docs/MASTER_ROADMAP.md`](docs/MASTER_ROADMAP.md) (the single source
of truth) and [`docs/IMPLEMENTATION_ROADMAP.md`](docs/IMPLEMENTATION_ROADMAP.md)
(the active, checkbox-level execution plan). `docs/ROADMAP.md` is a
lighter-weight, non-authoritative summary covering only M0–M6 — check
the two documents above for anything current.

### Development policy (Aug 2026)

| Area | Status |
|---|---|
| Backend architecture · API contracts · Database schema · Core backend modules · Milestone structure | 🔒 **Frozen** |
| Frontend / UI / UX | 🟢 **Continues** |

No additional backend architecture is introduced unless explicitly
approved after UI validation.

**Approved target architecture** — Local AI First (every installation
ships a local LLM; cloud enhances, never replaces), the Universal
AI/API Calibration Engine (no external API is called directly), the AI
Cost Optimizer, the three-tier AI strategy, hardware calibration at
install time, Personal/Administrator accounts, and the rule that users
never see provider names or routing — is specified in full in
[`docs/ARCHITECTURE.md` §22](docs/ARCHITECTURE.md#22-approved-architecture-decisions-aug-2026).

**It is approved, not built.** None of it exists in code yet; §22 is a
contract for the milestones that will build it, and exists so nobody
implements a competing design in the meantime.

As of this writing: **M0–M6 shipped** (Foundation, Chat, Voice,
Memory, Automation, Desktop Platform, Vision & Multimodal
architecture layer); **M7 — Workflow Intelligence** active (Phases
1–2 shipped); **M8 — React Frontend & Desktop Experience** active
(migrating the UI from PySide6 to React + Tauri — the PySide6 UI
above remains the one that actually runs today. Phases 1, 2 and 4
shipped, and Phase 3's Universal Workspace Framework: dockable and
resizable panels, multiple named workspace layouts with
import/export, a Notification Center, an Activity Center, and Global
Search over the real `/api/v1/search`); **M9 — Runtime &
Core Services shipped in full** — Runtime/Service/Session/Configuration
Managers, Health Monitor, Background Task Manager, Crash Recovery,
Resource Manager, a real `/api/v1/ws` WebSocket API, a full plugin
platform (SDK, Loader, Sandbox, Extension API, Permission Model,
Registration System, Store, Marketplace), and the Developer Platform
Tools that expose it all — Debug Console, Live Logs, Performance
Profiler, State Inspector, API Inspector, and a real `/api/v1/plugins`
+ `/api/v1/devtools` REST API (the first routes to follow
`docs/ARCHITECTURE.md` §5's full contract — Bearer auth + the
`{data, meta}` envelope); **M10 — AI Orchestrator active (partial)** —
extends M5A's `AgentOrchestrator` with an Intent Engine, a Context
Engine, parallel tool dispatch, interim Permission Validation, real
token-level streaming for the tool-composed path, and a real
`/api/v1/agent` REST API. M10 formally depends on M14, not shipped
yet, so the dependent remainder is explicitly deferred — **not 100%
complete.** **M10A — Universal Search & Knowledge Platform shipped in
full** (except File Search, deferred pending M11B) — a real Knowledge
Graph, `SearchService`'s pluggable provider registry spanning memory,
knowledge, goals, and commands, and a real `/api/v1/search` +
`/api/v1/knowledge` REST API, closing M10's own Context Engine
knowledge-graph deferral. **M10B — Intelligence Layer shipped in
full** — a Goal Manager with hierarchical progress tracking, deterministic
Routine and Preference Learning, keyword-boosted Predictive Suggestions,
an on-demand Daily Briefing, and a real `/api/v1/goals` +
`/api/v1/intelligence` REST API, registered into Universal Search as a
fourth `goals` provider; automatic scheduled delivery of the briefing
remains deferred pending M7's Scheduler (Phase 6), which does not exist
yet.

### Future vision

Beyond M10.5, the roadmap continues (all planned, none started;
milestone identities never renumbered once assigned — see
`docs/MASTER_ROADMAP.md` §1's charter). **M10.5 MCP & Integration
Platform** *(added Aug 2026)* — the Model Context Protocol
registry/adapter layer — is **complete** as of `0.20.0`, scheduled
before M11 exactly so M11's providers build on it rather than retrofit
onto it. Next: **M11 Integrations & Cloud Platform** (OAuth-backed integrations, API Gateway, optional Oracle
Cloud/MongoDB sync) and its companions M11A (SEO Intelligence) and
M11B (Productivity Suite — Tasks, Documents, File Manager, Command
Palette); **M12 Smart Home & IoT**; **M13 Desktop Intelligence &
Computer Control**, **M13A AI Sandbox**, and **M13B Self-Healing &
Observability** *(added Aug 2026 — the foundational subset of
M18/M20A, which remain their full-scale realizations)*; **M14 Security
Platform**
(the Authorization Engine several earlier milestones already defer
to) and **M14A Backup Platform**; **M15 Personality Engine**, **M16
Reflection Engine**, and **M17 Companion Intelligence** (+ **M17A
Training Studio**) — the personality, learning-from-feedback, and
synthesis layer built on M10A/M10B's foundation; **M18 Self-Healing &
Diagnostics Platform**; **M19 Knowledge Graph & Digital Twin
Platform** (M10A's full realization); **M20 Predictive Intelligence
Platform** (+ **M20A Analytics & Observability**); **M21 Mobile
Platform** (Mobile Companion, wearables/AR glasses); **M22 Edge AI
Platform**; **M23 Distributed JARVIS** (+ **M23A Robotics & Hardware
Control**, **M23B Autonomous Planning & Decision Engine**); and
**M24 Production Release (v1.0)**, followed by M25–M27's Cognitive
Intelligence, Self-Learning, and World Model platforms. Full detail,
dependencies, and acceptance criteria for every one of these:
`docs/MASTER_ROADMAP.md` §8.

## License

Proprietary — personal use only. See [`LICENSE`](LICENSE).
