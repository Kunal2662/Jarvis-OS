# Roadmap

This document tracks the high-level product milestones. Detailed task lists
live in the issue tracker; this file only pins the *order* of work.

> **This is a short reference, not the source of truth.**
> [`MASTER_ROADMAP.md`](MASTER_ROADMAP.md) is the single source of truth
> (per its own header) and is kept current; this file is a lighter-weight
> summary that had drifted out of sync with it (fixed as of this update)
> and can drift again — check `MASTER_ROADMAP.md` §1–2 for the
> authoritative, detailed status.

## ✅ Milestone 0 — Architecture & Scaffolding *(this repo)*

* Full folder layout & package structure.
* `Settings` (pydantic-settings) + `.env.example`.
* Loguru+structlog logging bootstrap.
* `dependency-injector` container with all providers declared.
* In-process async `EventBus`.
* Ports (`core.interfaces`) defined for every external system.
* NO-OP + typed adapter skeletons for OpenAI, Ollama, Whisper, OpenAI-TTS,
  Chroma, SQLite, Playwright, pywinauto.
* PySide6 `ThemeManager` + three QSS themes (dark/light/jarvis).
* FastAPI factory + `/api/health`, `/api/ready`.
* PyInstaller build script.
* Docs: architecture, configuration, DI, logging, theming, this roadmap.

## Milestone 1 — Shell & Chat ✅ *(delivered)*

* Real PySide6 main window (sidebar, chat panel, prompt input, status bar).
* Working `OpenAILLMProvider` + `OllamaLLMProvider` — both streaming, async.
* Streaming chat end-to-end (UI ↔ `ChatService` ↔ LLM).
* Persistent conversations (SQLite + SQLAlchemy 2.x async).
* Full Settings dialog architecture (16 pages, 6 implemented: Theme,
  Startup, Logging, AI Provider, Model Selection, API Keys).
* Fake-LLM + fake-Ollama-server test harness; 10 tests green.

## Milestone 2 — Voice ✅ *(delivered)*

* Real `WhisperLocalSTTProvider` (openai-whisper) + `OpenAIWhisperSTTProvider`.
* Real `OpenAITTSProvider` (async, streaming-ready).
* `SoundDeviceRecorder` + `SoundDevicePlayer` audio I/O adapters.
* `PynputHotkeyListener` — global cross-platform hotkeys.
* `VoiceService` (record → STT / TTS → play) + `HotkeyService`.
* MVVM `VoiceController` bridging service to Qt signals.
* Push-to-talk button + system tray icon + toggle-window global hotkey.
* Configurable interaction modes: `push_to_talk`, `toggle`, `always_on`
  (reserved).
* STT/TTS provider factories so ElevenLabs/Piper/Deepgram/Porcupine slot in
  without touching services.
* Real Voice + Wake Word settings pages (Wake Word: architecture-ready,
  disabled until an engine ships).
* `IMemoryRecallHook` reserved and injected into `ChatService` — Milestone
  3 becomes a drop-in.

## Milestone 3 — Memory ✅ *(core delivered)*

* Expanded SQLAlchemy `Memory` model: `memory_type`, `pinned`,
  `archived`, `expires_at`, `last_accessed_at` (still `create_all`-based;
  Alembic migrations remain future work — see `MASTER_ROADMAP.md` §10).
* `MemoryService.remember/recall` backed by ChromaDB (hybrid semantic +
  keyword via Reciprocal Rank Fusion) — plus new `search()`,
  `summarize()`, `enforce_policies()`, `export_memories()` /
  `import_memories()`, `forget_all()`, `delete_archived()`.
* `MemoryService` → `IMemoryRecallHook` via `SemanticMemoryRecallHook`
  — already the active DI binding.
* Settings ▸ Memory page: enable/disable, max memories, retention days,
  auto-summarize, recall tuning, plus Clear / Export / Import actions
  and a live stats readout.
* ~~Not yet delivered: a dedicated Timeline / semantic-search UI view~~
  — **delivered in Milestone 3.1**: `MemoryTimelineView` /
  `MemoryTimelineDialog` (type / pinned / archived filtering,
  per-row pin/archive/delete), reachable from the sidebar. A
  keyword/semantic search box and date-range control inside that
  dialog are still not wired up (the repository/service layer already
  supports date filtering) — see `MASTER_ROADMAP.md` §3 for the exact
  remaining gap.

## Milestone 4 — Automation ✅ *(delivered)*

* Real Playwright browser controller behind `BrowserService`
  (`PlaywrightBrowser` — was a stub, now implemented).
* Real Windows desktop controller behind `AutomationService`
  (`WindowsAutomationAdapter` — was a stub, now implemented).
* Full intent → plan → validate → confirm → execute → undo pipeline;
  task history persistence; ~20 automation actions.
* Not yet delivered: an Automation Panel UI (the service is fully
  MVVM-ready, no Qt views were built), a dedicated download-by-voice
  parser rule, and a few smaller items — see `MILESTONE_4_DELIVERY.md`
  §5 or `MASTER_ROADMAP.md` §1–2 for the exact list.

## Milestone 5 — Official UI & Frontend Framework ✅ *(delivered — not the Agents milestone originally planned here)*

> **Scope note:** this slot was originally planned as "Agents
> (LangGraph)" (see below, now renumbered "Milestone 5-Agents" since it
> remains unbuilt). The team instead delivered the full PySide6 desktop
> UI — Developer Mode, API Center, Update Center, 9 feature workspaces,
> the Theme Engine, and a Personalized Greeting Engine — under the
> Milestone 5 label. Full detail: `MILESTONE_5_DELIVERY.md`.

## Milestone 5.5 — Production Stabilization Pass ✅ *(delivered)*

* Evidence-based audit + fixes over Milestones 0–5: a real
  dangling-async-task reliability bug, a shutdown-path gap, a
  corrupted-config startup crash, a browser URL-scheme security gap, a
  keyboard-accessibility gap, and packaging foundations (PyInstaller
  spec, Inno Setup script, build script). Full detail:
  `AUDIT_REPORT_M0-M5.md`, `CHANGELOG.md`.

## Milestone 5-Agents — Agents (LangGraph) ✅ *(delivered)*

* `AgentOrchestrator` is now a real compiled LangGraph `StateGraph`:
  planner → tool-selector → tool-executor → critic → responder, with a
  loop-back edge and a hard `max_steps` stop.
* SQLite checkpointer (`langgraph-checkpoint-sqlite`) so a thread's
  state survives an app restart; falls back to in-memory if disabled.
* Tool registry (`agents/tools/`) exposes `MemoryService`,
  `AutomationService`, `BrowserService`, `SystemService`,
  `VoiceService` and `ChatService` as structured LangGraph tools.
* Step-level streaming via a new `AgentStepEvent` on the `EventBus`
  (full token-level streaming from inside the responder node is still
  future work). New Developer Mode "Agent Trace" panel shows it live.
* Full detail, including what's still open (vision tool deferred to
  Milestone 6, agent not yet wired into the main Chat view): see
  `MILESTONE_5_AGENTS_DELIVERY.md`.

## Milestone 6 — Polish & Release

* Windows installer (MSIX or Inno Setup wrapping PyInstaller).
* Auto-update channel.
* Crash reporter (opt-in).
* First-run wizard (pick default LLM, download Ollama models, grant hotkey).

---

## Milestone 7 onward — see `MASTER_ROADMAP.md`

This file stops at Milestone 6. Everything after it — M7 (Advanced
Automation), M8 (React Frontend & Desktop Experience), M9 (Runtime &
Core Services), M10/M10A/M10B (AI Orchestrator, Knowledge & Memory,
Intelligence), M10.5 (MCP Platform), M11 (Workspace, Productivity,
Files, AI Workspace, Integrations) — is tracked in
[`MASTER_ROADMAP.md`](MASTER_ROADMAP.md) §1–2 for status and §8 for
scope, with the checkbox-level execution plan in
[`IMPLEMENTATION_ROADMAP.md`](IMPLEMENTATION_ROADMAP.md).

Rather than duplicate those entries here — which is how this file
drifted before — this section is a pointer. Current release: **v0.29.0**
(M8 Phase 2, Universal Application Framework & Logic). See
[`CHANGELOG.md`](../CHANGELOG.md) for the per-release detail.
