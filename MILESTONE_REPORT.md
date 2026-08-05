# Milestone Report — M8 Phase 5 + Phase 6

**Version:** 0.31.0
**Branch:** `feature/m8-phase-5-6`
**Baseline:** v0.30.0 (`daf387f` M8 Phase 3, `524a123` architecture docs)
**Date:** 2026-08-06

---

## 1. Executive summary

Phase 5 turned the workspace into the JARVIS operating environment:
every backend module that has something real to show now reaches the
user, through three audience-specific dashboards and eleven new
dashboard widgets. Phase 6 hardened it — skeleton loaders, honest
per-widget offline/empty/error states, automatic connection recovery,
and the §22.12 audience gate.

**The milestone began with an API audit, and that audit changed the
plan.** I enumerated all 172 REST operations the frozen backend exposes
before writing any UI. Three findings shaped everything after:

1. **`GET /health` is a bare liveness probe** (`{status, version}`). The
   rich subsystem data every "… Status" widget needs is published as the
   `health.updated` **WebSocket** event, which nothing on the frontend
   was reading. The dashboards subscribe rather than poll — no new
   endpoint, and the numbers move on their own.
2. **Seven of the Administrator Dashboard's thirteen panels have no
   backend at all.** Users, budgets, provider priority, calibration
   status, analytics and synchronization are all `ARCHITECTURE.md` §22
   — approved and *not built*. They are named on screen, not mocked.
3. **Two AI Dashboard widgets from the brief have no data source.**
   Recent Conversations (no conversation-history route exists) and
   Pinned Projects (`Project` has no `pinned` column; `Note` and
   `Workspace` do).

**Backend untouched.** No route, model, schema, event or contract
changed. pytest, black, ruff and mypy are byte-identical to v0.30.0 —
the evidence, not the assertion, that the freeze held.

---

## 2. Architecture decisions

### 2.1 A single audience gate, not per-panel judgement

`core/user-mode.ts` defines three modes and the seven classes of
information §22.12 restricts. Every restricted surface asks it; none
re-decides what "advanced" means. `stores/user-mode.store.ts` *derives*
the mode from Developer Mode's existing session unlock rather than
keeping a second flag — two flags that can disagree about whether
provider names may be shown will eventually disagree permissively.

Administrator is modelled and enforced now even though the backend
account model does not exist (§22.11 is approved, not built). Nothing
regresses if it never arrives; nothing leaks if it does.
`resolveUserMode()` is the one function that changes on the day it ships.

### 2.2 Two gates, because layouts travel

Restricted panels are filtered out of the panel *menu* **and** refused
by the dashboard components themselves. The menu filter alone is not
enough: a workspace layout exported from a developer's machine and
imported on a personal one would otherwise render a Developer Dashboard.

This is a *render* gate, not a security boundary — the routes behind it
are session-authenticated like every other route. That division is
correct: the backend authenticates, the frontend decides what to show.
§22.12 is a product rule about what a personal user's JARVIS *contains*.

### 2.3 No new registries

Eleven AI Dashboard widgets joined the existing
`dashboardWidgetRegistry`; four new panels joined the existing
`panelRegistry`. Both are `ContributionRegistry` instances. The widget
grid, panel container, persistence and import/export all work on them
with no change, because there was nothing new to teach.

### 2.4 One fetch hook, one set of states

`useBackendResource` + `ResourceView` replace what would have been
fifteen hand-rolled `useEffect`/`useState` triples — fifteen chances to
forget the offline case and fifteen slightly different error strings. It
also makes connection recovery free at the widget level: `isLive` is a
dependency, so a widget refetches when the backend returns.

Deliberately not TanStack Query (which *is* a dependency): Query's value
is its cache, and a live health snapshot wants the current answer.

---

## 3. Implementation details

### 3.1 Phase 5 — modules and dashboards

**New:** `core/user-mode.ts`, `stores/user-mode.store.ts`,
`stores/health.store.ts`, `hooks/use-backend-resource.ts`,
`components/common/resource-view.tsx`,
`components/common/skeleton.tsx`,
`features/dashboard/ai-dashboard-widgets.tsx`,
`features/dashboard/ai-dashboard-registration.ts`,
`features/developer/developer-dashboard.tsx`,
`features/admin/administrator-dashboard.tsx`,
`features/plugins/plugins-panel.tsx`,
`features/diagnostics/diagnostics-panel.tsx`.

**Extended:** `services/api/endpoints.ts` (calendar, knowledge,
intelligence, plugins, devtools, MCP, gateway stats, audit log — every
path verified against the 172-operation dump), `services/realtime-bridge.ts`
(health snapshot + clear-on-disconnect), `core/panel-registry.ts`
(`requiredMode`), `core/startup-orchestrator.ts`.

**AI Dashboard — 11 widgets, all on real data:** System Overview,
Subsystem Status, Performance, Knowledge Graph, Suggestions (M10B's real
engine), Recent Tasks, Projects, Pinned Notes, Recent Files, Upcoming
Calendar, Notification Summary.

Six of the brief's separate "… Status" widgets ship as one
`SubsystemStatusWidget`: they share one data source and one
presentation, and a user asking "is anything wrong?" is better served by
one list than by hunting six cards.

**Developer Dashboard — 7 panels:** providers & routing, outbound API
counters, API inspector, performance metrics, agent trace, the relay's
61-event vocabulary, runtime state.

**Administrator Dashboard — 6 real panels + 1 honest gap panel:** AI
health, API usage, provider health, voice providers, secrets status
(configured-or-not, never values), audit log; plus "Not yet available"
naming the seven §22 capabilities and why.

### 3.2 Phase 6 — polish

Skeleton loaders shaped like the content they replace; `ResourceView`'s
four honest states per widget; automatic connection recovery
(`installConnectionRecovery` — re-runs ping → session → socket, because
the socket's own retry reuses a token a restarted backend will refuse
forever); virtual lists on every unbounded list; lazy-loaded panels with
`<Suspense>`; `memo` where it pays.

---

## 4. Security notes

**A real §22.12 leak I shipped in Phase 3 is fixed here.** The Activity
Center rendered `agent.step`'s raw `node` field — `planner`,
`tool_executor`, `critic` — to every audience. My Phase 3 report flagged
it as a gating requirement; this is that gate. Personal users now see
the mandated progress vocabulary; step count, ordering and status are
identical in both modes, so it is fewer *words*, not less truth.

**A correction to that same Phase 3 report:** it also claimed the Status
Bar's "AI Provider" item names a provider. It does not — it renders
"Not configured" via `NotConfiguredItem`, and never leaked.

**Secrets:** the Administrator Dashboard reports whether a secret is
configured, never its value, and does no redaction of its own — the
backend already redacts server-side (`public_snapshot()`, the Phase 2
fix). A second redaction layer would imply the first might be
incomplete.

**No credentials, tokens or provider values are rendered anywhere.**

---

## 5. Performance notes

| Concern | Approach |
|---|---|
| Fast startup | Panels and dashboards lazy-loaded; the build emits 14 feature chunks |
| Low memory | Virtual lists on notifications, activity, API calls, audit log, secrets |
| Fast navigation | Route splitting; `memo` on `PanelFrame` |
| Smooth panel movement | Fractional layout maths, no per-frame React state |
| Fast search | Debounced, out-of-order-guarded, server-side |
| Instant workspace switching | Layout is local state; switching is a store read |
| No duplicated state | Health has one store; activity merges three live stores rather than copying them; user mode is derived |

Bundle: largest app chunk 99 kB (29 kB gzipped), unchanged in shape from
v0.30.0; new features arrive as their own chunks.

---

## 6. Quality gate results

| Gate | Result | vs. v0.30.0 |
|---|---|---|
| `pytest` | 2218 passed, 1 skipped | **unchanged** |
| `npm test` | **530 passed, 67 files** | +41 tests, +3 files |
| `npm run lint` | 16 warnings, 1 category | **unchanged** |
| `npm run typecheck` | clean | unchanged |
| `npm run build` | clean, no warnings | unchanged |
| `black --check src tests` | 567 files unchanged | **unchanged** |
| `ruff check src tests` | 21 categories | **unchanged** |
| `mypy src` | 262 errors | **unchanged** |

One lint warning appeared mid-build (an unused non-component export in
`ai-dashboard-widgets.tsx`) and was removed rather than accepted.

**41 tests added:** `user-mode.test.ts` (14), `health.store.test.ts`
(13), `dashboard-gating.test.tsx` (10), plus the Activity Center suite
rewritten to prove both modes (11, up from 7).

---

## 7. Remaining work

**Not built because the frozen backend has no API** — all of it
`ARCHITECTURE.md` §22, approved and not built:

- Users & roles (§22.11) · Daily/monthly budgets (§22.3) · Provider
  priority (§22.2) · Calibration status (§22.8) · Analytics and
  Synchronization (§22.5).
- Recent Conversations — no conversation-history route.
- Vision status — M6 shipped an architecture layer; no vision service
  reports to the health monitor and no `vision` search source exists.

**Deliberate scope decisions:**

- *Pinned Projects* → **Pinned Notes**. `Project` has no `pinned`
  column; `Note` does. Projects surface by their real `status` field.
- *Provider Status* moved off the AI Dashboard to the Developer
  Dashboard — real data, but §22.12 restricts it.
- Plugin install/uninstall omitted: `POST /plugins/install` takes a path
  on the *backend's* filesystem, which a browser cannot supply.
- Eleven placeholder modules (Chat, Memory, Browser, Coding, Finance,
  Smart Home, Calendar, Gmail, Spotify…) still register no panel — they
  have no real content, and a title bar around "not built yet" would
  dress an unbuilt module up as a working one.

**Phase 6 items still open:** image optimization (no images to
optimise), window state persistence beyond the existing
`@tauri-apps/plugin-window-state`, and DPI/multi-monitor — all blocked
on the same Tauri window APIs as Phase 3's Window Management item.

---

## 8. Version, commit, push

- **Application version:** 0.30.0 → **0.31.0** (`pyproject.toml`).
- **Branch:** `feature/m8-phase-5-6`
- **Commit:** see §9 below.
- **Push:** confirmed to `origin`.

Documentation is a **separate commit** per the brief, made after this
one, touching no application code.
