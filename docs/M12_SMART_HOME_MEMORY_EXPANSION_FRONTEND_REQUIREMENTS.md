# M12 Smart Home Memory — Device-Category Expansion Slice — Frontend Requirements

**Status: planning/specification document only. Contains zero frontend
source code.** Derived exclusively from the shipped, fully-tested
backend implementation (`src/jarvis/services/smart_home_memory_service.py`,
`src/jarvis/infrastructure/api/routes/smart_home_memory.py`) and its
authoritative Logic Contract (`docs/
M12_SMART_HOME_MEMORY_EXPANSION_LOGIC_CONTRACT.md`), written after the
backend's full regression, targeted tests, and quality gates all
passed. No frontend implementation accompanies this file, and none is
authorized by it.

## 1. Backend capability summary

**SHIPPED BACKEND CAPABILITY**: the Task Group O manual/on-demand
device-snapshot capability (light/switch/thermostat) now extends to
six more categories (fan, cover, vacuum, humidifier, media player,
water heater) — nine total — plus two new operations: single-snapshot
deletion and a home-wide snapshot that captures every supported device
in one home in a single call. Sensor and Smart Lock snapshots remain
permanently excluded on privacy/security grounds; this is unchanged
from Task Group O and not something a future frontend should imply is
coming.

## 2. Supported device categories for the snapshot UI

Nine categories now show a "Snapshot this device" action wherever the
app already renders a device card: Light, Switch, Thermostat (existing
since Task Group O), plus Fan, Cover, Vacuum, Humidifier, Media
Player, Water Heater (new). Sensor and Lock device cards must **not**
show this action — attempting the underlying call for either returns
the same `UnsupportedSnapshotCategoryError` as any other unsupported
category (§9).

## 3. Snapshot list / detail UI (unchanged shape, wider coverage)

Same list view as Task Group O's own frontend note: device name,
`snapshot_at`, a short state summary. Now simply shows rows for nine
device categories instead of three — no new UI pattern, only wider
applicability of the existing one.

## 4. Delete affordance

**FRONTEND IMPLEMENTATION REQUIRED**: a delete control (e.g. a trash
icon) on each row of the snapshot list, calling
`DELETE /snapshots/{memory_id}`. No confirmation dialog is required by
the backend (§13), but a lightweight "are you sure" is a reasonable
UX choice for any destructive action — this is a frontend judgment
call, not a backend requirement.

## 5. Home-wide snapshot UI entry point

**FRONTEND IMPLEMENTATION REQUIRED**: a single action, conceptually
"Snapshot this home," on whatever screen already shows a home's device
list — calls `POST /snapshots/home/{home_id}` with no body beyond the
path parameter. No per-device selection UI is needed or supported;
the backend always attempts every supported-category device in the
home (§10).

## 6. API endpoints

| Endpoint | Method | Body |
|---|---|---|
| `/api/v1/smart-home/memory/snapshots` | `POST` | `{"device_id": string}` |
| `/api/v1/smart-home/memory/snapshots` | `GET` | `?device_id=&limit=` |
| `/api/v1/smart-home/memory/snapshots/{memory_id}` | `DELETE` | — |
| `/api/v1/smart-home/memory/snapshots/home/{home_id}` | `POST` | — |

All four require the same `Authorization: Bearer <session_id>` header
every other authenticated call already sends.

## 7. Delete response schema

```json
{ "memory_id": "string", "deleted": true }
```

## 8. Home-wide snapshot response schema

```ts
{
  home_id: string;
  requested_count: number;
  attempted_count: number;
  succeeded_count: number;
  failed_count: number;
  skipped_count: number;
  results: Array<{
    device_id: string;
    device_name: string;
    device_type: string;
    outcome: "succeeded" | "failed" | "skipped";
    memory_id: string | null;
    detail: string | null;
  }>;
  generated_at: string;   // ISO 8601 UTC
}
```

`meta.succeeded_count` mirrors `data.succeeded_count`, provided for
callers that only need the top-line outcome.

## 9. Per-device outcome presentation (home-wide)

Mirrors Panic/Vacation Mode's own established rule: **the frontend
must render `results` per device, never collapse it to a single
pass/fail message.** Three outcomes, rendered distinctly:

- **`succeeded`** — a snapshot was created; `memory_id` is set.
- **`skipped`** — the device's category isn't supported (a sensor, a
  lock, a camera, an "other"-bucket device). This is expected and
  normal for any home with those devices present — render it
  neutrally ("not supported for snapshotting"), never as a failure.
- **`failed`** — a genuine, unexpected error (e.g. a persistence
  failure); `detail` explains why. Render this distinctly from
  `skipped` — it's a real problem, not an expected exclusion.

## 10. Home-wide summary presentation

The four counts (`requested_count`/`succeeded_count`/`failed_count`/
`skipped_count`) are cheap to render as a one-line summary above the
per-device breakdown — e.g. "12 devices found, 8 snapshotted, 4 not
supported." `attempted_count` (`succeeded_count + failed_count`) is
mainly useful for a progress-style "8 of 8 attempted succeeded"
framing if the UI wants it.

## 11. Empty-home / zero-device behavior

A home with no devices at all returns `requested_count: 0` and an
empty `results` array — a normal `200`, not an error. Recommended
copy: "No devices found in this home," not any failure-toned message.

## 12. Loading/progress state

Not a backend concern — home-wide snapshot is a single synchronous
request/response; the backend does not stream partial results as it
processes each device (§10 of the Logic Contract: sequential, no
concurrency, but no incremental progress API either). A home with many
devices may take longer proportionally; a simple indeterminate loading
state is appropriate.

## 13. Error handling

| Condition | HTTP | Frontend treatment |
|---|---|---|
| No/invalid session | 401/403 | Standard auth-expired flow |
| `core:smart_home_memory` not granted | 400, `detail` contains "permission" | Direct the user to grant permission (existing generic plugin-permission flow) |
| Unsupported device category (create) | 400, `detail` contains "only supported for" | Should not be reachable from the UI if §2's category gating is respected client-side; treat as a stale client-state bug if it fires |
| Unknown device/home | 404 | Treat as a real error — stale client-side data |
| Unknown/already-deleted/non-snapshot memory id (delete) | 404 | Treat as "this snapshot no longer exists" — refresh the list rather than surfacing a scary error |
| Any outcome inside a 200 home-wide response | — | Not an error — render per §9/§10 |

## 14. Permission/confirmation expectations

**Permission**: all four operations (create, retrieve, delete,
home-wide) require the same `smart_home` scope grant to
`core:smart_home_memory` — no new grant surface, no per-operation
distinction for the frontend to build. **Confirmation**: no operation
in this slice is gated by the agent-layer `confirm_required_tools`
mechanism — a direct UI delete button needs no special confirmation
handling beyond whatever the frontend chooses for its own UX (§4).

## 15. Backend capability not available

None of the following exist server-side; a frontend must not render
controls or copy implying they do:

- Sensor or Smart Lock snapshots, in any form
- Snapshot deletion at device-wide or home-wide scope — only
  single-snapshot deletion exists
- Scheduled or automatic snapshots of any kind
- Diff/trend/comparison views between snapshots
- AI-generated snapshot summaries or descriptions
- A "cancel" action mid-home-wide-snapshot — it is a single
  synchronous call with no cancellation API

## 16. Frontend API-client requirements

**FRONTEND IMPLEMENTATION REQUIRED** (described, not built here): two
new typed client functions (`deleteDeviceSnapshot(memoryId)`,
`snapshotHome(homeId)`), extending whatever pattern the app's existing
`createSnapshot`/`listSnapshots` clients already use. Must not add a
device-wide or home-wide delete client function (§15).

## 17. Explicitly deferred (must not be represented as implemented)

Sensor/Lock snapshots, bulk/scoped deletion beyond single-snapshot,
scheduled snapshots, automatic/event-driven history, diff/trend
views, AI-generated summaries — none of these exist in the shipped
backend (Expansion Logic Contract §27) and none should appear in any
future frontend as if they do.

## Summary classification

| Item | Classification |
|---|---|
| `POST`/`GET .../snapshots`, `DELETE .../snapshots/{id}`, `POST .../snapshots/home/{id}` | SHIPPED BACKEND CAPABILITY |
| Agent tools (`snapshot_device_state`, `list_device_snapshots`, `delete_device_snapshot`, `snapshot_home`) | SHIPPED BACKEND CAPABILITY (agent-facing, not a frontend concern) |
| Snapshot UI on 6 new appliance-category device cards, delete affordance, home-wide snapshot action, per-device outcome display | FRONTEND IMPLEMENTATION REQUIRED (not started, not scoped beyond this document) |
| Sensor/Lock snapshots, bulk deletion, scheduled snapshots, diff/trend views, AI-generated summaries | BACKEND CAPABILITY NOT AVAILABLE |
