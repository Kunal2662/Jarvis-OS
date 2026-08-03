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
> documents.

**Document owner:** project lead
**Status:** Aug 2026 — tracks M8 (React Frontend & Desktop Experience),
the active milestone as of this writing. Phase 1 (React Foundation)
shipped; Phases 2–7 remain pending, each its own separately-approved
implementation pass.

---

## 1. Where things stand

| Milestone | Status |
|---|---|
| M0 – M7 | Shipped (M7 partially — Phases 1–2 shipped, Phase 3 deferred, Phases 4–6 pending). See `MASTER_ROADMAP.md` §3 and §8. |
| **M8 – React Frontend & Desktop Experience** | **Active — this document tracks it.** |
| M9 onward | Planned, not started. See `MASTER_ROADMAP.md` §8. |

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
- [ ] Workspace views (one per existing PySide6 workspace: Voice,
      Files & Drive, Browser, Coding, Finance, Smart Home, Calendar,
      Gmail, Spotify — ported feature-by-feature, not redesigned
      unless the feature itself changed).
- [ ] Window management (Tauri window APIs).
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
