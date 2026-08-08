# M11 API Center — Architecture Decision Record

**Status:** Decisions finalized. No code changed. No Logic Contract written yet — this
document is the input to that Logic Contract, not a replacement for it.

**Scope:** Resolves the five architectural ambiguities raised by the M11 API Center Phase 0
audit, plus two related questions (M5/M11 collision, Built-in Providers taxonomy) that block
writing a correct Logic Contract.

---

## 1. Current State

Two things are currently called "API Center," and they are unconnected:

- **M5 `ApiCenterService`** (`src/jarvis/services/api_center_service.py`) — shipped. Full CRUD
  over `ApiDefinition` (`src/jarvis/domain/api_center/models.py:54-78`), Fernet-encrypted
  secret fields (`api_key`, `bearer_token`, `secret`, `oauth_client_secret` —
  `api_center_service.py:39,93-103`), import/export, smart suggestion
  (`features/api_center/suggester.py`), and `validate()`/`validate_all()`
  (`api_center_service.py:225-235`) backed by `MockApiValidator`. Persists to
  `<data_dir>/config/api_center.json`. Reachable only from the PySide6 Developer Mode view
  (`ui/views/developer/api_center_view.py`) — **no REST route exists**.
  **Important, previously-unflagged finding:** `ApiDefinition.category` includes
  `ApiCategory.LLM` (`domain/api_center/models.py:34`) alongside `SEARCH`,
  `DEVELOPER_TOOLS`, `SMART_HOME`, `WEATHER`, `MAPPING`, `VISION_OCR`, `PERFORMANCE`,
  `CUSTOM`. The module's own docstring says its 14 built-in templates include "Gemini,
  OpenAI, Claude, ..." (`domain/api_center/models.py:3-6`). **M5's API Center already stores
  LLM-provider credentials in the same flat model as vendor-integration credentials.** This
  materially affects the M11/Calibration-Engine boundary (§10) and is addressed explicitly
  there — do not read past this document without that section.

- **M11 "API Center Architecture" module** — per `MASTER_ROADMAP.md:2947-2955`, explicitly
  "Planning only; no implementation exists yet." Its 10-item scope
  (`MASTER_ROADMAP.md:2977-3007`) is unbuilt.

- **Real, adjacent, shipped infrastructure that already exists and must be extended, not
  duplicated:** `core/integrations/{gateway.py, provider.py, catalogue.py, models.py,
  google.py}`, `services/integration_service.py`, `core/mcp/providers/{registry.py,
  manager.py}`, `core/mcp/auth/{store.py, manager.py, credentials.py}`,
  `infrastructure/api/routes/integrations.py` (14 routes). Full citations in the Phase 0
  audit; not repeated wholesale here.

---

## 2. M5 vs M11 Boundary — Final Decision

**Option C — coexist, with a documented, narrowed boundary. Neither Option A (M11 extends M5
wholesale) nor Option B (M11 replaces M5) is correct**, because M5 and the planned M11 module
solve two genuinely different problems that happen to share a name:

| | M5 `ApiCenterService` | M11 API Center Architecture |
|---|---|---|
| Unit of management | A user-entered `ApiDefinition` (name, base URL, headers, one flat auth blob) — works for *any* HTTP API, including ones nobody wrote an adapter for | A `RestIntegrationProvider` bound to a declarative `IntegrationSpec`/`OperationSpec` catalogue entry — structured operations, typed params, OAuth2 flows |
| Credential model | One flat `ApiDefinition` row, Fernet field-level encryption, one JSON file | `Credential` objects in `CredentialStore`, Fernet field-level encryption, a different JSON file, OAuth2-token-shaped (access/refresh/expiry) |
| Reachability | Desktop-only (PySide6), no REST | REST-first (`infrastructure/api/routes/integrations.py`), desktop-optional |
| Breadth | 14 built-in templates across 9 categories incl. LLM, SEARCH, WEATHER, MAPPING, SMART_HOME, PERFORMANCE, CUSTOM — a generic "any API key JARVIS might need" vault | 1 vendor family live (Google Workspace, 11 integrations/65 ops) — narrow, deep, operation-aware |
| Validation | Mock, unconditional (see §3) | None yet |

M5 is **not** a narrower version of M11 that can simply be absorbed — it is a *general-purpose
credential vault with a UI*, while M11's engine is a *typed operation-execution platform*. Forcing
one into the other would either (a) strip M11's typed `OperationSpec` model down to M5's flat
shape, losing path-encoding/param-validation safety already shipped in `models.py:220,240`, or
(b) force M5's LLM/weather/mapping/custom entries — which have no `IntegrationSpec` and never
will for most of them — through a catalogue-driven engine that assumes one exists.

**Decision:** M5 `ApiCenterService` remains authoritative for **generic, uncatalogued API
credentials** (anything without a hand-written `IntegrationSpec`: LLM keys, weather, mapping,
search, custom user-added APIs). M11's API Center Architecture module becomes authoritative for
**catalogued vendor integrations** (anything with a real `IntegrationSpec`/`OperationSpec`
entry: Google Workspace today, future Slack/GitHub/Notion/etc.). The two are related but
distinct registries, not a hierarchy.

**Where they must share, not duplicate:**
- Credential encryption technique (`jarvis.utils.crypto`, Fernet) — already shared by both
  today (`api_center_service.py:32`, `core/mcp/auth/store.py`). Keep it that way; do not add a
  third encryption helper.
- Health/status **display** — both should ultimately surface through the same "what's
  connected" view a user sees, even though the underlying storage differs. This is a UI/read
  concern, not a storage merge.

**What must NOT happen:** a new, third, unified "master" API Center store that re-persists
either M5's or M11's credentials. Neither store moves.

### Overlap
The only real overlap is conceptual (both answer "is API X connected and healthy") and
UI-surface (both currently render as a card list with a Validate/health badge). No code overlap
exists — confirmed by the Phase 0 audit's duplication search (zero shared classes/functions).

### Missing functionality
M5 has no REST route, no real validation, no connection registry beyond its own JSON file, no
concept of "operation" (it stores a base URL and lets the caller do whatever). M11's module has
none of the 10 scope items built yet (Phase 0 audit, §3).

### Migration path
None required today — no data migrates, no code moves. Should a future `IntegrationSpec` be
written for something currently only in M5 (e.g., a hand-written OpenAI/Gemini catalogue entry),
that specific `ApiDefinition` row would become *eligible* to also exist as an M11-managed
integration; the two are not mutually exclusive per-entry, but nothing forces migration.

### Final recommended architecture
Two coexisting registries behind one conceptual "connected APIs" surface:
- M5 `ApiCenterService` — generic vault, unchanged responsibilities, gets Task 3's real
  validator (§3) and, eventually, its own REST route (out of scope for this ADR — a
  Logic-Contract-time decision).
- M11 API Center Architecture — catalogue-driven vendor lifecycle engine, built as new code
  extending `core/integrations/` + `core/mcp/providers/`.

### Files that would eventually need modification (not now — Logic-Contract-time)
- `services/api_center_service.py` — swap `MockApiValidator` for a real validator (§3); no
  structural change otherwise.
- `features/api_center/validator.py` — new real implementation added alongside/replacing the
  mock (§3).
- New files under `core/integrations/` and/or `services/` for the M11 lifecycle registry
  itself (naming and shape belong to the Logic Contract, not this ADR).
- `infrastructure/api/routes/integrations.py` — extended with new routes for whichever of the
  10 items get REST surfaces.
- `core/di/container.py` — new provider registrations for whatever new M11 components are
  built.

---

## 3. Production Validation — Final Decision on `MockApiValidator`

**Why it exists:** `features/api_center/validator.py:1-7` self-documents as "Mock API
validation (Milestone 5, section 10B)... Deliberately deterministic-ish... nicer demo/test
experience." This is **temporary development/demo scaffolding that shipped to production
unchanged** — not test-only infrastructure that leaked, and not an intentionally-retained
long-term design. M5's own scope (per the roadmap, credential CRUD + UI) did not include a real
network validator; the mock was a placeholder to make the UI demoable before that work existed.

**Confirmed production exposure:** `_ApiRow._validate` → `ApiCenterService.validate()` →
`MockApiValidator.validate()` is reachable from a plain "Validate" button
(`api_center_view.py:76-79,137-141`) and a "Validate All" button (`api_center_view.py:168-170,
219-223`) with **no Developer Mode gate anywhere in the call path** — verified directly: no
`developer_mode`/`dev_mode` check exists in `api_center_service.py`, and `api_center_view.py`
itself is only reachable from within the Developer Mode section of the app, but that placement
does not gate the mock's *result* from being trusted/stored (`update_api(..., last_health=...)`,
`api_center_service.py:228-230`) as if it were real. This is a live violation of the user's
stated binding rule: *"Mock providers are permitted only when Developer Mode explicitly enables
them — never as a silent default"* (mirrors `MASTER_ROADMAP.md:2971-2975`).

**Target architecture:**

```
Production path:
  "Validate" click → ApiCenterService.validate(api_id)
    → real validator: makes an actual bounded HTTP request appropriate to api.auth_type
      (e.g. a cheap authenticated GET/HEAD against api.base_url, or the vendor's documented
      "who am I" endpoint where one exists)
    → structured ApiValidationResult (status, response_time_ms, message) — same shape as today,
      no API-breaking change to callers

Testing path:
  Real local aiohttp fake-vendor server (the project's established pattern — see
  tests/unit/test_api_gateway.py, tests/unit/test_integration_provider.py) stands in for
  api.base_url during tests. No unittest.mock/httpx-library patching.
```

**Decision: `MockApiValidator` is superseded, not deleted outright and not merely relocated.**
- A real validator (name/shape decided at Logic-Contract time) becomes the default behind
  `ApiCenterService.validate()`.
- `MockApiValidator` itself is **kept, but confined to tests and to an explicit Developer-Mode
  opt-in path** (e.g. a settings flag consistent with the project's existing Developer Mode
  gating elsewhere) — never the silent default again.
- This is a small, targeted fix (swap the default in `ApiCenterService.__init__`,
  `api_center_service.py:44-53`, plus add the real validator) — it does not require rebuilding
  M5's CRUD, storage, or UI.

---

## 4. Health Check vs. Connection Test — Formal Boundary

### Health Check
- **Purpose:** cheap, continuous "is this thing still working" signal for dashboards/alerts.
- **Trigger:** automatic, periodic — piggybacks on the existing `HealthMonitor` 15-second poll
  loop (`core/lifecycle/health_monitor.py:52,176-182`) via its `register_collector` extension
  point (`health_monitor.py:89-90`), exactly as the `mcp` collector already does.
- **Network behavior:** **local-only by default**, matching the existing, tested convention in
  `RestIntegrationProvider.health()` (`core/integrations/provider.py:255-261`, deliberately
  never calls the vendor). This convention is preserved, not broken.
- **Frequency:** every 15 seconds (shared interval, not per-provider-configurable initially).
- **Caching:** implicit — each poll tick's result is the only state kept; no separate cache
  layer.
- **Failure semantics:** a failed collector degrades that one entry in the snapshot
  (`health_monitor.py:148-152`, caught and reported as `{"error": ...}`) without failing the
  whole snapshot — same pattern applies to any new M11 collector.
- **Audit behavior:** flows into the existing `HealthUpdatedEvent` / WebSocket `health.updated`
  relay (`health_monitor.py:6-8,155-157`) — no new event type needed for the passive signal.

### Connection Test
- **Purpose:** user-initiated, authoritative "does this credential actually work right now"
  check — the thing "Validate" should have been doing all along (§3).
- **Trigger:** explicit user action only (REST call or button click) — never automatic, never
  on the health-poll cadence.
- **Network behavior:** **deliberately makes a real request** to the vendor/base URL — this is
  the one place the "health never calls the vendor" convention is intentionally overridden,
  and it must be documented as such wherever it's implemented so a future reader doesn't
  "fix" it back to local-only.
- **Timeout:** short and bounded (a few seconds) — this is a synchronous user-facing action, not
  a background poll; must not hang a UI button or REST request indefinitely. Exact value is a
  Logic-Contract parameter, not decided here.
- **Credential behavior:** uses the credential exactly as configured — no side effect on stored
  credential state beyond what already happens today (`last_health`/`last_response_time_ms`
  update, `api_center_service.py:228-230` pattern).
- **Audit behavior:** must follow the existing "secrets never reach a log line" rule
  (`core/integrations/gateway.py:30-34`) — request/response bodies and headers excluded from
  any audit record, matching `GatewayRequest.audit()` (`gateway.py:114-124`) and
  `IntegrationService.preview()`'s existing header omission (`integration_service.py:338-350`).
- **Response semantics:** structured result (status/latency/message) returned synchronously to
  the caller — same `ApiValidationResult` shape M5 already defines
  (`domain/api_center/models.py:82-89`), reused rather than reinvented for M11's catalogued
  integrations too.

**The boundary in one sentence:** Health Check answers "is it probably fine" without asking the
vendor; Connection Test answers "is it actually fine right now" by asking the vendor, on
request, with a short timeout, and identical no-secrets-logged discipline.

---

## 5. Runtime Provider Switching — Exact M11 Scope

**In scope for M11:** switching which *configured vendor integration/credential* handles a
given capability, where more than one is genuinely configured and interchangeable — e.g. two
Google Workspace accounts connected, or (once a second mail vendor is ever catalogued) choosing
which mail integration handles a "send email" call. **Today, concretely, this means: zero
integrations currently have a real alternative to switch to** (only Google Workspace is
catalogued) — so this item has no immediately buildable target beyond the *mechanism*, not the
*content*.

**Explicitly out of scope, always:** any of `GPT ↔ Claude`, `Ollama ↔ OpenAI`, `Vision Model A ↔
Vision Model B`, `Voice Model A ↔ Voice Model B`, or any `ILLMProvider` adapter selection. These
remain exclusively the unscheduled AI/API Calibration Engine's responsibility per
`ARCHITECTURE.md` §22.2 and the project's standing freeze instruction.

- **What triggers it:** user-initiated only in the initial scope (an explicit "use this
  connection instead" action) — no evidence in the codebase supports building *automatic*
  failover-triggered switching yet (see §7 on Failover, a related but separate item); automatic
  switching would need its own justification once more than one vendor per capability actually
  exists.
- **User-controlled vs. automatic:** user-controlled for the initial, buildable scope.
- **Credentials already installed:** yes — switching only ever selects among *already-connected*
  credentials (`Credential.status == CONNECTED` in `core/mcp/auth/credentials.py` terms); it
  never triggers a new OAuth flow as a side effect.
- **Permission revalidation:** must re-run the same dual permission gate
  (`MCPAuthManager.authorize_capability`, `core/integrations/provider.py:202-209`) the newly
  active integration would use for the next call — no bypass because a switch occurred.
- **Failure handling:** if the target integration is not connected/healthy, the switch is
  rejected synchronously with a structured error; it does not silently fall back to a third
  option (that would blur into Failover, §7, a distinct concept).
- **State preservation:** in-flight calls already dispatched to the previous integration are not
  retargeted; only calls issued after the switch use the new one.
- **Audit:** the switch itself is a loggable/event-worthy action (which integration became
  active, by whom, when) — no request/response bodies involved, so no additional secrecy
  concern beyond what §4 already establishes.

**If true generalized runtime switching cannot be safely built for all integration types** (per
the task's own instruction) **— it is scoped only to integration types where more than one
configured, connected credential genuinely exists for the same capability.** Given today's
catalogue has exactly one vendor family, this item's Logic Contract should define the mechanism
but its acceptance criteria cannot require a real second vendor to exist — that is itself an
open dependency on catalogue growth, not on M11's own code.

---

## 6. Automatic Provider Discovery — Exact M11 Scope

**Definition for M11:** discovering/registering **external integration adapters supported by
`core/integrations/`** — i.e., enumerating `IntegrationSpec` entries already present in
`catalogue.py`'s `AVAILABLE_SPECS` (`core/integrations/catalogue.py:41`) and any future
per-vendor spec modules alongside `google.py`, making them installable without a code change to
`integration_service.py` or the REST routes.

**Explicitly excluded:** `ILLMProvider` (`core/interfaces/llm_provider.py`), LLM models, voice
providers, vision providers, or any AI routing provider. The roadmap's own illustrative text
naming `ILLMProvider` as a discovery example (`MASTER_ROADMAP.md:2992-2995`) is **rejected as a
scope target for M11** — that enumeration, if ever built, belongs to the Calibration Engine, not
here.

- **Discovery source:** the `core/integrations/catalogue.py` module itself (`AVAILABLE_SPECS`
  and any future spec-package structure) — a static, code-defined catalogue, not a network
  scan or plugin-drop-folder scan. This matches the existing convention where
  `catalogue.build_spec()` (`catalogue.py:48`) already looks up by key rather than probing.
- **Adapter metadata:** whatever `IntegrationSpec` already carries (id, display name, auth
  method, operations) — no new metadata schema required.
- **Compatibility / version:** not currently modeled anywhere in `IntegrationSpec`
  (`core/integrations/models.py`) — if versioning is needed, that is new schema work belonging
  to the Logic Contract, not something "discovery" can infer from nothing.
- **Permissions:** unchanged — discovery only *lists* what's installable; installing still goes
  through the existing `IntegrationService.install()` → `MCPProviderManager.install()` path and
  its existing permission model.
- **Installation / activation:** discovery is a strictly read-only listing operation. Whether
  discovery also registers (making an entry visible before a user opts in) or only surfaces
  candidates is a Logic-Contract decision; this ADR fixes the **boundary** (integrations only,
  never AI providers), not that remaining detail.
- **Health / failure / rollback:** not applicable to discovery itself (it doesn't touch running
  state) — these apply to install/activate, which are already covered by existing
  `IntegrationService`/`MCPProviderManager` behavior.

**Decision on discover+register+install+activate depth:** discovery should be scoped to
**discover + register** only. Auto-installing or auto-activating a vendor integration without
explicit user action would contradict the OAuth-consent-driven model every existing integration
uses (`IntegrationService.start_authorization()`, `integration_service.py:186-190`) — a user must
still explicitly connect/authorize. This is a firm boundary, not left open for the Logic
Contract to relitigate.

---

## 7. Built-in Providers — Final Decision

**Option B, with a thin extension — reuse `ServiceManager.snapshot()`, do not build a new
registry.**

Inspected directly: `ServiceManager` (`core/lifecycle/service_manager.py:216-261`) already
tracks every registered service by name, lifecycle state, dependencies, and error
(`ServiceSnapshot`, lines 205-213), with a stable `register()`/`snapshot()` API every one of the
roadmap's 12 named built-ins (Memory, Automation, Workflow, Security, Database, Authentication,
Notifications, Configuration, Logging, Scheduler, Backup, Plugin Runtime) already goes through
today if they're modeled as `IService`. This is the exact "one source of truth for what's
running" the roadmap's Built-in Providers concept wants — building a second, parallel registry
(Option A) would immediately duplicate it, contradicting the project's own no-duplication rule.

**Gap, honestly stated:** `ServiceSnapshot` is a *lifecycle* view (name/state/dependencies/error)
— it does not carry the roadmap's desired display fields (Endpoint, Version) because those
concepts don't apply uniformly to in-process services. **Decision: do not invent them.** The
Built-in Providers surface should render `ServiceManager.snapshot()` as-is (Name, State, Health
via `HealthMonitor.snapshot()`'s `active_services`/`failed_services`, `health_monitor.py:133-
135`), and simply omit Endpoint/Version for entries that have none — not synthesize placeholder
values to fill a table column.

**Option C (separate internal capability registry) is rejected** — no evidence in the codebase
that `ServiceManager` is insufficient; introducing one would be exactly the kind of
"parallel/competing system" the standing project rules prohibit.

---

## 8. Credential Architecture — Authoritative Stores

**No third credential store.** Two remain authoritative, unchanged, for their existing domains:

1. `CredentialStore` (`core/mcp/auth/store.py:65`) — MCP/integration OAuth credentials
   (`<data_dir>/config/mcp_credentials.json`), Fernet-encrypted `access_token`/`refresh_token`
   only. Authoritative for **M11's catalogued integrations**.
2. `ConnectorCredentialStore` (`core/connectivity/credential_store.py:182`) — M12 device
   connector credentials, deliberately structurally separate from #1
   (`connectivity/credential_store.py:11-22`). **Out of scope for M11 entirely** — different
   domain (smart-home devices, not vendor APIs).

**A third, pre-existing store also stays as-is, unmerged:**

3. M5 `ApiCenterService`'s own encrypted fields inside `api_center.json`
   (`api_center_service.py:39,93-103`) — authoritative for **generic/uncatalogued API
   credentials** (§2). Not migrated into #1.

All three already use the same Fernet primitive (`jarvis.utils.crypto`) — that consistency is
preserved by construction, not by merging storage.

---

## 9. Registry Architecture — Authoritative Registries

- **`MCPProviderRegistry`** (`core/mcp/providers/registry.py:75`) — authoritative in-memory
  registry for every connected MCP-shaped provider, including every M11 integration. **M11's
  new lifecycle work extends this, and does not introduce a second provider registry.**
- **`ServiceManager`** (`core/lifecycle/service_manager.py:216`) — authoritative for built-in
  (non-API-key) services (§7). Not merged with `MCPProviderRegistry` — they track genuinely
  different kinds of things (in-process services vs. external-credential-backed providers), and
  merging them would force every built-in service to acquire a fake "credential" concept it
  doesn't have.
- **`core/integrations/catalogue.py`'s `AVAILABLE_SPECS`** — authoritative static catalogue of
  *what integrations exist to be installed* (§6). Distinct from the two registries above, which
  track *what's currently installed/running*.

No new registry class is created by this ADR.

---

## 10. AI Calibration Boundary — What M11 Does NOT Own

M11 owns the **Integration/Vendor Plane**: Gmail, Calendar, Drive, Slack, GitHub, Notion, and
other external productivity/vendor APIs — their OAuth/static-key credentials, connection state,
health, connection testing, failover, runtime activation/switching (scoped per §5), and
discovery (scoped per §6) — implemented by extending `core/integrations/` and
`core/mcp/providers/`.

M11 must **never** implement: LLM provider routing, LLM model selection, AI model ranking, AI
cost optimization, hardware-aware LLM routing, voice-model routing, vision-model routing,
`ILLMProvider` selection, AI model hot-swap, or AI provider calibration of any kind. These
belong exclusively to the unscheduled AI/API Calibration Engine (`ARCHITECTURE.md` §22.2).

**The one genuine wrinkle (§1, §2): M5's existing `ApiCenterService` already stores
LLM-category (`ApiCategory.LLM`) credentials** (Gemini/OpenAI/Claude keys) in the same flat
model as vendor APIs. This is resolved as follows, and this resolution is binding:

> Storing or validating the *existence/validity of a credential* for an LLM vendor (e.g. "is
> this OpenAI key well-formed and does the vendor accept it") is **credential management**, not
> AI routing, and is **not** a Calibration Engine concern — it's the same operation as
> validating a Slack token. M5 already does this today and may continue to. What crosses the
> line is **any code that uses that credential's existence, health, or any other signal to
> decide *which* LLM/voice/vision model or provider JARVIS actually calls for a given request**
> — that decision, in any form, is exclusively the Calibration Engine's.
>
> **Concretely: M11's new work (the catalogue-driven lifecycle engine) never touches
> `ApiCategory.LLM` entries at all** — those stay entirely inside M5's existing, unchanged
> scope. M11's Connection Testing/Health/Discovery/Switching apply only to `core/integrations/`
> catalogue entries (Google Workspace and future vendor specs), which today contain zero
> LLM-category entries. This keeps the boundary structural (different code, different registry)
> rather than relying on category-checking discipline at runtime.

---

## 11. Security Boundary — Is M14 Required?

**No. M14 is confirmed not a hard blocker for M11.** The existing Fernet-based `CredentialStore`
(`core/mcp/auth/store.py`) and M5's equivalent field-level encryption
(`api_center_service.py:93-103`) are adequate for everything in this module's scope: neither
introduces a new class of secret, a new storage location, or a new access-control requirement
that today's `MCPAuthManager` permission gates don't already cover
(`core/integrations/provider.py:202-209`). Nothing in §2–§9 requires inventing new secret
storage, and Task 10 (below) confirms no new credential store is proposed.

---

## 12. Migration Plan

**None required.** §2 establishes that M5 and M11 coexist as separate registries for separate
domains — no `ApiDefinition` row moves into `CredentialStore`, and no `Credential` moves into
`api_center.json`. The only concrete migration-shaped change identified is internal to M5 alone:
swapping `MockApiValidator` for a real validator behind the same `validate()`/`validate_all()`
interface (§3) — a drop-in replacement, not a data migration.

---

## 13. Test Strategy

Follow the project's existing, already-proven convention exactly (per
`tests/unit/test_api_gateway.py`, `tests/unit/test_integration_provider.py`,
`tests/integration/test_integration_platform_e2e.py`):

- **Real local `aiohttp` fake-vendor server** stands in for any external endpoint under test —
  for the new real validator (§3), for Connection Testing (§4), and for any future
  Failover/Switching tests (§5).
- **FastAPI `TestClient`** over the real service stack for any new REST routes, exactly as
  `tests/unit/test_integrations_route.py` does today.
- **No `unittest.mock`/`MagicMock` patching of `httpx`/`aiohttp`** anywhere in this module's
  tests — consistent with `CLAUDE.md`'s stated fakes-not-mocks convention.
- **Real temp-file JSON store** for `ApiCenterService`/`CredentialStore` persistence tests, as
  `tests/unit/test_api_center_service.py` already does — never a mocked repository.
- New tests for Health-vs-Connection-Test must explicitly assert the boundary in §4: a health
  poll must **not** produce an outbound HTTP request to the fake vendor server (assert zero
  requests received), while a Connection Test **must** (assert exactly one request received) —
  this prevents the two from silently merging back into one behavior over time.

---

## 14. Open Questions

**Zero unresolved architectural ambiguities remain among the five originally identified, plus
the M5/M11 collision and Built-in Providers questions — all seven are resolved above (§2–§7).**

Two items are explicitly deferred as **Logic-Contract-time parameters, not architectural
ambiguities** (they don't block writing a Logic Contract — the Logic Contract is exactly where
they get pinned down):
- Exact Connection Test timeout value (§4 — "short and bounded," a few seconds; exact number is
  a parameter).
- Exact naming/module location of the new M11 lifecycle-registry code and the real validator
  (§2, §3 — the *shape* is decided, the *file names* are not).

Neither is marked `BLOCKED` — both have a clear, bounded answer space and don't require further
codebase archaeology to resolve; they're ordinary Logic Contract fields (Failure Behaviour /
Inputs sections).
