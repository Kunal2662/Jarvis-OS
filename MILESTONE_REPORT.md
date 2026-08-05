# Milestone Report — M8 Phase 3: Universal Workspace Framework

**Version:** 0.30.0
**Branch:** `feature/m8-phase-3`
**Baseline:** v0.29.0 (`3fe956b`, M8 Phase 2)
**Date:** 2026-08-06

---

## 1. Scope

The Universal Workspace Framework: a dockable, resizable, persistable
panel system, multiple named workspace layouts, and the three
shell-level panels that framework existed to make possible.

**Frontend only.** No backend route, model, schema, contract or module
changed. Every Python gate below is identical to v0.29.0's — the
intended result of a frontend milestone, and the evidence that the
freeze held.

---

## 2. Requirements, and where each landed

| Requirement | Status | Where |
|---|---|---|
| Universal Workspace Layout | ✅ new | `components/workspace/workspace-container.tsx` |
| Dockable Panels | ✅ new | 4 zones + floating layer, `panel-zone.tsx` |
| Resizable Panels | ✅ new | `panel-splitter.tsx` (pointer **and** keyboard) |
| Persistent Layout Storage | ✅ new | `workspace-layout.store.ts`, `localStorage` |
| Multi-Workspace Support | ✅ new | same store |
| Workspace Switching | ✅ new | `workspace-toolbar.tsx` |
| Workspace Restore | ✅ new | explicit rehydrate at startup (§5) |
| Dynamic Module Loading | ✅ new | `panel-registry.ts` + `React.lazy` per panel |
| Global Command Palette | ✅ **already existed** | `command-palette-provider.tsx` (Phase 3 TG-G) |
| Global Search | ✅ new | `features/search/`, real `POST /api/v1/search` |
| Notification Center | ✅ new | `features/notifications/` — closes a deferred item |
| Activity Center | ✅ new | `features/activity/` |
| Status Bar | ✅ **already existed** | registry-driven, 9 items (Phase 3 TG-E) |
| Global Header | ✅ existed; extended | bell + workspace entry point wired |
| Sidebar Navigation | ✅ **already existed** | adaptive, nested, enablement-driven |
| Responsive Layout | ✅ new | `hooks/use-responsive-layout.ts` |
| Theme Integration | ✅ **already existed** | panels use design tokens throughout |
| Loading States | ✅ existed; applied | `LoadingState` at both Suspense boundaries |
| Empty States | ✅ new per panel | every panel has a real, honest empty state |
| Error States | ✅ existed; applied | `describeError` in Global Search |

Panel operations — open, close, resize, collapse, detach, move, restore
— all seven implemented and tested.

Workspace operations — create, rename, delete, duplicate, reset, import,
export — all seven implemented and tested.

Performance — lazy loading ✅, route splitting ✅, memoization ✅,
virtual lists ✅, Suspense ✅, code splitting ✅ (the build now emits
eight feature chunks where it previously emitted one bundle).

---

## 3. The naming problem this phase had to solve first

"Workspace" already meant two different things here. Adding a third
without separating them would have been a real defect, not a naming
quibble:

| Concept | Owner | What it is |
|---|---|---|
| Active module | `core/workspace-manager.ts` | Which module the route has mounted. One at a time. |
| `Workspace` entity | Backend M11 TG-A | A data scope owning projects, notes, tasks, files. |
| **Workspace layout** | `stores/workspace-layout.store.ts` | **New.** A named arrangement of panels. |

The layout links to the backend entity through `backendWorkspaceId` — an
id, never a copy of backend data, which is the whole point of a foreign
key — and does not touch the module router at all. A test asserts the
layout object has exactly five fields, so a future "convenience" mirror
of the backend workspace's name or project list fails rather than
silently going stale.

---

## 4. What was reused rather than rebuilt

The brief's requirement list contains several things this codebase
already had. Rebuilding any of them would have been the duplicate-system
mistake the project's rules single out, so:

- **`ContributionRegistry`** — `panelRegistry` is an instance of it, not
  a fourth hand-rolled registry alongside Navigation, Dashboard Widgets
  and Status Bar items. That class's own header says it exists for
  exactly this.
- **Command Palette, Status Bar, Sidebar, Theme** — verified present and
  working; untouched.
- **`notifications.store.ts` / `background-tasks.store.ts` /
  `agent-activity.store.ts`** — the Activity Center merges live reads of
  all three in a `useMemo`. A fourth "activity store" mirroring them
  would have gone stale the moment one updated without it.
- **`POST /api/v1/search`** — Global Search adds no index and no
  client-side corpus. A second search implementation would return
  different answers to the same question.
- **`use-media-query.ts`** — the responsive hook builds on it rather than
  writing a second `matchMedia` listener, and reuses the Sidebar's
  existing 768px breakpoint so the two cannot disagree by a few pixels
  and stutter mid-resize.

---

## 5. Two bugs found and prevented during the build

**`skipHydration`, or: workspace restore would have silently wiped
layouts.** Zustand's `persist` rehydrates when its module is first
imported — whenever some component happens to import it. The store's
`merge` drops panels whose contribution is not registered (which is what
makes restore safe against a module removed between releases). Put those
together and a layout rehydrated before `registerCorePanels()` ran would
have had *every* panel dropped as unknown, and the user would have lost
their arrangement to an import-order accident. The store now sets
`skipHydration` and the startup sequence registers panels and *then*
rehydrates, in one task, explicitly ordered.

**A splitter nested inside the flex item it resizes.** First draft put
the divider inside the panel's own flex child; it would have been laid
out along that item's axis and moved with it. Caught on review before it
was written to tests — the splitter is a sibling.

---

## 6. Deliberate limits

- **Detached panels float inside the viewport, not in OS windows.** A
  real second window needs Tauri's multi-window API — its own React root,
  store bridge and IPC — which is `IMPLEMENTATION_ROADMAP.md` Phase 3's
  separate, still-open "Window management (Tauri window APIs)" item. The
  persisted `frame` geometry is already in the shape that work needs, so
  this is a stopping point rather than a wrong turn.
- **Eleven modules register no panel.** The brief lists Chat, Memory,
  Knowledge Graph, Automation, Tasks, Calendar, Vision, Files, Developer
  and Admin Dashboard as example panels. Six panels ship (Dashboard,
  Voice, Settings, Notifications, Activity, Search) — the ones with real
  content. The rest still render `PlaceholderRoute`; wrapping "this
  module hasn't been built yet" in a title bar with resize handles would
  dress an unbuilt module up as a working one, which this project's
  standing "no fake data" rule forbids. The framework needs no change on
  the day they have something to show.
- **Layouts persist locally.** There is no endpoint for panel geometry
  and the backend contract is frozen. It is also genuinely per-device
  state: an arrangement that suits a 34" monitor is wrong on a laptop.
- **DPI scaling and multi-monitor remain open**, both blocked on the same
  Tauri window APIs. Marked as such in the roadmap rather than left
  ambiguous.

---

## 7. Quality gates

| Gate | Result | vs. baseline |
|---|---|---|
| `pytest` | 2218 passed, 1 skipped | **unchanged** |
| `npm test` | **489 passed, 64 files** | +85 tests, +6 files |
| `npm run lint` | 16 warnings, 1 category | **unchanged** |
| `npm run typecheck` | clean | unchanged |
| `npm run build` | clean, 8 feature chunks | no warnings |
| `black --check src tests` | 567 files unchanged | **unchanged** |
| `ruff check src tests` | 21 categories | **unchanged** |
| `mypy src` | 262 errors | **unchanged** |

Three lint warnings and one build warning appeared mid-build and were
both fixed rather than accepted:

- `react(only-export-components)` ×3 — the lazy route components were
  defined in `router.tsx`, which also exports `router`, breaking their
  Fast Refresh. Moved to `routes/lazy-routes.ts`.
- `INEFFECTIVE_DYNAMIC_IMPORT` — `dashboard-grid.tsx` was dynamically
  imported by the panel registry while statically imported by the router,
  so the dynamic import produced no chunk. Made static in both, with the
  reason recorded at both sites.

---

## 8. Tests added (85 across 6 files)

- `workspace-layout.store.test.ts` (36) — workspace lifecycle, zone
  normalisation invariants (sizes always sum to 1, orders always dense),
  detach/restore, import/export round-trip, and the malformed-import
  cases.
- `workspace-container.test.tsx` (12) — driven through the rendered
  chrome, not store calls: closing, collapsing, moving and detaching a
  panel; zones appearing only when populated; keyboard-operable
  splitters; rails dropping at compact widths.
- `workspace-toolbar.test.tsx` (13) — all seven workspace operations
  through the UI, including that export downloads a correctly-slugged
  file and revokes its object URL.
- `notification-center.test.tsx` (9), `activity-center.test.tsx` (7),
  `global-search-panel.test.tsx` (9).

Notable assertions: Global Search must not fire a request while offline
(a silently-empty search box is indistinguishable from one that searched
and found nothing); the Activity Center treats an unrecognised backend
status as *still running* rather than inventing an outcome; a workspace
layout has exactly five fields.

---

## 9. Documentation updated

`README.md` (current version and M8 status), `CHANGELOG.md` (0.30.0),
`docs/IMPLEMENTATION_ROADMAP.md` (Phase 3 checkboxes — Notification
Center and Responsive layout now checked, the framework itself added,
DPI/multi-monitor annotated with their blocking dependency),
`docs/MASTER_ROADMAP.md` (§1 status, §8 Phase 3 entry including the
three-meanings-of-workspace table), `pyproject.toml` (0.29.0 → 0.30.0).

---

## 10. Status

**M8 Phase 3's Universal Workspace Framework is complete**, with the
limits in §6 documented rather than glossed. Backend architecture, API
contracts, database schema and milestone structure are untouched.

**Stopping here for approval before any further milestone work.**
