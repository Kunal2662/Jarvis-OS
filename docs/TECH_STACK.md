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

| Concern | Technology | What it does | Why it was selected |
|---|---|---|---|
| Language | Python 3.13 | The entire backend runtime. | Unchanged from the current codebase — the AI/ML ecosystem (LangChain, transformers, Whisper, ChromaDB clients) is Python-native; rewriting the runtime in another language to chase a UI-technology change would be a solution in search of a problem. |
| API framework | FastAPI | Exposes every backend service over HTTP/WebSocket. | Async-native (matches the existing `asyncio`-based service layer), Pydantic-validated request/response models for free, and it was already the control-plane server from M0 — this migration grows its role rather than introducing a second framework. Replaces direct in-process Qt calls as the UI's entry point. |
| Real-time | WebSocket | Streaming chat tokens, agent trace events, voice state, live automation/workflow progress. | Anywhere the current `EventBus` publishes today needs a push channel, not polling — one connection per client session (`docs/ARCHITECTURE.md` §6), multiplexed by event category. |
| Sync calls | REST | Request/response operations — settings reads/writes, history queries, one-shot commands. | Simpler caching/retry semantics than a bidirectional channel for anything that isn't inherently a stream. |
| Agent runtime | LangGraph + LangChain | Orchestrates the multi-step tool-use/reasoning graph (Intent → Planning → Tool Execution → Verification) behind every AI-driven feature — `agents/graph.py`, `agents/nodes/*`. | A graph-based orchestrator makes each reasoning step (and its Agent Trace visibility) an inspectable node/edge instead of an opaque prompt chain — the binding requirement `docs/ARCHITECTURE.md` §15 (AI standards) formalizes so no feature builds its own ad hoc agent loop. |
| Local LLM | Ollama | Runs open-weight models entirely on-device — no network call, no per-token cost, no data leaving the machine. | The backbone of JARVIS's local-first default: every AI feature must work with zero cloud dependency; Ollama is the local inference path every LLM-backed service falls back to (or prefers) depending on user settings. |
| Cloud LLM | OpenAI | Optional, higher-capability model access when the user opts in. | Additive, never required — matches the "cloud features are additive" principle (§9 below); the same `ILLMProvider` port both Ollama and OpenAI implement means a feature never hardcodes which one it's talking to. |
| Everything below FastAPI | Unchanged | `services → agents → core.interfaces`, `infrastructure → core.interfaces`, DI container, Event Bus — all exactly as shipped in M0–M7. | FastAPI's routers become the new (and, per M5's "Backend Platform" reframing, only) consumer of these services; PySide6's direct in-process calls are retired as the UI migrates. |

**Backend/frontend contract:** FastAPI route handlers and WebSocket
consumers are the only new code this migration requires in the
Python layer. No service, agent tool, or domain model changes shape —
they gain an HTTP/WebSocket-facing adapter, the same way every
existing port gains a concrete adapter in `infrastructure/`.

---

## 4. Database

**Three storage tiers, three distinct jobs — none of them overlap, and
none of them replaces another:**

| Concern | Technology | What it stores | Why it was selected |
|---|---|---|---|
| **Local structured data** | **SQLite** | Every transactional record JARVIS owns — conversations, messages, memories, goals, routines, preferences, plugin state, settings. The single source of truth for anything queried by exact field (`WHERE id = ...`, `WHERE status = 'active'`). | Zero-ops, single-file, ships with Python — no server process to run or secure for a local-first product. Unchanged — same engine, same `IDatabase` port, same Alembic migration chain since M0. |
| **Vector memory** | **ChromaDB** | Embeddings for semantic search/recall over memory and knowledge-graph content — the *meaning*-based index SQLite's exact-match queries can't serve. One shared collection, records distinguished by `record_type` metadata (M10A) rather than a separate collection per feature. | Purpose-built for approximate-nearest-neighbor search over embeddings; running it alongside SQLite (rather than trying to bolt vector search onto a relational store) keeps each engine doing the one thing it's actually good at. See `MASTER_ROADMAP.md` §12. |
| **Cloud sync** *(future — see §5)* | **MongoDB** | An optional, outbound-only mirror of a user's data for multi-device sync — **not** a replacement for SQLite. SQLite remains the authoritative local store on every device; MongoDB (when a user opts in) is a sync target, the same "optional, additive, never required" role Oracle Cloud already occupies below. | Document-shaped, schema-flexible storage matches syncing heterogeneous, evolving record types (goals, memories, preferences) across devices without a rigid cross-device schema migration story — a different job than SQLite's single-machine transactional store, which is why it sits alongside it, not instead of it. |

**The rule, stated once so it doesn't need repeating per document:**
SQLite = local, ChromaDB = vector, MongoDB = cloud sync (future). Each
answers a different question (exact record / semantic similarity /
multi-device availability); a feature never picks one because "it's
the database," it picks the one whose question it's actually asking.

---

## 5. Cloud

| Concern | Technology | Notes |
|---|---|---|
| Cloud provider | Oracle Cloud | Optional — local-first remains the default; nothing requires a cloud account to run JARVIS. Used for the M11 Integrations & Cloud Platform's outbound sync target, when enabled. |
| Cloud data sync | MongoDB *(future)* | Not started, not yet assigned to a specific milestone — conceptually extends M11 Integrations & Cloud Platform's sync scope alongside Oracle Cloud. See §4 above for why it doesn't replace SQLite. |

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

---

## 10. Future technology

*(Not started. Listed here so a new developer knows what's coming and
why, without mistaking any of it for shipped scope — cross-check
`MASTER_ROADMAP.md` §8 before assuming any of the below is scheduled
for a specific milestone; several are not yet assigned one.)*

| Technology | What it will do | Why it's the right fit | Status |
|---|---|---|---|
| **MongoDB** | Optional multi-device cloud sync target for a user's data. | Document-shaped storage matches syncing heterogeneous, evolving record types across devices without a rigid schema-migration story — see §4's storage-tier table for why this sits alongside SQLite, never instead of it. | Not started; not yet assigned a milestone. Conceptually extends M11 Integrations & Cloud Platform. |
| **MCP (Model Context Protocol)** | A standardized way for JARVIS to consume external tool/context providers, and to expose its own tools to other MCP-aware clients, without a bespoke integration per provider. | The same "ports and adapters" principle JARVIS already applies to LLMs/STT/TTS/vector stores (§9 above, `docs/ARCHITECTURE.md` §1) — MCP is one more standardized protocol adapter, not a parallel integration mechanism. | Not started. **Owned by M10.5 — MCP & Integration Platform** (added Aug 2026), scheduled immediately before M11 so M11's providers build on it rather than retrofit onto it. See `MASTER_ROADMAP.md` §8. |
| **Plugin Marketplace evolution** | Growing M9's already-shipped Plugin Marketplace Foundation (backend index/install/uninstall API) and M8's Marketplace UI into a full discovery/distribution surface — ratings, versioned updates, a public listing. | Extends real, shipped infrastructure (`core/plugins/`, `routes/plugins.py`) rather than building a second plugin distribution mechanism. | Foundation shipped (M9); full marketplace experience not started. |
| **SDK** | A packaged, documented developer kit for building JARVIS plugins outside this repository — versioned, publishable, with its own compatibility contract (`sdk_range` in the module manifest, `docs/ARCHITECTURE.md` §10, already real). | The plugin manifest's `sdk_range` field and `IPlatformAdapter` capability-probing already exist specifically so a plugin can be built and version-checked independent of the host app's release cadence — an SDK package is that same contract, distributed. | Manifest contract shipped (M9); a standalone distributable SDK package not started. |
| **Mobile Companion** | Voice conversations, chat interface, notification center, remote assistant, personal dashboard, activity feed, and AI suggestions from a phone. | Reuses the same REST/WebSocket contract the React/Tauri desktop client uses (`docs/ARCHITECTURE.md` §5/§6) — a second client of the existing backend, not a second backend. | Not started. Planned under M21 Mobile Platform — see `MASTER_ROADMAP.md` §8. |
| **Wearables / AR Glasses (e.g. Mentra Live)** | Hands-free, glanceable JARVIS access — notifications, voice interaction, and lightweight visual overlays from a wearable device. | Same client-of-the-backend model as Mobile Companion; a wearable is a thin, capability-constrained client, not a reason to duplicate backend logic. Specific hardware partners (e.g. Mentra Live) are a client-integration detail, not an architecture decision — the backend contract doesn't change per device. | Not started. Planned under M21 Mobile Platform's Wearable integration scope alongside Mobile Companion. |
