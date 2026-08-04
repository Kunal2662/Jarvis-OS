# JARVIS OS — Master Roadmap

> **Single source of truth.** Every milestone, feature, provider and
> architectural decision lives here. Update this file whenever a
> milestone ships or a new one is scheduled — do not fork the roadmap
> into other docs.

**Document owner:** project lead
**Version:** 3.0 · Jul 2026 — reorganized long-term engineering roadmap
(see the changelog note at the very end of this file for what changed
and why).
**Companion docs:** [`ARCHITECTURE.md`](ARCHITECTURE.md) · [`ARCHITECTURE_LEGACY.md`](ARCHITECTURE_LEGACY.md) · [`TECH_STACK.md`](TECH_STACK.md) · [`IMPLEMENTATION_ROADMAP.md`](IMPLEMENTATION_ROADMAP.md) · [`CONFIGURATION.md`](CONFIGURATION.md) · [`DEPENDENCY_INJECTION.md`](DEPENDENCY_INJECTION.md) · [`THEMING.md`](THEMING.md) · [`LOGGING.md`](LOGGING.md)
**Delivery records:** [`MILESTONE_4_DELIVERY.md`](../MILESTONE_4_DELIVERY.md) · [`MILESTONE_5_DELIVERY.md`](../MILESTONE_5_DELIVERY.md) · [`MILESTONE_5_AGENTS_DELIVERY.md`](../MILESTONE_5_AGENTS_DELIVERY.md) · [`AUDIT_REPORT_M0-M5.md`](../AUDIT_REPORT_M0-M5.md) · [`AUDIT_REPORT_M5-AGENTS.md`](../AUDIT_REPORT_M5-AGENTS.md) · [`CHANGELOG.md`](../CHANGELOG.md)

---

## Table of contents

1. [Roadmap charter](#1-roadmap-charter)
2. [Current status](#2-current-status)
3. [Completed milestones (feature frozen)](#3-completed-milestones-feature-frozen)
4. [Engineering standards](#4-engineering-standards)
5. [Validation gate](#5-validation-gate)
6. [Versioning policy](#6-versioning-policy)
7. [Cross-platform systems](#7-cross-platform-systems)
8. [Future roadmap](#8-future-roadmap)
9. [Feature carry-forward map](#9-feature-carry-forward-map)
10. [Complete feature backlog](#10-complete-feature-backlog)
11. [Architecture roadmap](#11-architecture-roadmap)
12. [Database roadmap](#12-database-roadmap)
13. [AI provider roadmap](#13-ai-provider-roadmap)
14. [Version timeline](#14-version-timeline)
15. [Technical debt](#15-technical-debt)
16. [Recommended development order](#16-recommended-development-order)
17. [Appendix — companion documents](#17-appendix--companion-documents)

---

## 1. Roadmap charter

This document is the single, authoritative plan for JARVIS OS — from
the architecture already shipped through the multi-year vision for
where the product is going. It exists so that:

- **Every completed milestone stays historically accurate.** Nothing
  shipped is ever rewritten to look different than it actually landed
  — corrections are appended, not silently edited in place.
- **Every future milestone has an objective, a feature list, explicit
  dependencies, and acceptance criteria** before work starts on it —
  no milestone begins without its port/interface defined first (see
  [§4 Engineering standards](#4-engineering-standards)).
- **One document, not many.** Architecture decisions, database schema
  evolution, AI provider strategy, technical debt, and the delivery
  order all live here, cross-referenced, instead of scattered across
  ad-hoc docs that drift out of sync with each other.

**How to read this document:**
- §3 is frozen history — what shipped, exactly as it shipped.
- §4–§7 are permanent, cross-cutting policies that apply to *every*
  future milestone equally — read them once, not once per milestone.
- §8 is the actual future plan, milestone by milestone.
- §9–§16 are supporting detail (feature-level tracking, architecture
  evolution, database/provider strategy, debt, and sequencing).

---

## 2. Current status

*(Reconciled Aug 2026 — see the changelog addendum for the full
reconciliation pass. Every milestone below now carries exactly one of
four states: ✅ Completed, 🟡 Active, 🟠 Deferred, 🔴 Planned — §14's
version timeline uses the same four symbols consistently.)*

**Current version:** `0.22.0`

**Milestones shipped (✅ Completed):** M0 Foundation → M6 Vision &
Multimodal (Architecture Layer) (10 completed milestones, all
feature-frozen — see §3). M6 shipped its provider-abstraction layer
only (interfaces, settings, mock providers, service, agent tool,
Developer Mode/Settings UI) — real vision/OCR capability remains
future work; see M6's own §3 entry for the full scope note.

**Active (🟡):**
- **M7 — Workflow Intelligence** (see §8) — Phase 1 (Domain Foundation)
  and Phase 2 (Parallel Automation Execution) shipped; Phase 3
  (Structured Graph Planning) 🟠 deferred; Phases 4–6 (Workflow
  Builder, Recorder, Scheduler) pending, paused pending review of the
  "UI Foundation" cross-cutting initiative (Typography, SVG Icon
  System, and an application-state Logic Foundation — a design-system
  hardening pass, not its own roadmap milestone; see §7) — that review
  itself completed and was superseded by the decision to migrate the
  frontend to React + Tauri (M8), so M7's Phases 4–6 remain paused, not
  actively blocked on anything further. See M7's own §8 entry for the
  full phase-by-phase status, including acceptance-criteria detail.
- **M8 — React Frontend & Desktop Experience** (see §8) — Phase 1
  (React Foundation) and Phase 4 (Voice Experience & Motion, in full —
  the Premium UI & Voice Experience initiative's five task groups
  H–L) shipped; Phase 3 (Desktop Workspace) partially shipped (Dashboard,
  Sidebar, Dock, Status Bar, Command Palette shell, Dashboard Widget
  Grid); Phases 2, 5, 6, 7 and the remainder of Phase 3 (Notification
  Center, Context Menu system, Background Task Manager, Workspace
  views, Window management, Developer Mode's 9 read-only viewers,
  Responsive/DPI/Multi-monitor) are 🟠 **deferred to the Deferred
  Backlog** (see the new subsection under M8's §8 entry) — none of
  this blocks M9, which has no real dependency on it (see
  `IMPLEMENTATION_ROADMAP.md` §5's own Dependencies note). **M8 is not
  100% complete** — do not treat it as shipped.
- **M9 — Runtime & Core Services** (see §8) — ✅ **100% complete, all
  five task groups shipped:** Task Group A (Runtime Manager,
  Application Lifecycle), Task Group B (Service Manager, Session
  Manager, Configuration Manager, Runtime Health Monitor, Runtime
  WebSocket API, Runtime Integration), Task Group C (Background Task
  Manager, Crash Recovery, Resource Manager), Task Group D (Plugin SDK,
  Loader, Sandbox, Extension API, Permission Model, Registration
  System, Store, Marketplace Foundation), and Task Group E (Debug
  Console, Live Logs, Performance Profiler, State Inspector, API
  Inspector, Plugin Marketplace Foundation REST API, Permission
  Management API, Plugin Diagnostics) — see
  `IMPLEMENTATION_ROADMAP.md` §5.
- **M10 — AI Orchestrator** (see §8) — 🟡 **partial: the buildable-now
  scope shipped, the M14/M16-dependent remainder explicitly deferred,
  not silently dropped.** Shipped: Intent Engine (diagnostic), Context
  Engine, parallel tool dispatch (AC1, absorbing M7 Phase 3), interim
  Permission Validation (AC3), real token-level streaming for the
  tool-composed path (AC2), Decision Engine's `response_mode`,
  `agent.step` on the Runtime WebSocket relay, and
  `/api/v1/agent/invoke` + `/api/v1/agent/stream`. Context Engine's
  knowledge-graph half, originally deferred pending M10A, is now real
  -- see M10A below. Still deferred pending their owning milestones:
  Learning/Feedback via M16's Reflection Engine (needs M16), Permission
  Validation's final M14-routed form (needs M14). **M10 is not 100%
  complete** — do not treat it as shipped in full.
- **M10A — Universal Search & Knowledge Platform** (see §8) — ✅
  **Completed.** Knowledge Graph/Relationship Graph, Persistent Memory
  (reuses M3's `pinned`), Reflection Foundation (on-demand, not
  scheduled), scoped Learning (correction supersedes stale
  relationships), Universal Search with a provider registry
  (`register_source`/`unregister_source`/`get_sources`), Memory/
  Command/Semantic/AI Search, `/api/v1/search` + `/api/v1/knowledge/*`,
  `memory`/`knowledge` WebSocket categories, agent tool integration,
  and closing M10's own Context Engine deferral. One key feature
  explicitly deferred: File Search (needs M11B's File Manager, not
  started) — see M10A's own entry for the full Deferred list.
- **M10B — Intelligence Layer** (see §8) — ✅ **Completed.** Goal
  Manager (hierarchical progress tracking), deterministic Routine
  Learning (direct-observation reinforcement, not LLM pattern mining),
  Preference Learning (structured key-value store, separate from M3's
  freeform preference memories), Context Awareness (time/activity
  signals; no location provider exists yet, documented not faked),
  Predictive Suggestions (keyword-boost, no AI reranking), Daily
  Briefing (on-demand), `goal`/`briefing` WebSocket categories, agent
  tool integration, and a fourth Universal Search provider
  (`GoalSearchSource`). One key feature explicitly deferred: automatic
  scheduled Daily Briefing delivery (needs M7's Scheduler Phase 6, not
  started) — see M10B's own entry for the full Deferred list.

**Technology direction (Aug 2026):** JARVIS's frontend is migrating
from PySide6 to React + Tauri, starting at M8 — see
[`TECH_STACK.md`](TECH_STACK.md) for the full technology decision and
[`IMPLEMENTATION_ROADMAP.md`](IMPLEMENTATION_ROADMAP.md) for the
active, phase-by-phase execution plan. This is a UI-technology
migration only: M0–M7 shipped and remain historically accurate on
PySide6 (§3); the Python backend (`services → agents →
core.interfaces`) is unchanged and gains only a FastAPI/WebSocket-
facing adapter. §8's M8–M11 entries were retitled accordingly (React
Frontend & Desktop Experience, Runtime & Core Services, AI
Orchestrator, Integrations & Cloud Platform), with three new lettered
companions — M10A, M10B, M11B — added to house scope displaced by the
retitling, none of it dropped. See each entry's own "Retitled Aug
2026" note for what moved where.

**Version history summary:** `0.1` → `0.2` → `0.3` → `0.3.1` shipped on
schedule; Milestones 4, 5, and the 5.5 stabilization pass all shipped
under an unbumped `0.3.0` (a drift, closed retroactively — see §15);
`0.4.0` is the first version bump since `0.3.1` and is the first
version built under this document's now-codified
[Versioning policy](#6-versioning-policy) (§6); `0.5.0` (M6,
Architecture Layer) follows the same policy. `0.5.1` and `0.5.2` are
out-of-band PATCH releases per §6 (cryptography security upgrade;
DI container startup-time architecture fix) — neither is a milestone
and neither bumps past `0.5.x`; M7's own MINOR bump to `0.6.0` still
lands only once M7 itself completes. Every version from here forward
increments on milestone completion, not on a calendar.

---

## 3. Completed milestones (feature frozen)

> **Feature freeze policy.** Every milestone in this section is
> **done**. It may only be touched again for: critical bug fixes,
> security fixes, performance improvements, or compatibility fixes —
> never new features. New capability, however small, belongs in a
> future milestone (§8), not folded into a frozen one. This is why
> Milestone 5-Agents exists as its own slot rather than being folded
> back into Milestone 5, and why the Milestone 5.5 stabilization pass
> is documented as an audit-and-fix pass, not a feature milestone.

| Code | Milestone | Delivered | Delivery record |
|------|-----------|-----------|------------------|
| **M0** | Foundation | Jan 2026 | *(scaffolding — no dedicated delivery doc)* |
| **M1** | Chat Engine | Jan 2026 | *(shipped with M0)* |
| **M2** | Voice Platform | Jan 2026 | *(shipped with M0/M1)* |
| **M3** | Memory Platform (core) | Jul 2026 | — |
| **M3.1** | Memory Platform (polish) | Jul 2026 | — |
| **M4** | Automation Platform | Jul 2026 | [`MILESTONE_4_DELIVERY.md`](../MILESTONE_4_DELIVERY.md) |
| **M5** | Desktop Platform | Jul 2026 | [`MILESTONE_5_DELIVERY.md`](../MILESTONE_5_DELIVERY.md) |
| **M5.5** | Production Stabilization Pass | Jul 2026 | [`AUDIT_REPORT_M0-M5.md`](../AUDIT_REPORT_M0-M5.md) |
| **M5A** | Agent Runtime | Jul 2026 | [`MILESTONE_5_AGENTS_DELIVERY.md`](../MILESTONE_5_AGENTS_DELIVERY.md), [`AUDIT_REPORT_M5-AGENTS.md`](../AUDIT_REPORT_M5-AGENTS.md) |
| **M6** | Vision & Multimodal (Architecture Layer) | Jul 2026 | [`MILESTONE_6_VISION_DELIVERY.md`](../MILESTONE_6_VISION_DELIVERY.md) |

> **Naming note.** `M5A` is this document's short code for what earlier
> revisions called "Milestone 5-Agents." Same milestone, same delivery
> docs, same code — the label is shortened here to match the `M<n><letter>`
> convention used for every "companion/expansion" milestone from here
> forward (`M11A`, `M13A`, `M14A`, `M17A`, `M20A`, `M23A`, `M23B` — see
> §8). File names (`MILESTONE_5_AGENTS_DELIVERY.md`, etc.) are
> untouched.

> ⚠️ **Scope note — the Milestone 5 / M5A split.** This roadmap
> originally planned "Milestone 5" as the Agent Runtime. The team
> instead delivered the Official UI & Frontend Framework under that
> label, and the original Agent Runtime scope shipped later as its own
> slot ("Milestone 5-Agents", now `M5A`). Both are documented in full
> below, exactly as they actually happened.

### M0 — Foundation ✅ *(Jan 2026)*

**Scope:** Architecture, Dependency Injection, Configuration, Logging,
Core Framework.

**Delivered:**
- Layered + modular-monolith architecture (`core` / `infrastructure` /
  `services` / `agents` / `features` / `ui`), strict dependency
  direction enforced by convention (see §11).
- SOLID + Ports & Adapters at every external boundary.
- Dependency Injection via `dependency-injector` — one composition root
  (`core/di/container.py`).
- Config system: `pydantic-settings`, nested sections, `.env` +
  env-var override, cross-field validation, whitelisted UI persistence.
- Logging: `loguru` + `structlog`, stdlib interception, console / JSON
  / rotating file sinks.
- Async event bus (`EventBus`) — in-process, subscriber-safe.
- Exception hierarchy rooted at `JarvisError`.
- `ThemeManager` + 3 QSS themes (`jarvis`, `dark`, `light`) + `Palette`.
- FastAPI factory + `/api/health`, `/api/ready`.
- PyInstaller build script (`scripts/build_windows.py`).
- Comprehensive companion docs + this master roadmap.

**Architecture Evolution**

Introduced in this milestone: the layered architecture itself, the DI
Container (`core/di/container.py`), the async `EventBus`, the
`pydantic-settings` config system, and the `JarvisError` exception
hierarchy.

Later reused by: every subsequent milestone without exception — this
is the foundational substrate the rest of the codebase is built on, not
an optional dependency any later milestone chose to adopt. Two notable
extensions rather than mere reuse: the DI Container gained 14 lazy
`_build_*` adapter factories across M2–M6, then had its remaining
eager string-path providers converted to the same pattern in the DI
Container Architecture Fix (`v0.5.2`, out-of-band between M6 and M7);
the `EventBus` gained its first concrete event types in M4
(`AutomationStepEvent`) and M5A (`AgentStepEvent`), a pattern every
later milestone (M6, M7) has continued rather than inventing a second
notification mechanism.

### M1 — Chat Engine ✅ *(Jan 2026)*

**Scope:** Conversation, Streaming, LLM Providers, Context Management.

**Delivered:**
- PySide6 `MainWindow` with Sidebar / ChatView / PromptInput /
  StatusBar, keyboard shortcuts, streaming assistant bubble.
- `OpenAILLMProvider` — async streaming, embeddings, error translation.
- `OllamaLLMProvider` — async streaming, local-first.
- `ChatService` — user persist → memory recall (via hook) → LLM stream
  → assistant persist. Non-streaming `ask()` on top of `stream()`.
- `ConversationService` + repositories over `Conversation` / `Message`
  ORM models.
- `SQLiteDatabase` — SQLAlchemy 2.x async + aiosqlite, idempotent init.
- `SettingsService.set_env` — whitelisted `.env` upsert.
- Complete Settings dialog architecture (`PAGE_REGISTRY`,
  `PageDescriptor`) — 16 pages, extensible via one-line `register()`.
- Implemented pages: Theme · Startup · Logging · AI Provider · Model
  Selection · API Keys.
- `IMemoryRecallHook` + `NoopMemoryRecall` injected into `ChatService`
  — M3 later swapped the implementation without touching chat.

**Architecture Evolution**

Introduced in this milestone: `ChatService`, `ConversationService`,
`SQLiteDatabase` (SQLAlchemy 2.x async), and the `IMemoryRecallHook`
port.

Later reused by: M3 (swapped `NoopMemoryRecall` for
`SemanticMemoryRecallHook` behind the same port — the exact
"implementation swapped, chat untouched" outcome this milestone's own
delivered-list entry called out); M4 (`TaskHistoryRepository` follows
the same SQLAlchemy-repository pattern `ConversationService`
established); M5A (`agents/tools/chat_tools.py` wraps `ChatService` as
an agent tool). `SQLiteDatabase` itself is now the one shared database
connection every later milestone's repositories (`MemoryRepository`,
`TaskHistoryRepository`) are built against — no second database
technology was ever introduced.

### M2 — Voice Platform ✅ *(Jan 2026)*

**Scope:** Speech-to-Text, Text-to-Speech, Wake Word, Voice Pipeline.

**Delivered:**
- Ports: `IAudioRecorder`, `IAudioPlayer`, `IHotkeyListener`,
  `IWakeWordDetector`, `IMemoryRecallHook`.
- Real adapters: `WhisperLocalSTTProvider`, `OpenAIWhisperSTTProvider`,
  `OpenAITTSProvider`, `PiperTTSProvider`, `KokoroTTSProvider`,
  `EdgeTTSProvider`, `ElevenLabsTTSProvider`, `SoundDeviceRecorder`,
  `SoundDevicePlayer` (streaming/queued playback + interrupt),
  `PynputHotkeyListener`, `PorcupineWakeWordDetector`,
  `OpenWakeWordDetector`, `NoopWakeWordDetector`.
- Pluggable provider-factory registries in `infrastructure/stt/`,
  `infrastructure/tts/` and `infrastructure/wake_word/` — adding a new
  backend is a registration call, no branching elsewhere.
- `VoiceService` — a full conversation state machine
  (Idle/Listening/Thinking/Speaking/Interrupted/Offline/Error), with
  streaming TTS (`speak_stream`, sentence-chunked) and barge-in
  interrupt support (mic-monitor cancels playback instantly), plus
  `HotkeyService` (semantic hotkey registry).
- `VoiceController` (MVVM) bridges state changes to Qt signals, feeds
  LLM tokens into `speak_stream` incrementally, and drives
  continuous-conversation auto-relisten + wake-word start/stop.
- Widgets: `PushToTalkButton` (hold + toggle), `VoiceOrb` (animated
  listening/thinking/speaking feedback), `SystemTrayIcon`
  (Show/Hide/Toggle/Quit).
- Global toggle-window hotkey + PTT / toggle-listen hotkeys wired
  through `HotkeyService`.
- Auto-TTS on assistant reply, streamed sentence-by-sentence.
- Implemented pages: Voice (all TTS providers, pitch/volume/device
  controls) · Wake Word (Porcupine / openWakeWord, fully enabled).

**Architecture Evolution**

Introduced in this milestone: `VoiceService`, `HotkeyService`, the
`IAudioRecorder`/`IAudioPlayer`/`IHotkeyListener`/`IWakeWordDetector`
ports, and the `VoiceOrb`/`PushToTalkButton` widgets.

Later reused by: M5A (`agents/tools/voice_tools.py` wraps
`VoiceService` as an agent tool); M5 (`VoiceOrb` reused verbatim in the
Home dashboard's hero panel and in the dedicated Voice workspace,
`ui/views/workspaces/voice_workspace.py`, at a different fixed size —
same widget, two placements, not two implementations).

### M3 — Memory Platform ✅ *(core Jul 2026, polish Jul 2026 as M3.1)*

**Scope:** Semantic Memory, Memory Timeline, Memory Search, Policies,
Recall.

**M3 core delivered:**
- `MemoryType` enum (conversation / long_term / preference / project /
  task / file / ai_context) — every stored memory is classified.
- `Memory` ORM model extended: `memory_type`, `pinned`, `archived`,
  `expires_at`, `last_accessed_at`.
- `MemoryRepository` — type/archived filters, `count`, `list_expired`,
  `list_prunable` (pinned rows count against the cap but are never
  pruned), `archive`, bulk delete.
- `MemoryService.search(query, mode="semantic"|"keyword"|"hybrid"|"recent")`,
  `.summarize()` (LLM-authored, falls back to truncation on failure),
  `.enforce_policies()` (expiration + max-size pruning, returns a
  `PolicyReport`), `.delete_archived()`, `.export_memories()` /
  `.import_memories()` (JSON round-trip), `.forget_all()`.
- `SemanticMemoryRecallHook` — the active `memory_recall_hook` DI
  binding (hybrid semantic + keyword via Reciprocal Rank Fusion).
- `MemorySettings` (enabled, max_memories, retention_days,
  auto_summarize, recall_top_k, recall_min_score) — all six keys
  whitelisted in `SettingsService`.
- **Memory** settings page: live-editable tunables + Clear / Export /
  Import actions + a stats readout.
- Test double: `FakeVectorStore` (cosine similarity + `where`
  filtering, no `chromadb` dependency needed for unit tests).

**M3.1 polish delivered:**
- `MemoryRepository.list_filtered()` — type / pinned-only / archived /
  date-range listing backing the Timeline view.
- `MemoryRepository.restamp_expirations()` +
  `MemoryService.restamp_retention()` — recompute `expires_at` on every
  unpinned, active row from the *current* `retention_days`; wired into
  Settings ▸ Memory so changing the retention slider re-archives
  newly-expired rows immediately.
- `MemoryController` (`features/memory`) + `MemoryTimelineView` +
  `MemoryTimelineDialog` — filter by type / pinned / archived, per-row
  pin·unpin / archive / delete via context menu. Sidebar "🧠 Memory"
  button.
- Alembic migrations (`alembic/`, baseline `0001_initial_schema`).
  `create_all` stays as an idempotent dev/test fallback; new schema
  changes ship as Alembic revisions from here on.
- `WhisperLocalSTTProvider.preload()` — model warmed at GUI startup.
- Background scheduler — `enforce_policies()` runs every 6 hours, not
  only at boot.
- **Still open:** no keyword/semantic search box or date-range control
  in the Timeline dialog (the repository/service layer already
  supports it — `list_filtered(start_date=…, end_date=…)` — just not
  wired to a widget); no PII redaction before embedding.

**Architecture Evolution**

Introduced in this milestone: `MemoryService`,
`SemanticMemoryRecallHook`, and `MemoryRepository`.

Later reused by: M5A (`agents/tools/memory_tools.py` wraps
`MemoryService` as an agent tool); M5 (`MemoryTimelineView`/
`MemoryTimelineDialog`, the Home dashboard, and `greeting_service.py`'s
context-gathering all consume `MemoryService` directly). The
`SemanticMemoryRecallHook`/`IMemoryRecallHook` pairing introduced in M1
and completed here is the one recall mechanism every later
memory-aware surface uses — no second recall implementation exists.

### M4 — Automation Platform ✅ *(Jul 2026)*

**Scope:** Desktop Automation, Browser Automation, Safety, Undo,
History.

**Objective:** give JARVIS "hands" — a full intent → plan → validate →
confirm → execute → undo pipeline for controlling the desktop and
browser from natural language.

**Delivered:** real, non-stub `PlaywrightBrowser` and
`WindowsAutomationAdapter` (both were `NotImplementedError` before
this); `IntentParser`, `TaskPlanner`, `SafetyValidator`,
`PermissionGate`, `ActionExecutor`, `UndoManager`, `HistoryService`,
`RecipeManager`; a safety layer (dangerous-action confirmation gating,
system-path/mass-delete/shell-injection detection, plus a
Milestone-5.5 addition: browser URL-scheme validation); ~20 automation
actions across apps/files/system/search; task history persistence
(`TaskHistoryRepository`). Full file list and architecture diagram:
[`MILESTONE_4_DELIVERY.md`](../MILESTONE_4_DELIVERY.md).

- **Dependencies:** M1 (chat as trigger).
- **Files / modules touched:** ~35.
- **Acceptance criteria:** ✅ Playwright opens a URL and extracts text
  end-to-end · ✅ `PermissionGate` enforces confirmation/denial · ✅
  Undo works for reversible operations · 🟡 Recipes are JSON, not
  YAML-with-Pydantic-schema as originally scoped (functionally
  equivalent).
- **Still open:** no dedicated `ActionType.DOWNLOAD` parser rule; no
  Automation Panel / Running Tasks / History / Undo UI (service is
  fully MVVM-ready, Qt views never built); voice/chat don't
  auto-route into `AutomationService.run_command()`; no scheduled
  purge of expired history; steps still execute sequentially even
  when independent (no real parallel execution — see M7); Windows
  volume/brightness shells out to the optional `nircmd` tool if
  present, no bundled fallback.

**Architecture Evolution**

Introduced in this milestone: `AutomationService`, `ActionExecutor`,
`RecipeManager`, `TaskPlanner`, and the `Step`/`ExecutionPlan` domain
model (`domain/automation/models.py`).

Later reused by: M5A (`agents/tools/automation_tools.py` routes the
agent's `run_automation` tool straight through
`AutomationService.run_command()` — the agent never touches the
parser/planner/executor directly); M7 Phase 2, which rewrote
`ActionExecutor.run_plan()`'s dispatch loop in place (sequential →
wave-based) without changing `Step`/`ExecutionPlan`'s shape at all —
the dependency-graph data model (`Step.depends_on`) this milestone
introduced turned out to already be exactly what M7 needed, unused
until then. `RecipeManager`'s storage approach is also the direct
model M7 Phase 1's `WorkflowDefinition` was deliberately shaped to sit
alongside for its own future Workflow Builder phase.

### M5 — Desktop Platform ✅ *(Jul 2026)*

**Scope:** Premium UI, Dashboard, Developer Mode, Theme Engine,
Feature Workspaces.

**Delivered:** the full PySide6 desktop shell — Home dashboard, Chat,
Developer Mode (gated by a PBKDF2-HMAC-SHA256-hashed admin password)
with Module Manager, Plugin Manager, API Center, Update Center,
Developer Console, Security Center, Backup/Restore, System
Information, and Performance Monitor; 9 feature workspaces (Voice,
Files & Drive, Browser, Coding, Finance, Smart Home, Calendar, Gmail,
Spotify); a completed Theme Engine (dark/light/jarvis, accent-color
overrides, design tokens); a Personalized Greeting Engine (real
LLM-generated, context-aware startup greetings). Full file list:
[`MILESTONE_5_DELIVERY.md`](../MILESTONE_5_DELIVERY.md).

- **Dependencies:** M0–M3.1 (needed real services to build a UI
  around).
- **Files / modules touched:** ~120+ across three delivery passes.
- **Tests:** 205+ dedicated UI/service tests.
- **Still open:** no real SVG/Lucide icon assets (registry supports
  them, none ship — later shipped by the UI Foundation pass, see
  Architecture Evolution below); Update Terminal is edge-snapped, not
  a true `QDockWidget`; no real plugin loader (architecture only, as
  instructed — plugin-loader scope now lives in M9's Runtime & Core
  Services, not M8, per the Aug 2026 frontend migration — see the
  Frontend Migration Note below); most `AnnouncementEvent` values aren't fired
  from their subsystem yet; no custom-theme picker; every
  Gmail/Spotify/Weather/Finance/Smart-Home integration is still mock
  data by the brief's own instruction (see
  [`FUTURE_INTEGRATION_GUIDE.md`](FUTURE_INTEGRATION_GUIDE.md) for
  swapping a mock provider for a real one).

**Architecture Evolution**

Introduced in this milestone: the PySide6 desktop shell itself
(`MainWindow`, `Sidebar`, the workspace views), the Theme Engine
(`ThemeService`, `theme_manager.py`, `resources/themes/*.qss`), and
Developer Mode as an extensible gated panel (Module Manager, Plugin
Manager, API Center, Update Center, Developer Console, Security
Center, Backup/Restore, System Information, Performance Monitor).

Later reused by: M5A, which added its **Agent Trace** section directly
into this milestone's Developer Mode panel rather than building a new
gated surface; the UI Overhaul cross-cutting initiative (see §7 "UI
Foundation"), which built Typography and the SVG Icon System directly
on top of this milestone's `ThemeService`/`theme_manager.py` and
existing widget set (`buttons.py`, `card.py`, `service_widget.py`,
`sidebar.py`, every workspace view) rather than introducing a parallel
styling system.

**Frontend Migration Note (Aug 2026).** Everything above is preserved
exactly as it shipped — this milestone's scope, delivered list, and
"still open" items are not being rewritten. What's changing is only
where the codebase is going *next*: JARVIS's frontend technology
decision (see [`TECH_STACK.md`](TECH_STACK.md)) moves from PySide6 to
React + Tauri starting at M8. Concretely:
- The PySide6 desktop shell, Theme Engine, and Developer Mode panels
  this milestone delivered remain the real, shipped, historically
  accurate UI — nothing about them is retroactively false.
- Going forward, this milestone is understood internally as having
  delivered JARVIS's **backend platform** (the real services a UI
  needs to exist before it can be built around them — see
  Dependencies above) bundled together with a PySide6 frontend that
  is now superseded. The backend half was never Qt-specific to begin
  with (`services → agents → core.interfaces`, per
  `ARCHITECTURE_LEGACY.md`) and needs no rework; only the UI-rendering
  half is being replaced. See the new `ARCHITECTURE.md` for the
  forward-looking standard M8 onward is built against.
- M8's own scope (§8) is retitled "React Frontend & Desktop
  Experience" and rebuilds this milestone's UI surface (dashboard,
  workspaces, Developer Mode panels, Theme Engine equivalent) on the
  new stack, feature-by-feature — see `IMPLEMENTATION_ROADMAP.md` for
  the active, phase-by-phase execution plan.
- The §7 "UI Foundation" pass (Typography, SVG Icon System,
  `ModuleStateMachine`) is likewise being ported rather than
  discarded — its design tokens and Lucide icon set carry forward
  unchanged into the React stack; only the Qt-specific rendering code
  (`QFontDatabase`, `QSvgRenderer`/`QPainter`, QSS) is left behind. See
  §7's own note for detail.

### M5.5 — Production Stabilization Pass ✅ *(Jul 2026)*

Not a feature milestone — an evidence-based engineering audit and
stabilization pass over M0–M5. Full detail:
[`AUDIT_REPORT_M0-M5.md`](../AUDIT_REPORT_M0-M5.md).

- **Real, verified fixes:** a 55-site dangling-asyncio-task
  reliability bug; a shutdown-path gap (closing the window via the OS
  X button bypassed all resource cleanup) — fixed with a new
  `ShutdownManager` (`core.lifecycle.shutdown_manager`) so future
  subsystems register a cleanup hook once instead of every future
  service editing `MainWindow`; a corrupted-`.env`-file startup
  crash; a timing-attack anti-pattern in Developer Mode's password
  check; a browser-automation URL-scheme validation gap
  (`file://`/`javascript:`/`data:` could have been auto-allowed); a
  keyboard-accessibility gap (no visible focus indicator on any
  button); a measured ~57% `MainWindow` construction speedup (lazy
  workspace imports).
- **Packaging foundations laid, not yet verified:**
  `packaging/jarvis.spec` (PyInstaller), `packaging/jarvis_installer.iss`
  (Inno Setup), `packaging/build_windows.ps1` — see
  [`PACKAGING.md`](PACKAGING.md) for the honest "foundational, not
  release-ready" status.
- **Tests:** ~65 new regression/reliability/security tests; suite
  ended this pass at 265/265 passing, 234/234 modules importing
  cleanly with zero circular dependencies.

### M5A — Agent Runtime ✅ *(Jul 2026 — build; pre-merge validation Jul 2026)*

**Scope:** LangGraph, Planner, Critic, Tool Registry, SQLite
Checkpoints, Agent Trace.

**Objective:** a real agent graph that can plan, call tools, execute,
and self-critique — delivered as a standalone, independently-invokable
orchestrator (see "still open" below for why it isn't wired into the
main Chat view yet). Full detail, including the pre-merge validation
pass that followed the initial build:
[`MILESTONE_5_AGENTS_DELIVERY.md`](../MILESTONE_5_AGENTS_DELIVERY.md) ·
[`AUDIT_REPORT_M5-AGENTS.md`](../AUDIT_REPORT_M5-AGENTS.md).

**Delivered:**
- `AgentOrchestrator` — a real, compiled LangGraph `StateGraph`:
  `planner → tool_selector → tool_executor → critic → responder`,
  looping back from critic to tool-selector for multi-step tasks, with
  a hard `max_steps` stop (also clamped against
  `constants.MAX_AGENT_STEPS_HARD_CAP`) so a critic that never agrees
  "complete" can't loop forever.
- Tool registry (`agents/tools/`) — `MemoryService`,
  `AutomationService`, `BrowserService`, `SystemService`,
  `VoiceService`, `ChatService` auto-exposed as `langchain_core`
  structured tools; tool *selection* is driven by structured-JSON
  prompts against the existing `ILLMProvider` port rather than a
  second, langchain-native chat-model port (see
  `agents/prompting.py`'s module docstring).
- SQLite checkpointer (`agents/checkpointer.py`,
  `langgraph-checkpoint-sqlite`) — a thread's state survives a
  restart when `AgentSettings.checkpoint_enabled` is true; falls back
  to an in-memory saver otherwise.
- `SystemService.status()` — real `psutil`-backed implementation (was
  a stub since M1), needed as the agent's `get_system_status` tool.
- `AgentStepEvent` on the `EventBus` + Developer Mode **Agent Trace**
  section — run an ad-hoc prompt, watch each graph step arrive live.
- Prompt-injection mitigation: tool output fenced with an explicit
  `<<<TOOL_OUTPUT>>>...<<<END_TOOL_OUTPUT>>>` marker plus an
  instruction never to treat it as instructions
  (`UNTRUSTED_TOOL_OUTPUT_NOTICE`) — closes the gap the M5.5 audit
  flagged before this runtime existed.
- **Pre-merge validation pass** (after the initial build): real venv,
  full `ruff`/`black`/`mypy --strict` pass (all clean on this
  milestone's own files), 308/309 tests passing end-to-end, one real
  runtime bug found and fixed (`aiosqlite`/`langgraph-checkpoint-sqlite`
  incompatibility breaking the default SQLite-checkpointer path —
  pinned `aiosqlite<0.21`, added a permanent regression test), a
  `CVE-2025-67644` dependency finding confirmed not exploitable by
  anything this milestone ships.

- **Dependencies:** M3, M4 (tools depend on their services).
- **Files / modules touched:** ~30.
- **Tests:** ~40 dedicated tests + 1 regression test added during
  validation, all passing.
- **Still open:** vision tool deliberately deferred to M6 (a real
  vision pipeline belongs there, not duplicated here); the Chat view
  still talks to `ChatService` directly, not routed through the agent
  (deliberate — keeps the stable M1 chat flow unaffected; a
  chat-facing "Agent Mode" is future work, see M7); `stream()`
  re-chunks the already-composed final answer word-by-word rather
  than truly streaming LLM tokens from inside the responder node; no
  per-step timings in the trace panel; no UI for resuming a
  checkpointed thread (the checkpointer plumbing works, nothing
  exposes "resume thread X" yet); `run_automation` never passes a
  confirmation callback, so any action needing interactive
  confirmation is auto-denied.

**Architecture Evolution**

Introduced in this milestone: `AgentOrchestrator` and its compiled
LangGraph `StateGraph`, the `agents/tools/` registry, the SQLite
checkpointer, and `AgentStepEvent`.

Later reused by: M7 Phase 1's `WorkflowStep` domain model
(`domain/workflow/models.py`), whose `WorkflowStepKind.AGENT_TOOL`
variant is explicitly modelled to invoke "a registered agent tool (see
`agents/tools/registry.py`)" by name and arguments — a design-time
reference to this milestone's tool registry, not yet a runtime one
(Phase 1 deliberately shipped domain models only; no scheduler,
executor, or LangGraph wiring exists yet for that step kind — see M7
Phase 4+). No other milestone extends `AgentOrchestrator`,
`AgentState`, or the graph nodes themselves yet; the cross-tool
parallelism envisioned for those was explicitly scoped as M7 Phase 3
and deferred, not built.

### Architecture, technologies, and tests as of M5A

**Architecture implemented:**
```
UI (PySide6)  →  Features (MVVM controllers)  →  Services  →  Agents  →  core.interfaces
                                                                             ▲
                                              Infrastructure ────────────────┘
```
Strict dependency rule enforced by convention. All external SDKs are
imported only inside `infrastructure/*/` — with one narrow, deliberate
exception as of M5A: `agents/tools/*.py` and `agents/prompting.py`
import `langchain_core.tools` directly to build the tool registry (the
`agents` layer importing its own declared dependency for the job it
exists to do — `ILLMProvider` remains the one and only chat-LLM port,
no `infrastructure/` boundary is crossed).

**Technologies in use** *(delivered, not planned — see §13 for what's
still planned)*:

| Concern       | Technology                                              |
|---------------|---------------------------------------------------------|
| Language      | Python 3.13                                             |
| Desktop UI    | PySide6 6.7 + `qasync`                                  |
| API           | FastAPI + Uvicorn                                       |
| SQL DB        | SQLAlchemy 2.x + aiosqlite (SQLite)                     |
| Config        | pydantic 2 + pydantic-settings                          |
| Logging       | loguru + structlog                                      |
| DI            | dependency-injector                                     |
| Chat LLMs     | OpenAI (`openai` SDK), Ollama (`ollama` SDK)            |
| STT           | Whisper local (`openai-whisper`), OpenAI Whisper API    |
| TTS           | OpenAI TTS, Piper, Kokoro, Edge TTS, ElevenLabs         |
| Audio I/O     | sounddevice + soundfile                                 |
| Hotkeys       | pynput                                                  |
| Agent runtime | LangGraph `StateGraph` + `langgraph-checkpoint-sqlite`; `langchain-core` for tool schemas only |
| Testing       | pytest + pytest-asyncio + pytest-aiohttp + pytest-qt + pytest-cov |
| Lint / format | ruff + black + mypy (strict)                            |

**Tests:** 308 passing / 309 collected as of the M5A pre-merge
validation pass (see [`AUDIT_REPORT_M5-AGENTS.md`](../AUDIT_REPORT_M5-AGENTS.md)
for the full breakdown; the one remaining "error" is a pre-existing,
documented `pytest-aiohttp`-extra exclusion, not a failure). Earlier
per-milestone counts (M0–M3.1: 49/49; M4/M5: tracked in their own
delivery docs; M5.5: 265/265) are preserved in those delivery docs
rather than reconciled into one running total here — see §17 for the
full document index.

### M6 — Vision & Multimodal ✅ *(Architecture Layer — Jul 2026)*

**Scope note.** M6's §8 brief (preserved below in this same entry)
described the full feature set: real screen/camera capture, offline
OCR, image preprocessing, clipboard/drag-drop chat input, Image
Question Answering, and a Vision Agent Tool. What actually shipped
this pass is the **provider-abstraction layer only** — the Ports &
Adapters plumbing every one of those features will eventually plug
into, built and validated through seven incremental phases, each with
its own regression-tested delivery. No vision/OCR dependency
(`mss`/`opencv`/`pytesseract`/`Pillow`/PaddleOCR) was added, no
capture/OCR/image-processing code was written, and no multimodal chat
message type exists yet. This mirrors the M5 / M5A scope-split pattern
(§3) — same rationale: ship the real, tested slice now, document the
deferred remainder honestly rather than silently narrowing the
milestone's own definition.

**Objective:** give JARVIS real eyes — screen, camera, and document
understanding, wired into both chat and the agent runtime. *(Only the
abstraction layer this objective depends on has shipped; the eyes
themselves have not.)*

**Delivered** (Phases 1–7, [`MILESTONE_6_VISION_DELIVERY.md`](../MILESTONE_6_VISION_DELIVERY.md)):
- `IVisionProvider` / `IOCRProvider` ports (`core/interfaces/`) —
  mirror `ILLMProvider`'s shape (`name`, `async health()`),
  deliberately minimal until a real backend exists to validate a
  fuller method surface against — the same "clean interface, no real
  implementation yet" pattern already used for `IGmailProvider`.
- `VisionSettings` / `OCRSettings` (`core/config/settings.py`) —
  `enabled: bool = False` by default; `JARVIS_VISION_ENABLED` /
  `JARVIS_OCR_ENABLED` added to the Settings-UI writable key
  whitelist.
- `MockVisionProvider` / `MockOCRProvider`
  (`infrastructure/vision/`, `infrastructure/ocr/`) — the only
  concretes wired in; both honestly report
  `enabled=False, healthy=False` rather than simulating capability.
  Provider factories follow the existing `build_x_provider()` shape,
  with no backend-selection logic yet (nothing to select between).
- `VisionService` (`services/vision_service.py`) — one method,
  `status()`, reporting both providers' health as a plain dict.
- `VisionProviderStatusEvent` (`core/events/events.py`) — defined,
  matching `AgentStepEvent`'s shape; not yet published anywhere (no
  status change exists to report).
- Agent tool `vision_status` (`agents/tools/vision_tools.py`,
  registered in `agents/tools/registry.py`) — reports provider
  availability only. Required one additive, backward-compatible
  change to `AgentOrchestrator` (an optional `vision:
  VisionService | None = None` constructor kwarg, mirroring how
  `chat`/`voice`/`system` were already added in M5A) since
  `build_tool_registry()` is only ever called from inside
  `AgentOrchestrator.start()`.
- Developer Mode **Vision Status** section
  (`ui/views/developer/vision_status_view.py`, same pattern as M5A's
  Agent Trace) and a real **Vision** Settings page
  (`ui/dialogs/settings_pages/vision_page.py`, replacing the
  pre-existing placeholder) exposing the two `enabled` toggles —
  clearly labelled "unavailable / not yet implemented," no runtime
  effect beyond persisting the preference.
- `core/di/container.py` — `vision_provider`, `ocr_provider`,
  `vision_service` registered as Singletons; `vision=vision_service`
  threaded into the existing `agent_orchestrator` Singleton.

**Dependencies:** M5A (the Vision Agent Tool is exposed the same way
every other M5A tool is — through `agents/tools/registry.py`).

**Complexity:** M *(as scoped — this pass delivered the abstraction
layer only; complexity for the full feature set, if resumed as a
separate pass, would need its own review once real capture/OCR
dependencies are approved)*.

**Not delivered — remains future work, still under M6's original
scope:**
- Vision AI (screenshot/UI/chart/code/document understanding)
- OCR execution (`pytesseract`/PaddleOCR adapters)
- Screenshot capture (`mss`) and camera capture (`opencv`)
- Clipboard image support and drag-&-drop image input in chat
- Image Question Answering in chat
- Image preprocessing, compression, and bounded temp storage
- Vision Memory (image-derived facts into `MemoryService`)
- Multimodal messages in `ChatService` (`ChatMessage.content` is
  still `str`-only — Phase 1's architecture review flagged this exact
  fork-in-the-road decision as unresolved, deliberately, pending real
  requirements)
- Real provider implementations for any of the above

**Files / modules touched:** 20 created, 15 modified (interfaces,
settings, infrastructure adapters ×6, service, events, agent
tools/registry/orchestrator, DI container, Developer Mode view,
Settings page, plus the pre-existing dashboard section-count test's
required update, plus this delivery/changelog/roadmap/version-string
documentation pass).

**Tests:** 92 new tests added across 7 phases (interfaces 17,
settings 13, mock providers 15, service 16, agent tool + orchestrator
wiring 13, Developer Mode view 8, Settings page 10), all passing; full
regression suite reconfirmed after every phase and again at
milestone close — 100% pass, zero new failures, the same one
pre-existing `pytest-aiohttp`-environment gap as M5A (unrelated,
undisturbed).

**Still open:** everything in "Not delivered" above, plus: §16's
Recommended Development Order table still lists M6 in its future-work
rationale list (that table's own docstring notes it exists to explain
*why* an order was chosen, not to be re-derived) — left as-is rather
than risk an error-prone mass renumbering of every milestone after it
for a documentation-only finalization pass; flagged here as minor,
optional follow-up cleanup, not a functional gap.

**Architecture Evolution**

Introduced in this milestone: `IVisionProvider`/`IOCRProvider` ports,
`VisionService`, the `vision_status` agent tool, and
`VisionProviderStatusEvent`.

Later reused by: no later milestone yet — M7 Phase 1's domain models
(`WorkflowStep`, `ScheduleDefinition`) are vision-agnostic and don't
reference this layer, and M7 Phase 2 only touched
`features/automation/executor.py`. This abstraction layer is built and
tested but currently awaits either M6's own deferred feature phases or
a future milestone to build on top of it — recorded here as fact, not
projected reuse.

---

## 4. Engineering standards

Permanent, cross-cutting standards that apply to **every** milestone,
past and future — not repeated per milestone entry below.

- **Backward compatibility.** A milestone may extend the public
  surface (new services, new interfaces, new settings) but must never
  silently break an existing one. Breaking changes go through a
  deprecation window (old path kept, marked deprecated, removed no
  sooner than the following milestone) unless the change is itself a
  security fix.
- **Clean Architecture.** Strict layering — `ui → features → services
  → agents → core.interfaces`, `infrastructure → core.interfaces` —
  enforced by convention today (see §11 for the automated-enforcement
  plan). No layer imports "up" or sideways into another feature's
  internals.
- **MVVM for every UI surface.** Views own no business logic;
  controllers (ViewModels) bridge services to Qt signals; services own
  no Qt imports. Every new feature slice follows
  `features/<name>/controller.py` fronting a plain-Python service.
- **Dependency Injection everywhere.** New adapters and services
  register in `core/di/container.py` — no service ever imports a
  concrete adapter class directly, only its port.
- **Event Bus for cross-cutting notifications.** State changes another
  layer needs to react to (voice state, automation steps, update
  phases, agent steps) are `EventBus` events, not direct callbacks
  across layer boundaries.
- **Provider abstraction ("ports and adapters") at every external
  boundary.** LLMs, STT/TTS, vector stores, databases, browsers, OS
  automation, and (from M6 onward) vision/OCR are all abstract
  interfaces in `core/interfaces` first, concrete adapters second.
- **SOLID principles**, DRY, explicit typing (`mypy --strict` — see
  §5), modular design — one responsibility per class/module.
- **Test coverage never regresses.** A milestone that reduces the
  passing test count, or removes a test without replacing its
  coverage, does not ship. Every new port ships with a fake in
  `tests/fakes/` (see §5).
- **Documentation updates ship with the milestone, not after.** This
  roadmap (§3/§8/§10 as applicable), the milestone's own delivery
  doc, and `CHANGELOG.md` are all updated in the same change that
  ships the feature.
- **CHANGELOG discipline.** Every shipped milestone gets a
  `## [x.y.z]` entry in `CHANGELOG.md` the same day it ships, not
  batched later.
- **Architecture diagrams stay current.** The ASCII diagrams in §11
  and in `ARCHITECTURE.md` are updated whenever a layer gains a new
  component category (not on every individual class addition).
- **Module Logic Contract.** *(Added Aug 2026 as part of the roadmap
  architecture review — see the changelog addendum.)* Every module,
  frontend or backend, must have its Logic Contract written and
  reviewed before implementation begins. A Logic Contract defines:
  Purpose, Responsibilities, Business Logic, Inputs, Outputs,
  Dependencies, Permission Model, State Machine, Validation Rules,
  Failure Behaviour, Recovery Behaviour, Logging, Telemetry, Events,
  Tests, and Acceptance Criteria. This formalizes a practice this
  roadmap's milestone entries already follow informally (every
  milestone's own Objective/Dependencies/Acceptance Criteria
  breakdown) — the Logic Contract is that same discipline applied at
  the individual-module level, in `ARCHITECTURE.md`'s Module Manifest
  spec (§10) or the module's own design doc, not restated in this
  roadmap. **No implementation may begin until its module's Logic
  Contract is complete.**

---

## 5. Validation gate

Every milestone — without exception — passes through this gate before
it is considered done. This is the concrete, repeatable process; see
[`AUDIT_REPORT_M5-AGENTS.md`](../AUDIT_REPORT_M5-AGENTS.md) for a
worked example of the gate catching a real bug (`aiosqlite`
incompatibility) that unit tests alone had missed.

1. **Install dependencies.** `pip install -e ".[dev]"` into a clean
   environment. Do not silently ignore installation failures or
   dependency-resolution conflicts — resolve them before proceeding.
2. **Run Ruff.** `ruff check src tests`. Fix findings in the files the
   milestone touched; pre-existing findings in untouched files are
   tracked in §15, not silently absorbed into the milestone's diff.
3. **Run Black.** `black --check src tests`. Same scoping rule as
   Ruff.
4. **Run MyPy.** `mypy src` (strict, per `pyproject.toml`). Same
   scoping rule — except a milestone *is* responsible for fixing a
   pre-existing type error in a file it makes newly reachable for the
   first time (e.g. a stub interface whose mismatch was invisible
   until a real implementation existed — see the `IAgentOrchestrator.stream`
   fix in M5A for a worked example).
5. **Run Pytest.** Full suite (`pytest`), not just the new milestone's
   own tests — a milestone can silently break another one's tests via
   shared DI wiring, shutdown-hook ordering, or UI section counts (as
   M5A did to two pre-existing M5 tests, both fixed as part of the
   same milestone).
6. **Fix failures.** Root-cause every failure or error before
   re-running — do not skip, do not mark `xfail` to make the suite
   green artificially. Distinguish real regressions (fix the new
   code) from pre-existing tests whose hardcoded expectations the
   milestone correctly changed (update the test, note why).
7. **Re-run tests** after every fix, then **re-run the complete
   suite** once more before considering the gate passed.
8. **Verify documentation.** This roadmap, the milestone's delivery
   doc, and `CHANGELOG.md` all describe reality, not aspiration —
   re-read them against the actual shipped code, not against the plan
   written before the milestone started.
9. **Merge only after all tests pass** and the milestone's own
   acceptance criteria (defined in its §8 entry) are met — partial
   credit is recorded honestly (🟡) rather than rounded up to ✅.

**A milestone that finds real bugs during this gate is not a failed
milestone** — it's the gate doing its job. Fix the bug, add a
regression test that would have caught it, document the root cause
(not just the symptom), and continue.

---

## 6. Versioning policy

JARVIS OS follows a **milestone-driven**, not calendar-driven,
semantic-versioning scheme:

- **MAJOR (`x.0.0`)** — reserved for `1.0.0`, the M24 Production
  Release milestone (see §8), and for any future breaking change to
  the public plugin/agent-tool API surface after that.
- **MINOR (`0.x.0`)** — bumped exactly once per completed top-level
  milestone (`M6`, `M7`, `M8`, … including lettered companion
  milestones like `M11A`, which get their own minor bump, not a patch
  of their parent). See §14 for the full mapping.
- **PATCH (`0.x.y`)** — reserved for out-of-band fixes shipped
  between milestones (a fix urgent enough not to wait for the next
  milestone's minor bump) and for stabilization passes in the style
  of M5.5, which do not themselves earn a minor bump since they ship
  no new feature.

**Worked example** (the pattern requested for this document):
```
0.4.0  →  0.5.0  →  0.6.0  →  0.7.0  →  ...  →  1.0.0
 M5A        M6        M7        M8              M24
```

**Rules:**
- A version bump happens when a milestone's acceptance criteria pass
  the [Validation gate](#5-validation-gate) — never on a fixed
  calendar date.
- `pyproject.toml`, `src/jarvis/__version__.py`, and
  `Settings.app_version` must always agree — a CI check enforcing this
  is tracked as technical debt (§15) until M24's CI workflow lands.
- A milestone that ships **zero** new user-visible features (an audit
  pass, a dependency-pin fix, a pre-merge validation pass) does not
  bump the minor version — it's recorded as a `PATCH` or folded into
  the `CHANGELOG.md` entry of the milestone it validates, exactly as
  M5.5 and the M5A pre-merge validation pass were handled.

---

## 7. Cross-platform systems

Some capabilities don't belong to a single milestone — they evolve
continuously, touched by nearly every future milestone in some way.
Tracking them here (instead of duplicating "also update the AI
provider list" into every milestone's feature bullet list) is how this
document avoids the exact kind of duplication this reorganization was
asked to remove.

- **AI Providers** — new chat/embedding providers are added
  continuously (see §13 for the current roster and what's planned);
  no milestone "owns" provider count, every milestone that needs a
  new one adds it to §13 directly.
- **Voice pipeline quality** — wake-word engine accuracy, streaming
  STT/VAD tuning, and always-on-listening improvements (previously
  tracked as a standalone future milestone) are continuous refinements
  to the M2 Voice Platform, not a one-time deliverable — tracked in
  §10's Voice section and picked up opportunistically as other
  milestones touch the voice pipeline (M17 Companion Intelligence and
  M21 Mobile Platform are the two most likely to need real
  improvements here).
- **Observability** — logging, tracing, and the Agent Trace panel
  (M5A) grow together; M20A Analytics Platform is where this
  consolidates into a real dashboard, but structured-logging
  discipline itself is a continuous standard (§4), not a milestone.
- **Security** — every milestone that adds a new external-facing
  surface (a new provider, a new automation action, a new agent tool)
  is responsible for its own threat-modeling at build time; M14
  Security Platform is where the *cross-cutting* security
  infrastructure (keyring, audit log, encryption at rest, kill-switch)
  lands, not where all security work is deferred to.
- **Developer Mode** — every milestone that ships a new subsystem
  worth inspecting live (the way M5A shipped the Agent Trace panel)
  adds its own Developer Mode section rather than waiting for a
  dedicated "Developer Mode" milestone — there isn't one, by design.
- **Performance monitoring, metrics, cost tracking, token usage** —
  instrumented incrementally as the features that produce this data
  ship (agent runs, LLM calls, automation runs); M20A Analytics
  Platform is where it's finally surfaced as a real dashboard rather
  than scattered log lines.
- **Prompt-injection protection** — a standing concern from M5A
  onward (see the `UNTRUSTED_TOOL_OUTPUT_NOTICE` pattern in
  `agents/prompting.py`); every future milestone that adds a new
  agent tool consuming untrusted external content (web pages, OCR'd
  documents, emails) must apply the same fencing pattern, not
  reinvent it.
- **Developer tools** — the Developer Console, Module/Plugin Manager,
  and API Center (all M5) grow real backends incrementally as M9's
  Plugin Platform / Developer Platform Tools, M11's Integrations &
  Cloud Platform, and later milestones ship, rather than being
  "finished" by one milestone.
- **UI Foundation** — a design-system hardening pass (Jul 2026,
  post-M6/pre-M7-Phase-3) that upgraded the M5 desktop shell in place
  rather than shipping as its own numbered milestone: a centralized
  `Typography` scale (`ui/themes/typography.py`, sizes 32/24/20/18/16/
  14/12px, weights 400/500/600/700 only) backed by a real bundled
  Inter font (`resources/fonts/`, loaded via `QFontDatabase` in
  `ui/themes/fonts.py`); an `IconRegistry`-based SVG icon system
  (`ui/components/icons.py`) vendoring 84 Lucide icons
  (`resources/icons/`, ISC-licensed) with theme-aware `currentColor`
  recoloring, replacing emoji glyphs across the app's own UI code
  (mock-data providers were deliberately left untouched — see M5's
  "still open" note on mock providers); and a pure-logic UI State
  Machine Foundation (`domain/app_state/`) — `ConnectionState`,
  `ModuleState`, `ModuleStateMachine` — establishing the lifecycle
  contract every future module's Service Layer (Gmail, Spotify,
  Calendar, Smart Home, and the rest) is expected to build on. This is
  **not** part of M7 — M7 is Workflow Intelligence (§8, below) and
  this work shares no domain model or acceptance criteria with it —
  and it is **not itself a completed milestone**: it shipped no new
  service, provider, or user-facing module, only the typography,
  icon, and state-machine substrate later milestones' UI work is
  expected to consume. No later milestone has wired a real service
  through `ModuleStateMachine` yet; it is logic-only, unit-tested, and
  currently unconsumed outside its own test suite.
  **Frontend migration note (Aug 2026):** the Qt-specific rendering
  half of this pass (`QFontDatabase` font loading, `QSvgRenderer`/
  `QPainter`-based icon recoloring, QSS theme files) is superseded by
  M8's React + Tauri rebuild (see `TECH_STACK.md`) and is not carried
  forward as code. The design decisions this pass made — the
  Typography scale's exact values, the Lucide icon set, and the
  `ModuleStateMachine` lifecycle contract's shape — do carry forward:
  M8's Phase 1 (React Foundation) ports the same token values into
  Tailwind config, the same vendored Lucide SVGs into the React icon
  set, and M8's Phase 2 (Universal Application Framework) ports the
  same state-machine contract into TypeScript rather than redesigning
  it. This module's own `ui/themes/typography.py`,
  `ui/components/icons.py`, and `domain/app_state/` code remains
  exactly as shipped and untouched by this note.

---

## 8. Future roadmap

Every milestone below lists: **Objective**, **Key features**,
**Dependencies**, **Complexity** (T-shirt size: S/M/L/XL), and
**Acceptance criteria**. Lettered companion milestones (`M11A`,
`M13A`, `M14A`, `M17A`, `M20A`, `M23A`, `M23B`) are scoped narrowly on
purpose — each is a focused extension of its numeric parent,
schedulable independently once the parent milestone is stable, exactly
like `M5A` was a focused extension unlocked by `M3`/`M4` rather than a
dependency of the `M5` UI work. `M23A` and `M23B` are the two
exceptions to "extension of its numeric parent": `M23A` is a standalone
hardware abstraction platform, and `M23B` is a standalone autonomous
planning/decision platform, both placed alongside `M23` in the
sequence — immediately before `M24 — Production Release` — rather than
narrowly extending `M23 — Distributed JARVIS`'s own scope. See each
milestone's own entry for the full rationale.

*(M6 — Vision & Multimodal shipped its Architecture Layer Jul 2026 and
has moved to §3 Completed Milestones — see that entry for the full
scope note on what shipped vs. what remains future work. Kept out of
this section, consistent with how M0–M5A are listed only in §3, never
duplicated here.)*

### M7 — Workflow Intelligence

**Objective:** grow the M5A agent runtime from "one prompt, one graph
run" into a real workflow engine — parallel execution, durable task
planning, and user-authored automation.

**Key features:**
- Advanced Agent Runtime — the graph gains real parallel branches
  (closes the M4 "steps still execute sequentially" gap using
  `asyncio.gather`-based execution where the planner marks steps
  independent).
- Task Planning — multi-turn plans that persist across a session, not
  just within one `invoke()` call.
- Workflow Builder — a visual/declarative way to author a fixed
  sequence of agent + automation steps, built on the existing
  `RecipeManager` (M4) rather than replacing it.
- Macro Engine — user-recordable shortcuts for repeated automation
  sequences.
- Automation Recorder — "watch me do this once, then do it for me" —
  the natural successor to M4's manual `RecipeManager` authoring.
- Scheduler — cron-style recurring agent/automation runs (e.g. "check
  my inbox every morning at 8").

**Dependencies:** M5A (agent graph), M4 (automation actions the
workflow engine orchestrates).

**Complexity:** L.

**Acceptance criteria:**
1. A workflow with two independent steps measurably runs them in
   parallel, not sequentially.
2. A recorded macro can be replayed without re-authoring it by hand.
3. A scheduled workflow fires unattended and its result is visible in
   the Agent Trace panel.

**Implementation status (2026-08-01) — M7 is in progress, not
complete.** Six phases were scoped; two have shipped, one is
deliberately deferred, three are pending. Grouped by disposition:

- **Completed:**
  - Phase 1 (Domain Foundation) — `WorkflowDefinition` / `WorkflowStep`
    / `ScheduleDefinition` domain models, `AutomationSettings.max_parallel_steps`
    / `AgentSettings.max_parallel_steps` / `SchedulerSettings`,
    `WorkflowStepEvent` / `ScheduledJobFiredEvent`. 21 dedicated tests.
    Domain-only by design — no scheduler, executor, or LangGraph
    wiring for these models exists yet (that's Phases 4–6, below).
  - Phase 2 (Parallel Automation Execution) — `ActionExecutor`
    rewritten for wave-based dispatch using the pre-existing
    `Step.depends_on` / `gather_with_concurrency()`, with rollback and
    `PermissionGate` serialization preserved under concurrency. 11
    dedicated tests, measured (not estimated) parallel-vs-sequential
    speedup.
- **Deferred:**
  - Phase 3 (Structured Graph Planning) — would extend `AgentState` /
    `planner.py` / `tool_executor.py` / `graph.py` for cross-tool
    parallelism inside the agent runtime itself. Explicitly deferred
    pending its own separate approval per the original phase plan;
    not started.
- **Pending** (paused after Phase 2, not resumed until the UI overhaul
  work in §7's "UI Foundation" has been reviewed and approved):
  - Phase 4 — Workflow Builder (a visual/declarative authoring surface
    on top of the existing `RecipeManager`, M4).
  - Phase 5 — Recorder (Macro Engine / Automation Recorder).
  - Phase 6 — Scheduler (cron-style recurring agent/automation runs).

**Acceptance criteria status:**
1. *A workflow with two independent steps measurably runs them in
   parallel, not sequentially* — ✅ **Met**, by Phase 2.
2. *A recorded macro can be replayed without re-authoring it by hand*
   — ❌ **Not met** — Phase 5 (Recorder) is pending.
3. *A scheduled workflow fires unattended and its result is visible in
   the Agent Trace panel* — ❌ **Not met** — Phase 6 (Scheduler) is
   pending, and no workflow-to-Agent-Trace wiring exists yet.

Per §6's versioning policy, an in-progress/paused milestone doesn't
bump the version or earn its own `CHANGELOG.md` entry yet — that lands
when M7 actually completes, not before.

### M8 — React Frontend & Desktop Experience

*(Retitled Aug 2026 from "Plugin Platform" as part of the frontend
technology migration to React + Tauri — see `TECH_STACK.md` and the
changelog addendum at the end of this document for what changed and
why. Plugin Platform's own scope — SDK, Loader, Extension API,
Permission Model, Store, Marketplace — is preserved in full, not
dropped: it now lives under M9's expanded Runtime & Core Services
scope, below, since a plugin loader is a backend runtime concern, not
a frontend one. Nothing about the plugin system's design changed —
only which milestone number owns it.)*

**Objective:** rebuild JARVIS's entire user-facing surface on React +
Tauri, replacing the PySide6 desktop shell M5 delivered, feature by
feature, on the technology decision in `TECH_STACK.md`. This is a UI
rendering-technology migration, not a product redesign — every
screen, workspace, and Developer Mode panel M5 shipped gets a React
equivalent with the same functional scope before any new capability is
added on top. See `IMPLEMENTATION_ROADMAP.md` for the active,
checkbox-level execution plan this section summarizes.

**Key features** *(organized into 7 phases — see
`IMPLEMENTATION_ROADMAP.md` for the full checklist per phase)*:

#### Phase 1 — React Foundation
React 19, TypeScript, Vite, Tauri, Tailwind CSS, shadcn/ui, Radix UI,
Motion, Lucide Icons, React Router, Zustand, TanStack Query, React
Hook Form, Zod, the Inter font, design tokens, a Theme Engine
equivalent to M5's, and a base component library. Full technology
rationale in `TECH_STACK.md`.

#### Phase 2 — Universal Application Framework & Logic
The mandatory shape every application in the new frontend follows:
Business Logic → State Machine → Service Layer → React Hooks → State
Store → Authentication → Permissions → Storage → Settings → API Layer
→ Voice Integration → AI Integration → Automation Integration →
Offline Support → Error Handling. Ports the §7 UI Foundation's
`ModuleStateMachine` lifecycle contract into TypeScript rather than
redesigning it (see §7's own frontend migration note). **No fake
data** — every screen renders a real value, a real loading state, or a
real empty state; never a placeholder dressed up to look real.

#### Phase 3 — Desktop Workspace
Dashboard, Sidebar, Dock, Workspace views (one per M5 workspace:
Voice, Files & Drive, Browser, Coding, Finance, Smart Home, Calendar,
Gmail, Spotify), Window Management, Command Palette, Responsive
Layout, DPI Scaling, Multi-Monitor support.

**Dynamic Sidebar & Dashboard Widget Grid** *(added Aug 2026 per the
UI Architecture Update review — see the changelog addendum)*: both
are registry- and enablement-driven, not a fixed list rendered by
hand — Core JARVIS requires no code change when a new module or
plugin registers.

- **Dynamic Sidebar.** Renders only modules that are both
  *registered* (`ApplicationRegistry`) and *enabled*
  (`ModuleEnablementStore`, new) — "installed and enabled" in product
  terms. A **minimal default core set** ships enabled and cannot be
  disabled: Dashboard, AI (a nested group — Conversation, Voice,
  Memory), Automation, Files, Settings. Every other module (Browser,
  Coding, Finance, Smart Home, Calendar, Gmail, Spotify today; SEO,
  SEM, Vision, and any future plugin tomorrow) ships **disabled by
  default** and appears only once the user turns it on (Settings →
  Plugins, Phase 5 below) — never a permanent slot for a module the
  user hasn't opted into. `ModuleManifest` gains `isCore` (this fixed
  set only) and an optional `parentGroup` (how "AI" nests its three
  children) — both are manifest *data*, so Sidebar's own code stays
  generic regardless of how many modules exist.
- **Dashboard Widget Grid.** The Dashboard is a customizable widget
  grid, not a single static view — shipped in Aug 2026's Task Group F
  (see the changelog addendum). Built-in system widgets ship with Core
  JARVIS: **Notifications, Recent Activity, Quick Actions, System
  Status** ship real, each backed by an actual store/hook (the
  notification center, background task tracking, real navigation
  links, and the real WebSocket connection status respectively) — no
  fabricated content. **Tasks, Calendar, and Notes do not ship yet**:
  no real backing feature exists anywhere in the codebase for any of
  the three, and a widget with a title but no real feature behind it
  would be exactly the fake implementation this project's standing "no
  fake data" rule forbids. Each becomes a real Dashboard widget once
  its own feature ships (Tasks/Notes most naturally under M11B
  Productivity Suite; Calendar once real Google Workspace/OAuth data
  exists per M11) — `DashboardWidgetRegistry` places no cap on widget
  count, so this is additive, not a rework. Everything else (Gmail,
  Slack, Spotify, GitHub, an SEO Dashboard, Home Assistant, a
  Portfolio widget, and any future plugin's own) registers through
  `DashboardWidgetRegistry` (mirrors `ApplicationRegistry`'s own
  pattern, and is itself one named `ContributionRegistry` instance
  alongside Navigation and Status Bar — see the Task Group D/E
  addendum below) — the same extension point every other plugin
  surface uses (M9's expanded Plugin Registration System, below), not
  a Core-JARVIS-maintained special case per widget. Users can add,
  remove, resize (through 4 fixed grid footprints, not free-form
  drag), move, and pin widgets, and export/import their layout as one
  JSON document.

Both are fully shipped as of the Task Group F addendum below — real
third-party plugin *code loading* remains M9's Plugin Loader, below,
unchanged by this addendum.

#### Phase 4 — Voice Experience & Motion
Removes the Orb (a standing instruction from the earlier PySide6-era
UI overhaul brief, never carried out there — satisfied by construction
here, since the React frontend never had one to begin with). Replaces
it with **Voice String** *(shipped Aug 2026, Task Group H, revised
same month to a real-time multi-bar renderer — renamed from "Voice
Waveform" per the Premium UI & Voice Experience brief; same role)*: a
glassmorphism panel of 40 independently-animated bars whose color,
amplitude, and per-state envelope shape communicate state (Idle/Wake/
Listening/Thinking/Speaking/Success/Error) — no visible state label
ever renders. The renderer (`components/voice/voice-waveform-
renderer.tsx`) is pure — no store dependency, accepts `voiceState`,
`microphoneLevel`, `ttsLevel`, and `intensity` as props — so a future
voice backend streams real audio amplitudes into it with zero renderer
changes; `voice-string.tsx` is the thin layer wiring real store state
in. Backed by a real, validated state machine
(`core/voice-state-machine.ts`, mirrors `core/module-lifecycle.ts`'s
pattern) and source-of-truth stores (`stores/voice-state.store.ts`,
`stores/voice-audio-levels.store.ts`) that start and stay at rest,
since no real voice backend exists yet — never a cosmetic animation
with no backing state. Developer Mode's Voice State Preview panel can
manually drive or auto-cycle the real state store, plus manual sliders
for mic/TTS level and intensity, for full animation QA (disabled by
default, never an end-user surface). Live Transcript (word-by-word,
fades after inactivity) ships alongside it, honestly empty until a
real STT stream exists.

**Startup Experience** *(shipped Aug 2026, Task Group I — see the
changelog addendum)*: a choreographed ~4.2s cinematic sequence (energy
point, ripple, logo assembly/pulse, morph into the real Voice String,
Voice String activation and expansion, center-outward glass reveal)
replaces a bare loading flash, reusing the existing Voice String as its
centerpiece rather than building a second one. No startup text ever
renders. Genuinely lazy-registers the app's own real startup work
(`core/startup-orchestrator.ts`) behind the choreography, gated so the
dashboard only reveals once both the animation and the real work are
done. Respects a persisted skip preference and `prefers-reduced-motion`
alike — either launches straight into the dashboard.

**Glass design system** *(shipped Aug 2026, Task Group J — see the
changelog addendum)*: real glassmorphism (translucency +
`backdrop-filter` blur) on the three surfaces the brief names —
Sidebar, the shared Card primitive, and Command Palette — plus a
subtle ambient glow behind `DesktopShell` so those blurs have real
content behind them. Every surface offers a solid, non-blurred
fallback, all reading from the same real `disableGlassEffects`
preference Task Group I already shipped — now genuinely app-wide
rather than scoped to the startup sequence alone.

**Accessibility settings** *(shipped Aug 2026, Task Group K — see the
changelog addendum)*: a real Settings > Accessibility page
(`features/settings/settings-page.tsx`) exposing Skip startup
animation, Reduced motion, and Disable glass effects as working
toggles outside Developer Mode for the first time. The backing store
(`stores/startup-preferences.store.ts`) was renamed to
`accessibility-preferences.store.ts` now that it backs real, app-wide
UI rather than just the startup sequence, and gained a genuine third
preference — `reducedMotion`, an app-level override on top of
`prefers-reduced-motion` — wired into `MotionConfig` so every
declarative Motion animation in the app respects it.

**Dashboard widget drag-and-drop** *(shipped Aug 2026, Task Group L —
see the changelog addendum)*: real, mouse-driven drag-to-reorder for
Dashboard widgets, additive alongside the existing Move up/down
buttons — built on `motion/react`'s own `Reorder.Group`/`Reorder.Item`
(already a dependency, no new drag library added). This closes the
Premium UI & Voice Experience initiative's five task groups (H–L).
Conversation Timeline and the broader motion pass (hover, Sidebar,
Dock, Cards, Notifications) remain pending.

#### Phase 5 — Settings & User Profiles
Dynamic Settings (schema-driven, preserving M5's self-registering
Settings-page pattern), Developer Mode (ports M5's full gated panel
set), Profile Service, Guest Mode, Profile Switching, Profile Storage.

**Settings page structure** *(added Aug 2026 per the UI Architecture
Update review — see the changelog addendum)*: General, Appearance,
Voice, AI Models, Memory, Automation, Devices, Accounts, **Plugins**,
Security, Developer Mode, Backup & Restore, About — the concrete page
list Dynamic Settings' self-registering pattern renders. **Plugins**
here is the user-facing enable/disable surface for already-registered
modules (reads/writes Phase 3's `ModuleEnablementStore` — a simple,
reversible toggle, no install/uninstall) — distinct from Developer
Mode's existing Plugin Manager panel, which is the gated browse/
install/uninstall experience over M9's Marketplace. A module can be
*installed* (Marketplace, Developer Mode, privileged) without being
*enabled* (this page, unprivileged, reversible any time) — the two
states Phase 3's "installed and enabled" sidebar/dashboard rule
depends on.

#### Phase 6 — Premium UI Polish
Spacing, Typography, Cards, Animations, and Icons audited against the
design-token scale; a production-quality pass across every view built
in Phases 1–5.

#### Phase 7 — Optimization & QA
Accessibility, performance, lazy loading, bundle optimization,
responsive testing, regression testing, cross-platform testing. See
`TECH_STACK.md` §6 for the testing-tool assignment (Vitest, React
Testing Library, Playwright).

#### Deferred Backlog *(Aug 2026 — added by the roadmap reconciliation
pass, see the changelog addendum)*

Non-blocking work explicitly deferred out of M8's active scope so M9
could proceed — real, tracked, and not silently dropped, but not
required for any milestone beyond M8 itself. Nothing here blocks M9's
Runtime Core, Reliability, Plugin Platform, or Developer Platform
Tools modules (see `IMPLEMENTATION_ROADMAP.md` §5's own Dependencies
note). Full checklist-level detail lives in
`IMPLEMENTATION_ROADMAP.md`'s own Deferred Backlog section — this is
the summary:

- **Notification Center** (Phase 3) — the persistent panel view over
  `core/notification-framework.ts`'s already-real data.
  `components/layout/notification-layer.tsx` is a reserved,
  intentionally-empty anchor point (`return null`) — distinct from the
  ephemeral toast surface (`providers/notification-provider.tsx`'s
  `<Toaster />`), which already ships and is not part of this backlog
  item.
- **Context Menu system** (Phase 3) — a reusable, registry-driven
  right-click menu system for Sidebar/Dock/Workspace items.
  `components/ui/context-menu.tsx` is only the shadcn/ui primitive
  (Phase 1); `components/layout/context-menu-layer.tsx` is the
  reserved, intentionally-empty anchor point for the real system.
- **Background Task Manager** (Phase 3 / M9 Task Group C overlap) — a
  real supervised task queue. `stores/background-tasks.store.ts`
  exists only as a lightweight display store backing the Status Bar's
  "Background Task Progress" item, not a real manager — the real
  manager is M9 Task Group C's own Reliability-module deliverable, not
  a second, competing frontend-only implementation.
- **Workspace views** (Phase 3) — Voice, Files & Drive, Browser,
  Coding, Finance, Smart Home, Calendar, Gmail, Spotify — one React
  view per existing PySide6 workspace, not yet ported.
- **Window management** (Phase 3) — Tauri window APIs.
- **Responsive layout, DPI scaling, multi-monitor support** (Phase 3).
- **Settings & User Profiles** (Phase 5, in full) — Dynamic Settings,
  the full Developer Mode panel port, API Center UI + Developer API
  Analytics, Profile Service, Guest Mode, Profile Switching, Profile
  Storage.
- **Developer Mode's 9 read-only viewers** (Phase 5) — Module Manager,
  Plugin Manager, API Center, Update Center, Developer Console,
  Security Center, Backup/Restore, System Information, Performance
  Monitor. Only the Developer Mode shell
  (`features/developer/developer-panel.tsx`) and the Module State
  Inspector, Startup Preview, and Voice State Preview panels exist
  today.
- **Premium UI Polish** (Phase 6, in full) — spacing/typography/cards/
  animations/icons audit, production-quality pass across every view.
- **Conversation Timeline** and the **broader motion pass** (hover,
  Sidebar, Dock, Cards, Notifications) — Phase 4 items explicitly
  called out as still pending in that phase's own entry above.
- **Optimization & QA** (Phase 7, in full) — accessibility audit,
  performance pass, lazy loading, bundle optimization, responsive/
  cross-platform testing.

**Backend counterpart work** *(not this milestone's own scope, but
required alongside it — see `IMPLEMENTATION_ROADMAP.md` §3)*: FastAPI
routers + WebSocket handlers exposing the existing `services →
agents → core.interfaces` layers this frontend consumes. No
`services`, `agents`, `domain`, or `infrastructure` code changes shape
— only a new HTTP/WebSocket-facing adapter, the same way every
existing port already has a concrete adapter.

**Dependencies:** M0–M7 (every backend service this frontend renders
must already be real — unchanged from the original Plugin Platform's
own dependency reasoning, now applied to the frontend as a whole
rather than to a plugin surface specifically).

**Complexity:** XL *(a full frontend-technology migration across every
screen M5 shipped, not an incremental feature — sized consistently
with this roadmap's other XL "platform" milestones)*.

**Acceptance criteria:**
1. Every workspace, Dashboard, and Developer Mode panel M5 shipped has
   a React equivalent with matching functional scope.
2. No screen renders fake, simulated, or placeholder data — every
   value traces to a real FastAPI/WebSocket response, a real loading
   state, or a real empty state.
3. The Orb no longer exists anywhere in the shipped UI; the Voice
   Waveform is its sole replacement.
4. The full Vitest + React Testing Library + Playwright suite passes,
   and the existing Python backend's pytest suite remains unaffected
   (zero regressions in either).

### M9 — Runtime & Core Services

*(Retitled Aug 2026 from "Integration Platform" as part of the
frontend technology migration — see `TECH_STACK.md` and the changelog
addendum at the end of this document. Integration Platform's own scope
— API Gateway, OAuth, API Manager, Webhooks, Queue, Retry Policies,
Caching, Monitoring — is preserved in full, not dropped: it now lives
under the new M11 Integrations & Cloud Platform, below, since
outbound/inbound external-API governance is an integrations concern,
not a core-runtime one. The old M8 Plugin Platform's full scope — SDK,
Loader, Extension API, Permission Model, Store, Marketplace — moves
here instead, since a plugin loader is squarely a runtime/service
concern. Nothing about either milestone's design changed — only which
number owns which piece.)*

**Objective:** the backend runtime layer every other Python-side
service, and now every plugin, runs on top of — application lifecycle,
service management, health, and resource governance — plus the
plugin system this milestone inherits from the original M8. This is
the layer M8's FastAPI routers call into, and the layer a plugin's
`IPlugin` lifecycle hooks run inside.

**Key features** *(organized into 4 modules)*:

#### Runtime Core
- **Runtime Manager** *(shipped Aug 2026, Task Group A — see the
  changelog addendum)* — process/service startup and shutdown
  ordering. `RuntimeManager` (`core.lifecycle.runtime_manager`,
  renamed from the M5.5 stabilization pass's `ShutdownManager`) is now
  the single place every subsystem registers a lifecycle hook, in
  either direction, not just a cleanup one — `app.py`'s two best-effort
  startup steps (memory-policy enforcement, Whisper preload) register
  as real startup hooks instead of hand-written `try`/`except` blocks,
  mirroring exactly how `MainWindow`'s shutdown hooks already worked.
- **Application Lifecycle** *(shipped Aug 2026 — Task Group A's
  `AppReadyEvent`/`ShutdownRequestedEvent`; Task Group B added
  `RuntimeStartedEvent`/`RuntimeShutdownCompleteEvent`, see the
  changelog addendum)* — cold-start, ready, and shutting-down states
  are real, published on the existing `EventBus`, and now genuinely
  exposed over WebSocket to M8's frontend (`runtime.started`,
  `runtime.ready`, `runtime.stopping`, `runtime.shutdown` — see Runtime
  WebSocket API below) instead of a spinner with no backing signal.
- **Service Manager** *(shipped Aug 2026, Task Group B)* —
  `ServiceManager` (`core.lifecycle.service_manager`): a real registry,
  built on the existing `core/di/container.py` rather than a second
  one, with dependency-ordered startup/shutdown, restart, and health
  polling. Wraps a curated, conflict-free set of services in thin
  `IService` adapters (`ConversationService`, `ChatService`,
  `MemoryService`, `ThemeService`) — `VoiceService`/`HotkeyService` stay
  under `MainWindow`'s existing shutdown-hook ownership (avoiding two
  competing lifecycle owners for the same resource) and the DI
  `Factory`-provided services (`BrowserService`/`AutomationService`/
  `SystemService`) have no stable identity a registry could poll;
  retrofitting every remaining service onto `IService` is real future
  work, not this task group's (see §15).
- **Session Manager** *(shipped Aug 2026, Task Group B)* —
  `SessionManager` (`core.lifecycle.session_manager`): one runtime
  session per connected client, persisted (`runtime_sessions` table,
  `infrastructure/database/models.py`) so an unclean shutdown's
  dangling sessions are found and closed out on the next boot. Deliber-
  ately its own id space rather than reusing `Conversation.id` or the
  agent orchestrator's LangGraph `thread_id` — both stay optional,
  nullable references on the session row instead of being forced
  together or left with no link at all. Backs the
  `Depends(get_current_session)` mechanism §5/§6 reference, via
  `POST /api/v1/sessions`.
- **Configuration Manager** *(shipped Aug 2026, Task Group B)* — the
  existing `pydantic-settings` configuration layer, now with a real
  live-reload path (`ConfigurationManager.reload()`,
  `core.lifecycle.configuration_manager`) restricted to a curated
  `SAFE_RELOAD_SECTIONS` allowlist (`ui`, `voice_announce`, `memory`,
  `update`, `dev_mode`) — every provider credential/`enabled` field
  stays immutable startup configuration, matching
  `SettingsService`'s own pre-existing "no in-flight DI re-wiring"
  design. Composes on top of `SettingsService` rather than replacing
  it — `SettingsService` answers what the user can persist for next
  launch, `ConfigurationManager` answers what can change right now.
- **Runtime WebSocket API** *(shipped Aug 2026, Task Group B)* — the
  first real implementation of §6's documented WebSocket standard:
  `/api/v1/ws`, envelope/heartbeat/resume-with-60s-replay-buffer, all
  exactly as specified. Relays eleven events across the five managers
  above (`runtime.started/ready/stopping/shutdown`,
  `service.started/stopped/failed`, `configuration.updated`,
  `session.created/closed`, `health.updated`) — a thin relay of
  `EventBus` events (`RuntimeWebSocketHub`,
  `core.lifecycle.runtime_ws_hub`), not a second event system.
  Authenticated via a `SessionManager` session id as the `token` query
  param — M14's full Bearer/JWT session-token issuance layers on top of
  this same contract later, not a placeholder token scheme.
- Dependency Injection — the existing `core/di/container.py`; this
  module owns its continued evolution (e.g. the accepted-debt
  `PLC0415` lazy-import pattern noted in §15) rather than introducing
  a second DI mechanism.

#### Reliability *(✅ shipped Aug 2026, Task Groups B+C — see the
changelog addendum)*
- **Health Monitor** *(foundational slice shipped Aug 2026, Task Group
  B)* — `HealthMonitor` (`core.lifecycle.health_monitor`): lightweight,
  non-blocking `psutil`-based polling of process CPU/RAM/uptime,
  startup duration, active/failed services (via `ServiceManager`), and
  restart count, published as `health.updated` (see Runtime WebSocket
  API above). `register_collector()` is the extension point for GPU/
  plugin/network metrics once those exist — no collectors registered
  yet, deliberately not stubbed. Generalizes M5.5's one-time
  stabilization audit into a standing health-check surface
  (foundational; M18 Self-Healing & Diagnostics Platform later builds
  the full self-healing layer on top of this module's signals, not a
  competing one).
- **Background Task Manager** *(shipped Aug 2026, Task Group C)* —
  `BackgroundTaskManager` (`core.lifecycle.background_task_manager`): a
  bounded-concurrency (`asyncio.Semaphore`), per-task fault-isolated
  task queue for long-running non-request work (distinct from M7's
  `ActionExecutor`, which is user-triggered automation, not background
  runtime maintenance; also distinct from the frontend's `stores/
  background-tasks.store.ts`, which stays a display-only store reading
  this manager's `task.started`/`task.completed`/`task.failed` events
  over the Runtime WebSocket API rather than owning a second queue —
  see M8's Deferred Backlog). `submit()`/`cancel()`/`stop()` (graceful
  drain); a task cancelled before its coroutine's first scheduling turn
  is caught by a done-callback fallback, since Python never enters an
  unstarted coroutine's own body to run its `except CancelledError`.
- **Crash Recovery** *(shipped Aug 2026, Task Group C)* —
  `CrashRecoveryManager` (`core.lifecycle.crash_recovery`): a real
  "mark dirty at start, mark clean at end" on-disk marker
  (`runtime_state.json`, via the existing `config_dir` convention every
  other JSON-config-store service uses) detects an unclean previous
  shutdown and publishes `CrashRecoveredEvent`. Automatically
  respawning a fresh OS process after a real crash needs an external
  supervisor outside this application's own control — real, separate,
  future work, not claimed here (see this addendum's Future Work).
- **Resource Manager** *(shipped Aug 2026, Task Group C)* —
  `ResourceManager` (`core.lifecycle.resource_manager`): CPU/memory
  budget tracking, composing on `HealthMonitor` by subscribing to its
  existing `HealthUpdatedEvent` rather than polling `psutil` a second
  time. Publishes `ResourceBudgetExceededEvent` only on the transition
  into violation, not every tick a budget stays exceeded. Tracks and
  alerts only — nothing throttles or kills a service on a breach yet,
  the consumer-side counterpart to M22 Edge AI Platform's own future
  Resource Allocation module (see §15's Technical Debt "Resource
  Manager" entry). GPU/disk budgets are real, registerable
  (`register_budget()`) even though no collector publishes either
  metric yet.

#### Plugin Platform *(✅ Task Group D, shipped Aug 2026 — preserves the
original M8 scope in full; see the changelog addendum at the end of
this document for implementation detail)*
- Plugin SDK — `IPlugin` protocol, lifecycle hooks (`on_load` /
  `on_start` / `on_stop`), now running under this module's Runtime
  Manager rather than a standalone loader process.
- Plugin Loader — reads `plugins/*/manifest.json`, sandboxes with
  permission scopes (network, filesystem, hotkey, agent-tools).
- Extension API — a stable, versioned subset of services exposed via
  `PluginContext`; JARVIS refuses to load a plugin whose declared
  `sdk_version` doesn't match.
- Permission Model — declared in `manifest.json`, granted explicitly
  on install (`network`, `filesystem`, `hotkey`, `agent_tools`,
  `voice.stt`/`voice.tts`, `memory.read`/`memory.write`,
  `smart_home`, `notifications`); enforced through M14's Authorization
  Engine once that milestone ships, not a parallel permission check.
- Plugin Store — no hosted infra for v1; a signed JSON index on
  GitHub (`{name, description, author, versions[], sdk_range,
  homepage}`), community-curated via PRs.
- Marketplace — the discoverable, in-app browse/install/uninstall
  experience over the Plugin Store index; replaces M5's mock Plugin
  Manager backend with a real one, rendered by M8's React frontend.

**Plugin Safe Core Architecture** *(binding design principle, added
Aug 2026 as part of the roadmap architecture review — see the
changelog addendum)*: JARVIS Core — the services, agents, and
`core.interfaces` layers §4 already governs — is treated as
**immutable** from a plugin's perspective. Any future domain-specific
module built *after* this principle takes effect (illustrative
examples: a Children Module, Family Module, Medical Module, or
Business Module — none of these are scoped milestones today) ships as
a plugin under this section's Plugin SDK/Loader, not as a new core
service. This does **not** retroactively convert any existing,
already-scoped milestone (e.g. M12 Smart Home & IoT Platform, or the
Finance workspace tracked under M5/M11) into a plugin — that would be
a separate, explicit decision with its own migration plan, not implied
here. Requirements, extending the Permission Model bullet above:
- Plugin Isolation — a plugin's failure, exception, or resource
  exhaustion is contained to its own `IPlugin` instance.
- Version Compatibility — enforced via the existing `sdk_version`
  check (Extension API bullet above), not a new mechanism.
- Rollback Support — a failed plugin update reverts to the last-known
  good version without operator intervention.
- Crash Isolation — a plugin crash is caught by Crash Recovery (this
  milestone's Reliability module above) and does not propagate to
  Runtime Manager or any other plugin.
- Safe Disable — any plugin can be disabled at runtime without an
  application restart, leaving no orphaned hooks (Marketplace
  uninstall's existing "no orphan files or registered hooks"
  acceptance criterion, applied to disable as well as uninstall).
- Dependency Validation — a plugin declaring a dependency on another
  plugin or a core service version it's incompatible with fails to
  load, with a clear reason, rather than loading into a broken state.

**Plugin failures must never crash JARVIS Core** — the binding
acceptance test for this principle, folded into this milestone's own
acceptance criteria below.

**Plugin Registration System** *(added Aug 2026 per the UI
Architecture Update review, revised the same month once
`ContributionRegistry` shipped — see the changelog addendum)*: the
concrete list of what a plugin can register once the Plugin Loader
above actually loads it — extends the Extension API bullet with the
specific surfaces every plugin gets, rather than leaving "a stable,
versioned subset of services" undefined. Every surface below except
`ApplicationRegistry` itself (which owns module-level concerns —
dependency resolution, manifest validation — none of these need) is a
named instance of the *same* generic `ContributionRegistry` (M8 Phase
3) — one register/unregister/getAll/getByModule mechanism, not a
bespoke implementation per surface:

- Sidebar entries — via `ApplicationRegistry`/`NavigationContribution`
  (M8 Phase 2, `NavigationContribution`'s storage itself migrated onto
  `ContributionRegistry` in the same pass), the same mechanism every
  first-party module already registers navigation through; a loaded
  plugin is not a special case.
- Dashboard widgets — via `DashboardWidgetRegistry` (M8 Phase 3, Task
  Group F), a named `ContributionRegistry` instance, not a parallel
  class; Core JARVIS's own 4 built-in widgets (Notifications, Recent
  Activity, Quick Actions, System Status) register through this exact
  path.
- Status bar items — via `statusBarRegistry` (M8 Phase 3, Task Group
  E), another named `ContributionRegistry` instance; Core JARVIS's own
  9 built-in items (Current Workspace, Active Module, Current Running
  Task, Background Task Progress, AI Provider, Voice Status,
  Automation Status, Internet/Offline, Notification Indicator)
  register through this exact path, not a special case a plugin's own
  item has to work around.
- Pages / Routes — a plugin's own React route(s), mounted through
  M8 Phase 3's Workspace Routing, never a route that bypasses
  `BaseApplication`.
- Settings pages — via the Settings Framework (M8 Phase 2) and
  Dynamic Settings (M8 Phase 5); a plugin's settings schema renders
  with zero central-file edits, the same guarantee first-party
  modules get.
- Notifications — via the Notification Framework (M8 Phase 2).
- Voice commands — via the `voiceCommands` manifest field
  (`ARCHITECTURE.md` section 10) and the Voice Integration interface
  (M8 Phase 2).
- Automation actions — via the `automationSupport` manifest field
  (`ARCHITECTURE.md` section 10), exposed to the AI Orchestrator/
  `ActionExecutor` (M10).
- Permissions — via the Permission Model above; a plugin cannot
  invent a permission scope outside the fixed vocabulary
  (`ARCHITECTURE.md` section 10).
- Background services — via this milestone's own Background Tasks
  module (Reliability, above); a plugin's background work is
  supervised, not a bare, unmanaged process.
- Context menu actions — via a reusable context-menu registration
  point (M8 Phase 3, planned — not yet built; will itself be a
  `ContributionRegistry` instance, per the pattern above).
- Command Palette actions — via `NavigationContribution`'s existing
  `commandPaletteEntries` field (M8 Phase 2) — already real, not new,
  and as of M8 Phase 3 Task Group G has a real UI consumer
  (`components/layout/command-palette-layer.tsx`, `Ctrl+K`/
  `Ctrl+Shift+P`) rendering whatever it aggregates.

**What's already real vs. what still depends on the Plugin Loader
above:** every frontend-side registry this list points at
(`ApplicationRegistry`, `ContributionRegistry` and its named instances,
the Permission/Settings/Notification Frameworks) already exists and
works for first-party modules today — a registered `BaseApplication`
instance can already contribute navigation, a dashboard widget, a
status bar item, settings, and command palette entries with zero
further backend work.
What doesn't exist yet is the mechanism that loads *third-party*
plugin code into that same registry in the first place — the Plugin
Loader, sandboxing, and Marketplace install/uninstall flow above. The
landing pad is built; the delivery truck isn't. A plugin author cannot
ship a real, installable plugin until this milestone's Plugin Loader
ships; a first-party module can use
every one of these extension points today.

#### Developer Platform Tools *(✅ Task Group E, shipped Aug 2026 —
Developer Mode; closes out M9 in full — see the changelog addendum at
the end of this document for implementation detail)*
- Debug Console — a live, filterable view over the runtime's own
  structured logs (loguru/structlog), rendered by M8's frontend.
- Live Logs — streamed over the same WebSocket channel M8's Agent
  Trace / voice-state panels use.
- Performance Profiler — surfaces Resource Manager's per-service data.
- State Inspector — a live view into Service Manager's registry and
  each service's `ModuleStateMachine` state (§7 UI Foundation).
- API Inspector — request/response inspection for this milestone's
  own runtime API surface (distinct from M11's Workspace Developer
  Tools, which inspect *external* API calls).
- Plugin Marketplace Foundation — the backend index/install/uninstall
  API that M8's Marketplace UI (above) renders.

Lands in Developer Mode alongside M5's existing panels and M5A's Agent
Trace, following the established §7 Cross-Platform Systems pattern.

**Dependencies:** M0 (DI container, config, events — this module's own
foundation), M3, M4, M5 (services worth exposing as plugin surface
must already be real — kept from the original M8's own dependency
reasoning), M8 (the React frontend is this module's Developer Platform
Tools' and Marketplace's consumer).

**Complexity:** L *(consolidates two previously-separate L-sized
milestones' scope — the original Integration Platform's runtime-
adjacent reasoning was already thin, and Plugin Platform's own scope
is unchanged — not elevated to XL since neither module list approaches
M12–M14's dozen-module breadth)*.

**Acceptance criteria:**
1. A hello-world plugin registers a slash command and a hotkey.
2. A plugin without the `network` permission cannot make outbound
   requests (blocked with `PermissionError`).
3. Uninstall leaves no orphan files or registered hooks.
4. Service Manager's health status for every registered service is
   visible in Developer Mode's State Inspector in real time.
5. A simulated backend crash triggers Crash Recovery and the affected
   service resumes without a full application restart.
6. A plugin that throws an unhandled exception during any lifecycle
   hook (`on_load`/`on_start`/`on_stop`) is caught by Plugin Isolation
   and disabled; JARVIS Core and every other running plugin remain
   unaffected.

### M10 — AI Orchestrator

*(Retitled Aug 2026 from "Knowledge Engine" as part of the frontend
technology migration — see `TECH_STACK.md` and the changelog addendum
at the end of this document. Knowledge Engine's own scope — Knowledge
Graph, Persistent Memory, Reflection foundation, Learning, Relationship
Graph, Digital Twin Foundation — is preserved in full, not dropped: it
moves to the new **M10A Universal Search & Knowledge Platform**,
below, a lettered companion rather than a renumbering, per the
"zero renumbering" rule this migration pass follows throughout §8.)*

**Status (Aug 2026): 🟡 partial.** The buildable-now scope shipped
directly against M5A's `AgentOrchestrator` -- see the Aug 2026 M10
changelog addendum for the full list. M10 formally depends on M10A and
M14, below, neither of which has started; rather than block on that,
this pass shipped everything real without them and documented the rest
as explicitly deferred (Context Engine's knowledge-graph half needs
M10A; Learning/Feedback needs M16; Permission Validation's final
M14-routed form uses an interim `AgentPermissionGate` until M14 ships)
-- the same "Completed / Deferred with a documented reason" discipline
this project has applied since the M0-M9 Project Completion Audit.
**Do not treat M10 as 100% complete.**

**M10 Closure Summary (Aug 2026):**

✅ **Completed** (buildable now, no missing dependency):
- Intent Engine -- `agents/nodes/intent_classifier.py`, diagnostic
  classification ahead of planning.
- Context Engine (current implementation) -- `agents/nodes/
  context_engine.py`, M3 Memory only; see Deferred for the
  knowledge-graph half.
- Decision Engine -- `response_mode` on the `responder` node.
- Parallel Tool Dispatch -- `tool_selector`'s `tool_parallel` shape +
  `tool_executor`'s concurrent dispatch (Acceptance Criterion 1).
- Permission Validation (interim) -- `agents/permission.py`'s
  `AgentPermissionGate` + `permission_validator` node (Acceptance
  Criterion 3).
- Token Streaming -- real per-token output via `ILLMProvider.stream()`
  for the tool-composed path (Acceptance Criterion 2).
- Runtime WebSocket integration -- `agent.step` on
  `RuntimeWebSocketHub.EVENT_TYPE_NAMES`.
- `/api/v1/agent` endpoints -- `POST /agent/invoke`,
  `POST /agent/stream`.

🟠 **Deferred** (blocked on a milestone that hasn't shipped -- see each
item's own reason, not silently dropped):
- **Knowledge Graph integration** -- needs **M10A** (Universal Search &
  Knowledge Platform), not started; Context Engine today reads M3
  Memory only, no knowledge graph exists to query yet.
- **Final Authorization Engine integration** -- needs **M14**
  (Authorization Engine), not started; `AgentPermissionGate` is the
  interim single enforcement point, built so swapping in M14 later
  means replacing its `authorize()` body, not the graph wiring.
- **Learning & Feedback** -- needs **M16** (Reflection Engine), not
  started; M10's own spec routes this through M16, not a second
  learning mechanism.
- **Intent Engine gating graph routing** -- needs real signal from
  **M10A/M10B**, neither started; today the classification is recorded
  but diagnostic-only.
- **Final streaming optimizations** -- `tool_selector`'s "final"
  (no-tool-needed) shortcut still replays precomposed text rather than
  streaming real tokens, since its answer is embedded inside a JSON
  decision object; fixing this means restructuring tool selection
  itself, out of this pass's scope.
- **Remaining UI integration** -- wiring the PySide6 Agent Trace view
  or a React frontend surface to `/api/v1/agent` is **M8**'s own
  remaining phases (Phases 2-3/5-7), unchanged and unblocked by this
  pass.

**Regression Audit (Aug 2026, post-M10, ahead of M10A):** a full
milestone-by-milestone check of M1 through M9 for anything M10
disturbed.

| Milestone | Status |
|---|---|
| M0-M6 | ✅ Stable |
| M7 | ✅ Stable |
| M8 | ✅ Stable -- zero frontend files touched by M10 |
| M9 | ✅ Stable |

- **Fixed regression:** `test_runtime_ws_hub.py::
  test_every_documented_event_type_is_mapped` hardcoded the full
  `EVENT_TYPE_NAMES` value set; M10's new `agent.step` entry broke it
  -- an expected, mechanical update, not a design gap.
- **Fixed documentation issue:** `agent_trace_view.py`'s module
  docstring listed the fixed five-node M5A sequence, stale after M10
  added three nodes; the code itself already renders any node name
  generically, so this was a comment-only fix.
- **Remaining accepted technical debt (pre-existing, not a
  regression):** `AgentOrchestrator` has never been registered in
  `app.py`'s `RuntimeManager` shutdown hooks (true since M5A, unchanged
  by M10) -- its SQLite checkpointer connection relies on explicit
  `.stop()` calls rather than the app's own shutdown sequence.
- **Verification:** full suite 839/839 passing before and after;
  ruff 570 -> 597 findings (+27, 100% the established `PLC0415`
  lazy-import pattern, zero new categories); mypy 266 -> 266,
  byte-for-byte unchanged.

**Objective:** formalize and expand the M5A `AgentOrchestrator`
(the compiled LangGraph `StateGraph`: `planner → tool_selector →
tool_executor → critic → responder`) into a dedicated orchestration
platform — the central Intent → Plan → Execute → Verify pipeline every
AI-driven feature in JARVIS routes through, rather than each milestone
building its own ad-hoc agent loop. This is also the milestone M7
Phase 3 (Structured Graph Planning — cross-tool parallelism inside the
agent runtime, deferred since M7's own status review) now belongs to,
rather than reopening M7 for it: extending `AgentState` / `planner.py`
/ `tool_executor.py` / `graph.py` for parallel tool dispatch is this
milestone's own scope now.

**Key features:**
- Intent Engine — classifies a request into an actionable intent
  before planning starts, upstream of M5A's existing `planner.py` node.
- Planning — multi-step plan generation, extending M5A's planner node;
  absorbs M7 Phase 3's deferred cross-tool-parallelism work as this
  milestone's own acceptance criterion (below), not M7's.
- Context Engine — assembles the context window from M10A's knowledge
  substrate and M3 Memory, replacing context assembly scattered
  per-tool with one shared pipeline stage.
- Tool Selection — extends M5A's existing `tool_selector` node.
- Permission Validation — routes every tool invocation through M14's
  Authorization Engine once that milestone ships, replacing M5A's
  ad-hoc per-tool checks (e.g. `run_automation`'s confirmation-callback
  gap, noted in M5A's own "still open" list) with one enforcement
  point.
- Execution — extends M5A's existing `tool_executor` node.
- Verification — extends M5A's existing `critic` node.
- Learning / Feedback — closes the loop through M16's Reflection
  Engine (Workflow Reflection, Behaviour Reflection) rather than a
  second, competing learning mechanism.
- Streaming — real token-level streaming over M8's WebSocket layer,
  replacing M5A's `stream()` limitation ("re-chunks the already-
  composed final answer word-by-word," §15) with true incremental
  generation.
- Decision Engine — the `responder` node's successor, deciding final
  response shape and routing.

**Dependencies:** M5A (this milestone extends `AgentOrchestrator`
directly, not a rewrite), M8 (WebSocket transport for real streaming),
M10A (knowledge/context substrate), M14 (Permission Validation).

**Complexity:** L.

**Acceptance criteria:**
1. ✅ **Met.** A request needing two independent tool calls dispatches
   them in parallel inside a single graph run, not sequentially — the
   M7 Phase 3 acceptance criterion, now delivered here
   (`agents/nodes/tool_selector.py`'s `tool_parallel` shape +
   `agents/nodes/tool_executor.py`'s concurrent dispatch).
2. 🟡 **Met for the dominant path.** Token-level streaming is
   measurably real (verified: `ScriptedFakeLLM`'s per-word streaming
   yields distinguishably more chunks than the old word-chunked replay
   for the same text) for an answer composed from tool results.
   `tool_selector`'s "final" (no-tool-needed) shortcut still replays a
   precomposed string, since its answer is embedded inside a JSON
   decision object — a documented, scoped exception, not a hidden gap.
3. ✅ **Met, interim.** Every tool invocation passes through Permission
   Validation (`agents/nodes/permission_validator.py`) before
   executing; a denied permission blocks execution the same way a
   `PermissionGate` denial already does in M4's automation layer. The
   enforcement policy itself is interim (`AgentPermissionGate`,
   settings-driven) pending M14's Authorization Engine, per this
   milestone's own Permission Validation key feature above.

### M10A — Universal Search & Knowledge Platform

*(New lettered companion to M10, Aug 2026 — houses the original M10
Knowledge Engine's full scope, carried forward unchanged, alongside
the "Universal Search" scope from the Aug 2026 frontend migration
brief. Not a renumbering: M10A is additive, per the "zero renumbering"
rule.)*

**Status (Aug 2026): ✅ Completed.** Unlike M10, M10A's own declared
dependencies (M3, M5A) were both already shipped, so this milestone
was buildable to near-full completion in one pass -- see the Aug 2026
M10A changelog addendum for the full design. **One key feature is
explicitly deferred, not silently dropped:** File Search needs M11B's
File Manager surface, which doesn't exist yet; the `ISearchSource`
provider-registry architecture is the documented seam it plugs into
once M11B ships, requiring no `SearchService` changes when it does.

**M10A Closure Summary (Aug 2026):**

✅ **Completed:**
- Knowledge Graph / Relationship Graph -- `KnowledgeEntity` /
  `KnowledgeRelationship` / `KnowledgeEntityMemory`, LLM-driven
  extraction from memory content.
- Persistent Memory -- reuses M3's existing `pinned` mechanism rather
  than a second durability concept.
- Reflection Foundation -- `KnowledgeService.learn_from_recent_memories()`,
  on-demand (REST/agent tool), never a scheduled background job.
- Learning (scoped) -- `KnowledgeService.correct()` supersedes prior
  relationships with a higher-confidence replacement (Acceptance
  Criterion 3), an interim primitive, not a full Learning Engine.
- Digital Twin Foundation -- the Knowledge Graph schema itself is the
  substrate; this milestone does not itself claim to build a twin.
- Universal Search -- `SearchService`'s provider registry
  (`register_source`/`unregister_source`/`get_sources`), fanning out
  to every registered `ISearchSource` concurrently.
- Memory Search, Command Search, Semantic Search, Search Indexing, AI
  Search -- `MemorySearchSource`/`CommandSearchSource`/
  `KnowledgeSearchSource`, all reusing existing infrastructure (M3
  Memory, the Tool Registry, `PluginRegistry`, the single shared
  Chroma collection) rather than a parallel implementation.
- `/api/v1/search` + `/api/v1/knowledge/*` REST API, `memory`/
  `knowledge` WebSocket categories over the existing Runtime WebSocket
  relay, agent tool integration (`ask_knowledge`/`search_knowledge`),
  and Context Engine's knowledge-graph half -- closing the deferral
  M10's own closure documented.

🟠 **Deferred** (blocked on a milestone that hasn't shipped):
- **File Search** -- needs **M11B** (Productivity Suite), not started;
  no File Manager surface exists yet to index. The `ISearchSource`
  protocol is the seam it plugs into later.
- **AI reranking** -- `SearchResult`'s `confidence`/`reason` fields
  exist now (extensible model, per this milestone's own design
  requirement) but are unpopulated; deliberately not implemented this
  pass, reserved for a future milestone.
- **Scheduled Reflection** -- `learn_from_recent_memories()` is
  on-demand only; wiring it to M7's Scheduler for periodic execution
  is explicitly out of scope, deferred to a future pass.
- **Full Learning Engine** -- `correct()` is a scoped correction
  primitive satisfying Acceptance Criterion 3, not the general-purpose
  learning engine a future milestone might build.

**Objective:** turn the M3 Memory Platform's flat semantic store into
a real, queryable knowledge base — the foundation every "companion
intelligence" milestone later in this roadmap (M15–M20) builds on —
and provide the one unified search surface every other searchable
JARVIS data source (memory, files, commands) queries through, rather
than each maintaining its own index. Backs M8 Phase 3's Command
Palette shell and M11B's full Command Palette feature.

**Key features:**
- Knowledge Graph — entities and relationships extracted from
  conversations/memories, not just embedded text blobs.
- Persistent Memory — long-horizon memory that survives well beyond
  M3's retention-policy window for explicitly "durable" facts.
- Reflection Foundation — periodic summarization of what's been
  learned; the substrate M16 Reflection Engine's own objective
  describes as "building on, and now fully realizing, M10's original
  reflection foundation" — that foundation now lives here.
- Learning — feedback signals (corrections, confirmations) feed back
  into memory confidence scoring.
- Relationship Graph — how entities (people, projects, files) relate
  to each other, queryable by the agent runtime as a tool.
- Digital Twin Foundation — the data model this milestone establishes
  is the substrate M19 Intelligence Graph later builds a full digital
  twin on top of; this milestone does not itself claim to build one.
- Universal Search — one query surface spanning every source below,
  rather than a separate search box per data type.
- Memory Search — semantic + keyword search over M3's memory store.
- File Search — indexed search over M11B's File Manager surface.
- Command Search — the backing index for M8's Command Palette shell
  and M11B's full Command Palette feature.
- Semantic Search — vector-similarity search reused across every
  source above, not reimplemented per source.
- Search Indexing — the shared indexing pipeline every search type
  above is built on.
- AI Search — natural-language query answering over indexed content,
  distinct from Command Search's literal command matching.

**Dependencies:** M3 (Memory Platform), M5A (exposed as an agent tool
the same way every other service is).

**Complexity:** L.

**Acceptance criteria:**
1. ✅ **Met.** A query like "what do you know about Project X" returns
   a coherent answer drawing on multiple related memories, not just a
   keyword match -- `KnowledgeService.ask()`, verified end-to-end via
   `tests/integration/test_knowledge_platform_e2e.py`.
2. ✅ **Met.** The knowledge graph survives an export/import
   round-trip -- `KnowledgeService.export_graph()`/`import_graph()`,
   verified both at the unit level (fresh-database round-trip) and
   over the real REST API.
3. ✅ **Met.** A correction ("actually, my meeting is on Thursday not
   Wednesday") measurably updates future recall --
   `KnowledgeService.correct()` supersedes the prior relationship and
   inserts a higher-confidence replacement, verified end-to-end
   including over the real Runtime WebSocket relay.
4. ✅ **Met.** A single Universal Search query returns relevant
   results spanning at least two distinct source types (e.g. memory +
   knowledge) in one response -- `SearchService.search()`, verified
   over the real REST API with real memory and knowledge-graph data.

### M10B — Intelligence Layer

*(New lettered companion to M10, Aug 2026, from the frontend migration
brief's "Intelligence" scope. Deliberately scoped as an engine, not a
duplicate of M15's Proactive Intelligence module or M16's Goal
Reflection/Behaviour Reflection modules — both already exist, are
already detailed, and are explicitly left untouched by this migration.
This milestone is their shared backing implementation, not a
competing one — see Objective.)*

**Status (Aug 2026): ✅ Completed.** Extends M10A's architecture
directly -- `IntelligenceService`/`IntelligenceRepository` mirror
`KnowledgeService`/`KnowledgeRepository`'s exact shape, and Goal
Manager registers into `SearchService`'s existing provider registry as
a fourth source with zero changes to `SearchService` itself -- see the
Aug 2026 M10B changelog addendum for the full design. **One key
feature is explicitly deferred, not silently dropped:** automatic
scheduled Daily Briefing delivery needs M7's Scheduler (Phase 6),
which does not exist yet -- `SchedulerSettings` has been declared for
forward compatibility only since Phase 1. Daily Briefing is real and
on-demand (REST + agent tool) today; the Scheduler integration is the
documented seam it plugs into once M7 Phase 6 ships.

**M10B Closure Summary (Aug 2026):**

✅ **Completed:**
- Goal Manager -- `Goal` (self-referential hierarchy), full CRUD,
  progress tracking with auto-completion at >=100%, `goal.updated`
  WebSocket event.
- Routine Learning -- deterministic, direct-observation reinforcement
  (`Routine` rows, hour-of-day/day-of-week wildcards, confidence
  scoring), not LLM-driven pattern mining.
- Preference Learning -- a structured `Preference` key-value store,
  separate from M3's freeform preference memories.
- Context Awareness -- time/day/recent-activity signals via
  `MemoryService.browse()`; no location signal, since no location
  provider exists anywhere in the codebase yet.
- Predictive Suggestions -- combines due-soon goals, reinforced
  routines, and a preference-boost pass into one ranked list; plain
  keyword-boost logic, not an AI reranker.
- Daily Briefing -- on-demand generation (REST + agent tool),
  `briefing.generated` WebSocket event.
- `/api/v1/goals` + `/api/v1/intelligence/*` REST API, agent tool
  integration, and `GoalSearchSource` registered as Universal Search's
  fourth provider.

🟠 **Deferred** (blocked on a milestone that hasn't shipped):
- **Automatic scheduled Daily Briefing delivery** -- needs **M7**'s
  Scheduler (Phase 6), not started; Daily Briefing is on-demand only
  today.
- **Location-aware Context Signals** -- no location provider exists in
  the codebase; documented rather than faked.
- **AI reranking of Predictive Suggestions** -- plain keyword-boost
  logic only, matching M10A's own deferred AI reranking of search
  results.

**Objective:** the goal-tracking, routine/preference-learning, and
predictive-suggestion engine that M15's Proactive Intelligence module
(communication/delivery layer) and M16's Goal Reflection / Behaviour
Reflection modules (retrospective analysis layer) both consume as
their backing implementation, rather than each maintaining its own.
M20 Predictive Intelligence Platform is this engine's full-scale,
cross-milestone realization once that milestone ships; this milestone
is its foundation, not a second, parallel implementation.

**Key features:**
- Goal Manager — goal CRUD + hierarchy; the data model M23B's own,
  much larger Goal Management module later extends at full
  orchestration scale, not a competing one.
- Routine Learning.
- Preference Learning.
- Predictive Suggestions — the ranking engine behind M15's Smart
  Suggestions and Contextual Recommendations bullets.
- Context Awareness — signal aggregation (time, location if granted,
  active conversation, recent activity) feeding Predictive Suggestions.
- Daily Briefing — the concrete scheduled deliverable (via M7's
  Scheduler) that M15's Proactive Intelligence "Daily Briefings" bullet
  renders through its own personality/tone layer; this module supplies
  *what*, M15 supplies *how*, matching the existing M15↔M7/M17/M20
  "how vs. what" pattern already established in M15's own Acceptance
  Criterion 10.
- Assistant Intelligence — the umbrella capability M17 Companion
  Intelligence later synthesizes alongside M10A and M16.

**Dependencies:** M3 (memory substrate), M7 (Scheduler for Daily
Briefing), M10A (knowledge/context substrate).

**Complexity:** M.

**Acceptance criteria:**
1. ✅ **Met.** Goal Manager persists a goal across sessions with
   measurable progress tracking -- verified with three separate
   `IntelligenceService` instances against the same database (proving
   real persistence, not in-memory state) and end-to-end over the real
   REST API + WebSocket relay.
2. ✅ **Met.** A learned routine or preference measurably changes a
   future Predictive Suggestion -- two independent, directly-testable
   mechanisms: a routine only surfaces once reinforced past a minimum
   observation count, and a `suggestion_boost_keyword` preference
   multiplies a matching suggestion's score; both verified before/after
   at the unit level and over the real REST API.
3. ✅ **Met, on-demand only.** Daily Briefing generates real content
   (goals due soon, top suggestions, routine reminders) and relays
   `briefing.generated` over the real WebSocket. Firing on a configured
   schedule via M7, and rendering through M15's Proactive Intelligence
   delivery layer, remain deferred pending M7's Scheduler (Phase 6) and
   M15 respectively -- neither exists yet.

### M10.5 — MCP & Integration Platform

*(New milestone, Aug 2026 — introduced after M10B completed, as a
roadmap extension. Not a renumbering: M10.5 is additive, following the
decimal-companion precedent **M5.5** (Production Stabilization Pass,
§3) already set, and alters no existing milestone's identity or scope.)*

**Status: ✅ Completed (Aug 2026, v0.20.0) — Task Groups A (Core
Runtime), B (Transport Layer), C (Provider Framework), D
(Authentication Foundation) and E (SDK, Developer Experience &
Milestone Closure) all shipped.** The MCP platform is complete as
scoped: Capability Registry, transport abstraction, client runtime
(connection/handshake/discovery/health/reconnect), server runtime
(capability exposure + permission enforcement), capability negotiation,
DI wiring, runtime events, and a read-only ``/api/v1/mcp/*`` REST
surface (Task Group A) — plus **all four network transports**
(``stdio``, ``websocket``, ``http``, ``ipc``), a config-driven
transport factory, transport discovery/query, and a heartbeat monitor
(Task Group B) — plus the generic **Provider Framework** every future
integration plugs into: provider interface, registry with filtered
discovery, lifecycle manager, metadata/configuration models, health
collection and read-only `/api/v1/mcp/providers/*` routes (Task Group
C) — plus the **authentication framework** every future provider
uses: credential model, encrypted-at-rest storage, auth strategies,
provider sessions, the permission bridge, and read-only
`/api/v1/mcp/auth/*` routes (Task Group D) — plus the **SDK and
developer experience** an integration author works against: fluent
builders over the existing runtime models, a reusable validation
framework, the `jarvis mcp` read-only CLI, self-contained runnable
examples, the `MCPDiagnostics` aggregator and
`/api/v1/mcp/diagnostics` + `/api/v1/mcp/validate` (Task Group E).

**What this milestone deliberately does not include**, unchanged from
its original scope: no *real* provider ships, no OAuth flow (which
needs an authorization server and a callback endpoint), no server-side
network listener, and no vendor integration. Those are M11's scope,
and M10.5 exists so M11 builds *on* this substrate rather than
retrofitting onto it. See the Aug 2026 M10.5 Task Group A, B, C, D and
E changelog addenda for the full design, and **Deferred to M11** below
for the two acceptance criteria carried forward.

**Objective:** the protocol-level foundation for every external tool
and context provider JARVIS consumes — standardizing on **MCP (Model
Context Protocol)** so a new integration is a *registered provider*
rather than a bespoke adapter written from scratch each time.
Deliberately scoped as the protocol-and-registry layer *beneath* M11
Integrations & Cloud Platform, not a duplicate of it: this milestone
defines **how** an external capability is described, discovered,
permissioned and invoked; M11 supplies the **specific**
credential-backed providers (Gmail, Calendar, Spotify, Oracle Cloud
sync) that flow through it. Scheduled before M11 precisely so M11's
providers are built on this foundation rather than retrofitted onto it
afterwards.

**Key features:**
- MCP Client — consume external MCP servers as tool/context providers,
  surfaced through the existing Tool Registry rather than a parallel
  one.
- MCP Server (JARVIS as provider) — expose JARVIS's own tools and
  resources to other MCP-aware clients over the same protocol.
- Provider Registry — register/unregister/discover MCP providers at
  runtime, mirroring `SearchService`'s already-shipped `ISearchSource`
  registry pattern (M10A) rather than inventing a second registration
  mechanism.
- Capability Negotiation — a provider declares what it offers; JARVIS
  checks that declaration against the existing M9 plugin permission
  vocabulary before exposing it to the agent.
- Transport abstraction — stdio/HTTP/WebSocket MCP transports behind
  one port in `core/interfaces`, per §4's ports-and-adapters rule.
- Integration lifecycle — connect, health-check, reconnect, disconnect,
  matching M9's Service Manager per-service lifecycle rather than a
  bespoke one.
- Permission Model — every MCP-provided tool passes through M10's
  Permission Validation node before executing. No MCP tool bypasses
  the gate an in-process tool already goes through.

**Explicitly not duplicated here:** OAuth flows, credential storage,
API Gateway, webhooks, queue/retry/caching, cloud sync (Oracle Cloud,
MongoDB), and the specific Email/Calendar/Spotify/Weather/Finance
providers are all M11's own already-detailed scope. This milestone
provides the protocol substrate they register through; it does not
restate them.

**Dependencies:** M5A (agent tool exposure — MCP tools land in the
same Tool Registry every other tool does), M9 (Plugin Permission
Model, Service Manager lifecycle), M10 (the Permission Validation node
every tool call routes through), M10A (the provider-registry pattern
this milestone mirrors).

**Complexity:** L.

**Acceptance criteria (final, at milestone close):**
1. 🟡 **Substantially met (Task Groups A + B).** A registered MCP
   server's capability is discovered, negotiated and successfully
   invoked end-to-end over a real transport against a **real
   out-of-process peer** — verified in
   `tests/integration/test_mcp_transport_e2e.py` (stdio subprocess) and
   `tests/unit/test_mcp_transports_live.py` (real WebSocket and HTTP
   servers). Agent Trace integration remains deferred: it needs MCP
   tools exposed through the Tool Registry, which is M11's work.
2. ✅ **Met.** An MCP capability whose declared scope is not granted is
   refused — by M9's existing `PermissionModel`, namespaced
   `mcp:<client_id>`, with no second permission system and no new
   permission vocabulary. Verified both at the negotiation layer
   (the capability is dropped) and at the invocation layer (the call
   raises), plus a `mcp.permission_denied` event over the real
   WebSocket relay.
3. 🟡 **Partially met (Task Groups A + B).** `MCPServerRuntime` exposes
   JARVIS capabilities and serves `initialize`/`capabilities/list`/
   `capabilities/call`/`ping` to a real client. Consumption by an
   external client additionally needs JARVIS to *listen* on a network
   transport; all four shipped transports are outbound/client-side, and
   a server-side listener is deferred to M11.
4. ✅ **Met.** Connection loss, bounded retry with backoff, reconnect,
   and clean deregistration are all real and unit-tested; health is
   reported through M9's existing `HealthMonitor.register_collector`
   extension point, not a second health channel. No runtime restart is
   involved in any path.

**Deferred to M11 (named, not hidden).** Two acceptance criteria close
at 🟡 rather than ✅, and both are deferred deliberately rather than
missed:

| Deferred | Why it is not in M10.5 | Where it lands |
|---|---|---|
| Agent Trace integration for MCP tool calls (AC1) | Requires MCP capabilities to be surfaced as agent tools through the Tool Registry. That is provider-facing work, and this milestone ships no provider. | M11, with the first real provider |
| Server-side network listener (AC3) | The four shipped transports are outbound. Accepting inbound MCP connections means binding a port and authenticating callers — a security surface that belongs with M11's API Gateway rather than bolted on here. | M11, alongside the API Gateway |

Everything else M10.5 scoped is shipped, tested and wired. Neither
deferral blocks M11: the substrate M11 registers against is complete.

### M11 — Integrations & Cloud Platform

*(Retitled Aug 2026 from "Productivity Platform" as part of the
frontend technology migration — see `TECH_STACK.md` and the changelog
addendum at the end of this document. Absorbs the old M9 Integration
Platform's full scope (API Gateway, OAuth, API Manager, Webhooks,
Queue, Retry Policies, Caching, Monitoring — see M9's own note) plus
old M11 Productivity Platform's integration-facing features (Email,
Calendar, Browser Intelligence, Google Workspace). Old M11's
non-integration productivity features — Tasks, Documents, Research
Assistant, Coding Assistant, Command Palette, Clipboard Manager, File
Manager, Native notifications, Media Controls — are preserved in full,
not dropped: they move to the new **M11B Productivity Suite**, below,
a lettered companion rather than a renumbering.)*

**Objective:** the one governed surface for every external connection
JARVIS makes — outbound API integrations, OAuth-backed accounts, and
optional cloud sync — generalizing what M5's API Center started as
CRUD-only, and folding in what M9 originally scoped as a separate
milestone.

**Key features:**
- API Gateway — a single, audited egress point for outbound
  integration traffic.
- OAuth — a reusable authorization-code flow, replacing the
  read-only-mock integrations M5 shipped (Gmail, Spotify) with real
  ones.
- **API Center Architecture** — grows M5's API Center from credential
  CRUD into full lifecycle management (real-time activation, health
  checks, quota tracking, rotation reminders, usage analytics); see
  the dedicated module below.
- Webhooks — inbound event delivery for integrations that push rather
  than get polled.
- Queue — durable outbound-call queueing so a transient integration
  outage doesn't lose work.
- Retry Policies — standardized backoff/retry across every
  integration, not reimplemented per provider.
- Caching — response caching for expensive/rate-limited external
  calls.
- Monitoring — integration health surfaced in Developer Mode.
- Email — Gmail/Outlook, real (via this milestone's own OAuth),
  replacing M5's mock.
- Calendar — same treatment.
- Browser Intelligence — deeper automation over M4's `BrowserService`
  (multi-tab awareness, session persistence, structured extraction).
- Spotify, Weather, Finance — real providers replacing M5's mocks,
  per M5's own "still open" note naming these three as pending real
  integrations.
- Oracle Cloud — the optional outbound sync target (see `TECH_STACK.md`
  §5); local-first remains the default, nothing here requires a cloud
  account.
- Android Companion — the account-linking/pairing integration only;
  the mobile app's own UI and feature set remain M21 Mobile Platform's
  scope, not duplicated here (mirrors the Google Workspace module's
  own "provider abstraction, not a UI" boundary below).
- Sync, Conflict Resolution, Offline Queue — the mechanics underneath
  Oracle Cloud sync and Android Companion pairing.
- **Google Workspace Integration** — full G Suite provider suite +
  AI Meeting Assistant; see the dedicated module below.

**Explicitly not duplicated here:** Smart Home integration is M12
Smart Home & IoT Platform's own dedicated, already-detailed scope —
not restated in this milestone despite Smart Home appearing in this
milestone's original brief category list. Cloud file storage (Drive/
OneDrive/Dropbox/Box) is already covered by the Google Workspace
module below and its Future Expansion list — this milestone doesn't
define a second, competing file-storage integration. Local filesystem
access (the File Manager tool) is a different concern entirely and
lives in M11B, below.

**Dependencies:** M0 (core), M5 (extends M5's mock API Center and mock
Gmail/Spotify/Weather/Finance integrations into real ones), M14
(Secrets Management for OAuth tokens and cloud-sync credentials, once
that milestone ships — mirrored from the Google Workspace module's own
dependency below).

**Complexity:** XL *(merges two previously-separate L-sized
milestones' scope — the original Integration Platform and Productivity
Platform's integration half — plus new Oracle Cloud sync and Android
Companion pairing scope; sized consistently with this roadmap's other
XL "platform" milestones, e.g. M8, M12, M13, M14)*.

**Acceptance criteria:**
1. A real OAuth-backed Gmail connection replaces the M5 mock without
   changing the Gmail workspace's UI contract.
2. A webhook delivery is received, verified, and routed to the
   correct plugin/service.
3. An integration outage triggers retry-with-backoff, not an
   immediate user-facing failure.
4. A sync operation against Oracle Cloud completes, and a subsequent
   edit conflict resolves without silent data loss.

#### Module: API Center Architecture

> This subsection is the official roadmap for the API Center's full
> lifecycle-management design — expanding the API Center Architecture
> bullet above from credential CRUD into a governed, self-activating
> provider surface. It is a module within M11 — it does not introduce
> a new milestone code and does not change M11's numbering,
> dependencies, or acceptance criteria above. Planning only; no
> implementation exists yet.

**Objective:** one governed registry for every provider JARVIS talks
to — built-in (internal services) and external (credential-backed) —
with instant activation, health/usage visibility, and automatic
failover, replacing today's static, restart-required provider wiring
in `core/di/container.py`.

**Provider Activation Rule** *(binding, applies to every provider from
this milestone onward)*:
- Saving a valid API key **immediately activates** its provider — no
  restart, no separate "enable" step.
- Every module that depends on that provider **instantly uses it** the
  moment it activates, via the existing `ILLMProvider`-style port each
  module already depends on (§4's provider-abstraction standard),
  never a direct concrete-class reference.
- **Mock providers are permitted only when Developer Mode explicitly
  enables them** — never as a silent default when a real key is
  missing or invalid; the module instead surfaces its real
  `not_configured` state (§7 UI Foundation `ConnectionState`), the
  same rule M6's Vision/OCR mocks already follow.

**Runtime provider lifecycle**
- Real API Activation — a saved key transitions the provider straight
  from `not_configured` to `connecting`/`connected` (§7
  `ConnectionState`), with no separate build/deploy step.
- Runtime Provider Registration — providers register into the API
  Center's registry at activation time, not only at process startup;
  extends `core/di/container.py`'s existing Singleton-provider pattern
  with a live, post-startup registration path.
- API Key Validation — a lightweight round-trip check against the
  provider's own API before it is marked active.
- Connection Testing — an explicit, user-triggered "Test Connection"
  action per provider, independent of the passive health check below.
- Provider Health Check — periodic background health polling per
  active provider, feeding the same signal M9's Reliability module's
  Health Monitor already defines.
- Automatic Provider Discovery — the API Center enumerates every
  adapter already implementing the relevant port (e.g. every
  `ILLMProvider` adapter under `infrastructure/llm/`) rather than
  requiring a manually maintained registration list.
- Runtime Provider Switching — a module's active provider can change
  without restart, per §13's existing Provider switching mechanics
  (fallback chain, per-conversation override).
- Retry Strategy / Failure Recovery — standardized backoff-and-retry on
  a failed call, then automatic fallback to the next configured
  provider before surfacing an error to the user (this milestone's own
  Retry Policies feature above, applied specifically to
  provider-selection failures).
- Provider Priority / Provider Fallback — an ordered preference list
  per capability (chat, vision, STT, TTS, embeddings), reusing §13's
  existing fallback-chain concept rather than a second mechanism.

**Provider taxonomy**

*A. Built-in Providers* — internal JARVIS services, never API-key
gated: Memory, Automation, Workflow, Security, Database,
Authentication, Notifications, Configuration, Logging, Scheduler,
Backup, Plugin Runtime. Never expose an API key field. Display: Name,
Status, Endpoint, Version, Health.

*B. External Providers* — outbound, credential-backed integrations:
OpenAI, Claude, Gemini, OpenRouter, Groq, ElevenLabs, Google, GitHub,
Discord, Slack, Notion, and every other provider already tracked in
§13's per-capability tables (this taxonomy is the API Center's UI/
registry grouping layered over those tables, not a replacement for
them). Display: Provider Name, Masked API Key, Status, Test
Connection, Health, Last Used, Latency, Remaining Quota, Monthly
Usage.

**API Usage Analytics** *(Developer Mode)*
An Analytics Dashboard, per external provider, tracking: Request
Count, Token Usage, Monthly Usage, Cost, Budget %, Average Latency,
Failed Requests, Success Rate, Module Usage, Estimated Monthly Cost,
and Remaining Budget — plus Usage Timeline, Cost Trend, Provider
Comparison, and Monthly Statistics charts. Purpose: let the user see
which providers are worth keeping. Lands in Developer Mode alongside
M9's Developer Platform Tools and this milestone's own Monitoring
feature above; the underlying cost-analytics engine this dashboard
visualizes is M20A Analytics & Observability Platform's scope (see
also §13's Cost-Aware Model Router, which consumes the same usage data
for routing decisions) — this module owns the display surface, not a
second analytics backend.

**Rendered by:** M8's React frontend (API Center UI, Phase 5 — see
`IMPLEMENTATION_ROADMAP.md`), following the same "backend owns state,
frontend only renders it" rule as every other M8 workspace.

**Dependencies:** this milestone's own API Manager/Monitoring features
above (this module is their detailed design, not a parallel system),
M9 (Health Monitor, DI container), §13 (provider tables and
fallback-chain mechanics), M14 (Secrets Management for API key
storage — the same dependency this milestone's OAuth flow already
declares).

#### Module: Google Workspace Integration & AI Meeting Intelligence

> This subsection is the **official roadmap for all Google Workspace
> (G Suite) features** in JARVIS OS. It is a module within M11 — it
> does not introduce a new milestone code and does not change M11's
> numbering, dependencies, or existing acceptance criteria above.
> Everything below is planning only; no implementation exists yet.

**Objective:** first-class, provider-abstracted Google Workspace
integration — centralized authentication, the full Workspace API
surface, and an AI Meeting Assistant that turns calendar/Meet/Gmail/
Drive activity into searchable, actionable memory via the M3 Memory
Platform / M10A Universal Search & Knowledge Platform.

**Authentication**
- Google OAuth 2.0
- Multi-Account Support
- Token Management
- Secure Credential Storage
- Workspace Permission Management

**Workspace APIs**
- Gmail API
- Google Calendar API
- Google Meet API
- Google Drive API
- Google Docs API
- Google Sheets API
- Google Slides API
- Google Chat API
- Google Tasks API
- Google People API
- Google Workspace Events API

**Calendar Intelligence**
- Create Events
- Update Events
- Delete Events
- Find Available Time
- Free / Busy Detection
- Meeting Scheduling
- Recurring Meetings
- Smart Scheduling
- Time Zone Management
- Automatic Reminder Management

**Google Meet Intelligence**
- Create Google Meet Meetings
- Generate Meeting Links
- Retrieve Meeting Information
- Retrieve Participant Information
- Meeting Lifecycle Monitoring
- Meeting Status Detection
- Meeting Event Synchronization
- Live Meeting Monitoring
- Recording Lifecycle Tracking
- Recording Availability Detection
- Transcript Availability Detection
- Participant Join/Leave Events
- Meeting Artifact Synchronization
- Meeting Duration Analytics
- Meeting Timeline
- Attendance Tracking
- AI Meeting Timeline
- Context Linking Between Meetings

**AI Meeting Assistant**
- Automatic Meeting Detection
- Meeting Recording Integration
- Transcript Processing
- AI Meeting Summary
- Key Decisions Extraction
- Action Item Detection
- Follow-up Generation
- Deadline Extraction
- Speaker Identification (provider-dependent)
- Meeting Search
- Meeting Memory
- Meeting Timeline
- Context Linking

**AI Meeting Insights**
- Conversation Topics
- Topic Segmentation
- Key Decision Timeline
- Speaker Contribution Analysis
- Sentiment Analysis
- Risk Detection
- Follow-up Risk Detection
- Missing Action Item Detection
- Decision Confidence
- Meeting Health Score
- Productivity Score
- Discussion Summary
- Executive Summary
- Technical Summary

**Gmail Intelligence**
- AI Email Summary
- Smart Reply
- Draft Generation
- Follow-up Suggestions
- Email Search
- Attachment Analysis
- Meeting Invitation Detection
- Email Classification

**Google Drive Intelligence**
- File Search
- Folder Management
- AI Document Search
- Automatic Upload
- Version Tracking
- Shared File Management

**Google Docs Intelligence**
- Generate Meeting Notes
- AI Documentation
- Minutes of Meeting
- Project Reports
- SOP Generation

**Google Sheets Intelligence**
- KPI Dashboards
- SEO Reports (feeds M11A SEO Intelligence)
- Analytics Reports
- Project Trackers
- Budget Sheets
- Data Analysis

**Google Slides Intelligence**
- AI Presentation Creation
- Meeting Presentation
- Project Presentation
- Business Reports

**Google Chat Intelligence**
- Send Messages
- Team Notifications
- AI Alerts
- Workflow Notifications
- Smart Replies

**Google Tasks Intelligence**
- Create Tasks
- AI Task Extraction
- Priority Detection
- Reminder Synchronization
- Task Completion Tracking

**Google People Intelligence**
- Contact Lookup
- Participant Profiles
- Relationship Context
- Team Directory

**Workspace Memory Integration**
- Store Meeting Summaries
- Store Email Context
- Store Decisions
- Store Action Items
- Link Workspace Data to Long-Term Memory (M3 Memory Platform / M10A
  Universal Search & Knowledge Platform)
- Semantic Search Across Workspace Content

**Workspace Search**

Unified search across:
- Gmail
- Calendar
- Meet
- Drive
- Docs
- Sheets
- Slides
- Tasks
- Contacts

Supporting:
- Semantic Search
- Natural Language Search
- AI Answer Generation
- Cross-Service Search
- Context Retrieval

**Workspace Automation**
- Automatic Meeting Detection
- Calendar Triggered Workflows
- Automatic Meeting Preparation
- Automatic Meeting Notes
- Automatic Meeting Summary Delivery
- Automatic Follow-up Email Generation
- Automatic Task Creation
- Reminder Automation
- Approval Workflows
- Cross-Service Automation
- Event-Based Workflow Triggers
- Multi-Step Workflow Automation

These workflows must support Gmail, Calendar, Meet, Docs, Drive,
Sheets, and Tasks today, and any future productivity provider added
under the same Provider Abstraction architecture note below (Slack,
Notion, Jira, etc.) without a workflow-engine redesign. Built on M7's
Workflow Intelligence (Advanced Agent Runtime, Scheduler,
event-based triggers) rather than a parallel automation engine.

**Workspace Administration** *(enterprise)*
- Domain Support
- Multiple Workspace Accounts
- Workspace Switching
- Organization Support
- Shared Drive Support
- User Management Integration
- Group Management Integration
- Audit Log Integration (feeds M14 Security Platform's audit log)
- Organization Policy Awareness

Enterprise administration features are **optional** — a personal,
single-account setup never requires them — and every one of them
requires the appropriate Google Workspace admin/org permission scope
to be granted explicitly before it activates; none is assumed present
by default.

**Workspace Developer Tools** *(Developer Mode)*
- OAuth Debug Panel
- API Request Inspector
- API Response Viewer
- Rate Limit Monitor
- Workspace Event Viewer
- Sync Status Dashboard
- Background Job Monitor
- Integration Health Dashboard
- Permission Inspector
- API Usage Metrics

Lands in Developer Mode alongside M5A's Agent Trace panel, following
the same pattern established there and generalized in §7
(Cross-Platform Systems) — every milestone that ships a subsystem
worth inspecting live adds its own Developer Mode section rather than
waiting on a dedicated milestone.

**Future AI Productivity Features** *(exploratory — not yet scheduled
to a specific milestone acceptance criterion; tracked here so they are
not lost)*
- Daily Briefings
- Meeting Preparation Assistant
- Daily Calendar Planning
- Inbox Prioritization
- Smart Scheduling Assistant
- AI Executive Assistant
- AI Project Coordinator
- Cross-Meeting Knowledge Extraction
- Workspace Knowledge Graph
- Organizational Memory

These build on M15 Personality Engine, M16 Reflection Engine, M17
Companion Intelligence, and M19 Intelligence Graph once those
milestones exist — Workspace Knowledge Graph and Organizational
Memory in particular are the Google Workspace-specific instance of
M19's broader Digital Twin substrate, not a competing data model.

**Architecture notes** *(binding constraints for whenever this module
is built, per §4 Engineering Standards and §11's "ports first,
adapters second" rule)*:
- Every Google service is a provider abstraction first — a
  `core.interfaces` Protocol per capability area (Calendar, Meet,
  Gmail, Drive, Docs, Sheets, Slides, Chat, Tasks, People), concrete
  adapters second. No Google SDK import outside `infrastructure/`.
- OAuth is centralized through this milestone's own OAuth flow (see
  the top-level M11 Key features above) — one authorization-code
  implementation reused across every Workspace API, not reimplemented
  per service.
- Every Workspace API surface is designed for future extension — new
  scopes/endpoints are additive to the provider interface, never
  breaking.
- Every service (Calendar, Meet, Gmail, Drive, Docs, Sheets, Slides,
  Chat, Tasks, People) is independently replaceable — disabling or
  swapping one never affects another.
- All integrations are wired through Dependency Injection
  (`core/di/container.py`), matching every other service in the
  codebase — no service imports a concrete Google adapter directly.
- Every service exposes a clean interface — one Protocol per
  capability area, mirroring the existing `ILLMProvider`/
  `IBrowserAutomation` pattern.
- All secrets (OAuth client credentials, refresh tokens) use the
  existing Secrets Management system (M14 Security Platform's OS
  keyring / `SecretProxy`) — never `.env` plaintext.
- **Provider Abstraction:** Google Workspace is the **first supported
  Productivity Provider**, not the only one by design. All
  functionality above is implemented through the provider
  abstractions listed here, never against the Google API surface
  directly from business-logic code. The architecture must let a
  future provider (see Future expansion, below) implement the
  identical `core.interfaces` Protocols this module defines — Calendar,
  Meeting, Mail, Drive/Storage, Document, Spreadsheet, Presentation,
  Chat, Tasks, People — **without modifying any existing business
  logic** that already consumes them (services, agent tools,
  automation workflows). A second provider is a new adapter
  registered in `core/di/container.py`, never a fork of the first
  one's code path.
- **Security — token lifecycle:** OAuth Token Rotation, Automatic
  Token Refresh, and Least Privilege Permissions (request only the
  scopes a connected feature actually needs, not the broadest
  Workspace scope available) are non-negotiable, not opt-in
  hardening.
- **Security — secrets:** Secret Rotation, Credential Encryption, and
  a Secure Local Credential Cache (encrypted at rest, never a plain
  token file) apply to every stored Workspace credential, on top of
  the existing Secrets Management system referenced above.
- **Security — auditability:** Audit Logging of every Workspace API
  call feeds the same M14 Security Platform audit log as every other
  auditable action in the system — not a separate, Workspace-only log.
- **Security — resilience:** API Retry Policies and API Circuit
  Breakers reuse this milestone's own top-level retry/backoff and
  monitoring infrastructure rather than a Workspace-specific
  reimplementation; Request Idempotency is required on every
  write-side Workspace API call (event creation, email send, task
  creation) so a retried request after a network failure can never
  double-create the same artifact.

**Future expansion:** this same provider-abstracted architecture is
designed to extend, without major architectural changes, to
**Microsoft 365, Outlook, Teams, OneDrive, Slack, Notion, Jira,
Trello, ClickUp, Zoom, Discord, Dropbox, Box, Confluence, and Asana**
— each a new adapter behind the same `core.interfaces` contracts this
module establishes, not a parallel integration pattern built from
scratch.

**Dependencies:** this milestone's own top-level OAuth/API Gateway/
webhooks/retry/caching (no longer a separate M9 dependency — see M11's
Aug 2026 retitling note), M3 / M10A (Memory Platform / Universal
Search & Knowledge Platform — Workspace Memory Integration's storage
target), M14 (Security Platform — Secrets Management, audit log), M7
(Workflow Intelligence — Workspace Automation's scheduling/multi-step
workflow engine).

**Module acceptance criteria:**
1. A user connects a Google account via OAuth and every listed
   Workspace API surface (Gmail, Calendar, Meet, Drive, Docs, Sheets,
   Slides, Chat, Tasks, People) is reachable through its own provider
   interface.
2. An AI Meeting Summary — with key decisions, action items, and
   deadlines extracted — is generated automatically from a completed
   Google Meet meeting and is memory-searchable afterward.
3. Disabling or swapping any single Workspace API adapter (e.g.
   Drive) does not affect any other connected service.
4. A unified Workspace Search query returns relevant results spanning
   at least three connected services (e.g. Gmail + Calendar + Drive)
   in one response.
5. A calendar-triggered workflow (e.g. "meeting ends" →notes generated
   → summary delivered → follow-up tasks created) completes
   end-to-end without manual intervention.
6. Every enterprise Workspace Administration feature is inert until
   its required admin/org permission scope is explicitly granted.
7. No Google credential or token is ever persisted outside the
   Secrets Management system.

### M11A — SEO Intelligence

**Objective:** a dedicated SEO/marketing-analytics vertical, riding on
M11's Integrations & Cloud Platform (OAuth + API Gateway; formerly a
separate M9 Integration Platform dependency, now part of M11 itself —
see M11's Aug 2026 retitling note) — expanded significantly beyond the
original "SEO Assistant" bullet it grew from (see §9).

**Key features:**
- Google Search Console integration.
- GA4 (Google Analytics 4) integration.
- Semrush integration.
- Ahrefs integration.
- Rank Tracking.
- Keyword Tracking.
- Competitor Analysis.
- Technical SEO auditing (on-page, crawlability, Core Web Vitals).
- Content Intelligence (gap analysis, topic clustering).
- Automated Reports — scheduled (via M7's Scheduler), delivered
  through chat or export.

**Dependencies:** M11 (Integrations & Cloud Platform — OAuth + API
Gateway for every listed integration; no longer a separate M9
dependency), M7 (Scheduler for automated reports).

**Complexity:** M.

**Acceptance criteria:**
1. A real Search Console + GA4 connection produces a combined ranking
   + traffic report for a query the user asks in chat.
2. A scheduled report is delivered automatically on the configured
   cadence.
3. Competitor analysis returns a structured, exportable comparison,
   not just prose.

### M11B — Productivity Suite

*(New lettered companion to M11, Aug 2026 — preserves the non-
integration half of the original M11 Productivity Platform's scope
(Tasks, Documents, Research Assistant, Coding Assistant, Command
Palette, Clipboard Manager, File Manager, Native notifications, Media
Controls) unchanged, after M11 itself was retitled Integrations &
Cloud Platform and absorbed the integration-facing half. Not a
renumbering — additive, per the "zero renumbering" rule this
migration pass follows throughout §8.)*

**Objective:** the everyday local-productivity surface — task
tracking, document/research/coding assistants, and the
system-integration primitives (Command Palette, Clipboard, File
Manager) every domain assistant rides on — distinct from M11's
external-account integrations.

**Key features:**
- Tasks — a personal to-do list that syncs with M3 memories (absorbs
  the previously-planned standalone "Task Manager").
- Documents — PDF/docx/xlsx ingestion + Q&A over embedded stores (the
  "Document Assistant").
- Research Assistant — web-search + citation compiler.
- Coding Assistant — repo-aware, uses ripgrep + tree-sitter.
- Command Palette (`Ctrl+Shift+P`) — fuzzy search over commands,
  conversations, memories, plugin actions; backed by M10A's Universal
  Search & Knowledge Platform (Command Search) rather than a
  standalone index.
- Clipboard Manager — history, pin, search, paste-back.
- File Manager tool — safe, scoped **local** filesystem access with
  previews — distinct from M11's cloud file-storage integrations
  (Google Drive and friends), which are a different concern entirely.
- Native notifications (Windows toast).
- Media Controls — system media keys, playback control UI over M11's
  Spotify integration.

**Dependencies:** M5, M3 (Tasks' memory sync), M10A (Command Palette's
search index), M11 (each domain assistant is naturally a plugin, and
Media Controls reads M11's Spotify integration).

**Complexity:** L *(intrinsically parallel — each domain assistant can
be built independently once the platform primitives — Command
Palette, Clipboard, File Manager — exist; unchanged from the original
M11's own complexity reasoning)*.

**Acceptance criteria:**
1. Command Palette returns results in <50 ms over 10,000 indexed
   items.
2. Clipboard history survives a restart.
3. Each domain assistant (Coding, Document, Research) passes its own
   golden-file smoke test.

### M12 — Smart Home & IoT Platform

*(Formerly "Smart Home Bridge" — see §9. Redesigned Jul 2026 from a
single-bus device bridge into a complete enterprise-grade Smart Home
platform — see the changelog addendum at the end of this document for
what changed and why. Home Assistant remains the primary bus for v1,
but the architecture below no longer assumes it's the *only* path to
a device the way the original "Smart Home Bridge" scope did.)*

**Objective:** a complete, enterprise-grade Smart Home & IoT platform
— local-first by default, cloud-optional, multi-home, and built so
that every device ecosystem (today's and tomorrow's — see Future
expansion below) is a provider-abstracted adapter, never a
special-cased integration. JARVIS remains a thin, replaceable
integration layer over each ecosystem, not a device driver.

**Key features** *(organized into 15 modules — see below for each
module's full feature list)*: Smart Home Core, Connectivity Layer,
Smart Lighting, Smart Locks, Sensors, Smart Cameras, Energy
Management, Appliance Control, Home Automation, AI Home Assistant,
Security & Safety, Remote Access, Smart Home Memory, Smart Home
Analytics, Developer Tools.

#### Smart Home Core
- Device Manager
- Device Registry
- Device Discovery
- Device Pairing
- Room Management
- Zone Management
- Device Groups
- Home Profiles
- Multi-Home Support
- Device Health Monitoring
- Device Status Dashboard

#### Connectivity Layer
- ESP32
- MQTT
- Wi-Fi
- Bluetooth LE
- Zigbee
- Z-Wave
- Matter
- Thread
- Home Assistant Integration
- Local Network Discovery
- Secure Device Provisioning

#### Smart Lighting
- On / Off Control
- Brightness
- RGB Control
- Color Temperature
- Lighting Scenes
- Adaptive Lighting
- Motion Activated Lighting
- Sunrise / Sunset Automation
- Group Lighting
- Room Lighting

#### Smart Locks
- Wi-Fi Locks
- Bluetooth Locks
- Fingerprint Locks
- PIN Locks
- NFC Locks
- Temporary Access Codes
- Guest Access
- Remote Unlock
- Auto Lock
- Access History
- Access Notifications

#### Sensors
- Motion Sensors
- Presence Sensors
- LD2410B Support
- Door Sensors
- Window Sensors
- Temperature
- Humidity
- Air Quality
- Water Leak Detection
- Smoke Detection
- Gas Detection
- Light Sensors
- Vibration Sensors

#### Smart Cameras
- Camera Integration
- Live Streaming
- Motion Detection
- Person Detection
- Package Detection
- Face Recognition (optional, off by default — see Architecture notes)
- Vehicle Detection
- Recording Management
- Event Recording
- Snapshot Capture

#### Energy Management
- Smart Plugs
- Smart Switches
- Energy Monitoring
- Power Usage Analytics
- UPS Monitoring
- Battery Monitoring
- Solar Monitoring
- Generator Monitoring
- Automatic Power Saving
- Load Scheduling

#### Appliance Control
- Smart Fans
- Smart AC
- Smart TV
- Smart Curtains
- Smart Blinds
- Smart Geysers
- Smart Pumps
- Smart Irrigation
- Smart Kitchen Devices

#### Home Automation
- Rule Engine
- Event-Based Automation
- Time-Based Automation
- Sensor-Based Automation
- Presence-Based Automation
- Geofencing
- Multi-Step Workflows
- Scene Automation
- Emergency Automation

Built on M7's Workflow Intelligence (Advanced Agent Runtime,
Scheduler, event-based workflow triggers) rather than a parallel
automation engine — the same reuse relationship M11's Workspace
Automation module has with M7.

#### AI Home Assistant
- Natural Language Commands
- Voice Control
- Context Awareness
- Routine Suggestions
- Predictive Automation
- Occupancy Detection
- Device Recommendations
- Energy Optimization
- Smart Notifications

Voice control rides on the existing M2 Voice Platform pipeline and
`AutomationService`; natural-language commands and predictive
automation are exposed as M5A agent tools, following the same
tool-registry pattern every other service uses (`agents/tools/`).

#### Security & Safety
- Intrusion Detection
- Emergency Alerts
- Fire Detection Integration
- Gas Leak Alerts
- Water Leak Alerts
- Panic Mode
- Vacation Mode
- Home Status Dashboard

Every item in this module is `safety_critical` by default (see
Architecture notes) — none of it silently auto-executes.

#### Remote Access
- Secure Remote Access
- Mobile Notifications
- Live Device Status
- Remote Device Control
- Remote Automation
- Secure Authentication
- Remote Diagnostics

Mobile notifications and remote control are the Smart Home-specific
consumer of M21's Mobile Platform transport, not a parallel remote-
access channel.

#### Smart Home Memory
- Device History
- Automation History
- Home Event Timeline
- Energy Usage History
- Security Event History
- Device Learning
- Usage Analytics

All of it flows into the existing M3 Memory Platform / M10 Knowledge
Engine via `MemoryService.remember()`, the same integration pattern
M11's Workspace Memory Integration already established — not a
separate Smart-Home-only store.

#### Smart Home Analytics
- Energy Trends
- Device Usage Statistics
- Automation Effectiveness
- Occupancy Analytics
- Device Reliability
- Predictive Maintenance
- Cost Savings Dashboard

Surfaces through M20A's Analytics Platform dashboard once that
milestone exists, the same way every other §7 Cross-Platform Systems
metric does — Smart Home Analytics doesn't stand up its own,
disconnected dashboard.

#### Developer Tools *(Developer Mode)*
- Device Simulator
- MQTT Debug Console
- Device Logs
- Event Viewer
- Automation Tester
- Integration Health Dashboard
- Device Diagnostics

Lands in Developer Mode alongside M5A's Agent Trace panel and M11's
Workspace Developer Tools, following the same established pattern
(§7 Cross-Platform Systems) — every milestone that ships a subsystem
worth inspecting live adds its own Developer Mode section.

**Architecture notes** *(binding constraints for whenever this
milestone is built, per §4 Engineering Standards and §11's "ports
first, adapters second" rule)*:
- All hardware integrations must use provider abstractions — a
  `core.interfaces` Protocol per device category (Lighting, Locks,
  Sensors, Cameras, Energy, Appliances), concrete adapters
  (ESP32/MQTT, Zigbee, Z-Wave, Matter, Thread, Home Assistant, and
  each direct-vendor integration) registered second, in
  `core/di/container.py`, exactly like every other provider in the
  codebase.
- Every device ecosystem must be independently replaceable — disabling
  or swapping one (e.g. moving from Home-Assistant-mediated Zigbee to
  a direct Zigbee2MQTT adapter) never affects another ecosystem or
  requires touching business logic that consumes the `core.interfaces`
  Protocol.
- Device communication must use clean interfaces — no service or
  agent tool ever imports a vendor SDK or speaks a vendor's wire
  protocol directly; that lives in `infrastructure/` only.
- **Local-first architecture is preferred.** A local bus (MQTT, direct
  LAN, Home Assistant running locally) is always the default path;
  JARVIS must remain functional for local device control with zero
  internet connectivity.
- **Cloud integrations remain optional** — a cloud-dependent vendor
  integration (e.g. a manufacturer app-only ecosystem) is an opt-in
  adapter, never a requirement for the platform's core functionality.
- All credentials (device pairing secrets, Home Assistant long-lived
  tokens, cloud-vendor API keys) use the existing Secrets Management
  system (M14 Security Platform's OS keyring / `SecretProxy`) — never
  `.env` plaintext, the same rule M11's Google Workspace module
  follows.
- Smart Home services integrate with the Event Bus — device state
  changes, automation triggers, and security/safety alerts are
  `EventBus` events, not direct cross-layer callbacks, matching every
  other cross-cutting notification in the system.
- All automations must be sandbox-compatible — every Home Automation
  rule (and every AI Home Assistant predictive-automation suggestion)
  must be dry-runnable through M13A's AI Sandbox before it is trusted
  to run unattended, the same discipline M13's Computer Control work
  requires.
- All Smart Home features integrate with Long-Term Memory — see Smart
  Home Memory above; there is no Smart-Home-specific memory store
  outside M3/M10A.
- The platform must support multiple homes without architectural
  changes — `Home Profiles` / `Multi-Home Support` (Smart Home Core)
  is a first-class dimension of the data model from day one, not a
  later retrofit; every device, room, zone, scene, and automation is
  scoped to a home.
- Face Recognition (Smart Cameras) is optional and off by default,
  consistent with M14 Security Platform's privacy posture — enabling
  it is an explicit, per-camera user action, never an implied default
  of "Camera Integration."

**Future expansion:** this same provider-abstracted architecture is
designed to extend, without requiring changes to the core
architecture, to **Philips Hue, TP-Link Kasa, Shelly, Sonoff, Aqara,
Tuya Smart, Samsung SmartThings, Google Home, Amazon Alexa, Apple
HomeKit, Ring, Arlo, Eufy, Xiaomi, and Bosch Smart Home** — each a new
adapter behind the same `core.interfaces` Protocols this milestone
establishes (direct integration, via Home Assistant, or both), not a
parallel integration pattern built from scratch. This mirrors exactly
how M11's Google Workspace module scopes its own future-provider
expansion (Microsoft 365, Slack, Notion, etc.) — Smart Home and
Productivity are sibling examples of the same "provider abstraction
first" rule from §4/§11.

**Dependencies:** M5 (Desktop Platform — Smart Home settings page),
M5A (Agent Runtime — Natural Language Commands / predictive
automation exposed as agent tools), M7 (Workflow Intelligence — the
Home Automation rule engine's scheduling and multi-step workflow
execution), M11 (Integrations & Cloud Platform — cloud-vendor OAuth/API
access where a device ecosystem requires it; formerly a separate M9
dependency, now part of M11 itself), M10A (Universal Search & Knowledge
Platform — Smart Home Memory's storage target), M14 (Security
Platform — credential
storage for device pairing secrets, Home Assistant tokens, and
cloud-vendor API keys).

**Complexity:** XL *(upgraded from the original scope's L — 15
feature modules across device management, six device categories,
automation, AI assistance, security, remote access, memory, and
analytics is materially larger than the original single-bus bridge;
sized consistently with this roadmap's other XL milestones, e.g. M19
Intelligence Graph, M21 Mobile Platform)*.

**Acceptance criteria:**
1. Home Assistant devices appear in the Smart Home page within 10s of
   pairing.
2. Scene invocation from chat succeeds and returns confirmation.
3. Any device flagged `safety_critical: true` (locks, water pump, and
   every Security & Safety module item by default) requires the M4
   confirm-before-run modal — no silent execution.
4. **Smart Home architecture is fully modular** — each of the 15
   feature modules above maps to an independently pluggable adapter
   set, verifiable by disabling any one module in the DI container
   without other modules failing.
5. **Provider abstraction is documented** — every device category in
   Connectivity Layer/Smart Lighting/Smart Locks/Sensors/Smart
   Cameras/Energy Management/Appliance Control has a named
   `core.interfaces` Protocol in this roadmap's architecture notes
   before any adapter is built against it.
6. **Local-first operation is documented and verifiable** — the
   platform's core device-control path (pairing, on/off, state read)
   functions with zero internet connectivity on the local-bus path
   (MQTT/LAN/local Home Assistant).
7. **Multi-home support is documented** — the data model (Home
   Profiles, rooms, zones, devices, scenes, automations) is scoped
   per-home from the architecture notes onward, with no later
   migration required to add a second home.
8. **Automation architecture is complete** — the Rule Engine's
   event-based, time-based, sensor-based, presence-based, and
   geofencing triggers are each named and mapped to M7's Workflow
   Intelligence engine, with no automation category left unspecified.
9. **Developer tooling is defined** — every Developer Tools module
   item (Device Simulator, MQTT Debug Console, Device Logs, Event
   Viewer, Automation Tester, Integration Health Dashboard, Device
   Diagnostics) has a stated Developer Mode home before implementation
   begins.
10. **Future vendor expansion is documented** — all 15 vendors listed
    under Future expansion are named with an explicit "no core
    architecture change required" commitment, matching the same
    commitment made for M11's provider list.

### M13 — Desktop Intelligence & Computer Control Platform

*(Formerly "Computer Control" — redesigned Jul 2026 from a
vision-plus-control feature list into a complete Desktop Intelligence
platform; see the changelog addendum at the end of this document for
what changed and why.)*

**Objective:** transform JARVIS from a desktop automation tool into an
intelligent desktop operating assistant — one that understands,
navigates, and interacts with desktop environments safely, going well
beyond M4's action-catalog automation and beyond the original scope's
"hands and eyes" framing. The agent gains structured knowledge of
*what* is on screen (UI Intelligence, Desktop Vision), *how* to act on
it across every major desktop UI framework (Desktop Control,
Application Intelligence), *how* to sequence that action safely
(Workflow Execution, Safety & Permissions), and *how* to remember and
improve over time (Desktop Memory, AI Desktop Assistant) — all while
remaining fully compatible with Clean Architecture, MVVM, Dependency
Injection, Provider Abstraction, the Event Bus, the M5A LangGraph
Agent Runtime, the existing M4 Automation Framework, the existing M6
Vision Framework, and the existing M14 Security Framework.

**Key features** *(organized into 10 modules — see below for each
module's full feature list)*: Desktop Control, UI Intelligence,
Desktop Vision, Application Intelligence, Workflow Execution, AI
Desktop Assistant, Desktop Memory, Safety & Permissions, Performance &
Reliability, Developer Tools.

#### Desktop Control
- Mouse Automation
- Keyboard Automation
- Clipboard Management
- Drag & Drop Automation
- File Explorer Automation
- Window Management
- Multi-Monitor Support
- Virtual Desktop Support
- System Tray Interaction
- Notification Interaction
- Hotkey Management

Extends, never replaces, M4's existing action catalog
(`ActionExecutor`, `IOSAutomation`) — mouse/keyboard/clipboard here
are the autonomous, vision-and-goal-driven counterpart to M4's
discrete, named actions, sharing the same `SafetyValidator`/
`PermissionGate` safety layer.

#### UI Intelligence
- Native UI Detection
- Accessibility API Integration
- UI Element Detection
- OCR Integration
- Screen Region Recognition
- Control Identification
- Menu Recognition
- Dialog Recognition
- Form Recognition
- Window Hierarchy Mapping

The primary "how does the agent know what it's looking at" layer —
see Architecture notes below for why Accessibility APIs are the
preferred source of truth here, with OCR/vision as fallback, not the
default.

#### Desktop Vision
- Live Screen Understanding
- Screenshot Understanding
- Window Context Detection
- Layout Analysis
- Chart Recognition
- Table Recognition
- Code Window Recognition
- IDE Awareness
- Browser Context Recognition
- Error Dialog Recognition

Built directly on M6's Vision & Multimodal framework
(`IVisionProvider`, `IOCRProvider`, screenshot/OCR pipeline) — this
module is Desktop Intelligence's *consumer* of M6's vision provider
abstraction, not a second, competing vision stack.

#### Application Intelligence
- Browser Automation
- File Explorer Intelligence
- Office Application Support
- IDE Support
- Terminal Automation
- PDF Viewer Support
- Media Player Support
- System Settings Control
- Application Profiles
- Custom Application Adapters

Browser Automation here builds on M4's existing `BrowserService`/
`PlaywrightBrowser` and M11's Browser Intelligence, rather than a
third browser-control path.

#### Workflow Execution
- Goal-Based Automation
- Multi-Step Task Execution
- Workflow Chaining
- Conditional Logic
- Parallel Execution
- Retry Policies
- Error Recovery
- Checkpoints
- Rollback Support
- Human Approval Steps

Built on M7's Workflow Intelligence (Advanced Agent Runtime,
parallel execution, Workflow Builder, Scheduler) — the same reuse
relationship M11's Workspace Automation and M12's Home Automation
modules already have with M7; Checkpoints/Rollback Support reuse M4's
existing `UndoManager` pattern rather than a new one.

#### AI Desktop Assistant
- Natural Language Desktop Commands
- Context-Aware Actions
- Smart Recommendations
- Desktop Search
- Workspace Suggestions
- Task Assistance
- Intelligent Navigation
- Activity Awareness
- Routine Learning

Natural-language desktop commands are exposed as M5A agent tools
through the same `agents/tools/registry.py` pattern every other
service uses; Routine Learning feeds, and is fed by, M16's Reflection
Engine rather than maintaining a separate learning loop.

#### Desktop Memory
- Application Usage History
- Workspace Profiles
- Recent Context
- Frequently Used Actions
- Workflow Memory
- Window State Memory
- User Preferences
- Automation History

Flows into the existing M3 Memory Platform / M10A Universal Search &
Knowledge Platform via `MemoryService.remember()`, the same
integration pattern M11's
Workspace Memory Integration and M12's Smart Home Memory already
established — no separate, disconnected Desktop-only store.

#### Safety & Permissions
- Protected Actions
- Confirmation Policies
- Dry Run Mode
- Safe Execution
- Permission Levels
- Risk Analysis
- Restricted Operations
- Secure Automation
- User Approval Rules

Dry Run Mode and Risk Analysis are the Desktop Intelligence-specific
entry points into M13A's AI Sandbox (Automation Simulator, Risk
Analysis, Rollback Testing) — this module does not reimplement
sandboxing, it plugs into it.

#### Performance & Reliability
- Action Queue
- Background Automation
- Input Scheduling
- Resource Optimization
- Retry Engine
- Failure Recovery
- Latency Monitoring
- Automation Metrics

Latency Monitoring and Automation Metrics surface through M20A's
Analytics Platform dashboard once that milestone exists, the same way
every other §7 Cross-Platform Systems metric does.

#### Developer Tools *(Developer Mode)*
- Automation Recorder
- UI Inspector
- Coordinate Viewer
- Window Inspector
- Desktop Event Viewer
- Replay Engine
- Automation Debugger
- Execution Timeline
- Performance Dashboard

Automation Recorder and Replay Engine are the Desktop Intelligence
instance of M7's Automation Recorder / M17A's Training Studio, not a
parallel recording mechanism; the rest lands in Developer Mode
alongside M5A's Agent Trace panel, M11's Workspace Developer Tools,
and M12's Smart Home Developer Tools, following the same established
§7 Cross-Platform Systems pattern.

**Architecture notes** *(binding constraints for whenever this
milestone is built, per §4 Engineering Standards and §11's "ports
first, adapters second" rule)*:
- Desktop interaction must remain provider-based — a
  `core.interfaces` Protocol per interaction category (UI detection,
  application control, vision), concrete adapters (per accessibility
  framework, per application type) registered second, in
  `core/di/container.py`, exactly like every other provider in the
  codebase.
- UI automation must support multiple frameworks — see Supported
  frameworks below; no module above hard-codes assumptions specific
  to one UI toolkit.
- **Accessibility APIs should be preferred whenever available** — UI
  Intelligence's Accessibility API Integration is the primary source
  of truth for control identification; it is faster, more reliable,
  and less brittle to visual changes than screen-scraping.
- **Vision should be used only when native APIs are unavailable** —
  Desktop Vision (and OCR Integration under UI Intelligence) is the
  documented fallback path for applications with no accessibility
  tree (some Electron/Chromium/Qt/custom-rendered apps), not the
  default path for every application.
- All desktop actions must integrate with the Event Bus — control
  actions, workflow-execution state changes, and safety/approval
  events are `EventBus` events, matching every other cross-cutting
  notification in the system.
- All automation should be compatible with the AI Sandbox — every
  Workflow Execution goal and every AI Desktop Assistant suggestion
  must be dry-runnable through M13A before it is trusted to run
  unattended, the same discipline this roadmap already requires of
  M12's Home Automation.
- Human approval should be supported for sensitive operations — Human
  Approval Steps (Workflow Execution) and User Approval Rules (Safety
  & Permissions) both route through the same M4 `PermissionGate`
  confirmation mechanism already used app-wide, not a new approval UI.
- Automation history should integrate with Long-Term Memory — see
  Desktop Memory above; there is no Desktop-only history store outside
  M3/M10A.
- Desktop context should integrate with the Knowledge Graph — Activity
  Awareness and Workspace Profiles (AI Desktop Assistant / Desktop
  Memory) feed M10A's Universal Search & Knowledge Platform as
  first-class context, not a side channel it is unaware of.
- All interactions should support future cross-platform expansion —
  the provider abstraction in the first bullet is what makes a future
  macOS/Linux desktop-control adapter possible without redesigning
  this milestone's architecture (see Supported frameworks below for
  the Windows-first framework list this ships against initially).

**Supported frameworks** *(planned adapter targets — each a concrete
adapter behind the same `core.interfaces` Protocols this milestone
establishes, without changing the core architecture)*:
- Windows UI Automation (UIA)
- Win32
- WPF
- WinUI
- UWP
- Electron applications
- Chromium-based applications
- Qt applications
- Java applications
- Accessibility APIs (the cross-framework fallback layer referenced
  in the Architecture notes above)

**Dependencies:** M5 (Desktop Platform — the shell this operates
within), M5A (Agent Runtime — desktop commands exposed as agent
tools), M6 (Vision & Multimodal — Desktop Vision's provider), M7
(Workflow Intelligence — Workflow Execution's engine), M11
(Integrations & Cloud Platform — Application Intelligence adapters
that need external API access, e.g. some Office/IDE integrations;
formerly a separate M9 dependency, now part of M11 itself), M10A
(Universal Search & Knowledge Platform — Desktop Memory's storage
target and Desktop context), M13A (AI
Sandbox — every automation's dry-run/risk-analysis path; built
alongside M13 rather than strictly before it, exactly as §16
Recommended Development Order already pairs them), M14 (Security
Platform — Safety & Permissions' credential and audit-log
integration).

**Complexity:** XL *(upgraded from the original scope's L — 10
feature modules spanning multi-framework UI automation, vision,
workflow execution, AI assistance, memory, safety, performance, and
developer tooling is materially larger than the original "hands and
eyes" scope; sized consistently with this roadmap's other XL
milestones, e.g. M12 Smart Home & IoT Platform, M19 Intelligence
Graph, M21 Mobile Platform)*.

**Acceptance criteria:**
1. The agent completes a multi-app task (e.g. "copy this table from
   the browser into a new spreadsheet") using only vision + control,
   no hand-authored recipe.
2. Multi-monitor window targeting is correct on a 3-monitor test rig.
3. Every autonomous-control action remains subject to M4's safety
   layer — nothing here bypasses `SafetyValidator`/`PermissionGate`.
4. **Desktop architecture is modular** — each of the 10 feature
   modules above maps to an independently pluggable adapter set,
   verifiable by disabling any one module in the DI container without
   other modules failing.
5. **Provider abstraction is documented** — every interaction category
   (UI detection, application control, vision) has a named
   `core.interfaces` Protocol in this roadmap's architecture notes
   before any adapter is built against it.
6. **Native UI automation is prioritized** — the architecture notes
   explicitly document Accessibility API Integration as the preferred
   path, with a stated fallback order, before Desktop Vision is
   invoked.
7. **Vision fallback is documented** — the exact condition under which
   Desktop Vision/OCR is used instead of native APIs (no accessibility
   tree available) is stated, not left implicit.
8. **Safety mechanisms are defined** — Protected Actions, Confirmation
   Policies, Dry Run Mode, Permission Levels, and Risk Analysis are
   each named and mapped to either M4's `PermissionGate` or M13A's AI
   Sandbox, with no safety category left unspecified.
9. **Human approval workflow exists** — Human Approval Steps and User
   Approval Rules are both documented as routing through the existing
   `PermissionGate` confirmation mechanism, not a new, undocumented
   approval surface.
10. **Developer tooling is defined** — every Developer Tools module
    item (Automation Recorder, UI Inspector, Coordinate Viewer,
    Window Inspector, Desktop Event Viewer, Replay Engine, Automation
    Debugger, Execution Timeline, Performance Dashboard) has a stated
    Developer Mode home before implementation begins.
11. **Desktop memory integration is documented** — every Desktop
    Memory item is mapped to M3/M10A with no separate storage model
    implied.
12. **Future cross-platform support is documented** — all 10
    Supported frameworks are named, with the provider-abstraction
    architecture note explicitly stated as the mechanism that would
    let a future non-Windows adapter be added without a redesign.
13. **Documentation is internally consistent** — every module,
    architecture note, dependency, and acceptance criterion above
    cross-references the specific existing milestone (M3, M4, M5, M5A,
    M6, M7, M9, M10, M13A, M14, M16, M17A, M20A) it reuses or feeds,
    with no dangling, unexplained reference.

### M13A — AI Sandbox

**Objective:** safe testing infrastructure for M13's inherently riskier
autonomous-control capabilities — paired with M13 rather than shipped
separately after the fact.

**Key features:**
- Automation Simulator — dry-run a plan against a virtual
  desktop/browser state without touching the real one.
- Risk Analysis — score a plan's blast radius before execution
  (extends M4's `SafetyValidator` risk levels).
- Rollback Testing — verify a plan's `UndoManager` path actually
  reverses it, in the sandbox, before it ever runs for real.
- Safe Execution mode — an opt-in "confirm every step" mode for
  testing new workflows before trusting them to run unattended.

**Dependencies:** M13 (this milestone exists specifically to de-risk
it), M4 (`SafetyValidator`/`UndoManager` foundations).

**Complexity:** M.

**Acceptance criteria:**
1. A simulated plan reports its intended actions without any real
   side effect occurring.
2. Risk analysis correctly flags a destructive action before
   execution, not after.
3. Rollback testing catches at least one intentionally-broken undo
   path in the sandbox's own test corpus.

### M13B — Self-Healing & Observability

*(New lettered companion to M13, Aug 2026 — introduced after M10B
completed, as a roadmap extension. Additive: **M13A (AI Sandbox) keeps
its identity and scope entirely unchanged**, per this roadmap's
zero-renumbering rule (§1). Lettered rather than decimal to match the
existing companion convention — M10A/M10B, M11A/M11B, M13A, M14A,
M17A, M20A, M23A/M23B.)*

**Status: 🔴 Planned.** Not started.

**Objective:** the foundational self-healing and observability subset,
pulled forward from **M18** (Self-Healing & Diagnostics Platform) and
**M20A** (Analytics & Observability Platform), so that every milestone
between here and those two — M14 Security, M15 Personality, M16
Reflection, M17 Companion Intelligence — is built on a runtime that
can already report its own health and recover from routine faults,
rather than having that visibility retrofitted underneath them
afterwards. **This milestone does not replace M18 or M20A**, and does
not restate their scope: they remain the full-scale realizations, the
same "foundation now, full platform later" relationship M10A already
holds with M19 (Knowledge Graph & Digital Twin Platform). M18's own
binding constraint carries here unchanged: self-healing repairs
*itself* — never the user's data, memories, personality, or security
policies without explicit authorization.

**Key features:**
- Health Monitoring — extends M9's already-shipped `HealthMonitor`
  with per-service health history; not a second monitor.
- Fault Detection & Recovery — automatic restart/backoff for a failed
  service, building on M9's Service Manager and Crash Recovery rather
  than duplicating either.
- Structured Telemetry — a metrics/trace surface over the existing
  `EventBus` and Runtime WebSocket relay, so observability is one more
  event category, never a parallel channel.
- Diagnostics Snapshot — a single exportable "what is wrong right now"
  bundle, extending M9's Developer Platform Tools (Debug Console,
  State Inspector, Performance Profiler) rather than a new viewer set.
- Degradation Reporting — reduced-capability states (a provider
  offline, a model unavailable) surfaced as real, explicit state, per
  §4's no-fake-data rule.

**Explicitly deferred to M18/M20A** (documented, not dropped):
Predictive Reliability, AI Diagnostics, Security Diagnostics, Recovery
Management at platform scale, Fleet Management, Enterprise Monitoring,
Remote Diagnostics, the Plugin Health Marketplace, and the full
analytics/dashboard platform all remain those milestones' own scope.

**Dependencies:** M9 (Health Monitor, Service Manager, Crash Recovery,
Developer Platform Tools — all ✅ shipped), M13 (paired with it, the
same way M13A is), M5.5 (the stabilization-pass findings M18's own
objective already builds on).

**Complexity:** M.

**Acceptance criteria:**
1. A service that fails is detected, reported over the existing
   Runtime WebSocket relay, and automatically recovered without a
   runtime restart.
2. A diagnostics snapshot exports real health/state data for every
   registered service — no placeholder or simulated values.
3. A degraded capability (e.g. an offline provider) surfaces as an
   explicit degraded state, never silently masked or faked.
4. Telemetry flows through the existing `EventBus`/WebSocket relay,
   verified by an integration test asserting no second, parallel event
   channel was introduced.

### M14 — Security Platform

*(Formerly "Security & Privacy Hardening" — see §9. Redesigned Jul
2026 from a single feature list into a complete enterprise-grade
Security Platform serving as the central, cross-cutting security
architecture for every subsystem in JARVIS OS — see the changelog
addendum at the end of this document for what changed and why.)*

**Aug 2026 frontend-migration review note.** The migration brief that
retitled M8–M11 separately asked to "CREATE NEW MILESTONE — Security &
Privacy" (Credential Vault, Encryption, Secrets Management, Permission
Auditing, Privacy Controls, Audit Logs, Secure Storage, Backup
Encryption, Consent Management). Reviewed against this milestone's
existing 12 modules below: every one of those items already exists
here verbatim or near-verbatim — Credential Vault and Secrets
Management (Secrets Management module), Encryption/Secure Storage/
Backup Encryption (Data Protection module: Encryption at Rest,
Encryption in Transit, Secure Local Storage, Secure Backups),
Permission Auditing/Audit Logs (Monitoring & Auditing module: Audit
Trail, Compliance Reports), Privacy Controls/Consent Management
(Privacy module: Consent Management, Data Retention Policies, Privacy
Dashboard). No new content was added — duplicating already-detailed
scope under a second milestone would violate this document's own
"no duplicate milestones" rule. This milestone remains Security
Platform, unchanged, per the "M14 remains Security Platform, do not
replace it" instruction.

**Objective:** make JARVIS safe to leave running on a personal machine
24/7, and — expanded scope — make security a **shared platform every
other milestone builds on**, not an isolated feature bolted onto one.
This milestone is the single place identity, authorization, secrets,
encryption, network security, AI-specific security, monitoring,
incident response, and privacy controls live, consumed identically by
M11 Integrations & Cloud Platform, M11B Productivity Suite, M12 Smart
Home & IoT Platform, M13 Desktop Intelligence & Computer Control
Platform, M6 Vision & Multimodal, M7 Workflow Intelligence, M9 Runtime
& Core Services, M10A Universal Search & Knowledge Platform, M13A AI
Sandbox, and M5A Agent Runtime — none of which implement their
own parallel security mechanism.

**Key features** *(organized into 12 modules — see below for each
module's full feature list)*: Security Core, Identity &
Authentication, Authorization & Permissions, Secrets Management, Data
Protection, Network Security, AI Security, Smart Home Security,
Monitoring & Auditing, Incident Response, Privacy, Developer Security
Tools.

#### Security Core
- Security Architecture
- Trust Model
- Security Policies
- Identity Layer
- Authorization Engine
- Authentication Framework
- Session Management
- Security Configuration

The foundation every other module in this milestone — and every
consuming milestone listed in the Objective above — builds on; no
subsystem defines its own trust model or authorization engine.

#### Identity & Authentication
- Local Authentication
- Password Management
- PIN Support
- Windows Hello Integration
- Biometric Authentication
- Multi-Factor Authentication
- Device Trust
- Recovery Methods

Extends, rather than replaces, M5's existing PBKDF2-HMAC-SHA256
Developer Mode gate — Developer Mode becomes one consumer of this
module's Authentication Framework, not a separate auth mechanism.

#### Authorization & Permissions
- Role-Based Access Control
- Permission Profiles
- Sensitive Action Approval
- Automation Permissions
- Plugin Permissions
- Device Permissions
- API Permissions
- Temporary Permissions

The unified model spanning plugin permissions (M8), smart-home
safety-critical gating (M12), automation risk levels (M4), and
desktop-control permission levels (M13) — one Authorization Engine
(Security Core), not four separate ad-hoc mechanisms.

#### Secrets Management
- API Key Storage
- Credential Vault
- Encryption Keys
- Secure Token Storage
- OAuth Token Protection
- Certificate Management
- Secret Rotation
- Backup Protection

The single secrets system every other milestone's own "use existing
Secrets Management" note already refers to — M11's Google OAuth
credentials, M12's device-pairing secrets and Home Assistant tokens,
and every provider API key across the codebase all resolve to this
module, not a per-milestone credential store.

#### Data Protection
- Encryption at Rest
- Encryption in Transit
- Secure Local Storage
- Database Protection
- Memory Protection
- File Encryption
- Secure Backups
- Data Integrity Verification

Encryption at Rest covers the SQLite database (SQLCipher optional
adapter) and Secure Backups integrates directly with M14A's Backup
Platform rather than defining a second backup-encryption scheme.

#### Network Security
- Secure Communications
- TLS Management
- Local Network Protection
- Remote Access Security
- Firewall Awareness
- API Security
- Certificate Validation
- Secure Pairing

API Security and Certificate Validation are the security layer
underneath every M11 Integrations & Cloud Platform connection; Remote Access
Security is the security layer underneath M21 Mobile Platform and M23
Distributed JARVIS's remote-device transport.

#### AI Security
- Prompt Injection Protection
- Tool Permission Validation
- Agent Isolation
- Model Access Policies
- AI Audit Logs
- Memory Protection
- Safe Tool Execution
- Hallucination Risk Controls

Formalizes the M5A `agents/prompting.py`
`UNTRUSTED_TOOL_OUTPUT_NOTICE` pattern (§7 Cross-Platform Systems)
into a reusable, tested module every future agent-tool milestone (M6
Vision, M11 Productivity, M12 Smart Home, M13 Desktop Intelligence)
must use rather than reinvent; Tool Permission Validation is the
Authorization Engine's view into the M5A tool registry
(`agents/tools/registry.py`).

#### Smart Home Security
- Device Authentication
- Secure Pairing
- Access Policies
- Home Profiles
- Remote Device Validation
- Emergency Override
- IoT Event Verification
- Secure Automation Rules

The security-specific counterpart to M12's own Smart Home Core
(`Home Profiles`, `Device Pairing`) and Security & Safety modules —
this module supplies the Identity/Authorization/Secrets primitives
M12 consumes, rather than M12 re-implementing device authentication
itself.

#### Monitoring & Auditing
- Security Logs
- Audit Trail
- Threat Detection
- Intrusion Detection
- Security Alerts
- Risk Dashboard
- Event Correlation
- Compliance Reports

Audit Trail is the same append-only, tamper-evident (hash chain) log
already scoped for this milestone since its original "Security &
Privacy Hardening" draft; Risk Dashboard and Compliance Reports
surface through M20A's Analytics Platform dashboard once that
milestone exists, the same way every other §7 Cross-Platform Systems
metric does — not a disconnected, security-only dashboard.

#### Incident Response
- Threat Response
- Emergency Lockdown
- Credential Revocation
- Recovery Procedures
- Rollback
- Backup Recovery
- Security Diagnostics
- Post-Incident Analysis

Emergency Lockdown generalizes the original scope's kill-switch
hotkey (`Ctrl+Alt+K` default — stops all agents + voice immediately)
into a full incident-response action, not just a hotkey; Rollback and
Backup Recovery integrate with M4's `UndoManager` and M14A's Backup
Platform respectively rather than duplicating either.

#### Privacy
- Local-First Privacy
- Consent Management
- Data Retention Policies
- Memory Privacy
- User Data Controls
- Export & Deletion
- Privacy Dashboard
- Transparency Reports

Memory Privacy closes the PII-redaction-before-embedding gap flagged
since M3 shipped; Export & Deletion is the privacy-guarantee
counterpart to M19 Intelligence Graph's "full export and full
deletion are both one action each" acceptance criterion — this module
is where that guarantee is actually implemented, M19 only consumes it.

#### Developer Security Tools *(Developer Mode)*
- Security Inspector
- Permission Viewer
- Vault Manager
- Audit Explorer
- Threat Simulator
- Policy Editor
- Security Testing Tools
- Compliance Dashboard

Lands in Developer Mode alongside M5's existing Security Center, M5A's
Agent Trace panel, M11's Workspace Developer Tools, M12's Smart Home
Developer Tools, and M13's Desktop Intelligence Developer Tools,
following the same established §7 Cross-Platform Systems pattern —
Security Center (M5) becomes the landing surface these tools extend,
not a separate panel.

**Architecture notes** *(binding constraints for whenever this
milestone is built, per §4 Engineering Standards and §11's "ports
first, adapters second" rule)*:
- **Security is a shared platform across all milestones** — M11, M12,
  M13, M6, M7, M9, M10, M13A, and M5A all consume this milestone's
  Identity/Authorization/Secrets/Encryption/AI-Security primitives;
  none defines its own parallel security mechanism (this is the
  single most important constraint in this milestone — every other
  note below exists to enforce it).
- All modules must integrate with the Event Bus — authentication
  state changes, permission denials, security alerts, and incident-
  response actions are `EventBus` events, matching every other
  cross-cutting notification in the system.
- Every subsystem must enforce permission validation — no service,
  agent tool, plugin, or automation action executes without passing
  through the Authorization Engine (Security Core), regardless of
  which milestone built it.
- Secrets must never be stored in plaintext — no `.env` plaintext
  secret, no hardcoded credential, no unencrypted token file anywhere
  in the codebase; every secret resolves through Secrets Management.
- Encryption should be provider-independent — Data Protection's
  encryption-at-rest/in-transit mechanisms are defined against a
  `core.interfaces` Protocol, not against one specific library (e.g.
  SQLCipher is the first adapter, not the only one the architecture
  allows).
- AI agents operate with least-privilege access — every M5A agent
  tool is granted only the permission scope its declared capability
  needs (mirroring M11's Google Workspace least-privilege OAuth-scope
  principle), never a broad default grant.
- Human approval is required for high-risk actions — Sensitive Action
  Approval (Authorization & Permissions) routes through the same M4
  `PermissionGate` confirmation mechanism already used app-wide across
  M11, M12, and M13's own human-approval features, not a new approval
  surface.
- All plugins execute inside the AI Sandbox — every M8 plugin's
  automation/agent-tool actions are dry-run/risk-analyzed through
  M13A before being trusted to run unattended, the same discipline
  this roadmap already requires of M12's Home Automation and M13's
  Workflow Execution.
- Audit logs integrate with Analytics & Observability — Monitoring &
  Auditing's Security Logs and Compliance Reports feed M20A's
  Analytics Platform, not a standalone security-only log viewer.
- Security architecture must support future distributed deployments —
  the Identity/Trust Model (Security Core) is designed so M23
  Distributed JARVIS's multi-device and enterprise-collaboration
  scenarios don't require a security-architecture redesign later.

**Future expansion:** this same provider-independent security
architecture is designed to extend, without changing the core
architecture, to **TPM, Hardware Security Modules, FIDO2, Passkeys,
Smart Cards, Enterprise SSO, Azure AD, LDAP, Active Directory, and
Remote Device Trust** — each a new Identity/Authentication or
Authorization adapter behind the same `core.interfaces` Protocols
this milestone establishes, not a parallel security pattern built
from scratch. This mirrors exactly how M11's Google Workspace module,
M12's Smart Home & IoT Platform, and M13's Desktop Intelligence
platform each scope their own future-provider expansion — every
"platform" milestone in this roadmap follows the same "provider
abstraction first" rule from §4/§11.

**Dependencies:** M9 (plugin permission model to unify with — kept
from the original scope, formerly a separate M8 dependency before M8
was retitled React Frontend & Desktop Experience), M5 (Desktop
Platform — Security Center is the Developer Security Tools landing
surface), M5A (Agent Runtime — AI Security's tool-permission
validation and agent isolation), M7 (Workflow Intelligence — Incident
Response's automated recovery workflows), M11 (Integrations & Cloud
Platform — Network Security's API/OAuth security layer, formerly a
separate M9 dependency), M10A (Universal Search & Knowledge Platform —
Privacy's data-retention and export/deletion guarantees over stored
knowledge), M11B (Productivity Suite — Secrets Management's OAuth
credential consumer, e.g. Media Controls' Spotify token), M12
(Smart Home & IoT Platform — Smart Home Security's consumer), M13
(Desktop Intelligence & Computer Control Platform — Safety &
Permissions' consumer), M13A (AI Sandbox — the dry-run/risk-analysis
path every sandboxed plugin and automation routes through).

**Complexity:** XL *(upgraded from the original scope's M — 12
feature modules serving as the shared security platform for nine
other milestones is materially larger than the original
single-feature-list scope; sized consistently with this roadmap's
other XL "platform" milestones, e.g. M12 Smart Home & IoT Platform,
M13 Desktop Intelligence & Computer Control Platform)*.

**Acceptance criteria:**
1. External penetration test of the local attack surface passes with
   no critical findings.
2. Kill-switch / Emergency Lockdown stops all in-flight agent runs
   and voice activity within 1 second.
3. Audit log tampering (direct file edit) is detectable on next read.
4. **Modular security architecture** — each of the 12 feature modules
   above maps to an independently pluggable adapter set, verifiable
   by disabling any one module in the DI container without other
   modules failing.
5. **Authentication is documented** — every Identity & Authentication
   item (local auth, PIN, Windows Hello, biometric, MFA, device
   trust, recovery) is named with a stated `core.interfaces` Protocol
   before any adapter is built against it.
6. **Authorization is documented** — the unified Authorization Engine
   and its consumers (plugin, automation, device, API, temporary
   permissions) are each explicitly cross-referenced to the milestone
   that produces the permission request (M4, M8, M11, M12, M13).
7. **Secrets management is documented** — every secret category (API
   keys, credentials, encryption keys, tokens, certificates) has a
   named storage path through the Credential Vault, with no plaintext
   fallback described anywhere in this milestone's own text.
8. **Encryption strategy is documented** — Encryption at Rest/in
   Transit is specified as provider-independent (a `core.interfaces`
   Protocol), with SQLCipher named as the first adapter, not the only
   one the architecture allows.
9. **AI security is documented** — Prompt Injection Protection, Tool
   Permission Validation, Agent Isolation, and Hallucination Risk
   Controls are each named and mapped to the existing M5A
   `agents/prompting.py` pattern or the M5A tool registry.
10. **Smart Home security is documented** — every Smart Home Security
    item is mapped to the specific M12 module (Smart Home Core,
    Security & Safety) it supplies primitives to.
11. **Privacy controls are documented** — Consent Management, Data
    Retention Policies, and Export & Deletion are each named and
    mapped to the M3/M10A data they govern, with no undocumented
    retention/deletion gap left open.
12. **Monitoring is documented** — every Monitoring & Auditing item is
    mapped to either the Security Center (M5) UI surface or the M20A
    Analytics Platform dashboard it eventually surfaces through.
13. **Incident response is documented** — Threat Response, Emergency
    Lockdown, Credential Revocation, and Rollback are each named with
    a stated trigger condition and a stated integration point (M4
    `UndoManager`, M14A Backup Platform).
14. **Developer tooling is documented** — every Developer Security
    Tools item has a stated Developer Mode home (extending M5's
    existing Security Center) before implementation begins.
15. **Internal consistency is verified** — every module, architecture
    note, dependency, and acceptance criterion above cross-references
    a specific existing milestone (M3, M4, M5, M5A, M6, M7, M8, M9,
    M10, M11, M12, M13, M13A, M14A, M19, M20A, M21, M23) it supplies
    security primitives to or consumes from, with no dangling,
    unexplained reference.

### M14A — Backup Platform

**Objective:** real, verified backup/restore/migration — paired with
M14 since encryption-at-rest changes what a correct backup even means.

**Key features:**
- Automatic Backup — scheduled (via M7), local-first.
- Snapshots — point-in-time, restorable independently of the
  automatic schedule.
- Migration — moving a full JARVIS install (data + config, minus
  secrets) between machines.
- Restore — one-click restore from any snapshot.
- Version History — multiple retained snapshots, not just "latest."

**Dependencies:** M14 (must understand the encryption-at-rest scheme
to back it up correctly), M7 (Scheduler for automatic backups).

**Complexity:** M.

**Acceptance criteria:**
1. A full backup → restore round-trip on a fresh machine reproduces
   the original install's data exactly.
2. Migration between two machines preserves conversations, memories,
   and settings, but never leaks secrets in the exported archive.
3. Restoring an older snapshot doesn't corrupt data written after it
   (no partial-state restore).

### M15 — Personality Engine

*(Redesigned Jul 2026 from a single configurable-personality feature
into a complete enterprise-grade Personality Engine — see the
changelog addendum at the end of this document for what changed and
why.)*

**Objective:** define how JARVIS communicates, adapts, remembers, and
builds long-term interaction with the user — not as *a* single
hard-coded personality, but as a modular framework capable of
supporting multiple personalities, adaptive behavior, emotional
intelligence, and future extensions. This milestone still rides on
the existing `UISettings.system_prompt` mechanism as its base
substrate (per the original scope), never a parallel one, but it is
no longer just a set of tunable dials on top of it — it is the
cross-cutting behavioral layer that M3 Memory, M5A Agent Runtime, M6
Vision & Multimodal, M7 Workflow Intelligence, M10A Universal Search &
Knowledge Platform, M11 Integrations & Cloud Platform / M11B
Productivity Suite, M12 Smart Home & IoT Platform, M13 Desktop
Intelligence, and M14 Security Platform all express themselves
through, rather than each defining their own tone/behavior
independently.

**Key features** *(organized into 10 modules — see below for each
module's full feature list)*: Personality Core, Conversation &
Language Intelligence, Relationship Intelligence, Adaptive Behaviour,
Emotional Intelligence, Voice Personality, Persona Management,
Proactive Intelligence, Ethics
& Safety, Developer Tools.

#### Personality Core
- Personality Profiles
- Personality Traits
- Communication Style
- Confidence Levels
- Conversation Rules
- Personal Values
- Custom Personality Presets
- Personality Configuration

The foundation every other module in this milestone builds on — and
the layer that continues to compile down to `UISettings.system_prompt`
at the M1 Chat Engine boundary, exactly as the original scope
specified, so no downstream consumer (M11's chat surface, M13's AI
Desktop Assistant, M12's AI Home Assistant) needs its own personality
substrate.

#### Conversation & Language Intelligence

*(Renamed Jul 2026 from "Conversation Engine" — multilingual
communication capabilities are merged directly into this module
rather than living as a separate "Hindi Module," "Marathi Module," or
standalone "Language Module." Language is part of *how* JARVIS
communicates, not a distinct subsystem — see the changelog addendum at
the end of this document for the full reasoning.)*

**Conversation**
- Natural Conversations
- Context-Aware Replies
- Multi-Turn Dialogue
- Conversation Continuity
- Active Listening
- Clarification Handling
- Conversation Summaries

**Communication Style**
- Tone Adaptation
- Formal Mode
- Casual Mode
- Friendly Communication
- Professional Communication
- Humor Support
- Adaptive Speaking Style

**Multilingual Intelligence**
- English Support
- Hindi Support
- Marathi Support
- Hinglish Support
- Marathi-English Mixed Conversation
- Automatic Language Detection
- Automatic Response Language Matching
- User Preferred Language
- Temporary Language Switching
- Conversation Language Memory
- Multilingual Long-Term Memory
- Regional Accent Understanding
- Script Transliteration
- Translation Support
- Offline Language Packs

Humor Support remains an explicit, tunable dial, off by default —
carried forward unchanged from the original scope's own commitment
(see Acceptance criteria below).

**Conversation behaviour rules** *(language-switching behavior this
module must implement)*:
- If the user explicitly says "Speak in Hindi," JARVIS immediately
  switches to Hindi for both text and voice until instructed
  otherwise.
- If the user explicitly says "Speak in Marathi," JARVIS immediately
  switches to Marathi.
- If the user explicitly says "Speak in English," JARVIS immediately
  switches to English.
- If the user naturally starts speaking Hindi, JARVIS automatically
  detects Hindi and responds in Hindi.
- If the user naturally starts speaking Marathi, JARVIS automatically
  detects Marathi and responds in Marathi.
- If the user naturally speaks English, JARVIS responds in English.
- If the conversation mixes languages (Hinglish or Marathi-English),
  JARVIS naturally continues using the same mixed language style
  unless the user explicitly requests another language.

**Language is communication-only, never intelligence-altering.**
Changing language must never change Personality, Behaviour, Emotional
Intelligence, Reasoning, Decision Making, Long-Term Memory, Knowledge,
Safety Policies, Workflow Capabilities, Smart Home Behaviour, Desktop
Behaviour, or Productivity Features — language changes **how** JARVIS
communicates, never **what** it knows, decides, or is willing to do.
Personality and intelligence remain identical across every supported
language (see Architecture notes below and Acceptance criteria).

#### Relationship Intelligence
- User Familiarity
- Shared Experience Memory
- Preference Awareness
- Personal Context
- Long-Term Relationship Building
- Interaction History
- Trust Development
- Personal Milestones

Sourced from M3 Memory Platform and M10A Universal Search & Knowledge
Platform as durable personalization facts, not a separate preferences
store — the same
non-negotiable the original scope already established for
Preferences, now generalized across the whole module.

#### Adaptive Behaviour
- Communication Learning
- Preference Learning
- Routine Recognition
- Dynamic Personalisation
- Context Switching
- Behaviour Adjustment
- Feedback Integration
- Continuous Improvement

Routine Recognition and Continuous Improvement are the
Personality-Engine-specific consumers of M16's Reflection Engine
(habit recognition, learning feedback loops) once that milestone
exists — this module does not implement a second, competing learning
loop.

#### Emotional Intelligence
- Emotion Recognition
- Sentiment Awareness
- Empathetic Responses
- Encouragement
- Motivation
- Stress Detection
- Positive Reinforcement
- Emotional Boundaries

Tone-appropriate, informed by actual conversation context via M3/M10A
— not sentiment-analysis theater — carried forward unchanged from the
original scope's own framing; Emotional Boundaries is new: emotional
intelligence stays assistive, never manipulative (see Architecture
notes and Ethics & Safety below).

#### Voice Personality
- Voice Profiles
- Speaking Style
- Speech Pace
- Emotional Speech
- Pronunciation Preferences
- Conversation Flow
- Voice Customisation
- Voice Consistency

The Personality Engine's expression through the existing M2 Voice
Platform pipeline (`VoiceService`, TTS providers) — a personality
profile's tone/style carries through to speech, not just text; no
second voice-configuration system alongside M2's existing TTS
settings.

#### Persona Management
- Multiple Personas
- Persona Switching
- Scenario-Based Personas
- Work Mode
- Personal Mode
- Guest Mode
- Persona Templates
- Persona Import & Export

The concrete mechanism that makes "not a single hard-coded
personality" real — Guest Mode in particular must respect whatever
M14 Security Platform permission/session boundary is active (see
Architecture notes).

#### Proactive Intelligence
- Smart Suggestions
- Daily Briefings
- Contextual Recommendations
- Reminder Intelligence
- Habit Support
- Goal Tracking
- Wellness Suggestions
- Productivity Coaching

Daily Briefings and Contextual Recommendations are the Personality
Engine's voice for M17 Companion Intelligence and M20 Predictive
Intelligence's own proactive-suggestion features once those
milestones exist — this module supplies *how* a suggestion is
communicated, M17/M20 supply *what* the suggestion is.

#### Ethics & Safety
- Respectful Behaviour
- Privacy Awareness
- User Consent
- Emotional Safety
- Bias Mitigation
- Manipulation Prevention
- Sensitive Topic Handling
- Personality Guardrails

Manipulation Prevention and Personality Guardrails are the concrete
enforcement of "emotional intelligence should remain assistive, not
manipulative" (Architecture notes); Privacy Awareness and User Consent
route through M14 Security Platform's Privacy module rather than
defining a second consent mechanism.

#### Developer Tools *(Developer Mode)*
- Personality Editor
- Behaviour Simulator
- Prompt Testing
- Persona Debugger
- Personality Profiles Viewer
- Configuration Validator
- Conversation Replay
- Personality Analytics

Lands in Developer Mode alongside M5A's Agent Trace panel, M11's
Workspace Developer Tools, M12's Smart Home Developer Tools, M13's
Desktop Intelligence Developer Tools, and M14's Developer Security
Tools, following the same established §7 Cross-Platform Systems
pattern; Personality Analytics surfaces through M20A's Analytics
Platform dashboard once that milestone exists, the same way every
other §7 metric does.

**Architecture notes** *(binding constraints for whenever this
milestone is built, per §4 Engineering Standards and §11's "ports
first, adapters second" rule)*:
- Personality must remain modular and provider-independent — a
  `core.interfaces` Protocol per behavioral concern (tone/style,
  emotional response, voice expression), concrete personality presets
  and personas registered second, in `core/di/container.py`, like
  every other provider in the codebase.
- Behaviour must be configurable without changing core architecture —
  a new personality preset, persona, or tone dial is data (a
  configuration/profile record), never a code change.
- Personality decisions should integrate with Long-Term Memory —
  Relationship Intelligence and Adaptive Behaviour both read and write
  through M3/M10A, not a Personality-Engine-only store.
- Relationship intelligence should build over time — Interaction
  History, Trust Development, and Personal Milestones accumulate
  across sessions by design; there is no "reset to zero familiarity"
  path except an explicit user action (Ethics & Safety's User
  Consent / Export & Deletion, via M14).
- Emotional intelligence should remain assistive, not manipulative —
  the single most important constraint on Emotional Intelligence and
  Proactive Intelligence; Manipulation Prevention (Ethics & Safety) is
  the enforcement mechanism, not an afterthought bolted onto the
  feature list.
- Personality should integrate with Vision, Voice, Desktop and Smart
  Home modules — M6's Vision Trace, M2's Voice Platform (via Voice
  Personality above), M13's AI Desktop Assistant, and M12's AI Home
  Assistant all express the active personality/persona rather than
  each having their own tone.
- Persona switching must preserve security policies — switching from
  Work Mode to Personal Mode to Guest Mode never grants or revokes a
  permission Persona Management itself doesn't own; the M14
  Authorization Engine remains the sole source of truth for what a
  session may do, regardless of active persona.
- Personality settings must support future cloud synchronization — the
  data model (Personality Core, Persona Management) is shaped so
  M23 Distributed JARVIS's multi-device sync can carry a personality
  profile between devices without a later redesign.
- Behaviour should be observable through Analytics & Observability —
  Personality Analytics (Developer Tools) and behavioral adaptation
  events are `EventBus`-published and feed M20A's Analytics Platform,
  matching every other §7 Cross-Platform Systems metric.
- Future personalities should be installable without modifying the
  core system — a new persona/personality pack (see Future expansion
  below) is a data package loaded through the same provider
  abstraction as any other adapter, not a fork of this milestone's
  code.
- Language processing must remain provider-independent — Speech
  Recognition, Translation, and Text Generation are each a
  `core.interfaces` Protocol (mirroring M2's existing `ISTTProvider`/
  `ITTSProvider` pattern), with concrete per-language/per-vendor
  adapters registered second; Speech Recognition providers, Translation
  providers, and Text Generation providers must each be independently
  replaceable without touching Conversation & Language Intelligence's
  own logic.
- Voice providers must support multiple languages — Voice Personality
  (above) and M2's Voice Platform TTS providers are selected/
  configured per active conversation language, not hard-coded to one.
- Automatic language detection should occur before response
  generation — Automatic Language Detection runs as the first step of
  the Conversation & Language Intelligence pipeline, so tone,
  emotional intelligence, and reasoning all operate knowing the
  active language rather than detecting it after the fact.
- **Personality must remain identical across every supported
  language** — the single most important constraint this update adds:
  Personality Core, Emotional Intelligence, Relationship Intelligence,
  reasoning, decision-making, Long-Term Memory, Knowledge, Ethics &
  Safety policies, and every consuming milestone's behavior (M7
  Workflow, M12 Smart Home, M13 Desktop Intelligence, M11
  Productivity) stay identical regardless of active language; language
  only changes *how* a response is communicated, never *what* JARVIS
  knows, decides, or is willing to do.
- Long-Term Memory should store semantic meaning rather than
  language-specific text — Multilingual Long-Term Memory and
  Conversation Language Memory persist meaning (via M3/M10A), not a
  language-locked transcript, so a fact learned in one language is
  recallable and expressible correctly in any other supported
  language.
- All modules (Voice, Vision, Desktop, Smart Home, Automation,
  Productivity) should automatically inherit the active conversation
  language — M2 Voice, M6 Vision, M13 Desktop Intelligence, M12 Smart
  Home, M4 Automation, and M11 Productivity all read the active
  language from this module rather than each tracking their own.
- New languages should be installable without changing the core
  architecture — an Offline Language Pack or a new language's
  Speech-Recognition/Translation/Text-Generation adapter set is a data
  package behind the existing `core.interfaces` Protocols, exactly
  like a new persona/personality pack above.

**Future expansion:** this same modular, provider-independent
architecture is designed to extend, without changing the core
architecture, to **Multilingual Personalities, Cultural Adaptation,
Team Personas, Family Profiles, Voice Cloning Interfaces, a
Personality Marketplace, Custom Persona Packs, Enterprise Personas, an
AI Character Framework, and Community Personality Templates** — each
a new persona/personality data package or adapter behind the same
`core.interfaces` Protocols this milestone establishes, not a parallel
personality system built from scratch. This mirrors exactly how M11's
Google Workspace module, M12's Smart Home & IoT Platform, M13's
Desktop Intelligence platform, and M14's Security Platform each scope
their own future-provider expansion — every "platform" milestone in
this roadmap follows the same "provider abstraction first" rule from
§4/§11.

**Future language expansion:** Conversation & Language Intelligence's
Multilingual Intelligence sub-module (English, Hindi, Marathi,
Hinglish, and Marathi-English mixed conversation at launch) is
designed to extend, without requiring changes to the core
architecture, to **Gujarati, Tamil, Telugu, Kannada, Malayalam,
Bengali, Punjabi, Urdu, Spanish, French, German, Japanese, Korean, and
Arabic** — each a new Offline Language Pack / Speech-Recognition /
Translation / Text-Generation adapter set behind the same
`core.interfaces` Protocols, per the provider-independence Architecture
note above.

**Dependencies:** M1 (extends the existing system-prompt mechanism —
kept from the original scope), M3 (Memory Platform — Relationship
Intelligence's durable-fact substrate), M5A (Agent Runtime —
personality/persona expressed through agent responses and tool
narration), M6 (Vision & Multimodal — personality expressed through
Vision Trace and multimodal responses), M7 (Workflow Intelligence —
Proactive Intelligence's scheduled briefings/suggestions), M10A
(Universal Search & Knowledge Platform — Relationship Intelligence and
Adaptive Behaviour's knowledge substrate, alongside M3), M11 / M11B
(Integrations & Cloud Platform / Productivity Suite — personality
expressed through the chat/productivity surface), M12
(Smart Home & IoT Platform — AI Home Assistant's personality
consumer), M13 (Desktop Intelligence & Computer Control Platform — AI
Desktop Assistant's personality consumer), M14 (Security Platform —
Persona Management's session/permission boundary and Ethics & Safety's
consent/privacy mechanism).

**Complexity:** XL *(upgraded from the original scope's M — this is no
longer a standalone feature but a large, cross-cutting behavioral
platform: 10 feature modules that every other user-facing milestone
listed in Dependencies expresses itself through, rather than one
milestone's own isolated concern. A tone/style dial is a small
feature; a modular personality framework that Vision, Voice, Desktop
Intelligence, Smart Home, and Productivity all render themselves
through — with its own relationship memory, emotional-safety
guardrails, multi-persona switching bound to security policy, and a
marketplace-ready extension model — is platform-scale, sized
consistently with this roadmap's other XL "platform" milestones, e.g.
M12 Smart Home & IoT Platform, M13 Desktop Intelligence & Computer
Control Platform, M14 Security Platform)*.

**Acceptance criteria:**
1. Switching personality profiles measurably changes response style
   within the same conversation.
2. A stated preference ("keep answers short") persists across
   sessions without being restated.
3. Humor stays off unless explicitly enabled — no accidental tone
   regression for users who never opted in.
4. **Personality architecture is modular** — each of the 10 feature
   modules above maps to an independently pluggable adapter/profile
   set, verifiable by disabling any one module in the DI container
   without other modules failing.
5. **Multiple personas are supported** — Work Mode, Personal Mode, and
   Guest Mode each produce independently verifiable behavior/tone
   differences, and Persona Switching preserves whichever M14
   permission boundary was already active.
6. **Adaptive behaviour is documented** — Communication Learning,
   Preference Learning, and Routine Recognition are each named and
   mapped to their M3/M10A data source and, where applicable, to M16's
   Reflection Engine.
7. **Relationship intelligence is documented** — every Relationship
   Intelligence item is mapped to the specific M3/M10A storage it reads
   and writes, with no separate Personality-only relationship store
   implied.
8. **Emotional intelligence is documented** — Emotion Recognition,
   Sentiment Awareness, and Emotional Boundaries are each named with
   an explicit non-manipulation constraint cross-referenced to Ethics
   & Safety.
9. **Voice personality is documented** — every Voice Personality item
   is mapped to the existing M2 Voice Platform pipeline it extends,
   with no second voice-configuration system implied.
10. **Proactive intelligence is documented** — Daily Briefings,
    Contextual Recommendations, and Goal Tracking are each mapped to
    the M7/M17/M20 milestone that supplies the underlying
    scheduling/prediction, with this module supplying only how it's
    communicated.
11. **Ethics & safety are documented** — Bias Mitigation, Manipulation
    Prevention, and Personality Guardrails are each named as the
    concrete enforcement of the Architecture notes' "assistive, not
    manipulative" constraint.
12. **Developer tools are documented** — every Developer Tools item
    has a stated Developer Mode home before implementation begins.
13. **Cross-milestone integrations are documented** — personality
    expression through M6 Vision, M2 Voice, M12 Smart Home, and M13
    Desktop Intelligence is each explicitly named, with no consuming
    milestone left to infer its own tone independently.
14. **Internal consistency is verified** — every module, architecture
    note, dependency, and acceptance criterion above cross-references
    a specific existing milestone (M1, M2, M3, M5A, M6, M7, M10, M11,
    M12, M13, M14, M16, M17, M20, M20A, M23) it integrates with, with
    no dangling, unexplained reference.
15. **Roadmap formatting is preserved** — this entry follows the exact
    module/Architecture-notes/Future-expansion/Dependencies/
    Complexity/Acceptance-criteria structure established by M11's
    Google Workspace module, M12, M13, and M14.

### M16 — Reflection Engine

*(Redesigned Jul 2026 from a single learning-feedback feature into a
complete enterprise-grade Reflection Engine — see the changelog
addendum at the end of this document for what changed and why.)*

**Objective:** enable JARVIS to analyze past interactions, workflows,
decisions, successes, failures, and long-term patterns to
continuously improve future assistance — building on, and now fully
realizing, M10's original reflection foundation. Reflection is an
internal intelligence layer that works *alongside* M3 Memory, M15
Personality, M10 Knowledge, M20A Analytics, and M5A Agent Runtime,
never in place of any of them: it improves performance without
changing the user's data, memories, personality, or security
policies. Reflection observes and recommends; it does not silently
rewrite what JARVIS remembers, who JARVIS is, or what JARVIS is
permitted to do.

**Key features** *(organized into 10 modules — see below for each
module's full feature list)*: Reflection Core, Conversation
Reflection, Workflow Reflection, Knowledge Reflection, Behaviour
Reflection, Learning & Improvement, Goal Reflection, Reflection
Analytics, Safety & Governance, Developer Reflection Tools.

#### Reflection Core
- Reflection Architecture
- Reflection Scheduler
- Reflection Policies
- Reflection Sessions
- Reflection History
- Reflection Configuration
- Manual Reflection
- Automatic Reflection

The foundation every other module in this milestone builds on;
Reflection Scheduler is the M7 Workflow Intelligence consumer that
runs Automatic Reflection on a cadence, the same reuse relationship
every other scheduled capability in this roadmap already has with M7.

#### Conversation Reflection
- Conversation Review
- Response Quality Analysis
- Context Retention Review
- Missed Intent Detection
- Clarification Analysis
- Communication Improvement
- User Satisfaction Signals
- Language Consistency Analysis

Language Consistency Analysis is the reflection-side check on M15's
Conversation & Language Intelligence module — verifying the
personality-across-languages invariant M15 establishes is actually
holding in practice, not re-implementing language handling itself.

#### Workflow Reflection
- Workflow Success Analysis
- Failed Workflow Review
- Automation Optimization
- Task Efficiency Analysis
- Workflow Bottleneck Detection
- Reusable Workflow Discovery
- Retry Pattern Analysis
- Workflow Recommendations

Analyzes M7 Workflow Intelligence and M4 Automation Platform execution
history; Workflow Recommendations are suggestions surfaced to the
user or to M7's Workflow Builder, never an automatic rewrite of an
existing workflow.

#### Knowledge Reflection
- Knowledge Gap Detection
- Duplicate Knowledge Detection
- Knowledge Validation
- Memory Consistency Review
- Knowledge Confidence Scoring
- Knowledge Relationship Discovery
- Knowledge Quality Monitoring
- Knowledge Evolution

Reads M10A's Universal Search & Knowledge Platform and M3's Memory Platform to analyze
quality and structure — per the Architecture notes below, this module
never rewrites a memory or knowledge-graph entry automatically; every
finding here is a recommendation back to the user or to M10, not a
silent mutation.

#### Behaviour Reflection
- Behaviour Consistency
- Personality Consistency
- Emotional Response Review
- Communication Style Review
- Proactive Behaviour Review
- User Preference Alignment
- Decision Pattern Review
- Adaptive Behaviour Insights

The reflection-side audit of M15 Personality Engine's own Adaptive
Behaviour and Emotional Intelligence modules — checking that
personality stays consistent and assistive over time, not a second
personality-decision engine competing with M15.

#### Learning & Improvement
- Experience Learning
- Pattern Recognition
- Routine Discovery
- Preference Learning
- Continuous Optimisation
- Recommendation Generation
- Reflection-Based Learning
- Improvement Suggestions

Feeds M15's Adaptive Behaviour (Routine Recognition, Continuous
Improvement) and M17 Companion Intelligence's proactive suggestions —
this module supplies the *learning signal*, M15/M17 supply how it's
expressed to the user.

#### Goal Reflection
- Goal Progress Review
- Habit Tracking
- Long-Term Objective Review
- Milestone Analysis
- Success Measurement
- Missed Goal Detection
- Progress Forecasting
- Goal Recommendations

Generalizes the original scope's Goal Tracking into a full review
discipline, still checked in on by M17 Companion Intelligence exactly
as the original scope specified — this module tracks and analyzes
progress, M17 is where a check-in is actually surfaced to the user.

#### Reflection Analytics
- Reflection Metrics
- Learning Metrics
- Workflow Metrics
- Behaviour Metrics
- Trend Analysis
- Improvement Reports
- Performance Dashboards
- Reflection Timeline

Surfaces through M20A's Analytics Platform dashboard once that
milestone exists, the same way every other §7 Cross-Platform Systems
metric does — Reflection Analytics does not stand up its own,
disconnected dashboard.

#### Safety & Governance
- Reflection Permissions
- Privacy Controls
- User Approval Policies
- Sensitive Data Protection
- Reflection Audit Logs
- Data Retention Rules
- Explainable Reflections
- Reflection Guardrails

Every item here routes through M14 Security Platform's existing
Authorization Engine, Privacy module, and Audit Trail rather than
defining a second permissions/audit system — Reflection Guardrails is
the concrete enforcement of "recommend, never silently change" (see
Architecture notes).

#### Developer Reflection Tools *(Developer Mode)*
- Reflection Viewer
- Reflection Explorer
- Learning Timeline
- Reflection Debugger
- Improvement Simulator
- Reflection Logs
- Policy Editor
- Reflection Dashboard

Lands in Developer Mode alongside M5A's Agent Trace panel, M11's
Workspace Developer Tools, M12's Smart Home Developer Tools, M13's
Desktop Intelligence Developer Tools, M14's Developer Security Tools,
and M15's Personality Developer Tools, following the same established
§7 Cross-Platform Systems pattern.

**Architecture notes** *(binding constraints for whenever this
milestone is built, per §4 Engineering Standards and §11's "ports
first, adapters second" rule)*:
- Reflection must remain independent of Long-Term Memory storage — the
  Reflection Engine reads M3/M10A through their existing repository/
  service interfaces; it does not maintain a parallel copy of memory
  or knowledge data.
- Reflection analyzes memories but does not rewrite them
  automatically — Knowledge Reflection's findings (gaps, duplicates,
  inconsistencies) are surfaced as recommendations to the user or to
  M10, never applied as a silent, unattended mutation of stored
  memory.
- Reflection should generate recommendations rather than silently
  changing behaviour — the single most important constraint in this
  milestone; Workflow Recommendations, Goal Recommendations, and
  Improvement Suggestions are all read-only outputs a human (or an
  explicit downstream milestone like M15/M17) chooses whether to act
  on.
- Reflection integrates with the Agent Runtime — Reflection Sessions
  and Automatic Reflection run as M5A agent-orchestrated tasks
  (scheduled via M7), using the same tool-registry pattern every other
  service uses, not a separate execution engine.
- Reflection integrates with Analytics & Observability — Reflection
  Analytics (above) is `EventBus`-published and feeds M20A, matching
  every other §7 Cross-Platform Systems metric.
- Reflection integrates with the Knowledge Graph — Knowledge
  Reflection reads and proposes changes to M10's graph structure
  through M10's own interfaces, never a side channel M10 is unaware
  of.
- Reflection supports explainable AI principles — Explainable
  Reflections (Safety & Governance) means every recommendation states
  *why* it was generated (which data, which pattern), not an opaque
  suggestion with no traceable reasoning.
- Reflection should operate locally by default — consistent with M12's
  and M13's own local-first-preferred posture, Reflection Sessions run
  against local M3/M10A data with no required cloud dependency.
- Reflection must respect Security Platform policies — every
  Reflection module routes through M14's Authorization Engine, Privacy
  module (Sensitive Data Protection), and Audit Trail (Reflection
  Audit Logs), never defining its own permission or audit mechanism.
- Reflection must remain modular and provider-independent — a
  `core.interfaces` Protocol per reflection concern (conversation,
  workflow, knowledge, behaviour, goal), concrete analyzers registered
  second, in `core/di/container.py`, like every other provider in the
  codebase.

**Future expansion:** this same modular, provider-independent
architecture is designed to extend, without requiring changes to the
core architecture, to **Daily Reflection, Weekly Reflection, Monthly
Reflection, Goal Coaching, Team Reflection, Shared Reflection, an AI
Research Assistant, Personal Growth Insights, Reflection Plugins, and
Enterprise Reflection Reports** — each a new reflection cadence,
analyzer, or plugin behind the same `core.interfaces` Protocols this
milestone establishes, not a parallel reflection system built from
scratch. This mirrors exactly how M11's Google Workspace module, M12's
Smart Home & IoT Platform, M13's Desktop Intelligence platform, M14's
Security Platform, and M15's Personality Engine each scope their own
future-provider expansion — every "platform" milestone in this
roadmap follows the same "provider abstraction first" rule from
§4/§11.

**Dependencies:** M3 (Memory Platform — the primary data source, kept
from the original scope), M10A (Universal Search & Knowledge Platform foundation — kept
from the original scope), M5A (Agent Runtime — Reflection Sessions
run as orchestrated agent tasks), M7 (Workflow Intelligence —
Reflection Scheduler's cadence engine), M14 (Security Platform —
Safety & Governance's permission/privacy/audit mechanism), M15
(Personality Engine — Behaviour Reflection and Conversation
Reflection's subject), M20A (Analytics & Observability — Reflection
Analytics' dashboard).

**Complexity:** XL *(upgraded from the original scope's M — Reflection
is no longer a standalone learning-feedback feature but a
cross-cutting intelligence platform: 10 feature modules that observe
and improve conversation, workflow, knowledge, behaviour, and goal
outcomes across M3, M5A, M7, M10, M14, and M15 simultaneously, with
its own analytics, safety/governance, and developer tooling. A
feedback loop that "measurably changes future behavior" is a small
feature; a full observe-analyze-recommend layer spanning five other
milestones' own data and decisions — while remaining strictly
non-mutating and fully explainable — is platform-scale, sized
consistently with this roadmap's other XL "platform" milestones, e.g.
M12 Smart Home & IoT Platform, M13 Desktop Intelligence & Computer
Control Platform, M14 Security Platform, M15 Personality Engine)*.

**Acceptance criteria:**
1. A recognized habit is surfaced as a suggestion, not silently acted
   on (user stays in control).
2. A weekly experience summary is generated without manual triggering.
3. A tracked goal's progress is queryable at any time.
4. **Reflection architecture is modular** — each of the 10 feature
   modules above maps to an independently pluggable analyzer set,
   verifiable by disabling any one module in the DI container without
   other modules failing.
5. **Conversation reflection is documented** — every Conversation
   Reflection item is named and mapped to the M15 Conversation &
   Language Intelligence data it reviews.
6. **Workflow reflection is documented** — every Workflow Reflection
   item is mapped to the M4/M7 execution history it analyzes, with
   Workflow Recommendations explicitly stated as non-automatic.
7. **Knowledge reflection is documented** — every Knowledge Reflection
   item is mapped to the M3/M10A data it reads, with an explicit
   statement that no item in this module writes back automatically.
8. **Behaviour reflection is documented** — Behaviour Consistency and
   Personality Consistency are each mapped to the specific M15 module
   they audit, with no second personality-decision path implied.
9. **Learning mechanisms are documented** — Experience Learning,
   Pattern Recognition, and Reflection-Based Learning are each named
   with a stated output (a recommendation) and a stated consumer (M15
   Adaptive Behaviour or M17 Companion Intelligence).
10. **Goal reflection is documented** — every Goal Reflection item is
    mapped to its M17 Companion Intelligence check-in consumer, with
    this module's own scope limited to tracking and analysis.
11. **Reflection analytics are documented** — every Reflection
    Analytics item is mapped to the M20A Analytics Platform dashboard
    it eventually surfaces through.
12. **Safety controls are documented** — Reflection Permissions,
    Privacy Controls, and Reflection Guardrails are each named and
    mapped to the specific M14 Security Platform mechanism
    (Authorization Engine, Privacy module, Audit Trail) they route
    through.
13. **Developer tooling is documented** — every Developer Reflection
    Tools item has a stated Developer Mode home before implementation
    begins.
14. **Cross-milestone integrations are documented** — Reflection's
    relationship to M3, M5A, M7, M10, M14, M15, and M20A is each
    explicitly named, with no consuming or supplying milestone left
    to infer the integration independently.
15. **Internal consistency is verified** — every module, architecture
    note, dependency, and acceptance criterion above cross-references
    a specific existing milestone it reads from, writes
    recommendations to, or is governed by, with no dangling,
    unexplained reference.
16. **Roadmap formatting is preserved** — this entry follows the exact
    module/Architecture-notes/Future-expansion/Dependencies/
    Complexity/Acceptance-criteria structure established by M11's
    Google Workspace module, M12, M13, M14, and M15.

### M17 — Companion Intelligence

*(Redesigned Jul 2026 from a proactive-suggestions feature into a
complete enterprise-grade Companion Intelligence platform — see the
changelog addendum at the end of this document for what changed and
why.)*

**Objective:** define how JARVIS builds long-term, personalized,
trustworthy interaction with the user while respecting privacy,
autonomy, and security — the payoff milestone for M10/M15/M16's
foundations, still proactive and context-aware as originally scoped,
now formalized into relationship continuity, proactive assistance,
personalization, and long-term engagement as first-class platform
concerns. **This milestone does not replace M15 Personality Engine or
M16 Reflection Engine — it extends them.** M15 remains the source of
truth for *who* JARVIS is (tone, traits, persona); M16 remains the
source of truth for *what JARVIS has learned* (patterns,
recommendations); M17 is *how JARVIS applies both over time, in a
relationship, proactively* — synthesis, not replacement.

**Key features** *(organized into 10 modules — see below for each
module's full feature list)*: Companion Core, Relationship
Intelligence, Daily Companion, Personalization Engine, Proactive
Intelligence, Social & Communication Intelligence, Wellbeing Support,
Memory & Continuity, Safety & Boundaries, Developer Companion Tools.

#### Companion Core
- Companion Architecture
- Relationship Framework
- Interaction Lifecycle
- Companion Configuration
- User-Centric Design
- Personalization Policies
- Trust Framework
- Companion Profiles

The foundation every other module in this milestone builds on;
Trust Framework and Relationship Framework are the M17-specific
extension points that consume M15's Personality Core and M16's
Behaviour Reflection rather than redefining trust or personality from
scratch.

#### Relationship Intelligence
- Long-Term Relationship Building
- Trust Development
- Shared Experience Tracking
- Personal Context Awareness
- Interaction History
- Communication Familiarity
- Preference Evolution
- Milestone Recognition

Builds directly on M15's own Relationship Intelligence module
(User Familiarity, Trust Development, Personal Milestones) — this is
the same relationship substrate carried forward and applied over the
long term, not a second, competing relationship model.

#### Daily Companion
- Morning Briefings
- Evening Recaps
- Daily Planning
- Wellness Check-ins
- Goal Progress Updates
- Smart Reminders
- Calendar Awareness
- Contextual Suggestions

Calendar Awareness reads M11 Integrations & Cloud Platform's Google
Workspace Calendar Intelligence module; Goal Progress Updates read M16's Goal
Reflection — Daily Companion supplies the *when and how it's
communicated*, not a second calendar or goal-tracking data model.

#### Personalization Engine
- Routine Recognition
- Habit Understanding
- Adaptive Suggestions
- Workspace Preferences
- Smart Recommendations
- Lifestyle Preferences
- Interest Recognition
- Contextual Personalization

Routine Recognition and Habit Understanding consume M16's Learning &
Improvement module (Pattern Recognition, Routine Discovery) directly
— Personalization Engine is where a learned pattern becomes a
user-facing preference, not where pattern-learning itself happens.

#### Proactive Intelligence
- Context-Aware Assistance
- Predictive Suggestions
- Opportunity Detection
- Follow-up Recommendations
- Automation Suggestions
- Productivity Coaching
- Goal Support
- Preventive Notifications

Carries forward the original scope's Context Awareness and Predictive
Assistance unchanged in spirit — every suggestion here is offered, not
executed; Automation Suggestions route to M7 Workflow Intelligence /
M4 Automation Platform only after explicit user acceptance.

#### Social & Communication Intelligence
- Communication Style Adaptation
- Conversation Continuity
- Social Context Awareness
- Follow-up Tracking
- Contact Relationship Context
- Meeting Context Awareness
- Collaboration Support
- Conversation Summaries

Meeting Context Awareness and Contact Relationship Context read M11
Productivity Platform's Google Meet Intelligence and Google People
Intelligence modules directly, rather than maintaining a second
contacts/meetings model; Communication Style Adaptation defers to
M15's Conversation & Language Intelligence for the actual tone/
language mechanics.

#### Wellbeing Support
- Habit Encouragement
- Productivity Balance
- Wellness Reminders
- Break Suggestions
- Sleep Routine Awareness
- Stress Awareness
- Positive Reinforcement
- Goal Motivation

Stress Awareness and Positive Reinforcement consume M15's Emotional
Intelligence module rather than defining a second emotional-signal
pipeline; every Wellbeing Support item is a suggestion, never an
enforced behavior change (see Architecture notes).

#### Memory & Continuity
- Long-Term Context
- Conversation Continuity
- Cross-Session Awareness
- Preference Retention
- Semantic Memory Links
- Personal Timeline
- Important Event Tracking
- Memory Confidence

Reads M3 Memory Platform and M10A Universal Search & Knowledge Platform through their
existing interfaces — the same "no parallel data copy" discipline
M16's Reflection Engine already established for itself; Memory
Confidence surfaces M10's own confidence scoring, not a new one.

#### Safety & Boundaries
- User Consent
- Privacy Controls
- Emotional Boundaries
- Transparency
- Explainable Suggestions
- Companion Permissions
- Relationship Reset
- Data Ownership

Every item here routes through M14 Security Platform's existing
Authorization Engine and Privacy module rather than defining a second
consent/permission system; Relationship Reset and Data Ownership are
the Companion-specific instance of M14's Export & Deletion guarantee.

#### Developer Companion Tools *(Developer Mode)*
- Relationship Viewer
- Personalization Inspector
- Companion Simulator
- Behaviour Timeline
- Suggestion Explorer
- Trust Analytics
- Configuration Editor
- Companion Dashboard

Lands in Developer Mode alongside M5A's Agent Trace panel and every
other milestone's own Developer Tools section (M11, M12, M13, M14,
M15, M16), following the same established §7 Cross-Platform Systems
pattern; Trust Analytics and Companion Dashboard surface through
M20A's Analytics Platform once that milestone exists.

**Architecture notes** *(binding constraints for whenever this
milestone is built, per §4 Engineering Standards and §11's "ports
first, adapters second" rule)*:
- **Companion Intelligence extends Personality and Reflection without
  replacing them** — the single most important constraint in this
  milestone; M15 remains the source of truth for identity/tone, M16
  remains the source of truth for learned patterns, and no module
  above redefines either.
- Companion behaviour must remain transparent and explainable —
  Explainable Suggestions (Safety & Boundaries) means every proactive
  suggestion states *why* it was offered, mirroring M16's own
  Explainable Reflections principle.
- All proactive behaviour must respect user consent — Proactive
  Intelligence and Daily Companion features are opt-in per category,
  never enabled by default without explicit consent.
- Companion intelligence must never manipulate users — the same
  non-manipulation constraint M15 already places on Emotional
  Intelligence applies identically here; Wellbeing Support in
  particular must encourage, never pressure.
- Personalization should remain reversible — every Personalization
  Engine adaptation can be undone or reset by the user; nothing here
  is a one-way, irreversible profile change.
- Long-Term Memory should remain user-controlled — Memory & Continuity
  reads M3/M10A but every retention/deletion decision routes through
  M14's Privacy module and the user's own Data Ownership rights
  (Safety & Boundaries), never a Companion-only retention policy.
- Relationship intelligence should be based on explicit interactions
  rather than assumptions — Relationship Intelligence and Trust
  Development build from observed, actual interaction history, not
  inferred/assumed familiarity.
- Companion capabilities must integrate with Desktop, Smart Home,
  Productivity and Mobile modules — M13's AI Desktop Assistant, M12's
  AI Home Assistant, M11's Productivity surfaces, and M21's Mobile
  Platform (once it exists) all express Companion Intelligence rather
  than each building their own proactive-assistance layer.
- Security and Privacy policies always take precedence — wherever a
  Companion Intelligence feature and an M14 Security Platform policy
  conflict, M14 wins, without exception.
- Companion Intelligence must remain modular and provider-independent
  — a `core.interfaces` Protocol per companion concern (relationship,
  personalization, proactive suggestion, wellbeing), concrete
  companion behaviors registered second, in `core/di/container.py`,
  like every other provider in the codebase.

**Future expansion:** this same modular, provider-independent
architecture is designed to extend, without changing the core
architecture, to **Family Companion Profiles, Team Companion
Profiles, Multi-User Households, Shared Memories (opt-in),
Collaborative Planning, a Travel Companion, Health Companion
Integrations, an Education Companion, a Vehicle Companion, and
Plugin-Based Companion Skills** — each a new companion profile type or
skill behind the same `core.interfaces` Protocols this milestone
establishes, not a parallel companion system built from scratch. This
mirrors exactly how M11's Google Workspace module, M12's Smart Home &
IoT Platform, M13's Desktop Intelligence platform, M14's Security
Platform, M15's Personality Engine, and M16's Reflection Engine each
scope their own future-provider expansion — every "platform"
milestone in this roadmap follows the same "provider abstraction
first" rule from §4/§11.

**Dependencies:** M10A (Universal Search & Knowledge Platform — kept from the original
scope), M15 (Personality Engine — kept from the original scope, and
the milestone this one explicitly extends rather than replaces), M16
(Reflection Engine — kept from the original scope, and the other
milestone this one extends), M3 (Memory Platform — Memory &
Continuity's data source), M5A (Agent Runtime — proactive suggestions
and companion behavior expressed through agent tools), M7 (Workflow
Intelligence — Automation Suggestions' execution path once accepted),
M11 (Integrations & Cloud Platform — Daily Companion and Social &
Communication Intelligence's Calendar/Meet/People data), M12 (Smart
Home & IoT Platform — AI Home Assistant's companion consumer), M13
(Desktop Intelligence & Computer Control Platform — AI Desktop
Assistant's companion consumer), M14 (Security Platform — Safety &
Boundaries' consent/privacy/permission mechanism, which always takes
precedence).

**Complexity:** XL *(upgraded from the original scope's L — Companion
Intelligence is no longer a standalone proactive-suggestions feature
but a cross-cutting intelligence platform: 10 feature modules
synthesizing M3, M5A, M7, M10, M11, M12, M13, M14, M15, and M16 into
long-term relationship continuity, personalization, and proactive
assistance, while explicitly never replacing the two milestones (M15,
M16) it depends on most closely. A "surface a proactive suggestion"
feature is a small addition; a full relationship-continuity and
personalization platform that every other user-facing milestone
expresses itself through, bound by non-manipulation and
user-controlled-memory guarantees, is platform-scale, sized
consistently with this roadmap's other XL "platform" milestones, e.g.
M12 Smart Home & IoT Platform, M14 Security Platform, M15 Personality
Engine, M16 Reflection Engine)*.

**Acceptance criteria:**
1. A proactive suggestion is measurably relevant (user-accepted) more
   often than not in a dogfood period.
2. No proactive action executes without explicit confirmation — this
   milestone suggests, it does not act unattended.
3. Context awareness can be fully disabled via one settings toggle.
4. **Companion architecture is modular** — each of the 10 feature
   modules above maps to an independently pluggable adapter set,
   verifiable by disabling any one module in the DI container without
   other modules failing.
5. **Relationship intelligence is documented** — every Relationship
   Intelligence item is mapped to the M15 Relationship Intelligence
   module it builds on, with no second, competing relationship model
   implied.
6. **Personalization is documented** — every Personalization Engine
   item is mapped to its M16 Learning & Improvement data source, and
   is stated as reversible.
7. **Proactive assistance is documented** — every Proactive
   Intelligence item is stated as a suggestion, never an unattended
   action, with an explicit consent/opt-in requirement.
8. **Wellbeing support is documented** — every Wellbeing Support item
   is mapped to the M15 Emotional Intelligence signal it consumes,
   with an explicit non-manipulation, encouragement-only framing.
9. **Memory continuity is documented** — every Memory & Continuity
   item is mapped to the specific M3/M10A data it reads, with no
   Companion-only memory store implied.
10. **Safety boundaries are documented** — User Consent, Companion
    Permissions, and Relationship Reset are each named and mapped to
    the specific M14 Security Platform mechanism they route through.
11. **Privacy protections are documented** — Data Ownership and
    Privacy Controls are each mapped to M14's Privacy module, with an
    explicit statement that Security/Privacy policy always takes
    precedence over any Companion behavior.
12. **Developer tooling is documented** — every Developer Companion
    Tools item has a stated Developer Mode home before implementation
    begins.
13. **Cross-milestone integrations are documented** — Companion
    Intelligence's integration with M11 Productivity, M12 Smart Home,
    M13 Desktop Intelligence, and (once it exists) M21 Mobile Platform
    is each explicitly named, with no consuming milestone left to
    infer the integration independently.
14. **Internal consistency is verified** — every module, architecture
    note, dependency, and acceptance criterion above cross-references
    a specific existing milestone (M3, M5A, M7, M10, M11, M12, M13,
    M14, M15, M16, M20A, M21) it extends, reads from, or is governed
    by, with no dangling, unexplained reference.
15. **Roadmap formatting is preserved** — this entry follows the
    exact module/Architecture-notes/Future-expansion/Dependencies/
    Complexity/Acceptance-criteria structure established by M11's
    Google Workspace module, M12, M13, M14, M15, and M16.

### M17A — Training Studio

**Objective:** let the user directly teach JARVIS new skills, rather
than waiting for a built-in one — the natural companion to M7's
Automation Recorder, generalized beyond fixed macros.

**Key features:**
- Teach by Demonstration — record a multi-step task once, generalize
  it into a reusable skill (not just a literal macro replay).
- Workflow Recording — building on M7's recorder with generalization
  (parameterized inputs, not hardcoded values).
- Replay Engine — runs a taught skill against new inputs.
- Skill Builder — a UI for reviewing/editing a taught skill before
  saving it, and for sharing it as a local plugin (M8).

**Dependencies:** M7 (Automation Recorder foundation), M8 (a taught
skill can be packaged as a plugin).

**Complexity:** M.

**Acceptance criteria:**
1. A demonstrated task generalizes to at least one varied input
   without re-recording.
2. A taught skill exports as a valid M8 plugin manifest.
3. Skill Builder lets a user delete/edit a taught skill without
   touching a config file by hand.

### M18 — Self-Healing & Diagnostics Platform

*(Formerly "Diagnostics" — redesigned Jul 2026 from a permanent
health-monitoring subsystem into a complete enterprise-grade
Self-Healing & Diagnostics Platform — see the changelog addendum at
the end of this document for what changed and why.)*

**Objective:** monitor the health of JARVIS, detect failures, recover
from faults, diagnose issues, and maintain long-term reliability —
JARVIS can tell you (and itself) when something's wrong, still
building on M5.5's stabilization-pass findings exactly as originally
scoped, now formalized into a full platform rather than a single
permanent subsystem. **Self-Healing must improve system resilience
without modifying user data, memories, personality, or security
policies without explicit authorization** — this platform repairs
*itself*, never the user's data or JARVIS's identity/policies, without
the user's own consent.

**Key features** *(organized into 10 modules — see below for each
module's full feature list)*: Health Monitoring Core, Diagnostics
Engine, Self-Healing Engine, Predictive Reliability, Recovery
Management, Performance Optimization, Security Diagnostics, AI
Diagnostics, Developer Diagnostics Tools, Reporting & Analytics.

#### Health Monitoring Core
- System Health Monitoring
- Component Health Tracking
- Service Availability
- Heartbeat Monitoring
- Resource Monitoring
- Dependency Health
- Runtime Health
- Health Configuration

The foundation every other module in this milestone builds on;
continuous by design, not just the M5 Performance Monitor's point-in-
time snapshot — the original scope's "Health Monitoring" feature,
generalized into a full monitoring core.

#### Diagnostics Engine
- Error Detection
- Failure Classification
- Root Cause Analysis
- Diagnostic Reports
- Dependency Analysis
- Performance Diagnostics
- Environment Validation
- Diagnostic History

Diagnostic Reports carries forward the original scope's commitment
unchanged: exportable, shareable-for-support bundles, redacted of
secrets and raw prompt content by default (see Acceptance criteria).

#### Self-Healing Engine
- Automatic Recovery
- Intelligent Retry Policies
- Safe Restart Procedures
- Component Isolation
- Dependency Recovery
- Service Reinitialization
- Graceful Degradation
- Recovery Validation

Generalizes the original scope's Crash Recovery and Automatic Repair
(the M5.5 corrupted-`.env` case) from one-off fixes into a repeatable
pattern — Automatic Recovery only ever touches JARVIS's own runtime
state, never user data, memories, personality, or security policy
without explicit authorization (see Architecture notes).

#### Predictive Reliability
- Failure Prediction
- Resource Forecasting
- Early Warning Detection
- Health Trend Analysis
- Reliability Scoring
- Capacity Planning
- Preventive Maintenance
- Stability Forecasting

Consumes M16 Reflection Engine's Trend Analysis and Pattern
Recognition as its forecasting substrate rather than building a
second, competing pattern-detection engine — Predictive Reliability
is where reflection-derived patterns become reliability forecasts.

#### Recovery Management
- Checkpoints
- Rollback Management
- Configuration Recovery
- Safe Restore
- Session Recovery
- Workflow Recovery
- Backup Integration
- Recovery Verification

Checkpoints and Rollback Management reuse M4's existing `UndoManager`
pattern and M5A's LangGraph checkpointer where applicable; Backup
Integration is the Self-Healing consumer of M14A's Backup Platform,
not a second backup mechanism.

#### Performance Optimization
- Performance Monitoring
- Resource Optimization
- Memory Optimization
- CPU Optimization
- Disk Usage Monitoring
- Startup Optimization
- Background Task Optimization
- Performance Recommendations

Startup Optimization is the permanent, ongoing home for the kind of
work M5.5's own "~57% `MainWindow` construction speedup" fix
represented — a one-time audit finding generalized into continuous
monitoring, the same transformation this whole milestone represents
at platform scale.

#### Security Diagnostics
- Security Health Checks
- Permission Validation
- Credential Verification
- Secrets Integrity
- Plugin Validation
- Security Alerts
- Compliance Verification
- Threat Diagnostics

Every item here reads M14 Security Platform's own Monitoring &
Auditing and Incident Response modules rather than defining a second
security-check mechanism — Security Diagnostics is the
health-monitoring *view into* M14, not a competing implementation.

#### AI Diagnostics
- Agent Health
- Model Availability
- Prompt Pipeline Validation
- Tool Invocation Diagnostics
- Memory Access Validation
- Provider Health
- AI Performance Metrics
- Response Quality Monitoring

Reads M5A's `AgentState`/`AgentStepEvent` data and the M5A tool
registry directly — Agent Health and Tool Invocation Diagnostics are
this milestone's consumer of M5A's own Agent Trace panel data, not a
parallel agent-monitoring system.

#### Developer Diagnostics Tools *(Developer Mode)*
- Diagnostics Dashboard
- Health Explorer
- Recovery Timeline
- Failure Simulator
- Log Explorer
- Component Inspector
- Recovery Analytics
- Diagnostics Configuration

Lands in Developer Mode alongside M5A's Agent Trace panel and every
other milestone's own Developer Tools section (M11, M12, M13, M14,
M15, M16, M17), following the same established §7 Cross-Platform
Systems pattern — and is the natural, permanent home for what M5's
existing Logs & Diagnostics view and System Information view started.

#### Reporting & Analytics
- Health Reports
- Reliability Reports
- Incident Timeline
- Recovery Metrics
- Performance Dashboards
- Diagnostic Trends
- Service Availability Reports
- Executive Summary Reports

Surfaces through M20A's Analytics Platform dashboard once that
milestone exists, the same way every other §7 Cross-Platform Systems
metric does — Reporting & Analytics does not stand up its own,
disconnected dashboard.

**Architecture notes** *(binding constraints for whenever this
milestone is built, per §4 Engineering Standards and §11's "ports
first, adapters second" rule)*:
- Diagnostics must remain provider-independent — a `core.interfaces`
  Protocol per diagnostic concern (health, recovery, performance,
  security, AI), concrete monitors/healers registered second, in
  `core/di/container.py`, like every other provider in the codebase.
- **Self-Healing must never silently alter user data** — Automatic
  Recovery, Self-Healing Engine, and Recovery Management operate only
  on JARVIS's own runtime/component state; any action that would touch
  user data, memory, personality, or security policy requires explicit
  authorization, never happens silently.
- Automatic recovery should respect Security Platform policies — every
  Self-Healing Engine action routes through M14's Authorization Engine
  exactly as every other subsystem's actions do; recovery is not a
  privileged bypass of M14.
- Recovery operations should be fully auditable — every Self-Healing
  Engine and Recovery Management action is logged to M14's Audit Trail
  (Monitoring & Auditing), with no unattended-recovery action left
  unrecorded.
- Diagnostics integrate with Analytics & Observability — Reporting &
  Analytics and Predictive Reliability are `EventBus`-published and
  feed M20A, matching every other §7 Cross-Platform Systems metric.
- **Reflection Engine may recommend improvements but does not perform
  repairs** — M16 Reflection Engine's Workflow/Knowledge/Behaviour
  Reflection outputs are read as *input* to Predictive Reliability's
  forecasting; the actual repair action always belongs to this
  milestone's Self-Healing Engine, never to M16 itself, preserving the
  "recommend, never silently change" boundary M16 already established
  for its own scope.
- Recovery must support graceful degradation — when full recovery
  isn't possible, the Self-Healing Engine degrades a component to a
  reduced-but-functional state rather than failing the whole
  application, consistent with the existing `ShutdownManager`
  fault-isolation philosophy (M5.5).
- Diagnostic data should be privacy-aware — Diagnostic Reports and
  every Reporting & Analytics output are redacted of secrets and raw
  prompt content by default, routed through M14's Privacy module, the
  same non-negotiable the original scope already established.
- Developer tooling should expose explainable diagnostics — every
  Developer Diagnostics Tools item states *why* a health signal fired
  or a recovery action was taken, not just *that* it happened,
  mirroring M16's Explainable Reflections and M17's Explainable
  Suggestions principles.
- All monitoring should remain modular and independently replaceable —
  disabling or swapping any one of the 10 modules above never affects
  another module's ability to monitor, diagnose, or recover.

**Future expansion:** this same modular, provider-independent
architecture is designed to extend, without requiring changes to the
core architecture, to **Distributed Diagnostics, Multi-Device Health
Monitoring, Cloud Health Monitoring, Predictive Maintenance AI,
Enterprise Monitoring, Fleet Management, Automated Incident Reports,
Remote Diagnostics, a Plugin Health Marketplace, and Self-Healing
Extensions** — each a new monitoring/recovery adapter or plugin behind
the same `core.interfaces` Protocols this milestone establishes, not a
parallel diagnostics system built from scratch. This mirrors exactly
how M11's Google Workspace module, M12's Smart Home & IoT Platform,
M13's Desktop Intelligence platform, M14's Security Platform, M15's
Personality Engine, M16's Reflection Engine, and M17's Companion
Intelligence platform each scope their own future-provider expansion —
every "platform" milestone in this roadmap follows the same "provider
abstraction first" rule from §4/§11.

**Dependencies:** M5.5 (extends its findings into a permanent
subsystem — kept from the original scope), M14 (Security Platform —
redaction, authorization, and audit for every recovery action, kept
from the original scope), M5 (Desktop Platform — Performance Monitor
and Logs & Diagnostics are this milestone's permanent successor), M5A
(Agent Runtime — AI Diagnostics' data source), M7 (Workflow
Intelligence — Self-Healing Engine's retry/recovery scheduling), M10A
(Universal Search & Knowledge Platform — diagnostic/incident history
storage), M13 (Desktop
Intelligence & Computer Control Platform — Component Health Tracking's
consumer for desktop-control subsystems), M16 (Reflection Engine —
Predictive Reliability's forecasting substrate, read-only per the
"Reflection recommends, doesn't repair" note above), M17 (Companion
Intelligence — health/recovery events expressed through the companion
layer, e.g. a wellbeing-appropriate notice that JARVIS is recovering),
M20A (Analytics & Observability — Reporting & Analytics' dashboard).

**Complexity:** XL *(upgraded from the original scope's M —
Self-Healing & Diagnostics is no longer an isolated health-monitoring
feature but a cross-cutting platform supporting every subsystem: 10
feature modules spanning health, diagnostics, self-healing, predictive
reliability, recovery, performance, security, and AI — integrating
with M5, M5A, M7, M10, M13, M14, M16, M17, and M20A simultaneously,
while remaining strictly bounded from ever touching user data or
policy without authorization. "JARVIS can tell you when something's
wrong" is a small feature; a full observe-diagnose-heal-forecast
platform spanning nine other milestones' own subsystems — with its own
auditable recovery, privacy-aware reporting, and explainable developer
tooling — is platform-scale, sized consistently with this roadmap's
other XL "platform" milestones, e.g. M12 Smart Home & IoT Platform,
M14 Security Platform, M16 Reflection Engine, M17 Companion
Intelligence)*.

**Acceptance criteria:**
1. A simulated crash triggers automatic recovery without data loss.
2. A diagnostic report contains no secrets or raw prompt content by
   default.
3. At least one class of M5.5-style startup crash is now
   auto-repaired instead of merely logged.
4. **Modular diagnostics architecture is documented** — each of the
   10 feature modules above maps to an independently pluggable
   monitor/healer set, verifiable by disabling any one module in the
   DI container without other modules failing.
5. **Health monitoring is documented** — every Health Monitoring Core
   item is named with a stated `core.interfaces` Protocol before any
   adapter is built against it.
6. **Diagnostics engine is documented** — Error Detection, Failure
   Classification, and Root Cause Analysis are each mapped to the
   Diagnostic History they contribute to.
7. **Self-healing workflows are documented** — every Self-Healing
   Engine item is stated as operating only on JARVIS's own runtime
   state, with an explicit statement that user data/memory/personality/
   security policy changes always require authorization.
8. **Predictive reliability is documented** — every Predictive
   Reliability item is mapped to the M16 Reflection Engine data it
   consumes, with an explicit statement that M16 recommends and this
   milestone repairs.
9. **Recovery management is documented** — Checkpoints, Rollback
   Management, and Backup Integration are each mapped to the existing
   M4 `UndoManager`, M5A checkpointer, or M14A Backup Platform
   mechanism they reuse.
10. **Security diagnostics are documented** — every Security
    Diagnostics item is mapped to the specific M14 Security Platform
    module (Monitoring & Auditing, Incident Response) it reads from.
11. **AI diagnostics are documented** — every AI Diagnostics item is
    mapped to the M5A `AgentState`/`AgentStepEvent` data or tool
    registry it reads.
12. **Reporting is documented** — every Reporting & Analytics item is
    mapped to the M20A Analytics Platform dashboard it eventually
    surfaces through.
13. **Developer tooling is documented** — every Developer Diagnostics
    Tools item has a stated Developer Mode home before implementation
    begins, with an explicit explainability requirement.
14. **Cross-milestone integrations are documented** — Self-Healing &
    Diagnostics' relationship to M5, M5A, M7, M10, M13, M14, M16, M17,
    and M20A is each explicitly named, with no consuming or supplying
    milestone left to infer the integration independently.
15. **Internal consistency is verified** — every module, architecture
    note, dependency, and acceptance criterion above cross-references
    a specific existing milestone it reads from, repairs, or is
    governed by, with no dangling, unexplained reference.
16. **Roadmap formatting is preserved** — this entry follows the exact
    module/Architecture-notes/Future-expansion/Dependencies/
    Complexity/Acceptance-criteria structure established by M11's
    Google Workspace module, M12, M13, M14, M15, M16, and M17.

### M19 — Knowledge Graph & Digital Twin Platform

*(Redesigned Jul 2026 from "Intelligence Graph" — the full
digital-twin realization of the M10A Universal Search & Knowledge Platform's foundation —
into a complete enterprise-grade platform. See the changelog addendum
at the end of this document.)*

**Objective:** transform JARVIS from a collection of independent
modules into a unified intelligent system by connecting every entity,
memory, workflow, device, application, document, project, person,
automation, and relationship into a continuously evolving knowledge
graph. The Knowledge Graph becomes the central reasoning layer for
every future milestone; the Digital Twin is a live semantic model of
the user's digital ecosystem.

**Key features (organized into 10 modules):**

#### Knowledge Graph Core
- Graph Architecture
- Entity Management
- Relationship Engine
- Semantic Storage
- Knowledge Indexing
- Context Engine
- Graph Versioning
- Graph Configuration

The foundational graph substrate every other module in this milestone
— and every other milestone that reads from the graph — builds on;
this is the M10A Universal Search & Knowledge Platform's storage/indexing foundation
completed into a real queryable graph, not a second, competing data
model.

#### Digital Twin
- User Digital Twin
- Device Twin
- Desktop Twin
- Smart Home Twin
- Workspace Twin
- AI Twin
- Environment Twin
- Timeline Twin

Each twin is a semantic projection of Knowledge Graph Core data for
one facet of the user's ecosystem (M13 Desktop Intelligence, M12
Smart Home & IoT, M11B Productivity Suite, M15/M16/M17's AI-facing
state) — never a second copy of raw data, and always covered by the
same export/deletion guarantees as the rest of the graph.

#### Entity Intelligence
- People
- Organizations
- Projects
- Tasks
- Devices
- Applications
- Files
- Emails
- Calendar Events
- Notes
- Documents
- Locations
- Rooms
- Smart Devices

The canonical entity catalog the graph reasons over; entities are
sourced from existing subsystems (M3 Memory, M11 Integrations & Cloud
Platform, M11B Productivity Suite, M12 Smart Home & IoT, M13 Desktop
Intelligence) rather than re-collected independently.

#### Relationship Intelligence
- Entity Relationships
- Temporal Relationships
- Spatial Relationships
- Workflow Relationships
- Ownership
- Dependencies
- Communication Networks
- Context Relationships

How entities connect to one another over time, space, and workflow —
this is the "full version" of the Relationship Graph the pre-redesign
milestone described, now organized as its own module rather than a
single bullet.

#### Context Engine
- Current Context
- Historical Context
- Predicted Context
- Environmental Context
- Conversation Context
- Device Context
- Workspace Context
- Smart Home Context

Consumes M16 Reflection Engine and M17 Companion Intelligence's
situational-awareness data rather than re-deriving context
independently; this module is what lets the graph answer "what's
relevant right now," not just "what's true."

#### Semantic Search
- Natural Language Search
- Cross-System Search
- Relationship Search
- Timeline Search
- Similarity Search
- Contextual Search
- Graph Traversal
- Semantic Ranking

The query surface over the graph, exposed to the M5A Agent Runtime as
a tool the same way every other service is — agents reason over the
graph through this module, never by querying raw storage directly.

#### Timeline Intelligence
- Personal Timeline
- Activity Timeline
- Conversation Timeline
- Workflow Timeline
- Project Timeline
- Device Timeline
- Memory Timeline
- Event Correlation

Builds the Timeline Twin's underlying event stream and correlates it
across every subsystem that already timestamps its own activity (M3
Memory, M7 Workflow Intelligence, M13 Desktop Intelligence).

#### Knowledge Reasoning
- Graph Reasoning
- Context Inference
- Dependency Analysis
- Opportunity Detection
- Decision Support
- Cause & Effect Analysis
- Predictive Reasoning
- Recommendation Engine

The graph's inference layer — explicitly scoped as a foundation for
future AI planning capabilities (M20 Predictive Intelligence and
beyond), not itself an autonomous planner or decision-maker.

#### Knowledge Analytics
- Graph Health
- Entity Statistics
- Relationship Density
- Knowledge Coverage
- Confidence Scores
- Knowledge Growth
- Graph Quality
- Analytics Dashboard

Feeds M20A Analytics Platform and M18 Self-Healing & Diagnostics
Platform's reporting surfaces rather than shipping a competing
dashboard; this module is the graph's own health telemetry.

#### Developer Graph Tools *(Developer Mode)*
- Graph Explorer
- Entity Inspector
- Relationship Viewer
- Timeline Explorer
- Graph Debugger
- Query Console
- Graph Visualizer
- Knowledge Diagnostics

Developer Mode tooling for inspecting and debugging the graph
directly, following the same Developer Mode pattern established by
M5A's Agent Trace panel and M18's Developer Diagnostics Tools.

**Architecture notes** *(binding constraints for whenever this
milestone is implemented):*
- The Knowledge Graph is the central intelligence layer shared by all
  milestones — not a feature local to this one.
- Long-Term Memory (M3) stores experiences; the Knowledge Graph
  organizes and connects them. The graph never duplicates raw memory
  content, only structures references to it.
- The Digital Twin is a semantic representation of the user's
  ecosystem, not a duplicate of raw data.
- Every module should publish and consume graph events through the
  Event Bus, consistent with this roadmap's in-process eventing
  pattern used since M1.
- Graph entities should be provider-independent (no vendor-specific
  entity schema).
- Knowledge relationships should remain explainable and auditable —
  every inferred relationship traceable back to the facts that
  produced it.
- Graph reasoning should support future AI planning capabilities
  (explicitly scoped as a foundation for M20 and beyond, not itself a
  planner).
- Privacy and Security (M14) policies always apply to graph data —
  the graph is not a way around existing data-access controls.
- Knowledge Graph should support local-first operation with optional
  cloud synchronization, consistent with this roadmap's local-first
  charter (§1).
- New entity types and relationship models should be extensible
  without changing the core architecture.

**Future expansion:** Personal Knowledge Bases, Enterprise Knowledge
Graphs, Multi-User Graphs, Shared Digital Twins, Cross-Device
Knowledge Synchronization, an AI Planning Engine, Autonomous
Reasoning, Knowledge Plugins, Graph APIs, and Third-Party Knowledge
Connectors — all documented as future scope only; none require
changes to the core architecture defined above.

**Dependencies:** M3 (Memory), M5A (Agent Runtime), M6 (Vision &
Multimodal), M7 (Workflow Intelligence), M11 (Integrations & Cloud
Platform), M10A (Universal Search & Knowledge Platform — foundation),
M11B (Productivity Suite), M12 (Smart Home & IoT Platform), M13
(Desktop Intelligence), M14 (Security
Platform), M15 (Personality Engine), M16 (Reflection Engine — data
feeds the graph), M17 (Companion Intelligence — context data feeds the
graph), M18 (Self-Healing & Diagnostics).

**Complexity:** XL *(unchanged from the original scope's XL, with an
explicit rationale now documented: the Knowledge Graph is not a
standalone feature but the central intelligence platform that
connects every other subsystem in this roadmap — 10 feature modules
spanning graph storage, six twin types, 14 entity categories,
relationship/context/reasoning/analytics engines, and developer
tooling justifies the same XL tier as this roadmap's other
cross-cutting platforms, e.g. M14 Security Platform and M18
Self-Healing & Diagnostics Platform)*.

**Acceptance criteria:**
1. The digital twin answers a multi-hop relationship query ("who
   introduced me to X") correctly.
2. Full export and full deletion are both one action each, verified
   to leave nothing behind.
3. No digital-twin data leaves the device without explicit,
   per-destination user consent.
4. Knowledge Graph Core architecture is modular — each of the 10
   modules above can be developed, tested, and reasoned about
   independently.
5. Digital Twin architecture is documented, including how each of the
   6 twin types projects from Knowledge Graph Core data rather than
   duplicating it.
6. Entity Intelligence is documented, covering all 14 entity
   categories and their source subsystems.
7. Relationship Intelligence is documented, covering all 8
   relationship types.
8. Context Engine is documented, including its dependency on M16/M17
   context data.
9. Semantic Search is documented, including its exposure as an M5A
   agent tool.
10. Timeline Intelligence is documented, including cross-subsystem
    event correlation.
11. Knowledge Reasoning is documented, including its explicit scoping
    as a foundation for future AI planning rather than an autonomous
    planner.
12. Knowledge Analytics is documented, including how it feeds M20A and
    M18 rather than duplicating their dashboards.
13. Developer Graph Tools are documented as a Developer Mode surface.
14. Cross-milestone integrations (M3, M5A, M6, M7, M9, M10, M11, M12,
    M13, M14, M15, M16, M17, M18) are documented per module.
15. Internal consistency is verified across this milestone's modules,
    architecture notes, dependencies, and acceptance criteria.
16. Roadmap formatting is preserved and consistent with every other
    redesigned milestone in this document.

### M20 — Predictive Intelligence Platform

*(Redesigned Jul 2026 from "Predictive Intelligence" — turning the
M19 Knowledge Graph & Digital Twin Platform into forward-looking
assistance — into a complete enterprise-grade platform. See the
changelog addendum at the end of this document.)*

**Objective:** enable JARVIS to anticipate future needs, identify
opportunities, forecast outcomes, recommend actions, and optimize
long-term decision making on top of the M19 Knowledge Graph & Digital
Twin Platform. Prediction must always remain explainable,
user-controllable, privacy-aware, and recommendation-based — JARVIS
assists, it never automatically decides.

**Key features (organized into 10 modules):**

#### Prediction Core
- Prediction Engine
- Prediction Models
- Forecast Management
- Confidence Scoring
- Prediction Policies
- Prediction Scheduler
- Scenario Engine
- Prediction Configuration

The foundational prediction substrate every other module in this
milestone builds on, reading from M19's Knowledge Graph Core rather
than maintaining a second, competing model of the world.

#### Behaviour Prediction
- Routine Prediction
- User Intent Prediction
- Workflow Prediction
- Habit Forecasting
- Context Prediction
- Schedule Forecasting
- Activity Prediction
- Preference Forecasting

Forecasts what the user is likely to do next from M19's Timeline
Twin/Timeline Intelligence and M16 Reflection Engine's learned
patterns — this is the "full version" of the original milestone's
Intent Prediction bullet, now organized as its own module.

#### Opportunity Intelligence
- Productivity Opportunities
- Automation Opportunities
- Learning Opportunities
- Cost Saving Suggestions
- Time Optimization
- Health & Wellness Suggestions
- Smart Home Opportunities
- Workflow Improvements

Surfaces improvements across M7 Workflow Intelligence, M11
Productivity Platform, and M12 Smart Home & IoT Platform — always as
a suggestion the user can accept or dismiss, never an automatic
change.

#### Risk Intelligence
- Deadline Risk Detection
- Workflow Failure Prediction
- Device Health Prediction
- Security Risk Prediction
- Smart Home Risk Alerts
- Resource Exhaustion Forecast
- Schedule Conflict Detection
- Dependency Risk Analysis

Forward-looking counterpart to M18's Self-Healing & Diagnostics
Platform: M18 detects and repairs problems as/after they occur, this
module forecasts them before they happen and hands off to M18 and M14
Security Platform rather than acting on risk itself.

#### Planning Intelligence
- Goal Planning
- Task Sequencing
- Project Forecasting
- Calendar Optimization
- Resource Planning
- Smart Scheduling
- Travel Planning
- Scenario Comparison

The "full version" of the original milestone's Predictive Scheduling
bullet, extended to goals and projects; grounded in M7 Workflow
Intelligence and M11/M11B's existing Calendar/Tasks scheduling
surfaces rather than a competing planner.

#### Recommendation Engine
- Contextual Recommendations
- Proactive Suggestions
- Decision Support
- Alternative Strategies
- Priority Suggestions
- Productivity Coaching
- Workflow Guidance
- Explainable Recommendations

The "full version" of the original milestone's Recommendation Engine
and Decision Support bullets — grounded in M19 graph facts, not
generic collaborative filtering, and every recommendation stays
traceable back to the facts that produced it.

#### Simulation Engine
- What-if Analysis
- Scenario Simulation
- Automation Simulation
- Schedule Simulation
- Workflow Simulation
- Risk Simulation
- Resource Simulation
- Outcome Comparison

Lets the user explore hypothetical futures against the M19 Digital
Twin without committing to them — simulations never execute real
actions against M7 Workflow Intelligence or M12 Smart Home & IoT
Platform.

#### Predictive Analytics
- Forecast Dashboards
- Confidence Trends
- Behaviour Analytics
- Opportunity Metrics
- Risk Metrics
- Prediction Accuracy
- Long-Term Trends
- Executive Reports

Feeds M20A Analytics Platform's reporting surfaces rather than
shipping a competing dashboard; this module is the prediction
subsystem's own accuracy and health telemetry.

#### Governance & Safety
- User Approval
- Explainable Predictions
- Confidence Thresholds
- Privacy Controls
- Ethical AI Policies
- Recommendation Limits
- Audit Logs
- Prediction Transparency

The binding safety layer over every other module above: no prediction
silently executes an action, every prediction exposes its confidence
and reasoning, and M14 Security Platform's privacy/audit guarantees
apply to prediction data the same as everywhere else.

#### Developer Prediction Tools *(Developer Mode)*
- Prediction Explorer
- Scenario Builder
- Simulation Console
- Forecast Viewer
- Confidence Inspector
- Prediction Debugger
- Analytics Explorer
- Testing Dashboard

Developer Mode tooling for inspecting and debugging predictions
directly, following the same Developer Mode pattern established by
M5A's Agent Trace panel and M19's Developer Graph Tools.

**Architecture notes** *(binding constraints for whenever this
milestone is implemented):*
- Predictions must remain explainable — every forecast and
  recommendation traceable back to the graph facts and models that
  produced it.
- Predictions must never silently execute actions.
- Recommendations require user approval when appropriate, governed by
  the Governance & Safety module's confidence thresholds and
  recommendation limits.
- Predictions build upon the M19 Knowledge Graph & Digital Twin
  Platform rather than replacing it — this milestone reads the graph,
  it does not maintain a parallel data model.
- M16 Reflection analyzes the past; M20 Prediction estimates future
  outcomes — the two remain distinct, complementary subsystems, not a
  single blended one.
- Prediction confidence must always be exposed, never hidden behind a
  single opaque recommendation.
- Models must remain provider-independent.
- Privacy and Security (M14) policies apply to all predictions.
- Prediction services should remain modular and replaceable.
- Future AI planning systems should integrate without changing the
  core architecture (explicitly scoped as a foundation, consistent
  with M19's own "future AI planning" architecture note).

**Future expansion:** Autonomous Planning, Enterprise Forecasting,
Team Prediction, an AI Strategy Engine, Financial Forecasting, Project
Portfolio Forecasting, Digital Twin Simulation, Predictive Plugins,
External Forecast APIs, and Research Planning — all documented as
future scope only; none require changes to the core architecture
defined above.

**Dependencies:** M3 (Memory), M5A (Agent Runtime), M7 (Workflow
Intelligence), M10A (Universal Search & Knowledge Platform), M11 /
M11B (Integrations & Cloud Platform / Productivity Suite), M12 (Smart
Home & IoT Platform), M13 (Desktop Intelligence), M14
(Security Platform), M15 (Personality Engine), M16 (Reflection
Engine), M17 (Companion Intelligence), M18 (Self-Healing &
Diagnostics), M19 (Knowledge Graph & Digital Twin Platform — kept from
the original scope, now the graph this milestone reads from).

**Complexity:** XL *(upgraded from the original scope's L — 10 feature
modules spanning prediction core, behaviour/opportunity/risk/planning
intelligence, recommendations, simulation, analytics, governance, and
developer tooling make Predictive Intelligence a cross-cutting
decision-support platform that touches nearly every other subsystem in
this roadmap, not a standalone forecasting feature; sized consistently
with this roadmap's other XL milestones, e.g. M14 Security Platform,
M18 Self-Healing & Diagnostics Platform, M19 Knowledge Graph & Digital
Twin Platform)*.

**Acceptance criteria:**
1. Intent prediction measurably reduces average keystrokes-to-intent
   in a dogfood period.
2. Every recommendation is traceable to the graph facts that produced
   it (explainable, not a black box).
3. Predictive scheduling suggestions are opt-in per user, off by
   default.
4. Prediction Core architecture is documented, including how it reads
   from M19's Knowledge Graph Core rather than duplicating it.
5. Behaviour Prediction is documented, including its dependency on
   M19's Timeline Intelligence and M16 Reflection Engine.
6. Opportunity Intelligence is documented, including its integration
   with M7, M11, and M12.
7. Risk Intelligence is documented, including its hand-off to M18
   Self-Healing & Diagnostics Platform and M14 Security Platform
   rather than acting on risk directly.
8. Planning Intelligence is documented, including its grounding in
   M7/M11's existing scheduling surfaces.
9. Recommendation Engine is documented, including explainability back
   to M19 graph facts.
10. Simulation Engine is documented, including the guarantee that
    simulations never execute real actions.
11. Predictive Analytics is documented, including how it feeds M20A
    rather than duplicating its dashboard.
12. Governance & Safety is documented, including confidence exposure,
    approval requirements, and audit logging.
13. Developer Prediction Tools are documented as a Developer Mode
    surface.
14. Cross-milestone integrations (M3, M5A, M7, M10, M11, M12, M13,
    M14, M15, M16, M17, M18, M19) are documented per module.
15. Internal consistency is verified across this milestone's modules,
    architecture notes, dependencies, and acceptance criteria.
16. Roadmap formatting is preserved and consistent with every other
    redesigned milestone in this document.

### M20A — Analytics & Observability Platform

*(Redesigned Jul 2026 from "Analytics Platform" — the real dashboard
for everything §7 (Cross-Platform Systems) has been instrumenting
incrementally since M5A — into a complete enterprise-grade platform.
See the changelog addendum at the end of this document.)*

**Objective:** provide centralized visibility into every subsystem of
JARVIS OS through metrics, events, logs, traces, dashboards, reports,
and operational insights — so users and developers can understand how
JARVIS is operating, diagnose issues, measure performance, and
continuously improve the platform. Analytics is intended for system
health, transparency, and optimization — never advertising or user
profiling.

**Key features (organized into 10 modules):**

#### Observability Core
- Metrics Collection
- Event Collection
- Telemetry Pipeline
- Runtime Metrics
- Health Metrics
- Service Metrics
- Custom Metrics
- Observability Configuration

The foundational telemetry substrate every other module in this
milestone builds on, consuming events every subsystem already
publishes through the Event Bus rather than requiring bespoke
instrumentation per consumer.

#### Event Analytics
- Voice Events
- Desktop Events
- Smart Home Events
- Workflow Events
- Agent Events
- Memory Events
- Prediction Events
- Security Events

Structures the raw Observability Core event stream by originating
subsystem (M2 Voice, M13 Desktop Intelligence, M12 Smart Home & IoT
Platform, M7 Workflow Intelligence, M5A Agent Runtime, M3 Memory, M20
Predictive Intelligence Platform, M14 Security Platform).

#### Performance Analytics
- CPU Monitoring
- GPU Monitoring
- Memory Usage
- Storage Metrics
- Network Performance
- API Latency
- AI Response Latency
- Resource Utilization

The "full version" of the original milestone's Resource Monitoring
and Latency tracking bullets — consolidates M5's Performance Monitor
and M18 Self-Healing & Diagnostics Platform's Performance Optimization
module rather than shipping a competing collector.

#### AI Analytics
- Model Performance
- Prompt Statistics
- Token Usage
- Provider Comparison
- Tool Success Rate
- Hallucination Tracking
- AI Confidence Metrics
- Response Quality Metrics

The "full version" of the original milestone's AI Metrics bullet —
reads from M5A's `AgentState`/`AgentStepEvent` data and M20's
Predictive Analytics module rather than re-deriving AI telemetry
independently.

#### User Experience Analytics
- Feature Usage
- Automation Frequency
- Productivity Trends
- Learning Progress
- Workflow Effectiveness
- Routine Insights
- Recommendation Acceptance
- User Satisfaction Signals

Measures how the user actually uses JARVIS across M11 Productivity
Platform, M7 Workflow Intelligence, and M20's Recommendation Engine —
strictly for the user's own transparency and improvement, never
shared or used for profiling.

#### Dashboard Platform
- System Dashboard
- AI Dashboard
- Desktop Dashboard
- Smart Home Dashboard
- Security Dashboard
- Performance Dashboard
- Workflow Dashboard
- Executive Dashboard

The "full version" of the original milestone's single Performance
Dashboard bullet — one dashboard per major subsystem, each consuming
the Analytics API module below rather than a subsystem-specific
implementation.

#### Alert & Notification Engine
- Performance Alerts
- Security Alerts
- Automation Failures
- AI Errors
- Resource Warnings
- Device Alerts
- Health Notifications
- Custom Alert Rules

Surfaces issues proactively across every module above; security and
health alerts hand off to M14 Security Platform and M18 Self-Healing &
Diagnostics Platform rather than acting on them directly.

#### Reporting Platform
- Daily Reports
- Weekly Reports
- Monthly Reports
- Executive Reports
- Health Reports
- Productivity Reports
- AI Performance Reports
- Custom Reports

The "full version" of the original milestone's implicit
dashboard-only reporting — periodic, exportable summaries built from
every module above.

#### Developer Observability Tools *(Developer Mode)*
- Live Event Viewer
- Metrics Explorer
- Log Explorer
- Trace Explorer
- Timeline Viewer
- Performance Inspector
- Analytics Debugger
- Dashboard Builder

Developer Mode tooling for inspecting the observability pipeline
directly, following the same Developer Mode pattern established by
M5A's Agent Trace panel and M20's Developer Prediction Tools.

#### Analytics API
- Metrics API
- Event API
- Dashboard API
- Reporting API
- Alert API
- Export API
- Integration API
- Plugin Analytics SDK

The standardized surface every dashboard, report, and third-party
integration consumes — new analytics providers install against this
API without modifying the core architecture.

**Architecture notes** *(binding constraints for whenever this
milestone is implemented):*
- Analytics must remain provider-independent.
- Every subsystem should publish standardized events through the
  Event Bus, not bespoke per-consumer instrumentation.
- Metrics, logs, and traces should be independently replaceable.
- Analytics must integrate with the Event Bus, consistent with this
  roadmap's in-process eventing pattern used since M1.
- Sensitive information must be filtered before analytics storage.
- Privacy controls from M14 Security Platform always apply.
- Analytics should support local-first storage with optional cloud
  synchronization, consistent with this roadmap's local-first charter
  (§1).
- Dashboards should consume standardized Analytics API endpoints
  rather than subsystem-specific implementations.
- Analytics data should support M16 Reflection Engine, M20 Predictive
  Intelligence Platform, and M18 Self-Healing & Diagnostics Platform
  without creating circular dependencies — this milestone publishes
  data those milestones read, it does not itself consume their
  outputs as a precondition for its own operation.
- New analytics providers should be installable without modifying the
  core architecture.

**Future expansion:** Distributed Analytics, Enterprise Dashboards,
Fleet Analytics, AI Performance Benchmarking, Capacity Planning,
Business Intelligence Connectors, OpenTelemetry Integration, Custom
Analytics Plugins, Cross-Device Observability, and a Predictive
Operations Center — all documented as future scope only; none require
changes to the core architecture defined above.

**Dependencies:** M5 (Desktop Platform), M5A (Agent Runtime — AI
metrics source data), M7 (Workflow Intelligence), M9 (cost data
source — kept from the original scope), M10A (Universal Search & Knowledge Platform), M11
(Productivity Platform), M12 (Smart Home & IoT Platform), M13 (Desktop
Intelligence), M14 (Security Platform), M16 (Reflection Engine), M18
(Self-Healing & Diagnostics — diagnostics data source, kept from the
original scope), M19 (Knowledge Graph & Digital Twin Platform), M20
(Predictive Intelligence Platform).

**Complexity:** XL *(upgraded from the original scope's M — 10 feature
modules spanning observability core, event/performance/AI/UX
analytics, dashboards, alerting, reporting, developer tooling, and a
standardized API make Analytics & Observability a cross-cutting
operational platform supporting every other subsystem in this roadmap,
not an isolated reporting feature; sized consistently with this
roadmap's other XL milestones, e.g. M14 Security Platform, M18
Self-Healing & Diagnostics Platform, M19 Knowledge Graph & Digital
Twin Platform, M20 Predictive Intelligence Platform)*.

**Acceptance criteria:**
1. Token usage and cost figures reconcile with actual provider
   billing within a small, documented margin.
2. The dashboard renders with zero additional instrumentation code in
   consuming milestones — it only reads what §7 already requires them
   to emit.
3. Telemetry, if enabled, is independently verifiable to exclude
   prompt content (audit-loggable, per M14).
4. Observability Core architecture is documented, including its
   consumption of the Event Bus rather than bespoke instrumentation.
5. Event Analytics is documented, covering all 8 event categories and
   their source milestones.
6. Performance Analytics is documented, including consolidation with
   M5 and M18 rather than a competing collector.
7. AI Analytics is documented, including its dependency on M5A and
   M20's Predictive Analytics module.
8. Dashboard Platform is documented, including consumption of the
   Analytics API rather than subsystem-specific implementations.
9. Alert & Notification Engine is documented, including hand-off to
   M14 and M18 rather than acting on alerts directly.
10. Reporting Platform is documented.
11. Developer Observability Tools are documented as a Developer Mode
    surface.
12. Analytics API is documented as the standardized integration
    surface for dashboards, reports, and third-party providers.
13. Cross-milestone integrations (M5, M5A, M7, M9, M10, M11, M12, M13,
    M14, M16, M18, M19, M20) are documented per module.
14. Internal consistency is verified across this milestone's modules,
    architecture notes, dependencies, and acceptance criteria.
15. Roadmap formatting is preserved and consistent with every other
    redesigned milestone in this document.

### M21 — Mobile Platform

*(Absorbs the previously-planned "Mobile companion" + "Wearable
integration" scope — see §9. Further redesigned Jul 2026 from a
6-feature multi-device presence milestone into a complete
enterprise-grade Mobile Platform. See the changelog addendum at the
end of this document.)*

**Objective:** extend JARVIS beyond the desktop, enabling secure,
real-time interaction from smartphones and tablets while preserving
the desktop as the primary execution environment. The mobile
application acts as a companion interface, remote control, notification
center, secure authentication device, and portable AI assistant. The
architecture supports Android and iOS while remaining
platform-independent wherever possible.

**Key features (organized into 10 modules):**

#### Mobile Platform Core
- Platform Architecture
- Mobile Runtime
- Device Registration
- Session Management
- Configuration
- Offline Support
- Synchronization
- Platform Services

The foundational mobile substrate every other module in this milestone
builds on; establishes the Android/iOS runtime and reuses M11
Integrations & Cloud Platform's transport (including its Android
Companion pairing/account-linking scope, per M11's Aug 2026 retitling
note) rather than a separate mobile-only API layer — this milestone
builds the full mobile app on top of the pairing M11 establishes.

#### Mobile Companion
- Voice Conversations
- Chat Interface
- Notification Center
- Remote Assistant
- Personal Dashboard
- Activity Feed
- AI Suggestions
- Status Overview

The "full version" of the original milestone's Mobile Voice bullet —
routes voice through the same `VoiceService` pipeline as desktop, and
surfaces M17 Companion Intelligence and M20 Predictive Intelligence
Platform suggestions on the phone rather than reimplementing them.

#### Remote Control Platform
- Desktop Control
- Smart Home Control
- Workflow Control
- Automation Control
- Device Management
- File Access
- Media Control
- Remote Commands

The "full version" of the original milestone's Remote Commands
bullet — triggers M7 Workflow Intelligence automations and M12 Smart
Home & IoT Platform devices from the phone, always executed on the
desktop/hub side, never duplicated mobile-side logic.

#### Mobile Intelligence
- Context Awareness
- Location Awareness
- Device Sensors
- Presence Detection
- Mobile Routines
- Mobile Predictions
- Smart Suggestions
- Personal Insights

Feeds mobile-specific context (location, presence, sensors) into the
M19 Knowledge Graph & Digital Twin Platform's Context Engine and reads
M20's Behaviour Prediction module rather than maintaining a separate
prediction model.

#### Secure Access Platform
- Biometric Authentication
- Passkeys
- Device Trust
- Multi-Factor Authentication
- Session Approval
- Remote Authorization
- Security Verification
- Emergency Lockdown

The "full version" of the original milestone's implicit mobile-auth
requirement — meets the same security bar as desktop per M14 Security
Platform, and the mobile device itself can act as an MFA/session-
approval factor for desktop actions.

#### Synchronization Platform
- Settings Sync
- Memory Sync
- Knowledge Graph Sync
- Dashboard Sync
- Notification Sync
- Automation Sync
- Device Sync
- Conflict Resolution

Synchronizes semantic state from M3 Memory and M19's Knowledge Graph
Core rather than duplicating raw storage — the "conversation started
on desktop is resumable on mobile" guarantee from the original
milestone's acceptance criteria now lives here as one of eight sync
categories.

#### Mobile Notifications
- AI Alerts
- Security Alerts
- Automation Notifications
- Reminder Delivery
- Health Notifications
- Smart Home Alerts
- Workflow Updates
- Custom Notification Rules

The "full version" of the original milestone's Notifications bullet —
routes M20A's Alert & Notification Engine output to mobile, respecting
the same do-not-disturb rules the original wearable acceptance
criterion required.

#### Mobile Analytics
- Usage Metrics
- Performance Metrics
- Synchronization Metrics
- Device Health
- Battery Optimization
- Connectivity Analytics
- Crash Diagnostics
- Mobile Reports

Feeds M20A Analytics & Observability Platform's Event Analytics and
Dashboard Platform modules rather than shipping a competing mobile-only
dashboard.

#### Developer Mobile Tools *(Developer Mode)*
- Device Manager
- Emulator Support
- Mobile Debugger
- Push Notification Tester
- Sync Inspector
- Session Inspector
- Mobile Logs
- Mobile Diagnostics

Developer Mode tooling for inspecting the mobile platform directly,
following the same Developer Mode pattern established by M5A's Agent
Trace panel and M20A's Developer Observability Tools.

#### Mobile SDK & APIs
- Mobile SDK
- Authentication API
- Notification API
- Sync API
- Remote Command API
- Device API
- Extension API
- Plugin Integration

The standardized surface the Android/iOS apps (and future wearable
extensions) are built against — new mobile clients and wearable
integrations install against this API without modifying the core
architecture.

**Architecture notes** *(binding constraints for whenever this
milestone is implemented):*
- Desktop remains the primary execution environment.
- Mobile acts as a secure companion rather than replacing the desktop.
- Mobile should reuse existing services wherever possible (M9
  transport, `VoiceService`, M7 automations) rather than reimplementing
  them mobile-side.
- All communication must be encrypted.
- M14 Security Platform policies apply to all mobile interactions.
- M19's Knowledge Graph synchronizes semantic data rather than
  duplicating raw storage.
- Analytics integrate with M20A Analytics & Observability Platform.
- Mobile must support offline operation with synchronization when
  connectivity returns.
- Push notifications must be modular and provider-independent.
- Future wearable devices should integrate without modifying the core
  architecture (the original WatchOS/WearOS scope now lives under
  Future Expansion below, as a thin extension of Mobile SDK & APIs).

**Future expansion:** Wear OS, Apple Watch, Android Auto, Apple
CarPlay, Tablet Mode, Foldable Devices, Mobile Widgets, Offline AI,
Satellite Messaging, and Cross-Device Handoff — all documented as
future scope only; none require changes to the core architecture
defined above.

**Dependencies:** M5 (Desktop Platform), M5A (Agent Runtime), M6
(Vision & Multimodal), M7 (Workflow Intelligence), M11 (Integrations &
Cloud Platform — API Gateway is the transport, kept from the original
scope), M10A (Universal Search & Knowledge Platform), M11B
(Productivity Suite), M12 (Smart Home & IoT Platform), M13 (Desktop
Intelligence), M14 (Security
Platform — mobile auth must meet the same security bar as desktop,
kept from the original scope), M15 (Personality Engine), M16
(Reflection Engine), M17 (Companion Intelligence), M18 (Self-Healing &
Diagnostics), M19 (Knowledge Graph & Digital Twin Platform), M20
(Predictive Intelligence Platform), M20A (Analytics & Observability
Platform).

**Complexity:** XL *(unchanged from the original scope's XL, with an
explicit rationale now documented: the Mobile Platform is a complete
companion ecosystem — 10 feature modules spanning platform core,
companion UX, remote control, mobile-specific intelligence, secure
access, synchronization, notifications, analytics, developer tooling,
and an SDK — not a standalone mobile application; sized consistently
with this roadmap's other XL milestones, e.g. M14 Security Platform,
M19 Knowledge Graph & Digital Twin Platform, M20A Analytics &
Observability Platform)*.

**Acceptance criteria:**
1. A conversation started on desktop is resumable on mobile within 5s.
2. A remote command triggers the correct desktop-side agent/automation
   run and reports completion back to the phone.
3. Wearable notifications respect the same do-not-disturb rules as
   desktop.
4. Mobile Platform Core architecture is documented, including reuse of
   M9's transport rather than a separate mobile-only API layer.
5. Mobile Companion is documented, including routing through the
   shared `VoiceService` pipeline and M17/M20 suggestion surfaces.
6. Remote Control Platform is documented, including that commands
   always execute desktop/hub-side, never duplicated mobile-side.
7. Mobile Intelligence is documented, including its dependency on
   M19's Context Engine and M20's Behaviour Prediction.
8. Secure Access Platform is documented, including mobile-as-MFA-
   factor for desktop actions.
9. Synchronization Platform is documented, including semantic-only
   sync of M19's Knowledge Graph rather than raw storage duplication.
10. Mobile Notifications are documented, including integration with
    M20A's Alert & Notification Engine.
11. Mobile Analytics is documented, including how it feeds M20A rather
    than shipping a competing dashboard.
12. Developer Mobile Tools are documented as a Developer Mode surface.
13. Mobile SDK & APIs are documented as the standardized surface for
    mobile clients and future wearable extensions.
14. Cross-milestone integrations (M5, M5A, M6, M7, M9, M10, M11, M12,
    M13, M14, M15, M16, M17, M18, M19, M20, M20A) are documented per
    module.
15. Internal consistency is verified across this milestone's modules,
    architecture notes, dependencies, and acceptance criteria.
16. Roadmap formatting is preserved and consistent with every other
    redesigned milestone in this document.

### M22 — Edge AI Platform

*(Redesigned Jul 2026 from a 6-feature local/offline hardware
milestone — extending the existing Ollama local-first story to real
edge deployment — into a complete enterprise-grade platform. See the
changelog addendum at the end of this document.)*

**Objective:** enable JARVIS to execute AI models locally with strong
privacy, low latency, offline capability, hardware acceleration, and
intelligent hybrid execution. The platform abstracts model providers,
inference engines, and hardware backends behind a unified architecture
while allowing future expansion without redesign.

**Key features (organized into 10 modules):**

#### Edge AI Core
- Local AI Runtime
- Model Runtime Manager
- Inference Pipeline
- Execution Scheduler
- Runtime Configuration
- Resource Allocation
- Provider Abstraction
- Runtime Policies

The foundational runtime substrate every other module in this
milestone builds on — extends M1's Ollama provider foundation into a
full provider-abstracted local runtime, not a second, competing
inference layer.

#### Model Management
- Model Registry
- Model Installation
- Model Updates
- Version Management
- Model Validation
- Rollback Support
- Model Metadata
- Compatibility Management

Manages the local model lifecycle end-to-end; the "full version" of
the original milestone's implicit model-handling scope, now organized
as its own module.

#### Inference Engine
- Text Inference
- Vision Inference
- Audio Inference
- Multimodal Inference
- Batch Processing
- Streaming Inference
- Parallel Execution
- Result Optimization

Executes inference across every modality M6 Vision & Multimodal and
`VoiceService` already define, rather than a text-only local runtime.

#### Hardware Acceleration
- CPU Acceleration
- GPU Acceleration
- NPU Support
- DirectML Integration
- CUDA Support
- Vulkan Compute
- Hardware Detection
- Performance Profiles

The "full version" of the original milestone's GPU Acceleration
bullet — automatically detects and adapts to whatever CPU/GPU/NPU
hardware is present, not a fixed reference-hardware-only path.

#### Hybrid AI Execution
- Local-First Routing
- Cloud Fallback
- Provider Selection
- Cost Optimization
- Latency Optimization
- Offline Mode
- Hybrid Policies
- Failover Logic

The "full version" of the original milestone's Offline AI bullet —
local execution is preferred whenever practical, with cloud fallback
remaining optional and policy-driven rather than a hard dependency.

#### AI Resource Management
- Memory Management
- VRAM Management
- CPU Scheduling
- GPU Scheduling
- Thermal Awareness
- Battery Awareness
- Background Processing
- Resource Limits

The "full version" of the original milestone's CPU Scheduling and
Energy Optimization bullets — resource-aware scheduling so JARVIS
never starves other work, extended to thermal and battery awareness
for mobile/edge hardware (M21 Mobile Platform).

#### Privacy & Security
- Local Data Processing
- Secure Model Storage
- Model Integrity
- Execution Sandboxing
- Permission Policies
- Secure Updates
- Encryption
- Audit Logging

Applies M14 Security Platform's guarantees to local model execution —
sensitive data stays local, models are integrity-checked before load,
and every privileged action is audit-logged the same as everywhere
else in this roadmap.

#### Edge AI Analytics
- Inference Metrics
- Model Performance
- Resource Utilization
- Latency Reports
- Accuracy Tracking
- Cost Comparison
- Usage Trends
- Runtime Dashboards

Feeds M20A Analytics & Observability Platform's Performance Analytics
and AI Analytics modules rather than shipping a competing dashboard.

#### Developer Edge Tools *(Developer Mode)*
- Model Explorer
- Runtime Inspector
- Performance Profiler
- Inference Debugger
- Benchmark Suite
- Hardware Inspector
- Model Tester
- Diagnostics Console

Developer Mode tooling for inspecting the edge runtime directly,
following the same Developer Mode pattern established by M5A's Agent
Trace panel and M21's Developer Mobile Tools.

#### Edge AI SDK & APIs
- Model SDK
- Runtime API
- Inference API
- Hardware API
- Provider API
- Analytics API
- Plugin SDK
- Extension Framework

The standardized surface every model provider, hardware backend, and
third-party inference framework installs against — new providers
integrate without modifying the core architecture.

**Architecture notes** *(binding constraints for whenever this
milestone is implemented):*
- Local execution should be the preferred execution mode whenever
  practical.
- Cloud execution is optional and policy-driven.
- Provider abstraction must prevent vendor lock-in.
- Hardware acceleration should automatically adapt to available CPU,
  GPU, and NPU resources.
- Models remain modular and independently replaceable.
- Edge AI integrates with M14 Security Platform, M20A Analytics &
  Observability Platform, M19 Knowledge Graph & Digital Twin Platform,
  and M20 Predictive Intelligence Platform without creating circular
  dependencies — this milestone publishes runtime data those
  milestones read, it does not depend on their outputs to execute
  inference.
- Sensitive data should remain local whenever possible.
- Offline functionality is a first-class architectural goal.
- Runtime services should support future distributed execution.
- Future AI frameworks should integrate through standard provider
  interfaces.

**Future expansion:** On-device fine-tuning, Federated Learning,
Quantized Models, Multi-GPU Execution, Edge AI Clusters, AI
Accelerator Cards, Dynamic Model Loading, a Model Marketplace, Edge AI
Containers, and Autonomous AI Optimization — all documented as future
scope only; none require changes to the core architecture defined
above.

**Dependencies:** M1 (Ollama provider foundation — kept from the
original scope), M5 (Desktop Platform), M5A (Agent Runtime), M6
(Vision & Multimodal), M11 (Integrations & Cloud Platform), M10 (Knowledge
Engine), M13 (Desktop Intelligence), M14 (Security Platform), M18
(Self-Healing & Diagnostics), M19 (Knowledge Graph & Digital Twin
Platform), M20 (Predictive Intelligence Platform), M20A (Analytics &
Observability Platform), M21 (Mobile Platform).

**Complexity:** XL *(upgraded from the original scope's L — 10 feature
modules spanning runtime core, model management, multimodal inference,
hardware acceleration, hybrid execution, resource management, privacy
& security, analytics, developer tooling, and an SDK make the Edge AI
Platform a foundational runtime layer supporting all local AI
execution, not a standalone inference feature; sized consistently with
this roadmap's other XL milestones, e.g. M14 Security Platform, M20A
Analytics & Observability Platform, M21 Mobile Platform)*.

**Acceptance criteria:**
1. JARVIS runs a full chat + agent session with zero network calls on
   the reference hardware.
2. Quantized models pass the same acceptance bar as the full models
   on a defined quality benchmark.
3. Measured energy consumption improvement on battery-powered
   reference hardware vs. the unoptimized baseline.
4. Edge AI Core architecture is documented, including its extension of
   M1's Ollama provider foundation.
5. Model Management is documented, covering the full model lifecycle.
6. Inference Engine is documented, including multimodal inference
   coverage (text, vision, audio).
7. Hardware Acceleration is documented, including automatic
   CPU/GPU/NPU detection rather than a fixed reference-hardware path.
8. Hybrid AI Execution is documented, including the local-first,
   cloud-optional policy.
9. AI Resource Management is documented, including thermal/battery
   awareness for M21 Mobile Platform hardware.
10. Privacy & Security is documented, including its application of
    M14's guarantees to local model execution.
11. Edge AI Analytics is documented, including how it feeds M20A
    rather than duplicating its dashboard.
12. Developer Edge Tools are documented as a Developer Mode surface.
13. Edge AI SDK & APIs are documented as the standardized surface for
    model providers and hardware backends.
14. Cross-milestone integrations (M1, M5, M5A, M6, M9, M10, M13, M14,
    M18, M19, M20, M20A, M21) are documented per module.
15. Internal consistency is verified across this milestone's modules,
    architecture notes, dependencies, and acceptance criteria.
16. Roadmap formatting is preserved and consistent with every other
    redesigned milestone in this document.

### M23 — Distributed JARVIS

*(Absorbs the previously-planned "Cloud Sync" scope — see §9.)*

**Objective:** JARVIS as a distributed system across a user's devices
and, optionally, a team.

**Key features:**
- Distributed Agents — an agent run started on one device can
  continue on another.
- Multi-device Sync — end-to-end encrypted sync of conversations +
  memories to the user's own cloud (S3 / R2 / Nextcloud) — user
  brings the bucket, same principle as originally scoped.
- Shared Memory — opt-in memory sharing within a defined group
  (family, team).
- Remote Execution — trigger an agent/automation run on a specific
  remote device.
- Enterprise Collaboration — team-scoped conversations/memories with
  M14-grade access control.

**Dependencies:** M21 (Mobile Platform, for the multi-device
transport), M14 (Security Platform, for shared/enterprise access
control), M10A (Universal Search & Knowledge Platform, for what gets synced/shared).

**Complexity:** XL.

**Acceptance criteria:**
1. An agent run paused on desktop resumes correctly on a second
   device.
2. Shared memory respects per-item sharing scope — nothing leaks
   outside its intended group.
3. E2EE sync is verified end-to-end: the cloud bucket owner cannot
   read conversation content without the user's key.

### M23A — Robotics & Hardware Control Platform

*(Added Jul 2026, alongside M23, as a new companion milestone — not a
redesign of any existing milestone. M23 — Distributed JARVIS is
unchanged; see the changelog addendum at the end of this document.
Unlike every other lettered companion in this roadmap, M23A is not a
narrow extension of its numeric parent's own scope — it stands alone
as the unified hardware abstraction layer for the entire JARVIS
ecosystem, sequenced here because it depends on M21/M22's device and
edge-runtime foundations.)*

**Objective:** provide the unified hardware abstraction layer for the
entire JARVIS ecosystem — covering microcontrollers (ESP32, Arduino,
Raspberry Pi), USB/Bluetooth/BLE/Wi-Fi devices, GPIO, Smart Home
protocols (Matter, Zigbee, Z-Wave, MQTT), CAN bus, robotics, and
industrial controllers — so every future physical-device integration,
up to and including future humanoid robots, is built on one
vendor-neutral foundation rather than a new one-off integration each
time.

**Key features (organized into 10 modules):**

#### Hardware Abstraction Layer (HAL)
- Device abstraction
- Hardware profiles
- Driver interface
- Driver manager
- Dynamic driver loading
- Capability detection
- Version compatibility
- Device registry
- Plug & Play
- Driver sandbox
- Device lifecycle management
- Vendor-independent abstraction

The foundational substrate every other module in this milestone builds
on; every device (M12 Smart Home & IoT Platform devices included)
registers here first, through a vendor-independent profile rather than
a bespoke integration path.

#### Communication Interfaces
- USB
- UART
- Serial
- SPI
- I2C
- GPIO
- CAN Bus
- Ethernet
- Wi-Fi
- Bluetooth
- BLE
- NFC
- Infrared
- RS485
- WebSocket bridge

The physical/transport layer every driver in the HAL is built against;
reused by M12 Smart Home & IoT Platform and M21 Mobile Platform's
device-facing features rather than each maintaining its own transport
code.

#### IoT Connectivity
- MQTT
- Matter
- Zigbee
- Thread
- Z-Wave
- Home Assistant
- Google Home
- Alexa
- Apple HomeKit
- SmartThings
- Device discovery
- Secure pairing
- Auto provisioning
- OTA registration

The "full version" of the protocol/ecosystem support M12 Smart Home &
IoT Platform already scoped — M23A now owns the shared low-level
protocol implementations, M12 owns the smart-home-specific automation
and UX built on top of them.

#### Sensor Framework
- Motion, presence, and radar sensors (e.g. LD2410B)
- Temperature, humidity, pressure, light sensors
- Water level, smoke, and gas sensors
- Door, window, and camera sensors
- Microphones, GPS, and IMU
- Calibration
- Sensor fusion
- Noise filtering
- Sampling
- Health monitoring
- Sensor diagnostics

Normalizes raw sensor data before it reaches M19's Knowledge Graph
Context Engine or M12's automation triggers — consuming milestones
read fused, calibrated readings, never raw driver output.

#### Actuator Framework
- Relays, motors, servo and stepper motors
- Smart locks, solenoids, pumps
- Curtains, lights, fans, RGB LEDs
- Buzzers, displays
- PWM control
- Emergency stop
- Safety limits
- State monitoring

The output-side counterpart to the Sensor Framework; every actuator
action includes a safety-limit check and is auditable through M14
Security Platform the same as any other privileged action.

#### Robotics Runtime
- Robot controller
- Multi-axis movement
- Motion planner
- Kinematics abstraction
- Docking and charging
- Navigation hooks
- Obstacle awareness
- Robot state manager
- Simulation support
- Robot diagnostics
- Task execution

The dedicated runtime for mobile/physical robots — built on the HAL,
Communication Interfaces, Sensor Framework, and Actuator Framework
rather than a separate robotics stack; this is the module Future
Expansion's humanoid-robotics scope will eventually extend.

#### Device Automation Engine
- Event-driven automation
- Scheduling
- Conditional execution
- Multi-device workflows
- Automation chains, smart scenes
- Presence automation, occupancy detection
- Energy saving
- Recovery workflows, retry engine

Reuses M7 Workflow Intelligence's automation engine for device-level
triggers rather than shipping a second, competing automation runtime;
this module is the hardware-facing edge of that same engine.

#### Hardware Security
- Secure pairing
- Device authentication
- Signed firmware, secure boot
- OTA validation
- Hardware encryption
- Device permissions
- Hardware firewall, device isolation
- Tamper detection
- Trust verification

Applies M14 Security Platform's guarantees to physical devices —
every device is authenticated and permissioned before it can act, and
firmware updates are signed and validated the same way M14 already
requires for software updates.

#### Hardware Analytics
- Device uptime, battery health
- Power analytics, signal quality
- Error logs, event history
- Device statistics
- Maintenance prediction
- Performance monitoring
- Hardware diagnostics

Feeds M20A Analytics & Observability Platform's Event Analytics and
Performance Analytics modules, and M18 Self-Healing & Diagnostics
Platform's Predictive Reliability module, rather than shipping a
competing hardware dashboard.

#### Robotics SDK & APIs
- Driver SDK, hardware SDK, robot SDK, sensor SDK, automation SDK
- Plugin APIs
- Testing toolkit, emulator
- Documentation, sample projects
- REST APIs, local APIs

The standardized surface every new driver, sensor, actuator, and
robotics integration installs against — new hardware support is added
without modifying the core architecture.

**Architecture notes** *(binding constraints for whenever this
milestone is implemented):*
- Hardware abstraction is mandatory — no consuming milestone talks to
  a physical device driver directly; every interaction goes through
  the HAL.
- Vendor-neutral design — no protocol or vendor SDK is hard-wired into
  the core architecture.
- Driver isolation — a misbehaving or crashing driver must not take
  down the rest of the platform (driver sandbox).
- Hot-swappable devices — devices can be added/removed at runtime
  without a restart (Plug & Play).
- Local-first execution — device control does not require a cloud
  round-trip.
- Offline support is a first-class goal, not a degraded fallback mode.
- Safety-first architecture — actuator actions always pass through
  safety-limit checks; emergency stop is always available.
- Hardware sandboxing — untrusted or newly-paired devices operate
  under restricted permissions until explicitly trusted.
- Reusable APIs — the Robotics SDK & APIs module is the only sanctioned
  integration surface for new hardware, so third-party and future
  first-party integrations follow one contract.
- Future humanoid-robot compatibility — the Robotics Runtime module is
  deliberately generalized (kinematics abstraction, motion planning,
  task execution) rather than scoped to today's simpler devices.
- M23A publishes hardware capabilities, sensor data, and device
  telemetry for M12 Smart Home & IoT Platform, M18 Self-Healing &
  Diagnostics Platform, M19 Knowledge Graph & Digital Twin Platform,
  M20A Analytics & Observability Platform, and M21 Mobile Platform to
  consume — it does not itself depend on their outputs to operate,
  avoiding circular dependencies.

**Future expansion:** ROS2 Integration, Industrial PLC Support, Robot
Arms, Autonomous Drones, Smart Vehicle APIs, Edge Robotics AI,
Warehouse Robotics, Agricultural Robotics, Medical Robotics, Humanoid
Robotics, Autonomous Charging Stations, and Digital Twin Support — all
documented as future scope only; none require changes to the core
architecture defined above.

**Dependencies:** M1 (Ollama provider foundation), M5 (Desktop
Platform), M5A (Agent Runtime), M6 (Vision & Multimodal), M7 (Workflow
Intelligence — reused for Device Automation), M9 (Integration
Platform), M10A (Universal Search & Knowledge Platform), M13 (Desktop Intelligence), M14
(Security Platform), M18 (Self-Healing & Diagnostics), M19 (Knowledge
Graph & Digital Twin Platform), M20 (Predictive Intelligence
Platform), M20A (Analytics & Observability Platform), M21 (Mobile
Platform), M22 (Edge AI Platform — local inference for on-device
robotics/sensor intelligence).

**Complexity:** XL *(the foundational platform responsible for every
interaction between JARVIS and physical hardware — 10 feature modules
spanning hardware abstraction, communication transport, IoT protocol
support, sensors, actuators, a full robotics runtime, device
automation, hardware security, analytics, and an SDK make M23A a
cross-cutting hardware platform underneath M12 Smart Home & IoT
Platform and every future physical-device milestone, not a standalone
feature; sized consistently with this roadmap's other XL milestones,
e.g. M14 Security Platform, M21 Mobile Platform, M22 Edge AI
Platform)*.

**Acceptance criteria:**
1. A newly-connected USB, Bluetooth, or Wi-Fi device is discovered and
   registered in the device registry without a restart.
2. A driver for a supported device class loads dynamically and passes
   capability detection before the device is usable.
3. A registered sensor (e.g. a motion or temperature sensor) reports
   calibrated readings that pass sensor-fusion and noise-filtering
   checks.
4. A registered actuator (e.g. a relay or servo) executes a commanded
   action and reports its resulting state, with an emergency-stop path
   verified to halt it immediately.
5. A Matter, Zigbee, or Z-Wave device pairs securely and appears in
   M12 Smart Home & IoT Platform without M12 reimplementing the
   protocol itself.
6. A Robotics Runtime task (e.g. a docking/charging cycle) completes
   using the motion planner and obstacle-awareness hooks, verified in
   simulation before running on real hardware.
7. Hardware Abstraction Layer, Communication Interfaces, IoT
   Connectivity, Sensor Framework, Actuator Framework, Robotics
   Runtime, Device Automation Engine, Hardware Security, Hardware
   Analytics, and Robotics SDK & APIs are each independently
   documented as their own module.
8. All ten modules operate with zero network dependency once devices
   are paired (offline operation).
9. Hardware Analytics and diagnostics data (uptime, battery, error
   logs, maintenance prediction) is queryable per device.
10. Every device pairing, firmware update, and privileged actuator
    action is authenticated, signed/validated, and audit-logged per
    M14 Security Platform.
11. An OTA firmware update is signed, validated, and rejected if
    signature verification fails.
12. Device Automation Engine workflows (multi-device chains, smart
    scenes, presence automation) execute correctly and are reusable
    from M7 Workflow Intelligence.
13. Hardware Analytics data is queryable through M20A Analytics &
    Observability Platform without a competing dashboard.
14. Driver loading, sensor sampling, and actuator commands meet a
    documented latency budget appropriate for real-time device control.
15. A driver crash is contained by the driver sandbox and does not
    crash the rest of the platform (safety-first architecture).
16. Robotics SDK & APIs are documented and support building a new
    driver/sensor/actuator integration end-to-end via the emulator and
    testing toolkit, without touching the core architecture.
17. Cross-platform compatibility is verified across ESP32, Arduino,
    Raspberry Pi, and USB/Bluetooth/BLE/Wi-Fi device classes named in
    this milestone's scope.

### M23B — Autonomous Planning & Decision Engine

*(Added Jul 2026, alongside M23A, as a new companion milestone — not a
redesign of any existing milestone. M24 — Production Release is
unchanged; see the changelog addendum at the end of this document.
Like M23A, M23B is not a narrow extension of a single numeric parent's
own scope — it stands alone as the central reasoning and execution
planner for JARVIS, sequenced immediately before M24 so every
capability it orchestrates already exists by the time it is built.)*

**Objective:** become the central reasoning and execution planner for
JARVIS — orchestrating every subsystem without replacing them. M23B
consumes capabilities published by previous milestones and
intelligently decides what to do, when to do it, which AI agent should
perform it, which device should execute it, whether execution should
be local or cloud, and how to recover from failures.

**Key features (organized into 10 modules):**

#### Goal Management
- Goal creation
- Goal hierarchy
- Long-term goals
- Short-term goals
- Goal prioritization
- Goal cancellation
- Goal dependencies
- Goal history
- Goal persistence
- Goal templates

The foundational substrate every other module in this milestone builds
on; goals are the top-level unit M23B plans and executes against,
persisted and versioned the same way M19's Knowledge Graph persists
entities.

#### Task Planning
- Task decomposition
- Multi-step planning
- Sequential execution
- Parallel execution
- Dependency graph
- Planning optimization
- Dynamic replanning
- Execution ordering
- Resource-aware planning
- Time estimation

Breaks a goal into an executable task graph, reusing M7 Workflow
Intelligence's execution primitives rather than a second, competing
workflow engine.

#### Decision Engine
- Context-aware decisions
- Multi-option evaluation
- Cost-benefit analysis
- Risk scoring
- Confidence scoring
- AI reasoning
- Decision history
- Decision explanation
- Policy evaluation
- Human override

The "what to do" core — reads M19's Knowledge Graph and M20's
Predictive Intelligence Platform for context and forecasts rather than
re-deriving them, and every decision remains explainable and
overridable by the user.

#### Autonomous Execution
- Auto execution
- Approval workflow
- Safe execution
- Retry engine
- Rollback
- Pause
- Resume
- Checkpoints
- Recovery
- Completion validation

The "when to do it" and "how to recover" core — executes through
existing subsystems (M5A Agent Runtime, M7 Workflow Intelligence, M23A
Robotics & Hardware Control Platform) rather than a parallel execution
path, with approval workflow gating anything M23B's Safety & Governance
module flags as requiring one.

#### Resource Planner
- CPU planning
- GPU planning
- Memory planning
- Edge AI selection
- Cloud selection
- Device selection
- Battery awareness
- Network awareness
- Cost optimization
- Load balancing

The "local or cloud" and "which device" core — reads M22 Edge AI
Platform's Hybrid AI Execution module and M21 Mobile Platform/M23A
Robotics & Hardware Control Platform's device registries rather than
maintaining a second resource model.

#### Multi-Agent Orchestration
- Agent assignment
- Agent coordination
- Parallel agents
- Agent delegation
- Conflict resolution
- Shared task queue
- Agent monitoring
- Agent recovery
- Distributed planning
- Agent collaboration

The "which AI agent" core — coordinates M5A Agent Runtime instances
rather than reimplementing agent execution; conflict resolution
arbitrates when two goals compete for the same agent or device.

#### Predictive Intelligence
- Predictive scheduling
- Habit prediction
- Workflow prediction
- Failure prediction
- Maintenance prediction
- Resource prediction
- Smart recommendations
- Opportunity detection
- Risk prediction
- Trend analysis

Consumes M20 Predictive Intelligence Platform's Behaviour Prediction,
Risk Intelligence, and Opportunity Intelligence modules directly rather
than maintaining a second prediction model — this module is where M20's
forecasts become planning inputs.

#### Safety & Governance
- Execution policies
- Permission validation
- Safety rules
- Kill switch
- Emergency stop
- Compliance engine
- Ethical constraints
- Risk thresholds
- Audit logging
- Manual approval

Applies M14 Security Platform's guarantees to autonomous planning —
every autonomous action is permission-checked, policy-evaluated, and
audit-logged, and a global kill switch/emergency stop is always
available, consistent with M23A's own safety-first actuator
guarantees.

#### Planning Analytics
- Planning statistics
- Goal completion
- Execution success rate
- Failure analysis
- Planning efficiency
- Decision quality
- Resource utilization
- Time savings
- Productivity metrics
- Optimization reports

Feeds M20A Analytics & Observability Platform's Dashboard Platform and
Reporting Platform modules rather than shipping a competing dashboard.

#### Planning SDK & APIs
- Planning SDK
- Workflow SDK
- Goal APIs
- Decision APIs
- Automation APIs
- Plugin APIs
- Testing tools
- Simulation APIs
- Documentation
- Example workflows

The standardized surface every future milestone (and third-party
plugin) integrates against to submit goals or extend planning
behavior — new capabilities are added without modifying the core
architecture.

**Architecture notes** *(binding constraints for whenever this
milestone is implemented):*
- Goal-driven architecture — every autonomous action traces back to an
  explicit goal, never an ungoverned background process.
- Event-driven planning — reacts to Event Bus signals from every other
  subsystem rather than polling.
- Local-first reasoning — planning and decision-making run locally
  whenever practical, consistent with this roadmap's local-first
  charter (§1).
- Cloud-assisted planning is optional and policy-driven, mirroring
  M22 Edge AI Platform's Hybrid AI Execution module.
- Explainable AI decisions — every decision is traceable back to the
  context, options, and policy evaluation that produced it.
- Safe autonomous execution — rollback, checkpoints, and a kill switch
  are always available, never optional add-ons.
- Human approval when required — the Safety & Governance module's
  policy evaluation decides when autonomous execution needs explicit
  user sign-off.
- Distributed planning — plans can span multiple agents and devices
  coordinated through Multi-Agent Orchestration.
- Modular orchestration — M23B orchestrates existing subsystems, it
  does not replace or duplicate their own logic.
- No circular dependencies — M23B consumes services from M1, M5, M5A,
  M6, M9, M10, M13, M14, M18, M19, M20, M20A, M21, M22, M23, and M23A,
  and in turn publishes planning services (goals, decisions, execution
  status) for future milestones to consume — it does not require any
  milestone built after it to operate.

**Future expansion:** Long-term autonomous missions, AI project
management, strategic planning, autonomous business workflows, AI
negotiation, economic optimization, multi-week planning, team
collaboration planning, enterprise workflow orchestration,
self-improving planning, autonomous research planning, and cognitive
architecture integration — all documented as future scope only; none
require changes to the core architecture defined above.

**Dependencies:** M1 (Ollama provider foundation), M5 (Desktop
Platform), M5A (Agent Runtime — agents this milestone orchestrates),
M6 (Vision & Multimodal), M11 (Integrations & Cloud Platform), M10 (Knowledge
Engine), M13 (Desktop Intelligence), M14 (Security Platform), M18
(Self-Healing & Diagnostics), M19 (Knowledge Graph & Digital Twin
Platform — decision context), M20 (Predictive Intelligence Platform —
forecasts this milestone plans against), M20A (Analytics &
Observability Platform), M21 (Mobile Platform), M22 (Edge AI Platform —
local/cloud execution selection), M23 (Distributed JARVIS — multi-device
execution), M23A (Robotics & Hardware Control Platform — physical
execution targets).

**Complexity:** XL *(M23B becomes the cognitive planning layer
responsible for coordinating every intelligent subsystem inside
JARVIS — 10 feature modules spanning goal management, task planning, a
full decision engine, autonomous execution, resource planning,
multi-agent orchestration, predictive intelligence, safety &
governance, analytics, and an SDK make it a cross-cutting orchestration
platform, not a standalone planning feature; sized consistently with
this roadmap's other XL milestones, e.g. M14 Security Platform, M20
Predictive Intelligence Platform, M23A Robotics & Hardware Control
Platform)*.

**Acceptance criteria:**
1. Goal Management architecture is documented, including goal
   hierarchy, persistence, and history.
2. Task Planning is documented, including reuse of M7 Workflow
   Intelligence's execution primitives.
3. Decision Engine is documented, including its dependency on M19 and
   M20 for context and forecasts, and that every decision is
   explainable and overridable.
4. Multi-Agent Orchestration is documented, including coordination of
   M5A Agent Runtime instances and conflict resolution.
5. Autonomous Execution is documented, including approval workflow
   gating for flagged actions.
6. Rollback is documented as always available during autonomous
   execution, never an optional add-on.
7. Recovery (checkpoints, resume, retry) is documented for interrupted
   or failed executions.
8. Resource Planner is documented, including local/cloud and device
   selection reusing M22 and M21/M23A's existing device models.
9. Predictive Intelligence is documented, including direct consumption
   of M20's Behaviour/Risk/Opportunity Intelligence modules.
10. Planning Analytics is documented, including how it feeds M20A
    rather than duplicating its dashboard.
11. Planning SDK & APIs are documented as the standardized integration
    surface for future milestones and third-party plugins.
12. API stability is documented as a binding constraint for the
    Planning SDK & APIs module.
13. Performance is documented — planning and decision-making meet a
    defined latency budget appropriate for real-time orchestration.
14. Explainability is documented as binding for the Decision Engine —
    no black-box decisions.
15. Governance is documented, including the kill switch, emergency
    stop, compliance engine, and audit logging.
16. Offline planning is documented — Goal Management, Task Planning,
    and Decision Engine operate with zero network dependency when
    running against local-only agents and devices.
17. Distributed execution is documented, including how Multi-Agent
    Orchestration coordinates across M23 Distributed JARVIS's
    multi-device transport.
18. Cross-milestone integrations (M1, M5, M5A, M6, M9, M10, M13, M14,
    M18, M19, M20, M20A, M21, M22, M23, M23A) are documented per
    module, and cross-platform compatibility with every device class
    M23A already supports is verified.
19. Internal consistency is verified across this milestone's modules,
    architecture notes, dependencies, and acceptance criteria.
20. Roadmap formatting is preserved and consistent with every other
    redesigned/added milestone in this document.

### M24 — Production Release

*(Formerly "Release Engineering" — see §9.)*

**Objective:** ship `v1.0.0`.

**Key features:**
- Regression Testing — a full, automated pass across every milestone
  M0–M23's acceptance criteria, not just the newest one.
- Performance Optimization — a final pass informed by M20A's
  analytics data.
- Security Audit — a comprehensive audit beyond M14's per-milestone
  threat modeling, covering the whole system as shipped.
- Documentation — this roadmap and every companion doc reviewed for
  accuracy against the actual `v1.0.0` codebase.
- Installer — Windows installer (Inno Setup wrapping the PyInstaller
  build), building on M5.5's packaging foundations.
- Auto Update — delta-patch auto-updater.
- Code Signing — EV certificate, closing the M5.5 "no code-signing
  certificate configured" gap.
- Stable Release.
- Long-Term Support — a defined support/maintenance policy for
  `1.x`.

**Dependencies:** every prior milestone.

**Complexity:** L.

**Acceptance criteria:**
1. Double-click install → working app in <2 minutes on a fresh
   Windows 11 machine.
2. Every milestone's own acceptance criteria still pass in the final
   regression run.
3. The security audit closes with no critical findings outstanding.

### M25 — Cognitive Intelligence Platform

*(Added Jul 2026, as a new top-level milestone immediately after M24 —
not a redesign, renumbering, or replacement of any existing milestone.
M24 — Production Release is unchanged; see the changelog addendum at
the end of this document. M25 marks the start of the roadmap's
post-`v1.0.0` work — thematically "the beginning of JARVIS OS Version
2.0" — while its actual semantic version follows this document's
existing §6 policy: a MINOR bump (`1.1.0`), since MAJOR bumps are
reserved for `1.0.0` itself and future breaking changes to the public
plugin/agent-tool API surface, neither of which this milestone
introduces on its own.)*

**Objective:** give JARVIS a complete cognitive architecture that
continuously improves itself, learns from experience, refines its own
reasoning, adapts to the user, and evolves over time. Where M23B
Autonomous Planning & Decision Engine decides **what to do**, M25
decides **how to think** — the two are distinct, complementary
subsystems: planning consumes cognition's outputs (refined reasoning,
adapted preferences), cognition never executes actions itself.

**Key features (organized into 10 modules):**

#### Cognitive Memory
- Episodic memory
- Semantic memory
- Working memory
- Long-term memory
- Memory linking
- Memory compression
- Forgetting policies
- Context recall
- Memory importance scoring
- Memory indexing

The foundational substrate every other module in this milestone builds
on; structures M3 Memory Platform's raw storage and M19's Knowledge
Graph entities into episodic/semantic/working memory layers rather
than maintaining a third, competing store.

#### Meta Reasoning
- Reasoning about reasoning
- Confidence evaluation
- Self-evaluation
- Error detection
- Alternative solution generation
- Reflection loops
- Chain validation
- Strategy comparison
- Explanation engine
- Reasoning optimization

Evaluates and improves M5A Agent Runtime's own reasoning chains and
M23B's Decision Engine outputs after the fact — this module critiques
and explains reasoning, it does not itself make or execute decisions.

#### Continuous Learning
- Learning from interactions
- Learning from corrections
- Adaptive knowledge
- Experience replay
- Incremental learning
- Knowledge refinement
- Skill acquisition
- Knowledge validation
- Learning policies
- Improvement tracking

Extends M16 Reflection Engine's learning-from-experience scope into a
continuous, incremental process rather than a periodic reflection pass
— reads M16's reflection sessions as one of its learning signals.

#### Human Preference Modeling
- User habits
- User preferences
- Communication style
- Personal workflows
- Decision preferences
- Context adaptation
- Routine detection
- Personalized recommendations
- Interaction history
- Preference evolution

Reads and refines M15 Personality Engine's Adaptive Behaviour module
and M17 Companion Intelligence's Personalization Engine rather than
maintaining a second, competing preference model — this module is
where those milestones' preference data gets continuously updated.

#### Emotional Intelligence
- Emotion recognition
- Conversation tone analysis
- Empathetic response generation
- Mood estimation
- Social awareness
- Interaction adaptation
- Emotional memory
- Conversation continuity
- Response balancing
- Trust modeling

Extends M15 Personality Engine's Emotional Intelligence module with
continuously-learned emotional memory and trust modeling rather than a
static, configured emotional profile.

#### Knowledge Evolution
- Knowledge refinement
- Conflict resolution
- Source confidence
- Knowledge merging
- Version history
- Automatic updates
- Knowledge aging
- Fact validation
- Knowledge graph enrichment
- Citation tracking

Keeps M19's Knowledge Graph Core accurate over time — conflict
resolution and fact validation operate on M19's existing entities and
relationships, this module never maintains a parallel knowledge store.

#### Cognitive Analytics
- Thinking performance
- Learning metrics
- Memory utilization
- Decision quality
- Adaptation score
- Reflection statistics
- User satisfaction metrics
- Cognitive efficiency
- Knowledge growth
- Intelligence reports

Feeds M20A Analytics & Observability Platform's Dashboard Platform and
Reporting Platform modules rather than shipping a competing dashboard.

#### Cognitive Safety
- Bias detection
- Hallucination monitoring
- Reasoning validation
- Confidence thresholds
- Ethical safeguards
- Privacy preservation
- Human override
- Safety policies
- Risk analysis
- Audit logs

Applies M14 Security Platform's guarantees to cognition itself — every
self-improvement action is policy-evaluated and audit-logged, and a
human override is always available, consistent with M23B's own
Safety & Governance module for planning.

#### Self Improvement Engine
- Capability analysis
- Weakness detection
- Improvement planning
- Skill optimization
- Performance tuning
- Feedback integration
- Goal refinement
- Automatic optimization
- Learning roadmap
- Long-term evolution

The module that closes the loop — reads Cognitive Analytics and
Cognitive Safety's outputs to plan its own improvement, and hands
concrete improvement goals to M23B's Goal Management module for
execution rather than executing changes itself.

#### Cognitive SDK & APIs
- Memory APIs
- Learning APIs
- Reasoning APIs
- Reflection APIs
- Personality APIs
- Analytics APIs
- Plugin SDK
- Testing framework
- Documentation
- Sample integrations

The standardized surface every future intelligence milestone (and
third-party plugin) integrates against — new cognitive capabilities
are added without modifying the core architecture.

**Architecture notes** *(binding constraints for whenever this
milestone is implemented):*
- Modular cognition — each of the 10 modules above is independently
  developable, testable, and replaceable.
- Explainable reasoning — Meta Reasoning's explanation engine makes
  every reasoning chain inspectable, never a black box.
- Continuous adaptation — Continuous Learning and Human Preference
  Modeling update incrementally, not only on scheduled reflection
  passes.
- Human-centered intelligence — cognition serves the user's own goals
  and preferences; it does not optimize for engagement or any
  objective the user hasn't set.
- Privacy-first learning — Cognitive Memory and Human Preference
  Modeling never learn from or retain data outside M14 Security
  Platform's existing privacy boundaries.
- Transparent decision making — every self-improvement action taken by
  the Self Improvement Engine is logged and explainable via Meta
  Reasoning's explanation engine.
- Local-first cognition — reasoning and learning run locally whenever
  practical, consistent with this roadmap's local-first charter (§1).
- Cloud-assisted learning is optional and policy-driven, mirroring M22
  Edge AI Platform's Hybrid AI Execution module.
- Safe self-improvement — the Self Improvement Engine proposes
  improvement goals, it never silently modifies JARVIS's own reasoning
  or behavior without passing through Cognitive Safety's human
  override path.
- No circular dependencies — M25 consumes planning services from M23B
  and data from M1, M5, M5A, M6, M9, M10, M13, M14, M18, M19, M20,
  M20A, M21, M22, M23, M23A, and M24, and in turn publishes cognitive
  services (refined reasoning, learned preferences, emotional context)
  for all future intelligence milestones to consume — it does not
  require any milestone built after it to operate.

**Future expansion:** Lifelong learning, autonomous research, creative
reasoning, scientific discovery, AI tutoring, team cognition, swarm
intelligence, cross-device cognition, cognitive simulation, AGI
preparation, self-directed improvement, and collective intelligence —
all documented as future scope only; none require changes to the core
architecture defined above.

**Dependencies:** M1 (Ollama provider foundation), M5 (Desktop
Platform), M5A (Agent Runtime), M6 (Vision & Multimodal), M11
(Integrations & Cloud Platform), M10A (Universal Search & Knowledge
Platform), M13 (Desktop Intelligence), M14 (Security Platform), M18
(Self-Healing &
Diagnostics), M19 (Knowledge Graph & Digital Twin Platform — knowledge
this milestone evolves), M20 (Predictive Intelligence Platform), M20A
(Analytics & Observability Platform), M21 (Mobile Platform), M22 (Edge
AI Platform), M23 (Distributed JARVIS), M23A (Robotics & Hardware
Control Platform), M23B (Autonomous Planning & Decision Engine —
consumes this milestone's cognitive outputs), M24 (Production Release —
the stable `v1.0.0` foundation this milestone builds on).

**Complexity:** XL *(M25 introduces the cognitive architecture
responsible for lifelong learning and adaptive intelligence — 10
feature modules spanning cognitive memory, meta reasoning, continuous
learning, preference modeling, emotional intelligence, knowledge
evolution, analytics, safety, self-improvement, and an SDK make it a
foundational post-1.0 platform, not a standalone learning feature;
sized consistently with this roadmap's other XL milestones, e.g. M14
Security Platform, M20 Predictive Intelligence Platform, M23B
Autonomous Planning & Decision Engine)*.

**Acceptance criteria:**
1. Cognitive Memory architecture is documented, including its
   structuring of M3/M19 data into episodic/semantic/working layers
   rather than a third competing store.
2. Meta Reasoning is documented, including that it critiques and
   explains M5A/M23B's reasoning without itself executing decisions.
3. Continuous Learning is documented, including its extension of M16
   Reflection Engine into an incremental process.
4. Human Preference Modeling is documented, including its refinement
   of M15's Adaptive Behaviour and M17's Personalization Engine.
5. Emotional Intelligence is documented, including its extension of
   M15's Emotional Intelligence module with learned trust modeling.
6. Knowledge Evolution is documented, including that it operates on
   M19's existing entities rather than a parallel knowledge store.
7. Cognitive Analytics is documented, including how it feeds M20A
   rather than duplicating its dashboard.
8. Cognitive Safety is documented, including bias detection,
   hallucination monitoring, and the human override path.
9. Self Improvement Engine is documented, including that it hands
   improvement goals to M23B for execution rather than acting itself.
10. Cognitive SDK & APIs are documented as the standardized surface for
    future intelligence milestones and third-party plugins.
11. API stability is documented as a binding constraint for the
    Cognitive SDK & APIs module.
12. Performance is documented — reasoning, learning, and memory
    operations meet a defined latency budget.
13. Explainability is documented as binding for Meta Reasoning — no
    black-box reasoning chains.
14. Privacy is documented — Cognitive Memory and Human Preference
    Modeling never exceed M14's existing privacy boundaries.
15. Cross-platform compatibility is documented across every device
    class already supported by M21 Mobile Platform and M23A Robotics &
    Hardware Control Platform.
16. Long-term learning is documented — Continuous Learning and the
    Self Improvement Engine operate incrementally over the system's
    full lifetime, not only during onboarding.
17. Human oversight is documented — every Self Improvement Engine
    action passes through Cognitive Safety's human override path.
18. Continuous adaptation is documented — Human Preference Modeling and
    Emotional Intelligence update incrementally, not only on scheduled
    passes.
19. Testing is documented — the Cognitive SDK & APIs module's testing
    framework supports validating new cognitive integrations end-to-end.
20. Documentation and internal consistency are verified across this
    milestone's modules, architecture notes, dependencies, and
    acceptance criteria, and roadmap formatting is preserved and
    consistent with every other milestone in this document.

### M26 — Self-Learning & Autonomous Evolution Platform

*(Added Jul 2026, as a new top-level milestone immediately after
M25 — not a redesign, renumbering, or replacement of any existing
milestone. M24 — Production Release and M25 — Cognitive Intelligence
Platform are both unchanged; see the changelog addendum at the end of
this document. M26 builds directly on M25's cognitive architecture.)*

**Objective:** continuously improve every AI capability in JARVIS
through experience, feedback, optimization, and autonomous evolution.
The three-milestone distinction is explicit and binding: **M23B
decides what to do, M25 decides how to think, M26 decides how to
improve itself over time.** M26 never executes actions directly — it
refines the capabilities M23B plans with and M25 reasons with.

**Key features (organized into 10 modules):**

#### Self-Learning Engine
- Continuous learning
- Incremental learning
- Online learning
- Offline learning
- Learning sessions
- Learning scheduling
- Learning prioritization
- Learning confidence
- Learning validation
- Learning history

The foundational substrate every other module in this milestone builds
on; extends M25's Continuous Learning module into a dedicated
scheduling/session/prioritization engine rather than a second,
competing learning loop.

#### Experience Replay
- Experience storage
- Success replay
- Failure replay
- Replay prioritization
- Scenario replay
- Temporal replay
- Memory sampling
- Experience weighting
- Replay optimization
- Learning replay analytics

Replays experiences stored in M25's Cognitive Memory module rather
than maintaining a second experience store — this module decides
*which* stored experiences the Self-Learning Engine trains on and in
what order.

#### Skill Acquisition
- New skill learning
- Skill hierarchy
- Skill refinement
- Skill validation
- Skill transfer
- Skill composition
- Skill retirement
- Capability expansion
- Skill confidence
- Skill versioning

Expands what M5A Agent Runtime's tool registry and M23B's Multi-Agent
Orchestration can call on — new or refined skills are validated here
before becoming available to those milestones, not injected directly.

#### Knowledge Refinement
- Knowledge correction
- Knowledge merging
- Duplicate removal
- Source confidence
- Conflict resolution
- Fact refinement
- Semantic optimization
- Knowledge consistency
- Knowledge aging
- Knowledge quality scoring

Operates on M19's Knowledge Graph Core and M25's Knowledge Evolution
module's own outputs — this module is the continuous quality pass over
knowledge those two milestones already maintain, never a parallel
store.

#### Autonomous Optimization
- Performance optimization
- Workflow optimization
- Resource optimization
- Planning optimization
- Prompt optimization
- Runtime optimization
- Scheduling optimization
- Recommendation optimization
- Decision optimization
- Continuous optimization

Tunes existing subsystems in place — M7 Workflow Intelligence's
workflows, M22 Edge AI Platform's runtime, M23B's planning and
decisions, M20's recommendations — rather than replacing any of them
with a competing implementation.

#### Feedback Integration
- Human feedback
- AI feedback
- Explicit feedback
- Implicit feedback
- Reinforcement learning hooks
- Preference refinement
- Error correction
- Continuous evaluation
- Feedback history
- Feedback confidence

The primary input channel for every other module above; reads
explicit user corrections and implicit signals (M20A's User Experience
Analytics) rather than each module collecting feedback independently.

#### Evolution Analytics
- Learning metrics
- Skill growth
- Capability evolution
- Performance trends
- Optimization reports
- Knowledge growth
- Reflection statistics
- Improvement dashboards
- Historical comparisons
- Evolution forecasting

Feeds M20A Analytics & Observability Platform's Dashboard Platform and
Reporting Platform modules rather than shipping a competing dashboard.

#### Learning Governance
- Learning policies
- Safety constraints
- Ethical learning
- Approval workflows
- Rollback policies
- Version control
- Audit logging
- Compliance validation
- Change management
- Human oversight

Applies M14 Security Platform's guarantees to every learning and
optimization action — every change is versioned, rollback-capable, and
audit-logged, consistent with M25's own Cognitive Safety module and
M23B's Safety & Governance module.

#### Autonomous Improvement Engine
- Weakness detection
- Improvement planning
- Automatic experiments
- Controlled optimization
- Capability scoring
- Bottleneck analysis
- Goal refinement
- Performance tuning
- Adaptive behavior
- Evolution roadmap

The module that closes the loop — extends M25's Self Improvement
Engine with controlled, experiment-driven optimization, and hands
concrete improvement goals to M23B's Goal Management module for
execution rather than executing changes itself.

#### Self-Learning SDK & APIs
- Learning APIs
- Skill APIs
- Evolution APIs
- Feedback APIs
- Analytics APIs
- Plugin SDK
- Testing framework
- Simulation APIs
- Documentation
- Sample integrations

The standardized surface every future milestone (and third-party
plugin) integrates against to contribute learning signals or consume
evolution state — new capabilities are added without modifying the
core architecture.

**Architecture notes** *(binding constraints for whenever this
milestone is implemented):*
- Continuous learning — the Self-Learning Engine never stops between
  discrete "training runs"; it learns incrementally, always.
- Safe evolution — every change the Autonomous Improvement Engine makes
  is rollback-capable via Learning Governance's version control.
- Human-in-the-loop learning — Learning Governance's approval workflows
  gate any change that Learning Policies classify as requiring
  sign-off.
- Explainable improvement — every optimization and skill change is
  traceable back to the feedback or experience that produced it.
- Local-first learning — the Self-Learning Engine and Experience Replay
  run locally whenever practical, consistent with this roadmap's
  local-first charter (§1).
- Cloud-assisted optimization is optional and policy-driven, mirroring
  M22 Edge AI Platform's Hybrid AI Execution module.
- Privacy-preserving adaptation — Feedback Integration and Experience
  Replay never exceed M14 Security Platform's existing privacy
  boundaries.
- Versioned learning — every skill, knowledge refinement, and
  optimization is versioned, so any change can be attributed and
  reverted.
- Modular evolution — each of the 10 modules above is independently
  developable, testable, and replaceable.
- No circular dependencies — M26 consumes cognitive services from M25
  and data from M1, M5, M5A, M6, M9, M10, M13, M14, M18, M19, M20,
  M20A, M21, M22, M23, M23A, M23B, and M24, and in turn publishes
  self-improvement services (refined skills, tuned parameters, updated
  knowledge) for future milestones to consume — it does not require any
  milestone built after it to operate.

**Future expansion:** Federated learning, cross-device learning, swarm
learning, AI mentor systems, autonomous curriculum generation,
scientific learning, self-generated datasets, synthetic experience
generation, evolution simulation, lifelong autonomous learning,
collective intelligence, and AGI capability evolution — all documented
as future scope only; none require changes to the core architecture
defined above.

**Dependencies:** M1 (Ollama provider foundation), M5 (Desktop
Platform), M5A (Agent Runtime — skills feed its tool registry), M6
(Vision & Multimodal), M11 (Integrations & Cloud Platform), M10 (Knowledge
Engine), M13 (Desktop Intelligence), M14 (Security Platform), M18
(Self-Healing & Diagnostics), M19 (Knowledge Graph & Digital Twin
Platform — knowledge this milestone refines), M20 (Predictive
Intelligence Platform), M20A (Analytics & Observability Platform), M21
(Mobile Platform), M22 (Edge AI Platform), M23 (Distributed JARVIS),
M23A (Robotics & Hardware Control Platform), M23B (Autonomous Planning
& Decision Engine — receives this milestone's improvement goals), M24
(Production Release — the stable `v1.0.0` foundation), M25 (Cognitive
Intelligence Platform — this milestone's direct cognitive foundation:
Cognitive Memory feeds Experience Replay, Knowledge Evolution feeds
Knowledge Refinement, and Self Improvement Engine is extended by
Autonomous Improvement Engine).

**Complexity:** XL *(M26 is responsible for lifelong self-learning and
autonomous capability evolution across the entire JARVIS platform — 10
feature modules spanning self-learning, experience replay, skill
acquisition, knowledge refinement, autonomous optimization, feedback
integration, evolution analytics, governance, autonomous improvement,
and an SDK make it a foundational post-1.0 platform, not a standalone
learning feature; sized consistently with this roadmap's other XL
milestones, e.g. M14 Security Platform, M23B Autonomous Planning &
Decision Engine, M25 Cognitive Intelligence Platform)*.

**Acceptance criteria:**
1. Self-Learning Engine architecture is documented, including its
   extension of M25's Continuous Learning module into a dedicated
   scheduling/session engine.
2. Experience Replay is documented, including its dependency on M25's
   Cognitive Memory as the sole experience store.
3. Skill Acquisition is documented, including validation before new
   skills reach M5A's tool registry or M23B's orchestration.
4. Knowledge Refinement is documented, including that it operates on
   M19/M25's existing knowledge rather than a parallel store.
5. Autonomous Optimization is documented, including that it tunes
   M7/M20/M22/M23B in place rather than replacing them.
6. Feedback Integration is documented, including its consumption of
   M20A's User Experience Analytics as an implicit-feedback source.
7. Evolution Analytics is documented, including how it feeds M20A
   rather than duplicating its dashboard.
8. Learning Governance is documented, including rollback, version
   control, and audit logging per M14.
9. Autonomous Improvement Engine is documented, including that it hands
   improvement goals to M23B for execution rather than acting itself.
10. Self-Learning SDK & APIs are documented as the standardized surface
    for future milestones and third-party plugins.
11. API stability is documented as a binding constraint for the
    Self-Learning SDK & APIs module.
12. Explainability is documented as binding — every optimization and
    skill change traces back to its originating feedback or experience.
13. Privacy is documented — Feedback Integration and Experience Replay
    never exceed M14's existing privacy boundaries.
14. Safety is documented — every Autonomous Improvement Engine change
    is rollback-capable and gated by Learning Governance where required.
15. Human oversight is documented — approval workflows gate any change
    Learning Policies classify as requiring sign-off.
16. Performance is documented — learning, replay, and optimization
    operations meet a defined latency/resource budget.
17. Scalability is documented — Self-Learning Engine and Experience
    Replay operate incrementally over the system's full lifetime
    without unbounded resource growth (forgetting/aging policies
    inherited from M25's Cognitive Memory and this milestone's own
    Knowledge Refinement).
18. Testing is documented — the Self-Learning SDK & APIs module's
    testing and simulation framework supports validating new learning
    integrations end-to-end.
19. Cross-platform compatibility is documented across every device
    class already supported by M21 Mobile Platform and M23A Robotics &
    Hardware Control Platform.
20. Documentation and internal consistency are verified across this
    milestone's modules, architecture notes, dependencies, and
    acceptance criteria, and roadmap formatting is preserved and
    consistent with every other milestone in this document.

### M27 — World Model & Environmental Intelligence Platform

*(Added Jul 2026, as a new top-level milestone immediately after
M26 — not a redesign, renumbering, or replacement of any existing
milestone. M24 — Production Release, M25 — Cognitive Intelligence
Platform, and M26 — Self-Learning & Autonomous Evolution Platform are
all unchanged; see the changelog addendum at the end of this document.)*

**Objective:** give JARVIS a persistent, continuously-maintained
understanding of the physical and digital world it operates in. The
milestone distinction is explicit and binding: **M23B decides what to
do, M25 decides how to think, M26 decides how to improve, and M27
understands the world in which those decisions occur.** M27 publishes
world knowledge — it does not execute actions directly.

**Key features (organized into 10 modules):**

#### World Model Core
- Persistent world model
- Entity graph
- Object registry
- Environment representation
- Scene management
- Relationship mapping
- Spatial indexing
- Temporal state tracking
- Environment snapshots
- World versioning

The foundational substrate every other module in this milestone builds
on; extends M19's Knowledge Graph Core with a persistent, versioned
world representation rather than a second, competing entity graph.

#### Spatial Intelligence
- Indoor mapping
- Outdoor mapping
- Room awareness
- Distance estimation
- Navigation graphs
- Coordinate systems
- Zones
- Boundaries
- Safe areas
- Spatial reasoning

Supplies the spatial layer M23A's Robotics Runtime navigates against
and M12 Smart Home & IoT Platform's room-aware automations read, rather
than each maintaining its own map.

#### Object Intelligence
- Object classification
- Object tracking
- State detection
- Ownership
- Capabilities
- Object history
- Object lifecycle
- Object relationships
- Object confidence
- Inventory management

Tracks physical objects (recognized via M6 Vision & Multimodal and
M23A's Sensor Framework) as first-class World Model Core entities
rather than a separate, disconnected inventory system.

#### Environmental Awareness
- Weather
- Lighting
- Temperature
- Noise
- Occupancy
- Air quality
- Water status
- Energy usage
- Device status
- Environmental events

Aggregates M23A's Sensor Framework readings into a coherent
environmental picture, consumed by M12 Smart Home & IoT Platform's
automation triggers rather than each subsystem polling sensors
independently.

#### Human Context Intelligence
- Presence detection
- Identity abstraction
- Activity recognition
- Routine awareness
- Group context
- Social context
- Location history
- Interaction history
- Context confidence
- Temporal context

Feeds M19's Context Engine and M17 Companion Intelligence's Social &
Communication Intelligence module with world-grounded human context —
identity is abstracted, never raw biometric data, consistent with M14
Security Platform's privacy guarantees.

#### Digital World Intelligence
- Devices
- Applications
- Services
- Cloud resources
- Network topology
- Connected accounts
- Digital assets
- Active sessions
- Service health
- Dependency mapping

The digital-world counterpart to Spatial/Object Intelligence — tracks
M11 Integrations & Cloud Platform's connected services and M21 Mobile Platform's
registered devices as World Model Core entities alongside physical
ones, one unified world model rather than two disconnected ones.

#### World Analytics
- Environment analytics
- Object statistics
- Spatial analytics
- Context analytics
- Occupancy analytics
- Device analytics
- Event analytics
- Trend analysis
- Historical reports
- Predictive insights

Feeds M20A Analytics & Observability Platform's Dashboard Platform and
Reporting Platform modules rather than shipping a competing dashboard.

#### World Safety
- Hazard detection
- Restricted zones
- Safety policies
- Emergency awareness
- Privacy boundaries
- Secure mapping
- Access control
- Risk scoring
- Audit logging
- Compliance validation

Applies M14 Security Platform's guarantees to world knowledge itself —
spatial and object data is access-controlled and audit-logged, and
hazard/restricted-zone detection hands off to M18 Self-Healing &
Diagnostics Platform and M23A's safety-first actuator guarantees
rather than acting on hazards directly.

#### Simulation Engine
- Environment simulation
- Scenario simulation
- Decision simulation
- Resource simulation
- Multi-agent simulation
- Robot simulation
- Predictive simulation
- Risk simulation
- Rollback simulation
- Testing scenarios

Lets M23B's Autonomous Execution and M23A's Robotics Runtime rehearse
against a simulated version of the World Model before acting on the
real world — reuses M23A's own Robotics Runtime simulation support
rather than a second, disconnected simulator.

#### World SDK & APIs
- World APIs
- Mapping APIs
- Object APIs
- Context APIs
- Simulation APIs
- Analytics APIs
- Plugin SDK
- Documentation
- Testing tools
- Sample integrations

The standardized surface every future milestone (and third-party
plugin) integrates against to read or contribute world knowledge — new
sensors, mapping providers, and world-aware capabilities are added
without modifying the core architecture.

**Architecture notes** *(binding constraints for whenever this
milestone is implemented):*
- Persistent world representation — the World Model persists across
  restarts and sessions; it is not rebuilt from scratch each time.
- Local-first world model — spatial, object, and environmental data is
  stored and reasoned over locally whenever practical, consistent with
  this roadmap's local-first charter (§1).
- Privacy-preserving context — Human Context Intelligence abstracts
  identity rather than storing raw biometric or surveillance-grade
  data, and never exceeds M14 Security Platform's existing privacy
  boundaries.
- Modular intelligence — each of the 10 modules above is independently
  developable, testable, and replaceable.
- Spatial abstraction — Spatial Intelligence exposes zones/rooms/
  coordinates as a stable abstraction, insulating consumers from
  changes in underlying mapping providers.
- Temporal consistency — World Model Core's temporal state tracking
  ensures consumers can query "what was true at time T," not just
  "what's true now."
- Explainable world state — every fact in the World Model is traceable
  back to the sensor reading, vision observation, or integration event
  that produced it.
- Safe environmental reasoning — World Safety's hazard detection and
  risk scoring never trigger an action directly; they hand off to M18
  and M23A.
- Digital/physical integration — Digital World Intelligence and
  Spatial/Object Intelligence share one World Model Core rather than
  maintaining separate physical and digital world models.
- No circular dependencies — M27 consumes services from M1, M5, M5A,
  M6, M9, M10, M13, M14, M18, M19, M20, M20A, M21, M22, M23, M23A,
  M23B, M24, M25, and M26, and in turn publishes world knowledge
  services for all future intelligence layers to consume — it does not
  require any milestone built after it to operate.

**Future expansion:** Digital twins, city-scale world models,
multi-building mapping, autonomous navigation, robot fleet
coordination, AR integration, VR integration, satellite awareness,
vehicle world models, space robotics, industrial digital twins, and
planet-scale knowledge graphs — all documented as future scope only;
none require changes to the core architecture defined above.

**Dependencies:** M1 (Ollama provider foundation), M5 (Desktop
Platform), M5A (Agent Runtime), M6 (Vision & Multimodal — object/scene
recognition), M11 (Integrations & Cloud Platform — digital world
sources), M10A (Universal Search & Knowledge Platform), M13 (Desktop
Intelligence), M14 (Security
Platform), M18 (Self-Healing & Diagnostics), M19 (Knowledge Graph &
Digital Twin Platform — World Model Core extends this), M20
(Predictive Intelligence Platform), M20A (Analytics & Observability
Platform), M21 (Mobile Platform — digital device registry), M22 (Edge
AI Platform), M23 (Distributed JARVIS), M23A (Robotics & Hardware
Control Platform — sensor data source and simulation reuse), M23B
(Autonomous Planning & Decision Engine — consumes world knowledge for
planning), M24 (Production Release), M25 (Cognitive Intelligence
Platform), M26 (Self-Learning & Autonomous Evolution Platform).

**Complexity:** XL *(M27 is responsible for maintaining a persistent
understanding of the physical and digital environments in which
JARVIS operates — 10 feature modules spanning world model core,
spatial intelligence, object intelligence, environmental awareness,
human context, digital world intelligence, analytics, safety,
simulation, and an SDK make it a foundational platform underneath
every world-aware milestone (M12, M20, M23A, M23B), not a standalone
mapping feature; sized consistently with this roadmap's other XL
milestones, e.g. M14 Security Platform, M19 Knowledge Graph & Digital
Twin Platform, M23A Robotics & Hardware Control Platform)*.

**Acceptance criteria:**
1. World Model Core architecture is documented, including its
   extension of M19's Knowledge Graph Core rather than a second,
   competing entity graph.
2. Spatial Intelligence is documented, including its consumption by
   M23A's Robotics Runtime and M12's room-aware automations.
3. Object Intelligence is documented, including its dependency on M6
   Vision & Multimodal and M23A's Sensor Framework for recognition.
4. Environmental Awareness is documented, including aggregation of
   M23A's Sensor Framework readings for M12's automation triggers.
5. Human Context Intelligence is documented, including identity
   abstraction and its feed into M19's Context Engine and M17's Social
   & Communication Intelligence module.
6. Digital World Intelligence is documented, including unification with
   physical-world entities in one World Model Core.
7. World Analytics is documented, including how it feeds M20A rather
   than duplicating its dashboard.
8. World Safety is documented, including hand-off to M18 and M23A
   rather than acting on hazards directly.
9. Simulation Engine is documented, including reuse of M23A's Robotics
   Runtime simulation support and its use by M23B's Autonomous
   Execution.
10. World SDK & APIs are documented as the standardized surface for
    future milestones and third-party plugins.
11. API stability is documented as a binding constraint for the World
    SDK & APIs module.
12. Explainability is documented as binding — every World Model fact
    traces back to the sensor reading, vision observation, or
    integration event that produced it.
13. Privacy is documented — Human Context Intelligence never exceeds
    M14's existing privacy boundaries and abstracts identity rather
    than storing raw biometric data.
14. Scalability is documented — World Model Core's spatial indexing and
    temporal state tracking operate without unbounded resource growth
    as entities and history accumulate.
15. Performance is documented — spatial queries and object lookups meet
    a defined latency budget appropriate for real-time consumers
    (M23A, M23B).
16. Cross-platform compatibility is documented across every device
    class already supported by M21 Mobile Platform and M23A Robotics &
    Hardware Control Platform.
17. Documentation is complete for all 10 modules, architecture notes,
    dependencies, and acceptance criteria.
18. Testing is documented — the World SDK & APIs module's testing
    tools support validating new world-model integrations end-to-end.
19. Versioning is documented — World Model Core's world versioning
    lets consumers pin to or migrate between world-model schema
    versions safely.
20. Reliability is documented — World Model Core persists correctly
    across restarts, and World Safety's audit logging captures every
    access to sensitive spatial/human-context data.

---

## 9. Feature carry-forward map

Every planned feature from the previous version of this roadmap is
preserved — nothing was dropped in this reorganization. Where a
feature's original milestone number no longer matches the new
milestone scheme (§8), this table is the traceable record of where it
moved and why. **"Now" column updated Aug 2026** to reflect the
frontend-migration retitling of M8–M11 (§8) — the "Previously"→original-
"Now" mapping below is unchanged history; only the milestone *names* in
the rightmost two columns were refreshed so this table doesn't drift
from §8. See §8's own "Retitled Aug 2026" notes for the full reasoning
behind each rename.

| Feature | Previously | Now | Why |
|---------|-----------|-----|-----|
| Vision & Multimodal (screen/camera/OCR) | old M6 | **M6** | Same slot — expanded with the full feature list from this reorganization's brief. |
| Plugin SDK / Loader / Store | old M7 | **M9** Plugin Platform *(moved again, Aug 2026, from M8 — see §8)* | Renumbered to make room for M6/M7's new agent-workflow scope ahead of it; then moved a second time when M8 itself was retitled React Frontend & Desktop Experience. |
| Command Palette | old M8 | **M11B** Productivity Suite *(moved again, Aug 2026, from M11 — see §8)* | Folded in as a productivity primitive alongside Clipboard/Files/Tasks rather than kept as a standalone milestone; then split into its own lettered companion when M11 itself was retitled Integrations & Cloud Platform. |
| Clipboard Manager | old M8 | **M11B** Productivity Suite *(moved again, Aug 2026, from M11)* | Same reasoning as Command Palette. |
| File Manager tool | old M8 | **M11B** Productivity Suite *(moved again, Aug 2026, from M11)* | Same reasoning. |
| Native notifications | old M8 | **M11B** Productivity Suite *(moved again, Aug 2026, from M11)* | Same reasoning. |
| Task Manager | old M8 | **M11B** Productivity Suite *(moved again, Aug 2026, from M11)* (as "Tasks") | Merged with the personal-tasks feature already implied by "Productivity." |
| Smart Home Bridge (HA, MQTT, vendors) | old M9 | **M12** Smart Home | Renumbered only — feature list unchanged. |
| Wake Word & Always-Listening / streaming STT / VAD | old M10 | **§7 Cross-Platform Systems** | Reclassified as a continuous voice-quality workstream rather than a one-time milestone — it never had a natural "done" state distinct from ongoing tuning. |
| Coding / Document / Research Assistant, Email, Calendar, Media Controls | old M11 | **M11** Integrations & Cloud Platform (Email/Calendar) / **M11B** Productivity Suite (Coding/Document/Research/Media Controls) *(split, Aug 2026 — see §8)* | Originally one milestone number, expanded scope; split in the Aug 2026 pass into its external-integration half (M11) and local-productivity half (M11B). |
| SEO Assistant | old M11 | **M11A** SEO Intelligence | Split out into its own dedicated, significantly expanded milestone (GSC/GA4/Semrush/Ahrefs/rank tracking/technical SEO/content intelligence — far beyond the original one-line "SEO Assistant" bullet). |
| OS keyring, audit log, PII redaction, encryption at rest, kill-switch, per-plugin permission prompts, prompt-injection guardrails | old M12 | **M14** Security Platform | Renumbered to make room for M6–M13's new scope ahead of it. |
| E2EE cloud sync (own bucket) | old M13 | **M23** Distributed JARVIS | Moved later — now correctly sequenced after the Mobile Platform (M21) and Security Platform (M14) it depends on, rather than shipping before either existed. |
| Mobile companion, wearable integration | old M13 | **M21** Mobile Platform | Split out into its own dedicated milestone with a real feature list (Android, iOS, notifications, remote commands, mobile voice) instead of a two-line bullet inside a cloud-sync milestone. |
| Windows installer, code signing, auto-updater, crash reporter, first-run wizard, telemetry, landing page | old M14 | **M24** Production Release | Renumbered only — this is still the final, "ship v1.0" milestone; every prior milestone now depends on it instead of just M0–M13. |

**Entirely new scope in this reorganization** (no prior-roadmap
predecessor — genuinely new, long-term vision, not a renumbering):
M7 Workflow Intelligence, M11 Integrations & Cloud Platform, M10A
Universal Search & Knowledge Platform, M13 Computer Control, M13A AI
Sandbox, M14A Backup Platform, M15 Personality Engine, M16 Reflection
Engine, M17 Companion Intelligence, M17A Training Studio, M18
Diagnostics, M19 Intelligence Graph, M20 Predictive Intelligence, M20A
Analytics Platform, M22 Edge AI Platform, M23 Distributed JARVIS (the
distributed-systems half; the cloud-sync half carries forward from old
M13, see above).

**Aug 2026 frontend-migration carry-forward** (§8's own retitling —
distinct from the historical reorganization above; nothing here is a
renumbering, per the "zero renumbering" rule this pass follows):

| Feature | Previously | Now | Why |
|---------|-----------|-----|-----|
| Plugin SDK / Loader / Extension API / Permission Model / Store / Marketplace | M8 Plugin Platform | **M9** Runtime & Core Services (Plugin Platform module) + **M8** (Marketplace's React UI) | M8 retitled React Frontend & Desktop Experience; the plugin *system* is a runtime concern and moved to M9, the Marketplace's *UI* stays a React screen in M8. |
| API Gateway / OAuth / API Manager / Webhooks / Queue / Retry / Caching / Monitoring | M9 Integration Platform | **M11** Integrations & Cloud Platform | M9 retitled Runtime & Core Services; this scope merged into M11 alongside old M11's own integration-facing features. |
| Knowledge Graph / Persistent Memory / Reflection Foundation / Learning / Relationship Graph / Digital Twin Foundation | M10 Knowledge Engine | **M10A** Universal Search & Knowledge Platform | M10 retitled AI Orchestrator (formalizing the M5A agent graph); Knowledge Engine's own scope moved to a new lettered companion rather than being dropped. |
| Email / Calendar / Browser Intelligence / Google Workspace Integration | M11 Productivity Platform | **M11** Integrations & Cloud Platform | Kept at M11 alongside the absorbed M9 scope — the integration-facing half of the original Productivity Platform. |
| Tasks / Documents / Research Assistant / Coding Assistant / Command Palette / Clipboard Manager / File Manager / Native notifications / Media Controls | M11 Productivity Platform | **M11B** Productivity Suite | The local-productivity half of the original Productivity Platform, split into a new lettered companion when M11 itself was retitled. |
| Intent Engine / Planning / Context Engine / Tool Selection / Permission Validation / Execution / Verification / Learning / Streaming / Decision Engine | *(new)* | **M10** AI Orchestrator | Genuinely new scope from the Aug 2026 migration brief, formalizing M5A's existing `AgentOrchestrator` and absorbing M7 Phase 3's deferred cross-tool-parallelism work. |
| Goal Manager / Routine Learning / Preference Learning / Predictive Suggestions / Context Awareness / Daily Briefing / Assistant Intelligence | *(new)* | **M10B** Intelligence Layer | Genuinely new scope from the Aug 2026 migration brief, scoped as the backing engine M15/M16's existing modules consume rather than a duplicate of either. |
| Oracle Cloud sync / Android Companion pairing / Conflict Resolution / Offline Queue | *(new)* | **M11** Integrations & Cloud Platform | Genuinely new scope from the Aug 2026 migration brief. |

---

## 10. Complete feature backlog

Status legend:
✅ **Completed** · 🟡 **Planned** (scheduled milestone) · ⚪ **Future** (post-1.0) · 🔵 **Optional** (nice-to-have)

### Core AI
| Feature                       | Status | Milestone |
|-------------------------------|--------|-----------|
| Streaming chat                | ✅     | M1        |
| Non-streaming chat            | ✅     | M1        |
| System prompt customisation   | ✅     | M1        |
| Multi-provider switching (UI) | ✅     | M1        |
| Multi-turn context            | ✅     | M1        |
| Function / tool calling       | ✅ (agent-graph only, via structured-JSON prompting over `ILLMProvider` — not wired into the main Chat view yet) | M5A |
| Vision (image parts)          | 🟡     | M6        |
| Response caching              | 🔵     | any       |

### Voice
| Feature                       | Status | Milestone |
|-------------------------------|--------|-----------|
| Push-to-talk                  | ✅     | M2        |
| Toggle listen                 | ✅     | M2        |
| Local Whisper STT             | ✅     | M2        |
| OpenAI Whisper STT            | ✅     | M2        |
| OpenAI TTS                    | ✅     | M2        |
| Auto-speak replies            | ✅     | M2        |
| Playback speed control        | ✅     | M2        |
| Wake word                     | ✅     | M2        |
| ElevenLabs TTS                | ✅     | M2        |
| Piper TTS (offline)           | ✅     | M2        |
| Kokoro TTS (offline, optional)| ✅     | M2        |
| Edge TTS (free, streaming)    | ✅     | M2        |
| Streaming TTS (speak while synthesizing) | ✅ | M2  |
| Interrupt / barge-in          | ✅     | M2        |
| Streaming STT + partials      | 🟡     | §7 (continuous — see Feature carry-forward map) |
| VAD (silence trim)            | 🟡     | §7        |
| Deepgram STT                  | 🟡     | §7        |
| Mobile voice (PTT/continuous) | 🟡     | M21       |
| Voice cloning                 | ⚪     | post-1.0  |

### Memory & Knowledge

*(M19 was redesigned Jul 2026 from "Intelligence Graph" into a
complete enterprise-grade Knowledge Graph & Digital Twin Platform —
see M19's own §8 entry and the changelog addendum at the end of this
document. The Knowledge Graph / Relationship Graph / Digital Twin rows
below predate that redesign and are kept for continuity; each now
lives inside the module table that follows.)*

| Feature                       | Status | Milestone |
|-------------------------------|--------|-----------|
| SQLite chat history           | ✅     | M1        |
| Memory recall hook (contract) | ✅     | M2        |
| Semantic memory (Chroma, hybrid recall) | ✅ | M3   |
| Memory search/summarize/policy engine | ✅ | M3   |
| Memory export / import        | ✅     | M3        |
| Memory settings page          | ✅     | M3        |
| Timeline / browsing UI view   | ✅     | M3.1      |
| Semantic search UI (browse by type/date) | 🟡 partial (type/pinned/archived filters ship; keyword/semantic search box and date-range control not yet in the dialog) | M3.1 |
| Alembic migrations for memory schema | ✅ | M3.1  |
| PII redaction in memories     | 🟡     | M14       |
| Knowledge Graph                | 🟡     | M10 (foundation) / M19 (full) |
| Relationship Graph             | 🟡     | M10 / M19 |
| Digital Twin                   | 🟡     | M19       |
| Cross-device memory sync      | 🟡     | M23       |

### Knowledge Graph & Digital Twin Platform (M19 Modules)
| Feature                       | Status | Milestone |
|-------------------------------|--------|-----------|
| Knowledge Graph Core (graph architecture, entity management, relationship engine, semantic storage, indexing, context engine, versioning, configuration) | 🟡 | M19 |
| Digital Twin (user, device, desktop, smart home, workspace, AI, environment, timeline twins) | 🟡 | M19 |
| Entity Intelligence (people, organizations, projects, tasks, devices, applications, files, emails, calendar events, notes, documents, locations, rooms, smart devices) | 🟡 | M19 |
| Relationship Intelligence (entity, temporal, spatial, workflow relationships, ownership, dependencies, communication networks, context relationships) | 🟡 | M19 |
| Context Engine (current, historical, predicted, environmental, conversation, device, workspace, smart home context) | 🟡 | M19 |
| Semantic Search (natural language, cross-system, relationship, timeline, similarity, contextual search, graph traversal, semantic ranking) | 🟡 | M19 |
| Timeline Intelligence (personal, activity, conversation, workflow, project, device, memory timelines, event correlation) | 🟡 | M19 |
| Knowledge Reasoning (graph reasoning, context inference, dependency analysis, opportunity detection, decision support, cause & effect analysis, predictive reasoning, recommendation engine) | 🟡 | M19 |
| Knowledge Analytics (graph health, entity statistics, relationship density, knowledge coverage, confidence scores, knowledge growth, graph quality, analytics dashboard) | 🟡 | M19 |
| Developer Graph Tools (graph explorer, entity inspector, relationship viewer, timeline explorer, graph debugger, query console, graph visualizer, knowledge diagnostics) | 🟡 | M19 |

### Vision
| Feature                       | Status | Milestone |
|-------------------------------|--------|-----------|
| Screen capture                | 🟡     | M6        |
| OCR                           | 🟡     | M6        |
| Camera capture                | 🟡     | M6        |
| Screenshot / UI / chart / code / document understanding | 🟡 | M6 |
| Vision Agent Tool              | 🟡     | M6        |
| Desktop Vision (live control)  | 🟡     | M13       |
| Screen recording              | ⚪     | post-1.0  |
| Object detection              | ⚪     | post-1.0  |

### Windows Automation
| Feature                       | Status | Milestone |
|-------------------------------|--------|-----------|
| pywinauto adapter (interface) | ✅     | M0        |
| List / focus windows          | ✅     | M4        |
| Launch applications           | ✅     | M4        |
| Send text / hotkey            | ✅     | M4        |
| Parallel step execution       | ✅ wave-based `ActionExecutor` dispatch via `gather_with_concurrency`, satisfies M7's Acceptance Criterion 1 | M7 Phase 2 |
| Autonomous mouse/keyboard      | 🟡     | M13       |
| Native notifications          | 🟡     | M11       |
| File Manager tool             | 🟡     | M11       |

### Desktop Intelligence & Computer Control Platform

*(M13 was redesigned Jul 2026 from a flat "Computer Control" feature
list into a full Desktop Intelligence platform — see M13's own §8
entry and the changelog addendum at the end of this document. The
"Autonomous mouse/keyboard" row above predates that redesign and is
kept for continuity — it now lives inside the Desktop Control module
row below.)*

| Feature                       | Status | Milestone |
|-------------------------------|--------|-----------|
| Desktop Control (mouse/keyboard/clipboard/drag-drop, window & multi-monitor/virtual-desktop management, hotkeys) | 🟡 | M13 |
| UI Intelligence (native UI detection, accessibility API integration, OCR, control/menu/dialog/form recognition) | 🟡 | M13 |
| Desktop Vision (live/screenshot understanding, layout/chart/table/code recognition, IDE & browser context) | 🟡 | M13 |
| Application Intelligence (browser, file explorer, Office, IDE, terminal, PDF/media player, system settings) | 🟡 | M13 |
| Workflow Execution (goal-based automation, conditional/parallel logic, retries, checkpoints, rollback, approval) | 🟡 | M13 |
| AI Desktop Assistant (NL desktop commands, context-aware actions, desktop search, routine learning) | 🟡 | M13 |
| Desktop Memory (app usage history, workspace profiles, recent context, workflow/window-state memory) | 🟡 | M13 |
| Safety & Permissions (protected actions, confirmation policies, dry run mode, risk analysis, approval rules) | 🟡 | M13 |
| Performance & Reliability (action queue, background automation, retry engine, latency monitoring, metrics) | 🟡 | M13 |
| Developer Tools (automation recorder, UI/window/coordinate inspector, replay engine, execution timeline) | 🟡 | M13 |

### Browser Automation
| Feature                       | Status | Milestone |
|-------------------------------|--------|-----------|
| Playwright adapter (interface)| ✅     | M0        |
| Open / click / type / extract | ✅     | M4        |
| Full-page screenshot          | ✅     | M4        |
| Authenticated sessions        | ✅     | M4 (real Playwright sessions; no dedicated login-flow helper) |
| URL scheme validation (safety)| ✅     | M5.5 (added during the stabilization audit) |
| Browser Intelligence (multi-tab, structured extraction) | 🟡 | M11 |
| Chrome extension bridge       | 🔵     | post-1.0  |

### Agent System
| Feature                       | Status | Milestone |
|-------------------------------|--------|-----------|
| Orchestrator interface        | ✅     | M0        |
| LangGraph state machine       | ✅ `planner → tool_selector → tool_executor → critic → responder`, compiled `StateGraph` | M5A |
| Tool registry from services   | ✅ (memory/automation/browser/system/voice/chat) | M5A |
| Checkpointer (SQLite)         | ✅ `AsyncSqliteSaver`, falls back to in-memory if disabled/not installed | M5A |
| Multi-agent (planner+critic)  | ✅     | M5A       |
| Agent trace panel             | ✅ (no per-step timings yet) | M5A |
| Parallel execution             | 🟡 automation-level dispatch shipped (M7 Phase 2, see Windows Automation table above); LangGraph-level cross-tool parallel branches remain Phase 3, deferred pending separate approval | M7 |
| Workflow builder / macro engine / automation recorder | 🟡 (domain foundation only — `WorkflowDefinition`/`WorkflowStep`/`ScheduleDefinition` shipped in Phase 1; builder/recorder/scheduler themselves not yet built) | M7 |
| Scheduler                      | 🟡 (domain foundation only, see above) | M7        |
| Vision agent tool               | 🟡     | M6        |
| Chat view routed through agent  | 🟡     | not yet scheduled — deliberate M5A deferral (§3) |
| True token-level agent streaming | 🟡   | not yet scheduled — deliberate M5A deferral (§3) |
| Per-step timings in trace panel | 🟡    | M20A      |
| Checkpoint-resume UI            | 🟡     | not yet scheduled |

### Developer Mode
| Feature                       | Status | Milestone |
|-------------------------------|--------|-----------|
| Log viewer in UI              | ✅ (`logs_diagnostics_view.py`) | M5        |
| Configuration snapshot viewer | ✅ (read-only; editing still goes through the main Settings dialog) | M5 |
| Module Manager                | ✅ (mock registry backend) | M5 |
| Plugin Manager                | ✅ (architecture + mock provider; real loader is M8) | M5 |
| API Center                    | ✅ (real CRUD, Fernet encryption at rest, validation) | M5 |
| Update Center                 | ✅ (real version history, rollback, session history) | M5 |
| Security Center                | ✅     | M5        |
| Backup / Restore              | ✅     | M5        |
| Performance Monitor           | ✅     | M5        |
| Agent Trace                    | ✅     | M5A       |
| Vision Trace / OCR Debug       | 🟡     | M6        |
| Prompt playground             | 🟡 still not built | natural fit once M6/M7 land — not yet scheduled |
| Analytics dashboard            | 🟡     | M20A      |
| Python REPL (sandboxed)       | ⚪     | post-1.0  |

### Productivity & Command Surface
| Feature                       | Status | Milestone |
|-------------------------------|--------|-----------|
| Command Palette               | 🟡     | M11       |
| Clipboard Manager             | 🟡     | M11       |
| Task Manager                  | 🟡     | M11       |
| Email                         | 🟡     | M11       |
| Calendar                      | 🟡     | M11       |
| Coding Assistant              | 🟡     | M11       |
| Document Assistant            | 🟡     | M11       |
| Research Assistant            | 🟡     | M11       |
| Media Controls                | 🟡     | M11       |
| Google Workspace Integration (auth, Gmail/Calendar/Meet/Drive/Docs/Sheets/Slides/Chat/Tasks/People APIs) | 🟡 | M11 |
| AI Meeting Assistant (transcript processing, summaries, action items, deadlines) | 🟡 | M11 |
| AI Meeting Insights (topic segmentation, sentiment, risk detection, health/productivity score) | 🟡 | M11 |
| Workspace Memory Integration (semantic search over Workspace content) | 🟡 | M11 |
| Workspace Search (unified semantic + NL search across Gmail/Calendar/Meet/Drive/Docs/Sheets/Slides/Tasks/Contacts) | 🟡 | M11 |
| Workspace Automation (calendar-triggered, cross-service, multi-step workflows) | 🟡 | M11 |
| Workspace Administration (domains, multi-account, shared drives, org policy — enterprise, optional) | 🟡 | M11 |
| Workspace Developer Tools (OAuth debug, API inspector, rate-limit/health dashboards) | 🟡 | M11 |
| Future AI Productivity Features (daily briefings, AI executive assistant, workspace knowledge graph) | ⚪ | not yet scheduled — see M11's Google Workspace module |
| SEO Intelligence               | 🟡     | M11A      |
| Training Studio (teach by demonstration) | 🟡 | M17A |

### Plugin & Integration Platform

*(Milestone column updated Aug 2026 — Plugin Platform moved from M8 to
M9, and Integration Platform's scope moved from M9 to M11, per the
frontend migration's retitling of M8–M11. See §8 for the full
reasoning.)*

| Feature                       | Status | Milestone |
|-------------------------------|--------|-----------|
| Plugin SDK                    | 🟡     | M9        |
| Manifest schema               | 🟡     | M9        |
| Permission scopes             | 🟡     | M9        |
| Local plugin store             | 🟡     | M9        |
| Auto-update                   | 🟡     | M9        |
| Marketplace                    | 🟡     | M9 (backend) / M8 (React UI) |
| Signed plugins                | 🟡     | M14       |
| API Gateway / OAuth / Webhooks | 🟡    | M11       |
| Retry policies / caching / monitoring | 🟡 | M11  |

### Smart Home & IoT Platform

*(M12 was redesigned Jul 2026 from a single-bus device bridge into a
full enterprise-grade platform — see M12's own §8 entry and the
changelog addendum at the end of this document. The granular rows
below predate that redesign and are kept for continuity; each now
lives inside one of the 15 module rows that follow.)*

| Feature                       | Status | Milestone |
|-------------------------------|--------|-----------|
| Home Assistant integration    | 🟡     | M12       |
| MQTT                          | 🟡     | M12       |
| Matter (read-only)            | 🟡     | M12       |
| Zigbee (via Z2M)              | 🟡     | M12       |
| Shelly                        | 🟡     | M12       |
| Tuya                          | 🟡     | M12       |
| Philips Hue                   | 🟡     | M12       |
| ESP32 custom firmware bridge  | 🟡     | M12       |
| Smart locks                   | 🟡     | M12       |
| Security cameras (RTSP snap)  | 🟡     | M12       |
| Water pump                    | 🟡     | M12       |
| Energy monitoring             | 🟡     | M12       |
| Smart Home Core (device manager/registry/discovery/pairing, rooms, zones, groups, multi-home) | 🟡 | M12 |
| Connectivity Layer (ESP32, MQTT, Wi-Fi, BLE, Zigbee, Z-Wave, Matter, Thread, Home Assistant, secure provisioning) | 🟡 | M12 |
| Smart Lighting (on/off, brightness, RGB, color temp, scenes, adaptive/motion/sunrise-sunset automation) | 🟡 | M12 |
| Smart Locks (Wi-Fi/BLE/fingerprint/PIN/NFC, temporary/guest access, remote unlock, auto-lock, access history) | 🟡 | M12 |
| Sensors (motion, presence, LD2410B, door/window, temp/humidity, air quality, leak/smoke/gas, light, vibration) | 🟡 | M12 |
| Smart Cameras (live streaming, motion/person/package/vehicle detection, optional face recognition, recording) | 🟡 | M12 |
| Energy Management (smart plugs/switches, monitoring, UPS/battery/solar/generator, power saving, load scheduling) | 🟡 | M12 |
| Appliance Control (fans, AC, TV, curtains/blinds, geysers, pumps, irrigation, kitchen devices) | 🟡 | M12 |
| Home Automation (rule engine, event/time/sensor/presence-based, geofencing, multi-step, scene, emergency) | 🟡 | M12 |
| AI Home Assistant (NL commands, voice control, context awareness, predictive automation, energy optimization) | 🟡 | M12 |
| Security & Safety (intrusion, fire/gas/water alerts, panic mode, vacation mode, home status dashboard) | 🟡 | M12 |
| Remote Access (secure remote control, mobile notifications, live status, remote diagnostics) | 🟡 | M12 |
| Smart Home Memory (device/automation/energy/security history, device learning, usage analytics) | 🟡 | M12 |
| Smart Home Analytics (energy trends, usage stats, automation effectiveness, predictive maintenance, cost savings) | 🟡 | M12 |
| Developer Tools (device simulator, MQTT debug console, event viewer, automation tester, diagnostics) | 🟡 | M12 |
| Full Matter fabric commissioning | ⚪  | post-1.0  |

### Security / Privacy / Performance
*(M14 was redesigned Jul 2026 from a single feature list into a
complete enterprise-grade Security Platform — see M14's own §8 entry
and the changelog addendum at the end of this document. The rows
below predate that redesign and are kept for continuity; each now
lives inside one of the 12 module rows in the table that follows.)*

| Feature                       | Status | Milestone |
|-------------------------------|--------|-----------|
| OS keyring integration        | 🟡     | M14       |
| Audit log                     | 🟡     | M14       |
| PII redaction                 | 🟡     | M14       |
| Encryption at rest (SQLCipher)| 🟡     | M14       |
| Kill-switch hotkey            | 🟡     | M14       |
| Per-plugin permission prompts | 🟡     | M8 / M14  |
| Prompt-injection guardrails   | 🟡     | M14 (formalizes the M5A pattern) |
| Automation simulator / risk analysis / rollback testing | 🟡 | M13A |
| Model performance profiler    | 🔵     | any       |

### Security Platform (M14 modules)
| Feature                       | Status | Milestone |
|-------------------------------|--------|-----------|
| Security Core (architecture, trust model, identity layer, authorization engine, session management) | 🟡 | M14 |
| Identity & Authentication (local auth, PIN, Windows Hello, biometric, MFA, device trust, recovery) | 🟡 | M14 |
| Authorization & Permissions (RBAC, permission profiles, sensitive-action approval, temporary permissions) | 🟡 | M14 |
| Secrets Management (API key storage, credential vault, encryption keys, OAuth token protection, secret rotation) | 🟡 | M14 |
| Data Protection (encryption at rest/in transit, secure local storage, file encryption, integrity verification) | 🟡 | M14 |
| Network Security (secure communications, TLS management, remote access security, API/certificate security) | 🟡 | M14 |
| AI Security (prompt injection protection, tool permission validation, agent isolation, hallucination risk controls) | 🟡 | M14 |
| Smart Home Security (device authentication, secure pairing, access policies, emergency override) | 🟡 | M14 |
| Monitoring & Auditing (security logs, audit trail, threat/intrusion detection, risk dashboard, compliance reports) | 🟡 | M14 |
| Incident Response (threat response, emergency lockdown, credential revocation, rollback, post-incident analysis) | 🟡 | M14 |
| Privacy (local-first privacy, consent management, data retention, export & deletion, transparency reports) | 🟡 | M14 |
| Developer Security Tools (security inspector, vault manager, audit explorer, threat simulator, policy editor) | 🟡 | M14 |

### Backup, Diagnostics & Analytics

*(M18 was redesigned Jul 2026 from a permanent health-monitoring
subsystem into a complete enterprise-grade Self-Healing & Diagnostics
Platform, and M20A was separately redesigned Jul 2026 from a single
dashboard feature into a complete enterprise-grade Analytics &
Observability Platform — see each milestone's own §8 entry and the
changelog addenda at the end of this document. The M18 and M20A rows
below predate both redesigns and are kept for continuity; each now
lives inside its milestone's own module table that follows.)*

| Feature                       | Status | Milestone |
|-------------------------------|--------|-----------|
| Automatic backup / snapshots  | 🟡     | M14A      |
| Migration / restore / version history | 🟡 | M14A   |
| Health monitoring / crash recovery | 🟡 | M18      |
| Automatic repair               | 🟡     | M18       |
| Diagnostic reports              | 🟡     | M18       |
| Performance dashboard           | 🟡     | M20A      |
| AI metrics / token usage / cost analytics | 🟡 | M20A |
| Telemetry (opt-in)              | 🟡     | M20A / M24 |

### Self-Healing & Diagnostics (M18 Modules)
| Feature                       | Status | Milestone |
|-------------------------------|--------|-----------|
| Health Monitoring Core (system/component health, service availability, heartbeat, resource, dependency health) | 🟡 | M18 |
| Diagnostics Engine (error detection, failure classification, root cause analysis, diagnostic reports/history) | 🟡 | M18 |
| Self-Healing Engine (automatic recovery, intelligent retry, safe restart, component isolation, graceful degradation) | 🟡 | M18 |
| Predictive Reliability (failure prediction, resource forecasting, early warning, reliability scoring, capacity planning) | 🟡 | M18 |
| Recovery Management (checkpoints, rollback, configuration/session/workflow recovery, backup integration) | 🟡 | M18 |
| Performance Optimization (performance/resource/memory/CPU monitoring, startup and background task optimization) | 🟡 | M18 |
| Security Diagnostics (security health checks, permission/credential validation, secrets integrity, threat diagnostics) | 🟡 | M18 |
| AI Diagnostics (agent health, model/provider availability, prompt pipeline validation, response quality monitoring) | 🟡 | M18 |
| Developer Diagnostics Tools (diagnostics dashboard, health explorer, recovery timeline, failure simulator) | 🟡 | M18 |
| Reporting & Analytics (health/reliability reports, incident timeline, recovery metrics, executive summaries) | 🟡 | M18 |

### Analytics & Observability Platform (M20A Modules)
| Feature                       | Status | Milestone |
|-------------------------------|--------|-----------|
| Observability Core (metrics collection, event collection, telemetry pipeline, runtime/health/service/custom metrics, configuration) | 🟡 | M20A |
| Event Analytics (voice, desktop, smart home, workflow, agent, memory, prediction, security events) | 🟡 | M20A |
| Performance Analytics (CPU, GPU, memory, storage, network, API latency, AI response latency, resource utilization) | 🟡 | M20A |
| AI Analytics (model performance, prompt statistics, token usage, provider comparison, tool success rate, hallucination tracking, confidence/response quality metrics) | 🟡 | M20A |
| User Experience Analytics (feature usage, automation frequency, productivity trends, learning progress, workflow effectiveness, routine insights, recommendation acceptance, satisfaction signals) | 🟡 | M20A |
| Dashboard Platform (system, AI, desktop, smart home, security, performance, workflow, executive dashboards) | 🟡 | M20A |
| Alert & Notification Engine (performance, security, automation failure, AI error, resource, device, health alerts, custom alert rules) | 🟡 | M20A |
| Reporting Platform (daily, weekly, monthly, executive, health, productivity, AI performance, custom reports) | 🟡 | M20A |
| Developer Observability Tools (live event viewer, metrics/log/trace explorer, timeline viewer, performance inspector, analytics debugger, dashboard builder) | 🟡 | M20A |
| Analytics API (metrics, event, dashboard, reporting, alert, export, integration API, plugin analytics SDK) | 🟡 | M20A |

### Personality, Reflection & Companion Intelligence

*(M15, M16, M17, and M20 were each separately redesigned Jul 2026 —
from a single configurable-personality feature into a complete
enterprise-grade Personality Engine (M15), from a single
learning-feedback feature into a complete Reflection Engine (M16),
from a proactive-suggestions feature into a complete Companion
Intelligence platform (M17), and from a lightweight forward-looking
feature into a complete Predictive Intelligence Platform (M20) — see
each milestone's own §8 entry and the changelog addenda at the end of
this document. The rows below predate all four redesigns and are kept
for continuity; each now lives inside its milestone's own module table
that follows.)*

| Feature                       | Status | Milestone |
|-------------------------------|--------|-----------|
| Personality profiles / conversation style / humor | 🟡 | M15 |
| Preferences / emotional intelligence | 🟡 | M15 |
| Learning / habit recognition   | 🟡     | M16       |
| Experience summaries / goal tracking | 🟡 | M16  |
| Context awareness / routine assistance | 🟡 | M17 |
| Proactive / predictive suggestions | 🟡 | M17 / M20 |
| Intent prediction / recommendation engine | 🟡 | M20 |
| Decision support / predictive scheduling | 🟡 | M20 |

### Personality Engine (M15 Modules)
| Feature                       | Status | Milestone |
|-------------------------------|--------|-----------|
| Personality Core (profiles, traits, communication style, confidence levels, conversation rules, presets) | 🟡 | M15 |
| Conversation & Language Intelligence (natural conversations, multi-turn dialogue, tone adaptation, formal/casual modes, humor, multilingual support) | 🟡 | M15 |
| Automatic Language Detection                | 🟡     | M15       |
| English Conversation                         | 🟡     | M15       |
| Hindi Conversation                           | 🟡     | M15       |
| Marathi Conversation                         | 🟡     | M15       |
| Hinglish Support                             | 🟡     | M15       |
| Marathi-English Conversation                 | 🟡     | M15       |
| Language Memory (conversation + long-term, semantic-meaning-based) | 🟡 | M15 |
| Dynamic Language Switching (explicit command + natural-language auto-detect) | 🟡 | M15 |
| Offline Language Packs                       | 🟡     | M15       |
| Plugin-Based Language Framework (new-language adapters without core changes) | 🟡 | M15 |
| Relationship Intelligence (user familiarity, shared experience memory, long-term relationship building, trust) | 🟡 | M15 |
| Adaptive Behaviour (communication/preference learning, routine recognition, dynamic personalisation, feedback) | 🟡 | M15 |
| Emotional Intelligence (emotion recognition, sentiment awareness, empathetic responses, emotional boundaries) | 🟡 | M15 |
| Voice Personality (voice profiles, speaking style, speech pace, emotional speech, voice consistency) | 🟡 | M15 |
| Persona Management (multiple personas, persona switching, work/personal/guest mode, import & export) | 🟡 | M15 |
| Proactive Intelligence (smart suggestions, daily briefings, contextual recommendations, goal tracking) | 🟡 | M15 |
| Ethics & Safety (respectful behaviour, privacy awareness, bias mitigation, manipulation prevention, guardrails) | 🟡 | M15 |
| Developer Tools (personality editor, behaviour simulator, persona debugger, conversation replay, analytics) | 🟡 | M15 |

### Reflection Engine (M16 Modules)
| Feature                       | Status | Milestone |
|-------------------------------|--------|-----------|
| Reflection Core (architecture, scheduler, policies, sessions, history, manual/automatic reflection) | 🟡 | M16 |
| Conversation Reflection (conversation review, response quality, missed intent, language consistency) | 🟡 | M16 |
| Workflow Reflection (success/failure analysis, automation optimization, bottleneck detection, recommendations) | 🟡 | M16 |
| Knowledge Reflection (gap/duplicate detection, validation, consistency review, confidence scoring) | 🟡 | M16 |
| Behaviour Reflection (behaviour/personality consistency, emotional response review, decision pattern review) | 🟡 | M16 |
| Learning & Improvement (experience learning, pattern recognition, routine discovery, improvement suggestions) | 🟡 | M16 |
| Goal Reflection (goal progress review, habit tracking, milestone analysis, progress forecasting) | 🟡 | M16 |
| Reflection Analytics (reflection/learning/workflow/behaviour metrics, trend analysis, performance dashboards) | 🟡 | M16 |
| Safety & Governance (reflection permissions, privacy controls, audit logs, explainable reflections, guardrails) | 🟡 | M16 |
| Developer Reflection Tools (reflection viewer/explorer, learning timeline, debugger, improvement simulator) | 🟡 | M16 |

### Companion Intelligence (M17 Modules)
| Feature                       | Status | Milestone |
|-------------------------------|--------|-----------|
| Companion Core (architecture, relationship framework, interaction lifecycle, trust framework, companion profiles) | 🟡 | M17 |
| Relationship Intelligence (long-term relationship building, trust development, shared experience, milestone recognition) | 🟡 | M17 |
| Daily Companion (morning briefings, evening recaps, daily planning, wellness check-ins, calendar awareness) | 🟡 | M17 |
| Personalization Engine (routine recognition, habit understanding, adaptive suggestions, contextual personalization) | 🟡 | M17 |
| Proactive Intelligence (context-aware assistance, predictive suggestions, opportunity detection, goal support) | 🟡 | M17 |
| Social & Communication Intelligence (communication style adaptation, social context, meeting/contact context) | 🟡 | M17 |
| Wellbeing Support (habit encouragement, wellness reminders, break suggestions, stress awareness, goal motivation) | 🟡 | M17 |
| Memory & Continuity (long-term context, cross-session awareness, preference retention, personal timeline) | 🟡 | M17 |
| Safety & Boundaries (user consent, privacy controls, emotional boundaries, transparency, relationship reset) | 🟡 | M17 |
| Developer Companion Tools (relationship viewer, personalization inspector, companion simulator, trust analytics) | 🟡 | M17 |

### Predictive Intelligence Platform (M20 Modules)
| Feature                       | Status | Milestone |
|-------------------------------|--------|-----------|
| Prediction Core (prediction engine, models, forecast management, confidence scoring, policies, scheduler, scenario engine, configuration) | 🟡 | M20 |
| Behaviour Prediction (routine, intent, workflow, habit, context, schedule, activity, preference prediction) | 🟡 | M20 |
| Opportunity Intelligence (productivity, automation, learning, cost-saving, time optimization, health & wellness, smart home, workflow opportunities) | 🟡 | M20 |
| Risk Intelligence (deadline, workflow failure, device health, security, smart home, resource exhaustion, schedule conflict, dependency risk) | 🟡 | M20 |
| Planning Intelligence (goal planning, task sequencing, project forecasting, calendar optimization, resource planning, smart scheduling, travel planning, scenario comparison) | 🟡 | M20 |
| Recommendation Engine (contextual recommendations, proactive suggestions, decision support, alternative strategies, priority suggestions, productivity coaching, workflow guidance, explainable recommendations) | 🟡 | M20 |
| Simulation Engine (what-if analysis, scenario/automation/schedule/workflow/risk/resource simulation, outcome comparison) | 🟡 | M20 |
| Predictive Analytics (forecast dashboards, confidence trends, behaviour/opportunity/risk metrics, prediction accuracy, long-term trends, executive reports) | 🟡 | M20 |
| Governance & Safety (user approval, explainable predictions, confidence thresholds, privacy controls, ethical AI policies, recommendation limits, audit logs, transparency) | 🟡 | M20 |
| Developer Prediction Tools (prediction explorer, scenario builder, simulation console, forecast viewer, confidence inspector, debugger, analytics explorer, testing dashboard) | 🟡 | M20 |

### Cloud / Mobile / Distributed

*(M21 was redesigned Jul 2026 from a 6-feature multi-device presence
milestone into a complete enterprise-grade Mobile Platform, and M22
was separately redesigned Jul 2026 from a 6-feature local/offline
hardware milestone into a complete enterprise-grade Edge AI Platform —
see each milestone's own §8 entry and the changelog addenda at the end
of this document. The M21 and M22 rows below predate both redesigns
and are kept for continuity; each now lives inside its milestone's own
module table that follows.)*

| Feature                       | Status | Milestone |
|-------------------------------|--------|-----------|
| E2EE cloud sync (own bucket)  | 🟡     | M23       |
| Distributed agents / shared memory / remote execution | 🟡 | M23 |
| Enterprise collaboration        | 🟡     | M23       |
| Mobile companion (Android/iOS) | 🟡     | M21       |
| Wearable integration          | 🟡     | M21       |
| Edge AI (mini PC, GPU accel, quantization, offline) | 🟡 | M22 |

### Mobile Platform (M21 Modules)
| Feature                       | Status | Milestone |
|-------------------------------|--------|-----------|
| Mobile Platform Core (platform architecture, mobile runtime, device registration, session management, configuration, offline support, synchronization, platform services) | 🟡 | M21 |
| Mobile Companion (voice conversations, chat interface, notification center, remote assistant, personal dashboard, activity feed, AI suggestions, status overview) | 🟡 | M21 |
| Remote Control Platform (desktop, smart home, workflow, automation control, device management, file access, media control, remote commands) | 🟡 | M21 |
| Mobile Intelligence (context/location awareness, device sensors, presence detection, mobile routines/predictions, smart suggestions, personal insights) | 🟡 | M21 |
| Secure Access Platform (biometric authentication, passkeys, device trust, MFA, session approval, remote authorization, security verification, emergency lockdown) | 🟡 | M21 |
| Synchronization Platform (settings, memory, knowledge graph, dashboard, notification, automation, device sync, conflict resolution) | 🟡 | M21 |
| Mobile Notifications (AI, security, automation, reminder, health, smart home alerts, workflow updates, custom notification rules) | 🟡 | M21 |
| Mobile Analytics (usage, performance, sync metrics, device health, battery optimization, connectivity analytics, crash diagnostics, mobile reports) | 🟡 | M21 |
| Developer Mobile Tools (device manager, emulator support, mobile debugger, push notification tester, sync inspector, session inspector, mobile logs/diagnostics) | 🟡 | M21 |
| Mobile SDK & APIs (mobile SDK, authentication/notification/sync/remote command/device/extension API, plugin integration) | 🟡 | M21 |

### Edge AI Platform (M22 Modules)
| Feature                       | Status | Milestone |
|-------------------------------|--------|-----------|
| Edge AI Core (local AI runtime, model runtime manager, inference pipeline, execution scheduler, runtime configuration, resource allocation, provider abstraction, runtime policies) | 🟡 | M22 |
| Model Management (registry, installation, updates, version management, validation, rollback support, metadata, compatibility management) | 🟡 | M22 |
| Inference Engine (text, vision, audio, multimodal inference, batch processing, streaming inference, parallel execution, result optimization) | 🟡 | M22 |
| Hardware Acceleration (CPU, GPU, NPU support, DirectML integration, CUDA support, Vulkan compute, hardware detection, performance profiles) | 🟡 | M22 |
| Hybrid AI Execution (local-first routing, cloud fallback, provider selection, cost/latency optimization, offline mode, hybrid policies, failover logic) | 🟡 | M22 |
| AI Resource Management (memory/VRAM management, CPU/GPU scheduling, thermal/battery awareness, background processing, resource limits) | 🟡 | M22 |
| Privacy & Security (local data processing, secure model storage, model integrity, execution sandboxing, permission policies, secure updates, encryption, audit logging) | 🟡 | M22 |
| Edge AI Analytics (inference metrics, model performance, resource utilization, latency reports, accuracy tracking, cost comparison, usage trends, runtime dashboards) | 🟡 | M22 |
| Developer Edge Tools (model explorer, runtime inspector, performance profiler, inference debugger, benchmark suite, hardware inspector, model tester, diagnostics console) | 🟡 | M22 |
| Edge AI SDK & APIs (model SDK, runtime/inference/hardware/provider/analytics API, plugin SDK, extension framework) | 🟡 | M22 |

### Robotics & Hardware Control Platform (M23A Modules)

*(M23A was added Jul 2026 as a new companion milestone alongside M23 —
it is not a redesign of any existing milestone, and no legacy rows
predate it. See M23A's own §8 entry and the changelog addendum at the
end of this document. The full legacy roadmap milestone list elsewhere
in this document — including M23 — Distributed JARVIS's own rows —
is preserved unchanged for roadmap history.)*

| Feature                       | Status | Milestone |
|-------------------------------|--------|-----------|
| Hardware Abstraction Layer (device abstraction, hardware profiles, driver interface/manager, dynamic driver loading, capability detection, version compatibility, device registry, plug & play, driver sandbox, device lifecycle, vendor-independent abstraction) | 🟡 | M23A |
| Communication Interfaces (USB, UART, serial, SPI, I2C, GPIO, CAN bus, Ethernet, Wi-Fi, Bluetooth, BLE, NFC, infrared, RS485, WebSocket bridge) | 🟡 | M23A |
| IoT Connectivity (MQTT, Matter, Zigbee, Thread, Z-Wave, Home Assistant, Google Home, Alexa, Apple HomeKit, SmartThings, device discovery, secure pairing, auto provisioning, OTA registration) | 🟡 | M23A |
| Sensor Framework (motion/presence/radar/temperature/humidity/pressure/light/water/smoke/gas/door/window/camera sensors, microphones, GPS, IMU, calibration, sensor fusion, noise filtering, sampling, health monitoring, diagnostics) | 🟡 | M23A |
| Actuator Framework (relays, motors, servo/stepper motors, smart locks, solenoids, pumps, curtains, lights, fans, RGB LEDs, buzzers, displays, PWM control, emergency stop, safety limits, state monitoring) | 🟡 | M23A |
| Robotics Runtime (robot controller, multi-axis movement, motion planner, kinematics abstraction, docking, charging, navigation hooks, obstacle awareness, robot state manager, simulation support, diagnostics, task execution) | 🟡 | M23A |
| Device Automation Engine (event-driven automation, scheduling, conditional execution, multi-device workflows, automation chains, smart scenes, presence automation, occupancy detection, energy saving, recovery workflows, retry engine) | 🟡 | M23A |
| Hardware Security (secure pairing, device authentication, signed firmware, secure boot, OTA validation, hardware encryption, device permissions, hardware firewall, device isolation, tamper detection, trust verification) | 🟡 | M23A |
| Hardware Analytics (device uptime, battery health, power analytics, signal quality, error logs, event history, device statistics, maintenance prediction, performance monitoring, diagnostics) | 🟡 | M23A |
| Robotics SDK & APIs (driver/hardware/robot/sensor/automation SDK, plugin APIs, testing toolkit, emulator, documentation, sample projects, REST APIs, local APIs) | 🟡 | M23A |

### Autonomous Planning & Decision Engine (M23B Modules)

*(M23B was added Jul 2026 as a new companion milestone alongside
M23A, immediately before M24 — it is not a redesign of any existing
milestone, and no legacy rows predate it. See M23B's own §8 entry and
the changelog addendum at the end of this document. The full legacy
roadmap milestone list elsewhere in this document — including M24 —
Production Release's own content — remains preserved unchanged for
roadmap history.)*

| Feature                       | Status | Milestone |
|-------------------------------|--------|-----------|
| Goal Management (goal creation, hierarchy, long-term/short-term goals, prioritization, cancellation, dependencies, history, persistence, templates) | 🟡 | M23B |
| Task Planning (task decomposition, multi-step planning, sequential/parallel execution, dependency graph, planning optimization, dynamic replanning, execution ordering, resource-aware planning, time estimation) | 🟡 | M23B |
| Decision Engine (context-aware decisions, multi-option evaluation, cost-benefit analysis, risk/confidence scoring, AI reasoning, decision history/explanation, policy evaluation, human override) | 🟡 | M23B |
| Autonomous Execution (auto execution, approval workflow, safe execution, retry engine, rollback, pause/resume, checkpoints, recovery, completion validation) | 🟡 | M23B |
| Resource Planner (CPU/GPU/memory planning, edge AI selection, cloud selection, device selection, battery/network awareness, cost optimization, load balancing) | 🟡 | M23B |
| Multi-Agent Orchestration (agent assignment, coordination, parallel agents, delegation, conflict resolution, shared task queue, agent monitoring/recovery, distributed planning, agent collaboration) | 🟡 | M23B |
| Predictive Intelligence (predictive scheduling, habit/workflow/failure/maintenance/resource prediction, smart recommendations, opportunity detection, risk prediction, trend analysis) | 🟡 | M23B |
| Safety & Governance (execution policies, permission validation, safety rules, kill switch, emergency stop, compliance engine, ethical constraints, risk thresholds, audit logging, manual approval) | 🟡 | M23B |
| Planning Analytics (planning statistics, goal completion, execution success rate, failure analysis, planning efficiency, decision quality, resource utilization, time savings, productivity metrics, optimization reports) | 🟡 | M23B |
| Planning SDK & APIs (planning/workflow SDK, goal/decision/automation/plugin APIs, testing tools, simulation APIs, documentation, example workflows) | 🟡 | M23B |

### Release
| Feature                       | Status | Milestone |
|-------------------------------|--------|-----------|
| Windows installer             | 🟡     | M24       |
| Code signing                  | 🟡     | M24       |
| Auto-updater                  | 🟡     | M24       |
| Crash reporter                | 🟡     | M24       |
| First-run wizard              | 🟡     | M24       |
| Telemetry (opt-in)            | 🟡     | M24       |
| Full regression + security audit | 🟡  | M24       |

### Cognitive Intelligence Platform (M25 Modules)

*(M25 was added Jul 2026 as a new top-level milestone immediately
after M24 — it is not a redesign, renumbering, or replacement of any
existing milestone, and no legacy rows predate it. See M25's own §8
entry and the changelog addendum at the end of this document. M24 —
Production Release's own rows above remain preserved unchanged for
roadmap history.)*

| Feature                       | Status | Milestone |
|-------------------------------|--------|-----------|
| Cognitive Memory (episodic, semantic, working, long-term memory, memory linking, compression, forgetting policies, context recall, importance scoring, indexing) | 🟡 | M25 |
| Meta Reasoning (reasoning about reasoning, confidence/self-evaluation, error detection, alternative solution generation, reflection loops, chain validation, strategy comparison, explanation engine, reasoning optimization) | 🟡 | M25 |
| Continuous Learning (learning from interactions/corrections, adaptive knowledge, experience replay, incremental learning, knowledge refinement, skill acquisition, knowledge validation, learning policies, improvement tracking) | 🟡 | M25 |
| Human Preference Modeling (user habits/preferences, communication style, personal workflows, decision preferences, context adaptation, routine detection, personalized recommendations, interaction history, preference evolution) | 🟡 | M25 |
| Emotional Intelligence (emotion recognition, conversation tone analysis, empathetic response generation, mood estimation, social awareness, interaction adaptation, emotional memory, conversation continuity, response balancing, trust modeling) | 🟡 | M25 |
| Knowledge Evolution (knowledge refinement, conflict resolution, source confidence, knowledge merging, version history, automatic updates, knowledge aging, fact validation, graph enrichment, citation tracking) | 🟡 | M25 |
| Cognitive Analytics (thinking performance, learning metrics, memory utilization, decision quality, adaptation score, reflection statistics, user satisfaction metrics, cognitive efficiency, knowledge growth, intelligence reports) | 🟡 | M25 |
| Cognitive Safety (bias detection, hallucination monitoring, reasoning validation, confidence thresholds, ethical safeguards, privacy preservation, human override, safety policies, risk analysis, audit logs) | 🟡 | M25 |
| Self Improvement Engine (capability analysis, weakness detection, improvement planning, skill optimization, performance tuning, feedback integration, goal refinement, automatic optimization, learning roadmap, long-term evolution) | 🟡 | M25 |
| Cognitive SDK & APIs (memory/learning/reasoning/reflection/personality/analytics APIs, plugin SDK, testing framework, documentation, sample integrations) | 🟡 | M25 |

### Self-Learning & Autonomous Evolution Platform (M26 Modules)

*(M26 was added Jul 2026 as a new top-level milestone immediately
after M25 — it is not a redesign, renumbering, or replacement of any
existing milestone, and no legacy rows predate it. See M26's own §8
entry and the changelog addendum at the end of this document. M25 —
Cognitive Intelligence Platform's own rows above remain preserved
unchanged for roadmap history.)*

| Feature                       | Status | Milestone |
|-------------------------------|--------|-----------|
| Self-Learning Engine (continuous/incremental/online/offline learning, learning sessions, scheduling, prioritization, confidence, validation, history) | 🟡 | M26 |
| Experience Replay (experience storage, success/failure replay, replay prioritization, scenario/temporal replay, memory sampling, experience weighting, replay optimization, learning replay analytics) | 🟡 | M26 |
| Skill Acquisition (new skill learning, skill hierarchy, refinement, validation, transfer, composition, retirement, capability expansion, skill confidence, versioning) | 🟡 | M26 |
| Knowledge Refinement (knowledge correction, merging, duplicate removal, source confidence, conflict resolution, fact refinement, semantic optimization, knowledge consistency/aging, quality scoring) | 🟡 | M26 |
| Autonomous Optimization (performance/workflow/resource/planning/prompt/runtime/scheduling/recommendation/decision optimization, continuous optimization) | 🟡 | M26 |
| Feedback Integration (human/AI feedback, explicit/implicit feedback, reinforcement learning hooks, preference refinement, error correction, continuous evaluation, feedback history/confidence) | 🟡 | M26 |
| Evolution Analytics (learning metrics, skill growth, capability evolution, performance trends, optimization reports, knowledge growth, reflection statistics, improvement dashboards, historical comparisons, evolution forecasting) | 🟡 | M26 |
| Learning Governance (learning policies, safety constraints, ethical learning, approval workflows, rollback policies, version control, audit logging, compliance validation, change management, human oversight) | 🟡 | M26 |
| Autonomous Improvement Engine (weakness detection, improvement planning, automatic experiments, controlled optimization, capability scoring, bottleneck analysis, goal refinement, performance tuning, adaptive behavior, evolution roadmap) | 🟡 | M26 |
| Self-Learning SDK & APIs (learning/skill/evolution/feedback/analytics APIs, plugin SDK, testing framework, simulation APIs, documentation, sample integrations) | 🟡 | M26 |

### World Model & Environmental Intelligence Platform (M27 Modules)

*(M27 was added Jul 2026 as a new top-level milestone immediately
after M26 — it is not a redesign, renumbering, or replacement of any
existing milestone, and no legacy rows predate it. See M27's own §8
entry and the changelog addendum at the end of this document. M26 —
Self-Learning & Autonomous Evolution Platform's own rows above remain
preserved unchanged for roadmap history.)*

| Feature                       | Status | Milestone |
|-------------------------------|--------|-----------|
| World Model Core (persistent world model, entity graph, object registry, environment representation, scene management, relationship mapping, spatial indexing, temporal state tracking, environment snapshots, world versioning) | 🟡 | M27 |
| Spatial Intelligence (indoor/outdoor mapping, room awareness, distance estimation, navigation graphs, coordinate systems, zones, boundaries, safe areas, spatial reasoning) | 🟡 | M27 |
| Object Intelligence (object classification/tracking, state detection, ownership, capabilities, object history/lifecycle/relationships/confidence, inventory management) | 🟡 | M27 |
| Environmental Awareness (weather, lighting, temperature, noise, occupancy, air quality, water status, energy usage, device status, environmental events) | 🟡 | M27 |
| Human Context Intelligence (presence detection, identity abstraction, activity recognition, routine awareness, group/social context, location/interaction history, context confidence, temporal context) | 🟡 | M27 |
| Digital World Intelligence (devices, applications, services, cloud resources, network topology, connected accounts, digital assets, active sessions, service health, dependency mapping) | 🟡 | M27 |
| World Analytics (environment/object/spatial/context/occupancy/device/event analytics, trend analysis, historical reports, predictive insights) | 🟡 | M27 |
| World Safety (hazard detection, restricted zones, safety policies, emergency awareness, privacy boundaries, secure mapping, access control, risk scoring, audit logging, compliance validation) | 🟡 | M27 |
| Simulation Engine (environment/scenario/decision/resource/multi-agent/robot/predictive/risk/rollback simulation, testing scenarios) | 🟡 | M27 |
| World SDK & APIs (world/mapping/object/context/simulation/analytics APIs, plugin SDK, documentation, testing tools, sample integrations) | 🟡 | M27 |

---

## 11. Architecture roadmap

### Current architecture (as of M5A)

*(Diagram predates M6's vision layer and the UI Foundation pass — see
§3's M6 entry and §7's "UI Foundation" bullet for what each actually
added; not redrawn here to avoid an error-prone ASCII-art edit in a
documentation-only pass. It also predates the Aug 2026 decision to
migrate the top `UI` layer from PySide6 to React + Tauri, starting at
M8 — see `TECH_STACK.md`. Every layer below `UI` in this diagram
(`Features` down through `Infrastructure`) is unaffected by that
migration and remains accurate; only the top box's technology changes,
not its position or responsibilities in the stack.)*

```
┌──────────────────────────────────────────────────────────────┐
│                       UI  (PySide6)                          │
│  MainWindow · SettingsDialog · ChatView · PTT · Tray ·       │
│  Developer Mode (incl. Agent Trace)                          │
└──────────────────────────────┬───────────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────┐
│               Features (MVVM controllers)                    │
│  conversation.ConversationController · voice.VoiceController │
│  memory.MemoryController                                     │
└──────────────────────────────┬───────────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────┐
│                    Application services                      │
│  ChatService · ConversationService · VoiceService             │
│  HotkeyService · SettingsService · ThemeService               │
│  MemoryService · AutomationService · BrowserService ·        │
│  SystemService                                                │
└──────────────────────────────┬───────────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────┐
│                          Agents                               │
│  AgentOrchestrator — compiled LangGraph StateGraph            │
│  (planner → tool_selector → tool_executor → critic → responder)│
│  Tool registry (agents/tools/) · AgentCheckpointer            │
└──────────────────────────────┬───────────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────┐
│                            Core                               │
│  config · logging · di · events · exceptions · types          │
│  interfaces  (ILLM · ISTT · ITTS · IVectorStore · IDatabase   │
│              · IAudioRecorder · IAudioPlayer                  │
│              · IHotkeyListener · IWakeWordDetector            │
│              · IMemoryRecallHook · IBrowserAutomation         │
│              · IOSAutomation · IAgentOrchestrator)             │
└──────────────────────────────▲───────────────────────────────┘
                               │  implements
┌──────────────────────────────┴───────────────────────────────┐
│                       Infrastructure                          │
│  llm(openai, ollama, gemini) · stt(whisper_local, openai)     │
│  tts(openai, piper, kokoro, edge, elevenlabs)                 │
│  audio(sounddevice) · hotkey(pynput)                          │
│  vectorstore(chroma) · database(sqlite)                       │
│  browser(playwright) · automation(pywinauto, noop)            │
│  api(fastapi) · platform                                      │
└──────────────────────────────────────────────────────────────┘
```

### Future architecture (v1.0, post-M24)

Additions layered on top of the current one. **One exception to "no
existing layer changes shape":** the `UI` layer itself is fully
replaced (PySide6 → React + Tauri, M8 — see `TECH_STACK.md`), reached
through a new FastAPI/WebSocket boundary rather than in-process Qt
calls; every layer from `Features` down is otherwise unaffected — new
adapters, services, and features only:

- **UI layer** — PySide6 → React + Tauri (M8), talking to the Python
  backend over REST/WebSocket instead of in-process calls. See
  `TECH_STACK.md` §1 for the full boundary diagram.
- **Runtime layer** (new, above services) — Runtime Manager, Service
  Manager, Health Monitor, Resource Manager, and the plugin
  loader/sandbox (permission scopes; plugins register services,
  controllers, widgets, and agent tools) — M9.
- **Agents layer** grows real cross-tool parallel execution (absorbed
  into M10 AI Orchestrator, formerly M7 Phase 3 — see §8) and
  computer-control tools (M13); the vision tool (M6) already shipped
  through this same registry pattern M5A established — see §3's M6
  entry and the Reuse Matrix (§11) rather than treating it as
  still-future here.
- **Vision layer** (at the infra boundary) — `IVisionProvider` /
  `IOCRProvider` adapters already shipped in M6 (mock providers only;
  real backends remain M6's own deferred "Not delivered" scope, per
  §3).
- **Integration layer** (new, at the infra boundary) — API Gateway,
  OAuth, webhooks, queue (M11, formerly scoped as a separate M9 — see
  §8's retitling note).
- **Knowledge layer** (new, above services) — the M10A/M19 knowledge
  graph, queryable by the agent runtime as a tool.
- **Sync layer** (new, at the infra boundary) — outbound-only,
  end-to-end-encrypted push/pull to the user's own bucket (M23), plus
  M11's own Oracle Cloud sync target for optional cloud features ahead
  of M23's full distributed story.
- **Companion transport** (new, at the infra boundary) — the mobile
  app + wearable transport (M21, building on M11's Android Companion
  pairing scope), and the distributed-agent transport (M23).
- **Smart Home layer** — an "adapters of adapters" pattern: Home
  Assistant is the primary bus; other vendors plug in either through
  HA or directly via MQTT (M12).
- **Edge runtime variant** — the same architecture, deployable to
  constrained hardware with quantized models (M22).

### Module dependency graph (v1.0)

```
ui  ──►  features  ──►  services  ──►  agents  ──►  core.interfaces
                                                        ▲
                infrastructure  ────────────────────────┘
                (llm, stt, tts, vision, ocr, audio, hotkey, wake,
                 vector, db, browser, automation, api, platform,
                 plugins, integrations, sync, companion, smarthome,
                 knowledge)
```

### Expansion strategy

1. **Ports first, adapters second.** Every new capability starts as
   an abstract interface in `core.interfaces`. Adapters land later.
2. **DI factories are the only wiring point.** New adapters register
   in `core/di/container.py` — no service knows the concrete class.
3. **Feature slices are self-contained.** New capabilities live in
   `features/<name>/` and communicate through services + the event
   bus, never by importing another feature's internals.
4. **Every milestone leaves fakes behind.** Every new port ships with
   a fake in `tests/fakes/` so downstream milestones can be developed
   without the real dependency.
5. **Settings pages register themselves.** `PAGE_REGISTRY` +
   placeholders means new pages never require Settings dialog edits.
6. **Automated layer-boundary enforcement** (new, tracked as
   technical debt — §15) — the "strict dependency rule enforced by
   convention" note that has followed every version of this roadmap
   since M0 should become a lint rule, not a convention, before the
   plugin surface (M8) makes violating it a third-party concern too.

### Architecture Reuse Matrix

Cross-cutting systems, where each was introduced, and which later
milestones actually build on it — as opposed to the per-milestone
"Architecture Evolution" notes in §3, this table gathers the same
facts across all eleven systems in one place. Status markers match
§10's legend: ✅ Completed · 🟡 Planned (scheduled milestone) · ⚪
Future (post-1.0).

| System | Introduced In | Reused By | Current Status |
|--------|---------------|-----------|-----------------|
| Event Bus | M0 (`core/events/`) | Nearly every milestone since — M2 (voice state events), M4 (automation task events), M5 (`AnnouncementEvent`), M5A (`AgentStepEvent`), M6 (`VisionProviderStatusEvent`), M7 Phase 1 (`WorkflowStepEvent`, `ScheduledJobFiredEvent`) | ✅ Stable core contract, actively extended with new event types every milestone |
| DI Container | M0 (`core/di/container.py`) | Every milestone registers new providers here — M1 (chat services), M3 (memory), M4 (automation), M5A (agent orchestrator + tool registry), M6 (vision/OCR providers) | ✅ Stable; received one out-of-band patch (v0.5.2) for a lazy-provider performance fix, not a milestone |
| Plugin Runtime | Not yet built — planned M8 | None yet | ⚪ Referenced only as a future layer in this section's "Future architecture" diagram; no code exists |
| Automation Engine | M4 (`AutomationService`, `ActionExecutor`, `Step`/`ExecutionPlan`) | M5A (`agents/tools/automation_tools.py` wraps it as an agent tool); M7 Phase 1 (`WorkflowDefinition` shaped to sit alongside `RecipeManager`'s storage model); M7 Phase 2 (`ActionExecutor`'s dispatch loop rewritten in place for wave-based parallel execution — the most direct extension of any milestone's own code in this table) | ✅ Built, actively evolving — most recently extended by M7 Phase 2 |
| Agent Runtime | M5A (`AgentOrchestrator`, LangGraph `StateGraph`, `agents/tools/` registry, SQLite checkpointer) | M6 (added the `vision_status` tool + an optional `vision` constructor kwarg on `AgentOrchestrator`); M7 Phase 1 (`WorkflowStep.AGENT_TOOL` is modelled to reference the tool registry by name/arguments — a design-time reference only, no runtime wiring yet) | 🟡 Stable core, incrementally extended twice; cross-tool parallelism (M7 Phase 3) explicitly deferred, not built |
| Memory | M3 / M3.1 (`MemoryService`, `SemanticMemoryRecallHook`, `MemoryRepository`, ChromaDB) | M5A (`agents/tools/memory_tools.py`); M5 (Timeline views, Home dashboard, `greeting_service.py`) | ✅ Stable since M3.1 polish; contract unchanged, only consumed by later milestones |
| Knowledge Graph | Not yet built — planned M10 (foundation), extended M19 (full) | None yet | ⚪ Foundation and full-graph work both still ahead; no code exists |
| Workflow Engine | M7 Phase 1 (`WorkflowDefinition`/`WorkflowStep`/`ScheduleDefinition` domain models only) | None yet — M7 Phase 2 extended the separate Automation Engine above, not these models; Workflow Builder / Scheduler / Recorder (Phases 4–6) remain pending | 🟡 Domain foundation shipped; no execution layer yet |
| Security Layer | Not yet built as a dedicated milestone — planned M14 | Piecemeal hardening exists ahead of the dedicated milestone: M5 (PBKDF2-HMAC-SHA256 Developer Mode gate); M5.5 (fixed a Developer Mode timing-attack pattern and a browser `file://`/`javascript:`/`data:` URL-scheme validation gap) | 🟡 Hardening work done opportunistically in M5/M5.5; the dedicated audit log, encrypted settings overrides, and Security Center backend are still M14 |
| Analytics Platform | Not yet built — planned M20A | None yet | ⚪ No code exists |
| Edge AI Runtime | Not yet built — planned M22 | None yet | ⚪ Described in this section's "Future architecture" diagram as the same architecture deployed to constrained hardware with quantized models; no code exists |

### Architecture Stability Index

A maturity read on the same systems, using only repository evidence
(test coverage existing today, whether the contract has changed since
it shipped, and how many later milestones depend on it) — not a
subjective quality judgment. ★★★★★ = shipped, stable contract, tested,
multiple real consumers. Fewer stars mean less of that is true yet;
☆-only entries have no code to evaluate.

| System | Stability | Basis |
|--------|-----------|-------|
| DI Container | ★★★★★ | Present since M0, one patch fix in v0.5.2, every milestone since registers through it without incident |
| Event Bus | ★★★★★ | Present since M0, contract unchanged, new event types added every milestone with no breaking changes to existing ones |
| Memory | ★★★★☆ | Stable since M3.1; two independent real consumers (M5A, M5); Timeline search and PII redaction still open per §3's M3 entry |
| Automation Engine | ★★★★☆ | Shipped M4, rewritten in place for M7 Phase 2 without breaking its M5A consumer — survived a real internal rewrite, which is stronger evidence than an untouched module |
| Agent Runtime | ★★★☆☆ | Shipped M5A with a pre-merge validation pass (308/309 tests) and one real incompatibility bug found and fixed; extended twice since, but its own cross-tool parallelism work (M7 Phase 3) is deferred |
| Workflow Engine | ★★☆☆☆ | Domain models only (M7 Phase 1), 21 dedicated tests, but zero runtime consumers yet — nothing has executed a `WorkflowDefinition` yet |
| Security Layer | ★★☆☆☆ | Real fixes exist (M5.5) but they're incident-driven patches to other milestones' code, not a dedicated, tested subsystem yet |
| Plugin Runtime | ☆☆☆☆☆ | Not started |
| Knowledge Graph | ☆☆☆☆☆ | Not started |
| Analytics Platform | ☆☆☆☆☆ | Not started |
| Edge AI Runtime | ☆☆☆☆☆ | Not started |

---

## 12. Database roadmap

Two engines, one contract (`IDatabase` for SQL, `IVectorStore` for
embeddings). Each store below lists what it holds by `v1.0`.

### SQLite (structured, transactional)

Migrations managed by **Alembic** from M3 onwards.

| Table                 | Purpose                                              | Introduced |
|-----------------------|------------------------------------------------------|------------|
| `conversations`       | Chat sessions.                                       | M1         |
| `messages`            | Chat messages (role, content, timestamps).           | M1         |
| `memories`            | Semantic memory entries + metadata.                  | M3         |
| `tags`                | User + system tags for memories.                     | M3         |
| `automation_task_history` | Automation run history.                          | M4         |
| `tasks`               | Personal to-do items + agent-scheduled jobs.         | M11        |
| *(LangGraph-managed checkpoint tables)* | Agent state snapshots for resumable agents — owned by `langgraph-checkpoint-sqlite` in a dedicated `agent_checkpoints.db` file, not a hand-rolled table in the main app DB. | M5A |
| `plugins`             | Installed plugins + enabled state.                   | M8         |
| `plugin_permissions`  | Per-plugin permission grants (network, fs, hotkey…). | M8         |
| `plugin_data`         | Plugin-owned key/value store (namespaced).           | M8         |
| `commands`            | Command palette usage history.                       | M11        |
| `clipboard_items`     | Clipboard history (pinned + auto).                   | M11        |
| `knowledge_entities` / `knowledge_relationships` | Knowledge Graph. | M10 |
| `smart_home_devices`  | Discovered devices + last state cache.               | M12        |
| `smart_home_scenes`   | User scenes + automations.                           | M12        |
| `audit_log`           | Tamper-evident, append-only security events.         | M14        |
| `settings_overrides`  | Runtime setting overrides (currently `.env`-based).  | M14+       |
| `backups` / `snapshots` | Backup Platform metadata.                          | M14A       |
| `sync_state`          | Cloud-sync bookkeeping (Merkle roots, cursors).      | M23        |
| `analytics_events`    | AI metrics / cost / token-usage records.             | M20A       |

> **Note on `checkpoints`.** Earlier versions of this roadmap listed a
> hand-rolled `checkpoints` table introduced "at M5." M5A's actual
> implementation uses LangGraph's own `AsyncSqliteSaver`, which
> manages its own schema in a separate `agent_checkpoints.db` file —
> simpler, and avoids duplicating a schema LangGraph already owns. The
> row above reflects what was actually built, not the original plan.

### ChromaDB (vector memory)

Persistent client anchored at `<data_dir>/vectorstore/`. Collections:

| Collection            | Purpose                                              | Introduced |
|-----------------------|------------------------------------------------------|------------|
| `memory`              | Semantic memories referenced by `IMemoryRecallHook`. | M3         |
| `docs`                | Ingested documents (Document Assistant).             | M11        |
| `plugin_<name>`       | Per-plugin embeddings (namespaced by plugin).        | M8         |
| `vision_<name>`       | Image/document-derived embeddings (Vision Memory).   | M6         |

### Vector memory strategy

- Embedding model configurable via `JARVIS_VECTOR_EMBEDDING_MODEL`.
- Default: OpenAI `text-embedding-3-small`; offline default: Ollama
  `nomic-embed-text`.
- Hybrid recall since M3 — BM25 over SQL first-pass, then vector
  re-rank.

### Log storage

- File sink under `<data_dir>/logs/jarvis.log`, rotated by size +
  retention. Log rows are never persisted in SQLite until M14 (audit
  log is a separate concern with tamper-evidence).

### User preferences + settings

- **Now:** `.env` + `pydantic-settings` (M1 whitelist).
- **M14:** an encrypted `settings_overrides` table gains priority over
  `.env` for user-modifiable values; the whitelist stays.

### Backup & restore

- **M14A** formalizes this: one-click **Export** (zip of SQLite +
  Chroma + `.env` minus secrets) and **Import**, kept in
  `data/backups/` with a Merkle root recorded in `sync_state`,
  scheduled automatically via M7's Scheduler.

---

## 13. AI provider roadmap

### Chat providers

| Provider    | Status     | Milestone | Adapter path                                        |
|-------------|------------|-----------|-----------------------------------------------------|
| OpenAI      | ✅ Done    | M1        | `infrastructure/llm/openai_provider.py`             |
| Ollama      | ✅ Done    | M1        | `infrastructure/llm/ollama_provider.py`             |
| Google Gemini | ✅ Done  | M3        | `infrastructure/llm/gemini_provider.py` (secondary/fallback via `JARVIS_LLM_FALLBACK_PROVIDER`) |
| Anthropic Claude | 🟡     | §7 (continuous — no dedicated milestone) | `infrastructure/llm/anthropic_provider.py` |
| DeepSeek    | 🟡         | §7        | `infrastructure/llm/deepseek_provider.py`           |
| xAI Grok    | 🟡         | §7        | `infrastructure/llm/grok_provider.py`               |
| Groq (hosted)| 🟡        | §7        | `infrastructure/llm/groq_provider.py`               |
| LM Studio   | 🟡         | §7        | uses OpenAI-compatible endpoint via `base_url`      |
| OpenRouter  | 🟡         | §7        | `infrastructure/llm/openrouter_provider.py`         |
| Together AI | 🔵         | any       | OpenAI-compatible via `base_url`                    |
| Mistral (hosted) | 🔵    | any       | `infrastructure/llm/mistral_provider.py`            |

### Vision providers *(new — M6)*

| Provider    | Status | Milestone |
|-------------|--------|-----------|
| GPT-4o / GPT-4o-mini Vision | 🟡 | M6 |
| Gemini Vision | 🟡 | M6 |
| Local (LLaVA via Ollama) | 🟡 | M6 |

### OCR providers *(new — M6)*

| Provider    | Status | Milestone |
|-------------|--------|-----------|
| Tesseract (`pytesseract`) | 🟡 | M6 |
| PaddleOCR   | 🟡 | M6 |

### STT providers

| Provider          | Status | Milestone |
|-------------------|--------|-----------|
| Whisper local     | ✅     | M2        |
| OpenAI Whisper API| ✅     | M2        |
| Deepgram          | 🟡     | §7        |
| AssemblyAI        | 🔵     | post-1.0  |

### TTS providers

| Provider          | Status | Milestone |
|-------------------|--------|-----------|
| OpenAI TTS        | ✅     | M2        |
| Piper (offline, primary) | ✅ | M2      |
| Kokoro (offline, optional) | ✅ | M2    |
| Edge TTS (free, streaming) | ✅ | M2    |
| ElevenLabs        | ✅     | M2        |
| Azure TTS         | 🔵     | post-1.0  |

### Embedding providers

| Provider                  | Status | Milestone |
|---------------------------|--------|-----------|
| OpenAI `text-embedding-3` | ✅ (via LLM adapter) | M1 |
| Ollama `nomic-embed-text` | ✅ (via LLM adapter) | M1 |
| Voyage AI                 | 🔵     | post-1.0  |
| Cohere                    | 🔵     | post-1.0  |

### Provider switching mechanics

- **Default provider** is `JARVIS_LLM_DEFAULT_PROVIDER` (`openai`,
  `ollama`, or `gemini` today).
- All providers implement `ILLMProvider` — services never depend on
  concrete classes.
- **Fallback chain** — if the primary provider fails with a
  translated `LLMProviderError`, an ordered list of secondaries is
  tried before surfacing the error. Configurable in `AI Provider`
  settings.
- **Per-conversation override** — a conversation can pin a
  provider/model, stored on `conversations.metadata` — 🟡 not yet
  built, candidate for M11B (Productivity Suite) alongside the other
  chat-surface improvements there.
- **Cost-Aware Model Router** (post-1.0) — expands the earlier
  cost/latency heuristic above into a full router, natural fit once
  M20A's cost analytics (surfaced via M11's API Center Architecture
  module — see §8 M11) exist to inform routing decisions:
  - Automatic Provider Selection / Automatic Model Selection — pick
    the provider and model per request, not just per conversation.
  - Cost vs Quality Decision — weigh a cheaper/faster model against a
    higher-cost one per the user's configured preference, not a fixed
    rule.
  - Latency Optimization — short prompt → mini model; vision →
    capable multimodal model; the original heuristic, generalized.
  - Offline Model Selection — prefer a local Ollama model when
    privacy mode is on or connectivity is unavailable, never silently
    falling back to a cloud provider.
  - Intelligent Fallback / Retry Strategy — reuses M11's API Center
    Architecture's own Retry Strategy / Provider Fallback mechanics
    rather than a second retry implementation.
  - Budget Protection — refuses (or downgrades) a request that would
    exceed a provider's configured monthly budget, surfaced via the
    same Usage Analytics data (M11's API Center module).
  - Emergency Provider Switching — an exhausted-quota or hard-failed
    primary provider triggers an immediate switch to the next
    Provider Priority entry (M11 API Center Architecture), not a
    user-facing dead end.

---

## 14. Version timeline

| Version | Milestone | Theme                          | Status  |
|---------|-----------|---------------------------------|---------|
| **0.1** | M0 · M1   | Foundation + Chat Engine        | ✅ Shipped |
| **0.2** | M2        | Voice Platform                  | ✅ Shipped |
| **0.3** | M3        | Memory Platform (core)          | ✅ Shipped |
| **0.3.1** | M3.1    | Memory Platform (polish)        | ✅ Shipped |
| *(no bump)* | M4     | Automation Platform — shipped under `0.3.0`, see §15 version-drift note | ✅ Shipped |
| *(no bump)* | M5     | Desktop Platform — shipped under `0.3.0` | ✅ Shipped |
| *(no bump)* | M5.5   | Production Stabilization Pass — shipped under `0.3.0` | ✅ Shipped |
| **0.4** | M5A       | Agent Runtime                   | ✅ Shipped |
| **0.5** | M6        | Vision & Multimodal             | ✅ Shipped (Architecture Layer) |
| *(patch)* | —       | `0.5.1` security patch (cryptography upgrade), `0.5.2` DI container architecture fix — both out-of-band per §6, not milestones | ✅ Shipped |
| **0.6** | M7        | Workflow Intelligence           | 🟡 Active (Phase 1–2 shipped; Phase 3 deferred; Phases 4–6 paused) |
| **0.7** | M8        | React Frontend & Desktop Experience | 🟡 Active (Phase 1+4 shipped; Phase 3 partial; Phases 2/5/6/7 + Phase 3 remainder deferred — see Deferred Backlog, §8) |
| **0.8→0.12** | M9   | Runtime & Core Services          | ✅ **Completed** — see the versioning-granularity note below. All five task groups shipped (Runtime Core, Reliability, Plugin Platform, Developer Platform Tools), actual versions `0.8.0`–`0.12.0` per `CHANGELOG.md` — one minor bump per task group, not one bump for the whole milestone. |
| **0.13** | M10       | AI Orchestrator                  | 🟡 **Partial** — buildable-now scope shipped (Intent Engine, scoped Context Engine, parallel dispatch AC1, interim Permission Validation AC3, real streaming AC2 for the composed path, Decision Engine, `/api/v1/agent`); M10A/M14/M16-dependent remainder deferred, documented. |
| **0.14** | M10A      | Universal Search & Knowledge Platform | ✅ **Completed** — Knowledge Graph, Universal Search (provider registry), `/api/v1/search` + `/api/v1/knowledge/*`; File Search deferred pending M11B. |
| **0.15** | M10B      | Intelligence Layer               | ✅ **Completed** — Goal Manager, Routine/Preference Learning, Predictive Suggestions, Daily Briefing, `/api/v1/goals` + `/api/v1/intelligence/*`; automatic scheduled briefing delivery deferred pending M7's Scheduler (Phase 6). |
| **0.16** | M10.5     | MCP & Integration Platform      | 🟡 **Active** — Task Group A (Core Runtime) shipped: Capability Registry, transport abstraction, client/server runtimes, negotiation, `/api/v1/mcp/*`. |
| **0.17** | M10.5     | MCP & Integration Platform      | 🟡 **Active** — Task Group B (Transport Layer) shipped: stdio/websocket/http/ipc transports, transport factory, discovery/query, heartbeat monitor, four new relay events. Provider integrations remain a later task group. |
| **0.18** | M10.5     | MCP & Integration Platform      | 🟡 **Active** — Task Group C (Provider Framework) shipped: provider interface, registry with filtered discovery, lifecycle manager, metadata/config models, health collection, `/api/v1/mcp/providers/*`. Generic infrastructure only — real providers, authentication and OAuth are Task Group D. |
| **0.19** | M10.5     | MCP & Integration Platform      | 🟡 **Active** — Task Group D (Authentication Foundation) shipped: credential model, encrypted-at-rest store, auth strategy registry, provider sessions, permission bridge, `/api/v1/mcp/auth/*`. Infrastructure only — no real providers, no OAuth flow, no vendor integrations. |
| **0.20** | M10.5     | MCP & Integration Platform      | ✅ **Completed** — Task Group E (SDK, Developer Experience & Milestone Closure) shipped: SDK builders, validation framework, `jarvis mcp` CLI, self-contained examples, `MCPDiagnostics`, `/api/v1/mcp/diagnostics` + `/api/v1/mcp/validate`. Milestone closed across five task groups; Agent Trace integration and a server-side listener deferred to M11 (named in §8). |
| **0.21** | *(none)* | Backlog Completion & Stabilization Pass | ✅ **Completed** — not a milestone. Closes documented §15 backlog belonging to already-complete milestones: five published-but-unrelayed WebSocket categories, the `HealthMonitor` disk collector, `/api/v1/health`, and `/api/v1/sessions`'s envelope (one intentional breaking change). Also fixes two UI surfaces found rendering invented data over working backends — the Plugin Manager's mock provider and the Module Manager's randomised update flag. M8's deferred frontend backlog is deliberately untouched: it is the M8 milestone itself, in a UI stack being replaced. |
| **0.22** | *(none)* | Final Backlog Completion Pass | ✅ **Completed** — not a milestone. Closes what the roadmap had *not* written down: the startup greeting fed the LLM invented tasks, calendar events, weather and now-playing data and spoke them as fact (now real Goal Manager data, or nothing); three Settings pages still advertised milestones that had already shipped (M4 Automation ×2, M9 Plugins); and the Home dashboard's five service cards showed a green "connected" light over illustrative data (now an explicit preview state). Sweep found zero TODO/FIXME/HACK/XXX in `src/`, zero dead routes, zero unwired DI services. **All backlog for completed milestones is finished.** |
| *(next)* | M11       | Integrations & Cloud Platform    | 🔴 Planned |
| *(next)* | M11A      | SEO Intelligence                | 🔴 Planned |
| *(next)* | M11B      | Productivity Suite               | 🔴 Planned |
| *(next)* | M12       | Smart Home                      | 🔴 Planned |
| *(next)* | M13       | Computer Control                | 🔴 Planned |
| *(next)* | M13A      | AI Sandbox                      | 🔴 Planned |
| *(next)* | M13B      | Self-Healing & Observability     | 🔴 Planned — *(new, Aug 2026 roadmap extension; foundational subset of M18/M20A, which remain their full-scale realizations)* |
| *(next)* | M14       | Security Platform               | 🔴 Planned |
| *(next)* | M14A      | Backup Platform                 | 🔴 Planned |
| *(next)* | M15       | Personality Engine              | 🔴 Planned |
| *(next)* | M16       | Reflection Engine               | 🔴 Planned |
| *(next)* | M17       | Companion Intelligence          | 🔴 Planned |
| *(next)* | M17A      | Training Studio                 | 🔴 Planned |
| *(next)* | M18       | Self-Healing & Diagnostics Platform | 🔴 Planned |
| *(next)* | M19       | Knowledge Graph & Digital Twin Platform | 🔴 Planned |
| *(next)* | M20       | Predictive Intelligence Platform | 🔴 Planned |
| *(next)* | M20A      | Analytics & Observability Platform | 🔴 Planned |
| *(next)* | M21       | Mobile Platform                 | 🔴 Planned |
| *(next)* | M22       | Edge AI Platform                | 🔴 Planned |
| *(next)* | M23       | Distributed JARVIS              | 🔴 Planned |
| *(next)* | M23A      | Robotics & Hardware Control Platform | 🔴 Planned |
| *(next)* | M23B      | Autonomous Planning & Decision Engine | 🔴 Planned |
| **1.0** | M24       | Production Release              | 🟡      |
| **1.1** | M25       | Cognitive Intelligence Platform  | 🟡      |
| **1.2** | M26       | Self-Learning & Autonomous Evolution Platform | 🟡 |
| **1.3** | M27       | World Model & Environmental Intelligence Platform | 🟡 |
| **1.x** | —         | Post-1.0 improvements (🔵 & ⚪ backlog items) | future |

*(Version numbers 0.10 onward were originally planned to shift by
three slots, Aug 2026, to accommodate the new lettered companions
M10A, M10B, and M11B — these were meant as version-string sequence
positions, not milestone identities; no milestone was renumbered, per
the frontend migration's "zero renumbering" rule. See §8 for the full
retitling rationale. **Superseded by the versioning-granularity note
immediately below**: those specific slot numbers (`0.9`/`0.10`/`0.11`)
were actually consumed by M9's own Task Groups B/C/D before M10 ever
started, not reserved for M10A/M10B as originally planned here — the
milestone-to-slot mapping this note describes never actually played
out; only the "no milestone was renumbered" principle held.)*

*(Versioning-granularity note, added Aug 2026 during M9 Task Group D:
in practice, M9's Task Groups have each earned their own minor bump —
`0.9.0`/`0.10.0`/`0.11.0` for Task Groups B/C/D respectively, per
`CHANGELOG.md` — rather than saving up one bump for the whole
milestone as §6's "exactly once per completed top-level milestone"
rule describes. This is an accepted, real refinement for an unusually
large milestone (five task groups, each substantial), not a violation
left uncorrected — M9's own eventual completion does not get a second,
redundant minor bump on top of the granular ones already shipped. The
column above is deliberately marked `*(next)*` rather than a specific
projected number from M10 onward, since M9 already proved the original
one-slot-per-milestone numbering in this table doesn't hold in
practice; the next real version number is decided when that milestone
actually ships, per §6's own "feature-driven, not time-boxed" rule.)*

Version bumps are **feature-driven**, not time-boxed — see §6 for the
full policy. A version ships when its milestone's acceptance criteria
pass the [Validation gate](#5-validation-gate) (§5).

---

## 15. Technical debt

Reorganized (this documentation pass) from the previous
category-by-topic layout into a Resolved / Pending / Future timeline —
same underlying items, regrouped by disposition instead of subsystem,
so "what's actually still owed" reads in one pass. Every item below is
either a direct repository fact (a file, a test, a commit-verified
fix) or an explicit forward-reference to a not-yet-started milestone;
nothing here is a new claim invented for this pass.

### Resolved

- **Version drift** — `pyproject.toml`, `Settings.app_version`, and
  `src/jarvis/__version__.py` were stuck at `"0.3.0"` since M3.1
  despite M4, M5, and M5.5 all shipping real work since; all three now
  read `"0.5.2"` in lockstep (verified during the roadmap audit that
  added this note). *Cleared in M5A.*
- **Static analysis was never actually enforced against this
  codebase** — every pre-existing finding from the M5A validation
  pass baseline (588 ruff / 262-of-304-files black / 288 mypy) was
  triaged (safe-fix / manual-review / accepted-debt / false-positive),
  the safe-fix tier applied, and `.pre-commit-config.yaml` +
  `.github/workflows/ci.yml` added so this can't silently regress
  again. Remaining pre-existing findings (e.g. `PLC0415` on
  intentionally-lazy imports, widespread in `container.py` and
  elsewhere) are deliberately accepted debt, not an enforcement gap —
  see the per-file-ignore pattern in `pyproject.toml`. *Cleared by the
  Repository Stabilization pass (between M6 and M7).*
- **`pytest --cov` was broken** — the subprocess-coverage propagation
  gap in `tests/unit/test_performance_lazy_imports.py` (its
  subprocess's `cwd` change broke `COV_CORE_*` env-var resolution) was
  root-caused and fixed by stripping those env vars from that one
  subprocess's environment. `pytest --cov` now runs cleanly; 64% total
  coverage was measured for the first time. *Cleared by the Repository
  Stabilization pass.*
- **CI was manual** — `.github/workflows/ci.yml` (added during the
  Repository Stabilization pass) now runs on every PR/push to `main`:
  ruff/black/mypy (advisory, `continue-on-error: true` while
  pre-existing lint debt is worked down), `pytest --cov` as a hard
  gate, `pip check`, and `pip-audit` (advisory). Verified present in
  the repository as of this pass. Still open, correctly scoped to a
  future milestone rather than left implicit here: the workflow runs
  `windows-latest` only, not the Windows+Ubuntu matrix originally
  envisioned, and ruff/black/mypy aren't hard gates yet — both remain
  M24 scope (see Future, below).
- **`cryptography`'s share of the dependency CVE backlog** — of 24
  known CVEs across 12 pre-existing pinned dependencies, `cryptography`
  43.0.3→48.0.1 (the `0.5.1` patch) resolved `PYSEC-2026-35`,
  `PYSEC-2026-1284`, `PYSEC-2026-2141`, `GHSA-537c-gmf6-5ccf`, and
  `CVE-2026-39892` — confirmed via `pip-audit`: 24 → 19 total findings
  repo-wide, all 5 removed entries were `cryptography`'s. *Cleared in
  the `0.5.1` patch.* (The remaining ~19 are Pending, below.)
- **`aiosqlite` / `langgraph-checkpoint-sqlite` incompatibility** —
  `langgraph-checkpoint-sqlite` 2.0.11's `AsyncSqliteSaver.setup()`
  calls a method (`Connection.is_alive()`) that only exists because
  older `aiosqlite` subclassed `threading.Thread`; `aiosqlite` 0.21+
  dropped that base class. Fixed with a version pin (`aiosqlite<0.21`)
  + a permanent regression test during the M5A pre-merge validation
  pass, so an unrelated future dependency bump can't silently
  reintroduce it.
- **`PlaywrightBrowser` / `WindowsAutomationAdapter` / `AutomationService.launch`
  / `BrowserService.open`** (all previously raised `NotImplementedError`)
  — real implementations. *Cleared in M4.*
- **`AgentOrchestrator`** (previously a placeholder) — real compiled
  LangGraph `StateGraph`; see §3's M5A entry. *Cleared in M5A.*
- **`SystemService.status()`** (previously a stub) — real
  `psutil`-backed implementation, needed as the agent's
  `get_system_status` tool. *Cleared in M5A.* (Its own small follow-up
  — System Information and Performance Monitor still calling `psutil`
  directly instead of through this service — is Pending, below.)
- **`ChromaVectorStore` / `MemoryService.remember` / `recall`**
  (previously placeholders) — real implementations. *Cleared in M3.*
- **No Alembic migrations** — real migration chain added. *Cleared in
  M3.1.*
- **No dedicated Timeline UI view** — real Timeline view shipped.
  *Cleared in M3.1.* (Its own small follow-up — no keyword/semantic
  search box or date-range control in the dialog — is Pending, below.)
- **`retention_days` changes didn't retroactively re-stamp existing
  rows** — fixed. *Cleared in M3.1.*
- **No background scheduler for `enforce_policies()`** — a scheduler
  now runs it. *Cleared in M3.1.* (The interval still isn't
  user-configurable — folded into the same Pending item as the
  archive/hard-delete follow-up, below.)
- **`IVisionProvider` / `IOCRProvider`** — this section previously
  listed these as reserved interfaces "will land in M6." M6 has since
  shipped (see §3): both ports are real, in `core/interfaces/`, with
  `MockVisionProvider`/`MockOCRProvider` wired in `infrastructure/`.
  *Correcting a stale forward-reference during this documentation
  pass — reclassified from "reserved" to resolved, no code changed.*
- **Whisper model loaded eagerly on first call** — now lazy. *Cleared
  in M3.1.*

### Pending

Open items with no assigned future milestone — either genuinely
unscheduled, or explicitly tracked as continuous work under §7 rather
than a numbered milestone.

- The remaining ~19 dependency CVEs (mostly across
  `langchain*`/`langgraph`/`black`/`pytest`) each require a
  major-version bump crossing this project's `<1.0`-style pins —
  recommended as its own dedicated, separately-tested effort rather
  than bundled into a feature milestone (same rationale as the
  `cryptography` pass). One of the 19, `CVE-2025-67644` (SQL injection
  via checkpoint-metadata filter keys in `langgraph-checkpoint-sqlite`),
  is confirmed not exploitable by anything M5A ships (see §3's M5A
  entry). Note: `.github/workflows/ci.yml`'s `pip-audit` step comment
  still says "24 pre-existing known vulnerabilities," not updated
  after the `0.5.1` upgrade — flagged here, not fixed as part of this
  documentation-only pass (it's a CI file, not the roadmap).
- Pydantic warning: `LoggingSettings.json` shadows a parent attribute
  — cosmetic; consider renaming to `emit_json` in a future refactor.
- pynput requires a display server — global hotkeys unavailable in
  headless environments (documented; degrades gracefully — a
  permanent platform constraint, not a bug to fix).
- Chat streaming's "chunk" vs "typewriter" UX difference is currently
  identical (both append every token); real chunked mode with a
  typing indicator is a polish task, not yet scheduled.
- Screen-shot generation via Qt's `grab()` on
  `QT_QPA_PLATFORM=offscreen` produces empty images — dev tool only,
  works on Windows/mac/X11.
- System Information and Performance Monitor's developer views call
  `psutil` directly rather than through `SystemService.status()` —
  de-duplicating those two call sites is a nice-to-have, no milestone
  assigned.
- No keyword/semantic search box and no date-range control in the
  Timeline dialog itself — the repository/service layer already
  supports date filtering, just not wired to a widget.
- `enforce_policies()`'s interval still isn't user-configurable, and
  it still *archives* (not hard-deletes) expired/pruned rows — call
  `delete_archived()` to reclaim space, or wire a "Clear Memory"
  confirmation that also purges archives.
- `OllamaLLMProvider.embed` exists but its embedding model default is
  whatever `settings.ollama.model` is — no dedicated
  `nomic-embed-text` fallback wiring yet as originally scoped.
- `IWakeWordDetector` — real engines shipped (Porcupine/openWakeWord);
  ongoing accuracy tuning tracked as continuous work (§7), not a fixed
  milestone.
- STT backend `DEEPGRAM` — enum declared, factory raises
  `ConfigError("reserved")`; tracked as continuous work (§7).
- Extract `RecordingSession` from `VoiceService` so PTT and toggle
  modes share one state machine — no milestone assigned.
- Introduce an `AppContext` façade so widgets receive one dependency
  (`ctx`) instead of many — reduces constructor noise as features
  grow; no milestone assigned.
- Consolidate CSV/list env parsing into a reusable validator
  (currently duplicated in `ApiSettings.cors_origins` and
  `WakeWordSettings.keywords`) — no milestone assigned.
- ChromaDB warms up in-process; consider spawning it as a subprocess
  when memory count > 100k — no milestone assigned.
- Log JSON sink uses `sys.stdout.write` sync — move to a queued
  handler with `enqueue=True` (the file sink already does this) — no
  milestone assigned.
- No `pytest-qt` widget tests beyond the headless smoke suite —
  introduce one QtBot smoke per major widget as new UI ships; no
  milestone assigned.

**M8/M9-era items** *(added Aug 2026, Project Completion Audit — these
already exist in full detail in their own task groups' changelog
addenda and `IMPLEMENTATION_ROADMAP.md`'s per-task-group "Future Work"
notes; consolidated here so §15 remains the one place every open item
across the whole repository is tracked, not just M0–M7's)*:

- **M8's full Deferred Backlog** — Notification Center, Context Menu
  system, Background Task Manager's frontend surface, Workspace views,
  Window management, Responsive/DPI/Multi-monitor, all of Phases 2/5/6/7
  — see M8's own §8 entry's "Deferred Backlog" subsection and
  `IMPLEMENTATION_ROADMAP.md` §6 for the full checklist. None of it
  blocks M9.
- **M9 Task Group B** — retrofitting `VoiceService`/`HotkeyService`/
  `BrowserService`/`AutomationService`/`SystemService` onto `IService`
  and migrating their lifecycle-hook ownership into `ServiceManager`;
  cascading `ServiceManager.restart()` to a service's dependents;
  unifying `RuntimeSession` with `Conversation`/LangGraph `thread_id`
  beyond the optional-reference link already added; extending §6's
  WebSocket category table to the pre-existing `voice`/`ai`/
  `automation`/`memory`/`progress`/`notification` categories (only the
  Runtime/Service/Session/Configuration/Health/Task/Resource
  categories are relayed today — **closed Aug 2026, backlog pass**:
  `voice.state_changed`, `automation.step`, `progress.update_phase`,
  `notification.plugin` and `plugin.custom` are relayed now. Every one
  of those events was already published by real code; only the
  `EVENT_TYPE_NAMES` entry was missing. Four event classes stay out
  because nothing publishes them yet — `WorkflowStepEvent`,
  `ScheduledJobFiredEvent` (both M7), `VisionProviderStatusEvent` (M6's
  remainder), `PluginCrashedEvent` (the deferred supervisor) — and
  `DebugLogCapturedEvent` stays out because it fires per log line and
  this hub has no per-category subscription); a genuine headless `_run_api_only()`
  runtime mode (the embedded API server exists only inside the GUI
  runtime path); M14's real Bearer/JWT session-token issuance (today's
  `/api/v1/ws` auth uses a `SessionManager` session id as a real,
  working stand-in).
- **M9 Task Group C** — an external supervisor/watchdog process for
  genuine automatic process restart after a crash (Crash Recovery only
  detects and reports today, by design — a process cannot restart
  itself after crashing); ~~GPU/disk collectors for `HealthMonitor`~~
  **disk closed Aug 2026, backlog pass** — `disk_percent`/
  `disk_free_bytes`/`disk_total_bytes` are in the snapshot as flat
  top-level keys, which is what makes them targetable by
  `ResourceManager.register_budget()`; **GPU stays open** and is not
  faked, because reading it needs a vendor library this project does
  not depend on; enforcement (throttle/kill) on a Resource Manager
  budget breach; persisting/resuming the Background Task Manager's
  queue across a restart.
- ~~**`/api/v1/sessions`'s response shape**~~ — **closed Aug 2026,
  backlog pass.** The route now returns the `{"data": ..., "meta": ...}`
  envelope §5 mandates. The stated precondition ("revisit once M9 Task
  Group D or M10+ adds the next real REST resource") was met several
  times over — six route modules use the envelope consistently — so the
  reasoning for deferring had expired and the inconsistency was the only
  thing left. This is the pass's one intentional breaking change:
  callers read `response.json()["data"]["session_id"]`. The route keeps
  its separate *authentication* exemption.
- ~~**Health router mount prefix mismatch**~~ — **closed Aug 2026,
  backlog pass.** The router is now mounted at **both** `/api` and
  `/api/v1`, so the documented `/api/v1/health` works without breaking
  the `/api/health` that external monitoring may have polled since M0.
  One router, mounted twice — not two implementations that could drift
  apart, and a test pins that their bodies stay identical.

**Found *and* closed by the Aug 2026 backlog pass** *(previously
untracked — the audit surfaced them, so they are recorded here with
their resolution rather than filed as new debt)*:

- ~~**Desktop Plugin Manager rendered fabricated data**~~ — the M5-era
  `PluginManagerView` was still wired to a `MockPluginProvider` that
  seeded two invented plugins ("Weather Widget", "Spotify Connector")
  and a three-entry invented marketplace. M9 Task Group C had shipped
  the real Plugin Platform — registry, loader, sandbox, permission
  model, marketplace, `/api/v1/plugins/*` — and this view was simply
  never rewired, so it showed made-up rows next to a working runtime.
  That is exactly what M8 AC2 ("no screen renders fake, simulated, or
  placeholder data") forbids. Now reads the live `PluginRegistry`
  through a new `PluginRegistryProvider`; Enable/Disable/Reload perform
  real lifecycle transitions; an install with no plugins shows an empty
  state. The mock was deleted, not left beside the real one.
- ~~**Module Manager invented update availability**~~ — `check_update`
  rolled `random.random() < 0.3` and fabricated a bumped version number
  when it came up, so the same click told the user a different story
  each time. There is no module update channel, which has exactly one
  honest answer; the UI now says "No update channel" rather than the
  equally untrue "Up to Date".

### Future

Open items with an explicit, named future-milestone owner — listed
here, not implemented, per this pass's documentation-only scope.

- The CI version-match step (fails the build if `pyproject.toml`,
  `Settings.app_version`, and `__version__.py` diverge) and the
  Windows+Ubuntu CI matrix (today `windows-latest` only) — **M24**,
  alongside promoting ruff/black/mypy from advisory to hard gates.
- No PII redaction toggle before embedding — content is embedded and
  stored verbatim. Candidate before any cloud-embedding provider ships
  — **M14**.
- Plugin SDK interfaces — **M9 Task Group D** *(relabeled Aug 2026,
  Project Completion Audit — these three items still said "M8" from
  before the Aug 2026 retitling moved Plugin Platform's full scope
  from M8 to M9; no scope change, correcting a stale forward-reference
  only)*.
- Move DI provider builders out of `container.py` into a per-domain
  `providers/` package once factory count grows further — **M9 Task
  Group D**, when the plugin loader adds its own factories.
- Promote the "strict dependency rule enforced by convention" note
  (§11) into an actual lint rule before the plugin surface makes
  violating it externally visible — **M9 Task Group D**.
- QTextBrowser append is O(n) per token — swap to a custom scroll area
  with row widgets once messages exceed ~2k / conversation — **M11**,
  alongside the other chat-surface work there.
- No property-based tests — consider `hypothesis` for the memory
  search ranking — **M10**, a natural place given the ranking logic
  it will add.
- Fernet key today lives in `.env` — **M14** moves it to OS keyring by
  default with a one-time migration.
- `.env` writes are line-based; a race could corrupt a concurrent edit
  — **M14** moves this to atomic tempfile+rename.
- API keys are visible in memory once read — **M14** introduces
  `SecretProxy` with time-boxed decryption.
- Plugin sandbox (M8) is permission-based, not process-isolated at
  first — **M14** hardens it to process isolation for plugins
  requesting `network` + `filesystem` simultaneously.

---

## 16. Recommended development order

**Guiding principles**

1. Ship user-visible value early and often.
2. Never let a milestone start without its port defined (§4).
3. Prefer dropping in an implementation for an existing hook over
   opening new architectural fronts.
4. Keep the test count monotonic — no milestone reduces coverage (§4,
   §5).
5. Every milestone passes the [Validation gate](#5-validation-gate)
   (§5) before the next one starts.

**Sequence and rationale** (§8's milestone numbering already encodes
this order; this table exists to make the *why* explicit, not to
re-derive a different order):

*(M6 shipped its Architecture Layer Jul 2026 — see §3 — and its "Order
1" row below is kept for historical continuity rather than
renumbering every row that follows; the table's own "why this order"
purpose still holds for M7 onward.)*

| Order | Milestone | Reason |
|-------|-----------|--------|
| 1 | **M6** Vision & Multimodal ✅ *(Architecture Layer — shipped)* | M5A explicitly deferred the vision tool here; unblocked immediately, no new dependency to wait on. |
| 2 | **M7** Workflow Intelligence 🟡 *(Active — Phase 1–2 shipped, Phase 3 deferred, Phases 4–6 pending)* | Turns the M5A agent graph from single-run into a real workflow engine before anything else builds on top of "one prompt, one graph run." |
| 3 | **M8** React Frontend & Desktop Experience 🟡 *(Active — Phase 1+4 shipped, rest deferred; see §8's Deferred Backlog)* | With a maturing agent + workflow surface, and the Aug 2026 decision to migrate off PySide6 (see `TECH_STACK.md`), the UI is rebuilt before new backend surfaces need a home to render into. |
| 4 | **M9** Runtime & Core Services 🟡 *(Active — Runtime Core + Reliability + Plugin Platform shipped, Task Groups A–D; Developer Platform Tools pending)* | Third-party extensions (this milestone's own Plugin Platform scope, formerly M8's) need a governed runtime to load into; scheduled right after the new frontend so Developer Mode's ported panels have a real backend from the start. |
| 5 | **M10** AI Orchestrator | Formalizes the M5A agent graph into a dedicated orchestration platform, absorbing M7 Phase 3's deferred cross-tool-parallelism scope — scheduled early since M15–M20's "companion intelligence" arc all route through it. |
| 5A | **M10A** Universal Search & Knowledge Platform | Only needs M3 (already done); scheduled alongside M10 because M15–M20 all depend on it and it's cheaper to build once, early, than to retrofit under six later milestones — unchanged reasoning from the original (pre-migration) M10 Knowledge Engine slot. |
| 5B | **M10B** Intelligence Layer | The backing engine M15's Proactive Intelligence and M16's Goal/Behaviour Reflection modules both consume; scheduled alongside M10A since both are M15/M16 prerequisites. |
| 5C | **M10.5** MCP & Integration Platform | *(Added Aug 2026, roadmap extension.)* Scheduled immediately before M11 by design: M11's credential-backed providers should be built **on** the MCP protocol/registry substrate rather than retrofitted onto it afterwards. Depends only on already-shipped work (M5A, M9, M10, M10A). |
| 6 | **M11** Integrations & Cloud Platform (+ **M11A** SEO Intelligence, + **M11B** Productivity Suite alongside it) | Plugins (M9) need somewhere governed to make real external calls — this generalizes M5's mock API Center into that surface, now merged with the original Productivity Platform's integration half; SEO Intelligence and Productivity Suite are independent enough to build in parallel with additional contributors. |
| 7 | **M12** Smart Home | Best delivered as a group of plugins on top of M9's Plugin Platform, same as before. |
| 8 | **M13** Computer Control (+ **M13A** AI Sandbox, + **M13B** Self-Healing & Observability alongside it) | Needs M6 (vision) and M7 (workflow engine) both in place; the sandbox is scheduled *with* it, not after, given the risk profile. **M13B** *(added Aug 2026, roadmap extension)* is scheduled here so M14–M17 are built on a runtime that already reports its own health — it pulls forward the foundational subset of M18/M20A, which remain their full-scale realizations. |
| 9 | **M14** Security Platform (+ **M14A** Backup Platform alongside it) | Harden everything now that the feature surface (through M13) is stable; backup strategy depends on knowing the final encryption-at-rest scheme. Already absorbs the Aug 2026 migration brief's "Security & Privacy" scope in full — see M14's own Aug 2026 review note. |
| 10 | **M15** Personality Engine | Needs M10A's knowledge substrate and M10B's intelligence engine; otherwise low-risk, could parallelize with M16. |
| 11 | **M16** Reflection Engine | Builds on M10A; feeds M17. |
| 12 | **M17** Companion Intelligence (+ **M17A** Training Studio alongside it) | The synthesis milestone for M10A/M10B/M15/M16; Training Studio pairs naturally since both extend M7's recorder. |
| 13 | **M18** Self-Healing & Diagnostics Platform | Generalizes M5.5's one-time audit into a permanent, self-healing subsystem once there's enough surface area (M6–M17) worth monitoring. |
| 14 | **M19** Knowledge Graph & Digital Twin Platform | The full realization of M10A's foundation, now informed by M16/M17's real usage data. |
| 15 | **M20** Predictive Intelligence Platform (+ **M20A** Analytics & Observability Platform alongside it) | Needs M19; the analytics dashboard is scheduled with it since both consume the same underlying event/metrics data. |
| 16 | **M21** Mobile Platform | Needs M11 (transport, including its Android Companion pairing scope) and M14 (security bar); intrinsically parallel with a dedicated mobile team once started. |
| 17 | **M22** Edge AI Platform | Only needs M1 (Ollama); could in principle move earlier, kept here since it's a lower-priority hardware-specific investment relative to the companion-intelligence arc above it. |
| 18 | **M23** Distributed JARVIS | Needs M21 (mobile transport) and M14 (security); the natural conclusion of the multi-device story before final release. |
| 18A | **M23A** Robotics & Hardware Control Platform | Needs M21 (mobile transport) and M22 (edge inference for on-device robotics/sensor intelligence); scheduled alongside M23 rather than dependent on it — both are independent extensions of the M14-hardened platform. |
| 18B | **M23B** Autonomous Planning & Decision Engine | Needs M20 (predictions to plan against), M22 (local/cloud execution selection), and M23A (physical execution targets); scheduled last among the capability milestones since it orchestrates nearly everything before it, immediately before the M24 wrap-up. |
| 19 | **M24** Production Release | Wrap-up. Ships `v1.0.0`. |
| 20 | **M25** Cognitive Intelligence Platform | The first post-`v1.0.0` milestone; needs a stable M24 release to learn from and improve upon, and consumes planning services from M23B. Marks the start of the roadmap's "Version 2.0" era. |
| 21 | **M26** Self-Learning & Autonomous Evolution Platform | Builds directly on M25's cognitive architecture (Cognitive Memory, Knowledge Evolution, Self Improvement Engine); needs M25 stable before it has anything to learn from and refine. |
| 22 | **M27** World Model & Environmental Intelligence Platform | Extends M19's Knowledge Graph with a persistent world model; needs M23A (sensor/physical data) and M6 (vision) in place, and is consumed by M23B's planning and M23A's Robotics Runtime simulation. |

**Parallelisation opportunities**

- M11A (SEO Intelligence) and M11B (Productivity Suite) alongside M11
  (Integrations & Cloud Platform) — focused, independent verticals.
- M10A (Universal Search & Knowledge Platform) and M10B (Intelligence
  Layer) alongside M10 (AI Orchestrator) — both are lettered
  companions with their own dependency chain (M3, M7), not sequential
  extensions of M10 itself.
- M13A (AI Sandbox) alongside M13 (Computer Control) — the sandbox
  exists specifically to de-risk M13, most efficient built alongside
  it rather than after.
- M14A (Backup Platform) alongside M14 (Security Platform) — same
  reasoning; backup strategy needs the final encryption scheme.
- M17A (Training Studio) alongside M17 (Companion Intelligence) — both
  extend M7's recorder; low coupling to each other.
- M20A (Analytics Platform) alongside M20 (Predictive Intelligence) —
  both consume the same metrics substrate.
- M12 (Smart Home) vendor adapters are independent and parallel once
  M9 (Plugin Platform) exists.
- M21 (Mobile Platform) is intrinsically parallelizable with a
  dedicated mobile team once M11/M14 land.

**Deferred (post-1.0)**

- Voice cloning.
- Chrome extension bridge.
- Python REPL developer tool.
- Full Matter fabric commissioning.
- Response caching, model performance profiler (🔵 optional items from
  §10 with no forcing dependency).

---

## 17. Appendix — companion documents

This roadmap is the single source of truth for *planning*; these
documents are the source of truth for *what actually shipped* in
their respective milestone, referenced throughout §3 and never
duplicated back into this file:

| Document | Covers |
|----------|--------|
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | The Aug 2026 architecture standard — layered architecture, module architecture/lifecycle/state machine, API/WebSocket/Event Bus/service/error/manifest/settings/storage/developer/UI/AI/automation/security/testing/performance standards. Governs M8 onward. |
| [`ARCHITECTURE_LEGACY.md`](ARCHITECTURE_LEGACY.md) | The as-shipped M0–M7 PySide6-era architecture (renamed from `ARCHITECTURE.md`, Aug 2026) — package responsibilities, dependency rules, provider-registration pattern. Historical reference, not updated going forward. |
| [`TECH_STACK.md`](TECH_STACK.md) | The Aug 2026 frontend technology decision — React 19 + Tauri + the full stack table, architecture diagram, folder structure, coding standards. Governs M8 onward; does not change M0–M7's shipped PySide6 history. |
| [`IMPLEMENTATION_ROADMAP.md`](IMPLEMENTATION_ROADMAP.md) | Active, phase-by-phase execution checklist for M8 (React Frontend & Desktop Experience) — narrower and more actionable than this document's own §8 entry, which remains the authoritative source for M8's dependencies/AC. |
| [`MILESTONE_4_DELIVERY.md`](../MILESTONE_4_DELIVERY.md) | M4 Automation Platform — full file list, architecture diagram, manual testing checklist. |
| [`MILESTONE_5_DELIVERY.md`](../MILESTONE_5_DELIVERY.md) | M5 Desktop Platform — full file list across all three delivery passes, manual testing checklist. |
| [`AUDIT_REPORT_M0-M5.md`](../AUDIT_REPORT_M0-M5.md) | M5.5 Production Stabilization Pass — per-finding evidence, fix, and verification. |
| [`MILESTONE_5_AGENTS_DELIVERY.md`](../MILESTONE_5_AGENTS_DELIVERY.md) | M5A Agent Runtime — full file list, architecture, request-flow walkthrough, manual testing checklist. |
| [`AUDIT_REPORT_M5-AGENTS.md`](../AUDIT_REPORT_M5-AGENTS.md) | M5A pre-merge validation pass — environment, static analysis, test results, security/performance findings, production-readiness assessment. |
| [`CHANGELOG.md`](../CHANGELOG.md) | Chronological, version-tagged summary of every shipped change. |
| [`CONFIGURATION.md`](CONFIGURATION.md) | `Settings` structure, `.env` conventions. |
| [`DEPENDENCY_INJECTION.md`](DEPENDENCY_INJECTION.md) | `Container` wiring conventions. |
| [`THEMING.md`](THEMING.md) | `ThemeManager` / QSS theme structure. |
| [`LOGGING.md`](LOGGING.md) | Logging sinks and conventions. |
| [`PACKAGING.md`](PACKAGING.md) | PyInstaller/Inno Setup packaging status (foundational as of M5.5; verified build is M24 scope). |
| [`FUTURE_INTEGRATION_GUIDE.md`](FUTURE_INTEGRATION_GUIDE.md) | How to swap a mock M5 integration (Gmail, Spotify, etc.) for a real one. |
| [`PLUGIN_GUIDE.md`](PLUGIN_GUIDE.md) | Plugin architecture notes ahead of the real M9 loader (moved from M8 in the Aug 2026 frontend migration — see §8). |
| [`ROADMAP.md`](ROADMAP.md) | Lighter-weight milestone summary — explicitly *not* the source of truth; kept loosely in sync with this document. |

---

*Last updated: Jul 2026 — **v3.0 reorganization.** This roadmap was
restructured end-to-end: all completed-milestone history (§3) was
preserved and de-duplicated (the old version described M4/M5/M5.5/M5A
twice — once in prose, once as a formal entry — now merged into one
account each); four new permanent sections were added (§4 Engineering
standards, §5 Validation gate, §6 Versioning policy, §7 Cross-platform
systems); the future-milestone plan (old M6–M14, nine milestones) was
replaced with a long-term 24-milestone-plus-six-companion-milestone
plan (§8, M6–M24 plus `M11A`/`M13A`/`M14A`/`M17A`/`M20A`) reaching
through `v1.0.0`; every renumbered or relocated feature is traceable
via the new §9 Feature carry-forward map, so nothing already planned
was silently dropped. No completed milestone's history, delivery
document, or changelog reference was altered — only reorganized and
de-duplicated. Milestone 6 (Vision & Multimodal) remains next.

*Jul 2026 addendum:* added the **Google Workspace Integration & AI
Meeting Intelligence** module under M11 — Google OAuth/multi-account
auth, the full Workspace API surface (Gmail, Calendar, Meet, Drive,
Docs, Sheets, Slides, Chat, Tasks, People, Events), Calendar/Meet/
Gmail/Drive/Docs/Sheets/Slides/Chat/Tasks/People "Intelligence"
feature groups, an AI Meeting Assistant (transcript processing,
summaries, decisions, action items, deadlines), and Workspace Memory
Integration into M3/M10A. Provider-abstracted and DI-wired by design,
explicitly scoped to extend later to Microsoft 365, Slack, Notion,
Jira, Trello, ClickUp, Zoom, Discord, and Dropbox without an
architecture change. Planning only — no implementation exists yet, no
milestone numbering changed, M11's existing content and every
completed milestone (§3) are untouched. This is now the official
roadmap section for all Google Workspace features.

*Jul 2026 addendum 2:* expanded the Google Workspace module with six
new feature groups — **Workspace Automation** (calendar-triggered,
cross-service, multi-step workflows spanning Gmail/Calendar/Meet/
Docs/Drive/Sheets/Tasks, built on M7's Workflow Intelligence),
**AI Meeting Insights** (topic segmentation, sentiment/risk detection,
decision confidence, meeting health/productivity scores, executive/
technical summaries), **Workspace Search** (unified semantic + natural
-language search with AI answer generation across every connected
service), **Workspace Administration** (domain/org/multi-account
support for enterprise deployments — explicitly optional, gated on
granted admin permission scopes), **Workspace Developer Tools** (an
OAuth debug panel, API request/response inspector, rate-limit and
integration-health dashboards, landing in Developer Mode alongside
M5A's Agent Trace panel), and **Future AI Productivity Features**
(daily briefings, an AI executive assistant, workspace knowledge
graph — exploratory, not yet bound to a milestone acceptance
criterion). Also expanded Google Meet Intelligence with live
monitoring, recording/transcript lifecycle tracking, and attendance
analytics; hardened the Architecture Notes with an explicit Provider
Abstraction statement (Google Workspace is the first of several
planned Productivity Providers, all behind identical
`core.interfaces` Protocols) and a dedicated Security subsection
(token rotation, least privilege, secret rotation, credential
encryption, retry/circuit-breaker resilience, request idempotency);
extended the Future Expansion provider list with Box, Confluence, and
Asana. §10's feature backlog gained one row per new feature group.
Still planning only — no implementation, no milestone numbering or
ordering change, M11's pre-existing content and every completed
milestone (§3) untouched.

*Jul 2026 addendum 3:* redesigned **M12 — Smart Home** into **M12 —
Smart Home & IoT Platform**, a complete enterprise-grade Smart Home
milestone, mirroring the depth of M11's Google Workspace module. The
single flat feature list was replaced with 15 structured modules:
Smart Home Core, Connectivity Layer, Smart Lighting, Smart Locks,
Sensors, Smart Cameras, Energy Management, Appliance Control, Home
Automation, AI Home Assistant, Security & Safety, Remote Access, Smart
Home Memory, Smart Home Analytics, and Developer Tools. Architecture
notes were expanded with ten binding constraints — provider
abstraction per device category, independent replaceability, clean
device-communication interfaces, local-first-preferred/cloud-optional
operation, Secrets Management for all credentials, Event Bus
integration, AI Sandbox-compatibility for every automation, Long-Term
Memory integration, architecture-level multi-home support, and
opt-in-only face recognition. The Future Expansion vendor list grew to
15 named vendors (Philips Hue, TP-Link Kasa, Shelly, Sonoff, Aqara,
Tuya Smart, Samsung SmartThings, Google Home, Amazon Alexa, Apple
HomeKit, Ring, Arlo, Eufy, Xiaomi, Bosch Smart Home), each committed to
requiring no core architecture change — the same commitment pattern
M11 already established for its own provider list. Dependencies were
updated to M5, M5A, M7, M9, M10, and M14; Complexity was upgraded from
L to XL to honestly reflect the larger scope; Acceptance criteria grew
from 3 functional checks to 10 (the original 3 kept, 7 new
architecture-documentation checks added). §10's feature backlog
gained 15 new module-level rows alongside the pre-existing granular
rows, kept for continuity. Still planning only — no implementation, no
milestone renumbering or reordering, no completed milestone (§3)
altered, and M12's own pre-redesign history is preserved in this
changelog rather than erased.

*Jul 2026 addendum 4:* redesigned **M13 — Computer Control** into
**M13 — Desktop Intelligence & Computer Control Platform**, transforming
it from a "hands and eyes" feature list into a complete desktop
operating-assistant platform, mirroring the depth of M11's Google
Workspace module and M12's Smart Home & IoT Platform. The flat
feature list was replaced with 10 structured modules: Desktop
Control, UI Intelligence, Desktop Vision, Application Intelligence,
Workflow Execution, AI Desktop Assistant, Desktop Memory, Safety &
Permissions, Performance & Reliability, and Developer Tools.
Architecture notes were expanded with ten binding constraints —
provider-based desktop interaction, multi-framework UI automation,
Accessibility-APIs-preferred/vision-as-fallback ordering, Event Bus
integration, AI Sandbox compatibility, `PermissionGate`-routed human
approval, Long-Term Memory and Knowledge Graph integration, and
architecture-level cross-platform extensibility. A new **Supported
frameworks** list named 10 planned adapter targets (Windows UI
Automation, Win32, WPF, WinUI, UWP, Electron, Chromium-based, Qt,
Java, and Accessibility APIs generally) without committing to any
architecture change to add them. Dependencies were updated to M5,
M5A, M6, M7, M9, M10, M13A, and M14 (M13/M13A's relationship is
documented as a built-alongside pairing, not a strict one-way
dependency, consistent with how §16 already sequences them);
Complexity was upgraded from L to XL to honestly reflect the larger
scope, matching M12's own L→XL upgrade; Acceptance criteria grew from
3 functional checks to 13 (the original 3 kept, 10 new
architecture-documentation checks added, including an explicit
internal-consistency check). §10's feature backlog gained a new
"Desktop Intelligence & Computer Control Platform" table with 10
module-level rows, alongside the pre-existing "Autonomous
mouse/keyboard" row kept for continuity. Still planning only — no
implementation, no milestone renumbering or reordering, no completed
milestone (§3) altered, and M13's own pre-redesign history is
preserved in this changelog rather than erased.

*Jul 2026 addendum 5:* redesigned **M14 — Security Platform** from a
single feature list into the **central, cross-cutting security
architecture for every subsystem in JARVIS OS**, mirroring the depth
of M11's Google Workspace module, M12's Smart Home & IoT Platform, and
M13's Desktop Intelligence platform. The flat feature list was
replaced with 12 structured modules: Security Core, Identity &
Authentication, Authorization & Permissions, Secrets Management, Data
Protection, Network Security, AI Security, Smart Home Security,
Monitoring & Auditing, Incident Response, Privacy, and Developer
Security Tools. Architecture notes were expanded with ten binding
constraints, the first and most important being that security is
explicitly a *shared platform* every other milestone (M6, M7, M9,
M10, M11, M12, M13, M13A, M5A) consumes rather than reimplements — the
other nine notes (Event Bus integration, universal permission
validation, no-plaintext-secrets, provider-independent encryption,
least-privilege AI agents, `PermissionGate`-routed human approval,
sandbox-wrapped plugin execution, Analytics-integrated audit logs, and
distributed-deployment readiness) all exist to enforce it. A Future
Expansion list named 10 planned identity/authentication targets (TPM,
Hardware Security Modules, FIDO2, Passkeys, Smart Cards, Enterprise
SSO, Azure AD, LDAP, Active Directory, Remote Device Trust) with the
same "no core architecture change" commitment every other platform
milestone in this roadmap makes. Dependencies were expanded from a
single M8 reference to M5, M5A, M7, M8, M9, M10, M11, M12, M13, and
M13A (M8 kept from the original scope, not dropped, since the
Permission System module still explicitly unifies with it);
Complexity was upgraded from M to XL to honestly reflect the platform
becomes the security foundation for nine other milestones, not a
single feature; Acceptance criteria grew from 3 functional checks to
15 (the original 3 kept, 12 new architecture-documentation checks
added, including an explicit internal-consistency check). §10's
feature backlog gained a new "Security Platform (M14 modules)" table
with 12 module-level rows, alongside the pre-existing granular rows
kept for continuity. Still planning only — no implementation, no
milestone renumbering or reordering, no completed milestone (§3)
altered, and M14's own pre-redesign history is preserved in this
changelog rather than erased.

*Jul 2026 addendum 6:* redesigned **M15 — Personality Engine** from a
single configurable-personality feature into a **complete
enterprise-grade Personality Engine** — a modular framework for
multiple personalities, adaptive behavior, emotional intelligence, and
long-term relationship building, not a single hard-coded personality —
mirroring the depth of M11's Google Workspace module, M12's Smart
Home & IoT Platform, M13's Desktop Intelligence platform, and M14's
Security Platform. The flat feature list was replaced with 10
structured modules: Personality Core, Conversation Engine,
Relationship Intelligence, Adaptive Behaviour, Emotional Intelligence,
Voice Personality, Persona Management, Proactive Intelligence, Ethics
& Safety, and Developer Tools. Architecture notes were expanded with
ten binding constraints, most notably that emotional intelligence must
remain assistive, never manipulative, and that persona switching
(Work/Personal/Guest mode) must always preserve whichever M14 security
policy is active rather than persona-switching becoming a permission
side-channel. A Future Expansion list named 10 planned extensions
(Multilingual Personalities, Cultural Adaptation, Team Personas,
Family Profiles, Voice Cloning Interfaces, a Personality Marketplace,
Custom Persona Packs, Enterprise Personas, an AI Character Framework,
Community Personality Templates) with the same "no core architecture
change" commitment every other platform milestone in this roadmap
makes. Dependencies were expanded from M10 + M1 to M1, M3, M5A, M6,
M7, M10, M11, M12, M13, and M14 (M1 kept from the original scope, not
dropped, since personality still compiles down to the existing
`UISettings.system_prompt` mechanism); Complexity was upgraded from M
to XL, with an explicit rationale distinguishing "a tone/style dial"
(the original scope) from "a cross-cutting behavioral platform every
other user-facing milestone expresses itself through" (the redesigned
scope) — consistent with the M12/M13/M14 XL precedent. Acceptance
criteria grew from 3 functional checks to 15 (the original 3 kept, 12
new architecture-documentation checks added, including explicit
internal-consistency and roadmap-formatting checks). §10's feature
backlog gained a new "Personality Engine (M15 Modules)" table with 10
module-level rows, alongside the pre-existing granular rows kept for
continuity. Still planning only — no implementation, no milestone
renumbering or reordering, no completed milestone (§3) altered, and
M15's own pre-redesign history is preserved in this changelog rather
than erased.

*Jul 2026 addendum 7:* merged multilingual conversation capabilities
directly into M15's **Conversation Engine module, renamed
"Conversation & Language Intelligence."** Deliberately **not** a
separate "Hindi Module," "Marathi Module," or standalone "Language
Module" — language is part of *how* JARVIS communicates, so it lives
inside the existing Conversation Engine rather than as a new,
eleventh module. The module was restructured into three labeled
groups — **Conversation** (natural conversations, multi-turn dialogue,
active listening, clarification handling, conversation summaries — all
existing features preserved, three new), **Communication Style** (tone
adaptation, formal/casual/friendly/professional modes, humor — all
existing features preserved, one new: adaptive speaking style), and
**Multilingual Intelligence** (new: English, Hindi, Marathi, Hinglish,
and Marathi-English mixed conversation support, automatic language
detection and response matching, user-preferred and temporary language
switching, conversation and long-term language memory, regional accent
understanding, script transliteration, translation support, offline
language packs). Documented explicit **conversation behaviour rules**
for explicit language commands ("Speak in Hindi/Marathi/English")
versus natural-language auto-detection versus mixed-language (Hinglish/
Marathi-English) continuity. Established the module's single most
important invariant: **language changes only how JARVIS communicates,
never what it knows, decides, reasons about, or is willing to do** —
Personality, Behaviour, Emotional Intelligence, Reasoning, Decision
Making, Long-Term Memory, Knowledge, Safety Policies, Workflow
Capabilities, Smart Home Behaviour, Desktop Behaviour, and Productivity
Features all stay identical across every supported language. Added
eight new Architecture notes covering provider-independent Speech
Recognition/Translation/Text-Generation, multi-language voice
providers, detect-before-generate ordering, the personality-invariant
constraint, semantic (not language-locked) Long-Term Memory storage,
automatic language inheritance across every other module (Voice,
Vision, Desktop, Smart Home, Automation, Productivity), and
core-architecture-free new-language installability. Added a new
**Future language expansion** note naming 14 planned languages
(Gujarati, Tamil, Telugu, Kannada, Malayalam, Bengali, Punjabi, Urdu,
Spanish, French, German, Japanese, Korean, Arabic) alongside the
existing Future expansion note (kept unchanged, covering personality/
persona extensions rather than languages). §10's feature backlog
gained 10 new traceable rows (Automatic Language Detection, English/
Hindi/Marathi/Hinglish/Marathi-English Conversation, Language Memory,
Dynamic Language Switching, Offline Language Packs, Plugin-Based
Language Framework) alongside the renamed, expanded Conversation
Engine row; all pre-existing backlog entries preserved for continuity.
Acceptance criteria were **not** modified this pass — out of the
explicitly requested scope. Still planning only — no implementation,
no milestone renumbering or reordering, no completed milestone (§3)
altered, and M15's prior addendum (addendum 6) is preserved in this
changelog rather than erased.

*Jul 2026 addendum 8:* redesigned **M16 — Reflection Engine** from a
single learning-feedback feature into a **complete enterprise-grade
Reflection Engine** — an internal intelligence layer that analyzes
past conversations, workflows, decisions, and long-term patterns to
continuously improve future assistance, working *alongside* M3
Memory, M15 Personality, M10 Knowledge, M20A Analytics, and M5A Agent
Runtime rather than in place of any of them — mirroring the depth of
M11's Google Workspace module, M12's Smart Home & IoT Platform, M13's
Desktop Intelligence platform, M14's Security Platform, and M15's
Personality Engine. The flat feature list was replaced with 10
structured modules: Reflection Core, Conversation Reflection, Workflow
Reflection, Knowledge Reflection, Behaviour Reflection, Learning &
Improvement, Goal Reflection, Reflection Analytics, Safety &
Governance, and Developer Reflection Tools. Architecture notes were
expanded with ten binding constraints, the two most important being
that Reflection reads M3/M10A through their existing interfaces without
maintaining a parallel data copy, and that Reflection generates
recommendations rather than silently changing behaviour, memory,
personality, or security policy — every module's description was
written to make that "observe and recommend, never silently mutate"
boundary explicit rather than implicit. A Future Expansion list named
10 planned extensions (Daily/Weekly/Monthly Reflection, Goal Coaching,
Team Reflection, Shared Reflection, an AI Research Assistant, Personal
Growth Insights, Reflection Plugins, Enterprise Reflection Reports)
with the same "no core architecture change" commitment every other
platform milestone in this roadmap makes. Dependencies were expanded
from M10 + M3 to M3, M5A, M7, M10, M14, M15, and M20A (M3 and M10 kept
from the original scope, not dropped); Complexity was upgraded from M
to XL, with an explicit rationale distinguishing "a feedback loop that
changes future behavior" (the original scope) from "a cross-cutting
intelligence platform observing five other milestones' own data and
decisions while remaining strictly non-mutating and fully explainable"
(the redesigned scope) — consistent with the M12/M13/M14/M15 XL
precedent. Acceptance criteria grew from 3 functional checks to 16
(the original 3 kept, 13 new architecture-documentation checks added,
including explicit internal-consistency and roadmap-formatting
checks). §10's feature backlog gained a new "Reflection Engine (M16
Modules)" table with 10 module-level rows, alongside the pre-existing
granular rows kept for continuity (the shared legacy-note above the
Personality/Reflection tables was updated to reference both
redesigns). Still planning only — no implementation, no milestone
renumbering or reordering, no completed milestone (§3) altered, and
M16's own pre-redesign history is preserved in this changelog rather
than erased.

*Jul 2026 addendum 9:* redesigned **M17 — Companion Intelligence**
from a proactive-suggestions feature into a **complete
enterprise-grade Companion Intelligence platform** defining how JARVIS
builds long-term, personalized, trustworthy interaction while
respecting privacy, autonomy, and security — mirroring the depth of
M11's Google Workspace module, M12's Smart Home & IoT Platform, M13's
Desktop Intelligence platform, M14's Security Platform, M15's
Personality Engine, and M16's Reflection Engine. The flat feature list
was replaced with 10 structured modules: Companion Core, Relationship
Intelligence, Daily Companion, Personalization Engine, Proactive
Intelligence, Social & Communication Intelligence, Wellbeing Support,
Memory & Continuity, Safety & Boundaries, and Developer Companion
Tools. The Objective and every module description were written to
make explicit that **this milestone extends M15 Personality Engine and
M16 Reflection Engine rather than replacing either** — M15 stays the
source of truth for identity/tone, M16 stays the source of truth for
learned patterns, M17 is the long-term, relationship-and-proactive
application of both. Architecture notes were expanded with ten binding
constraints, most notably that Companion Intelligence must never
manipulate users, personalization must remain reversible, relationship
intelligence must be based on explicit interactions rather than
assumptions, and Security/Privacy policy (M14) always takes precedence
over any companion behavior. A Future Expansion list named 10 planned
extensions (Family/Team Companion Profiles, Multi-User Households,
Shared Memories, Collaborative Planning, Travel/Health/Education/
Vehicle Companions, Plugin-Based Companion Skills) with the same "no
core architecture change" commitment every other platform milestone in
this roadmap makes. Dependencies were expanded from M10 + M15 + M16 to
M3, M5A, M7, M10, M11, M12, M13, M14, M15, and M16 (M10/M15/M16 kept
from the original scope); Complexity was upgraded from L to XL, with
an explicit rationale distinguishing "surface a proactive suggestion"
(the original scope) from "a full relationship-continuity and
personalization platform every other user-facing milestone expresses
itself through" (the redesigned scope) — consistent with the
M12/M13/M14/M15/M16 XL precedent. Acceptance criteria grew from 3
functional checks to 15 (the original 3 kept, 12 new
architecture-documentation checks added). §10's feature backlog gained
a new "Companion Intelligence (M17 Modules)" table with 10
module-level rows, alongside the pre-existing granular rows kept for
continuity (the shared legacy-note above the Personality/Reflection/
Companion tables was updated to reference all three redesigns). Still
planning only — no implementation, no milestone renumbering or
reordering, no completed milestone (§3) altered, and M17's own
pre-redesign history is preserved in this changelog rather than
erased.

*Jul 2026 addendum 10:* redesigned **M18 — Diagnostics** into **M18 —
Self-Healing & Diagnostics Platform**, a complete enterprise-grade
platform responsible for monitoring JARVIS's health, detecting
failures, recovering from faults, diagnosing issues, and maintaining
long-term reliability — mirroring the depth of M11's Google Workspace
module, M12's Smart Home & IoT Platform, M13's Desktop Intelligence
platform, M14's Security Platform, M15's Personality Engine, M16's
Reflection Engine, and M17's Companion Intelligence platform. The flat
feature list was replaced with 10 structured modules: Health
Monitoring Core, Diagnostics Engine, Self-Healing Engine, Predictive
Reliability, Recovery Management, Performance Optimization, Security
Diagnostics, AI Diagnostics, Developer Diagnostics Tools, and
Reporting & Analytics. The Objective was written to make explicit that
**self-healing must never modify user data, memories, personality, or
security policy without explicit authorization** — this platform
repairs JARVIS's own runtime, never the user's data or JARVIS's
identity/policies, without consent. Architecture notes were expanded
with ten binding constraints, most notably that automatic recovery
must respect M14 Security Platform policy and be fully auditable, and
that **M16 Reflection Engine may recommend improvements but never
performs repairs itself** — repair action always belongs to this
milestone's Self-Healing Engine, preserving the "recommend, never
silently change" boundary M16 already established. A Future Expansion
list named 10 planned extensions (Distributed Diagnostics, Multi-
Device/Cloud Health Monitoring, Predictive Maintenance AI, Enterprise
Monitoring, Fleet Management, Automated Incident Reports, Remote
Diagnostics, a Plugin Health Marketplace, Self-Healing Extensions)
with the same "no core architecture change" commitment every other
platform milestone in this roadmap makes. Dependencies were expanded
from M5.5 + M14 to M5, M5.5, M5A, M7, M10, M13, M14, M16, M17, and
M20A (M5.5 and M14 kept from the original scope); Complexity was
upgraded from M to XL, with an explicit rationale distinguishing "tell
you when something's wrong" (the original scope) from "a cross-cutting
platform supporting every subsystem" (the redesigned scope) —
consistent with the M12/M13/M14/M15/M16/M17 XL precedent. Acceptance
criteria grew from 3 functional checks to 16 (the original 3 kept, 13
new architecture-documentation checks added). §10's feature backlog
gained a new "Self-Healing & Diagnostics (M18 Modules)" table with 10
module-level rows, alongside the pre-existing granular rows kept for
continuity. M18's display name was also updated in §14's Version
Timeline and §16's Recommended Development Order tables to keep those
live cross-references consistent with the redesign (M12/M13's own
similarly-stale display names in those same tables were left
untouched, being pre-existing and outside this pass's explicit scope).
Still planning only — no implementation, no milestone renumbering or
reordering, no completed milestone (§3) altered, and M18's own
pre-redesign history is preserved in this changelog rather than
erased.

*Jul 2026 addendum 11:* redesigned **M19 — Intelligence Graph** into
**M19 — Knowledge Graph & Digital Twin Platform**, a complete
enterprise-grade platform connecting every entity, memory, workflow,
device, application, document, project, person, automation, and
relationship into a continuously evolving knowledge graph — the
central reasoning layer for every future milestone, with the Digital
Twin as a live semantic model of the user's digital ecosystem. The
flat feature list was replaced with 10 structured modules: Knowledge
Graph Core, Digital Twin, Entity Intelligence, Relationship
Intelligence, Context Engine, Semantic Search, Timeline Intelligence,
Knowledge Reasoning, Knowledge Analytics, and Developer Graph Tools.
Architecture notes were expanded with ten binding constraints, most
notably that **Long-Term Memory (M3) stores experiences while the
Knowledge Graph organizes and connects them** — the graph never
duplicates raw memory content, only structures references to it — and
that the Digital Twin is a semantic representation of the user's
ecosystem, never a duplicate of raw data. A Future Expansion list
named 10 planned extensions (Personal Knowledge Bases, Enterprise
Knowledge Graphs, Multi-User Graphs, Shared Digital Twins, Cross-
Device Knowledge Synchronization, an AI Planning Engine, Autonomous
Reasoning, Knowledge Plugins, Graph APIs, Third-Party Knowledge
Connectors), each requiring no change to the core architecture, per
this roadmap's established platform-milestone pattern. Dependencies
were expanded from {M10, M16, M17} to M3, M5A, M6, M7, M9, M10, M11,
M12, M13, M14, M15, M16, M17, and M18 (M10, M16, M17 kept from the
original scope) — reflecting that the graph is fed by, and feeds,
nearly every other subsystem in this roadmap. Complexity remains XL,
now with an explicit rationale documenting *why*: the Knowledge Graph
is the central intelligence platform connecting every other
subsystem, not a standalone feature, consistent with the XL tier
already used for M14 Security Platform and M18 Self-Healing &
Diagnostics Platform. Acceptance criteria grew from 3 functional
checks to 16 (the original 3 kept, 13 new architecture-documentation
checks added). §10's feature backlog gained a new "Knowledge Graph &
Digital Twin Platform (M19 Modules)" table with 10 module-level rows,
alongside the pre-existing Knowledge Graph / Relationship Graph /
Digital Twin rows kept for continuity under an explanatory note. M19's
display name was also updated in §14's Version Timeline and §16's
Recommended Development Order tables to keep those live cross-
references consistent with the redesign; references to M19 by its old
"Intelligence Graph" name embedded in other milestones' own prose
(M10's Digital Twin Foundation note, M11's Google Workspace module,
M12's complexity rationale, M14's Data Privacy module, M20's
Objective/Dependencies) were left untouched, being pre-existing cross-
references outside this pass's explicit scope — consistent with the
M12/M13 precedent set during the M18 turn. Still planning only — no
implementation, no milestone renumbering or reordering, no completed
milestone (§3) altered, and M19's own pre-redesign history is
preserved in this changelog rather than erased.

*Jul 2026 addendum 12:* redesigned **M20 — Predictive Intelligence**
into **M20 — Predictive Intelligence Platform**, a complete
enterprise-grade platform enabling JARVIS to anticipate future needs,
identify opportunities, forecast outcomes, recommend actions, and
optimize long-term decision making on top of the M19 Knowledge Graph &
Digital Twin Platform. The flat feature list was replaced with 10
structured modules: Prediction Core, Behaviour Prediction, Opportunity
Intelligence, Risk Intelligence, Planning Intelligence, Recommendation
Engine, Simulation Engine, Predictive Analytics, Governance & Safety,
and Developer Prediction Tools. Architecture notes were expanded with
ten binding constraints, most notably that **predictions must never
silently execute actions** and that **M16 Reflection analyzes the
past while M20 Prediction estimates future outcomes** — the two remain
distinct, complementary subsystems rather than a single blended one,
mirroring the "recommend vs. repair" boundary already drawn between
M16 and M18. A Future Expansion list named 10 planned extensions
(Autonomous Planning, Enterprise Forecasting, Team Prediction, an AI
Strategy Engine, Financial Forecasting, Project Portfolio Forecasting,
Digital Twin Simulation, Predictive Plugins, External Forecast APIs,
Research Planning), each requiring no change to the core architecture,
per this roadmap's established platform-milestone pattern. Dependencies
were expanded from {M19, M16} to M3, M5A, M7, M10, M11, M12, M13, M14,
M15, M16, M17, M18, and M19 (M19 and M16 kept from the original
scope) — reflecting that prediction reads from nearly every other
subsystem in this roadmap. Complexity was upgraded from L to **XL**,
with an explicit rationale documenting *why*: Predictive Intelligence
is a cross-cutting decision-support platform touching nearly every
other subsystem, not a standalone forecasting feature, consistent with
the XL tier already used for M14, M18, and M19. Acceptance criteria
grew from 3 functional checks to 16 (the original 3 kept, 13 new
architecture-documentation checks added). §10's feature backlog gained
a new "Predictive Intelligence Platform (M20 Modules)" table with 10
module-level rows, alongside the pre-existing Intent
Prediction/Recommendation Engine/Decision Support rows kept for
continuity under an explanatory note now covering all four of
M15/M16/M17/M20's redesigns. M20's display name was also updated in
§14's Version Timeline and §16's Recommended Development Order tables
to keep those live cross-references consistent with the redesign;
references to M20 by its shorter pre-redesign name embedded in other
milestones' own prose (M17's proactive-suggestions note, M19's
Knowledge Reasoning architecture note, M20A's own future scope) were
left untouched, being pre-existing cross-references outside this
pass's explicit scope — consistent with the M12/M13/M19 precedent set
during the M18 and M19 turns. Still planning only — no implementation,
no milestone renumbering or reordering, no completed milestone (§3)
altered, and M20's own pre-redesign history is preserved in this
changelog rather than erased.

*Jul 2026 addendum 13:* redesigned **M20A — Analytics Platform** into
**M20A — Analytics & Observability Platform**, a complete
enterprise-grade platform providing centralized visibility into every
subsystem of JARVIS OS through metrics, events, logs, traces,
dashboards, reports, and operational insights. The flat feature list
was replaced with 10 structured modules: Observability Core, Event
Analytics, Performance Analytics, AI Analytics, User Experience
Analytics, Dashboard Platform, Alert & Notification Engine, Reporting
Platform, Developer Observability Tools, and Analytics API.
Architecture notes were expanded with ten binding constraints, most
notably that **analytics data should support M16 Reflection Engine,
M20 Predictive Intelligence Platform, and M18 Self-Healing &
Diagnostics Platform without creating circular dependencies** — this
milestone publishes data those milestones read, it never itself
depends on their outputs to operate — and that the platform exists for
**system health, transparency, and optimization, never advertising or
user profiling**. A Future Expansion list named 10 planned extensions
(Distributed Analytics, Enterprise Dashboards, Fleet Analytics, AI
Performance Benchmarking, Capacity Planning, Business Intelligence
Connectors, OpenTelemetry Integration, Custom Analytics Plugins,
Cross-Device Observability, a Predictive Operations Center), each
requiring no change to the core architecture, per this roadmap's
established platform-milestone pattern. Dependencies were expanded
from {M5A, M9, M18} to M5, M5A, M7, M9, M10, M11, M12, M13, M14, M16,
M18, M19, and M20 (M5A, M9, and M18 kept from the original scope) —
reflecting that observability collects from, and feeds, nearly every
other subsystem in this roadmap. Complexity was upgraded from M to
**XL**, with an explicit rationale documenting *why*: Analytics &
Observability is a cross-cutting operational platform supporting every
other subsystem, not an isolated reporting feature, consistent with
the XL tier already used for M14, M18, M19, and M20. Acceptance
criteria grew from 3 functional checks to 15 (the original 3 kept, 12
new architecture-documentation checks added). §10's feature backlog
gained a new "Analytics & Observability Platform (M20A Modules)"
table with 10 module-level rows, inserted immediately after the M18
Self-Healing & Diagnostics module table; the shared "Backup,
Diagnostics & Analytics" legacy note above both tables was updated to
reference both redesigns. M20A's display name was also updated in
§14's Version Timeline and §16's Recommended Development Order tables
to keep those live cross-references consistent with the redesign;
references to M20A by its shorter pre-redesign name embedded in other
milestones' own prose (M18's Performance Optimization note, M19's
Knowledge Analytics module) were left untouched, being pre-existing
cross-references outside this pass's explicit scope — consistent with
the M12/M13/M19/M20 precedent set during the M18, M19, and M20 turns.
Still planning only — no implementation, no milestone renumbering or
reordering, no completed milestone (§3) altered, and M20A's own
pre-redesign history is preserved in this changelog rather than
erased.

*Jul 2026 addendum 14:* redesigned **M21 — Mobile Platform** (a
6-feature multi-device presence milestone) into a complete
enterprise-grade Mobile Platform, keeping the same milestone name. The
flat feature list was replaced with 10 structured modules: Mobile
Platform Core, Mobile Companion, Remote Control Platform, Mobile
Intelligence, Secure Access Platform, Synchronization Platform, Mobile
Notifications, Mobile Analytics, Developer Mobile Tools, and Mobile
SDK & APIs. Architecture notes were expanded with ten binding
constraints, most notably that **the desktop remains the primary
execution environment and mobile acts as a secure companion rather
than replacing it**, and that the Knowledge Graph synchronizes
semantic data rather than duplicating raw storage. The original
milestone's pre-redesign framing note ("Absorbs the previously-planned
'Mobile companion' + 'Wearable integration' scope — see §9") was kept
verbatim above the new redesign note, preserving both layers of
history. A Future Expansion list named 10 planned extensions (Wear OS,
Apple Watch, Android Auto, Apple CarPlay, Tablet Mode, Foldable
Devices, Mobile Widgets, Offline AI, Satellite Messaging, Cross-Device
Handoff) — the original milestone's own Wearable integration bullet
now lives here as future scope rather than shipped-with-M21 scope, a
thin extension of the new Mobile SDK & APIs module rather than a
separate platform. Dependencies were expanded from {M9, M14} to M5,
M5A, M6, M7, M9, M10, M11, M12, M13, M14, M15, M16, M17, M18, M19,
M20, and M20A (M9 and M14 kept from the original scope) — reflecting
that the mobile companion surfaces nearly every other subsystem in
this roadmap. Complexity remains XL, now with an explicit rationale
documenting *why*: the Mobile Platform is a complete companion
ecosystem — platform core, companion UX, remote control, mobile
intelligence, secure access, sync, notifications, analytics, developer
tooling, and an SDK — not a standalone mobile application. Acceptance
criteria grew from 3 functional checks to 16 (the original 3 kept, 13
new architecture-documentation checks added). §10's feature backlog
gained a new "Mobile Platform (M21 Modules)" table with 10 module-level
rows, alongside the pre-existing Mobile companion / Wearable
integration rows kept for continuity under an explanatory note in the
"Cloud / Mobile / Distributed" section (the M22 Edge AI and M23
Distributed JARVIS rows in that same shared table were left untouched,
being pre-existing and outside this pass's explicit scope). M21's
display name in §14's Version Timeline and §16's Recommended
Development Order was already "Mobile Platform" and required no
change. Still planning only — no implementation, no milestone
renumbering or reordering, no completed milestone (§3) altered, and
M21's own pre-redesign history is preserved in this changelog rather
than erased.

*Jul 2026 addendum 15:* redesigned **M22 — Edge AI Platform** (a
6-feature local/offline hardware milestone extending the existing
Ollama local-first story to real edge deployment) into a complete
enterprise-grade platform, keeping the same milestone name. The flat
feature list was replaced with 10 structured modules: Edge AI Core,
Model Management, Inference Engine, Hardware Acceleration, Hybrid AI
Execution, AI Resource Management, Privacy & Security, Edge AI
Analytics, Developer Edge Tools, and Edge AI SDK & APIs. Architecture
notes were expanded with ten binding constraints, most notably that
**local execution is preferred whenever practical, with cloud
execution remaining optional and policy-driven**, and that **Edge AI
integrates with Security, Analytics, Knowledge Graph, and Prediction
without creating circular dependencies** — this milestone publishes
runtime data those milestones read, it does not depend on their
outputs to execute inference. A Future Expansion list named 10 planned
extensions (On-device fine-tuning, Federated Learning, Quantized
Models, Multi-GPU Execution, Edge AI Clusters, AI Accelerator Cards,
Dynamic Model Loading, a Model Marketplace, Edge AI Containers,
Autonomous AI Optimization), each requiring no change to the core
architecture, per this roadmap's established platform-milestone
pattern. Dependencies were expanded from {M1} to M1, M5, M5A, M6, M9,
M10, M13, M14, M18, M19, M20, M20A, and M21 (M1's Ollama provider
foundation kept from the original scope) — reflecting that the edge
runtime now integrates with nearly every other subsystem in this
roadmap. Complexity was upgraded from L to **XL**, with an explicit
rationale documenting *why*: the Edge AI Platform is a foundational
runtime layer supporting all local AI execution, not a standalone
inference feature, consistent with the XL tier already used for M14,
M20A, and M21. Acceptance criteria grew from 3 functional checks to 16
(the original 3 kept, 13 new architecture-documentation checks added).
§10's feature backlog gained a new "Edge AI Platform (M22 Modules)"
table with 10 module-level rows, inserted immediately after the M21
Mobile Platform module table; the shared "Cloud / Mobile / Distributed"
legacy note above both tables was updated to reference both redesigns
(the M23 Distributed JARVIS rows in that same shared table were left
untouched, being pre-existing and outside this pass's explicit scope).
M22's display name in §14's Version Timeline and §16's Recommended
Development Order was already "Edge AI Platform" and required no
change. Still planning only — no implementation, no milestone
renumbering or reordering, no completed milestone (§3) altered, and
M22's own pre-redesign history is preserved in this changelog rather
than erased.

*Jul 2026 — Addendum 16:* added **M23A — Robotics & Hardware Control
Platform** as a brand-new companion milestone alongside M23 — not a
redesign of any existing milestone. This request initially described
its content as an expansion of "M23," but this document's actual M23
is, and remains, **Distributed JARVIS** (distributed agents, E2EE
multi-device sync, shared memory, remote execution, enterprise
collaboration) — untouched, unrenamed, and unrenumbered. Per explicit
user direction, the robotics/hardware-control content was instead
added as a new lettered companion milestone, `M23A`, following this
roadmap's existing `M<n><letter>` convention for companion/expansion
milestones (`M11A`, `M13A`, `M14A`, `M17A`, `M20A`). M23A expanded a
modular enterprise architecture with ten subsystem modules — Hardware
Abstraction Layer, Communication Interfaces, IoT Connectivity, Sensor
Framework, Actuator Framework, Robotics Runtime, Device Automation
Engine, Hardware Security, Hardware Analytics, and Robotics SDK &
APIs — establishing the unified hardware abstraction layer for the
entire JARVIS ecosystem: ESP32, Arduino, Raspberry Pi, USB/Bluetooth/
BLE/Wi-Fi devices, GPIO, Matter/Zigbee/Z-Wave/MQTT, CAN bus, robotics,
and industrial controllers, with future humanoid-robot compatibility
as an explicit architecture goal. Ten architecture notes were
documented, most notably that **M23A publishes hardware capabilities,
sensor data, and device telemetry for M12, M18, M19, M20A, and M21 to
consume, without depending on their outputs to operate** — avoiding
circular dependencies — and that safety-first design (emergency stop,
safety limits on every actuator action) is binding, not optional. A
Future Expansion list named 12 planned extensions (ROS2 Integration,
Industrial PLC Support, Robot Arms, Autonomous Drones, Smart Vehicle
APIs, Edge Robotics AI, Warehouse/Agricultural/Medical/Humanoid
Robotics, Autonomous Charging Stations, Digital Twin Support), each
requiring no change to the core architecture. Dependencies were set to
M1, M5, M5A, M6, M7, M9, M10, M13, M14, M18, M19, M20, M20A, M21, and
M22. Complexity was classified **XL**, with an explicit rationale: the
foundational platform responsible for every interaction between JARVIS
and physical hardware, underneath M12 Smart Home & IoT Platform and
every future physical-device milestone. Acceptance criteria total 17
(covering device discovery, driver loading, sensor operation, actuator
control, Smart Home integration, robot control, offline operation,
diagnostics, security, OTA updates, automation, analytics, performance,
safety, SDK functionality, and cross-platform compatibility). §10's
feature backlog gained a new "Robotics & Hardware Control Platform
(M23A Modules)" table with 10 module-level rows, inserted immediately
after the M22 Edge AI Platform module table, with its own note
clarifying that no legacy rows predate M23A and that the full legacy
roadmap milestone list — including M23 — Distributed JARVIS's own
rows — is preserved unchanged. §2's companion-milestone naming note
and §8's future-roadmap intro were both updated to list `M23A`
alongside the other lettered companions, with an explicit callout that
M23A is the one companion in this roadmap that is *not* a narrow
extension of its numeric parent's own scope. §14's Version Timeline
gained a new `0.28 | M23A` row between M23 (`0.27`) and M24 (`1.0`,
unchanged); §16's Recommended Development Order gained a new `18A`
row alongside M23's `18`, scheduled in parallel rather than dependent
on it. Milestone numbering, ordering, and every completed milestone
(§3) remain untouched; M23 — Distributed JARVIS's own history is
preserved verbatim and unrenamed throughout.

*Jul 2026 — Addendum 17:* added **M23B — Autonomous Planning &
Decision Engine** as a brand-new companion milestone immediately
before M24 — not a redesign of any existing milestone. This request
initially described its content as an expansion of "M24," but this
document's actual M24 is, and remains, **Production Release** — the
dedicated `v1.0.0` wrap-up milestone — untouched, unrenamed, and
unrenumbered. Per explicit user direction, the autonomous-planning
content was instead added as a new lettered companion milestone,
`M23B`, following this roadmap's existing `M<n><letter>` convention
and placed directly after `M23A` (`M22 → M23 → M23A → M23B → M24`).
M23B expanded a modular enterprise architecture with ten subsystem
modules — Goal Management, Task Planning, Decision Engine, Autonomous
Execution, Resource Planner, Multi-Agent Orchestration, Predictive
Intelligence, Safety & Governance, Planning Analytics, and Planning
SDK & APIs — establishing M23B as the central reasoning and execution
planner for JARVIS: deciding what to do, when to do it, which AI agent
performs it, which device executes it, whether execution is local or
cloud, and how to recover from failures, all by orchestrating existing
subsystems rather than replacing them. Ten architecture notes were
documented, most notably that **M23B consumes services from M1, M5,
M5A, M6, M9, M10, M13, M14, M18, M19, M20, M20A, M21, M22, M23, and
M23A, and in turn publishes planning services for future milestones to
consume, without requiring any milestone built after it to operate** —
avoiding circular dependencies — and that safe autonomous execution
(rollback, checkpoints, a kill switch) is binding, never optional. A
Future Expansion list named 12 planned extensions (long-term autonomous
missions, AI project management, strategic planning, autonomous
business workflows, AI negotiation, economic optimization, multi-week
planning, team collaboration planning, enterprise workflow
orchestration, self-improving planning, autonomous research planning,
cognitive architecture integration), each requiring no change to the
core architecture. Dependencies were set to M1, M5, M5A, M6, M9, M10,
M13, M14, M18, M19, M20, M20A, M21, M22, M23, and M23A. Complexity was
classified **XL**, with an explicit rationale: the cognitive planning
layer responsible for coordinating every intelligent subsystem inside
JARVIS. Acceptance criteria total 20 (covering goal management, task
planning, decision making, multi-agent coordination, safe execution,
rollback, recovery, resource planning, predictive intelligence,
analytics, SDK functionality, API stability, performance,
explainability, governance, offline planning, distributed execution,
and cross-platform compatibility). §10's feature backlog gained a new
"Autonomous Planning & Decision Engine (M23B Modules)" table with 10
module-level rows, inserted immediately after the M23A module table,
with its own note clarifying that no legacy rows predate M23B and that
M24 — Production Release's own content remains preserved unchanged.
§2's companion-milestone naming note and §8's future-roadmap intro
were both updated to list `M23B` alongside the other lettered
companions, with an explicit callout (alongside M23A's existing one)
that M23B is not a narrow extension of a single numeric parent's own
scope. §14's Version Timeline gained a new `0.29 | M23B` row between
M23A (`0.28`) and M24 (`1.0`, unchanged); §16's Recommended Development
Order gained a new `18B` row between M23A's `18A` and M24's `19`.
Milestone numbering, ordering, and every completed milestone (§3)
remain untouched; M24 — Production Release's own history is preserved
verbatim and unrenamed throughout.

*Jul 2026 — Addendum 18:* added **M25 — Cognitive Intelligence
Platform** as a brand-new top-level milestone immediately after M24 —
not a redesign, renumbering, or replacement of any existing milestone.
M24 — Production Release remains completely unchanged. M25 expanded a
modular enterprise architecture with ten subsystem modules — Cognitive
Memory, Meta Reasoning, Continuous Learning, Human Preference
Modeling, Emotional Intelligence, Knowledge Evolution, Cognitive
Analytics, Cognitive Safety, Self Improvement Engine, and Cognitive
SDK & APIs — establishing M25 as JARVIS's cognitive architecture:
continuously improving itself, learning from experience, refining
reasoning, adapting to the user, and evolving over time. The milestone
is explicitly distinguished from M23B: **planning decides what to do,
cognition decides how to think** — M25 never executes actions itself,
it hands concrete improvement goals to M23B's Goal Management module
for execution. Ten architecture notes were documented, most notably
that **M25 consumes planning services from M23B and data from fourteen
prior milestones, and in turn publishes cognitive services for all
future intelligence milestones to consume, without requiring any
milestone built after it to operate** — avoiding circular dependencies
— and that safe self-improvement (human override via Cognitive Safety)
is binding, never optional. A Future Expansion list named 12 planned
extensions (lifelong learning, autonomous research, creative
reasoning, scientific discovery, AI tutoring, team cognition, swarm
intelligence, cross-device cognition, cognitive simulation, AGI
preparation, self-directed improvement, collective intelligence), each
requiring no change to the core architecture. Dependencies were set to
M1, M5, M5A, M6, M9, M10, M13, M14, M18, M19, M20, M20A, M21, M22,
M23, M23A, M23B, and M24. Complexity was classified **XL**, with an
explicit rationale: the cognitive architecture responsible for
lifelong learning and adaptive intelligence. Acceptance criteria total
20 (covering memory, learning, reflection, preference adaptation,
emotional intelligence, knowledge evolution, analytics, safety,
self-improvement, SDK functionality, API stability, performance,
explainability, privacy, cross-platform compatibility, long-term
learning, human oversight, continuous adaptation, testing, and
documentation). §10's feature backlog gained a new "Cognitive
Intelligence Platform (M25 Modules)" table with 10 module-level rows,
inserted immediately after the Release (M24) table, with its own note
clarifying that no legacy rows predate M25 and that M24's own rows
remain preserved unchanged. §14's Version Timeline gained a new `1.1 |
M25` row between M24 (`1.0`) and the `1.x` post-1.0 placeholder row —
per this document's existing §6 versioning policy, M25 earns a MINOR
version bump rather than an actual `2.0.0` MAJOR bump, since MAJOR
bumps are reserved for `1.0.0` and future breaking API changes;
"Version 2.0" in this milestone's framing is a thematic label for the
start of the post-1.0 era, not a literal semver jump. §16's
Recommended Development Order gained a new `20 | M25` row after M24's
`19`. Milestone numbering, ordering, and every completed milestone
(§3) remain untouched; M24 — Production Release's own history is
preserved verbatim and unmodified throughout.

*Jul 2026 — Addendum 19:* added **M26 — Self-Learning & Autonomous
Evolution Platform** as a brand-new top-level milestone immediately
after M25 — not a redesign, renumbering, or replacement of any
existing milestone. M24 — Production Release and M25 — Cognitive
Intelligence Platform both remain completely unchanged. M26 expanded a
modular enterprise architecture with ten subsystem modules —
Self-Learning Engine, Experience Replay, Skill Acquisition, Knowledge
Refinement, Autonomous Optimization, Feedback Integration, Evolution
Analytics, Learning Governance, Autonomous Improvement Engine, and
Self-Learning SDK & APIs — establishing M26 as the layer responsible
for continuously improving every AI capability in JARVIS through
experience, feedback, optimization, and autonomous evolution. The
three-milestone distinction is now documented explicitly and
verbatim in M26's own Objective: **M23B decides what to do, M25
decides how to think, M26 decides how to improve itself over time** —
M26 never executes actions directly, it hands improvement goals to
M23B's Goal Management module for execution, the same "recommend/plan,
don't act" boundary this roadmap has drawn between reflection and
execution milestones since M16/M18. Ten architecture notes were
documented, most notably that **M26 consumes cognitive services from
M25 and data from fifteen prior milestones, and in turn publishes
self-improvement services for future milestones to consume, without
requiring any milestone built after it to operate** — avoiding
circular dependencies — and that every learning/optimization change is
versioned and rollback-capable via Learning Governance. A Future
Expansion list named 12 planned extensions (federated learning,
cross-device learning, swarm learning, AI mentor systems, autonomous
curriculum generation, scientific learning, self-generated datasets,
synthetic experience generation, evolution simulation, lifelong
autonomous learning, collective intelligence, AGI capability
evolution), each requiring no change to the core architecture.
Dependencies were set to M1, M5, M5A, M6, M9, M10, M13, M14, M18, M19,
M20, M20A, M21, M22, M23, M23A, M23B, M24, and M25. Complexity was
classified **XL**, with an explicit rationale: responsible for
lifelong self-learning and autonomous capability evolution across the
entire JARVIS platform. Acceptance criteria total 20 (covering
continuous learning, experience replay, skill acquisition, knowledge
refinement, optimization, feedback integration, evolution analytics,
governance, autonomous improvement, SDK functionality, API stability,
explainability, privacy, safety, human oversight, performance,
scalability, testing, documentation, and cross-platform
compatibility). §10's feature backlog gained a new "Self-Learning &
Autonomous Evolution Platform (M26 Modules)" table with 10
module-level rows, inserted immediately after the M25 module table,
with its own note clarifying that no legacy rows predate M26 and that
M25's own rows remain preserved unchanged. §14's Version Timeline
gained a new `1.2 | M26` row between M25 (`1.1`) and the `1.x`
post-1.0 placeholder row, continuing the same MINOR-bump policy
established for M25 (§6). §16's Recommended Development Order gained a
new `21 | M26` row after M25's `20`. Milestone numbering, ordering, and
every completed milestone (§3) remain untouched; M24 — Production
Release's and M25 — Cognitive Intelligence Platform's own history is
preserved verbatim and unmodified throughout.

*Jul 2026 — Addendum 20:* added **M27 — World Model & Environmental
Intelligence Platform** as a brand-new top-level milestone immediately
after M26 — not a redesign, renumbering, or replacement of any
existing milestone. M24 — Production Release, M25 — Cognitive
Intelligence Platform, and M26 — Self-Learning & Autonomous Evolution
Platform all remain completely unchanged. M27 expanded a modular
enterprise architecture with ten subsystem modules — World Model Core,
Spatial Intelligence, Object Intelligence, Environmental Awareness,
Human Context Intelligence, Digital World Intelligence, World
Analytics, World Safety, Simulation Engine, and World SDK & APIs —
establishing M27 as the layer responsible for a persistent,
continuously-maintained understanding of the physical and digital
world JARVIS operates in. The four-milestone distinction is now
documented explicitly in M27's own Objective: **M23B decides what to
do, M25 decides how to think, M26 decides how to improve, and M27
understands the world in which those decisions occur** — M27
publishes world knowledge, it does not execute actions directly,
continuing the same "recommend/model, don't act" boundary this roadmap
has drawn since M16/M18. Ten architecture notes were documented, most
notably that **M27 consumes services from sixteen prior milestones and
in turn publishes world knowledge services for all future intelligence
layers to consume, without requiring any milestone built after it to
operate** — avoiding circular dependencies — and that World Safety's
hazard detection hands off to M18 and M23A rather than acting on
hazards directly. A Future Expansion list named 12 planned extensions
(digital twins, city-scale world models, multi-building mapping,
autonomous navigation, robot fleet coordination, AR/VR integration,
satellite awareness, vehicle world models, space robotics, industrial
digital twins, planet-scale knowledge graphs), each requiring no
change to the core architecture. Dependencies were set to M1, M5, M5A,
M6, M9, M10, M13, M14, M18, M19, M20, M20A, M21, M22, M23, M23A, M23B,
M24, M25, and M26. Complexity was classified **XL**, with an explicit
rationale: responsible for maintaining a persistent understanding of
the physical and digital environments in which JARVIS operates, a
foundational platform underneath M12, M20, M23A, and M23B rather than
a standalone mapping feature. Acceptance criteria total 20 (covering
world modeling, spatial intelligence, object intelligence,
environmental awareness, human context, digital environment,
simulation, analytics, safety, SDK functionality, API stability,
explainability, privacy, scalability, performance, cross-platform
compatibility, documentation, testing, versioning, and reliability).
§10's feature backlog gained a new "World Model & Environmental
Intelligence Platform (M27 Modules)" table with 10 module-level rows,
inserted immediately after the M26 module table, with its own note
clarifying that no legacy rows predate M27 and that M26's own rows
remain preserved unchanged. §14's Version Timeline gained a new `1.3 |
M27` row between M26 (`1.2`) and the `1.x` post-1.0 placeholder row,
continuing the same MINOR-bump policy established for M25/M26 (§6).
§16's Recommended Development Order gained a new `22 | M27` row after
M26's `21`. Milestone numbering, ordering, and every completed
milestone (§3) remain untouched; M24's, M25's, and M26's own history is
preserved verbatim and unmodified throughout.

*Aug 2026 — Addendum 21:* **frontend technology migration** — JARVIS's
UI moves from PySide6 to **React 19 + TypeScript + Vite + Tauri**
(full stack in the new [`TECH_STACK.md`](TECH_STACK.md); active
execution plan in the new [`IMPLEMENTATION_ROADMAP.md`](IMPLEMENTATION_ROADMAP.md)).
Per explicit user direction: **zero milestone renumbering** — M12
through M27 keep their exact existing numbers, and no milestone's
completed history (§3, M0–M7) was rewritten. What changed is §8's
content at M8 through M11, plus three new lettered companions:
- **M8** retitled Plugin Platform → **React Frontend & Desktop
  Experience** (7 phases: React Foundation; Universal Application
  Framework & Logic; Desktop Workspace; Voice Experience & Motion;
  Settings & User Profiles; Premium UI Polish; Optimization & QA).
  Plugin Platform's own scope (SDK, Loader, Extension API, Permission
  Model, Store, Marketplace) was not dropped — it moved to M9.
- **M9** retitled Integration Platform → **Runtime & Core Services**
  (Runtime Core, Reliability, Plugin Platform — inheriting M8's full
  original scope — and Developer Platform Tools). Integration
  Platform's own scope (API Gateway, OAuth, Webhooks, Queue, Retry,
  Caching, Monitoring) was not dropped — it moved to M11.
- **M10** retitled Knowledge Engine → **AI Orchestrator** (Intent
  Engine, Planning, Context Engine, Tool Selection, Permission
  Validation, Execution, Verification, Learning, Streaming, Decision
  Engine — formalizing M5A's `AgentOrchestrator` and absorbing M7
  Phase 3's deferred cross-tool-parallelism scope). Knowledge Engine's
  own scope was not dropped — it moved to the new **M10A**.
- **M10A — Universal Search & Knowledge Platform** *(new lettered
  companion)* — the original M10 Knowledge Engine's full scope
  (Knowledge Graph, Persistent Memory, Reflection Foundation,
  Learning, Relationship Graph, Digital Twin Foundation), plus
  Universal/Memory/File/Command/Semantic/AI Search and Search
  Indexing.
- **M10B — Intelligence Layer** *(new lettered companion)* — Goal
  Manager, Routine Learning, Preference Learning, Predictive
  Suggestions, Context Awareness, Daily Briefing, Assistant
  Intelligence. Deliberately scoped as the backing engine M15's
  Proactive Intelligence and M16's Goal/Behaviour Reflection modules
  consume, not a duplicate of either — **M15 (Personality Engine) and
  M16 (Reflection Engine) were reviewed and left completely
  unchanged**, per explicit user direction, after their existing scope
  (450+ and similarly large, respectively, with real cross-references
  from M11/M12/M13/M17) was found to already be large, shipped-in-doc
  content that a naive "replace with Search/Intelligence" instruction
  would have destroyed.
- **M11** retitled Productivity Platform → **Integrations & Cloud
  Platform** — absorbs M9's original Integration Platform scope in
  full, plus M11's own original integration-facing features (Email,
  Calendar, Browser Intelligence, Google Workspace), plus new Spotify/
  Weather/Finance real-provider scope, Oracle Cloud sync, Android
  Companion pairing, Conflict Resolution, and Offline Queue. Smart
  Home integration was explicitly **not** duplicated here — it remains
  M12's own dedicated scope.
- **M11B — Productivity Suite** *(new lettered companion)* — the
  non-integration half of the original M11 Productivity Platform
  (Tasks, Documents, Research Assistant, Coding Assistant, Command
  Palette, Clipboard Manager, File Manager, Native notifications,
  Media Controls), preserved in full.
- **M14 — Security Platform** was reviewed against a request to
  "create a new Security & Privacy milestone" and found to already
  cover every listed item (Credential Vault, Encryption, Secrets
  Management, Permission Auditing, Privacy Controls, Audit Logs,
  Secure Storage, Backup Encryption, Consent Management) verbatim or
  near-verbatim across its existing 12 modules — no duplicate
  milestone was created; M14 itself is unchanged beyond a review note.

Every one of the ~50 stale cross-references this retitling created
across M12–M27, §2, §7, §9, §10, §11, §14, §15, §16, and §17 (other
milestones' Dependencies lists, Architecture notes, and backlog tables
naming the old "M9 Integration Platform," "M10 Knowledge Engine," or
"M11 Productivity Platform" by name) was located and corrected to
point at the renamed milestone or the correct new lettered companion —
tracked in §9's new "Aug 2026 frontend-migration carry-forward" table.
§14's Version Timeline shifted three version-string slots (0.10
onward) to fit M10A/M10B/M11B — a sequence-position change only, not a
milestone renumbering. M5's completed entry (§3) gained a
non-destructive "Frontend Migration Note" clarifying it is now
understood as having delivered JARVIS's backend platform bundled with
a since-superseded PySide6 frontend, without altering its Delivered/
Still-open bullets. §7's "UI Foundation" bullet gained an equivalent
note. Milestone numbering M12–M27, every completed milestone (§3), and
M15/M16's own scope remain untouched throughout. Bump this line
whenever you edit the roadmap.*

*Aug 2026 addendum — roadmap architecture review (pre-Phase-3
directive):* six additions integrated into existing milestones, no new
milestone numbers introduced, no completed milestone (§3) touched.
(1) **API Center Architecture** — new module under M11 (§8), expanding
the API Manager bullet into a full Built-in/External provider
registry with the binding Provider Activation Rule ("saving a key
activates it immediately; mocks only under explicit Developer Mode"),
runtime lifecycle (activation, registration, validation, connection
testing, health checks, discovery, switching, retry/fallback,
priority), and an API Usage Analytics dashboard (cross-referencing
M20A for the underlying cost-analytics engine). (2) **Cost-Aware Model
Router** — the previously one-line §13 "Cost/latency router" bullet
expanded into automatic provider/model selection, cost-vs-quality,
latency optimization, offline model preference, intelligent fallback,
budget protection, and emergency provider switching, explicitly wired
to consume M11's new API Center Architecture module's usage data
rather than inventing a second mechanism. (3) **Module Logic
Contract** — new permanent §4 Engineering standard: every module
defines Purpose/Responsibilities/Business Logic/Inputs/Outputs/
Dependencies/Permission Model/State Machine/Validation/Failure/
Recovery/Logging/Telemetry/Events/Tests/Acceptance Criteria before
implementation begins; formalizes a discipline this roadmap's
milestone entries already followed informally. (4) **Plugin Safe Core
Architecture** — new binding principle inside M9's existing Plugin
Platform module (§8): JARVIS Core is immutable from a plugin's
perspective; future *not-yet-scoped* domain modules (illustrative
only — Children/Family/Medical/Business; none are roadmap milestones
today) ship as plugins, with Plugin Isolation, Version Compatibility,
Rollback Support, Crash Isolation, Safe Disable, and Dependency
Validation: added as M9's acceptance criterion 6. Explicitly does
**not** retroactively convert any existing scoped milestone (M12 Smart
Home & IoT Platform, or the Finance workspace under M5/M11) into a
plugin — that remains a separate future decision. (5–6) Corresponding
checklist items added to `IMPLEMENTATION_ROADMAP.md`'s active M8
Phase 2 (API Integration Rework), Phase 3 (Adaptive Sidebar), and
Phase 5 (API Center UI + Developer API Analytics) — the only
milestone that document tracks. No dependency, acceptance-criterion,
or numbering conflict was found against M0–M27; M8 Phase 3
implementation (paused mid-task, before this review) resumes after
this addendum. Bump this line whenever you edit the roadmap.*

*Aug 2026 addendum — UI Architecture Update:* three additions
integrated into existing milestones, no new milestone numbers, no
completed milestone (§3) touched. (1) **Dynamic Sidebar & Dashboard
Widget Grid** — new subsection under M8 Phase 3 (§8): a minimal,
non-disableable core nav set (Dashboard, AI [nested: Conversation,
Voice, Memory], Automation, Files, Settings) plus a
registered-*and*-enabled gate (`ModuleEnablementStore`) for every
other module — supersedes Task Group C's shipped flat Workspace/
Connected grouping (that work's collapse/keyboard/accessibility
mechanics are unaffected and carry forward). The Dashboard becomes a
widget grid; built-in system widgets ship with Core, everything else
registers through the new `DashboardWidgetRegistry`. (2) **Plugin
Registration System** — new subsection inside M9's existing Plugin
Platform module (§8): the concrete 12-surface list (sidebar, dashboard
widgets, pages/routes, settings pages, notifications, voice commands,
automation actions, permissions, background services, context menu
actions, command palette actions) a plugin gets once loaded, explicit
about which of those already work today for first-party modules via
already-shipped Phase 2 frontend registries (`ApplicationRegistry`,
`NavigationContribution`, the Permission/Settings/Notification
Frameworks) versus which still require M9's own, still-unbuilt Plugin
Loader (third-party code loading, sandboxing, Marketplace install/
uninstall) — no scope invented for the Loader itself, only named more
precisely. (3) **Settings page structure** — new subsection under M8
Phase 5 (§8): the concrete page list (General/Appearance/Voice/AI
Models/Memory/Automation/Devices/Accounts/Plugins/Security/Developer
Mode/Backup & Restore/About), with an explicit **installed** (Developer
Mode's Marketplace, privileged) vs. **enabled** (this page's Plugins
toggle, unprivileged, reversible) distinction — the two states Phase
3's sidebar/dashboard gating rule depends on. Corresponding checklist
items added to `IMPLEMENTATION_ROADMAP.md`'s active M8 Phase 3 and
Phase 5. Validated against the shipped codebase before this addendum:
`ApplicationRegistry`, `NavigationContribution` (including its
existing `commandPaletteEntries` field), and the Permission/Settings/
Notification Frameworks are real and already support first-party
extension today — the new `DashboardWidgetRegistry` and
`ModuleEnablementStore` extend that same, already-proven pattern
rather than inventing a parallel one. No dependency, acceptance-
criterion, or numbering conflict was found against M0–M27. Bump this
line whenever you edit the roadmap.*

*Aug 2026 addendum — Contribution Registry unification & Task Group D
(Dock):* corrects a real architectural gap this same review cycle
introduced: `DashboardWidgetRegistry`, added the prior pass as its own
bespoke class mirroring `ApplicationRegistry`'s pattern, was exactly
the "multiple unrelated registries" anti-pattern the Plugin
Registration System addendum above warns against. Fixed by extracting
the shared register/unregister/getAll(cached)/getByModule mechanism
into `core/contribution-registry.ts`'s generic `ContributionRegistry<T>`,
then migrating both `DashboardWidgetRegistry` (now a thin named
instance) and `NavigationContribution`'s internal storage (previously
its own raw `Map`) onto it — public APIs unchanged for both, so no
consuming code (`BaseApplication`, Sidebar, tests) needed to change.
`ApplicationRegistry` itself is deliberately not refactored to compose
the generic class — it owns module-specific concerns (dependency
resolution, manifest validation) neither `ContributionRegistry` nor
its consumers need, and refactoring already-tested, widely-depended-
upon code for zero externally-visible benefit was judged not worth the
risk. M9's Plugin Registration System subsection (§8) updated to name
`ContributionRegistry` as the actual shared mechanism throughout.
Also: **M8 Phase 3, Task Group D (Dock)** shipped in the same pass —
registry- and enablement-driven, the same pattern Task Group C
established for Sidebar, the last consumer of the now-fully-retired
`routes/nav-items.ts`. No dependency, acceptance-criterion, or
numbering conflict was found against M0–M27. Bump this line whenever
you edit the roadmap.*

*Aug 2026 addendum — Task Group E (Status Bar):* the Status Bar became
another `ContributionRegistry` (M8 Phase 3) instance, `statusBarRegistry`
-- a fourth named surface alongside Navigation and Dashboard Widgets,
not a new bespoke class. Core JARVIS's 9 built-in items (left: Current
Workspace, Active Module; center: Current Running Task, Background
Task Progress; right: AI Provider, Voice Status, Automation Status,
Internet/Offline, Notification Indicator) register through the same
path a future plugin's own status item would. Three items (AI
Provider, Voice Status, Automation Status) have no real backend data
source yet — no AI-provider-state API, no voice WebSocket relay, no
automation-run status exists on the frontend today — and honestly
render "Not configured" rather than fabricated data, the same honesty
standard the existing connection-status indicator (folded into this
same registry as the "Internet/Offline" item, not duplicated as a
second mechanism) already established. `DashboardWidgetContribution`'s
`render` field, left deliberately untyped (`() => unknown`) when it had
no real consumer, is now typed as a proper component reference,
matching `StatusBarContribution.render`'s contract, now that building
an actual consumer clarified the correct shape: each contribution
renders as its own element so it manages its own reactivity, rather
than a value being read and interpolated by the consuming layout
component (which would violate React's Rules of Hooks over a
variable-length list). No dependency, acceptance-criterion, or
numbering conflict was found against M0–M27. Bump this line whenever
you edit the roadmap.*

*Aug 2026 addendum — Task Group F (Dashboard Widget Grid):* the
Dashboard's `home` route became a real page (`features/dashboard/
dashboard-grid.tsx`), replacing `PlaceholderRoute`, and
`DashboardWidgetContribution` gained an `isCore` field — the same
reasoning `StatusBarContribution.isCore` already established, since
Core JARVIS's widgets register under the reserved `moduleId: "core"`,
which isn't a real `ApplicationRegistry` entry an enablement check
could otherwise resolve `isCore` from. A new `stores/dashboard-
layout.store.ts` (persisted, key `jarvis.dashboard-layout`) is the
grid's own preference layer — which registered+enabled widgets are
currently visible, at what size, in what order, and whether pinned —
kept separate from the registry describing *what widgets exist*, the
same split `stores/dock.store.ts` (preference) and
`core/application-registry.ts` (existence) already established.
Widgets resize through 4 fixed grid footprints (1×1, 2×1, 1×2, 2×2)
rather than free-form drag-resize: no grid-layout or drag-and-drop
library is installed in `frontend/package.json`, and introducing one
unannounced was judged worse than a small, fully-functional, honestly-
scoped fixed-tier resize control. Export/import round-trips one JSON
document shaped like `core/settings-framework.ts`'s existing
`{schemaVersion, values}`-style envelope, validated (not blindly
trusted) before being applied — this repo's first real client-side
file download/upload, added deliberately rather than left as an inert
button.

Of the roadmap's originally-listed 7 built-in widgets, **4 shipped
real** (Notifications, Recent Activity, Quick Actions, System Status)
and **3 were deliberately not built** (Tasks, Calendar, Notes) — a
repo-wide search confirmed zero backing store, data model, or backend
endpoint exists for any of the three, so a widget for them today would
be exactly the fake/placeholder implementation this project's standing
rule forbids. This is the same "build only what's honestly real, and
document the rest" resolution this same UI Architecture Update review
established for `StatusBarContribution`'s three "Not configured"
items — applied here to whole widgets rather than individual status
fields, since there is no partial-honest state between "a real Tasks
feature" and "no Tasks widget at all." `DashboardWidgetRegistry` places
no cap on widget count, so each becomes additive once its own feature
ships. No dependency, acceptance-criterion, or numbering conflict was
found against M0–M27. Bump this line whenever you edit the roadmap.*

*Aug 2026 addendum — Task Group G (Command Palette):* filled in
`components/layout/command-palette-layer.tsx`, the reserved DesktopShell
region that had rendered nothing since Phase 3's own foundation pass.
Both `Ctrl+K` and `Ctrl+Shift+P` open it
(`providers/command-palette-provider.tsx`, following the same
`useEffect` + `window` keydown + cleanup idiom `providers/developer-
provider.tsx` established for `Ctrl+Shift+D`) — the roadmap's canonical
binding has always been `Ctrl+Shift+P`, but `components/layout/
header.tsx`'s Search button has visually promised "Ctrl+K" since Phase
1; binding only one would silently break the other's promise.

Before building, confirmed `NavigationContribution.commandPaletteEntries`
+ `getAllCommandPaletteEntries()` (`core/interfaces/navigation-
interface.ts`, M8 Phase 2) is real, already-wired infrastructure —
every module's `mount()`/`unmount()` already calls `registerNavigation()`
via `BaseApplication`, confirmed by tracing the call chain through
`WorkspaceManager.switchTo()`. **No new `ContributionRegistry` instance
was built for commands** — the M9 Plugin Registration System's own text
already calls this mechanism "already real, not new"; building a
parallel one would have repeated the exact "multiple unrelated
registries" mistake the Task Group D/E addendum above fixed. The
Command Palette's "Navigate" entries instead come from
`ApplicationRegistry` + `ModuleEnablementStore`, the same data
Sidebar/Dock already read.

Found and fixed a real bug in the process: `components/ui/command.tsx`'s
`CommandDialog` (scaffolded in Phase 1, never previously given a real
consumer) didn't wrap its `children` in cmdk's own `<Command>` root —
every `CommandInput`/`CommandList`/`CommandItem` rendered inside it
threw at render time with no cmdk context to read from. Fixed at the
primitive, not worked around per-consumer. Also added a `scrollIntoView`
no-op stub to `test/setup.ts` (jsdom doesn't implement it; cmdk's list
uses it internally) — same category as the existing `ResizeObserver`/
`matchMedia` stubs already there. No dependency, acceptance-criterion,
or numbering conflict was found against M0–M27. Bump this line whenever
you edit the roadmap.*

*Aug 2026 addendum — Premium UI & Voice Experience initiative, Task
Group H (Voice State Architecture):* the first task group of a new,
larger visual-modernization pass (glassmorphism, an original startup
sequence, Sidebar/Command Palette visual polish, accessibility settings
for motion/glass/contrast — tracked as sequential task groups I–L,
this one first since it was the most architecturally sensitive). Ships
M8 Phase 4's Voice String (renamed from the original "Voice Waveform"
wording) and Live Transcript.

Before building, confirmed no real voice state machine exists on the
frontend today: `core/interfaces/voice-integration.ts` only covers
command bindings, and no WebSocket voice event relay exists (same gap
Status Bar's "AI Provider"/"Voice Status" items already honestly
report as "Not configured"). Resolved by building the real thing now,
kept honest: `core/voice-state-machine.ts` (mirrors `core/module-
lifecycle.ts`'s already-established pattern — fixed states, a
validated transition graph, a typed error on an illegal jump, rather
than a bare mutable field) and `stores/voice-state.store.ts` (the one
real entry point, `transition()`, that a future voice pipeline will
call — Developer Mode's new Voice State Preview panel
(`features/developer/voice-state-preview.tsx`) calls the exact same
function, so there is no separate "fake preview" code path). The store
starts and stays `idle` in normal operation; the preview panel is
Developer-Mode-gated, off by default, and never simulates a
conversation outside itself — manual transition buttons only ever
offer legal next states (`reachableVoiceStates()`), so a click can
never hit the store's own validation and throw.

`components/voice/voice-string.tsx` renders the wave via `motion/react`'s
`useTime`/`useTransform` (a continuous, GPU-friendly animation loop,
not a discrete `animate` transition) and branches on Motion's own
`useReducedMotion()` hook directly, since `MotionConfig`'s app-wide
`reducedMotion="user"` (`providers/app-providers.tsx`) only covers
declarative transitions, not a manually-driven per-frame loop.
`components/voice/live-transcript.tsx` is a thin view over
`stores/voice-transcript.store.ts`, empty (renders nothing) until a
real STT stream exists, fading 4s after the last real word arrives.
Both wired as the `voice` module's real route element
(`features/voice/voice-page.tsx`), replacing its `PlaceholderRoute` the
same way Task Group F did for `home`. No dependency, acceptance-
criterion, or numbering conflict was found against M0–M27. Bump this
line whenever you edit the roadmap.*

*Aug 2026 addendum — Voice String revision (real-time multi-bar
waveform):* the single-sine-path Voice String shipped earlier this
same task group was superseded, same day, once the Premium UI & Voice
Experience brief asked specifically for a "premium real-time voice
waveform" matching the visual quality of modern voice assistants
(Google Assistant, Gemini Live, ChatGPT Voice) — composed of many
animated bars, not a smooth curve.

Split the single `voice-string.tsx` component into two, on purpose:
`components/voice/voice-waveform-renderer.tsx` is the pure renderer —
zero store dependency, accepts `voiceState`, `microphoneLevel`,
`ttsLevel`, and `intensity` as plain props — and `voice-string.tsx` is
now the thin layer wiring real store state into it. This is a direct
answer to the brief's own requirement ("design it so the future voice
backend can stream real audio amplitudes directly into the renderer,"
"separate rendering from state management") — the renderer will need
zero changes once a real audio pipeline exists; only the values fed
into its already-real props change. Added `stores/voice-audio-
levels.store.ts` for the two new real fields (`microphoneLevel`,
`ttsLevel`), following the exact same "start and stay at `0`, no real
pipeline exists yet" honesty `voice-state.store.ts` and every other
not-yet-backed store in this app already establishes — the renderer's
procedural ambient motion (an honest, designed animation curve per
state, not fabricated audio data) is additively boosted by these real
fields once they carry real values, with bars nearer the panel's
center reacting more strongly, matching how a real center-weighted
level meter reads.

Each of the 40 bars derives its height from one shared `useTime()`
clock via `useTransform` (one requestAnimationFrame loop feeding many
cheap derived values, each bound straight to the DOM through Motion's
`style` prop — no React re-render per frame, `transform`-only so it's
GPU-compositable, no layout shifts) rather than 40 independent RAF
subscriptions. Per-state "envelope" shapes (`flat`/`center`/`wave`/
`random`) implement the brief's own state-by-state spec directly:
Wake's "center pulse, wave expands outward" is a radial phase offset
by distance from center; Thinking's "calm flowing... different from
Listening" is a traveling left-to-right wave; Listening/Speaking's
reactive look uses two overlapping deterministic sine terms per bar
(a fixed per-bar phase seed, not `Math.random()`, which would reseed
every render and read as jitter rather than the brief's own "smooth
interpolation, no jitter" requirement). The glass-panel container
(blurred translucent background, soft state-colored bloom) uses this
app's existing semantic color tokens (`text-accent`/`text-warning`/
`text-success`/`text-destructive`) for the "cyan/blue gradient" look
the brief asks for, not new hardcoded hex values, per `ARCHITECTURE.md`
section 14's binding color-token rule.

Developer Mode's Voice State Preview panel now drives the raw renderer
directly (not the `VoiceString` convenience wrapper) so it has full
manual control over every prop the renderer accepts: mic/TTS level
sliders write to the real `voice-audio-levels.store.ts` (the same
store a real audio pipeline will publish to — no separate fake preview
path), and a local `intensity` control (a QA-only animation-tuning
knob, not a persistent app-wide concept, so it was deliberately not
promoted to its own store). No dependency, acceptance-criterion, or
numbering conflict was found against M0–M27. Bump this line whenever
you edit the roadmap.*

*Aug 2026 addendum — Premium UI & Voice Experience initiative, Task
Group I (Startup Experience & Lazy Loading):* the second task group of
the visual-modernization pass begun by Task Group H. Ships M8 Phase
4's Startup Experience — a choreographed ~4.2s sequence (energy point
-> ripple -> logo assemble -> logo pulse -> morph into the existing
Voice String -> Voice String activation -> Voice String expansion ->
center-outward glass reveal) replacing a bare loading flash, per the
brief's explicit "IMPORTANT: the Voice String architecture is now
considered COMPLETE — do not redesign or replace it; reuse the
existing renderer as the centerpiece" instruction. No startup text
ever renders (no "Loading...", percentages, or technical messages) —
only an `sr-only role="status"` string for assistive tech, satisfying
the brief's own "the animation itself communicates startup" rule.

`core/startup-orchestrator.ts` is the real work the animation hides:
`STARTUP_TASKS` maps the brief's High/Medium/Low priority tiers onto
what this codebase actually has to register today —
`registerCoreStatusBarItems`/`registerCoreDashboardWidgets` (high),
`registerPlaceholderModules` (medium). `low` has no real task yet;
left honestly empty rather than backed by a fabricated delay, matching
this project's "no fake data" rule extended to timing — it starts
doing real work the moment a real background service (cache cleanup,
analytics, etc.) exists. These three calls moved here from `main.tsx`,
which used to invoke them directly and synchronously before the first
paint.

`components/startup/startup-gate.tsx` reveals the real app only once
both the orchestrator's real work *and* the choreography's own
animation have finished — genuine synchronization, not a cosmetic
delay, since `WorkspaceManager` needs `ApplicationRegistry` actually
populated before it can resolve the initial route's module. Honors the
brief's accessibility requirements directly: a persisted
`skipStartupAnimation` preference (`stores/startup-preferences.store.ts`)
and Motion's `useReducedMotion()` each independently skip straight to
the dashboard, satisfying "if startup animation is disabled: launch
directly into Dashboard." `components/startup/startup-sequence.tsx`
drives the **real** `voice-state.store.ts` at its morph/expand phases
(`wake`, then `idle`) rather than a second, decorative state — the
Voice String shown during startup is the exact same store-driven
component shown everywhere else in the app. The center-outward reveal
is a real animated CSS `mask-image: radial-gradient(...)` (via
`useMotionTemplate`/`useMotionValue`), the literal mechanic the "reveal
from the center outward" requirement describes, not an opacity
approximation. `components/layout/desktop-shell.tsx` gained an
additive staggered fade/rise for its Sidebar/Header/Status-Bar/Dock
regions on first mount — since `StartupGate` only mounts the real
dashboard once startup is truly complete, this stagger *is* the
brief's "Dashboard Reveal" sequence, with no separate signal needed
between the two systems.

**Bug found and fixed during this task group:** `StartupGate`'s
initialization `useEffect` (empty dependency array) is double-invoked
by React `<StrictMode>` in development — by design, to surface
non-idempotent effects. The second, illegal call to
`registerPlaceholderModules()` threw (`ApplicationRegistry` rejects a
duplicate module registration), and since the effect's
`runStartupSequence().then(...)` chain had no `.catch()`, the resulting
unhandled promise rejection silently left `workDoneRef.current` at
`false` forever — the choreography would finish and then hang
indefinitely on a blank frame, with no visible error. Root-caused via
live browser reproduction (not guessed): confirmed the reveal
completed once, then re-broke, isolating it to the double-invoke rather
than the mask-image/reveal logic itself. Fixed at the actual source of
the invariant — `runStartupSequence()` itself is now idempotent (a
module-level cached promise, `startupPromise ??= (async () => {...})()`)
— rather than a call-site guard in `StartupGate`, since "real
initialization runs exactly once per app lifetime" is a property of the
orchestrator, not of any one caller. A separate, real bug
(`useStartupPreferencesStore` was never added to `StoreProvider`'s
`persistedStores` hydration-gate array) was found and fixed in the same
pass; on its own it did not resolve the hang, confirming the two were
independent issues rather than one being a symptom of the other.
`e2e/app-shell.spec.ts` seeds the real `skipStartupAnimation`
preference via `page.addInitScript` in a new `beforeEach`, using the
same accessibility escape hatch a real user gets rather than weakening
the suite. No dependency, acceptance-criterion, or numbering conflict
was found against M0–M27. Bump this line whenever you edit the
roadmap.*

*Aug 2026 addendum — Premium UI & Voice Experience initiative, Task
Group J (Glass design system):* the third task group of the
visual-modernization pass. Ships real glassmorphism (translucency +
`backdrop-filter` blur, not just a tinted flat color) on the three
surfaces the brief specifically names: Sidebar, Command Palette, and
Cards — plus a subtle, static ambient glow behind `DesktopShell`,
which turned out to be a real prerequisite, not decoration for its own
sake: a flat `bg-background` gives `backdrop-blur` nothing to blur, so
without it every glass surface would have rendered as a barely-visible
tint rather than genuine glass.

`hooks/use-glass-effects.ts` exports `useGlassEffectsEnabled()`, a thin
wrapper around the real, persisted `disableGlassEffects` preference
Task Group I already shipped (`stores/startup-preferences.store.ts`).
Deliberately reused rather than adding a second flag: the preference
existed but, until this task group, gated nothing outside the startup
sequence's own glow — that comment in the store itself said as much
("an app-wide 'disable glass everywhere' toggle is a later, dedicated
accessibility task group's job"), and once J was about to ship the
first *real* app-wide glass surfaces, leaving that comment's promise
unfulfilled would have shipped a toggle that visibly lied about what it
did. The hook exists specifically so call sites read correctly:
`components/ui/card.tsx` and `components/ui/command.tsx` importing
something named `useStartupPreferencesStore` directly would have been
a real readability smell for surfaces with nothing to do with startup,
even though `components/ui/sonner.tsx` already established the
precedent that a `components/ui/` primitive reading a small, targeted
app store directly is acceptable in this codebase.

Each surface picked its own blur intensity deliberately, not a single
shared constant: Sidebar (`bg-card/70 backdrop-blur-xl`) and Command
Palette (`bg-popover/70 backdrop-blur-2xl`) are both large, mostly-empty
panels where a strong blur reads as premium; the shared `Card`
primitive — the base every dashboard widget, and dialog already
builds on — got a conservative `bg-card/85 backdrop-blur-md` instead,
since Cards hold dense text at every size in this app and legibility
had to come first. Command Palette's glass treatment is scoped to
`CommandDialog`'s own `DialogContent` override in `components/ui/
command.tsx`, not the shared `Dialog`/`Command` primitives other real
dialogs in the app (Notifications, Context Menu, etc.) also render
through — those keep their original plain background untouched, since
the brief named Command Palette specifically, not every dialog in the
app. Every glass surface has a real, solid fallback (no blur, higher
opacity) when `disableGlassEffects` is set, verified live in the
browser via actual computed `backdrop-filter`/`background-color`
values (not just class-name assertions) across all three shipped
themes (light/dark/jarvis) and with the preference both on and off. No
dependency, acceptance-criterion, or numbering conflict was found
against M0–M27. Bump this line whenever you edit the roadmap.*

*Aug 2026 addendum — Premium UI & Voice Experience initiative, Task
Group K (Accessibility settings):* the fourth of five sequential task
groups in the visual-modernization pass (H, I, J, K, L — see below).
Ships M8 Phase 4's Settings >
Accessibility page (`features/settings/settings-page.tsx`, replacing
the `settings` module's `PlaceholderRoute`) -- the first real,
non-Developer-Mode surface for the three preferences Task Groups I/J
already made real: Skip startup animation, Reduced motion, Disable
glass effects. Developer Mode's Startup Preview panel keeps working
unchanged as a QA convenience, not a duplicate source of truth -- both
surfaces read and write the exact same store.

Renamed `stores/startup-preferences.store.ts` to `stores/
accessibility-preferences.store.ts` (`useStartupPreferencesStore` ->
`useAccessibilityPreferencesStore`, persist key `jarvis.startup-
preferences` -> `jarvis.accessibility-preferences`) as part of this
task group, not a separate cleanup pass: the store had already grown
real, app-wide consumers unrelated to startup (Task Group J's Sidebar/
Card/Command Palette glass surfaces), and this task group was about to
add its first genuinely new preference and its first real end-user
Settings surface -- the moment those two things happen is the cheapest
and most honest time to fix a name that was actively misleading by
then, not defer it further. Mechanical at every real call site (17
files); `hooks/use-glass-effects.ts` already existed specifically to
keep the awkward store name from leaking into UI-primitive call sites,
and needed no behavioral change, only its own import updated.

Added a genuine third preference, `reducedMotion` -- an app-level
override on top of the OS-level `prefers-reduced-motion` `MotionConfig`
already honors, for users whose OS setting doesn't (or can't) express
it. `providers/app-providers.tsx` gained `AccessibleMotionConfig`,
which feeds the real preference into `MotionConfig`'s own
`reducedMotion` prop (`"always"` vs `"user"`) -- deliberately read
*inside* `StoreProvider`'s hydration gate (a separate component
rendered as its child, exactly how `ThemeProvider` already reads
`useThemeStore`), not in `AppProviders` itself above the gate, so it
can never observe the pre-hydration default the way a hook call above
the gate could.

**Real bug found and fixed while wiring this up:** the two places in
this app that branch on their own reduced-motion logic --
`components/startup/startup-gate.tsx` (whether to skip the
choreography) and `components/voice/voice-waveform-renderer.tsx`
(whether to freeze the wave) -- both called Motion's public
`useReducedMotion()` hook directly. That hook, it turns out, only ever
reads the OS-level `prefers-reduced-motion` media query and completely
ignores `MotionConfig`'s own `reducedMotion` context value -- setting
the new app preference would have had zero effect on either real call
site, silently. `MotionConfig`'s `reducedMotion` prop only reaches
Motion's *declarative* `animate`/`variants` animations automatically
(Motion's rendering engine consults it internally for those); it does
not reach app code that reads reduced-motion state for its own
branching decisions. Root-caused by reading Motion's own source
(`framer-motion`'s `use-reduced-motion-config.mjs`) rather than
guessing, once a live-browser check surfaced identical bar heights
regardless of the preference. Fixed by switching both call sites to
`useReducedMotionConfig()` -- the hook Motion itself uses internally to
combine the OS query and the context value -- rather than hand-rolling
an equivalent; it is public API (exported from `framer-motion`,
re-exported through `motion/react`), just not the hook either call site
had reached for. No dependency, acceptance-criterion, or numbering
conflict was found against M0–M27. Task Group K was the fourth of five
sequential task groups planned for this initiative (H, I, J, K, L);
**Task Group L (Dashboard Widget drag-and-drop)** remains the one
still open, plus the broader hover/Sidebar/Dock/Cards/Notifications
motion pass tracked separately under Phase 6. Bump this line whenever
you edit the roadmap.*

*Aug 2026 addendum — Premium UI & Voice Experience initiative, Task
Group L (Dashboard widget drag-and-drop):* the fifth and final task
group of the visual-modernization pass. Resolves the brief's own
"Drag" requirement for Dashboard widgets against the button-based
interaction model Task Group F had already shipped — additively, per
the earlier flagged default (a genuinely ambiguous question in the
brief's answer set at the time): drag is a second, real way to reorder
widgets, and none of the existing Move up/down/Resize/Pin/Remove
buttons were removed or changed.

Built on `motion/react`'s own `Reorder.Group`/`Reorder.Item` rather
than a bespoke drag implementation or a new dependency — this app
already depends on Motion for every other animation surface, and
Framer's Reorder API is purpose-built for exactly this "drag to
reorder a list" case. `stores/dashboard-layout.store.ts` gained
`reorderPeers(peerIds, pinned)`, additive alongside the existing
`moveWidget()`: given a full drag-produced permutation of one pin
group (exactly what `Reorder.Group`'s own `onReorder` callback
provides), it walks the stored `order` array and, at each position
currently held by a member of that group, substitutes the next id from
the new sequence — every other id (the opposite pin group, and hidden
widgets) keeps its exact position untouched. `moveWidget()`'s discrete
up/down/start/end steps and `reorderPeers()`'s full-permutation drops
both operate on the same `order` array, so the two interaction models
can never disagree about the current layout.

`dashboard-grid.tsx` renders two separate `Reorder.Group` instances,
one per pin group, each `as="div"`/`className="contents"` so neither
introduces a wrapper box of its own — their `Reorder.Item` children
remain direct children of the existing CSS grid, unchanged from before
this task group. Dragging a widget only ever reorders it among its own
pin-group peers, the same constraint the Move buttons already enforce
— chosen deliberately over a single combined drag list, which would
have let a user drag an unpinned widget above a pinned one, violating
the "pinned widgets always render first" invariant every other part of
this feature already relies on. Each `WidgetCard` is now a
`Reorder.Item` with a dedicated drag handle (`dragListener={false}` +
`useDragControls()`, started from the handle's own `onPointerDown`)
rather than making the whole card draggable — the card is full of its
own interactive controls (five buttons, plus the widget's own real
content), so a whole-card drag target would fight with clicking any of
them.

**A real verification lesson surfaced while confirming this worked
live:** a live check against the Browser pane, plus a scripted
`dispatchEvent`-based `PointerEvent` sequence, showed no reorder
occurring at all — Framer Motion's drag gesture recognition depends on
genuinely trusted browser pointer events (real `setPointerCapture`
semantics and sequencing) that a synthetic dispatch in that harness
couldn't faithfully reproduce, and the Browser pane's screenshot
dependency (unavailable in that session) blocked using its own
mouse-drag primitive to confirm otherwise. Resolved by adding a real
Playwright end-to-end test (`e2e/dashboard-widgets.spec.ts`) using
`page.mouse.move`/`.down`/`.up` against Playwright's own, separately
managed dev server — genuine, trusted browser mouse events, not a
scripted dispatch — which confirmed the drag gesture and the resulting
reorder both work correctly end to end, including that the real store
persists the new order (not just a visual change) and that dragging
never adds or removes a widget, only reorders it. A second Playwright
test confirms the pre-existing Move up/down buttons still work
unchanged alongside the new handle. No dependency, acceptance-
criterion, or numbering conflict was found against M0–M27. This closes
the Premium UI & Voice Experience initiative's five task groups (H, I,
J, K, L) in full; the broader hover/Sidebar/Dock/Cards/Notifications
motion pass remains tracked separately under Phase 6 — Premium UI
Polish. Bump this line whenever you edit the roadmap.*

*Aug 2026 addendum — M9 Task Group A (Runtime Manager & Application
Lifecycle):* the frontend's Premium UI & Voice Experience initiative
(H–L) being done, work resumes on the documented milestone sequence —
M9 Runtime & Core Services, the first backend milestone after M8. This
follows an architecture review the user requested and then explicitly
closed: a Node.js/Electron backend pivot was considered, two
exploration passes confirmed the existing Python backend already has
real, working implementations of 4 of the reviewed priorities (AI
Orchestrator, Agent Framework, Memory Engine, Tool Router — all
LangGraph/ChromaDB-backed) totalling roughly 15,000 lines of non-UI
logic plus real pytest coverage, and the user's final decision was to
keep Python + FastAPI + Tauri as the official architecture, unchanged,
and continue the documented roadmap exactly. No architecture doc in
this repository was rewritten as a result — this addendum is the only
record of that review, since nothing about the actual architecture
changed.

Scopes only Runtime Core's first two bullets (Runtime Manager,
Application Lifecycle) — not all of M9, following the same
task-group-at-a-time discipline the frontend work above already
established. `core/lifecycle/shutdown_manager.py`'s `ShutdownManager`
(M5.5) is renamed to `core/lifecycle/runtime_manager.py`'s
`RuntimeManager`, exactly matching this milestone's own pre-existing
wording ("generalizing the existing `ShutdownManager` ... into the
single place every subsystem registers a lifecycle hook, not just a
cleanup one") — the shutdown-side API (`register`/`unregister`/
`shutdown`) is unchanged in behavior, only renamed alongside a new,
symmetric startup-side API (`register_startup`/`unregister_startup`/
`startup`) sharing the same priority-ordered, fault-isolated hook
design (generalized `LifecycleHook`/`LifecycleResult` dataclasses,
replacing the shutdown-only `ShutdownHook`/`ShutdownResult`). `app.py`'s
two ad-hoc startup steps (memory-policy enforcement, Whisper preload —
each previously its own hand-written `try`/`except`, both already
commented "must never block boot") now register as real startup hooks,
the literal startup-side mirror of the exact problem `ShutdownManager`
was built to solve for shutdown. `AppReadyEvent`/`ShutdownRequestedEvent`
(`core/events/events.py`) — previously undocumented as "placeholder
examples for milestone authors," never published anywhere — are now
real: `AppReadyEvent` publishes once `RuntimeManager.startup()`
completes, `ShutdownRequestedEvent` publishes at the start of
`MainWindow._graceful_quit()`, both over the existing `EventBus`.
Exposing this lifecycle state to M8's frontend over WebSocket remains
separate, not-yet-built work — no FastAPI WebSocket route exists at
all yet (confirmed during this task group; the frontend's own
WebSocket client has been waiting since M8 Phase 1) — a natural
Task Group B, alongside the rest of Runtime Core (Service Manager,
Session Manager, Configuration Manager's live-reload path).

All 17 real call sites across `src/` and `tests/` were updated for the
rename (DI container's `shutdown_manager` provider → `runtime_manager`,
`MainWindow`, `AgentCheckpointer`'s docstring, and every test asserting
the container's provider surface or exercising shutdown behavior
directly); genuinely historical prose (the M5.5 stabilization pass's
own "Real, verified fixes" narrative, a Troubleshooting doc pointing
users at a specific old build) was deliberately left referring to
`ShutdownManager` by its name at the time, not rewritten. Full pytest
suite passes; the new `runtime_manager.py` and its test file
(`tests/unit/test_runtime_manager.py`, extending the original
`test_shutdown_manager.py` one-for-one plus new startup-side and
cross-direction-independence coverage) are mypy- and ruff-clean. The
pre-existing mypy/ruff findings surfaced while checking the touched
files (container.py's un-annotated `providers.Singleton` assignments,
the project-wide accepted-debt `PLC0415` lazy-import pattern §15
already documents, a few unrelated `main_window.py`/`app.py` findings)
were confirmed — by diff scope, not assumption — to predate this task
group and were left alone. No dependency, acceptance-criterion, or
numbering conflict was found against M0–M27. Bump this line whenever
you edit the roadmap.*

*Aug 2026 addendum — M9 Task Group B (Service Manager, Session
Manager, Configuration Manager, Runtime Health Monitor, Runtime
WebSocket API, Runtime Integration):* the second and final Runtime
Core task group, closing out every bullet Task Group A explicitly
deferred. Architecture remained fixed for this task group exactly as
Task Group A's own addendum recorded — Python 3.13 + FastAPI + Tauri,
no migration — this addendum documents implementation only, not
another review.

`core/interfaces/service.py` makes `IService` (`docs/ARCHITECTURE.md`
§8) real code for the first time — `initialize`/`start`/`stop`/
`health`/`status`/`shutdown`, plus `HealthStatus`/`ServiceStatus`
dataclasses. No existing service was retrofitted onto it directly;
`core/lifecycle/service_manager.py`'s `ServiceManager` wraps a curated
set (`ConversationService`, `ChatService`, `MemoryService`,
`ThemeService`) in thin adapter classes instead — composition over
inheritance, per this task group's own binding requirement.
`VoiceService`/`HotkeyService` were deliberately excluded:
`ui/main_window.py`'s `_register_shutdown_hooks()` already owns their
shutdown lifecycle directly against `RuntimeManager` (predating this
task group), and giving one resource two competing lifecycle owners
would be a regression, not an improvement. `BrowserService`/
`AutomationService`/`SystemService` are DI `Factory` providers (a new
instance every resolution) with no stable identity a registry could
poll `health()` on repeatedly — retrofitting those onto `IService` is
real future work (see §15), not silently worked around here. The
`memory_policies` startup hook that lived directly in `app.py` since
Task Group A is now `MemoryServiceAdapter.start()` — one real owner
instead of a standalone hook plus a future competing one.

`core/lifecycle/session_manager.py`'s `SessionManager` introduces
`RuntimeSession` (`infrastructure/database/models.py`, new
`runtime_sessions` table via the existing `Base.metadata.create_all`
migration-free pattern) — deliberately its own id space, not a reuse
of `Conversation.id` or the agent orchestrator's LangGraph `thread_id`.
Those model two different, already-real things with no existing link
between them; `RuntimeSession` is the first place they can optionally
sit side by side (both columns nullable) rather than being forced
together or left disconnected. `recover()` closes out any session an
unclean previous shutdown left open, proven under test across two
independent `SQLiteDatabase` instances against the same on-disk file —
the same shape two real OS process launches would see.

`core/lifecycle/configuration_manager.py`'s `ConfigurationManager`
adds a real live-reload path restricted to `SAFE_RELOAD_SECTIONS`
(`ui`, `voice_announce`, `memory`, `update`, `dev_mode`) — grounded in
observed code, not guessed: `ChatService.stream()` demonstrably reads
`settings.ui.system_prompt` fresh on every call, so reloading it is
genuinely live, not cosmetic. Every provider credential/`enabled`
field stays untouched, matching `SettingsService`'s own pre-existing
documented philosophy against in-flight DI re-wiring — composes on top
of `SettingsService` rather than replacing it.

`core/lifecycle/health_monitor.py`'s `HealthMonitor` polls
`psutil.Process` (already a project dependency) for CPU/RAM/uptime,
reads `ServiceManager.snapshot()`/`restart_count` for service health,
and publishes `health.updated` — non-blocking (`cpu_percent(interval=
None)`, no `time.sleep`), a plain `asyncio` task on the existing loop,
not a thread. `register_collector()` is a real, tested extension point
for GPU/plugin/network metrics; none are registered yet, deliberately
not stubbed out.

`core/lifecycle/runtime_ws_hub.py`'s `RuntimeWebSocketHub` is the first
real implementation of `docs/ARCHITECTURE.md` §6's WebSocket standard
— `infrastructure/api/routes/runtime_ws.py` mounts it at `/api/v1/ws`
with the exact documented envelope, 30s heartbeat, and `resume`/
`last_id` reconnect flow against a 60s bounded replay buffer (`None`
beyond the window signals a required REST refetch, never a silent
empty replay). Relays the eleven events this task group's five other
subsystems publish (`runtime.started/ready/stopping/shutdown`,
`service.started/stopped/failed`, `configuration.updated`,
`session.created/closed`, `health.updated`) — §6's existing category
table predates these five managers and is extended, not replaced (see
`docs/ARCHITECTURE.md`'s own changelog). Authentication uses a
`SessionManager` session id as the `token` query param
(`infrastructure/api/routes/sessions.py`'s `POST /api/v1/sessions`)
rather than building M14's full Bearer/JWT session-token
issuance/refresh/expiry here — that stays real, separate, future work
(§17); this is the real `Depends(get_current_session)` mechanism §5/§6
already reference, not a placeholder pending it.
`infrastructure/api/fastapi_server.py`'s `create_app()` now accepts an
optional DI `Container` and mounts both new routers only when one is
supplied, and `infrastructure/api/embedded_server.py`'s
`EmbeddedApiServer` embeds the ASGI app inside the existing PySide6/
qasync event loop (`app.py`'s `_run_gui`) rather than a second process
— the one real, running path this WebSocket relay needed to actually
be reachable from, not a placeholder nothing serves.

Runtime Integration wires all five into `RuntimeManager`
(`app.py`'s new `_register_task_group_b_hooks`, split out of
`_run_gui` to keep its statement count readable) in the exact
deterministic order requested — Configuration Manager → Service
Manager → Session Manager → remaining runtime services (Health
Monitor, WebSocket relay, embedded API server) → Application Ready —
and shuts down in reverse. `RuntimeManager` itself gained an optional
`event_bus` constructor parameter (every existing test still
constructs it with zero arguments) so `startup()`/`shutdown()` publish
`RuntimeStartedEvent`/`RuntimeShutdownCompleteEvent` at the very
start/end of each sequence — the two events the WebSocket relay's
`runtime.started`/`runtime.shutdown` categories needed and Task Group
A's addendum didn't yet define.

58 new tests across six files (`test_service_manager.py`,
`test_session_manager.py`, `test_configuration_manager.py`,
`test_health_monitor.py`, `test_runtime_ws_hub.py`,
`test_runtime_ws_route.py`) cover dependency-ordered startup/shutdown,
restart behavior, failure isolation (independent-service and
dependent-of-failed-service cases), session persistence/recovery
across two independent database instances, safe-section-only
live-reload, non-blocking health polling and collector extensibility,
and the real FastAPI WebSocket transport end-to-end (auth accept/
reject, event relay, resume/replay, resume-outside-window) via
`TestClient` against a real temp-file SQLite database, per
`docs/ARCHITECTURE.md` §18's own testing standard — no mocked network
anywhere in this task group's tests. Full suite: 524 passed, zero
regressions. mypy/ruff/black were diffed against a clean pre-task-
group baseline (`git stash`, not assumption) rather than eyeballed:
zero new findings in any category except four new `Need type
annotation` hits on the container's four new `providers.Singleton`
declarations, mechanically the same pre-existing, already-accepted
pattern (§15) every other service in that file already has, and six
new `PLC0415` lazy-import hits inside the new tests' function-scoped
imports, the same accepted convention every existing test in this
suite already uses. No dependency, acceptance-criterion, or numbering
conflict was found against M0–M27.

**Future Work** (explicitly out of scope for this task group, not
implemented): retrofitting the remaining services
(`VoiceService`/`HotkeyService`/`BrowserService`/`AutomationService`/
`SystemService`) onto `IService` and migrating their existing
lifecycle-hook ownership into `ServiceManager`; cascading
`ServiceManager.restart()` to a service's dependents; unifying
`RuntimeSession` with `Conversation`/LangGraph `thread_id` beyond the
optional-reference link this task group added; extending
`docs/ARCHITECTURE.md` §6's category table to the pre-existing
`voice`/`ai`/`automation`/`memory`/`progress`/`notification`
categories (only the five new managers' events are relayed today);
building `_run_api_only()` into a genuine headless runtime mode (the
embedded server exists only inside the GUI runtime path today); M14's
real Bearer/JWT session-token issuance this task group's session-id
auth stands in for. Bump this line whenever you edit the roadmap.*

*Aug 2026 addendum — Roadmap reconciliation pass (project-wide, ahead
of M9 Task Group C):* a full audit of `MASTER_ROADMAP.md`,
`IMPLEMENTATION_ROADMAP.md`, `ARCHITECTURE.md`, `TECH_STACK.md`,
`CHANGELOG.md`, and `CLAUDE.md` (the last does not exist in this
repository — confirmed, not created as part of this pass, since
creating one wasn't requested) against the actual repository state,
requested explicitly rather than assumed correct. Every milestone now
carries exactly one of four states — ✅ Completed, 🟡 Active, 🟠
Deferred, 🔴 Planned — applied consistently across §2's "Current
status" and §14's version timeline, replacing the previous mix of
✅/🟢/bare-🟡 with no fixed meaning for the latter two.

**§2 was stale and is now corrected.** It still read "Current version:
`0.5.2`" and "In progress: M7" with no mention of M8 or M9 at all —
current since the last time §2 itself was edited, predating the entire
M8 React migration and M9 Runtime Core work. Now reads `0.9.0` (this
`CHANGELOG.md`'s current entry) and lists M7/M8/M9 as the three active
milestones with their real, current phase/task-group status.

**§14's version timeline had a real defect, not just staleness**: `🟡`
was used for both M8 (genuinely active, partially shipped) and every
unstarted milestone from M10 through M23B — the same symbol meaning
two different things depending which row you read. M7/M8/M9 now read
`🟡 Active` with real status text; M10–M23B now read `🔴 Planned` —
mechanical, safe, and accurate, since none of them have any real
implementation (confirmed: no `agents/orchestrator` streaming work, no
search platform, no integrations layer, no plugin loader — all
genuinely unstarted).

**M8's own §8 entry gained a new Deferred Backlog subsection**,
requested explicitly rather than left implicit across scattered phase
checkboxes. Verified against the actual repository, not assumed from
prior task-tracker notes alone: `components/layout/notification-
layer.tsx` and `context-menu-layer.tsx` are real, honest, reserved
placeholders (`return null`, both docstring-labeled "renders nothing
today") — confirming Notification Center and the Context Menu system
are genuinely unbuilt, not merely undocumented. `stores/background-
tasks.store.ts` (54 lines) is a real display-only store backing the
Status Bar's "Background Task Progress" item, not the real supervised
queue M9 Task Group C's own Reliability module owns — the two were at
risk of being built twice; this pass records explicitly that the
frontend store stays display-only and the real manager is Task Group
C's job, not a second implementation. `frontend/src/features/
developer/` was confirmed to contain only the Developer Mode shell,
Module State Inspector, Startup Preview, and Voice State Preview — the
9 read-only viewers (Module Manager, Plugin Manager, API Center,
Update Center, Developer Console, Security Center, Backup/Restore,
System Information, Performance Monitor) are confirmed not yet ported.
None of this blocks M9 — M9's own documented dependency on M8 is
narrow (Developer Platform Tools' and Marketplace's *consumer*
surfaces, which already exist) and untouched by any deferred item
here.

**M9's Reliability/Plugin Platform/Developer Platform Tools modules**
now carry explicit Task Group letters (C/D/E respectively, continuing
from Task Groups A/B) in both `MASTER_ROADMAP.md` §8 and
`IMPLEMENTATION_ROADMAP.md` §5, where they previously read "Task Group
C and onward" with no per-module breakdown — the same letters
`IMPLEMENTATION_ROADMAP.md`'s own checklist now uses, so a reader can
go from either document to the same concrete scope.

No milestone was renumbered; no existing shipped-history entry (§3)
was altered; M10/M10A/M10B/M11 remain exactly as previously documented
— this pass changed status bookkeeping and added the missing Deferred
Backlog, not scope. `git status`/`git diff` confirm the actual
repository was the source of truth throughout — no doc content was
assumed correct without a matching file, test, or store checked
directly. Full `pytest`/`mypy`/`ruff`/`black` validation re-run clean
(zero regressions; see this pass's own commit for the exact numbers,
unchanged from M9 Task Group B's own validated baseline since no
source code changed in this pass — documentation only). Bump this line
whenever you edit the roadmap.*

*Aug 2026 addendum — M9 Task Group C (Background Task Manager, Crash
Recovery, Resource Manager):* closes out M9's Reliability module,
following directly from the roadmap reconciliation pass above.
Architecture unchanged — Python + FastAPI + Tauri; this addendum
documents implementation only.

`core/lifecycle/background_task_manager.py`'s `BackgroundTaskManager`
supervises a bounded-concurrency (`asyncio.Semaphore`) task queue with
per-task fault isolation, matching every other M9 lifecycle
component's own guarantee. A real, non-obvious bug surfaced by its own
test suite: cancelling a task still *waiting* for a concurrency slot
(never yet entered its coroutine's first scheduling turn) delivers
`CancelledError` without ever running a single line of that
coroutine's own body -- Python's documented behavior for `.throw()`
into an unstarted generator/coroutine is to re-raise immediately to
the caller, never entering the function. `_run()`'s own
`except CancelledError` handler is consequently unreachable for that
specific case; a `done_callback` registered at submission time is the
fallback that still marks the task `CANCELLED`, a no-op whenever
`_run()` already handled it itself. Publishes `task.started`/
`task.completed`/`task.failed`, relayed over the Runtime WebSocket API
-- the real backend queue the frontend's existing, display-only
`stores/background-tasks.store.ts` (see M8's Deferred Backlog) will
eventually read from, not a second, competing implementation.

`core/lifecycle/crash_recovery.py`'s `CrashRecoveryManager` writes a
"dirty" marker (`runtime_state.json`, via the existing
`config_dir`/JSON-config-store convention every other service like
`ApiCenterService` already uses) at the very start of startup and only
clears it once shutdown has genuinely finished. If startup finds the
marker already dirty, the previous run never reached a clean shutdown
-- detected, published as `CrashRecoveredEvent`. Explicitly does *not*
claim to automatically respawn a crashed process -- a process cannot
restart itself after crashing by definition, and building an external
supervisor/watchdog process is real, separate, future work (see this
addendum's Future Work), not silently implied by "Crash Recovery"'s
name. Proven under test across two independent
`CrashRecoveryManager`/marker-file instances, simulating a real crash
by simply never calling `mark_clean()` on the first one -- the same
shape a real hard process kill leaves behind.

`core/lifecycle/resource_manager.py`'s `ResourceManager` tracks
CPU/memory budgets (new `ResourceSettings`,
`core/config/settings.py` -- `max_cpu_percent`/`max_memory_mb`) by
subscribing to `HealthMonitor`'s existing `HealthUpdatedEvent` rather
than polling `psutil` a second time or running a competing poll loop --
avoiding both duplicate collection and a duplicate loop, per this
milestone's own "reuse `RuntimeManager`/`HealthMonitor` behavior
instead of duplicating logic" requirement. Publishes
`ResourceBudgetExceededEvent` only on the transition into violation
(proven under test: staying over budget on a later tick does not
re-publish; dropping under budget then crossing again does). Tracks
and alerts only -- nothing throttles or kills a service on a breach,
matching Reliability's "observability, not an autonomous scheduler"
scope; real enforcement is M22 Edge AI Platform's future Resource
Allocation module.

`app.py`'s `_register_task_group_c_hooks` (new, mirroring Task Group
B's own `_register_task_group_b_hooks` sibling) wires all three into
`RuntimeManager` in deterministic order: Crash Recovery's dirty-check
runs immediately after Configuration Manager (priority 1, before
Service Manager) so every later manager boots with crash status
already known; Background Task Manager and Resource Manager join at
the very end of startup (priorities 10-11). Shutdown reverses this --
Resource Manager and Background Task Manager stop first (priorities
0-1), and Crash Recovery marks the run clean *last of all* (priority
7), after every other shutdown hook has actually finished, so "clean"
is accurate. Task Group B's own five shutdown-hook priorities were
renumbered from 0-4 to 2-6 (pure, safe, in-place renumbering within
the same method already being extended -- priorities are relative ints
re-declared fresh at every boot, never persisted, so this carries no
migration concern) to make room. `RuntimeWebSocketHub`'s
`EVENT_TYPE_NAMES` gained five more entries
(`runtime.crash_recovered`, `task.started/completed/failed`,
`resource.budget_exceeded`), extending `docs/ARCHITECTURE.md` §6's
category table the same way Task Group B's own five did.

29 new tests across three files (`test_background_task_manager.py`,
`test_crash_recovery.py`, `test_resource_manager.py`) cover bounded
concurrency, fault isolation, both cancellation code paths (mid-run and
pre-first-run), crash detection across independent marker-file
instances, corrupt-marker resilience, and budget-transition-only event
publishing. One existing test
(`test_runtime_ws_hub.py::test_every_documented_event_type_is_mapped`)
was updated to include the five new relayed categories -- an expected
extension of Task Group B's own event map, not a regression. Full
suite: 542 passed, zero regressions. mypy/ruff/black diffed against a
clean pre-task-group `git stash` baseline: zero new findings outside
two more `Need type annotation` hits on the container's two new
`providers.Singleton` declarations (`crash_recovery_manager`,
`background_task_manager` -- the same pre-existing, already-accepted
§15 pattern every other service in that file already has) and one more
`PLC0415` lazy-import hit inside the new tests, the same accepted
convention every existing test already uses. No dependency,
acceptance-criterion, or numbering conflict was found against M0–M27.

**Future Work** (explicitly out of scope for this task group, not
implemented): an external supervisor/watchdog process for genuine
automatic process restart after a crash (this task group's Crash
Recovery only detects and reports, per its own module docstring);
GPU/disk collectors for `HealthMonitor` (Resource Manager's
`register_budget()` already supports them once a collector exists);
enforcement (throttle/kill) on a Resource Manager budget breach;
persisting/resuming the Background Task Manager's queue across a
restart; Task Group D (Plugin Platform) and Task Group E (Developer
Platform Tools), M9's two remaining modules. Bump this line whenever
you edit the roadmap.*

*Aug 2026 addendum — M9 Task Group D (Plugin Platform):* closes out M9
in full except one module -- Task Group E (Developer Platform Tools) is
now the only work left in this milestone. Architecture unchanged --
Python + FastAPI + Tauri; this addendum documents implementation only.
New package `core/plugins/` (`sdk.py`, `manifest.py`, `loader.py`,
`sandbox.py`, `extension_api.py`, `permissions.py`, `registry.py`,
`store.py`, `marketplace.py`), plus a new Platform Abstraction Layer
(`core/interfaces/platform.py` + `infrastructure/platform/adapter.py`)
added specifically for this task group's Universal Compatibility
requirement -- Windows is the only implemented target, but nothing
above the PAL's `IPlatformAdapter` boundary branches on OS directly, so
a future Linux/macOS adapter is a second implementation of that one
port, not a redesign.

`sdk.py`/`manifest.py` (Plugin SDK) -- `IPlugin`'s three lifecycle hooks
(`on_load`/`on_start`/`on_stop`, mirroring `IService`'s own "never a
seventh method" rule), the fixed 10-scope permission vocabulary
`docs/ARCHITECTURE.md` §10 already specified, a hand-rolled semver/
range comparator (no new dependency), and `PluginManifest` (pydantic,
frozen) extended with the Universal Compatibility fields requirement 5
asked for: `supported_os`, `supported_arch`, `required_capabilities`,
`min_jarvis_version` -- all platform-neutral by default (a manifest that
omits them is loadable everywhere this JARVIS build knows about).

`loader.py` (Plugin Loader) -- discovery, Kahn's-algorithm dependency
ordering (same technique `ServiceManager._ordered_names` already uses,
deliberately more fault-tolerant on a cycle than that method: a plugin
set is third-party, so a cyclic/missing dependency isolates just the
affected plugin(s), never raises across the whole batch), full
compatibility checking (`sdk_range`, `min_jarvis_version`,
`supported_os`/`supported_arch`, `required_capabilities` -- all through
`IPlatformAdapter`, never a raw `sys.platform` check), and real hot
reload. A genuine bug its own test suite caught:
`importlib.util.spec_from_file_location`'s `.pyc` cache validates on
mtime+size, and two plugin source revisions of identical length
rewritten within the same filesystem mtime tick are indistinguishable
to it -- reload now reads source and compiles fresh every call,
bypassing that cache entirely.

`sandbox.py` (Secure Plugin Sandbox) -- two real tiers, not one
mechanism pretending to be both. In-process (default): fault-isolated,
timeout-bounded (`asyncio.wait_for`) hook execution, the same guarantee
every other M9 lifecycle component makes. Out-of-process (opt-in): a
real `multiprocessing` (`spawn`) child process reachable only over a
pipe, so a crash or hang there cannot corrupt the parent; `psutil`-based
monitor-and-terminate enforces a CPU/memory budget -- a real, working,
but detect-and-kill control on a polling interval, not a kernel-level
hard cap, documented as such. Known, documented v1 limit: a
process-isolated plugin's `on_load` receives a minimal
`MinimalPluginContext` (identity only), not the full in-process
`PluginContext` -- a live `EventBus` reference cannot cross a process
boundary by value; a real IPC-relayed Extension API for that tier is
Future Work, below.

`extension_api.py` (Extension API) -- `PluginContext`, the one channel a
plugin gets: permission-gated `filesystem` (confined to the plugin's
own data dir, real path-traversal check), `network` (declaration only --
no request mediation yet), `hotkeys` (real, delegates to the existing
`HotkeyService`, namespaced `plugin.<id>.<semantic>` so two plugins
can't collide), `notifications` (publishes a real
`PluginNotificationEvent`); unrestricted `events` (a plugin's own
namespaced `PluginCustomEvent`, never a raw core event type, so it
can't impersonate a first-party component) and `commands` (only IDs the
plugin's own manifest declared); `config` (validated against the
manifest's `settings_schema`); `platform` (read-only capability
queries). UI extension points are scoped honestly: the frontend's
`ApplicationRegistry`/`ContributionRegistry` live in a separate process
with no in-process bridge, so this module exposes the plugin's
manifest-declared UI surface for a future FastAPI route to serve, the
same "declare it, the frontend renders it" pattern first-party modules
already use -- it does not fake a live call into them.

`permissions.py` (Permission Model) -- the real `IPermissionChecker`.
Least-privilege by construction: a declared scope starts `PENDING`,
`is_granted()` returns `False` until an explicit `grant()`. No
interactive UI exists yet (that's Task Group E's Developer Platform
Tools), but the workflow itself is real and persisted (`config_dir`
convention) -- declare -> pending -> grant/deny, each a real state
transition with an audit trail (bounded `deque`) and a published event
(`PluginPermissionGrantedEvent`/`PluginPermissionDeniedEvent`);
`pending()` is the actual queue a future approval surface would read
from.

`registry.py` (Plugin Registration System) -- `PluginRegistry`,
composing all of the above the same way `ServiceManager` composes
`IService`. `discover_and_load_all()` never lets one plugin's failure
block another's -- every failure mode from every earlier phase
(incompatibility, a Sandbox-isolated exception, an unresolved
dependency) lands as that one plugin's own `FAILED` state. Real
rollback support: `update()` backs up the previous on-disk version
before staging the new one in; if the new version fails to load, the
backup is restored and reloaded automatically -- "a failed plugin update
reverts to the last-known good version without operator intervention,"
the Plugin Safe Core Architecture requirement, verified under test.
`disable()` also calls the context's `hotkeys.unregister_all()` so a
disabled plugin never leaves an orphaned global hotkey bound.

`store.py` (Plugin Store Foundation) -- turns a directory or `.zip`
(Zip Slip-guarded extraction) into a Registry-installable directory.
Two independent real checks: integrity (`checksums.json`, SHA-256,
order-independent) and authenticity (`ISignatureVerifier`;
`UnsignedAllowedVerifier` does a genuine Ed25519 verify via
`cryptography` -- already a pinned dependency -- when a
`manifest.json.sig`/`publisher.pub` pair exists, and otherwise allows
unsigned only when configured to, matching the roadmap's own "no hosted
infra for v1" position). Offline by construction -- nothing in this
module makes a network call.

`marketplace.py` (Marketplace Foundation) -- `IPluginRepository` is the
seam a future `GitHubPluginRepository`/`CloudPluginRepository` plugs
into without changing anything above it (search/browse/categories/
ratings); `LocalPluginRepository` is the real v1 implementation of the
exact `{name, description, author, versions[], sdk_range, homepage}`
JSON index shape this section's own Plugin Store bullet already
specified. `InMemoryReviewStore` genuinely accepts/lists/averages
ratings for the runtime's own lifetime (not persisted across a restart,
no real user-identity system beyond a caller-supplied reviewer string --
both honest, documented v1 limits).

`app.py`'s new `_register_task_group_d_hooks` (mirroring Task Groups
B/C's own sibling methods) wires `PluginRegistry` into `RuntimeManager`
as the outermost layer over an already-running core -- Plugin Safe Core
Architecture's own framing: plugins start *last* (priority 12, after
Task Group C's 10-11) and stop *first* (priority -1, before Task Group
B's own priority-0-and-up chain), so no plugin is ever running against
a service mid-teardown. A no-op when `settings.plugins.enabled` is
false. `RuntimeWebSocketHub`'s `EVENT_TYPE_NAMES` gained eleven more
entries (`plugin.discovered/loaded/load_failed/unloaded/enabled/
disabled/installed/uninstalled/updated/permission_granted/
permission_denied`), extending `docs/ARCHITECTURE.md` §6's category
table the same way Task Groups B and C's own additions did.

199 new tests across twelve files (`test_platform_adapter.py`,
`test_plugin_sdk.py`, `test_plugin_manifest.py`, `test_plugin_loader.py`,
`test_plugin_sandbox.py`, `test_plugin_extension_api.py`,
`test_plugin_permissions.py`, `test_plugin_registry.py`,
`test_plugin_store.py`, `test_plugin_marketplace.py`, plus a real
end-to-end `tests/integration/test_plugin_platform_e2e.py` loading a
real `tests/fixtures/plugins/hello_world` plugin through the entire
Loader -> Sandbox -> Permission Model -> Registry stack -- proving this
milestone's own acceptance criterion, "a hello-world plugin registers a
slash command and a hotkey," including the full least-privilege
workflow: first boot denied while pending, then genuinely running once
granted). One existing test
(`test_runtime_ws_hub.py::test_every_documented_event_type_is_mapped`)
was updated to include the eleven new relayed categories -- an expected
extension, not a regression. Full suite: 741 passed (up from 542), zero
regressions; frontend: 293 passed, unaffected (this task group is
backend-only). mypy/ruff/black diffed against a clean pre-task-group
`git stash -u` baseline (including untracked files, so the diff is
genuinely clean, not contaminated by this task group's own new files):
exactly one new finding each in `container.py` (`platform_adapter`'s
`Need type annotation`, the same pre-existing, already-accepted §15
pattern every other string-path `providers.Singleton` in that file
already has) and `app.py` (one more `PLC0415` lazy-import hit inside
the new hook method, the same accepted convention Task Groups B and C's
own hook methods already use) -- zero new findings anywhere else across
the full 299-file `src/` tree.

**Future Work** (explicitly out of scope for this task group, not
implemented): a real IPC-relayed Extension API for process-isolated
plugins (today limited to `MinimalPluginContext`); actual
outbound-request mediation/quota enforcement for the `network`
permission scope (today a declaration check only); a hosted, signed
Plugin Store index and a real `GitHubPluginRepository`/
`CloudPluginRepository` (today local-file-only, by the roadmap's own
"no hosted infra for v1" design); persisted, multi-session ratings/
reviews with real user identity; an interactive permission-approval UI
(the workflow and its audit trail are real today; only the visual
surface is Task Group E's Developer Platform Tools to build); Task
Group E (Developer Platform Tools), M9's one remaining module. Bump
this line whenever you edit the roadmap.*

*Aug 2026 addendum — M9 Task Group E (Developer Platform Tools):*
closes out M9 in full -- **Milestone 9 is now 100% complete across all
five task groups.** Architecture unchanged -- Python + FastAPI + Tauri;
this addendum documents implementation only.

`core/devtools/` -- four small, focused components, each a thin
wrapper over already-real M9 infrastructure rather than a second data
source: `debug_console.py`'s `DebugConsole` attaches as a real loguru
sink (the exact mechanism `core/logging/logger.py`'s own JSON/console/
file sinks already use) into a bounded, filterable buffer -- "Debug
Console" (query it) and "Live Logs" (watch it grow via a published
`DebugLogCapturedEvent` per line) are one mechanism, not two.
`performance_profiler.py`'s `PerformanceProfiler` subscribes to
`HealthMonitor`'s existing `HealthUpdatedEvent` and keeps real
time-series history per metric -- `HealthMonitor.snapshot()` already
gave the latest value; this adds the trend. `state_inspector.py`'s
`StateInspector` combines `ServiceManager.snapshot()` (Task Group B)
and `PluginRegistry.snapshot()` (Task Group D) into one view.
`api_inspector.py`'s `ApiInspector` is a real Starlette middleware
recording this app's own `/api/v1/*` request/response metadata --
method, path, status, duration only, deliberately never bodies or
headers (a secret could be in either).

`infrastructure/api/auth.py` -- the real `Depends(get_current_session)`
Bearer-auth dependency `docs/ARCHITECTURE.md` sections 5/6 have
referenced by name since Task Group B, but that no route had actually
depended on until now (both prior real routes,
`/api/v1/health`/`/api/v1/sessions`, are documented, deliberate
exceptions to needing it). Validates the same `SessionManager` session
id `RuntimeWebSocketHub.authenticate()` already validates for the
WebSocket -- one real session concept, two transports. Also adds the
real `{data, meta}` `Envelope` response wrapper section 5 specifies.

`infrastructure/api/routes/plugins.py` -- "the backend index/install/
uninstall API that M8's Marketplace UI renders," this module's own
words for what M9's Plugin Platform module still needed after Task
Group D shipped the domain layer underneath it: full plugin lifecycle
(list/get/enable/disable/install/uninstall/update), permission
management (grant/deny/revoke, a pending queue, an audit log), and
marketplace browse/search/categories/get/reviews -- every route a thin
FastAPI layer over exactly one `PluginRegistry`/`PluginStore`/
`PermissionModel`/`Marketplace` method call. The first real resource
routes to follow section 5's contract in full, resolving the two
documented exceptions `/api/v1/sessions` needed (see section 5's own
"M10+ resource routes are expected to follow this section exactly,
unwinding both exceptions" note -- Task Group E turned out to be the
one that did, not M10).

`infrastructure/api/routes/devtools.py` -- REST reads over the four
new `core/devtools/` components, plus Plugin Diagnostics: one combined
view (a plugin's status, health, recent related logs filtered by
plugin id, and its own permission audit trail) rather than a fourth
data source alongside the three this task group already built.

`app.py`'s new `_register_task_group_e_hooks` wires Debug Console and
Performance Profiler into `RuntimeManager` as observability that
bookends every other hook: startup priority -1 (one earlier than
Configuration Manager's own 0, so capture starts before anything else
can log or report health) and shutdown priority 8 (one later than Task
Group C's Crash Recovery mark-clean at 7, so capture continues until
the very end). `RuntimeWebSocketHub.EVENT_TYPE_NAMES` gained the eleven
`plugin.*` categories Task Group D's events had defined but never
wired to a relay, plus `devtools.log_captured`.

A real, Windows-first-breaking bug in Task Group D was found and fixed
by these same tests running for the first time against a genuine
Windows machine rather than Task Group D's own hardcoded-`"x86_64"`
test double: `platform.machine()` reports `"AMD64"` on Windows, not
`"x86_64"` -- every plugin manifest's *default* `supported_arch` list
was silently rejecting every real Windows x86_64 plugin install.
`infrastructure/platform/adapter.py`'s `DefaultPlatformAdapter.info()`
now normalizes the OS-reported architecture string to this project's
own canonical vocabulary at the Platform Abstraction Layer boundary --
exactly the kind of quirk that layer exists to absorb, so nothing
above it ever needs to know Windows spells it differently.

74 new tests across nine files, including a real end-to-end test
(`tests/integration/test_devtools_platform_e2e.py`) proving the new
REST API genuinely drives Task Group D's `PluginRegistry`/
`PermissionModel` *and* that the result is relayed over the real
Runtime WebSocket API -- install over REST, watch `plugin.installed`/
`plugin.load_failed` arrive over the socket (the plugin's own `on_load`
genuinely exercises a permission-gated capability, so the failure is
real, not staged); grant the permission over REST, watch
`plugin.permission_granted` arrive; enable over REST, watch
`plugin.loaded`/`plugin.enabled` arrive; read diagnostics over REST and
see the same final state. Full suite: 815 passed (up from 741), zero
regressions; frontend unaffected (this task group is backend-only).
mypy/ruff/black diffed against a clean pre-task-group `git stash -u`
baseline: every finding category's count is byte-for-byte unchanged
except `PLC0415` (+24, the same accepted lazy-import-inside-test-
fixture convention `test_runtime_ws_route.py` already established) --
zero new findings of any other kind, and zero new mypy findings at
all.

**Future Work** (explicitly out of scope for this task group, not
implemented): a real interactive permission-approval UI (the workflow
and its audit trail this task group's own REST routes expose are real
today; only a visual surface consuming them is future work, most
naturally M8's React frontend's Developer Mode panels); Live Logs'
real-time relay is fire-and-forget per line today, not batched --
acceptable for a developer-only tool, revisit if it ever needs to
handle sustained high-volume logging; Performance Profiler's history is
in-memory only, not persisted across a restart; API Inspector has no
REST-exposed clear/reset endpoint (only Debug Console does). None of
M9's own five task groups have further scope remaining -- the next
work in this milestone's own numbering is M10 (AI Orchestrator). Bump
this line whenever you edit the roadmap.*

*Aug 2026 addendum — M10 (AI Orchestrator, partial):* M10 formally
depends on M10A (Universal Search & Knowledge Platform) and M14
(Authorization Engine), §8, neither of which had started when this pass
began. Rather than block, this pass shipped the full subset buildable
without them, extending M5A's `AgentOrchestrator` directly (no rewrite),
and documented the M10A/M14/M16-dependent remainder as explicitly
deferred -- the same "Completed / Deferred with a documented reason"
discipline this project has applied since the M0-M9 Project Completion
Audit. **M10 is not 100% complete; this addendum documents a partial,
honest milestone, not a completed one.**

Intent Engine -- `agents/nodes/intent_classifier.py`, a new node before
`planner` classifying the request into `tool_use` / `direct_answer` /
`clarification_needed` with a confidence score. Diagnostic only in this
pass: nothing yet reads `intent`/`intent_confidence` to change graph
routing, since M10A/M10B (the milestones expected to give the
classification real signal to act on) haven't shipped either -- recorded
in `AgentState` and available to any future consumer without a second
migration.

Context Engine (scoped) -- `agents/nodes/context_engine.py`, assembles
context from M3 Memory (`MemoryService.recall`) before planning starts,
closing the pre-M10 gap where no node ever queried memory ahead of
planning. M10's own spec describes Context Engine pulling from "M10A's
knowledge substrate and M3 Memory" -- M10A doesn't exist, so only the M3
half is real here; the knowledge-graph half is deferred, not silently
dropped.

Parallel tool dispatch -- Milestone 10 Acceptance Criterion 1, also
closing out M7 Phase 3's deferred cross-tool-parallelism scope, which
this milestone's own Objective absorbed rather than reopening M7 for it.
`tool_selector.py` gained a `tool_parallel` decision shape (a list of
independent `{tool, args}` calls) alongside the pre-existing `tool`/
`final` ones -- additive, not a replacement; the single-tool shape is
byte-for-byte unchanged, so every M5A-era unit test kept passing
unmodified. `tool_executor.py` dispatches a `tool_parallel` batch
concurrently via the existing `gather_with_concurrency` utility (already
proven in M7 Phase 2's automation executor), bounded by
`AgentSettings.max_parallel_steps` -- declared in M7 "for forward
compatibility only" and read by zero code until this pass activated it.

Permission Validation (interim) -- Milestone 10 Acceptance Criterion 3.
`agents/permission.py`'s `AgentPermissionGate` plus a new
`permission_validator` node inserted between `tool_selector` and
`tool_executor` in the graph: the one enforcement point every proposed
tool call (single or parallel) now passes through before execution,
replacing the pre-M10 gap where only `run_automation` had any permission
awareness at all, and that only internal to `AutomationService` --
invisible to the graph itself, and every other tool (memory writes,
browser navigation, ...) executed with no check whatsoever. Explicitly
interim: M10's own spec routes Permission Validation through M14's
Authorization Engine "once that milestone ships" -- M14 hasn't.
`AgentPermissionGate` is a single, narrow class specifically so that
swap means replacing its `authorize()` body later, not touching the
graph wiring that calls it. Policy today is declarative and
settings-driven: `AgentSettings.confirm_required_tools` (default
`{"run_automation"}`), reusing `features/automation/permission.py`'s
existing `ConfirmationCallback` protocol rather than defining a second,
identical one.

Real token-level streaming -- Milestone 10 Acceptance Criterion 2.
`AgentOrchestrator.stream()` previously re-chunked an already-composed
string word-by-word regardless of path (§15's own documented
limitation). It now yields real per-token output from
`ILLMProvider.stream()` (already real at the provider layer for OpenAI/
Ollama/Gemini -- just never called from the streaming path before) for
the dominant case, an answer composed from tool results. Mechanism: a
second, responder-less compiled graph variant
(`build_agent_graph(..., include_responder=False)`, routing the "final"/
"done" branches straight to `END`) runs the identical intent/context/
plan/tool-select/permission/execute/critique pipeline, then
`AgentOrchestrator.stream()` calls `llm.stream()` directly on the same
prompt `responder_node` would have used --
`agents/nodes/responder.py`'s `build_final_response_prompt`, extracted
as a pure function shared by both paths so they can't drift. One path
remains a documented, scoped exception, not a hidden gap: `tool_selector`'s
"final" shortcut (no tool needed at all) still composes its answer
synchronously inside a JSON decision object, and JSON-embedded text
can't be cleanly token-streamed without restructuring tool selection
itself -- that path still replays its precomposed text in the pre-M10
chunked style. Verified for real, not just asserted: the integration
test exploits `ScriptedFakeLLM`'s per-word streaming granularity against
the old chunked-replay's 4-word grouping -- a composed 5-word sentence
arrives as 5 chunks through the new real path and would only arrive as 2
through the old one, so the chunk count itself proves which path ran.

Decision Engine -- `responder` node (and the real-streaming path above)
now write `response_mode` (`"direct"` for the tool_selector shortcut,
`"composed"` for a real answer composition) into `AgentState`, per this
milestone's own description of Decision Engine as "the responder node's
successor, deciding final response shape and routing."

`core/lifecycle/runtime_ws_hub.py`'s `EVENT_TYPE_NAMES` gained one more
category, `agent.step` -- real-time Agent Trace visibility over the same
`/api/v1/ws` relay Task Group B built, not a second, parallel channel.
Per-token events were deliberately *not* added to this relay (one WS
frame per LLM token would mean hundreds of frames per response); the
token-level half of "real streaming over M8's WebSocket layer" is
`/api/v1/agent/stream`'s Server-Sent Events response instead.

`infrastructure/api/routes/agent.py` -- `POST /api/v1/agent/invoke`
(blocking, `{data, meta}` envelope) and `POST /api/v1/agent/stream`
(real token-level SSE -- a documented, scoped exception to the envelope
rule, the same way `/api/v1/sessions` already is, since an SSE body is a
sequence of `data: <chunk>` frames by the nature of the transport, not
one JSON object). Same `Depends(get_current_session)` Bearer auth as
`routes/plugins.py`/`routes/devtools.py`.

A genuine, self-caught test-design bug surfaced while building the
streaming integration test: the first attempt asserted `len(chunks) > 1`
as proof of real token streaming, which both the new real path and the
old chunked-replay path would satisfy for a multi-word sentence --
useless as a distinguishing assertion. Fixed by computing the exact
expected chunk count under each path's own grouping rule (5 for
per-word real streaming, 2 for 4-word chunked replay) and asserting the
exact count, so the test can only pass if the real path actually ran.

Deferred, documented, not silently dropped: Context Engine's
knowledge-graph half (needs M10A); Learning/Feedback closing through
M16's Reflection Engine (needs M16); Permission Validation's final
M14-routed form (needs M14; `AgentPermissionGate` is the interim single
enforcement point); Intent Engine gating graph routing instead of just
recording a diagnostic (needs M10A/M10B for real signal); `tool_selector`'s
"final" shortcut path's real token streaming (needs restructuring tool
selection itself); wiring the PySide6 Agent Trace view or a React
frontend surface to `/api/v1/agent` (M8's own remaining phases,
unchanged by this pass).

839/839 tests passing (unit + integration) -- up from 815 in the M9
Task Group E release (+24: new unit tests for Intent/Context Engine,
parallel dispatch, and Permission Validation; a new `AgentPermissionGate`
unit suite; a new `/api/v1/agent` route test suite; three new
orchestrator integration tests exercising parallel dispatch, permission
denial, and real streaming end-to-end) -- zero regressions. One
pre-existing test, `test_runtime_ws_hub.py::test_every_documented_event_type_is_mapped`,
needed updating for the new `agent.step` category -- an expected,
mechanical update, not a design gap. Ruff/mypy findings proportional to
the pre-existing accepted baseline: the four line-length findings this
pass's own new code introduced were fixed outright rather than absorbed
into the baseline; every remaining new finding is `PLC0415`, matching
this codebase's already-established lazy-import convention -- zero new
finding categories of any kind. Version bumped `0.12.0` -> `0.13.0`,
continuing the one-minor-bump-per-milestone-scope-of-work granularity
§14's versioning-granularity note already documents.

*Aug 2026 addendum — M10A (Universal Search & Knowledge Platform):*
unlike M10, M10A's own declared dependencies (M3 Memory Platform, M5A
Agent Orchestrator exposure) were both already shipped when this pass
began, so this milestone was buildable to near-full completion in one
pass rather than a partial one. The single exception, documented not
dropped: File Search needs M11B's File Manager surface, which doesn't
exist yet.

**Implementation principles honored throughout:** every new component
extends an existing one rather than introducing a parallel system --
`RuntimeManager`, `ServiceManager`, `MemoryService`, `ChromaVectorStore`,
`AgentOrchestrator`, Context Engine, `EventBus`, the Runtime WebSocket
Hub, `PluginRegistry`, and the Tool Registry are all reused as-is, none
rewritten.

Universal Search / Search Provider Registry -- `services/search_service.py`'s
`SearchService` owns a provider registry (`register_source`/
`unregister_source`/`get_sources`) so a future module or plugin can add
a new `ISearchSource` (new `core/interfaces/search.py` Protocol)
without `SearchService` itself ever changing -- no hardcoded source
list, no `isinstance` dispatch on source type. Three sources registered
today: `MemorySearchSource` (wraps `MemoryService.search`),
`KnowledgeSearchSource` (wraps `KnowledgeService.search`), and
`CommandSearchSource` (agent tools, resolved once at the DI composition
root via the existing `build_tool_registry`, plus plugin-declared
commands read *live* from `PluginRegistry.list_manifests()` on every
query -- a plugin installed after `SearchService` was first wired still
shows up, not a value snapshotted once and left stale). `SearchResult`
(also in `core/interfaces/search.py`) is deliberately extensible per
this pass's own design requirement: `confidence` and `reason` fields
exist now, unpopulated, so a future milestone can add real AI reranking
without changing the model's shape or any caller's field access.

Knowledge Platform / Knowledge Graph -- three new tables in the
existing `infrastructure/database/models.py` (`Base.metadata.create_all()`
idempotent boot-time creation, no new persistence framework, no Alembic
migration -- matching M3's own established convention):
`KnowledgeEntity`, `KnowledgeRelationship` (a `superseded` flag
implements the correction primitive below -- old edges are marked
superseded, never hard-deleted, so history stays auditable), and
`KnowledgeEntityMemory` (a join table mirroring `MemoryTag`'s own
shape). `KnowledgeRepository` mirrors `MemoryRepository`'s exact
method-by-method pattern. `services/knowledge_service.py`'s
`KnowledgeService` communicates with the memory store *only* through
`MemoryService`'s existing public interface (`recall`/`browse`/
`summarize`/`set_pinned`) -- never touches memory SQL rows directly.
"Persistent Memory" reuses `MemoryService.set_pinned` rather than
inventing a second durability mechanism, since M3's existing pinned
memories already skip retention-policy expiry. "Reflection Foundation"
(`learn_from_recent_memories()`) is deliberately on-demand only -- no
`RuntimeManager` hook, no scheduler, no additional lifecycle manager;
wiring it to M7's existing Scheduler for periodic execution is
explicit future work, not built here. Entity/relationship extraction
uses the same LLM JSON-decision pattern the agent nodes already
established (`jarvis.agents.prompting`'s `safe_complete`/
`parse_json_object`, relocated to `jarvis.utils.llm_json` during this
pass specifically so `KnowledgeService` -- a `services` module -- could
reuse them without creating a `services` -> `agents` dependency, since
this project's layering rule runs the other way: `agents` depends on
`services`, never the reverse; `agents/prompting.py` now re-exports
both names unchanged so every existing node import keeps working).

Correction / scoped Learning (Acceptance Criterion 3) --
`KnowledgeService.correct(statement)` extracts the corrected fact(s)
from *statement* using the same extraction pipeline, then
`KnowledgeRepository.supersede_relationships()` marks every prior
`(subject, predicate)` edge superseded before inserting the new one at
`confidence=0.95`. Verified for real: a `meeting occurs_on Wednesday`
relationship, corrected to `Thursday`, and `get_entity_detail("meeting")`
returns Thursday afterward -- not merely asserted, executed against a
real SQLite database. This is a scoped correction primitive, not the
general-purpose Learning Engine a future milestone might build --
documented as deferred, not implemented as if it were the same thing.

ChromaDB integration -- the *existing* single Chroma collection is
reused as-is; entity records are upserted into it tagged
`record_type: "knowledge_entity"` metadata so semantic entity lookup
can filter separately from (or alongside) memory content. No second
vector store, no new adapter class.

Agent / Context Engine integration -- new `agents/tools/knowledge_tools.py`
(`ask_knowledge`/`search_knowledge`, mirroring `memory_tools.py`'s
shape exactly), wired into `build_tool_registry()` as a new optional
`knowledge` parameter -- additive, every existing call site unaffected.
`agents/nodes/context_engine.py` gained an optional `knowledge`
parameter too: when supplied, it now also queries the knowledge graph
for entities/relationships related to the prompt, closing the
knowledge-graph-half deferral M10's own completion report documented.
`AgentOrchestrator`, `build_agent_graph`, and the DI container's
`agent_orchestrator` provider all thread `knowledge` through --
`KnowledgeService` is exposed as an agent tool the same way every
other service already is, per M10A's own declared dependency on M5A.

Runtime integration -- `KnowledgeService`/`SearchService` are plain DI
singletons with no background loop of their own, the same lifecycle
class `MemoryService` already occupies -- no `RuntimeManager` changes,
no new lifecycle manager.

REST API / WebSocket integration -- new `infrastructure/api/routes/knowledge.py`:
`POST /api/v1/search` (Universal Search), `GET /api/v1/knowledge/entities/{name}`,
`GET /api/v1/knowledge/ask`, `POST /api/v1/knowledge/correct`,
`POST /api/v1/knowledge/learn` (the on-demand Reflection Foundation
trigger), `GET/POST /api/v1/knowledge/export|import` -- same
`Depends(get_current_session)` Bearer auth + `{data, meta}` envelope
convention as `routes/plugins.py`/`routes/devtools.py`/`routes/agent.py`.
`core/lifecycle/runtime_ws_hub.py`'s `EVENT_TYPE_NAMES` finally
realizes the `memory` category (`memory.updated`, `memory.recalled`)
`docs/ARCHITECTURE.md` §6 has documented as a target since before any
of the Milestone 9 managers existed, plus a new `knowledge` category
(`knowledge.entity_updated`, `knowledge.correction_applied`) -- both
verified over the real relay in
`tests/integration/test_knowledge_platform_e2e.py`, not just asserted
at the unit level (REST write -> real service -> real WebSocket read,
the same discipline `test_devtools_platform_e2e.py` established).
`MemoryService` gained an optional `event_bus` constructor parameter to
publish these -- additive, defaulting to `None`, every existing call
site unaffected.

Permission Model -- no new scopes introduced. Plugin access reuses M9's
already-defined `memory.read`/`memory.write` permission scopes, since
knowledge is conceptually an extension of memory for permission
purposes; agent-tool-initiated knowledge reads/writes stay ungated,
matching `remember`/`forget`'s own existing ungated precedent.

Testing -- 49 new tests across seven files (`test_knowledge_repository.py`,
`test_knowledge_service.py`, `test_search_service.py`,
`test_search_sources.py`, `test_knowledge_tools.py`,
`test_knowledge_route.py`, `tests/integration/test_knowledge_platform_e2e.py`,
plus two new Context Engine tests in `test_agent_nodes.py`), including
one integration test per Acceptance Criterion, each exercised against a
real temp-file SQLite database and the real DI container, not doubles
of each other. Full suite: 888 passed (up from 839), zero regressions.
Ruff/mypy diffed against a clean pre-milestone baseline using the
established `git stash -u` methodology: mypy 266 -> 266, byte-for-byte
unchanged after two real fixes in `knowledge_service.py` (a
`dict[str, Any]` annotation for a Chroma metadata dict mixing string
and `list[float]` values, and removing seven copy-pasted `# type:
ignore[assignment]` comments that turned out unnecessary in this file's
context); ruff findings proportional to the pre-existing accepted
baseline, entirely `PLC0415` (the established lazy-import convention)
plus a handful of genuinely new, immediately-fixed issues (two unused
imports, one import-ordering fix, one unused-unpacked-variable rename)
-- zero new finding categories left unresolved. Version bumped
`0.13.0` -> `0.14.0`, continuing the one-minor-bump-per-milestone-scope
granularity.

*Aug 2026 addendum — M10B (Intelligence Layer):* extends M10A's
architecture directly rather than introducing a parallel system --
`IntelligenceService`/`IntelligenceRepository` mirror
`KnowledgeService`/`KnowledgeRepository`'s exact shape (same
`database`/`event_bus` constructor pattern, same repository-per-session
pattern, same lazy event-import idiom), and Goal Manager registers into
`SearchService`'s existing provider registry as a fourth source
(`GoalSearchSource`) with zero changes to `SearchService` itself -- the
extensibility M10A's registry design was built for. No `RuntimeManager`
changes, no new lifecycle manager, no background scheduler.

Goal Manager -- `Goal` (self-referential `parent_goal_id` FK,
`ondelete="CASCADE"`) in the existing `infrastructure/database/models.py`;
`IntelligenceRepository` mirrors `KnowledgeRepository`'s method-by-method
pattern. `IntelligenceService.update_goal_progress()` auto-completes a
goal (stamps `completed_at`, clamps to 100%) once progress reaches
100%, publishing `goal.updated` with an `action` field
(created/progress_updated/completed/deleted) -- one relay name, not one
event class per action, matching `memory.updated`'s already-established
shape rather than the Plugin*Event pattern of one class per action.
Verified for real: three separate `IntelligenceService` instances
constructed against the same database, proving persistence survives
across service instantiation, not merely in-memory state within one
object's lifetime.

Routine Learning -- deliberately deterministic, not LLM-driven pattern
mining: `Routine` rows keyed by nullable `hour_of_day`/`day_of_week`
(`None` on either side wildcard-matches), `reinforce_routine()`
increments `observation_count` and raises `confidence` by a fixed step
capped at 1.0 on a repeated observation at the same time slot. A
routine only surfaces in Predictive Suggestions once it crosses a
minimum observation count -- verified with a before/after test (single
observation: no suggestion; second observation at the same slot:
surfaces) and a time-slotted negative test (a routine learned at 9am
Tuesday does not suggest at 10pm Wednesday).

Preference Learning -- a structured `Preference` key-value store
(`key` unique, find-or-create upsert), deliberately kept separate from
M3's freeform `MemoryType.PREFERENCE` memories rather than merged into
them, since this milestone's preferences are structured signals a
ranking pass reads programmatically, not conversational facts. A
`suggestion_boost_keyword` preference whose value substring-matches a
suggestion's title multiplies that suggestion's score by a fixed
multiplier (capped at 1.0) -- the second, independent mechanism (along
with Routine Learning) satisfying this milestone's Acceptance Criterion
2, verified with its own before/after test.

Context Awareness -- `get_context_signals()` returns hour of day, day
of week, recent memory snippets (via `MemoryService.browse()`, wrapped
in a `try`/`except` so a memory-layer failure degrades to empty
snippets rather than breaking suggestion generation), and the active
conversation id. Location is deliberately omitted from the returned
signal, not silently stubbed -- no location provider exists anywhere in
the codebase yet; the dataclass's own docstring documents the gap.

Predictive Suggestions -- `predict_suggestions()` combines due-soon
active goals (a fixed lookahead window), routines past the
reinforcement threshold, and the preference-boost pass into one ranked
list. Plain keyword-boost logic, not an LLM reranker -- consistent with
M10A's own "Do NOT implement AI reranking" instruction, extended
unprompted to this milestone's own new ranking surface rather than
treated as a one-time M10A-only constraint.

Daily Briefing -- `generate_daily_briefing()` assembles goals due soon,
the top suggestions, and routine reminders into a single value object,
publishing `briefing.generated`. **Deliberately on-demand only, the
same discipline M10A applied to Reflection Foundation:** M7's Scheduler
(Phase 6) does not exist -- `core/config/settings.py`'s
`SchedulerSettings` has been documented as "declared in Phase 1 for
forward compatibility only -- no scheduler loop exists yet" since M7's
own Phase 1 landed, long before this milestone began. Wiring automatic
delivery to M7's Scheduler once it ships is the documented seam this
milestone leaves for that future pass, not a silently dropped
requirement.

A SQLite-specific bug surfaced and was fixed during this pass:
`DateTime(timezone=True)` columns round-trip an aware Python `datetime`
as a **naive** one on read-back under SQLite, so subtracting a
freshly-constructed aware "now" from a retrieved `target_date` raised
`TypeError: can't subtract offset-naive and offset-aware datetimes`.
Fixed with a small `_days_until()` helper that normalizes both operands
to UTC-aware before subtracting, used by both `predict_suggestions()`
and `generate_daily_briefing()` -- a SQL-level `WHERE` comparison would
never have hit this, only Python-level arithmetic on a retrieved value
does.

Agent / REST / WebSocket integration -- new
`agents/tools/intelligence_tools.py` (`create_goal`/`list_goals`/
`update_goal_progress`/`get_suggestions`/`get_daily_briefing`, mirroring
`knowledge_tools.py`'s shape), wired into `build_tool_registry()` as a
new optional `intelligence` parameter. New
`infrastructure/api/routes/intelligence.py`: `POST/GET /api/v1/goals`,
`GET /api/v1/goals/{id}`, `PATCH /api/v1/goals/{id}/progress`,
`POST /api/v1/goals/{id}/complete`, `DELETE /api/v1/goals/{id}`,
`GET /api/v1/intelligence/context|suggestions|briefing`,
`POST/GET /api/v1/intelligence/preferences` -- same Bearer auth +
envelope convention as `routes/knowledge.py`. `EVENT_TYPE_NAMES` gained
`goal.updated`/`briefing.generated`, verified over the real relay in
`tests/integration/test_intelligence_platform_e2e.py` (REST write ->
real service -> real WebSocket read), not just asserted at the unit
level. Context Awareness is deliberately *not* wired into the agent
graph's `context_engine.py` node: it answers a different question
(time/activity signals for ranking suggestions) than that node's
LLM-prompt context assembly, so conflating them would have blurred two
distinct "context" concepts rather than kept scope tight.

Permission Model -- no new scopes introduced. Reuses M10A's existing
`memory.read`/`memory.write` scopes; no `goal.read`/`goal.write`
introduced, per this milestone's own explicit instruction.

Testing -- 48 new tests across five new files
(`test_intelligence_repository.py`, `test_intelligence_service.py`,
`test_intelligence_tools.py`, `test_intelligence_route.py`,
`tests/integration/test_intelligence_platform_e2e.py`) plus one new
test in `test_search_sources.py`, including one integration test per
Acceptance Criterion, each exercised against a real temp-file SQLite
database and the real DI container. Full suite: 936 passed (up from
888), zero regressions -- one pre-existing M10A test
(`test_search_returns_envelope`) asserted an exact 3-source set;
updated to the now-correct 4-source set rather than treated as a
regression, since Goal Manager registering a fourth provider is exactly
the extensibility the Search Provider Registry was designed for. Ruff/
mypy diffed against a clean pre-milestone baseline using the
established `git stash -u` methodology: mypy 266 -> 266, byte-for-byte
unchanged after removing 14 copy-pasted `# type: ignore[assignment]`
comments that turned out unnecessary in `intelligence_service.py` --
the identical mistake, and identical fix, M10A's own addendum above
already documented in `knowledge_service.py`; ruff findings proportional
to the pre-existing accepted baseline, entirely `PLC0415` (the
established lazy-import convention, matching `KnowledgeService`'s own
already-accepted instances of the same pattern line-for-line) -- zero
new finding categories left unresolved. Version bumped `0.14.0` ->
`0.15.0`, continuing the one-minor-bump-per-milestone-scope granularity.

*Aug 2026 addendum — roadmap evolution (M10.5, M13B):* two new
milestones were introduced after M10B completed, extending the roadmap
forward. **No completed milestone's identity, numbering, scope, or
implementation history was altered** -- both additions are strictly
additive, per §1's charter and the zero-renumbering rule this roadmap
has held to through every prior lettered-companion addition.

**M10.5 -- MCP & Integration Platform** (new, planned) is the
protocol-and-registry layer beneath M11: standardizing on the Model
Context Protocol so an external tool/context provider is a *registered
provider* rather than a bespoke adapter written per integration. It is
scheduled immediately before M11 (§16, order slot 5C) specifically so
M11's credential-backed providers are built on that substrate instead
of retrofitted onto it later. The decimal identifier follows the
precedent **M5.5** (Production Stabilization Pass) already set in §3 --
not a new numbering scheme. MCP had previously been recorded in
`docs/TECH_STACK.md` §10 as "not yet assigned a milestone"; that entry
now points here. M11's own scope (OAuth, credential storage, API
Gateway, webhooks, queue/retry/caching, cloud sync, and the specific
Email/Calendar/Spotify/Weather/Finance providers) is unchanged and
deliberately not restated in M10.5.

**M13B -- Self-Healing & Observability** (new, planned) pulls forward
the foundational subset of **M18** (Self-Healing & Diagnostics
Platform) and **M20A** (Analytics & Observability Platform), so that
M14 Security, M15 Personality, M16 Reflection and M17 Companion
Intelligence are each built on a runtime that already reports its own
health and recovers from routine faults. **M18 and M20A are unchanged
and remain their full-scale realizations** -- the same "foundation
now, full platform later" relationship M10A already holds with M19;
Predictive Reliability, AI/Security Diagnostics, Fleet Management,
Enterprise Monitoring, Remote Diagnostics, the Plugin Health
Marketplace and the full analytics platform all stay with their
original owners.

**On the identifier:** this milestone was originally proposed as
"M13A". That identifier was already taken -- **M13A is AI Sandbox**, a
fully specified milestone (objective, key features, dependencies,
acceptance criteria) paired with M13 to de-risk it. Reusing "M13A"
would have either overwritten an existing milestone identity or
created a duplicate ID, both of which the zero-renumbering rule
forbids. It was therefore recorded as **M13B**, the next free letter,
matching the existing companion convention (M10A/M10B, M11A/M11B,
M13A, M14A, M17A, M20A, M23A/M23B). **M13A (AI Sandbox) is untouched.**

*Aug 2026 addendum -- M10.5 Task Group A (MCP & Integration Platform,
Core Runtime):* the first implementation pass on M10.5. Ships the MCP
runtime foundation only -- **no network transport and no provider
integration** -- so the milestone is 🟡 Active, not complete.

**Everything reused, nothing duplicated.** The whole point of this
task group was to add a protocol layer without adding a parallel
runtime, and each piece plugs into something that already exists:

- **Permissions** reuse M9's `PermissionModel` outright -- same store,
  same persisted grants, same audit log, same events, same
  `PENDING`-until-granted default. MCP principals are namespaced
  `mcp:<client_id>` so an MCP peer and a plugin cannot collide on one
  identity while both stay visible in the single `pending()` queue a
  future approval surface reads. **No new permission vocabulary**: an
  MCP capability declares scopes from `core/plugins/sdk.py`'s existing
  `PERMISSION_SCOPES`, validated at registration.
- **Capability Registry** mirrors `SearchService`'s M10A provider
  registry shape (`register`/`unregister`/`get`/`list_capabilities`),
  with one deliberate divergence: a duplicate name is an *error* unless
  `replace=True` is passed, because a search source silently replacing
  itself is benign whereas a capability shadowing another's name would
  silently change what an existing permission grant authorizes.
- **Health** joins through `HealthMonitor.register_collector` -- the
  extension point M9 Task Group B built for exactly this and that
  nothing had used until now. MCP health rides the existing
  `health.updated` snapshot; there is no second health channel.
- **Events** ride the existing `EventBus` and Runtime WebSocket relay:
  `mcp.connection_changed` (one relay name, a `state` payload field,
  the shape `memory.updated`/`goal.updated` established),
  `mcp.capabilities_changed`, `mcp.permission_denied`.
- **Lifecycle**: the client and server runtimes are plain DI singletons
  with their own `start`/`stop`, the same lifecycle class
  `MemoryService`/`KnowledgeService` already occupy. No new lifecycle
  manager, no background supervisor loop (M9's
  `BackgroundTaskManager` already owns "run this repeatedly"), and no
  `RuntimeManager` change beyond registering hooks the way every other
  subsystem does.

**Transports are ports, deliberately.** `IMCPTransport` lives in
`core/interfaces/mcp.py`; `TransportFactoryRegistry` is where `stdio`/
`websocket`/`http`/`ipc` each register in their own later pass. All
four are *named* in `TRANSPORT_TYPES` so a future milestone uses the
identifier already documented rather than inventing a near-miss
spelling, and `GET /api/v1/mcp/transports` reports the `known`-versus-
`registered` gap honestly instead of implying transports exist that do
not. One transport does ship -- `InProcessTransport`, which connects
the client runtime straight to the in-process server runtime. It is
not a provider integration and not a test double: it is how JARVIS
consumes its own MCP server, and it means the handshake, discovery,
negotiation and permission-enforcement paths are exercised against
something real rather than only against mocks.

**Negotiation** is pure functions over plain data -- no I/O, no
transport, no permission-store access (the caller passes the resolved
grant set in), so every branch is unit-testable without a connection.
Version mismatch fails the whole negotiation (there is no shared
language to continue in); an unsupported capability kind or an
ungranted scope is rejected *per capability* and never fails the
connection. Graceful fallback is real: a peer that speaks only the
older shared revision connects on that revision.

**REST is read-only by design.** `/api/v1/mcp/status|capabilities|
connections|transports` observe the runtime; registering, connecting
and granting are Task Group B's surface and M11's provider scope. Every
route is a `GET`, so the write endpoints land beside them additively
without breaking anything.

Testing -- 89 new tests across six files
(`test_mcp_capabilities.py`, `test_mcp_negotiation.py`,
`test_mcp_transport.py`, `test_mcp_server.py`, `test_mcp_client.py`,
`test_mcp_route.py`, plus
`tests/integration/test_mcp_platform_e2e.py`), covering the registry,
negotiation, transports, both lifecycles, permission enforcement
against the *real* `PermissionModel` on a real temp-file store, DI
construction, and the real WebSocket relay. Ruff/mypy diffed against
the repository baseline: mypy 266 -> 266, unchanged, zero errors in any
MCP file; ruff's category list is byte-identical to the baseline's 22
categories (the growth is entirely `PLC0415`, the established
lazy-import convention) after fixing the three genuinely-new findings
this pass introduced (`SIM300`, `RUF059`, `I001`). Version bumped
`0.15.0` -> `0.16.0`.

*Aug 2026 addendum -- M10.5 Task Group B (MCP Transport Layer &
Runtime Connectivity):* fills the seam Task Group A left. All four
transports the milestone names are now real -- ``stdio``,
``websocket``, ``http``, ``ipc`` -- plus a config-driven factory,
transport discovery/query, and a heartbeat monitor. **Still not the
whole milestone:** no provider integration ships, and OAuth/cloud sync
remain M11's scope throughout.

**Nothing from Task Group A was duplicated or rewritten.** Reconnect,
handshake, capability discovery and negotiation stay
``MCPClientRuntime``'s; permission enforcement stays
``MCPServerRuntime``'s; a transport's entire responsibility is to move
one JSON-RPC request and return its response. That boundary is what
kept four transports from becoming four connection managers.

**Framing is shared where it is genuinely the same, and not otherwise.**
``JsonRpcStreamChannel`` owns newline-delimited framing plus
request/response correlation over an ``(StreamReader, StreamWriter)``
pair; ``stdio`` and ``ipc`` both use it and differ only in how they
obtain that pair (a subprocess' pipes versus a local socket/named
pipe). ``websocket`` deliberately does *not* reuse it -- a WebSocket
already delivers discrete messages, and wrapping a message-oriented
protocol in a stream abstraction just to unwrap it again would be
duplication of a different kind. ``http`` is stateless and needs no
channel at all.

**IPC uses the real OS primitive, not loopback TCP.** A named pipe on
Windows, a Unix domain socket elsewhere -- one branch, six lines. A TCP
socket on ``127.0.0.1`` would have been uniform but is not local IPC:
it occupies a port, is reachable by any process that can bind a client
socket, and carries none of the OS-level access control the real
primitives do. Local-first and security-by-design both pointed the same
way.

**Heartbeat is composed, not bolted onto the port.** Adding ``ping()``
to ``IMCPTransport`` would have forced every transport -- including
Task Group A's shipped ``InProcessTransport`` -- to implement a concern
that is identical across all of them. ``MCPHeartbeatMonitor`` instead
rides the ``request`` primitive each transport already exposes, so a
transport added in a later milestone gets heartbeat for free. It runs
one loop over every connection (mirroring M9's ``HealthMonitor``, not a
timer per peer), reports failures rather than raising, and leaves
recovery to the client runtime's existing reconnect. The ``ping``
method itself was registered on the server through Task Group A's own
``register_method`` seam -- which is what that seam was for.

**Honest ``connect`` semantics for a stateless transport.** An early
version of ``HttpTransport.connect`` routed its reachability probe
through ``request``, which wraps every ``httpx`` failure as
``MCPTransportError`` -- so "host unreachable" was indistinguishable
from "peer answered with a JSON-RPC error", and swallowing the latter
meant an unreachable endpoint silently reported itself connected. A
functional test against a real closed port caught it. The probe now
uses ``httpx`` directly: only a genuine transport failure fails the
connect; any HTTP response at all proves reachability, which is the
only thing a stateless transport's ``connect`` can honestly assert.
``tests/unit/test_mcp_transports_live.py`` guards the regression.

Runtime events -- ``mcp.handshake_completed``,
``mcp.negotiation_completed``, ``mcp.transport_failed`` and
``mcp.heartbeat`` join Task Group A's three, all over the existing
relay. They are deliberately distinct from one another: a transport
failure is a connectivity problem, whereas a permission denial or a
negotiation rejection is the protocol working correctly, and collapsing
them into one event would lose exactly the distinction an operator
needs. ``MCPConnectionState`` gained ``reconnecting`` so a subscriber
can tell recovery from initial setup without tracking prior state.

REST stays read-only: ``GET /api/v1/mcp/transports`` now returns one
descriptor per transport (traits, config keys, registered-or-not),
``GET /api/v1/mcp/transports/{id}`` adds the connections currently
using it, and ``GET /api/v1/mcp/heartbeat`` reports the last probe per
peer without ever forcing one -- so polling it cannot generate peer
traffic. A 404 there means "not in the vocabulary"; "known but not
registered in this build" is a 200 with ``registered: false``, which is
a genuinely different situation.

Testing -- 100 new tests across eight files, against **real** peers
throughout: a real subprocess for stdio (``tests/fixtures/
mcp_stdio_peer.py``), a real ``websockets`` server, a real HTTP server,
and a real named pipe / Unix socket for IPC. A stubbed peer would
exercise neither process lifecycle nor stream framing, which is most of
what these transports are. One test-harness subtlety worth recording:
a real subprocess' pipes are bound to the event loop that created them,
so each integration test runs all of its transport work inside a single
``asyncio.run`` scenario rather than one call per ``asyncio.run`` --
the first draft did the latter and failed with a dead-loop write error
that looked like a product bug but was not. Ruff/mypy diffed against
the repository baseline: mypy 266 -> 266, unchanged, zero errors in any
MCP file; ruff's category list is identical to the baseline's 22 after
fixing the two genuinely-new findings this pass introduced (`RUF100`,
`PLW2901`). Version bumped `0.16.0` -> `0.17.0`.

*Aug 2026 addendum -- M10.5 Task Group C (MCP Provider Framework):*
the generic framework every future MCP integration plugs into
**without modifying the MCP runtime**. Infrastructure only -- no real
provider, no authentication, no OAuth, no vendor code; those are Task
Group D and M11.

**The framework is three collaborators, not one god object**, split
the way ``core/plugins/`` already splits its own:

- ``metadata.py`` -- what a provider *is* (``ProviderMetadata``) and how
  this install *runs* it (``ProviderConfig``). Inert, validated at
  registration. The separation is what lets a deployment move a
  provider from stdio to websocket without editing the provider, and it
  is why ``ProviderConfig.transport`` overrides
  ``ProviderMetadata.transport`` rather than duplicating it.
- ``registry.py`` -- what providers *exist*. **Registration is inert**:
  no transport built, no subprocess spawned, no socket opened. That is
  precisely what makes ``discover()`` safe to call from a REST handler,
  and it is why lifecycle does not live here.
- ``manager.py`` -- what providers are *doing*. Lifecycle, events,
  health collection, permission resolution.

**Nothing was duplicated.** Every connect/disconnect delegates through
``TransportBackedProvider`` to Task Group A's ``MCPClientRuntime``;
transports are built by Task Group B's ``TransportFactoryRegistry``;
permissions resolve against M9's ``PermissionModel`` (namespaced
``mcp:<provider_id>``, the same prefix Task Group A established, with
**no new scope vocabulary** -- a provider may only request scopes the
plugin platform already defines); health is a plain dict for
``HealthMonitor.register_collector``; shutdown ordering is a
``RuntimeManager`` hook. There is no second registry, lifecycle
manager, health subsystem or permission system anywhere in this task
group.

**Eight transitions, one event class.** ``mcp.provider_changed`` carries
an ``action`` field (registered/initialized/connected/disconnected/
suspended/resumed/failed/removed) plus the resting ``state`` -- the
shape ``memory.updated``/``goal.updated``/``mcp.connection_changed``
already established, rather than eight event classes. The two fields
genuinely differ for ``resumed``, which lands in ``connected``:
``ProviderState`` deliberately has no ``RESUMED`` member, because
inventing a state nothing rests in would make the state machine lie.

**Credential-shaped surfaces were built defensively now, not
retrofitted later.** ``ProviderConfig.as_dict()`` reports option *key
names only, never values* -- provider options will carry tokens once
M11's integrations exist, and a REST test asserts a secret value never
appears in the response body.

Scopes resolve fresh on every connect rather than being cached at
install time, so granting a permission after installation takes effect
on the next connect without re-registering the provider -- verified
end-to-end against a real peer.

Testing -- 84 new tests across five files: metadata/config validation,
registry and every discovery filter, the full lifecycle including
failure and fault-isolated batch operations, health, events, REST, DI
singleton identity, and an end-to-end suite driving a **real stdio peer
subprocess** through the real DI container and real ``PermissionModel``
with lifecycle events verified over the real WebSocket relay. Ruff/mypy
diffed against the repository baseline: mypy 266 -> 266, unchanged,
zero errors in any new file; ruff's category list identical to the
baseline's 22 after fixing the two genuinely-new findings this pass
introduced (`I001`, `SIM300`). Version bumped `0.17.0` -> `0.18.0`.

*Aug 2026 addendum -- M10.5 Task Group D (Authentication & Provider
Integration Foundation):* the authentication framework every future MCP
provider uses. Infrastructure only -- no real provider, no vendor code,
and **no OAuth flow**, which needs an authorization server and a
callback endpoint this task group explicitly does not ship.

**The security posture is the design.** Tokens are the most dangerous
thing this milestone has handled, so the protections are structural
rather than remembered:

- ``Credential`` redacts its own ``__repr__``/``__str__``, so a stray
  ``logger.info("... {}", credential)`` or an exception rendering its
  arguments cannot leak one.
- Two serializers, deliberately: ``to_storage_dict`` (everything, for
  the encrypted store and nothing else) and ``to_public_dict``
  (metadata only, for REST, logs and events). "Safe to show" is a
  choice the type makes, not something each caller must get right.
- Revoking **clears** both tokens rather than only setting a flag: a
  revoked credential still holding its secret is a credential waiting
  to leak.
- The tests assert against raw artefacts -- the actual REST response
  text, the actual event payload, the actual health snapshot, the
  actual bytes on disk -- rather than a parsed field, so a leak
  anywhere in a payload fails them.

**One deliberate divergence from an existing precedent.**
``ApiCenterService`` encrypts secret fields when a key is configured and
writes plaintext when one is not -- a reasonable trade for API
definitions that are mostly non-secret metadata. Access and refresh
tokens are not that. ``CredentialStore`` therefore **refuses to
persist** without a real key: it raises, writes no file at all, and
records the in-memory-only caveat on the session. An unconfigured
install still authenticates for the current session; it simply will not
remember it. Degrading loudly beats degrading quietly when the quiet
option is a plaintext token on disk.

**The permission bridge is two gates, not one.** A capability is usable
only when the operator has granted the JARVIS-side scope (M9's
``PermissionModel``, namespaced ``mcp:<provider_id>`` -- the prefix Task
Group A established, with **no new scope vocabulary**) *and* the
credential actually carries the provider-side scope the remote service
demands (``repo:read``, say). ``authorize_capability`` names which gate
refused, because "the operator has not granted this" and "the token
does not carry that scope" call for completely different fixes, and
collapsing them into one boolean would hide that.

**Sessions are a distinct concept, not a duplicate.** M9's
``SessionManager`` owns *user* sessions -- the Bearer tokens the REST
API authenticates callers with. ``ProviderSession`` owns *provider*
sessions -- how long JARVIS's own credential for an outbound
integration stays usable. Same word, different subject, different
lifetime; merging them would couple an operator's login to a provider's
token expiry.

Three real bugs surfaced during implementation and were fixed in the
code rather than papered over in the tests. Two shared a root cause:
``expire()`` inferred "already announced" from the session's derived
state, but a lazily-created session syncs straight to ``EXPIRED`` before
anything has been announced -- so the first expiry was never published.
Fixed with an explicit ``expiry_announced`` flag, because derived state
genuinely cannot answer that question. The third: ``mark_active`` clears
``error``, which was also wiping the "held in memory only" note --
fixed by separating ``warning`` (a caveat that still applies) from
``error`` (a failure a success clears), which is the more honest model
anyway.

``oauth2`` and ``client_credentials`` are in the vocabulary and
reported as **unsupported** by ``GET /api/v1/mcp/auth/methods``.
Registering a flow that cannot complete would be worse than registering
none, and the honest report is what lets a caller distinguish "not
built yet" from "broken".

Testing -- 101 new tests across five files: redaction, both
serializers, expiry boundaries and naive-datetime normalization,
encryption at rest verified against real file bytes, wrong-key and
corrupt-record handling, key rotation, the full lifecycle including
refresh/revoke/reconnect/failure, both permission gates, health
sweeping, REST, DI singleton identity, and an end-to-end suite through
the real container with events verified over the real WebSocket relay.
Ruff/mypy diffed against the repository baseline: mypy 266 -> 266,
unchanged, zero errors in any new file; ruff's category list identical
to the baseline's 22 after fixing the three genuinely-new findings this
pass introduced (`I001`, `RUF100`, `SIM300`). Version bumped `0.18.0`
-> `0.19.0`.

*Aug 2026 addendum -- M10.5 Task Group E (SDK, Developer Experience &
Milestone Closure):* the last task group. It ships nothing a *user*
sees and everything an integration *author* needs, then closes the
milestone.

**Why an SDK when the runtime models are already plain dataclasses.**
The builders are not ceremony over a constructor. They validate at the
point of construction, so a bad permission scope surfaces while the
provider is being written rather than at first connect; they are
autocomplete-friendly, so ``.with_permission("agent_tools")`` rejects a
typo that ``required_permissions=("agent_tolls",)`` would carry into
production; and they insulate an author from a dataclass the runtime is
free to extend. The dataclasses stay public and directly constructible
-- the builders are a convenience, not a gate.

**The validation framework earns its place by answering the question no
single model can.** Every model already validates itself, and that stays
where it is. What ``validate_registry_consistency`` adds is the
*cross-object* check: a provider declaring a transport nothing
registered, an auth method no strategy implements, a scope still
awaiting a grant decision. Each object is valid; the set is not.
``ERROR`` and ``WARNING`` are kept separate deliberately -- collapsing
them would make the warning either ignorable noise or a false blocker,
and ``jarvis mcp validate`` exits non-zero only on a real error so it is
usable in a pre-commit hook.

**The examples live in ``src/``, not in a document.** A code sample in
Markdown rots the moment an API changes and nothing notices;
``tests/unit/test_mcp_sdk_examples.py`` imports and executes these, so
the same change breaks the build instead. They are entirely
self-contained -- the transport answers from an in-memory dict, the auth
strategy mints a local token, and a test asserts against the module
source that nothing there imports ``socket``, ``httpx``, ``subprocess``
or reads ``os.environ``.

Two example decisions are worth recording because the obvious
alternative was worse. ``ExampleAuthStrategy`` claims ``BEARER_TOKEN``,
which collides with the shipped static strategy and therefore needs
``replace=True`` to register. Claiming the unregistered ``OAUTH2``
instead would have avoided the collision at the cost of reporting an
OAuth flow the class does not implement -- exactly the simulated
functionality this project forbids. And ``ExampleTransport`` reuses the
existing ``in_process`` identifier rather than inventing a sixth:
``TRANSPORT_TYPES`` is closed by design, an integration author
configures one of the five, and an example that widened the set would
teach a move the platform rejects.

**Diagnostics collects; it never computes.** Every figure
``MCPDiagnostics`` reports is already owned by the subsystem that
produced it -- capability counts from the capability registry,
connection state from the client runtime, health from
``MCPProviderManager.collect_health``, credential status from
``MCPAuthManager``. It holds no state and caches nothing, and a test
runs every read twice with the world captured either side to prove that
inspecting changes nothing. It is one DI singleton, so ``jarvis mcp``
and ``/api/v1/mcp/diagnostics`` are two renderings of one truth rather
than two things that might drift; an integration test asserts their
payloads are identical.

**The CLI is a delivery shim, nothing more** -- the same rule
`ARCHITECTURE.md` §1 states for FastAPI routers, applied to the second
delivery mechanism. It is read-only end to end, so it can never be the
thing that broke a provider, and it has no vendor-specific commands: the
subcommands describe the *platform*, and a provider appears in them only
because someone registered it. ``run_command`` returns
``(output, exit_code)`` rather than printing, so its tests assert on
values instead of scraping stdout.

**Final Runtime Review.** The audit this task group owed the milestone,
run against the whole tree rather than from memory:

- *Registries* -- four, each holding a distinct kind of thing
  (capabilities, providers, transport factories, auth strategies), none
  overlapping, plus the plugin platform's own in a separate domain.
- *Lifecycle* -- one ``MCPProviderManager`` for provider lifecycle,
  hanging off M9's existing ``RuntimeManager`` hooks. No background
  supervisor, no second scheduler, and no lifecycle hook for diagnostics
  because a stateless read needs none.
- *Permissions* -- one ``PermissionModel`` (M9's), namespaced
  ``mcp:<id>``. ``features/automation``'s ``PermissionGate`` is a
  different axis entirely (per-intent risk confirmation, not scope
  grants) and is not a duplicate.
- *Health* -- one ``HealthMonitor``, one registered collector named
  ``mcp`` aggregating all four subsystems into the single
  ``health.updated`` snapshot. ``MCPHeartbeatMonitor`` is transport
  liveness probing, a different concern from app-wide health.
- *Authentication* -- one ``MCPAuthManager``, one ``CredentialStore``.
- *Layering* -- ``core/mcp/`` imports only ``core`` (plus the
  ``utils.crypto`` leaf); ``infrastructure/cli/`` imports only ``core``,
  the correct direction, and sits beside ``infrastructure/api/`` because
  both are delivery mechanisms over the same core.

Two real defects surfaced and were fixed rather than noted: a stale
comment on ``TRANSPORT_TYPES`` still claiming only ``in_process`` had a
shipped implementation (Task Group B shipped the other four), and a dead
``SessionState`` import left in ``auth/manager.py`` by Task Group D.
One pre-existing layering exception is recorded and left alone:
``core/lifecycle/session_manager.py`` imports an infrastructure
repository, which predates this milestone and is a real refactor rather
than a comment fix.

Testing -- 137 new tests across six files: builders and their rejection
paths, every validator including the cross-object ones, the examples
executed end to end through the real provider manager, diagnostics
proven read-only and token-free against raw serialized output, every CLI
command in both output formats with its exit code, and an integration
suite through the real DI container asserting the CLI and REST report
byte-identical payloads. Suite 1296 -> 1433, all passing. Ruff/mypy
diffed against the repository baseline: mypy 266 -> 266, unchanged, zero
errors in any new file; ruff's category list identical to the baseline's
22 after fixing the four genuinely-new findings this pass introduced
(`E501`, `PLR0402`, `PLR0911`, `RUF100`), with `F401` improving 3 -> 2.
Version bumped `0.19.0` -> `0.20.0`.

**M10.5 is closed.** Five task groups, `0.16.0` through `0.20.0`. Two
acceptance criteria remain 🟡 and are named in §8 with where they land
(Agent Trace integration and a server-side listener, both M11). No real
provider, no OAuth flow, no vendor integration ships here -- that was
always M11's scope, and the substrate M11 registers against is now
complete.

*Aug 2026 addendum -- Backlog Completion & Stabilization Pass
(pre-M11):* not a milestone. A sweep of the documented backlog belonging
to milestones already marked complete, plus the UI and runtime audit
that sweep implies.

**Two screens were showing invented data over a working backend**, and
finding them is the main reason this pass was worth running. The
desktop Plugin Manager was still wired to an M5-era mock that seeded
"Weather Widget" and "Spotify Connector" and a three-entry invented
marketplace. M9 Task Group C had shipped the real Plugin Platform --
registry, loader, sandbox, permission model, marketplace, REST routes --
and nobody rewired the view, so it rendered fabricated rows beside a
runtime that could have answered honestly. The Module Manager was worse
in kind if not in scale: `check_update` rolled a die and invented a
version number 30% of the time, so the same button told the user a
different story on each click. Both are now real or honestly empty, and
the mock provider was deleted rather than left sitting next to its
replacement.

This is the failure mode worth naming for future passes: neither was a
bug in code anyone wrote recently. Both were *stale wiring* -- honest
placeholders written when there was genuinely nothing behind them,
which quietly became lies the moment the backend shipped. Nothing fails
when that happens. Only an audit that reads a docstring's claim against
the current tree catches it, which is why the docstrings that made those
claims were rewritten too, not just the code.

**Four §15 items closed**, all with their stated preconditions already
met:

- *Five WebSocket categories that were published but never relayed.*
  `voice.state_changed`, `automation.step`, `progress.update_phase`,
  `notification.plugin`, `plugin.custom` -- every one had a real
  publisher and no `EVENT_TYPE_NAMES` entry, so no subscriber could
  ever receive them. `UNPUBLISHED_EVENT_TYPES` now names the four
  classes still absent because nothing publishes them, and a test fails
  if one gains a publisher without gaining a relay entry.
  `DebugLogCapturedEvent` stays out on its own reasoning: it fires once
  per log line, and this hub broadcasts to every connection with no
  per-category subscription, so relaying it would drown every other
  event in the replay buffer.
- *The `HealthMonitor` disk collector.* Flat `disk_percent` /
  `disk_free_bytes` / `disk_total_bytes` keys rather than a nested
  collector payload -- `ResourceManager.register_budget()` reads one
  top-level key and compares a float, so nesting would have left them
  unbudgetable, and "so a budget can target it" was the entire reason
  §15 tracked the item. GPU stays open and unfaked: it needs a vendor
  library this project does not depend on.
- *The health router prefix mismatch.* Mounted at both `/api` and
  `/api/v1` rather than moved. An unversioned liveness probe is the URL
  external monitoring is likeliest to have hard-coded, and breaking it
  to satisfy a doc would be the wrong trade; a test pins that both
  paths return identical bodies.
- *`/api/v1/sessions`'s response shape.* **The pass's one intentional
  breaking change.** §15 deferred wrapping it while `/sessions` was the
  only real resource route, reasoning that adopting a wrapper before a
  second route proved the shape risked getting it wrong twice. Six route
  modules now use the envelope consistently, so that reasoning had
  expired and the inconsistency was the only thing left. Callers read
  `response.json()["data"]["session_id"]`; the route keeps its separate
  authentication exemption, which was always a different question from
  its response shape.

**What was deliberately not done, and why.** M8's deferred backlog --
Notification Center, Context Menu system, Workspace views, window
management, responsive/DPI/multi-monitor, Phases 2/5/6/7 -- is not
stabilization work. It is the M8 milestone itself, M8 is *active* rather
than complete, and it is an XL migration off PySide6. Building those
surfaces in the outgoing stack would mean writing them twice. M7's
Scheduler, M10A's File Search, M10B's scheduled briefing, M10's
Learning/Feedback and M10.5's two partial acceptance criteria are each
blocked on a milestone that has not started (M7 Phase 6, M11B, M15,
M16, M14, M11) -- blocked on dependencies, not on effort, and
implementing any of them here would be starting those milestones early
under another name.

Validation: 1433 -> 1451 tests, all passing. mypy 266 -> 265 (the
`HealthMonitor` DI factory replaced a string-path provider, removing one
`var-annotated` error). Ruff's category list unchanged at 22 after
fixing the one new finding (`I001`). Version bumped `0.20.0` ->
`0.21.0` -- a minor bump rather than a patch, because the sessions
envelope is a breaking change to a live route.

*Aug 2026 addendum -- Final Backlog Completion Pass (pre-M11):* the
second and last backlog pass. `0.21.0` closed the §15 items the
roadmap had written down; this one closed what it had not.

**The pattern the previous pass named, found three more times.** Stale
wiring -- an honest placeholder written when nothing existed behind it,
which becomes a lie the moment the backend ships, silently, because
nothing fails:

- *The startup greeting invented the user's day.* It fed the LLM an
  invented task list, invented calendar events, an invented "recent
  achievement", a fabricated temperature and a fabricated now-playing
  track -- and the result was **spoken aloud** as fact. This was the
  worst instance in the repository, because every other case was a
  screen a user could inspect; this one was a sentence they were told.
  M10B's Goal Manager had shipped a real source for the work-context
  half and was never wired in. It is now: real open goals, real
  completed goals. Calendar, weather, music and smart-home stay empty
  until M11/M12 give them a source -- the prompt drops what it has no
  context for, which is the honest alternative to inventing it.
- *Three Settings pages advertised milestones that had already
  shipped.* "Browser Automation" and "Desktop Automation" read *Coming
  in Milestone 4* while `BrowserSettings`/`WindowsAutomationSettings`
  were real and consumed by shipped services. "Plugins" read *Coming in
  Milestone 5 — Agents* -- a milestone that never owned plugins, for a
  platform M9 shipped. All three are now real pages over settings that
  already existed; nothing new was built.
- *The Home dashboard's service cards claimed to be connected.* Gmail,
  Spotify, Weather, Finance and Smart Home rendered a green "online"
  indicator and a last-sync timestamp over invented figures. The cards
  themselves are a legitimate M5 deliverable and their real adapters
  are genuinely M11/M12, so the fix is not to delete them: a `preview`
  flag forces the offline indicator and shows a visible note. The
  illustrative data stays; the claim to be connected does not.

**What a clean sweep looks like.** Zero `TODO`/`FIXME`/`HACK`/`XXX` in
`src/`. All nine routers mounted -- no dead routes. No unwired DI
service. Every `NotImplementedError` is an abstract-method or
explicitly-not-undoable contract. The remaining stand-ins are all owned
by milestones that have not started, and each now says so on screen:
the integration providers (M11/M12), the vision and OCR providers (M6's
remainder, already reporting themselves unavailable), the module
registry (no module hot-reload machinery exists to back it), and the
Automations workspace placeholder.

**What stays deferred, and the one rule behind all of it.** The
Automations workspace, M8's nine workspace views, Notification Center,
Context Menu system, window management and responsive/DPI work are all
*new PySide6 screens*. M8 is an active migration to React + Tauri.
Building them now means building them twice, and "reuse instead of
reinventing" is the rule this repository has enforced most
consistently. Everything else -- M7's Scheduler, M10A's File Search,
M10B's scheduled briefing, M10's Learning/Feedback, M10.5's two partial
acceptance criteria -- is blocked on a milestone that has not started,
not on effort.

Validation: 1451 -> 1460 tests, all passing. mypy 265 -> 263. Ruff 22
-> 21 categories (simplifying `build_context` removed the file's
`PLR0912`); no new category. Version `0.21.0` -> `0.22.0`.

**All backlog for completed milestones is finished.** The remaining
items are intentionally deferred to future milestones.
