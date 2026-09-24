# M12 Developer Tools — Device Logs — Logic Contract

Status: **Implemented this session** (Task Group V). Written following
a Phase 0 audit that found the natural approach — mirroring
`get_plugin_diagnostics`'s `DebugConsole.entries(contains=plugin_id)`
pattern verbatim for `device_id` — would have shipped a route that
always returns empty for real devices, because (unlike `plugin_id`,
which every plugin-lifecycle log line already embeds) no service or
connector in this codebase logged a device's own `device_id` anywhere.
This contract's Architecture Decision (§3) is the fix for that finding,
not a restatement of the plugin pattern.

## 1. Purpose

A read-only devtools endpoint answering "what has this device been
told to do recently, and did it work?" — closing the still-unbuilt
"Device Logs" item named explicitly in `MASTER_ROADMAP.md`'s M12
Developer Tools feature list.

## 2. Current source evidence

**Finding (the reason this contract exists at all):** grepped every
`_logger.*(` call across `services/*.py` and `core/connectivity/**/*.py`
before writing any code. Zero of them included a device's own
`device_id` (the app-level primary key) in the log message. Connector
logs reference host/port/topic; `smart_home_service.py` logs
home/zone/room ids, never a device id. Every one of the eleven
device-category services (`smart_lighting_service.py`,
`smart_switch_service.py`, `smart_lock_service.py`, `thermostat_service.py`,
`appliance_service.py`, `vacuum_humidifier_service.py`,
`media_player_service.py`, `water_heater_service.py`,
`siren_service.py`, `alarm_control_panel_service.py`,
`security_service.py`) has **no logging calls at all** — none of them
log anything, device-identified or not.

**What all eleven do share:** every one of them mutates a device only
by calling `ConnectivityService.send_command(device_id, command,
payload)` — already documented in that method's own docstring as "the
single chokepoint a later M12 module... gates for `safety_critical`
devices." Confirmed by grep: `send_command(` is called from exactly
those eleven service files plus `connectivity_service.py` itself (the
generic passthrough route), and nowhere else.

## 3. Architecture decision

**One logging call added inside `ConnectivityService.send_command`,
not eleven calls added to each device-category service.** Rejected
alternative: adding a `_logger.info("Device {!r} ...", device_id, ...)`
call to each of the eleven services individually, mirroring how each
call site happens to phrase its own mutation. Rejected because (a) it
duplicates the same log line eleven times with eleven slightly
different wordings, (b) it touches eleven already-shipped, already
individually-tested service files instead of one, and (c) `send_command`
is *already* the documented single chokepoint for exactly this kind of
cross-cutting concern (the same reasoning that method's own docstring
gives for why a future safety-critical gate belongs there and not in
each service). One change point, every device type covered.

Three outcomes, each logged distinctly, matching `CommandResult`'s own
documented semantics (`core/interfaces/connectivity.py`: "success=False
with a detail is a real, expected outcome... not every failure is an
exception"):

1. **No recorded connector** (`connector_type_for(device) is None`) —
   `_logger.warning("Device {!r} command {!r} failed: no recorded
   connector.", device_id, command)`, then the existing
   `ConnectorNotConnectedError` raise (unchanged).
2. **Connector-level failure** (`_require_connector` or
   `connector.send_command` raises any `ConnectivityError`) —
   `_logger.warning("Device {!r} command {!r} failed: {}", device_id,
   command, err)`, then re-raised unchanged. Caught at the
   `ConnectivityError` base class, not `ConnectorNotConnectedError`
   specifically, since a connector's own `send_command` can raise other
   subclasses too (§2 of the Connectivity Layer's own Logic Contract).
3. **`CommandResult` returned** — `success=True` logs
   `_logger.info("Device {!r} command {!r} succeeded.", device_id,
   command)`; `success=False` logs `_logger.warning("Device {!r}
   command {!r} failed: {}", device_id, command, result.detail)`.

**`payload` is never logged, in any of the three cases.** A lock's own
`unlock`/`lock` call already carries `{"code": "1234"}`-shaped data in
this codebase's own existing tests (`test_send_command_routes_to_the_
owning_connector`) — logging it verbatim would put a PIN in plaintext
log history, the exact class of leak `routes/devtools.py`'s own
attribute-redaction list (Device Diagnostics §7) exists to prevent
elsewhere. `device_id` and `command` (a fixed vocabulary string like
`"turn_on"`/`"lock"`/`"arm_away"`, never free-form user input) are the
only values interpolated.

## 4. REST endpoint

```
GET /api/v1/devtools/devices/{device_id}/logs?limit=200
```

Lives in `routes/devtools.py`, directly after Device Diagnostics
(grouping with the other device-scoped devtools capability), before
Device Simulator. Logic mirrors `get_device_diagnostics`'s own shape:
`SmartHomeService.require_device` first (404 on unknown device,
matching that route's convention exactly), then
`DebugConsole.entries(contains=device_id, limit=limit)` — the same
accessor `get_plugin_diagnostics` already calls, no new
`core/devtools/` component.

Response envelope matches every other devtools route: `{data, meta}`,
`data` = a tuple of `{at, level, logger, message}` (identical shape to
`get_debug_logs`'s own per-entry fields, minus `module`/`function`/
`line` — irrelevant for this audience, which cares about the device
outcome, not the source location), `meta = {"device_id": ..., "count":
len(data)}`.

No `PermissionModel` gate — session auth only (the router's blanket
`Depends(get_current_session)`), matching every one of this file's
other capabilities. Reasoned, not inherited by default: this is
read-only, and its content (a device id, a command name, success/
failure) is no more sensitive than `get_plugin_diagnostics`'s own
already-shipped, already-ungated `recent_logs`/`permission_audit`
exposure for a plugin.

## 5. Error semantics

| Condition | Behavior |
|---|---|
| Unknown `device_id` | `SmartHomeService.require_device`'s own `ServiceError` → 404 |
| Device exists, no commands ever sent to it | 200, empty `data` tuple — not an error |
| Debug Console sink never started (`console.start()` not called) | 200, empty `data` tuple, `meta.count == 0` — matches `get_debug_logs`'s own existing behavior exactly, not a new case |
| Malformed request | N/A — path parameter + one optional query int, ordinary FastAPI handling |
| Unexpected internal failure | Propagates as a genuine 500, matching every other route in this codebase |

## 6. Agent tool decision

**None.** No conversational use case exists for "read me the raw
devtools command log for device X" — matches Device Diagnostics'
identical reasoning (that Logic Contract §10) and Device Simulator's
before it.

## 7. EventBus / Scheduler / Analytics / Memory / database

**None of the five.** The route makes two calls
(`SmartHomeService.require_device`, `DebugConsole.entries`), neither
touches `EventBus`/`Scheduler`/`Analytics`/`MemoryService`, and no new
table, column, or migration is introduced. The one non-route change
(`ConnectivityService.send_command`'s new logging calls) does not
touch any of these five either — it calls the existing module-level
`_logger` only, the same one that method's surrounding class already
imports.

## 8. Test strategy

`ConnectivityService.send_command` (unit, `test_connectivity_service.py`):
success path logs an info line containing `device_id` and `command`;
device-level rejection (`next_command_succeeds = False`) logs a
warning containing `result.detail`; no-recorded-connector and
not-connected paths each log a warning before their existing raise is
preserved; **no test payload value ever appears in a captured log
line** (the PIN-leak guard this contract exists to prevent).

Route (integration, `test_m12_devtools_device_logs_route.py`, same
`FakeDeviceConnector` + real FastAPI app pattern as
`test_m12_device_diagnostics_route.py`): unknown device → 404; a
device with no commands sent → 200 with empty `data`; sending a
command through the real `/api/v1/connectivity/*` route then querying
`.../logs` surfaces that exact outcome; a second, unrelated device's
own commands are excluded (the `contains` filter's own precision);
`limit` is respected; envelope shape; session-only auth boundary (no
grant needed, matching Device Diagnostics); architecture guards
(no `EventBus`/`Scheduler`/`Analytics`/`MemoryService` reference in the
route module, no agent tool named `get_device_logs`/`device_logs`
registered).

## 9. Deferred scope

Read/discovery-triggered logging (only command outcomes are captured —
a device's state *reads*, and discovery runs, are not logged per-device,
since neither goes through `send_command`), structured per-device log
storage (this reuses the existing bounded, in-memory `DebugConsole`
ring buffer — restarting the process loses history, same as every
other Debug Console consumer), MQTT Debug Console, Event Viewer,
Automation Tester (all still separately unbuilt/blocked, unchanged by
this slice), and retroactively logging the eleven already-shipped
device-category services' own non-`send_command` code paths (none
exist — confirmed in §2).

## 10. Acceptance criteria

- `GET /api/v1/devtools/devices/{device_id}/logs` implemented directly
  in `routes/devtools.py`, no new service, no new `core/devtools/`
  component.
- `ConnectivityService.send_command` logs exactly one line per call
  (success, device-level rejection, no-connector, or connector-level
  failure), and only there — no other service gains a new logging call.
- `payload` never appears in a logged line, under any outcome — pinned
  by a test.
- Unknown device → 404; every other case → 200, never a 500 for an
  expected outcome.
- No `PermissionModel` gate on the route — session auth only.
- No agent tool, no `Tool Registry`/`AgentOrchestrator` change.
- Zero `EventBus`/Scheduler/Analytics/`MemoryService` reference.
- Zero frontend file touched.
- No database/schema change.
