"""MCP SDK -- Milestone 10.5 Task Group E.

The developer-facing surface for building an MCP provider, without
touching the runtime's internals. Everything here composes the existing
models and registries; no new runtime type is introduced, and nothing in
``core/mcp/`` imports this package -- the dependency runs one way, so
the SDK can be reshaped without risk to the platform.

A provider author needs four things, in this order::

    from jarvis.core.mcp.sdk import (
        CapabilityBuilder, ProviderBuilder, TransportBuilder, ConfigBuilder,
        register_provider,
    )

    capability = (
        CapabilityBuilder("myservice.search")
        .describe("Searches the thing.")
        .with_permission("network")
        .build()
    )

    metadata = (
        ProviderBuilder("My Service")
        .transport("stdio")
        .with_capability(capability)
        .with_permission("network")
        .build()
    )

    config = ConfigBuilder().from_transport(
        TransportBuilder("stdio").command("my-mcp-server", "--stdio")
    ).build(metadata)

    await register_provider(manager, "myservice", metadata, config)

``build()`` validates and raises with the complete problem list, so a
mistake surfaces while writing the provider rather than at connect time.
Prefer the raw dataclasses if you would rather -- they stay public, and
the builders are a convenience, not a gate.

See ``examples.py`` for a runnable, self-contained reference that
connects to nothing.
"""

from __future__ import annotations

from jarvis.core.mcp.sdk.builders import (
    AuthBuilder,
    CapabilityBuilder,
    ConfigBuilder,
    ProviderBuilder,
    SDKValidationError,
    TransportBuilder,
    capability_names,
    expose_capabilities,
    register_provider,
)
from jarvis.core.mcp.sdk.validation import (
    Severity,
    ValidationIssue,
    ValidationReport,
    validate_auth,
    validate_capabilities,
    validate_capability,
    validate_provider_config,
    validate_provider_metadata,
    validate_registry_consistency,
    validate_transport_config,
)

__all__ = [
    "AuthBuilder",
    "CapabilityBuilder",
    "ConfigBuilder",
    "ProviderBuilder",
    "SDKValidationError",
    "Severity",
    "TransportBuilder",
    "ValidationIssue",
    "ValidationReport",
    "capability_names",
    "expose_capabilities",
    "register_provider",
    "validate_auth",
    "validate_capabilities",
    "validate_capability",
    "validate_provider_config",
    "validate_provider_metadata",
    "validate_registry_consistency",
    "validate_transport_config",
]
