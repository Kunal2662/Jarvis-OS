# M12 Developer Tools — Event Viewer — Logic Contract

Status: **Implemented this session** (Task Group X). Closes the gap
Device Diagnostics' and Device Logs' own Logic Contracts both named
explicitly: "Event Viewer... blocked on the still-unresolved
device-command EventBus publishing gap" — no `EventBus` event existed
anywhere in this codebase naming a device command, because every
device-category service mutates a device by calling
`ConnectivityService.send_command` directly, and that method never
published anything.

## 1. Purpose

A read-only devtools endpoint answering "what device commands has this
system executed recently, across every device and every category?" —
a structured, typed event history, distinct from the Device Logs
slice's own unstructured log-line capture (same underlying moments,
different data shape and different mechanism, per §3).

## 2. Existing architecture

**Finding, re-confirmed this session:** `ConnectivityService.send_command`
is the single chokepoint every one of the eleven device-category
services routes a mutation through (already established during Device
Logs). `ConnectivityService` already holds an optional `EventBus`
(`self._event_bus: EventBus | None`) and already publishes one event
type from it, `ConnectivityStatusChangedEvent`, via a private
`_publish_status` helper — the exact seam this slice extends, not
replaces.

**The relay guard, read in full before designing anything:**
`core/lifecycle/runtime_ws_hub.py` pins a **closed allowlist** of event
classes that are deliberately *not* relayed over the Runtime WebSocket
API, enforced by two duplicate tests
(`test_runtime_ws_hub.py::test_...`, `test_platform_integration.py`):

```python
absent = {cls.__name__ for cls in all_events - set(EVENT_TYPE_NAMES)}
assert absent == {*UNPUBLISHED_EVENT_TYPES, "DebugLogCapturedEvent"}
```

`UNPUBLISHED_EVENT_TYPES` already contains four **published** M11
Integration events (`IntegrationConnectionTestEvent` et al.) with an
explicit, on-the-record reason: "relaying them is a separate,
deliberately deferred decision: wiring a new relayed event also means
regenerating the frontend WS contract and its four pinned tests...
which is a frontend-touching change outside those task groups'
backend-only scope." This is precisely this slice's own situation, not
a new argument invented for it.

## 3. Architecture decision

**A new `DeviceCommandExecutedEvent`, published by `ConnectivityService.
send_command` for every outcome, captured by a new `core/devtools/`
component (`DeviceEventLog`, mirroring `DebugConsole`'s own shape),
exposed read-only over REST. Deliberately added to
`UNPUBLISHED_EVENT_TYPES`, not to `EVENT_TYPE_NAMES` — relay is
explicitly out of scope for this pass, following the exact precedent
above, not a new one.**

Rejected alternatives:

- **Reuse `DebugLogCapturedEvent`/`DebugConsole` instead of a new event
  and component.** Rejected: Device Logs already reuses `DebugConsole`
  for *unstructured log text* filtered by a `device_id` substring match
  — genuinely useful, but it can only ever answer "does this text
  contain that id," never "give me every command for device X as
  structured data," "was this specific attempt a success or a
  rejection" (a typed `bool`, not a string a caller must parse), or
  "how many total commands ran across all devices in this session."
  Event Viewer is named as its own, separate roadmap item precisely
  because it is a different capability, not a rebrand of Debug Console.
- **Relay this event over WebSocket immediately (`EVENT_TYPE_NAMES`).**
  Rejected for this pass, using the codebase's own already-established
  reasoning (§2) verbatim: doing so pulls in `event-contract.generated.json`,
  `types.ts`'s `RELAYED_EVENTS`, and the frontend contract test — every
  M12 Developer Tools slice shipped so far (Device Simulator, Device
  Diagnostics, Device Logs, MQTT Debug Console) has been backend-only,
  frontend deferred; this slice keeps that discipline rather than being
  the first to break it as a side effect of an unrelated feature.
- **Publish from each of the eleven device-category services
  individually.** Rejected for the identical reason Device Logs
  rejected it: one chokepoint, one publish call, not eleven
  near-duplicate ones.

## 4. Event shape

```python
@dataclass(frozen=True, slots=True)
class DeviceCommandExecutedEvent(Event):
    device_id: str = ""
    command: str = ""
    success: bool = False
    detail: str = ""
```

Mirrors `CommandResult`'s own fields (`external_id` renamed `device_id`
to match this event's own audience — a devtools consumer thinks in
`Device.id`, the same id Device Logs' own route already keys on, not a
connector's `external_id`). `payload` is **not** a field on this event
at all, structurally, not filtered out at read time — the same reason
Device Logs never logs it (a lock's own PIN can be in there).

## 5. Publish points (all four `send_command` outcomes)

Same four cases Device Logs' own logging already distinguishes, one
`await self._event_bus.publish(DeviceCommandExecutedEvent(...))` call
added at each, guarded by the same `if self._event_bus is not None`
check `_publish_status` already uses:

1. No recorded connector → `success=False`, `detail="no recorded connector"`.
2. Connector-level failure (`ConnectivityError`) → `success=False`, `detail=str(err)`.
3. `CommandResult.success=True` → `success=True`, `detail=""`.
4. `CommandResult.success=False` → `success=False`, `detail=result.detail`.

## 6. Capture component

`core/devtools/device_event_log.py` — `DeviceEventLog`, structurally
parallel to `DebugConsole` (`start()`/`stop()`/`entries()`/`clear()`/
`is_running`/`__len__`) but simpler: it subscribes directly to the
in-process `EventBus` (`EventBus.subscribe` calls handlers synchronously
on the publishing coroutine's own task — no loguru sink, no background
thread, no `enqueue=True` cross-thread cost `DebugConsole`'s own
docstring documents paying). `entries(*, device_id=None, limit=200)`
filters by device id and returns most-recent-first, matching
`DebugConsole.entries`'s own convention.

**Gated by settings, on by default.** `settings.devtools.
device_event_log_enabled: bool = True` (new field on the existing
`DevToolsSettings`), matching `debug_console_enabled`'s own documented
posture: "a developer-facing, opt-out-if-you-must tool, not a hardened
production data path." `device_event_log_max_entries: int = 200`.
Registered as a `RuntimeManager` startup/shutdown hook in `app.py`,
directly alongside (not replacing) Debug Console's own hook
registration, at the same priority band (observability hooks bookend
the sequence).

## 7. REST endpoint

```
GET /api/v1/devtools/events?device_id=...&limit=200
DELETE /api/v1/devtools/events
```

Lives in `routes/devtools.py`, grouped with Debug Console/Live Logs (the
structurally closest sibling capability), before the Connectivity
Health section. Response shape mirrors `get_debug_logs` exactly:
`{data, meta}`, `data` = tuple of `{at, device_id, command, success,
detail}`, `meta = {"count": ..., "running": device_event_log.is_running}`.
`DELETE` clears the buffer, matching `DELETE /devtools/logs`'s own
existing precedent. No `PermissionModel` gate — session auth only,
matching every devtools capability in this router; this data is no more
sensitive than Device Logs' own already-shipped, already-ungated
per-device command outcome text.

## 8. Error semantics

| Condition | Behavior |
|---|---|
| `device_event_log_enabled=False` | 200, always empty `data`, `meta.running: false` — same shape `get_debug_logs` returns when `DebugConsole` was never started |
| No commands sent yet | 200, empty `data` — not an error |
| Unknown `device_id` filter value | 200, empty `data` — this route does not validate the device exists (unlike Device Logs' own `/devices/{id}/logs`, which 404s); an event-history query naturally allows "nothing happened for this id," including a typo, without that being an error |
| Malformed request | N/A — no path parameter, two optional query params, ordinary FastAPI handling |
| Unexpected internal failure | Propagates as a genuine 500 |

## 9. Agent tool decision

**None.** No conversational use case for raw devtools event history —
matches every prior M12 devtools capability's identical reasoning.

## 10. Relay / frontend / database / schema

**None of the four**, all deliberately, per §3: no `EVENT_TYPE_NAMES`
entry (added to `UNPUBLISHED_EVENT_TYPES` instead, with a documenting
comment matching the existing four-event precedent's own wording), no
frontend file, no new table/column/migration. `Scheduler`/`Analytics`
remain entirely absent from this codebase, unreferenced by this slice.

## 11. Test strategy

`DeviceCommandExecutedEvent` publishing (unit, `test_connectivity_service.py`):
one event published per `send_command` outcome (all four cases),
correct fields, `payload` never appears on the event object (no field
exists for it, pinned structurally); no event published when
`event_bus=None` (existing constructor default, matching
`_publish_status`'s own guard).

`DeviceEventLog` (unit, `test_device_event_log.py`, mirroring
`test_debug_console.py`'s own structure): start/stop idempotency,
capture-and-query, filter by `device_id`, `limit`, most-recent-first
ordering, bounded buffer eviction, clear, not-running before start.

Route (integration, extends `test_devtools_route.py` or a new sibling
file): empty when disabled/never started; a real `send_command` call
(through the REST connectivity layer, real `FakeDeviceConnector`)
surfaces in `GET /devtools/events`; `device_id` filter excludes other
devices' events; `DELETE` clears; envelope shape; session-only auth;
architecture guards (`EVENT_TYPE_NAMES` does NOT gain a new entry --
pinned by asserting `DeviceCommandExecutedEvent not in EVENT_TYPE_NAMES`
directly against the real `runtime_ws_hub` module; `UNPUBLISHED_EVENT_TYPES`
contains `"DeviceCommandExecutedEvent"`; the existing
`test_no_event_class_silently_missing_a_relay_entry`-style guard in
`test_runtime_ws_hub.py`/`test_platform_integration.py` still passes
unmodified with no edits to either test file beyond what the
allowlist constant itself already covers).

## 12. Non-goals

WebSocket relay / live streaming (§3 — explicitly deferred, not
forgotten; revisit only alongside an actual frontend Developer Mode
pass, matching every sibling devtools capability's own deferral),
read/discovery-triggered events (only `send_command` outcomes, same
scope boundary Device Logs already drew), a write/replay endpoint,
historical persistence beyond the in-memory bounded buffer (restarting
the process loses history, same posture as every other `core/devtools/`
capture component), Automation Tester (separately, still genuinely
blocked — nothing to test until Home Automation/M7 exists).

## 13. Acceptance criteria

- `DeviceCommandExecutedEvent` defined in `core/events/events.py`,
  published from `ConnectivityService.send_command` for all four
  outcomes, never carrying a `payload` field.
- `DeviceEventLog` implemented in `core/devtools/`, wired into the DI
  container and `app.py`'s startup/shutdown hooks exactly like
  `DebugConsole`.
- `GET /api/v1/devtools/events` and `DELETE /api/v1/devtools/events`
  implemented in `routes/devtools.py`.
- `DeviceCommandExecutedEvent` is added to `UNPUBLISHED_EVENT_TYPES`
  with a documenting comment — **not** to `EVENT_TYPE_NAMES` — and both
  existing relay-completeness guard tests pass with zero edits to their
  own assertion logic.
- No `PermissionModel` gate, no agent tool, no schema change, no
  frontend file touched.
- Settings-gated (`device_event_log_enabled`, default `True`), matching
  `debug_console_enabled`'s own posture.
