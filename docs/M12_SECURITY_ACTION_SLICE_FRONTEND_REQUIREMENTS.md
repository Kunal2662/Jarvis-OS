# M12 Security & Safety — Manual Action Slice — Frontend Requirements

**Status: planning/specification document only. Contains zero frontend
source code.** Derived exclusively from the shipped, fully-tested
backend implementation (`src/jarvis/services/security_service.py`,
`src/jarvis/infrastructure/api/routes/security.py`) and its
authoritative Logic Contract (`docs/
M12_SECURITY_ACTION_SLICE_LOGIC_CONTRACT.md`), written after the
backend's full regression, targeted tests, and quality gates all
passed. No frontend implementation accompanies this file, and none is
authorized by it.

## 1. Backend capability summary

**SHIPPED BACKEND CAPABILITY**: two synchronous, on-demand, home-scoped
actions — **Panic Mode** (lock every lock, turn on every light) and
**Vacation Mode** (lock every lock, turn off every light, best-effort
eco-adjust every capable thermostat). Both require an explicit,
confirmed trigger; neither runs automatically, on a schedule, or in
response to any condition.

## 2. Panic Mode UI entry point

A single action the user (or an agent, with confirmation) can invoke
for one home — conceptually a button/menu item on whatever screen
already shows that home's security status (the read-only slice's own
existing aggregate). No configuration exists to accept beyond *which
home* — there is no "lock only these rooms" or "skip these lights"
option in this MVP.

## 3. Vacation Mode UI entry point

Same shape as Panic Mode — one action, one home, no further
configuration. The UI should not imply anything the backend doesn't
do: no date range, no "how long will I be away" input, no schedule —
this is a **one-shot** action, not a mode that persists (see §16/§23).

## 4. Home selection

**BACKEND CAPABILITY AVAILABLE**: `home_id` is a required field on
both endpoints (§5) — there is no "all homes" or default-home
behavior; the frontend must always resolve and pass a specific
`home_id`, sourced from whatever home-selection UI the app already
has for other Smart Home features. An unknown `home_id` is a 404 (§9)
— the frontend should treat this as a real error state, not something
that can happen from normal navigation (it would indicate stale
client-side home data).

## 5. API endpoints

| Endpoint | Method | Body |
|---|---|---|
| `/api/v1/security/panic-mode` | `POST` | `{"home_id": string}` |
| `/api/v1/security/vacation-mode` | `POST` | `{"home_id": string}` |

Both require the same `Authorization: Bearer <session_id>` header
every other authenticated call in the app already sends. Neither
endpoint has a corresponding `GET` — there is no stored/queryable
"last panic mode result"; each call's response **is** the only record
of what happened (see §21 — no persistence exists).

## 6. Request payload

Exactly one field, always required:

```json
{ "home_id": "home_abc123" }
```

Omitting `home_id` is a **422** (Pydantic-level rejection, before the
backend even attempts anything) — the frontend should never construct
this request without a home_id already resolved.

## 7. Response schema

Both endpoints return the identical shape inside the standard
`{data, meta}` envelope:

```ts
{
  home_id: string;
  mode: "panic" | "vacation";
  status: "SUCCESS" | "PARTIAL_SUCCESS" | "FAILED" | "NO_TARGETS";
  locks: Array<{ device_id: string; name: string; success: boolean; detail: string }>;
  lights: Array<{ device_id: string; name: string; success: boolean; detail: string }>;
  thermostats: Array<{
    device_id: string; name: string;
    success: boolean | null;   // null when skipped or unavailable -- never attempted
    detail: string;
    skipped: boolean;
    skip_reason: string | null;
  }>;
  requested_count: number;
  attempted_count: number;
  succeeded_count: number;
  failed_count: number;
  unavailable_count: number;
  skipped_count: number;
  generated_at: string;   // ISO 8601 UTC
}
```

`thermostats` is always `[]` for Panic Mode — the backend never
touches thermostats for that action (verified by a source-level test
in the backend suite). `meta.status` mirrors `data.status`, provided
for callers that only need the top-line outcome.

## 8. Overall operation status

Four values, mutually exclusive, computed deterministically by the
backend — the frontend should render each distinctly, not collapse
them to a single pass/fail:

- **`SUCCESS`** — every device found was attempted and every attempt
  succeeded.
- **`PARTIAL_SUCCESS`** — a real mix: some devices succeeded, others
  failed or were unavailable.
- **`FAILED`** — at least one device was found, but zero succeeded.
- **`NO_TARGETS`** — the home has no locks/lights (and, for Vacation
  Mode, no thermostats either) at all. This is not an error.

## 9. Per-device results

Every lock and light found is represented exactly once, in exactly
one of: succeeded (`success: true`), failed (`success: false`, `detail`
explains why), or unavailable (`success: false`, `detail: "device
unavailable"`). Thermostats (Vacation Mode only) add a third outcome,
skipped (§12). **The frontend must render `detail` or a faithful
paraphrase of it for every non-success entry** — collapsing everything
to a generic "failed" loses real, backend-provided information (a
permission problem reads very differently from a device simply being
offline).

## 10. Successful devices

`success: true` entries. No further backend-side detail beyond
`device_id`/`name` — the frontend already has richer device
information (room, type) from the app's existing device list/detail
views if it wants to cross-reference.

## 11. Failed devices

`success: false` entries where `detail` is **not** `"device
unavailable"`. Common real causes surfaced verbatim in `detail`: a
missing nested permission grant (`core:smart_locks`/
`core:smart_lighting`/`core:thermostats` not granted — a distinct
concern from this action's own `core:security` grant, see §20), a
device with no recorded connector, or a genuine wire-command failure
reported by the connector.

## 12. Unavailable devices

`success: false`, `detail: "device unavailable"` — the device was
never sent a command at all (its last-known connectivity status was
offline/unreachable). The frontend should visually distinguish this
from a genuine failed *attempt* (§11) — "we didn't try, because it
was already known to be offline" is a different, less alarming state
than "we tried and it rejected the command."

## 13. Skipped devices (Vacation Mode thermostats only)

`skipped: true`, `skip_reason: "device does not report an
eco-adjacent hvac_mode"`, `success: null`. **This is expected,
common, and not a failure** — most real thermostats will land here
today (the backend's eco-detection only recognizes a device-reported
`hvac_mode` literally named `"eco"`, which many real integrations
expose as a separate `preset_mode` this backend does not read — see
Logic Contract §5). The frontend should present skipped thermostats
neutrally ("no eco mode available on this device"), not as an error.

## 14. Partial-success presentation

**FRONTEND IMPLEMENTATION REQUIRED**: when `status ===
"PARTIAL_SUCCESS"`, the UI must show *which* devices succeeded and
*which* didn't (§9–§13) — never a bare "partially worked" message with
no detail. The counts (`succeeded_count`/`failed_count`/
`unavailable_count`/`skipped_count`) are cheap to render as a
one-line summary above the per-device breakdown.

## 15. Total-failure presentation

`status === "FAILED"` means zero devices succeeded, but the response
is still a normal `200` — the frontend must not treat this as an HTTP
error or a broken request. Render it as "nothing succeeded" with the
same per-device detail as partial success, since the *reason* every
device failed (e.g., a missing nested grant) is exactly the
actionable information the user needs.

## 16. Empty-home behavior

`status === "NO_TARGETS"` (also a normal `200`) means the home has no
eligible devices at all. This is meaningfully different from `FAILED`
— nothing went wrong, there was simply nothing to do. Recommended
copy: "No locks or lights found in this home" (Vacation Mode: "...or
thermostats"), not any failure-toned message.

## 17. Loading/progress state

Not a backend concern — this is a single synchronous request/response;
the backend has no notion of incremental progress across devices (it
does not stream partial results). A home with many devices may take
longer proportionally, so a simple indeterminate loading state is
appropriate; there is no API for a progress bar with per-device ticks.

## 18. Error handling

| Condition | HTTP | Frontend treatment |
|---|---|---|
| No/invalid session | 401/403 | Standard auth-expired flow |
| `core:security` not granted | 400, `detail` contains "permission" | Direct the user to grant permission (existing generic plugin-permission flow) |
| Unknown `home_id` | 404 | Treat as a real error — stale client state |
| Missing `home_id` in body | 422 | A frontend bug if this ever fires — the request should never be built without one |
| Any `status` value in a 200 | — | Not an error — render per §8–§16 |

## 19. Recommended safety UX

**FRONTEND IMPLEMENTATION REQUIRED, recommended not mandated**: because
both actions affect every lock/light (and, for Vacation Mode, every
eco-capable thermostat) in an entire home at once, the frontend should
present a clear pre-action confirmation naming the home and the scope
("This will lock every door and turn on every light in {home
name}") — distinct from and in addition to the backend's own
interactive-agent confirmation requirement (§20), since a direct
UI button click doesn't go through the agent's confirmation channel at
all. This is a UX recommendation grounded in the Logic Contract's own
"large blast radius" reasoning for why these actions require agent
confirmation in the first place (Action Slice Logic Contract §11) —
the same reasoning applies to a direct button, which has no agent
confirmation step to rely on.

## 20. Permission/confirmation expectations

**Permission**: both actions require the `smart_home` scope granted to
`core:security` — the same grant the existing read-only Security
dashboard already needs, no new grant surface for the frontend to
build. **Confirmation**: is enforced at the **agent** layer
(`AgentSettings.confirm_required_tools`) for the `trigger_panic_mode`/
`trigger_vacation_mode` **tools** specifically — this has no direct
REST equivalent; a frontend calling the REST endpoints directly is not
subject to that mechanism at all and must supply its own confirmation
step if it exposes a direct button (§19). The frontend should not
assume the backend will reject an unconfirmed direct REST call — it
won't; confirmation is an agent-invocation concept, not a REST-layer
gate.

## 21. Backend capability not available

None of the following exist server-side; a frontend must not render
controls or copy implying they do:

- Scheduled or recurring Panic/Vacation Mode
- Randomized presence simulation
- Geofencing or occupancy-triggered activation
- Emergency alerts, SMS, email, or push notifications of any kind
- Siren or alarm-panel integration
- Camera/vision integration of any kind
- A "cancel/undo" action once a trigger has been sent (no atomicity is
  claimed — see §15/§23)
- A history or log of past Panic/Vacation Mode invocations (§21
  heading is intentional — no persistence exists at all; each
  response is the only record)
- Any configuration of *which* devices participate — always "every
  lock/light" (and eco-capable thermostat) in the home, never a subset

## 22. Frontend API-client requirements

**FRONTEND IMPLEMENTATION REQUIRED** (described, not built here): two
typed client functions (`triggerPanicMode(homeId)`,
`triggerVacationMode(homeId)`), following whatever pattern the app's
existing Security dashboard client already uses for `GET .../status`.
Must not add client-side defaults for `home_id` (§4/§6) and must not
retry automatically on `PARTIAL_SUCCESS`/`FAILED` — those are
successful HTTP responses describing a real outcome, not something a
client-side retry would fix.

## 23. Explicitly deferred (must not be represented as implemented)

Scheduling, randomization, notifications, sirens, cameras, presets/
temperature fallback for thermostats, multi-home orchestration, scenes,
user-defined routines, automatic remediation, and emergency-service
integration — none of these exist in the shipped backend (Action Slice
Logic Contract §12) and none should appear in any future frontend as
if they do.

## Summary classification

| Item | Classification |
|---|---|
| `POST .../panic-mode`, `POST .../vacation-mode` | SHIPPED BACKEND CAPABILITY |
| Agent tools (`trigger_panic_mode`, `trigger_vacation_mode`) | SHIPPED BACKEND CAPABILITY (agent-facing, not a frontend concern) |
| Any Panic/Vacation Mode UI entry point, confirmation dialog, or result display | FRONTEND IMPLEMENTATION REQUIRED (not started, not scoped beyond this document) |
| Scheduling, notifications, sirens, cameras, geofencing, history/log of past triggers | BACKEND CAPABILITY NOT AVAILABLE |
| Direct-REST-call confirmation UX (§19) | FRONTEND IMPLEMENTATION DEFERRED pending a real product decision — the backend's own confirmation mechanism does not cover this path |
