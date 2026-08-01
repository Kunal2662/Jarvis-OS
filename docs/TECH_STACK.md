# JARVIS OS — Technology Stack

> **Companion to [`MASTER_ROADMAP.md`](MASTER_ROADMAP.md).** This
> document is the single source of truth for *what JARVIS is built
> with* going forward. It does not track feature scope, milestones, or
> acceptance criteria — see `MASTER_ROADMAP.md` for those.
>
> **Scope note.** This is the technology decision for **future**
> work (M8 onward). M0–M7 shipped, and remain historically accurate,
> on PySide6 + Qt Widgets + QSS — see `MASTER_ROADMAP.md` §3 for what
> was actually built and `ARCHITECTURE_LEGACY.md` for its as-shipped
> architecture. Nothing here retroactively changes what those
> milestones delivered. See [`ARCHITECTURE.md`](ARCHITECTURE.md) for
> the current, forward-looking architecture standard this stack
> decision implements.

**Document owner:** project lead
**Status:** Official technology decision, Aug 2026 — governs M8 (React
Frontend & Desktop Experience) onward.

---

## 1. Architecture

JARVIS is not a desktop application with an AI feature bolted on — it
is an AI Operating System. The UI is one replaceable layer among
several; the Python runtime underneath (AI, Memory, Automation, Voice,
Vision, Plugins, Integrations) is the actual product and does not
change shape because the UI's rendering technology changed.

```
React UI
   │
   ▼
Tauri (native shell, IPC bridge)
   │
   ▼
REST + WebSocket
   │
   ▼
Python Runtime
   │
   ├── AI (agent orchestration, LLM providers)
   ├── Memory (semantic + structured)
   ├── Automation (action execution)
   ├── Voice (STT/TTS pipeline)
   ├── Vision (screen/camera/OCR)
   ├── Runtime (lifecycle, services, plugins)
   └── Integrations (OAuth, external APIs)
   │
   ▼
SQLite
   │
   ▼
Cloud (Oracle Cloud, optional)
```

**Why this shape:** the Python backend already implements Clean
Architecture (`ui → features → services → agents → core.interfaces`,
`infrastructure → core.interfaces`, per `ARCHITECTURE_LEGACY.md`).
Replacing
the UI layer means the `ui` and `features` (MVVM controller) layers
are rebuilt in React; `services` downward is untouched Python, now
reached over REST/WebSocket instead of in-process Qt signals. This is
a UI technology change, not a backend architecture change.

---

## 2. Frontend stack

| Concern | Technology | Notes |
|---|---|---|
| UI library | React 19 | Function components + hooks only; no class components. |
| Language | TypeScript | Strict mode. No `any` without a documented reason. |
| Build tool | Vite | Dev server + production bundling. |
| Native shell | Tauri | Replaces Electron — smaller binary, Rust-backed IPC, no bundled Chromium engine duplication. |
| Styling | Tailwind CSS | Utility-first; no separate hand-written CSS files per component unless a utility genuinely can't express it. |
| Component primitives | Radix UI | Unstyled, accessible primitives underneath shadcn/ui. |
| Component library | shadcn/ui | Copy-in components built on Radix, styled with Tailwind — not an npm-installed black box, so components stay editable in-repo. |
| Motion | Motion (Framer Motion's successor) | All animation — hover states, transitions, list reordering. |
| Icons | Lucide Icons | Same icon set already vendored for the PySide6 UI Foundation pass — one visual language carries across the migration. |
| Routing | React Router | Client-side routing within the single Tauri window. |
| Client state | Zustand | Local/UI state — sidebar open/closed, active workspace, transient UI flags. |
| Server state | TanStack Query | All data fetched from the Python backend — caching, invalidation, background refetch. Never duplicate server state into Zustand. |
| Forms | React Hook Form | Every form in the app, including Settings. |
| Validation | Zod | Schema validation, paired with React Hook Form resolvers and to validate WebSocket/REST payloads at the boundary. |
| Font | Inter | Same font already bundled for the PySide6 UI Foundation pass (`resources/fonts/Inter.ttf`) — carries forward unchanged. |

**State management boundary (important):** Zustand and TanStack Query
are not interchangeable. If a value originates from the Python
backend (chat history, memory entries, automation status), it is
TanStack Query's responsibility, cached and invalidated through query
keys — never copied into a Zustand store "for convenience." Zustand
owns only state that has no backend source of truth.

---

## 3. Backend stack

| Concern | Technology | Notes |
|---|---|---|
| Language | Python 3.13 | Unchanged from the current codebase. |
| API framework | FastAPI | Replaces direct in-process Qt calls as the UI's entry point. |
| Real-time | WebSocket | Streaming chat tokens, agent trace events, voice state, live automation/workflow progress — anywhere the current `EventBus` publishes today. |
| Sync calls | REST | Request/response operations — settings reads/writes, history queries, one-shot commands. |
| Everything below FastAPI | Unchanged | `services → agents → core.interfaces`, `infrastructure → core.interfaces`, DI container, Event Bus — all exactly as shipped in M0–M7. FastAPI's routers become the new (and, per M5's "Backend Platform" reframing, only) consumer of these services; PySide6's direct in-process calls are retired as the UI migrates. |

**Backend/frontend contract:** FastAPI route handlers and WebSocket
consumers are the only new code this migration requires in the
Python layer. No service, agent tool, or domain model changes shape —
they gain an HTTP/WebSocket-facing adapter, the same way every
existing port gains a concrete adapter in `infrastructure/`.

---

## 4. Database

| Concern | Technology | Notes |
|---|---|---|
| Structured data | SQLite | Unchanged — same engine, same `IDatabase` port, same Alembic migration chain. |
| Vector memory | ChromaDB | Unchanged — see `MASTER_ROADMAP.md` §12. |

---

## 5. Cloud

| Concern | Technology | Notes |
|---|---|---|
| Cloud provider | Oracle Cloud | Optional — local-first remains the default; nothing requires a cloud account to run JARVIS. Used for the M11 Integrations & Cloud Platform's outbound sync target, when enabled. |

---

## 6. Testing

| Layer | Tool | Notes |
|---|---|---|
| Frontend unit | Vitest | Component and hook logic. |
| Frontend component | React Testing Library | Behavior-driven component tests — query by role/text, not implementation detail. |
| End-to-end | Playwright | Full user flows through the Tauri-hosted app. |
| Backend unit/integration | pytest | Unchanged — same suite, same fixtures, same fakes-in-`tests/fakes/` pattern. |
| Backend lint | Ruff | Unchanged. |
| Backend format | Black | Unchanged. |
| Backend types | MyPy (strict) | Unchanged, `src/` scope. |

No frontend test file talks to a real backend process — REST/WebSocket
calls are mocked at the query-client boundary (TanStack Query) or via
Playwright's own request interception for E2E. No backend test talks
to a real frontend — FastAPI routes are tested with `TestClient`/
`httpx`, the same way the existing API layer already is.

---

## 7. Folder structure

**As actually scaffolded in M8 Phase 1** (`frontend/`, verified building):

```
jarvis-os/                       # repo root -- src/jarvis/ (Python) untouched, unmoved
├── frontend/                    # new React application (self-contained npm project)
│   ├── src/
│   │   ├── main.tsx               # mounts <AppProviders />, the one composition root
│   │   ├── index.css              # Tailwind + design tokens + theme entry point
│   │   ├── providers/              # ThemeProvider, QueryProvider, StoreProvider, RouterProvider, ...
│   │   ├── stores/                  # Zustand stores (UI state only)
│   │   ├── routes/                   # router.tsx, nav-items.ts, per-route placeholders
│   │   ├── components/
│   │   │   ├── ui/                    # shadcn/ui primitives (Button, Card, Dialog, ...)
│   │   │   ├── layout/                 # DesktopShell, Sidebar, Header, Workspace, StatusBar, Dock
│   │   │   └── common/                  # LoadingSpinner and other shared, non-module components
│   │   ├── features/                    # one folder per application (developer/ exists; Gmail/Chat/etc. land per their own phase)
│   │   ├── services/
│   │   │   ├── api/                       # typed REST client (client.ts), query-key factory
│   │   │   ├── websocket/                  # connection manager, event types
│   │   │   └── window/                      # Tauri window-control wrapper
│   │   ├── hooks/                            # shared React hooks (use-connection-status, ...)
│   │   ├── lib/                               # utils.ts (shadcn), motion.ts (Motion config)
│   │   ├── styles/                              # fonts.css, themes.css, tokens.css
│   │   ├── types/                                # shared UI-only types
│   │   └── test/                                  # Vitest setup
│   ├── e2e/                        # Playwright specs (separate from Vitest's src/**)
│   └── src-tauri/                  # Tauri native shell (Rust) -- a subfolder of frontend/,
│                                    # not a repo-root sibling; this is Tauri's own standard
│                                    # convention (`tauri init`'s default target), corrected
│                                    # here from this document's earlier, untested sibling-
│                                    # folder sketch.
└── src/jarvis/                   # existing Python backend, unchanged
```

Each React `features/<name>/` folder mirrors a backend `features/<name>/`
slice by naming convention only — they communicate exclusively through
the REST/WebSocket contract, never by direct import, matching the
existing Clean Architecture rule that no layer imports "up."

---

## 8. Coding standards

**Frontend**
- Function components + hooks only.
- One component per file; colocate a component's own hook if it isn't
  reused elsewhere.
- No inline styles — Tailwind utility classes only, `cn()` (from
  shadcn/ui) for conditional classes.
- Every form uses React Hook Form + a Zod schema — no manually-managed
  `useState` form state.
- Every backend-sourced value is read through a TanStack Query hook —
  no raw `fetch`/`WebSocket` calls inside components.
- No fake or simulated data in production code paths (see §9,
  Development Principles) — a loading state, an empty state, or a real
  value; never a placeholder that looks real.

**Backend** — unchanged from the existing codebase standard (see
`ARCHITECTURE_LEGACY.md` and `MASTER_ROADMAP.md` §4):
- Clean Architecture layering enforced by convention.
- MVVM-equivalent separation: FastAPI routers own no business logic;
  they call `services/`, which own no HTTP/Qt-specific concerns.
- Dependency Injection via `core/di/container.py` for every new
  adapter.
- `EventBus` for cross-cutting notifications, now also relayed over
  WebSocket to subscribed frontend clients.

---

## 9. Technology decisions & development principles

**Why Tauri over Electron:** no bundled Chromium (uses the OS's own
WebView), a Rust-backed native shell, and a smaller resulting binary —
consistent with JARVIS's local-first, resource-conscious design goal
already established in the Python backend (see M22 Edge AI Platform's
resource-consciousness).

**Why REST + WebSocket, not a single transport:** REST for
request/response operations keeps caching/retry semantics simple
(TanStack Query's model); WebSocket is reserved for genuinely
streaming/event-driven data (chat token streaming, Agent Trace,
voice state, live progress) — the same split the Python backend's
`EventBus` (fire-and-forget notifications) versus direct service calls
(request/response) already reflects today.

**Why shadcn/ui over a traditional component library:** components are
copied into the repo, not installed as an opaque dependency — every
component is editable source code, matching the project's existing
preference for owning its own code over depending on a black box
(mirrors why `IconRegistry` vendors specific SVGs rather than pulling
an icon-font dependency).

**Development principles (binding for every new module, per
`MASTER_ROADMAP.md` §8's Global Development Rules):**
1. Business Logic → State Machine → Service Layer → Authentication →
   Permissions → Storage → API Integration → Voice Integration → AI
   Integration → Automation Integration → UI Rendering → Testing, in
   that order. UI is built last, never first.
2. Never create fake data. Never simulate completed functionality. The
   UI only displays real application state — a real value, a real
   loading state, or a real empty state; never a placeholder dressed
   up to look real.
3. No service imports a concrete adapter directly — only its port
   (`core.interfaces` on the backend; a typed API client on the
   frontend).
4. Every new capability ships with tests in the same pass it ships in
   — see §6 above for which tool owns which layer.
