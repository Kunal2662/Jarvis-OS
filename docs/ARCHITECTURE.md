# Architecture

> Layered + modular monolith · SOLID · Ports & Adapters at the edges.

## 1. Guiding principles

| # | Principle                    | Consequence in code                                        |
|---|------------------------------|------------------------------------------------------------|
| 1 | **Single Responsibility**    | One class = one reason to change. Services never touch two adapters that could each be responsible for the change. |
| 2 | **Open/Closed**              | Providers are opened for extension (add a new `ILLMProvider`) but closed for modification (existing services untouched). |
| 3 | **Liskov Substitution**      | Every implementation of an interface is drop-in swappable — no `isinstance` checks in higher layers. |
| 4 | **Interface Segregation**    | Small, focused ports (`ISTTProvider` ≠ `ITTSProvider`). No fat "AI provider" interface. |
| 5 | **Dependency Inversion**     | Higher layers depend on abstractions in `core.interfaces`; concrete adapters are injected by the DI container. |

## 2. Layers

```
┌──────────────────────────────────────────────┐
│                  UI (PySide6)                │  presentation
├──────────────────────────────────────────────┤
│         Features (modular monolith)          │  vertical slices
├──────────────────────────────────────────────┤
│              Application services            │  orchestration
├──────────────────────────────────────────────┤
│           Agents (LangGraph runtime)         │  reasoning
├──────────────────────────────────────────────┤
│         Core   (config, DI, logging,         │  abstractions
│                 interfaces, events, types)   │
├──────────────────────────────────────────────┤
│  Infrastructure adapters (OpenAI, Ollama,    │  external I/O
│  Whisper, Chroma, SQLite, Playwright,        │
│  pywinauto, FastAPI, ...)                    │
└──────────────────────────────────────────────┘
```

**Dependency rule** (enforced by convention & code review):

```
ui → features → services → agents → core.interfaces
infrastructure ──────────────────→ core.interfaces
```

`infrastructure` and `ui`/`features`/`services`/`agents` **must not** import
each other. They meet only inside the DI container.

## 3. Package responsibilities

| Package                | What lives here                                                                                     | Allowed imports                     |
|------------------------|-----------------------------------------------------------------------------------------------------|-------------------------------------|
| `jarvis.core.config`   | `Settings` (pydantic), constants, path resolution.                                                  | stdlib, pydantic                    |
| `jarvis.core.logging`  | Loguru + structlog bootstrap, stdlib interception, JSON/console sinks.                              | stdlib, loguru, structlog           |
| `jarvis.core.di`       | `Container` — the single composition root.                                                          | dependency-injector, `core.*`       |
| `jarvis.core.events`   | In-process async event bus + event base class.                                                      | stdlib, `core.logging`              |
| `jarvis.core.lifecycle`| `ShutdownManager` — priority-ordered, fault-isolated shutdown hook registry (Milestone 5.5).        | stdlib, `core.logging`              |
| `jarvis.core.interfaces`| Abstract ports (`ILLMProvider`, `ISTTProvider`, `ITTSProvider`, `IVectorStore`, `IDatabase`, `IBrowserAutomation`, `IOSAutomation`, `IAgentOrchestrator`). | stdlib, `core.types` |
| `jarvis.infrastructure`| One concrete adapter per port per provider. **Only place** where third-party SDKs are imported.[^1] | third-party SDKs, `core.interfaces` |
| `jarvis.services`      | Application services that orchestrate one or more adapters.                                         | `core.interfaces`, `core.*`         |
| `jarvis.agents`        | LangGraph orchestrator, state, nodes, tools.                                                        | `core.interfaces`, `services`, `langgraph`/`langchain_core` |

[^1]: One narrow, deliberate exception (Milestone 5-Agents):
`agents/tools/*.py` and `agents/prompting.py` import `langchain_core.tools`
directly to build the tool registry — the "agents" layer importing its
own declared dependency for the job it exists to do, not `services` or
`core` reaching for a third-party SDK. `ILLMProvider` remains the one
and only chat-LLM port; no `infrastructure/` boundary is crossed.
| `jarvis.features`      | Feature-based slices (`conversation`, `voice`, `memory`, `automation`, `settings`).                 | `services`, `core.events`           |
| `jarvis.ui`            | PySide6 widgets, views, dialogs, `ThemeManager`.                                                    | PySide6, `services`, `features`     |
| `jarvis.utils`         | Small helpers (async, crypto, files).                                                               | stdlib, `core.exceptions`           |

## 4. Runtime lifecycle

```
python -m jarvis
│
├─ main.py                       — parse CLI flags
├─ app.ApplicationBootstrapper.run()
│    ├─ _configure()             — load Settings, configure logging,
│    │                             build Container, wire packages
│    ├─ _install_signal_handlers — graceful shutdown on SIGINT/SIGTERM
│    └─ _run_gui / _run_headless / _run_api_only
│         └─ Container provides everything
└─ shutdown()                    — ShutdownManager runs every registered
                                    cleanup hook in priority order,
                                    fault-isolated (Milestone 5.5; see
                                    core/lifecycle/shutdown_manager.py).
                                    Any resource (UI or not) registers
                                    once via container.shutdown_manager()
                                    -- adding a future subsystem's
                                    cleanup never means editing
                                    MainWindow again.
```

## 5. Ports & adapters map

| Port (`core.interfaces`)   | Adapter (`infrastructure`)                                     |
|----------------------------|----------------------------------------------------------------|
| `ILLMProvider`             | `llm.openai_provider.OpenAILLMProvider`, `llm.ollama_provider.OllamaLLMProvider` |
| `ISTTProvider`             | `stt.whisper_local_provider.WhisperLocalSTTProvider`, `stt.openai_whisper_provider.OpenAIWhisperSTTProvider` (both via `stt.provider_factory`) |
| `ITTSProvider`             | `tts.openai_tts_provider.OpenAITTSProvider`                    |
| `IVectorStore`             | `vectorstore.chroma_client.ChromaVectorStore`                  |
| `IMemoryRecallHook`        | `services.semantic_memory_recall_hook.SemanticMemoryRecallHook` (active), `core.interfaces.memory.NoopMemoryRecall` (fallback) |
| `IDatabase`                | `database.sqlite_client.SQLiteDatabase`                        |
| `IBrowserAutomation`       | `browser.playwright_adapter.PlaywrightBrowser`                 |
| `IOSAutomation`            | `automation.windows_adapter.WindowsAutomationAdapter` (Win), `automation.noop_adapter.NoopAutomationAdapter` (other) |
| `IAgentOrchestrator`       | `jarvis.agents.orchestrator.AgentOrchestrator`                 |

Adding a new provider (e.g. Anthropic):

1. Create `infrastructure/llm/anthropic_provider.py` implementing `ILLMProvider`.
2. Add `AnthropicSettings` to `core/config/settings.py` (with `enabled` flag).
3. Register the factory in `core/di/container.py::_build_llm_provider`.
4. Nothing else changes.

### 5a. Memory subsystem (Milestone 3)

Two stores, one service, one hook:

* **SQLite** (`Memory` ORM row) is the source of truth — content,
  `memory_type`, lifecycle flags (`pinned`/`archived`/`expires_at`),
  and metadata. Written first on every `remember()`.
* **ChromaDB** (`ChromaVectorStore`) holds the embedding for semantic
  lookup, keyed by the same id as the SQLite row.
* `MemoryService` is the only thing that talks to both stores. It
  never lets them drift permanently out of sync: writes go SQL → vector,
  deletes go SQL → vector, and any vector failure is logged and
  swallowed (a memory that failed to index is still recallable via
  keyword search) rather than rolling back the SQL write.
* `recall()` / `search(mode="hybrid")` fuse semantic + keyword hits
  with Reciprocal Rank Fusion rather than picking one signal.
* `SemanticMemoryRecallHook` (implements `IMemoryRecallHook`) is what
  `ChatService` calls before every LLM turn — it is a thin adapter over
  `MemoryService.recall()`, keeping the chat pipeline unaware that
  memory exists at all beyond the port.
* Policy enforcement (`enforce_policies()`) is pull-based, not a
  background scheduler: it runs once at GUI startup and whenever the
  Settings ▸ Memory page's actions call it indirectly. Expired/pruned
  rows are **archived**, not deleted — `delete_archived()` is the
  explicit, separate step that reclaims space.

## 6. Concurrency model

* Qt event loop is bridged to `asyncio` via **qasync**.
* All services and adapters expose **async** APIs.
* Long-running/CPU-bound work (Whisper transcription) must run in a
  dedicated thread pool — never on the UI thread.
* The event bus dispatches handlers on the currently-running loop.

## 7. Error handling

* Every module raises subclasses of `JarvisError` (`core.exceptions`).
* Adapters translate third-party exceptions into their own subclass
  (`LLMProviderError`, `OSAutomationError`, …).
* Services never leak infrastructure exceptions to the UI — they either
  handle them or wrap them in `ServiceError`.
* The UI shows a single, user-friendly error dialog for any `JarvisError`.

## 8. Testing strategy

| Level         | Scope                                          | Runs on CI? |
|---------------|------------------------------------------------|-------------|
| `unit`        | Pure functions, services with fake adapters.   | ✅          |
| `integration` | Real Chroma, real SQLite, mocked network.      | ✅          |
| `e2e`         | Full app boot, headless UI, dummy LLM.         | Nightly     |
| `windows`     | pywinauto-based; only on Windows runners.      | Windows CI  |

Fixtures live in `tests/conftest.py`. Adapters expose fakes under
`tests/fakes/` (added in Milestone 1).

## 9. Anti-patterns rejected on sight

* Reaching into `infrastructure` from `services`/`ui`/`features`.
* Instantiating adapters outside the DI container.
* Global mutable state (module-level dicts/lists holding runtime data).
* Wrapping every call in `try/except Exception:` — trust the base class.

## 10. Milestone 5 completion pass -- new layers

Extends the Milestone 5 UI framework (workspaces, service cards, icon
system, Update Terminal docking, live transcript, module/plugin
managers, theme engine) without touching the layering rules above.
Every addition slots into an existing layer:

* **`ui/views/workspaces/`** -- the 9 full desktop workspaces (Voice,
  Files & Drive, Browser, Coding, Finance, Smart Home, Calendar, Gmail,
  Spotify) that replaced `ComingSoonView` placeholders. Built entirely
  from `ui/components/workspace.py` (`WorkspaceHeader`, `EmptyState` /
  `LoadingState` / `ErrorState`, `ActivityFeed`, `QuickActionsRow`,
  `CardGrid`), `ui/components/table.py` / `virtual_list.py`, and
  `ui/components/charts.py` -- no workspace hand-rolls its own layout
  primitives. Pages are constructed lazily on first nav visit (see
  `MainWindow._on_nav_selected`), not eagerly at startup.
* **`core/interfaces/providers.py`** -- eight new ports
  (`IGmailProvider`, `ISpotifyProvider`, `IWeatherProvider`,
  `IFinanceProvider`, `ISmartHomeProvider`, `IPluginProvider`,
  `ITranscriptProvider`, `IUpdateProvider`), same `Protocol`-based shape
  as every existing port in this file. `features/integrations/mocks.py`
  and `features/plugins/mock_provider.py` are the only concrete
  implementations today; a real adapter for any of them is a
  `core/di/container.py` wiring change, not a UI change.
* **`ui/components/service_widget.py`** -- `ServiceWidget`, the
  production-quality Gmail/Spotify/Weather/Finance/Smart-Home card
  (status, summary, activity, quick actions, last sync, connection
  indicator, loading/error states) that replaced the old static
  `ServiceCard` usage on the Home dashboard.
* **`ui/async_utils.py`** -- `fire_and_forget()`, the safe
  "kick off a coroutine from a widget constructor" helper every new
  auto-refreshing widget (`ServiceWidget`, the workspaces) uses instead
  of calling `asyncio.ensure_future` directly, so construction never
  crashes if the qasync loop isn't running yet.
* **`features/modules/mock_registry.py`**, **`features/plugins/mock_provider.py`**
  -- mock backends for the expanded Module Manager and Plugin Manager
  (version, dependencies, permissions, enable/disable/reload).
* **`domain/voice_announcements/events.py`** -- `AnnouncementEvent`,
  the general app-lifecycle event vocabulary (startup, wake word, task
  lifecycle, automation, memory, plugins, APIs, smart home,
  notifications), consumed by `VoiceAnnouncementService.announce_event()`
  alongside the original `UpdatePhase`-only `announce()`.
* **`services/theme_service.py`** -- completed Theme Engine: the
  inherited `switch()` stub now actually switches themes in-memory,
  accent-color overrides are a safe literal QSS find-and-replace (a
  no-op at the factory-default accent, so the default UI stays
  byte-identical), `tokens()` exposes structured design metadata, and
  `list_custom_themes()` / `load_custom()` pick up future custom themes
  from the user's data directory.

See `MILESTONE_5_DELIVERY.md` for the full file-by-file list and the
honest real-vs-mock breakdown.
