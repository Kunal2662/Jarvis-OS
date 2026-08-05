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
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

from jarvis.core.exceptions import ServiceError
from jarvis.core.integrations.catalogue import build_spec, describe_catalogue
from jarvis.core.integrations.models import IntegrationError, IntegrationSpec
from jarvis.core.integrations.provider import RestIntegrationProvider
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
        uses."""
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
        self._unregister_search(integration_id)
        with _as_service_error():
            return await self._providers.disconnect(integration_id)

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
