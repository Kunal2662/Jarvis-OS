# M12 Task Group V — Smart Home Memory Security Device-Category Expansion — Logic Contract

**Status: Phase 1. No implementation exists yet. This contract governs Phase 2.**

Authoritative basis: `M12 PHASE 0 POST-TASK-GROUP-U AUDIT` (delivered this session),
recommendation #1. Every claim in that audit relevant to this task group has been
independently re-verified against current source below, not assumed.

## 1. Scope

**In scope:**
- Add Smart Home Memory snapshot support for Siren devices (`SirenService.get_siren_state`).
- Add Smart Home Memory snapshot support for alarm_control_panel devices
  (`AlarmControlPanelService.get_alarm_control_panel_state`).
- A new Tier-3 dispatch cascade in `SmartHomeMemoryService._read_state`, active only for
  `device_type=="other"`.
- `snapshot_home` automatically picks up both new categories once dispatch is extended — no
  separate wiring.

**Out of scope (explicit, per the approved Phase 1 instruction):**
- No database/schema changes.
- No new repository/history/analytics service.
- No EventBus subscription or publication.
- No Scheduler dependency.
- No analytics/trend/diff functionality.
- No AI/LLM enrichment.
- No frontend implementation (planning doc only, Phase 2, after backend verification).
- No Panic Mode / Vacation Mode / Siren coupling / alarm_control_panel coupling.
- Sensor and Smart Lock snapshots remain **permanently** excluded (privacy/security grounds,
  unchanged since Task Group O, reaffirmed by Task Group S, reaffirmed again here — not
  reopened by this task group).
- No Camera snapshots — no `CameraService` exists (reconfirmed by fresh grep this session:
  zero `camera*.py`/`CameraService`/RTSP code anywhere in `src/`).
- No new deletion functionality — `delete_snapshot` (Task Group S) is unmodified; the two new
  categories simply become deletable through the existing, generic, category-agnostic
  `delete_snapshot(memory_id)` the moment they can be created.
- No new REST endpoints or agent tools unless proven necessary (§10 — none are).

## 2. Fresh verification — `SmartHomeMemoryService` (current, Task Groups O + S)

Read in full this session (`src/jarvis/services/smart_home_memory_service.py`, 437 lines).
Confirmed current state, not assumed from the Phase 0 audit's own summary:

- **Tier 1** (`self._readers`, dict keyed by `device.device_type`): `light`, `switch`,
  `thermostat` — direct one-shot dispatch, unique `device_type` per category.
- **Tier 2** (`self._appliance_readers`, ordered list of `(name, reader)` tuples, tried only
  when `device.device_type == "appliance"`): `fan`, `cover`, `vacuum`, `humidifier`,
  `media_player`, `water_heater` — each reader is that category's own already-public
  `get_<category>_state`; a `ServiceError` from one candidate means "not this category,"
  caught and the loop continues.
- `_read_state` (lines 267–288) is the exact, sole dispatch chokepoint: Tier 1 dict lookup,
  then Tier 2 cascade if `device_type == "appliance"`, else `UnsupportedSnapshotCategoryError`
  — a distinct `ServiceError` subclass, never confused with "unknown device."
- `_capture_snapshot` (lines 290–324) calls `_read_state` once, persists the returned dict
  **verbatim** into `MemoryService.remember`'s `metadata["state"]`, and builds `content` via
  `_snapshot_content`, which iterates `state.items()` excluding `_IDENTITY_KEYS` — this is
  category-agnostic: it has no knowledge of what fields `state` contains, so a new category's
  differently-shaped payload (e.g. `state`/`available` for alarm_control_panel vs. `on`/
  `available` for siren) requires zero change to either helper.
- `snapshot_home` (lines 336–382) iterates every device in a home, calls `_capture_snapshot`
  per device, catches `UnsupportedSnapshotCategoryError` → `"skipped"`, catches any other
  `Exception` → `"failed"`, else `"succeeded"` — sequential, partial-success, never aborts.
  This method has **zero per-category logic of its own**; it is automatically correct for any
  category `_read_state` resolves, confirming the approved instruction's claim that no change
  to `snapshot_home` itself is needed.
- Constructor (`__init__`, lines 212–252) takes each owning service as an explicit keyword
  parameter and builds `self._readers`/`self._appliance_readers` from them directly.

## 3. Fresh verification — `SirenService` and `AlarmControlPanelService`

Read in full this session (both already fully implemented and shipped, Task Groups R and U).

**`SirenService.get_siren_state(self, device_id: str) -> dict[str, Any]`**
(`src/jarvis/services/siren_service.py:227-235`):
- Calls `self._require_siren(device_id)`, which calls `SmartHomeService.require_device`, then
  raises a **plain `ServiceError`** — `f"Device {device_id!r} is not a siren."` — if
  `device.device_type != "other" or _domain_for(device) != "siren"`.
- `_domain_for` (module-private, lines 142-153): `metadata["domain"]`, falling back to
  `metadata["component"]` — entirely internal to `siren_service.py`, never exposed publicly,
  never needs to be duplicated by this task group.
- Returns `_siren_payload(device, raw)`: `{id, home_id, room_id, name, status, manufacturer,
  model, external_id, on: bool|None, available: bool}` — confirmed via
  `test_siren_payload_never_includes_raw_metadata_json` (existing test) that no
  `metadata`/`metadata_json` key is ever present.
- Ungated — no permission check inside `get_siren_state` (reads are ungated for Siren, per
  Task Group R's own Logic Contract).

**`AlarmControlPanelService.get_alarm_control_panel_state(self, device_id: str) -> dict[str, Any]`**
(`src/jarvis/services/alarm_control_panel_service.py:272-280`):
- Calls `self._require_alarm_control_panel(device_id)`, which raises a **plain `ServiceError`**
  — `f"Device {device_id!r} is not an alarm control panel."` — if
  `device.device_type != "other" or _domain_for(device) != "alarm_control_panel"`.
- Its own `_domain_for` (lines 177-187) is the byte-identical fallback order, module-private to
  `alarm_control_panel_service.py`.
- Returns `_alarm_control_panel_payload(device, raw)`: `{id, home_id, room_id, name, status,
  manufacturer, model, external_id, state: str|None, available: bool}` — confirmed via
  `test_payload_never_includes_raw_metadata_json` (existing test) that no
  `metadata`/`metadata_json` key is ever present. `state` is one of ten verbatim HA values or
  `None` if unrecognized/unavailable — never fabricated.
- Ungated — no permission check inside `get_alarm_control_panel_state`.

**Critical confirmation**: both methods raise a **bare `ServiceError`**, not a category-specific
subclass, for "this device is not [siren|alarm_control_panel]" — the exact same signal shape
Tier 2's `except ServiceError: continue` already relies on. No new exception-handling pattern
is needed; Tier 3 reuses Tier 2's own `try/except ServiceError` idiom verbatim.

## 4. Fresh verification — existing snapshot tests

Read in full this session (`tests/unit/test_m12_smart_home_memory_service.py`, 1212 lines) and
grepped `tests/unit/test_m12_smart_home_memory_tools.py` /
`tests/unit/test_m12_smart_home_memory_route.py` for `siren`/`alarm_control_panel` (zero
matches in either — no tools/route test needs correction).

Two **existing** assertions in `test_m12_smart_home_memory_service.py` are directly inverted
by this task group's approved scope and **must be corrected in Phase 2**, not silently patched
— identified explicitly here per the Phase 1 instruction:

1. **`test_unsupported_category_is_a_distinct_error`** (line 355), parametrized case at
   line 347: `("other", {"domain": "siren"})`, with an inline comment stating *"Siren lives in
   the shared 'other' bucket, domain='siren' -- simply out of this task group's named scope...
   not privacy-excluded like sensor/lock."* Under Task Group V's approved scope, a siren
   device becomes **supported**, not rejected — this parametrize case must be removed and
   replaced with a genuine still-unsupported `"other"`-domain case (e.g.
   `("other", {"domain": "valve"})`, a real, unmapped HA `"other"`-bucket domain named in
   Siren's own module docstring) so the test continues to prove the Tier-3 cascade doesn't
   falsely match every `"other"`-typed device.
2. **`test_no_deferred_functionality_exists`** (line 1193), specifically the forbidden-term
   list at line 1204: `"alarm_control_panel"` is currently asserted **absent** from the
   module's source. This task group's approved scope requires calling
   `AlarmControlPanelService.get_alarm_control_panel_state` from inside this exact module —
   `"alarm_control_panel"` will legitimately appear (import, reader-tuple key, docstring).
   This term must be removed from the forbidden-term list in Phase 2.

No other existing test in any of the three files references `siren` or `alarm_control_panel`.
The nine-category regression suite (Tier 1 + Tier 2, all existing snapshot/list/delete/
snapshot_home tests) is otherwise expected to pass **unmodified** — Tier 3 is purely additive
and gated on a `device_type` no existing test's fixtures use in a way that would newly collide
(existing "other"-typed unsupported-device tests use `{}` or non-siren/alarm domains, per §4
item 1's own analysis).

## 5. Fresh verification — DI/container wiring

Read in full this session (`src/jarvis/core/di/container.py`).

- `_build_smart_home_memory_service` (line 718): takes each owning service as an explicit
  keyword-only parameter, unchanged pattern since Task Group O, extended by Task Group S.
- `siren_service = providers.Singleton(...)` is defined at line 1677.
- `alarm_control_panel_service = providers.Singleton(...)` is defined at line 1689.
- `smart_home_memory_service = providers.Singleton(_build_smart_home_memory_service, ...)` is
  defined at line 1704 — **after** both `siren_service` and `alarm_control_panel_service` in
  file order. `python-dependency-injector` providers resolve by reference at call time, not
  declaration order, but this confirms zero reordering is required: both new dependencies are
  already fully constructed, singleton-scoped providers available to reference by the time
  `smart_home_memory_service`'s own provider block is reached, exactly as `siren_service`/
  `appliance_service`/etc. already are for the four Task Group S dependencies.

**Phase 2 wiring will be**: two new keyword parameters on `_build_smart_home_memory_service`
(`siren_service: Any`, `alarm_control_panel_service: Any`), threaded into the
`SmartHomeMemoryService(...)` call as `siren=siren_service`,
`alarm_control_panels=alarm_control_panel_service`; and two new arguments on the
`smart_home_memory_service = providers.Singleton(...)` call, referencing the existing
`siren_service`/`alarm_control_panel_service` providers. No new provider is created — this is
a rewiring of already-shipped providers, exactly matching Task Group S's own four-dependency
addition.

## 6. Fresh verification — device model / metadata handling

Read in full this session (relevant excerpts of `siren_service.py`/`alarm_control_panel_service.py`,
§3 above). Confirmed:
- Neither connector nor `DEVICE_TYPES`/`CONNECTOR_TYPES` needs any change — both Siren and
  alarm_control_panel are already fully identifiable today (Task Groups R and U's own
  findings, unaffected by anything in this task group).
- `Device.metadata_json` is never read directly by `SmartHomeMemoryService` for any category,
  Tier 1, 2, or (proposed) 3 — only ever through an owning service's own already-sanitized
  public read method. This task group introduces no new metadata-handling code at all.

## 7. Tier-3 dispatch design (resolved)

```python
# New constant, local literal copy -- mirrors _APPLIANCE_DEVICE_TYPE's own precedent
# (never importing another service's private constant, Expansion Logic Contract §7).
_OTHER_DEVICE_TYPE = "other"
```

Constructor gains two new keyword parameters, `siren: SirenService`,
`alarm_control_panels: AlarmControlPanelService`, and builds one new ordered cascade list,
`self._security_readers: list[tuple[str, _DeviceStateReader]]`:

```python
self._security_readers: list[tuple[str, _DeviceStateReader]] = [
    ("siren", siren.get_siren_state),
    ("alarm_control_panel", alarm_control_panels.get_alarm_control_panel_state),
]
```

`_read_state` gains one new `elif` branch, inserted after the Tier-2 block and before the
final `raise`, mirroring Tier 2's own shape exactly:

```python
if device.device_type == _OTHER_DEVICE_TYPE:
    for _name, security_reader in self._security_readers:
        try:
            return await security_reader(device.id)
        except ServiceError:
            continue
raise UnsupportedSnapshotCategoryError(...)  # message text updated, §8
```

**Why not reuse `_appliance_readers`'s own list/loop generically for both tiers?** The gating
condition differs (`device_type == "appliance"` vs. `device_type == "other"`), and collapsing
both into one generic "device_type -> cascade" dict would be exactly the kind of "generic
domain-resolution framework" the approved scope explicitly forbids introducing for this task
group alone — two clearly-named, independently-gated blocks read more plainly than one
parameterized helper serving exactly two three-and-two-item call sites.

**Why not duplicate `_domain_for` locally?** Both `get_siren_state` and
`get_alarm_control_panel_state` already perform the full identity check (device_type +
domain/component fallback) internally and signal failure via `ServiceError` — calling the
public method and catching that error *is* the domain check, with zero duplication. This
directly satisfies the approved instruction's requirement not to re-implement private
`_domain_for` logic.

**Ordering**: siren before alarm_control_panel — mirrors ship order (Task Group R before
Task Group U), the same convention Tier 2's own list already follows (fan/cover from Task
Group G-era work before vacuum/humidifier from J before media_player from K before
water_heater from L). Since the two domains are mutually exclusive (a device cannot
simultaneously report `domain=="siren"` and `domain=="alarm_control_panel"`), ordering has no
behavioral effect on outcome — only on which `ServiceError` message (if any were ever
inspected, which nothing does) fires first. Documented for determinism, not because it changes
behavior.

## 8. Explicit dispatch/edge-case decisions (per Phase 1 instruction #5)

- **Unsupported `"other"` domain** (e.g. `domain="valve"`, `domain="select"`, or any
  unmapped/unknown value): both readers raise `ServiceError` (device_type matches but domain
  doesn't), the Tier-3 loop exhausts, falls through to `UnsupportedSnapshotCategoryError` —
  identical shape to Tier 2's own `("appliance", {"domain": "unknown_appliance_domain"})` case.
- **Missing domain metadata entirely** (`metadata={}` on an `"other"`-typed device): both
  services' own `_domain_for` returns `None` (no `domain`, no `component` fallback either) →
  both raise `ServiceError` → `UnsupportedSnapshotCategoryError`, same as above.
- **Component metadata used as fallback** (MQTT Discovery-sourced device, `metadata={
  "component": "siren"}`, no `domain` key): `SirenService._domain_for` already falls back to
  `component` internally — `get_siren_state` succeeds exactly as it does when called directly
  against `/api/v1/sirens/{id}`. No special handling needed in `SmartHomeMemoryService`.
- **A service raises `ServiceError` for a reason *other* than "wrong category"** (there is no
  such path today — `get_siren_state`/`get_alarm_control_panel_state` raise `ServiceError`
  *only* from `_require_siren`/`_require_alarm_control_panel`'s identity check; a genuinely
  unreachable connector is handled internally via `contextlib.suppress(ConnectivityError)` and
  never propagates as `ServiceError`). Tier 3 therefore cannot mistake a transient failure for
  "wrong category" — confirmed by source, not assumed.
- **Unavailable device** (connector unreachable): the owning service's own read already
  returns `available: False` with the live field (`on`/`state`) as `None` rather than raising
  — `_capture_snapshot` persists this honestly, exactly as every existing category already
  does for an unavailable device. No new behavior.
- **Device is not Siren/alarm_control_panel** (any other `"other"`-bucket device, or any
  entirely different `device_type`): falls through to `UnsupportedSnapshotCategoryError`,
  `snapshot_home` records `"skipped"` — unchanged shape from today.
- **Deterministic dispatch ordering**: siren, then alarm_control_panel (§7). Tier order itself
  (1 → 2 → 3) is unchanged and remains deterministic — a device's `device_type` selects at
  most one tier's cascade; there is no cross-tier ambiguity.
- **`snapshot_home` success/failure/skipped semantics**: entirely unchanged — `snapshot_home`
  has no per-category code; it calls `_capture_snapshot`, which calls `_read_state`. Two
  additional categories now resolve where they previously fell through to
  `UnsupportedSnapshotCategoryError` ("skipped"); nothing about the failure/success accounting
  shape changes.

`UnsupportedSnapshotCategoryError`'s message text updates from the current 9-category
enumeration to include the two new categories:

```python
raise UnsupportedSnapshotCategoryError(
    f"Device {device.id!r} is a {device.device_type!r}; snapshotting is only "
    "supported for light/switch/thermostat/fan/cover/vacuum/humidifier/"
    "media_player/water_heater/siren/alarm_control_panel devices in this release."
)
```

The existing test regex `match="only supported for"` (unchanged substring) continues to match.

## 9. Security / privacy re-verification

- **No `metadata_json` leakage**: confirmed transitively — neither new reader ever returns a
  `metadata`/`metadata_json` key (§3), and `_capture_snapshot`/`_snapshot_content` only ever
  touch the dict `_read_state` returns, never `Device.metadata_json` directly, for any tier.
- **No credentials/tokens/network data**: neither `_siren_payload` nor
  `_alarm_control_panel_payload` includes a connector config, credential, or network-layer
  field of any kind — both are pure device-identity + normalized-state dicts (§3's own field
  lists).
- **No new sensitive security-history exposure beyond the approved Siren/alarm-panel state
  snapshot**: an alarm_control_panel snapshot can capture `state` — one of ten values including
  `"triggered"`, `"disarmed"`, `"armed_home"`/`"armed_away"`/etc. A persisted history of these
  values is a real, named security-posture signal, structurally identical in kind to the
  privacy concern that keeps Lock snapshots permanently excluded. **This is accepted, explicit,
  approved scope** (the user's own Phase 1 instruction explicitly approves alarm_control_panel
  snapshot support), not an oversight — recorded here so the tradeoff is visible in the
  contract, not silently absorbed. It does not extend to Lock (still excluded) or any other
  category.
- **Sensor/Lock exclusion preserved**: `_readers` (Tier 1) and the constant literals
  `_APPLIANCE_DEVICE_TYPE`/`_OTHER_DEVICE_TYPE` never reference `"sensor"` or `"lock"` as a
  `device_type`; the existing architecture guard test
  (`test_no_deferred_functionality_exists`'s own `'"sensor":' not in source` /
  `'"lock":' not in source` structural assertions) continues to hold, since neither literal
  key is introduced by this change.
- **No PIN/code exposure**: `AlarmControlPanelService.get_alarm_control_panel_state` has no
  code/PIN parameter or field anywhere (Task Group U's own permanent, structural guarantee) —
  a snapshot of an alarm control panel's state can never carry one, transitively.

## 10. REST / agent-tool impact

**No new REST endpoint. No new agent tool.** Verified by fresh read of both
`routes/smart_home_memory.py` and `agents/tools/smart_home_memory_tools.py` (§ "fresh reads,"
above): every route/tool already calls `snapshot_device`/`list_snapshots`/`delete_snapshot`/
`snapshot_home` generically, with zero per-category branching anywhere in either file. Once
`_read_state` resolves a siren or alarm_control_panel device, `POST .../snapshots` (body
`{"device_id": ...}`), `GET .../snapshots`, `DELETE .../snapshots/{id}`, and
`POST .../snapshots/home/{home_id}` all handle it automatically — this is the same "REST/tool
layer is category-agnostic by construction" property Task Group S already relied on and
verified for its own four new categories.

## 11. Frontend requirements (planning-only note for Phase 2)

Per the approved instruction, a frontend-requirements document will be written in Phase 2,
**after** backend verification, following the exact planning-only precedent every prior task
group's own frontend-requirements doc has used (no frontend source, `BACKEND CAPABILITY`
classification table). It will document: that `GET /smart-home/memory/snapshots` and
`POST .../snapshots/home/{home_id}` responses may now include `device_type: "other"` rows with
`device_type` metadata identifying `siren`/`alarm_control_panel` (via the persisted
`metadata["state"]` shape, which differs by category exactly as it already does for e.g. fan
vs. water_heater); that a security-conscious UI may want to visually distinguish
alarm-panel-state history from other device snapshots given §9's own security-posture note;
and that no new endpoint exists to filter snapshot listing by category (the existing
`device_id`-only filter is unchanged).

## 12. Non-goals / deferred scope (explicit)

- Automatic/event-driven/scheduled snapshot capture of Siren or alarm_control_panel state —
  still blocked on the same EventBus device-command publishing gap named in the Phase 0 audit,
  unchanged by this task group.
- Diff/trend/analytics views over snapshot history — M20A's job, unstarted.
- Any coupling between a captured alarm_control_panel/siren snapshot and Panic Mode, Vacation
  Mode, or either device-category service's own mutation methods — this module remains
  strictly read-only against devices, as it already is.
- Sensor and Smart Lock snapshot support — permanently excluded, not revisited by this
  contract.
- Camera snapshot support — no `CameraService` exists to read from.
- Any new deletion mechanism, filter parameter, or REST/tool surface beyond what already
  exists.
- Extending Tier 3 to any further `"other"`-bucket domain (e.g. a future `valve`/`select`
  device-category service) — out of this task group's own named scope; a future task group's
  own decision.

## 13. Test strategy (described for Phase 2, not created now)

All new tests added to the existing `tests/unit/test_m12_smart_home_memory_service.py` (no new
test file — this is an internal dispatch extension to an already-tested module, matching Task
Group S's own precedent of extending, not forking, the test file). Matrix:

**Identity / dispatch:**
1. A device with `device_type="other"`, `metadata={"domain": "siren"}` resolves via
   `SirenService.get_siren_state` — `snapshot_device` succeeds, snapshot content/metadata
   reflects the siren's own `on`/`available` fields.
2. Same, `metadata={"component": "siren"}` (component fallback, no `domain` key) — succeeds
   identically.
3. A device with `device_type="other"`, `metadata={"domain": "alarm_control_panel"}` resolves
   via `AlarmControlPanelService.get_alarm_control_panel_state` — succeeds, snapshot reflects
   `state`/`available`.
4. Same, `metadata={"component": "alarm_control_panel"}` — succeeds identically.
5. Domain precedence: `metadata={"domain": "siren", "component": "switch"}` resolves as siren
   (domain wins), mirroring `SirenService`'s own precedence test.
6. `device_type="other"`, `metadata={}` (no domain/component at all) — falls through both
   readers, raises `UnsupportedSnapshotCategoryError`.
7. `device_type="other"`, `metadata={"domain": "valve"}` (a real, unmapped "other"-bucket
   domain) — falls through both readers, raises `UnsupportedSnapshotCategoryError`. Replaces
   the now-inverted `("other", {"domain": "siren"})` parametrize case (§4).
8. A siren device is never matched by the alarm_control_panel reader and vice versa (no false
   cross-match) — covered implicitly by 1/3 plus an explicit assertion that only the expected
   reader's own fields appear in the persisted state.
9. `device_type="switch"` with a stray `metadata={"domain": "siren"}` is **not** picked up by
   Tier 3 (Tier 3 only runs for `device_type=="other"`) — proves tier gating, mirroring the
   existing `("appliance", {"domain": "unknown_appliance_domain"})`-style guard.

**Reads / content:**
10. Persisted `metadata["state"]` for a siren snapshot matches `SirenService.get_siren_state`'s
    own return value verbatim (byte-for-byte dict equality).
11. Same, alarm_control_panel snapshot vs. `get_alarm_control_panel_state`.
12. Snapshot `content` (the generated text) mentions siren/alarm-panel-specific fields (e.g.
    `on=True` / `state=armed_home`) via the existing generic `_snapshot_content` template — no
    new template code needed, test proves the existing one handles the new shape.
13. Unavailable siren/alarm_control_panel (connector unreachable) still produces a snapshot
    with `available: False` and the live field `None` — never raises, never fabricates.
14. No `metadata`/`metadata_json` key ever appears in a persisted siren/alarm_control_panel
    snapshot's `metadata["state"]` — direct assertion, mirroring the existing
    `test_siren_payload_never_includes_raw_metadata_json`-style check but at the memory-service
    boundary.

**`snapshot_home` / mixed-category:**
15. A home containing one of each: light, fan, siren, alarm_control_panel, and one
    unsupported-category device (e.g. a bare `"other"`-typed device with no matching domain) —
    `snapshot_home` reports 4 succeeded, 1 skipped, 0 failed, and per-device `results` entries
    for all 5, in list order.
16. Empty home (`list_devices` returns `[]`) — `snapshot_home` returns
    `requested_count=0`/all counts 0, `results=[]`, unchanged from today.
17. A home containing **only** unsupported devices (sensors, locks, and a non-matching
    "other") — all skipped, 0 succeeded, 0 failed — proves Tier 3 doesn't accidentally
    "succeed" on something it shouldn't.
18. A siren whose live read raises an unexpected exception (simulated) is recorded `"failed"`,
    not `"skipped"` — proves Tier 3 participates correctly in the existing failed-vs-skipped
    distinction (`UnsupportedSnapshotCategoryError` → skipped; anything else → failed).
19. Deterministic ordering: two "other"-bucket devices (one siren, one alarm_control_panel) in
    a home produce `results` entries in the same order `list_devices` returned them — proves
    Tier 3 doesn't reorder within `snapshot_home`'s own already-deterministic device iteration.

**Permissions:**
20. `snapshot_device`/`snapshot_home`/`list_snapshots` against a siren or alarm_control_panel
    device still require only the existing `core:smart_home_memory`/`smart_home` grant — no
    new principal, and critically, **no** requirement that `core:sirens`/
    `core:alarm_control_panels` also be granted (Tier 1/Tier 2 already establish this
    "memory's own grant is sufficient" precedent; this test proves Tier 3 doesn't
    silently require the owning service's own permission too).

**Regression:**
21. The full existing nine-category test suite in `test_m12_smart_home_memory_service.py`
    passes with zero further modification beyond the two corrections named in §4.
22. `test_m12_smart_home_memory_tools.py` and `test_m12_smart_home_memory_route.py` pass
    unmodified (zero siren/alarm_control_panel-specific assertions needed there, confirmed §10
    — though a REST/tool-level round-trip test for the new categories is still worth adding
    for coverage, even though no route/tool code changes).

**Architecture guards:**
23. `test_no_deferred_functionality_exists`'s forbidden-term list, corrected per §4 item 2,
    still passes (no `EventBus`/`Scheduler`/`notification`/`predict`/`continuous`/
    `automatic_history` term appears in the module's real code).
24. Import guard: `siren_service`/`alarm_control_panel_service` modules are imported only for
    typing (`TYPE_CHECKING`) — the constructor receives already-constructed instances, exactly
    like every other owning service, never importing `SirenService`/`AlarmControlPanelService`
    beyond the type-check block.
25. `AlarmControlPanelService`'s own permanent PIN/code absence is not re-tested here (already
    exhaustively covered in Task Group U's own test suite) — this module has no code path that
    could reintroduce one, since it only ever calls the read-only `get_alarm_control_panel_state`.

## 14. Acceptance criteria

- Tier-3 cascade added to `_read_state`, gated on `device_type=="other"`, trying
  `siren.get_siren_state` then `alarm_control_panels.get_alarm_control_panel_state`, each
  guarded by `except ServiceError: continue`.
- `SmartHomeMemoryService.__init__` gains exactly two new required keyword parameters:
  `siren: SirenService`, `alarm_control_panels: AlarmControlPanelService`.
- `_UnsupportedSnapshotCategoryError` message text updated to enumerate 11 categories.
- DI container: `_build_smart_home_memory_service` gains the two new parameters; the
  `smart_home_memory_service` provider call threads the two already-existing `siren_service`/
  `alarm_control_panel_service` providers through.
- Zero changes to `routes/smart_home_memory.py`, `agents/tools/smart_home_memory_tools.py`,
  `snapshot_home`, `delete_snapshot`, `list_snapshots`, the snapshot data model, or any
  connector/`DEVICE_TYPES`/schema.
- The two named pre-existing test corrections (§4) are made explicitly, not silently.
- Full test matrix (§13) implemented and green; full nine-category regression green; M12
  regression green; M11+M12 regression green; full backend regression green.
- Black/Ruff/Mypy clean against the same baseline-comparison discipline every prior task group
  used (compare against current `HEAD`, `ea26aaa`).
- Frontend requirements doc written after backend verification, planning-only.
- `CHANGELOG.md`/`docs/MASTER_ROADMAP.md` updated to mark only this expansion slice shipped —
  not Smart Home Memory complete, not M12 complete.
- Exactly two commits (`feat(m12-v)`/`docs(m12-v)`), pushed, matching every prior task group's
  own convention.

## Phase 1 safety confirmation

- Exactly one new untracked file: this Logic Contract.
- Zero tracked changes.
- `HEAD`/`origin/feature/m22-task-group-c` unchanged at `ea26aaa9c1d184b6b59afc8245b32c45203819d2`.
- No commit made. No push made.
