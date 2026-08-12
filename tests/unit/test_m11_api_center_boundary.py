"""M11 Task Group A -- API Center boundary tests.

Proves the M5/M11 coexistence decision in
``docs/M11_API_CENTER_ARCHITECTURE_DECISIONS.md`` is real in code, not
only in documentation: M5 remains the sole owner of generic/LLM-category
credentials, M11 (``core/integrations/``) owns only catalogue-backed
vendors, neither introduces a duplicate credential store or provider
registry, and M11 never reaches into ``ILLMProvider``/AI-routing
territory. No network calls, no ``unittest.mock`` -- every check is
either a real-component construction (matching
``tests/unit/test_integration_provider.py``'s pattern) or a static scan
of the actual shipped source.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from jarvis.core.config.settings import Settings
from jarvis.core.events.event_bus import EventBus
from jarvis.core.integrations.catalogue import available_ids, build_spec
from jarvis.core.integrations.gateway import ApiGateway
from jarvis.core.mcp.auth.manager import MCPAuthManager
from jarvis.core.mcp.auth.store import CredentialStore
from jarvis.core.mcp.auth.strategies import build_default_strategy_registry
from jarvis.core.mcp.client import MCPClientRuntime
from jarvis.core.mcp.providers.manager import MCPProviderManager
from jarvis.core.mcp.providers.registry import MCPProviderRegistry
from jarvis.core.mcp.transport import TransportFactoryRegistry
from jarvis.core.plugins.permissions import PermissionModel
from jarvis.domain.api_center.models import ApiAuthType, ApiCategory, ApiDefinition
from jarvis.services.api_center_service import ApiCenterService
from jarvis.services.integration_service import IntegrationService

_SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "jarvis"

# ---------------------------------------------------------------------------
# M5 owns generic / LLM-category credentials
# ---------------------------------------------------------------------------


def test_m5_owns_llm_category_credential(tmp_path: Path) -> None:
    """An LLM-category API key is stored and retrieved by ApiCenterService
    -- M11's existence does not change this."""
    settings = Settings(data_dir=tmp_path)
    service = ApiCenterService(settings)
    llm_api = service.add_api(
        ApiDefinition(
            name="Team OpenAI Key",
            provider="OpenAI",
            category=ApiCategory.LLM,
            auth_type=ApiAuthType.API_KEY,
            api_key="sk-test-key",
        )
    )
    fetched = service.get(llm_api.id)
    assert fetched.category is ApiCategory.LLM
    assert fetched.api_key == "sk-test-key"


# ---------------------------------------------------------------------------
# M11 owns catalogue-backed vendors
# ---------------------------------------------------------------------------


def test_m11_owns_catalogue_backed_integration() -> None:
    """A real catalogue entry (Google Workspace) resolves through
    core/integrations/ as a typed IntegrationSpec, never as an
    ApiDefinition row."""
    integration_id = available_ids()[0]
    spec = build_spec(integration_id)
    assert spec.vendor == "google"
    assert spec.operations


# ---------------------------------------------------------------------------
# M11 reuses existing credential + registry infrastructure -- identity
# checks prove no shadow instance was introduced anywhere in the chain.
# ---------------------------------------------------------------------------


@pytest.fixture()
def _integration_env(tmp_path: Path):
    bus = EventBus()
    permissions = PermissionModel(bus, store_path=tmp_path / "permissions.json")
    credential_store = CredentialStore(tmp_path / "mcp_credentials.json", secret_key="")
    auth_manager = MCPAuthManager(
        credential_store, build_default_strategy_registry(), permissions, event_bus=bus
    )
    provider_registry = MCPProviderRegistry()
    provider_manager = MCPProviderManager(
        provider_registry,
        client_runtime=MCPClientRuntime(),
        transport_registry=TransportFactoryRegistry(),
        permission_model=permissions,
        event_bus=bus,
    )
    gateway = ApiGateway(max_attempts=1, backoff_seconds=0.0)
    settings = Settings(data_dir=tmp_path)
    integration_service = IntegrationService(
        provider_manager=provider_manager,
        auth_manager=auth_manager,
        gateway=gateway,
        settings=settings,
    )
    return {
        "integration_service": integration_service,
        "provider_manager": provider_manager,
        "provider_registry": provider_registry,
        "auth_manager": auth_manager,
        "credential_store": credential_store,
    }


def test_m11_reuses_existing_provider_manager_and_registry(_integration_env: dict) -> None:
    """IntegrationService holds no registry of its own -- it is the same
    MCPProviderManager/MCPProviderRegistry every other MCP provider uses."""
    env = _integration_env
    assert env["integration_service"]._providers is env["provider_manager"]
    assert env["provider_manager"].registry is env["provider_registry"]


def test_m11_reuses_existing_credential_store(_integration_env: dict) -> None:
    """IntegrationService authenticates through the same MCPAuthManager,
    backed by the same CredentialStore -- no second store."""
    env = _integration_env
    assert env["integration_service"]._auth is env["auth_manager"]
    assert env["auth_manager"]._store is env["credential_store"]


# ---------------------------------------------------------------------------
# No duplicate credential store or provider registry anywhere in source
# ---------------------------------------------------------------------------

_FORBIDDEN_CLASS_NAMES = (
    "M11CredentialStore",
    "VendorCredentialStore",
    "IntegrationCredentialStore",
)


def test_no_shadow_credential_store_introduced() -> None:
    """None of the explicitly-forbidden duplicate-credential-store class
    names (Logic Contract Step 5) exist anywhere in shipped source."""
    hits: list[str] = []
    for py_file in _SRC_ROOT.rglob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name in _FORBIDDEN_CLASS_NAMES:
                hits.append(f"{py_file}:{node.lineno} defines {node.name}")
    assert not hits, hits


# ---------------------------------------------------------------------------
# M11 never reaches into ILLMProvider / AI-routing territory
# ---------------------------------------------------------------------------

_M11_FILES = (
    "core/integrations/provider.py",
    "core/integrations/gateway.py",
    "core/integrations/catalogue.py",
    "core/integrations/models.py",
    "core/integrations/google.py",
    "services/integration_service.py",
)

_FORBIDDEN_SUBSTRINGS = ("ILLMProvider", "infrastructure.llm", "FallbackLLMProvider")


def test_m11_never_references_illm_provider_or_ai_routing() -> None:
    """M11's own files never import or name ILLMProvider, infrastructure.llm,
    or FallbackLLMProvider -- the AI Calibration boundary (Logic Contract
    §26) holds structurally, not just by convention."""
    hits: list[str] = []
    for relative in _M11_FILES:
        text = (_SRC_ROOT / relative).read_text(encoding="utf-8")
        for needle in _FORBIDDEN_SUBSTRINGS:
            if needle in text:
                hits.append(f"{relative}: contains {needle!r}")
    assert not hits, hits
