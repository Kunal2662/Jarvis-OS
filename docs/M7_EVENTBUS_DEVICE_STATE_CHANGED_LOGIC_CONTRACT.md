# M7 EventBus Tier 2 — Device State-Changed Event — Logic Contract

**Status: Phase 1 planning document only. Contains zero source-code
changes.** Built directly on the completed Phase 0 audit's evidence,
with every load-bearing claim freshly re-verified against current
source in this same session before being relied on here (see §2). No
implementation accompanies this document, and none is authorized by
it. Scope is Tier 2's *first slice only* — a lifecycle-status
state-changed event — never attribute-level state, never a
cross-category normalized schema.

## 1. Scope

**In scope**: one new, additive event — `DeviceStateChangedEvent` —
published only when a device's generic lifecycle `status`
(`discovered`/`pairing`/`paired`/`offline`/`unreachable`/`removed`)
genuinely transitions, anchored at `SmartHomeService.
report_device_state()`.

**Out of scope** (see §17 for the complete list with owners):
per-category attribute state (brightness, temperature, humidity,
etc.), Sensor state-change events, real-time Home Assistant updates,
continuous MQTT-push-to-persistence wiring, event batching/rate
limiting, state history/analytics, Event Viewer, frontend integration,
correlation IDs, automatic Smart Home Memory capture, Home Automation
implementation, any fix to `DeviceUpdatedEvent`'s own existing
same-value gap (documented, not fixed — see §6).

## 2. Fresh verification performed this phase

Re-read, this session, immediately before drafting: `SmartHomeService.
report_device_state`/`pair_device`/`update_device`/`delete_device`/
`_publish_device` (`smart_home_service.py:361-489,598-607`, in full);
`DeviceRepository.update`/`add`/`delete`
(`infrastructure/database/repositories/smart_home_repository.py:264-
376`, in full); `runtime_ws_hub.py`'s `EVENT_TYPE_NAMES` entry for
`DeviceUpdatedEvent` (confirmed present: `"device.updated"`,
`runtime_ws_hub.py:241`); the existing pinned tests in
`test_smart_home_service.py` (`report_device_state`/`pair_device`/
`update_device` sections, lines 44-59, 206-262, 461-504). `EventBus`
(`event_bus.py`), `events.py`'s `DeviceUpdatedEvent`/
`DeviceCommandExecutedEvent`, and `ConnectivityService.
refresh_device_state`/Tier 1's implementation were freshly read during
Phase 0 in this same session with zero source changes since (confirmed
via `git diff --stat HEAD` against every relevant file — empty output,
i.e. byte-for-byte identical to the Phase 0 read). No file listed in
the Phase 0 audit's evidence base has drifted.

## 3. Current architecture (as verified, not assumed)

- `SmartHomeService.report_device_state(device_id, *, status,
  touch_last_seen=True)` (`smart_home_service.py:361-384`): fetches
  the `Device` row (`device = await self.get_device(device_id)`,
  capturing the *old* status into a local variable), then
  unconditionally writes the new status via `DeviceRepository.update`
  and unconditionally publishes `DeviceUpdatedEvent(action=
  "status_changed", status=status)` through the shared
  `_publish_device` helper — **regardless of whether the new status
  equals the one just fetched.** The old status is never read after
  being fetched.
- `SmartHomeService.pair_device(device_id)` (`smart_home_service.py:
  386-410`): the *only* other status-transition writer. Its own
  precondition (`if device.status not in {"discovered","offline",
  "unreachable"}: raise ServiceError`) makes a same-value call to
  `pair_device` **structurally impossible** — you cannot call it on an
  already-`"paired"` device without it raising first (confirmed by the
  existing pinned test `test_pairing_an_already_paired_device_is_
  rejected`). `pair_device` therefore has no same-value gap to fix;
  only `report_device_state` does.
- `DeviceRepository.update()` (`smart_home_repository.py:330-368`):
  fetch → mutate the same ORM object in place → return it. No
  diffing, no previous-value capture, at the repository layer.
- `_publish_device` (`smart_home_service.py:598-607`): the single
  shared helper `report_device_state`, `pair_device`, `update_device`,
  and `delete_device` all funnel through to publish
  `DeviceUpdatedEvent`. A guard added inside `report_device_state`
  itself (before calling `_publish_device`) would not need to touch
  this shared helper.
- `DeviceUpdatedEvent` (`events.py:940-953`) **is already registered
  in `EVENT_TYPE_NAMES`** (`runtime_ws_hub.py:241`, relay name
  `"device.updated"`) — confirmed fresh, not assumed. This is the
  single most important architectural fact distinguishing Tier 2 from
  Tier 1: Tier 1's own event was new and deliberately unrelayed;
  `DeviceUpdatedEvent` is old, shipped, and **already reaches any
  currently-connected frontend today.**
- No existing pinned test exercises the same-value/no-op case for
  `report_device_state` — both `test_report_device_state_updates_
  status_and_touches_last_seen` (`discovered`→`paired`) and
  `test_report_device_state_publishes_status_changed`
  (`discovered`→`offline`) are genuine transitions. **Nothing in the
  current regression suite locks in the unconditional-publish behavior
  as an intentional contract** — but the *absence* of a test doesn't
  prove the absence of a real external consumer relying on it (see §6).

## 4. Validating, not copying, Phase 0's conclusions

Phase 0 (§9) recommended `SmartHomeService.report_device_state()` as
the canonical publication point. Re-validated here against the fresh
re-read in §3: confirmed correct — it remains the only place a
device's previous lifecycle status is already fetched into scope at
zero extra query cost, and it already holds a live `EventBus`
reference. No change to that conclusion.

Phase 0 (§20, §35's open question) left the `DeviceUpdatedEvent`
fix-in-place-vs-additive question open pending this Logic Contract
phase. This phase's fresh evidence (§3: no pinned test exercises the
no-op case) makes Option A *test-safe* in a way Phase 0 could not have
confirmed without this re-read — but test-safety is not the same as
external-consumer-safety (frontend source was not, and is not in this
backend-only investigation, read). §6 resolves this explicitly, with
the added evidence this phase surfaced.

## 5. Event semantics — `DeviceStateChangedEvent`

Represents: **"this device's generic lifecycle status genuinely
transitioned from one value to a different value."** Distinguished
precisely from "observed": this event is published *only* when a
same-value guard (§7) confirms `new_status != previous_status` — an
observation that finds the same status again produces no event at
all. This is the "changed" semantic Phase 0 (§11) identified as
requiring the guard to be honest; the guard is part of this contract's
design, not deferred.

**Explicitly not**: a claim about *why* the status changed (command-
induced vs. externally observed — indistinguishable with current
evidence, per Phase 0 §15); a claim about *per-category attribute*
state (brightness, temperature, etc. — never persisted anywhere, per
Phase 0 §7/§10); a replacement for, or authority over, `DeviceUpdatedEvent`
(§6).

## 6. Same-value guard / `DeviceUpdatedEvent` decision

**Decision: Option B — leave `DeviceUpdatedEvent` and
`report_device_state`'s existing publish behavior completely
untouched. Add `DeviceStateChangedEvent` as a new, purely additive
publish call, independently guarded, inside `report_device_state`.**

Both options evaluated on the instruction's own required axes:

| Axis | Option A (fix `DeviceUpdatedEvent` in place) | Option B (additive `DeviceStateChangedEvent`) |
|---|---|---|
| Architecture | Single source of truth; no duplicate concepts | Two similar-but-distinct events coexist |
| Backward compatibility | Changes the *frequency* of an already-shipped event's publication — fewer publishes than today for no-op refreshes | Zero change to any existing code path or behavior |
| Frontend/WebSocket impact | **Unknown and unverifiable from this backend-only investigation** — `DeviceUpdatedEvent` is already relayed (`"device.updated"`) to any connected frontend; if any current consumer treats a repeated `status_changed` publish as a liveness/heartbeat signal rather than strictly a transition, this silently removes that signal | None — the existing relayed event's behavior, frequency, and meaning are unchanged for every current consumer |
| Regression risk (backend tests) | Low — verified fresh (§3) that no pinned test exercises the no-op case | None — nothing existing is touched |
| Fixes the Phase 0 P1 finding | Yes, directly | No — the pre-existing gap in `DeviceUpdatedEvent` remains, undisturbed |

Option A is genuinely *test-safe*, verified this phase, not merely
assumed. It is rejected anyway because the instruction's own governing
rule — "completed working functionality must remain unchanged unless
the contract explicitly proves a necessary correctness/rework change"
and "do not silently change existing behavior" — requires proof, and
this investigation cannot prove frontend-consumer safety without
reading frontend source, which is out of scope here. Absence of
evidence of harm is not evidence of absence of harm for an
already-shipped, already-relayed event. Option B carries zero such
risk by construction: it adds a new, independently-guarded, currently
non-existent event and touches nothing else.

**The Phase 0 P1 finding (`DeviceUpdatedEvent` publishes
unconditionally, contradicting its own docstring's stated intent) is
therefore *not* fixed by this contract.** It remains open, documented,
and — per §3's fresh evidence that no test currently locks in the
buggy behavior — is a legitimate, small, separately-approvable future
fix if the project later decides the frontend-consumer risk is
acceptable. This contract does not decide that; it only declines to
bundle that decision into Tier 2's first slice.

## 7. Previous / current state and the guard itself

Inside `report_device_state`, after the existing `device = await self.
get_device(device_id)` fetch (already there, unchanged) and before the
existing `DeviceRepository.update` call:

```
previous_status = device.status
# ... existing validation, existing DeviceRepository.update call, unchanged ...
# existing _publish_device(..., action="status_changed", ...) call, unchanged ...
if previous_status != status:
    await self._publish_state_changed(device_id, device.home_id,
        device_type=device.device_type, room_id=device.room_id,
        previous_status=previous_status, status=status)
```

(Illustrative only — exact placement, connector_type resolution, and
helper naming are Phase 2 implementation detail, not decided here.)

**Exactly when the event is emitted**: only when `report_device_state`
is called (i.e., only on an explicit `ConnectivityService.
refresh_device_state()` call, itself only reachable via the one
existing on-demand REST route — confirmed unchanged from Phase 0 §4)
**and** the newly-observed status differs from what was already
persisted.

**First-observation behavior**: every `Device` row is created with a
default `status="discovered"` (`models.py`, confirmed via Phase 0's
fresh read) — there is no "null previous status" case for this field.
The very first `report_device_state` call for a device therefore
already has a real `previous_status` to compare against (`"discovered"`
in the common case) and behaves like any other transition — no special
first-observation suppression is needed for this *lifecycle-status-only*
slice (this differs from a hypothetical future attribute-level event,
where "first reading" genuinely has no prior value — explicitly out of
this slice's scope).

**Repeated identical status**: produces **no** `DeviceStateChangedEvent`
— the guard's entire purpose. `DeviceUpdatedEvent` continues to publish
unconditionally on the same call, unchanged (§6).

## 8. Event schema

```python
@dataclass(frozen=True, slots=True)
class DeviceStateChangedEvent(Event):
    device_id: str = ""
    home_id: str = ""
    room_id: str = ""
    device_type: str = ""
    connector_type: str = ""
    previous_status: str = ""
    status: str = ""
```

`id`/`occurred_at` inherited free from the base `Event` class, matching
every other event in this codebase, including Tier 1's own.
`connector_type` resolved via the same existing `connector_type_for()`
helper Tier 1 already reuses (`connectivity_service.py:63-79`) —
`SmartHomeService` does not currently import this helper, so Phase 2
must decide whether to pass it in from the one caller
(`ConnectivityService.refresh_device_state`, which already has it) or
resolve it independently; not decided here, flagged for Phase 2.

**Explicitly prohibited**, matching Tier 1's own precedent exactly:
`metadata_json` (discovery-time-only, never proven live-relevant, per
Phase 0 §7); raw `DeviceState.attributes` (unvetted, connector-supplied
free-form data — never available at this chokepoint anyway, since
`report_device_state` only ever receives a mapped `status` string, not
raw connector attributes); credentials/tokens (never present in this
data path — connector `connect(config)` is structurally separate);
raw MQTT payloads (not available at this chokepoint — this event
publishes from `SmartHomeService`, two layers removed from any
connector); command payloads (irrelevant — this is not a command
event).

## 9. Availability

**Decision: availability transitions (`offline`↔`unreachable`↔`paired`
etc.) are represented through the same `DeviceStateChangedEvent`, not
a separate event type.** `Device.status`'s existing closed vocabulary
already encodes availability as ordinary status values — a
`"paired"`→`"offline"` transition is exactly the same shape of fact as
a `"discovered"`→`"paired"` transition, and both flow through the
identical `report_device_state` chokepoint with the identical guard.
Introducing `DeviceAvailabilityChangedEvent` as a distinct type would
duplicate the exact same mechanism for no payload or consumer benefit
the evidence supports — rejected on the same "smallest architecture
the evidence supports" basis Tier 1 used to reject a parallel command
event per outcome type.

## 10. Duplicate-event strategy

The same-value guard in §7 is the entire strategy. Verified against
every duplicate-risk source Phase 0 identified (§14): MQTT QoS-1
redelivery, MQTT retained-message replay on reconnect, repeated manual
refresh, process restart — **all of these can, at most, cause
`report_device_state` to be called more than once with the same
resulting status**, and the guard compares against the already-fetched
current DB row before publishing, so every one of these produces zero
duplicate `DeviceStateChangedEvent`s. No state hashing, no dedicated
last-known-state cache, no new persistence table, no explicit dedup
table, and no source sequence number are introduced — none is needed,
confirmed by re-tracing each duplicate source against the guard's
actual comparison point.

## 11. EventBus behavior

Re-verified fresh in Phase 0 and re-confirmed unchanged this phase
(§2): `EventBus.publish()`'s existing per-handler `try/except
Exception` isolation (never re-raised) already, unconditionally,
covers `DeviceStateChangedEvent` with zero new code — the same
guarantee every other event in this codebase already relies on. No
new retry, queue, persistence, or dedup infrastructure is created;
none is justified by any evidence gathered.

## 12. WebSocket / frontend boundary

**Decision: `DeviceStateChangedEvent` remains unpublished/unrelayed
for this entire slice** — declared in `events.py` (Phase 2), but
**not** added to `EVENT_TYPE_NAMES`, and instead named in
`UNPUBLISHED_EVENT_TYPES` (`runtime_ws_hub.py`), matching Tier 1's own
precedent and the existing treatment of `IntegrationConnectionTestEvent`
and its siblings. No `RuntimeWebSocketHub` behavior changes, no
frontend WS-contract regeneration, no frontend code of any kind. This
mirrors §6's caution exactly: a *new* event with zero existing
consumers carries zero backward-compatibility risk either way, so the
conservative default (declared but not relayed until a real consumer
exists) is the correct, evidence-matched choice — not modified in this
Phase 1 document, only decided; the actual `UNPUBLISHED_EVENT_TYPES`
edit is Phase 2 implementation.

## 13. Scheduler boundary

Not modified, not referenced. No polling loop, automatic refresh
mechanism, or scheduled state-check is introduced anywhere by this
contract — `report_device_state` remains reachable only via the one
existing on-demand REST route, exactly as confirmed in Phase 0 §4 and
re-confirmed unchanged in §3 above. `ScheduleService` gains no new
capability and needs none: any future scheduled "check device state"
step (if ever built) would call the same existing service methods any
other caller does, producing the identical event automatically — the
exact non-duplication principle Tier 1's own §14 already established
for command events, unchanged and equally applicable here, though
building such a scheduled step is itself out of this contract's scope.

## 14. MQTT / Home Assistant boundary

Neither connector is modified, referenced, or newly depended upon.
This slice is deliberately connector-agnostic: it operates entirely
inside `SmartHomeService`, downstream of whichever connector
`ConnectivityService.refresh_device_state()` already pulled from. No
Home Assistant WebSocket client is added (Phase 0 §26 confirmed this
would be a separate, larger, connector-level change requiring its own
Windows/`ProactorEventLoop` compatibility verification per CLAUDE.md's
own constraint). No automatic MQTT push-to-persistence wiring is
added — MQTT's existing `_state_cache` push path remains exactly as
Phase 0 found it: internal to the connector, reachable only by an
explicit `read_state()`/`refresh_device_state()` pull, never
automatically forwarded.

## 15. Smart Home Memory boundary

`SmartHomeMemoryService` is not modified, not subscribed to
`EventBus`, and gains no new capability. Its own module docstring
(re-confirmed in Phase 0 §7/§10) already, independently, prohibits
exactly this kind of automatic/event-driven coupling. `EventBus`
remains a generic transport; a future subscriber could react to
`DeviceStateChangedEvent` by calling `SmartHomeMemoryService.
snapshot_device` — that subscriber is not built here, and building it
would be a separate, later decision with its own approval.

## 16. Home Automation compatibility

`DeviceStateChangedEvent`, as scoped here, is **sufficient** for
exactly one class of future trigger: "a device became unavailable" /
"a device became available" (and any other lifecycle-status
transition, e.g. `discovered`→`paired`). It is **explicitly
insufficient** for every attribute-level trigger example named in
Phase 0 §17 — light turned on, switch turned off, temperature/humidity
changed, sensor state changed, door unlocked — none of these are
lifecycle-status transitions; none is persisted anywhere by this
slice or by any existing code. Building Home Automation triggers for
those requires the state-normalization work named in §17 as deferred,
not this contract.

## 17. State normalization boundary

No universal device-state schema is created. Phase 0 §10's finding
stands, re-confirmed: 12 device-category services each build their own
ad-hoc `dict[str, Any]` state payload with no shared base type,
inconsistent `available` field presence/naming. This contract does not
touch any of the 12 M12 device services, does not add a shared
schema, and does not attempt to unify their state representations.
Attribute-level normalization remains a distinct, future, larger
initiative (Phase 0 §9's "Option F") with its own eventual Logic
Contract, not a prerequisite this slice silently assumes solved.

## 18. Security / privacy

**Safe, confirmed**: `device_id, home_id, room_id, device_type,
connector_type, previous_status, status` — a closed, six-value
vocabulary for both status fields, the same class of fields Tier 1
already publishes safely.

**Explicitly excluded, confirmed via §8**: raw `DeviceState.attributes`
(not even reachable at this chokepoint — `report_device_state` only
ever receives a mapped status string), `metadata_json`, any
credential/token, any command payload, raw MQTT payload text. Sensor
occupancy/presence-revealing values and Smart Lock state are entirely
out of reach of this event by construction — this slice covers only
the generic `Device.status` lifecycle field, which carries no
category-specific attribute of any kind, sensitive or otherwise.

No new redaction framework is introduced or needed — the closed
lifecycle-status vocabulary is safe by construction, exactly as Tier 1
concluded for its own payload.

## 19. Compatibility with M0–M6 feature freeze and M12 closure

`SmartHomeService` is M12 Task Group A, and M12 Feature Development is
recorded as closed per the current checkpoint. This contract's change
to `report_device_state` is **purely additive** — a new local variable
capture, a new comparison, and one new conditional publish call to a
brand-new event type — with **zero modification to any existing
statement, return value, exception, or publish call** already in that
method. This mirrors exactly how Tier 1 added code to
`ConnectivityService` (also nominally M12-owned) without being treated
as "new M12 feature work": both are M7 EventBus infrastructure reusing
an existing M12 chokepoint, not M12 functionality being extended. No
dispensation from the M12-closure status is required because no M12
*behavior* changes (§6's Option B decision is precisely what keeps
this true).

## 20. Testing strategy (Phase 2)

- **Emission — genuine transition**: `report_device_state(id,
  status=X)` where `X != current status` publishes exactly one
  `DeviceStateChangedEvent` with correct `previous_status`/`status`.
- **No emission — same-value**: `report_device_state(id, status=X)`
  where `X == current status` publishes zero `DeviceStateChangedEvent`s.
- **`previous_status` correctness**: matches the value stored
  immediately before the call, across at least two consecutive
  transitions (verifying it isn't stale/cached across calls).
- **`status` correctness**: matches the newly-written value.
- **First-observation behavior**: a freshly-registered device's first
  `report_device_state` call still fires correctly, using the
  `"discovered"` default as `previous_status` (§7).
- **Availability transitions**: `paired`→`offline`,
  `offline`→`paired`/`unreachable`→`paired` all produce the event with
  correct field values (§9).
- **MQTT/HA refresh parity**: the identical event shape results
  regardless of which connector `refresh_device_state` pulled from —
  connector-agnostic by construction (§14), verified by exercising
  both connector types' fixtures against the same assertion.
- **EventBus subscriber exception isolation**: a raising subscriber
  does not alter `report_device_state`'s own return value (mirrors
  Tier 1's own isolation test).
- **No duplicate events**: two consecutive `report_device_state` calls
  with the same target status after the first genuine transition
  produce exactly one event, not two.
- **`DeviceUpdatedEvent` unchanged**: existing pinned tests
  (`test_report_device_state_publishes_status_changed`,
  `test_pairing_publishes_status_changed_not_updated`,
  `test_report_device_state_updates_status_and_touches_last_seen`)
  continue to pass unmodified, proving §6's Option B decision was
  implemented as purely additive, not a silent behavior change.
- **REST refresh path**: the one existing `POST /connectivity/devices/
  {id}/refresh` route still functions unchanged end-to-end, now also
  producing the new event when applicable.
- **Permission/authorization**: `report_device_state` and
  `refresh_device_state` have no permission gate of their own today
  (confirmed via Phase 0's trace) — this slice adds none; a test
  should confirm no new permission requirement was accidentally
  introduced.
- **Architecture/scope guards** (source-scanning tests, matching the
  established `test_m7_schedule_service.py` convention): no connector
  file references `DeviceStateChangedEvent`; no M12 device-category
  service file references it; `SmartHomeMemoryService` gains no
  `event_bus.subscribe` call; `ScheduleService` gains no new coupling;
  `DeviceStateChangedEvent` absent from `EVENT_TYPE_NAMES`, present in
  `UNPUBLISHED_EVENT_TYPES`.
- **No schema changes**: no new migration, no new column — a guard
  test confirming `Device`'s column set is unchanged from this
  contract's own §3 baseline.
- **No connector changes**: `mqtt.py`/`home_assistant.py` diff against
  baseline is empty.
- **No WebSocket relay changes**: `EVENT_TYPE_NAMES`'s existing keys
  are unchanged (only `UNPUBLISHED_EVENT_TYPES` gains the new name).
- **No Scheduler/Memory/Home-Automation coupling**: source-scanning
  guards confirming none of those modules reference the new event or
  gain new `EventBus` subscriptions.

## 21. Acceptance criteria

- `DeviceStateChangedEvent` published from exactly one place:
  `SmartHomeService.report_device_state()`.
- Published only on a genuine `previous_status != status` transition —
  verified by test, not by inspection alone.
- `DeviceUpdatedEvent`'s existing behavior, frequency, and meaning are
  byte-for-byte unchanged — proven by the existing pinned test suite
  passing unmodified.
- No new DI wiring (`SmartHomeService` already holds `event_bus`).
- No schema/migration change.
- No connector modification.
- No `EVENT_TYPE_NAMES` entry; `UNPUBLISHED_EVENT_TYPES` gains the new
  name.
- No Scheduler, `SmartHomeMemoryService`, Home Automation, or frontend
  code touched.
- Full backend regression green, including all existing
  `test_smart_home_service.py` tests unmodified.

## 22. Deferred scope

Per-category attribute state-change events (brightness, temperature,
humidity, volume, etc.); Sensor state-change events (excluded pending
the same privacy review `SmartHomeMemoryService` already applies to
this category); Smart Lock state events (no additional exclusion
needed — this slice never reaches attribute-level state for any
category, locks included); real-time Home Assistant WebSocket state
updates; continuous MQTT state-event persistence/relay; event
batching/rate limiting; state history storage; analytics; Event Viewer
implementation; frontend integration of any kind; correlation IDs;
automatic Smart Home Memory capture; Home Automation implementation;
the `DeviceUpdatedEvent` same-value-guard fix documented in §6 as a
legitimate, separately-approvable future item, not part of this slice.

## 23. Explicit Phase 2 implementation boundary

Phase 2, if approved, implements **only**: the `DeviceStateChangedEvent`
dataclass in `events.py`; the guard + additive publish call inside
`SmartHomeService.report_device_state()`; the `UNPUBLISHED_EVENT_TYPES`
entry in `runtime_ws_hub.py` (required by the same pinned
all-events-accounted-for vocabulary test Tier 1's own implementation
satisfied the same way); the test matrix in §20. Nothing else in this
document authorizes any other file to change.
