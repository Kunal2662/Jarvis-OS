# JARVIS OS — Architecture Standard

> **Single source of truth for how JARVIS is built, going forward.**
> JARVIS is not a desktop application with an AI feature bolted on —
> it is an **AI Operating System**. The UI is one replaceable layer;
> the Python runtime underneath (AI, Memory, Automation, Voice,
> Vision, Integrations) is the actual product. Every future developer
> should be able to read this document once and know exactly how any
> module — present or future — is built, before writing a line of
> code.

**Document owner:** project lead
**Status:** Official architecture standard, Aug 2026 — governs M8
onward.
**Companion docs:** [`TECH_STACK.md`](TECH_STACK.md) (technology
choices) · [`IMPLEMENTATION_ROADMAP.md`](IMPLEMENTATION_ROADMAP.md)
(active execution plan) · [`ARCHITECTURE_LEGACY.md`](ARCHITECTURE_LEGACY.md)
(the as-shipped M0–M7 PySide6 architecture — historical, frozen) ·
[`MASTER_ROADMAP.md`](MASTER_ROADMAP.md) (milestones, scope, timeline).

**Scope note.** This is documentation and standards only — no code
changes ship with this document. M0–M7's shipped implementation is
unaffected; see `ARCHITECTURE_LEGACY.md` for what was actually built.
Where a standard below cites a real, already-shipped mechanism (the
`EventBus`, `ConnectionState`, `JarvisError` hierarchy, the M9 plugin
manifest, and others), that citation is a fact, not aspiration — it is
called out explicitly. Where a standard describes something not yet
built (Priority/Retry on the event bus, the WebSocket protocol, the
FastAPI layer itself), it is marked **(new, M8+)** so no reader
mistakes a standard for a shipped guarantee.

---

## Table of contents

1. [Overall architecture](#1-overall-architecture)
2. [Module architecture](#2-module-architecture)
3. [Module lifecycle](#3-module-lifecycle)
4. [State machine standard](#4-state-machine-standard)
5. [API contract standards](#5-api-contract-standards)
6. [WebSocket standards](#6-websocket-standards)
7. [Event bus standards](#7-event-bus-standards)
8. [Service standards](#8-service-standards)
9. [Error handling standards](#9-error-handling-standards)
10. [Module manifest specification](#10-module-manifest-specification)
11. [Settings standards](#11-settings-standards)
12. [Storage standards](#12-storage-standards)
13. [Developer standards](#13-developer-standards)
14. [UI standards](#14-ui-standards)
15. [AI standards](#15-ai-standards)
16. [Automation standards](#16-automation-standards)
17. [Security standards](#17-security-standards)
18. [Testing standards](#18-testing-standards)
19. [Performance standards](#19-performance-standards)
20. [Governance — how this document changes](#20-governance--how-this-document-changes)

---

## 1. Overall architecture

```
┌──────────────────────────────────────────────────────────────┐
│                          React UI                             │
│   Views · Components · Hooks · Zustand stores · TanStack      │
│   Query · React Hook Form + Zod                                │
└──────────────────────────────┬────────────────────────────────┘
                               │
┌──────────────────────────────▼────────────────────────────────┐
│                            Tauri                                │
│   Native shell · window management · OS integration · IPC      │
└──────────────────────────────┬────────────────────────────────┘
                               │  REST (request/response)
                               │  WebSocket (streaming/events)
┌──────────────────────────────▼────────────────────────────────┐
│                           FastAPI                                │
│   Routers (one per feature slice) · WebSocket handlers ·        │
│   Auth/session middleware · request validation (Pydantic)       │
└──────────────────────────────┬────────────────────────────────┘
                               │
┌──────────────────────────────▼────────────────────────────────┐
│                         Core Runtime                             │
│   Runtime Manager · Service Manager · DI Container · Event Bus  │
│   · Config · Logging · Exceptions · State Machines               │
└──────────────────────────────┬────────────────────────────────┘
                               │
        ┌──────────┬──────────┼──────────┬──────────┬──────────┐
        ▼          ▼          ▼          ▼          ▼          ▼
   ┌────────┐ ┌────────┐ ┌─────────┐ ┌───────┐ ┌────────┐ ┌────────────┐
   │   AI   │ │ Memory │ │Automation│ │ Voice │ │ Vision │ │Integrations│
   └────┬───┘ └────┬───┘ └────┬────┘ └───┬───┘ └────┬───┘ └──────┬─────┘
        └──────────┴──────────┴──────────┴──────────┴────────────┘
                               │
┌──────────────────────────────▼────────────────────────────────┐
│                            SQLite                                │
│   Structured data · ChromaDB (vector memory) · Alembic migrations│
└──────────────────────────────┬────────────────────────────────┘
                               │  optional, outbound-only
┌──────────────────────────────▼────────────────────────────────┐
│                             Cloud                                 │
│   Oracle Cloud (optional sync target) — local-first remains the  │
│   default; nothing above this line requires it to function.      │
└──────────────────────────────────────────────────────────────┘
```

**The dependency rule** (unchanged from the Clean Architecture rule
`ARCHITECTURE_LEGACY.md` already established, extended to the new
top boundary):

```
React UI → Tauri → REST/WebSocket → FastAPI → Core Runtime →
    { AI · Memory · Automation · Voice · Vision · Integrations } →
    core.interfaces
infrastructure ─────────────────────────────────────────→ core.interfaces
```

- **React UI** never imports Python. It knows only the typed REST/
  WebSocket contract (§5, §6).
- **Tauri** is a transport and native-shell concern only — it holds no
  business logic. A Tauri command handler that does more than forward
  to REST/WebSocket or touch the local filesystem (for Tauri-native
  concerns like window state) is a bug.
- **FastAPI** routers are thin — they validate the request (Pydantic),
  call exactly one service method, and shape the response. Business
  logic never lives in a router function.
- **Core Runtime** is the layer introduced by M9 (Runtime & Core
  Services) — Runtime Manager, Service Manager, DI Container (the
  existing `core/di/container.py`, unchanged), Event Bus (the existing
  `core/events/event_bus.py`, unchanged), Config, Logging, Exceptions,
  and the State Machine standard (§4).
- **AI / Memory / Automation / Voice / Vision / Integrations** are the
  existing `services`/`agents` layer from `ARCHITECTURE_LEGACY.md`,
  unrenamed in code — this diagram groups them by capability for
  readability, not as a new package structure.
- **SQLite** and **Cloud** are unchanged from today — see §12.

**What changed vs. the legacy architecture, precisely:** only the top
two boxes (`UI`, and the boundary immediately below it). `Features`
down through `Infrastructure` in `ARCHITECTURE_LEGACY.md` §2 keep
their exact shape; they are reached through FastAPI now instead of
in-process Qt calls, and nothing else about them changes.

---

## 2. Module architecture

Every application/module in JARVIS — present or future, frontend or
backend — is built in this order, and only this order. This is not a
suggestion: a module that skips a layer (most commonly, building UI
before the Service Layer exists) is rejected in review.

```
Application
   │
   ▼
Business Logic        — what determines this module's behavior, in
   │                     prose first, then pure functions/classes with
   │                     zero framework imports (no Qt, no React, no
   │                     FastAPI). Unit-testable with zero mocking.
   ▼
State Machine          — the module's states (§4) and legal
   │                     transitions between them. Pure logic, imports
   │                     only Business Logic above it.
   ▼
Service Layer           — a real class (e.g. `GmailService`) that
   │                     *uses* the State Machine and Business Logic,
   │                     implements a `core.interfaces` Protocol,
   │                     wired through the DI container (§8).
   ▼
Storage                 — where this module's data lives (§12) —
   │                     declared before the module reads or writes
   │                     anything.
   ▼
Authentication          — if the module connects to anything external,
   │                     its auth flow (§17) is defined here, not
   │                     improvised per-provider.
   ▼
Permissions              — what this module is allowed to do, and who
   │                     grants it (§10's manifest, §17).
   ▼
API Provider              — the real OAuth/HTTP client behind the
   │                     Service Layer's port — the concrete adapter
   │                     in `infrastructure/`, per the existing
   │                     Ports & Adapters pattern.
   ▼
Voice                     — if applicable, the module's voice commands
   │                     (§10 manifest) and how it participates in the
   │                     voice pipeline (§15).
   ▼
AI                        — if applicable, the module's agent tool(s)
   │                     (§15), registered the same way every M5A tool
   │                     already is.
   ▼
Automation                 — if applicable, the module's automation
   │                     actions (§16) — what it exposes to
   │                     `ActionExecutor`/the AI Orchestrator.
   ▼
UI                        — a React view that reads the Service
   │                     Layer's state (via REST/WebSocket, §5/§6) and
   │                     renders it, never inventing data not actually
   │                     reported.
   ▼
Tests                     — every layer above gets its own test at the
                          layer it was built, not retrofitted at the
                          end. See §18.
```

**Why this order, not "UI first":** a UI built before the Service
Layer exists has nothing real to render, so it renders fake or
simulated data — the single most-repeated failure mode this
architecture exists to prevent (see §14's "no fake data" rule, and
the Development Principles below). Building bottom-up means every
layer above is testable and real by the time the layer above it
exists.

**Real precedent this section formalizes, not invents:** this is
exactly the build order the §7 "UI Foundation" pass (Typography, SVG
Icons, `ModuleStateMachine`) already followed and documented — see
`MASTER_ROADMAP.md` §7. This document makes that precedent the
binding standard for every module, not just that one pass.

---

## 3. Module lifecycle

Every module (a backend service, a plugin, an integration provider)
implements the following lifecycle. Not every stage does real work for
every module — a module with nothing to configure has a no-op
`configure()` — but every stage must exist and be documented, even as
a no-op, so the Runtime Manager (M9) can always call the full sequence
uniformly.

| Stage | Called when | Responsibilities |
|---|---|---|
| `install()` | Once, on first setup (module added, plugin installed) | Create any storage this module owns (§12) that doesn't yet exist; register the module's manifest (§10) with the Runtime; never touches network or requires user auth. |
| `configure()` | After install, and whenever settings change | Load/validate this module's settings (§11) against its schema; does not connect to anything external yet. |
| `initialize()` | On every app start, before `start()` | Build the module's Service Layer instance, wire it through the DI container, register it with Service Manager (M9) — no I/O to external systems yet, this is object construction only. |
| `start()` | Immediately after `initialize()` | Begin the module's real work — open connections, start background tasks, transition the module's state machine (§4) out of its idle state. May fail; a failed `start()` moves the module to `ERROR`, not a crash. |
| `ready()` | Called by the module itself, not the Runtime, once `start()`'s async work completes | Publishes a state-machine transition to `READY` (or `EMPTY`/`CONNECTED`, per §4) over the Event Bus so the UI can react; this is a signal, not a lifecycle stage the Runtime blocks on. |
| `pause()` | User action, or Runtime-initiated resource pressure (e.g. Resource Manager, M9) | Suspends non-critical work (background sync, polling) without losing state; must be resumable via `resume()` without re-running `start()`. |
| `resume()` | User action, or resource pressure clearing | Reverses `pause()` exactly; a module that cannot cleanly resume must document why and fall back to a full `stop()`/`start()` cycle instead — this is the exception, not the default. |
| `stop()` | User disables the module, or app shutdown begins | Closes connections, cancels background tasks, transitions the state machine toward `DISCONNECTED`; must be safe to call even if `start()` never completed. |
| `shutdown()` | App shutdown, after every module's `stop()` | Releases any resource that survives `stop()` (file handles, thread pools); registered once with the existing `ShutdownManager` (`core.lifecycle.shutdown_manager`, shipped M5.5) — a module never implements its own shutdown-ordering logic. |

**Failure handling:** if any stage raises, it raises a `JarvisError`
subclass (§9), the Runtime logs it and moves the module to `ERROR`
(§4) rather than propagating the exception to crash the app —
mirroring `ShutdownManager`'s existing "fault-isolated" cleanup
guarantee, extended to every lifecycle stage, not just shutdown.

**Idempotency:** `install()`, `configure()`, and `stop()` must be safe
to call more than once with no additional effect the second time — a
module is never in an undefined state because a lifecycle stage ran
twice (e.g. a retried Runtime Manager call after a partial failure).

---

## 4. State machine standard

**This standard is already shipped, not new.** `domain/app_state/models.py`
(built during the §7 "UI Foundation" pass) defines exactly this state
set today:

```python
class ConnectionState(StrEnum):
    NOT_INSTALLED = "not_installed"
    NOT_CONFIGURED = "not_configured"
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    AUTHENTICATING = "authenticating"
    CONNECTED = "connected"
    SYNCING = "syncing"
    READY = "ready"
    EMPTY = "empty"
    OFFLINE = "offline"
    ERROR = "error"
```

Every connected module (Gmail, Spotify, Calendar, Finance, Weather,
Smart Home, and every future integration) reports through this exact
enum — no module invents its own state name. `domain/app_state/machine.py`'s
`ModuleStateMachine` (also shipped) enforces the legal transition
graph below; an illegal jump (e.g. `NOT_CONFIGURED` straight to
`SYNCING`, skipping `CONNECTING`) raises `InvalidStateTransitionError`
(`core/exceptions.py`) rather than silently letting a caller — or the
UI — render a state that was never actually reached.

**Transition graph** (as implemented in `ModuleStateMachine`):

```
NOT_INSTALLED ──► NOT_CONFIGURED ──► CONNECTING ──┬──► AUTHENTICATING ──┬──► CONNECTED
                                                     └────────────────────┘         │
                                                                          ERROR ◄────┤
                                                                                     ▼
                                              ┌──────────────────────────── SYNCING ◄┤
                                              │                                      │
                                              ▼                                      ▼
                          DISCONNECTED ◄── READY ◄──────────────────────────► EMPTY
                                │             │                                 │
                                │             ▼                                 ▼
                                │          OFFLINE ◄─────────────────────────────┘
                                │             │
                                └─────────────┴──► CONNECTING (reconnect)
ERROR ──► CONNECTING | DISCONNECTED | NOT_CONFIGURED
```

Self-transitions (re-entering the same state, e.g. re-confirming
`READY` after a no-op refresh) are always legal. See
`domain/app_state/machine.py`'s `_TRANSITIONS` dict for the
authoritative, exhaustive table — the diagram above is a readable
summary, the code is the source of truth if the two ever disagree.

**A second, distinct state shape** already exists for linear,
run-once pipelines (a voice/chat turn), not persistent connections —
`ConversationTurnState`:

```python
class ConversationTurnState(StrEnum):
    LISTENING = "listening"
    TRANSCRIBING = "transcribing"
    THINKING = "thinking"
    RESPONDING = "responding"
    SPEAKING = "speaking"  # voice only
    READY = "ready"
```

**Rule: no module may invent a custom state without documenting it
here.** If a module's lifecycle genuinely doesn't fit `ConnectionState`
or `ConversationTurnState`, the new state set must be added to this
section, with its own transition graph, before that module's Service
Layer is built — not discovered by a reviewer after the fact.

**Default states — "no fake data" applied to state.** A module with no
real provider yet reports `NOT_CONFIGURED` (connected-type modules) or
`EMPTY` (local-only modules like Tasks/Schedule/Memory) — never a
state implying capability that doesn't exist. `MODULE_DEFAULT_STATES`
in `domain/app_state/models.py` is the living registry of this rule
applied to every named module.

---

## 5. API contract standards

**Status: (new, M8+)** — no FastAPI layer exists yet; this is the
binding contract for the one M8 builds.

### Naming and versioning

- Base path: `/api/v1/<resource>` — every route is versioned from day
  one. A breaking change to a resource's shape ships as `/api/v2/...`
  alongside `v1` for a deprecation window (mirrors the existing
  backward-compatibility standard in `MASTER_ROADMAP.md` §4), never an
  in-place breaking edit to `v1`.
- Resources are plural nouns: `/api/v1/conversations`, not
  `/api/v1/conversation` or `/api/v1/getConversations`.
- Nested resources reflect real ownership only:
  `/api/v1/conversations/{id}/messages` — never more than two levels
  deep; a third level is a sign the resource needs its own top-level
  route.
- Actions that aren't CRUD are verbs under the resource:
  `POST /api/v1/automations/{id}/run`, not a query parameter hack.

### Request / response schema

Every request body and response body is a Pydantic model, generating
the OpenAPI schema automatically — no hand-written, undocumented JSON
shapes.

```jsonc
// Response envelope — every successful response
{
  "data": { /* the resource or list */ },
  "meta": { /* pagination, timing — omitted when not applicable */ }
}
```

```jsonc
// Error envelope — every non-2xx response, using the universal
// error format from §9
{
  "error": {
    "code": "AUTOMATION_PERMISSION_DENIED",
    "message": "This action requires confirmation.",
    "recovery_action": "Retry with confirm=true, or ask the user.",
    "severity": "warning",
    "retryable": false
  }
}
```

### Pagination

Cursor-based, not offset-based (offset pagination drifts under
concurrent writes):

```jsonc
GET /api/v1/memories?cursor=<opaque>&limit=50
{
  "data": [ /* up to 50 items */ ],
  "meta": { "next_cursor": "<opaque-or-null>" }
}
```

`limit` defaults to 50, caps at 200. A route that can return unbounded
results and doesn't paginate is a bug, not an exception.

### Streaming

A REST route that returns a genuinely large or slow-to-produce
response streams via `StreamingResponse` (Server-Sent Events) rather
than making the client wait for one large JSON body — used for
non-interactive long responses; interactive, bidirectional streaming
(chat tokens, Agent Trace, voice state) is always WebSocket (§6), not
SSE, so there's exactly one streaming transport for anything the user
is actively watching.

### Authentication

Every route except `/api/v1/health` requires a session token
(Bearer, `Authorization: Bearer <token>`), issued by the session
mechanism §17 defines, validated by FastAPI dependency injection
(`Depends(get_current_session)`) — never re-implemented per router.

### Validation

- Pydantic models validate shape and type at the FastAPI boundary —
  a request that fails validation never reaches a service method.
- Business-rule validation (e.g. "this automation step's dependencies
  must exist") happens in the Service Layer, not the router — the
  router's job is shape, the service's job is meaning.
- Every validation failure returns `422` with the error envelope
  above, `code: "VALIDATION_ERROR"`, and a `field_errors` array
  matching Pydantic's own error detail shape.

---

## 6. WebSocket standards

**Status: (new, M8+).**

### Single connection

One WebSocket connection per client session, at `/api/v1/ws`,
multiplexing every event category below by `type` — not one socket
per feature. This mirrors the existing `EventBus`'s own design (§7):
the WebSocket layer is a thin relay of `EventBus` events to connected
clients, not a second, parallel event system.

### Message schema

Every message, both directions, is a JSON envelope:

```jsonc
{
  "type": "voice.state_changed",     // dot-namespaced event name
  "id": "<uuid>",                     // matches Event.id when relaying an EventBus event
  "occurred_at": "2026-08-01T12:00:00Z",
  "payload": { /* event-specific shape */ }
}
```

### Event naming

`<category>.<event>`, lowercase, snake_case within each segment —
categories map directly to the Event Bus categories in §7:

| Category | Example events |
|---|---|
| `voice` | `voice.state_changed`, `voice.transcript_partial`, `voice.transcript_final` |
| `ai` | `ai.token`, `ai.step`, `ai.complete` (streaming, §15) |
| `automation` | `automation.step_started`, `automation.step_completed`, `automation.workflow_finished` |
| `memory` | `memory.updated`, `memory.recalled` |
| `progress` | `progress.update` (long-running non-AI operations — backups, sync) |
| `notification` | `notification.created` (user-facing toast-equivalent) |
| `runtime` | `runtime.module_state_changed` (relays §4 transitions) |

### Heartbeat and reconnect

- Server sends `{"type": "heartbeat", "occurred_at": ...}` every 30s.
- Client that misses 2 consecutive heartbeats (90s) treats the
  connection as dead and reconnects with exponential backoff (1s, 2s,
  4s, 8s, capped at 30s).
- On reconnect, the client sends `{"type": "resume", "last_id": "<uuid>"}`
  with the last message `id` it processed; the server replays any
  events published since, up to a bounded buffer (60s) — beyond that
  window the client does a full state refetch via REST instead of
  relying on WebSocket replay.

### Authentication

The WebSocket handshake carries the same Bearer session token as REST
(§5), as a query parameter at connect time (`wss://.../ws?token=...`)
since WebSocket handshakes cannot carry custom headers from a browser
`WebSocket` constructor — the token is validated once at connect, and
the connection is closed with code `4401` if invalid or expired.

### Event category detail

- **Progress events** carry `{ "operation_id", "percent", "message" }`
  — the WebSocket-native successor to `UpdatePhaseEvent`'s existing
  shape (`session_id`/`phase`/`progress_percent`/`message`), extended
  to any long-running operation, not just Update Center.
- **AI streaming events** (`ai.token`) are the real token-level
  streaming M10 (AI Orchestrator) introduces, replacing M5A's
  `stream()` word-chunking limitation — see `MASTER_ROADMAP.md` §8's
  M10 entry.
- **Automation events** mirror the shipped `AutomationStepEvent` /
  `WorkflowStepEvent` shapes (`core/events/events.py`) field-for-field
  — the WebSocket payload is that dataclass's fields, not a
  reinvented shape.

---

## 7. Event bus standards

**The transport is already shipped** (`core/events/event_bus.py`) —
publish/subscribe, async-aware, in-process only. Its own docstring is
explicit about current scope: *"no persistence, no remote transport
and no retries."* The standards below extend that shipped bus; items
marked **(new, M8+)** are not yet implemented.

### Publish / Subscribe (shipped)

```python
bus.subscribe(SomeEvent, handler)      # returns an unsubscribe callable
await bus.publish(event)               # awaits every handler
bus.publish_nowait(event)              # fire-and-forget, schedules on the loop
```

Handlers are matched by MRO — subscribing to a base `Event` subtype
also receives every subclass instance, exactly as `EventBus.publish`'s
existing `type(event).__mro__` walk implements today.

### Event naming (standardized, not yet enforced by lint)

`<Noun><PastTenseVerb>Event` — matching every event already in
`core/events/events.py` (`AppReadyEvent`, `VoiceStateChangedEvent`,
`AutomationStepEvent`, `WorkflowStepEvent`, `ScheduledJobFiredEvent`).
A new event that doesn't follow this pattern is a naming-convention
bug, flagged in review the same way an un-Pythonic identifier would
be.

### Priority **(new, M8+)**

The shipped bus delivers to subscribers in subscription order with no
priority concept. Going forward, a handler may declare
`priority: Literal["critical", "normal", "low"] = "normal"` at
subscribe time; `critical` handlers (e.g. `ShutdownManager`-adjacent
safety hooks) run before `normal`, which run before `low` — within the
same priority tier, subscription order is preserved exactly as today.

### Retry **(new, M8+)**

The shipped bus does not retry a failing handler — it logs the
exception (`_logger.exception(...)`, already implemented) and moves on
to the next subscriber, which remains correct default behavior for
most events. For the subset of events where a failed handler
represents lost work (not just a missed UI update), a handler may
declare `retry: RetryPolicy(max_attempts=3, backoff_seconds=1)` — the
same backoff shape already standardized for M11's Integration retry
policy — applied per-handler, never globally, so a flaky UI-update
handler never delays a critical one.

### Failure isolation (shipped, extended)

Already true today: one handler's exception never prevents other
subscribers of the same event from running (`EventBus.publish`'s
`try/except` around each handler call). Extended standard: a handler
that fails 3 consecutive times (regardless of retry policy) is
auto-unsubscribed and a `runtime.handler_disabled` event (§6) is
published so Developer Mode's Debug Console (M9) can surface it —
never a silent, permanently-broken subscription.

### Cancellation **(new, M8+)**

Long-running handlers (rare — most handlers should be fast, dispatch-
and-return) may accept an `asyncio.Event` cancellation token, checked
cooperatively; `EventBus` does not force-cancel a handler task, matching
Python's own cooperative-cancellation model rather than inventing a
harsher one.

### Example events (shipped + standardized future ones)

| Event | Status |
|---|---|
| `AppReadyEvent`, `ShutdownRequestedEvent`, `VoiceStateChangedEvent`, `AutomationStepEvent`, `UpdatePhaseEvent`, `AgentStepEvent`, `VisionProviderStatusEvent`, `WorkflowStepEvent`, `ScheduledJobFiredEvent` | Shipped, `core/events/events.py` |
| `TaskCreatedEvent`, `TaskCompletedEvent` | Planned — M11B (Productivity Suite) Tasks feature |
| `MemoryUpdatedEvent` | Planned — formalizes `MemoryService`'s existing write path into a published event |
| `EmailReceivedEvent`, `CalendarUpdatedEvent` | Planned — M11 (Integrations & Cloud Platform) webhook-driven events |
| `PluginLoadedEvent` | Planned — M9 (Runtime & Core Services) Plugin Platform |

Every planned event above follows the naming standard and inherits
`Event` exactly like the shipped ones — no special-casing.

---

## 8. Service standards

Every service (the Service Layer from §2) exposes exactly this
interface — the same six methods `ARCHITECTURE_LEGACY.md`'s services
already implement informally, made an explicit, binding `Protocol`:

```python
class IService(Protocol):
    async def initialize(self) -> None: ...   # build state, no I/O
    async def start(self) -> None: ...         # begin real work
    async def stop(self) -> None: ...           # graceful stop
    async def health(self) -> HealthStatus: ...  # cheap, frequent check
    async def status(self) -> dict: ...           # detailed, on-demand
    async def shutdown(self) -> None: ...          # final resource release
```

| Method | Responsibility | Called by |
|---|---|---|
| `initialize()` | Construct internal state, resolve DI dependencies. No network/disk I/O. | Runtime Manager, once, at app start — matches §3's `initialize()` lifecycle stage exactly. |
| `start()` | Begin real work per §3. May raise; a raised exception moves the owning module to `ERROR` (§4), it does not crash the Runtime. | Runtime Manager, after every service's `initialize()` has completed. |
| `stop()` | Graceful, idempotent stop per §3. | Runtime Manager (module disabled) or shutdown sequence. |
| `health()` | Cheap (<10ms), frequent, boolean-ish signal — "is this service able to do its job right now." Backs Service Manager's live registry (M9) and Developer Mode's State Inspector. | Health Monitor (M9), polled. |
| `status()` | Detailed, human-readable snapshot — safe to call on-demand, not on a tight poll loop. Backs the Developer Platform Tools' Debug Console/API Inspector (M9). | On-demand — Developer Mode, diagnostics. |
| `shutdown()` | Final resource release beyond what `stop()` already did (file handles, thread pools) — registers with the existing `ShutdownManager`, never implements its own ordering. | Shutdown sequence, once, after every service's `stop()`. |

**A service never implements a seventh top-level lifecycle method.**
Anything else a service needs to expose is a domain-specific method on
top of this base six — `AutomationService.run_command()`,
`MemoryService.recall()`, and so on, exactly as they exist today.

---

## 9. Error handling standards

**The hierarchy is already shipped** (`core/exceptions.py`) — every
exception in JARVIS inherits from `JarvisError`. The standards below
formalize the *shape* of an error crossing a layer boundary (service →
API → UI), which does not exist as a structured format yet.

### Universal error format **(new, M8+ — the format; the exception
hierarchy it wraps is shipped)**

```python
@dataclass(frozen=True, slots=True)
class ErrorPayload:
    code: str                 # SCREAMING_SNAKE_CASE, stable across versions
    message: str               # human-readable, safe to show the user
    recovery_action: str | None  # what the user/caller can do about it
    severity: Literal["info", "warning", "error", "critical"]
    retryable: bool
    log_level: Literal["debug", "info", "warning", "error", "critical"]
    user_visible: bool          # False for internal errors the UI never surfaces
    developer_visible: bool = True  # nearly always True; False only for expected, silent-swallow cases
```

### Mapping existing exceptions to `code`

Every `JarvisError` subclass maps to exactly one `code` — the class
name, upper-snake-cased, with the `Error` suffix dropped:
`AutomationPermissionDeniedError` → `AUTOMATION_PERMISSION_DENIED`,
`ToolExecutionError` → `TOOL_EXECUTION`, and so on. This mapping is
generated, not hand-maintained — a new exception class automatically
gets a `code` with zero extra work, and the mapping can never drift
out of sync with the hierarchy.

### Severity guide

| Severity | Meaning | Example |
|---|---|---|
| `info` | Not actually a failure — informational, rarely surfaced | A cache miss that fell back correctly |
| `warning` | Degraded but functional | `RetryableError` before its final attempt |
| `error` | The requested operation failed | `AutomationValidationError` |
| `critical` | The module/service itself is compromised | `DatabaseError` on the primary connection |

### Layer responsibilities

- **Services** raise the specific `JarvisError` subclass — never a
  bare `Exception`, never swallow-and-return-`None` for a real
  failure (matches the existing anti-pattern rule in
  `ARCHITECTURE_LEGACY.md` §9).
- **FastAPI routers** catch `JarvisError` once, at the outermost
  layer, and translate it to the `ErrorPayload` envelope (§5) — a
  router never has a bare `except Exception` either; an unmapped
  exception is a bug to fix, not a case to paper over.
- **React** shows `message` when `user_visible` is true, logs the full
  payload to the console/Developer Mode when `developer_visible` is
  true, and never shows a raw stack trace or exception repr to the
  user — mirroring the existing "single, user-friendly error dialog"
  rule from `ARCHITECTURE_LEGACY.md` §7, now applied per-toast instead
  of per-dialog.

---

## 10. Module manifest specification

Every application/module — a plugin, an integration provider, a first-
party feature slice — declares itself with a manifest. This formalizes
and extends the manifest shape M9's Plugin Platform already specifies
(`plugins/*/manifest.json`) into the standard every module type uses,
not just third-party plugins.

```jsonc
{
  "name": "gmail",
  "display_name": "Gmail",
  "version": "1.0.0",
  "sdk_range": ">=1.0.0,<2.0.0",
  "dependencies": ["memory"],
  "is_core": false,
  "parent_group": null,
  "permissions": [
    "network", "memory.read", "memory.write"
  ],
  "commands": [
    { "id": "gmail.search", "description": "Search email" }
  ],
  "voice_commands": [
    { "phrase": "check my email", "command": "gmail.search" }
  ],
  "automation_support": {
    "actions": ["gmail.send", "gmail.archive"],
    "reversible": ["gmail.archive"]
  },
  "settings_schema": {
    "sync_interval_minutes": { "type": "integer", "default": 15 }
  },
  "routes": ["/api/v1/gmail"],
  "icons": { "default": "gmail.svg" },
  "developer_metadata": {
    "author": "JARVIS core team",
    "homepage": null,
    "repository": null
  }
}
```

| Field | Required | Notes |
|---|---|---|
| `name` | Yes | Lowercase, matches the module's DI-container key. |
| `display_name` | Yes | Human-readable label a UI renders (e.g. "Files") — distinct from `name`. Added Aug 2026 (UI Architecture Update); the frontend's `ModuleManifest.displayName` (`core/module-manifest.ts`) already required this — this table previously omitted it. |
| `version` | Yes | Semver. |
| `sdk_range` | Yes (plugins) / N/A (first-party) | Same `sdk_range` check M9's Plugin Loader already performs — JARVIS refuses to load a mismatched plugin. |
| `dependencies` | Yes (may be empty) | Other module `name`s this one requires present. |
| `is_core` | No, defaults `false` | True only for the fixed default-enabled set (Dashboard, AI's children, Automation, Files, Settings) — added Aug 2026 (UI Architecture Update). Every other module ships disabled until a user enables it (Settings → Plugins, M8 Phase 5) — see M8 Phase 3's Dynamic Sidebar. |
| `parent_group` | No | Groups this module under a synthetic parent nav entry (e.g. `"ai"`) — added Aug 2026 (UI Architecture Update). `null`/absent renders as a top-level entry. |
| `permissions` | Yes (may be empty) | From the fixed vocabulary already defined for M9's Permission Model: `network`, `filesystem`, `hotkey`, `agent_tools`, `voice.stt`, `voice.tts`, `memory.read`, `memory.write`, `smart_home`, `notifications`. |
| `commands` | No | Command Palette-indexed actions (M10A Command Search). |
| `voice_commands` | No | Phrase → command bindings (§15). |
| `automation_support` | No | Actions this module exposes to the AI Orchestrator/`ActionExecutor` (§16), and which are undo-able. |
| `settings_schema` | No | JSON Schema for this module's settings (§11) — enables Dynamic Settings (M8 Phase 5) with zero central-file edits. |
| `routes` | No (backend modules only) | FastAPI route prefixes this module owns. |
| `icons` | No | Lucide icon key (§14), matching the existing `IconRegistry` pattern. |
| `developer_metadata` | No | Author/homepage/repository — informational only. |

**Enforcement:** a module without a manifest cannot be loaded by the
Runtime Manager (M9) — this is not optional documentation, it's the
mechanism the loader reads.

---

## 11. Settings standards

- **Versioned.** Every settings schema declares a `schema_version`
  integer. A settings read at startup with an older version runs
  through a migration chain (one function per version bump,
  `migrate_v1_to_v2`, etc.) before the app touches it — never a
  silent reinterpretation of old keys under new meanings.
- **Migration strategy.** Migrations are additive and one-directional
  — forward only. A migration never deletes a user's data, only
  reshapes it; a field being removed is deprecated (kept, ignored) for
  one full milestone before actual removal, mirroring the
  backward-compatibility policy in `MASTER_ROADMAP.md` §4.
- **Defaults.** Every setting has a default declared in its
  `settings_schema` (§10) — a module never assumes an unset value
  means "disabled" or "enabled" implicitly; the schema says so
  explicitly.
- **Import / Export.** Settings export as one JSON document (matching
  the module manifest's `settings_schema` shape), importable back
  in — validated against the current schema (running the migration
  chain if the imported file's `schema_version` is older) before
  being applied, never applied raw.
- **Backup.** Settings are included in M14A's Backup Platform export
  bundle unchanged from today's `.env`-adjacent scope — extended to
  cover the new per-module settings store as those modules ship.
- **Reset.** A "reset to defaults" action is per-module (reset just
  Gmail's settings) and global (reset everything) — both are
  explicit, confirmed user actions, never automatic.
- **Encryption.** Any setting value that is itself a secret (an API
  key typed into a settings field, not through OAuth) is encrypted at
  rest through the same Secrets Management system as every other
  credential (§17) — a settings value is never assumed safe to store
  in plaintext just because it arrived through a settings form instead
  of an OAuth flow.

---

## 12. Storage standards

| Data type | Where it lives | Notes |
|---|---|---|
| Structured, relational data | SQLite, via `IDatabase` | Conversations, messages, memories, tasks, automation history — see `MASTER_ROADMAP.md` §12 for the full table inventory. |
| Vector / semantic data | ChromaDB, via `IVectorStore` | Keyed by the same id as its SQLite row (existing `MemoryService` pattern, §1 of this document / `ARCHITECTURE_LEGACY.md` §5a) — never a vector entry with no relational counterpart. |
| Cache | In-process (per-service, e.g. an LRU dict) or a dedicated `cache` SQLite table for cross-restart caches | Never a source of truth — always safe to clear; a service that can't function after its cache is wiped has a bug, not a caching strategy. |
| Temporary | OS temp dir (`tempfile`), never `data/` | Screenshot capture buffers, download-in-progress files — cleaned on every startup, not just on success. |
| Persistent, non-secret | `<data_dir>/` subdirectories, one per concern (`logs/`, `vectorstore/`, `backups/`) | Matches the existing `data_dir` convention exactly. |
| Encrypted / Secrets | OS keyring (target — see §17), `.env` (current, being migrated per `MASTER_ROADMAP.md` §15) | Never plaintext in SQLite, never plaintext in a settings JSON export. |
| Cloud sync | Oracle Cloud, outbound-only, end-to-end encrypted before leaving the device | Local SQLite/Chroma remain the source of truth; cloud is a sync target, never a required dependency for local operation (§1). |

**Rule: every new data type gets a row in this table before its first
migration ships.** A PR introducing a new kind of persisted data
without an entry here is incomplete, the same way it would be
incomplete without a test.

---

## 13. Developer standards

### Folder structure

See `TECH_STACK.md` §7 for the full frontend/backend tree. Summary
rule: the React `frontend/src/features/<name>/` folders mirror the
Python `backend/src/jarvis/features/<name>/` slices **by name only**
— communication is exclusively through the REST/WebSocket contract
(§5, §6), never a direct import across the language boundary (there
isn't one to make).

### Naming

- Python: `snake_case` modules/functions, `PascalCase` classes,
  `SCREAMING_SNAKE_CASE` constants — unchanged from the existing
  codebase convention.
- TypeScript/React: `camelCase` functions/variables, `PascalCase`
  components/types, `SCREAMING_SNAKE_CASE` constants.
- Events: `<Noun><PastTenseVerb>Event` (§7). WebSocket messages:
  `<category>.<event>` (§6). API routes: plural nouns (§5).

### React rules

- Function components + hooks only (no class components).
- One component per file; a component's own single-use hook is
  colocated, a shared hook lives in `hooks/`.
- No inline styles — Tailwind utilities only.
- Every backend-sourced value flows through a TanStack Query hook
  (§8's services are the ultimate source; nothing is fetched with a
  raw `fetch()` inside a component).
- See `TECH_STACK.md` §8 for the full list (this section does not
  duplicate it).

### Python rules

- Clean Architecture layering (§1) enforced by convention today,
  targeted for a lint rule before M9's plugin surface makes violating
  it externally visible (`MASTER_ROADMAP.md` §15's existing Pending
  item).
- Every new adapter/service registers in `core/di/container.py` — no
  service imports a concrete adapter class directly, only its port.
- Type hints everywhere; `mypy --strict` on `src/`.

### FastAPI rules

- Routers are thin (§5) — one router per feature slice, matching
  `features/<name>/`.
- Every route has a Pydantic request/response model — no route
  returns a raw dict.
- Auth is a FastAPI dependency (`Depends(...)`), never hand-rolled
  per-route.

### Testing rules

See §18 — this section does not duplicate the full standard, only the
rule that every PR includes tests for the layer it touches, per §2's
"tests at the layer they were built" principle.

### Documentation rules

- A new module ships with its manifest (§10) — that manifest **is**
  its baseline documentation (permissions, commands, dependencies).
- Documentation updates ship with the code, not after — the existing
  `MASTER_ROADMAP.md` §4 rule, unchanged, extended to this document
  and `TECH_STACK.md`.

### Logging rules

- loguru + structlog, unchanged from `ARCHITECTURE_LEGACY.md` §1's
  `core.logging` package.
- Every log line at `warning` or above corresponds to an `ErrorPayload`
  `log_level` (§9) — logging and the error format are not two
  disconnected systems.

### Dependency rules

- `infrastructure` is the only place a third-party SDK is imported —
  unchanged from `ARCHITECTURE_LEGACY.md` §2's dependency rule, now
  also true of the frontend: `lib/` is the only place `fetch`/
  `WebSocket` primitives are touched directly (everything else uses
  the typed clients built on top, per `TECH_STACK.md` §2's state
  boundary rule).

---

## 14. UI standards

**Standards only — no redesign.** This section defines *rules*, not
new visuals; the actual design language is whatever M8's React build
implements against the design tokens already established.

| Concern | Standard |
|---|---|
| Typography | The existing `Typography` scale (`ui/themes/typography.py`): 32/24/20/18/16/14/12px, weights 400/500/600/700 only — ported into Tailwind config (`IMPLEMENTATION_ROADMAP.md` Phase 1), not redefined. |
| Spacing | 4px base unit, scale of 4/8/12/16/24/32/48/64px — no arbitrary spacing values in component code. |
| Cards | One `Card` primitive (shadcn/ui-based), consistent padding/radius/shadow across every workspace — no per-feature card reinvention, matching the existing `ui/components/card.py` pattern's intent. |
| Buttons | One `Button` primitive with a fixed variant set (primary/secondary/ghost/destructive) and fixed size set (sm/md/lg) — no ad-hoc button styling. |
| Animations | Motion (§`TECH_STACK.md` §2) for all transitions; durations below. |
| Icons | Lucide only, through the ported `IconRegistry` pattern — no emoji, no mixed icon sets (unchanged rule from the §7 UI Foundation pass). |
| Colors | Semantic tokens (`background`, `foreground`, `accent`, `destructive`, ...) mapped per-theme (dark/light/jarvis) — components never reference a raw hex value. |
| Breakpoints | `sm` 640px / `md` 768px / `lg` 1024px / `xl` 1280px / `2xl` 1536px — Tailwind's own defaults, not overridden without a documented reason. |
| Responsive rules | Desktop-first (JARVIS's primary target), but every view degrades gracefully down to `md` — nothing below `md` is a supported layout target for v1. |
| Motion durations | `fast` 100ms (hover/press feedback), `base` 200ms (most transitions), `slow` 350ms (panel open/close, page transitions) — three tiers only, no per-component bespoke duration. |
| Window behavior | Native Tauri window chrome; remembers size/position per-monitor across restarts (state stored per §12's "persistent, non-secret" row). |
| Dock behavior | Pinned items persist across restarts; unpin/repin is instant, no confirmation dialog (low-risk, reversible action). |
| Sidebar behavior | Collapsible, state persists across restarts; exactly one nav item active at a time — unchanged UX contract from the shipped PySide6 sidebar (`ui/widgets/sidebar.py`), just re-rendered in React. |
| Status bar behavior | Left/center/right, sorted by ascending `priority` within each — no hardcoded item order. A module that has no real backing data for an item shows an honest "Not configured"/idle state, never a fabricated value (added Aug 2026, M8 Phase 3 Task Group E). |
| Dashboard widget grid behavior | Registry- and enablement-driven, no hardcoded widget list; per-widget size/order/pin/visibility is a separate user-preference store from the registry describing what widgets exist (same split as Dock behavior above). Resize cycles 4 fixed grid footprints (1×1, 2×1, 1×2, 2×2), not free-form drag-resize. A widget with no real backing feature is not registered at all, never shipped as an empty shell (added Aug 2026, M8 Phase 3 Task Group F). |
| Command Palette behavior | `Ctrl+K` and `Ctrl+Shift+P` both open it — the header's Search button has always visually promised "Ctrl+K", the roadmap's canonical binding is "Ctrl+Shift+P"; both are honored rather than picking one. "Navigate" entries come from the same `ApplicationRegistry`/`ModuleEnablementStore` data Sidebar/Dock read; "Commands" entries come from the existing `NavigationContribution.commandPaletteEntries` mechanism (M8 Phase 2), not a new registry (added Aug 2026, M8 Phase 3 Task Group G). |
| Voice String behavior | No Orb, no visible state label ("Listening...") — a glassmorphism panel of 40 independently-animated bars (`VoiceWaveformRenderer`, pure/no store dependency) whose color/amplitude/envelope-shape communicate Idle/Wake/Listening/Thinking/Speaking/Success/Error, backed by a real validated state machine (`core/voice-state-machine.ts`) that starts and stays idle, and real (always-0-until-real) `microphoneLevel`/`ttsLevel` fields (`stores/voice-audio-levels.store.ts`) the renderer accepts as props so a future audio pipeline needs zero renderer changes. Respects `useReducedMotion()` directly (freezes rather than animates), since the wave is a continuous `useTime()` loop, not a discrete transition `MotionConfig`'s app-wide setting already covers (added Aug 2026, M8 Phase 4 Task Group H; revised same month to this multi-bar renderer). |
| Startup sequence behavior | A choreographed ~4.2s sequence (energy point, ripple, logo assemble/pulse, morph into the existing Voice String, Voice String activation/expansion, center-outward `mask-image` glass reveal) reuses the real `VoiceString`/`VoiceWaveformRenderer` and drives the real `voice-state.store.ts` (`wake` then `idle`) — never a second, decorative animation path. No startup text ever renders; only an `sr-only role="status"` string for assistive tech. The real app is revealed only once both the choreography *and* `core/startup-orchestrator.ts`'s real registration work (Status Bar, Dashboard widgets, Modules) finish — genuine synchronization, not a cosmetic delay. A persisted `skipStartupAnimation` preference and `useReducedMotion()` each independently skip straight to the dashboard. `runStartupSequence()` is idempotent (a cached promise) since React `<StrictMode>` double-invokes the initializing effect in development and real registration must run exactly once (added Aug 2026, M8 Phase 4 Task Group I). |

**UI extension points are registry-driven, not per-surface bespoke
code** *(added Aug 2026, UI Architecture Update)*: Sidebar, Dashboard
Widgets, and the Status Bar all read from a named instance of the same
generic `ContributionRegistry` (`frontend/src/core/contribution-registry.ts`)
rather than each shell component maintaining its own hardcoded list or
its own registration mechanism. A module contributes to any of these
surfaces the same way regardless of which one — register, unregister,
query by owning module — full detail in `MASTER_ROADMAP.md` §8 M9's
Plugin Registration System subsection, which also tracks which surfaces
are real today versus still pending the Plugin Loader. As of Task
Group F, all three surfaces have a real rendering consumer (Sidebar,
the Dashboard Widget Grid, and the Status Bar itself) — none is
registry-only scaffolding anymore.

---

## 15. AI standards

Formalizes M10 (AI Orchestrator)'s already-designed pipeline
(`MASTER_ROADMAP.md` §8) as the binding standard every AI-driven
feature routes through — no feature builds its own agent loop.

| Stage | Standard |
|---|---|
| **Intent** | Every user request is classified into an intent before planning starts (M10's Intent Engine) — a feature never skips straight to tool execution on raw text. |
| **Planning** | Multi-step plans extend M5A's `planner` node (M10's Planning) — a plan is data (a sequence of tool calls with dependencies), inspectable in Developer Mode's Agent Trace, never an opaque prompt chain. |
| **Reasoning** | Reasoning happens inside the LLM call the Planning/Tool Selection stages make — this standard does not prescribe a specific reasoning technique (chain-of-thought, ReAct, etc.), only that reasoning is never hidden from Agent Trace. |
| **Memory** | Every AI feature reads context through M10A's Universal Search & Knowledge Platform / M3 Memory — never a feature-local, undocumented memory store. |
| **Permissions** | Every tool invocation passes through Permission Validation (M10, routed to M14's Authorization Engine once it ships) before executing — no exceptions, matching M10's own Acceptance Criterion 3. |
| **Execution** | Tool execution extends M5A's `tool_executor` node (M10's Execution) — every tool call is logged to Agent Trace, success or failure. |
| **Verification** | Extends M5A's `critic` node (M10's Verification) — an AI action is not considered complete until verified, not just "the LLM said so." |
| **Feedback** | Closes through M16's Reflection Engine (Workflow Reflection, Behaviour Reflection) — feedback is a read from Reflection's existing analysis, not a second, competing feedback loop (per M10's own Learning/Feedback item). |
| **Learning** | Backed by M10B's Intelligence Layer (Routine Learning, Preference Learning) — an AI feature that wants to "learn" from usage reads/writes through M10B, never invents its own learning mechanism. |

**Prompt-injection standard (already shipped, extended):** every tool
whose output includes untrusted external content (web pages, OCR'd
documents, emails) fences it with the existing
`UNTRUSTED_TOOL_OUTPUT_NOTICE` pattern (`agents/prompting.py`,
`MASTER_ROADMAP.md` §7) — this is not new guidance, it is the binding
rule for every future tool, restated here so it lives in the
architecture standard, not only in §7's prose.

---

## 16. Automation standards

Formalizes the existing M4/M7 automation engine
(`ActionExecutor`/`Step`/`ExecutionPlan`) as the standard every
automatable action follows.

| Concern | Standard |
|---|---|
| **Workflow** | A `WorkflowDefinition`/`WorkflowStep` (M7 Phase 1, shipped) sequence — declarative data, never imperative code a user can't inspect. |
| **Nodes** | Each step is either an `AUTOMATION` action (existing `ActionType` catalog) or an `AGENT_TOOL` invocation (M10A/M10's tool registry) — `WorkflowStepKind`'s existing discriminated-union shape, unchanged. |
| **Execution** | Wave-based, dependency-aware parallel dispatch — the shipped M7 Phase 2 `ActionExecutor.run_plan()` behavior, using `Step.depends_on` and `gather_with_concurrency()`, capped by `AutomationSettings.max_parallel_steps`. |
| **Rollback** | `FAILED` triggers rollback in deterministic (reverse-completion) order; `DENIED` does not (existing, deliberate asymmetry — see M7 Phase 2's own report) — every future action type preserves this distinction, it is not accidental. |
| **Recovery** | A step that fails mid-workflow leaves already-completed, non-rolled-back steps' side effects in place — recovery is "resume from the failed step after a fix," never a full workflow re-run by default. |
| **Permissions** | Every action passes through `PermissionGate` — serialized (no concurrent confirmation dialogs), unchanged from the shipped M7 Phase 2 guarantee, and now also the single point M10's AI-driven Permission Validation routes through for automation-typed tool calls. |
| **Scheduling** | M7 Phase 6's Scheduler (cron-style) is the only path a workflow runs unattended — no feature builds its own timer/cron loop. |
| **Dependencies** | `Step.depends_on` is the only dependency mechanism — a step never encodes an implicit ordering assumption outside this field. |

---

## 17. Security standards

Formalizes M14 (Security Platform)'s already-designed scope
(`MASTER_ROADMAP.md` §8) as the binding standard — this section does
not restate M14's full 12-module detail, only the rules every other
module must follow now, ahead of M14 actually being built.

| Concern | Standard |
|---|---|
| **OAuth** | One authorization-code implementation (M11's Integrations & Cloud Platform), reused by every OAuth-backed integration — never reimplemented per provider. |
| **Secrets** | Every secret (API key, OAuth token, refresh token) resolves through Secrets Management (M14) — no `.env` plaintext, no hardcoded credential, no unencrypted token file, anywhere. |
| **Tokens** | Session tokens (§5's Bearer auth) are short-lived and refreshable; OAuth tokens follow Automatic Token Refresh + Least Privilege Permissions (M14's existing standard, requesting only the scope a feature actually needs). |
| **Encryption** | At rest (SQLite, via a provider-independent `core.interfaces` Protocol — SQLCipher is the first adapter, not the only one the architecture allows) and in transit (TLS for every external call, WSS for the WebSocket connection). |
| **Permissions** | One Authorization Engine (M14's Security Core) — plugin permissions (M9), automation risk levels (M4), desktop-control permission levels (M13), and AI tool permissions (§15) all resolve through it, never four separate ad-hoc mechanisms. |
| **Developer Mode** | Gated by the existing PBKDF2-HMAC-SHA256 password check (shipped M5), extended by M14's Authentication Framework (MFA, biometric, Windows Hello) as an additive option, never a replacement that weakens the existing gate. |
| **Audit logs** | Every permission grant/denial, secret access, and security-relevant action is append-only, tamper-evident (hash chain, M14's existing Audit Trail design) — logged once, in one place, not per-module. |
| **Privacy** | Local-first by default; PII redaction before embedding (closing the gap flagged since M3); Export & Deletion is one action each, covering every subsystem's data, not a per-module manual process. |

---

## 18. Testing standards

| Layer | Tool | Standard |
|---|---|---|
| Frontend unit | Vitest | Every hook and pure function; co-located `*.test.ts(x)` files. |
| Frontend component | React Testing Library | Query by role/text (behavior), never by implementation detail (class names, internal state). |
| Backend unit | pytest | Every service method, with fakes for adapters (`tests/fakes/`, existing pattern) — never a real network/LLM call in a unit test. |
| API | pytest + `httpx.AsyncClient` / FastAPI `TestClient` | Every route's success path, validation-failure path (§5), and auth-failure path. |
| Integration | pytest | Real SQLite, real ChromaDB, mocked network — existing `tests/integration` pattern, unchanged. |
| Automation | pytest | Every `ActionType` and workflow shape gets a golden-file or fixture-driven test — existing M4/M7 pattern. |
| End-to-end | Playwright | Full user flows through the Tauri-hosted app — one flow per major feature, not exhaustive per-screen coverage. |
| Performance | pytest-benchmark (backend) / Playwright trace (frontend) | Regression-gated against the budgets in §19, not just "did it run." |
| Accessibility | axe-core (via Playwright) | Every new screen gets an automated a11y pass; carries forward the M5.5 focus-indicator fix's standard. |
| Regression | Full suite, every PR | Zero pre-existing-failure tolerance — a red CI run is always a real regression, per the existing `.github/workflows/ci.yml` hard-gate design. |

**Rule (§2 restated):** tests are written at the layer they were
built, in the same PR — a UI PR with no corresponding service test
because "the service already has tests" is fine; a service PR with no
tests because "the UI will catch it" is not.

---

## 19. Performance standards

Concrete budgets, not aspirations — a PR that regresses one of these
without an explicit, reviewed justification is blocked, mirroring the
existing "keep the test count monotonic" discipline in
`MASTER_ROADMAP.md` §4 applied to performance instead of coverage.

| Metric | Budget | Measured by |
|---|---|---|
| Cold startup time | < 3s to interactive (React UI rendered, WebSocket connected) | Playwright trace, M8 Phase 7 |
| Warm startup time | < 1s | Same |
| Idle memory usage | < 400MB (Tauri + backend process combined) | Manual profiling, checked per milestone that adds a persistent background service |
| Idle CPU usage | < 1% | Same |
| Animation frame rate | 60fps sustained during any Motion transition | Playwright trace / browser devtools |
| REST API latency (p95) | < 200ms for any non-streaming route | pytest-benchmark against a local FastAPI instance |
| WebSocket message latency | < 50ms server-publish to client-receive, same machine | Integration test with a timestamp round-trip |
| Frontend bundle size | < 5MB gzipped, initial load | Vite build report, checked every M8 phase |
| SQLite database size | No hard cap — growth rate tracked; `enforce_policies()`'s archive/delete split (existing M3.1 behavior) is the mitigation, not a size limit |

Every budget above is a **starting target**, set before real-world
usage data exists — §20 governs how these numbers get revised once M8
ships and real measurements replace estimates.

---

## 20. Governance — how this document changes

- This document is updated in the same change that introduces a new
  standard, not after — mirroring `MASTER_ROADMAP.md` §4's
  documentation-discipline rule.
- A new module type that doesn't fit an existing standard (a new state
  set, a new manifest field, a new event category) gets that gap
  filled here **before** the module ships, not retrofitted once a
  reviewer notices the gap — matching §4's "no module may invent
  custom lifecycle states without documentation" rule, generalized to
  every standard in this document.
- Sections marked **(new, M8+)** are removed once the corresponding
  code ships and the standard is verified against real behavior — at
  that point the section reads as shipped fact, the same way §4 (State
  Machine Standard) already does today for `domain/app_state/`.
- Conflicts between this document and `ARCHITECTURE_LEGACY.md`: the
  legacy document is never wrong about what M0–M7 actually shipped; it
  is simply no longer the standard for what ships next. Nothing in
  this document retroactively changes what `ARCHITECTURE_LEGACY.md`
  records.
