# M12 Appliance Control — Fan Percentage + Cover Position Slice — Frontend Requirements

**Status: planning/specification document only. Contains zero frontend
source code.** Derived exclusively from the shipped, fully-tested
backend implementation (`src/jarvis/services/appliance_service.py`,
`src/jarvis/infrastructure/api/routes/appliances.py`) and its
authoritative Logic Contract (`docs/
M12_APPLIANCE_FAN_COVER_POSITION_LOGIC_CONTRACT.md`), written after the
backend's full regression, targeted tests, and quality gates all
passed. No frontend implementation accompanies this file, and none is
authorized by it.

## 1. Backend capability summary

**SHIPPED BACKEND CAPABILITY**: fan speed percentage control
(`set_fan_percentage`) and cover position control (`set_cover_position`),
each 0-100, added to the already-shipped Core Appliance Slice
(on/off for fans, open/close for covers, unchanged). Both are new,
standalone operations — never merged into the existing on/off/open/
close controls.

## 2. Fan percentage UI

**FRONTEND IMPLEMENTATION REQUIRED**: a slider or stepper (0-100) on
each fan's device card, alongside the existing on/off toggle — not a
replacement for it. Calls `POST /api/v1/appliances/fans/{id}/set_percentage`
with `{"percentage": N}`. `0` is a valid, selectable value; the UI
should not special-case it as "off" — it is sent to the device
literally, and what the device does with it is device-dependent (some
treat it as off, some ignore it — this is Home Assistant's own
documented ambiguity, not something the frontend can resolve).

## 3. Cover position UI

**FRONTEND IMPLEMENTATION REQUIRED**: a slider (0-100, 0=closed,
100=open) on each cover's device card, alongside the existing open/
close buttons — not a replacement for them. Calls
`POST /api/v1/appliances/covers/{id}/set_position` with
`{"position": N}`.

## 4. Reading current percentage/position

`GET /api/v1/appliances/fans/{id}` now includes a `percentage` field
(`int | null`); `GET /api/v1/appliances/covers/{id}` now includes a
`position` field (`int | null`). Both are `null` when the device is
unavailable or does not report/support that attribute — the frontend
should render this as "not available," never as `0`. As with every
other M12 device-category screen, only the detail (`GET .../{id}`)
endpoint reports live values — the list endpoints
(`GET /api/v1/appliances/fans`, `GET /api/v1/appliances/covers`) remain
DB-only and do not include a meaningful `percentage`/`position` value.

## 5. API endpoints

| Endpoint | Method | Body |
|---|---|---|
| `/api/v1/appliances/fans/{device_id}/set_percentage` | `POST` | `{"percentage": 0-100}` |
| `/api/v1/appliances/covers/{device_id}/set_position` | `POST` | `{"position": 0-100}` |

Both require the same `Authorization: Bearer <session_id>` header
every other authenticated call already sends. Existing endpoints
(`/on`, `/off`, `/open`, `/close`, and both `GET` routes) are
completely unchanged.

## 6. Response schema

Identical shape to every other appliance mutation:

```json
{ "device_id": "string", "success": true, "detail": "string" }
```

A `200` response with `success: false` is a normal, expected outcome
(the connector reported the command failed) — not an HTTP error; the
frontend must render `detail`, never a generic "action failed."

## 7. Validation and error handling

| Condition | HTTP | Frontend treatment |
|---|---|---|
| No/invalid session | 401/403 | Standard auth-expired flow |
| `core:appliances` `smart_home` scope not granted | 400, `detail` contains "permission" | Direct the user to grant permission (existing generic plugin-permission flow) |
| `percentage`/`position` outside 0-100 | 400, `detail` contains "0-100" | Client-side range validation on the slider/stepper avoids this in normal use; treat a 400 here as a real bug if the UI's own bounds are respected |
| Unknown device, or device is not a fan/cover | 400 | Treat as a real error — stale client-side device data |
| `success: false` in a 200 response | — | Not an HTTP error — render `detail` |

## 8. Permission/confirmation expectations

**Permission**: same `smart_home` scope grant to `core:appliances`
every existing fan/cover control already requires — no new grant
surface. **Confirmation**: neither `set_fan_percentage` nor
`set_cover_position` is gated by the agent-layer
`confirm_required_tools` mechanism (same as the existing on/off/open/
close tools) — a direct UI slider needs no special confirmation
handling.

## 9. Backend capability not available

None of the following exist server-side; a frontend must not render
controls or copy implying they do:

- Fan oscillation or preset/speed-list modes
- Cover tilt control
- A `stop_cover` action
- Scheduled or automatic percentage/position changes
- Historical percentage/position charts or trends
- Notifications on percentage/position change

## 10. Frontend API-client requirements

**FRONTEND IMPLEMENTATION REQUIRED** (described, not built here): two
new typed client functions (`setFanPercentage(deviceId, percentage)`,
`setCoverPosition(deviceId, position)`), following whatever pattern the
app's existing `fanOn`/`coverOpen` clients already use. Must not add a
combined "set state" client function merging percentage/position with
on/off (§6 of the Logic Contract — the backend has no such merged
operation).

## 11. Explicitly deferred (must not be represented as implemented)

Fan oscillation/presets, cover tilt, `stop_cover`, scheduling,
automation, historical tracking, notifications — none of these exist
in the shipped backend and none should appear in any future frontend
as if they do.

## Summary classification

| Item | Classification |
|---|---|
| `POST .../fans/{id}/set_percentage`, `POST .../covers/{id}/set_position` | SHIPPED BACKEND CAPABILITY |
| `percentage`/`position` fields on `GET .../fans/{id}` / `GET .../covers/{id}` | SHIPPED BACKEND CAPABILITY |
| Agent tools (`set_fan_percentage`, `set_cover_position`) | SHIPPED BACKEND CAPABILITY (agent-facing, not a frontend concern) |
| Fan percentage slider/stepper, cover position slider on device cards | FRONTEND IMPLEMENTATION REQUIRED (not started, not scoped beyond this document) |
| Fan oscillation/presets, cover tilt, stop, scheduling, history, notifications | BACKEND CAPABILITY NOT AVAILABLE |
