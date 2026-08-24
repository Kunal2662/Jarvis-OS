# M8 Production Frontend Integration — Logic Contract

Status: **approved-pending-review, Phase 1**. No implementation exists yet. This document defines
how `2.0-main/frontend/` — established as the authoritative production frontend by the M8 Phase 0
Frontend Authority & Reconciliation Audit — will expose six already-shipped backend capabilities
(Smart Home, Devices, Connectivity, Home Automation, Workflow Builder, Recorder) and close the
directly-related remaining M8 production-readiness gaps. Every architectural claim below was
freshly re-verified against current source during Phase 1 — not carried over unchecked from the
Phase 0 audit. Two corrections to Phase 0's own findings surfaced during that re-verification and
are called out explicitly in §1 and §11 rather than silently folded in.

`Jarvis-Frontend-main` is referenced throughout as UX reference material only. Nothing in this
contract requires touching it, depends on its code, or adopts its architecture.

## 1. Current architecture — what a new feature must follow

Freshly verified against `2.0-main/frontend/src/` (all paths below relative to that root).

### 1.1 Entry point and routing

There is no `App.tsx`. Entry is `main.tsx` → `providers/app-providers.tsx`'s `AppProviders`
(`ErrorBoundary` → `StoreProvider` → `ThemeProvider` → `AccessibleMotionConfig` → `StartupGate`).
`StartupGate` awaits `runStartupSequence()` (`core/startup-orchestrator.ts`) before revealing the
router.

`routes/router.tsx` builds routes from `MODULE_DEFINITIONS`, not by hand-editing a route list:

```ts
const REAL_ROUTE_ELEMENTS: Partial<Record<string, ReactElement>> = {
  home: <DashboardGrid />,
  voice: lazyRoute(<VoiceRoute />),
  settings: lazyRoute(<SettingsRoute />),
};

const childRoutes: RouteObject[] = MODULE_DEFINITIONS.map((manifest) => {
  const route = manifest.routes[0] ?? "/";
  const element = REAL_ROUTE_ELEMENTS[manifest.name] ?? <PlaceholderRoute label={manifest.displayName} />;
  return route === "/" ? { index: true, element } : { path: route.slice(1), element };
});
```

**A route becomes real by adding one key to `REAL_ROUTE_ELEMENTS`, not by touching the route
tree.** `smart-home` and `automations` already have `ModuleManifest` entries (§1.2) but no key in
this map, so both currently render `PlaceholderRoute` — this is the exact "hasn't been built yet"
screen the Phase 0 audit found.

Lazy routes (`routes/lazy-routes.ts`) follow one shape:

```ts
export const VoiceRoute = lazy(async () => ({
  default: (await import("@/features/voice/voice-page")).VoicePage,
}));
```

A new full-page feature adds `export const SmartHomeRoute = lazy(async () => ({ default: (await
import("@/features/smart-home/smart-home-page")).SmartHomePage }));` and one entry,
`"smart-home": lazyRoute(<SmartHomeRoute />)`, in `REAL_ROUTE_ELEMENTS`. Same pattern for
`automations`, `home-automation` (if it needs its own top-level surface — see §21 on why it does
not), `workflow-builder`, `recorder`.

### 1.2 Module registry — and a correction

`ModuleManifest` (`core/module-manifest.ts`) is data: `name, displayName, version, category,
dependencies, permissions, commands, voiceCommands, automationSupport, settingsSchema, icon,
routes, capabilities, isCore, parentGroup, developerMetadata`. `modules/module-definitions.ts`
already declares:

```ts
definition({ name: "smart-home", displayName: "Smart Home", icon: "lightbulb", route: "/smart-home", category: "connected" }),
definition({ name: "automations", displayName: "Automation", icon: "workflow", route: "/automations", isCore: true }),
```

**Correction to a plausible but wrong assumption**: `PlaceholderModule`'s own doc comment says a
module "graduates" by being replaced with a custom `BaseApplication` subclass instead of
`PlaceholderModule`. Fresh verification shows this has **never actually happened** for any of the
14 current modules — `home`, `voice`, and `settings` (all three already real-routed, shipping
today) are **still** plain `PlaceholderModule` instances. Route-level graduation (§1.1) and
module-class graduation are decoupled in this codebase's actual practice, whatever one doc comment
aspires to. **This contract follows the proven, currently-shipping pattern**: add the real route
and page component; leave the module's `PlaceholderModule` registration exactly as-is. Writing a
custom `SmartHomeApplication extends BaseApplication` would be inventing a pattern this codebase
has never shipped, not following precedent — explicitly not required by this contract.

### 1.3 Module enablement

`stores/module-enablement.store.ts`: `isModuleEnabled(isCore, moduleId, enabledModuleIds) =
isCore || enabledModuleIds.includes(moduleId)`. `automations` is `isCore: true` (always on).
`smart-home` is optional (`category: "connected"`, `isCore` unset) — starts disabled until a user
opts in via the Settings → Plugins-equivalent enablement UI. **No such enablement UI is built yet**
(the existing `features/plugins/plugins-panel.tsx` manages backend *plugins*, a different concept,
not `ModuleEnablementStore` toggles). This contract does not build that UI — see §20 — but a
Smart Home page reachable only via direct navigation or the command palette, without a sidebar/nav
entry surfaced pre-enablement, is acceptable for this scope; enabling the module via
`useModuleEnablementStore.getState().enableModule("smart-home")` remains a manual/future step,
consistently with the existing gap.

### 1.4 Panel registry

`core/panel-registry.ts`'s own comment is current and accurate: none of the 9 not-yet-built
modules (including Smart Home, Automation) has a panel contribution, deliberately, so a
resizable-panel chrome never wraps a "not built yet" placeholder. **This contract does not add
panel-registry entries for the six features in scope** — all six are naturally full-page
experiences (device management, an automation/workflow list-detail-run flow, a recording
lifecycle), matching exactly how `Jarvis-Frontend-main`'s own UX reference treats them (full
`*Page.tsx` components, never a panel). If a future pass wants an at-a-glance dashboard widget
(e.g. "3 devices offline"), that is additive via `dashboardWidgetRegistry` and explicitly out of
this contract's scope (§20).

### 1.5 API client architecture

`services/api/client.ts`'s `apiRequest<T>`/`apiList<T>`/`apiVoid` are the only sanctioned way to
call the backend — every typed client in `services/api/endpoints.ts` is a thin wrapper over these
three. Non-2xx handling (`toApiError`) has a `status === 401` special case; every other non-2xx
(**including 400s and 404s**) falls through to a generic branch producing `{code: "HTTP_${status}",
message: <detail>, severity, retryable}`. There is **no 403 in this contract's scope at all** — see
§13 for why (all six features' permission and not-found errors are 400/404, never 403).

New typed clients (`smartHomeApi`, `connectivityApi`, `homeAutomationApi`, `workflowBuilderApi`,
`recorderApi`) are added to `services/api/endpoints.ts` in the same file, following the existing
`const xApi = { method: (...) => apiRequest<T>(path, {...}) }` shape. **Genuine gap found**: no
existing client has a `create`/`update`/`delete` method — every current one is read-only except
the action-verb style (`enable`/`disable`/`grant`/`deny`). The five new clients will be this
codebase's first `POST`-with-body "create" calls; the shape is unambiguous by direct extension of
`searchApi.query`'s and `session.ts`'s existing `POST` + `body` usage, not a new pattern.

### 1.6 Data layer — correction to the Phase 0 audit

**Phase 0's audit stated "TanStack Query, real, fetch-based, not mocked" and was correct that the
provider and API layer are real** — but fresh, deeper verification this phase found **zero
components anywhere call `useQuery` or `useMutation`**. The actual, exclusively-used data-fetching
pattern is a bespoke hook, `useBackendResource` (`hooks/use-backend-resource.ts`), whose own
docstring explains the deliberate choice: TanStack Query's value is caching, and dashboard/list
data here wants the current answer, not a cached one. `services/api/query-keys.ts` is an
acknowledged, unused stub. **This contract follows the actually-shipped pattern, not the installed-
but-unused one**:

```ts
const { state, refresh } = useBackendResource(
  () => smartHomeApi.listDevices({ home_id }),
  [home_id],
);
```

composed with `ResourceView` (widget/section scale) or `ModuleStateView`/`error-framework.ts`'s
`ViewState` (full-page scale — the correct choice for these six full-page features). For mutations
(create/update/delete/enable/disable/run/pair/command/start/stop/cancel), the precedent is
`PluginsPanel`'s `toggle()`: a plain async function calling the typed client, `try/catch`,
`reportSuccess`/`reportError` (`services/error-reporting.ts`), then the sibling `refresh()` — never
`useMutation`, since no precedent for it exists either.

### 1.7 `ResourceView` / `ModuleStateView`

`ResourceView` (`components/common/resource-view.tsx`) handles a six-state union (`idle`/
`loading`/`ready`/`empty`/`offline`/`error`) at widget scale. `ModuleStateView`
(`components/common/module-state-view.tsx`) is its full-page sibling, driven by
`error-framework.ts`'s `ViewState` (`loading`/`empty`/`offline`/`error`/`permission_denied`/
`auth_required`/`config_required`). **All six new features use `ModuleStateView` for their
top-level page** (list views, detail views) and `ResourceView` only for any smaller, contained
section within a page (e.g. a device's recent-activity list inside its detail view).

### 1.8 WebSocket integration

`services/websocket/types.ts`'s `RELAYED_EVENTS` already includes `home.updated`, `device.updated`
(labeled M12 Task Group A), and `connectivity.status_changed` — type-safe today, but **no payload
interface exists yet for `home.updated`/`device.updated`**, and **no subscriber exists** in
`services/realtime-bridge.ts` for any of the three. Components never touch `websocketManager`
directly — `installRealtimeBridge()` is the single place subscriptions live, updating a Zustand
store components read reactively (exact pattern in §11).

### 1.9 Authentication / session

`services/api/session.ts`'s `createSession`/`ensureSession`/`endSession` are real; one session
token is attached to both REST (`Authorization: Bearer`) and WebSocket (`?token=`).
`ensureSession()` is invoked from `services/backend-connection.ts`'s `connectBackend()`, itself run
once at startup by `startup-orchestrator.ts`'s `backend-connection` task, and again on every
reconnect. **New features do nothing to manage auth** — every call through `apiRequest` already
carries the token; a feature only has to handle the possibility that a call fails.

### 1.10 Permission / user-mode boundaries

`core/user-mode.ts`'s three-tier audience gate (personal/developer/administrator) governs *what
information is revealed* (provider names, routing, debug state) — it is unrelated to backend
resource-scope permissions and does not gate any of these six features. `core/permission-
framework.ts` is a **client-side-only** grant/deny tracker mirroring `ModuleManifest.permissions`
vocabulary, never a network call — also not what backend 400/permission-denial needs. **No
existing frontend pattern maps a backend permission-scope denial to UI today** — see §13 for the
evidence-grounded design decision this contract makes instead of inventing a new `ViewState`.

### 1.11 Design-system inventory

`components/ui/`: 16 shadcn/Radix files, notably **missing `select`, `switch`, `checkbox`, `badge`,
`popover`, `table`, `form`**. `settings-page.tsx` fakes a toggle with a plain `<Button
role="switch">` rather than a real Switch primitive. **No create/edit form or detail-drawer pattern
exists anywhere in this codebase today** — the closest precedents are `DiagnosticsDialog`
(`features/installer/installer-diagnostics.tsx`, a real `Dialog`/`DialogContent`/`DialogFooter`
structure, but read-only, no form fields) and `PluginsPanel` (list + inline mutation buttons, no
dialog). This contract's step-editor form (Home Automation trigger config, Workflow Builder step
list, Recorder's stop-name modal) is new UI territory, modeled on `DiagnosticsDialog`'s dialog
structure plus `PluginsPanel`'s mutation-feedback pattern — see §20 on adding the missing shadcn
primitives (`select`, `switch`) as a small prerequisite, not scope creep.

### 1.12 Tauri boundary

Two established patterns: `isTauri()` guard around an official `@tauri-apps/api` import
(`services/window/window-service.ts`), or a typed `globalThis.__TAURI__` feature-detect for a
custom Rust command (`features/installer/provisioning-transport.ts`). **None of the six features in
this contract need either** — they are pure REST/WebSocket consumers with no native OS capability
requirement.

## 2. Backend contract verification

All items below were read fresh from source this phase, not carried over from Phase 0.

### 2.1 Smart Home (`routes/smart_home.py`, `routes/smart_home_memory.py`)

**No `smart_home` permission scope at the route layer for the core registry** — Homes/Zones/Rooms/
Devices/DeviceGroups CRUD is gated by session auth only (`Depends(get_current_session)`); neither
`SmartHomeService` nor `ConnectivityService` checks any `PermissionModel` scope. Only
`SmartHomeMemoryService` (snapshot capture) checks the shared `"smart_home"` scope.

Routes (all `{data, meta}` envelope): `POST/GET /homes`, `GET/PATCH/DELETE /homes/{id}`, `GET
/homes/{id}/metadata`; the identical five-shape CRUD for `/smart-home/zones` and `/smart-home/
rooms`; `POST/GET /devices`, `GET/PATCH/DELETE /devices/{id}`, `POST /devices/{id}/pair`; the
identical CRUD plus `/members` sub-routes for `/smart-home/device-groups`. Memory: `POST/GET
/smart-home/memory/snapshots`, `DELETE /smart-home/memory/snapshots/{id}`, `POST /smart-home/
memory/snapshots/home/{home_id}` (batch, always 200, per-device outcome in the body).

Device payload: `{id, home_id, room_id, name, device_type, status, manufacturer, model,
external_id, created_at, updated_at, last_seen_at}`. Status vocabulary: `{"discovered", "pairing",
"paired", "offline", "unreachable", "removed"}` — **`"pairing"` and `"removed"` are validated but
never written by any shipped code path**; the UI's status filter/badge set may offer all six for
forward-compatibility, but should not expect to see the latter two in practice. `device_type`:
`{"light", "lock", "sensor", "camera", "switch", "thermostat", "appliance", "other"}`.

**Known backend inconsistency, preserved as-is, not silently designed around**: `POST /devices/
{id}/pair` on an unknown `device_id` returns **400**, not 404 (the service raises before the
route's own 404 branch can run). The UI must not assume every unknown-id case returns 404 for this
one endpoint.

### 2.2 Devices — command dispatch and event visibility

`ConnectivityService.send_command()` is the sole chokepoint. **No permission scope at all.**
Three-way failure shape: unknown device → 404; no/disconnected connector → 400; connector
transport failure → 400 (no `CommandResult`, no event). Otherwise **always 200** with `{external_id,
command, success, detail}` — a device-level rejection is `success: false`, never an exception. The
command result is returned synchronously in this same response.

`DeviceCommandExecutedEvent` and `DeviceStateChangedEvent` both exist, are published on the
internal `EventBus`, and have stable field shapes — but **both are in `UNPUBLISHED_EVENT_TYPES`**,
not relayed over WebSocket. `DeviceUpdatedEvent`→`"device.updated"` and `HomeUpdatedEvent`→
`"home.updated"` **are** relayed, but `device.updated` fires **unconditionally** on every
`report_device_state()` call (not only on a genuine transition — that distinction is what
`DeviceStateChangedEvent`, the unrelayed event, is actually for). **Design consequence for §4/§11**:
command feedback comes from the synchronous REST response, never from a WS push (there is nothing
to push); `device.updated`/`home.updated` are usable only as a generic "something in this home may
have changed, consider refetching" signal, never as "device X is now in state Y" without a
follow-up `GET`.

### 2.3 Connectivity (`routes/connectivity.py`)

`GET /connectivity/connectors` (live `{connector_type, connected}` per `CONNECTOR_TYPES =
{"home_assistant", "mqtt"}` — closed set), `POST .../connect` (idempotent), `POST .../disconnect`
(always succeeds), `POST /connectivity/discover` (body `{connector_type, home_id}`), `POST
/connectivity/devices/{id}/refresh`, `POST /connectivity/devices/{id}/command`. No permission scope
anywhere in this router either.

Connector status is **not** a stored field — `GET /connectivity/connectors` computes it live from
`connector.is_connected`. The event-level status vocabulary (`ConnectivityStatusChangedEvent`,
**relayed** as `"connectivity.status_changed"`) is `"connecting" | "connected" | "disconnecting" |
"disconnected"` — **no `"error"` value**; a failed `connect()` raises (surfaced as REST 400)
without ever publishing a terminal status for that attempt.

**No API lists valid commands per connector type** — `POST .../command` is a fully generic,
uninterpreted passthrough; command semantics are private to each connector implementation. A
generic command console is out of this contract's scope for that reason (§20) — Home Automation's
and Workflow Builder's `"automation"` step kind already covers the actually-needed device-command
use case via the existing `ActionExecutor` vocabulary, not this raw passthrough.

**Credentials**: confirmed no REST response in this router ever includes a raw credential value —
`ConnectorCredential.to_public_dict()` reports only `secret_keys`/`has_secrets`/expiry/`revoked`,
never `secrets` itself; `to_storage_dict()` (the only method with real values) is called
exclusively from the encrypted-at-rest store, never from a route handler.

### 2.4 Home Automation (`routes/home_automation.py`) — 8 routes, no PATCH

`POST/GET /home-automation`, `GET/POST(enable)/POST(disable)/DELETE /home-automation/{id}`, `POST
/home-automation/{id}/run`, `GET /home-automation/{id}/executions`. Permission: `"home_automation"`
scope, checked on every route; denial → **400** (not 403), message contains "permission" and a
grant-instruction hint. Unknown id → 404, except create/list validation errors → 400.

Trigger payload: `{id, workflow_id, name, device_id, from_status, to_status, enabled, created_at,
updated_at, last_fired_at}`. Execution payload: `{id, automation_trigger_id, workflow_id, source,
status, started_at, finished_at, error, step_results}`. Create body: `{name, device_id, to_status,
steps: [{kind, instruction, tool_name, tool_args, depends_on, label}], from_status="", description="",
enabled=true}` — `from_status=""` means wildcard (any prior status matches). No update route by
design (Scheduler's own precedent) — editing means delete + recreate. `run` is a manual test
execution reusing the identical dispatch path a real event-triggered match uses — it does not
bypass step-level permission/confirmation.

### 2.5 Workflow Builder (`routes/workflow_builder.py`) — 7 routes, incl. the family's only PATCH

`POST/GET /workflows`, `GET/PATCH/DELETE /workflows/{id}`, `POST /workflows/{id}/run`, `GET
/workflows/{id}/executions`. Permission: `"workflow_builder"` scope, denial → 400. `PATCH` is a
genuine partial update — only supplied fields change, `steps` (if supplied) replaces the whole
list.

Workflow payload: `{id, name, description, steps, created_at}`. Step shape (shared with Home
Automation, `WorkflowStepKind`): `{id, kind: "automation" | "agent_tool", instruction, tool_name,
tool_args, depends_on, label}` — an `"automation"` step requires non-empty `instruction`; an
`"agent_tool"` step requires non-empty `tool_name`. `run` is the only execution path, awaited
synchronously — the caller gets the final execution result directly in the response, not via a
follow-up event.

### 2.6 Recorder (`routes/recorder.py`) — 5 routes

`POST /recordings/start`, `POST /recordings/{id}/stop` (body `{name, description?}`), `POST
/recordings/{id}/cancel`, `GET /recordings`, `GET /recordings/{id}`. Two independent scopes:
`"recorder"` (session start/stop/cancel/list) and, only inside `stop`'s delegation to
`WorkflowBuilderService.create_workflow()`, a **freshly and separately re-checked**
`"workflow_builder"` scope — holding `recorder` alone is not enough to complete a stop that
produced a genuinely captured step. Both denials → 400.

Session payload: `{id, status: "recording"|"completed"|"cancelled", started_at, stopped_at,
resulting_workflow_id}`; `stop`'s success response additionally carries the full created
`resulting_workflow` object (same shape as §2.5). A `stop` call with nothing supported captured
fails 400 **and leaves the session `"recording"`** — not finalized — so the UI must keep the
active-recording state alive on that specific failure rather than treating it as terminal.

### 2.7 Real-time events — none of the M7 trio has one

`WorkflowStepEvent` and `ScheduledJobFiredEvent` are both in `UNPUBLISHED_EVENT_TYPES`. There is no
relayed event for Home Automation, Workflow Builder, or Recorder execution progress at all. This is
not a gap this contract needs to fix — every execution-triggering call (`run`, `stop`) is a
synchronous REST call whose response already carries the final result (§2.4/§2.5/§2.6). No
real-time channel is needed for these three features; see §11.

### 2.8 Permission scopes (verbatim, `core/plugins/sdk.py`)

`smart_home` (Memory only, not core registry/Connectivity), `home_automation`, `workflow_builder`,
`recorder`. Fourteen scopes total exist; only these four are relevant here.

## 3. Smart Home UI

Full page (`features/smart-home/smart-home-page.tsx`), `ModuleStateView`-driven. Home selector (if
&gt;1 home) → device grid grouped by room, each card showing name/type/status badge. Device detail
(drawer or sub-route) shows manufacturer/model/room/status/last-seen plus a **Pair** action
(visible only for `discovered`/`offline`/`unreachable` devices, per the backend's own transition
rule) and a **Refresh** action (`POST /connectivity/devices/{id}/refresh`). Loading: `ModuleStateView`
"loading". Empty (no homes yet): a "Create your first home" call to action (`POST /homes`). Error:
`ModuleStateView` "error" with retry. No "unavailable/offline" state beyond the existing
`useBackendResource` offline branch — there is no separate "Smart Home subsystem down" signal from
the backend. Refresh behavior: manual pull-to-refresh/refresh button (`refresh()` from
`useBackendResource`) plus a `device.updated`/`home.updated` WS subscription that triggers the same
`refresh()` (never a direct store mutation, since those events carry no payload guaranteeing what
changed — §2.2). No device controls beyond Pair/Refresh/Rename(`PATCH`)/Remove(`DELETE`) — **no
brightness sliders, no on/off toggles, no thermostat controls** here; those already exist as
separate, normalized per-category routers (Smart Lighting, Smart Locks, etc.) genuinely out of this
contract's six-feature scope (§20).

## 4. Device UI

Folded into §3's device detail view rather than a separate top-level surface — the backend has no
concept of "device" independent of Smart Home's own registry. Command execution
(`connectivityApi.sendCommand`) is exposed only where a normalized per-category UI doesn't already
cover it — for the six-feature scope of this contract, that means **no generic raw-command console
is built** (§2.3 explains why: uninterpreted, per-connector-private semantics, no discovery API).
`DeviceCommandExecutedEvent` vs. `DeviceStateChangedEvent` distinction (§2.2) is preserved in the
UI's own mental model even though neither is currently observable via WebSocket: a command
succeeding (`success: true` in the synchronous response) is shown as "command sent successfully,"
**never** as "device is now in state X" — the UI does not fabricate a state change from a command
acknowledgment. A stale-state indicator (e.g. "last confirmed &lt;n&gt; minutes ago", from
`last_seen_at`) communicates this honestly instead.

## 5. Connectivity UI

A settings-adjacent surface (not a top-level nav item — reachable from Smart Home's own "no
devices yet, connect a service" empty state, or a Developer/Settings connectivity panel) listing
the two connector types with live `connected` status, Connect/Disconnect actions, and a Discover
action per connected connector (`POST /connectivity/discover`, requires `home_id`). Connection form
fields are connector-specific and unavoidably credential-bearing (e.g. a Home Assistant base URL +
long-lived token) — **the UI must never log, telemetry-report, or echo back the submitted `config`
body**, consistent with the backend's own redaction discipline (§2.3); a submitted credential is
write-only from the UI's perspective, never redisplayed after submission. No `"error"` status badge
exists in the backend's own vocabulary (§2.3) — a failed connect surfaces via the synchronous
400's error message only, not a persisted connector state.

## 6. Home Automation UI

Full page (`features/home-automation/home-automation-page.tsx` or as a tab within Automations —
see §21 on ordering). List (name, device, trigger summary, enabled toggle, last-fired) →
create/edit-equivalent form (name, device picker, `to_status`/`from_status` selects populated from
the real `DEVICE_STATUSES` vocabulary, step list reusing the shared step-editor component built for
Workflow Builder — §7) → detail view (trigger config, execution history via `GET .../executions`) →
Enable/Disable (two dedicated routes, not a PATCH) → Run now (`POST .../run`, synchronous result
shown immediately) → Delete (with a confirmation dialog — a destructive action). Execution status
badges use the real `AutomationExecution.status` values. No cooldown value is exposed by any read
route today (`min_refire_interval_seconds` is a service-internal guard, not in the trigger payload)
— do not display a cooldown countdown that has no backing data. Concurrency/failure: an execution
row's `status`/`error` fields are the only representation needed; no separate "automation is
currently running" live indicator exists (no relayed event for it, §2.7) — the UI relies on the
synchronous `run` response plus a post-run refetch of the execution list.

**Explicitly not built** (deferred, per your own list): attribute-level triggers, multi-device
conditions, presence/camera triggers, AI-generated automations, MQTT-native trigger UI beyond what
the generic `device_id`/`to_status` model already supports, an Event Viewer, Smart Home Memory
integration into this feature.

## 7. Workflow Builder UI

Full page (`features/workflow-builder/workflow-builder-page.tsx`). List → create (name,
description, ordered step list: each step picks `kind` ∈ {automation, agent_tool}, then either
`instruction` or `tool_name`+`tool_args`, matching §2.5's exact validation) → detail/edit (the
family's only `PATCH` — supports true partial update: submitting only `name` leaves `steps`
untouched, and vice versa) → Run now (synchronous) → execution history → Delete (confirmation
dialog). Step reordering is a client-side array operation submitted as the full `steps` array on
save — the backend has no separate reorder endpoint. Validation mirrors §2.5 exactly (non-empty
name, at least one step, each step's kind-specific field non-empty) — **do not invent a step kind
beyond `automation`/`agent_tool`**, and do not reintroduce `RecipeManager` or build a second
execution path; `run` always calls the one shared `WorkflowExecutionService` via the existing
backend delegation, and the frontend has no execution code of its own to add here either.

## 8. Recorder UI

Full page (`features/recorder/recorder-page.tsx`). Entry point states the capture scope plainly
(records JARVIS's own automation-engine actions only, never raw keyboard/mouse, never anything
outside JARVIS — same requirement this project held for the M7 Recorder backend itself). Start →
active-recording state (elapsed-time indicator computed client-side from `started_at`, **no live
captured-action list** — the backend has no endpoint for that, §2.6/§2.7 — a caption should say so
honestly rather than implying live capture) → Stop opens a name-required (description optional)
confirmation step → on the "nothing captured" 400, the modal shows the error inline and **the
active-recording state is preserved**, not abandoned (§2.6) → on success, a generated-workflow
preview (reusing Workflow Builder's own step-list rendering, §7) with "Open in Workflow Builder"
(navigate) and "Run now" (calls the *same* `workflowBuilderApi.run`, never a Recorder-local
execution path) → Cancel (non-destructive, frees the slot immediately) → a past-recordings history
list (`GET /recordings`).

**Explicitly not built, ever, per the backend's own boundary**: raw keyboard/mouse recording,
computer-use recording, AI workflow inference from the recording, agent-tool-call capture (no
backend mechanism exists for any of these — building frontend UI for them would imply a capability
that does not exist).

## 9. Shared UX requirements

**Loading**: `ModuleStateView`'s "loading" for page-level, `ResourceView`'s skeleton for
section-level — reuse existing `SkeletonRows`/`SkeletonStatGrid`, do not invent a new skeleton
shape. **Empty**: `ModuleStateView`/`ResourceView`'s existing empty-state rendering with a
feature-specific `emptyMessage` and, where a create action exists, its call-to-action button routed
through the same button already used elsewhere. **Errors**: the backend's own message string is
shown verbatim (it is already written for a human, including permission-grant hints — §13); no
message rewriting/paraphrasing layer. **Retries**: `ModuleStateView`/`ResourceView`'s built-in
retry, wired to the same `refresh()` the resource hook already returns — never a bespoke retry
button. **Stale data**: `last_seen_at`/`updated_at`/`last_fired_at` timestamps are shown, not
hidden — this project's "no fake data" rule extends to not implying freshness that isn't real.
**Mutations are never optimistic** — every create/update/delete/run/pair/command mutation shows a
loading state on its own trigger control and waits for the real response before updating any list,
consistent with `PluginsPanel`'s existing pattern and the fact several of these actions
(pair/command/run) can genuinely fail in ways worth surfacing precisely. **Success feedback**:
`reportSuccess`/`reportError` (the existing toast/sonner-backed mechanism) — **no second
notification system**. **Destructive actions** (delete workflow, delete automation, delete
home/room/device) get a confirmation dialog (`components/ui/dialog.tsx` / `alert-dialog.tsx`) —
Cancel (recording), Disable (automation), and Disconnect (connector) are **not** treated as
destructive (all are reversible/non-data-destroying) and need no confirmation, consistent with how
this project's backend Logic Contracts have already drawn that line. **Accessibility/keyboard/
responsive**: inherit the existing app shell's patterns (Radix dialog focus-trapping, the existing
768px responsive breakpoint hook) — no new mechanism.

## 10. Authentication and session

No new mechanism (§1.9). Every new typed API client call goes through the existing `apiRequest`,
which already attaches the Bearer token. **Unauthorized response**: a 401 already has dedicated
handling in `toApiError` (`code: "UNAUTHENTICATED"`) — the existing `connectBackend()`/reconnect
flow already re-establishes a session automatically; no feature-specific handling is needed.
**Session expiration/reconnect/logout**: entirely handled by the existing `connection.store.ts` +
`installConnectionRecovery()` machinery — none of these six features add, bypass, or duplicate it.
**Protected routes**: all six live behind the same app shell every other route does; there is no
route-level auth gate to add (session establishment happens once, at startup, before the router is
even revealed via `StartupGate`).

## 11. WebSocket integration

**Home Automation, Workflow Builder, Recorder need no WebSocket wiring at all** — §2.7 established
no relayed event exists for any of their execution states, and none is needed, because `run`/`stop`
are synchronous REST calls that already return the final outcome. Building a WS subscription for
these three would be inventing an event that doesn't exist, which this contract explicitly refuses
to do.

**Smart Home / Devices / Connectivity**: three events are genuinely available and should be wired:

- Add `HomeUpdatedPayload`/`DeviceUpdatedPayload` interfaces to `services/websocket/types.ts`
  (none exist today) — shape TBD by the actual event payload dataclasses (`HomeUpdatedEvent`/
  `DeviceUpdatedEvent` in the backend's `core/events/events.py`; confirm exact fields during Phase
  2, since this contract's backend investigation focused on `DeviceCommandExecutedEvent`/
  `DeviceStateChangedEvent`'s shapes specifically, not these two).
- One new block in `services/realtime-bridge.ts`'s `installRealtimeBridge()`, following the
  existing `health.updated` shape exactly: `websocketManager.on<HomeUpdatedPayload>("home.updated",
  (message) => useSmartHomeStore.getState().markStale())` — **`markStale()`, not a direct state
  write**, since (§2.2) `device.updated`/`home.updated` fire unconditionally and carry no guarantee
  about *what* changed. A "stale" flag triggers the visible page's own `refresh()` next time it's
  interacted with, or immediately if the page is currently mounted and idle.
- `connectivity.status_changed` subscribed the same way, updating a connector-status store consumed
  by §5's Connectivity UI.

No component ever calls `websocketManager` directly — all three subscriptions live in
`installRealtimeBridge()`, per existing convention (§1.8).

## 12. REST / data-layer integration

`useBackendResource` + `ModuleStateView`/`ResourceView` for reads (§1.6/§1.7) — **not**
`useMutation`/`useQuery`, correcting the plausible-but-wrong assumption that TanStack Query hooks
are the pattern to follow. Five new typed clients in `services/api/endpoints.ts` (§1.5). Mutations
follow `PluginsPanel.toggle()`'s shape: async function → typed client call → `try/catch` →
`reportSuccess`/`reportError` → sibling `refresh()`. No client-side pagination beyond what
`apiList`'s existing `{count, limit, offset, has_more}` meta already provides (none of these six
features' list endpoints need more than that). No optimistic updates anywhere in this scope (§9).
Cache/invalidation: there is no cache to invalidate — `refresh()` re-runs the fetcher, exactly as
every existing feature already does.

## 13. Permissions and security

Backend authorization is the sole source of truth; the frontend never decides what's allowed, only
reflects what the backend already decided. **Concrete mapping**:

| Feature | Scope | Denial status | Notes |
|---|---|---|---|
| Smart Home core registry (Homes/Zones/Rooms/Devices/Groups) | *(none)* | — | session-auth only |
| Connectivity (connect/discover/refresh/command) | *(none)* | — | session-auth only |
| Smart Home Memory (snapshots) | `smart_home` | 400 | |
| Home Automation | `home_automation` | 400 | |
| Workflow Builder | `workflow_builder` | 400 | also independently re-checked inside Recorder's `stop` |
| Recorder | `recorder` (+ `workflow_builder` on `stop`) | 400 | permission stacking, never bypassed |

**Design decision, evidence-grounded, not the plausible-default choice**: since every one of these
services signals permission denial as **400 with a prose `detail` message**, not 403, this contract
does **not** add a new `403`/`PERMISSION_DENIED` branch to `toApiError` or a new `permission_denied`
`ViewState` trigger. That machinery exists in `error-framework.ts` today but is fed only by the
client-side `permission-framework.ts`, an unrelated concept (§1.10) — wiring a real backend 400 into
it would require string-matching the message, which is fragile and unnecessary. **The backend's own
detail message (which already includes a grant-instruction hint) is shown verbatim via the existing
generic error/toast path** — the same one every other 400 already uses. Frontend visibility is never
treated as authorization: a disabled/hidden button is a UX nicety, never the actual gate; every
mutating action still goes through the real backend call and handles a denial if the frontend's own
guess about what's currently granted was wrong (e.g. stale local state, revoked mid-session).
Fail-safe (never fail-open) is preserved by construction — nothing in this scope adds a client-side
bypass of any kind, and Recorder's dual-scope stacking is surfaced, not flattened, in the UI copy
when it's the specific cause of a denial.

## 14. Production data only

No mock device lists, no mock automations, no fake workflow execution, no fake recorder sessions,
no fake connector state — every one of the six features' list/detail/history views renders only
what `useBackendResource` returns from the real typed client, with `ModuleStateView`/`ResourceView`
handling the honest empty/loading/error/offline states in between. This is the same "no fake data"
discipline every other `2.0-main/frontend` feature already follows (§14 of the Phase 0 audit
confirmed this holds everywhere checked) — nothing here is a new rule, only its extension to six
more features. Development-only mocks are not introduced by this contract at all; if a future
implementer wants one for local iteration, it must follow this codebase's own established
`ready`-flagged adapter convention if one is added later, never silently ship in the production
path.

## 15. `Jarvis-Frontend-main` — reference only

Not a dependency, not a source of code, not an architecture to adopt. UX behavior worth preserving
as a **design reference** (re-derived from this session's own direct knowledge of that repo's
implementation, since it was built this session):

- **Home Automation**: trigger list with device/status summary, enabled/disabled badge, a
  create/edit form pairing a device picker with `to_status`/`from_status` selects, execution
  history list with status badges. Worth preserving: the clarity of showing `from_status`/
  `to_status` as a compact "X → Y" summary on the list row.
- **Workflow Builder**: drawer-based detail view (steps + execution history + Edit/Run/Delete
  footer), a step-kind selector switching between an instruction field and a tool-name field.
  Worth preserving: the partial-update-aware edit form (only resubmits changed sections) and the
  ordered-step-list-with-remove-row editor UX.
- **Recorder**: the elapsed-time active-recording indicator, the explicit "Preview — actual capture
  is finalized when you stop" honesty caption, the name-required stop modal that keeps the session
  alive on a "nothing captured" failure, and the generated-workflow preview's "Open in Workflow
  Builder"/"Run now" pairing. Worth preserving: all of it — this exact flow maps directly onto
  §2.6's real backend semantics and needed no adaptation to the *behavior*, only to the target
  design system's components.

None of this authorizes copying a single file. `2.0-main/frontend`'s own design-system primitives,
`useBackendResource`/`ModuleStateView` pattern, and typed-client convention are what Phase 2 must
use, full stop.

## 16. Playwright regression

`e2e/dashboard-widgets.spec.ts:27` currently fails (a `role="group"` selector matching 15 elements
instead of the expected 4) — a test-selector bug, not a product defect, found during the Phase 0
audit. **Not fixed in this Phase 1 contract**, per explicit instruction. It matters because the
roadmap's own M8 acceptance criterion #4 ("the full... Playwright suite passes") does not currently
hold, and because a future implementer adding new e2e coverage for these six features should not
inherit a false "everything's green" signal. **Acceptance requirement for Phase 2**: the full
Playwright suite (all specs, this one included) must pass before Phase 2 is considered complete.
**Required verification**: `npm run test:e2e` with 0 failures. **Regression expectation**: no new
Playwright spec added for these six features may be allowed to reduce the passing count elsewhere;
each new spec is additive.

## 17. Accessibility / QA acceptance requirements

Keyboard navigation: every new interactive element (buttons, form fields, list rows that open a
detail view) reachable and operable via keyboard alone, consistent with the existing Radix-backed
primitives' built-in behavior — no new custom keyboard handling invented. Focus management: dialogs
(Stop-recording modal, delete confirmations) trap and restore focus via the existing `Dialog`
primitive, not a bespoke implementation. ARIA: reuse existing patterns (`role`/`aria-*` attributes
already present in `components/layout/*`) rather than inventing new conventions. Contrast/
screen-reader: **not formally verified by this contract** — consistent with the Phase 0 audit's
own honest finding that no contrast-ratio measurement or screen-reader pass exists anywhere in this
codebase yet; this contract does not claim compliance it hasn't tested, and does not expand scope
to build that formal audit (§20). Responsive: the existing 768px breakpoint hook applies unchanged.
Chromium verification: required (existing Playwright config, single project). Production build:
required (`npm run build`, zero errors). Typecheck/lint: required, zero errors (warnings at the
existing baseline are acceptable, matching the 17 pre-existing Fast-Refresh advisories Phase 0
found). Unit tests: required, 100% pass, including all new tests for these six features. Integration
tests: **backend-side** integration tests for these six features already exist and pass (159 tests
across Home Automation/Workflow Builder/Recorder alone, from this session's own prior work) — no
new backend integration test is anticipated unless Phase 2 discovers a genuine contract gap (§24).
Playwright: per §16, full suite green including the pre-existing failure's fix.

## 18. Tauri / production build strategy

Read-only verification only in this phase, per instruction — no build performed. Phase 2's build
verification must cover: `npm run build` (Vite production build, already proven to succeed per
Phase 0), `npm run tauri build` (or equivalent) for the Windows Tauri bundle, confirming the version
-consistency test (`tests/unit/test_version_consistency.py`, backend-side) still holds after any
`tauri.conf.json` touch (none anticipated — this contract adds no packaging-relevant configuration),
and a smoke check that the six new routes render inside the actual Tauri shell, not only the Vite
dev server (nothing in this contract's design depends on a Tauri-specific API, so this is a
low-risk confirmation, not a redesign checkpoint). Windows packaging (`packaging/jarvis_installer.iss`,
`packaging/jarvis.spec`) needs no changes — these six features add no new binary, service, or
installer-relevant asset.

## 19. AARYA boundary

No rename performed or designed here. Nothing in this contract's six features introduces a new
"JARVIS"-branded identifier that would need special handling later — page titles/copy for Smart
Home/Automations/Workflow Builder/Recorder are feature names, not brand names, and need no
AARYA-readiness accommodation beyond what already applies app-wide. The known sensitive identifiers
from the Phase 0 audit (`ui.theme` persisted value, `exposed_by_jarvis` MCP field, MCP `server_id`)
are untouched by this contract and remain out of scope entirely.

## 20. Deferred scope — explicitly not touched by this contract

Phase 5A Settings/User Profiles and the backend account model (§22.11, approved-not-built);
advanced window management, DPI/multi-monitor; the Context Menu system; Conversation Timeline; the
formal accessibility audit, cross-platform QA, screen-reader QA; advanced performance optimization
beyond what's already shipped; an Event Viewer (which is specifically what would justify relaying
`DeviceCommandExecutedEvent`/`DeviceStateChangedEvent`/`WorkflowStepEvent`/`ScheduledJobFiredEvent`
— not built here); Smart Home Memory *automation* (as opposed to manual snapshot capture, which
already exists and is untouched); attribute-level/presence/camera automation triggers;
AI-generated workflows; agent-tool recording; raw computer-use recording; advanced workflow
composition (branching, conditionals) beyond the shipped linear step list; a generic raw-connector-
command console (§2.3); per-category device controls (lighting/locks/thermostats/etc. — already
served by their own existing routers, untouched and unduplicated here); the Smart Home module-
enablement UI (§1.3) itself; a dashboard-widget-registry entry for any of these six features.

## 21. Implementation order

Dependencies, not the plausible default ordering, determined the sequence below.

1. **Shared infrastructure, first, because everything else needs it**: the two missing shadcn
   primitives (`select`, `switch` — §1.11) if the step-editor/toggle UI needs them; the five new
   typed API clients (§1.5); a shared step-editor component (kind selector + instruction/tool_name
   field + depends_on/label, §2.4/§2.5's identical step shape) since **Home Automation and Workflow
   Builder share this exact sub-component** — building it twice would be the "duplicate execution
   engine"-flavored mistake this project consistently avoids elsewhere.
2. **Workflow Builder before Home Automation and Recorder**, not after, because both of the other
   two depend on it conceptually and via API (Home Automation creates a dedicated workflow
   internally; Recorder's `stop` delegates to `workflow_builder_service.create_workflow()`) — having
   its real list/detail/run UI and step-editor component built first gives the other two something
   concrete to link to ("Open in Workflow Builder") rather than a placeholder link.
3. **Recorder next** — it is the smallest of the three (no create/edit form, only start/stop/cancel
   plus a preview that reuses Workflow Builder's own step-list rendering, §8), and its "Open in
   Workflow Builder"/"Run now" actions need #2 to already exist to be meaningful.
4. **Home Automation** — needs the shared step editor (#1) and benefits from Workflow Builder's
   list-page conventions already being proven (#2), and is otherwise independent.
5. **Smart Home / Devices / Connectivity** — genuinely independent of #2-4 (different backend
   surface entirely), but ordered after them because it is the only one of the six areas needing new
   WebSocket wiring (§11) and a new credential-bearing form (§5) — more infrastructure work per
   feature than #2-4, better sequenced once the team has already built and proven the shared
   step-editor/mutation-feedback patterns on the simpler three.
6. **Shared execution/history UX polish** — once all four backend-linked list/detail pages exist,
   a pass to make sure execution-history rendering, status badges, and confirmation-dialog copy are
   genuinely shared components, not four near-duplicates.
7. **Playwright regression fix** (§16) — deliberately last among the "real work" items, once new
   e2e coverage for these six features exists, so the fix and the new specs are verified together
   rather than the old failure masking a new one.
8. **Final QA pass** (§17) and **production build verification** (§18) — always last.

## 22. Acceptance criteria

- **Smart Home**: real device/home/room data displayed, created, and updated via the real REST
  API; no mock data anywhere in the production build; `device.updated`/`home.updated` WS events
  trigger a visible refresh.
- **Devices**: pair/refresh/command all call the real `ConnectivityService`; command feedback is
  the synchronous response, never a fabricated state change.
- **Connectivity**: connect/disconnect/discover call the real API; no credential value is ever
  displayed, logged, or echoed after submission.
- **Home Automation**: create/list/detail/enable/disable/delete/run-now/execution-history all
  operate against the real `/api/v1/home-automation` API with no mock fallback.
- **Workflow Builder**: create/list/detail/edit(PATCH)/delete/run-now/execution-history all operate
  against the real `/api/v1/workflows` API, partial-update semantics verified.
- **Recorder**: start/stop(name-required)/cancel/generated-workflow-preview/run-now all operate
  against the real `/api/v1/recordings` API; the "nothing captured" failure path correctly leaves
  the session active.
- **Authentication**: every new feature's REST calls succeed only with a valid session; a 401
  triggers the existing reconnect flow with no feature-specific code.
- **Security**: no client-side authorization bypass exists for any of the six features; every
  mutating action's actual permission is decided by the backend on every call.
- **Testing**: unit tests (new, one suite per feature minimum) green; backend integration tests
  (already existing, 159+) remain green and untouched; typecheck clean; lint clean at the existing
  baseline; full Playwright suite green including the pre-existing regression's fix; production
  build succeeds.

Every item above is objectively verifiable by running the named command/test, not by inspection
alone.

## 23. Security review

- **Unauthorized UI access**: mitigated by construction — no route in this contract renders any
  data without going through `apiRequest`'s existing Bearer-token attachment; a missing/invalid
  session produces the existing 401 → reconnect flow, never a silent fallback to stale or fabricated
  data.
- **Stale sessions**: handled entirely by existing `connection.store.ts`/`installConnectionRecovery()`
  machinery; no feature-specific session logic is added that could diverge from it.
- **Backend permission denial**: always shown to the user via the backend's own message (§13);
  never silently swallowed, never retried with elevated pretend-permission.
- **Command execution** (§2.2/§4): a command's `success: false` outcome is shown as a failure, never
  optimistically treated as success; no state is fabricated from a command acknowledgment alone.
- **Automation/workflow execution** (§2.4/§2.5): `run` always goes through the one shared
  `WorkflowExecutionService`; the frontend has no path to execute a step outside that service, so no
  new execution-related attack surface is introduced.
- **Recorder workflow creation** (§2.6): the dual-scope permission stack (`recorder` +
  `workflow_builder`) is preserved and surfaced, not flattened into a single "recording" permission
  the UI might imply is sufficient on its own.
- **Sensitive connector data** (§5): credentials are write-only from the UI's perspective; nothing
  in this contract introduces a code path that could log, cache, or redisplay one.
- **WebSocket events**: the three events this contract subscribes to (`home.updated`, `device.
  updated`, `connectivity.status_changed`) carry no credential or otherwise sensitive payload data
  per the backend's own event definitions; no new relayed event is added by this contract at all
  (§11), so no new WS-surface risk is introduced.
- **Client-side state manipulation**: no optimistic updates (§9) means there is no client-predicted
  state a malicious or buggy client script could desync from backend truth in a way that persists —
  every view re-derives from the next real fetch.
- **Mock data reaching production**: prevented structurally — this contract adds no mock adapter of
  any kind (§14); there is nothing to accidentally ship enabled.

## 24. Scope / file boundaries

**Primary area**: `2.0-main/frontend/src/features/{smart-home,connectivity,home-automation,
workflow-builder,recorder}/` (new), plus the small, enumerated shared-infrastructure touches:
`services/api/endpoints.ts` (five new client blocks), `services/websocket/types.ts` (two new payload
interfaces), `services/realtime-bridge.ts` (one new subscription block), `routes/router.tsx` /
`routes/lazy-routes.ts` (five new route entries), possibly `components/ui/select.tsx` /
`components/ui/switch.tsx` (new shadcn primitives, if the step-editor/toggle needs them and they
don't already exist by Phase 2).

**Backend changes**: **none assumed necessary.** Every route, payload shape, and permission model
this contract relies on already exists and is already tested (§2). If Phase 2 discovers a genuine
integration blocker — e.g., a payload field this contract assumed exists but doesn't — that is a
signal to stop, report the discrepancy, and seek explicit approval for a scoped backend change,
never to silently patch the backend mid-frontend-implementation.

**`Jarvis-Frontend-main`**: remains completely untouched by Phase 2 unless a separate, explicit
instruction authorizes otherwise.

## 25. Documentation requirements

After Phase 2 implementation (not now): `README.md`, `docs/MASTER_ROADMAP.md`, `docs/
IMPLEMENTATION_ROADMAP.md`, `CHANGELOG.md` must be updated to record that Smart Home/Devices/
Connectivity/Home Automation/Workflow Builder/Recorder UI shipped in the authoritative production
frontend, superseding the "placeholder route"/"hasn't been built yet" status this audit found.
**Explicit rule, stated for the record**: `Jarvis-Frontend-main`'s own requirements/reference
documents (`docs/CORE_*_CONTRACT_REQUIRED.md` etc.) are not automatically copied into this
repository's documentation — any contract fact worth carrying over must be re-derived from this
document's own §2, which was independently, freshly verified against real backend source, not
inherited from that repo's own unverified assumptions.

## 26. Process notes / git safety

This document was authored under a strict read-only constraint: no source file in either repository
was modified while researching or writing it. See the accompanying completion report for the
recorded before/after git state of both repositories.
