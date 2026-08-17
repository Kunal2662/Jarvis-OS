# M12 Security & Safety — Siren Integration — Logic Contract

Status: **Draft — Logic Contract only.** Written per `M12 TASK GROUP R
— PHASE 1` approval, following the `M12 PHASE 0 POST-TASK-Q AUDIT`
(delivered in-conversation; no audit file exists on disk, consistent
with every prior Phase 0 audit this session). **Not approved for
implementation** — no source, tests, DI, routes, tools, connector,
`DEVICE_TYPES`, roadmap, CHANGELOG, or frontend changes accompany this
file. Every claim about existing code is freshly re-verified against
the current working tree this session (clean, HEAD `a1f5ded`), not
carried over from the Phase 0 audit unchecked. Labeled per the
requested convention: **[REPO]** = verified by reading the current
source this turn; **[EXTERNAL]** = verified this turn against Home
Assistant's own developer documentation (fetched live); **[UNVERIFIED]**
= not confirmed, flagged for Phase 2.

## 1. Purpose

Normalized on/off control for siren devices — the first M12 module
addition that discriminates a device category living inside the
generic `device_type="other"` bucket rather than its own dedicated
`device_type` or the shared `"appliance"` bucket. Closes one of the
two items Security & Safety's own roadmap feature list names as
outstanding ("siren/alarm-panel integration") — this slice covers
**siren only**; `alarm_control_panel` is explicitly out of scope (§15).

## 2. Repository evidence

**[REPO]** `SecurityService` (`services/security_service.py`, read in
full this turn) — `trigger_panic_mode`'s own docstring states
verbatim: *"Never unlocks, never turns anything off, never touches
thermostats/cameras/sirens, never schedules or publishes an event."*
This is a direct, existing, tested statement that `SecurityService`
has **zero** siren coupling today — confirming there is nothing to
"extend" there, and that adding siren logic to this class would
contradict its own documented boundary (§3).

**[REPO] Decisive, previously-unconfirmed finding**: both connectors
**already capture siren identity today, unconditionally, for every
discovered device, regardless of `device_type`** — this is proven
code, not a proposed technique:
- `home_assistant.py:_entity_to_discovered_device` (`:263-295`):
  `metadata: dict[str, Any] = {"domain": domain}` is set for **every**
  entity, where `domain = entity_id.split(".", 1)[0]` — for a
  `siren.front_door` entity this is `metadata["domain"] = "siren"`,
  set exactly the same way regardless of the fact that
  `_DEVICE_DOMAINS["siren"] == "other"` (`:88`).
- `mqtt.py:_handle_ha_discovery` (`:507-556`): `metadata: dict[str,
  Any] = {"component": component, "discovery_topic": topic}` is set
  for every registered device the same way, where `component` comes
  from the discovery topic itself — `_HA_COMPONENT_DEVICE_TYPES
  ["siren"] == "other"` (`:169`) does not prevent `metadata
  ["component"] = "siren"` from being captured.

This means a siren discovered through either connector **today,
already, with zero code changes** carries exactly the identifying
metadata a new service needs — the only missing piece is a service
that reads it.

**[REPO]** `SmartSwitchService` (`services/smart_switch_service.py`,
re-read this turn) — the closest architectural template: single
boolean capability, `_require_switch` domain-check, ungated reads,
gated mutation under its own principal, `_translate_home_assistant`/
`_translate_mqtt` both returning `(command.value, {})` with **no
payload merge**, matching a siren's own equally simple shape exactly.

**[REPO]** `smart_locks.py`/`smart_switches.py` routes (both read in
full this turn) — confirmed the exact REST convention: `GET
/{resource}`, `GET /{resource}/{id}`, and **two separate verb-POST
endpoints**, never a merged `/state` body (Locks: `/lock`/`/unlock`;
Switches: `/on`/`/off`) — `smart_locks.py`'s own docstring states this
explicitly: *"two explicit action endpoints... are clearer"* than a
merged body for a single binary attribute.

**[REPO]** `AgentSettings.confirm_required_tools`
(`core/config/settings.py:522-524`, re-read this turn) — current exact
set: `{"run_automation", "unlock_device", "trigger_panic_mode",
"trigger_vacation_mode"}`. Confirms **two independent existing
justifications** already coexist in this one set: `unlock_device`
(single-device, directional physical-security risk — `lock_device`
itself is *not* gated) and `trigger_panic_mode`/`trigger_vacation_mode`
(blast radius — an entire home's devices at once). This diversity is
directly relevant to §10's own decision.

**[REPO]** `ConnectivityService.send_command`/`read_raw_state`
(re-confirmed this turn, unchanged since Task Group Q's own contract)
— generic, connector-agnostic, no modification needed for any new
device category to use it.

## 3. Architecture decision

**Option A — a new, standalone `SirenService` in `services/`. Chosen.**
Two alternatives evaluated and rejected with direct evidence, not
assumption:

- **Option B (extend `SmartSwitchService`)** — rejected.
  `SmartSwitchService` is hard-scoped to `_SWITCH_DEVICE_TYPE =
  "switch"` (`:65`); a siren is a structurally and semantically
  different HA domain (`siren.turn_on`/`turn_off`, not
  `switch.turn_on`/`turn_off`) discovered under a different entity
  domain. Overloading one service to discriminate two unrelated device
  identities would blur an invariant every other device-category
  service currently holds (one service, one identity check).
- **Option C (extend `SecurityService`)** — rejected on direct textual
  evidence (§2): `SecurityService`'s own `trigger_panic_mode` docstring
  already asserts it never touches sirens. Task Group M's own
  Panic/Vacation Mode extension of `SecurityService` was justified
  specifically because those were *"a second capability over the same
  ['home security posture'] concept [SecurityService] already owns,"*
  not a new device category — the same Logic Contract explicitly
  contrasted this against Appliance Control's own siblings, which
  **do** get new services because they **are** new device categories.
  A siren is a new device category by that same test, not a new
  capability over an existing one.
- **Option D**: no other architecture found superior to A.

`SirenService` mirrors `SmartSwitchService`'s constructor shape exactly
(`smart_home`, `connectivity`, `permissions` — no `database`, no
`event_bus`).

## 4. Siren identity / domain resolution

**Discrimination**: `device.device_type == "other"` **and**
(`metadata.get("domain") == "siren"` **or** `metadata.get("component")
== "siren"`) — the `domain`-preferred, `component`-fallback order
every appliance-domain service (`VacuumHumidifierService`,
`MediaPlayerService`, `WaterHeaterService`) already establishes for
`device_type="appliance"`. This is the **first application of that
exact fallback technique to `device_type="other"`** — the technique
itself is proven (§2's appliance-domain precedent); applying it to a
different, larger, more heterogeneous bucket is the one genuinely novel
element of this contract, and is why §2's direct trace of both
connectors' own discovery code (not analogy) was necessary before
proposing it.

**No connector modification, no `DEVICE_TYPES` change** — `"other"`
already exists as a `DEVICE_TYPES` value (`domain/smart_home/
models.py:54`, unchanged), and both connectors already populate the
needed metadata unconditionally (§2). `_DEVICE_DOMAINS`/
`_HA_COMPONENT_DEVICE_TYPES`'s own `"siren": "other"` entries are
**not** touched.

**Honest limitation, stated not hidden**: `device_type="other"` is a
large, heterogeneous bucket (also covers `select`/`number`/`valve`/
`alarm_control_panel`/anything unmapped) — `SmartHomeService.
list_devices(device_type="other")` returns every device in that
bucket; `SirenService.list_sirens` must filter by domain/component in
Python after that DB read, the same "list, then Python-filter by
metadata" tradeoff `VacuumHumidifierService`/`MediaPlayerService`
already accept for their own, smaller `"appliance"` bucket.

## 5. Normalized read model

```python
{
    "id": str,
    "home_id": str,
    "room_id": str | None,
    "name": str,
    "status": str,             # Device's own DB lifecycle status
    "manufacturer": str,
    "model": str,
    "external_id": str | None,
    "on": bool | None,         # None when unavailable/unparseable
    "available": bool,
}
```

Mirrors `SmartSwitchService`'s own `_switch_payload` shape field-for-
field. **Deliberately excludes** `available_tones`/`supported_features`
— **[EXTERNAL]** Home Assistant's own developer documentation
(`developers.home-assistant.io/docs/core/entity/siren/`, fetched this
turn) confirms `available_tones` only exists when
`SirenEntityFeature.TONES` is set, and this MVP's command surface
(§8) never uses tones — including a field the contract's own scope
never acts on would be exactly the "field merely because HA might
support it" the task explicitly forbids. Neither connector's
`read_state()` parses HA's `supported_features` bitmask today, and
this contract does not propose adding that parsing.

## 6. Read behavior

`list_sirens(*, home_id=None, room_id=None)` — last-known DB rows only
(list/detail asymmetry, matching every prior M12 device-category
service). `get_siren_state(device_id)` — live read via
`ConnectivityService.read_raw_state`, wrapped in the identical
`with contextlib.suppress(ConnectivityError)` pattern every other
service already uses; unavailable/unreachable → `on: None, available:
False`, never fabricated. Unknown device or wrong domain → plain
`ServiceError` (→ 404 at the route). **Reads are ungated** — see §9 for
the reasoning, evaluated independently rather than inherited.

## 7. Mutation behavior

**Two separate operations — `turn_on(device_id)` / `turn_off
(device_id)` — not a merged `set_siren_state`.** This is not merely
stylistic: §10's confirmation decision requires it. `confirm_required_
tools` gates by exact tool name; a merged tool would force either
confirming *both* directions (defeating the asymmetric design a siren
genuinely needs — see §10) or a per-argument confirmation mechanism
this codebase has no precedent for. Mirrors `SmartLockService.lock`/
`.unlock`'s own two-method shape exactly, for the same underlying
reason (one direction is safe, the other is not).

## 8. Home Assistant / MQTT command mapping

**[EXTERNAL, verified this turn against `developers.home-assistant.io/
docs/core/entity/siren/`]**: domain is `siren`; services are
`siren.turn_on`, `siren.turn_off` (a `siren.toggle` also exists,
**not used** — this MVP never needs it). `turn_on` accepts three
**entirely optional** parameters, each gated behind its own
`SirenEntityFeature` flag: `tone` (requires `TONES`), `duration`
(requires `DURATION`), `volume_level` (requires `VOLUME_SET`).
`turn_off` accepts no parameters. **This directly confirms the MVP's
own scope decision is not just "smaller" but genuinely correct**: a
bare `turn_on`/`turn_off` call with no payload is a fully valid,
complete HA service call for *any* siren regardless of which optional
features it supports — the base platform documentation itself states
unsupported parameters are filtered automatically. No `[UNVERIFIED]`
wire-level claim remains for the MVP's own command surface.

Translation, mirroring `SmartSwitchService`'s exact shape:

```python
def _translate_home_assistant(command: SirenCommand) -> tuple[str, dict[str, Any]]:
    return command.value, {}   # "turn_on"/"turn_off", no payload -- §8's own external verification

def _translate_mqtt(command: SirenCommand) -> tuple[str, dict[str, Any]]:
    return command.value, {}   # JARVIS-native vocabulary, mirroring HA's own names -- same precedent as switch/lock
```

**No connector code changes** — reached through the existing,
unmodified `ConnectivityService.send_command` chokepoint, exactly like
every other device-category service.

## 9. Permission model

New principal `core:sirens`, existing `smart_home` scope — matching
every prior principal's naming convention exactly. **Reads are
ungated** — evaluated independently, not defaulted: a siren's on/off
state is comparable in sensitivity to a light's or switch's (Lighting/
Locks/Switches/Thermostat/Appliance Control precedent), not to raw
sensor telemetry that can reveal occupancy (Sensors'/Security's own
reason for gating reads). **Mutations require `core:sirens`/
`smart_home`**, matching every device-category service's own uniform
mutation-gating pattern.

## 10. Confirmation decision — the central design question

**`turn_siren_on` requires confirmation (added to `confirm_required_
tools`). `turn_siren_off` does not.** Evaluated independently against
the two existing justifications already in that set (§2), not
inherited from either wholesale:

- **Not blast-radius-based** (unlike Panic/Vacation Mode) — a single
  `turn_siren_on` call affects exactly one device, so that
  justification does not directly apply.
- **Directly analogous to `unlock_device`/`lock_device`'s own
  asymmetry** — JARVIS's existing convention already distinguishes
  confirmation not by "is this a mutation" but by "does this specific
  *direction* carry an asymmetric real-world risk." Turning a siren
  **on** is loud, disruptive, can alarm neighbors, can draw an
  unwanted emergency response, and is genuinely hard to "undo" the
  moment it happens (the noise already occurred). Turning a siren
  **off** is the safe direction — silencing a siren is never harmful,
  exactly mirroring why `lock_device` needs no confirmation while
  `unlock_device` does.

This is a real, evidence-grounded, independently-reasoned decision,
not a copy of any single prior precedent — it recombines an existing
*pattern* (directional asymmetry) in a new context, explicitly
distinct from blast-radius reasoning.

## 11. REST design

**[REPO]** deviates from the Phase 0 audit's own tentative suggestion
(`/api/v1/security/sirens/*`) after fresh verification: since §3
establishes `SirenService` as its own sibling service (not a
`SecurityService` extension), nesting its REST route under
`/security/*` — a different service's own namespace — would mismatch
route ownership with service ownership, unlike Task Group N's
Connectivity Health route (deliberately nested in `routes/devtools.py`
because *that* capability conceptually **is** a devtools capability
even though its service lives elsewhere). A siren is its own device
category, exactly like locks/switches — it gets its own top-level
resource, matching that established convention instead:

```
GET  /api/v1/sirens
GET  /api/v1/sirens/{device_id}
POST /api/v1/sirens/{device_id}/turn_on
POST /api/v1/sirens/{device_id}/turn_off
```

Envelope, auth, and error-mapping identical to `smart_locks.py`'s own
template: plain `GET .../{id}` → 404 on unknown/wrong-domain; every
action endpoint → 400 on any `ServiceError` (unknown device, wrong
domain, permission not granted alike).

## 12. Agent-tool design

Four tools — `list_sirens`, `get_siren_state`, `turn_siren_on`,
`turn_siren_off` — matching `SmartSwitchService`'s own exact
tool-count precedent (list/get/on/off), not automatically four because
"other modules have four." `turn_siren_on`'s tool name is added to
`confirm_required_tools` (§10) — the same existing, unmodified
`AgentPermissionGate` mechanism `unlock_device` already uses; no new
confirmation infrastructure.

## 13. EventBus boundary

No `EventBus` dependency, no publish, no subscribe, no
`SirenUpdatedEvent`, no automatic event-driven behavior of any kind.
The pre-existing device-command EventBus publishing gap is not
addressed by this slice and is not attempted.

## 14. Panic Mode boundary

**`SecurityService.trigger_panic_mode`/`trigger_vacation_mode` are not
modified in this task group.** Wiring the new siren capability into
Panic Mode (so a future call also sounds every siren in a home) is a
real, natural follow-up this slice enables, explicitly deferred to a
separate future task group, not built here — matching the Phase 0
audit's own boundary and the instruction's explicit prohibition.

## 15. `alarm_control_panel` boundary

Not implemented. Genuinely different command/state model (`alarm_
control_panel.alarm_arm_home`/`alarm_arm_away`/`alarm_disarm`, an
armed/disarmed/triggered state machine, not a boolean) — bundling it
into this MVP would be scope creep, mirroring how Task Group G
(Appliance Control) scoped down to Fan+Cover only rather than every
possible category at once. No armed/disarmed states, no alarm codes,
no alarm history, no placeholder code of any kind for this item.

## 16. Deferred scope

`alarm_control_panel` integration; Panic Mode/Vacation Mode wiring;
tones/sounds, duration, volume, flashing/patterns (all confirmed
optional/feature-gated in HA's own API, §8, none needed for MVP);
notifications; scheduled siren actions; automation; EventBus
integration; alarm/activation history; analytics; memory capture;
remote access; frontend implementation; multi-home orchestration;
emergency-service integration. No placeholder/scaffold for any of the
above.

## 17. Security considerations

No credential/secret ever reachable through this slice — `SirenService`
never reads `Device.metadata_json` directly (only the owning service's
own already-normalized `metadata.get("domain"/"component")` values,
already established as safe by every prior device-category service),
never imports a connector class, never touches `ConnectorCredentialStore`.
The one genuinely new physical-world risk this slice introduces (an
audible, disruptive device activation) is addressed structurally by
§10's confirmation requirement, not merely documented.

## 18. Test strategy (future Phase 2 — described, not created)

Identity: a `siren`-domain device (HA-sourced, `metadata["domain"]`)
and a `siren`-component device (MQTT-sourced, `metadata["component"]`)
both resolve correctly; a `valve`/`select`/`number`-domain
`device_type="other"` device is rejected; a device with no domain/
component metadata at all is rejected; every other M12 device_type
(light/switch/lock/sensor/thermostat/appliance) is rejected. Read:
list/get, live-read success, unavailable-device honesty (`on: None`),
unknown device, non-siren device rejection. Mutation: `turn_on`/
`turn_off` each produce the exact `("turn_on", {})`/`("turn_off", {})`
wire call for both connector types, command failure reporting,
unavailable-device mutation behavior. Permission: reads succeed
without a grant; mutations require `core:sirens`/`smart_home`, denied/
granted states, principal correctness. Confirmation: `turn_siren_on`
present in `AgentSettings().confirm_required_tools`, `turn_siren_off`
explicitly absent (a negative guard, not merely omitted). REST: all
four endpoints, envelope shape, 404/400 semantics, auth boundary.
Tools: registration, invocation, permission propagation. Security: no
`metadata_json`/credential leakage (text-scan guard). Scope guards
(AST-docstring-stripped): no `alarm_control_panel` reference, no
`EventBus`/Scheduler/Analytics/`MemoryService` reference, no
`SecurityService` modification, no connector modification, no
`DEVICE_TYPES`/`CONNECTOR_TYPES` change, no `trigger_panic_mode`/
`trigger_vacation_mode` modification.

## 19. Acceptance criteria

- `SirenService` depends only on `SmartHomeService` + `ConnectivityService`
  + `PermissionModel` — no `IDatabase`, no `EventBus`, no direct
  connector import.
- `SecurityService` is **not modified** — pinned by a diff/guard.
- No connector file is modified; `_DEVICE_DOMAINS`/
  `_HA_COMPONENT_DEVICE_TYPES` unchanged.
- No `DEVICE_TYPES`/`CONNECTOR_TYPES` change.
- `turn_siren_on` present, `turn_siren_off` absent, in
  `AgentSettings().confirm_required_tools` — both pinned by tests.
- Reads ungated, mutations gated under `core:sirens`/`smart_home`.
- No `alarm_control_panel` code path anywhere.
- No schema/migration change.
- Zero frontend file touched.
- Every §16 deferred item has zero corresponding code.
- This Logic Contract is reviewed and approved **before** any
  implementation begins.

## 20. External verification

**[EXTERNAL]** Fetched and read this turn:
- `https://www.home-assistant.io/integrations/siren/` — confirmed
  domain `siren`, services `siren.turn_on`/`turn_off`/`toggle`, state
  values on/off/unavailable/unknown.
- `https://developers.home-assistant.io/docs/core/entity/siren/` —
  confirmed `SirenEntity` class, `is_on`/`available_tones` properties,
  `SirenEntityFeature` flags (`TURN_ON`, `TURN_OFF`, `TONES`,
  `DURATION`, `VOLUME_SET`), and the exact `turn_on` parameter set
  (`tone`, `duration`, `volume_level`) with each parameter's gating
  feature flag — all confirmed **optional**, directly supporting §8's
  MVP scope decision.

No third-party/non-authoritative source was used for any wire-level
claim in this contract.

## 21. Phase 2 verification requirements

**[UNVERIFIED, must confirm during Phase 2]**: live behavior against a
real Home Assistant instance's actual `siren` entity (this contract's
external verification is documentation-based, not a live integration
test — matching this project's own established discipline of
verifying against a real local peer before trusting a wire-format
claim in production code, the same rule the MQTT connector's own
`gmqtt` choice was validated against). Confirm a real MQTT HA-Discovery
`siren` component payload shape matches the `metadata["component"]`
assumption in practice, not only in the connector's own parsing code.

## 22. Git safety verification

Expected after writing: exactly one new untracked file (this
document), zero tracked changes, HEAD unchanged at `a1f5ded`, origin
unchanged at `a1f5ded`, no commit, no push.
