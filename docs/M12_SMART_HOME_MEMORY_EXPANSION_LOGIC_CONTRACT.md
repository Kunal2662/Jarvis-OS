# M12 Task Group S — Smart Home Memory Device-Category Expansion — Logic Contract

**Status: Phase 1 — Logic Contract only. No implementation.** Written
after independent, fresh re-verification of the shipped Task Group O
(`SmartHomeMemoryService`), every currently-shipped M12 device-category
service, and `MemoryService`'s real public API — not by trusting the
Phase 0 Post-Task-R Audit's own scope suggestion, which this contract
partially overrides (§6).

## 1. Scope

Extend the already-shipped, manual/on-demand-only `SmartHomeMemoryService`
(Task Group O) in three ways:

1. **Device-category expansion** — add the six currently-shipped
   appliance-domain categories (Fan, Cover, Vacuum, Humidifier, Media
   Player, Water Heater) to the supported-snapshot set. **Sensors and
   Smart Locks are explicitly NOT added** — see §6, a direct,
   evidence-based override of the Phase 0 audit's proposed scope.
2. **Snapshot deletion** — a single-snapshot-scoped delete capability,
   safely wrapping `MemoryService.forget()` (§12).
3. **Home-wide/batch snapshot** — one call that snapshots every
   supported device in a home, partial-success semantics (§13).

Everything else about Task Group O's own architecture, naming
boundary, and prohibitions (EventBus/Scheduler/Analytics/AI, §16-§19)
carries forward unchanged.

## 2. Fresh verification — `SmartHomeMemoryService` (existing, Task Group O)

Read in full (`src/jarvis/services/smart_home_memory_service.py`).
Confirmed exact current shape:

- `_readers: dict[str, _DeviceStateReader]` — `device.device_type` is
  the dict key directly (`"light"`/`"switch"`/`"thermostat"`), because
  each of those three has a **unique** `device_type`. This is the
  entire dispatch mechanism today — no domain resolution of any kind.
- `_require_supported_device(device_id)` — calls
  `SmartHomeService.require_device` (raises `ServiceError` "does not
  exist" for an unknown device), then checks `device.device_type in
  self._readers`, raising `UnsupportedSnapshotCategoryError` otherwise.
- `snapshot_device(device_id)` — permission check, resolve device,
  call the resolved reader, persist verbatim via
  `MemoryService.remember()`.
- `list_snapshots(device_id=None, limit=50)` — `MemoryService.browse
  (memory_type="device_snapshot")`, over-fetch + client-side filter by
  `metadata["device_id"]` when given (no indexed per-device query
  exists — a documented, not hidden, limitation carried forward
  unchanged).
- `_snapshot_content`/`_snapshot_summary`/`_IDENTITY_KEYS` — pure,
  deterministic string/dict builders. `_IDENTITY_KEYS` (`id`,
  `home_id`, `room_id`, `name`, `status`, `manufacturer`, `model`,
  `external_id`) matches every M12 device-category payload's own
  identity-field convention **exactly**, including all six appliance
  services verified in §4 — confirmed compatible with zero changes.
- Two dedicated exception subclasses:
  `SmartHomeMemoryPermissionError`, `UnsupportedSnapshotCategoryError`
  — both `ServiceError` subclasses, mapped by the route to 400.

Routes (`routes/smart_home_memory.py`) and tools
(`agents/tools/smart_home_memory_tools.py`) also read in full — see
§21/§22 for how they extend.

## 3. Fresh verification — device-category services

### Light / Switch / Thermostat (unchanged, already supported)
Re-confirmed `get_light_state`/`get_switch_state`/`get_thermostat_state`
signatures unchanged since Task Group O. No action needed.

### Appliance-domain services (Fan, Cover, Vacuum, Humidifier, Media Player, Water Heater)

Read `appliance_service.py`, `vacuum_humidifier_service.py`,
`media_player_service.py`, `water_heater_service.py` in full.
**Critical finding, confirmed by direct source read, not assumed:**
**all four files each define their own private, near-identical,
module-level `_domain_for(device)` function** — four independent
copies, not a shared utility. Each service's own
`_require_<category>(device_id)` method calls
`SmartHomeService.require_device`, then checks `device.device_type ==
"appliance"` (the shared `_APPLIANCE_DEVICE_TYPE = "appliance"`
constant) **and** its own private `_domain_for(device) ==
<CATEGORY>_DOMAIN`, raising a plain `ServiceError` (not a distinct
subclass) — e.g. `f"Device {device_id!r} is not a fan."` — on any
mismatch (wrong `device_type`, wrong domain, *or* device not found,
since `require_device` itself raises the same bare `ServiceError` type
for an unknown device).

Every one of the six categories already exposes a public, already-
shipped, ungated `get_<category>_state(device_id) -> dict[str, Any]`
method with this exact shape: `_require_<category>` → optional
`contextlib.suppress(ConnectivityError)`-wrapped live read via
`ConnectivityService.read_raw_state` → a payload builder returning
`{id, home_id, room_id, name, status, manufacturer, model,
external_id, available, ...category-specific fields}`. This is
**identical in shape** to Light/Switch/Thermostat's own read methods
Task Group O already depends on.

## 4. Fresh verification — payload contents (privacy pre-check)

Read every appliance payload builder in full (`_fan_payload`,
`_cover_payload`, `_vacuum_payload`, `_humidifier_payload`,
`_media_player_payload`, `_water_heater_payload`). None include
credentials, access codes, tokens, network configuration, or precise
location beyond `home_id`/`room_id` (identical to Light/Switch/
Thermostat's own fields). `MediaPlayerService`'s `media_title`/
`media_artist` fields are the only mildly personal data found — not a
new exposure surface: both are already returned, unmodified, by the
existing ungated `GET /api/v1/media-players/{id}` route shipped in
Task Group K, so persisting them in a snapshot discloses nothing a
caller couldn't already read live today. Full privacy conclusion in
§10.

## 5. Fresh verification — `MemoryService`

Read `services/memory_service.py` in full. Confirmed public methods:
`remember`, `forget(memory_id)`, `forget_all()`, `recall`, `search`,
`browse`. **Correction to Task Group O's own Logic Contract**: its
§21 states *"No memory-deletion capability of any kind is exposed
anywhere in this repository today"* — this is **factually incorrect**,
confirmed by direct source read. `MemoryService.forget(memory_id)`
exists today (deletes one memory from both SQL and vector stores,
publishes `MemoryUpdatedEvent(action="deleted")`) and `forget_all()`
exists today (used by Settings ▸ Memory ▸ "Clear Memory"). This
contract does not re-litigate why Task Group O's own audit missed
this — it simply corrects the record and builds on the real API (§12).

**`forget(memory_id)` is completely unscoped** — no type check, no
ownership check, no source/principal verification. It will delete
*any* memory by id, including conversation memories, workspace
memories, or anything else `MemoryService` stores. This confirms the
concern raised in this task group's own kickoff instructions: it is
**too broad to expose directly** through Smart Home Memory's own
permission gate (§12).

`MemoryRepository.get(memory_id) -> Memory | None` exists at the
repository layer but is **not** exposed via any `MemoryService` public
method. M3 (`MemoryService`) falls within the M0–M6 feature-frozen
range this project's own conventions protect — this contract does
**not** propose adding a new public method to `memory_service.py`
(§12 resolves deletion scoping without touching it).

## 6. Device-category scope decision — overrides the Phase 0 audit

**Sensors: EXCLUDED. Smart Locks: EXCLUDED.** This directly overrides
the Phase 0 Post-Task-R Audit's proposed scope, which listed both as
candidate additions without checking Task Group O's own stated
reasoning first.

Re-read `docs/M12_SMART_HOME_MEMORY_SNAPSHOT_LOGIC_CONTRACT.md` §5 in
full. It already excluded Sensors and Smart Locks **on privacy/
security grounds, not architectural ones** — a deliberate, reasoned,
already-shipped decision:

- **Sensors** — excluded because `SensorService`'s own Logic Contract
  already gates *live reads* specifically because motion/presence/
  occupancy device classes directly reveal who is home and when.
  Persisting that into a searchable, retained memory store is a
  **strictly larger** version of the same risk a single live read
  already takes seriously.
- **Smart Locks** — excluded because lock state is a direct security-
  posture indicator, and this codebase already treats the *unlock*
  direction as safety-relevant enough to require interactive
  confirmation (`unlock_device`). A persisted, browsable lock-state
  history compounds that same risk into long-term storage.

Nothing in this task group's own fresh source audit (§2–§5) surfaces
any new fact that weakens either reason. Re-opening either exclusion
would require overturning a privacy/security decision on no new
evidence — this contract declines to do that. **Both categories remain
permanently excluded from Smart Home Memory**, not merely "not yet
built."

**Appliance-domain categories: INCLUDED — the exact expansion Task
Group O's own §5 anticipated.** Its own text: *"excluded on
architectural grounds only — not privacy... A future slice could add
them once a shared, public domain-resolution utility exists, without
reopening this contract's own privacy reasoning."* §7 below resolves
that architectural question **without** building the shared utility
Task Group O's text envisioned — a different, narrower mechanism that
satisfies the same constraint (zero private `_domain_for` duplicated,
zero new shared abstraction) via a cheaper path.

## 7. Critical architectural question — dispatch mechanism (resolved)

**Decision: Option A/B hybrid — dispatch using existing public service
APIs, via two tiers, no new reusable abstraction.**

**Tier 1 (unchanged):** Light/Switch/Thermostat keep the existing
`dict[device_type, reader]` direct lookup — O(1), zero risk, untouched
code path.

**Tier 2 (new, appliance-domain only):** for `device.device_type ==
"appliance"`, an ordered list of `(name, reader)` pairs — one entry
per appliance category, each `reader` being that category's own
already-public `get_<category>_state` method
(`vacuum_humidifier.get_vacuum_state`, `.get_humidifier_state`,
`media_player.get_media_player_state`, `water_heater.
get_water_heater_state`, `appliances.get_fan_state`,
`.get_cover_state`). Tried in sequence: call `reader(device_id)`;
if it raises `ServiceError`, the device isn't that category — try the
next; if it returns, that **is** the state to snapshot (the call
itself both validates ownership and produces the state in one step,
no separate probe).

**Why this is safe to catch broadly.** `SmartHomeMemoryService`
already calls `SmartHomeService.require_device(device_id)` itself,
directly, **before** entering the Tier-2 cascade (existing code,
unchanged) — by the time the cascade runs, the device's existence is
already confirmed. Every appliance service's own internal
`require_device` call (inside its `_require_<category>`) is therefore
guaranteed to succeed too, so the *only* remaining source of
`ServiceError` from a cascade candidate is its own domain-mismatch
check. Catching bare `ServiceError` in the cascade cannot be confused
with "unknown device" or a permission failure (`get_<category>_state`
methods are all ungated reads, confirmed in §3 — no permission
`ServiceError` can occur there either).

**Why this is not "a shared, public domain-resolution utility."** No
new function is added anywhere that inspects `metadata["domain"]`/
`["component"]`. `SmartHomeMemoryService` never reads a domain string
itself, never duplicates any of the four private `_domain_for`
functions, and never introduces a generic "resolve a device's owning
service" framework other modules could misuse. It only calls methods
those services **already expose publicly** for an unrelated purpose
(their own REST/tool reads), in a fixed, closed, six-entry list local
to this one dispatch helper.

**Cost, stated explicitly:** an appliance device snapshot may trigger
up to 5 wasted `require_device` DB round-trips (one per non-matching
candidate tried before the real match) before succeeding. Manual/
on-demand, low-frequency, single-device operation — not a hot path.
Accepted as the trade-off for zero new shared architecture, consistent
with "avoid architecture expansion unless genuinely necessary."

**Rejected alternatives:**
- *Option C (new reusable abstraction)* — rejected; disproportionate
  to this slice, and Task Group O's own text only ever anticipated it
  as one possible future path, not a requirement.
- *Option D (exclude some appliance categories)* — rejected for all
  six; §4 found no privacy/security distinction among them, and the
  Tier-2 mechanism handles all six identically with no added risk from
  including all rather than a subset.

## 8. Device-category scope table

| Category | `device_type` | domain/component | Public read API | Snapshot-safe? | Include? |
|---|---|---|---|---|---|
| Light | `light` (unique) | n/a | `SmartLightingService.get_light_state` | Yes (already shipped, Task Group O) | Already included |
| Switch | `switch` (unique) | n/a | `SmartSwitchService.get_switch_state` | Yes (already shipped) | Already included |
| Thermostat | `thermostat` (unique) | n/a | `ThermostatService.get_thermostat_state` | Yes (already shipped) | Already included |
| Sensor | `sensor` (unique) | n/a | `SensorService.get_sensor_state` | **No** — occupancy/security-signal risk, own Logic Contract already gates live reads | **Excluded (§6)** |
| Lock | `lock` (unique) | n/a | `SmartLockService.get_lock_state` | **No** — security-posture history risk | **Excluded (§6)** |
| Fan | `appliance` (shared) | `fan` | `ApplianceService.get_fan_state` | Yes — verified §4 | **Include** |
| Cover | `appliance` (shared) | `cover` | `ApplianceService.get_cover_state` | Yes — verified §4 | **Include** |
| Vacuum | `appliance` (shared) | `vacuum` | `VacuumHumidifierService.get_vacuum_state` | Yes — verified §4 | **Include** |
| Humidifier | `appliance` (shared) | `humidifier` | `VacuumHumidifierService.get_humidifier_state` | Yes — verified §4 | **Include** |
| Media Player | `appliance` (shared) | `media_player` | `MediaPlayerService.get_media_player_state` | Yes — verified §4 (title/artist not a new exposure) | **Include** |
| Water Heater | `appliance` (shared) | `water_heater` | `WaterHeaterService.get_water_heater_state` | Yes — verified §4 | **Include** |
| Siren | `other` (shared) | `siren` | `SirenService.get_siren_state` | Not evaluated — out of scope for this slice; not requested by the Phase 0 audit or this task group's kickoff | **Not included, not deferred-with-reason — simply out of scope** |
| Camera | `camera` (unique) | n/a | none shipped | N/A — no service exists | Not applicable |

Nine supported categories total after this task group: Light, Switch,
Thermostat (unchanged) + Fan, Cover, Vacuum, Humidifier, Media Player,
Water Heater (new).

## 9. Sensor scope (restated, unchanged from Task Group O)

Excluded outright, all device classes, no per-class carve-out (e.g.
"allow temperature/humidity, exclude motion/presence"). A per-class
allowlist would require `SmartHomeMemoryService` to read and interpret
`device_class` values itself — new classification logic this slice
has no evidence justifies building, and Task Group O's own reasoning
treated "Sensors" as one category, not nine independently-risk-rated
device classes. No change to that framing.

## 10. Smart Lock scope (restated, unchanged from Task Group O)

Excluded outright. `SmartLockService.get_lock_state` was not read in
detail for this contract beyond confirming its exclusion stands — the
governing reasoning (persisted lock-state history as a security-
posture risk) does not depend on the exact field shape, so re-reading
it would not change the decision.

## 11. Appliance scope (see §8 table)

All six included. No credential/token/network/precise-location fields
found in any of the six payload builders (§4). `media_title`/
`media_artist` accepted as no new exposure (already public via each
category's own existing REST route).

## 12. Snapshot deletion — decision

**Decision: single-snapshot deletion only, via a safe scoped wrapper
inside `SmartHomeMemoryService` — `MemoryService.forget()` is reused
unmodified, `memory_service.py` is not touched.**

**Scoping mechanism** (avoids the "too broad" problem in §5): before
calling `self._memory.forget(memory_id)`, first confirm the target
record is actually a snapshot by reusing the **existing** `browse
(memory_type="device_snapshot", limit=<generous cap, e.g. 1000)`
method — already used by `list_snapshots` — and checking whether any
returned record's `id == memory_id`. If not found among snapshot-type
records (whether because the id doesn't exist at all, or because it
exists but is a different memory type entirely), raise a new
`SnapshotNotFoundError(ServiceError)` — mapped by the route to 404,
mirroring this module's own existing 404-for-unknown-device
convention. Only on a confirmed match does `forget()` run. This
guarantees a caller holding only the `core:sirens`-style
`core:smart_home_memory` grant can never delete a conversation memory,
a workspace memory, or any record this service didn't itself create.

**Cost, stated explicitly:** same over-fetch/filter pattern
`list_snapshots` already accepts as a documented limitation (no
indexed per-id-within-type query in `MemoryRepository` today) — not a
new trade-off, the same one already made.

**Scope questions answered:**
1. Reuse `MemoryService.forget()`? **Yes**, behind the scoped check
   above.
2. Should Smart Home Memory expose deletion? **Yes** — a real,
   named-in-the-original-contract gap (§21 of Task Group O's own
   contract listed it as deferred, on the mistaken belief no deletion
   mechanism existed at all).
3. Scope: **single snapshot only.** Device-wide and home-wide deletion
   are both explicitly rejected for this slice — no verified use case
   justifies a destructive bulk operation, and this task group already
   introduces one new bulk operation (home-wide *snapshot*, §13);
   pairing it with a home-wide *delete* in the same pass would double
   the blast-radius surface being introduced without doubling the
   justification.
4. New permission principal for deletion? **No** — reuses
   `core:smart_home_memory`/`smart_home` (§14).
5. Confirmation required? **No** — see §15.
6. Exposed as REST? **Yes** — `DELETE .../snapshots/{memory_id}`
   (§21).
7. Exposed as an agent tool? **Yes** — `delete_device_snapshot`
   (§22).

## 13. Home-wide/batch snapshot — decision

**Decision: B + D — snapshot only devices in supported categories
(§8), skip unsupported ones, continue on per-device failure, return
full per-device results. Sequential, no concurrency.**

- **Enumeration**: `SmartHomeService.list_devices(home_id=...)` —
  existing public method, whatever order it already returns (not
  re-sorted; no new ordering requirement invented).
- **Per device**: attempt the same dispatch used by
  `snapshot_device` (§7's two-tier resolution). Three outcomes:
  - **Succeeded** — category supported, snapshot persisted.
  - **Skipped** — category not supported (`UnsupportedSnapshotCategoryError`,
    caught specifically, not a generic catch-all) — e.g. a Sensor,
    Lock, Camera, or `"other"`-bucket device. Not an error; expected
    for any home containing excluded categories.
  - **Failed** — a genuine, unexpected failure (e.g. `MemoryService.
    remember` raising) — caught, recorded with `detail`, loop
    continues. Never aborts the batch.
- **Unavailable devices**: still snapshotted, same as single-device
  behavior (§2) — an honest `available: false` snapshot is captured,
  never skipped and never fabricated.
- **Concurrency**: **none.** A plain sequential loop — no
  `asyncio.gather`, matching this task group's own explicit
  instruction and Task Group O's own single-device method's already-
  sequential nature.
- **Duplicates**: not deduplicated — see §20 (same reasoning as
  single-device snapshotting, unchanged).
- **Blast radius**: read-only against devices (via each service's own
  ungated `get_<category>_state`) plus N memory-row writes — **no
  device is ever commanded**, unlike Panic/Vacation Mode's real
  device-mutation blast radius. This distinction is the basis for
  §15's no-confirmation decision.

**Response shape** — reuses the exact `requested_count`/
`attempted_count`/`succeeded_count`/`failed_count`/`skipped_count` +
per-device-results convention Task Group M's `SecurityService`
(Panic/Vacation Mode) already established, not a new shape invented
for this slice:

```json
{
  "home_id": "string",
  "requested_count": 0,
  "attempted_count": 0,
  "succeeded_count": 0,
  "failed_count": 0,
  "skipped_count": 0,
  "results": [
    {
      "device_id": "string",
      "device_name": "string",
      "device_type": "string",
      "outcome": "succeeded | failed | skipped",
      "memory_id": "string | null",
      "detail": "string | null"
    }
  ],
  "generated_at": "ISO 8601 UTC"
}
```

`requested_count` = total devices found in the home (every category,
including excluded ones). `attempted_count` = devices whose category
resolved successfully (an actual snapshot attempt was made, whether it
then succeeded or failed). `skipped_count` = devices whose category
never resolved at all. Every device in the home appears exactly once
in `results`, regardless of outcome — matching Panic/Vacation Mode's
own "represent every device exactly once" rule.

## 14. Permission model

**No new principal.** Snapshot creation, retrieval, deletion, and
home-wide snapshot all require the same existing `smart_home` scope
granted to `core:smart_home_memory` — the identical grant Task Group O
already established for create+retrieve. Extending it to the two new
operations (delete, home-wide) is the conservative choice: it does not
weaken Task Group O's own "persistent and cumulatively browsable data
needs gating on both directions" reasoning (§10 of its own contract),
and a single grant surface remains simpler for the operator to reason
about than a per-operation principal split with no evidence any
operation needs a *different* trust level than any other.

`PermissionModel.is_granted()` is used only at the actual mutation-
authorization call site (`_require_permission()`, unchanged pattern
from Task Group O) — never for passive/informational inspection,
consistent with this session's own established `is_granted()`
side-effect finding (Task Group Q).

## 15. Confirmation model

**No new `confirm_required_tools` entries.** Evaluated per-operation,
not defaulted:

- **Single snapshot creation** (existing) — no confirmation, unchanged
  from Task Group O (touches one device, writes one memory row, never
  a physical action).
- **Home-wide snapshot** (new) — no confirmation. Its blast radius is
  real (potentially many devices, many memory rows) but, critically,
  it is **read-only against devices** (§13) — it never commands a
  physical device the way Panic/Vacation Mode's own confirmation-
  requiring blast radius does. The precedent this codebase has
  actually established (`unlock_device`, `trigger_panic_mode`,
  `trigger_vacation_mode`, `turn_siren_on`) gates *physical/real-world*
  consequences, not "any operation touching many rows." A large but
  purely informational read-and-record operation does not meet that
  bar.
- **Snapshot deletion** (new) — no confirmation, single-snapshot
  scope only (§12). Irreversible in the narrow sense that one memory
  row is gone, but it deletes JARVIS's own historical record, not a
  physical device state, and not a home-wide quantity of anything —
  categorically smaller in consequence than any operation currently in
  `confirm_required_tools`. `MemoryService.forget_all()` (the actually
  dangerous, unscoped, home-wide-equivalent bulk delete) remains
  reachable only via Settings UI, not this task group's own scoped
  single-snapshot delete — that boundary is the real safety control
  here, not a confirmation prompt on a narrower operation.

## 16. EventBus boundary (unchanged, reverified)

No event subscription, no automatic capture, no device-state
listener, no background worker. Home-wide snapshot remains an
explicit, synchronous, single request/response call — not a batch job
queued anywhere. The pre-existing device-command EventBus gap
(reconfirmed in the Phase 0 Post-Task-R Audit) is untouched, not
worked around.

## 17. Scheduler boundary (unchanged, reverified)

No Scheduler dependency anywhere in this slice. No recurring
snapshots, no cron behavior, no delayed jobs. Confirmed M7 Phase 6
(Scheduler) remains unshipped (Phase 0 audit, reconfirmed).

## 18. Analytics boundary (unchanged, reverified)

No trends, charts, aggregation, comparison, or predictive behavior of
any kind. `list_snapshots` remains a plain, unmodified listing.
Home-wide snapshot's own summary counts (§13) are a same-call response
shape, not a stored or computed analytics artifact — no new query
persists or aggregates across calls.

## 19. AI boundary (unchanged, reverified)

No LLM-generated snapshot descriptions, no AI summaries, no automatic
inference, no semantic enrichment beyond `MemoryService.remember`'s
own pre-existing best-effort embedding step (unchanged, not touched by
this slice). Snapshot content remains the same deterministic template
string (`_snapshot_content`) for every newly-supported category —
extended with zero new logic, since it already operates generically on
any `state: dict[str, Any]` and `_IDENTITY_KEYS` filter, verified
compatible in §2/§4.

## 20. Duplicate / idempotency behavior

**No deduplication, unchanged from Task Group O.** Snapshotting the
same device twice (whether via two single-device calls, or a device
appearing in two separate home-wide calls) produces two separate
memory rows, distinguished by `snapshot_at`. This is the intended,
historical-record behavior — a snapshot is explicitly a point-in-time
capture, and collapsing repeated captures into one row would silently
discard the "this changed between two captures" signal that is the
entire reason to capture more than once. No new requirement introduces
deduplication for the newly-supported categories or for home-wide
snapshotting.

## 21. Database / schema

**Zero schema changes.** Same conclusion as Task Group O's own §15,
reverified: `MemoryService`'s existing SQLite + Chroma storage,
`browse()`, and `forget()` are all already sufficient for every
operation this task group adds. No new table, no new column, no new
`MemoryRepository` method, no `MemoryType` enum value added (the
existing `memory_type="device_snapshot"`/`source="device_snapshot"`
plain-string pair is reused unchanged, correct for the same reason
Task Group O's own §6 already established — it remains the accurate,
mechanism-level answer regardless of category).

## 22. Architecture (proposed)

```
SmartHomeMemoryService
    -> SmartHomeService            (require_device / list_devices — existing)
    -> {SmartLightingService, SmartSwitchService, ThermostatService}
       (get_light_state / get_switch_state / get_thermostat_state — existing, Tier 1)
    -> {ApplianceService, VacuumHumidifierService,
        MediaPlayerService, WaterHeaterService}
       (get_fan_state / get_cover_state / get_vacuum_state /
        get_humidifier_state / get_media_player_state /
        get_water_heater_state — NEW, Tier 2, ordered-cascade dispatch, §7)
    -> MemoryService                (remember / browse / forget — forget is NEW usage)
```

No new class. No `MemoryRepository` wrapper. No `DeviceSnapshotRepository`.
No `DeviceHistoryService`. No `AnalyticsService`. No event listener. No
Scheduler worker. `SmartHomeMemoryService`'s constructor gains four new
required dependencies (`appliances: ApplianceService`,
`vacuum_humidifier: VacuumHumidifierService`, `media_players:
MediaPlayerService`, `water_heaters: WaterHeaterService`) — DI wiring
only, no new provider function shape beyond adding four parameters to
the existing `_build_smart_home_memory_service`/`smart_home_memory_service`
provider in `container.py`.

## 23. REST design

Minimal extension of the existing two routes — no endpoint
proliferation, no per-category route, no duplicate recall route:

| Endpoint | Method | Body/Query | New? |
|---|---|---|---|
| `/api/v1/smart-home/memory/snapshots` | `POST` | `{"device_id": string}` | Existing, unchanged — now accepts 9 categories instead of 3 |
| `/api/v1/smart-home/memory/snapshots` | `GET` | `?device_id=&limit=` | Existing, unchanged |
| `/api/v1/smart-home/memory/snapshots/{memory_id}` | `DELETE` | — | **New** |
| `/api/v1/smart-home/memory/snapshots/home/{home_id}` | `POST` | — | **New** |

Status codes, extending the existing convention exactly:
`SmartHomeMemoryPermissionError` → 400 (all four routes);
`UnsupportedSnapshotCategoryError` → 400 (create, unchanged); new
`SnapshotNotFoundError` → 404 (delete only); unknown device/home
(bare `ServiceError` from `SmartHomeService`) → 404 (create, home-wide);
home-wide snapshot itself never returns a non-200 for partial/zero
success — mirrors Panic/Vacation Mode's own "a normal 200 describes a
real outcome" rule (§13's response shape carries the outcome, not the
HTTP status).

No generic memory `DELETE`, no generic memory CRUD route added
anywhere. `DELETE .../snapshots/{memory_id}` only ever reaches
snapshot-type memories (§12's scoping check) — it is not a generic
memory-deletion endpoint wearing a Smart Home Memory path.

## 24. Agent tools

Two new tools, added to the existing two (`snapshot_device_state`,
`list_device_snapshots`, both unchanged in shape, now covering 9
categories):

| Tool | Purpose | Permission | Confirmation | Input | Result | Failure |
|---|---|---|---|---|---|---|
| `delete_device_snapshot` | Delete one snapshot by memory id | `core:smart_home_memory`/`smart_home` | None (§15) | `memory_id: str` | Confirmation string | Not-found/permission errors returned as a string, mirroring every other tool's own try/except-and-describe pattern |
| `snapshot_home` | Snapshot every supported device in one home | `core:smart_home_memory`/`smart_home` | None (§15) | `home_id: str` | JSON summary (§13 shape) | Same pattern |

No duplication of `recall_memory` (generic, `agents/tools/
memory_tools.py`) — unchanged from Task Group O's own reasoning for
not building a third snapshot-specific retrieval tool.

## 25. Error / partial-failure semantics

| Condition | Behavior |
|---|---|
| Unknown device (single snapshot) | `ServiceError` from `require_device` → REST 404, tool returns descriptive string |
| Unsupported device type/appliance domain (single snapshot) | `UnsupportedSnapshotCategoryError` → REST 400 |
| Unknown home (home-wide) | `ServiceError` from `SmartHomeService` → REST 404 |
| Unavailable device (single or home-wide) | Snapshot still created, `available: false`/`None` fields captured honestly — never an error (§2/§13) |
| Permission denied (any of the four operations) | `SmartHomeMemoryPermissionError` → REST 400 |
| Snapshot persistence failure (`MemoryService.remember` raises) | Single snapshot: propagates as a real error (existing behavior, unchanged). Home-wide: caught per-device, recorded as `outcome: "failed"`, batch continues (§13) |
| Delete: unknown snapshot id | New `SnapshotNotFoundError` → REST 404 |
| Delete: id belongs to a non-snapshot memory | Same `SnapshotNotFoundError` — indistinguishable from "doesn't exist" from the caller's perspective (§12), deliberately, to avoid revealing the existence/type of unrelated memory records |
| Delete: already-deleted snapshot (repeat call) | Same `SnapshotNotFoundError` — `browse()` no longer returns it, so the scoping check naturally reports "not found," no special-cased "already deleted" state |
| Delete: unauthorized | `SmartHomeMemoryPermissionError` → REST 400, checked before the scoping lookup |
| Home-wide: partial batch failure | Never a non-200 — `succeeded_count`/`failed_count`/`skipped_count` in the response body carry the real outcome (§13) |

## 26. Test strategy (described for Phase 2, not created now)

- **Regression**: existing light/switch/thermostat snapshot behavior
  unchanged (reuse Task Group O's own test fixtures/assertions
  verbatim where possible).
- **New categories**: one test per appliance category (fan, cover,
  vacuum, humidifier, media_player, water_heater) — snapshot succeeds,
  state persisted verbatim, identity fields excluded from content text
  (same `_IDENTITY_KEYS` check Task Group O already has).
- **Dispatch correctness**: a device in each appliance domain resolves
  to the *correct* reader (not a false match from an earlier cascade
  entry); an unsupported `"other"`-bucket device (e.g. a siren) is
  rejected via `UnsupportedSnapshotCategoryError`, not miscategorized.
- **Security**: no `metadata_json` in any snapshot's persisted state
  or content (all nine categories); no credentials/tokens/access codes
  anywhere in test fixtures or assertions.
- **Permissions**: create/retrieve/delete/home-wide each independently
  denied without grant, each independently succeeding once granted.
- **Deletion**: valid delete succeeds and the snapshot no longer
  appears in `list_snapshots`; unknown memory_id → `SnapshotNotFoundError`;
  a real (non-snapshot) `MemoryService.remember()`-created memory
  cannot be deleted through this API even with the grant; repeat
  delete of an already-deleted id → `SnapshotNotFoundError`, not a
  crash; unauthorized delete denied before any lookup occurs.
- **Home-wide**: empty home → `requested_count: 0`, empty `results`;
  all-supported-devices home → all succeeded; a home with excluded
  categories (sensor/lock) present → correctly counted as `skipped`,
  not `failed`; a forced `MemoryService.remember` failure for one
  device → that device `failed`, every other device still processed;
  deterministic result ordering (matches `list_devices`' own return
  order, asserted directly, not re-sorted by the test).
- **Architecture guards**: AST-based, docstring-stripped source
  inspection (reusing this session's own established
  `_code_without_docstrings` helper, not a brittle raw-substring scan)
  confirming zero real references to `EventBus`, `Scheduler`,
  `AnalyticsService`, frontend paths, notification transport, or
  remote-access code in `smart_home_memory_service.py`.

## 27. Deferred functionality

| Item | Why deferred |
|---|---|
| Sensor snapshots | Privacy — occupancy-signal risk (§6/§9), permanently excluded, not "not yet built" |
| Smart Lock snapshots | Security — posture-history risk (§6/§10), permanently excluded |
| Siren snapshots | Out of this task group's named scope (§8); no privacy/architecture blocker found, simply not requested — a future slice could add it via the same Tier-2 pattern if ever prioritized |
| Camera snapshots | No `CameraService` exists at all (Phase 0 audit, reconfirmed) |
| Device-wide or home-wide snapshot *deletion* | No verified use case for bulk destructive deletion; single-snapshot scope only (§12) |
| Automatic/event-driven history | EventBus device-command gap remains unresolved (§16) |
| Scheduled/recurring snapshots | Needs M7 Scheduler, unshipped (§17) |
| Diff/trend/comparison views over snapshots | M20A Analytics' job, unstarted (§18) |
| AI-generated snapshot summaries | Out of scope (§19) |
| Frontend implementation | Frozen this phase (§28) |

**No placeholder code or schema for any of the above.**

## 28. Frontend requirements

Not created in this Phase 1 pass, per the established Water Heater/
Security Action/Developer Tools/Siren Integration precedent — only
written after backend implementation and verification, and only if
genuinely warranted at that point. Conceptually, a future frontend
would extend whatever "Snapshot this device" action already exists for
Light/Switch/Thermostat to the six new appliance cards, plus a
"Delete" affordance on each snapshot list row and a "Snapshot this
home" action at the home level — no new UI pattern beyond what Task
Group O's own frontend note already anticipated.

## 29. Acceptance criteria

- `SmartHomeMemoryService` depends only on `SmartHomeService` +
  `SmartLightingService` + `SmartSwitchService` + `ThermostatService` +
  `ApplianceService` + `VacuumHumidifierService` + `MediaPlayerService`
  + `WaterHeaterService` + `MemoryService` — no direct `IDatabase`, no
  `EventBus`, no direct connector import, no new shared
  domain-resolution utility (§7).
- Sensor and Smart Lock device types are never accepted by
  `snapshot_device`, `snapshot_home`, or any new route/tool — enforced
  by test (§26).
- Every one of the nine supported categories' snapshot state is the
  owning service's own normalized payload, verbatim — never
  re-derived, never read from `Device.metadata_json`.
- `list_snapshots` and `delete_device_snapshot` never operate on a
  non-`"device_snapshot"`-type memory record.
- `snapshot_home` never sends a command to any device (read-only
  against devices) and never runs devices concurrently.
- Create/retrieve/delete/home-wide all require the same
  `core:smart_home_memory`/`smart_home` grant — no new principal, no
  weakened boundary relative to Task Group O.
- No `confirm_required_tools` entries added.
- Zero database/schema changes.
- Zero `EventBus`, `Scheduler`, `AnalyticsService`, or AI-generation
  references anywhere in the new code (AST-guard-tested, §26).
- Zero frontend source files touched.
- Full M12 regression, M11+M12 regression, and full backend regression
  all green before any commit (Phase 2 requirement, not this
  document's own claim).
- Clean git state (this contract as the only untracked file) before
  Phase 2 implementation begins.
