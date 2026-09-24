# M7 EventBus Tier 1 — Device Command Events — Frontend Requirements

**Status: planning/specification document only. Contains zero frontend
source code.** Derived exclusively from the shipped, fully-tested
backend implementation (`src/jarvis/services/connectivity_service.py`,
`src/jarvis/core/events/events.py`) and its authoritative Logic
Contract (`docs/M7_EVENTBUS_DEVICE_COMMAND_EVENTS_LOGIC_CONTRACT.md`),
written after the backend's full regression and quality gates all
passed. No frontend implementation accompanies this file, and none is
authorized by it. Nothing under `frontend/` was read, inspected, or
modified to produce this document.

## 1. Backend capability summary

**SHIPPED BACKEND CAPABILITY**: `ConnectivityService.send_command()`
now publishes a `DeviceCommandExecutedEvent` on the in-process
`EventBus` for every device command it routes, whether that call
originated from a REST route, an agent tool, or a scheduled step.
**NOT SHIPPED, and out of scope for this document to design**: any
frontend surface that consumes this event. There is currently no
WebSocket relay entry for it and no REST endpoint that lists past
command events — see §3.

## 2. There is nothing for the frontend to build yet

Unlike the M7 Scheduler MVP's own frontend requirements doc (which
mapped seven real, callable REST endpoints to seven required frontend
surfaces), this document has no such mapping to offer. Tier 1 is
*purely* an internal, backend-side observability primitive at this
point:

- **No REST endpoint exposes `DeviceCommandExecutedEvent` data.**
  Nothing under `/api/v1/` lists, filters, or paginates past command
  events — none was built, and building one is future Event Viewer
  work, not Tier 1.
- **No WebSocket relay entry exists for it.** The event is
  deliberately absent from `EVENT_TYPE_NAMES` in
  `core/lifecycle/runtime_ws_hub.py` (present instead in
  `UNPUBLISHED_EVENT_TYPES`, alongside `IntegrationConnectionTestEvent`
  and its siblings) — a live frontend WebSocket subscriber has no way
  to receive this event today, by design, per the Logic Contract's
  own §17/§20.
- **No UI element in this codebase (existing or planned) references
  device command history.** This document's own search of the backend
  surface found nothing to map, because nothing has been exposed.

**Consequently: this document's purpose is to describe what a future
Event Viewer's *device-command* panel would need from the backend,
not to hand the frontend team a build list.** The single actionable
item here is item §5.

## 3. What Event Viewer would need before it could show anything

For a future Developer Tools "Event Viewer" (already named as Tier
1's own intended eventual consumer, per the Logic Contract §17, and
not part of this task group) to display device command history, at
least two backend capabilities would need to exist first, neither of
which this task group built:

1. **A relay entry.** `DeviceCommandExecutedEvent` would need to move
   from `UNPUBLISHED_EVENT_TYPES` into `EVENT_TYPE_NAMES` — the
   documented "5 surfaces" change (`CLAUDE.md`): the dataclass, the
   relay dict, the frontend's generated WS contract
   (`event-contract.generated.json`), `types.ts`'s `RELAYED_EVENTS`,
   and the four pinned vocabulary tests. None of this was done here,
   deliberately — see the Logic Contract §17.
2. **A query surface**, since `EventBus` itself has zero persistence
   (Logic Contract §13, verified directly from source) — a live
   WebSocket relay only shows events that fire *while the panel is
   open*. Anything resembling command *history* (not just a live
   feed) requires Event Viewer to bring its own storage decision, which
   this task group explicitly did not make.

## 4. What a live feed alone (without history) could offer, if built later

If only item 1 above were done (relay wired, no persistence added),
a frontend "live device activity" panel could show, per event,
exactly the fields the backend publishes and nothing more:
`device_id`, `home_id`, `room_id`, `device_type`, `connector_type`,
`command`, `success`, `detail`, plus the base `id`/`occurred_at`. No
raw command payload is available to show — see §5's warning — and no
correlation identifier exists to group a burst of events back to one
originating user action (Logic Contract §11: deliberately not
introduced in Tier 1).

## 5. The one thing worth flagging now, for whoever builds this later

**A device command's `detail` field is the connector's own free-text
outcome summary (`CommandResult.detail`) — it is not guaranteed
translated, localized, or written for end-user display.** It is a
developer/diagnostic string (e.g. `"fake rejection"` in this task
group's own test fixtures; a real connector's equivalent would be
whatever HA/MQTT itself reports). A future Event Viewer showing this
field verbatim is showing internal diagnostic text, which is
appropriate for its stated audience (Developer Tools) but would need
its own presentation decision if ever surfaced anywhere end-user
facing — a decision this document does not make, since no such
surface exists yet.

## Summary classification

| Item | Classification |
|---|---|
| `DeviceCommandExecutedEvent` published from `ConnectivityService.send_command()` | SHIPPED BACKEND CAPABILITY |
| REST endpoint listing/filtering past command events | BACKEND CAPABILITY NOT AVAILABLE — not part of Tier 1 |
| WebSocket relay entry (`EVENT_TYPE_NAMES`) | BACKEND CAPABILITY NOT AVAILABLE, by design — deferred until a real consumer exists (Logic Contract §17) |
| Any frontend UI surface for device command history | FRONTEND IMPLEMENTATION NOT STARTED — nothing to build against yet |
| Persisted command history (beyond a live feed) | BACKEND CAPABILITY NOT AVAILABLE — `EventBus` is non-persistent by design; a future consumer must bring its own storage decision |
| `detail` field end-user presentation | UNDECIDED — flagged for whoever eventually builds a consumer, not resolved here |
