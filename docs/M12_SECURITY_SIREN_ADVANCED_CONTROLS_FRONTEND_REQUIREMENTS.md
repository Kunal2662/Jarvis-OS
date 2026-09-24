# M12 Security & Safety — Siren Advanced Controls Slice — Frontend Requirements

**Status: planning/specification document only. Contains zero frontend
source code.** Derived exclusively from the shipped, fully-tested
backend implementation (`src/jarvis/services/siren_service.py`,
`src/jarvis/infrastructure/api/routes/sirens.py`) and its authoritative
Logic Contract (`docs/M12_SECURITY_SIREN_ADVANCED_CONTROLS_LOGIC_
CONTRACT.md`), written after the backend's full regression, targeted
tests, and quality gates all passed. No frontend implementation
accompanies this file, and none is authorized by it.

## 1. Backend capability summary

**SHIPPED BACKEND CAPABILITY**: the existing `turn_siren_on`
capability (Task Group R) now accepts three optional parameters --
`tone`, `duration` (seconds), `volume_level` (`0.0`-`1.0`) -- Home
Assistant's own verbatim `siren.turn_on` parameters, externally
verified. No new endpoint, no new tool: `POST /sirens/{id}/turn_on`
and the `turn_siren_on` agent tool both gained an optional request
shape; every existing bare call continues to work byte-for-byte
unchanged.

## 2. Tone selector

**FRONTEND IMPLEMENTATION REQUIRED**: a tone field on the siren detail/
control UI. Because `tone` is genuinely device-specific (Home
Assistant's own documentation: *"you can use either the key or the
value from its list of available tones"*) and this slice deliberately
does not add `available_tones` to the persisted read model (§8), the
frontend has two reasonable choices, neither backend-mandated:
- A free-text field, with copy making clear the value is
  device-specific and unvalidated until sent; or
- A selector populated from a **separate, live** `GET .../{id}` call
  read directly by the frontend at the moment the control panel opens
  (not from this slice's own persisted state) -- a legitimate future
  backend addition (§15), not shipped here.

## 3. Duration input

**FRONTEND IMPLEMENTATION REQUIRED**: a numeric seconds field.
Backend validation: integer, non-negative (0 is valid and means
"a legitimate zero-second value," not an error), no enforced maximum
-- Home Assistant's own documentation defines none. The frontend
should not invent a maximum either; if a product decision later wants
one, it belongs in a future, separately-scoped change.

## 4. Volume control

**FRONTEND IMPLEMENTATION REQUIRED**: a slider or numeric input,
range `0.0`-`1.0` -- Home Assistant's own protocol-level range for
`volume_level` (0 = inaudible, 1 = maximum), identical to the range
this codebase's own Media Player volume control already uses.

## 5. Supported-tone handling

**BACKEND CAPABILITY AVAILABLE, partially**: the backend validates a
submitted `tone` against the device's own live-reported
`available_tones` **only when the device reports a non-empty list** --
permissive otherwise (never inventing a fixed global tone vocabulary).
A frontend that wants to warn a user *before* submitting an
unsupported tone would need its own live capability read (§2) --
this slice does not expose that as part of `get_siren_state`.
Submitting an unsupported tone (when the device *does* report a list)
returns a `400` with a `detail` naming the exact supported list (§7) --
render this message directly, it is already precise and actionable.

## 6. Unsupported-feature handling

**Important distinction, backend-verified**: a device that does not
support `DURATION`/`VOLUME_SET`/`TONES` **at all** (no capability
flag) does not error when sent one of these parameters -- Home
Assistant's own base platform silently filters an unsupported
parameter before it reaches the device integration. The frontend
should not present this as a failure; if the action otherwise
succeeds (`success: true`), treat it as a normal success, since
JARVIS itself cannot distinguish "ignored because unsupported" from
"applied" without a live capability read the backend does not
currently perform for duration/volume. Recommended copy near these
controls: "Not every siren supports every option -- unsupported
values are silently ignored by the device."

## 7. Validation errors

| Condition | HTTP | Frontend treatment |
|---|---|---|
| Empty/non-string tone | 400, `detail` names the field | Inline field error |
| Tone not in device's reported `available_tones` | 400, `detail` lists the supported tones | Inline field error, show the supported list from `detail` |
| Negative duration | 400, `detail` names the field | Inline field error |
| Non-integer duration | 400 | Inline field error |
| `volume_level` outside `0.0`-`1.0` | 400, `detail` names the field | Inline field error |
| Unknown device / non-siren device | 404 (`GET`) / 400 (`POST .../turn_on`) | Unchanged from the existing Siren contract -- stale client-side data |

## 8. Existing confirmation UX (unchanged)

**No new confirmation UX required.** `turn_siren_on` remains the same
confirmation-gated agent tool it already was -- a request now simply
shows the requested tone/duration/volume in the confirmation prompt
text, a direct readability improvement with no new UI to build. A
direct-REST "Turn On" button's own optional confirmation dialog
(already recommended, not mandated, by the original Siren Integration
Slice's own frontend requirements) may now also display the requested
tone/duration/volume if the frontend collects them before the call --
still a UX choice, not a backend requirement.

## 9. Limitation: no current-value read-back

**BACKEND CAPABILITY NOT AVAILABLE, permanently, not a gap.** Home
Assistant's own siren entity state exposes exactly one property
(`is_on`) -- there is no "last tone played," "last duration," or
"last volume" to read back, for any siren, from any integration. The
frontend must not render a "current tone" or "current volume" field
implying one exists, and must not persist the last-submitted values
client-side and present them as device state after a page reload --
that would misrepresent a UI cache as live device state.

## 10. API endpoints (unchanged shape, extended body)

| Endpoint | Method | Body |
|---|---|---|
| `/api/v1/sirens` | `GET` | — |
| `/api/v1/sirens/{device_id}` | `GET` | — |
| `/api/v1/sirens/{device_id}/turn_on` | `POST` | `{"tone"?: string, "duration"?: int, "volume_level"?: float}` -- all optional, absent body unchanged |
| `/api/v1/sirens/{device_id}/turn_off` | `POST` | — (no body, unchanged) |

## Summary classification

| Item | Classification |
|---|---|
| `POST .../turn_on` with optional `tone`/`duration`/`volume_level` body | SHIPPED BACKEND CAPABILITY |
| Agent tool `turn_siren_on` with the same three optional arguments | SHIPPED BACKEND CAPABILITY (agent-facing, not a frontend concern) |
| Tone selector, duration input, volume control, validation-error display, unsupported-feature messaging | FRONTEND IMPLEMENTATION REQUIRED (not started, not scoped beyond this document) |
| A live `available_tones` capability read exposed through `get_siren_state` | FRONTEND IMPLEMENTATION DEFERRED -- a legitimate future backend addition, not shipped by this slice |
| Any current-tone/duration/volume read-back | BACKEND CAPABILITY NOT AVAILABLE, permanently -- Home Assistant itself exposes none |
| Siren pattern/waveform control | BACKEND CAPABILITY NOT AVAILABLE -- no corresponding Home Assistant `SirenEntityFeature` exists at all |
