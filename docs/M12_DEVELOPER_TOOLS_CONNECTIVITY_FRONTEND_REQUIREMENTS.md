# M12 Developer Tools — Connectivity / Integration Health — Frontend Requirements

**Status: specification/planning document only. Contains zero
frontend source code.** Derived exclusively from the shipped, fully-
tested backend implementation
(`src/jarvis/services/devtools_connectivity_service.py`,
`src/jarvis/infrastructure/api/routes/devtools.py`) and its
authoritative Logic Contract (`docs/
M12_DEVELOPER_TOOLS_CONNECTIVITY_LOGIC_CONTRACT.md`), written after
the backend's full regression and quality gates all passed. **No
frontend implementation accompanies this file, and none is authorized
by it. FRONTEND IMPLEMENTATION REQUIRED LATER** — this document
exists so that whenever frontend work on this capability begins, it
starts from the backend's real, verified contract rather than
assumption.

## 1. API endpoint

```
GET /api/v1/devtools/connectivity?home_id=<optional>
```

Lands alongside the four existing Developer Mode capabilities already
under `/api/v1/devtools/*` (logs, performance, state, API calls) —
conceptually a fifth panel in the same Developer Mode surface, not a
new top-level app section.

## 2. Request/response contract

**Request**: no body; one optional query parameter, `home_id`.

**Response** (`{data, meta}` envelope, matching every other route in
this app):

```ts
{
  data: {
    connectors: Array<{
      connector_type: string;      // e.g. "home_assistant", "mqtt"
      registered: boolean;         // always true today -- see §9
      connected: boolean;
    }>;
    homes: Array<{
      home_id: string;
      room_count: number;
      zone_count: number;
      device_count: number;
      paired_device_count: number;
      offline_device_count: number;
      unreachable_device_count: number;
    }>;
  };
  meta: {
    connector_count: number;
    home_count: number;
  };
}
```

**No other fields exist.** In particular: no latency, uptime,
reconnect count, error count, or per-device detail beyond the
aggregate counts above — the backend does not track any of these
today (§9).

## 3. Authentication / authorization expectations

**Session authentication only** — the same `Authorization: Bearer
<session_id>` header every other route in the app already sends.
**There is no additional permission grant to request or check** —
unlike M12 device-control features (Smart Lighting, Locks, Water
Heater, etc.), this route has no `smart_home`-scope gate at all. This
matches every other Developer Mode panel exactly (Debug Console,
Performance, State, API Inspector) — none of them require a grant
either. The frontend should **not** build a "grant devtools
permission" flow for this capability; none exists on the backend.

**Developer Mode's own password-unlock UI gate** (already used to
enter Developer Mode's screens generally) remains the relevant
frontend-side gate, exactly as it already is for the other four
panels — this capability introduces no new backend enforcement of
that gate (the backend doesn't enforce it for any of the five
existing panels today, verified directly against the real source).

## 4. UI components (conceptual — not designed here)

A "Connectivity & Device Health" panel, likely placed alongside the
existing Debug Console/Performance/State/API Inspector tabs in
Developer Mode:
- A small table of connector rows (`connector_type`, a
  connected/disconnected indicator).
- A per-home summary (or a home picker + single-home summary when
  `home_id` filtering is used) showing the six counts.

## 5. States

- **Loading**: no backend concept of progress: this is one
  synchronous call. A simple spinner/skeleton is sufficient.
- **Empty — no connectors registered**: `connectors: []`. Theoretical
  in practice (the app always registers `home_assistant`+`mqtt`
  factories at startup) but the frontend should handle it without
  erroring — render "no integrations configured," not a blank table.
- **Empty — no homes**: `homes: []`. A legitimate, common state before
  any home is created (e.g. a fresh install) — render "no homes yet,"
  not an error.
- **Registered but not connected**: a connector row with `connected:
  false` is normal, not an error state — render it distinctly from
  "connected" (e.g. a gray/red dot vs. green), never omit the row.
- **Error — unknown `home_id`**: HTTP 404 when a specific `home_id`
  filter doesn't resolve to a real home. This should only happen from
  stale client-side state (a home deleted after the picker was
  populated) — treat it as a real error, refresh the home list.
- **Error — no session**: HTTP 401. Standard auth-expired handling,
  same as every other route.

## 6. Data fields to display

Every field in §2's response and nothing invented beyond it. In
particular, **do not display a unit/percentage/health-score derived
from these counts** unless that derivation is added to the backend
first — e.g., don't compute a "92% healthy" figure client-side from
`paired_device_count`/`device_count`; if that's wanted, it belongs in
the backend contract, not invented in the frontend layer (this
mirrors the Security Action Slice's and Water Heater's own "frontend
must not infer capabilities the backend didn't provide" precedent).

## 7. Refresh/polling behavior

**Not defined by the backend** — this is a plain synchronous GET with
no push/streaming counterpart (no WebSocket event exists for
connectivity or device-count changes; the pre-existing device-command
EventBus gap means nothing publishes when a device goes offline). If
live-ish updates are wanted, the frontend would need to poll this
endpoint on an interval of its own choosing — there is no
backend-recommended interval, since nothing about the underlying data
changes faster than "whenever a device state is next read." A
reasonable default (e.g. poll on panel focus, or a coarse interval
like 30–60s) is a frontend product decision, not something this
contract specifies.

## 8. Future extensibility considerations

If a future backend pass adds real telemetry (latency, uptime,
reconnect history — none of which exist today, §9), those would
appear as **additional** fields on the existing `connectors`/`homes`
rows, not a new endpoint — the frontend's data model should tolerate
additional unknown fields gracefully (don't hard-fail on an
unexpected key) rather than assuming today's field list is final.
Similarly, if `registered_types` ever includes a type this build
doesn't recognize, the frontend should render it generically (the
`connector_type` string itself, not a hardcoded icon/label map
limited to `home_assistant`/`mqtt`).

## 9. What is explicitly NOT available (must not be represented as implemented)

- Latency, uptime, reconnect count, or error count for any connector.
- Any per-device diagnostic (only home-level aggregate counts exist).
- MQTT message inspection, command tracing/replay, or an Event Viewer
  — none of this infrastructure exists (the EventBus device-command
  gap remains open).
- Any mutation from this panel — this is a read-only capability; there
  is no "reconnect" or "disconnect" button this endpoint backs (that
  functionality exists elsewhere, under `/api/v1/connectivity/*`, a
  different, already-shipped M12 surface this Developer Tools panel
  does not duplicate or wrap).
- Any connector credential, token, password, or configuration detail
  — structurally impossible for this endpoint to return one (verified
  in the backend's own test suite).

## Summary classification

| Item | Classification |
|---|---|
| `GET /api/v1/devtools/connectivity` | SHIPPED BACKEND CAPABILITY |
| A Developer Mode "Connectivity & Device Health" panel | FRONTEND IMPLEMENTATION REQUIRED LATER — not started, not scoped beyond §4's conceptual description |
| Latency/uptime/reconnect metrics, Event Viewer, MQTT inspection | BACKEND CAPABILITY NOT AVAILABLE — must not appear in any future frontend as if implemented |
| Connector reconnect/disconnect actions from this panel | Out of this capability's scope — belongs to the existing `/api/v1/connectivity/*` surface, not duplicated here |
