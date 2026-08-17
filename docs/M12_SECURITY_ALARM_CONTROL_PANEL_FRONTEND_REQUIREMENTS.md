# M12 Security & Safety — alarm_control_panel Integration Slice — Frontend Requirements

**Status: planning/specification document only. Contains zero frontend
source code.** Derived exclusively from the shipped, fully-tested
backend implementation
(`src/jarvis/services/alarm_control_panel_service.py`,
`src/jarvis/infrastructure/api/routes/alarm_control_panels.py`) and its
authoritative Logic Contract
(`docs/M12_SECURITY_ALARM_CONTROL_PANEL_LOGIC_CONTRACT.md`), written
after the backend's full regression, targeted tests, and quality gates
all passed. No frontend implementation accompanies this file, and none
is authorized by it.

## 1. Backend capability summary

**SHIPPED BACKEND CAPABILITY**: read (list/get) and control (arm_home,
arm_away, disarm) for alarm control panels discovered under the
generic `device_type: "other"` bucket and identified by HA domain/MQTT
component `"alarm_control_panel"`. **No PIN/code entry exists anywhere
in this capability, permanently** — every action is sent as a bare
command; a code-protected panel will report the action failed rather
than accept a code (§9).

## 2. Alarm control panels list UI

A filterable list (by home, optionally by room — same filter shape the
app's other device-category lists already use), one row per panel:
name, room, and availability. **The list endpoint never returns a
live `state`** (§7) — if the UI wants to show a panel's current
arm/disarm state in the list it must call the detail endpoint per
device, the same list/detail asymmetry every other M12 device-category
screen already has.

## 3. Alarm control panel detail / control UI

One panel's live state (rendered from the closed ten-value vocabulary
in §6) plus three explicit actions — "Arm (Home)", "Arm (Away)", and
"Disarm" — never a single toggle, since the three actions carry
different confirmation requirements (§10/§11) and a toggle control
cannot represent three distinct target states. **No code/PIN entry
field of any kind** — the UI must not present one, even as an optional
field (§9).

## 4. Home/room selection

**BACKEND CAPABILITY AVAILABLE**: `home_id`/`room_id` are optional
query filters on `GET /alarm-control-panels` only — omitting both
returns every panel across every home the session can see. The
frontend should still default to the currently-selected home in
whatever home-selection UI the app already uses for other Smart Home
screens, matching existing list behavior elsewhere.

## 5. API endpoints

| Endpoint | Method | Body |
|---|---|---|
| `/api/v1/alarm-control-panels` | `GET` | — (`home_id`/`room_id` optional query params) |
| `/api/v1/alarm-control-panels/{device_id}` | `GET` | — |
| `/api/v1/alarm-control-panels/{device_id}/arm_home` | `POST` | — (no body) |
| `/api/v1/alarm-control-panels/{device_id}/arm_away` | `POST` | — (no body) |
| `/api/v1/alarm-control-panels/{device_id}/disarm` | `POST` | — (no body) |

All five require the same `Authorization: Bearer <session_id>` header
every other authenticated call in the app already sends. **No mutation
endpoint accepts a body of any kind** — there is no code/PIN parameter
to pass, structurally, not merely unfilled (§9).

## 6. State vocabulary

`state` (on the detail response only, §7) is one of exactly ten
verbatim Home Assistant values, or `null` when unrecognized/
unavailable — the frontend must not invent additional values or
collapse these into a simpler set without a real product decision:

```
disarmed | armed_home | armed_away | armed_night | armed_vacation |
armed_custom_bypass | pending | arming | disarming | triggered
```

**Only `armed_home`/`armed_away`/`disarmed` are reachable through this
slice's own actions** (§1) — `armed_night`/`armed_vacation`/
`armed_custom_bypass`/`pending`/`arming`/`disarming`/`triggered` can
only ever be observed if the panel entered them through some means
outside this slice (e.g. a physical keypad, or another HA automation)
and are read-only here. The frontend should render each of the ten
values with a distinct, legible label but must not offer a control
that targets any state this slice cannot command.

## 7. Detail response schema and the list/detail asymmetry

`GET /alarm-control-panels/{id}` returns:

```ts
{
  id: string;
  home_id: string;
  room_id: string | null;
  name: string;
  status: string;              // last-known DB device status, not live state
  manufacturer: string;
  model: string;
  external_id: string | null;
  state: string | null;        // one of §6's ten values, or null -- see below
  available: boolean;
}
```

`available: false` when the connector could not be reached (backend
falls back to last-known DB fields, `state: null`); `available: true`
with `state` set to a recognized value, or `state: null` if the
connector reported a status this slice's closed vocabulary (§6) does
not recognize — this is not an error, just an honestly-unmapped
reading. `GET /alarm-control-panels` (the list endpoint) returns the
identical shape, but **`state` is always `null` and `available` is
always `false` on list rows** — no live connector read is attempted
per row. **The frontend must not treat `state`/`available` from the
list endpoint as real state** — call the detail endpoint per panel for
anything the UI actually renders as current arm/disarm state, the same
list/detail split `SirenService`'s own frontend contract already
establishes.

## 8. Action response schema

All three mutation endpoints return, inside `{data, meta}`:

```ts
{
  device_id: string;
  success: boolean;
  detail: string;
}
```

`meta.success` mirrors `data.success` for callers that only need the
top-line outcome. A `200` response with `success: false` is a normal,
expected outcome — **including the expected outcome for a
code-protected panel that rejects a bare command** (§9) — never an
HTTP error; the frontend must render `detail` in that case, never a
generic "action failed" with no explanation, and should specifically
consider surfacing "this panel may require a code JARVIS does not
support" as a possible cause when `success: false` comes back from an
otherwise-healthy connector.

## 9. No PIN/code support — mandatory frontend messaging

**BACKEND CAPABILITY NOT AVAILABLE, permanently, not a deferred gap.**
No endpoint, agent tool, or wire command in this slice accepts a code
or PIN of any kind (Logic Contract §8/§11). The frontend:

- must never render a code/PIN entry field anywhere in this feature;
- must never imply, in copy or UI affordance, that a code can be
  provided later or through a different flow;
- should surface a clear, honest message when an action fails on a
  panel that appears to require a code (e.g. "This panel could not be
  armed/disarmed. If it requires a code, JARVIS does not support
  entering one — use the panel or its own app directly.").

## 10. Disarm confirmation UX (agent path)

**Confirmation is enforced at the agent layer only**
(`AgentSettings.confirm_required_tools` includes `disarm`, not
`arm_home`/`arm_away`) — this has no direct REST equivalent. A
frontend calling `POST .../disarm` directly is not subject to that
mechanism at all; the backend will not reject an unconfirmed direct
REST call.

## 11. Recommended direct-UI confirmation for disarm

**FRONTEND IMPLEMENTATION REQUIRED, recommended not mandated**: because
disarming removes protection (the same reasoning the Logic Contract
§12 used to gate the agent tool), a direct "Disarm" button should
present its own confirmation step ("Disarm {panel name}? This removes
protection.") before calling the endpoint — mirroring
`turn_siren_on`'s/`unlock_device`'s own established UX precedent for
the same asymmetry. "Arm (Home)" and "Arm (Away)" need no such step;
both are always the safe direction and should remain single-click.

## 12. Loading/progress state

Not a backend concern — all three mutation endpoints are single
synchronous request/response calls with no streamed progress
(`pending`/`arming`/`disarming` in §6 are states the panel itself may
report, not something this slice's own request lifecycle exposes). A
simple indeterminate loading state on the button being pressed is
sufficient; polling the detail endpoint after a mutation is a
reasonable way to observe a transitional state resolve, at whatever
interval the app's existing polling conventions use elsewhere.

## 13. Error handling

| Condition | HTTP | Frontend treatment |
|---|---|---|
| No/invalid session | 401/403 | Standard auth-expired flow |
| `core:alarm_control_panels` `smart_home` scope not granted | 400, `detail` contains "permission" | Direct the user to grant permission (existing generic plugin-permission flow) |
| Unknown `device_id`, or device is not an alarm control panel | 404 on `GET .../{id}`; 400 on any of the three actions | Treat as a real error — stale client-side device data |
| Device has no recorded connector / unsupported connector type | 400, `detail` explains why | Render `detail` verbatim; this is a configuration problem, not something a retry fixes |
| `success: false` in a 200 action response | — | Not an HTTP error — render per §8/§9 |

## 14. Permission expectations

All three mutations require the `smart_home` scope granted to
`core:alarm_control_panels` — a distinct principal from every other
device-category service's own principal (`core:sirens`,
`core:smart_locks`, ...). Reads (list/get) require no grant at all.
The frontend's existing generic plugin-permission grant flow covers
this with no new UI pattern — same as every other M12 device-category
service.

## 15. Backend capability not available

None of the following exist server-side; a frontend must not render
controls or copy implying they do:

- A code/PIN field anywhere, ever (§9) — the single most important
  item on this list
- Arm modes other than home/away (`arm_night`, `arm_vacation`,
  `arm_custom_bypass`) — these can only ever appear as a *read-only*
  observed `state` (§6), never as a command this slice can issue
- A `trigger`/panic-style forced-alarm action
- Any coupling to Siren, Panic Mode, or Vacation Mode — arming/
  disarming a panel never turns a siren on or off, and Panic/Vacation
  Mode never touch a panel
- A history or log of past arm/disarm events — each action response is
  the only record of what happened, nothing is persisted
- Scheduled or automatic arm/disarm of any kind
- Push/SMS/email notification on any state change (including
  `triggered`)

## 16. Frontend API-client requirements

**FRONTEND IMPLEMENTATION REQUIRED** (described, not built here): five
typed client functions (`listAlarmControlPanels(homeId?, roomId?)`,
`getAlarmControlPanelState(deviceId)`, `armHome(deviceId)`,
`armAway(deviceId)`, `disarm(deviceId)`), following whatever pattern
the app's existing Siren client already uses. Must not add a
code/PIN parameter to any of these signatures (§9) and must not
auto-retry a `success: false` mutation result.

## 17. Explicitly deferred (must not be represented as implemented)

Code/PIN support (permanent, not deferred — §9), night/vacation/
custom-bypass arm modes, a trigger action, arm/disarm history or
logging, Siren/Panic/Vacation Mode coupling, scheduled arm/disarm, and
any notification on state change — none of these exist in the shipped
backend (Logic Contract §21) and none should appear in any future
frontend as if they do.

## Summary classification

| Item | Classification |
|---|---|
| `GET /alarm-control-panels`, `GET .../{id}`, `POST .../arm_home`, `POST .../arm_away`, `POST .../disarm` | SHIPPED BACKEND CAPABILITY |
| Agent tools (`list_alarm_control_panels`, `get_alarm_control_panel_state`, `arm_home`, `arm_away`, `disarm`) | SHIPPED BACKEND CAPABILITY (agent-facing, not a frontend concern) |
| Alarm control panel list/detail UI, three action controls, disarm confirmation dialog | FRONTEND IMPLEMENTATION REQUIRED (not started, not scoped beyond this document) |
| Code/PIN entry (any form) | BACKEND CAPABILITY NOT AVAILABLE, permanently — must never be built |
| Night/vacation/custom-bypass arm modes, trigger action, arm/disarm history, Siren/Panic/Vacation coupling, notifications | BACKEND CAPABILITY NOT AVAILABLE |
| Direct-REST-call disarm confirmation UX (§11) | FRONTEND IMPLEMENTATION DEFERRED pending a real product decision — the backend's own confirmation mechanism does not cover this path |
