# M12 Smart Home Memory — Manual/On-Demand Device Snapshot — Logic Contract

Status: **Draft — Logic Contract only.** Written per the `M12 PHASE 0
POST-TASK-N AUDIT` and its approval (`APPROVED — PROCEED WITH PHASE 1
ONLY`). **Not approved for implementation** — no source, tests, DI,
routes, tools, connector, permission, EventBus, roadmap, CHANGELOG, or
frontend changes accompany this file. Base: the shipped M3 Memory
Platform (`MemoryService`), M12 Smart Home Core (`SmartHomeService`),
and the shipped M12 device-category services.

**Naming boundary, stated once, binding throughout this document and
whatever implementation follows it**: this capability is
**Manual/On-Demand Device Snapshot**. It is never referred to, coded,
documented, or presented as Device History, Automatic Device History,
Continuous Device Monitoring, Automatic State Tracking, or
Event-Driven Memory. A snapshot exists only because a user or agent
explicitly requested one, at that moment.

**Legend.** Every claim about code that exists today is marked
**(EXISTING)** with a `file:line` citation, verified against the
current working tree this session (clean, HEAD `3902a4d`). Everything
marked **(PROPOSED)** does not exist yet.

## 1. Scope

**In scope**: one on-demand, single-device action — capture a
device's current normalized state (as already produced by its owning
M12 service) into `MemoryService`, and retrieve previously-captured
snapshots. **Explicitly not this slice's job** (§21 gives the full
accounting): automatic/event-driven capture, scheduled or recurring
snapshots, analytics/trends over snapshots, multi-device or home-wide
snapshotting, deletion tooling, or any frontend work.

## 2. MemoryService — verified, not assumed

**(EXISTING, re-read in full this session)** `services/
memory_service.py`:
- `remember(content, *, source="user", memory_type=MemoryType.
  CONVERSATION, metadata=None, conversation_id=None, pinned=False,
  expires_at=None) -> str` (`:109-176`) — persists a SQL row (source
  of truth) then best-effort embeds and upserts into the vector store;
  **returns the memory id**. `metadata` is an arbitrary JSON-
  serializable `dict`, stored as `meta_json` (`:137-138`). Embedding
  failure is caught and logged, never raised — `remember()` still
  succeeds, degraded to keyword-only recall for that row (`:155-159`).
- **`memory_type` accepts a plain string, not only the `MemoryType`
  enum** (`memory_type: MemoryType | str`, `:114`) — confirmed by
  `MemoryType`'s own docstring (`core/types.py:91-98`): *"The value is
  free-form enough to be stored as a plain string column (no DB-level
  enum), so adding a new type later never requires a migration."*
  **This is the decisive finding for §6**: a new snapshot-specific
  type does not require touching the shared `MemoryType` enum at all.
- **`browse(*, memory_type=None, pinned_only=False,
  include_archived=False, start_date=None, end_date=None, limit=200)
  -> list[MemoryRecord]`** (`:312-342`) — **already the exact
  retrieval mechanism this slice needs**, filtered by `memory_type`,
  most-recent-first (`MemoryRepository.list_filtered`,
  `infrastructure/database/repositories/memory_repository.py:157-177`,
  `ORDER BY created_at DESC`). **No `source`-level or arbitrary-
  metadata-field filter exists** — confirmed by reading
  `list_filtered`'s full signature and body. This is the one real
  retrieval limitation this contract must design around (§7).
- `forget(memory_id) -> None` (`:178-186`) — deletion **already
  exists** generically, for any memory. **(EXISTING, re-verified)**
  no REST route or agent tool exposes it anywhere in this repository
  today (`agents/tools/memory_tools.py` has exactly two tools,
  `remember`/`recall_memory`; no `infrastructure/api/routes/memory.py`
  file exists at all). §7 resolves whether this slice adds one.
- `MemoryRecord` (`:51-61`): `id, content, source, metadata, score,
  created_at, memory_type, pinned, archived` — the complete shape any
  retrieval call returns.
- **No schema/migration concern** — confirmed directly from
  `MemoryType`'s own documented design intent (above), and from
  `remember()`'s own `metadata` parameter already accepting arbitrary
  structured data with no predefined shape.

## 3. SmartHomeService — verified, not assumed

**(EXISTING)** `require_device(device_id) -> Device`
(`services/smart_home_service.py:416-420`) raises `ServiceError` for
an unknown id — the single lookup this slice needs to resolve a
device's `device_type`, `home_id`, `room_id`, and `name` before
dispatching to the owning service (§16).

## 4. Existing device-category services — verified, not assumed

**(EXISTING, re-confirmed this session)** every shipped M12
device-category service exposes a `get_<category>_state(device_id) ->
dict[str, Any]` read method: `SmartLightingService.get_light_state`
(`:319`), `SmartLockService.get_lock_state` (`:174`),
`SensorService.get_sensor_state` (`:238`),
`SmartSwitchService.get_switch_state` (`:178`),
`ThermostatService.get_thermostat_state` (`:280`),
`VacuumHumidifierService.get_vacuum_state`/`get_humidifier_state`
(`:345`/`:400`), `MediaPlayerService.get_media_player_state` (`:330`),
`WaterHeaterService.get_water_heater_state` (`:322`). All return a
plain dict already normalized by that service's own read model — this
slice never re-derives normalization (§16).

**A real, decisive architectural asymmetry, found by reading each
service's own domain-discrimination helper**: `light`/`lock`/
`sensor`/`switch`/`thermostat` each have their **own, unique
`Device.device_type`** — a device's `device_type` field alone
identifies which single service owns it. `vacuum`/`humidifier`/
`media_player`/`water_heater` (and `fan`/`cover`, owned by
`ApplianceService`) all share **the same** `device_type="appliance"`
and are distinguished only by each service's own **private**
`_domain_for()` helper (`metadata["domain"]`/`["component"]`) — there
is no shared, public "resolve an appliance device's owning service"
utility anywhere in this repository. Supporting an appliance-domain
category here would require either duplicating that private
domain-resolution logic (directly against §16's "do not duplicate
device normalization" instruction) or trial-calling every
appliance-domain service until one accepts the device (fragile,
inefficient, and still implicitly duplicates knowledge of the
domain-to-service mapping). This finding is the primary driver of §5's
scope decision.

**`SecurityService.get_security_status()` is excluded outright** — it
is a multi-device aggregate (hazard sensors + locks combined), not a
single-device read; it does not fit "snapshot one device" at all.

## 5. MVP device-category scope — resolved, not defaulted to "all"

**Decision: Option B — three categories: Smart Lighting, Smart
Switches (Energy Management), Thermostat.** Two independent,
separately-stated reasons converge on this same set:

1. **Architectural — simple dispatch only.** All three have a unique
   `device_type` (`light`/`switch`/`thermostat`); `SmartHomeService.
   require_device` alone tells this slice which service to call, with
   no domain-resolution step to duplicate (§4).
2. **Privacy/security tier — reusing this codebase's own existing
   classification, not inventing a new one (§11).** Every one of
   Lighting's/Switches'/Thermostat's own shipped Logic Contracts
   already decided their reads are **ungated** — this codebase's own
   prior judgment that none of them carries Sensors-grade privacy
   weight. This contract reuses that exact, already-made
   classification as its own discriminator for "safe to persist,"
   rather than inventing a fresh privacy rule.

**Explicitly excluded from the MVP, each for a distinct, stated
reason**:
- **Sensors** — excluded on **privacy** grounds specifically:
  `SensorService`'s own Logic Contract already gates *reads* because
  motion/presence/occupancy device classes directly reveal who is
  home and when (`docs/M12_SENSORS_LOGIC_CONTRACT.md` §20's own
  reasoning, cited, not re-litigated here). Persisting that same data
  into a searchable, retained memory store is a **strictly larger**
  version of the exact risk that contract already took seriously for
  a single live read — this contract extends that precedent rather
  than contradicting it.
- **Smart Locks** — excluded on **security** grounds specifically:
  lock state is a direct security-posture indicator (unlocked =
  vulnerable), and this codebase already treats the *unlock* direction
  as physically safety-relevant enough to require interactive
  confirmation (`unlock_device`, `config/settings.py:513`). A
  persisted, browsable record of lock-state history compounds that
  same risk category into long-term storage.
- **Vacuum/Humidifier/Media Player/Water Heater (and Fan/Cover)** —
  excluded on **architectural** grounds only (§4) — not privacy; all
  six have "reads ungated" Logic Contracts identical in privacy tier
  to Lighting/Switches/Thermostat. A future slice could add them once
  a shared, public domain-resolution utility exists, without
  reopening this contract's own privacy reasoning.

This is a **genuinely narrower MVP than "every shipped category"** —
the explicit intent of the audit's own instruction not to default to
"all" merely because the services exist.

## 6. Snapshot naming / source — resolved, explicit, consistent

**`memory_type = "device_snapshot"`, `source = "device_snapshot"`.**
Both fields deliberately set to the same literal string, for two
distinct reasons: `memory_type` is the **retrieval discriminator**
(§7 — `browse(memory_type="device_snapshot")` isolates every snapshot
from every other memory kind); `source` records **what produced this
memory**, and "device_snapshot" is the accurate, mechanism-level
answer regardless of whether a human clicked a button or an agent
invoked a tool (§9) — matching existing usage precedent (`source=
"summary"` for `summarize()`'s own auto-stored notes, `services/
memory_service.py:430`). **No `MemoryType` enum value is added** —
per §2's finding, the plain-string path is already fully supported
and is the more conservative choice, touching zero shared/foundational
code.

## 7. Retrieval design — resolved against MemoryService's real limits

**Create**: one new `remember()` call per snapshot (§2). **No new
persistence mechanism.**

**Retrieve — two honestly-scoped capabilities, nothing more**:
1. **List snapshots** (optionally for one device): calls `MemoryService.
   browse(memory_type="device_snapshot", limit=<internal fetch size>)`
   — already-existing, most-recent-first — then, when a `device_id`
   filter was requested, filters the returned records **client-side**
   inside this slice's own new service by matching
   `record.metadata.get("device_id") == device_id`. **This is a real,
   stated limitation, not hidden**: there is no indexed, per-device
   query in `MemoryRepository` — a device-scoped list is "browse
   recent snapshots, then filter," not a targeted SQL `WHERE`. Fine
   for the bounded, low-volume nature of a manual, on-demand capability;
   would need real Phase-2-of-its-own attention if snapshot volume
   ever grew large enough for this to matter.
2. **Retrieve via existing `recall()`/`search()`** — already works
   unmodified for free-text queries against snapshot content (e.g. "what
   was my thermostat set to yesterday") since `remember()` already
   embeds snapshot content like any other memory. Not a new capability
   this contract builds — an inherited one, worth naming so it is not
   later "discovered" and reimplemented.

**Explicitly NOT built in this slice**: a dedicated delete-snapshot
tool/route. `MemoryService.forget()` already exists generically
(§2) and no memory-deletion capability of any kind is exposed via
REST or agent tool anywhere in this repository today — building one
specific to snapshots, when none exists for any other memory type,
would be scope creep beyond what this task group needs. Snapshots
inherit the same generic retention/expiration/pruning policy every
other memory type already gets (`enforce_policies()`,
`settings.memory.retention_days`) with zero special-casing required.

## 8. REST design

```
POST /api/v1/smart-home/memory/snapshots
GET  /api/v1/smart-home/memory/snapshots?device_id=<optional>&limit=<optional>
```

**No unnecessary CRUD** — no `PUT`, no `DELETE`, no single-snapshot
`GET .../{id}` (list is the only read shape; a caller wanting one
specific snapshot already has its `memory_id` from the create
response). `POST` body: `{"device_id": str}`. `POST` response:
`{"memory_id": str, "device_id": str, "device_type": str,
"snapshot_at": str}`. `GET` response: a list of stored snapshot
summaries (§9's data model). `{data, meta}` envelope, `Depends(
get_current_session)`, matching every M12 route.

## 9. Agent tools

Two tools, matching the two genuinely distinct capabilities (§7) —
not built merely to mirror REST:

| Tool | Wraps |
|---|---|
| `snapshot_device_state` | `POST .../snapshots` |
| `list_device_snapshots` | `GET .../snapshots` |

No third tool wrapping `recall()`/`search()` — those are already
exposed generically by the existing `recall_memory` tool
(`agents/tools/memory_tools.py:32-40`); duplicating them here for
snapshot content specifically would be redundant, not "meaningful,"
directly answering the instruction not to invent tools beyond real
need.

## 10. Permission / privacy model — evaluated, not copied

**Scope**: existing `smart_home` — no new scope. **Principal
(PROPOSED)**: `core:smart_home_memory`.

**Decision: BOTH create and retrieve are gated — a deliberate
departure from the majority "reads ungated" M12 precedent, explicitly
justified, not defaulted.** Every prior appliance-category module's
"reads ungated" decision was made for a **live, ephemeral** read — a
snapshot of the current moment, gone the instant a new command
changes it. A stored snapshot is categorically different: it is
**persistent and cumulatively browsable** (`browse()`/`recall()`
retrieve it indefinitely, subject only to retention policy), which
means a browsable *history* of even "safe-tier" devices (§5) reveals
patterns a single live read never could (e.g., a browsable series of
"living room light: on" snapshots over weeks starts to approximate a
presence signal, the exact risk category this contract's own §5
reasoning already took seriously for Sensors). Gating **both**
directions is the honest response to that risk, not a copy of any
single prior module's own narrower reasoning.

**No confirmation requirement.** Evaluated explicitly, not defaulted:
unlike Task Group M's Panic/Vacation Mode (blast radius: an entire
home's devices, one call), a snapshot touches exactly one device and
writes exactly one memory row — a passive record of already-existing
state, never a change to any physical device. There is no comparable
"large, hard-to-reverse consequence" here; "undo" is simply never
retrieving or acting on that one memory row again.

## 11. Privacy/security — full reasoning, not a blanket rule

Given in full inline at §5 (category exclusions) and §10
(gating both directions). Summarized: device *category* choice is the
first privacy gate (Sensors/Locks excluded outright); permission
gating on both create and retrieve is the second (persistence and
cumulative browsability treated as a materially larger risk than any
single live read); no blanket "memory is always safe" or "memory is
always dangerous" rule is asserted anywhere in this contract — each
decision is tied to a specific, named mechanism (occupancy inference,
security-posture history, cumulative pattern exposure).

## 12. EventBus — explicitly prohibited

No event subscription, no automatic capture, no automatic
state-change recording, no background memory worker, no device-
history mechanism of any kind. The pre-existing device-command
EventBus publishing gap is not touched, worked around, or relied upon
— this slice never needs it, by design, since every snapshot is
explicit and on-demand.

## 13. Scheduler — explicitly prohibited

No Scheduler dependency, no scheduled snapshots, no recurring
snapshots, no background capture of any kind.

## 14. Analytics — explicitly prohibited

No Analytics dependency, no trends, no charts, no historical
aggregation, no power analytics. A snapshot is a single, standalone
memory row; nothing in this slice computes anything over a set of
them beyond the plain listing in §7.

## 15. Database / schema — resolved

**Zero schema changes.** `MemoryService`'s existing SQLite + Chroma
storage is fully sufficient (§2) — `MemoryType`'s own documented
design explicitly anticipates new string values requiring no
migration, and `metadata` already accepts arbitrary structured data.
No new table, no new column, no new repository method (`browse()`
already provides everything §7 needs).

## 16. Architecture (PROPOSED)

```
SmartHomeMemoryService
    ↓
SmartHomeService (require_device -- device_type/home_id/room_id/name)
    ↓ (dispatch by device_type: light/switch/thermostat only, §5)
SmartLightingService / SmartSwitchService / ThermostatService
  (get_light_state / get_switch_state / get_thermostat_state)
    ↓
MemoryService (remember / browse)
```

New `services/`-layer class, depending on `SmartHomeService` +
`SmartLightingService` + `SmartSwitchService` + `ThermostatService` +
`MemoryService` — no `IDatabase` of its own, no `EventBus`, **no
direct connector import ever** (every device read already goes
through an owning service's own `ConnectivityService` chokepoint).
Never re-derives normalization — always consumes each service's own
already-normalized dict verbatim into `metadata["state"]` (§17).

## 17. Snapshot data model

**A. Snapshot content** (the `content` string passed to `remember()`,
what gets embedded/semantically searched) — a deterministic, template-
generated sentence, **not LLM-generated** (this slice has no direct
LLM dependency of its own; `remember()`'s own best-effort embedding
step is inherited transitively, unchanged):
```
"Snapshot of {device.name} ({device_type}) in home {home_id}[, room {room_id}]: {state_summary}. Captured at {snapshot_at}."
```
where `state_summary` joins only the state-specific keys of the
owning service's own read dict (excluding the identity fields —
`id`/`home_id`/`room_id`/`name`/`status`/`manufacturer`/`model`/
`external_id` — already carried in metadata, §17B, to avoid
duplicating them into the embedded text).

**B. Memory metadata** (`metadata` dict passed to `remember()`):
```python
{
  "device_id": str,
  "device_type": str,           # "light" | "switch" | "thermostat"
  "home_id": str,
  "room_id": str | None,
  "device_name": str,
  "snapshot_at": str,            # ISO 8601 UTC, this call's own timestamp
  "state": dict,                 # the owning service's get_X_state() dict, verbatim
}
```
**Never populated from `Device.metadata_json` directly** — only from
each service's own already-normalized read-model dict, which never
carries `connector_type` or any other connector-specific field. No
credential, token, secret, or raw connector configuration is reachable
through this data model, structurally — the same discipline Task
Group N's own Logic Contract already established, reused here.

**C. Retrieval identity**: the `memory_id` string `remember()`
returns — the only reference needed if a future capability (not this
one, §7) ever adds retrieval-by-id or deletion.

**No fabricated data anywhere**: `snapshot_at` is the one and only
timestamp this contract invents, and it is real (the moment of the
call) — every other field is copied verbatim from the owning service's
own live read, including `None`/unavailable values when the device
itself is unreachable (§18).

## 18. Error semantics

| Condition | Behavior |
|---|---|
| `core:smart_home_memory` not granted | `ServiceError` before any device lookup — top-level gate, checked first |
| Unknown `device_id` | `SmartHomeService.require_device`'s own `ServiceError` propagates — 404 at REST |
| Device exists but `device_type` is not `light`/`switch`/`thermostat` | A new, distinct `ServiceError` naming the unsupported category explicitly — 400 at REST (the device is real; this feature simply doesn't cover it yet) |
| Device unavailable (owning service's own `available: false`) | **A valid snapshot is still created**, honestly capturing the unavailable state itself (`state.available = False`, live fields `None`) — never skipped, never converted into a fake success with invented values |
| Memory persistence failure (a genuine DB-layer exception from `remember()`) | Propagates unhandled, exactly as any other unexpected DB failure elsewhere in this codebase — not specially caught or papered over |
| Partial failure across multiple devices | Not applicable — this MVP is single-device only (§20) |

## 19. Single-device vs multi-device — resolved

**Single-device only: `snapshot_device(device_id)`.** No home-wide or
batch snapshot endpoint. The smallest coherent scope, per instruction
— a batch/home-wide capability is a real, separately-justifiable
future extension (its own result-model design question, mirroring
Task Group M's own multi-device result model) that this slice does
not need to solve to deliver real value on its own.

## 20. No fabricated state (restated, binding)

A snapshot contains only what the owning service's `get_X_state()`
call actually returns, plus exactly one contract-invented field
(`snapshot_at`, the real capture timestamp). No availability,
attribute, or historical value is ever guessed, defaulted, or
inferred beyond what that call itself reports.

## 21. Explicitly deferred scope

| Item | Why deferred |
|---|---|
| Automatic/event-driven device history | The device-command EventBus gap remains unresolved (re-confirmed this session); this slice is deliberately scoped around that gap, not through it. |
| Scheduled/recurring snapshots | Needs M7's Scheduler, confirmed still unshipped. |
| Analytics/trends over snapshots | M20A's job, unstarted. |
| Prediction, AI-generated memory, automatic context extraction | AI Home Assistant's job — confirmed to have no genuine new backend surface today (Phase 0 audit). |
| Home-wide continuous state history | Same EventBus gap. |
| Memory-triggered automation | Home Automation's job, blocked on Scheduler + EventBus. |
| Notification integration | No notification transport exists for smart home today. |
| Sensor/Lock snapshot support | Deferred on privacy/security grounds (§5), not merely unbuilt. |
| Appliance-domain category snapshot support (Vacuum/Humidifier/Media Player/Water Heater/Fan/Cover) | Deferred on architectural grounds (§4/§5) — no shared domain-resolution utility exists yet. |
| Snapshot deletion tooling | No memory-deletion capability of any kind is exposed anywhere in this repository today (§7); out of this slice's scope. |
| Frontend implementation | Frozen this phase; see §22. |

**No placeholder code or schema for any of the above.**

## 22. Future frontend integration note (not a requirements document)

A future frontend could eventually surface a "Snapshot this device"
action on any Lighting/Switch/Thermostat device card, plus a simple
list view (device name, `snapshot_at`, state summary) reusing
whatever the app's existing Memory Timeline UI already does for other
memory types — `browse()`/`MemoryRecord` already back that UI pattern
generically (§2). No frontend requirements document is created in
this Phase 1 pass; per the established Water Heater/Security
Action/Developer Tools precedent, that would only be written after
this backend capability is implemented and verified.

## 23. Test strategy (future Phase 2 — described, not created)

Supported-category snapshot (light, switch, thermostat — each
independently), unsupported category (e.g. a lock or vacuum id
rejected with the distinct §18 error, not a 404), unknown device
(404), unavailable device (snapshot still created, `available: false`
honestly captured), normalized state preserved verbatim in metadata
(no re-derivation), `snapshot_at` is real and current, memory
persistence via real `remember()` (temp-file SQLite + a fake/stub
vector store, matching this codebase's "real components, not mocks"
discipline), retrieval via `browse()` (all snapshots, then device-
filtered), retrieval via existing `recall()` unmodified, permission
boundary on both create and retrieve (a real departure from majority
precedent, must be pinned), source-level guards confirming no
`EventBus` reference, no Scheduler reference, no Analytics reference,
no automatic-capture code path, no fabricated field beyond
`snapshot_at`, and that every §21 deferred item has zero corresponding
route/tool/field/scaffold anywhere in the implementation.

## 24. Acceptance criteria

- `SmartHomeMemoryService` depends only on `SmartHomeService` +
  `SmartLightingService` + `SmartSwitchService` + `ThermostatService`
  + `MemoryService` — no `IDatabase` of its own, no `EventBus`, no
  direct connector import.
- No existing service (`MemoryService`, `SmartHomeService`, or any
  device-category service) is modified.
- No `MemoryType` enum value is added — the plain-string path is used.
- Zero schema/migration changes.
- Only `light`/`switch`/`thermostat` devices can be snapshotted;
  every other category is explicitly rejected with a distinct error,
  never silently accepted or silently skipped.
- An unavailable device still produces a valid, honest snapshot —
  never a fabricated one, never a silent failure.
- `snapshot_at` is the only invented field anywhere in a snapshot;
  every other field is copied verbatim from the owning service's own
  read.
- Both create and retrieve require the `core:smart_home_memory`/
  `smart_home` grant — pinned by a positive test, since this
  deliberately departs from the majority "reads ungated" precedent.
- No confirmation requirement exists on either tool — pinned by a
  negative test.
- No credential, token, secret, or raw connector configuration is
  reachable through any snapshot's content or metadata.
- Zero `EventBus`, Scheduler, or Analytics reference anywhere in the
  implementation.
- Every item in §21's deferred table has zero corresponding route,
  tool, field, enum value, or scaffold in whatever implementation
  eventually follows this contract.
- No file under `frontend/` is touched.
- Full backend regression stays green (baseline at the time of
  writing: 3450 tests, 0 failures, 0 errors, 1 pre-existing skip).
- This Logic Contract is reviewed and approved **before** any
  implementation begins.

Every criterion above is implementable without EventBus, Scheduler,
Analytics, Memory infrastructure changes, connector changes, schema
changes, or frontend work.
