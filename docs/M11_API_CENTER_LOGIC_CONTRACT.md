# M11 API Center — Logic Contract

**Status:** Draft, implementation-ready pending Task Group kickoff. Documentation only — no
source code, tests, migrations, or roadmap files were touched to produce this document.

**Authoritative inputs:** [`M11_API_CENTER_ARCHITECTURE_DECISIONS.md`](M11_API_CENTER_ARCHITECTURE_DECISIONS.md)
(the ADR) and [`M11_API_CENTER_SCOPE_MATRIX.md`](M11_API_CENTER_SCOPE_MATRIX.md). Every decision
below traces to a numbered ADR section; none are reopened or reinterpreted here. Where the
existing codebase constrains a choice, the constraint is cited by file:line, not assumed.

---

## 1. Purpose

Give JARVIS a real lifecycle-management layer for **catalogued external vendor
integrations** — activation, registration, connection state, health, user-triggered connection
testing, scoped discovery, and narrowly-scoped failover/runtime-switching — extending the
existing `core/integrations/` + `core/mcp/providers/` engine (Google Workspace today, 11
integrations / 65 operations) rather than replacing or duplicating it. This closes the 10-item
"API Center Architecture" scope declared "Planning only" at `MASTER_ROADMAP.md:2947-2955`.

## 2. Scope

In scope: real (non-mock) validation for M5's `ApiCenterService`; a new user-triggered Connection
Test capability for catalogued integrations; a dedicated M11 health-collector surface; discovery
of catalogue entries (discover + register only); narrowly-scoped runtime switching and failover
among *already-connected* catalogued-integration credentials; REST/event/observability surfaces
for all of the above.

## 3. Non-goals

This Logic Contract explicitly does **not** cover: LLM/voice/vision provider routing or
selection, AI cost optimization, hardware-aware AI routing, `ILLMProvider` adapter selection, AI
model hot-swap, or any AI provider calibration (§26). It does not migrate or restructure M5's
`ApiCenterService` (ADR §2, §12 — no migration is planned). It does not add a REST route for M5
(out of scope, undecided — ADR does not resolve this and this contract does not either; see §28).
It does not build real multi-vendor failover content — only the mechanism, because exactly one
vendor family is catalogued today (ADR §5, carried into §15 below).

## 4. Architecture boundary

M11 owns the **Integration/Vendor Plane**: `core/integrations/` (gateway, provider, catalogue,
models, per-vendor spec modules) and the parts of `core/mcp/providers/`+`core/mcp/auth/` that
back it. It extends these; it introduces no parallel registry, no parallel credential store, no
parallel health channel (ADR §8, §9; Phase 0 audit's duplication search, zero competing
implementations found).

## 5. M5/M11 coexistence

Binding, per ADR §2 (Option C): **M5 `ApiCenterService`** (`services/api_center_service.py`)
remains authoritative for generic/uncatalogued credentials — including `ApiCategory.LLM` entries
(`domain/api_center/models.py:34`) — permanently, with no migration path (ADR §12). **M11**
becomes authoritative for catalogued, `IntegrationSpec`-backed vendor integrations. The only
change this contract makes to M5 is swapping its validator default (§12). No `ApiDefinition` row
ever becomes a `Credential` row or vice versa.

| | M5 (unchanged scope) | M11 (this contract's scope) |
|---|---|---|
| Storage | `api_center.json`, `ApiCenterService` | `mcp_credentials.json`, `CredentialStore` |
| Unit | `ApiDefinition` (flat, any HTTP API) | `RestIntegrationProvider` + `IntegrationSpec` (typed operations) |
| Reachability | Desktop only, no REST | REST-first (`infrastructure/api/routes/integrations.py`) |
| Categories | LLM, SEARCH, WEATHER, MAPPING, SMART_HOME, VISION_OCR, PERFORMANCE, DEVELOPER_TOOLS, CUSTOM | Vendor integrations only (Google Workspace today) |

## 6. Component responsibilities

| Responsibility | Owning component | New code? |
|---|---|---|
| Provider registration/lifecycle | `MCPProviderManager` (`core/mcp/providers/manager.py:54`, `.install()` 79, `.connect()` 149, `.disconnect()` 176) | No — reused as-is |
| Provider registry (in-memory) | `MCPProviderRegistry` (`core/mcp/providers/registry.py:75`) | No — reused as-is |
| Credential storage/encryption | `CredentialStore` (`core/mcp/auth/store.py:65`) | No — reused as-is |
| Dual permission gate | `MCPAuthManager.authorize_capability` (`core/mcp/auth/manager.py:383-420`) | No — reused as-is |
| Egress, retry, cache | `ApiGateway` (`core/integrations/gateway.py:258`) | No — reused as-is |
| Operation execution | `RestIntegrationProvider` (`core/integrations/provider.py:184`) | No — reused as-is |
| Catalogue lookup | `catalogue.py:build_spec/describe_catalogue` | No — reused as-is |
| Install/connect/invoke orchestration | `IntegrationService` (`services/integration_service.py:89`) | Extended — new methods for connection test, discovery listing, switch, failover (§16) |
| Passive periodic health | `HealthMonitor` (`core/lifecycle/health_monitor.py:55`) via `register_collector` | Extended — new `integrations_health` collector alongside the existing `mcp` one |
| Built-in service visibility | `ServiceManager.snapshot()` (`core/lifecycle/service_manager.py:249`) | Not touched — out of this contract's scope (built-ins are not vendor integrations) |
| Real credential validation | New: replaces `MockApiValidator` as `ApiCenterService`'s default (§12) | New, small |
| Connection Test | New: extends `IntegrationService` (§11) | New |
| Discovery listing | New: extends `IntegrationService`, reads `catalogue.py` (§9) | New |
| Runtime Switching | New: extends `IntegrationService` (§14) | New |
| Failover | New: extends `IntegrationService` (§15) | New |

## 7. Data model

All new types are additions, not replacements, and follow existing conventions (frozen
dataclasses, `as_dict()`/public-dict serializers matching `Credential`'s pattern at
`core/mcp/auth/credentials.py:225-260`).

```python
# core/integrations/testing.py (new)
@dataclass(frozen=True, slots=True)
class ConnectionTestResult:
    integration_id: str
    outcome: str            # "success" | "failure" — see §21 for error_code vocabulary
    error_code: str = ""    # empty when outcome == "success"
    status_code: int | None = None   # vendor HTTP status, when one was received
    latency_ms: float | None = None
    message: str = ""       # human-readable, never includes secret values
    tested_at: datetime = field(default_factory=lambda: datetime.now(UTC))

# core/integrations/switching.py (new)
@dataclass(frozen=True, slots=True)
class SwitchResult:
    capability: str          # e.g. "mail" — the logical role being switched
    from_integration_id: str
    to_integration_id: str
    outcome: str              # "success" | "failure"
    error_code: str = ""
    requested_at: datetime = field(default_factory=lambda: datetime.now(UTC))

# core/integrations/failover.py (new)
@dataclass(frozen=True, slots=True)
class FailoverAttempt:
    capability: str
    failed_integration_id: str
    candidate_integration_id: str | None   # None when no candidate exists (§15)
    outcome: str              # "recovered" | "no_candidate" | "failed"
    attempt: int
    error_code: str = ""
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
```

No changes to `IntegrationSpec`/`OperationSpec` (`core/integrations/models.py`) — discovery reads
the existing shape as-is (§9). No changes to `Credential`/`CredentialStore` (§8).

## 8. Credential model

Authoritative store: `CredentialStore` (`core/mcp/auth/store.py:65`), unchanged. M11 introduces
**no new credential fields and no new store**. Connection Testing, Switching, and Failover all
read credentials exclusively through the existing `MCPAuthManager`/`RestIntegrationProvider`
path — never a second lookup. Access pattern: `RestIntegrationProvider.invoke()`
(`core/integrations/provider.py:184`) already gates every outbound call through
`MCPAuthManager.authorize_capability` (§18); the new Connection Test capability reuses the exact
same gate before making its request (§11). Rotation/deletion/revocation are unchanged —
`MCPAuthManager.revoke()` (`manager.py:229`) remains the only revocation path.

## 9. Discovery model

Per ADR §6: **discover + register only.** Never install, never auto-activate, never auto-connect.

- **Source:** `core/integrations/catalogue.py`'s `AVAILABLE_SPECS` (`catalogue.py:41`) — a static,
  code-defined dict. Discovery is a read of this dict via `describe_catalogue()`
  (`catalogue.py`, already the source `IntegrationService.catalogue()` uses,
  `integration_service.py:115-118`) — **no new discovery source**, this *is* discovery; the new
  work is exposing "what's discoverable but not yet installed" as a distinct, explicit view
  rather than the flat catalogue list that exists today.
- **Metadata surfaced:** `integration_id`, `name`, `vendor`, `description`, `version`,
  `required_permissions`, `required_scopes`, `operations` — all already on `IntegrationSpec`
  (`models.py:427-442`, `as_dict()`). No new metadata schema.
- **Identifier:** `integration_id` (existing, `_NAME_RE`-validated at `models.py:369-373`).
- **Version:** `IntegrationSpec.version` (`models.py:319`, default `"1.0.0"`) — already present;
  no compatibility-checking logic exists or is added (ADR §9 gap 3: not modeled beyond the raw
  string; adding real compatibility semantics is out of scope here).
- **Capabilities/permissions:** `IntegrationSpec.required_permissions`/`required_scopes`
  (`models.py:352-360`) — already computed; discovery surfaces them, does not recompute them.
- **Registration semantics:** "registered" means present in the discovery listing's result set —
  it does **not** mean `MCPProviderRegistry`-registered (that only happens on `install()`,
  `integration_service.py:130-159`). This is a deliberate terminology split: catalogue-registered
  (discoverable) vs. provider-registered (installed). The REST/event surfaces (§16, §17) must use
  distinct terms to avoid conflating the two.
- **Duplicate handling:** `catalogue.py`'s `AVAILABLE_SPECS` is a `dict` keyed by
  `integration_id` — duplicates are structurally impossible (a second entry overwrites, never
  coexists). No new duplicate-detection logic needed.
- **Unavailable adapter handling:** an entry with `availability_note` set (`models.py:330`,
  e.g. "cannot work on ordinary accounts") is still discoverable but flagged — surfaced verbatim,
  never filtered out silently (a caller must be able to see *why* something isn't usable).
- **Invalid metadata:** `IntegrationSpec.validate()` (`models.py:365-398`) already raises
  `IntegrationError` at catalogue build time — an invalid entry cannot reach discovery at all,
  because `build_spec()`/`describe_catalogue()` would already have failed constructing it. No new
  validation layer needed.
- **Version incompatibility:** `BLOCKED — REQUIRES ARCHITECTURE DECISION`. No compatibility
  contract (e.g. against a minimum engine version) exists anywhere in the codebase for
  `IntegrationSpec.version` to be checked against. This cannot be resolved from the current
  architecture without inventing behavior — deferred to whichever Task Group first needs it, not
  decided here.

## 10. Registration model

"Registration" in M11 has exactly two meanings, and this contract keeps them distinct rather than
merging them (a merge would itself create the ambiguity the ADR eliminated):
1. **Catalogue registration** — an `IntegrationSpec` existing in `AVAILABLE_SPECS`. Build-time,
   code-defined, not a runtime action (§9).
2. **Provider registration** — `IntegrationService.install()` → `MCPProviderManager.install()`
   (`manager.py:79`) → `MCPProviderRegistry` entry. Runtime, user-triggered, already fully
   implemented and unchanged by this contract.

No new registration mechanism is introduced. Discovery (§9) surfaces #1; installation remains
exactly what `POST /integrations` already does today (`infrastructure/api/routes/integrations.py:
119-136`).

## 11. Connection model

**Health** and **Connection Test** are formally distinct (ADR §4), restated here as the binding
contract:

| | Health | Connection Test |
|---|---|---|
| Purpose | Cheap, continuous "probably fine" signal | Authoritative, on-demand "actually fine right now" |
| Trigger | Automatic, every 15s (`HealthMonitor.DEFAULT_POLL_INTERVAL_SECONDS`, `health_monitor.py:52`) | Explicit user/API action only |
| Network behavior | **Local-only** — `RestIntegrationProvider.health()` never calls the vendor (`provider.py:255-261`), preserved unchanged | **Real vendor request**, deliberately overriding the local-only convention |
| Timeout | N/A (no network call) | Bounded — reuses `ApiGateway`'s existing `DEFAULT_TIMEOUT_SECONDS = 30.0` (`gateway.py:61`) as the ceiling; a Connection Test additionally caps at a shorter caller-facing budget (default 10s) so a hung vendor cannot stall a synchronous user action for the full 30s |
| Caching | Implicit — one snapshot per poll tick (`health_monitor.py:125-153`) | None — every Connection Test is a fresh call, never served from `ApiGateway`'s cache (mirrors the existing mutating-call-never-cached rule, `gateway.py`) |
| Failure semantics | Degrades one collector entry, never the whole snapshot (`health_monitor.py:148-152`) | Returns a structured `ConnectionTestResult` (§7) — never raises past the service boundary; `_as_service_error()` (`integration_service.py:62-86`) pattern applies |
| Audit | Flows into existing `HealthUpdatedEvent` (`health_monitor.py:6-8`) | New `IntegrationConnectionTestEvent` (§17) |

**Inputs (Connection Test):** `integration_id` (required), `operation` (optional — which
catalogued operation to probe; defaults to a lightweight read-category operation if the spec
declares one, otherwise the spec's own auth validation endpoint if one exists), `timeout_seconds`
(optional, capped at the 10s default above).

**Outputs:** `ConnectionTestResult` (§7) — `outcome`, `error_code`, `status_code`, `latency_ms`,
`message`.

**Failure categories:** enumerated in §21 (Error taxonomy), shared with Discovery/Switching/
Failover rather than a separate vocabulary per feature.

## 12. Validation model

Binding per ADR §3: `MockApiValidator` is **superseded as the production default**, not deleted.

- **Production path:** `ApiCenterService.validate()`/`validate_all()`
  (`api_center_service.py:225-235`) default to a new real validator (name TBD at
  implementation time — this contract fixes behavior, not the class name) that makes a bounded,
  real HTTP request appropriate to `ApiDefinition.auth_type`
  (`domain/api_center/models.py:61`) — e.g. an authenticated `GET`/`HEAD` against `base_url`, or
  the vendor's documented identity endpoint where the built-in template names one.
- **Test path:** the real validator is tested exclusively against a real local `aiohttp`
  fake-vendor server (§22) — never `unittest.mock`.
- **Validator interface:** unchanged signature — `async def validate(self, api: ApiDefinition) ->
  ApiValidationResult` (matches `MockApiValidator.validate`, `features/api_center/validator.py:
  25`) — so `ApiCenterService.__init__`'s `validator` parameter (`api_center_service.py:44-53`)
  needs no call-site changes beyond the default.
- **Timeout:** bounded, short (same 10s default as §11's Connection Test, for consistency across
  the codebase's two validation surfaces).
- **Failure handling:** maps to `ApiHealthStatus` (`domain/api_center/models.py:45-51`) —
  `AUTH_FAILED`, `NETWORK_ERROR`, `INVALID_KEY`, `DISABLED` — the enum already exists and already
  covers every category the real validator needs; **no new status enum required**.
- **Authentication failure / network failure / malformed response / unsupported vendor / invalid
  credentials:** all map onto the existing `ApiHealthStatus` values above; "unsupported vendor"
  (an `auth_type`/`base_url` combination the real validator cannot probe meaningfully) returns
  `ApiHealthStatus.UNKNOWN` with a message explaining why, rather than fabricating a result.
- **Audit behavior:** `ApiCenterService.validate()` already persists `last_health`/
  `last_response_time_ms` (`api_center_service.py:228-230`) — unchanged. No response body or
  request header is ever logged (matches the redaction discipline already used across
  `core/integrations/`).
- **Secret-redaction:** `ApiDefinition`'s secret fields are already Fernet-encrypted at rest
  (`api_center_service.py:93-103`); the real validator receives the decrypted value only in
  memory, for the duration of the one outbound call, and never logs or returns it — same
  discipline as `GatewayRequest.audit()` (`core/integrations/gateway.py:114-124`).
- **`MockApiValidator`'s remaining role:** kept for tests (`tests/unit/test_api_center_service.py`
  pattern) and behind an explicit Developer-Mode opt-in flag (new, small addition to
  `Settings` — exact field name is an implementation detail, not an architectural one). It is
  never the silent default again (Acceptance Criterion, §25).

## 13. Health model

Fully specified in §11's table. Implementation surface: a new `register_collector("integrations",
...)` call (mirroring the existing `mcp` collector wired in `app.py:485-511`) that iterates
`MCPProviderManager.collect_health()` (`manager.py:281`) filtered to catalogued-integration
provider ids — **not** a new health mechanism, a new named view over the existing one. No health
history is stored — `HealthMonitor` itself keeps no history today (`health_monitor.py` — every
`snapshot()` call is a fresh read), and this contract does not add one; "get health history" from
the user's illustrative REST list (§16) is therefore marked not-applicable rather than built.

## 14. Runtime switching model — exact M11 scope

Binding per ADR §5, restated as a contract:

- **Meaning:** switching which *connected, catalogued integration* handles a logical capability
  (e.g. "mail") — never `ILLMProvider`/model/voice/vision switching.
- **Trigger:** user-initiated only. No automatic switching in this contract's scope.
- **Precondition:** both the current and target integration must already be connected
  (`Credential.status(...) == ACTIVE` or `EXPIRING`, `core/mcp/auth/credentials.py:171-185`) —
  a switch never triggers a new OAuth flow as a side effect.
- **Authorization:** re-runs `MCPAuthManager.authorize_capability` (`manager.py:383-420`) for the
  *target* integration before completing the switch — no bypass.
- **Failure handling:** rejected synchronously with a structured `SwitchResult` (§7,
  `outcome="failure"`) if the target isn't connected/healthy; **never** silently falls through to
  a third candidate (that would blur into Failover, §15 — a deliberately separate concept).
- **State preservation:** in-flight calls already dispatched to the previous integration
  complete against it; only calls issued after the switch use the new target.
- **Reversibility:** a switch back to the original integration is just another switch request —
  no special "undo" mechanism, because nothing is destroyed by switching (both credentials remain
  connected).
- **Audit:** `IntegrationSwitchEvent` (§17).
- **Present real-world applicability:** exactly **one** vendor family (Google Workspace) is
  catalogued today, so this mechanism has no real second target to switch to at ship time (ADR
  §5). The mechanism is contracted and buildable now; its acceptance criteria (§25) cannot claim
  a real switch between two different vendors until a second one exists in the catalogue — this
  is a catalogue-growth dependency, not a code dependency (§24).

## 15. Failover model

Binding, mirroring §14's constraint: vendor-integration failover only, never LLM/model/voice/
vision failover (explicitly excluding `FallbackLLMProvider`,
`infrastructure/llm/fallback_provider.py`, which is a different, frozen-adjacent mechanism this
contract does not touch or extend).

- **Failover condition:** a `GatewayError` (`core/integrations/gateway.py:74-85`) with
  `retryable=True` persisting past the gateway's own retry budget (`RETRYABLE_STATUSES =
  {429, 500, 502, 503, 504}`, `gateway.py:59`, `DEFAULT_MAX_ATTEMPTS = 3`, `gateway.py:62`) — i.e.
  failover is a *second-order* response to something the gateway already tried and gave up on,
  never a replacement for the gateway's own retry logic.
- **Retry/timeout/backoff at the failover layer:** none beyond what `ApiGateway` already does
  (`DEFAULT_BACKOFF_SECONDS = 0.5`, `Retry-After` honored up to `MAX_HONOURED_RETRY_AFTER_SECONDS
  = 60.0`, `gateway.py:63,71`) — failover triggers *after* the gateway exhausts its own attempts,
  it does not duplicate or race against them.
- **Retryable vs. non-retryable:** exactly `GatewayError.retryable` (`gateway.py:82-85`) — reused
  as-is, not reinvented.
- **Authorization failure / credential failure:** `GatewayError` with `status_code in {401, 403}`
  or an `MCPAuthError` from `authorize_capability` failing — **not retryable, not a failover
  condition** (switching to a different integration doesn't fix a bad credential on this one; the
  correct response is surfacing the auth failure, not silently trying somewhere else).
- **Vendor outage:** a persisting `retryable=True` `GatewayError` — the one real failover
  condition.
- **Maximum attempts (at the failover layer):** exactly one candidate switch attempt per failed
  call — failover does not chain across more than one alternate, consistent with §14's "never
  silently falls through to a third candidate."
- **Audit:** `IntegrationFailoverEvent` (§17), fired even when `candidate_integration_id is None`
  (§7's `FailoverAttempt.outcome = "no_candidate"`) — a failed failover attempt (because nothing
  exists to fail over to) must be visible, not silently absorbed.
- **Rollback:** not applicable — failover selects a *different already-connected* integration
  for the *next* call; it never mutates or rolls back the failed one's state.
- **User visibility:** surfaced via the same event (above) and, where a REST caller is
  synchronously waiting, in the response of whatever call triggered the failover.
- **Binding constraint, restated:** per the user's own instruction and ADR §5's finding, this
  contract does **not** implement failover for a vendor category where no valid alternate exists
  — today, that's every category (one vendor family only). The mechanism and its event/audit
  contract are specified now; real failover behavior has no acceptance criterion requiring a live
  second vendor (§25), matching §14's treatment of the same constraint.

## 16. REST API contract

All new routes extend the existing `infrastructure/api/routes/integrations.py` router
(`APIRouter(tags=["integrations"], dependencies=[Depends(get_current_session)])`,
`integrations.py:44`) — same session auth, same `{data, meta}` `Envelope` convention
(`integrations.py:90-95` pattern), same `ServiceError` → 400 translation (`_bad_request`,
`integrations.py:80-84`). **No duplicate routes** — every existing route listed in the Phase 0
audit (catalogue, install, status, connect, disconnect, uninstall, oauth authorize/callback,
revoke, invoke, preview, search, gateway/stats) is reused unchanged.

| Method | Path | Auth | Request | Response | Notes |
|---|---|---|---|---|---|
| GET | `/integrations/discoverable` | Session | — | `Envelope[list[dict]]` (catalogue entries not yet installed) | New. Filters `catalogue()` (existing) by `not in installed_ids()` (existing) — no new data source |
| POST | `/integrations/{id}/test-connection` | Session | `{operation?: str, timeout_seconds?: float}` | `Envelope[ConnectionTestResult]` | New. §11 |
| GET | `/integrations/{id}/health` | Session | — | `Envelope[dict]` (this integration's entry from the new `integrations` health collector, §13) | New, thin — reuses `HealthMonitor.snapshot()` |
| ~~GET `/integrations/{id}/health/history`~~ | — | — | — | — | **Not built** — no history is stored anywhere in `HealthMonitor` (§13); adding one is out of this contract's scope |
| POST | `/integrations/switch` | Session | `{capability: str, to_integration_id: str}` | `Envelope[SwitchResult]` | New. §14 |
| GET | `/integrations/failover/history` | Session | `?capability=` | `Envelope[list[FailoverAttempt]]` | New, in-memory only (bounded ring buffer, e.g. last 50) — not persisted, since no persistence layer exists for this today and inventing one is out of scope |

Idempotency: `test-connection` and `/switch` are **not** idempotent in the retry-safe sense (each
call may have a side effect worth auditing) — callers must not blindly retry on timeout; this
matches the existing `invoke` route's posture (mutating operations are never auto-retried,
`gateway.py`'s `MUTATING_METHODS` convention, `models.py:70`). Timeout behavior: every new route
uses the bounded timeouts specified in §11/§12 (≤10s caller-facing default) — never the
unbounded default.

**Why no new discovery-install/activate route:** per §9, discovery is discover+register only;
installing a discovered integration is already `POST /integrations` (existing, unchanged).

## 17. Event contract

The codebase's established convention (confirmed at `core/events/events.py:339-380`) is **one
event class per lifecycle domain, carrying an `action` field**, not one class per transition —
`MCPProviderStateChangedEvent` and `MCPAuthStateChangedEvent` both do this deliberately (their
own docstrings: "matching the shape... already established"). This contract follows that
convention rather than the user-request's illustrative 15-class list, and maps every illustrative
name onto the consolidated set below (nothing in the illustrative list is dropped — each is
represented as an `action` value):

| New event class | `action` values | Replaces illustrative names |
|---|---|---|
| `IntegrationDiscoveryEvent` | `discovered`, `registered` | IntegrationDiscovered, IntegrationRegistered |
| `IntegrationConnectionTestEvent` | `started`, `completed`, `failed` | ConnectionTestStarted/Completed/Failed |
| `IntegrationSwitchEvent` | `requested`, `completed`, `failed` | IntegrationSwitchRequested/Completed/Failed |
| `IntegrationFailoverEvent` | `started`, `completed`, `failed`, `no_candidate` | IntegrationFailoverStarted/Completed/Failed |

**Reused, not duplicated** (per the instruction "if an existing event already satisfies the
requirement, reuse it"):
- `IntegrationActivated`/`Deactivated`/`Connected`/`Disconnected` → already
  `MCPProviderStateChangedEvent` (`events.py:339-354`, `action` ∈ {"connected", "disconnected",
  ...}) — integrations are MCP providers, so `IntegrationService.connect()`/`disconnect()`
  already flow through this event today (`integration_service.py:283-307` calls
  `self._providers.connect/disconnect`). **No new event needed.**
- `IntegrationHealthChanged` → already the periodic `HealthUpdatedEvent`
  (`health_monitor.py:6-8,155-157`), which will include the new `integrations` collector's output
  (§13) in its existing snapshot. **No new event needed** — adding one would be exactly the kind
  of second notification path `IntegrationCallCompletedEvent`'s own docstring warns against
  (`events.py:811-816`: "a third event for the same transitions would be a second notification
  path for one thing happening").

Per-event fields (all four new classes): `integration_id` (or `capability` for Switch/Failover),
`action`, `detail` (human-readable, matching `MCPAuthStateChangedEvent`'s "carries no secret"
discipline, `events.py:369-372`), plus event-specific fields from §7's dataclasses. Every event
gets the base `Event` class's existing `event_id`/`timestamp`/correlation fields (whatever `Event`
already provides — unchanged, not redefined here). **Sensitive fields:** none — no request/
response body, no header, no credential value in any of the four new event payloads, matching
`IntegrationCallCompletedEvent`'s existing posture (`events.py:803-809`).

## 18. Security model

- **Authentication:** every new route sits behind `Depends(get_current_session)`
  (`integrations.py:44`) — same as all existing integration routes. No new auth mechanism.
- **Authorization:** every new capability that reaches the vendor (Connection Test, the
  post-switch first call, a failover attempt) re-runs `MCPAuthManager.authorize_capability`
  (`manager.py:383-420`) — the same dual gate (JARVIS permission + vendor scope) every existing
  `invoke()` call already passes through (`provider.py:202-209`). No new permission model.
- **Credential access:** unchanged — routed exclusively through `MCPAuthManager`/`CredentialStore`
  (§8). No new component ever reads `access_token`/`refresh_token` directly.
- **Rate limits / abuse protection (Connection Test, Discovery, Failover):**
  `BLOCKED — REQUIRES ARCHITECTURE DECISION`. No rate-limiting layer exists anywhere in
  `infrastructure/api/routes/` today (confirmed: none of the existing integration routes apply
  one) — this contract cannot invent a first one without a broader decision about where
  API-wide rate limiting belongs (a cross-cutting concern, not an M11-specific one). Flagged, not
  guessed.
- **Runtime-switch authorization:** covered above (re-run `authorize_capability` against the
  target). No additional privilege tier is introduced.
- **M14 dependency:** confirmed, per ADR §11 and Phase 0 audit §7 — **not required.** The existing
  Fernet-based `CredentialStore` is adequate for everything in this contract.

## 19. Audit model

Every privileged action in this contract (Connection Test, Switch, Failover, Discovery
registration) publishes its corresponding event (§17) — this **is** the audit trail, matching the
existing pattern where `IntegrationCallCompletedEvent` is the audit record for `invoke()`
(`integration_service.py:323-329`) rather than a separate audit log. No new audit-log table or
file is introduced. Secret-redaction discipline (§8, §12) applies uniformly: no event, REST
response, log line, or exception message emitted by this contract's new code ever carries a
credential value — matching `Credential.__repr__`'s redaction (`credentials.py:128-137`) and
`GatewayRequest.audit()`'s header/body omission (`gateway.py:114-124`).

## 20. Observability

Reuses the existing event/health infrastructure — **no separate observability platform.** New
signals, all derivable from data this contract already produces:

| Metric | Source |
|---|---|
| Integration count / active / connected | `IntegrationService.list_installed()` (existing) + `Credential.status()` (existing) |
| Connection-test success rate / latency | Aggregated from `IntegrationConnectionTestEvent` payloads (§17) — computed by whatever reads the event stream, not stored as a running counter inside `IntegrationService` itself |
| Health state | New `integrations` `HealthMonitor` collector (§13) |
| Vendor error rate | `ApiGateway.stats()` (existing, `gateway.py:326`, already reachable via `GET /integrations/gateway/stats`) |
| Failover count | Aggregated from `IntegrationFailoverEvent` |
| Switch count | Aggregated from `IntegrationSwitchEvent` |
| Discovery count | Aggregated from `IntegrationDiscoveryEvent` |
| Authentication failure count | Already tracked via `MCPAuthStateChangedEvent` (existing, unmodified) |

## 21. Error taxonomy

Extends the existing hierarchy (`core/exceptions.py`, `core/integrations/models.py:51-59`,
`core/integrations/gateway.py:74-85`) — **no new exception base class.** Every new failure
category maps to an existing exception type plus a stable `error_code` string carried in the new
dataclasses (§7), for machine readability without inventing a second exception hierarchy:

| Failure category | Exception raised | `error_code` |
|---|---|---|
| Invalid credentials | `MCPAuthError` (`core/mcp/auth/credentials.py:33`) | `invalid_credentials` |
| Unauthorized (JARVIS permission gate) | `authorize_capability` returns `(False, reason)` — no exception, structured refusal (`manager.py:389-394`) | `unauthorized` |
| Forbidden (vendor scope gate) | same as above, `reason` names the scope gate | `forbidden_scope` |
| Timeout | `GatewayError(retryable=True)` on an `asyncio.TimeoutError` from the underlying HTTP client | `timeout` |
| DNS/network failure | `GatewayError(status_code=None, retryable=True)` (`gateway.py:74-85`, `provider.py`'s unreachable-host case) | `network_error` |
| Vendor unavailable | `GatewayError(status_code in {500,502,503,504}, retryable=True)` | `vendor_unavailable` |
| Rate limited | `GatewayError(status_code=429, retryable=True)` | `rate_limited` |
| Malformed response | New: caught at the Connection Test/validator layer when a 2xx response body cannot be parsed as declared | `malformed_response` |
| Unsupported capability | `IntegrationError` (`models.py:51-59`, e.g. `operation()` lookup failure at `models.py:339-342`) | `unsupported_capability` |
| Configuration error | `ServiceError` (`integration_service.py:187-190`, e.g. missing OAuth client) | `configuration_error` |
| Internal error | Any uncaught exception, translated to `ServiceError` at the `_as_service_error()` boundary (`integration_service.py:62-86`) — never leaks a raw traceback past the service layer | `internal_error` |

Every REST route maps these through the existing `_bad_request()` → HTTP 400 pattern
(`integrations.py:80-84`) for caller-fault categories, and lets `internal_error` surface as the
route's normal unhandled-exception path (500) — no new HTTP status-code convention introduced.

## 22. Test strategy

Fixed, per instruction and existing project convention (`CLAUDE.md`, confirmed in
`tests/unit/test_api_gateway.py`, `tests/unit/test_integration_provider.py`,
`tests/integration/test_integration_platform_e2e.py`):

- **Real local `aiohttp` fake-vendor server** for every new network-touching test (real
  validator, Connection Test, Failover's retryable-error path). No `unittest.mock`, no patched
  `httpx`/`aiohttp`.
- **FastAPI `TestClient`** for the new REST routes (§16), following
  `tests/unit/test_integrations_route.py`'s existing pattern exactly.
- **Real temp-file JSON store** for any `ApiCenterService` validator-swap tests, matching
  `tests/unit/test_api_center_service.py`.
- **Boundary-enforcing tests required, not optional:** a Health-poll test must assert **zero**
  requests reach the fake vendor server during a poll tick; a Connection-Test test must assert
  **exactly one**. This directly tests the §11 boundary rather than trusting it by convention.

| Area | Required cases |
|---|---|
| Discovery | catalogue enumeration, already-installed entries excluded, `availability_note`-flagged entries still surfaced |
| Connection | valid credentials, invalid credentials, timeout, network failure, unauthorized, forbidden, vendor unavailable, malformed response |
| Health | healthy, unhealthy (failed collector), zero network calls during poll |
| Switching | valid switch, unauthorized target, target not connected, in-flight-call isolation |
| Failover | retryable failure → recovers via candidate, non-retryable failure → no failover attempted, no candidate exists → `no_candidate` outcome recorded |
| Security | credential never appears in any new event/response/log (assert via string search over serialized payloads, matching the existing audit-payload tests' pattern in `test_integration_platform_e2e.py`) |

## 23. Task Group boundaries

Planning groups only — no branch, no code, created by this document:

| Group | Content | Depends on |
|---|---|---|
| TG-A | M5 coexistence boundary made explicit in code comments/docstrings (no behavior change) | none |
| TG-B | Real validator (§12) + Connection Testing (§11, §16's `test-connection` route) | TG-A |
| TG-C | Health surface (§13, §16's `health` route) | none (independent of B) |
| TG-D | Discovery listing (§9, §16's `discoverable` route) | none (independent of B/C) |
| TG-E | Runtime Switching (§14, §16's `switch` route) | TG-B (reuses Connection Test's auth-check pattern) |
| TG-F | Failover (§15) | TG-E (shares the "no valid alternate" handling) |
| TG-G | Events (§17) + Observability (§20) + full test suite (§22) | TG-B through TG-F, threaded through each rather than done last |

## 24. Dependencies

None hard-blocking (ADR §11, Phase 0 audit §7 — M14 not required). Two soft, content-only
dependencies, not code dependencies: real multi-vendor Runtime Switching (§14) and real Failover
(§15) both need a second catalogued vendor to exist before their full acceptance criteria can be
demonstrated — the mechanism is buildable and testable (with a synthetic second fake-vendor spec
in tests) independent of that.

## 25. Acceptance criteria

1. M5 (`ApiCenterService`) and M11 (`core/integrations/`) remain two separate, coexisting
   authoritative domains — no data migrates between them.
2. No third credential store exists anywhere in the diff.
3. No third provider registry exists anywhere in the diff.
4. `ApiCenterService.validate()`'s default validator is not `MockApiValidator`.
5. `MockApiValidator` is reachable only from tests or an explicit Developer-Mode opt-in — never
   the unconditional default.
6. Connection Testing (§11, §16) is the only path that makes a vendor request as validation;
   `RestIntegrationProvider.health()` continues to make zero vendor requests.
7. `HealthMonitor`'s poll loop never issues a vendor HTTP request (test-enforced, §22).
8. Discovery (§9) enumerates only `core/integrations/catalogue.py` entries — never `ILLMProvider`
   or any AI/voice/vision provider.
9. Discovery never calls `install()`, `connect()`, or any auth flow as a side effect.
10. Runtime Switching (§14) never references `ILLMProvider`, LLM/voice/vision model names, or the
    Calibration Engine's (unbuilt) concepts anywhere in its implementation.
11. Failover (§15) never wraps or extends `FallbackLLMProvider`.
12. No code introduced by this contract imports from or extends anything under a future/planned
    Calibration Engine path.
13. No credential value (access/refresh token, API key, secret) appears in any new log line,
    event payload, REST response, or exception message (test-enforced, §22).
14. Every new privileged action (Connection Test, Switch, Failover, Discovery registration)
    publishes a corresponding event (§17) and passes through `authorize_capability` where it
    reaches a vendor.
15. Every new network-touching test uses a real local `aiohttp` fake-vendor server — zero
    `unittest.mock`/patched-`httpx` usage in the diff.
16. No existing REST route, event class, registry, or credential store is duplicated — every new
    route/event is additive per §16/§17's tables.
17. `MCPProviderRegistry`, `MCPProviderManager`, `CredentialStore`, `ApiGateway`, and
    `catalogue.py` are extended, never reimplemented.
18. Existing integration REST routes (catalogue, install, connect, invoke, preview, search,
    oauth, revoke, gateway/stats) are unchanged.
19. Connection Test has a bounded, enforced timeout (≤10s caller-facing default).
20. Every failure category in §21 maps to a stable, tested `error_code`.
21. Runtime Switching and Failover ship with their mechanism fully tested (via a synthetic
    second fake-vendor spec in tests) even though only one real vendor is catalogued at ship
    time (§24).

## 26. Explicit AI Calibration boundary

Restating ADR §10 and Scope Matrix as binding, testable exclusions for this contract's
implementation: **no code produced under this Logic Contract may reference** `ILLMProvider`
(`core/interfaces/llm_provider.py`), any class under `infrastructure/llm/`, model names (GPT,
Claude, Gemini, etc.) as routing targets, `FallbackLLMProvider`, voice/vision provider selection,
or AI cost/hardware routing of any kind. The one permitted exception, unchanged from the ADR: M5
`ApiCenterService` may continue storing/validating `ApiCategory.LLM`-tagged credentials as
generic credential management — this contract's new code never touches those entries (§5).

## 27. Migration/compatibility notes

None required (ADR §12). This is additive: existing REST routes, events, registries, and stores
are unchanged; new routes/events/collectors are added alongside them. The only behavior change to
existing code is `ApiCenterService`'s validator default (§12) — a drop-in swap behind the same
`validate()`/`validate_all()` interface, with no caller-visible signature change.

## 28. Open questions

Per instruction, anything not resolvable from the approved architecture is marked `BLOCKED`
rather than guessed. Two remain, both narrow and non-blocking for starting TG-A/TG-C/TG-D:

1. **`BLOCKED — REQUIRES ARCHITECTURE DECISION`: version-incompatibility handling for discovered
   integrations (§9).** No compatibility contract exists in the codebase for `IntegrationSpec.
   version` to be checked against; this needs a decision before Discovery's version-check
   behavior (not its basic listing behavior) can be implemented.
2. **`BLOCKED — REQUIRES ARCHITECTURE DECISION`: rate-limiting/abuse protection for
   Connection Test, Discovery, and Failover (§18).** No API-wide rate-limiting layer exists
   anywhere in `infrastructure/api/routes/` today; this is a cross-cutting concern larger than
   M11 and should not be solved as an M11-local mechanism without that broader decision.

Everything else — the five originally-flagged architectural ambiguities (M5/M11 boundary, mock
validator, health vs. connection test, runtime switching scope, discovery scope), plus Built-in
Providers and the AI Calibration boundary — is fully resolved by the ADR and restated as binding
throughout this contract. No other open architectural ambiguity remains.
