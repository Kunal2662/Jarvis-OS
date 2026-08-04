# JARVIS OS — Implementation Roadmap (Active)

> **Companion to [`MASTER_ROADMAP.md`](MASTER_ROADMAP.md) and
> [`TECH_STACK.md`](TECH_STACK.md).** `MASTER_ROADMAP.md` remains the
> complete historical + full future-milestone reference — nothing has
> been moved out of it, and it stays the source of truth for
> dependencies, acceptance criteria, and shipped history. This document
> is narrower and more actionable on purpose: it tracks only *what's
> actively being built right now*, phase by phase, so day-to-day
> development has a checklist that doesn't require reading an 8,000+
> line file. When a phase here ships, its status updates in both
> documents. A full Project Completion Audit (Aug 2026, ahead of M9
> Task Group D) cross-checked this document's own checklists against
> the repository and found them already current — no changes required
> here at that time; every new finding from that audit lives in
> `MASTER_ROADMAP.md` §15 Pending and `docs/ARCHITECTURE.md` §5. M9
> Task Groups D (Plugin Platform) and E (Developer Platform Tools) have
> since shipped — **Milestone 9 is now 100% complete.** See §5 below.
> M10 (AI Orchestrator) has since shipped its buildable-now scope —
> **M10 is partial, not 100% complete;** the M10A/M14/M16-dependent
> remainder is explicitly deferred, documented rather than dropped. See
> §5 below.

**Document owner:** project lead
**Status:** Aug 2026 — tracks M8 (React Frontend & Desktop Experience)
and, as of Task Group A, M9 (Runtime & Core Services) as well, both
active in parallel. M8 Phase 1 (React Foundation) and Phase 4 (Voice
Experience & Motion, in full — the Premium UI & Voice Experience
initiative's five task groups H–L) shipped; Phases 2–3 and 5–7 remain
pending, each its own separately-approved implementation pass. M9's
Runtime Core module is now fully shipped across Task Group A (Runtime
Manager, Application Lifecycle) and Task Group B (Service Manager,
Session Manager, Configuration Manager, Runtime Health Monitor,
Runtime WebSocket API, Runtime Integration) and Task Group C
(Background Task Manager, Crash Recovery, Resource Manager); Task
Group D (Plugin Platform — SDK, Loader, Sandbox, Extension API,
Permission Model, Registration System, Store, Marketplace Foundation)
and Task Group E (Developer Platform Tools — Debug Console, Live Logs,
Performance Profiler, State Inspector, API Inspector, Plugin
Marketplace Foundation REST API, Permission Management API, Plugin
Diagnostics) have both now shipped — see §5 below. **Milestone 9 is
100% complete.** M10 (AI Orchestrator) has since shipped its
buildable-now scope (Intent Engine, scoped Context Engine, parallel
tool dispatch, interim Permission Validation, real streaming for the
composed path, Decision Engine, `/api/v1/agent`) — **M10 is partial**,
since it formally depends on M10A and M14, neither of which has
started; the dependent remainder is documented as deferred, not
dropped. See §5 below. Both were a deliberate, explicit exception to
"one active milestone at a time":
M9's Runtime Core had no real dependency on M8's remaining frontend
backlog (see §5's own Dependencies note), following an architecture
review the user requested and then closed with "keep the documented
roadmap exactly as-is" — see `MASTER_ROADMAP.md`'s own changelog
addendum for the full reasoning. M8's remaining Phases 2–3/5–7 are now
tracked explicitly in §6's **Deferred Backlog** (added Aug 2026, roadmap
reconciliation pass) rather than only as unchecked boxes scattered
across §2 — nothing in it blocks M9.

---

## 1. Where things stand

*(Reconciled Aug 2026 — every milestone below carries exactly one of
four states: ✅ Completed, 🟡 Active, 🟠 Deferred, 🔴 Planned.)*

| Milestone | Status |
|---|---|
| M0 – M6 | ✅ Completed. See `MASTER_ROADMAP.md` §3. |
| M7 — Workflow Intelligence | 🟡 Active (Phases 1–2 shipped; Phase 3 🟠 deferred; Phases 4–6 pending). See `MASTER_ROADMAP.md` §8. |
| **M8 – React Frontend & Desktop Experience** | 🟡 **Active — this document tracks it.** Phase 1 and Phase 4 shipped; Phase 3 partial; Phases 2, 5, 6, 7 and the rest of Phase 3 🟠 **deferred — see §6, Deferred Backlog.** **Not 100% complete.** |
| **M9 – Runtime & Core Services** | ✅ **Completed — all five task groups (A–E) shipped, see §5 below.** |
| **M10 – AI Orchestrator** | 🟡 **Partial — buildable-now scope shipped; M10A/M14/M16-dependent remainder deferred. See §5 below and `MASTER_ROADMAP.md` §8/§14.** |
| M10A, M10B, M11 onward | 🔴 Planned, not started. See `MASTER_ROADMAP.md` §8 and §14. |

M7's Phases 4–6 (Workflow Builder, Recorder, Scheduler) were paused
pending the UI Foundation review; that review is superseded by the
decision to migrate the frontend to React + Tauri (this document).
M7's Python-side domain models (`WorkflowDefinition`, `WorkflowStep`,
`ScheduleDefinition`, wave-based `ActionExecutor`) are untouched by
this migration and remain exactly as shipped — a future UI, whichever
technology renders it, consumes the same backend contract.

---

## 2. M8 — React Frontend & Desktop Experience

Full milestone definition (Objective, Dependencies, Complexity,
Acceptance Criteria) lives in `MASTER_ROADMAP.md` §8 — this section is
the execution checklist for its seven phases.

### Phase 1 — React Foundation ✅ *(Aug 2026)*
- [x] Vite + React 19 + TypeScript project scaffolded under `frontend/`.
- [x] Tauri shell wired to the Vite dev server / production build —
      `tauri.conf.json`/`Cargo.toml`/`src-tauri/src/` scaffolded and
      configured; **Rust compilation itself is unverified** (no Rust
      toolchain in the build environment this phase ran in) — `npm run
      build` (the React side Tauri bundles) is verified passing.
- [x] Tailwind CSS configured with the design tokens ported from the
      existing `Typography` scale (`ui/themes/typography.py`) and the
      real `DARK_PALETTE`/`LIGHT_PALETTE`/`JARVIS_PALETTE` hex values
      (`ui/themes/palette.py`) — not `ThemeService`'s Qt-specific API
      itself, which has no React equivalent, but its underlying color
      data.
- [x] shadcn/ui + Radix UI installed; base component set copied in
      (Button, Card, Dialog, AlertDialog, Input, DropdownMenu,
      ContextMenu, Tabs, Tooltip, Sonner/Toast, ScrollArea, Command).
- [x] Motion installed; base transition/hover primitives established
      (`lib/motion.ts`, page transitions, Developer Panel slide-in).
- [x] Lucide Icons wired (`lucide-react`, mapped 1:1 to the 14 nav
      items).
- [x] React Router base layout + route structure (14 routes, one
      shared placeholder each).
- [x] Zustand store scaffold (theme, sidebar, dock, window,
      notifications, developer-mode — 6 stores, all UI-state only).
- [x] TanStack Query client + base API/WebSocket client
      (`services/api/`, `services/websocket/`).
- [ ] React Hook Form + Zod wired for the first real form — installed,
      not yet wired to a real form; Settings (Phase 5) is the first
      actual candidate, correctly not built this phase.
- [x] Inter font loaded (`resources/fonts/Inter.ttf`, self-hosted via
      `@font-face`, verified in the production bundle).
- [x] Component library smoke-tested — via Vitest + React Testing
      Library (not Storybook specifically; RTL component tests serve
      the same "does this render correctly" verification role and are
      the same tool this phase's own Testing Foundation standardized
      on). 6 Vitest tests + 3 Playwright E2E tests, all passing against
      the real running app.

**Verified working, not just configured:** production build (`npm run
build`), dev server, all three themes resolving distinct real palette
values, React Router navigation + active-state highlighting, the full
Vitest + Playwright suite. One real bug was found and fixed during this
verification: a redundant `.dark` CSS class selector could desync from
the `data-theme` attribute and silently override the light theme's
colors — `data-theme` is now the sole source of color truth (see
`styles/themes.css`). A second bug (mismatched sidebar active-state vs.
rendered route, caused by mixing `index: true` with an explicit
`path: undefined` in the route config) was also found and fixed — see
`routes/router.tsx`.

### Phase 2 — Universal Application Framework & Logic
- [ ] Business Logic → State Machine → Service Layer → Hooks → Store
      pattern established as the mandatory shape for every application
      (mirrors the PySide6-era `ModuleStateMachine` foundation —
      `domain/app_state/` — ported to a TypeScript equivalent, not
      redesigned from scratch).
- [ ] Authentication flow against the FastAPI backend.
- [ ] Permissions model surfaced from the backend's Authorization
      Engine (M14).
- [ ] Storage — client-side persistence layer (Tauri's filesystem
      APIs / local storage as appropriate per data sensitivity).
- [ ] Settings — API layer + store, real backend-backed values only.
- [ ] API layer — typed REST client + WebSocket client, per
      `TECH_STACK.md` §3.
- [ ] Voice Integration — WebSocket-streamed voice state, replacing
      the PySide6 `VoiceOrb`'s direct service calls.
- [ ] AI Integration — chat/agent streaming over WebSocket.
- [ ] Automation Integration — automation run status over WebSocket.
- [ ] Offline support — graceful degradation when the Python backend
      is unreachable (never fake data — an explicit "disconnected"
      state).
- [ ] Error handling — a single, consistent error-boundary + toast
      pattern for the whole app.

**API Integration Rework** *(added Aug 2026 per the roadmap
architecture review — full design in `MASTER_ROADMAP.md` §8 M11's
API Center Architecture module)*:
- [ ] Real API Activation — a saved key activates its provider
      immediately, no restart.
- [ ] Provider Registry — the live, post-startup registration surface
      every provider joins on activation.
- [ ] Runtime Provider Registration — providers can register after
      process startup, not only at boot.
- [ ] API Validation — round-trip key validation before a provider is
      marked active.
- [ ] Connection Testing — explicit, user-triggered per-provider test.
- [ ] Health Checks — periodic background health polling per active
      provider.
- [ ] Automatic Provider Loading — provider adapters are discovered
      from their implemented port, not manually listed.
- [ ] Provider Failover — automatic fallback to the next configured
      provider on failure.
- [ ] No Fake Providers — mock providers only when Developer Mode
      explicitly enables them; never a silent default.
- [ ] Runtime Provider Switching — a module's active provider can
      change without restart.

**Hard rule for this phase and every phase after it:** no fake data,
no simulated completed functionality. Every screen renders a real
value, a real loading state, or a real empty state.

### Phase 3 — Desktop Workspace
- [x] Dashboard (Home) view -- `features/dashboard/dashboard-grid.tsx`
      is now the `home` module's real route element (`routes/router.tsx`),
      replacing the shared `PlaceholderRoute` the way that file's own
      header comment describes for a route's first real feature module.
- [x] Sidebar (ports the existing 14-item nav list from
      `ui/widgets/sidebar.py` — same nav structure, new renderer).
  - [x] **Adaptive Sidebar** *(added Aug 2026 per the roadmap
        architecture review)*:
    - [x] Expanded mode
    - [x] Collapsed mode
    - [x] Smooth width animation
    - [x] Active indicator
    - [x] Hover tooltip (collapsed mode)
    - [x] Keyboard navigation
    - [x] Responsive behaviour
    - [x] Persistent sidebar state (expanded/collapsed survives
          restart, per Phase 1's `sidebar.store.ts`)
    - [x] Modern AI desktop UX — matches Phase 3's premium/minimal
          visual language, not a bolted-on toggle.
  - [x] **Dynamic Sidebar revision** *(added Aug 2026 per the UI
        Architecture Update review — supersedes the flat
        Workspace/Connected grouping shipped above, not the
        underlying collapse/keyboard/accessibility mechanics, which
        carry forward unchanged)*: minimal core taxonomy (Dashboard,
        AI [nested: Conversation, Voice, Memory], Automation, Files,
        Settings) always visible; every other module hidden unless
        both registered *and* enabled
        (`stores/module-enablement.store.ts`, new) — see
        `MASTER_ROADMAP.md` §8 M8 Phase 3.
    - [x] `ModuleManifest.isCore` + `parentGroup` fields.
    - [x] `ModuleEnablementStore` (new) — installed-vs-enabled state.
    - [x] Nested/expandable group rendering (the "AI" parent).
    - [x] Re-classify the 14 existing modules: 7 core, 7
          optional/disabled-by-default.
    - [x] Keyboard roving-focus updated for variable visible-item sets
          (collapsed groups skip their hidden children).
- [x] **Dashboard Widget Grid** *(added Aug 2026 per the UI
      Architecture Update review; built out Aug 2026, Task Group F —
      see `MASTER_ROADMAP.md` §8 M8 Phase 3)*:
  - [x] `DashboardWidgetRegistry` + `DashboardWidgetContribution`
        (extended with `isCore`, matching `StatusBarContribution`'s own
        reasoning — Core JARVIS's widgets register under the reserved
        `moduleId: "core"`, which isn't a real `ApplicationRegistry`
        entry).
  - [x] Built-in widgets — **4 of the originally-listed 7 shipped**:
        Notifications, Recent Activity, Quick Actions, System Status.
        **Tasks, Calendar, and Notes were deliberately NOT built** — no
        real backing store or feature exists anywhere in this codebase
        for any of the three (confirmed by search: no `tasks.store.ts`,
        no calendar data model, no notes data model, no backend
        endpoint for any of them). Per this project's standing "no fake
        data"/"no placeholder business logic" rule, a widget with a
        title and an empty shell but no real feature behind it would be
        exactly the fake implementation this milestone forbids. Each
        needs its own real feature build first — Tasks and Notes most
        naturally belong under a future Productivity milestone (see
        `MASTER_ROADMAP.md` M11B Productivity Suite), Calendar under its
        own module once Google Workspace/OAuth integration (M11) ships
        real data — before it can honestly register a Dashboard widget.
        `dashboardWidgetRegistry` and the grid UI place no limit on
        widget count, so adding these later is additive, not a rework.
  - [x] Grid layout (add/remove/resize/move/pin) — `stores/dashboard-
        layout.store.ts`. Resize cycles a widget through 4 fixed grid
        footprints (1×1, 2×1, 1×2, 2×2) rather than free-form drag
        resizing (no drag/grid-layout library is installed or
        pre-approved for this stack — see `docs/TECH_STACK.md`); move
        reorders a widget among its own same-pinned-state peers only,
        so a pinned widget's "up"/"down" never silently swaps with an
        unrelated unpinned neighbor.
  - [x] Layout persistence (`localStorage`, key `jarvis.dashboard-
        layout`, same `jarvis.<name>` convention as `sidebar.store.ts`/
        `dock.store.ts`) + import/export (one JSON document, the same
        `{schemaVersion, values}`-shaped envelope `core/settings-
        framework.ts`'s `ModuleSettings.export()`/`.import()` already
        establishes; validated before being applied, never trusts an
        imported file's shape blindly).
- [x] Dock (registry- and enablement-driven, same pattern as Sidebar --
      pinned modules only render if also registered *and* enabled;
      active state from `WorkspaceManager`, not the route).
- [x] **Status Bar** *(added Aug 2026, Task Group E -- see
      `MASTER_ROADMAP.md` §8 M9's Plugin Registration System)*:
      registry-driven via `statusBarRegistry`, a named
      `ContributionRegistry` instance -- no hardcoded status items.
  - [x] `StatusBarContribution` type + `statusBarRegistry`.
  - [x] Core JARVIS's 9 built-in items (left: Current Workspace, Active
        Module; center: Current Running Task, Background Task
        Progress; right: AI Provider, Voice Status, Automation Status,
        Internet/Offline, Notification Indicator) -- all real data
        (`WorkspaceManager`, `background-tasks.store.ts`,
        `notifications.store.ts`, the existing WebSocket connection
        hook) or an honest "Not configured" where no backend data
        source exists yet (AI Provider, Voice Status, Automation
        Status) -- never fabricated.
  - [x] `DashboardWidgetContribution.render`'s type corrected to a real
        component reference (was `() => unknown`), matching
        `StatusBarContribution.render`'s contract, now that a real
        consumer proved out the correct shape.
- [ ] **Notification Center** *(moved to the Deferred Backlog, §6 —
      see there for detail)* — the persistent panel view over
      `core/notification-framework.ts`'s already-real data.
      `components/layout/notification-layer.tsx` exists today only as
      a reserved, empty anchor (`return null`).
- [ ] **Context Menu system** *(moved to the Deferred Backlog, §6)* —
      a reusable, registry-driven right-click menu system for Sidebar/
      Dock/Workspace items. `components/ui/context-menu.tsx` is only
      the shadcn/ui primitive; `components/layout/context-menu-
      layer.tsx` is the reserved, empty anchor for the real system.
- [ ] **Background Task Manager** *(moved to the Deferred Backlog, §6
      — real implementation is M9 Task Group C's job, not a second,
      frontend-only one)* — `stores/background-tasks.store.ts` is a
      display-only store today, not a real supervised queue.
- [ ] Workspace views (one per existing PySide6 workspace: Voice,
      Files & Drive, Browser, Coding, Finance, Smart Home, Calendar,
      Gmail, Spotify — ported feature-by-feature, not redesigned
      unless the feature itself changed). *(Deferred Backlog, §6.)*
- [ ] Window management (Tauri window APIs). *(Deferred Backlog, §6.)*
- [x] **Command Palette** *(Aug 2026, Task Group G)* — shell/keybinding
      only, per this phase's scope; see `MASTER_ROADMAP.md` M11B
      Productivity Suite for the full indexed-search feature.
  - [x] `Ctrl+K` **and** `Ctrl+Shift+P` both open it
        (`providers/command-palette-provider.tsx`) — the roadmap's
        canonical binding is `Ctrl+Shift+P`, but `components/layout/
        header.tsx`'s Search button has visually promised "Ctrl+K"
        since Phase 1; binding both keeps that promise honest rather
        than silently breaking it.
  - [x] Built on the already-scaffolded `CommandDialog`/`cmdk`
        primitive (`components/ui/command.tsx`, Phase 1) — fixed a
        real bug found while wiring it up: `CommandDialog` never
        wrapped its children in cmdk's own `<Command>` root, so
        `CommandInput`/`CommandList`/`CommandItem` threw at render
        time with no root context to read from. Never exercised until
        this task group gave it a real consumer.
  - [x] "Navigate" entries come from `ApplicationRegistry` +
        `ModuleEnablementStore` -- the same registry+enablement data
        Sidebar/Dock already read, not a separate nav-item list.
  - [x] "Commands" entries come from `getAllCommandPaletteEntries()`
        (`core/interfaces/navigation-interface.ts`) -- confirmed this
        is real, already-wired M8 Phase 2 infrastructure (every
        module's `mount()`/`unmount()` already calls
        `registerNavigation()`/its unregister fn via
        `BaseApplication`), not dead code. **No new `ContributionRegistry`
        instance was built for commands** -- one already exists for
        exactly this purpose; duplicating it would repeat the
        "multiple unrelated registries" mistake this project's rules
        warn against. Renders no "Commands" group today only because
        no module overrides `getNavigationContribution()` yet
        (`modules/placeholder-module.ts` deliberately doesn't) --
        honest emptiness, not a missing feature.
- [ ] Responsive layout.
- [ ] DPI scaling.
- [ ] Multi-monitor support.

### Phase 4 — Voice Experience & Motion
- [x] Remove the Orb (per the standing instruction from the earlier UI
      overhaul brief) — satisfied by construction: the React frontend
      never had an Orb to begin with (built fresh), so there was
      nothing to remove; **Task Group H** built its replacement
      directly.
- [x] **Voice String** *(Aug 2026, Task Group H, revised same month —
      renamed from "Voice Waveform" per the Premium UI & Voice
      Experience brief; same role, replaces the Orb)*: a real-time
      multi-bar waveform (40 independently-animated bars, not a single
      sine path — the original single-path version was superseded once
      the brief asked for a "premium real-time voice waveform" matching
      modern voice-assistant quality), rendered as a glassmorphism panel
      (blurred translucent background, soft state-colored bloom).
      Color/amplitude/envelope-shape communicate state -- no visible
      text label ("Listening...", "Thinking...") ever renders, per the
      brief's own rule; an `aria-label` carries the state name for
      screen readers only. Each bar derives its height from one shared
      `motion/react` `useTime()` clock via `useTransform` (one
      requestAnimationFrame loop feeding many cheap derived values,
      bound straight to the DOM, `transform`-only) rather than N
      independent loops. Respects `useReducedMotion()` (freezes the
      wave rather than animating) since `MotionConfig`'s app-wide
      `reducedMotion="user"` doesn't cover a manually-driven `useTime()`
      loop.
  - [x] `components/voice/voice-waveform-renderer.tsx` -- the pure
        renderer, no store dependency of its own. Accepts `voiceState`,
        `microphoneLevel`, `ttsLevel`, and `intensity` as props exactly
        as the brief specifies, so a future voice backend can stream
        real audio amplitudes into it with zero renderer changes.
        `components/voice/voice-string.tsx` is now just the thin layer
        wiring real store state into it -- state management and
        rendering are deliberately separate.
  - [x] `stores/voice-audio-levels.store.ts` -- real `microphoneLevel`/
        `ttsLevel` fields, always `0` today (no audio pipeline exists),
        additively boosting the renderer's procedural ambient motion
        once real. Same "honest zero until real" pattern as every other
        not-yet-backed store in this app.
  - [x] `core/voice-state-machine.ts` -- a real, validated state machine
        (mirrors `core/module-lifecycle.ts`'s pattern exactly: fixed
        states, a transition graph, a typed error on an illegal jump)
        for the full Idle/Wake/Listening/Thinking/Speaking/Success/Error
        set, superseding this line's earlier, vaguer "Thinking /
        Streaming Response / Speaking" wording.
  - [x] `stores/voice-state.store.ts` -- the single source of truth,
        starts and stays `idle` since no real voice backend exists yet
        (`core/interfaces/voice-integration.ts` only covers command
        bindings, no live state; no WebSocket voice event relay
        exists). Never a cosmetic animation with no backing state: the
        wave always renders whatever this store's real value is.
  - [x] Developer Mode's **Voice State Preview** panel
        (`features/developer/voice-state-preview.tsx`) -- manually
        drives or auto-cycles the real `voice-state.store.ts`, plus
        manual sliders for `microphoneLevel`/`ttsLevel` (writing to the
        real `voice-audio-levels.store.ts`) and a local `intensity`
        control, so every state -- and the renderer's full prop surface
        -- can be QA'd before either real backend exists. Disabled by
        default, never an end-user surface, never simulates a fake
        conversation.
- [x] Live Transcript view -- `components/voice/live-transcript.tsx`,
      streaming word-by-word (`voice-transcript.store.ts`), fades 4s
      after the last word arrives. Starts and stays empty (renders
      nothing) until a real speech-to-text stream exists -- no
      placeholder text.
- [x] **Startup Experience** *(Aug 2026, Task Group I, Premium UI &
      Voice Experience initiative)*: a choreographed ~4.2s cinematic
      sequence (point -> ripple -> logo assemble -> logo pulse -> morph
      into the Voice String -> Voice String activation -> Voice String
      expansion -> center-outward glass reveal) that replaces a bare
      loading flash with a wake-up moment, while genuinely
      lazy-registering the app's real startup work behind it. No
      startup text ever renders ("Loading...", progress %, etc. are
      explicitly excluded by the brief) -- only an `sr-only role="status"`
      string for screen readers.
  - [x] `core/startup-orchestrator.ts` -- `STARTUP_TASKS`, three real,
        high/medium-priority tasks (`registerCoreStatusBarItems`,
        `registerCoreDashboardWidgets`, `registerPlaceholderModules`)
        mapped from the brief's tier list onto what this codebase
        actually has to register today. `low` has no real tasks yet --
        left honestly empty rather than padded with a fake delay, per
        this project's "no fake data" rule; it starts doing real work
        the moment a real background service exists.
        `runStartupSequence()` is idempotent (caches its own in-flight/
        settled promise) -- **not just a defensive nicety**: React
        `<StrictMode>` double-invokes effects in development, and a
        second real call to `registerPlaceholderModules()` throws
        (`ApplicationRegistry` rejects a duplicate registration); the
        resulting unhandled rejection silently stalled the reveal
        forever until this was found and fixed. `__resetStartupSequenceForTests()`
        exists solely for test isolation.
  - [x] `components/startup/startup-sequence.tsx` -- the choreography
        itself, driving the **real** `voice-state.store.ts` (`wake` at
        the morph phase, `idle` at the expand phase) rather than a
        second, fake animation path; explicitly reuses the existing
        Voice String/`voice-waveform-renderer.tsx` as its centerpiece
        per the brief's "do not build a second Voice String" rule. The
        center-outward reveal is a real animated CSS
        `mask-image: radial-gradient(...)` (via `useMotionTemplate` +
        `useMotionValue`), not an opacity fade -- the literal mechanic
        the brief asked for.
  - [x] `components/startup/startup-gate.tsx` -- gates on **both** the
        real orchestrator work and the choreography's own completion
        (whichever finishes last), so the dashboard is never revealed
        before `ApplicationRegistry` is actually populated. Skips
        straight to the real app when `skipStartupAnimation` is set or
        `useReducedMotion()` reports a system preference -- "if startup
        animation is disabled: launch directly into Dashboard," per the
        brief.
  - [x] `stores/startup-preferences.store.ts` -- persisted
        `skipStartupAnimation`/`disableGlassEffects` preferences, both
        default `false`; registered in `StoreProvider`'s hydration gate
        so the skip preference is never read stale before rehydration
        completes.
  - [x] `components/layout/desktop-shell.tsx` -- an additive staggered
        fade/rise for Sidebar, Header+Workspace, Status Bar, and Dock on
        first mount, which -- since `StartupGate` only mounts the real
        app once startup is truly done -- naturally lands as the
        "everything animates smoothly into place" dashboard reveal the
        brief asks for, with no separate "startup just finished" signal
        needed.
  - [x] Developer Mode's **Startup Preview** section
        (`features/developer/startup-preview.tsx`) -- replays the real
        `StartupSequence` component on demand and exposes both real
        preferences as toggles, so the sequence and its accessibility
        escape hatches can be QA'd without restarting the app.
- [x] **Glass design system** *(Aug 2026, Task Group J, Premium UI &
      Voice Experience initiative)*: real glassmorphism (translucency +
      `backdrop-filter` blur) on Sidebar, the Card primitive, and
      Command Palette -- the three surfaces the brief names -- plus a
      subtle, static ambient glow behind `DesktopShell` so those blurs
      have real visual content to blur rather than a no-op over a flat
      background. Every surface offers a solid, non-blurred fallback:
      `hooks/use-glass-effects.ts`'s `useGlassEffectsEnabled()` wraps
      the real, persisted `disableGlassEffects` preference (Task Group
      I) behind a name that reads correctly outside a startup context.
      Wiring these new surfaces to that same existing preference (rather
      than a second, competing flag) makes it genuinely app-wide for the
      first time -- previously it only gated the startup sequence's own
      glow.
  - [x] Sidebar: `bg-card/70 backdrop-blur-xl`, falling back to solid
        `bg-card`.
  - [x] `components/ui/card.tsx` (the shared primitive every dashboard
        widget/dialog/panel already builds on): a conservative
        `bg-card/85 backdrop-blur-md` -- lighter blur than Sidebar/
        Command Palette on purpose, since Cards hold dense text at
        every size and legibility comes first.
  - [x] Command Palette: glass treatment scoped to `CommandDialog`'s own
        `DialogContent` override (`bg-popover/70 backdrop-blur-2xl`),
        not the shared `Dialog` primitive other dialogs use -- every
        other dialog in the app keeps its plain background.
  - [x] Verified live (not just unit tests): real `backdrop-filter`/
        `background-color` computed styles confirmed in the browser
        across all three themes (light/dark/jarvis) and with the
        preference both on and off.
- [x] **Accessibility settings** *(Aug 2026, Task Group K, Premium UI &
      Voice Experience initiative)*: a real Settings > Accessibility
      surface -- `features/settings/settings-page.tsx`, replacing the
      `settings` module's `PlaceholderRoute` -- exposing the three
      accessibility preferences (Skip startup animation, Reduced
      motion, Disable glass effects) as real, working toggles for the
      first time outside Developer Mode. `stores/startup-preferences
      .store.ts` renamed to `stores/accessibility-preferences.store.ts`
      (`useAccessibilityPreferencesStore`) -- it now backs real,
      app-wide UI, not just the startup sequence, and the old name had
      become misleading. Added a genuine third preference, `reducedMotion`
      -- an app-level override on top of `prefers-reduced-motion`, for
      users whose OS setting doesn't (or can't) express it.
  - [x] `providers/app-providers.tsx`'s new `AccessibleMotionConfig`
        feeds the real preference into `MotionConfig`'s own
        `reducedMotion` prop (`"always"` vs `"user"`), which every
        *declarative* Motion animation in the tree already consults
        internally -- covers `DesktopShell`'s stagger reveal,
        `JarvisLogo`'s pulse, etc. for free.
  - [x] Real bug found while wiring this up: the public `useReducedMotion()`
        hook (used directly by `startup-gate.tsx` and
        `voice-waveform-renderer.tsx`) only ever reads the OS-level
        media query and completely ignores `MotionConfig`'s own
        `reducedMotion` prop -- setting the app preference had zero
        effect on either of those two real call sites. Fixed by
        switching both to Motion's own `useReducedMotionConfig()` (the
        hook Motion uses internally to combine the two), rather than
        hand-rolling an equivalent.
  - [x] Developer Mode's Startup Preview panel gained a matching
        "Reduced motion" toggle alongside its existing two, so all
        three real preferences stay reachable from both surfaces.
- [x] **Dashboard widget drag-and-drop** *(Aug 2026, Task Group L,
      Premium UI & Voice Experience initiative — final task group)*:
      real mouse-driven drag-to-reorder for Dashboard widgets, additive
      alongside the existing Move up/down buttons -- neither replaces
      the other, both operate on the same `stores/dashboard-layout
      .store.ts` `order` array. Built on `motion/react`'s own
      `Reorder.Group`/`Reorder.Item` (already a dependency via Motion,
      no new drag library added) rather than a bespoke drag
      implementation.
  - [x] `reorderPeers(peerIds, pinned)` -- a new store action applying
        a full drag-produced permutation of one pin group, leaving the
        opposite pin group and any hidden widgets' positions untouched.
        Additive alongside `moveWidget()`'s existing discrete up/down/
        start/end steps.
  - [x] Two separate `Reorder.Group` instances in
        `features/dashboard/dashboard-grid.tsx`, one per pin group
        (`as="div" className="contents"` so neither introduces its own
        wrapper box -- their `Reorder.Item` children stay direct
        children of the existing CSS grid). Dragging a widget only ever
        reorders it among its own pin-group peers, the same constraint
        the Move buttons already enforce -- consistent semantics, not a
        second, looser interaction model.
  - [x] A dedicated drag handle (`dragListener={false}` +
        `useDragControls()`) rather than making the whole card
        draggable -- the card is full of its own interactive controls
        (buttons, the widget's own real content), so a whole-card drag
        target would fight with clicking any of them.
  - [x] Verified with a real, mouse-driven Playwright test
        (`e2e/dashboard-widgets.spec.ts`) using `page.mouse`, not a
        scripted DOM `dispatchEvent` -- Framer Motion's drag gesture
        recognition depends on genuinely trusted browser pointer events
        a synthetic dispatch can't faithfully reproduce, which a live
        check against the Browser pane confirmed firsthand (no reorder
        occurred from dispatched events; a real Playwright-driven mouse
        drag reordered correctly). This closes the Premium UI & Voice
        Experience initiative's five task groups (H, I, J, K, L).
- [ ] Conversation Timeline.
- [ ] Motion animations: hover, Sidebar, Dock, Cards, Notifications --
      broader premium-UI motion pass, still pending (see the Premium
      UI & Voice Experience initiative's later task groups).

### Phase 5 — Settings & User Profiles
- [ ] Dynamic Settings (schema-driven, mirrors the existing
      `PAGE_REGISTRY` self-registration pattern so new settings pages
      never require a central-file edit).
  - [ ] **Settings page structure** *(added Aug 2026 per the UI
        Architecture Update review — see `MASTER_ROADMAP.md` §8 M8
        Phase 5)*: General, Appearance, Voice, AI Models, Memory,
        Automation, Devices, Accounts, **Plugins** (enable/disable
        toggle over `ModuleEnablementStore`, distinct from Developer
        Mode's install/uninstall Plugin Manager below), Security,
        Developer Mode, Backup & Restore, About.
- [ ] Developer Mode (ports M5's gated panel set — Module Manager,
      Plugin Manager, API Center, Update Center, Developer Console,
      Security Center, Backup/Restore, System Information, Performance
      Monitor — feature-by-feature).
  - [ ] **API Center UI** *(added Aug 2026 per the roadmap
        architecture review — full design in `MASTER_ROADMAP.md` §8
        M11's API Center Architecture module)*, split into:
    - [ ] Built-in Providers section — Name, Status, Endpoint,
          Version, Health; no API key field.
    - [ ] External Providers section — Provider Name, Masked API Key,
          Status, Test Connection, Health, Last Used, Latency,
          Remaining Quota, Monthly Usage.
    - [ ] Provider cards (one per provider, either section).
    - [ ] API testing (per-provider "Test Connection" action).
    - [ ] Masked key display/entry.
    - [ ] Health dashboard.
    - [ ] Search and filters across providers.
  - [ ] **Developer API Analytics** *(same module)*: Usage Dashboard,
        Connection Status, Latency, Monthly Usage, Budget Usage —
        per-provider Request Count / Token Usage / Cost / Budget % /
        Success Rate / Module Usage, plus Usage Timeline, Cost Trend,
        Provider Comparison, and Monthly Statistics charts.
- [ ] Profile Service.
- [ ] Guest Mode.
- [ ] Profile Switching.
- [ ] Profile Storage.

### Phase 6 — Premium UI Polish
- [ ] Spacing audited against the design token scale.
- [ ] Typography audited against the ported `Typography` scale.
- [ ] Cards — final visual pass.
- [ ] Animations — final visual pass (builds on Phase 4).
- [ ] Icons — final visual pass.
- [ ] Production-quality pass across every view built in Phases 1–5.

### Phase 7 — Optimization & QA
- [ ] Accessibility audit (keyboard nav, screen reader, focus
      indicators — carries forward the M5.5 focus-indicator fix's
      standard).
- [ ] Performance pass (bundle size, render performance).
- [ ] Lazy loading for route-level code splitting.
- [ ] Bundle optimization.
- [ ] Responsive testing across window sizes.
- [ ] Regression testing (Vitest + React Testing Library + Playwright,
      per `TECH_STACK.md` §6).
- [ ] Cross-platform testing (Windows primary target, per the existing
      CI platform choice — see `MASTER_ROADMAP.md` §15).

---

## 3. Backend work this milestone requires

M8 is a frontend migration, but it is not frontend-only — every screen
above needs a FastAPI-facing counterpart:

- [ ] FastAPI router scaffold (`api/routers/`) mirroring each
      `features/<name>/` slice.
- [ ] WebSocket handler(s) for streaming concerns (chat, voice state,
      Agent Trace, automation/workflow progress) — relaying the
      existing `EventBus` events, not a parallel notification system.
- [ ] Auth/session handling for the FastAPI layer (backed by M14's
      Authorization Engine once that milestone ships; a minimal local
      session mechanism until then).

No `services/`, `agents/`, `domain/`, or `infrastructure/` code changes
shape for this milestone — see `TECH_STACK.md` §1 for why.

---

## 4. Exit criteria

M8 is done when every phase above is checked off, the PySide6 UI is no
longer the primary interface (retained or removed per a separate,
explicit decision — not implied by this document), and M8's
Acceptance Criteria in `MASTER_ROADMAP.md` §8 are met. This document
does not restate those acceptance criteria — see the roadmap entry
itself so there is exactly one place they can drift out of sync from.

---

## 5. M9 — Runtime & Core Services (✅ Completed — all five task groups shipped)

Placed after §4 rather than renumbered in between M8's own sections,
matching this project's "zero renumbering" convention applied to
document structure, not just milestone numbers — M9's real work began
here while M8's own Phases 2–3/5–7 are still open, tracked in §2
above.

- [x] **Task Group A — Runtime Manager & Application Lifecycle**
      *(Aug 2026 — see `MASTER_ROADMAP.md`'s own changelog addendum
      for the full reasoning and design)*: `core/lifecycle/
      shutdown_manager.py`'s `ShutdownManager` (M5.5) renamed and
      generalized to `core/lifecycle/runtime_manager.py`'s
      `RuntimeManager` — the shutdown-side API is behavior-unchanged
      (renamed only), with a new symmetric startup-side API
      (`register_startup`/`unregister_startup`/`startup`) sharing the
      same priority-ordered, fault-isolated hook design. `app.py`'s
      two ad-hoc best-effort startup steps (memory-policy enforcement,
      Whisper preload) now register as real startup hooks instead of
      hand-written `try`/`except` blocks. `AppReadyEvent`/
      `ShutdownRequestedEvent` (`core/events/events.py`) — previously
      unused placeholder event types — now genuinely publish on the
      real `EventBus`, at real startup-complete and
      shutdown-beginning points respectively.
  - [x] All 17 real call sites updated for the rename across `src/`
        and `tests/` (DI container's `shutdown_manager` provider →
        `runtime_manager`, `MainWindow`, `AgentCheckpointer`'s
        docstring, every test asserting the container's provider
        surface or exercising shutdown behavior directly). Genuinely
        historical prose (M5.5's own "Real, verified fixes" narrative
        in `MASTER_ROADMAP.md`, a `TROUBLESHOOTING.md` entry pointing
        at a specific old build) deliberately left referring to
        `ShutdownManager` by its name at the time.
  - [x] Full pytest suite passes; `runtime_manager.py` and its test
        file (`tests/unit/test_runtime_manager.py`) are mypy- and
        ruff-clean. Pre-existing mypy/ruff findings in the touched
        files (container.py's un-annotated `providers.Singleton`
        assignments, the project-wide accepted-debt `PLC0415`
        lazy-import pattern `MASTER_ROADMAP.md` §15 already documents)
        were confirmed by diff scope to predate this task group and
        were left alone.
  - [x] Exposing Application Lifecycle state to M8's frontend over
        WebSocket — shipped as part of Task Group B's Runtime WebSocket
        API, below.
- [x] **Task Group B — Service Manager, Session Manager, Configuration
      Manager, Runtime Health Monitor, Runtime WebSocket API, Runtime
      Integration** *(Aug 2026 — see `MASTER_ROADMAP.md`'s own
      changelog addendum for the full reasoning and design)*: closes
      out Runtime Core in full.
  - [x] `core/interfaces/service.py` — `IService` Protocol (`docs/
        ARCHITECTURE.md` §8) made real code for the first time,
        `HealthStatus`/`ServiceStatus` dataclasses.
  - [x] `core/lifecycle/service_manager.py` — `ServiceManager`:
        dependency-ordered startup/shutdown, restart, health polling,
        fault isolation. Wraps `ConversationService`/`ChatService`/
        `MemoryService`/`ThemeService` in thin `IService` adapters
        (composition, not retrofit) — `VoiceService`/`HotkeyService`
        stay under `MainWindow`'s existing shutdown-hook ownership;
        `BrowserService`/`AutomationService`/`SystemService` (DI
        `Factory` providers, no stable identity) are out of scope.
  - [x] `core/lifecycle/session_manager.py` — `SessionManager`: a new
        `RuntimeSession` table (nullable, optional links to
        `Conversation.id`/LangGraph `thread_id`, not a forced merge),
        persisted creation/close, dangling-session recovery after an
        unclean shutdown (tested across two independent database
        instances).
  - [x] `core/lifecycle/configuration_manager.py` — `ConfigurationManager`:
        live `reload()` restricted to `SAFE_RELOAD_SECTIONS` (`ui`,
        `voice_announce`, `memory`, `update`, `dev_mode`), grounded in
        `ChatService.stream()`'s observed per-call settings read;
        provider credentials/`enabled` flags stay immutable.
  - [x] `core/lifecycle/health_monitor.py` — `HealthMonitor`: non-blocking
        `psutil`-based CPU/RAM/uptime/startup-duration/service-health/
        restart-count polling, `health.updated` events,
        `register_collector()` extension point for future GPU/plugin/
        network metrics.
  - [x] `core/lifecycle/runtime_ws_hub.py` + `infrastructure/api/routes/
        runtime_ws.py` + `infrastructure/api/routes/sessions.py` —
        `docs/ARCHITECTURE.md` §6's WebSocket standard made real at
        `/api/v1/ws`: envelope, 30s heartbeat, `resume`/60s replay
        buffer, all eleven events (`runtime.*`, `service.*`,
        `configuration.updated`, `session.*`, `health.updated`).
        Authenticated via a `SessionManager` session id
        (`POST /api/v1/sessions`) standing in for M14's future
        Bearer/JWT session tokens.
  - [x] `infrastructure/api/embedded_server.py` — embeds the FastAPI
        app inside the existing PySide6/qasync loop so the WebSocket
        relay is actually reachable from the one real running app
        today, not a placeholder nothing serves.
  - [x] `app.py`'s new `_register_task_group_b_hooks` wires all five
        managers into `RuntimeManager` in deterministic order
        (Configuration → Service → Session → Health/WS relay/embedded
        server → Application Ready), shutdown reverse.
        `RuntimeManager` gained an optional `event_bus` parameter
        (every existing zero-arg test still passes) to publish the
        new `RuntimeStartedEvent`/`RuntimeShutdownCompleteEvent`.
  - [x] 58 new tests (service registration/ordering/restart/failure
        isolation, session persistence/recovery, safe-reload,
        non-blocking health polling, real FastAPI `TestClient` WebSocket
        transport incl. auth reject/resume/replay-window-expired) — full
        suite 524 passed, zero regressions. mypy/ruff/black diffed
        against a clean pre-task-group `git stash` baseline: zero new
        findings outside the pre-existing, already-accepted
        `providers.Singleton` annotation and `PLC0415` lazy-import
        patterns §15 documents.
  - **Future Work** (explicitly deferred, not implemented): retrofitting
        `VoiceService`/`HotkeyService`/`BrowserService`/
        `AutomationService`/`SystemService` onto `IService`; cascading
        `ServiceManager.restart()` to dependents; unifying
        `RuntimeSession` with `Conversation`/`thread_id` beyond the
        optional link added here; extending `docs/ARCHITECTURE.md` §6's
        category table to the pre-existing `voice`/`ai`/`automation`/
        `memory`/`progress`/`notification` categories; a genuine
        headless `_run_api_only()` runtime mode; M14's real Bearer/JWT
        session-token issuance.
- [x] **Task Group C — Reliability** *(Aug 2026 — see
      `MASTER_ROADMAP.md`'s own changelog addendum for the full
      reasoning and design)*: Background Task Manager, Crash Recovery,
      Resource Manager. Builds on `ServiceManager`/`HealthMonitor`
      (Task Group B) rather than a parallel mechanism.
  - [x] `core/lifecycle/background_task_manager.py` —
        `BackgroundTaskManager`: bounded-concurrency
        (`asyncio.Semaphore`) task queue, per-task fault isolation,
        `submit()`/`cancel()`/`stop()` (graceful drain). A
        done-callback fallback handles the real edge case its own test
        suite found: a task cancelled before its coroutine's first
        scheduling turn never runs any of its own body (Python's
        `.throw()` into an unstarted coroutine re-raises immediately
        without entering it), so `_run()`'s own `except
        CancelledError` can't be relied on alone.
  - [x] `core/lifecycle/crash_recovery.py` — `CrashRecoveryManager`: a
        "mark dirty at start, mark clean at end" on-disk marker
        (`runtime_state.json`, existing `config_dir` JSON-config-store
        convention) detects an unclean previous shutdown, publishes
        `CrashRecoveredEvent`. Explicitly does not claim to
        auto-respawn a crashed process — real, separate future work.
  - [x] `core/lifecycle/resource_manager.py` — `ResourceManager`: CPU/
        memory budget tracking (new `ResourceSettings`) by subscribing
        to `HealthMonitor`'s existing `HealthUpdatedEvent` rather than
        polling `psutil` a second time. Publishes
        `ResourceBudgetExceededEvent` only on the transition into
        violation, not every tick over budget.
  - [x] `app.py`'s new `_register_task_group_c_hooks` wires all three
        into `RuntimeManager`: Crash Recovery's dirty-check runs right
        after Configuration Manager (before Service Manager);
        Background Task Manager and Resource Manager join at the end
        of startup. Shutdown reverses this, with Crash Recovery
        marking the run clean *last of all*, after every other
        shutdown hook has finished. Task Group B's own five shutdown
        priorities were renumbered (0-4 → 2-6, in-place, no migration
        concern) to make room.
  - [x] `RuntimeWebSocketHub`'s `EVENT_TYPE_NAMES` gained
        `runtime.crash_recovered`, `task.started/completed/failed`,
        `resource.budget_exceeded`.
  - [x] 29 new tests (bounded concurrency, fault isolation, both
        cancellation code paths, crash detection across independent
        marker-file instances, corrupt-marker resilience,
        budget-transition-only publishing) — full suite 542 passed,
        zero regressions. mypy/ruff/black diffed against a clean
        pre-task-group `git stash` baseline: zero new findings outside
        the same pre-existing, already-accepted `providers.Singleton`
        annotation and `PLC0415` patterns §15 documents.
  - **Future Work** (explicitly deferred, not implemented): an
        external supervisor/watchdog process for genuine automatic
        process restart after a crash; GPU/disk collectors for
        `HealthMonitor` (`ResourceManager.register_budget()` already
        supports them once a collector exists); enforcement
        (throttle/kill) on a budget breach; persisting/resuming the
        Background Task Manager's queue across a restart.
- [x] **Task Group D — Plugin Platform** *(Aug 2026 — see
      `MASTER_ROADMAP.md`'s own changelog addendum for the full
      reasoning and design)*: closes out M9's Plugin Platform module in
      full, preserving the original scope unchanged.
  - [x] Plugin SDK (`core/plugins/sdk.py`, `manifest.py`) — `IPlugin`'s
        three lifecycle hooks, the fixed 10-scope permission
        vocabulary, a hand-rolled semver/range comparator, and
        `PluginManifest` (pydantic, frozen) extended with the Universal
        Compatibility fields (`supported_os`, `supported_arch`,
        `required_capabilities`, `min_jarvis_version`), all
        platform-neutral by default.
  - [x] Platform Abstraction Layer (`core/interfaces/platform.py` +
        `infrastructure/platform/adapter.py`) — added for Universal
        Compatibility; Windows is the only implemented adapter, but
        nothing above `IPlatformAdapter` branches on OS directly, so a
        future Linux/macOS adapter is a second implementation, not a
        redesign.
  - [x] Plugin Loader (`loader.py`) — discovery, Kahn's-algorithm
        dependency ordering (fault-isolating a cycle/missing dependency
        to just the affected plugin(s), deliberately more tolerant than
        `ServiceManager`'s own stricter rule), full compatibility
        checks, and real hot reload (reads source and compiles fresh
        every call — a real `.pyc`-cache staleness bug its own tests
        caught and fixed).
  - [x] Secure Plugin Sandbox (`sandbox.py`) — in-process (default,
        fault-isolated + timeout-bounded) and opt-in out-of-process
        (`multiprocessing`, real `psutil`-based resource-budget
        monitor-and-terminate) tiers.
  - [x] Extension API (`extension_api.py`) — `PluginContext`:
        permission-gated `filesystem`/`network`/`hotkeys`/
        `notifications`, unrestricted `events`/`commands` (both scoped
        to the plugin's own declared surface), `config`, `platform`.
  - [x] Permission Model (`permissions.py`) — the real
        `IPermissionChecker`: least-privilege by construction (declare
        -> pending -> grant/deny), persisted, audited, event-published.
  - [x] Plugin Registration System (`registry.py`) — `PluginRegistry`:
        enable/disable, install/uninstall, update with real rollback
        support (Plugin Safe Core Architecture's requirement, verified
        under test), health/status tracking.
  - [x] Plugin Store Foundation (`store.py`) — directory/`.zip` package
        staging (Zip Slip-guarded), real SHA-256 integrity checks, real
        Ed25519 signature verification (`cryptography`, already a
        pinned dependency) with an honest unsigned-allowed v1 default.
  - [x] Marketplace Foundation (`marketplace.py`) — `IPluginRepository`
        abstraction (a future hosted repository is a second
        implementation, not a redesign), real `LocalPluginRepository`
        + search/categories, genuinely functional in-memory
        ratings/reviews.
  - [x] `app.py`'s `_register_task_group_d_hooks` wires `PluginRegistry`
        into `RuntimeManager` as the outermost layer: starts last
        (priority 12), stops first (priority -1), a no-op when
        `settings.plugins.enabled` is false. `RuntimeWebSocketHub`
        gained eleven `plugin.*` relay categories.
  - [x] 199 new tests across twelve files, including a real end-to-end
        integration test (`tests/integration/test_plugin_platform_e2e.py`)
        loading the real `tests/fixtures/plugins/hello_world` plugin
        through the entire stack — proving the module's own acceptance
        criterion, "a hello-world plugin registers a slash command and
        a hotkey." Full suite: 741 passed (up from 542), zero
        regressions; frontend: 293 passed, unaffected. mypy/ruff/black
        diffed against a clean pre-task-group `git stash -u` baseline:
        zero new findings outside the same pre-existing, already-accepted
        `providers.Singleton` annotation and `PLC0415` patterns §15
        documents.
  - **Future Work** (explicitly deferred, not implemented): a real
        IPC-relayed Extension API for process-isolated plugins (today
        `MinimalPluginContext` only); outbound-request mediation/quota
        enforcement for the `network` permission scope; a hosted,
        signed Plugin Store index and a real `GitHubPluginRepository`/
        `CloudPluginRepository`; persisted, multi-session ratings/
        reviews with real user identity; an interactive
        permission-approval UI (the workflow itself is real; only the
        visual surface is Task Group E's to build).
- [x] **Task Group E — Developer Platform Tools** *(Aug 2026 — see
      `MASTER_ROADMAP.md`'s own changelog addendum for the full
      reasoning and design)*: closes out M9 in full. **Milestone 9 is
      now 100% complete across all five task groups.**
  - [x] `core/devtools/` — Debug Console + Live Logs
        (`debug_console.py`: a real loguru sink into a bounded,
        filterable buffer, plus a published event per line), Performance
        Profiler (`performance_profiler.py`: real time-series history
        over `HealthMonitor`'s existing poll-tick snapshots), State
        Inspector (`state_inspector.py`: combines `ServiceManager`'s and
        `PluginRegistry`'s own real snapshots), API Inspector
        (`api_inspector.py`: a real Starlette middleware over this app's
        own `/api/v1/*` traffic — method/path/status/duration only,
        never bodies or headers).
  - [x] `infrastructure/api/auth.py` — the real
        `Depends(get_current_session)` Bearer-auth dependency and
        `{data, meta}` `Envelope` helper, finally implementing what
        Task Group B's own docs had referenced by name since it shipped.
  - [x] `infrastructure/api/routes/plugins.py` — the real Plugin
        Marketplace Foundation + Permission Management REST API: full
        plugin lifecycle, permission grant/deny/revoke/pending/audit,
        marketplace browse/search/categories/get/reviews. The first
        real resource routes to follow `docs/ARCHITECTURE.md` §5's
        contract in full (envelope + auth), resolving the two
        exceptions `/api/v1/sessions` needed.
  - [x] `infrastructure/api/routes/devtools.py` — REST reads over the
        four new `core/devtools/` components, plus Plugin Diagnostics
        (one combined status/health/logs/audit view per plugin).
  - [x] `app.py`'s `_register_task_group_e_hooks` bookends every other
        hook (Debug Console/Performance Profiler start first, stop
        last). `RuntimeWebSocketHub` gained the eleven `plugin.*`
        categories Task Group D's events had defined but never wired to
        a relay, plus `devtools.log_captured`.
  - [x] **Real bug found and fixed in Task Group D** by these tests
        running against a genuine Windows machine for the first time:
        `platform.machine()` reports `"AMD64"` on Windows, not
        `"x86_64"` — every plugin manifest's default `supported_arch`
        was silently rejecting every real Windows install.
        `infrastructure/platform/adapter.py` now normalizes this at the
        Platform Abstraction Layer boundary.
  - [x] 74 new tests across nine files, including a real end-to-end test
        (`tests/integration/test_devtools_platform_e2e.py`) proving the
        REST API drives the real `PluginRegistry`/`PermissionModel` *and*
        that the result relays over the real Runtime WebSocket API.
        Full suite: 815 passed (up from 741), zero regressions. mypy/
        ruff/black diffed against a clean pre-task-group `git stash -u`
        baseline: every finding category byte-for-byte unchanged except
        `PLC0415` (+24, the same accepted test-fixture convention
        `test_runtime_ws_route.py` already established) — zero new
        findings of any other kind, zero new mypy findings.
  - **Future Work** (explicitly deferred, not implemented): an
        interactive permission-approval UI (the real workflow's visual
        surface, most naturally M8's React frontend); batching Live
        Logs' per-line relay if sustained high-volume logging ever
        becomes a real scenario; persisting Performance Profiler's
        history across a restart; a REST clear/reset endpoint for API
        Inspector (only Debug Console has one).

**Dependencies note:** M9's own documented dependency on M8
(`MASTER_ROADMAP.md` §8) is narrow — Developer Platform Tools' and
Marketplace's *consumer* surfaces, which already exist and work today
(Developer Mode, Task Group F's Dashboard/Command Palette work). Task
Groups A, B, C, D, and E touched neither, so none were blocked by M8's
remaining Phase 2–3/5–7 backlog, and none of M9's Deferred Backlog
dependency (§6) ever materialized into an actual blocker.

---

## 5A. M10 — AI Orchestrator (🟡 Partial — buildable-now scope shipped)

M10 formally depends on M10A (Universal Search & Knowledge Platform)
and M14 (Authorization Engine), neither of which has started. Rather
than block, this pass shipped everything real without them and
documented the rest as explicitly deferred — see
`MASTER_ROADMAP.md`'s own Aug 2026 M10 changelog addendum for the full
reasoning and design. **M10 is not 100% complete.**

- [x] Intent Engine — `agents/nodes/intent_classifier.py`, a new node
      before `planner` classifying the request into `tool_use` /
      `direct_answer` / `clarification_needed` with a confidence score.
      Diagnostic only: nothing yet branches graph routing on it.
- [x] Context Engine (scoped) — `agents/nodes/context_engine.py`,
      assembles context from M3 Memory before planning. The M10A
      knowledge-graph half is deferred (M10A not started).
- [x] Parallel tool dispatch (Acceptance Criterion 1, also closing out
      M7 Phase 3's deferred cross-tool-parallelism scope) —
      `tool_selector.py`'s new `tool_parallel` decision shape,
      `tool_executor.py`'s concurrent dispatch via the existing
      `gather_with_concurrency`, bounded by
      `AgentSettings.max_parallel_steps` (declared M7, unread until
      now). Single-tool path unchanged, byte-for-byte.
- [x] Permission Validation, interim (Acceptance Criterion 3) —
      `agents/permission.py`'s `AgentPermissionGate` + a new
      `permission_validator` node, the one enforcement point every
      proposed tool call now passes through. Explicitly interim pending
      M14; `AgentSettings.confirm_required_tools` (default
      `{"run_automation"}`) is today's policy.
- [x] Real token-level streaming (Acceptance Criterion 2) —
      `AgentOrchestrator.stream()` now yields real per-token output via
      `ILLMProvider.stream()` for the tool-composed path, using a
      second responder-less compiled graph
      (`build_agent_graph(..., include_responder=False)`) and a shared
      prompt builder (`build_final_response_prompt`). The
      no-tool-needed "final" shortcut still replays precomposed text —
      a documented, scoped exception (JSON-embedded text can't be
      cleanly token-streamed without restructuring tool selection).
- [x] Decision Engine — `response_mode` (`"direct"`/`"composed"`) added
      to `AgentState`.
- [x] `agent.step` added to `RuntimeWebSocketHub.EVENT_TYPE_NAMES` —
      real-time Agent Trace over the existing `/api/v1/ws` relay.
- [x] `infrastructure/api/routes/agent.py` — `POST /api/v1/agent/invoke`
      (envelope) and `POST /api/v1/agent/stream` (real token-level SSE,
      a documented exception to the envelope rule). Same
      `Depends(get_current_session)` Bearer auth as
      `routes/plugins.py`/`routes/devtools.py`.
- [x] 24 new tests (unit: Intent/Context Engine, parallel dispatch,
      `AgentPermissionGate`, the new route; integration: parallel
      dispatch, permission denial, and real streaming end-to-end).
      839/839 passing, zero regressions. Ruff/mypy findings proportional
      to the pre-existing accepted baseline — zero new categories.
  - **Deferred** (documented, not silently dropped): Context Engine's
        knowledge-graph half (needs M10A); Learning/Feedback via M16's
        Reflection Engine (needs M16); Permission Validation's final
        M14-routed form (needs M14); Intent Engine gating graph routing
        (needs M10A/M10B for real signal); the "final" shortcut path's
        real token streaming; PySide6 Agent Trace view / React frontend
        wiring to `/api/v1/agent` (M8's own remaining phases).

**Dependencies note:** M10's formal dependencies are M5A (✅, extended
directly), M8 (🟡 partial — the backend WebSocket transport this pass
needed is real via M9; M8's own remaining frontend phases are
unaffected either way), M10A (🔴, blocks Context Engine's full scope),
M14 (🔴, blocks Permission Validation's final form).

---

## 6. Deferred Backlog

*(Added Aug 2026 — roadmap reconciliation pass, ahead of M9 Task Group
C. Everything below is real, tracked, non-blocking work explicitly
deferred out of M8's active scope — not dropped, not forgotten, and
not required for M9's Runtime Core (shipped), Reliability, Plugin
Platform, or Developer Platform Tools modules. See the Dependencies
note above and in §5 for why M9 was never blocked on any of this.)*

### M8 Phase 3 — Desktop Workspace (remainder)
- [ ] **Notification Center** — the persistent panel view over
      `core/notification-framework.ts`'s already-real data (distinct
      from the ephemeral toast surface, `providers/notification-
      provider.tsx`'s `<Toaster />`, which already ships).
      `components/layout/notification-layer.tsx` is a reserved, empty
      anchor point today.
- [ ] **Context Menu system** — a reusable, registry-driven right-click
      menu system for Sidebar/Dock/Workspace items.
      `components/layout/context-menu-layer.tsx` is a reserved, empty
      anchor point today; `components/ui/context-menu.tsx` is only the
      underlying shadcn/ui primitive (Phase 1).
- [ ] **Background Task Manager** (frontend surface) — real supervised
      task-queue UI, once M9 Task Group C ships the actual backend
      queue; `stores/background-tasks.store.ts` stays a display-only
      store, not a second, competing implementation.
- [ ] Workspace views — Voice, Files & Drive, Browser, Coding, Finance,
      Smart Home, Calendar, Gmail, Spotify (one React view per existing
      PySide6 workspace).
- [ ] Window management (Tauri window APIs).
- [ ] Responsive layout, DPI scaling, multi-monitor support.

### M8 Phase 2 — Universal Application Framework & Logic (in full)
- [ ] Business Logic → State Machine → Service Layer → Hooks → Store
      pattern, Authentication, Permissions, Storage, Settings API
      layer, Voice/AI/Automation Integration, Offline support, Error
      handling, and the full API Integration Rework block — see §2
      above for the complete itemized list.

### M8 Phase 5 — Settings & User Profiles (in full)
- [ ] Dynamic Settings, Settings page structure (General/Appearance/
      Voice/AI Models/Memory/Automation/Devices/Accounts/Plugins/
      Security/Developer Mode/Backup & Restore/About).
- [ ] **Developer Mode's 9 read-only viewers** — Module Manager, Plugin
      Manager, API Center, Update Center, Developer Console, Security
      Center, Backup/Restore, System Information, Performance Monitor.
      Only the Developer Mode shell (`features/developer/developer-
      panel.tsx`), Module State Inspector, Startup Preview, and Voice
      State Preview exist today.
- [ ] API Center UI + Developer API Analytics (full module — see §2).
- [ ] Profile Service, Guest Mode, Profile Switching, Profile Storage.

### M8 Phase 6 — Premium UI Polish (in full)
- [ ] Spacing, Typography, Cards, Animations, Icons audited against
      the design-token scale; production-quality pass across every
      view built in Phases 1–5.
- [ ] Conversation Timeline.
- [ ] The broader motion pass (hover, Sidebar, Dock, Cards,
      Notifications) — beyond what Task Group H–L already shipped.

### M8 Phase 7 — Optimization & QA (in full)
- [ ] Accessibility audit, performance pass, lazy loading, bundle
      optimization, responsive testing, regression testing,
      cross-platform testing — see §2 above for the complete list.

**Why deferred, not implemented now:** M8's own Phase 1 (React
Foundation) and Phase 4 (Voice Experience & Motion, in full) shipped;
everything above is real, scoped work that simply wasn't next in
priority order once the roadmap architecture review redirected effort
to M9's Runtime Core (which had zero real dependency on any of it).
**M8 is not 100% complete** and should not be treated as shipped —
this backlog is the explicit record of what remains, so none of it
silently disappears from the roadmap.
