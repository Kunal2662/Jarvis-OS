"""Integration service -- Milestone 11 Task Group E.

The application-facing surface over the integration platform: install a
connector, run its OAuth flow, invoke an operation, and search inside a
connected vendor. REST (``routes/integrations.py``), the agent tools and
the CLI all talk to this one class, so the three cannot drift into three
different ideas of what "connect Gmail" means.

**Everything underneath is M10.5's.** This service holds no registry of
its own: providers live in ``MCPProviderRegistry``, lifecycle runs
through ``MCPProviderManager``, credentials through ``MCPAuthManager``
and its ``CredentialStore``, permissions through the shared
``PermissionModel``, health through the provider manager's existing
collector. What is genuinely this class's own is the OAuth *flow* --
the two-step start/complete dance a browser redirect requires -- and
turning a catalogue id into an installed provider.

**Client credentials come from settings, never from a spec.** A spec is
source code and a client secret is a deployment secret. :meth:`start_authorization`
reads them from ``Settings`` at flow time and refuses, naming the
environment variable, when they are absent -- rather than starting a
flow that can only fail at the token exchange.

**Search sources are registered per connected integration.** A vendor
that declares a ``search_operation`` contributes one ``ISearchSource``
to the *existing* ``SearchService`` when it connects, and has it removed
when it disconnects. That is M10A's provider registry working as
designed; there is no second index and no change to ``SearchService``.

**M5 / M11 boundary (Task Group A).** This service owns only
*catalogue-backed* vendor integrations -- anything with a hand-written
:class:`~jarvis.core.integrations.models.IntegrationSpec` (Google
Workspace today; Phases 2-6 are catalogue entries against the same
engine, not yet written). Generic or uncatalogued API credentials --
including every LLM-category key -- remain permanently owned by M5's
:class:`~jarvis.services.api_center_service.ApiCenterService`; this
service does not read, write, or migrate them, and never will. It also
owns no LLM/voice/vision provider selection of any kind -- that is the
separate, unscheduled AI/API Calibration Engine's territory
(``ARCHITECTURE.md`` §22), which this service does not implement, wrap,
or extend. See ``docs/M11_API_CENTER_ARCHITECTURE_DECISIONS.md`` §2,
§5 and §10 for the approved boundary.
"""

from __future__ import annotations

import contextlib
from collections import deque
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

from jarvis.core.exceptions import ServiceError
from jarvis.core.integrations.catalogue import available_ids, build_spec, describe_catalogue
from jarvis.core.integrations.discovery import DiscoveryResult
from jarvis.core.integrations.failover import FailoverAttempt
from jarvis.core.integrations.gateway import GatewayError
from jarvis.core.integrations.models import IntegrationError, IntegrationSpec
from jarvis.core.integrations.provider import (
    RestIntegrationProvider,
    _classify_authorization_reason,
    _classify_gateway_error,
)
from jarvis.core.integrations.switching import SwitchResult
from jarvis.core.integrations.testing import ConnectionTestResult
from jarvis.core.interfaces.mcp import MCPError
from jarvis.core.logging.logger import get_logger
from jarvis.core.mcp.auth.credentials import AuthMethod
from jarvis.core.mcp.auth.oauth2 import (
    BoundOAuth2Strategy,
    OAuthFlowStore,
    build_authorization_url,
)
from jarvis.core.mcp.providers.metadata import ProviderConfig

if TYPE_CHECKING:
    from jarvis.core.config.settings import Settings
    from jarvis.core.events.event_bus import EventBus
    from jarvis.core.integrations.gateway import ApiGateway, GatewayResult
    from jarvis.core.mcp.auth.manager import MCPAuthManager
    from jarvis.core.mcp.providers.manager import MCPProviderManager
    from jarvis.services.search_service import SearchService

_logger = get_logger("jarvis.services.integration")


@contextlib.contextmanager
def _as_service_error() -> Iterator[None]:
    """Translate the MCP/integration exception family into ``ServiceError``.

    This service is the boundary between two error families: everything
    below it raises ``MCPError`` subclasses (``IntegrationError``,
    ``MCPProviderError``, ``MCPAuthError``, ``GatewayError``), and
    everything above it -- the REST routes, the agent tools, the CLI --
    catches ``ServiceError``. Without a translation here an undeclared
    parameter reaches the caller as a 500, which is precisely the gap
    Task Group C found with attachments: the refusal was correct, the
    status code said "we broke" instead of "you asked for something
    invalid".

    One context manager rather than a try/except per method, so a
    method added later cannot forget -- and so the translation reads as
    a boundary rather than as scattered defensive code.
    """
    try:
        yield
    except ServiceError:
        # Already the right family; re-wrapping would lose the message.
        raise
    except MCPError as err:
        raise ServiceError(str(err)) from err


class IntegrationService:
    """Install, authorize, invoke and search vendor integrations."""

    def __init__(
        self,
        *,
        provider_manager: MCPProviderManager,
        auth_manager: MCPAuthManager,
        gateway: ApiGateway,
        settings: Settings,
        flow_store: OAuthFlowStore | None = None,
        search_service: SearchService | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        self._providers = provider_manager
        self._auth = auth_manager
        self._gateway = gateway
        self._settings = settings
        self._flows = flow_store or OAuthFlowStore()
        self._search = search_service
        self._event_bus = event_bus
        self._installed: dict[str, RestIntegrationProvider] = {}
        #: Bounded, in-memory only -- Task Group E's failover history
        #: read surface. Not persisted: a restart losing the last 50
        #: attempts is an acceptable trade against inventing a new
        #: persistence layer for a diagnostics list.
        self._failover_history: deque[FailoverAttempt] = deque(maxlen=50)
        #: Task Group G -- in-memory operational counters, the same
        #: increment-a-plain-int pattern ``ApiGateway._calls``/
        #: ``_failures`` already uses. Not a second observability
        #: platform: just enough to answer "how many, how often" without
        #: replaying the whole event history. Failover's own counts are
        #: deliberately *not* duplicated here -- they are already fully
        #: recoverable from ``_failover_history`` above.
        self._connection_test_count = 0
        self._connection_test_success_count = 0
        self._switch_count = 0
        self._switch_success_count = 0
        self._discovery_run_count = 0

    # ------------------------------------------------------------------
    # Catalogue
    # ------------------------------------------------------------------
    def catalogue(self) -> tuple[dict[str, Any], ...]:
        """What could be installed. Data only -- describing an
        integration never touches the network."""
        return describe_catalogue()

    def describe(self, integration_id: str) -> dict[str, Any]:
        """One integration in full, including every operation."""
        return self._spec(integration_id).as_dict()

    def installed_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._installed))

    # ------------------------------------------------------------------
    # Automatic Discovery (Task Group F -- catalogue only, never a
    # filesystem scan, an import, or a network fetch)
    # ------------------------------------------------------------------
    async def discover(self) -> list[dict[str, Any]]:
        """Enumerate every entry in ``core/integrations/catalogue.py``
        and register whichever ones are not yet installed, through
        :meth:`install` (Task Group D) -- no second registration
        mechanism, and no duplicate lifecycle event: ``install()``
        already publishes its own ``MCPProviderStateChangedEvent`` when
        it actually registers something new, so this only adds a
        discovery-level audit record on top, never a second
        registration event for the same registration.

        Never activates (:meth:`connect`), never contacts a vendor,
        never validates or requires a credential -- a catalogue entry
        with no stored credential is registered exactly as
        :meth:`install` already allows.

        Idempotent and failure-isolated: a second call sees every
        already-installed entry as ``"already_registered"`` and changes
        nothing; one entry failing to register never prevents or
        undoes another's.
        """
        self._discovery_run_count += 1
        results = [await self._discover_one(integration_id) for integration_id in available_ids()]
        for result in results:
            await self._publish_discovery(result)
        return [result.as_dict() for result in results]

    async def _discover_one(self, integration_id: str) -> DiscoveryResult:
        if integration_id in self._installed:
            spec = self._installed[integration_id].spec
            return DiscoveryResult(
                integration_id=integration_id,
                vendor=spec.vendor,
                status="already_registered",
                version=spec.version,
                capabilities=spec.operation_names,
            )

        try:
            spec = build_spec(integration_id)
        except IntegrationError as err:
            # A malformed catalogue entry -- IntegrationSpec.validate()
            # (models.py) already ran inside build_spec() and refused
            # it. Reported, not raised: one bad entry must not fail the
            # whole sweep.
            return DiscoveryResult(
                integration_id=integration_id, vendor="", status="rejected", reason=str(err)
            )

        try:
            await self.install(integration_id)
        except ServiceError as err:
            return DiscoveryResult(
                integration_id=integration_id,
                vendor=spec.vendor,
                status="rejected",
                reason=str(err),
                version=spec.version,
                capabilities=spec.operation_names,
            )

        return DiscoveryResult(
            integration_id=integration_id,
            vendor=spec.vendor,
            status="registered",
            version=spec.version,
            capabilities=spec.operation_names,
        )

    # ------------------------------------------------------------------
    # Installation
    # ------------------------------------------------------------------
    async def install(
        self, integration_id: str, *, account_id: str = "", replace: bool = False
    ) -> dict[str, Any]:
        """Register an integration as an MCP provider.

        Installing declares the integration's permission requests
        against the shared ``PermissionModel`` (they land ``PENDING``)
        and creates nothing on the network. An install is reversible and
        cheap, which is what lets an approval screen show what a
        connector *would* do before anyone authorizes it.

        This *is* M11 Task Group D's "Registration" operation. The
        Logic Contract's own analysis (§10) found no second mechanism
        was needed: this already establishes the runtime relationship
        between an ``IntegrationSpec`` and a live ``MCPProviderRegistry``
        entry that Task Group D's objective describes, is already
        deterministic (a duplicate call without ``replace=True`` is
        rejected, never silently duplicated), and already never
        contacts the vendor. No separate ``register()`` method exists.
        """
        spec = self._spec(integration_id)
        provider = RestIntegrationProvider(
            spec,
            gateway=self._gateway,
            auth_manager=self._auth,
            account_id=account_id,
        )
        with _as_service_error():
            record = await self._providers.install(
                spec.integration_id,
                spec.to_metadata(),
                ProviderConfig(options={"integration_id": spec.integration_id}),
                replace=replace,
                provider=provider,
            )
        self._installed[spec.integration_id] = provider
        await self._providers.initialize(spec.integration_id)
        _logger.info("Integration installed: {}", spec.integration_id)
        return record.as_dict()

    async def uninstall(self, integration_id: str) -> bool:
        """Remove the provider and its search source. The credential is
        deliberately **kept** -- uninstalling is not revoking, and
        silently discarding a token the user granted would make
        reinstalling require a fresh consent screen for no reason. Use
        :meth:`revoke` to drop the credential."""
        self._unregister_search(integration_id)
        self._installed.pop(integration_id, None)
        with _as_service_error():
            return await self._providers.remove(integration_id)

    # ------------------------------------------------------------------
    # Authorization (the flow M10.5 deferred)
    # ------------------------------------------------------------------
    def start_authorization(
        self, integration_id: str, *, redirect_uri: str = "", scopes: list[str] | None = None
    ) -> dict[str, Any]:
        """Begin an OAuth2 authorization-code flow.

        Returns the URL a user opens and the ``state`` that identifies
        the flow. The PKCE verifier stays server-side in the flow store
        and is never returned -- handing it to a caller would defeat the
        exchange it protects.
        """
        spec = self._spec(integration_id)
        if spec.auth.method is not AuthMethod.OAUTH2:
            raise ServiceError(
                f"Integration {integration_id!r} uses {spec.auth.method.value}, which has "
                "no authorization URL. Authenticate it directly instead."
            )

        client_id, client_secret = self._client_credentials(spec)
        if not client_id:
            raise ServiceError(
                f"No OAuth client is configured for vendor {spec.vendor!r}. Set "
                f"{self._env_prefix(spec.vendor)}_CLIENT_ID (and _CLIENT_SECRET) first."
            )

        resolved_redirect = redirect_uri or self._settings.integrations.redirect_uri
        requested = tuple(scopes) if scopes else spec.required_scopes
        flow = self._flows.start(
            spec.integration_id,
            client_id=client_id,
            redirect_uri=resolved_redirect,
            token_url=spec.auth.token_url,
            scopes=requested,
            revoke_url=spec.auth.revoke_url,
            metadata={"vendor": spec.vendor, "has_secret": bool(client_secret)},
        )
        return {
            "integration_id": spec.integration_id,
            "state": flow.state,
            "authorization_url": build_authorization_url(
                spec.auth.authorize_url, flow, extra_params=spec.auth.authorize_params
            ),
            "redirect_uri": resolved_redirect,
            "scopes": list(requested),
        }

    async def complete_authorization(self, *, state: str, code: str) -> dict[str, Any]:
        """Exchange the authorization code for tokens.

        The ``state`` is consumed here -- single-use, so a replayed
        callback finds nothing. Everything about storing the credential
        (encryption, session, events) belongs to ``MCPAuthManager``;
        this method supplies the exchange inputs and nothing else.
        """
        if not code.strip():
            raise ServiceError("The authorization callback carried no code.")

        try:
            flow = self._flows.consume(state)
        except MCPError as err:
            # An unknown, replayed or expired state. A caller error, so
            # it becomes a ServiceError the route reports as 400 rather
            # than a 500 -- nothing broke.
            raise ServiceError(str(err)) from err

        spec = self._spec(flow.provider_id)
        _, client_secret = self._client_credentials(spec)

        with _as_service_error():
            credential = await self._auth.authenticate(
                flow.provider_id,
                AuthMethod.OAUTH2,
                {
                    "code": code,
                    "code_verifier": flow.code_verifier,
                    "redirect_uri": flow.redirect_uri,
                    "client_id": flow.client_id,
                    "client_secret": client_secret,
                    "token_url": flow.token_url,
                    "scopes": list(flow.scopes),
                },
            )
        _logger.info("Integration {!r} authorized.", flow.provider_id)
        return {
            "integration_id": flow.provider_id,
            "credential": credential.to_public_dict(),
            "granted_scopes": list(credential.scopes),
        }

    async def revoke(self, integration_id: str) -> bool:
        """Revoke the credential, remotely where the vendor supports it.

        Binds a strategy that knows this vendor's endpoints first --
        a ``Credential`` deliberately carries no configuration, so the
        registry-wide strategy can only clear the token locally. Then
        ``MCPAuthManager.revoke`` does the rest: it publishes the
        events, clears the tokens and marks the session, exactly as it
        does for every other provider.
        """
        self._bind_refresh_strategy(integration_id)
        with _as_service_error():
            revoked = await self._auth.revoke(integration_id)
        if revoked and integration_id in self._installed:
            await self.disconnect(integration_id)
        return revoked

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------
    async def connect(self, integration_id: str) -> dict[str, Any]:
        """Connect through ``MCPProviderManager`` -- the same call, the
        same events and the same state machine every MCP provider
        uses.

        This *is* M11 Task Group D's "Activation" operation: it makes a
        registered integration available to the runtime using only
        locally-known state -- a stored credential, per
        ``RestIntegrationProvider.start()``'s own "connecting is not
        calling" docstring -- and never a vendor request. A failure
        (missing credential, disabled provider, ...) lands the provider
        in ``ProviderState.FAILED`` (``MCPProviderManager._safe``) and
        is surfaced as a ``ServiceError`` below; it is never reported as
        connected. No separate ``activate()`` method exists; see
        ``docs/M11_API_CENTER_LOGIC_CONTRACT.md`` §10/§14.
        """
        self._require_installed(integration_id)
        with _as_service_error():
            connected = await self._providers.connect(integration_id)
        if connected:
            self._bind_refresh_strategy(integration_id)
            self._register_search(integration_id)
            return await self.status(integration_id)

        # `MCPProviderManager` records a failure as the provider's own
        # FAILED state rather than raising, so a caller that only looked
        # at the return value would see "not connected" with no reason.
        record = self._providers.registry.get(integration_id)
        raise ServiceError(
            f"Integration {integration_id!r} could not connect"
            f"{f': {record.error}' if record is not None and record.error else '.'}"
        )

    async def disconnect(self, integration_id: str) -> bool:
        """This *is* M11 Task Group D's "Deactivation" operation. The
        credential is deliberately preserved -- deactivating is not
        revoking, matching :meth:`uninstall`'s same principle one level
        up. Never a vendor request. No separate ``deactivate()`` method
        exists."""
        self._unregister_search(integration_id)
        with _as_service_error():
            return await self._providers.disconnect(integration_id)

    # ------------------------------------------------------------------
    # Connection Testing (Task Group B -- the one path allowed to
    # contact a vendor; see docs/M11_API_CENTER_LOGIC_CONTRACT.md §11)
    # ------------------------------------------------------------------
    async def test_connection(
        self,
        integration_id: str,
        *,
        operation: str | None = None,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        """Explicit, user-triggered only -- never called from
        :meth:`install`, :meth:`connect`, :meth:`health`, or anywhere
        in startup. Delegates the real HTTP work to the provider
        (:meth:`RestIntegrationProvider.test_connection`), which caps
        *timeout_seconds* at ``MAX_CONNECTION_TEST_TIMEOUT_SECONDS``
        regardless of what's requested -- a caller can only make this
        fail faster, never hold a vendor connection open longer. This
        layer only resolves the trusted, already-installed provider and
        publishes the audit event.
        """
        provider = self._require_installed(integration_id)
        kwargs: dict[str, Any] = {"operation": operation}
        if timeout_seconds is not None:
            kwargs["timeout_seconds"] = timeout_seconds
        result = await provider.test_connection(**kwargs)
        self._connection_test_count += 1
        if result.outcome == "success":
            self._connection_test_success_count += 1
        await self._publish_connection_test(result)
        return result.as_dict()

    # ------------------------------------------------------------------
    # Runtime Switching (Task Group E -- user-triggered only)
    # ------------------------------------------------------------------
    async def switch(
        self, *, operation: str, from_integration_id: str, to_integration_id: str
    ) -> dict[str, Any]:
        """Move *operation* from one already-catalogued integration to
        another. Concretely: activate the target, then deactivate the
        source -- in that order, so a target that fails to activate
        never causes the source to be falsely reported inactive (the
        source is untouched until the target is confirmed connected).

        *operation* is an existing capability both integrations must
        declare (:meth:`IntegrationSpec.has_operation`) -- not a new
        taxonomy. Eligibility requires the target to be installed and
        to already carry a valid credential
        (``MCPAuthManager.validate``); this never starts a new OAuth
        flow. Never raises for an ineligible target -- every outcome is
        a structured, secret-free :class:`SwitchResult`; only an
        unknown *from*/*to* id (never installed at all, ever) is a
        ``ServiceError``.
        """
        self._require_installed(from_integration_id)
        try:
            target = self._require_installed(to_integration_id)
        except ServiceError:
            result = SwitchResult(
                capability=operation,
                from_integration_id=from_integration_id,
                to_integration_id=to_integration_id,
                outcome="failure",
                error_code="target_not_registered",
            )
            await self._publish_switch(result)
            return result.as_dict()

        if not target.spec.has_operation(operation):
            result = SwitchResult(
                capability=operation,
                from_integration_id=from_integration_id,
                to_integration_id=to_integration_id,
                outcome="failure",
                error_code="unsupported_capability",
            )
            await self._publish_switch(result)
            return result.as_dict()

        if not self._auth.validate(to_integration_id):
            result = SwitchResult(
                capability=operation,
                from_integration_id=from_integration_id,
                to_integration_id=to_integration_id,
                outcome="failure",
                error_code="target_not_eligible",
            )
            await self._publish_switch(result)
            return result.as_dict()

        op = target.spec.operation(operation)
        allowed, reason = self._auth.authorize_capability(
            to_integration_id,
            required_permissions=op.permissions,
            required_scopes=op.scopes,
        )
        if not allowed:
            result = SwitchResult(
                capability=operation,
                from_integration_id=from_integration_id,
                to_integration_id=to_integration_id,
                outcome="failure",
                error_code=_classify_authorization_reason(reason),
            )
            await self._publish_switch(result)
            return result.as_dict()

        try:
            await self.connect(to_integration_id)
        except ServiceError:
            result = SwitchResult(
                capability=operation,
                from_integration_id=from_integration_id,
                to_integration_id=to_integration_id,
                outcome="failure",
                error_code="activation_failed",
            )
            await self._publish_switch(result)
            return result.as_dict()

        try:
            await self.disconnect(from_integration_id)
        except ServiceError as err:
            # The target is already correctly active and reported as
            # such -- per the Logic Contract's own invariant, this is
            # the success condition. The source lingering connected is
            # a soft inconsistency (multiple integrations may already
            # be connected simultaneously in this architecture), not an
            # unsafe one, and is surfaced rather than swallowed.
            _logger.warning(
                "Switch {} -> {} activated the target but could not " "deactivate the source: {}",
                from_integration_id,
                to_integration_id,
                err,
            )

        result = SwitchResult(
            capability=operation,
            from_integration_id=from_integration_id,
            to_integration_id=to_integration_id,
            outcome="success",
        )
        await self._publish_switch(result)
        return result.as_dict()

    # ------------------------------------------------------------------
    # Invocation
    # ------------------------------------------------------------------
    async def invoke(
        self, integration_id: str, operation: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Call one vendor operation and publish the audit event."""
        provider = self._require_installed(integration_id)
        try:
            result = await provider.invoke(operation, params or {})
        except MCPError as err:
            await self._publish_call(integration_id, operation, status=0, ok=False, detail=str(err))
            raise ServiceError(str(err)) from err

        await self._publish_call(
            integration_id,
            operation,
            status=result.status_code,
            ok=result.ok,
            from_cache=result.from_cache,
        )
        return {
            "integration_id": integration_id,
            "operation": operation,
            "status_code": result.status_code,
            "from_cache": result.from_cache,
            "data": result.data,
        }

    def preview(
        self, integration_id: str, operation: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """What :meth:`invoke` *would* send, without sending it.

        An outbound call is the one thing that cannot be undone by
        inspecting it afterwards, so the request is inspectable before
        it leaves. Headers are omitted: the whole point is that a
        preview is safe to show, and one of those headers is a token.
        """
        provider = self._require_installed(integration_id)
        with _as_service_error():
            return provider.build_request(operation, params or {}).audit()

    # ------------------------------------------------------------------
    # Vendor Integration Failover (Task Group E)
    # ------------------------------------------------------------------
    async def invoke_with_failover(
        self,
        integration_id: str,
        operation: str,
        params: dict[str, Any] | None = None,
        *,
        candidate_integration_id: str | None = None,
    ) -> dict[str, Any]:
        """:meth:`invoke`, plus exactly one caller-named fallback.

        On success, behaves identically to :meth:`invoke` (same event,
        same response shape). On a **non-retryable** failure (auth,
        forbidden, configuration, ...), behaves identically to
        :meth:`invoke` too -- that is never a failover condition, and
        propagates the same way. Only a persisting **retryable**
        ``GatewayError`` (timeout, network failure, vendor 5xx, 429 --
        i.e. something ``ApiGateway`` already retried and gave up on)
        reaches the failover branch.

        There is no catalogue scan here: *candidate_integration_id*
        must be supplied by the caller. Absent, unregistered,
        capability-incompatible or uncredentialed candidates all result
        in the same outcome a real vendor outage would if nothing else
        were configured: the call fails with ``NO_ELIGIBLE_ALTERNATE``.
        Exactly one candidate is ever tried -- if it also fails, this
        does not chain to a second one, which is what makes an
        A -> B -> A cycle structurally impossible here.
        """
        provider = self._require_installed(integration_id)
        try:
            result = await provider.invoke(operation, params or {})
        except GatewayError as err:
            return await self._handle_failover(
                integration_id, operation, params, err, candidate_integration_id
            )
        except MCPError as err:
            # Not a GatewayError -- a permission refusal or similar
            # local failure, never retryable, never a failover
            # condition. Identical to invoke()'s own behavior.
            await self._publish_call(integration_id, operation, status=0, ok=False, detail=str(err))
            raise ServiceError(str(err)) from err

        await self._publish_call(
            integration_id,
            operation,
            status=result.status_code,
            ok=result.ok,
            from_cache=result.from_cache,
        )
        return {
            "integration_id": integration_id,
            "operation": operation,
            "status_code": result.status_code,
            "from_cache": result.from_cache,
            "data": result.data,
        }

    async def _handle_failover(
        self,
        integration_id: str,
        operation: str,
        params: dict[str, Any] | None,
        err: GatewayError,
        candidate_integration_id: str | None,
    ) -> dict[str, Any]:
        await self._publish_call(integration_id, operation, status=err.status_code or 0, ok=False)

        if not err.retryable:
            attempt = FailoverAttempt(
                capability=operation,
                failed_integration_id=integration_id,
                candidate_integration_id=candidate_integration_id,
                outcome="failed",
                error_code=_classify_gateway_error(err),
            )
            await self._record_failover(attempt)
            raise ServiceError(f"{integration_id}.{operation} failed (not retryable).") from err

        if candidate_integration_id is None or candidate_integration_id not in self._installed:
            attempt = FailoverAttempt(
                capability=operation,
                failed_integration_id=integration_id,
                candidate_integration_id=candidate_integration_id,
                outcome="no_candidate",
                error_code="no_eligible_alternate",
            )
            await self._record_failover(attempt)
            raise ServiceError(
                f"{integration_id}.{operation} failed and no eligible alternate is "
                "available (NO_ELIGIBLE_ALTERNATE)."
            ) from err

        candidate = self._installed[candidate_integration_id]
        if not candidate.spec.has_operation(operation) or not self._auth.validate(
            candidate_integration_id
        ):
            attempt = FailoverAttempt(
                capability=operation,
                failed_integration_id=integration_id,
                candidate_integration_id=candidate_integration_id,
                outcome="no_candidate",
                error_code="no_eligible_alternate",
            )
            await self._record_failover(attempt)
            raise ServiceError(
                f"{integration_id}.{operation} failed and {candidate_integration_id!r} is "
                "not an eligible alternate (NO_ELIGIBLE_ALTERNATE)."
            ) from err

        try:
            candidate_result = await candidate.invoke(operation, params or {})
        except MCPError as candidate_err:
            attempt = FailoverAttempt(
                capability=operation,
                failed_integration_id=integration_id,
                candidate_integration_id=candidate_integration_id,
                outcome="failed",
                error_code="candidate_failed",
            )
            await self._record_failover(attempt)
            raise ServiceError(
                f"{integration_id}.{operation} failed and the alternate "
                f"{candidate_integration_id!r} also failed."
            ) from candidate_err

        attempt = FailoverAttempt(
            capability=operation,
            failed_integration_id=integration_id,
            candidate_integration_id=candidate_integration_id,
            outcome="recovered",
        )
        await self._record_failover(attempt)
        await self._publish_call(
            candidate_integration_id,
            operation,
            status=candidate_result.status_code,
            ok=candidate_result.ok,
            from_cache=candidate_result.from_cache,
        )
        return {
            "integration_id": candidate_integration_id,
            "operation": operation,
            "status_code": candidate_result.status_code,
            "from_cache": candidate_result.from_cache,
            "data": candidate_result.data,
            "failed_over_from": integration_id,
        }

    def failover_history(self, *, capability: str | None = None) -> list[dict[str, Any]]:
        """The last (up to 50) failover attempts, newest first.
        In-memory only -- see the constructor's ``_failover_history``
        for why this is not persisted."""
        attempts = list(self._failover_history)
        if capability is not None:
            attempts = [a for a in attempts if a.capability == capability]
        return [a.as_dict() for a in reversed(attempts)]

    def observability_snapshot(self) -> dict[str, Any]:
        """Safe operational counters across the whole M11 surface --
        Task Group G. Collected, not computed by a second platform: the
        gateway's own counters are embedded as-is
        (:meth:`gateway_stats`), failover counts are derived from the
        same bounded history :meth:`failover_history` already reads,
        and the rest are plain in-memory counters incremented at their
        one natural call site (the same pattern
        ``ApiGateway._calls``/``_failures`` already uses). No request/
        response bodies, no credentials -- integers and integration ids
        only.
        """
        failed_over = [a for a in self._failover_history if a.outcome == "recovered"]
        no_candidate = [a for a in self._failover_history if a.outcome == "no_candidate"]
        failed = [a for a in self._failover_history if a.outcome == "failed"]
        connected = [
            record.provider_id
            for record in self._providers.registry.discover()
            if record.provider_id in self._installed and record.state.value == "connected"
        ]
        return {
            "installed_count": len(self._installed),
            "connected_count": len(connected),
            "connection_test_count": self._connection_test_count,
            "connection_test_success_count": self._connection_test_success_count,
            "switch_count": self._switch_count,
            "switch_success_count": self._switch_success_count,
            "failover_recovered_count": len(failed_over),
            "failover_no_candidate_count": len(no_candidate),
            "failover_failed_count": len(failed),
            "discovery_run_count": self._discovery_run_count,
            "gateway": self.gateway_stats(),
        }

    # ------------------------------------------------------------------
    # Health (Task Group C -- local-only, never a vendor request)
    # ------------------------------------------------------------------
    async def health(self, integration_id: str) -> dict[str, Any]:
        """Locally-known health for one installed, catalogued integration.

        Never a vendor request. ``MCPProviderManager.health()`` (below)
        calls ``RestIntegrationProvider.health()``, which is documented
        local-only for exactly this reason -- a health poll must not
        turn into vendor quota spend, and a vendor's slow minute must
        not fail an otherwise-healthy integration. Credential
        *presence* comes from ``MCPAuthManager.status()``, itself a
        local read of ``CredentialStore`` metadata -- never a token
        validation call. This is deliberately **not** Connection
        Testing (a different, user-triggered, vendor-contacting
        capability reserved for a later task group); see
        ``docs/M11_API_CENTER_LOGIC_CONTRACT.md`` §11/§13 for the full
        boundary.

        No second periodic collector is registered for this data.
        Every installed integration is already an MCP provider, so
        ``MCPProviderManager.collect_health()`` -- and therefore the
        existing ``mcp`` ``HealthMonitor`` collector wired in
        ``app.py`` -- already carries it on every poll tick. This
        method is the on-demand, integration-scoped *view* the REST
        surface needs over that same local state, not a second
        measurement of it.
        """
        self._require_installed(integration_id)
        with _as_service_error():
            provider_health = await self._providers.health(integration_id)
        auth_status = self._auth.status(integration_id)
        credential = auth_status.get("credential")
        return {
            "integration_id": integration_id,
            "vendor": self._spec(integration_id).vendor,
            "state": provider_health["state"],
            "healthy": provider_health["healthy"],
            "detail": provider_health["detail"],
            "credential_status": credential["status"] if credential else "missing",
            "credential_configured": bool(credential and credential["has_access_token"]),
        }

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------
    async def status(self, integration_id: str) -> dict[str, Any]:
        """Provider state, permissions and credential status in one
        payload -- collected from the subsystems that own each, never
        recomputed here."""
        self._require_installed(integration_id)
        with _as_service_error():
            payload = await self._providers.status(integration_id)
        payload["auth"] = self._auth.status(integration_id)
        payload["pending_flows"] = self._flows.pending_for(integration_id)
        return payload

    async def list_installed(self) -> tuple[dict[str, Any], ...]:
        return tuple([await self.status(pid) for pid in self.installed_ids()])

    def gateway_stats(self) -> dict[str, Any]:
        return self._gateway.stats()

    async def search(
        self, integration_id: str, query: str, *, top_k: int = 10
    ) -> list[dict[str, Any]]:
        """Search inside one connected integration.

        Uses the vendor's own search endpoint -- the one the spec names
        -- rather than fetching everything and filtering locally, which
        would be slower, cost quota, and give worse answers than the
        vendor's own index.
        """
        spec = self._spec(integration_id)
        if not spec.search_operation:
            return []
        with _as_service_error():
            operation = spec.operation(spec.search_operation)
        params = _search_params(spec, operation.name, query, top_k)
        result = await self.invoke(integration_id, spec.search_operation, params)
        return _rows(result.get("data"))

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _spec(self, integration_id: str) -> IntegrationSpec:
        provider = self._installed.get(integration_id)
        if provider is not None:
            return provider.spec
        try:
            return build_spec(integration_id)
        except IntegrationError as err:
            raise ServiceError(str(err)) from err

    def _require_installed(self, integration_id: str) -> RestIntegrationProvider:
        provider = self._installed.get(integration_id)
        if provider is None:
            raise ServiceError(
                f"Integration {integration_id!r} is not installed. "
                f"Installed: {list(self.installed_ids()) or 'none'}."
            )
        return provider

    def _client_credentials(self, spec: IntegrationSpec) -> tuple[str, str]:
        """Read this vendor's OAuth client from settings.

        Per vendor rather than per integration: Google issues one client
        for a project and every Google product authorizes against it, so
        keying by integration would make an operator configure eleven
        identical pairs.
        """
        clients = self._settings.integrations.clients
        entry = clients.get(spec.vendor) or {}
        return str(entry.get("client_id") or ""), str(entry.get("client_secret") or "")

    @staticmethod
    def _env_prefix(vendor: str) -> str:
        return f"JARVIS_INTEGRATIONS_CLIENTS__{vendor.upper()}"

    def _bind_refresh_strategy(self, integration_id: str) -> None:
        """Give the auth manager a strategy that can actually refresh
        this provider.

        The registry-wide OAuth2 strategy cannot: a ``Credential``
        carries no token endpoint. Binding one per provider keeps that
        configuration out of the credential model while making
        unattended refresh work, which is the whole point of holding a
        refresh token.
        """
        spec = self._spec(integration_id)
        client_id, client_secret = self._client_credentials(spec)
        if not client_id:
            return
        self._auth.bind_strategy(
            integration_id,
            BoundOAuth2Strategy(
                token_url=spec.auth.token_url,
                client_id=client_id,
                client_secret=client_secret,
                revoke_url=spec.auth.revoke_url,
            ),
        )

    def _register_search(self, integration_id: str) -> None:
        if self._search is None:
            return
        spec = self._spec(integration_id)
        if not spec.search_operation:
            return
        from jarvis.services.search_sources import IntegrationSearchSource

        self._search.register_source(IntegrationSearchSource(self, spec))

    def _unregister_search(self, integration_id: str) -> None:
        if self._search is None:
            return
        self._search.unregister_source(f"integration:{integration_id}")

    async def _publish_call(
        self,
        integration_id: str,
        operation: str,
        *,
        status: int,
        ok: bool,
        from_cache: bool = False,
        detail: str = "",
    ) -> None:
        if self._event_bus is None:
            return
        from jarvis.core.events.events import IntegrationCallCompletedEvent

        await self._event_bus.publish(
            IntegrationCallCompletedEvent(
                integration_id=integration_id,
                operation=operation,
                status_code=status,
                ok=ok,
                from_cache=from_cache,
                detail=detail[:300],
            )
        )

    async def _publish_connection_test(self, result: ConnectionTestResult) -> None:
        """Not yet relayed over WebSocket -- see
        ``core/lifecycle/runtime_ws_hub.py``'s ``UNPUBLISHED_EVENT_TYPES``
        for why that's a documented, separate decision, not an
        oversight. Internal subscribers (audit, future observability)
        can still receive it from the event bus today."""
        if self._event_bus is None:
            return
        from jarvis.core.events.events import IntegrationConnectionTestEvent

        await self._event_bus.publish(
            IntegrationConnectionTestEvent(
                integration_id=result.integration_id,
                action="completed" if result.outcome == "success" else "failed",
                outcome=result.outcome,
                error_code=result.error_code,
                status_code=result.status_code or 0,
                latency_ms=result.latency_ms or 0.0,
            )
        )

    async def _publish_switch(self, result: SwitchResult) -> None:
        """Not yet relayed over WebSocket -- same documented, deferred
        decision as connection-test/failover events; see
        ``runtime_ws_hub.py``'s ``UNPUBLISHED_EVENT_TYPES``."""
        self._switch_count += 1
        if result.outcome == "success":
            self._switch_success_count += 1
        if self._event_bus is None:
            return
        from jarvis.core.events.events import IntegrationSwitchEvent

        await self._event_bus.publish(
            IntegrationSwitchEvent(
                capability=result.capability,
                from_integration_id=result.from_integration_id,
                to_integration_id=result.to_integration_id,
                action="completed" if result.outcome == "success" else "failed",
                outcome=result.outcome,
                error_code=result.error_code,
            )
        )

    async def _record_failover(self, attempt: FailoverAttempt) -> None:
        """Appends to the bounded in-memory history
        (:meth:`failover_history`) and publishes the audit event --
        the one place both happen together, so neither can be forgotten
        for a future call site."""
        self._failover_history.append(attempt)
        if self._event_bus is None:
            return
        from jarvis.core.events.events import IntegrationFailoverEvent

        action = {"recovered": "completed", "no_candidate": "no_candidate", "failed": "failed"}[
            attempt.outcome
        ]
        await self._event_bus.publish(
            IntegrationFailoverEvent(
                capability=attempt.capability,
                failed_integration_id=attempt.failed_integration_id,
                candidate_integration_id=attempt.candidate_integration_id or "",
                action=action,
                outcome=attempt.outcome,
                error_code=attempt.error_code,
            )
        )

    async def _publish_discovery(self, result: DiscoveryResult) -> None:
        """Discovery-level audit only -- when *result* is a fresh
        ``"registered"``, ``install()`` (called from :meth:`_discover_one`)
        has already published its own ``MCPProviderStateChangedEvent``;
        this is a second, distinct event about the discovery sweep
        itself, not a duplicate of that one."""
        if self._event_bus is None:
            return
        from jarvis.core.events.events import IntegrationDiscoveryEvent

        await self._event_bus.publish(
            IntegrationDiscoveryEvent(
                integration_id=result.integration_id,
                vendor=result.vendor,
                action=result.status,
                reason=result.reason,
            )
        )


# ---------------------------------------------------------------------------
# Search helpers
# ---------------------------------------------------------------------------
def _search_params(
    spec: IntegrationSpec, operation_name: str, query: str, top_k: int
) -> dict[str, Any]:
    """Map a plain query onto one vendor's search parameters.

    Vendors disagree about the name of "the search box" (``q``,
    ``query``) and about where it goes (query string, POST body), so the
    mapping is here, in one place, driven by what the operation
    declares. A spec field per vendor would put the same knowledge in
    thirty files.
    """
    operation = spec.operation(operation_name)
    params: dict[str, Any] = {}

    for name in ("q", "query"):
        if name in operation.query or name in operation.body:
            params[name] = query
            break

    for name, value in (("maxResults", top_k), ("pageSize", top_k)):
        if name in operation.query or name in operation.body:
            params[name] = value
            break

    # Google's per-user endpoints take the caller's own mailbox/account.
    for name in operation.path_params:
        if name == "user_id":
            params[name] = "me"
        elif name == "calendar_id":
            params[name] = "primary"

    # People API refuses a request that names no fields to return.
    if "readMask" in operation.query:
        params["readMask"] = "names,emailAddresses"
    if "personFields" in operation.query and "personFields" not in params:
        params["personFields"] = "names,emailAddresses"
    return params


def _rows(data: Any) -> list[dict[str, Any]]:
    """Pull the list out of a vendor response.

    Vendors wrap their results under different keys and there is no
    standard; trying every known one and giving up gracefully beats a
    per-vendor extractor function, because the failure mode here is
    "no results" rather than a wrong answer.
    """
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if not isinstance(data, dict):
        return []
    for key in (
        "messages",
        "items",
        "files",
        "results",
        "notes",
        "albums",
        "mediaItems",
        "connections",
        "people",
        "threads",
        "documents",
    ):
        value = data.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
    return []
