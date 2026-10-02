# M8 Frontend Real-Backend Integration — Logic Contract

Status: **planning-only, Phase 1**. No implementation exists yet. This document defines how
`Jarvis-Frontend-main` — now the single canonical frontend for AARYA, on the reconciled branch
`feature/production-integration` — converts from a mock/scaffold frontend into one that talks to
the real JARVIS Core backend (`2.0-main`). Every architectural claim below was freshly verified
against real source during Phase 1, in both repositories, not carried forward unchecked from any
earlier audit. `2.0-main/frontend/` remains frozen, untouched, and not deleted.

> MOCK FRONTEND → REAL AUTH → REAL REST → REAL WEBSOCKET → REAL CORE BACKEND → REAL PRODUCTION DATA

The central finding this contract is built on: **`Jarvis-Frontend-main` already has the right
shape for this transition.** Every feature already sits behind a `get<Feature>Service()` seam with
a `mock<Feature>Adapter.ts` (`ready: true`) and a `core<Feature>Adapter.ts` (`ready: false`, stub)
implementing one shared TypeScript interface, consumed generically by `useAsync` +
`StateView`/`Message`. **The objective of Phase 2 is therefore almost entirely "implement the
stub adapters and the shared infrastructure they call into" — not "rebuild the UI."** For five of
six in-scope features, zero UI component changes are required at all.

## 1. Current canonical frontend — freshly verified

**Root correction, load-bearing for every file path below**: the git root is
`Jarvis-Frontend-main/`, not `Jarvis-Frontend-main/frontend/` — the app lives in the `frontend/`
subdirectory, but `docs/CORE_*_CONTRACT_REQUIRED.md` and the other planning docs live at the repo
root's own `docs/`, one level above `frontend/docs` (which doesn't exist). Any reference to
`docs/CORE_X_CONTRACT_REQUIRED.md` elsewhere in this contract is repo-root-relative.

**Entry point / routing**: standard Vite/React Router setup; `App.tsx` renders top-bar
`Home/Chat/Voice/Automations` primary routes plus ~20 lazy-loaded secondary routes, each
registered in `app/modules.tsx`'s flat `modules: ModuleDef[]` array (`surface: 'topbar' |
'secondary' | 'settings' | 'developer'`, `audience`, `status: 'live' | 'planned'`).

**Module/feature architecture**: one directory per feature under `src/features/`, each owning its
own `<feature>Service.ts` (interface + `get<Feature>Service()` selector), `adapters/{mock,core}
<Feature>Adapter.ts`, and page/component files. No shared registry beyond the flat `modules`
array — there is no `ApplicationRegistry`/`ModuleManifest`/panel-registry concept here (that
architecture belongs to `2.0-main/frontend/`, a different codebase entirely; do not port it).

**API/service architecture, state management, data layer** — freshly confirmed, not assumed: the
existing, exclusively-used pattern is `useAsync` (`src/design-system/hooks/useAsync.ts`, a generic
`idle → loading → ready | empty | error` hook with built-in `AbortController` cancellation)
composed with `StateView` (`src/design-system/composites/StateView/StateView.tsx`, the one
renderer for every surface's loading/empty/error/unavailable state, driven off `UIStatus`). Every
existing feature page already calls `useAsync<T>((signal) => service.getX(signal))` and passes the
result straight to `StateView`. **This is the data layer Phase 2 must keep using — do not
introduce TanStack Query hooks merely because a future decision might add the dependency; nothing
in this repo uses it today, and nothing needs to.**

**Adapter pattern** (confirmed 100% consistent across all ~22 feature seams, two named exceptions
below): `mock*Adapter.ts` → `id: 'mock'` (or `'dev'`/`'local'` for Chat/Voice specifically),
`ready: true`, real in-memory/localStorage behavior with simulated latency. `core*Adapter.ts` →
`id: 'core'`, `ready: false`, every method throws/rejects a `Core<Feature>ContractUnavailableError`
via a shared `unavailable()` helper — **except `coreChatAdapter.ts`**, which per `ChatService`'s
own "must never throw" interface contract instead *resolves* with `{ outcome: 'error' }` and an
`onError` callback. Selection is `import.meta.env.VITE_<FEATURE>_BACKEND` (default `'mock'`/`'dev'`
/`'local'`), read once per module load. Full current variable list, verified fresh (22 distinct
vars — this table does not exist anywhere in the repo today and is a real Phase 2 deliverable,
§4.1):

| Feature | Env var | Default |
|---|---|---|
| Workflow Builder | `VITE_WORKFLOW_BUILDER_BACKEND` | `mock` |
| Recorder | `VITE_RECORDER_BACKEND` | `mock` |
| Home Automation | `VITE_HOME_AUTOMATION_BACKEND` | `mock` |
| Automations | `VITE_AUTOMATIONS_BACKEND` | `mock` |
| Smart Home | `VITE_SMART_HOME_BACKEND` | `mock` |
| Home Assistant (Smart Home sub-connector) | `VITE_HOME_ASSISTANT_BACKEND` | `mock` |
| MQTT (Smart Home sub-connector) | `VITE_MQTT_BACKEND` | `mock` |
| Chat | `VITE_CHAT_BACKEND` | `dev` |
| Voice | `VITE_VOICE_BACKEND` | `local` |
| Settings | `VITE_SETTINGS_BACKEND` | `mock` |
| Home/Dashboard | `VITE_HOME_BACKEND` | `mock` |
| *(13 more — Agents, AI Apps, Calendar, Diagnostics, Files, Intelligence, Knowledge, Memory, Notes, Search, Tasks — same pattern, out of this contract's six-feature scope)* | | |

**Current auth assumptions**: none. Zero `Authorization`/`Bearer` header anywhere in `src/`, no
`/api/v1/sessions` call, no session concept at all.

**Current WebSocket assumptions**: none. No WebSocket client exists; no `event-contract.
generated.json`.

**Test architecture**: Vitest + React Testing Library, one `__tests__/` directory per feature,
`MemoryRouter` + `ToastProvider`/`TooltipProvider` wrapping, mock-adapter-driven integration-style
tests plus fake-service-driven state tests (`*PageStates.test.tsx`) using `vi.mock`.

**Build architecture**: `tsc -b && vite build`; `vite.config.ts` has **no `envPrefix` and no
`define` block** — only `VITE_`-prefixed vars are ever exposed to client code (confirmed: this
makes `chatClient.ts`'s `REACT_APP_BACKEND_URL` fallback dead code under the current config — a
Create-React-App-era name that Vite never populates).

**Environment/configuration**: **no `.env` or `.env.example` file exists anywhere in this repo
today** (both `.gitignore`s provision for one, neither is checked in). `VITE_BACKEND_URL` is the
one cross-feature variable (read by `chatClient.ts`); every other variable is the per-feature
`VITE_<FEATURE>_BACKEND` selector above.

## 2. Existing features — inventory and integration readiness

| Feature | UI completeness | Mock adapter | Backend match | Test coverage | Integration readiness |
|---|---|---|---|---|---|
| Workflow Builder | Complete (list/create/edit/run/history) | Full, stateful | Exact — `/api/v1/workflows`, 7 routes | Full suite | Ready |
| Recorder | Complete (start/stop/cancel/preview/history) | Full, stateful | Exact — `/api/v1/recordings`, 5 routes | Full suite (known timing flakiness, §8/§19) | Ready |
| Home Automation | Complete (list/create/enable/disable/run/delete/history, no edit) | Full, stateful | Close but one field gap (§6.3) | Full suite | Ready, with a small adapter-level transformation |
| Smart Home | Complete (3 sub-services: core registry + Home Assistant + MQTT) | Full, stateful | Exact — `/api/v1/{homes,zones,rooms,devices,device-groups}`, `/api/v1/connectivity/*` | Full suite | Ready |
| Automations | Complete (rich CRUD, conditions, typed actions) | Full, stateful | **None** — no backend service models this shape (§5.6) | Full suite | **Not integrable as designed — stays mock, explicitly** |
| Chat | Complete (real SSE against a local dev scaffold) | Real dev-backend I/O (not mock data) | Real, but a different endpoint/shape than assumed (§5.7) | Present | Ready, adapter rewrite required |
| Settings | Minimal (2 real fields; everything else is pass-through to other features) | `localStorage`-backed, genuinely persists | **Real backend exists** — correction to this repo's own docs, §5.8 | Present | Ready, small scope |
| Dashboard/Home | Complete (one aggregated `HomeSnapshot`) | Static, hand-authored | Partial — composable from other already-verified real endpoints, no single matching endpoint | Present | Partial only (§5.9) |

Two findings worth flagging on their own, found in passing, **neither requires Phase 2 action**:
`features/home/HomeWidgets.tsx` (151 lines) is dead code — zero importers anywhere, superseded by
`HomeSections.tsx`, which correctly consumes the real `homeService.ts` seam. And unlike every
sibling feature, `homeService.ts`'s own module doc does not cite a specific
`CORE_HOME_CONTRACT_REQUIRED.md` — no such document exists in this repo, an asymmetry inherited
from this repo's own prior process, not something this contract needs to fix.

## 3. Real Core authentication

Freshly verified against the real backend (confirmed via `2.0-main/frontend`'s own already-proven
`services/api/session.ts`, which describes the backend's actual session API — this is backend
behavior, unaffected by which frontend consumes it):

- `POST /api/v1/sessions` (anonymous, no prior auth needed) → `SessionInfo` including `session_id`.
- Every other resource route requires `Authorization: Bearer <session_id>`, enforced by
  `Depends(get_current_session)`.
- The identical `session_id` is reused as the WebSocket connection's `?token=<session_id>` query
  parameter — one credential, two transports.
- No refresh-token concept exists; a session is checked for liveness by `GET /api/v1/sessions/{id}`
  and a fresh `POST /api/v1/sessions` is issued on any failure (including a backend restart, whose
  session table does not survive it).
- **The token must never be persisted to `localStorage`** — a restarted backend's session table is
  empty, so a persisted token would be stale more often than useful; re-establish once per page
  load instead.

**Phase 2 architecture** (new file, e.g. `src/lib/session.ts`): `createSession()`, `ensureSession()`
(reuse-or-recreate), `endSession()`, an in-memory current-session variable, and a `setAuthToken()`
hook feeding the canonical REST client (§4) and the future WebSocket client (§12). Invoked once at
app startup (a new bootstrap step, analogous to but independent of `runStartupSequence()`-style
orchestration if one exists here — confirm exact startup hook location during Phase 2, not
assumed here) and again on every reconnect. **Unauthorized (401) response**: re-run `ensureSession()`
and retry the failed call once; a second 401 surfaces as a genuine error, never a silent loop.
**Logout**: `endSession()` (`DELETE /api/v1/sessions/{id}`) — no product surface currently needs
this (no login screen exists or is being added), but the primitive is included in the shared
session module `2.0-main/frontend` proved out, and required by good practice, not because a
Logout button ships in Phase 2. **Protected routes**: none — the whole app is unauthenticated
until Phase 2, and after Phase 2 the entire app still has no user-facing login; the session
establishes automatically and transparently, matching how `2.0-main/frontend` itself has no login
UI either.

**No second auth mechanism** — `core/permission-framework.ts`-equivalent client-side-only
constructs do not exist in this repo and are not introduced here; backend authorization (§15)
remains the sole source of truth.

## 4. Real REST client

One new canonical client, e.g. `src/lib/apiClient.ts`, modeled directly on `2.0-main/frontend`'s
own already-proven `services/api/client.ts` (the same backend, so the same shape is the correct
one to reuse conceptually — not copy verbatim, since this repo's TypeScript conventions differ):

- Base URL: `import.meta.env.VITE_BACKEND_URL` (already the one cross-feature var `chatClient.ts`
  reads — every feature's real adapter reuses this same variable, not a new one per feature).
- `Authorization: Bearer <token>` attached automatically from the session module (§3), on every
  call except session bootstrap itself.
- Response unwrapping: every resource route's real shape is `{data: T, meta: {...}}` — the client
  unwraps `.data`, exposes `.meta` alongside where a caller needs pagination/count info.
- Error normalization (§14): non-2xx responses produce one typed error shape carrying `status`,
  the backend's own `detail` message string verbatim, and a `retryable` hint (5xx/429 only).
- Timeout: a sane client-side timeout (e.g. 30s) distinct from the backend's own request handling
  — necessary because nothing today defends against a hung connection.
- Cancellation: every existing service method already accepts an optional `AbortSignal` (the
  `useAsync` convention) — the REST client accepts and forwards it to `fetch`'s own `signal` option,
  no new cancellation mechanism invented.
- Retry policy: **none automatic** beyond the single 401-triggered re-auth-and-retry in §3 — this
  matches `2.0-main/frontend`'s own proven, deliberately conservative choice; blind retries on a
  mutating POST (create/run/command) risk duplicate side effects the backend has no idempotency key
  to protect against.

**Hard rule, per instruction**: no feature module may call raw `fetch()` against the Core backend
directly. The one narrow exception is Chat's SSE stream (§17) — a streaming response cannot be
unwrapped through a JSON-envelope client — which gets its own thin, dedicated stream-reading
function, following the exact parsing-loop shape `chatClient.ts` already implements for the dev
scaffold, redirected at the real endpoint.

## 5. API contract mapping — freshly verified, all six areas

### 5.1 Workflow Builder
`POST/GET /api/v1/workflows`, `GET/PATCH/DELETE /api/v1/workflows/{id}`, `POST /api/v1/workflows/
{id}/run`, `GET /api/v1/workflows/{id}/executions`. Permission scope `workflow_builder`, denial is
**HTTP 400** (not 403), message contains "permission". Workflow payload: `{id, name, description,
steps, created_at}`. Step: `{id, kind: "automation" | "agent_tool", instruction, tool_name,
tool_args, depends_on, label}`. `PATCH` genuinely partial — omitted fields untouched.

### 5.2 Recorder
`POST /api/v1/recordings/start`, `POST /api/v1/recordings/{id}/stop` (`{name, description?}`),
`POST /api/v1/recordings/{id}/cancel`, `GET /api/v1/recordings`, `GET /api/v1/recordings/{id}`.
Two independently-checked scopes: `recorder` (lifecycle) and, only inside `stop`'s delegation,
`workflow_builder` (freshly re-checked, never cached — holding `recorder` alone is insufficient).
Both denials 400. Session payload: `{id, status, started_at, stopped_at, resulting_workflow_id}`;
`stop`'s success response adds the full `resulting_workflow`. A "nothing captured" 400 leaves the
session `"recording"`, not finalized.

### 5.3 Home Automation
`POST/GET /api/v1/home-automation`, `GET/POST(enable)/POST(disable)/DELETE /api/v1/home-automation/
{id}`, `POST /api/v1/home-automation/{id}/run`, `GET /api/v1/home-automation/{id}/executions`. No
`PATCH` — editing means delete + recreate. Scope `home_automation`, denial 400. Trigger payload:
`{id, workflow_id, name, device_id, from_status, to_status, enabled, created_at, updated_at,
last_fired_at}` — **note what's absent: no `instruction` field**. See §6.3 for the frontend
consequence.

### 5.4 Smart Home
`POST/GET /api/v1/homes`, `GET/PATCH/DELETE /api/v1/homes/{id}`, `GET /api/v1/homes/{id}/metadata`;
identical CRUD shape for `/api/v1/smart-home/zones` and `/api/v1/smart-home/rooms`; `POST/GET
/api/v1/devices`, `GET/PATCH/DELETE /api/v1/devices/{id}`, `POST /api/v1/devices/{id}/pair`;
`/api/v1/smart-home/device-groups` CRUD + `/members`. **No `smart_home` permission scope at this
layer** — session-auth only. Device payload: `{id, home_id, room_id, name, device_type, status,
manufacturer, model, external_id, created_at, updated_at, last_seen_at}`. Status vocabulary:
`{discovered, pairing, paired, offline, unreachable, removed}` — `pairing`/`removed` validated but
never written by any shipped path. One known backend inconsistency to preserve, not paper over:
`POST /devices/{id}/pair` on an unknown id returns 400, not 404.

### 5.5 Connectivity
`GET /api/v1/connectivity/connectors`, `POST .../connect`, `POST .../disconnect`, `POST /api/v1/
connectivity/discover`, `POST /api/v1/connectivity/devices/{id}/refresh`, `POST /api/v1/
connectivity/devices/{id}/command`. No permission scope. Connector types: closed set
`{home_assistant, mqtt}`. No `"error"` status value exists in the connector lifecycle vocabulary —
a failed connect surfaces only via the synchronous 400. **No API lists valid commands per connector
type** — `command` is a fully generic, uninterpreted passthrough; do not build a command console
against this route, the frontend's existing Smart Home UI already covers device interaction at the
right level. Credentials are never returned in any response (verified: `ConnectorCredential.
to_public_dict()` never includes `secrets`).

### 5.6 Automations — no real backend match, confirmed both directions
The frontend's `Automation` type (`trigger: {type: 'schedule'|'event', schedule?, event?}`,
`conditions: AutomationCondition[]`, `actions: AutomationAction[]` with `type: 'notify'|'run-agent'
|'device'|'integration'`) is a general condition/action rules engine. **No backend service matches
this shape.** Confirmed by exhaustive route search: `AutomationService`/`ActionExecutor` (the M4/M5A
OS-automation engine this frontend feature might plausibly have meant) has **zero REST routes** —
it is reachable only as an agent tool (`run_automation`, natural-language instruction in, text out),
with no persisted, listable "Automation" entity; the one adjacent concept, `Recipe`, is file-backed,
trigger-less, and also has no REST route. Scheduler (`/api/v1/schedules`) and Home Automation
(`/api/v1/home-automation`) are real, tested, REST-reachable — but neither has conditions or typed
multi-kind actions; both are narrower than this feature's own model. **Do not force-fit this
feature onto either** — their trigger/action vocabularies don't match, and bending one to imitate
the other risks exactly the kind of "duplicate execution engine" mistake this project consistently
avoids. **Conclusion: Automations stays mock-only in Phase 2, explicitly and permanently, not as a
placeholder for later work** — this repo's own `docs/CORE_AUTOMATIONS_CONTRACT_REQUIRED.md` already
says as much ("no Core automation endpoint has been invented"); this contract confirms that
conclusion with fresh backend evidence rather than assumption.

### 5.7 Chat — real backend exists, but not at the assumed endpoint
**No REST route named anything like `/api/chat/stream` or `chat.py` exists in the backend at all.**
`ChatService.stream()` (the plain-LLM-passthrough path `CLAUDE.md` describes) is reached only
in-process by the PySide6 desktop shell's `ConversationController` — it has no HTTP surface. The
only REST-reachable conversational surface is the full tool-using agent:

- `POST /api/v1/agent/invoke` — plain REST, `{data: {text, thread_id, steps, metadata}}`.
- `POST /api/v1/agent/stream` — **real SSE** (`text/event-stream`), request body `{prompt: string,
  thread_id?: string}`. Response is a sequence of raw `data: <token-text>\n\n` frames — **not**
  JSON-wrapped, **not** the `{data,meta}` envelope (an explicitly documented exception) — terminated
  by `event: done\ndata: {}\n\n`.
- Both require the same Bearer session auth as every other route.
- No WebSocket chat path exists. `agent.step` is a real, relayed WS event (`AgentStepEvent`:
  `{thread_id, step, node, status, detail}`) but is a coarse node-transition trace only — raw
  response tokens are never relayed over WebSocket, only over the SSE response above.

**Consequence for the adapter**: real Chat integration means talking to `AgentOrchestrator`, not a
plain chat passthrough — a materially richer backend than the dev scaffold's simple echo-style
`/api/chat/stream`. The request shape also differs structurally: the real endpoint takes one
`prompt` string plus an optional `thread_id`, not a `messages[]` array — see §17 for the exact
adapter design this implies.

### 5.8 Settings — correction to this repo's own documentation
`docs/CORE_SETTINGS_CONTRACT_REQUIRED.md` states no Core settings contract exists anywhere — that
conclusion was reached by searching only this repo's own Core-alignment doc set, not the actual
backend source. **Fresh verification finds this is incomplete: a real, tested settings API exists**
— `2.0-main/frontend`'s own already-proven `settingsApi` (`GET /api/v1/settings`, `GET /api/v1/
settings/{dottedKey}`) is real, and `tests/integration/test_settings_api_e2e.py` exercises it
end-to-end (e.g. `{"key": "ui.theme", "value": "jarvis"}`). This is reported here explicitly per
the "do not silently reconcile conflicting evidence" instruction — the two real fields this
frontend's Settings feature manages (`notificationsEnabled`, `developerModeEnabled`) are plausible
candidates for real `dottedKey`s once Phase 2 confirms which keys the backend actually persists
for them (not assumed further here — a small, low-risk Phase 2 verification step, not a blocker).

### 5.9 Dashboard/Home — partial, composed integration only
`HomeSnapshot`'s eight fields (`presence, system, suggestions, tasks, events, automations, devices,
activity`) have no single matching backend endpoint — `2.0-main/frontend`'s own AI Dashboard proved
the real pattern is composing several already-verified typed calls (tasks, notes/calendar, smart
home devices, execution histories), not one aggregation route. Phase 2 should wire only the fields
with a genuine real source (`devices` from §5.4, `automations`/`activity` from §5.1/§5.3's
execution histories) and explicitly leave fields with no real backend equivalent (`presence`, and
any `suggestions` sourced from a capability not covered by this contract's six features) mock/
absent — never fabricated to fill the shape.

## 6. Adapter migration strategy

```
CURRENT:  UI → mock<Feature>Adapter → in-memory mock data
TARGET:   UI → core<Feature>Adapter → canonical REST/WS client (§4/§12) → Core backend
```

**Because every feature already sits behind this exact seam, the UI layer requires zero changes**
for Workflow Builder, Recorder, Home Automation, Smart Home, and Connectivity — `useAsync`/
`StateView` (§1) already consume the interface generically; implementing `core<Feature>Adapter.ts`
to satisfy the same interface and flipping the env var is the entire migration for those five.

### 6.1 Workflow Builder
Near-1:1 field mapping (§5.1 ↔ existing `Workflow`/`WorkflowStep` TS interfaces — already
confirmed identical in shape from this session's own earlier work building this exact feature).
No transformation needed beyond snake_case→camelCase at the client boundary.

### 6.2 Recorder
Same — near-1:1 (`id/status/startedAt/stoppedAt/resultingWorkflowId` ← `id/status/started_at/
stopped_at/resulting_workflow_id`). `resultingWorkflow` on stop success maps directly to the same
`Workflow` shape as §6.1.

### 6.3 Home Automation — the one real transformation required
The frontend's `HomeAutomation.instruction: string` (a direct field) has **no backend equivalent**
— the real trigger payload only carries `workflow_id` (§5.3); the instruction text lives inside
that referenced workflow's `steps[0].instruction`. Two options, evaluated:
- **(A) Fetch the linked workflow only in `getHomeAutomation(id)` (the detail view), not in
  `getHomeAutomations()` (the list)** — avoids an N+1 fetch storm on the list screen. **Chosen.**
- (B) Fetch the linked workflow for every row in the list too — rejected: no batch/join endpoint
  exists, and the list view does not currently need to *display* the instruction text per the
  existing `HomeAutomationCard.tsx`'s own summary fields (name/device/status), only the detail
  drawer does.
**Required UI adjustment**: none to the list card; the detail drawer's existing `instruction`
display continues to work once the adapter performs the one extra `GET /api/v1/workflows/
{workflow_id}` call inside `getHomeAutomation`. `createHomeAutomation` needs no such change — it
already sends the instruction forward as `steps: [{kind: "automation", instruction}]`, which the
real `POST /api/v1/home-automation` accepts directly.

### 6.4 Smart Home
Direct mapping across Homes/Zones/Rooms/Devices/DeviceGroups; the `pair`/`refresh`/`command`
mutations map to the corresponding real routes 1:1.

### 6.5 Connectivity
Direct mapping; `sendCommand`'s `success: false` response must be rendered as a real, non-optimistic
failure (§9 of the prior integration contract's UX discipline applies equally here — no state is
fabricated from a command acknowledgment).

### 6.6 Automations
No adapter work in Phase 2 — stays on `mockAutomationAdapter`, permanently, per §5.6. The
`coreAutomationAdapter.ts` stub remains exactly as-is; do not implement it against a service that
doesn't exist.

### 6.7 Chat
The one feature needing more than a field-mapping pass — see §17.

## 7. Workflow Builder integration
Real CRUD/edit(PATCH)/delete/run/history against `/api/v1/workflows` (§5.1), through the new
`coreWorkflowBuilderAdapter.ts` implementing the existing `WorkflowBuilderService` interface
unchanged. No new step kind invented (only `automation`/`agent_tool` exist). No `RecipeManager`
involvement — none exists in this feature's design already. No second execution engine — `run`
always means "call the real synchronous REST route and render its response," matching what the
UI already does against the mock. Permission denial (400, §5.1) renders via the existing error
path (§14) with the backend's own message shown verbatim, including its grant-instruction hint.

## 8. Recorder integration
Real start/stop(name-required)/cancel/history/generated-workflow-preview/run against `/api/v1/
recordings` (§5.2). The dual-scope permission stack (`recorder` + `workflow_builder`, checked
independently on `stop`) is preserved exactly — the adapter must not cache or infer the second
scope's grant state from the first. No raw keyboard/mouse/computer-use/agent-tool capture — none
of that exists in the real backend and none is added here. See §19 for the test-debt strategy;
not fixed in this phase.

## 9. Home Automation integration
Real list/create/enable/disable/run-now/delete/history against `/api/v1/home-automation` (§5.3),
with the one adapter-level transformation in §6.3. No edit route exists (backend precedent: delete
+ recreate) — the frontend already has no edit flow, so no UI change is implied. No presence/
camera/attribute-level/multi-device-condition triggers, no AI-generated automations, no Event
Viewer, no Smart Home Memory integration, no MQTT-native trigger UI — none of these exist in the
real backend and none is added here, matching the frontend's own pre-existing scope note verbatim.

## 10. Smart Home integration
Real home/room/zone/device data and lifecycle (§5.4) through the existing `SmartHomeService`
interface. Only backend-supported operations are exposed: pair, refresh, rename (PATCH),
remove (DELETE) — no brightness/on-off/thermostat-style controls at this layer (those belong to
already-separate, out-of-scope per-category routers this contract does not touch).

## 11. Connectivity integration
Real connector list/connect/disconnect/discover/command (§5.5) through
`smartHomeIntegrationService.ts`'s existing Home Assistant/MQTT adapters. Credential fields remain
write-only from the UI's perspective — never redisplayed after submission, matching the backend's
own redaction discipline (§5.5) and this repo's own existing "preserve current backend
credential-persistence semantics" instruction.

## 12. WebSocket client
One canonical client, new (e.g. `src/lib/websocket.ts`), connecting to `${WS_BASE}/api/v1/ws?
token=<session_id>` (base URL derived from `VITE_BACKEND_URL`, same as the REST client). Handles:
connect, the same Bearer-equivalent token auth as REST (§3), reconnect with backoff, disconnect,
session-expiry-triggered re-auth-and-reconnect (reuse §3's `ensureSession()`), event parsing (a
typed `{type, id, occurred_at, payload}` envelope), a `subscribe(eventType, handler)` API mirroring
`2.0-main/frontend`'s own proven `websocketManager.on<T>(type, handler)` shape, and cleanup on
unmount.

**Only real, relayed events are consumed**: `home.updated`, `device.updated`,
`connectivity.status_changed`. **`DeviceCommandExecutedEvent`/`DeviceStateChangedEvent` are
published internally but not relayed — no subscription for either is built.** Every Workflow
Builder/Recorder/Home Automation execution outcome already arrives synchronously in its own REST
response (§5.1–§5.3) — no WebSocket wiring is needed or added for any of those three. `home.
updated`/`device.updated` are used purely as **refetch signals** (call the existing `useAsync`
`refresh()`/reload the affected list) — never as a direct state overwrite, since neither event's
payload guarantees which field actually changed (confirmed: `device.updated` fires unconditionally
on every `report_device_state()` call, not only on a genuine transition).

## 13. Data refresh / cache strategy
No new data layer. `useAsync` + `StateView` (§1) stay exactly as they are; a WebSocket-triggered
refetch is just a call to the same `refresh()` function a manual retry button already calls.
Mutations (create/update/delete/run/pair/command/start/stop/cancel) are **never optimistic** —
every one waits for the real response before updating any list, matching how the mock adapters'
own simulated-latency behavior already trains the UI to behave. No rollback logic is needed as a
consequence — there is nothing to roll back.

## 14. Error model
One normalization point, inside the canonical REST client (§4): every non-2xx response produces
`{status, message: <backend's own detail string, shown verbatim>, retryable: status >= 500 ||
status === 429}`. **Explicit, evidence-based correction to the plausible default**: this backend's
own convention for Workflow Builder/Recorder/Home Automation/Smart Home Memory permission denials
is **HTTP 400**, not 403 — no code branch should assume every authorization failure is a 403, and
none is written to specifically detect 403 here since these six features' backends never send one.
409/422/429 are not currently produced by any of the six in-scope backend areas (confirmed absent
during fresh route verification) — the client handles them generically (as any other non-2xx) so a
future backend change wouldn't silently mis-render, without inventing bespoke UI for a status this
integration never actually receives today. WebSocket disconnect and session expiration both route
through the same reconnect/re-auth path (§3/§12), not a separate error surface. No internal stack
trace or raw exception text is ever rendered — only each layer's own already-human-written message
string.

## 15. Permissions

| Feature | Scope | Denial status |
|---|---|---|
| Smart Home core registry, Connectivity | *(none)* | — |
| Home Automation | `home_automation` | 400 |
| Workflow Builder | `workflow_builder` | 400 (also independently re-checked inside Recorder's `stop`) |
| Recorder | `recorder` (+ `workflow_builder` on `stop`) | 400 |
| Chat/agent | *(session auth only — no scope gate found on `/api/v1/agent/*`)* | 401 if unauthenticated |

Frontend visibility is never authorization — no button-hiding logic substitutes for a real
permission check; every mutating action still calls the real backend and renders whatever it
decides. No frontend-only bypass is introduced. Fail-safe behavior (deny by default) is preserved
by construction: nothing in this contract adds a client-side path that executes without going
through the real, authoritative backend call.

## 16. Real data only
After Phase 2, the five real-mapped features' production code paths (env var flipped to `core`)
never fall back to mock data on error — a failure renders the real error state (§14), not
synthesized content. Automations (§5.6) is the sole, explicitly-permanent exception, and it must
remain visibly labeled as such (its existing `service.label`/`ready` surfacing already does this —
no change needed). **Guard strategy**: a new, small test asserting `getWorkflowBuilderService()`/
`getRecorderService()`/`getHomeAutomationService()`/`getSmartHomeService()`/`getConnectivityService
equivalents resolve to the `core` adapter whenever the corresponding env var is set to `'core'` —
mirroring the exact assertion shape `workflowBuilderService.test.ts` already uses for "defaults to
mock," inverted for the production-build case.

## 17. Chat integration
`coreChatAdapter.ts`'s `sendMessage(turns, handlers, signal, sessionId?)` is implemented against
`POST /api/v1/agent/stream` (§5.7), not the assumed `/api/chat/stream` shape. Two real design
decisions this reconciliation requires, resolved here rather than left open:

- **Request shape**: the real endpoint takes one `prompt: string` + optional `thread_id`, not a
  `messages[]` array. The adapter sends only the latest user turn as `prompt`, and passes a
  `thread_id` (generated client-side once per conversation, or `sessionId`-derived) for the
  backend's own conversation continuity — this is how a stateful, thread-based agent API is meant
  to be driven, not by resending full history every call.
- **Stream parsing**: raw `data: <token>\n\n` frames, not the dev scaffold's `event:`/`data:` JSON
  event blocks. The adapter's parsing loop is simpler than `chatClient.ts`'s existing one (no
  `event:` line, no JSON parse per chunk — the token text *is* the frame body, with `\n`
  un-escaped back from the wire's `\n`→`\\n` encoding), terminated on the literal `event: done`
  frame rather than a `{event: 'done'}` JSON payload.

**Preserved unchanged**: the conversation UI (`ChatPage.tsx`), message history persistence
(`chatStore.ts`'s `localStorage` behavior), the existing lifecycle status states (`sending →
streaming → completed|cancelled|error`), and cancellation (`AbortSignal` → the real endpoint
supports request cancellation the same way any `fetch` does). `coreChatAdapter`'s existing
"resolve with an error outcome, never throw" contract is preserved exactly — only its *internal*
implementation changes from an immediate synthetic error to a real network call that may itself
resolve into that same error shape on failure.

## 18. Testing strategy

**Unit**: the canonical REST client (§4), error normalization (§14), the session module (§3), the
WebSocket client (§12) — each in isolation, mocking `fetch`/`WebSocket` only, not the feature
adapters built on top of them.

**Feature**: one test file per feature's `core<Feature>Adapter.ts`, mocking only the canonical
REST client's exported functions (matching this repo's own existing convention of mocking at the
service/adapter seam, confirmed in `*PageStates.test.tsx` files) — verifying the exact field
transformations in §6, not re-testing UI already covered by each feature's existing mock-adapter
test suite (which stays green and unchanged, since the mock adapter itself is untouched).

**Integration**: against the real backend's actual REST contract, using the same "fakes not mocks"
discipline the backend repo itself follows — i.e., point a test build at a real, ephemeral backend
instance (matching how the backend's own `tests/unit/test_*_route.py` files already spin up a real
`TestClient` + real temp-file SQLite) rather than a hand-rolled JSON fixture server.

**E2E**: authentication (session establishes silently at startup, no login UI), navigation to each
of the five real-mapped features, real data loading (against a real backend instance), one full
mutation flow per feature (create-then-see-it-in-the-list, at minimum), an induced-error path
(stop the backend mid-session, confirm the reconnect flow from §3/§12 recovers without a page
reload), and Automations' own "still mock, still labeled as such" state remaining correctly
distinguishable from the five real ones.

No test is weakened or deleted to make the suite pass — a failing test after a real change is a
signal to fix the implementation or, if the test's own expectation was wrong, to fix the test's
expectation with a stated reason, never to silently loosen an assertion.

## 19. Recorder test debt — established facts and Phase 2 strategy

**Facts, from this session's own direct experience, not inference**: `RecorderPage.test.tsx`'s
"stops immediately" test relies on real wall-clock elapsed time staying under the mock adapter's
500ms "nothing captured" threshold; under this session's own heavy sustained load it failed
consistently (3 consecutive runs, including in isolation) despite being reliably green earlier in
the same session under lighter load. An attempted fix — `vi.spyOn(Date, 'now').mockReturnValue(...)`
— was tried and reverted: it broke React 19's internal scheduler (a `useMediaQuery`/
`useReducedMotion` hook failed during initial render), a strictly worse failure mode than the
timing flakiness it was meant to fix. This is pre-existing debt, unrelated to the branch
reconciliation that surfaced it, already documented in the mock adapter's own source comments as a
known, accepted risk ("even under slow/CI test timing").

**Safer Phase 2 approach, evaluated in advance so it isn't re-derived under time pressure**: full
`vi.useFakeTimers({ shouldAdvanceTime: true })` combined with `userEvent.setup({ advanceTimers:
vi.advanceTimersByTime })` — vitest's documented, React-Testing-Library-safe pattern for exactly
this scenario (deterministic `Date.now()`/timer control that does not fight React's own scheduler,
because fake timers with `shouldAdvanceTime` still tick forward in real time for anything not
explicitly frozen). This is a **larger, riskier retrofit than a one-line mock** — it touches every
`await` in the test file's interaction sequence, not just the one flaky assertion — and is
explicitly scoped as its own small, isolated Phase 2 sub-task, attempted with time to iterate and
verify, not bundled into the main integration work where a mistake could destabilize an otherwise-
unrelated feature's tests. If it proves too invasive within Phase 2's time budget, the fallback is
to leave the flakiness documented exactly as it is now (already an accepted state, not a blocker)
rather than force a second risky quick-fix.

## 20. Security

- **Token leakage**: session token lives in memory only (§3), never `localStorage`/`sessionStorage`
  — matching `2.0-main/frontend`'s own proven choice for the same backend.
- **Credential leakage** (Connectivity, §5.5/§11): write-only from the UI, never redisplayed,
  never logged.
- **Unauthorized API calls**: impossible by construction — every call goes through the canonical
  client (§4), which always attaches the current token; there is no code path that calls the
  backend without it.
- **Session fixation / stale session**: `ensureSession()`'s liveness check (§3) is the sole
  defense — a stale token is detected and replaced automatically, never silently reused past
  validity.
- **WebSocket hijacking**: the token is passed as a query parameter over the same origin/transport
  security as the REST calls — no new exposure beyond what the REST channel already has.
- **Client-side permission manipulation**: not possible to matter — §15 establishes the backend
  as sole authority; a manipulated client-side flag changes only what's *offered*, never what's
  *allowed*.
- **Malicious backend payloads**: all rendered text goes through React's normal escaping (no
  `dangerouslySetInnerHTML` is introduced anywhere by this contract); no rendered content is ever
  interpreted as HTML/script.
- **Mock data leakage into production paths**: prevented by §16's guard test plus the unchanged
  `ready` flag convention already governing every adapter.
- **Sensitive error messages**: §14 shows only the backend's own already-human-written `detail`
  string — the backend itself is responsible for not leaking internals into that string, which is
  an existing, unchanged backend property, not something this frontend contract can or should
  re-verify.
- **`localStorage`/`sessionStorage` exposure**: audited scope is small — `chatStore.ts`'s message
  history (unchanged by this contract) and `mockSettingsAdapter`'s two boolean flags (also
  unchanged, since Settings' mock adapter is not being replaced wholesale, only the two real
  fields eventually pointed at real keys per §5.8) — neither holds a credential or token.

## 21. Performance
Existing lazy-loading/code-splitting (one chunk per feature page, already proven working — the
earlier reconciliation build confirmed `HomeAutomationPage`/`WorkflowBuilderPage`/`RecorderPage`
each split correctly) is preserved unchanged; Phase 2 adds no new top-level bundle. No request
deduplication layer is introduced beyond `useAsync`'s existing single-in-flight-per-hook-instance
behavior — sufficient for this contract's scope, since no two components currently fetch the same
resource concurrently. The WebSocket client (§12) is one connection, shared app-wide, not one per
feature. Smart Home device lists and Recorder history use the existing list rendering as-is — none
of the six features' expected data volumes (tens to low hundreds of rows) justify virtualization
work beyond what already exists elsewhere in the design system if a future volume problem appears;
none is added speculatively here. Chat streaming performance is inherited entirely from the SSE
mechanism already proven by the dev scaffold — no new throttling/batching logic is introduced.

## 22. Tauri boundary
Out of scope, explicitly. `Jarvis-Frontend-main` has no Tauri/Electron shell today and none is
added in this contract or its Phase 2. `2.0-main/frontend/src-tauri/` is not copied, referenced,
or used as more than historical evidence that a working Tauri setup exists *somewhere* in this
project's history should a future, separately-approved desktop-packaging milestone need it.
`2.0-main/frontend/` itself is not touched, not deleted, in this phase or the next.

## 23. JARVIS → AARYA boundary
No rename performed. Documenting only, per instruction, using the AARYA impact assessment already
completed this session: branding-only surfaces in this repo (page titles, the "JARVIS" wordmark in
the top bar, README/doc prose) are safe future rename candidates with no functional risk. Nothing
in Phase 2's actual scope (new adapter implementations, auth/REST/WS infrastructure) touches any
of the previously-identified sensitive identifiers (the persisted `ui.theme` value, any MCP-visible
field/server-id, package/env-var names) — none of those are read, written, or referenced by any
file this contract's Phase 2 creates or modifies.

## 24. Secondary repository disposition
`2.0-main/frontend/` remains frozen. Not deleted, not archived, not modified, in this phase. Per
the standing eight-point gate already established: deletion/archival requires this canonical
frontend fully integrated, real backend integration verified, full tests green, E2E green,
production build verified, security audit complete, and the desktop/Tauri strategy explicitly
resolved — **plus explicit approval**, as its own separate, deliberate step, not a side effect of
finishing Phase 2. Nothing in this contract moves that decision any closer than restating the gate.

## 25. Documentation
Deferred to after Phase 2 is implemented and verified, not touched now beyond this contract itself.
When it happens: `README.md`, `MASTER_ROADMAP.md`, `IMPLEMENTATION_ROADMAP.md`, `CHANGELOG.md` in
`2.0-main` must state plainly that `Jarvis-Frontend-main` is the canonical frontend, that
`2.0-main/frontend/` is frozen (not deleted), and exactly which of the six features are really
backend-integrated versus intentionally still mock (Automations). No historical milestone record
is rewritten — this is a forward-looking correction, not a retroactive one.

## 26. Implementation order
Dependency-derived, not the plausible default:

1. **Shared configuration/environment layer** — the `.env.example` this repo has never had (§1),
   documenting `VITE_BACKEND_URL` and the five features' own `_BACKEND=core` switches.
2. **Auth/session infrastructure** (§3) — nothing else can make a real call without it.
3. **Canonical REST client** (§4) and **error normalization** (§14) together — the client's own
   error handling *is* the normalization layer, not a separate pass.
4. **Canonical WebSocket client** (§12) — needed before any feature that subscribes to it (Smart
   Home), not needed by Workflow Builder/Recorder/Home Automation at all (§12), so this can
   actually happen in parallel with step 7-9 rather than strictly before them if that's more
   efficient — flagged as the one deliberate deviation from a strict top-to-bottom reading of the
   requested order, because the real dependency graph doesn't require it earlier.
5. **Workflow Builder** (§7) — first feature adapter, because Home Automation and Recorder both
   reference it (Recorder's "Open in Workflow Builder," Home Automation's underlying dedicated
   workflow) and having its real adapter proven first de-risks both.
6. **Recorder** (§8) — depends on #5 conceptually (not technically — its own REST calls are
   independent — but its generated-workflow preview is most meaningfully verified once Workflow
   Builder is already real).
7. **Home Automation** (§9) — needs the §6.3 transformation, best done once #5's workflow-fetching
   pattern already exists to copy from.
8. **Smart Home** (§10) — independent backend surface; benefits from the WebSocket client (§12,
   step 4) already existing.
9. **Connectivity** (§11) — same backend surface as #8, naturally sequenced alongside it.
10. **Chat** (§17) — the one feature needing real design work (§17's two decisions), sequenced
    after the simpler five so the canonical REST client and error model are already
    battle-tested against real traffic before Chat's more complex streaming case.
11. **Integration tests** (§18) — per feature, as each lands, not batched to the end.
12. **E2E tests** (§18).
13. **Production build verification**.
14. **Security audit** (§20, as a final structured pass, even though individual protections are
    built in at each step).
15. **Scope audit** (confirm nothing in §22/§23/§24's boundaries was crossed).
16. **Documentation** (§25).
17. **Final verification and the completion report**.

Automations (§5.6/§6.6) has **no implementation step** — it is explicitly excluded from this
sequence, not merely deferred to the end.

## 27. Acceptance criteria
- **Authentication**: a real session establishes at app startup against the real backend; every
  subsequent call carries a valid Bearer token; a simulated backend restart triggers automatic
  re-authentication without a page reload.
- **REST**: Workflow Builder, Recorder, Home Automation, Smart Home, and Connectivity make zero
  calls outside the canonical client; zero raw `fetch()` against the Core backend exists in any of
  their adapter files.
- **WebSocket**: `home.updated`/`device.updated`/`connectivity.status_changed` genuinely trigger a
  visible refetch in a running app; no subscription exists for either unrelayed device event.
- **Workflow Builder / Recorder / Home Automation / Smart Home / Connectivity**: each performs its
  full real CRUD/lifecycle/run/history operations against the live backend with zero mock fallback
  when `VITE_<FEATURE>_BACKEND=core`.
- **Automations**: verifiably still mock — `service.id === 'mock'`, `service.ready === true`,
  clearly labeled as such in the UI, by design, confirmed via a test asserting this stays true.
- **Chat**: a real message round-trips through `/api/v1/agent/stream` and renders token-by-token.
- **Production**: the §16 guard test passes — no mock adapter is reachable when every relevant env
  var is set to its real value.
- **Quality**: typecheck, lint (at the existing pre-existing-`.storybook`-error baseline), unit,
  feature, integration, and E2E tests all pass; production build succeeds.

Every criterion above is verified by running the named command/test — not by inspection alone.

## 28. Git safety

| | Before | After |
|---|---|---|
| `Jarvis-Frontend-main` branch | `feature/production-integration` | unchanged |
| `Jarvis-Frontend-main` HEAD | `1ca68d5` | unchanged |
| `Jarvis-Frontend-main` working tree | clean | clean |
| `2.0-main` branch/HEAD/origin | `feature/m22-task-group-c` / `126455c` / `126455c` | unchanged |
| `2.0-main` working tree | one untracked file (the prior Logic Contract) | one new untracked file added (this contract); no source changed |

No source file was modified in either repository. `2.0-main/frontend/` was not touched. No file
was deleted anywhere. No commit was created. No push was performed.
