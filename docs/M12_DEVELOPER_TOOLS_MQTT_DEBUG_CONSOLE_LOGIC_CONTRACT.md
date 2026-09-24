# M12 Developer Tools — MQTT Debug Console — Logic Contract

Status: **Implemented this session** (Task Group W). Written following
a Phase 0 audit that resolved a real architectural question raised
during the Device Logs slice's own review: whether Aarya's multi-home
data model implies multiple simultaneously-live `MqttConnector`
instances (one per home), which would have forced a per-home or
per-connector-instance buffer design instead of a single global one.

## 1. Purpose

A read-only devtools endpoint answering "what is actually arriving
over MQTT right now?" — closing the still-unbuilt "MQTT Debug Console"
item named explicitly in `MASTER_ROADMAP.md`'s M12 Developer Tools
feature list. The primary use case is diagnosing why a new device
isn't showing up (is its HA Discovery config even reaching the broker
in the expected shape?) or why a state update isn't landing (is the
topic actually being published, and what does the raw payload say?).

## 2. Existing architecture — connector ownership

**Finding (resolves the multi-instance question left open after Device
Logs):** `ConnectivityService` is registered as `providers.Singleton`
in the DI container (`core/di/container.py:1386`) — exactly one
instance for the whole process. Its own `connect()`/`_require_connector()`
methods (re-read this session) cache at most **one connector instance
per `connector_type` string** in `self._connectors: dict[str,
IDeviceConnector]`:

```python
async def connect(self, connector_type: str, config: dict[str, Any] | None = None) -> None:
    connector = self._connectors.get(connector_type)
    if connector is None:
        connector = self._registry.create(connector_type, config)
        self._connectors[connector_type] = connector
    await connector.connect()
```

`connect()`'s own docstring confirms this is deliberate: "connecting an
already-connected type reconnects the existing instance rather than
leaking a second one." `ConnectorFactoryRegistry.create()` genuinely
does build a new instance on every call (confirmed by reading
`registry.py` directly) — but `ConnectivityService` only ever calls it
**once** per `connector_type`, caching the result. Multi-home support
(Smart Home Core's own first-class dimension) does not multiply
connector instances: every home's MQTT-connected devices share the
same one broker connection, distinguished only by their own
`external_id` within that shared connection — exactly the same way
`HomeAssistantConnector` already works for multi-home Home Assistant
setups.

**Conclusion: there is exactly one live `MqttConnector` at a time,
system-wide, or none.** The "per-home buffer" and "per-connector-
instance buffer" designs raised as open questions before this audit are
not live alternatives — they would be solving a problem this codebase's
actual connector-caching model does not have. A single, global buffer
is not a simplification made for convenience; it is the only model the
real ownership structure supports.

## 3. Architecture decision

**A bounded, in-memory buffer owned by `MqttConnector` itself**
(instance attribute, `collections.deque(maxlen=200)`), populated from
the single `_on_message` gmqtt callback — the one place every inbound
message already arrives, already wrapped in a "one bad message must
not kill the loop" `try`/`except` (confirmed by reading `mqtt.py`
directly, unchanged by this slice). Rejected alternatives:

- **A buffer inside `ConnectivityService`** — rejected. That service's
  own docstring is explicit: "it does not know or care whether a
  connector talks to Home Assistant, MQTT, or anything else." Owning
  an MQTT-specific message buffer there would put protocol-specific
  state in the one class this codebase deliberately keeps
  protocol-agnostic.
- **A buffer inside `DebugConsole`** — rejected. `DebugConsole`
  captures the application's own **log** stream (a loguru sink); an
  MQTT message is wire traffic that was never going to be logged at
  all (this connector logs almost nothing per-message, by design —
  only `_on_connect`/`_on_disconnect`/errors). Routing MQTT traffic
  through the logger just to let `DebugConsole` capture it would mean
  either logging every message (noisy, and a behavior change to a
  connector this project's own Phase 3 report already tuned) or adding
  an MQTT-specific method to a component whose entire value is being a
  generic log-line capture, not a protocol-specific one.
- **A new `core/devtools/` component** — rejected. Nothing here needs
  cross-cutting coordination (no `EventBus`, no shared state across
  multiple consumers); it is one connector's own private buffer, read
  by exactly one route.

**Chosen: the connector owns its own buffer, exposed through an
optional capability Protocol.** A new `@runtime_checkable`
`IConnectorDebugCapture` Protocol in `core/interfaces/connectivity.py`
(the ports file) declares `recent_messages(*, limit: int = 200) ->
tuple[ConnectorDebugMessage, ...]`. `MqttConnector` implements it
structurally (no inheritance, matching every other adapter in this
codebase). `routes/devtools.py` reaches it via `ConnectivityService.
get_connector("mqtt")` (a new, trivial, connector-agnostic accessor —
`self._connectors.get(connector_type)`, no new logic) plus an
`isinstance(connector, IConnectorDebugCapture)` check — never by
importing `MqttConnector` directly, preserving this router's own
existing "ports first" test guard
(`test_device_diagnostics_does_not_import_connectors_directly`, which
this slice's own test file extends). `HomeAssistantConnector` — a
stateless request/response REST client with nothing push-based to
buffer — simply does not implement the Protocol; the route treats that
identically to "no connector connected," never branching on connector
type.

## 4. Direction: inbound only

**Deliberately excludes `send_command`'s own outbound publish.** This
mirrors the Device Logs slice's own established reasoning exactly: a
device command's `payload` can carry a lock's PIN (`{"code": "1234"}`,
already seen in this codebase's own `send_command` tests), and
`send_command`'s wire-level publish call carries that exact payload,
JSON-encoded, in `mqtt.py`'s `build_command_envelope(...).to_json()`.
Capturing outbound traffic verbatim here would re-expose, through a new
endpoint, precisely what Device Logs' own Logic Contract decided must
never be logged. Building a safe redaction path for arbitrary outbound
command payloads (parsing the JARVIS-native envelope, redacting only
within its nested `payload` object) was evaluated and rejected as
disproportionate complexity for a devtools slice when the inbound-only
design already covers the dominant real debugging need — "is my device
announcing/reporting itself correctly over MQTT" — without ever
touching command payload data at all. `send_command` itself is
untouched by this slice.

## 5. Message model and capture point

```python
@dataclass(frozen=True, slots=True)
class ConnectorDebugMessage:
    at: datetime
    topic: str
    payload: str   # already sanitized + truncated, see §6
    qos: int
```

Captured in `MqttConnector._capture_debug_message`, called as the
**first** step of `_on_message` — before the existing topic-dispatch
`try`/`except` — so a message the routing logic cannot recognize
(logged today as "skipping unreadable message") is still visible in
the debug console; that is precisely the case a developer most needs
to see. The capture call itself is wrapped in its own
`contextlib.suppress(Exception)` at the call site: a capture bug must
never look like, or cause, a message-routing failure.

## 6. Sanitization and bounding

Two independent transforms, both applied before a message ever enters
the buffer (never applied lazily at read time, so nothing unsanitized
is ever held in memory):

1. **Truncation** — `payload.decode("utf-8", errors="replace")`, then
   capped at 2000 characters with a `"...(truncated)"` marker. Bounds
   worst-case buffer memory (200 messages × 2000 chars ≈ 400 KB) against
   an anomalous oversized retained message; ordinary HA discovery/state
   JSON is a few hundred bytes.
2. **Text-level key redaction** — a regex,
   `_SENSITIVE_JSON_STRING_VALUE`, matches the common compact-JSON
   `"key": "value"` shape where `key` contains `token`/`password`/
   `secret`/`credential`/`api_key`/`auth` (case-insensitive, mirroring
   `routes/devtools.py`'s own `_SENSITIVE_ATTRIBUTE_KEY_SUBSTRINGS` from
   the Device Diagnostics slice) and replaces the **value** with
   `"<redacted>"`. Operates on raw text, not a parsed dict — a captured
   message is wire text here, not yet a JSON object, and not every
   payload is even JSON (an HA availability payload can be the bare
   word `"online"`).

**Never touches connector credentials.** `MqttConnector`'s own
`_username`/`_password`/`_host`/`_port` fields are configuration the
connector holds privately; nothing in this capability reads them —
only the topic/payload/qos of each inbound wire message is ever
captured. There is no code path by which a broker credential could
reach `ConnectorDebugMessage`.

## 7. REST endpoint

```
GET /api/v1/devtools/mqtt/messages?limit=200
```

Lives in `routes/devtools.py`, directly after Device Logs (grouping
with the other connectivity-adjacent devtools capability), before
Device Simulator. No `home_id` or `connector_id` path/query parameter —
§2 establishes there is exactly one live MQTT connector, never one per
home, so a scoping parameter would name a distinction the architecture
does not have.

Response envelope matches every other devtools route: `{data, meta}`,
`data` = a tuple of `{at, topic, payload, qos}`, `meta = {"connected":
bool, "count": len(data)}`. `connected: false` covers both "no MQTT
connector has ever been created" and "the MQTT connector type is
registered but not currently connected" (both collapse to
`ConnectivityService.get_connector("mqtt") is None` — `_connectors` is
only ever populated by a successful `connect()` call and removed on
`disconnect()`). `connected: true` with an empty `data` list is a
distinct, valid state: connected, but no message has arrived yet.

No `PermissionModel` gate — session auth only, matching every other
capability in this router. Reasoned, not inherited by default: this is
read-only, carries no credential (§6), and its content (recent
device-reported state/discovery traffic) is the same class of data
Device Diagnostics' own live-read already exposes for known devices,
here surfaced pre-registration as well — the primary reason this
slice's own debugging value exists at all (seeing a device *before* it
is paired).

## 8. Error semantics

| Condition | Behavior |
|---|---|
| No MQTT connector connected | 200, `data: []`, `meta.connected: false` |
| Connected, no messages yet | 200, `data: []`, `meta.connected: true`, `meta.count: 0` |
| Connected, connector doesn't implement `IConnectorDebugCapture` (only possible today via a test double registered under the `"mqtt"` type) | 200, `data: []`, `meta.connected: false` — treated identically to "no connector," since the capability, not the connector's mere presence, is what this route reports |
| Malformed request | N/A — no path parameter, one optional query int, ordinary FastAPI handling |
| Unexpected internal failure | Propagates as a genuine 500, matching every other route in this codebase |

## 9. Agent tool decision

**None.** No conversational use case exists for "show me the raw MQTT
wire traffic" — matches Device Diagnostics/Device Simulator/Device
Logs' identical reasoning.

## 10. EventBus / Scheduler / Analytics / Memory / database / schema

**None of the six.** The capture point is a plain method call inside
`MqttConnector`'s own existing synchronous callback; the route makes
one call (`ConnectivityService.get_connector`) plus one method call on
the result. No new table, column, or migration; no `DEVICE_TYPES`/
`CONNECTOR_TYPES` change.

## 11. Lifecycle behavior

- **Connect** — buffer starts empty (a fresh `MqttConnector` instance
  per `connect()` call that creates one; see §2 — the same instance is
  reused across gmqtt's own automatic reconnects, so the buffer is
  *not* cleared on a transient reconnect, matching this connector's own
  established "reconnection is silent, no special-cased branch" design
  for `_on_connect`).
- **Disconnect** — `ConnectivityService.disconnect()` deletes the
  connector from `self._connectors` entirely (confirmed by reading
  `disconnect()`); the next `get_connector("mqtt")` call returns `None`
  and the route reports `connected: false`, `data: []`. The buffer
  itself is garbage-collected with the discarded instance — no
  explicit clear needed, no stale data could leak into a *later*,
  different connector instance since each one owns its own `deque`.
- **Reconnect (automatic, gmqtt-driven)** — same instance, same
  buffer; messages continue accumulating across the gap with no
  special handling required.
- **Replacement (a fresh `connect()` after a full `disconnect()`)** —
  a genuinely new `MqttConnector` instance with a genuinely new, empty
  buffer; the old buffer is unreachable, never merged or carried
  forward. This is correct: the debug console should never show a
  since-disconnected connector's history under a new session.

## 12. Risks

- The redaction regex (§6) is a text-level heuristic, not a formal
  schema — a differently-shaped sensitive field (a numeric value, an
  array, a key spelled outside the matched substrings) could pass
  through unredacted. Mitigated, not eliminated, exactly as Device
  Diagnostics' own Logic Contract documented the identical limitation
  for its key-based dict redaction. The one structural guarantee that
  does hold unconditionally: connector credentials themselves are never
  read by this capability at all (§6), regardless of the regex's
  coverage.
- Inbound-only is a real, visible gap for a developer specifically
  debugging an outbound command delivery problem ("did my command
  actually reach the broker?") — accepted deliberately (§4) rather than
  building outbound redaction; documented, not hidden. A future slice
  could revisit this if a safe outbound-payload redaction design is
  worked out and given its own review.

## 13. Test strategy

`MqttConnector` (unit, `test_mqtt_connector.py`): an inbound message on
a recognized topic is captured; an unrecognized/malformed message is
still captured even though routing logs it as unreadable; capture
order is most-recent-first; `limit` is respected; the buffer evicts the
oldest entry once `DEFAULT_DEBUG_MESSAGE_BUFFER_SIZE` is exceeded; a
payload longer than 2000 characters is truncated with the marker; a
payload containing a `"password"`/`"token"`/etc. JSON string value is
redacted while an ordinary key passes through verbatim; outbound
`send_command` traffic never appears in `recent_messages()`.

Route (integration, `test_m12_devtools_mqtt_debug_console_route.py`,
real FastAPI app + a real local test MQTT broker matching
`test_mqtt_connector.py`'s own established fixture — never a mocked
client, per this project's testing conventions): no connector connected
→ `connected: false`, empty `data`; connected with no messages yet →
`connected: true`, empty `data`; a real published message surfaces in
the response; `limit` is respected; session-only auth boundary (no
grant needed); architecture guards (`MqttConnector`/
`HomeAssistantConnector`/`ConnectorCredentialStore` never imported by
`routes/devtools.py`, no agent tool named for this capability, no
`EventBus`/`Scheduler`/`Analytics`/`MemoryService` reference).

## 14. Non-goals

MQTT Discovery/State/Availability protocol changes (none — zero
`CONNECTOR_TYPES`/topic-vocabulary changes), outbound command capture
(§4), per-home or per-connector-instance scoping (§2 — architecturally
not applicable), a write/clear endpoint (`DebugConsole`'s own `DELETE
/devtools/logs` has no MQTT equivalent here — the buffer self-evicts
via its bounded size, and there is no operational need to clear it
early), historical persistence beyond the in-memory buffer (restarting
the process, or a full disconnect/reconnect cycle, loses history — same
posture as `DebugConsole` itself), and Event Viewer/Automation Tester
(both remain separately unbuilt, unchanged by this slice).

## 15. Acceptance criteria

- `GET /api/v1/devtools/mqtt/messages` implemented directly in
  `routes/devtools.py`, reached only through `IConnectorDebugCapture`
  + `ConnectivityService.get_connector` — no direct `MqttConnector`
  import in the route module, pinned by a test.
- `MqttConnector.send_command`'s own outbound publish is never
  captured — pinned by a test.
- A payload containing a sensitive-shaped JSON key is redacted before
  ever entering the buffer — pinned by a test.
- Buffer capacity is bounded and evicts oldest-first — pinned by a
  test.
- No connector, or a connector without the capability → `connected:
  false`, never a 500.
- No `PermissionModel` gate — session auth only.
- No agent tool, no database/schema change, no `EventBus`/Scheduler/
  Analytics/`MemoryService` reference.
- Zero frontend file touched.
