"""REST integration provider -- Milestone 11 Task Group E.

:class:`RestIntegrationProvider` satisfies
:class:`~jarvis.core.interfaces.mcp.IMCPProvider` for a vendor REST API,
which is the case that Protocol's own docstring reserved: *"This
Protocol exists so a future integration with genuinely different needs
(a token refresh loop, say) can supply its own implementation without
the framework changing."* A Gmail connector has exactly that need, and
the framework does not change.

**What it reuses, and therefore does not rebuild.**

* Lifecycle and state -- ``MCPProviderManager`` drives the same six
  methods it drives on ``TransportBackedProvider``, publishes the same
  ``MCPProviderStateChangedEvent``, and records the same
  ``ProviderState``.
* Capabilities -- each operation is registered as an ``MCPCapability``
  in an ``MCPCapabilityRegistry``, the same class the client and server
  runtimes use. Its docstring already allowed for more than two owners:
  *"Each runtime owns its own instance."* This is a third owner.
* Permissions and credentials -- every call goes through
  ``MCPAuthManager.authorize_capability``, which checks the operator's
  grant in the shared ``PermissionModel`` **and** the vendor scopes the
  token actually carries. No third gate, no local grant store.
* Egress -- one shared ``ApiGateway``. This class builds a request from
  a spec and hands it over; it owns no connection pool and no retry
  logic.

**What it adds that a transport-backed provider does not have.** A token
that expires mid-session. :meth:`invoke` refreshes through the auth
manager when the credential is close to expiry, once, before the call --
rather than letting the vendor answer 401 and guessing what that meant.

**Connecting is not calling.** :meth:`start` verifies that a usable
credential exists and that the gateway is open. It deliberately makes no
vendor request: an integration that costs an API call every time
JARVIS starts would spend quota proving something the credential
already tells us, and a vendor being briefly unreachable is not a reason
to refuse to register a provider.
"""

from __future__ import annotations

import time
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from jarvis.core.integrations.gateway import GatewayError, GatewayRequest
from jarvis.core.integrations.models import IntegrationError, IntegrationSpec, OperationSpec
from jarvis.core.integrations.testing import (
    DEFAULT_CONNECTION_TEST_TIMEOUT_SECONDS,
    MAX_CONNECTION_TEST_TIMEOUT_SECONDS,
    ConnectionTestResult,
)
from jarvis.core.interfaces.service import HealthStatus, ServiceStatus
from jarvis.core.logging.logger import get_logger
from jarvis.core.mcp.capabilities import MCPCapabilityRegistry

if TYPE_CHECKING:
    from collections.abc import Collection

    from jarvis.core.integrations.gateway import ApiGateway, GatewayResult
    from jarvis.core.mcp.auth.manager import MCPAuthManager

_logger = get_logger("jarvis.core.integrations.provider")

#: Path parameters with a well-known safe default -- the same
#: convention ``IntegrationService``'s search-query mapping already
#: uses (Google's per-user/per-calendar endpoints take the caller's own
#: account). Lets an automatic connection-test probe pick a real,
#: zero-argument-from-the-caller operation without vendor-specific code
#: here.
_SAFE_PROBE_PATH_DEFAULTS: dict[str, str] = {"user_id": "me", "calendar_id": "primary"}

#: Fixed, reviewed, secret-free messages -- never the raw vendor
#: response or the raw transport exception, either of which could echo
#: something sensitive back.
_SAFE_GATEWAY_ERROR_MESSAGES: dict[str, str] = {
    "authentication_failed": "The vendor rejected the credentials.",
    "authorization_failed": "The vendor refused authorization for this request.",
    "timeout": "The vendor did not respond in time.",
    "network_error": "The vendor could not be reached.",
    "rate_limited": "The vendor is rate-limiting this integration.",
    "vendor_unavailable": "The vendor reported a server error.",
    "configuration_error": "The vendor rejected the request (endpoint or configuration problem).",
    "vendor_error": "The vendor rejected the request.",
}

#: Refresh a credential this close to expiry rather than after it. A
#: token that dies mid-request produces a 401 the caller cannot
#: distinguish from a revoked grant.
REFRESH_LEEWAY_SECONDS = 120.0


class RestIntegrationProvider:
    """One vendor integration, driven by its :class:`IntegrationSpec`."""

    def __init__(
        self,
        spec: IntegrationSpec,
        *,
        gateway: ApiGateway,
        auth_manager: MCPAuthManager,
        account_id: str = "",
    ) -> None:
        self.provider_id = spec.integration_id
        self._spec = spec
        self._gateway = gateway
        self._auth = auth_manager
        self._account_id = account_id
        self._capabilities = MCPCapabilityRegistry(owner=spec.integration_id)
        self._initialized = False
        self._connected = False
        self._error = ""
        self._granted_scopes: set[str] = set()
        self._calls = 0
        self._failures = 0

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------
    @property
    def spec(self) -> IntegrationSpec:
        return self._spec

    @property
    def capabilities(self) -> MCPCapabilityRegistry:
        """This integration's operations as MCP capabilities -- the same
        registry class, so ``/api/v1/mcp/capabilities`` describes a Gmail
        operation exactly as it describes a peer's tool."""
        return self._capabilities

    # ------------------------------------------------------------------
    # Lifecycle (the IMCPProvider contract)
    # ------------------------------------------------------------------
    async def initialize(self) -> None:
        """Validate the spec and publish its operations as capabilities.

        No network: the Protocol says initialization resolves
        dependencies and validates configuration, and that ``connect``
        owns I/O. Registering capabilities here is what lets a
        configured-but-unauthenticated integration still describe what
        it *would* do, which is what an approval screen needs to show.
        """
        if self._initialized:
            return
        self._spec.validate()
        self._capabilities.clear()
        for operation in self._spec.operations:
            self._capabilities.register(
                operation.to_capability(self._spec.integration_id), replace=True
            )
        self._initialized = True
        _logger.info(
            "Integration {!r} initialized with {} operation(s).",
            self.provider_id,
            len(self._spec.operations),
        )

    async def start(self) -> None:
        """Open the shared gateway and confirm a usable credential."""
        if not self._initialized:
            await self.initialize()
        await self._gateway.start()

        if not self._auth.validate(self.provider_id) and not await self._auth.reconnect(
            self.provider_id
        ):
            self._error = (
                f"Integration {self.provider_id!r} has no usable credential. " "Authorize it first."
            )
            self._connected = False
            raise IntegrationError(self._error)

        self._connected = True
        self._error = ""

    async def stop(self) -> None:
        """Idempotent, and it does **not** close the gateway -- the pool
        is shared, so one integration disconnecting must not cut off
        every other one."""
        self._connected = False

    async def suspend(self) -> None:
        self._connected = False

    async def resume(self) -> None:
        await self.start()

    async def shutdown(self) -> None:
        await self.stop()
        self._capabilities.clear()
        self._initialized = False

    # ------------------------------------------------------------------
    # Permissions
    # ------------------------------------------------------------------
    def set_granted_scopes(self, scopes: Collection[str]) -> None:
        """Resolved by ``MCPProviderManager`` from the shared
        ``PermissionModel``. Recorded for reporting only -- the
        authoritative check happens per call in :meth:`invoke`, because
        a grant revoked after connect must take effect on the next call
        rather than the next reconnect."""
        self._granted_scopes = set(scopes)

    @property
    def granted_scopes(self) -> frozenset[str]:
        return frozenset(self._granted_scopes)

    # ------------------------------------------------------------------
    # Invocation
    # ------------------------------------------------------------------
    async def invoke(
        self, operation_name: str, params: dict[str, Any] | None = None
    ) -> GatewayResult:
        """Call one vendor operation.

        The order of checks is the security-relevant part, and it runs
        cheapest-and-strictest first: the operation must exist, the
        provider must be connected, **both** permission gates must pass,
        and only then is a request built and sent. A caller cannot reach
        the gateway without passing every one.
        """
        operation = self._spec.operation(operation_name)
        if not self._connected:
            raise IntegrationError(
                f"Integration {self.provider_id!r} is not connected"
                f"{f': {self._error}' if self._error else '.'}"
            )

        allowed, reason = self._auth.authorize_capability(
            self.provider_id,
            required_permissions=operation.permissions,
            required_scopes=operation.scopes,
        )
        if not allowed:
            self._failures += 1
            raise IntegrationError(f"{self.provider_id}.{operation_name} refused: {reason}")

        await self._refresh_if_due()
        request = self.build_request(operation_name, params or {})

        try:
            result = await self._gateway.send(request)
        except GatewayError:
            self._failures += 1
            raise
        self._calls += 1
        return result

    def build_request(self, operation_name: str, params: dict[str, Any]) -> GatewayRequest:
        """Turn a spec plus caller parameters into one resolved request.

        Public, and separated from :meth:`invoke`, so a caller can see
        exactly what would be sent *without sending it* -- an outbound
        call is the one thing that cannot be undone by asserting on it
        afterwards. ``/api/v1/integrations/{id}/preview`` is this
        method; so is the test that pins Gmail's resolved URL.

        Building a request is not making one: no credential is read
        beyond the header this method attaches, and nothing leaves the
        process.
        """
        operation = self._spec.operation(operation_name)
        query, body = operation.split_params(params)
        base = (operation.base_url or self._spec.base_url).rstrip("/")
        url = f"{base}{operation.render_path(params)}"

        return GatewayRequest(
            integration_id=self.provider_id,
            operation=operation_name,
            method=operation.method,
            url=url,
            query=query,
            body=body if (body or operation.mutating) else None,
            headers=self._auth_headers(),
            account_key=self._account_key,
            cacheable=not operation.mutating,
        )

    # ------------------------------------------------------------------
    # Health / status
    # ------------------------------------------------------------------
    async def health(self) -> HealthStatus:
        """Cheap and local -- never a vendor call.

        ``HealthMonitor`` polls this on a cadence; making it reach the
        network would turn a health poll into quota spend and would fail
        a healthy integration whenever a vendor had a slow minute.
        """
        if not self._initialized:
            return HealthStatus(healthy=False, detail="Integration is not initialized.")
        if not self._connected:
            return HealthStatus(
                healthy=False, detail=self._error or "Integration is not connected."
            )
        if not self._auth.validate(self.provider_id):
            return HealthStatus(healthy=False, detail="Credential is missing, expired or revoked.")
        return HealthStatus(healthy=True)

    async def status(self) -> ServiceStatus:
        auth_status = self._auth.status(self.provider_id)
        return ServiceStatus(
            name=f"integration:{self.provider_id}",
            state="connected" if self._connected else "disconnected",
            detail={
                "vendor": self._spec.vendor,
                "base_url": self._spec.base_url,
                "operations": list(self._spec.operation_names),
                "capabilities": list(self._capabilities.names),
                "granted_permissions": sorted(self._granted_scopes),
                "required_permissions": list(self._spec.required_permissions),
                "required_vendor_scopes": list(self._spec.required_scopes),
                "credential": auth_status.get("credential"),
                "authenticated": auth_status.get("authenticated", False),
                "calls": self._calls,
                "failures": self._failures,
                "availability_note": self._spec.availability_note,
                "error": self._error,
            },
        )

    # ------------------------------------------------------------------
    # Connection Testing (Milestone 11 Task Group B)
    # ------------------------------------------------------------------
    async def test_connection(
        self,
        *,
        operation: str | None = None,
        timeout_seconds: float = DEFAULT_CONNECTION_TEST_TIMEOUT_SECONDS,
    ) -> ConnectionTestResult:
        """The explicit, user-triggered "does this actually work right
        now" check. Deliberately distinct from :meth:`health` (Task
        Group C, local-only, periodic, never a vendor call): this makes
        exactly one real, bounded, read-only HTTP request.

        Usable whether or not :meth:`start` has been called -- testing
        credentials *before* activating is the ordinary case this
        exists for, not an edge case.

        Never retried at the gateway (``GatewayRequest.single_attempt``
        below): a retry would turn a diagnostic into "try until it
        works", which is not what a caller pressing "Test Connection"
        asked for. Never raises -- every failure mode becomes a
        classified, secret-free :class:`ConnectionTestResult`.

        The vendor target always comes from this provider's own
        :class:`IntegrationSpec` -- an *existing, catalogued* operation
        name may be requested, never a URL. An unknown or mutating
        operation name is refused before anything is built, which is
        what keeps this from ever becoming "call whatever URL the
        caller supplies" (SSRF).
        """
        started = time.monotonic()
        bounded_timeout = min(timeout_seconds, MAX_CONNECTION_TEST_TIMEOUT_SECONDS)

        try:
            probe = self._resolve_probe_operation(operation)
        except IntegrationError as err:
            return ConnectionTestResult(
                integration_id=self.provider_id,
                outcome="failure",
                error_code="unsupported_capability",
                message=str(err),
            )

        allowed, reason = self._auth.authorize_capability(
            self.provider_id,
            required_permissions=probe.permissions,
            required_scopes=probe.scopes,
        )
        if not allowed:
            # `reason` is already secret-free -- provider id, credential
            # *status* name, permission/scope names, never a token
            # value (see MCPAuthManager.authorize_capability).
            return ConnectionTestResult(
                integration_id=self.provider_id,
                outcome="failure",
                error_code=_classify_authorization_reason(reason),
                message=reason,
            )

        request = self.build_request(probe.name, _probe_params(probe))
        request = replace(request, timeout_seconds=bounded_timeout, single_attempt=True)

        try:
            result = await self._gateway.send(request)
        except GatewayError as err:
            error_code = _classify_gateway_error(err)
            _logger.info("Connection test for {!r} failed: {}", self.provider_id, error_code)
            return ConnectionTestResult(
                integration_id=self.provider_id,
                outcome="failure",
                error_code=error_code,
                status_code=err.status_code,
                latency_ms=(time.monotonic() - started) * 1000,
                message=_SAFE_GATEWAY_ERROR_MESSAGES.get(error_code, "The vendor request failed."),
            )

        latency_ms = (time.monotonic() - started) * 1000
        if _looks_malformed(result.data):
            return ConnectionTestResult(
                integration_id=self.provider_id,
                outcome="failure",
                error_code="malformed_response",
                status_code=result.status_code,
                latency_ms=latency_ms,
                message="The vendor responded, but not in the expected shape.",
            )

        _logger.info("Connection test for {!r} succeeded.", self.provider_id)
        return ConnectionTestResult(
            integration_id=self.provider_id,
            outcome="success",
            status_code=result.status_code,
            latency_ms=latency_ms,
            message="Connected successfully.",
        )

    def _resolve_probe_operation(self, operation_name: str | None) -> OperationSpec:
        """The smallest safe read for a connection test.

        A caller-supplied name must already exist on this integration's
        own spec (never a URL, never an arbitrary vendor path) and must
        not mutate anything. Left unspecified, the first zero-argument
        read/search operation is chosen automatically -- one that needs
        no parameter beyond the handful with a well-known safe default
        (``user_id``/``calendar_id``, the same convention
        ``IntegrationService``'s search mapping already uses).
        """
        if operation_name is not None:
            operation = self._spec.operation(operation_name)
            if operation.mutating:
                raise IntegrationError(
                    f"Operation {operation_name!r} is not safe for a connection test "
                    "(it mutates vendor state) -- choose a read or search operation."
                )
            return operation

        for candidate in self._spec.operations:
            if candidate.category not in ("read", "search"):
                continue
            if candidate.required:
                continue
            if any(name not in _SAFE_PROBE_PATH_DEFAULTS for name in candidate.path_params):
                continue
            return candidate
        raise IntegrationError(
            f"Integration {self.provider_id!r} declares no zero-argument read/search "
            "operation suitable for an automatic connection test; specify one explicitly."
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    @property
    def _account_key(self) -> str:
        """Cache and audit key. Includes the account so one user's
        cached inbox can never be served to another."""
        return f"{self.provider_id}:{self._account_id}"

    def _auth_headers(self) -> dict[str, str]:
        """Through ``MCPAuthManager.auth_header`` -- the one sanctioned
        route a token takes out of the auth subsystem. This class never
        reads a credential, so a token cannot reach a log line here."""
        return self._auth.auth_header(
            self.provider_id,
            header=self._spec.auth.header,
            prefix=self._spec.auth.header_prefix,
        )

    async def _refresh_if_due(self) -> None:
        """Refresh a nearly-expired credential before the call, not after
        a 401.

        Best-effort: a refresh that fails leaves the existing token in
        place, and the call proceeds. If the token really is dead the
        vendor says so, and that error names the vendor's own reason --
        which is more useful than this method deciding in advance.
        """
        if not self._auth.needs_refresh(self.provider_id, leeway_seconds=REFRESH_LEEWAY_SECONDS):
            return
        try:
            await self._auth.refresh(self.provider_id)
        except Exception as err:
            _logger.warning(
                "Pre-call refresh for {!r} failed; using the existing token: {}",
                self.provider_id,
                err,
            )


# ---------------------------------------------------------------------------
# Connection Testing helpers (Milestone 11 Task Group B)
# ---------------------------------------------------------------------------
def _probe_params(operation: OperationSpec) -> dict[str, str]:
    """Fill only the path parameters that have a well-known safe
    default -- see ``_SAFE_PROBE_PATH_DEFAULTS``.
    ``_resolve_probe_operation`` already refused any candidate with a
    path parameter outside that set, so this never needs a fallback."""
    return {
        name: _SAFE_PROBE_PATH_DEFAULTS[name]
        for name in operation.path_params
        if name in _SAFE_PROBE_PATH_DEFAULTS
    }


#: Sub-reasons for the "not authenticated" gate, keyed by the
#: ``CredentialStatus`` name ``authorize_capability`` interpolates.
_CREDENTIAL_STATUS_ERROR_CODES: dict[str, str] = {
    "missing": "credential_missing",
    "expired": "credential_expired",
    "revoked": "credential_revoked",
}

#: HTTP status -> error code, for the statuses with an unambiguous
#: meaning. Anything else falls through to the 5xx range check or the
#: generic ``vendor_error`` in ``_classify_gateway_error``.
_STATUS_ERROR_CODES: dict[int, str] = {
    401: "authentication_failed",
    403: "authorization_failed",
    404: "configuration_error",
    408: "timeout",
    429: "rate_limited",
}


def _classify_authorization_reason(reason: str) -> str:
    """``MCPAuthManager.authorize_capability``'s reason strings are
    already secret-free (provider id, credential *status* name,
    permission/scope names -- never a token value); this only adds a
    stable, machine-readable code on top of an already-safe message."""
    if "is not authenticated" in reason:
        for status_name, code in _CREDENTIAL_STATUS_ERROR_CODES.items():
            if f"status: {status_name}" in reason:
                return code
        return "authentication_failed"
    if "JARVIS permission" in reason:
        return "forbidden"
    if "does not carry provider scope" in reason:
        return "forbidden_scope"
    return "authentication_failed"  # pragma: no cover -- exhaustive per authorize_capability


def _classify_gateway_error(err: GatewayError) -> str:
    if err.kind == "timeout":
        return "timeout"
    status = err.status_code
    if status is None:
        return "network_error"
    if status in _STATUS_ERROR_CODES:
        return _STATUS_ERROR_CODES[status]
    if 500 <= status < 600:
        return "vendor_unavailable"
    return "vendor_error"


def _looks_malformed(data: Any) -> bool:
    """``ApiGateway``'s own JSON-parse-failure fallback wraps unparsed
    text as ``{"raw": ...}`` (see ``gateway.py``'s ``_parse``) -- the
    same signal this reuses rather than re-parsing the body a second
    time. A 2xx status is not automatically success."""
    return not isinstance(data, dict) or set(data.keys()) == {"raw"}
