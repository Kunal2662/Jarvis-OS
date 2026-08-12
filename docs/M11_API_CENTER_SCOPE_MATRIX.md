# M11 API Center — Scope Matrix

Companion to [`M11_API_CENTER_ARCHITECTURE_DECISIONS.md`](M11_API_CENTER_ARCHITECTURE_DECISIONS.md).
This table exists to make the M11 vs. AI Calibration Engine boundary impossible to misread.
Every row's reasoning is expanded in the ADR's matching section (cited in the last column).

| Capability | M11 Owns? | Existing Implementation | Planned Implementation | AI Calibration? |
|---|---|---|---|---|
| Vendor credentials (OAuth/static key, catalogued integrations) | **Yes** | `CredentialStore` (`core/mcp/auth/store.py`), `RestIntegrationProvider` (`core/integrations/provider.py`) | New lifecycle-registry work extends these; no new store (ADR §8) | No |
| Generic/uncatalogued API credentials (incl. LLM-category keys) | **No — stays with M5** | `ApiCenterService` (`services/api_center_service.py`), `ApiDefinition` (`domain/api_center/models.py`) | Real validator replaces `MockApiValidator` (ADR §3); structure otherwise unchanged | Credential storage: No. See "LLM routing" row below for the line. |
| Vendor health (periodic, local-only) | **Yes** | `RestIntegrationProvider.health()` (`core/integrations/provider.py:255-261`), `HealthMonitor` `mcp` collector (`app.py`) | New M11-scoped collector following the same pattern (ADR §4) | No |
| Connection testing (user-triggered, real network call) | **Yes** | None — confirmed absent (Phase 0 audit) | New, scoped per ADR §4 (short timeout, no secrets logged, deliberately overrides the health-is-local-only convention) | No |
| Vendor failover (ordered fallback among configured integrations) | **Yes, narrowly** | None for this domain. `FallbackLLMProvider` exists but is a *different*, LLM-scoped mechanism (see below) | Scoped only to integration types with more than one connected credential for the same capability (ADR §5 discussion of Runtime Switching applies analogously) | No |
| Vendor runtime switching (which connected integration handles a capability) | **Yes, narrowly** | None | Scoped per ADR §5 — user-triggered only initially; today's catalogue has no second vendor to switch to, so only the mechanism, not real content, is buildable now | No |
| Integration discovery (enumerate installable `IntegrationSpec` catalogue entries) | **Yes** | `catalogue.py`'s `AVAILABLE_SPECS` (static dict, one vendor family populated) | Discover + register only, never auto-install/auto-activate (ADR §6) | No |
| Built-in (internal, non-API-key) service visibility | **Yes, via reuse** | `ServiceManager.snapshot()` (`core/lifecycle/service_manager.py:249`) | Read/display layer over the existing snapshot; no new registry (ADR §7) | No |
| LLM routing (which model handles a request) | **No** | Not built anywhere | N/A to M11 — reserved, unscheduled | **Yes — exclusively** |
| Model selection (GPT vs. Claude vs. Gemini, etc.) | **No** | Not built anywhere | N/A to M11 | **Yes — exclusively** |
| AI cost optimization | **No** | Not built anywhere | N/A to M11 | **Yes — exclusively** |
| AI hardware-aware routing | **No** | Not built anywhere | N/A to M11 | **Yes — exclusively** |
| LLM hot swap (runtime model switch) | **No** | `FallbackLLMProvider` (`infrastructure/llm/fallback_provider.py`) — static, config-driven, single primary→secondary, not a runtime "switch" in the M11 sense | N/A to M11 | **Yes — exclusively** |
| Voice provider routing | **No** | Not built anywhere | N/A to M11 | **Yes — exclusively** |
| Vision provider routing | **No** | Not built anywhere | N/A to M11 | **Yes — exclusively** |

## The one row that needs extra care

**"Generic/uncatalogued API credentials"** includes `ApiCategory.LLM` entries (e.g. an OpenAI or
Gemini API key stored via M5's Add API dialog). M11 does not take ownership of this row, and
never will as currently scoped — see ADR §10 for the full reasoning. The short version: *storing
and validating that a key exists and is well-formed* is credential management (fine, M5's job,
unrelated to M11); *deciding which model that key unlocks gets called* is AI routing (never M11,
never M5 — exclusively the Calibration Engine, unbuilt, frozen).
