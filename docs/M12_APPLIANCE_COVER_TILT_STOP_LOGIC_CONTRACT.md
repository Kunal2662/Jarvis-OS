# M12 Appliance Control — Cover Tilt + Stop — Logic Contract

Status: **Implemented this session** (Task Group Z). Closes two items
the Fan Percentage + Cover Position Slice's own Logic Contract
explicitly named and deferred (§17): "Cover tilt (`current_tilt_position`,
`set_cover_tilt_position`) — a separate HA feature flag
(`CoverEntityFeature.SET_TILT_POSITION`), not evaluated this pass" and
"Cover `stop_cover` — a third existing HA service this slice does not
add; binary open/close plus position is the approved scope."

## 1. External verification (this session, via live web search —
Home Assistant's own documentation, not recalled from training data)

- **`cover.stop_cover`** — stops a cover's movement. No parameters.
  [Cover — Home Assistant](https://www.home-assistant.io/integrations/cover/)
- **`cover.set_cover_tilt_position`** — tilts a cover to a specific
  position. One parameter, **`tilt_position`**, integer 0–100 (0 =
  fully closed tilt, 100 = fully open tilt), the identical convention
  `position`/`percentage` already use.
  [Set cover tilt position — Home Assistant](https://www.home-assistant.io/actions/cover.set_cover_tilt_position/)
- **Read attribute: `current_tilt_position`** — not
  `current_cover_tilt_position`, confirmed to be the real name (matches
  what the original Fan Percentage + Cover Position Logic Contract §17
  had already recorded — this session's search corroborates it, not a
  new finding). Mirrors `current_cover_position`'s own established
  "different name from the write parameter" pattern.
  [Cover — Home Assistant](https://www.home-assistant.io/integrations/cover/)

## 2. Existing evidence (re-confirmed this session)

Both HA and MQTT translators already exist for `set_cover_position`
(`services/appliance_service.py`) and already prove the exact shape
this slice needs — one wire command, one value, translated identically
by both connectors. `_domain_for`/`_require_cover` domain
discrimination is unchanged; `stop_cover`/`set_cover_tilt_position` are
cover-domain commands like every other cover command already handled.
Zero connector changes — both connectors' `send_command` already
accept an arbitrary payload dict generically, the same reasoning every
prior Appliance Control slice has established.

## 3. Architecture decision

**Add `cover_stop`/`set_cover_tilt_position` as two new methods on the
existing `ApplianceService`, not a new service.** Matches this
module's own established shape — every cover capability lives on this
one service, discriminated by `metadata["domain"]`, never split across
services per command.

**Fix the translator's key-selection logic, not extend the awkward
binary if/else.** The existing translators pick a payload key with
`key = "percentage" if command is FanCommand.SET_PERCENTAGE else
"position"` — correct for exactly two value-bearing commands, but
`else "position"` would silently mislabel `set_cover_tilt_position`'s
own payload key too. Replaced with an explicit
`_VALUE_PAYLOAD_KEYS: dict[FanCommand | CoverCommand, str]` mapping
(`SET_PERCENTAGE → "percentage"`, `SET_POSITION → "position"`,
`SET_TILT_POSITION → "tilt_position"`), which both translators look up
— correct by construction for any future value-bearing command, not
just the two that existed before this slice. `stop_cover` needs no key
at all (no value), so it is unaffected — it already falls through the
existing "no value → `{}` payload" branch every no-argument command
(`turn_on`/`turn_off`/`open_cover`/`close_cover`) already uses.

## 4. Read model addition

```python
payload["tilt_position"] = None
```

Added to `_cover_payload`, read from `attributes.get("current_tilt_position")`
via the existing `_coerce_int` helper, gated behind `available` — the
same category `position` already falls into (a current reading, not a
declared capability; no capability list exists for cover tilt the way
`hvac_modes`/`fan_modes` exist for thermostats, since HA reports tilt
support as a static feature flag on the entity, not a value list this
module's own `read_raw_state` surfaces).

## 5. Write model addition

- `cover_stop(device_id)` — sends `stop_cover` with no payload,
  mirroring `cover_open`/`cover_close` exactly (permission check, then
  `_send_cover`).
- `set_cover_tilt_position(device_id, tilt_position)` — sends exactly
  one `set_cover_tilt_position` wire command, never an implicit
  accompanying open/close/position call, mirroring
  `set_cover_position`'s own "exactly one standalone wire command"
  discipline. Reuses `_validate_percent_range` verbatim (already
  attribute-agnostic; `field_name="tilt_position"`).

## 6. REST / agent tools

- `POST /appliances/covers/{device_id}/stop` — no request body.
- `POST /appliances/covers/{device_id}/set_tilt_position` — body
  `{"tilt_position": int}`.
- Two new agent tools, `cover_stop`/`set_cover_tilt_position`, mirroring
  `cover_open`/`set_cover_position`'s own docstring and
  confirm-before-calling framing exactly. Neither is added to
  `AgentSettings.confirm_required_tools` — tilting/stopping a cover
  carries the same non-safety-relevant weight `set_cover_position`
  already carries.

## 7. Permission / security

Unchanged. Same `core:appliances` principal, same `smart_home` scope,
same ungated-reads/gated-mutation shape as every other appliance
command.

## 8. Test strategy

Extends `test_m12_appliance_service.py`, `test_m12_appliances_route.py`,
`test_m12_appliance_tools.py` (all three already exist), mirroring
`set_cover_position`'s own existing test shape for both `cover_stop`
(denied-by-default, wrong-device-type rejection, sends exactly one
no-payload call, never implies open/close, failure reporting) and
`set_cover_tilt_position` (denied-by-default, wrong-device-type,
valid-range acceptance, out-of-range/non-integer rejection, never
implies open/close/position, failure reporting, MQTT translation, read
round-trip including the "a stray `tilt_position`-adjacent attribute
name must not be misread" pattern `current_cover_position` already
established for `position`). Translator key-mapping fix is itself
pinned by a direct unit test asserting the payload key for all three
value-bearing commands.

## 9. Non-goals

Every other item the original slice's own §17 deferred table still
names (fan oscillation/preset modes, cover-position `stop_cover`
already closed here, but nothing else) remains deferred. No connector,
`DEVICE_TYPES`, or `CONNECTOR_TYPES` change.

## 10. Acceptance criteria

- `cover.stop_cover` and `cover.set_cover_tilt_position` names, and the
  `tilt_position` parameter/`current_tilt_position` attribute names,
  externally verified this session (§1), not recalled.
- `_VALUE_PAYLOAD_KEYS` replaces the binary if/else; both translators
  produce the correct key for `percentage`/`position`/`tilt_position`.
- `set_cover_tilt_position` validated 0-100 integer via the existing
  `_validate_percent_range`, no new validator.
- `tilt_position` read gated behind `available`, like `position`.
- Zero connector, `DEVICE_TYPES`, or `CONNECTOR_TYPES` changes.
- No new REST route beyond the two named; no new agent-tool beyond the
  two named; neither added to `confirm_required_tools`.
