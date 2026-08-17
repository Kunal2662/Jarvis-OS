# M12 Smart Home Memory — Manual/On-Demand Device Snapshot — Frontend Requirements

**Status: specification/planning document only. Contains zero frontend
source code.** Derived exclusively from the shipped, fully-tested
backend implementation (`src/jarvis/services/
smart_home_memory_service.py`, `src/jarvis/infrastructure/api/routes/
smart_home_memory.py`, `src/jarvis/agents/tools/
smart_home_memory_tools.py`) and its authoritative Logic Contract
(`docs/M12_SMART_HOME_MEMORY_SNAPSHOT_LOGIC_CONTRACT.md`), written
after the backend's full regression and quality gates all passed. **No
frontend implementation accompanies this file, and none is authorized
by it. FRONTEND IMPLEMENTATION REQUIRED LATER** — this document exists
so that whenever frontend work on this capability begins, it starts
from the backend's real, verified contract rather than assumption.

**Naming boundary, binding for any future frontend copy.** This
capability is **Manual/On-Demand Device Snapshot**. UI copy must never
call it "Device History," "Automatic Device History," "Continuous
Device Monitoring," "Automatic State Tracking," or "Event-Driven
Memory" — a snapshot exists only because the user (or an agent, on the
user's behalf) explicitly asked for one, never automatically.

## 1. API endpoints

```
POST /api/v1/smart-home/memory/snapshots
GET  /api/v1/smart-home/memory/snapshots?device_id=<optional>&limit=<optional>
```

Conceptually a capability of the Smart Home area, not a new top-level
app section — most naturally surfaced as a "Snapshot" action on a
device's own detail view (Lighting/Switches/Thermostat only, §9) plus
a small snapshot list/timeline reachable from that same device.

## 2. Request/response contract

**`POST` request**: `{"device_id": string}`.

**`POST` response** (`{data, meta}` envelope, matching every other
route in this app):

```ts
{
  data: {
    memory_id: string;
    device_id: string;
    device_type: "light" | "switch" | "thermostat";
    snapshot_at: string;   // ISO 8601 UTC
  };
  meta: { device_id: string };
}
```

**`GET` request**: no body; optional query parameters `device_id`,
`limit` (default 50).

**`GET` response**:

```ts
{
  data: Array<{
    memory_id: string;
    device_id: string;
    device_type: string;
    home_id: string;
    room_id: string | null;
    device_name: string;
    snapshot_at: string;
    state: Record<string, unknown>;   // the device's own normalized read model, verbatim
    content: string;                  // the stored human-readable summary sentence
  }>;
  meta: { count: number };
}
```

**No other fields exist.** In particular: no diff-against-previous-
snapshot, no computed trend, no annotation/tag field — the backend
does not compute or store any of these (§8).

## 3. Authentication / authorization expectations

**Session authentication** (`Authorization: Bearer <session_id>`)
plus, unlike most M12 device-control features, **an explicit
permission grant is required for both endpoints** — `POST` *and*
`GET` alike. This is a deliberate departure from the majority "reads
ungated" M12 pattern (Logic Contract §10): a browsable snapshot
history carries more cumulative privacy weight than a single live
device read, so retrieval is gated the same as creation.

The frontend must therefore treat this capability as **permission-
gated in both directions** — the same generic grant flow already used
elsewhere (`POST /api/v1/plugins/core:smart_home_memory/permissions/
smart_home/grant`), not the "just works" pattern Lighting/Switch/
Thermostat control's own reads already enjoy. A "Snapshot" button and
a snapshot list should both be capable of showing a permission-
required state (§6), not just the button.

## 4. UI components (conceptual — not designed here)

- A **"Snapshot" action** on a light/switch/thermostat device's detail
  view — a single button, not a form (the only input is the already-
  known `device_id`).
- A **snapshot list** for that device — a simple reverse-chronological
  list of prior snapshots (timestamp + a one-line state summary),
  reusing the same list-row pattern the app's existing Memory Timeline
  UI already uses for other memory types (`browse()`/`MemoryRecord`
  already back that UI pattern generically — nothing new to design
  from scratch there).
- No separate top-level "Device Snapshots" navigation entry is implied
  by the backend — this reads as a per-device capability, not a
  cross-home browsing surface (though nothing prevents a future
  frontend design from also offering an unfiltered `GET` view; the
  backend supports it, §2).

## 5. Device scope the frontend must enforce client-side too

Only **light**, **switch**, and **thermostat** devices support
snapshots (Logic Contract §5). The frontend should only show the
"Snapshot" action on those three device-category detail views —
**never render it on Sensor, Smart Lock, Camera, or any
`appliance`-domain device's screen** (Vacuum, Humidifier, Media
Player, Water Heater, Fan, Cover). This is not merely a defensive
check against the backend's own 400 — it reflects the Logic Contract's
own deliberate privacy exclusion for Sensors/Locks (§5/§11) and
architectural exclusion for appliance-domain categories; a future
frontend must not "helpfully" show the button everywhere and rely on
the error response to hide it, since that would visually suggest the
capability might exist for those categories when it structurally does
not.

## 6. States

- **Loading (create)**: a single synchronous `POST` — a brief inline
  spinner/disabled-button state on the "Snapshot" action is sufficient.
- **Loading (list)**: a single synchronous `GET` — standard
  skeleton/spinner list state.
- **Permission required**: `POST`/`GET` both return HTTP 400 with a
  message naming `core:smart_home_memory`/`smart_home` when the grant
  is missing (§3) — render a "Grant permission to enable device
  snapshots" prompt rather than a generic error toast, reusing
  whatever the app's existing permission-prompt pattern already is for
  other gated M12 mutations (e.g. Security Action Slice's own
  panic-mode gating).
- **Empty — no snapshots yet**: `data: []`, `meta.count: 0`. A normal,
  expected first-use state — render "No snapshots yet. Capture one to
  see it here," not an error.
- **Success (create)**: show the new snapshot's `snapshot_at` and a
  short confirmation (e.g. a toast), then prepend it to the list view
  if one is currently shown (or simply refetch the list, §7).
- **Error — unknown device**: HTTP 404 (`POST` only — should only
  happen from stale client-side state, e.g. a device deleted after the
  page loaded).
- **Error — unsupported device category**: HTTP 400 with "only
  supported for light/switch/thermostat devices" in the detail — this
  should be unreachable in practice if §5 is honored, but the frontend
  must not crash or show a raw error string if it ever occurs; a
  friendly "Snapshots aren't available for this device type" message
  is more honest than exposing the raw backend detail text.
- **Error — no session**: HTTP 401. Standard auth-expired handling,
  same as every other route.

## 7. Refresh/polling behavior

**Not defined by the backend** — a plain synchronous `GET` with no
push/streaming counterpart (no WebSocket event exists for snapshot
creation; nothing publishes to the Runtime WebSocket hub for this
capability, §10). The natural pattern is to refetch the list after a
successful `POST` (the creating client already knows a new snapshot
exists) rather than polling — there is no cross-client "someone else
just snapshotted this device" signal to poll for, since a snapshot
only exists when *this* request created it.

## 8. Future extensibility considerations

If a future backend pass adds a diff-against-previous-snapshot,
annotation/tagging, or a computed trend, those would appear as
**additional** fields on the existing snapshot row shape, not a new
endpoint — the frontend's data model should tolerate additional
unknown fields gracefully rather than assuming today's field list is
final. If a future backend pass extends device-category scope beyond
light/switch/thermostat (Logic Contract §21's own deferred item), the
frontend's category allow-list (§5) should be sourced from a single
shared constant, not duplicated ad hoc, so extending it later is a
one-line change.

## 9. What is explicitly NOT available (must not be represented as implemented)

- Automatic, scheduled, or event-driven snapshot capture of any kind —
  every snapshot exists only because a "Snapshot" action (or an agent
  tool call) was explicitly invoked. No "auto-snapshot on device
  change" toggle exists or should be implied by any future UI copy.
- Sensor, Smart Lock, Camera, or appliance-domain (Vacuum/Humidifier/
  Media Player/Water Heater/Fan/Cover) device snapshots — structurally
  unsupported today (§5).
- Snapshot deletion — no delete route or tool exists (Logic Contract
  §7); a future frontend must not add a delete button that has nothing
  to call.
- Any diff, trend, chart, or analytics view over multiple snapshots —
  the backend returns only a plain, most-recent-first list (§2); the
  frontend must not compute or imply a derived comparison itself
  without new backend support.
- Home-wide or batch snapshotting — every capture is single-device
  (Logic Contract §19); no "snapshot all devices in this room" action
  exists.

## Summary classification

| Item | Classification |
|---|---|
| `POST /api/v1/smart-home/memory/snapshots` | SHIPPED BACKEND CAPABILITY |
| `GET /api/v1/smart-home/memory/snapshots` | SHIPPED BACKEND CAPABILITY |
| A "Snapshot" action on light/switch/thermostat device views | FRONTEND IMPLEMENTATION REQUIRED LATER — not started, not scoped beyond §4's conceptual description |
| A per-device snapshot list/timeline view | FRONTEND IMPLEMENTATION REQUIRED LATER — not started |
| Snapshot deletion, diff/trend view, automatic/scheduled capture, Sensor/Lock/appliance-domain snapshots | BACKEND CAPABILITY NOT AVAILABLE — must not appear in any future frontend as if implemented |
