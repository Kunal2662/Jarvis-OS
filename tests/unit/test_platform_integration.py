"""Platform integration tests -- Milestone 11 Task Group F.

The audits this task group performed, turned into tests so they cannot
quietly regress. Each one pins an invariant that held when it was
checked and that a later milestone could break without noticing:

* one health channel, and every M11 subsystem reporting into it;
* one registration per search source, none missing, none doubled;
* one relay name per event, and every declared event either relayed or
  on the documented exception list;
* one DI provider per name, and no name silently bound twice;
* every settings section under the shared env prefix.
"""

from __future__ import annotations

import asyncio
import inspect
from pathlib import Path

import pytest

from jarvis.core.events import events as events_module
from jarvis.core.lifecycle.runtime_ws_hub import EVENT_TYPE_NAMES, UNPUBLISHED_EVENT_TYPES


@pytest.fixture
def container(tmp_path: Path):
    from jarvis.core.config.settings import Settings
    from jarvis.core.di.container import Container

    container = Container()
    settings = Settings(data_dir=str(tmp_path / "data"))
    settings.db.url = f"sqlite+aiosqlite:///{tmp_path / 'jarvis.db'}"
    container.settings.override(settings)
    asyncio.run(container.database().initialize())
    return container


# --- health: one channel, every subsystem in it ---------------------------------


def test_the_workspace_platform_reports_into_the_shared_health_monitor(container, tmp_path) -> None:
    """Task Groups A-E shipped five subsystems and none of them reported
    anything to HealthMonitor. This is the one collector that closes
    that -- registered on the existing extension point, not a second
    health subsystem."""
    from jarvis.app import ApplicationBootstrapper

    settings = container.settings()
    monitor = container.health_monitor()
    boot = ApplicationBootstrapper.__new__(ApplicationBootstrapper)
    boot._container = container
    boot._register_workspace_platform_hooks(settings, monitor)

    snapshot = asyncio.run(monitor.snapshot())

    assert "workspace_platform" in snapshot
    platform = snapshot["workspace_platform"]
    assert set(platform) == {"files", "ai_workspace", "egress", "search_sources"}
    assert platform["files"]["storage_root"].endswith("files")
    assert platform["egress"]["calls"] == 0
    assert "workspaces" in platform["search_sources"]


def test_the_platform_collector_never_counts_rows(container) -> None:
    """It runs on the health poll's cadence, so it reports signals the
    subsystems already hold. A poll that scanned the workspace tables
    would make observability cost more than the thing observed."""
    from jarvis.app import ApplicationBootstrapper

    monitor = container.health_monitor()
    boot = ApplicationBootstrapper.__new__(ApplicationBootstrapper)
    boot._container = container
    boot._register_workspace_platform_hooks(container.settings(), monitor)

    snapshot = asyncio.run(monitor.snapshot())
    rendered = str(snapshot["workspace_platform"])

    for forbidden in ("workspace_count", "note_count", "file_count", "task_count"):
        assert forbidden not in rendered


def test_integrations_are_not_repeated_in_the_platform_collector(container) -> None:
    """An integration is an MCP provider, so it is already reported
    under the `mcp` collector. Two answers to one question is exactly
    what this task group audits for."""
    from jarvis.app import ApplicationBootstrapper

    monitor = container.health_monitor()
    boot = ApplicationBootstrapper.__new__(ApplicationBootstrapper)
    boot._container = container
    boot._register_workspace_platform_hooks(container.settings(), monitor)

    platform = asyncio.run(monitor.snapshot())["workspace_platform"]

    assert "providers" not in platform
    assert "integrations" not in platform


# --- search: exactly once, nothing missing --------------------------------------


def test_every_search_source_is_registered_exactly_once(container) -> None:
    types = [source.source_type for source in container.search_service().get_sources()]

    assert len(types) == len(set(types))


def test_the_expected_search_sources_are_all_present(container) -> None:
    """Thirteen at rest; a connected integration adds a fourteenth at
    runtime (proved in the Task Group E end-to-end suite)."""
    types = {source.source_type for source in container.search_service().get_sources()}

    assert types == {
        "memory",
        "knowledge",
        "goals",
        "commands",
        "workspaces",
        "projects",
        "notes",
        "tasks",
        "calendar",
        "reminders",
        "files",
        "folders",
        "attachments",
    }


# --- events: one name each, nothing undocumented --------------------------------


def test_every_declared_event_is_relayed_or_documented_as_absent() -> None:
    declared = {
        obj
        for obj in vars(events_module).values()
        if inspect.isclass(obj)
        and issubclass(obj, events_module.Event)
        and obj is not events_module.Event
    }
    absent = {cls.__name__ for cls in declared - set(EVENT_TYPE_NAMES)}

    assert absent == {*UNPUBLISHED_EVENT_TYPES, "DebugLogCapturedEvent"}


def test_no_two_events_share_a_relay_name() -> None:
    names = list(EVENT_TYPE_NAMES.values())

    assert len(names) == len(set(names))


def test_every_relay_name_is_lowercase_category_dot_event() -> None:
    """``docs/ARCHITECTURE.md`` §6's naming rule, enforced rather than
    described."""
    for name in EVENT_TYPE_NAMES.values():
        assert name == name.lower(), name
        assert name.count(".") == 1, name


# --- dependency injection -------------------------------------------------------


def test_no_provider_name_is_bound_twice_in_the_container() -> None:
    """`memory_recall_hook` was bound twice before this task group: an
    earlier no-op registration that the real one silently replaced.
    Behaviour was right, but a reader following the first binding would
    have concluded recall was disabled."""
    import collections
    import re

    source = Path("src/jarvis/core/di/container.py").read_text(encoding="utf-8")
    body = source.split("class Container(", 1)[1]
    assigned = re.findall(r"^    ([a-z_][a-z0-9_]*) = providers\.", body, re.M)

    duplicated = [name for name, count in collections.Counter(assigned).items() if count > 1]
    assert duplicated == []


def test_the_memory_recall_hook_is_the_real_one(container) -> None:
    assert type(container.memory_recall_hook()).__name__ == "SemanticMemoryRecallHook"


def test_the_m11_services_are_singletons(container) -> None:
    """A second instance would mean a second gateway pool, a second set
    of installed integrations, or a second in-flight OAuth flow store --
    each of which would break something subtle and intermittently."""
    for name in (
        "workspace_service",
        "workspace_knowledge_service",
        "workspace_assistant_service",
        "integration_service",
        "api_gateway",
        "oauth_flow_store",
        "search_service",
        "mcp_provider_manager",
        "mcp_auth_manager",
    ):
        provider = getattr(container, name)
        assert provider() is provider(), name


# --- settings -------------------------------------------------------------------


def test_every_settings_section_uses_the_shared_env_prefix() -> None:
    from pydantic_settings import BaseSettings

    from jarvis.core.config.settings import ENV_PREFIX, Settings

    for name, field in Settings.model_fields.items():
        annotation = field.annotation
        if not (inspect.isclass(annotation) and issubclass(annotation, BaseSettings)):
            continue
        prefix = (annotation.model_config or {}).get("env_prefix", "")
        assert prefix.startswith(ENV_PREFIX), f"{name} -> {prefix}"


def test_no_two_settings_sections_share_an_env_prefix() -> None:
    """A shared prefix would make one section silently shadow another's
    variables."""
    import collections
    import inspect as _inspect

    from pydantic_settings import BaseSettings

    from jarvis.core.config.settings import Settings

    prefixes = [
        (f.annotation.model_config or {}).get("env_prefix", "")
        for f in Settings.model_fields.values()
        if _inspect.isclass(f.annotation) and issubclass(f.annotation, BaseSettings)
    ]

    assert [p for p, c in collections.Counter(prefixes).items() if c > 1] == []


def test_every_settings_section_builds_from_defaults() -> None:
    """Local-first: a fresh install with no .env must start."""
    from pydantic_settings import BaseSettings

    from jarvis.core.config.settings import Settings

    for field in Settings.model_fields.values():
        annotation = field.annotation
        if inspect.isclass(annotation) and issubclass(annotation, BaseSettings):
            annotation()  # raises if a field is required with no default
