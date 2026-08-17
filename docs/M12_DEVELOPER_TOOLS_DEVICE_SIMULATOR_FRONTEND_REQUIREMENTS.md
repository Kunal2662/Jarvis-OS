# M12 Developer Tools — Device Simulator — Frontend Requirements

**Status: specification/planning document only. Contains zero frontend
source code.** Derived exclusively from the shipped, fully-tested
backend implementation (`src/jarvis/core/connectivity/connectors/
simulator.py`, `src/jarvis/infrastructure/api/routes/devtools.py`) and
its authoritative Logic Contract (`docs/
M12_DEVELOPER_TOOLS_DEVICE_SIMULATOR_LOGIC_CONTRACT.md`), written after
the backend's full regression and quality gates all passed. **No
frontend implementation accompanies this file, and none is authorized
by it. FRONTEND IMPLEMENTATION REQUIRED LATER** — this document exists
so that whenever frontend work on this capability begins, it starts
from the backend's real, verified contract rather than assumption.

**This is a local development/testing tool, not a product feature.**
Any future UI for it belongs in Developer Mode only, gated the same
way every other devtools panel already is, and must never be reachable
or advertised to an ordinary end user.

## 1. API endpoints

```
POST   /api/v1/devtools/simulator/devices
GET    /api/v1/devtools/simulator/devices
DELETE /api/v1/devtools/simulator/devices/{external_id}
POST   /api/v1/devtools/simulator/devices/{external_id}/fault
POST   /api/v1/devtools/simulator/reset
```

Lands alongside the five existing Developer Mode capabilities already
under `/api/v1/devtools/*` (logs, performance, state, API calls,
connectivity health) — conceptually a sixth panel in the same
Developer Mode surface, not a new top-level app section.

**Discovery, import, live state reads, and command execution are
deliberately not part of this API** — those already run through the
existing, unmodified generic Connectivity Layer routes
(`/api/v1/connectivity/*`) and every ordinary M12 device-category
route/UI, exactly as they would for a real device. A future frontend
must reuse those existing flows for a simulated device, never build a
parallel "simulator device" viewer/controller.

## 2. Request/response contract

**`POST /devtools/simulator/devices`** — request:
```ts
{
  device_type: "light" | "switch" | "thermostat" | "lock" | "sensor";
  external_id?: string;        // auto-generated if omitted
  name?: string;
  status?: string;
  attributes?: Record<string, unknown>;
  device_class?: string;       // sensor only
  binary?: boolean;            // sensor only, default false
}
```
Response (`{data, meta}` envelope, matching every other route):
```ts
{
  data: {
    external_id: string;
    device_type: string;
    name: string;
    status: string;
    attributes: Record<string, unknown>;
    unavailable: boolean;
    force_command_failure: boolean;
    failure_detail: string;
  };
}
```

**`GET /devtools/simulator/devices`** — no request body; response is
an array of the same shape, `meta.count`.

**`DELETE /devtools/simulator/devices/{external_id}`** — response
`{"deleted": boolean}`.

**`POST /devtools/simulator/devices/{external_id}/fault`** — request
(all fields optional, only supplied fields change):
```ts
{ unavailable?: boolean; force_command_failure?: boolean; failure_detail?: string }
```

**`POST /devtools/simulator/reset`** — no request body; response
`{"cleared": number}`.

## 3. Authentication / authorization expectations

**Session authentication only** (`Authorization: Bearer <session_id>`)
— there is no additional permission grant to request or check, matching
every other Developer Mode panel exactly (none of the existing five
require one either, and this capability's own Logic Contract §9
explicitly evaluated and rejected adding one, since a simulated
device's mutations never touch real device or real home data). The
frontend should **not** build a "grant simulator permission" flow;
none exists on the backend.

**Developer Mode's own password-unlock UI gate** remains the relevant
frontend-side gate, exactly as it already is for the other five
panels — this capability introduces no new backend enforcement of that
gate.

## 4. UI components (conceptual — not designed here)

A "Device Simulator" panel, likely placed alongside the existing
Debug Console/Performance/State/API Inspector/Connectivity Health tabs
in Developer Mode:
- A small form to define a new simulated device (device_type picker +
  optional external_id/name/initial state).
- A table of currently-defined simulated devices with their live
  status/attributes and fault flags, and a delete action per row.
- A per-device fault toggle (unavailable / force-fail) and a
  reset-everything action.
- A clear, persistent visual indicator that "simulator mode" is a
  whole-app-instance setting, not a per-device toggle — e.g. a banner
  when `settings.devtools.simulator_enabled` is on, since while it is
  on, the real Home Assistant connector is not reachable at all
  (Logic Contract §4).

Once a simulated device is imported into a real home through the
existing generic discovery flow, its detail/control view is **whatever
the app already renders for a real light/switch/thermostat/lock/
sensor** — no simulator-specific device view.

## 5. States

- **Loading**: each call here is a single synchronous request; a
  simple spinner/disabled-button state is sufficient.
- **Empty roster**: `data: []`, `meta.count: 0` — a normal, expected
  state (nothing defined yet, or just reset), render "No simulated
  devices defined," not an error.
- **Invalid `device_type`**: HTTP 400 with a message naming the five
  supported categories — render inline on the create form, not a
  generic error toast.
- **Unknown `external_id`** (delete/fault): delete reports `{"deleted":
  false}` with HTTP 200 (not found is a normal outcome, not an error);
  fault reports HTTP 404 — the frontend should treat these two
  differently, matching the backend's own distinction.
- **No session**: HTTP 401. Standard auth-expired handling, same as
  every other route.

## 6. Data fields to display

Every field in §2's response and nothing invented beyond it. In
particular, do not compute or display a derived "health"/"realism"
score for a simulated device — none exists on the backend.

## 7. Refresh/polling behavior

**Not defined by the backend** — plain synchronous REST, no
push/streaming counterpart. Since every mutation here originates from
the same developer's own UI action, a simple refetch-after-mutation
pattern (no interval polling) is sufficient — there is no
multi-client "someone else changed the simulator" scenario worth
designing for in a local development tool.

## 8. Future extensibility considerations

If a future backend pass extends the supported device-category set
beyond light/switch/thermostat/lock/sensor (Logic Contract §18's own
deferred item), the frontend's device-type picker should be driven by
whatever the backend actually rejects/accepts (via the 400 response),
not a hardcoded five-item list baked in permanently.

## 9. What is explicitly NOT available (must not be represented as implemented)

- Any way to simulate MQTT-sourced devices specifically — this MVP
  only ever affects the `"home_assistant"` connector slot (Logic
  Contract §18).
- Any simulator-specific discovery/import/state/command endpoint —
  those are deliberately absent; the existing generic Connectivity
  Layer routes are the only path (§1).
- Latency/jitter simulation, or any random/probabilistic failure mode
  — every fault is deterministic and caller-configured only.
- Persistence of the simulator's own roster across a server
  restart — it is explicitly ephemeral, in-memory only.
- Any way to run the simulator alongside a real Home Assistant
  connection in the same running instance — simulator mode is a
  whole-process setting; turning it on structurally replaces the real
  connector for that process (Logic Contract §4).
- Any end-user-facing surface — this must never appear outside
  Developer Mode.

## Summary classification

| Item | Classification |
|---|---|
| `POST/GET/DELETE /api/v1/devtools/simulator/devices*`, `/fault`, `/reset` | SHIPPED BACKEND CAPABILITY |
| A Developer Mode "Device Simulator" panel | FRONTEND IMPLEMENTATION REQUIRED LATER — not started, not scoped beyond §4's conceptual description |
| Simulator-specific discovery/import/state/command routes, MQTT-slot simulation, latency simulation, cross-restart persistence | BACKEND CAPABILITY NOT AVAILABLE — must not appear in any future frontend as if implemented |
| Discovery, import, live state, and command control of a simulated device | Already fully covered by the existing, unmodified generic Connectivity Layer and device-category UI — no new frontend work needed there |
