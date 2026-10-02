# M7 EventBus Tier 2 — Device State-Changed Event — Frontend Requirements

**Status: planning/specification document only. Contains zero frontend
source code.** Derived exclusively from the shipped, fully-tested
backend implementation (`src/jarvis/services/smart_home_service.py`,
`src/jarvis/core/events/events.py`) and its authoritative Logic
Contract (`docs/M7_EVENTBUS_DEVICE_STATE_CHANGED_LOGIC_CONTRACT.md`),
written after the backend's full regression and quality gates all
passed. No frontend implementation accompanies this file, and none is
authorized by it. Nothing under `frontend/` was read, inspected, or
modified to produce this document.

## 1. Backend capability summary

**SHIPPED BACKEND CAPABILITY**: `SmartHomeService.
report_device_state()` now publishes a `DeviceStateChangedEvent` on
the in-process `EventBus` whenever a device's generic lifecycle status
(`discovered`/`pairing`/`paired`/`offline`/`unreachable`/`removed`)
genuinely transitions — never on a same-value refresh. **NOT
shipped, and out of scope for this document to design**: any frontend
surface that consumes this event, and any per-category attribute
state (brightness, temperature, etc. — this event never carries
those). There is no WebSocket relay entry for it and no REST endpoint
that lists past state transitions.

## 2. There is nothing new for the frontend to build against this event specifically

Matching Tier 1's own frontend-requirements precedent exactly:

- **No REST endpoint exposes `DeviceStateChangedEvent` data.** Nothing
  under `/api/v1/` lists or filters past state transitions.
- **No WebSocket relay entry exists for it.** The event is
  deliberately absent from `EVENT_TYPE_NAMES`
  (`core/lifecycle/runtime_ws_hub.py`), present instead in
  `UNPUBLISHED_EVENT_TYPES` — a live frontend subscriber has no way to
  receive it today, by design.
- **This is distinct from `DeviceUpdatedEvent`**, which *is* already
  relayed today (`"device.updated"`) and is completely unaffected by
  this slice — any frontend surface currently reacting to
  `device.updated` (if one exists) continues to work exactly as
  before, receiving the same events at the same frequency it always
  has. This slice adds no new relayed signal for any existing consumer
  to pick up.

## 3. What a future Event Viewer would need before it could show anything

Same two prerequisites as Tier 1, neither built here:

1. **A relay entry** — moving `DeviceStateChangedEvent` from
   `UNPUBLISHED_EVENT_TYPES` into `EVENT_TYPE_NAMES`, the documented
   "5 surfaces" change (dataclass, relay dict, generated WS contract,
   `types.ts`'s `RELAYED_EVENTS`, the four pinned vocabulary tests).
2. **A query surface**, since `EventBus` has zero persistence — a
   relay alone only shows transitions that fire while a panel is open,
   never history.

## 4. What a live feed alone (relay wired, no persistence) could offer, if built later

Exactly the seven domain fields the backend publishes and nothing
more: `device_id`, `home_id`, `room_id`, `device_type`,
`connector_type`, `previous_status`, `status` (plus base `id`/
`occurred_at`). No raw connector attribute is available to show — this
event is scoped to lifecycle status only (§1) — and no correlation
identifier exists to group a transition back to whatever triggered it
(a manual refresh, a future scheduled check, etc.).

## 5. The one thing worth flagging now, for whoever builds this later

**This event and `DeviceUpdatedEvent` will coexist**, and any future
consumer needs to understand the difference: `device.updated`
(already relayed) fires on *every* `report_device_state`/`pair_device`/
`update_device`/`delete_device` call regardless of whether anything
actually changed (a pre-existing, documented, not-fixed-by-this-slice
characteristic — see the Logic Contract §6); `DeviceStateChangedEvent`
(not yet relayed) fires *only* on a genuine lifecycle-status
transition. A future Event Viewer wanting an honest "this device's
status actually changed" timeline should prefer
`DeviceStateChangedEvent` once relayed, not `device.updated` — using
the latter for that purpose would show false transitions on every
no-op refresh.

## Summary classification

| Item | Classification |
|---|---|
| `DeviceStateChangedEvent` published from `SmartHomeService.report_device_state()` | SHIPPED BACKEND CAPABILITY |
| REST endpoint listing/filtering past state transitions | BACKEND CAPABILITY NOT AVAILABLE — not part of this slice |
| WebSocket relay entry (`EVENT_TYPE_NAMES`) | BACKEND CAPABILITY NOT AVAILABLE, by design — deferred until a real consumer exists |
| Any frontend UI surface for device state-transition history | FRONTEND IMPLEMENTATION NOT STARTED — nothing to build against yet |
| Existing `device.updated` WebSocket relay behavior | UNCHANGED — this slice adds no coupling to it and modifies no existing consumer's experience |
| Per-category attribute state events (brightness/temperature/etc.) | BACKEND CAPABILITY NOT AVAILABLE — explicitly out of this slice's scope, blocked on future state-normalization work |
