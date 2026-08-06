# JARVIS OS — Implementation Roadmap (Active)

> ### Development policy (Aug 2026) — read before starting a phase
>
> | Area | Status |
> |---|---|
> | Backend architecture · API contracts · Database schema · Core backend modules · Milestone structure | 🔒 **Frozen** |
> | Frontend / UI / UX | 🟢 **Continues** |
>
> No additional backend architecture is introduced unless explicitly
> approved **after UI validation.** A phase below that appears to need a
> new backend route, model or contract should stop and raise it, not
> add one.
>
> **Approved architecture decisions are recorded but not scheduled.**
> Local AI First, the Universal AI/API Calibration Engine, the AI Cost
> Optimizer, the three-tier AI strategy, the Oracle Cloud role, the
> voice provider abstraction, hardware calibration, the Universal
> Performance Engine, the installation platform, the two-account model
> and the hidden-backend-operations rule are specified in
> [`ARCHITECTURE.md` §22](ARCHITECTURE.md#22-approved-architecture-decisions-aug-2026).
> **None of it is in any checklist in this document**, and none of it is
> in scope for the phases below. Cross-Platform Distribution is the one
> exception with a milestone: it joins M22.
>
> The binding rule until the Calibration Engine exists: **do not build a
> competing design.** A phase needing provider routing, cost control,
> voice-provider selection or hardware profiling raises a blocker rather
> than solving it locally.

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
> **M10 is partial, not 100% complete;** the M14/M16-dependent
> remainder is explicitly deferred, documented rather than dropped. See
> §5A below. M10A (Universal Search & Knowledge Platform) has since
> shipped in full except File Search (deferred pending M11B) —
> **M10A is complete**, closing M10's own Context Engine
> knowledge-graph deferral in the process. See §5B below. M10B
> (Intelligence Layer) has since shipped in full except automatic
> scheduled Daily Briefing delivery (deferred pending M7's Scheduler
> Phase 6) — **M10B is complete.** See §5C below.

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
| **M10 – AI Orchestrator** | 🟡 **Partial — buildable-now scope shipped; M14/M16-dependent remainder deferred. Context Engine's knowledge-graph half closed by M10A. See §5A below and `MASTER_ROADMAP.md` §8/§14.** |
| **M10A – Universal Search & Knowledge Platform** | ✅ **Completed — File Search deferred pending M11B. See §5B below and `MASTER_ROADMAP.md` §8/§14.** |
| **M10B – Intelligence Layer** | ✅ **Completed — automatic scheduled Daily Briefing delivery deferred pending M7's Scheduler (Phase 6). See §5C below and `MASTER_ROADMAP.md` §8/§14.** |
| **M10.5 – MCP & Integration Platform** | ✅ **Completed (`0.20.0`) — all five task groups.** Capability Registry, client/server runtimes, negotiation, DI, runtime events, `/api/v1/mcp/*` (A); all four transports (stdio/websocket/http/ipc), transport factory, discovery/query, heartbeat (B); provider interface, registry with filtered discovery, lifecycle manager, health collection (C); credential model, encrypted store, auth strategies, provider sessions, permission bridge (D); SDK builders, validation framework, `jarvis mcp` CLI, self-contained examples, `MCPDiagnostics`, `/api/v1/mcp/diagnostics` + `/validate` (E). Generic infrastructure throughout — real providers, the OAuth flow, a server-side listener and vendor integrations are M11's scope. See §5D below and `MASTER_ROADMAP.md` §8/§14. |
| **M13B – Self-Healing & Observability** | 🔴 Planned, not started. *(New lettered companion to M13, added Aug 2026 — the foundational subset of M18/M20A, which remain their full-scale realizations. M13A "AI Sandbox" is unchanged.)* See `MASTER_ROADMAP.md` §8 and §14. |
| M11 onward | 🔴 Planned, not started. See `MASTER_ROADMAP.md` §8 and §14. |

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
- [x] Business Logic → State Machine → Service Layer → Hooks → Store
      pattern established as the mandatory shape for every application
      (mirrors the PySide6-era `ModuleStateMachine` foundation —
      `domain/app_state/` — ported to a TypeScript equivalent, not
      redesigned from scratch). `core/module-lifecycle.ts` is that port
      (12 states, same transition graph, `InvalidStateTransitionError`)
      and shipped in Phase 1; Phase 2 supplies the Service Layer and
      Hooks tiers the pattern was missing (`services/`, `hooks/use-
      backend-status.ts`) and follows the direction strictly — no
      business logic in a store, no `websocketManager` import in a
      component.
- [x] Authentication flow against the FastAPI backend —
      `services/api/session.ts`. One credential across both transports
      (Bearer header for REST, `?token=` for the WebSocket), per
      `ARCHITECTURE.md` §5/§6. Not persisted, deliberately: backend
      sessions do not survive a restart, and M11 Task Group F tightened
      `/sessions/{id}` because a leaked id is a real problem.
- [x] Permissions model surfaced from the backend's Authorization
      Engine (M14) — surfaced from **M9's `PermissionModel`**, the
      Authorization Engine that actually exists, whose ten-scope
      vocabulary `core/permission-framework.ts` already mirrors exactly.
      `services/permissions-sync.ts` feeds the existing framework rather
      than adding a second permission system; write-through asks the
      backend first, so a permission is never shown as held that the
      enforcing process does not recognise. Repoints in one place if a
      future M14 supersedes it.
- [x] Storage — client-side persistence layer (Tauri's filesystem
      APIs / local storage as appropriate per data sensitivity).
      `core/storage-framework.ts` already implements all four
      sensitivity tiers of `ARCHITECTURE.md` §12, including refusing
      client-side encryption rather than pretending to offer it.
      Verified as sufficient; no new work, and none invented.
- [x] Settings — API layer + store, real backend-backed values only.
      New `GET /api/v1/settings` (read-only, secrets redacted
      server-side) + `stores/settings.store.ts`. Distinct from
      `core/settings-framework.ts`, which owns *per-module client*
      settings — different owner, different lifetime.
- [x] API layer — typed REST client + WebSocket client, per
      `TECH_STACK.md` §3. `services/api/client.ts`,
      `services/api/endpoints.ts`, `services/websocket/`. Three drifts
      from the real server corrected (error envelope, pagination,
      event vocabulary) — see `CHANGELOG.md` 0.29.0.
- [x] Voice Integration — WebSocket-streamed voice state, replacing
      the PySide6 `VoiceOrb`'s direct service calls. `voice.state_changed`
      drives `stores/voice-state.store.ts` through
      `services/realtime-bridge.ts`.
- [x] AI Integration — chat/agent streaming over WebSocket. `agent.step`
      relays step-level progress into `stores/agent-activity.store.ts`.
      Token-level output stays on `/api/v1/agent/stream` (SSE) — M10's
      deliberate split, not an omission.
- [x] Automation Integration — automation run status over WebSocket
      (`automation.step`).
- [x] Offline support — graceful degradation when the Python backend
      is unreachable (never fake data — an explicit "disconnected"
      state). `services/backend-connection.ts` distinguishes
      `unreachable` from `unauthenticated`; `selectIsOffline` does not
      report offline before an attempt has concluded.
- [x] Error handling — a single, consistent error-boundary + toast
      pattern for the whole app. `providers/error-boundary.tsx` (render
      failures) + `services/error-reporting.ts` (action failures), with
      one `describeError` deciding what any failure reads like.

**API Integration Rework** *(added Aug 2026 per the roadmap
architecture review — full design in `MASTER_ROADMAP.md` §8 M11's
API Center Architecture module)*:

> **Not delivered by M8 Phase 2 (v0.29.0), deliberately.** Every item
> below is *backend* provider-lifecycle work — activation, registration,
> validation, failover, health polling — belonging to M11's API Center
> Architecture module, not to the frontend framework phase this block
> happens to sit inside. Phase 2 shipped the rest of §2 in full; these
> ten were left unchecked rather than marked done on the strength of a
> client that can merely *display* provider state. They need their own
> milestone slot.

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
- [x] **Notification Center** *(shipped v0.30.0, M8 Phase 3)* — the
      persistent panel view over `core/notification-framework.ts`'s
      already-real data, as `features/notifications/notification-center.tsx`.
      It was deferred because it had nowhere to live; the Universal
      Workspace Framework's panel system is that container, so it ships
      as a panel rather than as a bespoke layer. The header's
      notification bell gained its handler at the same time and for the
      same reason. `components/layout/notification-layer.tsx` stays a
      reserved `return null` anchor for a future *transient* overlay
      (e.g. an OS-style banner) — deliberately not a second rendering of
      the same list, which could scroll and mark-as-read independently
      of the panel.
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
- [x] **Universal Workspace Framework** *(added Aug 2026, shipped
      v0.30.0 — M8 Phase 3)*: the dockable/resizable panel system the
      rest of this phase's surfaces now compose into.
  - [x] `core/panel-registry.ts` — a `ContributionRegistry` instance,
        the same generic mechanism Navigation, Dashboard Widgets and
        Status Bar items already register through. Not a fourth registry.
  - [x] `stores/workspace-layout.store.ts` — multi-workspace layouts with
        create/rename/delete/duplicate/reset/import/export/switch, panel
        instances, zone sizing, and `localStorage` persistence under the
        established `jarvis.<name>` convention.
  - [x] Four dock zones (`left`, `main`, `right`, `bottom`) plus a
        floating layer; each zone disappears when empty.
  - [x] Panel operations: open, close, resize, collapse, detach, move,
        restore. Splitters are pointer-driven *and* keyboard-operable
        (WAI-ARIA `separator`), since a drag-only layout is unreachable
        without a pointer.
  - [x] **Detached panels float inside the viewport**, not in OS windows
        — a real second window is the separate "Window management (Tauri
        window APIs)" item below, still open. The persisted `frame`
        geometry is already in the shape that work needs.
  - [x] Activity Center (`features/activity/`) — merges background
        tasks, `agent.step` and `automation.step` into one timeline
        without storing a fourth copy of them.
  - [x] Global Search (`features/search/`) — the real
        `POST /api/v1/search`, M10A's 13 registered sources. Distinct
        from the Command Palette, which resolves navigation locally.
  - [x] Performance: route splitting (`routes/lazy-routes.ts`), lazily
        imported panels, `<Suspense>` at both boundaries, `memo` on
        `PanelFrame`, and `components/common/virtual-list.tsx` for the
        two unbounded lists.
  - [x] **Panels are registered only by modules with real content** —
        six today (Dashboard, Voice, Settings, Notifications, Activity,
        Search). The eleven placeholder modules register none; a title
        bar and resize handles around "this module hasn't been built
        yet" would dress an unbuilt module up as a working one.
- [x] **Responsive layout** *(v0.30.0)* — `hooks/use-responsive-layout.ts`
      shares the Sidebar's existing 768px breakpoint rather than
      introducing a second one a few pixels away. Below it the workspace
      drops its rails and `main` fills the width; rail panels stay in the
      workspace and remain reachable from the toolbar. Squeezing three
      rails onto a phone is how a layout ends up technically responsive
      and practically unusable.
- [ ] DPI scaling. *(Deferred Backlog, §6 — needs Tauri window APIs,
      same dependency as Window management below.)*
- [ ] Multi-monitor support. *(Deferred Backlog, §6 — same dependency.)*

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
  - **Deferred** (documented, not silently dropped): Learning/Feedback
        via M16's Reflection Engine (needs M16); Permission Validation's
        final M14-routed form (needs M14); Intent Engine gating graph
        routing (needs M10A/M10B for real signal); the "final" shortcut
        path's real token streaming; PySide6 Agent Trace view / React
        frontend wiring to `/api/v1/agent` (M8's own remaining phases).
        *(Context Engine's knowledge-graph half, originally deferred
        here pending M10A, is now real — see §5B below.)*

**Dependencies note:** M10's formal dependencies are M5A (✅, extended
directly), M8 (🟡 partial — the backend WebSocket transport this pass
needed is real via M9; M8's own remaining frontend phases are
unaffected either way), M10A (✅ **now shipped**, closing Context
Engine's knowledge-graph deferral — see §5B below), M14 (🔴, blocks
Permission Validation's final form).

---

## 5B. M10A — Universal Search & Knowledge Platform (✅ Completed)

Unlike M10, M10A's own declared dependencies (M3 Memory Platform, M5A
Agent Orchestrator exposure) were both already shipped when this pass
began, so this milestone was buildable to near-full completion in one
pass. One key feature is explicitly deferred, not silently dropped:
File Search needs M11B's File Manager surface, which doesn't exist
yet — see `MASTER_ROADMAP.md`'s own Aug 2026 M10A changelog addendum
for the full reasoning and design.

- [x] Knowledge Graph / Relationship Graph — `KnowledgeEntity` /
      `KnowledgeRelationship` / `KnowledgeEntityMemory` in the existing
      `infrastructure/database/models.py`, `Base.metadata.create_all()`
      boot-time creation, no new persistence framework. LLM-driven
      extraction reuses the same JSON-decision pattern the agent nodes
      already established.
- [x] Persistent Memory — reuses `MemoryService.set_pinned` rather than
      a second durability mechanism.
- [x] Reflection Foundation — `KnowledgeService.learn_from_recent_memories()`,
      on-demand (REST `/api/v1/knowledge/learn` or an agent tool),
      never a scheduled background job — no `RuntimeManager` changes,
      no new lifecycle manager, no scheduler.
- [x] Learning, scoped (Acceptance Criterion 3) —
      `KnowledgeService.correct()` supersedes the prior
      `(subject, predicate)` relationship and inserts a
      higher-confidence replacement rather than deleting history. A
      scoped correction primitive, not a general-purpose Learning
      Engine.
- [x] Digital Twin Foundation — the Knowledge Graph schema itself is
      the substrate; no separate twin-building code, matching this
      milestone's own "does not itself claim to build one" scope note.
- [x] Universal Search / Search Provider Registry —
      `services/search_service.py`'s `SearchService` owns
      `register_source`/`unregister_source`/`get_sources`; three
      sources registered (`MemorySearchSource`, `KnowledgeSearchSource`,
      `CommandSearchSource` — agent tools + plugin commands, the latter
      read *live* from `PluginRegistry.list_manifests()` on every
      query, never snapshotted once). `SearchResult` is deliberately
      extensible: `confidence`/`reason` fields exist now, unpopulated,
      for a future AI-reranking milestone to fill in without an API
      change.
- [x] ChromaDB integration — reuses the single existing collection,
      tagged `record_type: "knowledge_entity"` metadata; no second
      vector store, no new adapter.
- [x] Agent / Context Engine integration — new
      `agents/tools/knowledge_tools.py` (`ask_knowledge`/
      `search_knowledge`); `context_engine.py` gained an optional
      `knowledge` parameter, closing M10's own documented
      knowledge-graph deferral.
- [x] REST API — `POST /api/v1/search`, `GET /api/v1/knowledge/entities/{name}`,
      `GET /api/v1/knowledge/ask`, `POST /api/v1/knowledge/correct`,
      `POST /api/v1/knowledge/learn`, `GET/POST /api/v1/knowledge/export|import`.
      Same Bearer auth + envelope convention as
      `routes/plugins.py`/`routes/devtools.py`/`routes/agent.py`.
- [x] WebSocket integration — `core/lifecycle/runtime_ws_hub.py`
      finally realizes the `memory` category (`memory.updated`,
      `memory.recalled`) `docs/ARCHITECTURE.md` §6 documented as a
      target since before the Milestone 9 managers existed, plus a new
      `knowledge` category. `MemoryService` gained an optional
      `event_bus` constructor parameter to publish these — additive,
      every existing call site unaffected.
- [x] Permission Model — no new scopes; reuses M9's existing
      `memory.read`/`memory.write` Plugin SDK scopes.
- [x] 49 new tests across seven files, including one integration test
      per Acceptance Criterion, each against a real temp-file SQLite
      database and the real DI container — AC1 (`ask()` synthesis
      answer), AC2 (export/import round-trip), AC3 (correction
      relayed over the real WebSocket), AC4 (Universal Search spanning
      ≥2 real source types over the real REST API). 888/888 passing,
      zero regressions. mypy diffed against a clean baseline via
      `git stash -u`: 266 → 266, byte-for-byte unchanged after two
      real fixes. Ruff findings proportional to the pre-existing
      accepted baseline — zero new categories left unresolved.
  - **Deferred** (documented, not silently dropped): File Search
        (needs M11B's File Manager, not started); AI reranking
        (`SearchResult.confidence`/`.reason` exist but are unpopulated);
        scheduled Reflection (on-demand only; M7 Scheduler integration
        is future work); a full, general-purpose Learning Engine
        (`correct()` is a scoped primitive, not that engine).

**Dependencies note:** M10A's formal dependencies, M3 (Memory
Platform) and M5A (agent tool exposure), were both already shipped —
this milestone was never blocked, unlike M10.

---

## 5C. M10B — Intelligence Layer (✅ Completed)

Extends M10A's architecture directly rather than introducing a
parallel system: `IntelligenceService`/`IntelligenceRepository` mirror
`KnowledgeService`/`KnowledgeRepository`'s exact shape, and Goal
Manager registers into `SearchService`'s existing provider registry as
a fourth source with zero changes to `SearchService` itself. One key
feature is explicitly deferred, not silently dropped: automatic
scheduled Daily Briefing delivery needs M7's Scheduler (Phase 6),
which does not exist yet — see `MASTER_ROADMAP.md`'s own Aug 2026 M10B
changelog addendum for the full reasoning and design.

- [x] Goal Manager — `Goal` (self-referential `parent_goal_id`
      hierarchy) in the existing `infrastructure/database/models.py`;
      `IntelligenceRepository` mirrors `KnowledgeRepository`'s
      method-by-method pattern. Progress auto-completes a goal at
      ≥100%, publishing `goal.updated`.
- [x] Routine Learning — deterministic, direct-observation
      reinforcement (`Routine` rows, hour-of-day/day-of-week
      wildcards, confidence scoring), not LLM-driven pattern mining. A
      routine only surfaces in suggestions once past a minimum
      observation count.
- [x] Preference Learning — a structured `Preference` key-value store,
      deliberately separate from M3's freeform preference memories.
- [x] Context Awareness — `get_context_signals()`: hour of day, day of
      week, recent memory snippets (via `MemoryService.browse()`,
      tolerant of failure), active conversation id. No location signal
      — no location provider exists anywhere in the codebase, documented
      rather than faked.
- [x] Predictive Suggestions — combines due-soon goals, reinforced
      routines, and a preference-boost pass into one ranked list.
      Plain keyword-boost logic, not an AI reranker.
- [x] Daily Briefing — on-demand generation (REST + agent tool),
      publishes `briefing.generated`. Automatic scheduled delivery via
      M7 remains deferred (see below).
- [x] Agent integration — new `agents/tools/intelligence_tools.py`
      (`create_goal`/`list_goals`/`update_goal_progress`/
      `get_suggestions`/`get_daily_briefing`), wired into
      `build_tool_registry()` as a new optional `intelligence`
      parameter.
- [x] REST API — `POST/GET /api/v1/goals`, `GET /api/v1/goals/{id}`,
      `PATCH /api/v1/goals/{id}/progress`,
      `POST /api/v1/goals/{id}/complete`, `DELETE /api/v1/goals/{id}`,
      `GET /api/v1/intelligence/context|suggestions|briefing`,
      `POST/GET /api/v1/intelligence/preferences`. Same Bearer auth +
      envelope convention as `routes/knowledge.py`.
- [x] WebSocket integration — `core/lifecycle/runtime_ws_hub.py`
      gained `goal.updated`/`briefing.generated`, verified over the
      real relay in `tests/integration/test_intelligence_platform_e2e.py`.
- [x] Universal Search integration — `GoalSearchSource` registered as
      a fourth provider (`memory`, `knowledge`, `goals`, `commands`),
      with no `SearchService` changes required.
- [x] Permission Model — no new scopes; reuses M10A's existing
      `memory.read`/`memory.write` scopes.
- [x] 48 new tests across five new files plus one new test in
      `test_search_sources.py`, including one integration test per
      Acceptance Criterion, each against a real temp-file SQLite
      database and the real DI container — AC1 (goal persistence +
      progress tracking over REST and the real WebSocket), AC2 (a
      learned routine measurably changing a future suggestion), AC3
      (Daily Briefing generation relayed over the real WebSocket).
      936/936 passing (up from 888), zero regressions — one
      pre-existing M10A test updated for the now-correct 4-source
      Universal Search set. mypy diffed against a clean baseline via
      `git stash -u`: 266 → 266, byte-for-byte unchanged after removing
      14 unnecessary `type: ignore` comments. Ruff findings
      proportional to the pre-existing accepted baseline — zero new
      categories left unresolved.
  - **Deferred** (documented, not silently dropped): automatic
        scheduled Daily Briefing delivery (needs M7's Scheduler Phase
        6, not started); location-aware Context Signals (no location
        provider exists); AI reranking of Predictive Suggestions
        (plain keyword-boost logic only).

**Dependencies note:** M10B's formal dependencies are M3 (Memory
Platform), M7 (Scheduler, for automatic Daily Briefing delivery — not
started, hence that one deferral), and M10A (knowledge/context
substrate, already shipped). Only the M7 dependency blocked anything,
and only the automatic-scheduling half of one feature.

---

## 5D. M10.5 — MCP & Integration Platform (✅ Completed — all five task groups)

The protocol-and-registry layer beneath M11. **Closed Aug 2026 at
`0.20.0`**, across Task Groups A (Core Runtime), B (Transport Layer),
C (Provider Framework), D (Authentication Foundation) and E (SDK,
Developer Experience & Milestone Closure). No *real* provider, no OAuth
flow and no vendor integration ship here — that was always M11's scope.
Two acceptance criteria close at 🟡 and are named with where they land
in `MASTER_ROADMAP.md` §8; see that document's Aug 2026 M10.5 Task
Group A–E changelog addenda for the full design.

- [x] MCP Capability Registry — `core/mcp/capabilities.py`;
      register/unregister/discovery/metadata/version/permissions,
      mirroring `SearchService`'s M10A provider-registry shape.
- [x] Transport abstraction — `IMCPTransport` port +
      `TransportFactoryRegistry`. `stdio`/`websocket`/`http`/`ipc` are
      named in `TRANSPORT_TYPES` but **not implemented**; one reference
      `InProcessTransport` ships so the runtime paths are exercised
      against something real.
- [x] MCP Client Runtime — connection management, handshake, capability
      discovery, health, bounded-retry reconnect. Lifecycle only.
- [x] MCP Server Runtime — capability exposure, permission enforcement,
      extensible protocol dispatch, `IService`-shaped lifecycle.
- [x] Capability negotiation — version compatibility, capability
      compatibility, graceful fallback to an older shared revision.
      Pure functions, no I/O.
- [x] Permission model — **reuses M9's `PermissionModel`**, namespaced
      `mcp:<client_id>`. No second permission system, no new scope
      vocabulary.
- [x] Dependency Injection — `mcp_server_runtime`,
      `mcp_client_runtime`, `mcp_transport_registry` singletons.
- [x] Runtime events — `mcp.connection_changed`,
      `mcp.capabilities_changed`, `mcp.permission_denied` over the
      existing `EventBus` + Runtime WebSocket relay; health via
      `HealthMonitor.register_collector`.
- [x] REST API — `GET /api/v1/mcp/status|capabilities|connections|
      transports`. Read-only by design; provider management is Task
      Group B.
- [x] 89 new tests across seven files — unit, lifecycle, DI,
      permission, negotiation, registry, route, and a real-WebSocket
      integration suite.
  - *(Network transports were deferred here and are now shipped --
        see Task Group B immediately below.)*

### Task Group B — Transport Layer & Runtime Connectivity (✅ shipped)

- [x] Stdio transport — real subprocess, newline-delimited JSON-RPC
      over stdin/stdout, graceful shutdown escalating to kill.
- [x] WebSocket transport — persistent outbound JSON-RPC. Distinct
      from `RuntimeWebSocketHub`, which serves JARVIS's own relay
      inbound.
- [x] HTTP transport — stateless POST, with a `connect` that
      distinguishes an unreachable host from a peer-level error.
- [x] IPC transport — Windows named pipe / Unix domain socket, not
      loopback TCP (which is not local IPC and carries no OS-level
      access control).
- [x] `JsonRpcStreamChannel` — framing + correlation shared by stdio
      and ipc; websocket deliberately does not reuse it.
- [x] Transport factory + registry discovery/query — all five
      transports registered at the DI composition root.
- [x] `MCPHeartbeatMonitor` — one loop over every connected peer,
      riding the existing `request` primitive rather than a new port
      method; `ping` registered through Task Group A's own
      `register_method` seam.
- [x] Four new relay events (`handshake_completed`,
      `negotiation_completed`, `transport_failed`, `heartbeat`) plus a
      `reconnecting` connection state.
- [x] REST — `GET /api/v1/mcp/transports`, `/transports/{id}`,
      `/heartbeat`. Still read-only.
- [x] 100 new tests across eight files, against real peers throughout
      (real subprocess, real websockets server, real HTTP server, real
      named pipe / Unix socket).
  - *(Provider management was deferred here and its framework is now
        shipped -- see Task Group C immediately below.)*

### Task Group C — Provider Framework (✅ shipped)

Infrastructure only. **No real providers**, no OAuth, no vendor code.

- [x] `IMCPProvider` — transport-independent provider port; six
      lifecycle methods mirroring `IService`, plus `suspend`/`resume`.
- [x] `ProviderMetadata` / `ProviderConfig` — inert validated models
      separating what a provider *is* from how this install *runs* it;
      config carries enabled/transport/options/reconnect/retry/heartbeat.
- [x] `MCPProviderRegistry` — register/unregister/lookup/enumerate/
      metadata/validation, plus `discover()` filtered by transport,
      capability, state, protocol, permission and enabled-ness.
      Registration is inert, so discovery has no side effects.
- [x] `MCPProviderManager` — install/initialize/connect/disconnect/
      suspend/resume/shutdown/remove, fault-isolated in batch.
- [x] `TransportBackedProvider` — the generic implementation covering
      every config-driven integration.
- [x] `mcp.provider_changed` relay event with an `action` field for all
      eight transitions plus the resting `state`.
- [x] REST — `GET /api/v1/mcp/providers`, `/providers/{id}`,
      `/providers/{id}/health`, `/providers/{id}/metadata`. Read-only.
- [x] DI singletons; RuntimeManager shutdown ordering (providers before
      the client runtime); health via `HealthMonitor.register_collector`.
- [x] 84 new tests across five files, including a full lifecycle
      against a real stdio peer subprocess with events verified over
      the real WebSocket relay.
  - *(Authentication was deferred here and its framework is now
        shipped -- see Task Group D immediately below.)*

### Task Group D — Authentication & Provider Integration Foundation (✅ shipped)

Infrastructure only. **No real providers**, no vendor code, **no OAuth
flow** (it needs an authorization server and a callback endpoint).

- [x] `AuthMethod` vocabulary — api_key / bearer_token /
      personal_access_token / oauth2 / client_credentials / none.
- [x] `Credential` — tokens, expiry, scopes, provider id, account id,
      encryption metadata. Frozen; redacts its own `repr`; separate
      storage and public serializers.
- [x] `CredentialStore` — encrypted at rest via the existing Fernet
      helpers and `config/` convention. **Refuses plaintext
      persistence**; rotation-ready via per-record `key_id`.
- [x] `AuthStrategyRegistry` + `StaticTokenStrategy`/`NoAuthStrategy`.
- [x] `ProviderSession` — provider-side auth state. Not M9's
      `SessionManager`, which owns user sessions.
- [x] `MCPAuthManager` — authenticate/refresh/revoke/validate/expire/
      reconnect, the permission bridge, and the health payload.
- [x] Permission bridge — two independent gates (JARVIS-side scope via
      `PermissionModel`; provider-side scope carried by the token),
      naming which one refused. No new scope vocabulary.
- [x] `mcp.auth_changed` relay event with an `action` field for all
      eight transitions; carries no token.
- [x] Health — expiry sweep rides `HealthMonitor.register_collector`
      rather than a second timer.
- [x] REST — `GET /api/v1/mcp/auth`, `/auth/methods`,
      `/auth/{provider}`, `/auth/{provider}/status`. Read-only.
- [x] DI singletons; `app.py` health wiring.
- [x] 101 new tests across five files, including on-disk encryption
      verification and an end-to-end suite with events over the real
      WebSocket relay.
  - **Deferred to M11 / later**: the OAuth2 and client-credentials
        flows (in the vocabulary, reported unsupported rather than
        half-implemented); login and OAuth callback endpoints; write
        endpoints; GitHub/Gmail/Slack/Calendar/Drive and every other
        vendor integration; MCP tools surfaced through the agent Tool
        Registry and Agent Trace; a server-side network listener.

### Task Group E — SDK, Developer Experience & Milestone Closure (✅ shipped)

The author-facing surface, and the milestone's close. Nothing here is
vendor-specific and nothing connects to an external service.

- [x] **MCP SDK** — `core/mcp/sdk/builders.py`. `CapabilityBuilder`,
      `ProviderBuilder`, `TransportBuilder`, `AuthBuilder`,
      `ConfigBuilder`, each producing the **existing** runtime model.
      No new runtime type; nothing in `core/mcp/` imports the SDK, so
      the dependency runs one way.
- [x] Registry helpers — `register_provider` (validates metadata and
      config *together* before anything is registered),
      `expose_capabilities` (all-or-nothing), `capability_names`.
- [x] **Validation framework** — `core/mcp/sdk/validation.py`.
      `ValidationReport`/`ValidationIssue` with stable codes and
      ERROR/WARNING severity; validators for capability, provider
      metadata, provider config, transport config, auth, and
      **registry consistency** — the cross-object check no single model
      can make about itself.
- [x] **Developer CLI** — `jarvis mcp status|validate|list|inspect|
      capabilities|transports|providers|auth|connections`, with
      `--json` and `--config`. Read-only, no vendor commands, dispatched
      from `main.py` before the run-mode parser so it never launches the
      app. `run_command` returns `(output, exit_code)`.
- [x] **Example implementations** — `core/mcp/sdk/examples.py`. A
      capability, provider, config, transport and auth strategy, all
      self-contained and all imported by tests so they cannot rot.
      Reuses the existing `in_process` transport identifier rather than
      widening the closed `TRANSPORT_TYPES` set.
- [x] **Diagnostics** — `core/mcp/diagnostics.py`. One read-only
      aggregator over every MCP subsystem; collects, never computes;
      holds no state. Reuses `RuntimeManager`'s existing hooks (it needs
      none of its own) and `HealthMonitor`'s single `mcp` collector.
- [x] REST — `GET /api/v1/mcp/diagnostics`, `GET /api/v1/mcp/validate`.
      Read-only; `validate` always returns `200` and callers branch on
      `data.ok`.
- [x] DI — one `mcp_diagnostics` singleton, resolved by both the CLI and
      the REST layer, so the two can never report different facts.
- [x] **Final Runtime Review** — audited for duplicate registries,
      lifecycle managers, permission systems, health systems and
      authentication systems; none found. Two real defects fixed (a
      stale `TRANSPORT_TYPES` comment, a dead import in
      `auth/manager.py`); one pre-existing layering exception recorded
      and left alone. Full findings in `MASTER_ROADMAP.md`'s Task Group
      E addendum.
- [x] 137 new tests across six files; suite 1296 → 1433, all passing.
  - **Deferred to M11**: Agent Trace integration for MCP tool calls
        (needs MCP capabilities in the Tool Registry, which needs a real
        provider); a server-side network listener (belongs with M11's
        API Gateway); the OAuth2 and client-credentials flows; every
        vendor integration.

**Dependencies note:** M10.5's formal dependencies — M5A (agent tool
exposure), M9 (Permission Model, Service Manager lifecycle), M10
(Permission Validation), M10A (the provider-registry pattern) — were
all already shipped, so this task group was never blocked.

---

## 5E. Backlog Completion & Stabilization Pass (✅ Completed — `0.21.0`, pre-M11)

Not a milestone. A sweep of documented backlog belonging to milestones
already marked complete, plus the UI/runtime audit that implies. Full
reasoning in `MASTER_ROADMAP.md`'s own Aug 2026 addendum; §15 there
carries the per-item resolutions.

**Closed §15 items:**

- [x] Five WebSocket categories published but never relayed —
      `voice.state_changed`, `automation.step`, `progress.update_phase`,
      `notification.plugin`, `plugin.custom`. `UNPUBLISHED_EVENT_TYPES`
      names the four still absent because nothing publishes them, and a
      test fails if that changes silently.
- [x] `HealthMonitor` disk collector — flat `disk_percent` /
      `disk_free_bytes` / `disk_total_bytes`, so
      `ResourceManager.register_budget()` can target them. **GPU stays
      open** (needs a vendor library this project has no dependency on).
- [x] `/api/v1/health` + `/api/v1/ready` — added alongside the original
      `/api/health` + `/api/ready`, not instead of them.
- [x] `/api/v1/sessions` `{data, meta}` envelope — **the one intentional
      breaking change**; callers read
      `response.json()["data"]["session_id"]`.

**Found and fixed by the UI audit** (previously untracked):

- [x] Plugin Manager rendered two invented plugins and an invented
      marketplace from an M5-era mock, next to the real Plugin Platform
      M9 Task Group C shipped. Now reads the live `PluginRegistry` via
      `PluginRegistryProvider`; the mock was deleted.
- [x] Module Manager fabricated "update available" 30% of the time via
      `random.random()`. Now reports "No update channel", which is the
      one honest answer available.

**Deliberately out of scope** — recorded so a later pass does not
re-litigate it: M8's Deferred Backlog (§6 below) is the M8 *milestone*,
not stabilization, and M8 is an active migration off PySide6 — building
those surfaces in the outgoing stack means writing them twice. M7's
Scheduler, M10A's File Search, M10B's scheduled briefing, M10's
Learning/Feedback and M10.5's two 🟡 acceptance criteria are each
blocked on a milestone that has not started, not on effort.

---

## 5F. Final Backlog Completion Pass (✅ Completed — `0.22.0`, pre-M11)

The second and last backlog pass. `0.21.0` closed the §15 items the
roadmap had written down; this one closed what it had not. Full
reasoning in `MASTER_ROADMAP.md`'s own Aug 2026 addendum.

- [x] **Startup greeting no longer invents the user's day.** Work
      context now comes from M10B's real Goal Manager; calendar,
      weather, music and smart-home stay empty until M11/M12 supply a
      source. `features/greeting/mock_context.py` deleted.
- [x] **Browser Automation + Desktop Automation Settings pages** — were
      placeholders reading "Coming in Milestone 4" while M4's settings
      were real and consumed by shipped services.
- [x] **Plugins Settings page** — was a placeholder reading "Coming in
      Milestone 5 — Agents"; the Plugin Platform shipped in M9.
- [x] **Home dashboard service cards** no longer show a "connected"
      indicator over illustrative data — a `preview` state forces the
      offline indicator and a visible note.
- [x] Remaining Settings placeholders name their real owners (M12, M14)
      instead of the retired "Milestone 6 — Ecosystem" grouping.

**Sweep result:** zero `TODO`/`FIXME`/`HACK`/`XXX` in `src/`, zero dead
routes (all nine routers mounted), zero unwired DI services.

**Still deferred, one rule behind all of it** — the Automations
workspace and every item in §6 below are *new PySide6 screens*, and M8
is an active migration to React + Tauri. Building them now means
building them twice. Everything else (M7 Scheduler, M10A File Search,
M10B scheduled briefing, M10 Learning/Feedback, M10.5's two 🟡 criteria)
is blocked on a milestone that has not started.

**All backlog for completed milestones is finished.**

---

## 5G. M11 — Intelligent Workspace & Productivity (🟡 Active — Task Groups A–F shipped; F's UI half deferred to M8)

Six task groups, A–F. The milestone was restructured before
implementation so that a shared Workspace substrate comes first and the
original integration brief (now Task Group E) builds on it. Full
reasoning in `MASTER_ROADMAP.md`'s own Aug 2026 M11 Task Group A
addendum.

### Task Group A — Workspace Foundation (✅ shipped, `0.23.0`)

- [x] Workspace domain — `Workspace`/`Project`/`Note` ORM models;
      `WorkspaceSettings` (JSON column) + `WorkspaceMetadata` (derived,
      never stored).
- [x] `WorkspaceRepository` / `ProjectRepository` / `NoteRepository`,
      following `IntelligenceRepository`'s shape.
- [x] `WorkspaceService` — lifecycle, project CRUD, note CRUD,
      settings, metadata, search hooks, event publishing.
- [x] `WorkspaceManager` — composes Knowledge/Search/Memory; collects,
      never computes; collaborators optional.
- [x] DI — `workspace_service` + `workspace_manager` singletons.
- [x] REST — `/api/v1/workspaces`, `/projects`, `/notes` (CRUD) plus
      `/metadata`, `/overview`, `/context`.
- [x] WebSocket — `workspace.updated`, `project.updated`,
      `note.updated` on the existing relay.
- [x] Search — three sources through M10A's provider registry, no
      `SearchService` change.
- [x] 56 tests across unit / repository / REST / integration.

### Task Group B — Productivity Core (✅ shipped, `0.24.0`)

- [x] Task domain — model, repository, `TaskService`, `TaskManager`;
      status, priority, due dates, normalized tags, agenda.
- [x] Local Calendar engine — `Calendar` + `CalendarEvent`,
      `CalendarRepository`, `CalendarService`, `CalendarManager`;
      categories, metadata, per-workspace default calendar.
- [x] `RecurrenceRule` — four frequencies, interval, count/until, with
      bounded pure expansion and month-end clamping. **Rules stored,
      occurrences computed on demand.**
- [x] Reminder domain — model, repository, `ReminderService`,
      `ReminderManager`; scheduling metadata and status transitions.
      **No execution** — see below.
- [x] Four relay events; three search sources through M10A's registry;
      DI singletons for all six components.
- [x] REST — `/api/v1/tasks`, `/api/v1/calendar/*`,
      `/api/v1/reminders`, plus `/agenda`, `/occurrences`, `/due`,
      `/context`.
- [x] 97 tests across domain / service / manager / REST / integration.

**Scope boundary:** nothing fires. `due_before()` and `/reminders/due`
report which reminders have come due and change nothing — no loop, no
timer, no queue, no `reminder.fired` event. Scheduler execution is M7
Phase 6.

**External calendar providers are not here.** Google, Outlook and
synchronization are Task Group E; this is the local engine they will
map onto.

### Task Group C — File Platform (✅ shipped, `0.25.0`)

- [x] File domain — `domain/files/models.py`: `safe_join`,
      `validate_name`, `extract_text`, MIME/extension helpers, and the
      closed vocabularies. Pure: no database, no service, no container.
- [x] Six tables — `Folder` (self-referential, denormalized
      `relative_path` cache), `File`, `FileTag` (a real join table),
      `FileMetadata`, `IndexRecord`, `WorkspaceAttachment` (five
      nullable foreign keys, one per target kind).
- [x] `FolderRepository` / `FileRepository` / `MetadataRepository` /
      `AttachmentRepository`.
- [x] `FolderService` — create, rename, move, delete; cycle prevention
      and subtree path rewriting; a non-empty delete needs an explicit
      `recursive`.
- [x] `FileService` — CRUD, move, rename, tags, extensible metadata,
      indexing, per-workspace stats, search.
- [x] `AttachmentService` — attach/detach across five workspace
      entities, with target existence and workspace ownership validated
      before the insert.
- [x] `FolderManager` / `FileManager` / `AttachmentManager` — collect,
      never compute; collaborators optional.
- [x] Three relay events; three search sources through M10A's registry;
      DI singletons for all six components.
- [x] REST — `/api/v1/files`, `/api/v1/folders`, `/api/v1/attachments`,
      plus `/tree`, `/contents`, `/content`, `/context`, `/stats`,
      `/index`, `/for-target`, `/for-file`.
- [x] 116 tests across domain / service / manager / REST / integration.

**Scope boundary — the storage root is a hard boundary.** Every path
resolves through one pure `safe_join`, which refuses rather than clamps
and runs at construction *and* on every read. The REST surface accepts
no path fragment at all.

**Indexing reads seven extensions as plain text**, bounded at 1 MiB per
file. No OCR, no PDF parsing, no embeddings, no summarisation — those
need Vision, Document Intelligence and the vector store.

**Cloud storage is not here.** Drive, Dropbox, OneDrive and sync are
Task Group E; this is the local subsystem they will map onto.

### Task Group D — AI Workspace (✅ shipped, `0.26.0`)

- [x] AI Workspace domain — `domain/ai_workspace/models.py`:
      `ContextItem`/`ContextSection`/`WorkspaceContext`, the
      character-budget `pack()`, `clip()`, `order_sections()` and
      `build_assist_prompt()`, plus the four closed vocabularies. Pure:
      no database, no service, no container, no provider.
- [x] One table — `WorkspaceKnowledgeLink`: workspace + entity, four
      nullable narrow foreign keys (project/note/task/file), `source`
      (`extracted` | `manual`) and `confidence`. The association table
      Task Group A's `WorkspaceManager.context` explicitly declined to
      invent until this task group had said what it needed.
- [x] `WorkspaceLinkRepository` — exact-match `find` (nulls compared,
      so "this note is about Ada" and "this workspace is about Ada" stay
      distinct rows), `delete_extracted_for_target`, and an aggregate
      `entities_for_workspace` join.
- [x] `WorkspaceKnowledgeService` — link/unlink with target existence
      *and* workspace-ownership validation, idempotent linking with
      extracted→manual promotion, and ingestion over a workspace's own
      text, its notes and its files' index records.
- [x] `WorkspaceContextManager` — the budgeted context assembled across
      every M11 subsystem plus Knowledge and Memory, read through the
      *managers* that own each answer.
- [x] `WorkspaceRetriever` — workspace-scoped retrieval over the shared
      `SearchService`, with the calendar join an event's missing
      `workspace_id` requires.
- [x] `WorkspaceAssistantService` — grounded `summarize`/`ask`/
      `next_actions` with citations, degrading to the assembled context
      when no provider answers.
- [x] Five agent tools on the **existing** registry
      (`agents/tools/workspace_tools.py`), reaching the agent through
      `build_tool_registry`'s new optional argument.
- [x] Two relay events (`workspace.knowledge_linked`,
      `workspace.assisted`); `AIWorkspaceSettings`; DI singletons for
      all four components; `WorkspaceManager` gained an optional link
      store and an additive `linked_knowledge` key.
- [x] REST — `/api/v1/workspace-ai/{id}/context`, `/retrieve`,
      `/assist`, `/ingest`, `/entities`, plus `/api/v1/knowledge-links`.
- [x] 199 tests across domain / service / manager / tools / REST /
      integration.

**Scope boundary — no second anything.** Retrieval narrows M10A's
`SearchService`; extraction is `KnowledgeService.learn_from_text`;
the agent is M10's `AgentOrchestrator`, reached as tools. **No search
source was registered**: knowledge entities are already searchable
through `KnowledgeSearchSource`, and a second source over the same rows
would return one entity twice with no way to tell the hits apart.

**Nothing is scheduled and nothing is stored about an assist call.**
Ingestion runs on demand (M7 Phase 6 owns scheduling), and an assist
returns its answer and publishes an event — `ConversationService` owns
chat history, and duplicating it here would be a second transcript.

**No embeddings over workspace content.** The context is assembled from
stored fields and Task Group C's plain-text index; semantic indexing
needs the vector store work Task Group C deferred.

**One additive change to a shipped milestone:**
`ExtractionResult.entity_ids` (M10A) — the counts alone cannot say
*which* entities a text is about, and a text mentioning an entity the
graph already knows creates nothing. Defaulted and last, so every
existing construction site and assertion is unchanged.

### Task Group E — Integration Platform (🟡 platform + Phase 1 shipped, `0.27.0`)

- [x] **OAuth2, closing M10.5's explicit deferral** —
      `core/mcp/auth/oauth2.py`: the authorization-code grant with
      mandatory PKCE (S256), the client-credentials grant, an
      `OAuthFlowStore` whose `state` is single-use and expiring, and
      `BoundOAuth2Strategy` for per-provider refresh and remote revoke.
      Registered into the **existing** `AuthStrategyRegistry` — the one
      call Task Group D's docstring predicted, and nothing else changed.
- [x] **API Gateway** — `core/integrations/gateway.py`: one `httpx`
      pool, retry for idempotent methods **only**, `Retry-After`
      honoured and bounded, a short account-keyed response cache
      invalidated by any mutation, and an audit payload carrying no
      headers and no bodies.
- [x] **Connectors as data** — `core/integrations/models.py`:
      `IntegrationSpec`/`OperationSpec`/`AuthSpec`, validated at
      registration. Path rendering is the security boundary: a caller
      supplies parameters, never a path, and an undeclared parameter is
      refused rather than forwarded.
- [x] **`RestIntegrationProvider`** — an `IMCPProvider` for vendor REST
      APIs, registered in the *same* `MCPProviderRegistry`, driven by
      the *same* `MCPProviderManager`, publishing the *same* events,
      with each operation registered as an `MCPCapability`. Both
      permission gates run per call through
      `MCPAuthManager.authorize_capability`.
- [x] **Google Workspace, Phase 1** — 11 integrations, 65 operations:
      Gmail, Calendar, Meet, Drive, Docs, Sheets, Slides, Contacts,
      Tasks, Keep, Photos.
- [x] **`IntegrationService`**, one relay event
      (`integration.call_completed`), per-integration search sources on
      M10A's existing registry, four agent tools on the existing tool
      registry, `IntegrationSettings`, DI, and
      `/api/v1/integrations/*` including the OAuth callback.
- [x] 200 tests across spec / gateway / OAuth / provider / catalogue /
      REST / end-to-end.

**One route in this application is session-free, and only one.** The
OAuth callback is reached by a browser redirect, which carries no
`Authorization` header and cannot be made to. `state` — generated with
`secrets`, single-use, expiring, held server-side beside the PKCE
verifier — is what proves the response belongs to a flow this process
started (RFC 6749 §10.12).

**Scope boundary — Phases 2–6 are catalogue entries, not architecture.**
Microsoft 365, GitHub/GitLab, Slack/Discord/Teams, Notion/Jira/Trello/
ClickUp/Linear/Asana and Dropbox/Box run on this engine as spec data.
They are deliberately **not** written from memory: an endpoint path or a
scope name that is subtly wrong ships an integration that fails at the
first real call, and a wrong catalogue entry is worse than an absent one
because it claims to work. Each needs its vendor's published API
reference open beside it.

**Two-way sync is not implemented** for Google Tasks or Keep. Pull and
push operations ship; a *sync* needs a conflict-resolution policy and
something to run it on a cadence, and M7's Scheduler (Phase 6) does not
exist. One-directional import that works beats a bidirectional mirror
that silently loses an edit.

**Also not built:** resumable/multipart upload (Drive's simple upload
ships, correct to 5 MB), webhooks and inbound delivery, a durable
outbound queue, and Oracle Cloud sync.

### Task Group F — Platform Integration & Closure (🟡 backend shipped, `0.28.0`)

An audit of every cross-cutting surface Task Groups A–E built, plus the
fixes it turned up. Four defects were real; the rest was already
consistent, and the record below says which is which.

- [x] **Security — sessions could be read and closed by anyone who
      learned an id.** A session id *is* the Bearer token for this API,
      and `GET`/`DELETE /sessions/{id}` took it in the URL path and
      required nothing else. Both now require the token *and* check it
      names the same session; cross-session access is `404`, not `403`,
      so a valid token cannot probe for others' sessions.
- [x] **Pagination — collections truncated silently.** Repositories
      already capped at 200/500, nothing exposed the cap, and `meta`
      reported only `count`. All nine M11 collections now take
      `limit`/`offset` and report `{count, limit, offset, has_more}`
      through one shared helper, `infrastructure/api/pagination.py`.
- [x] **DI — `memory_recall_hook` was bound twice**, an earlier no-op
      registration silently replaced by the real one. Behaviour was
      right; the dead binding misled every reader. Removed.
- [x] **Health — M11's subsystems reported nothing.** One
      `workspace_platform` collector on the existing extension point now
      carries the file storage root, the AI-workspace switches, the
      egress counters and the live search sources. Integrations are
      deliberately absent: they are MCP providers and already ride the
      `mcp` collector.
- [x] Audit invariants pinned as tests
      (`tests/unit/test_platform_integration.py`), so none of this can
      regress quietly.

**Verified and already correct** — recorded so a later audit knows they
were checked rather than skipped: 170 routes with exactly six
deliberate session-free exceptions; the `{data, meta}` envelope on every
resource route (probes and SSE excepted); `404` for unknown ids and
`400` for invalid input with zero deviations across 14 probes; 66 event
classes with 61 relayed and 5 documented as absent, no duplicate relay
names; 13 search sources each registered exactly once; 88 DI providers
with no duplicate targets; 37 settings sections all under `JARVIS_`,
all constructible from defaults; and cross-workspace writes refused
with a reason.

**Not built: the React/Tauri workspace UI.** The original brief paired
"UI Integration" with "Platform Closure". The frontend half is M8's,
which is deferred, so this task group delivered the backend integration
only and **M11 is not closed**.

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

### M8 Phase 2 — Universal Application Framework & Logic
**Shipped in v0.29.0** — Business Logic → State Machine → Service Layer
→ Hooks → Store pattern, Authentication, Permissions, Storage, Settings
API layer, Voice/AI/Automation Integration, Offline support and Error
handling are all complete; see §2 above for the itemized list and
`CHANGELOG.md` 0.29.0 for what the phase found and fixed.
- [ ] **API Integration Rework block only** — the ten provider-lifecycle
      items (Real API Activation, Provider Registry, Runtime Provider
      Registration, API Validation, Connection Testing, Health Checks,
      Automatic Provider Loading, Provider Failover, No Fake Providers,
      Runtime Provider Switching). Backend work belonging to M11's API
      Center Architecture module; see the note in §2.

### M8 Phase 5 — AI Workspace & Module Integration ✅ *(v0.31.0)*
- [x] Every backend module with real content reaches the user, through
      the **existing** `panelRegistry` and `dashboardWidgetRegistry` —
      no duplicate registries.
- [x] **AI Dashboard** — 11 widgets, every one on real backend data.
- [x] **Developer Dashboard** (Developer Mode only) — providers &
      routing, outbound API counters, API inspector, performance
      metrics, agent trace, the 61-event relay vocabulary, runtime state.
- [x] **Administrator Dashboard** (Administrator only) — AI health, API
      usage, provider health, voice providers, secrets status, audit
      log; plus a panel naming the seven capabilities that have no
      backend.
- [x] **Personal Mode** (`ARCHITECTURE.md` §22.12) — `core/user-mode.ts`
      is the single audience gate; restricted panels are filtered from
      the panel menu *and* refused by their own components.
- [x] Global Search continues to use `POST /api/v1/search`. No
      client-side search.
- [x] Every panel docks, undocks, floats, collapses, restores, persists,
      notifies, searches and themes — inherited from Phase 3's framework
      with no change needed.

**Not built — no API exists in the frozen backend.** Users & roles
(§22.11), daily/monthly budgets (§22.3), provider priority (§22.2),
calibration status (§22.8), analytics and synchronization (§22.5);
Recent Conversations (no conversation-history route); Vision status (no
vision service reports to the health monitor). *Pinned Projects* shipped
as **Pinned Notes** — `Project` has no `pinned` column, `Note` does.

### M8 Phase 6 — UI Polish, Performance & Production UX ✅ *(v0.31.0)*
- [x] Skeleton loaders shaped like the content they replace; loading,
      empty, error and offline states per widget via `ResourceView`.
- [x] **Connection recovery** — re-runs ping → session → socket, because
      the socket's own retry reuses a token a restarted backend refuses.
- [x] Responsive layout, keyboard navigation, ARIA labels, focus
      management, dark/light polish.
- [x] Lazy loading, code splitting, memoization, virtual lists,
      Suspense, startup optimization.

**Still open:** image optimization (no images to optimise), window state
persistence beyond `@tauri-apps/plugin-window-state`, DPI scaling and
multi-monitor — all blocked on the same Tauri window APIs as Phase 3's
Window Management item.

### M8 Phase 5A — Settings & User Profiles (in full, still deferred)
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

### M8 Phase 6 — Premium UI Polish (remainder)
*(The production-UX half of Phase 6 — skeletons, state handling,
connection recovery, performance, accessibility — shipped in v0.31.0;
see §2 above. What remains is the visual-design pass.)*
- [ ] Spacing, Typography, Cards, Animations, Icons audited against
      the design-token scale; production-quality pass across every
      view built in Phases 1–5.
- [ ] Conversation Timeline. *(Blocked: no conversation-history API
      exists in the frozen backend.)*
- [ ] The broader motion pass (hover, Sidebar, Dock, Cards,
      Notifications) — beyond what Task Group H–L already shipped.

### M8 Phase 7 — Production Readiness ✅ *(v0.32.0)*
- [x] Every screen reviewed for loading / skeleton / empty / offline /
      error / reconnect / auth / permission states, theme, spacing,
      typography, icons, transitions, panel and workspace behaviour.
- [x] **Audited against a live backend**, not by reading code — real
      `create_app` + real DI container + real `HealthMonitor` poll,
      driven from the client, with the backend killed mid-session and
      restarted.
- [x] Workspace operations validated (create/rename/delete/duplicate/
      reset/import/export/switch/restore/dock/float/collapse/resize/
      persist) — 71 tests across four suites.
- [x] Personal / Developer / Administrator modes validated, with a
      **source-level guard** (`restricted-surface.test.ts`) that fails if
      any module reads §22.12-restricted data without gating.
      Mutation-tested.
- [x] Dead code removed; each removal verified as having zero importers
      first.

**Four defects found and fixed** — version drift three releases deep
(`/api/v1/health` reported `0.28.0`), a dead-end journey (five widgets
told users to bind a workspace with no control to do it), a status
selector reporting a fault that did not exist, and inconsistent offline
messaging. See `CHANGELOG.md` 0.32.0.

**Not done, and open:** cross-browser testing (Chromium only — the Tauri
shell uses WebKit/WebView2), a screen-reader pass, and contrast-ratio
measurement. **Eleven modules remain placeholders** — they are not
completed modules, so their placeholder routes are correct rather than a
regression.

### M8 Phase 7A — Optimization & QA (remainder)
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
