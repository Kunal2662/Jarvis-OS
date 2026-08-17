# M12 Smart Home Memory — Security Device-Category Expansion Slice — Frontend Requirements

**Status: planning/specification document only. Contains zero frontend
source code.** Derived exclusively from the shipped, fully-tested
backend implementation (`src/jarvis/services/smart_home_memory_service.py`)
and its authoritative Logic Contract (`docs/
M12_SMART_HOME_MEMORY_SECURITY_DEVICE_EXPANSION_LOGIC_CONTRACT.md`),
written after the backend's full regression, targeted tests, and
quality gates all passed. No frontend implementation accompanies this
file, and none is authorized by it.

## 1. Backend capability summary

**SHIPPED BACKEND CAPABILITY**: the existing nine-category snapshot
capability (Task Groups O + S) now extends to two more categories —
Siren and alarm_control_panel — eleven total. No new endpoint, no new
agent tool: the existing `POST`/`GET .../snapshots`,
`DELETE .../snapshots/{id}`, and `POST .../snapshots/home/{home_id}`
all pick up the two new categories automatically, exactly as they did
when Task Group S added six appliance categories. Sensor and Smart
Lock snapshots remain permanently excluded, unchanged.

## 2. Siren snapshot visibility

Siren device cards gain the same "Snapshot this device" action every
other supported category already has (§3 of the prior Frontend
Requirements doc's own precedent). A siren snapshot's stored state
carries `on: boolean | null` and `available: boolean` — the identical
shape `GET /api/v1/sirens/{id}` already returns, since this module
persists the owning service's own read verbatim.

## 3. alarm_control_panel snapshot visibility

alarm_control_panel device cards gain the same action. A panel
snapshot's stored state carries `state: string | null` (one of ten
verbatim Home Assistant values, or `null`) and `available: boolean` —
identical to `GET /api/v1/alarm-control-panels/{id}`'s own shape.

## 4. Security-sensitive history presentation

**FRONTEND IMPLEMENTATION REQUIRED, recommended not mandated**: an
alarm_control_panel snapshot can capture `state: "triggered"` or any
`armed_*` value — a real, persisted security-posture history point
(Security Device Expansion Logic Contract §9's own accepted tradeoff,
explicitly approved scope, not an oversight). The snapshot list/detail
UI should consider visually distinguishing these entries (e.g. a
distinct icon or subtle emphasis for a `"triggered"` snapshot) so a
user scanning snapshot history notices a past alarm event — but this
is a UX judgment call, not a backend requirement; the backend applies
no special treatment to this state versus any other.

## 5. Unavailable states

Identical honesty guarantee every other category already has: if the
connector is unreachable at snapshot time, the stored state is
`on: null`/`state: null` with `available: false` — never fabricated,
never silently skipped. Render exactly as the existing nine-category
UI already does for an unavailable device's snapshot.

## 6. Permissions

**No new permission surface.** Snapshotting a siren or
alarm_control_panel requires only the existing `smart_home` grant to
`core:smart_home_memory` — the same single grant every other category
already requires. Critically, **granting `core:sirens` or
`core:alarm_control_panels` is not required** and the frontend must
not imply otherwise (e.g. by gating the snapshot action on those
grants) — this module's own permission check is fully independent of
either device-category service's own principal.

## 7. Deletion behavior

**Unchanged, no new UI.** The existing single-snapshot delete
affordance (`DELETE /snapshots/{memory_id}`) already works for any
`memory_type="device_snapshot"` record regardless of category — a
siren or alarm_control_panel snapshot deletes exactly the same way a
light snapshot does. No category-specific delete logic exists or is
needed.

## 8. Home-wide snapshot behavior

**No new UI entry point** — the existing "Snapshot this home" action
(`POST /snapshots/home/{home_id}`) now includes any siren/
alarm_control_panel devices in that home automatically, alongside the
nine already-supported categories. The existing per-device outcome
rendering (`succeeded`/`skipped`/`failed`, per the prior Frontend
Requirements doc §9) needs no change — a siren or alarm_control_panel
device simply appears as one more row using the same three outcomes.

## 9. API endpoints (unchanged)

| Endpoint | Method | Body |
|---|---|---|
| `/api/v1/smart-home/memory/snapshots` | `POST` | `{"device_id": string}` |
| `/api/v1/smart-home/memory/snapshots` | `GET` | `?device_id=&limit=` |
| `/api/v1/smart-home/memory/snapshots/{memory_id}` | `DELETE` | — |
| `/api/v1/smart-home/memory/snapshots/home/{home_id}` | `POST` | — |

No endpoint changed shape. The only difference a frontend observes is
that `device_type: "other"` rows may now appear in list/home-wide
responses where they previously always resolved to
`UnsupportedSnapshotCategoryError` and were skipped.

## 10. Error handling (unchanged, one clarification)

Same table as the prior Frontend Requirements doc's own §13, with one
addition: a `device_type: "other"` device that is **not** a siren or
alarm_control_panel (e.g. a `valve`) still returns the same
`UnsupportedSnapshotCategoryError` (400 on create, `"skipped"` on
home-wide) every other unsupported category already does — the
frontend's existing "not supported for snapshotting" treatment applies
unchanged, no new error case to handle.

## 11. Explicit non-goals

- No code/PIN entry anywhere — a snapshot only ever reads
  alarm_control_panel *state*, never arms or disarms it, and the
  underlying service has no code/PIN parameter to begin with (Task
  Group U's own permanent guarantee, inherited transitively).
- No alarm history/log view beyond the existing generic snapshot list
  — this slice adds no dedicated "security history" screen.
- No coupling to Siren on/off control, alarm_control_panel arm/disarm
  actions, Panic Mode, or Vacation Mode — this module remains strictly
  read-only against devices.
- No new filter (e.g. "show only security snapshots") — the existing
  `device_id`-only filter is unchanged.
- Sensor/Lock snapshots remain permanently excluded — not revisited by
  this slice.

## Summary classification

| Item | Classification |
|---|---|
| Siren/alarm_control_panel snapshot creation, retrieval, deletion, home-wide inclusion | SHIPPED BACKEND CAPABILITY |
| Snapshot UI on Siren/alarm_control_panel device cards, security-posture-history visual treatment | FRONTEND IMPLEMENTATION REQUIRED (not started, not scoped beyond this document) |
| A dedicated security-history view, code/PIN entry, arm/disarm from a snapshot, Sensor/Lock snapshots | BACKEND CAPABILITY NOT AVAILABLE |
