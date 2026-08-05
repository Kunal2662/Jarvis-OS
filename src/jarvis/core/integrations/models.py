"""Integration specifications -- Milestone 11 Task Group E.

The declarative half of the Integration Platform: what a vendor
integration *is*, expressed as data rather than as a class per vendor.
Pure -- no I/O, no network, no container -- so a specification can be
validated, described and tested without anything being connected, the
same property ``ProviderMetadata`` (M10.5 Task Group C) already has and
for the same reason.

**Why connectors are data.** Gmail, Drive, GitHub, Slack and Jira are
the same shape: an OAuth2-authenticated REST API with resources and
operations. Writing a class per vendor would mean thirty
implementations of one pattern, thirty places for a retry bug to hide,
and thirty things to keep in step when the gateway changes. An
:class:`IntegrationSpec` names the endpoints; one tested engine
(``core/integrations/provider.py`` + ``gateway.py``) executes them.
Adding a vendor is a spec, reviewed against that vendor's published API
reference -- not a new subsystem.

**Two permission vocabularies, deliberately kept apart.**
:attr:`OperationSpec.permissions` are JARVIS's own
``PERMISSION_SCOPES`` -- what the operator has allowed JARVIS to do.
:attr:`OperationSpec.scopes` are the *vendor's* OAuth scopes -- what the
token actually carries. Both gates must pass, which is exactly the
distinction ``MCPAuthManager.authorize_capability`` already draws; this
module supplies its two inputs and adds no third vocabulary.

**Paths are templates, and that is a security boundary.** An operation
declares ``/gmail/v1/users/{user_id}/messages``; the caller supplies
``user_id``. Callers never supply a path. Every placeholder is
substituted through one escaping function
(:func:`OperationSpec.render_path`), and a parameter that is not
declared is refused rather than passed through -- so a caller cannot
reach an endpoint the spec does not describe, and cannot smuggle a
query string into a path segment.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote, urlparse

from jarvis.core.interfaces.mcp import MCPCapability, MCPError
from jarvis.core.mcp.auth.credentials import AuthMethod
from jarvis.core.mcp.providers.metadata import ProviderMetadata
from jarvis.core.plugins.sdk import PERMISSION_SCOPES


class IntegrationError(MCPError):
    """An invalid integration declaration, or an illegal invocation.

    Inherits ``MCPError`` rather than starting a new exception family:
    an integration *is* an MCP provider in this architecture, and a
    caller already catching ``MCPError`` around provider work should not
    need a second except clause because the provider happened to be
    REST-backed.
    """


#: HTTP methods an operation may declare. Closed, like every other
#: vocabulary in this codebase: a typo'd method would otherwise reach
#: the gateway and fail as a confusing 405 from the vendor.
HTTP_METHODS: frozenset[str] = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE"})

#: Methods that change remote state. Used for two decisions the gateway
#: must not get wrong: a mutating call is never served from cache, and
#: it is never retried automatically (a retried "send email" sends two).
MUTATING_METHODS: frozenset[str] = frozenset({"POST", "PUT", "PATCH", "DELETE"})

#: What an operation is *for*, so a caller (and the agent) can find the
#: right one without reading every path. Advisory grouping, not a second
#: capability vocabulary -- ``MCPCapability.kind`` stays MCP's own three.
OPERATION_CATEGORIES: frozenset[str] = frozenset(
    {"read", "write", "search", "upload", "download", "admin"}
)

_PLACEHOLDER_RE = re.compile(r"\{([a-z][a-z0-9_]*)\}")
_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$")


@dataclass(frozen=True, slots=True)
class AuthSpec:
    """How one vendor authenticates.

    ``authorize_url``/``token_url`` are the vendor's own endpoints, so
    the OAuth2 strategy needs no per-vendor branch -- it reads them from
    here. ``client_id``/``client_secret`` are deliberately **absent**:
    those are deployment secrets, they arrive from ``Settings`` at
    connect time, and putting them in a spec would put them in source.
    """

    method: AuthMethod = AuthMethod.OAUTH2
    authorize_url: str = ""
    token_url: str = ""
    revoke_url: str = ""
    #: Vendor scopes requested when no operation-specific set is given.
    default_scopes: tuple[str, ...] = ()
    #: Extra parameters the vendor requires on the authorization URL --
    #: Google needs ``access_type=offline`` to issue a refresh token at
    #: all, which is the kind of vendor quirk that belongs in data.
    authorize_params: dict[str, str] = field(default_factory=dict)
    #: Where the access token goes. Every vendor here uses a bearer
    #: header; the field exists so one that does not can be described
    #: rather than special-cased in the gateway.
    header: str = "Authorization"
    header_prefix: str = "Bearer"

    def validate(self, integration_id: str) -> None:
        if self.method is AuthMethod.OAUTH2:
            for label, url in (
                ("authorize_url", self.authorize_url),
                ("token_url", self.token_url),
            ):
                if not url:
                    raise IntegrationError(
                        f"Integration {integration_id!r} uses oauth2 but declares no {label}."
                    )
                _require_https(url, f"{integration_id}.auth.{label}")
        if self.method is AuthMethod.CLIENT_CREDENTIALS and not self.token_url:
            raise IntegrationError(
                f"Integration {integration_id!r} uses client_credentials but declares no token_url."
            )
        if not self.header.strip():
            raise IntegrationError(f"Integration {integration_id!r} declares an empty auth header.")

    def as_dict(self) -> dict[str, Any]:
        return {
            "method": self.method.value,
            "authorize_url": self.authorize_url,
            "token_url": self.token_url,
            "revoke_url": self.revoke_url,
            "default_scopes": list(self.default_scopes),
            "header": self.header,
        }


@dataclass(frozen=True, slots=True)
class OperationSpec:
    """One callable vendor endpoint."""

    name: str
    method: str
    path: str
    description: str = ""
    category: str = "read"
    #: JARVIS-side scopes, from ``core/plugins/sdk.py``'s fixed set.
    permissions: tuple[str, ...] = ("network",)
    #: Vendor-side OAuth scopes this endpoint needs.
    scopes: tuple[str, ...] = ()
    #: Query parameters a caller may supply. Anything else is refused.
    query: tuple[str, ...] = ()
    #: JSON body fields a caller may supply. Anything else is refused.
    body: tuple[str, ...] = ()
    #: Path parameters that must be supplied. Derived from *path* when
    #: left empty, which is the normal case -- declaring them twice is
    #: how the two drift apart.
    required: tuple[str, ...] = ()
    #: Overrides the integration's ``base_url`` for the few endpoints a
    #: vendor hosts elsewhere (Google's upload host, for one).
    base_url: str = ""

    # ------------------------------------------------------------------
    # Derived
    # ------------------------------------------------------------------
    @property
    def path_params(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(_PLACEHOLDER_RE.findall(self.path)))

    @property
    def mutating(self) -> bool:
        return self.method in MUTATING_METHODS

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    def validate(self, integration_id: str) -> None:
        where = f"{integration_id}.{self.name}"
        if not _NAME_RE.match(self.name):
            raise IntegrationError(
                f"Operation name {self.name!r} in {integration_id!r} must be dotted "
                "lowercase (e.g. 'messages.list')."
            )
        if self.method not in HTTP_METHODS:
            raise IntegrationError(
                f"{where} declares unknown HTTP method {self.method!r}; "
                f"allowed: {sorted(HTTP_METHODS)}."
            )
        if not self.path.startswith("/"):
            raise IntegrationError(f"{where} path must start with '/': got {self.path!r}.")
        if self.category not in OPERATION_CATEGORIES:
            raise IntegrationError(
                f"{where} declares unknown category {self.category!r}; "
                f"allowed: {sorted(OPERATION_CATEGORIES)}."
            )
        unknown = sorted(set(self.permissions) - PERMISSION_SCOPES)
        if unknown:
            raise IntegrationError(
                f"{where} declares unknown JARVIS permission scope(s) {unknown}; "
                f"allowed: {sorted(PERMISSION_SCOPES)}."
            )
        if not self.permissions:
            raise IntegrationError(
                f"{where} declares no JARVIS permissions. Every outbound call needs at "
                "least 'network' -- an operation nothing gates is an operation nothing "
                "can refuse."
            )
        missing = sorted(
            set(self.required) - set(self.path_params) - set(self.query) - set(self.body)
        )
        if missing:
            raise IntegrationError(f"{where} marks {missing} required, but declares them nowhere.")
        if self.base_url:
            _require_https(self.base_url, where)

    # ------------------------------------------------------------------
    # Request construction -- the security boundary
    # ------------------------------------------------------------------
    def render_path(self, params: dict[str, Any]) -> str:
        """Substitute path placeholders from *params*.

        Every value is percent-encoded with ``safe=""``, so a value
        containing ``/``, ``?`` or ``..`` becomes one literal path
        segment instead of changing which endpoint is called. That is
        the whole reason callers pass parameters and never paths -- the
        same posture ``domain/files/safe_join`` takes toward the
        filesystem, applied to a URL.
        """
        missing = [name for name in self.path_params if not str(params.get(name, "")).strip()]
        if missing:
            raise IntegrationError(
                f"Operation {self.name!r} requires path parameter(s) {sorted(missing)}."
            )
        rendered = self.path
        for name in self.path_params:
            rendered = rendered.replace(f"{{{name}}}", quote(str(params[name]), safe=""))
        return rendered

    def split_params(self, params: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        """Partition *params* into ``(query, body)``.

        An undeclared parameter is refused rather than forwarded. A
        vendor would usually ignore it, but "usually" is not a security
        property: a forwarded parameter is a caller reaching an endpoint
        behaviour the spec does not describe, and the review that
        approved the spec never saw.
        """
        allowed = set(self.path_params) | set(self.query) | set(self.body)
        unknown = sorted(set(params) - allowed)
        if unknown:
            raise IntegrationError(
                f"Operation {self.name!r} does not accept parameter(s) {unknown}; "
                f"accepted: {sorted(allowed) or 'none'}."
            )
        missing = sorted(set(self.required) - {k for k, v in params.items() if v is not None})
        if missing:
            raise IntegrationError(f"Operation {self.name!r} requires parameter(s) {missing}.")

        query = {k: v for k, v in params.items() if k in self.query and v is not None}
        body = {k: v for k, v in params.items() if k in self.body and v is not None}
        return query, body

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------
    def to_capability(self, integration_id: str) -> MCPCapability:
        """The operation as an :class:`MCPCapability`.

        This is what makes "every connector is an MCP provider" true
        rather than decorative: an integration's operations are
        registered in the *same* ``MCPCapabilityRegistry`` an MCP peer's
        capabilities go into, carry the same permission scopes, and are
        described through the same ``/api/v1/mcp/capabilities`` surface.
        """
        return MCPCapability(
            name=f"{integration_id}.{self.name}",
            kind="tool",
            description=self.description,
            permissions=self.permissions,
            metadata={
                "integration_id": integration_id,
                "operation": self.name,
                "method": self.method,
                "category": self.category,
                "mutating": self.mutating,
                "vendor_scopes": list(self.scopes),
            },
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "method": self.method,
            "path": self.path,
            "description": self.description,
            "category": self.category,
            "mutating": self.mutating,
            "permissions": list(self.permissions),
            "scopes": list(self.scopes),
            "query": list(self.query),
            "body": list(self.body),
            "path_params": list(self.path_params),
            "required": list(self.required),
        }


@dataclass(frozen=True, slots=True)
class IntegrationSpec:
    """One vendor integration, whole."""

    integration_id: str
    name: str
    vendor: str
    base_url: str
    auth: AuthSpec
    operations: tuple[OperationSpec, ...] = ()
    description: str = ""
    version: str = "1.0.0"
    #: Free-form grouping for discovery -- "mail", "calendar", "storage".
    tags: tuple[str, ...] = ()
    #: The operation callers should use for Universal Search, when the
    #: vendor has one. Absent means this integration contributes no
    #: search source, which is the honest state for (say) a Drive upload
    #: endpoint rather than an empty source returning nothing.
    search_operation: str = ""
    #: Set when an integration cannot work on ordinary accounts. Carried
    #: as data so the REST surface can say so *before* a caller spends
    #: an OAuth round trip discovering it.
    availability_note: str = ""

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------
    def operation(self, name: str) -> OperationSpec:
        for operation in self.operations:
            if operation.name == name:
                return operation
        raise IntegrationError(
            f"Integration {self.integration_id!r} has no operation {name!r}. "
            f"Available: {sorted(op.name for op in self.operations)}."
        )

    def has_operation(self, name: str) -> bool:
        return any(op.name == name for op in self.operations)

    @property
    def operation_names(self) -> tuple[str, ...]:
        return tuple(op.name for op in self.operations)

    @property
    def required_permissions(self) -> tuple[str, ...]:
        return tuple(sorted({scope for op in self.operations for scope in op.permissions}))

    @property
    def required_scopes(self) -> tuple[str, ...]:
        """Every vendor scope any operation needs, plus the auth
        defaults -- what an authorization URL must ask for."""
        declared = {scope for op in self.operations for scope in op.scopes}
        return tuple(sorted(declared | set(self.auth.default_scopes)))

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    def validate(self) -> None:
        """Raises :class:`IntegrationError` on anything that must not be
        installed. Called at registration, so a malformed spec fails at
        declaration rather than at first call."""
        if not _NAME_RE.match(self.integration_id):
            raise IntegrationError(
                f"Integration id {self.integration_id!r} must be lowercase "
                "alphanumeric with underscores."
            )
        if not self.name.strip():
            raise IntegrationError(f"Integration {self.integration_id!r} has an empty name.")
        _require_https(self.base_url, self.integration_id)
        self.auth.validate(self.integration_id)

        if not self.operations:
            raise IntegrationError(
                f"Integration {self.integration_id!r} declares no operations. An "
                "integration that can do nothing is a connection waiting to disappoint."
            )
        seen: set[str] = set()
        for operation in self.operations:
            if operation.name in seen:
                raise IntegrationError(
                    f"Integration {self.integration_id!r} declares operation "
                    f"{operation.name!r} twice."
                )
            seen.add(operation.name)
            operation.validate(self.integration_id)

        if self.search_operation and not self.has_operation(self.search_operation):
            raise IntegrationError(
                f"Integration {self.integration_id!r} names search operation "
                f"{self.search_operation!r}, which it does not declare."
            )

    # ------------------------------------------------------------------
    # Bridge to the MCP provider framework
    # ------------------------------------------------------------------
    def to_metadata(self) -> ProviderMetadata:
        """The spec as M10.5 provider metadata.

        ``transport="http"`` is honest and deliberate: this provider
        reaches its peer over HTTP. What differs from the ``http``
        *transport* is the payload convention -- REST resources rather
        than JSON-RPC -- which is the provider implementation's business,
        not the transport vocabulary's. A sixth ``TRANSPORT_TYPES``
        member for a payload convention would make that vocabulary mean
        two things at once, so ``RestIntegrationProvider`` simply never
        asks ``TransportFactoryRegistry`` for a transport, and claims
        none.
        """
        return ProviderMetadata(
            name=self.name,
            version=self.version,
            author=self.vendor,
            description=self.description,
            capabilities=tuple(f"{self.integration_id}.{op}" for op in self.operation_names),
            transport="http",
            required_permissions=self.required_permissions,
            tags=(self.vendor, "integration", *self.tags),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "integration_id": self.integration_id,
            "name": self.name,
            "vendor": self.vendor,
            "description": self.description,
            "version": self.version,
            "base_url": self.base_url,
            "tags": list(self.tags),
            "auth": self.auth.as_dict(),
            "operations": [op.as_dict() for op in self.operations],
            "required_permissions": list(self.required_permissions),
            "required_scopes": list(self.required_scopes),
            "search_operation": self.search_operation,
            "availability_note": self.availability_note,
        }


def _require_https(url: str, where: str) -> None:
    """Refuse a non-HTTPS endpoint.

    This is the one place outbound egress could be downgraded to
    cleartext, and every vendor here publishes HTTPS endpoints -- so a
    plain-``http://`` URL in a spec is a mistake, not a deployment
    choice. ``localhost`` is exempted because that is how the fake
    server in this project's own tests is reached, and refusing it would
    mean the engine could only be tested against the real internet.
    """
    parsed = urlparse(url)
    if parsed.scheme == "https":
        return
    if parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}:
        return
    raise IntegrationError(
        f"{where} declares base URL {url!r}. Integration endpoints must be https "
        "(loopback is allowed for local test servers)."
    )
