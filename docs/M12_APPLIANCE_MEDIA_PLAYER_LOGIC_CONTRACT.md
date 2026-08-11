# M12 Appliance Control — Media Player Core Slice — Logic Contract

Status: **Draft — Logic Contract only.** Written per the `M12
POST-TASK-GROUP-J PHASE 0 AUDIT` and its approval (`APPROVED — PROCEED
WITH PHASE 1 ONLY`). **Not approved for implementation** — no source,
tests, DI, routes, tools, connector, permission, EventBus, roadmap or
CHANGELOG changes accompany this file. Base: the shipped M12 Appliance
Control Core Slice (`docs/M12_APPLIANCE_CONTROL_LOGIC_CONTRACT.md`,
commits `5550899`/`5ac30cf`), Climate/Thermostat Slice (`docs/
M12_APPLIANCE_CLIMATE_LOGIC_CONTRACT.md`, commits `7db0528`/`db0d21f`),
and Vacuum + Humidifier Core Slice (`docs/
M12_APPLIANCE_VACUUM_HUMIDIFIER_LOGIC_CONTRACT.md`, commits shipped as
Task Group J, HEAD now `2856bff`).

**Legend.** Every claim about code that exists today is marked
**(EXISTING)** with a `file:line` citation, verified against the
current working tree this session (clean, HEAD `2856bff`). Everything
marked **(PROPOSED)** does not exist yet. Anything not verifiable from
this repository is marked **(VERIFIED EXTERNALLY)** — checked against
HA's real public documentation this session, cited as such, never
presented as repository evidence.

## 1. Scope

**In scope**: one new dedicated service, `MediaPlayerService`, covering
read state + five independent transport commands + one merged
attribute mutation (volume/mute/source) for `device_type="appliance"`
devices whose domain is `media_player`.

**Explicitly not this slice's job** (§18 gives the full accounting):
`play_media` (arbitrary content dispatch), `join`/`unjoin` (dynamic
multi-speaker grouping), shuffle, repeat, sound mode, album, duration,
playback position (+ its staleness timestamp), media content
ID/type, artwork, queue/playlist management, room synchronization,
scheduling, automation, AI recommendations, playback history,
analytics.

## 2. Device model — confirmed, not re-decided

**(EXISTING, re-confirmed this session)**: `media_player` →
`device_type="appliance"` in both `_DEVICE_DOMAINS`
(`home_assistant.py:84`) and `_HA_COMPONENT_DEVICE_TYPES`
(`mqtt.py:165`) — the Fan/Cover/Vacuum/Humidifier pattern, not
Climate's own-`device_type` pattern. **No new `DEVICE_TYPES` entry.**
No new ORM model, no new table.

**Domain discrimination**: every `MediaPlayerService` operation
verifies `device.device_type == "appliance"` **and** the device's
domain resolves to `"media_player"`. Resolution reads
`metadata["domain"]` first, falling back to `metadata["component"]`
when absent — the identical, now twice-shipped pattern
`VacuumHumidifierService._domain_for` established (`docs/
M12_APPLIANCE_VACUUM_HUMIDIFIER_LOGIC_CONTRACT.md` §3): MQTT HA
Discovery's `component` segment carries the identical domain vocabulary
HA's own REST connector calls `domain` (`_HA_COMPONENT_DEVICE_TYPES`'s
keys are identical to `_DEVICE_DOMAINS`'s keys, re-verified this
session). **This fallback is implemented once, locally, inside
`MediaPlayerService`'s own domain-lookup helper — it does not touch
`ApplianceService` or any connector**, exactly as instructed.

## 3. Architecture (PROPOSED)

```
MediaPlayerService
    ↓
ConnectivityService (read_raw_state / send_command)
    ↓
HomeAssistantConnector / MqttConnector
```

Dependencies: `SmartHomeService` + `ConnectivityService` +
`PermissionModel` only — the identical shape `ApplianceService`/
`SmartSwitchService`/`ThermostatService`/`VacuumHumidifierService` all
share. **No `IDatabase`** (no scenes/persistence of its own), **no
`EventBus`** (§15), **no direct connector import** (all wire traffic
goes through `ConnectivityService`'s two existing chokepoints,
re-verified unchanged this session: `read_raw_state`
`connectivity_service.py:195`, `send_command`
`connectivity_service.py:214`), **no frontend dependency** (§17).

## 4. Normalized read model (PROPOSED)

```
{
  "id": str, "home_id": str, "room_id": str | None, "name": str,
  "status": str, "manufacturer": str, "model": str, "external_id": str | None,
  "state": str | None,          # open pass-through -- see §5
  "available": bool,
  "volume_level": float | None, # 0.0-1.0, HA-native -- see §6
  "is_volume_muted": bool | None,
  "source": str | None,
  "source_list": list[str],     # [] when unreported
  "media_title": str | None,
  "media_artist": str | None,
}
```

**Included, with reasoning**:
- `volume_level`, `is_volume_muted`, `source`, `source_list` — the
  three controllable attributes plus their declared-capability list;
  see §6/§7.
- `media_title`, `media_artist` — zero-cost, zero-command informational
  reads (no mutation surface, no validation complexity); the single
  highest conversational value ("what's playing") for the lowest
  implementation cost. Read only, from `attributes.get("media_title")`/
  `attributes.get("media_artist")` **(VERIFIED EXTERNALLY)**, `None`
  when absent or not a string.

**Explicitly deferred from the read surface, with reasoning per item**:

| Field | Why deferred |
|---|---|
| `media_album_name` | Third tier of the same title/artist/album metadata triad -- lowest marginal conversational value of the three, and this contract already draws the line at title+artist to keep the read surface bounded, not because album is architecturally harder. |
| `media_duration` | Numeric and cheap to coerce, but only meaningful paired with `media_position` -- including one without the other is a half-finished surface. |
| `media_position` / `media_position_updated_at` | The one field this codebase has never normalized: a **live-changing value with a staleness timestamp**, genuinely more complex than any prior field (Thermostat's/Humidifier's fields are all either static capability or point-in-time readings, never a value whose accuracy decays with wall-clock time since last report). Deferred, not attempted partially. |
| `media_content_id` / `media_content_type` | Only meaningful in combination with `play_media` (§10, explicitly not implemented) -- reading a content ID this module can never act on is dead information. |
| `media_image_url` | Presentation-layer concern; no consumer exists without frontend work, which is out of scope. |
| `sound_mode` / `sound_mode_list` | A second, parallel "mode" axis alongside `source` -- adding it now would double the validated-list surface for marginal value; can be added later following this contract's own `source`/`source_list` template if real demand emerges. |
| `shuffle` / `repeat` | Playlist-shaped state with no corresponding transport command in this MVP (§8 excludes `clear_playlist`) -- reading toggles this module cannot itself set would be inconsistent. |
| `supported_features` | HA's own capability bitmask -- a MediaPlayerEntity-shaped implementation detail with no normalized meaning across connectors; this contract uses per-field presence (`source_list` non-empty, etc.) as the capability signal instead, the same pattern Thermostat already uses for `hvac_modes`. |

**No fabricated values anywhere**: every field above defaults to
`None`/`[]` when unreported — never a guessed default, never `0.0` for
an unparseable number, matching every prior M12 module's discipline.

## 5. Playback state (PROPOSED)

**Decision: open pass-through, not a closed enum** — the identical
choice Vacuum's `state` field made (`docs/
M12_APPLIANCE_VACUUM_HUMIDIFIER_LOGIC_CONTRACT.md` §5), for the
identical reason: **(VERIFIED EXTERNALLY)** HA's real media_player
states include `playing`/`paused`/`idle`/`off`/`standby`/`buffering`/
`on`, but this repository carries zero prior reference to any of them,
and per-integration extensions to this vocabulary are common. Inventing
a closed set this module validates against would risk rejecting a real
device over a vocabulary gap — the same principle `DEVICE_TYPES`' own
comment states explicitly.

**Normalization rules**:
- `state` is `raw.status.strip().lower()`, or `None` if the stripped
  result is empty.
- **Unavailable → `state = None`**, never the literal
  `"unavailable"`/`"offline"` string — the same rule Vacuum/Thermostat
  both established for their own "entity state doubles as a semantic
  field" cases, re-applied here because the media_player entity's own
  state string *is* its playback state, exactly like Vacuum.
- **Unknown/unrecognized state string** (anything HA or a vendor
  integration reports that isn't in the commonly-known set above) is
  passed through verbatim, lowercased — never coerced to `None` and
  never rejected. Only the *unavailable* case forces `None`.
- Case is always normalized on read (`.lower()`); no case-folding is
  needed on write since this module sends no state string back (§8
  commands are verb-shaped, not state-shaped).

## 6. Volume — resolved

**Decision: Option A — preserve HA-native `0.0`–`1.0` float. No
JARVIS-normalized 0–100 representation.**

**Why A, and why this is *not* the same situation as Lighting's
`brightness_pct`.** Smart Lighting normalizes brightness to 0–100
specifically because **HA's `light.turn_on` service itself accepts
`brightness_pct` as a first-class parameter** (`smart_lighting_service.
py:123-126`, existing code, re-read this session) — the 0–100
representation is not JARVIS's invention, it is HA's own alternate
native parameter, so normalizing to it costs nothing and avoids a lossy
0–255 round-trip. **No equivalent exists for volume**: HA's
`media_player.volume_set` service has exactly one native
representation, `volume_level: float, 0.0-1.0` **(VERIFIED
EXTERNALLY)** — there is no `volume_pct` sibling parameter the way
`brightness_pct` sits alongside `brightness`. Introducing a 0–100
JARVIS scale here would require *this module* to invent and maintain a
conversion (`value / 100.0`) that has no HA-side counterpart to
justify it — exactly the kind of invented unit conversion Thermostat's
own Logic Contract §7 already ruled out for temperature, generalized
here to volume. Preserving the native `0.0`–`1.0` float is therefore
the same "opaque scalar in the connector's own representation"
principle, correctly applied to the one case where no alternate native
parameter exists.

**Validation rules (PROPOSED)**:
- Accepted: `int` or `float`, coerced to `float`.
- **Rejected**: `bool` (an `int` subclass — the same explicit guard
  every prior numeric field in this codebase uses), `NaN`, `+inf`,
  `-inf` — `ServiceError` before any wire call.
- **Range enforced**: `0.0 <= value <= 1.0`, rejected outside that
  range with `ServiceError` — unlike Thermostat's temperature (bounded
  only when the *device* reports `min_temp`/`max_temp`), volume's
  `0.0`–`1.0` bound is **HA's own protocol-level constraint on the
  parameter itself**, not a device-specific capability this module
  would otherwise have no evidence for — so enforcing it does not
  violate the "no invented limits" principle; it is enforcing the
  wire format's own contract, the same way `_validate_color`
  (`smart_lighting_service.py:190-196`) already enforces `0-255` per
  channel because that is RGB's own definition, not a guessed safety
  limit.
- **Read**: `volume_level` is `None` when unreported or unparseable —
  never fabricated as `0.0`.

## 7. Mute (PROPOSED)

**Field name: `is_volume_muted`, not a JARVIS-renamed `muted`.**
Reasoning: every prior M12 module that passes an HA attribute through
read-only uses HA's own attribute name verbatim when no cross-connector
ambiguity exists (e.g. `min_temp`/`max_temp`, `hvac_modes`) — renaming
would add a translation layer with no benefit, since this field has
only one real-world shape (a boolean) and no unit-conversion concern
the way volume does. The **mutation parameter**, however, is
`muted: bool | None` on `set_media_player_state` (§9) — matching the
established pattern of short, ergonomic mutation-parameter names
(`on`, `hvac_mode`, `temperature`) distinct from the fuller read-payload
field names.

- **Validation**: must be `bool` if supplied; anything else →
  `ServiceError` before any wire call. No range/enum concern.
- **Missing on read**: `is_volume_muted = None` when unreported.
- **Combination with volume/source**: no interaction rule needed — the
  three attributes are independent HA-side concepts (§9's ordering is
  about wire-call sequencing, not semantic coupling); setting mute
  does not imply or require a volume/source value and vice versa.

## 8. Transport commands (PROPOSED)

```python
class MediaPlayerCommand(enum.StrEnum):
    PLAY = "media_play"
    PAUSE = "media_pause"
    STOP = "media_stop"
    NEXT = "media_next_track"
    PREVIOUS = "media_previous_track"
```

Five independent, zero-payload commands — **not** merged into §9's
attribute mutation, per the explicit instruction and matching
`VacuumCommand`'s exact precedent (`docs/
M12_APPLIANCE_VACUUM_HUMIDIFIER_LOGIC_CONTRACT.md` §6): these are
momentary actions, not settable attributes, so a merged method would
not "preserve one intent" — it would just pack five unrelated verbs
into one call.

**HA wire commands — (VERIFIED EXTERNALLY, not repository-derived)**:

| Normalized | HA service | Payload |
|---|---|---|
| `PLAY` | `media_play` | `{}` |
| `PAUSE` | `media_pause` | `{}` |
| `STOP` | `media_stop` | `{}` |
| `NEXT` | `media_next_track` | `{}` |
| `PREVIOUS` | `media_previous_track` | `{}` |

Reached through the existing generic dispatcher (`home_assistant.py:
230-256`, re-verified unchanged): `media_player.*` entity ids resolve
`domain="media_player"`, routing to `POST /api/services/media_player/
{command}` — zero connector changes.

**Explicitly not implemented** (§18 gives full reasoning): `play_media`,
`join`, `unjoin`, `clear_playlist`, any arbitrary media-URI dispatch.

## 9. Merged state mutation (PROPOSED)

```python
async def set_media_player_state(
    self, device_id: str, *,
    volume: float | None = None,
    muted: bool | None = None,
    source: str | None = None,
) -> dict[str, Any]: ...
```

Mirrors `ThermostatService.set_thermostat_state`'s shape exactly — the
three attributes can combine into one user intent ("mute it and switch
to Spotify"), unlike §8's transport verbs.

**Empty mutation**: all three `None` → `ServiceError` before any wire
call, identical to every prior merged-mutation module's rule.

**Validation order** (fails fast, before any wire call): device-type/
domain check → per-field type/range validation (§6/§7) → `source`
against device-reported `source_list` when non-empty (§7 of this
contract... see §11 below) → wire dispatch.

**Command ordering — resolved: volume, then mute, then source.**
Reasoning: HA has three independent single-purpose services here
(`volume_set`, `volume_mute`, `select_source`), so — unlike Thermostat's
mode-before-temperature (where mode changes what the temperature means)
or Humidifier's on/off-before-humidity (a readability convention) —
there is **no semantic dependency between any pair of these three**.
The ordering is therefore a convention, not a correctness requirement,
chosen to match the field declaration order in the method signature
and in §4's payload (volume → mute → source) for predictability. Stated
explicitly so it is never later mistaken for a discovered HA behavior.

**Partial failure semantics**: identical to Thermostat/Humidifier — each
requested call executes in order, stopping at the first failure;
`success: false` names exactly which calls already applied
(`"volume_set failed (...); already applied: volume_set."`-shaped
detail) — never a false full success, never a silent retry.

**Response**: `{"device_id": str, "success": bool, "detail": str}` —
identical shape to every prior M12 command result.

## 10. HA translation (PROPOSED)

**(VERIFIED EXTERNALLY, explicitly not claimed as repository-derived)**:

| Normalized | HA service | Payload |
|---|---|---|
| `volume` | `volume_set` | `{"volume_level": <float 0.0-1.0>}` |
| `muted` | `volume_mute` | `{"is_volume_muted": <bool>}` |
| `source` | `select_source` | `{"source": "<str>"}` |

All reached through the same generic dispatcher as §8 — zero connector
changes.

**Explicitly not implemented, with reasoning**:
- `play_media` — arbitrary content URI/type dispatch has no safe
  normalization without inventing per-vendor payload logic; the
  highest scope-creep risk item the Phase 0 audit identified.
- `join`/`unjoin` — dynamic multi-speaker grouping; no repository
  modeling exists for dynamic multi-device relationships (Room/Group
  are static, `SmartHomeService`-owned concepts, not the same shape).
- `clear_playlist` — playlist-shaped state with no corresponding read
  surface in this MVP (§4 excludes `shuffle`/`repeat`/queue state).

## 11. MQTT translation (PROPOSED)

**A first-definition JARVIS-native vocabulary** — no prior MQTT
consumer for media playback exists (re-confirmed this session: zero
matches for any of these terms anywhere in `src/`/`tests/`), the
identical situation every prior M12 module's own MQTT vocabulary was
in.

Transport (always one merged-free, single call each, mirroring §8's
zero-payload shape):

| Normalized | MQTT `command` | MQTT `args` |
|---|---|---|
| `PLAY` | `media_play` | `{}` |
| `PAUSE` | `media_pause` | `{}` |
| `STOP` | `media_stop` | `{}` |
| `NEXT` | `media_next_track` | `{}` |
| `PREVIOUS` | `media_previous_track` | `{}` |

Reuses the identical literal strings as the HA translator for
cross-connector predictability — the same choice every prior module's
MQTT vocabulary made.

State mutation — **one merged `set_state` call**, mirroring Thermostat's
and Humidifier's own MQTT convention (deliberately *not* copying HA's
three-separate-service split, since the MQTT envelope has no such
constraint):

| Requested | MQTT `command` | MQTT `args` |
|---|---|---|
| volume only | `set_state` | `{"volume": <float>}` |
| muted only | `set_state` | `{"muted": <bool>}` |
| source only | `set_state` | `{"source": <str>}` |
| any combination | `set_state` | merged dict of whichever above are set |

**Domain resolution**: `metadata["domain"]` first, `metadata["component"]`
fallback — §2's local helper, reused for MQTT-discovered media players
exactly as for HA-discovered ones. **No connector modification.**

## 12. Source validation (PROPOSED)

Directly mirrors `ThermostatService`'s `hvac_mode`/`hvac_modes`
precedent (`docs/M12_APPLIANCE_CLIMATE_LOGIC_CONTRACT.md` §6),
re-applied to `source`/`source_list`:

- **When the device reports a non-empty `source_list`** (from
  `attributes.get("source_list")`, coerced to a list of stripped,
  non-empty strings): a requested `source` not in that list is
  rejected with `ServiceError` before any wire call.
- **When `source_list` is absent/empty**: any non-empty string
  `source` is accepted and passed through — the device/connector is
  the authority, and a rejection surfaces as `success: false`, not a
  fabricated local error.
- **No fixed source enum is invented anywhere** — the same "rejecting a
  real device over a vocabulary gap is the worse failure" principle
  `DEVICE_TYPES`' own comment states.
- Comparison is exact-string (no case-folding) — unlike HVAC mode,
  source names are often mixed-case, human-facing labels (`"Spotify"`,
  `"HDMI 1"`) where forcing lowercase could break a real device's
  actual expected value; this module does not normalize case for
  `source`, only for `state` (§5), a deliberate, stated difference.

## 13. REST contract (PROPOSED)

Under the existing `/appliances` prefix, matching Fan/Cover/Vacuum/
Humidifier's own convention (siblings in every architectural respect
even though each lives in its own service):

| Method | Path | Behavior |
|---|---|---|
| GET | `/appliances/media-players` | List (DB-only, no live read). |
| GET | `/appliances/media-players/{id}` | Live state (§4). 404 if unknown/not a media player. |
| POST | `/appliances/media-players/{id}/play` | |
| POST | `/appliances/media-players/{id}/pause` | |
| POST | `/appliances/media-players/{id}/stop` | |
| POST | `/appliances/media-players/{id}/next` | |
| POST | `/appliances/media-players/{id}/previous` | |
| POST | `/appliances/media-players/{id}/state` | Body `{"volume"?: float, "muted"?: bool, "source"?: str}`. Empty body → 400. |

`{data, meta}` envelope, `Depends(get_current_session)` — identical to
every M12 router. **Error taxonomy**: matches Vacuum+Humidifier's
convention exactly — reads ungated, so no permission-driven 400-vs-404
split. Plain `GET .../{id}`: unknown/wrong-type → **404**. Every action
endpoint: any `ServiceError` → **400**. `success: false` is **200**,
never an error, identical to every prior M12 command.

## 14. Agent tools (PROPOSED)

Eight tools — reads + five independent transport tools + one merged
state tool, exactly the shape §9's instruction specifies, no separate
volume/mute/source tools:

| Tool | Wraps |
|---|---|
| `list_media_players` | `list_media_players()` |
| `get_media_player_state` | `get_media_player_state()` |
| `media_play` | `play()` |
| `media_pause` | `pause()` |
| `media_stop` | `stop()` |
| `media_next` | `next_track()` |
| `media_previous` | `previous_track()` |
| `set_media_player_state` | `set_media_player_state(volume?, muted?, source?)` |

All eight call `MediaPlayerService` only, never `ConnectivityService`
or a connector directly. No mutation tool requires confirmation (§19).
Every tool catches `Exception` broadly and returns a friendly string,
matching every M12 tool file's convention.

## 15. EventBus decision

**No event changes, prohibited explicitly.** `MediaPlayerService`
publishes nothing. No `MediaPlayerUpdatedEvent`, no subscriptions, no
workers, no playback-history events. Poll-based only, matching all
eight prior M12 modules (re-verified this session: zero
`event_bus`/`EventBus` references remain the pattern across every
service file). The pre-existing device-command event-publishing gap
remains untouched — not fixed here, recorded as a separate
architectural dependency for Home Automation/Smart Home Memory/
Developer Tools' Event Viewer, exactly as every prior contract recorded
it.

## 16. Database / Memory / Analytics decision

**None required.** No new table, no new column, no `DEVICE_TYPES`
addition. **Explicitly deferred, not stubbed**: playback history,
listening history, media analytics, trends, recommendations, long-term
media memory — all Smart Home Memory's/Smart Home Analytics' job, both
unstarted. No `MemoryService`/Analytics dependency, no placeholder
hooks toward either.

## 17. Frontend independence

Zero frontend files referenced, read, or required. **Backend-only
viable: YES** — REST + tools deliver full MVP value without any UI,
consistent with every M12 module to date.

## 18. Deferred scope (explicit, no placeholders)

| Item | Why deferred |
|---|---|
| `play_media` / arbitrary media URI/content dispatch | Highest scope-creep risk identified in Phase 0; no safe normalization without vendor-specific payload logic. |
| `join` / `unjoin` / dynamic multi-speaker grouping | No repository modeling exists for dynamic multi-device relationships (Room/Group are static, `SmartHomeService`-owned, a different shape). |
| Shuffle, repeat, sound mode | No corresponding read fields in this MVP (§4); would need their own validated-list pattern, deferrable to a future slice following this contract's own `source`/`source_list` template. |
| Album, duration, playback position (+ staleness timestamp) | §4's per-field reasoning — position specifically is the first "value that decays with wall-clock time" this codebase would need to normalize; deferred whole, not partially. |
| Media content ID/type, artwork/image URL | Only meaningful paired with `play_media` or a frontend consumer, neither in scope. |
| Queue/playlist management | No corresponding transport command (`clear_playlist` explicitly excluded, §10). |
| Room/output synchronization beyond existing static Room/Group | Same reasoning as `join`/`unjoin`. |
| Vendor-specific controls | By definition, no normalized model exists to build against. |
| Scheduling, automation | Home Automation's job — blocked on M7's Scheduler (confirmed unstarted in every prior audit this session) and the event-publishing gap (§15). |
| AI recommendations | AI Home Assistant's job, unstarted. |
| Playback history, analytics | Smart Home Memory's/Smart Home Analytics' job, both unstarted (§16). |

**No placeholder backend architecture, no scaffolding, no dead
parameters, no reserved-but-unused payload fields for any of these.**

## 19. Safety / confirmation

Play, pause, stop, next, previous, volume, mute, and source are all
**ordinary media-playback controls with no physical safety or security
consequence** — the same risk tier `fan_on`/`switch_on`/`cover_open`/
`set_thermostat_state`/`set_humidifier_state` already occupy, none of
which required a `confirm_required_tools` entry
(`config/settings.py:513`, unchanged: `{"run_automation",
"unlock_device"}`). Unlike `unlock_device` (a physical security
boundary) or a hypothetical safety-critical actuator, changing what a
speaker is playing has no comparable irreversibility or harm profile.
**No confirmation requirement is added.** Reads remain ungated for the
identical reason every appliance-shaped module's reads are ungated: no
Sensors-grade privacy weight (knowing what's playing does not reveal
who is home the way motion/presence does).

## 20. Permission decision (PROPOSED)

- **Scope**: existing `smart_home` — no new scope.
- **Principal**: `core:media_players`, declared once at construction,
  `PENDING` by default, granted through the existing generic route
  `POST /api/v1/plugins/core:media_players/permissions/smart_home/
  grant` — the ninth instance of this now-fully-proven pattern.
- **Reads: UNGATED.** **Mutations (both transport and merged state):
  GATED.**
- **No confirmation** (§19).

## 21. Test strategy (future — described, not created)

Real components throughout (`FakeDeviceConnector`, real temp-file
SQLite, real `PermissionModel`), matching every prior M12 module's
discipline — no mocks.

- Discovery/domain: `_domain_for` resolves via `"domain"` then
  `"component"` fallback; rejects a device with neither. Wrong device
  type (every foreign `device_type`) and wrong appliance-domain (fan/
  cover/vacuum/humidifier ids passed to media-player endpoints, and
  vice versa) rejected on every method, including reads.
- State normalization: full payload; unavailable → `state=None`
  (never the literal string); unknown/unrecognized state string passed
  through verbatim; missing/malformed attributes → `None`/`[]`, never
  fabricated.
- Volume: valid range accepted at both bounds inclusive; out-of-range
  rejected; `bool` rejected; `NaN`/`+inf`/`-inf` rejected; missing on
  read → `None`.
- Mute: `bool` accepted; non-bool rejected; missing on read → `None`.
- Source: accepted when in device-reported `source_list`; rejected
  when not; permissive when `source_list` empty/absent; case preserved
  (not lowercased).
- Transport: all five commands, HA translation (zero payload each) and
  MQTT translation (zero payload each), for both device types is-a-
  media-player.
- Merged mutation: volume-only, mute-only, source-only, every pairwise
  and full-triple combination; ordering verified (volume → mute →
  source); empty mutation rejected; partial failure reports exactly
  what applied.
- Permission: reads ungated with no grant; every mutation (transport
  and merged) denied without `core:media_players`/`smart_home`.
- REST: list/get/five transport verbs/merged state; validation → 400;
  permission → 400; not found → 404; wrong type → 404 (GET)/400
  (action); unavailable device still 200; envelope shape.
- Tools: registration; all eight tools' happy path and error path.
- Cross-cutting: source-level test proving `ApplianceService` carries
  no `media_player`/`MediaPlayerCommand`/`set_media_player_state`
  symbol (mirroring the exact "not extended" proof pattern Thermostat's
  and Vacuum+Humidifier's own implementations used); source-level test
  proving no `EventBus` reference and no direct connector import exist
  in the new service.
- Explicit negative tests confirming every §18 deferred item has no
  route, tool, field, or enum value anywhere in the implementation.

## 22. Risks

1. **Largest attribute/service surface of any M12 module to date** —
   even after trimming to the MVP in §4, this remains the richest
   normalized model yet; implementation must re-verify every
   VERIFIED-EXTERNALLY item against a real HA instance before relying
   on it, the same discipline every prior contract's own uncertain
   items required.
2. **External HA evidence vs. repository evidence** — every service
   name and payload shape in §8/§10 is web-verified, not
   repository-derived; this is a materially different confidence tier
   than §2's connector-mapping claims, which *are* repository-verified.
3. **MQTT is a first-definition vocabulary** with no prior consumer to
   cross-check against, the same situation (now four times) every
   prior module's own MQTT translator was in.
4. **Volume representation (§6)** is the audit's flagged undecided
   question, now resolved here with an explicit architectural
   justification distinct from Lighting's `brightness_pct` case — a
   real design decision, not a default.
5. **Source validation (§12)** directly reuses Thermostat's proven
   template; the risk is case-sensitivity assumptions if a real device
   turns out to expect normalized-case source names despite this
   contract's explicit choice not to lowercase them.
6. **Playback-state variability** — the open-vocabulary decision (§5)
   means a typo'd or unexpected state string simply passes through;
   accepted deliberately, the same tradeoff Vacuum already made.
7. **Arbitrary-media-playback scope creep** — `play_media` is the
   single most likely feature to be requested "just this once" during
   implementation; §10/§18 exclude it explicitly and by name.
8. **Dynamic multi-device grouping** — `join`/`unjoin` is the second
   most likely scope-creep target; excluded explicitly.
9. **Playback-position semantics** — deferred whole (§4) specifically
   because no prior M12 field has needed a staleness/timestamp concept;
   a future slice attempting it should not assume today's `_coerce_
   float`-style helpers are sufficient without designing that concept
   fresh.
10. **Partial failure during the three-call merged mutation** — the
    most calls any single M12 mutation has needed to sequence (three,
    vs. Thermostat's/Humidifier's two); the partial-failure detail
    message must name potentially two already-applied calls, not just
    one — a slightly larger surface for that logic than any prior
    module exercised.

## 23. Acceptance criteria

- `MediaPlayerService` depends only on `SmartHomeService`,
  `ConnectivityService`, `PermissionModel` — no `IDatabase`, no
  `EventBus`, no direct connector import.
- `ApplianceService` is **not** modified, extended, or branched into.
- Domain discrimination correctly resolves both HA-REST-sourced
  (`"domain"`) and MQTT-HA-Discovery-sourced (`"component"` fallback)
  devices, implemented locally in the new service only.
- Zero connector code changes, zero `DEVICE_TYPES` additions, zero
  schema changes, zero new permission scope, zero events published.
- No fabricated values anywhere: every unreported field is `None`/`[]`;
  `state` is `None`, never the literal `"unavailable"`/`"offline"`
  string, when the device is unavailable.
- `volume_level` stays HA-native `0.0`–`1.0`; no 0–100 conversion
  exists anywhere in the implementation.
- `source` is validated against device-reported `source_list` only
  when non-empty; no fixed source enum exists.
- Five transport commands remain independent, zero-payload, and never
  appear in the merged mutation's parameter list.
- The merged mutation rejects the empty (all-`None`) case and reports
  partial failure honestly, naming exactly what already applied.
- Every item in §18's deferred table has zero corresponding route,
  tool, field, enum value, or scaffold anywhere in whatever
  implementation eventually follows this contract.
- No mutation requires `confirm_required_tools`; reads remain ungated;
  mutations require `core:media_players`/`smart_home`.
- Full backend regression stays green (baseline: 3157 tests, 0
  failures, 1 pre-existing skip).
- No file under `frontend/` or `Jarvis-Frontend-main/frontend` is
  touched.
- This Logic Contract is reviewed and approved **before** any
  implementation begins.

Every criterion above is implementable without new schema, EventBus,
frontend, a new milestone dependency, connector-wide refactoring,
`ApplianceService` modification, or any change to previously shipped
M12 behavior.
