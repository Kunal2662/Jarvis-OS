"""WorkspaceManager tests -- Milestone 11 Task Group A.

The manager's contract is that it *coordinates* and never computes or
stores. These assert both halves: every figure it returns matches what
the owning subsystem reports, and a missing or failing collaborator
costs context rather than the whole call.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.core.events.event_bus import EventBus
from jarvis.core.exceptions import ServiceError
from jarvis.core.interfaces.search import SearchResult
from jarvis.services.workspace_manager import WorkspaceManager
from jarvis.services.workspace_service import WorkspaceService


def _settings(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("JARVIS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("JARVIS_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'jarvis.db'}")

    from jarvis.core.config import settings as settings_mod

    settings_mod.load_settings.cache_clear()  # type: ignore[attr-defined]
    return settings_mod.load_settings()


@pytest.fixture
async def service(tmp_path: Path, monkeypatch):
    settings = _settings(tmp_path, monkeypatch)
    from jarvis.infrastructure.database.sqlite_client import SQLiteDatabase

    db = SQLiteDatabase(settings.db)
    await db.initialize()
    try:
        yield WorkspaceService(database=db, event_bus=EventBus())
    finally:
        await db.dispose()


class _Knowledge:
    async def search(self, query: str, *, top_k: int = 10) -> list[SearchResult]:
        return [
            SearchResult(
                id="k1",
                title=f"entity for {query}",
                content="",
                source="knowledge",
                score=1.0,
            )
        ]


class _Memory:
    async def recall(self, query: str, *, top_k: int = 10):
        from types import SimpleNamespace

        return [SimpleNamespace(id="m1", content=f"memory of {query}")]


class _Broken:
    async def search(self, query: str, *, top_k: int = 10):
        raise RuntimeError("index unavailable")

    async def recall(self, query: str, *, top_k: int = 10):
        raise RuntimeError("vector store down")


# --- overview -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_overview_gathers_the_four_reads(service: WorkspaceService) -> None:
    manager = WorkspaceManager(service)
    workspace = await service.create_workspace("Research", description="papers")
    await service.create_project(workspace.id, "P1")
    await service.create_note(workspace.id, "N1")

    overview = await manager.overview(workspace.id)

    assert overview["workspace"]["name"] == "Research"
    assert [p["name"] for p in overview["projects"]] == ["P1"]
    assert [n["title"] for n in overview["notes"]] == ["N1"]
    assert overview["metadata"]["project_count"] == 1
    assert overview["settings"]["color"] == ""


@pytest.mark.asyncio
async def test_overview_numbers_match_the_owning_service(service: WorkspaceService) -> None:
    """Collected, not recomputed. If these ever disagree the manager has
    grown its own idea of the truth."""
    manager = WorkspaceManager(service)
    workspace = await service.create_workspace("W")
    await service.create_project(workspace.id, "P")
    await service.create_note(workspace.id, "N")

    overview = await manager.overview(workspace.id)

    assert overview["metadata"] == (await service.metadata(workspace.id)).as_dict()
    assert len(overview["projects"]) == len(await service.list_projects(workspace_id=workspace.id))


@pytest.mark.asyncio
async def test_overview_of_an_unknown_workspace_raises(service: WorkspaceService) -> None:
    with pytest.raises(ServiceError, match="does not exist"):
        await WorkspaceManager(service).overview("nope")


# --- context --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_context_adds_the_neighbouring_subsystems(service: WorkspaceService) -> None:
    manager = WorkspaceManager(service, knowledge_service=_Knowledge(), memory_service=_Memory())
    workspace = await service.create_workspace("Quantum", description="research")

    context = await manager.context(workspace.id)

    # The overview's keys are all still there -- the shape is additive,
    # which is what lets Task Groups B-D extend it.
    assert set(context) >= {"workspace", "settings", "metadata", "projects", "notes"}
    assert context["related_knowledge"][0]["id"] == "k1"
    assert context["related_memories"][0]["id"] == "m1"


@pytest.mark.asyncio
async def test_context_without_collaborators_is_still_a_context(
    service: WorkspaceService,
) -> None:
    """A partially-wired container degrades to less context, not an
    error."""
    workspace = await service.create_workspace("Alone")

    context = await WorkspaceManager(service).context(workspace.id)

    assert context["related_knowledge"] == []
    assert context["related_memories"] == []
    assert context["workspace"]["name"] == "Alone"


@pytest.mark.asyncio
async def test_a_failing_collaborator_costs_context_not_the_call(
    service: WorkspaceService,
) -> None:
    broken = _Broken()
    manager = WorkspaceManager(service, knowledge_service=broken, memory_service=broken)
    workspace = await service.create_workspace("Resilient")

    context = await manager.context(workspace.id)

    assert context["related_knowledge"] == []
    assert context["related_memories"] == []
    assert context["workspace"]["name"] == "Resilient"


# --- search ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_prefers_the_shared_search_service(service: WorkspaceService) -> None:
    """So a caller gets the same ranking every other source is subject
    to, rather than a second ranking that only workspace results see."""

    class _Search:
        def __init__(self) -> None:
            self.calls: list[str] = []

        async def search(self, query: str, *, top_k: int = 10) -> list[SearchResult]:
            self.calls.append(query)
            return [SearchResult(id="s1", title="shared", content="", source="memory", score=1.0)]

    shared = _Search()
    results = await WorkspaceManager(service, search_service=shared).search("anything")

    assert shared.calls == ["anything"]
    assert [r.id for r in results] == ["s1"]


@pytest.mark.asyncio
async def test_search_falls_back_to_the_three_workspace_sources(
    service: WorkspaceService,
) -> None:
    """Narrower without a SearchService, never wrong."""
    workspace = await service.create_workspace("Quantum research")
    await service.create_project(workspace.id, "Quantum project")
    await service.create_note(workspace.id, "Quantum note")

    results = await WorkspaceManager(service).search("quantum")

    assert {r.source for r in results} == {"workspaces", "projects", "notes"}
    # Sorted by score, highest first.
    assert [r.score for r in results] == sorted((r.score for r in results), reverse=True)


@pytest.mark.asyncio
async def test_search_fallback_respects_top_k(service: WorkspaceService) -> None:
    workspace = await service.create_workspace("Quantum")
    for index in range(5):
        await service.create_note(workspace.id, f"Quantum {index}")

    assert len(await WorkspaceManager(service).search("quantum", top_k=3)) == 3


@pytest.mark.asyncio
async def test_the_manager_persists_nothing(service: WorkspaceService) -> None:
    """It is a read-side coordinator. Calling every read twice must
    leave the domain exactly as it was."""
    manager = WorkspaceManager(service, knowledge_service=_Knowledge(), memory_service=_Memory())
    workspace = await service.create_workspace("Stable")
    await service.create_note(workspace.id, "N")
    before = (await service.metadata(workspace.id)).as_dict()

    for _ in range(2):
        await manager.overview(workspace.id)
        await manager.context(workspace.id)
        await manager.search("stable")

    assert (await service.metadata(workspace.id)).as_dict() == before
