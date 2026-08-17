# M12 Appliance Control — Water Heater — Frontend Requirements

**Status: planning/specification document only. Contains zero frontend
source code.** Derived exclusively from the shipped backend
implementation (`src/jarvis/services/water_heater_service.py`,
`src/jarvis/infrastructure/api/routes/water_heaters.py`) and its
authoritative Logic Contract (`docs/
M12_APPLIANCE_WATER_HEATER_LOGIC_CONTRACT.md`), verified against the
real backend regression before this document was written. No frontend
implementation accompanies this file, and none is authorized by it.

This document does not itself commit to a frontend timeline. It exists
so that whenever frontend work on Water Heater begins, it starts from
the backend's real, verified contract rather than from assumption.

## 1. Backend capability summary

**SHIPPED BACKEND CAPABILITY**: read water heater state (list + one
device's live detail); mutate on/off, operation mode, and target
temperature via one merged endpoint. Reads require no permission grant;
the mutation requires an operator-granted permission. No other
capability exists server-side for this device category.

## 2. API endpoints exposed to the frontend

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/appliances/water-heaters` | List all water heaters (last-known DB state only). |
| `GET /api/v1/appliances/water-heaters/{id}` | One device's live state. |
| `POST /api/v1/appliances/water-heaters/{id}/state` | Merged mutation: temperature, operation mode, on/off. |

No other Water Heater route exists. **FRONTEND IMPLEMENTATION
DEFERRED / NOT APPLICABLE**: any UI implying a fourth endpoint (e.g. a
dedicated `/turn_on` button wired to its own call) would be
misrepresenting the API — there is no such route.

## 3. HTTP methods

`GET` for both read routes. `POST` for the mutation route (not `PATCH`
— matches every other M12 appliance module's convention). All three
require `Authorization: Bearer <session_id>` (`Depends(
get_current_session)`), identical to every other resource route in
this codebase.

## 4. Request payloads

Only the mutation route accepts a body:

```json
{
  "temperature": 55.0,
  "operation_mode": "eco",
  "on": true
}
```

All three fields are **optional individually**, but **at least one is
required** — an empty object (`{}`) is rejected with HTTP 400. Any
subset (one, two, or all three) is valid. Field names are exactly
`temperature` (number), `operation_mode` (string), `on` (boolean) — no
other field is accepted or has any effect.

## 5. Response envelope

Every response uses the standard `{data, meta}` envelope this codebase
uses everywhere:

```json
{ "data": { ... }, "meta": { ... } }
```

`GET /water-heaters` → `data`: array of normalized objects (§6);
`meta`: `{"count": <int>}`. `GET /water-heaters/{id}` → `data`: one
normalized object; `meta`: `{}`. `POST .../state` → `data`:
`{"device_id": str, "success": bool, "detail": str}`; `meta`:
`{"success": bool}` (mirrors `data.success`, provided for callers that
only inspect `meta`).

## 6. Normalized Water Heater state

Exact shape returned by both `GET` routes:

```ts
{
  id: string;
  home_id: string;
  room_id: string | null;
  name: string;
  status: string;
  manufacturer: string;
  model: string;
  external_id: string | null;
  available: boolean;
  state: string | null;
  is_on: boolean | null;
  current_temperature: number | null;
  target_temperature: number | null;
  operation_mode: string | null;
  operation_list: string[];
  min_temp: number | null;
  max_temp: number | null;
}
```

This is the **entire** field set. No field beyond this list exists on
the backend today.

## 7. Availability behavior

`available: boolean` reflects whether the device is currently
reachable. When `false`, every live-reading field (`state`, `is_on`,
`current_temperature`, `target_temperature`, `operation_mode`) is
`null` — **the backend never fabricates a value for an unavailable
device.** `operation_list`, `min_temp`, `max_temp` are the three
exceptions: they represent the device's declared *capability*, not a
live reading, and **do survive unavailability** (they stay populated
if the device previously reported them, `[]`/`null` otherwise). The
frontend must render capability fields (e.g. a temperature slider's
bounds) even while a device shows unavailable, but must never invent a
live reading in that state.

## 8. Current temperature

`current_temperature: number | null`. `null` whenever unreported,
unparseable, or the device is unavailable. **No unit is reported by
the API** — the number is whatever unit the device/connector uses
internally (§4 of the Logic Contract: no conversion is performed
anywhere in the backend). The frontend cannot determine Celsius vs.
Fahrenheit from this API alone; see §22/§24.

## 9. Target temperature

`target_temperature: number | null`, same null/unit rules as §8. This
is also the value the mutation endpoint's `temperature` field sets —
read and write share the same unit and the same "no fabricated value"
rule.

## 10. Operation mode

`operation_mode: string | null` — an **open, backend-unvalidated
vocabulary** (e.g. `"eco"`, `"electric"`, `"gas"`, `"heat_pump"`,
`"high_demand"`, or a plain `"on"`/`"off"` token on devices that only
support on/off — see Logic Contract §7). The frontend must **never**
hardcode a fixed list of operation modes to render as options — it
must always render whatever the specific device's own `operation_list`
(§11) reports. `null` when unavailable or unreported.

## 11. Operation list

`operation_list: string[]` — the device's own declared set of valid
operation-mode values, already lowercased by the backend. `[]` when the
device reports none — in that case, per Logic Contract §6, the backend
accepts **any** non-empty string as a mode (permissive, connector is
the authority). The frontend should therefore treat an empty
`operation_list` as "no dropdown constraint available," not as "no
modes exist" — a free-text or best-effort input is more correct than a
disabled control in that case, though the disabled-control simplicity
is also a defensible UI choice; this document does not mandate one.

## 12. Minimum/maximum temperature

`min_temp` / `max_temp: number | null` — the device's own reported
bounds, in the same unreported unit as §8/§9. `null` when the device
reports neither. **The backend enforces these bounds server-side only
when both are present**; it never invents a default range. **The
frontend must not invent one either** — if both are `null`, no client-
side range validation should be applied beyond basic numeric-input
sanity (see §22).

## 13. On/off state

Two related fields: `state` (raw, open pass-through string — see
§10-adjacent note: on a device that only supports on/off, `state` and
`operation_mode` will be identical, both equal to `"on"`/`"off"`) and
`is_on: boolean | null` — a **derived convenience field**, `true`/
`false` only when `state` is a recognized on/off token, `null`
otherwise (including when the device is mid-operation-mode, e.g.
`"eco"` — an operation mode being reported does not by itself prove
power state). The mutation endpoint's `on` field is a plain boolean;
sending it issues a `turn_on`/`turn_off`-equivalent command
server-side. **The frontend must not assume every device exposes
on/off control** — the Logic Contract records this as HA's own
`ON_OFF` feature flag being optional, not universal; a `set_water_heater_state`
call with `on` set against a device that doesn't support it will
report `success: false` from the backend, not a local validation error.

## 14. Mutation behavior

`POST .../state` is the **only** mutation entry point. It accepts any
non-empty combination of `temperature`/`operation_mode`/`on`. Server-
side, the backend issues **up to three sequential wire calls**, in a
fixed order: on/off, then operation mode, then temperature. This
ordering has **no UI implication** the frontend needs to reproduce —
the frontend simply submits whichever fields the user changed in one
request; the backend owns call sequencing entirely.

## 15. Permission/error behavior

Reads (`GET`) require no permission grant. The mutation (`POST
.../state`) requires the `smart_home` scope granted to principal
`core:water_heaters` — if not granted, the endpoint returns **HTTP
400** with a message containing `"permission"`. The frontend should
surface this distinctly from a validation error (§16) since the
resolution is different (grant permission via the existing generic
plugin-permission flow, not "fix your input") — see §29.

## 16. Validation/error states

| Condition | HTTP status | Notes |
|---|---|---|
| Unknown device id (`GET`) | 404 | |
| Wrong device type / wrong appliance domain (`GET`) | 404 | A fan/cover/vacuum/humidifier/media-player/thermostat id passed here 404s, not 400. |
| Empty mutation body (`POST`) | 400 | |
| Invalid field type (e.g. `temperature` not numeric) at the HTTP layer | 422 | Pydantic schema rejection, before the service layer runs. |
| Invalid value the service layer rejects (out-of-bounds temperature, unsupported operation mode, non-boolean `on`) | 400 | |
| Permission not granted | 400 | |
| Unavailable device, otherwise valid request | 200 | Not an error — see §7/§18. |
| Partial mutation failure (some but not all wire calls succeeded) | 200, `data.success: false` | Not an HTTP error — see §19. |

## 17. Loading states

Not a backend concern — the API has no notion of "loading"; it is a
synchronous request/response contract. The frontend owns whatever
loading/skeleton/spinner behavior it wants around these calls; this
document does not prescribe one.

## 18. Unavailable/offline states

A `GET` on an unavailable device returns **HTTP 200**, not an error —
`available: false` with every live field `null` (§7). The frontend
must render this as a distinct, legible "unavailable" state (not as a
generic error, and not by hiding the device) — this is normal,
expected backend behavior, not a failure.

## 19. Partial-failure behavior

A combined mutation (e.g. `on` + `operation_mode` + `temperature`
together) can partially succeed: the backend stops at the first wire
call that fails and reports `success: false` with a `detail` string
**naming exactly which calls already applied** (e.g. `"set_operation_mode
failed (...); already applied: turn_on."`). This is a normal, honest
**200** response, not an exception. **FRONTEND IMPLEMENTATION
REQUIRED**: the UI must surface `detail` verbatim or a faithful
paraphrase — it must never claim full success when `success` is
`false`, and it must never claim nothing happened when part of the
`detail` says otherwise.

## 20. UI actions the frontend will eventually need

- List water heaters (by home/room).
- View one device's live state.
- Set target temperature.
- Set operation mode (from the device's own `operation_list` when
  non-empty).
- Turn on/off.
- Submit any combination of the three above in one action (matching
  the backend's own single merged endpoint — three separate "Save"
  buttons calling the same endpoint three times would work but is not
  required by the API shape).

No other action exists to build against.

## 21. UI information that should be displayed

Device name, room, availability, current temperature, target
temperature, operation mode (and the modes available for this specific
device), on/off state, and — when relevant to the interaction — the
device's own `min_temp`/`max_temp` as input bounds.

## 22. Fields that MUST NOT be fabricated

- **Temperature unit** (°C vs. °F vs. K) — the API does not report
  one. The frontend must not assume a unit; if a unit label is shown,
  it must be sourced from somewhere the frontend controls explicitly
  (e.g. a user/app-level display preference), never presented as if
  the backend confirmed it.
- **Temperature bounds** when `min_temp`/`max_temp` are both `null` —
  do not substitute a guessed range (e.g. "0–100").
- **Operation modes** when `operation_list` is `[]` — do not render a
  hardcoded mode list.
- **On/off support** — do not assume every device has it; the backend
  reports failure (`success: false`), not a capability flag, when it
  doesn't.
- **Device availability** — never show a device as available/
  reachable based on cached frontend state after a failed or
  unanswered request; only the backend's own `available` field is
  authoritative.

## 23. Deferred backend capabilities that MUST NOT be represented as implemented UI

None of the following exist server-side. A frontend that renders
controls or displays for these would be showing functionality that
silently does nothing or errors:

- Away/vacation mode
- Dual/secondary setpoint (`target_temperature_high`/`_low`)
- Scheduling or automation of any kind
- Energy usage history, cost dashboards, or optimization
- Predictive/AI control or recommendations
- Multi-device orchestration or scenes involving this device
- Leak detection or safety alerting
- Notifications
- Advanced heating profiles or multi-zone control
- Any Smart Kitchen functionality
- Any confirmation/interactive-approval step before a mutation is sent
  (the backend deliberately does not require one — see Logic Contract
  §11)

## 24. Frontend API-client requirements

**FRONTEND IMPLEMENTATION REQUIRED** (described, not built here): a
typed client function per endpoint (list, get, set-state), following
whatever pattern the existing frontend already uses for sibling
modules (Thermostat, Media Player, Vacuum/Humidifier) once those exist
in the frontend — this document does not prescribe a new pattern
distinct from siblings. The client must pass the `Authorization`
header the same way every other authenticated call in the app already
does. It must not add client-side defaults for any field this document
marks as "must not be fabricated" (§22).

## 25. Frontend TypeScript/domain-model requirements

A domain type mirroring §6's shape exactly (field names and
nullability unchanged) is the minimum requirement. It should not widen
`operation_mode`/`state` to a union of known literal strings — both
are backend-open-vocabulary strings (§10), and a closed TypeScript
union would misrepresent that and require ongoing maintenance the
backend contract explicitly avoids.

## 26. Suggested component responsibilities

(Suggested, not mandated — no component exists yet.) A list view
consuming `GET /water-heaters`; a detail/card view consuming `GET
/water-heaters/{id}` and rendering §21's fields with §18's
unavailable-state handling; a control surface (however composed)
that collects a subset of temperature/operation_mode/on and submits
one `POST .../state` call, then displays the result per §19.

## 27. Suggested state-management requirements

Whatever the frontend's existing pattern is for other device
categories should be reused — this document does not introduce a new
state-management requirement specific to Water Heater. The one
Water-Heater-specific note: because `operation_list` and `min_temp`/
`max_temp` survive unavailability while other fields do not (§7),
any local cache/store must preserve that same asymmetry rather than
clearing the entire record when a device goes unavailable.

## 28. Accessibility requirements

No requirement specific to this device category beyond the app's
existing accessibility baseline. A temperature input and a mode
selector are standard form controls; no water-heater-specific
interaction pattern is implied by the backend contract.

## 29. Error/feedback requirements

Per §15/§16/§19: permission errors, validation errors, not-found, and
partial-mutation-failure must each be distinguishable to the user —
collapsing all four into one generic "Something went wrong" message
would lose information the backend already provides (a specific
`detail` string in every case).

## 30. Future integration/testing requirements

Once a frontend implementation exists, its own tests should verify
against this document's §6 shape and §16 status-code table using the
real backend (or a contract-accurate fixture) — not a shape invented
independently of the backend. This document should be revisited
(not silently left stale) if the backend's Water Heater contract ever
changes.

## Summary classification

| Item | Classification |
|---|---|
| List/get/mutate REST endpoints | SHIPPED BACKEND CAPABILITY |
| Agent tools (`list_water_heaters`, `get_water_heater_state`, `set_water_heater_state`) | SHIPPED BACKEND CAPABILITY (not a frontend concern — consumed by the agent, not the UI) |
| Any Water Heater frontend page/component/card | FRONTEND IMPLEMENTATION REQUIRED (not started, not scoped by this document beyond §26) |
| Away mode, dual setpoint, scheduling, energy analytics, predictive control, scenes, leak/safety alerting, notifications, multi-zone, Smart Kitchen | BACKEND CAPABILITY NOT AVAILABLE — must not appear in any future frontend as if implemented |
| Temperature unit display, bound-fallback UI, hardcoded mode lists | FRONTEND IMPLEMENTATION DEFERRED pending a real product decision — explicitly not backend-sourced (§22) |
