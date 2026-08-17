# M12 Developer Tools — Device Diagnostics — Frontend Requirements

**Status: specification/planning document only. Contains zero frontend
source code.** Derived exclusively from the shipped, fully-tested
backend implementation (`src/jarvis/infrastructure/api/routes/
devtools.py`) and its authoritative Logic Contract (`docs/
M12_DEVELOPER_TOOLS_DEVICE_DIAGNOSTICS_LOGIC_CONTRACT.md`), written
after the backend's full regression and quality gates all passed. **No
frontend implementation accompanies this file, and none is authorized
by it. FRONTEND IMPLEMENTATION REQUIRED LATER** — this document exists
so that whenever frontend work on this capability begins, it starts
from the backend's real, verified contract rather than assumption.

## 1. API endpoint

```
GET /api/v1/devtools/devices/{device_id}/diagnostics
```

Lands alongside the six existing Developer Mode capabilities already
under `/api/v1/devtools/*` (logs, performance, state, API calls,
connectivity health, device simulator) — conceptually a natural "View
Diagnostics" action on any device already shown in an existing device
list/detail view (Smart Home's own device screens, or a future
Connectivity Health panel row), not a new top-level app section.

## 2. Request/response contract

**Request**: no body; one required path parameter, `device_id`.

**Response** (`{data, meta}` envelope, matching every other route):

```ts
{
  data: {
    device: {
      id: string;
      name: string;
      device_type: string;
      status: string;             // DB lifecycle status, not live state
      home_id: string;
      room_id: string | null;
      manufacturer: string;
      model: string;
      external_id: string | null;
      last_seen_at: string | null; // ISO 8601
    };
    connectivity: {
      connector_type: string | null;
      read_succeeded: boolean;     // did the live read attempt complete -- NOT "is device online"
      status: string | null;       // the connector's own raw status string, only when read_succeeded
      attributes: Record<string, unknown> | null;  // sanitized, only when read_succeeded
      read_error: string | null;   // populated only when read_succeeded is false
    };
    permission: {
      principal: string | null;    // e.g. "core:smart_lighting"; null if unresolved
      scope: string | null;
      state: "pending" | "granted" | "denied" | null;
      detail: string | null;       // explains an unresolved principal
    };
  };
  meta: { device_type: string };
}
```

## 3. Authentication / authorization expectations

**Session authentication only** — no additional permission grant to
request or check, matching every other Developer Mode panel exactly.
The frontend should **not** build a "grant diagnostics permission"
flow; none exists on the backend (Logic Contract §8).

**Developer Mode's own password-unlock UI gate** remains the relevant
frontend-side gate, exactly as it already is for every other panel.

## 4. UI components (conceptual — not designed here)

A "View Diagnostics" action, most naturally placed as a button/link on
any device row already rendered somewhere in the app (a Smart Home
device list, a future Connectivity Health panel row, or the Device
Simulator panel's own roster rows) — opening a detail panel/modal with
three clearly separated sections mirroring the response shape exactly:
**Device** (identity), **Connectivity** (live state or why it
couldn't be read), **Permission** (grant status for the owning
category, or an explanation when none applies).

## 5. States

- **Loading**: a single synchronous call; a simple spinner/skeleton is
  sufficient.
- **Unknown device**: HTTP 404 — should only happen from stale
  client-side state (a device deleted after the page loaded); treat as
  a real error.
- **Connectivity read failed**: **not an HTTP error** —
  `connectivity.read_succeeded: false` with `connectivity.read_error`
  populated. Render this as an explanatory inline state ("Could not
  read live state: <read_error>"), never as a failed API call.
- **Unresolved permission** (`principal: null`): a normal, expected
  state for `appliance`/`camera`/other categories, not an error —
  render `permission.detail`'s own explanation, e.g. "spans multiple
  permission principals," rather than a blank/broken-looking section.
- **No session**: HTTP 401. Standard auth-expired handling.

## 6. Data fields to display

Every field in §2's response and nothing invented beyond it. In
particular:
- Do not compute a derived "health score" from these three sections —
  none exists on the backend.
- Do not interpret `connectivity.read_succeeded: false` as "device is
  offline" — it means the read attempt itself did not complete; an
  actually-reachable-but-reporting-unavailable device is a
  `read_succeeded: true` response with `status: "unavailable"`. These
  are different states and must be rendered differently.
- Render `connectivity.attributes` values as opaque — some may already
  be the literal string `"<redacted>"` (a real sanitized value, not a
  placeholder to be filled in); never attempt to "unredact" or fetch
  the real value through another path.

## 7. Refresh/polling behavior

**Not defined by the backend** — a plain synchronous GET with no
push/streaming counterpart. A manual refresh button (re-issuing the
same GET) is sufficient; no interval polling is implied or recommended
by the backend contract.

## 8. Future extensibility considerations

If a future backend pass resolves the `appliance` sub-domain principal
mapping (deferred, Logic Contract §7/§15), the frontend's permission
section should already tolerate `principal`/`state` becoming non-null
for a device that previously reported them as null — no special-casing
should assume `appliance` will forever be unresolved.

## 9. What is explicitly NOT available (must not be represented as implemented)

- Any mutation from this view — this is a strictly read-only
  diagnostic; there is no "fix," "reconnect," or "grant permission"
  action this endpoint backs (reconnect exists elsewhere, under the
  existing generic `/api/v1/connectivity/*` surface; permission
  granting exists under the existing generic `/api/v1/plugins/*`
  surface — this panel should link to those, not duplicate them).
- Command history, uptime/latency metrics, or any historical view over
  a device's diagnostics — this is a single, current-moment snapshot
  only.
- A resolved permission principal for `appliance`/`camera`/any
  category outside the five named in Logic Contract §7 — must not be
  invented client-side if the backend reports `null`.

## Summary classification

| Item | Classification |
|---|---|
| `GET /api/v1/devtools/devices/{device_id}/diagnostics` | SHIPPED BACKEND CAPABILITY |
| A "View Diagnostics" action/panel for a device | FRONTEND IMPLEMENTATION REQUIRED LATER — not started, not scoped beyond §4's conceptual description |
| Command history, uptime/latency analytics, mutation actions from this panel | BACKEND CAPABILITY NOT AVAILABLE — must not appear in any future frontend as if implemented |
| Reconnect / grant-permission actions | Out of this capability's scope — belongs to the existing generic Connectivity/Plugins surfaces, not duplicated here |
