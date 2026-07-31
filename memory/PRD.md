# JARVIS OS — Product Requirements Document

## Original problem statement
Create a production-ready Windows desktop application called **JARVIS OS**
for personal use. Stack: Python 3.13, PySide6, FastAPI, SQLite, ChromaDB,
LangGraph, Ollama, OpenAI, Playwright, pywinauto, Whisper, OpenAI TTS.
Deliver architecture first, then feature milestones.

## User choices
- Layered (core/services/ui/infrastructure) + modular monolith + MVVM.
- Scaffold on Linux, target Windows 11; Windows-only code behind adapters.
- Config-driven providers, `.env`-based; no hard-coded keys.
- `pyproject.toml` primary + `requirements.txt`. Python 3.13.
- OpenAI SDK path: direct `openai` SDK with user-provided keys.
- Streaming UX: both modes, user-toggleable.
- Chat persistence: minimal SQLite now, expanded in Milestone 3.
- Verification: implement + syntax verify + fake-server smoke tests.
- Settings dialog: **complete architecture immediately**; only priority
  pages implemented per milestone; placeholders for future ones.
- **Milestone 2 additions**: provider interfaces future-proofed for
  ElevenLabs, Piper, Deepgram; configurable PTT + global hotkey; wake
  word + always-listening architecture reserved; memory-recall hook
  reserved in `ChatService`.

## Personas
- **Owner-operator** (primary): power user on personal Windows 11.
- **Contributor** (secondary): future maintainer extending features.

## Non-functional requirements
- SOLID, MVVM, `mypy --strict`-clean, ruff/black/pytest-covered.
- Async everywhere; Qt bridged to asyncio via `qasync`.
- Cross-platform where possible; Windows-only behind adapters.
- PyInstaller-ready for Windows `.exe`.

---

## Milestone 0 — Architecture & Scaffolding ✅ *(Jan 2026)*
Full package layout, config, logging, DI, event bus, ports, adapter
skeletons, FastAPI factory, 3 QSS themes, docs, scripts, tests.

## Milestone 1 — Shell & Chat ✅ *(Jan 2026)*
- PySide6 MainWindow (sidebar, chat view, prompt input, status bar).
- Real `OpenAILLMProvider` + `OllamaLLMProvider` (async streaming).
- `ChatService`, `ConversationService`, `SQLiteDatabase`
  (SQLAlchemy 2.x + aiosqlite), Conversation/Message models, repositories.
- `SettingsService.set_env` (whitelisted `.env` upsert).
- Full Settings dialog architecture with `PAGE_REGISTRY` — 16 pages,
  6 implemented (Theme, Startup, Logging, AI Provider, Model, API Keys).
- Fake-LLM + Ollama fake-server test harness; 10 tests green.

## Milestone 2 — Voice ✅ *(Jan 2026)*

**Added ports** (`core/interfaces/`):
- `IAudioRecorder` / `IAudioPlayer` — device I/O.
- `IHotkeyListener` — cross-platform global hotkeys.
- `IWakeWordDetector` — reserved for future engines.
- `IMemoryRecallHook` — Milestone 3 drop-in slot in `ChatService`.

**Real adapters** (`infrastructure/`):
- `WhisperLocalSTTProvider` (openai-whisper, lazy load, thread pool).
- `OpenAIWhisperSTTProvider` (async OpenAI `/v1/audio/transcriptions`).
- `OpenAITTSProvider` (async, encoded bytes; playback-agnostic).
- `SoundDeviceRecorder` — 16-bit PCM mono via `sounddevice`.
- `SoundDevicePlayer` — decodes mp3/wav/opus via `soundfile`,
  plays on the audio thread pool.
- `PynputHotkeyListener` — thread-safe, marshals callbacks onto the
  qasync loop via `call_soon_threadsafe`.
- **Provider factories** (`stt/provider_factory.py`,
  `tts/provider_factory.py`) so ElevenLabs, Piper, Deepgram, etc. slot
  in without service changes.

**Services**:
- `VoiceService` — record → STT / TTS → play; `is_listening` state.
- `HotkeyService` — semantic-name registry over `IHotkeyListener`.

**MVVM UI**:
- `VoiceController` (QObject) — bridges VoiceService to Qt signals
  (`listening_started`, `transcribed`, `speaking_started`, etc.).
- `PushToTalkButton` — hold-to-talk *and* toggle mode.
- `SystemTrayIcon` — Show/Hide/Toggle/Quit; left-click toggles window.
- MainWindow: PTT next to prompt input; voice status chip in status bar;
  toggle-window global hotkey; PTT/toggle-listening hotkey; auto-TTS
  reply when `JARVIS_TTS_SPEAK_REPLIES=true`.

**Settings** — new nested models:
- `VoiceSettings` (mode: push_to_talk / toggle / always_on, hotkey,
  input/output device).
- `WakeWordSettings` (engine, keywords, sensitivity, model_path — engine
  choice reserved but architecture-ready).
- `HotkeySettings` (enabled, toggle_window, tray_show).
- STT settings extended (`sample_rate`, `silence_threshold`,
  `silence_seconds`); TTS extended (`speak_replies`, `playback_speed`).
- **Two new implemented pages**: `Voice Input & Output`, `Wake Word`
  (fully rendered; wake-word `enabled` toggle disabled until engine).
- Whitelist expanded with 15 voice/hotkey env keys.

**Reserved for Milestone 3**:
- `IMemoryRecallHook` protocol + `NoopMemoryRecall` default.
- `ChatService` accepts `memory_recall=` and prepends returned memories
  between the system prompt and the persisted history. Test
  `test_memory_recall_hook.py` proves the hook order and call semantics.

**Tests** (18 green):
- Unit: architecture (3), chat service (1), settings service (4),
  voice + hotkey service (7).
- Integration: chat E2E (1), memory-recall hook (1), Ollama fake server (1).
- Fakes: `FakeLLM`, `FakeRecorder`, `FakePlayer`, `FakeHotkeyListener`,
  `FakeSTT`, `FakeTTS`.

**Deps added**: `pynput>=1.7,<2.0` (already had `sounddevice`, `soundfile`,
`openai-whisper` in Milestone 0 requirements).

Metrics: 126 Python files, 18/18 tests pass. Headless UI smoke
(`scripts/ui_smoke.py`) reports "OK: MainWindow built, SettingsDialog
built, DB initialized." Global hotkeys degrade gracefully in headless
sandboxes with no display server.

---

## Prioritized backlog
### P0 — Milestone 3: Memory
- Alembic migrations; expanded SQLAlchemy models (tasks, memories).
- Full `MemoryService.remember/recall` backed by ChromaDB.
- Ship a `SemanticMemoryRecallHook` and wire it in `Container` — replaces
  `NoopMemoryRecall`. No touching `ChatService`.
- Memory settings page becomes implemented (currently placeholder).
- Timeline UI + semantic search UI.

### P1 — Milestone 4: Automation
- Playwright browser controller behind existing `BrowserService`.
- pywinauto Windows controller behind existing `AutomationService`.
- Task runner: retry, idempotence, allow-lists, undo.

### P2 — Milestone 5: Agents (LangGraph)
- Planner → tools → executor → critic graph.
- SQLite checkpointer (already reserved via `AgentSettings.checkpoint_enabled`).
- Tool registry exposing services.

### P2 — Milestone 6: Polish & Release
- Windows installer (Inno Setup wrapping PyInstaller).
- Auto-updater, crash reporter, first-run wizard.

### P3 — Voice v2.1
- Streaming STT (Deepgram or streaming Whisper) with partial transcripts.
- ElevenLabs + Piper TTS adapters.
- Real wake-word engine (Porcupine / openWakeWord) → flips the currently
  disabled toggle on the Wake Word settings page.
- Voice activity detection (silence thresholds already exposed in Settings).

## Next actions
1. **Milestone 3 — Memory**: replace `NoopMemoryRecall` with a
   `SemanticMemoryRecallHook` fed by ChromaDB; implement the Memory
   settings page.
2. Optional 2.1: streaming STT + wake word (architecture ready).
3. Small polish: bundle a proper tray icon PNG in `resources/icons/`.
