# M12 Task Group W — Security & Safety: Siren Advanced Controls (Tone / Duration / Volume) — Logic Contract

**Status: Phase 1. No implementation exists yet. This contract governs Phase 2.**

Authoritative basis: `M12 POST-TASK-GROUP-V PHASE 0 AUDIT` (delivered this session), ranked
candidate #1. Treated as a starting hypothesis, not unquestioned truth — every claim below is
re-verified against current source at `HEAD 5cad91d` and against Home Assistant's own current
developer documentation, fetched fresh this session.

## 1. Scope

**In scope:**
- `tone` (string, optional) — HA's `siren.turn_on` parameter, "the key or the value from the
  device's own list of available tones."
- `duration` (integer, optional, seconds) — HA's `siren.turn_on` parameter.
- `volume_level` (float, optional, 0.0–1.0) — HA's `siren.turn_on` parameter.
- Extending the existing `SirenService.turn_on`/`POST /sirens/{id}/turn_on`/`turn_siren_on`
  agent tool with these three optional parameters.

**Out of scope (explicit):**
- Siren pattern/custom waveform — does not exist as an HA `SirenEntityFeature` (§3 below);
  nothing to build.
- `alarm_control_panel` actions of any kind.
- Siren activation history/state history.
- Notifications, automation, scheduled sirens.
- Panic Mode / Vacation Mode coupling.
- EventBus, Scheduler, Analytics, Memory integration.
- New connector classes, database/schema changes.
- Frontend source.

## 2. Source evidence (fresh reads this session, `HEAD 5cad91d`)

**`src/jarvis/services/siren_service.py`** (262 lines, read in full): `SirenCommand` is a
closed 2-value `StrEnum` (`TURN_ON`, `TURN_OFF`). Both translators
(`_translate_home_assistant`, `_translate_mqtt`) return `(command.value, {})` — always an empty
payload. `_send` is the sole mutation chokepoint: resolves connector type, looks up translator,
calls `self._connectivity.send_command(device_id, wire_command, payload)`. `turn_on`/`turn_off`
each call `_require_permission()` then `_send`. Module docstring already states HA's own
`turn_on`/`turn_off` "take an entirely optional payload (`tone`/`duration`/`volume_level`, each
gated behind its own `SirenEntityFeature` flag" — this MVP "sends no payload at all," explicitly
flagging the gap this task group closes.

**`routes/sirens.py`** (91 lines, read in full): `POST /sirens/{device_id}/turn_on` takes no
request body today — the route function signature is `(device_id: str, request: Request)`,
nothing else. `turn_off` has the identical shape. Both call the service method with only
`device_id`.

**`agents/tools/siren_tools.py`** (97 lines, read in full): `turn_siren_on(device_id: str) -> str`
takes exactly one argument today. `turn_siren_off` identical shape.

**`tests/unit/test_m12_siren_service.py`** (562 lines, read in full): every `turn_on`/`turn_off`
assertion checks `fake_connector.sent_commands == [("siren.front_yard", "turn_on", {})]` — an
**empty dict literal**, asserted repeatedly across HA and MQTT translation tests. These
assertions must remain valid for a bare `turn_on()` call after this task group ships (§22).

**`ConnectivityService.send_command`** (`services/connectivity_service.py:214-230`): the single
chokepoint every M12 mutation uses. Resolves the device's connector, calls
`connector.send_command(device.external_id, command, payload)` — no payload inspection,
transformation, or validation of any kind at this layer.

**`HomeAssistantConnector.send_command`** (`core/connectivity/connectors/home_assistant.py:230-255`,
read in full): builds `body = {"entity_id": external_id, **payload}` and `POST`s to
`/api/services/{domain}/{command}` — a fully generic payload passthrough. **Zero connector
change needed** for any new payload key.

**`MqttConnector.send_command`** (`core/connectivity/connectors/mqtt.py:460-483`, read in full):
builds `build_command_envelope(external_id, command, payload)` and publishes it — equally
generic. **Zero connector change needed.**

**`smart_lighting_service.py`** (validation precedent, read in full): `_validate_brightness`
rejects `bool`/non-`int`/out-of-0-100-range; `_validate_color_temp_kelvin` rejects
`bool`/non-`int`/non-positive. Exact pattern this contract reuses for `duration`.

**`media_player_service.py`** (validation precedent, read in full): `_validate_volume`
(lines 208-220) rejects `bool`, non-numeric, NaN/inf, and anything outside `0.0`–`1.0` —
**byte-identical range to `siren.volume_level`**, confirmed independently via external HA
verification (§3). `_check_source` (lines 414-429) performs a **live connector read**
(`self._connectivity.read_raw_state`) before mutating, validates the requested `source` against
the device's own reported `source_list` **only when non-empty**, permissive otherwise. This is
the direct precedent for `tone` validation (§9).

**`AgentPermissionGate.authorize`** (`agents/permission.py:69-87`, read in full): gates purely by
`tool_name` — `if tool_name not in self._confirm_required: return True, ...`. **`args` is never
inspected for the gating decision**, only interpolated into the confirmation prompt string. This
means adding optional kwargs to `turn_siren_on` changes nothing about how confirmation is
enforced.

**`AgentSettings.confirm_required_tools`** (`core/config/settings.py:535-544`): current exact
contents — `{"run_automation", "unlock_device", "trigger_panic_mode", "trigger_vacation_mode",
"turn_siren_on", "disarm"}`. `turn_siren_on` present, `turn_siren_off` absent.

**`routes/appliances.py`** (REST body-model precedent, read in full): `SetFanPercentageRequest`/
`SetCoverPositionRequest` are minimal Pydantic `BaseModel`s with one required field each, used
because `fan.set_percentage`/`cover.set_cover_position` are **genuinely separate HA services**
from `turn_on`/`open_cover` (Task Group T's own finding). This precedent does **not** apply
here — see §13.

## 3. HA external verification (Home Assistant's own developer documentation, fetched fresh this session)

**`https://www.home-assistant.io/actions/siren.turn_on/`** — exact parameter list:
- **`tone`** (string, optional): *"The tone to emit. Your siren must support tones, and you can
  use either the key or the value from its list of available tones."*
- **`volume_level`** (float, optional): *"The volume to play at, from 0 (inaudible) to 1
  (maximum)."* — *"Your siren must support setting the volume."*
- **`duration`** (integer, optional, unit **seconds**): *"The number of seconds the sound is
  played."* — *"Your siren must support setting a duration."*
- No other `siren.turn_on` parameters are documented. No fourth parameter exists.

**`https://developers.home-assistant.io/docs/core/entity/siren/`** — entity platform contract:
- **`SirenEntityFeature`** has exactly five flags: `TURN_ON`, `TURN_OFF`, `TONES`, `DURATION`,
  `VOLUME_SET`. **No pattern/waveform flag exists anywhere in HA's core siren platform.** The
  roadmap's own recurring phrase "tone/duration/volume/pattern control" (`MASTER_ROADMAP.md`
  lines 1003/5047/5065/5081) has no corresponding real HA capability for the word "pattern" —
  this is an imprecision in prior roadmap text, not a real deferred feature; recorded here, not
  silently corrected (§23/§25).
- **`available_tones`**: a real, device-reported capability-metadata attribute — the siren's own
  supported-tone list (dict or list, converted to a normalized key form by HA's base platform).
  Distinct from live state (§15).
- **`is_on`**: the only documented state property. No last-used-tone/duration/volume read-back
  attribute is documented anywhere.
- **Unsupported-parameter behavior, verbatim**: *"If the corresponding flag isn't set when a
  given input parameter is provided in the service action call, it will be filtered out from the
  call by the base platform before being passed to the integration."* HA's own core silently
  drops an unsupported parameter — it does not error. This is decisive for §9/§10.

## 4. Architecture decision

**Extend `SirenService.turn_on` with three new optional keyword parameters — do not add new
methods, new commands, or a new service.** This mirrors `SmartLightingService`'s own "merge
whatever is set into one wire call" shape, **not** `ApplianceService`'s Fan%/Cover-position
precedent. The distinguishing test, established by Task Group T's own docstring ("never merge
into the safe-direction command unless the wire protocol requires it") and now applied in the
opposite direction: `fan.set_percentage`/`cover.set_cover_position` are genuinely **separate**
HA services from `turn_on`/`open_cover`, which is why Task Group T built dedicated methods and
endpoints. `siren.turn_on`'s own `tone`/`duration`/`volume_level` are, by contrast, **optional
parameters of the exact same HA service** (confirmed §3) — the wire protocol itself requires
merging, not separating. This is architecturally identical to Smart Lighting's `brightness`/
`color_temp_kelvin`/`color` being optional `light.turn_on` parameters, not separate services.

`SirenCommand` enum is unchanged — no new command values. `turn_off` is completely untouched;
HA/MQTT documentation and this service's own docstring confirm `turn_off` takes no parameters of
any kind.

## 5. Siren capability model

Two distinct concepts, kept structurally separate per the Phase 1 instruction:
- **Capability metadata** (`available_tones`): what the device *could* accept, read live,
  optional, used only for pre-mutation validation (§9) — never persisted, never part of the
  read-model's identity fields.
- **Current device state** (`on`, `available`): unchanged, existing `_siren_payload` shape.
- **Command parameters** (`tone`, `duration`, `volume_level` on a `turn_on` call): write-only
  inputs to one mutation; never read back, because HA itself exposes no such read-back attribute
  (§3).

## 6. Command model

`turn_on` gains three new optional keyword parameters:

```python
async def turn_on(
    self,
    device_id: str,
    *,
    tone: str | None = None,
    duration: int | None = None,
    volume_level: float | None = None,
) -> dict[str, Any]:
```

`turn_off` signature is unchanged. `SirenCommand` enum is unchanged (`TURN_ON`/`TURN_OFF` only —
these three are parameters of `TURN_ON`, not new command values).

## 7. HA translation

`_translate_home_assistant` gains the three optional parameters, building the payload dict only
from whichever are set — verbatim mirroring `smart_lighting_service._translate_home_assistant`'s
own `if brightness is not None: payload["brightness_pct"] = brightness` shape:

```python
def _translate_home_assistant(
    command: SirenCommand, *, tone: str | None = None, duration: int | None = None,
    volume_level: float | None = None,
) -> tuple[str, dict[str, Any]]:
    if command is SirenCommand.TURN_OFF:
        return command.value, {}
    payload: dict[str, Any] = {}
    if tone is not None:
        payload["tone"] = tone
    if duration is not None:
        payload["duration"] = duration
    if volume_level is not None:
        payload["volume_level"] = volume_level
    return command.value, payload
```

Field names are HA's own verbatim parameter names (§3) — no renaming, no scale conversion
(`volume_level` is already HA-native `0.0`–`1.0`, `duration` is already HA-native seconds).

## 8. MQTT translation

**No standardized MQTT siren vocabulary exists** — confirmed by the complete absence of any
siren-specific MQTT specification in this repository or any prior Logic Contract; Task Group R's
own `_translate_mqtt` already established the precedent of defining a JARVIS-native vocabulary
"deliberately mirroring HA's own siren-domain service names for cross-connector predictability."
This task group **extends that same JARVIS-native vocabulary**, using HA's own verified
parameter names verbatim (`tone`/`duration`/`volume_level`) for semantic equivalence between the
two connector representations — the same choice `_translate_home_assistant`/`_translate_mqtt`
already share for `turn_on`/`turn_off`'s command name itself:

```python
def _translate_mqtt(
    command: SirenCommand, *, tone: str | None = None, duration: int | None = None,
    volume_level: float | None = None,
) -> tuple[str, dict[str, Any]]:
    if command is SirenCommand.TURN_OFF:
        return command.value, {}
    payload: dict[str, Any] = {}
    if tone is not None:
        payload["tone"] = tone
    if duration is not None:
        payload["duration"] = duration
    if volume_level is not None:
        payload["volume_level"] = volume_level
    return command.value, payload
```

**MQTT connector is not modified** — `MqttConnector.send_command` already accepts an arbitrary
payload dict generically (§2), confirmed by fresh read. No connector-level change is
unavoidable; therefore none is made.

## 9. Validation model

- **`volume_level`**: reuses `MediaPlayerService._validate_volume`'s exact logic (reject `bool`,
  non-numeric, NaN/inf, anything outside `0.0`–`1.0`) — HA's own protocol-level range (§3),
  independently confirmed against `siren.volume_level`'s own documented `0`–`1` range. This is
  not an invented limit; it is HA's own documented constraint on the parameter.
- **`duration`**: reject `bool`, non-`int`, and negative values (mirroring
  `_validate_color_temp_kelvin`'s "reject non-positive" shape, adapted to "reject negative" since
  HA's own doc does not state `0` is invalid — "0 seconds" is not defined as an error case
  anywhere in HA's documentation, so `0` is passed through, not rejected; inventing a
  minimum-positive rule here would be exactly the kind of unverified range this contract must not
  fabricate). No maximum is enforced — HA's own documentation states no upper bound, and no
  device-reported bound exists to check against (unlike Water Heater's `min_temp`/`max_temp`,
  which are real, reported fields; no `max_duration` attribute exists in HA's siren platform).
- **`tone`**: reject non-`str`, reject empty/whitespace-only string (mirrors
  `_validate_source`'s exact shape). **Additionally, mirrors `_check_source`'s live-validation
  precedent**: before sending, read the device's live state via
  `self._connectivity.read_raw_state`, extract `available_tones` from `raw.attributes`, and — only
  if the device reports a non-empty tone list — reject a `tone` not present in it. Permissive
  when the device reports nothing, for the identical reason `_check_source` is permissive:
  rejecting a real device over a vocabulary gap is the worse failure. This is a **deliberate,
  source-grounded design decision**, not an assumption: `tone` is genuinely open-vocabulary
  (device-specific, per HA's own doc), the exact same shape `source`/`hvac_mode`/`operation_mode`
  already are in sibling services, each with an established live-capability-check precedent.
- **Unsupported feature** (a device that doesn't support `TONES`/`DURATION`/`VOLUME_SET` at
  all): **not rejected locally.** HA's own base platform already silently filters an unsupported
  parameter before it reaches the integration (§3, verbatim quote) — duplicating that check
  client-side would require reading and interpreting a `supported_features` bitmask this
  codebase has never parsed anywhere, for a case HA already handles gracefully. Decision: **pass
  through and preserve connector failure honesty** — if a device silently ignores an unsupported
  parameter, that is HA's own documented, correct behavior, not a JARVIS bug to work around.
- **Missing/null values**: absent parameters (`None`) are the existing default — behaves exactly
  like today's bare `turn_on()`. Passing `null` explicitly through the REST body is
  indistinguishable from omitting the field (Pydantic optional-field semantics, §13).
- **Wrong types**: every parameter is validated by the functions above before any translator or
  connector call — a `TypeError`-shaped input (e.g. `duration="loud"`) raises the same
  `ServiceError` class every other M12 validation failure already raises.

## 10. Error semantics

| Condition | Behavior |
|---|---|
| Unknown device | `ServiceError` from `SmartHomeService.require_device` (unchanged path) |
| Non-siren device | `ServiceError("... is not a siren.")` from `_require_siren` (unchanged) |
| Unavailable siren | Command still attempted — `ConnectivityService.send_command` reports the connector's own failure via `CommandResult.success=False`; no local pre-check blocks it (matches every existing M12 mutation's own honesty convention) |
| Unsupported tone (device reports a list, requested tone not in it) | `ServiceError` raised locally, before any connector call (§9) |
| Unsupported duration/volume (device doesn't support the feature at all) | Not rejected locally; HA's own base platform silently filters it (§3/§9) — reported as `success=True` if the underlying `turn_on` otherwise succeeds, exactly matching HA's own documented behavior |
| Connector failure (transport-level) | `CommandResult.success=False`, `detail` populated — unchanged, existing path |
| HA command failure (4xx from `/api/services/...`) | Unchanged existing path — `HomeAssistantConnector.send_command`'s own `response.status_code >= 400` handling, untouched by this task group |
| MQTT command failure | Unchanged existing path — `MqttConnector.send_command`'s own publish-exception handling |
| Invalid request (bad type/range) | `ServiceError` from the validation functions (§9), surfaced as REST `400` (existing `_bad_request` convention) |

No silent success anywhere — every path above either raises `ServiceError` before any wire call,
or returns the connector's own honest `success`/`detail` pair, identical in shape to every
existing M12 mutation.

## 11. Permission model

**Reuses `core:sirens`/`smart_home` verbatim. No new principal, no new scope, no per-parameter
permission, no second tier.** `SirenService._require_permission` is called once per `turn_on`
invocation regardless of which optional parameters are set — the same single check already
gates a bare `turn_on()` today. Security analysis: `tone`/`duration`/`volume_level` do not
change *what* is being authorized (still "may this caller turn this siren on"), only *how loud/
long/what sound* — the same category of refinement `SmartLightingService`'s own `brightness`/
`color` already represent under `core:smart_lighting`'s single grant, with no per-attribute
permission precedent anywhere in this codebase.

## 12. Confirmation model

**`turn_siren_on` remains in `AgentSettings.confirm_required_tools`, unchanged.
`tone`/`duration`/`volume_level` are fully covered by the existing confirmation requirement —
no new confirmation infrastructure.** Confirmed directly from `AgentPermissionGate.authorize`'s
own source (§2): the gate checks only `tool_name`, never `args` — a `turn_siren_on` call with
`tone="alarm"` is confirmed by the exact same code path as a bare `turn_siren_on()` call. `args`
is interpolated into the confirmation prompt text (`f"Agent wants to call
{tool_name}({args}). Allow?"`), so a user reviewing the confirmation will *see* which
tone/duration/volume was requested — a strict UX improvement, not a gap.

**Does any new parameter materially change the physical consequence or blast radius?** No.
`duration`/`volume_level` bound or extend the *same* physical event (a siren sounding) a bare
`turn_on` already triggers unconditionally and indefinitely; a request-scoped duration is, if
anything, a **smaller** blast radius than today's default (no HA-side auto-off exists for a
bare `turn_on` — many real sirens continue until explicitly turned off). `tone` changes *what*
plays, not *whether* or *how consequentially* something plays. No case here rises to a
qualitatively new risk requiring its own gate, mirroring exactly how `SmartLightingService`
never introduced a separate confirmation tier for `brightness`/`color`.

## 13. REST design

**Option A chosen: extend the existing `POST /sirens/{device_id}/turn_on` with an optional
request body. No new endpoint.**

```python
class TurnSirenOnRequest(BaseModel):
    tone: str | None = None
    duration: int | None = None
    volume_level: float | None = None
```

FastAPI/Pydantic already makes every field here optional with a `None` default — an empty or
absent JSON body (`{}` or no body at all, matching every current test/caller) continues to
construct a `TurnSirenOnRequest()` with all fields `None`, producing byte-identical behavior to
today's bare call. **This is verified backward-compatible by construction**, not merely assumed:
FastAPI treats a route parameter typed as a Pydantic model with all-optional fields as itself
optional when the request has no body — matching `SnapshotDeviceRequest`'s own established
precedent for a required field, inverted here for an all-optional shape (no direct existing
precedent for an all-optional body in this codebase, but this is standard, well-defined
FastAPI/Pydantic behavior, not a novel mechanism).

**Why not Option B (dedicated endpoints)?** Rejected per §4's own architectural finding: unlike
Fan%/Cover-position, these are not separate HA services — a
`POST /sirens/{id}/turn_on_with_tone` would misrepresent the wire protocol and force a caller to
choose between two functionally overlapping endpoints for what is, on the wire, one HA service
call. `turn_off` is untouched — no request body, no new parameters (HA's own `siren.turn_off`
takes none, confirmed alongside `turn_on`'s own doc page).

Existing bare `POST /sirens/{id}/turn_on` calls (no body) continue working unchanged — no
existing caller's behavior changes.

## 14. Agent tool design

**Extend the existing `turn_siren_on` tool with the same three optional arguments. No new
tool.** Per the Phase 1 instruction's own framing: separate tools mirroring every REST parameter
would be unjustified — `langchain_core`'s `@tool` decorator already supports optional
keyword arguments with defaults, and the agent gains the capability through the same tool name
`AgentSettings.confirm_required_tools` already names, requiring no change to that frozenset.

```python
@tool
async def turn_siren_on(
    device_id: str, tone: str = "", duration: int = 0, volume_level: float = 0.0
) -> str:
    """... tone/duration/volume_level are all optional; omit any you don't want to set."""
    try:
        result = await sirens.turn_on(
            device_id,
            tone=tone or None,
            duration=duration or None,
            volume_level=volume_level or None,
        )
    ...
```

(Exact default-sentinel handling — empty string/zero vs. `None` — is a Phase 2 implementation
detail; `langchain_core` tool schemas do not cleanly support `Optional[...] = None` defaults for
every backing LLM function-calling format, so this mirrors `list_sirens`' own existing
`home_id: str = ""` sentinel convention already used in this exact file, not a new pattern.)

`turn_siren_off` is unchanged. `list_sirens`/`get_siren_state` are unchanged.

## 15. Read-model decision

**No change to `SirenService.get_siren_state`, `_siren_payload`, or the persisted read model.**
Confirmed directly: HA's own siren entity platform documents exactly one state property
(`is_on`) and no read-back attribute for a previously-sent tone/duration/volume (§3) — there is
nothing to read back because HA itself does not expose it. `available_tones` is real capability
metadata, but is deliberately **not** added to `_siren_payload`: doing so would require a live
read on every `list_sirens` call (which is explicitly DB-only per this module's own established
list/detail asymmetry) or silently change `get_siren_state`'s existing field set, neither of
which this task group's own narrow scope justifies. **No persisted/fabricated value of any kind
is introduced** — this task group is a pure write-capability expansion, confirming the Phase 0
audit's own conclusion.

## 16. Security/privacy

No new sensitive data. `tone`/`duration`/`volume_level` are non-identifying operational
parameters, never persisted (§15), never logged beyond the existing generic tool-failure
`_logger.warning` calls already present in `siren_tools.py`. No `metadata_json` exposure risk —
this task group touches only the write path, never the read/payload-construction path where that
guarantee already lives.

## 17. EventBus boundary (unchanged, reverified)

No `event_bus`/`EventBus` reference anywhere in the proposed changes. `SirenService` has never
taken an `EventBus` dependency and does not gain one here — confirmed via the existing
`test_no_alarm_control_panel_or_panic_mode_coupling` guard's own `"EventBus"` forbidden-term
check, which this task group's real code must continue to pass unmodified.

## 18. Scheduler boundary (unchanged, reverified)

No scheduling of any kind. `duration` bounds one already-triggered command's own duration
parameter — it is not a delayed or recurring trigger, and requires no Scheduler dependency,
confirmed by HA's own semantics (the *device*, not JARVIS, times the duration).

## 19. Analytics/Memory boundary (unchanged, reverified)

No `Analytics`/`MemoryService` reference. No siren-activation history of any kind is introduced —
Smart Home Memory's own Tier-3 cascade (Task Group V) already snapshots a siren's `on`/
`available` state on demand; this task group does not extend or interact with that in any way.

## 20. Frontend requirements boundary (planning only, Phase 2)

To be written in Phase 2, after backend verification, following the established planning-only
precedent. Will describe: a tone selector populated from `GET .../{id}`'s own **capability**
read (a future, separately-decided read-model addition, **not** shipped by this task group per
§15) or, absent that, a free-text field with an honest "device-specific; not validated until
sent" note; a duration field (seconds, no enforced maximum); a volume slider (0–1, matching
`_validate_volume`'s own range); explicit unsupported-feature messaging (a device that silently
ignores the parameter, per §3, should not be presented as if it errored); confirmation UX
identical to today's `turn_siren_on` dialog, now showing the requested tone/duration/volume in
the prompt; and an explicit note that no current-value read-back exists for any of the three
(§15) — a frontend must not render a "current tone" field, because HA itself provides none.

## 21. Testing strategy (described for Phase 2, not created now)

All 26 items from the Phase 1 instruction, mapped to concrete additions in
`tests/unit/test_m12_siren_service.py` (extended, not forked) plus `test_m12_siren_tools.py`/
`test_m12_sirens_route.py`:

1. **Bare `turn_on()` regression**: every existing assertion of
   `fake_connector.sent_commands == [("siren.front_yard", "turn_on", {})]` must continue to pass
   unmodified — proves zero behavior change for the existing call shape.
2. **Tone payload translation**: `turn_on(id, tone="alarm")` → HA payload `{"tone": "alarm"}`.
3. **Duration payload translation**: `turn_on(id, duration=30)` → HA payload `{"duration": 30}`.
4. **Volume payload translation**: `turn_on(id, volume_level=0.5)` → HA payload
   `{"volume_level": 0.5}`.
5. **Combined parameter translation**: all three set → payload carries all three, no
   cross-contamination with `_siren_payload`'s own read-model fields.
6. **HA translation**: verified against `_translate_home_assistant`'s exact field names (§7).
7. **MQTT translation**: verified against `_translate_mqtt`'s own JARVIS-native vocabulary (§8).
8. **Permission enforcement**: `turn_on(id, tone="x")` without grant raises the same
   `ServiceError` as a bare call — proves no permission bypass via optional parameters.
9. **Existing `turn_siren_on` confirmation**: `test_turn_siren_on_is_in_the_default_confirm_
   required_tools`-style assertion, unchanged.
10. **Confirmation approve/decline/no-channel**: `AgentPermissionGate.authorize("turn_siren_on",
    {"device_id": "x", "tone": "alarm"})` behaves identically to the existing argument-less test
    — proves the gate's name-only keying (§2) holds with a richer `args` dict.
11. **Invalid input validation**: non-string tone, empty-string tone, non-int duration, negative
    duration, non-numeric volume, volume `<0`/`>1`, `bool` passed for any parameter (the
    established bool-is-int-subclass gotcha check) — each raises `ServiceError`.
12. **Unsupported-feature behavior**: a device reporting no `available_tones` accepts any
    non-empty tone string (permissive path, §9); a device with no capability metadata at all
    for duration/volume still accepts the command locally (HA is trusted to filter, §9/§10).
13. **Connector failure honesty**: `fake_connector.next_command_succeeds = False` with tone/
    duration/volume set still reports `success=False`, `detail` populated — unchanged shape.
14. **Non-siren rejection**: unchanged existing `_require_siren` path, now also exercised with
    optional parameters present to prove the identity check runs before translation.
15. **Unknown-device behavior**: unchanged existing path.
16. **`turn_off` regression**: fully unchanged, no parameters, existing assertions untouched.
17. **REST request/response behavior**: `POST .../turn_on` with `{}` body, with a populated
    body, and with no body at all (three separate cases) — all three produce
    `fake_connector.sent_commands` matching the equivalent direct-service-call shape.
18. **Agent tool behavior**: `tools["turn_siren_on"].ainvoke({"device_id": ..., "tone": "x"})`
    round-trip.
19. **Backward-compatible empty `turn_on` call**: explicit REST test with body `{}` and with no
    `Content-Length`/body at all, both producing the pre-existing empty-payload wire call.
20. **No read-model fabrication**: `get_siren_state` response shape is asserted unchanged
    (`set(state.keys())` equality check, mirroring the existing
    `test_siren_payload_never_includes_raw_metadata_json`'s own exact-key-set assertion) —
    proves no `tone`/`duration`/`volume_level`/`available_tones` key leaks into the read model.
21. **No `metadata_json` leakage**: unchanged existing guard, re-run against the extended
    service to confirm no regression.
22. **Architecture guards**: `test_no_alarm_control_panel_or_panic_mode_coupling`'s own
    forbidden-term list (`alarm_control_panel`, `trigger_panic_mode`, `trigger_vacation_mode`,
    `EventBus`) re-run unmodified — must still pass, since none of those terms are introduced.
23. **No EventBus/Scheduler/Analytics/Memory references**: covered by #22 plus new terms
    (`Scheduler`, `Analytics`, `MemoryService`) added to the same guard's own term list.
24. **No new connector/schema changes**: a source-diff-based test is impractical; verified
    instead via the same manual scope-audit discipline every prior task group's Phase 2 used
    (`git diff --stat` limited to the expected file set).
25. **Existing Task Group R tests remain green**: the full, unmodified
    `test_m12_siren_service.py`/`test_m12_siren_tools.py`/`test_m12_sirens_route.py` suites,
    run as regression.
26. **Relevant M12 regression remains green**: Security/Siren/AlarmControlPanel/Appliance
    sibling regression, full M12 regression, M11+M12 regression, full backend regression — same
    sequence every prior task group's Phase 2 used.

## 22. Backward compatibility

Explicitly guaranteed, each independently verified against source in §2:
- `turn_siren_on` with no arguments — unchanged (all three new parameters default to `None`).
- `turn_siren_off` — completely untouched, no parameters added.
- Existing permissions — `core:sirens`/`smart_home`, unchanged, no new grant required.
- Existing confirmation behavior — `AgentPermissionGate` gates by name only (§2), unaffected by
  richer `args`.
- Existing HA translation — `TURN_OFF` branch returns `(command.value, {})` unchanged; a bare
  `TURN_ON` call with all three parameters `None` also returns `(command.value, {})`, byte-
  identical to today.
- Existing MQTT translation — identical reasoning.
- Existing REST response envelope — unchanged `{data, meta}` shape, unchanged `meta.success`.
- Existing agent tool name — `turn_siren_on`, unchanged; no new tool added, tool count stays 4.
- Existing tests — the exact assertions naming an empty-dict payload (§2) remain valid and must
  pass without modification.

**No existing siren capability is removed or renamed.**

## 23. Deferred scope (explicit, not silently expanded)

- Siren pattern/custom waveform — confirmed no corresponding HA capability exists (§3); nothing
  to defer because nothing to build, but recorded here since the roadmap's own text names it.
- `alarm_control_panel` actions of any kind.
- Siren activation history / state history beyond Smart Home Memory's own existing, unmodified
  on-demand snapshot (Task Group V).
- Notifications, automation, scheduled sirens.
- Panic Mode / Vacation Mode coupling, in either direction.
- A future `GET`-side capability read (`available_tones` surfaced in `get_siren_state`) — a
  real, legitimate possible follow-on, deliberately not bundled into this write-only task group.

## 24. Acceptance criteria

- `SirenService.turn_on` gains exactly three new optional keyword parameters; `turn_off` and
  `SirenCommand` are unchanged.
- Both translators updated per §7/§8; both connectors remain completely unmodified.
- REST: `POST /sirens/{id}/turn_on` accepts an optional `TurnSirenOnRequest` body; no new route.
- Agent tools: `turn_siren_on` gains the same three optional arguments; tool count remains 4; no
  entry added to/removed from `AgentSettings.confirm_required_tools`.
- `get_siren_state`/`_siren_payload`/`list_sirens` are byte-identical to today.
- Full 26-item test matrix (§21) implemented and green; existing Task Group R suite green
  unmodified; sibling/M12/M11+M12/full backend regression green.
- Black/Ruff/Mypy clean against the `5cad91d` baseline, same discipline as every prior task
  group.
- Frontend requirements doc written after backend verification, planning-only.
- `CHANGELOG.md`/`docs/MASTER_ROADMAP.md` updated to mark only this slice shipped.

## 25. Risks

- **`tone` live-validation adds a connector read to the mutation path** — a new pattern for
  `SirenService` specifically (though an established one in `MediaPlayerService`). Risk: a slow
  or flaky connector read could add latency to every tone-bearing `turn_on` call. Mitigation:
  identical to `_check_source`'s own accepted tradeoff — `contextlib.suppress(ConnectivityError)`
  already makes this fully non-blocking; a failed read simply skips validation (permissive), the
  same behavior `_check_source` already ships with today.
- **Roadmap's "pattern control" phrase has no real HA counterpart** (§3/§23) — risk of a future
  reader assuming pattern control is still-deferred-but-buildable; mitigated by recording the
  finding explicitly in this contract and the eventual CHANGELOG entry, not by silently editing
  historical roadmap prose out of scope for this task group.
- **`duration` has no enforced upper bound** — a caller could request an extremely long
  duration; accepted as HA's own documented behavior (no maximum specified), consistent with
  this codebase's "no invented limits" principle applied identically to Water Heater's
  temperature and Humidifier's humidity bounds.

## 26. Exact Phase 2 implementation plan

1. Extend `SirenCommand`'s two translators (`_translate_home_assistant`, `_translate_mqtt`) per
   §7/§8.
2. Add `_validate_volume_level`/`_validate_duration` (adapted from `media_player_service.py`/
   `smart_lighting_service.py` precedents) and `_validate_tone` (format-only) plus
   `_check_tone_supported` (live-read, mirroring `MediaPlayerService._check_source`) to
   `siren_service.py`.
3. Extend `SirenService.turn_on` signature and `_send` call per §6.
4. Add `TurnSirenOnRequest` Pydantic model and thread it through `routes/sirens.py`'s
   `turn_siren_on` route per §13.
5. Extend `agents/tools/siren_tools.py`'s `turn_siren_on` tool per §14.
6. No DI/container changes — `SirenService`'s constructor is unchanged.
7. Write the full test matrix (§21) in the three existing Siren test files.
8. Run quality gates in the established order (targeted → sibling → M12 → M11+M12 → full
   backend → Black → Ruff → Mypy, baseline-compared against `5cad91d`).
9. Scope/security audit (grep for forbidden terms, `git diff --stat` scope check).
10. Write the frontend requirements doc.
11. Update `CHANGELOG.md`/`docs/MASTER_ROADMAP.md`.
12. Two commits (`feat(m12-w)`/`docs(m12-w)`), push, verify.

## M12 exit note (recorded, not decided — per Phase 1 instruction)

Per the Post-Task-Group-V audit's own conclusion (§21 of that audit: M12 should continue only
1–2 more high-value slices before the structured M0–M12 rework/audit phase), **Task Group W
appears to be one of the final two M12 slices**, likely to be followed by the previously-ranked
bundled Appliance completion slice (Fan oscillation/presets + Cover tilt/stop) before M12 enters
its exit/rework phase. This is a recorded observation for Phase 2/post-Phase-2 planning, not an
exit decision made in this Phase 1.

## Phase 1 safety confirmation

- Exactly one new untracked file: this Logic Contract.
- Zero tracked changes.
- `HEAD`/`origin/feature/m22-task-group-c` unchanged at `5cad91d8b1c6623197e2596273a0e22732e6f26c`.
- No commit made. No push made.
