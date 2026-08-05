"""Integration Platform — Milestone 11 Task Group E.

Every connector is an MCP provider: declared as data (:mod:`models`),
executed through one audited egress point (:mod:`gateway`), driven by
M10.5's provider lifecycle (:mod:`provider`), authenticated by M10.5's
auth framework plus the OAuth2 grants this milestone adds
(``core/mcp/auth/oauth2.py``).
"""

from __future__ import annotations

from jarvis.core.integrations.catalogue import (
    AVAILABLE_SPECS,
    available_ids,
    build_all,
    build_spec,
    describe_catalogue,
    vendors,
)
from jarvis.core.integrations.gateway import (
    ApiGateway,
    GatewayError,
    GatewayRequest,
    GatewayResult,
)
from jarvis.core.integrations.models import (
    HTTP_METHODS,
    MUTATING_METHODS,
    OPERATION_CATEGORIES,
    AuthSpec,
    IntegrationError,
    IntegrationSpec,
    OperationSpec,
)
from jarvis.core.integrations.provider import RestIntegrationProvider

__all__ = [
    "AVAILABLE_SPECS",
    "HTTP_METHODS",
    "MUTATING_METHODS",
    "OPERATION_CATEGORIES",
    "ApiGateway",
    "AuthSpec",
    "GatewayError",
    "GatewayRequest",
    "GatewayResult",
    "IntegrationError",
    "IntegrationSpec",
    "OperationSpec",
    "RestIntegrationProvider",
    "available_ids",
    "build_all",
    "build_spec",
    "describe_catalogue",
    "vendors",
]
