# Changelog

All notable changes to JARVIS OS are documented here. Format loosely
follows [Keep a Changelog](https://keepachangelog.com/).

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
