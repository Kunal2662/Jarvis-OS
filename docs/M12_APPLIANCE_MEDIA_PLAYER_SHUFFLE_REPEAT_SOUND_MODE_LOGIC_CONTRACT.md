# M12 Appliance Control — Media Player Shuffle/Repeat/Sound Mode — Logic Contract

Status: **Implemented this session** (Task Group BB). Closes one item
the Media Player Core Slice's own Logic Contract explicitly named and
deferred (§18): "Shuffle, repeat, sound mode — No corresponding read
fields in this MVP (§4); would need their own validated-list pattern,
deferrable to a future slice following this contract's own `source`/
`source_list` template." `play_media`, join/unjoin, album/duration/
playback position, and queue management remain separately deferred,
unchanged.

## 1. External verification (this session, via live web search — Home
Assistant's own documentation, not recalled from training data)

- **`media_player.shuffle_set`** — one parameter, **`shuffle`**,
  boolean.
  [Set media player shuffle — Home Assistant](https://www.home-assistant.io/actions/media_player.shuffle_set)
- **`media_player.repeat_set`** — one parameter, **`repeat`**, a
  protocol-level fixed enum: `off` / `all` (loop the whole queue) /
  `one` (loop the current track). Unlike `source`, this is HA's own
  closed vocabulary, not a device-reported list.
  [Set media player repeat — Home Assistant](https://www.home-assistant.io/actions/media_player.repeat_set/)
- **`media_player.select_sound_mode`** — one parameter, **`sound_mode`**,
  a string whose valid values are device-reported (mirrors `source`
  exactly).
  [Select media player sound mode — Home Assistant](https://www.home-assistant.io/actions/media_player.select_sound_mode/)
- **Read attributes: `shuffle` (bool), `repeat` (string), `sound_mode`
  (string), `sound_mode_list` (list, the device's own reported
  capability)** — confirmed as the real attribute names, not invented.
  [Media player — Home Assistant](https://www.home-assistant.io/integrations/media_player/)

## 2. Existing evidence (re-confirmed this session)

`MediaPlayerService._translate_state_home_assistant`/`_translate_state_
mqtt` already prove the exact shape this slice needs — HA sends one
independent service call per attribute (`volume_set`/`volume_mute`/
`select_source`), MQTT merges everything into one `set_state` call.
`_check_source`/`_coerce_source_list`/`_validate_source` already prove
the "validate against the device's own reported list, permissive when
absent" template this slice's own deferred-scope entry named
explicitly. Zero connector changes — both connectors' `send_command`
already accept an arbitrary payload dict generically.

## 3. Architecture decision

**Extend the existing merged `set_media_player_state` with three more
optional keywords, not a new method.** `shuffle`/`repeat`/`sound_mode`
are attributes that combine with `volume`/`muted`/`source` into the
same "one user intent" mutation — the identical reasoning that already
grouped `volume`/`muted`/`source` into one call rather than three
separate methods. Call order becomes volume, mute, source, shuffle,
repeat, sound_mode (extends the contract's own declared convention,
still not a discovered dependency — none of the six changes what
another means).

**`repeat` is validated against a fixed, hardcoded enum
(`{"off", "all", "one"}`), unlike `source`/`sound_mode`.** This is the
one exception to this module's own "no invented enum" rule, justified
the same way `_validate_volume`'s `0.0`-`1.0` bound already is: HA
defines `repeat` as a protocol-level closed vocabulary identical across
every media player, not a device-specific list the way `source_list`/
`sound_mode_list` are. `sound_mode` gets the `source` treatment exactly
(non-empty string, checked against the device's own `sound_mode_list`
only when non-empty) since HA defines no fixed sound-mode vocabulary.

## 4. Read model addition

```python
payload["shuffle"] = None
payload["repeat"] = None
payload["sound_mode"] = None
payload["sound_mode_list"] = []
```

Added to `_media_player_payload`. `sound_mode_list` is a capability
field that survives unavailability (mirrors `source_list` exactly —
reuses the same generic `_coerce_source_list` helper, which coerces
any device-reported string list, not something source-specific despite
its name). `shuffle`/`repeat`/`sound_mode` are live readings, gated
behind `available`, mirroring `source`/`is_volume_muted`. `repeat` is
an open pass-through of HA's own state string (like `state` itself),
never independently re-validated on read — the same "detect at use,
not fabricate" discipline `_infer_cover_state` already established
elsewhere, since a mis-set device attribute should be visible, not
silently blanked.

## 5. Write model addition

`set_media_player_state` gains three new keyword-only parameters:
- `shuffle: bool | None = None` — validated via a new `_validate_shuffle`
  (mirrors `_validate_muted` verbatim).
- `repeat: str | None = None` — validated via a new `_validate_repeat`
  against the fixed `{"off", "all", "one"}` set (§3).
- `sound_mode: str | None = None` — validated via a new
  `_validate_sound_mode` (mirrors `_validate_source` verbatim), then
  checked via a new `_check_sound_mode` (mirrors `_check_source`
  verbatim) against the device's own reported `sound_mode_list`.

The empty-mutation check widens to all six keywords. `_translate_state_
home_assistant`/`_translate_state_mqtt` gain the same three keyword-only
parameters (defaulting to `None`) — every existing call site and every
existing direct-call unit test assertion (which pass `volume=`/`muted=`/
`source=` explicitly) is unaffected.

## 6. REST / agent tools

No new route, no new agent tool — `POST /appliances/media_players/{id}/
state` and the existing `set_media_player_state` agent tool both gain
the three new optional fields, identical to how Thermostat Fan Mode
extended `set_thermostat_state` without a new route or tool.

## 7. Permission / security

Unchanged. Same `core:media_players` principal, same `smart_home`
scope, same ungated-reads/gated-mutation shape as every other media
player command.

## 8. Test strategy

Extends `test_m12_media_player_service.py`, `test_m12_media_players_
route.py` (if it exists as a separate file) or the equivalent route
test module, and `test_m12_media_player_tools.py` — mirroring
`source`'s own existing test shape for `sound_mode` (denied-by-default,
device-list validation, permissive-when-no-list, empty-string
rejection) and adding dedicated tests for `shuffle` (boolean
rejection) and `repeat` (valid-enum acceptance for all three values,
invalid-value rejection). Combined-mutation ordering is pinned by a
direct translator unit test asserting all six calls in the declared
order when all six are supplied.

## 9. Non-goals

Every other item the original slice's own §18 deferred table still
names (`play_media`, join/unjoin, album/duration/playback position,
queue management, vendor-specific controls, scheduling, AI
recommendations, playback history/analytics) remains deferred,
unchanged. No connector, `DEVICE_TYPES`, or `CONNECTOR_TYPES` change.

## 10. Acceptance criteria

- `media_player.shuffle_set`/`repeat_set`/`select_sound_mode` names and
  their `shuffle`/`repeat`/`sound_mode` parameters, plus the
  `shuffle`/`repeat`/`sound_mode`/`sound_mode_list` attribute names,
  externally verified this session (§1), not recalled.
- `repeat` validated against the fixed `{"off", "all", "one"}` set;
  `sound_mode` validated against the device's own reported
  `sound_mode_list` only when non-empty, never an invented enum.
- `sound_mode_list` read survives unavailability like `source_list`;
  `shuffle`/`repeat`/`sound_mode` are gated behind `available` like
  `source`.
- Every existing `set_media_player_state`/translator call site and
  direct-call unit test is behaviorally unchanged.
- Zero connector, `DEVICE_TYPES`, or `CONNECTOR_TYPES` changes.
- No new REST route; no new agent tool.
