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

See [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md).

## Roadmap

Full, current milestone plan and status in
[`docs/MASTER_ROADMAP.md`](docs/MASTER_ROADMAP.md) (the single source
of truth) and [`docs/IMPLEMENTATION_ROADMAP.md`](docs/IMPLEMENTATION_ROADMAP.md)
(the active, checkbox-level execution plan). `docs/ROADMAP.md` is a
lighter-weight, non-authoritative summary covering only M0–M6 — check
the two documents above for anything current.

As of this writing: **M0–M6 shipped** (Foundation, Chat, Voice,
Memory, Automation, Desktop Platform, Vision & Multimodal
architecture layer); **M7 — Workflow Intelligence** active (Phases
1–2 shipped); **M8 — React Frontend & Desktop Experience** active
(migrating the UI from PySide6 to React + Tauri — the PySide6 UI
above remains the one that actually runs today); **M9 — Runtime &
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
knowledge, and commands, and a real `/api/v1/search` +
`/api/v1/knowledge` REST API, closing M10's own Context Engine
knowledge-graph deferral.

## License

Proprietary — personal use only. See [`LICENSE`](LICENSE).
