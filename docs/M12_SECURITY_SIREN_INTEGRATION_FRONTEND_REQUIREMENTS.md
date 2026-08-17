# M12 Security & Safety — Siren Integration Slice — Frontend Requirements

**Status: planning/specification document only. Contains zero frontend
source code.** Derived exclusively from the shipped, fully-tested
backend implementation (`src/jarvis/services/siren_service.py`,
`src/jarvis/infrastructure/api/routes/sirens.py`) and its authoritative
Logic Contract (`docs/M12_SECURITY_SIREN_INTEGRATION_LOGIC_CONTRACT.md`),
written after the backend's full regression, targeted tests, and
quality gates all passed. No frontend implementation accompanies this
file, and none is authorized by it.

## 1. Backend capability summary

**SHIPPED BACKEND CAPABILITY**: read (list/get) and control (turn
on/turn off) for sirens discovered under the generic `device_type:
"other"` bucket and identified by HA domain/MQTT component `"siren"`.
A siren has exactly one controllable attribute — on/off — with no
tone/duration/volume/pattern control in this MVP.

## 2. Sirens list UI

A filterable list (by home, optionally by room — same filter shape the
app's other device-category lists already use), one row per siren:
name, room, on/off state, availability. No live poll is required by
the backend for the list endpoint itself (§7) — if the UI wants live
state per row it must call the detail endpoint per device (§3), the
same list/detail asymmetry every other M12 device-category screen
already has.

## 3. Siren detail / control UI

One siren's live on/off state plus two explicit actions — "Turn On"
and "Turn Off" — never a single toggle switch that silently branches
to one endpoint or the other client-side, since the two directions
carry different confirmation requirements (§19/§20) and a toggle
control obscures which one is about to fire.

## 4. Home/room selection

**BACKEND CAPABILITY AVAILABLE**: `home_id`/`room_id` are optional
query filters on `GET /sirens` only — omitting both returns every
siren across every home the session can see. The frontend should still
default to the currently-selected home in whatever home-selection UI
the app already uses for other Smart Home screens, matching existing
list behavior elsewhere.

## 5. API endpoints

| Endpoint | Method | Body |
|---|---|---|
| `/api/v1/sirens` | `GET` | — (`home_id`/`room_id` optional query params) |
| `/api/v1/sirens/{device_id}` | `GET` | — |
| `/api/v1/sirens/{device_id}/turn_on` | `POST` | — (no body) |
| `/api/v1/sirens/{device_id}/turn_off` | `POST` | — (no body) |

All four require the same `Authorization: Bearer <session_id>` header
every other authenticated call in the app already sends. Neither
mutation endpoint accepts a body — there is no tone/duration/volume
parameter to pass (§21).

## 6. List response schema

Inside the standard `{data, meta}` envelope, `data` is an array of:

```ts
{
  id: string;
  home_id: string;
  room_id: string | null;
  name: string;
  status: string;        // last-known DB device status, not live on/off
  manufacturer: string;
  model: string;
  external_id: string | null;
  on: boolean | null;    // always null on the list endpoint -- see §7
  available: boolean;    // always false on the list endpoint -- see §7
}
```

`meta.count` is the row count. This is the same shape as the detail
endpoint (§7) so the frontend can reuse one row-rendering component,
but `on`/`available` are not meaningful on list rows (§7).

## 7. Detail response schema and the list/detail asymmetry

`GET /sirens/{id}` returns the identical shape, but `on`/`available`
reflect a real, current connector read attempted at request time:
`available: false` when the connector could not be reached (backend
falls back to last-known DB fields, `on: null`); `available: true` with
`on: true|false` when a live read succeeded. **The frontend must not
treat `on`/`available` from the list endpoint as real state** — call
the detail endpoint per siren for anything the UI actually renders as
current on/off, the same list/detail split `SmartLockService`'s own
frontend contract already establishes.

## 8. Turn on / turn off response schema

Both mutation endpoints return, inside `{data, meta}`:

```ts
{
  device_id: string;
  success: boolean;
  detail: string;
}
```

`meta.success` mirrors `data.success` for callers that only need the
top-line outcome. A `200` response with `success: false` is a normal,
expected outcome (e.g. the connector reported the command failed) —
**not** an HTTP error; the frontend must render `detail` in that case,
never a generic "action failed" with no explanation.

## 9. Turn-on confirmation UX (agent path)

**Confirmation is enforced at the agent layer only**
(`AgentSettings.confirm_required_tools` includes `turn_siren_on`, not
`turn_siren_off`) — this has no direct REST equivalent. A frontend
calling `POST .../turn_on` directly is not subject to that mechanism
at all; the backend will not reject an unconfirmed direct REST call.

## 10. Recommended direct-UI confirmation for turn-on

**FRONTEND IMPLEMENTATION REQUIRED, recommended not mandated**: because
turning a siren on is loud, disruptive, and can draw an unwanted
emergency response (the same reasoning the Logic Contract §10 used to
gate the agent tool), a direct "Turn On" button should present its own
confirmation step ("Turn on {siren name}? This is loud and may alert
neighbors.") before calling the endpoint — mirroring
`unlock_device`'s own established UX precedent for the same
asymmetry. "Turn Off" needs no such step; it is always the safe
direction and should remain a single click.

## 11. Loading/progress state

Not a backend concern — both mutation endpoints are single synchronous
request/response calls with no streamed progress. A simple
indeterminate loading state on the button being pressed is sufficient.

## 12. Error handling

| Condition | HTTP | Frontend treatment |
|---|---|---|
| No/invalid session | 401/403 | Standard auth-expired flow |
| `core:sirens` `smart_home` scope not granted | 400, `detail` contains "permission" | Direct the user to grant permission (existing generic plugin-permission flow) |
| Unknown `device_id`, or device is not a siren | 404 on `GET .../{id}`; 400 on either mutation | Treat as a real error — stale client-side device data |
| Device has no recorded connector / unsupported connector type | 400, `detail` explains why | Render `detail` verbatim; this is a configuration problem, not something a retry fixes |
| `success: false` in a 200 mutation response | — | Not an HTTP error — render per §8 |

## 13. Permission expectations

Both mutations require the `smart_home` scope granted to
`core:sirens` — a distinct principal from every other device-category
service's own principal (`core:smart_locks`, `core:smart_switches`,
...). Reads (list/get) require no grant at all. The frontend's
existing generic plugin-permission grant flow covers this with no new
UI pattern — same as every other M12 device-category service.

## 14. Backend capability not available

None of the following exist server-side; a frontend must not render
controls or copy implying they do:

- Tone, duration, or volume-level control (`siren.turn_on`'s own
  optional HA parameters are never sent — see Logic Contract §11)
- Flashing/strobe or any pattern selection
- A merged "set state" call — always two explicit actions (§3)
- Any coupling to Panic Mode, Vacation Mode, or an alarm control panel
  (`alarm_control_panel` domain devices are not sirens and are not
  discovered by this slice)
- A history or log of past siren activations — each mutation response
  is the only record of what happened, nothing is persisted
- Scheduled or automatic siren activation of any kind
- Push/SMS/email notification when a siren is triggered

## 15. Frontend API-client requirements

**FRONTEND IMPLEMENTATION REQUIRED** (described, not built here): four
typed client functions (`listSirens(homeId?, roomId?)`,
`getSirenState(deviceId)`, `turnSirenOn(deviceId)`,
`turnSirenOff(deviceId)`), following whatever pattern the app's
existing Smart Locks client already uses. Must not add a client-side
merged "set state" helper (§14) and must not auto-retry a
`success: false` mutation result.

## 16. Explicitly deferred (must not be represented as implemented)

Tone/duration/volume control, flashing patterns, alarm-panel
integration, Panic/Vacation Mode coupling, scheduled activation,
activation history/logging, and any notification on trigger — none of
these exist in the shipped backend (Logic Contract §11/§16) and none
should appear in any future frontend as if they do.

## Summary classification

| Item | Classification |
|---|---|
| `GET /sirens`, `GET /sirens/{id}`, `POST .../turn_on`, `POST .../turn_off` | SHIPPED BACKEND CAPABILITY |
| Agent tools (`list_sirens`, `get_siren_state`, `turn_siren_on`, `turn_siren_off`) | SHIPPED BACKEND CAPABILITY (agent-facing, not a frontend concern) |
| Sirens list/detail UI, turn-on/turn-off controls, turn-on confirmation dialog | FRONTEND IMPLEMENTATION REQUIRED (not started, not scoped beyond this document) |
| Tone/duration/volume/pattern control, alarm-panel integration, Panic/Vacation Mode coupling, activation history, notifications | BACKEND CAPABILITY NOT AVAILABLE |
| Direct-REST-call turn-on confirmation UX (§10) | FRONTEND IMPLEMENTATION DEFERRED pending a real product decision — the backend's own confirmation mechanism does not cover this path |
