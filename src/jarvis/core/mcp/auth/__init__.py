"""MCP Authentication Framework -- Milestone 10.5 Task Group D.

Infrastructure only: the authentication framework every future MCP
provider plugs into. **No real providers**, no vendor code, no OAuth
flow (which needs an authorization server and a callback endpoint --
both explicitly out of this task group's scope).

The split mirrors ``core/mcp/providers/``'s own:

- ``credentials.py`` -- the credential model and the method vocabulary.
  Redacts its own ``repr``; offers separate storage and public
  serializers so "safe to show" is a deliberate choice, not an
  accident.
- ``store.py`` -- encrypted-at-rest persistence, reusing the existing
  Fernet helpers and config-dir convention. Refuses to write when no
  real key is configured rather than falling back to plaintext.
- ``strategies.py`` -- one strategy per authentication method, in a
  registry a future method plugs into.
- ``session.py`` -- per-provider authentication state. Not M9's
  ``SessionManager``, which owns *user* sessions.
- ``manager.py`` -- lifecycle, the permission bridge, and the health
  payload.
"""

from __future__ import annotations

from jarvis.core.mcp.auth.credentials import (
    DEFAULT_EXPIRY_WARNING_SECONDS,
    REFRESHABLE_METHODS,
    STATIC_METHODS,
    AuthMethod,
    Credential,
    CredentialStatus,
    EncryptionMetadata,
    MCPAuthError,
)
from jarvis.core.mcp.auth.manager import AUTH_ACTIONS, MCPAuthManager
from jarvis.core.mcp.auth.session import ProviderSession, SessionState
from jarvis.core.mcp.auth.store import CredentialEncryptionError, CredentialStore
from jarvis.core.mcp.auth.strategies import (
    AuthStrategyRegistry,
    IAuthStrategy,
    NoAuthStrategy,
    StaticTokenStrategy,
    UnsupportedAuthMethodError,
    build_default_strategy_registry,
)

__all__ = [
    "AUTH_ACTIONS",
    "DEFAULT_EXPIRY_WARNING_SECONDS",
    "REFRESHABLE_METHODS",
    "STATIC_METHODS",
    "AuthMethod",
    "AuthStrategyRegistry",
    "Credential",
    "CredentialEncryptionError",
    "CredentialStatus",
    "CredentialStore",
    "EncryptionMetadata",
    "IAuthStrategy",
    "MCPAuthError",
    "MCPAuthManager",
    "NoAuthStrategy",
    "ProviderSession",
    "SessionState",
    "StaticTokenStrategy",
    "UnsupportedAuthMethodError",
    "build_default_strategy_registry",
]
