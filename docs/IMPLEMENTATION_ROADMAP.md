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
- [ ] Dashboard (Home) view.
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
- [ ] **Dashboard Widget Grid** *(added Aug 2026 per the UI
      Architecture Update review — see `MASTER_ROADMAP.md` §8 M8
      Phase 3)*:
  - [x] `DashboardWidgetRegistry` + `DashboardWidgetContribution`
        (foundation only — mirrors `ApplicationRegistry`'s pattern;
        no widget grid UI renders these yet -- that's the next task).
  - [ ] Built-in widgets: Tasks, Calendar, Notes, Notifications,
        Recent Activity, Quick Actions, System Status.
  - [ ] Grid layout (add/remove/resize/move/pin).
  - [ ] Layout persistence + import/export.
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
- [ ] Command Palette (`Ctrl+Shift+P`) — see `MASTER_ROADMAP.md`
      M11B Productivity Suite for its full feature scope; this phase
      ships the shell/keybinding, M11B ships the full indexed-search
      backend.
- [ ] Responsive layout.
- [ ] DPI scaling.
- [ ] Multi-monitor support.

### Phase 4 — Voice Experience & Motion
- [ ] Remove the Orb (per the standing instruction from the earlier UI
      overhaul brief — never carried out on the PySide6 side, now
      executed directly in the new frontend instead of twice).
- [ ] Voice Waveform component, replacing the Orb.
- [ ] Live Transcript view.
- [ ] Thinking / Streaming Response / Speaking states — each a real
      state from the voice/agent state machine (Phase 2), never a
      cosmetic animation with no backing state.
- [ ] Conversation Timeline.
- [ ] Motion animations: hover, Sidebar, Dock, Cards, Notifications.

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
