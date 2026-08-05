"""WorkspaceAssistantService tests -- Milestone 11 Task Group D.

The assistant's contract has three halves worth pinning: it grounds
every prompt in the workspace's own assembled context, it degrades to
that context rather than failing when no model answers, and it writes
nothing anywhere.

``FakeLLM`` (``tests/fakes/fake_llm.py``) throughout, including its
``fail=True`` mode -- the degradation path is the one an offline-first
product will actually take most often, so it is tested as a first-class
outcome rather than an edge case.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.core.events.event_bus import EventBus
from jarvis.core.events.events import WorkspaceAssistCompletedEvent
from jarvis.core.exceptions import ServiceError
from jarvis.core.interfaces.search import SearchResult
from jarvis.services.workspace_ai_managers import WorkspaceContextManager, WorkspaceRetriever
from jarvis.services.workspace_ai_service import WorkspaceAssistantService
from jarvis.services.workspace_service import WorkspaceService
from tests.fakes.fake_llm import FakeLLM


def _settings(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("JARVIS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("JARVIS_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'jarvis.db'}")

    from jarvis.core.config import settings as settings_mod

    settings_mod.load_settings.cache_clear()  # type: ignore[attr-defined]
    return settings_mod.load_settings()


class _Search:
    def __init__(self, results: list[SearchResult]) -> None:
        self.results = results

    async def search(self, query: str, *, top_k: int = 20) -> list[SearchResult]:
        return self.results


class _Env:
    def __init__(self, db, bus) -> None:
        self.bus = bus
        self.events: list[WorkspaceAssistCompletedEvent] = []
        bus.subscribe(WorkspaceAssistCompletedEvent, lambda e: self.events.append(e) or None)
        self.workspaces = WorkspaceService(database=db, event_bus=bus)
        self.context_manager = WorkspaceContextManager(self.workspaces)

    def assistant(
        self, *, llm: FakeLLM | None = None, search: _Search | None = None, **overrides
    ) -> WorkspaceAssistantService:
        retriever = WorkspaceRetriever(self.workspaces, search_service=search)
        options = {
            "llm": llm or FakeLLM("A tidy summary."),
            "context_manager": self.context_manager,
            "retriever": retriever,
            "workspace_service": self.workspaces,
            "event_bus": self.bus,
        }
        options.update(overrides)
        return WorkspaceAssistantService(**options)  # type: ignore[arg-type]


@pytest.fixture
async def env(tmp_path: Path, monkeypatch):
    settings = _settings(tmp_path, monkeypatch)
    from jarvis.infrastructure.database.sqlite_client import SQLiteDatabase

    db = SQLiteDatabase(settings.db)
    await db.initialize()
    try:
        yield _Env(db, EventBus())
    finally:
        await db.dispose()


# --- grounding ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_summarize_prompts_with_the_workspace_context(env) -> None:
    workspace = await env.workspaces.create_workspace("Research", description="the migration")
    await env.workspaces.create_note(workspace.id, "Standup", content="we discussed it")
    llm = FakeLLM("A tidy summary.")

    result = await env.assistant(llm=llm).summarize(workspace.id)

    prompt = llm.calls[0][0].content
    assert "Workspace: Research" in prompt
    assert "Standup" in prompt
    assert result.answer == "A tidy summary."
    assert result.synthesized is True


@pytest.mark.asyncio
async def test_the_prompt_states_the_grounding_rule(env) -> None:
    workspace = await env.workspaces.create_workspace("Research")
    llm = FakeLLM("ok")

    await env.assistant(llm=llm).summarize(workspace.id)

    assert "Do not invent" in llm.calls[0][0].content


@pytest.mark.asyncio
async def test_ask_carries_the_question_into_the_prompt(env) -> None:
    workspace = await env.workspaces.create_workspace("Research")
    llm = FakeLLM("ok")

    await env.assistant(llm=llm).ask(workspace.id, "what is overdue?")

    assert "Question: what is overdue?" in llm.calls[0][0].content


@pytest.mark.asyncio
async def test_ask_retrieves_and_reports_citations(env) -> None:
    """Citations are what was actually in the prompt, not what a model
    claimed to have used."""
    workspace = await env.workspaces.create_workspace("Research")
    hit = SearchResult(
        id="n1",
        title="Migration notes",
        content="we agreed to cut over on Friday",
        source="notes",
        score=1.0,
        uri="note://n1",
        metadata={"workspace_id": workspace.id},
    )
    llm = FakeLLM("Friday.")

    result = await env.assistant(llm=llm, search=_Search([hit])).ask(
        workspace.id, "when is cutover?"
    )

    assert [c.id for c in result.citations] == ["n1"]
    assert result.citations[0].uri == "note://n1"
    assert "cut over on Friday" in llm.calls[0][0].content


@pytest.mark.asyncio
async def test_summarize_does_not_retrieve(env) -> None:
    """Only ``ask`` has a query to retrieve against; the other two modes
    read the context alone."""
    workspace = await env.workspaces.create_workspace("Research")
    hit = SearchResult(
        id="n1",
        title="t",
        content="c",
        source="notes",
        score=1.0,
        metadata={"workspace_id": workspace.id},
    )
    llm = FakeLLM("ok")

    result = await env.assistant(llm=llm, search=_Search([hit])).summarize(workspace.id)

    assert result.citations == ()
    assert "Retrieved for this question:" not in llm.calls[0][0].content


@pytest.mark.asyncio
async def test_next_actions_asks_for_provenance(env) -> None:
    workspace = await env.workspaces.create_workspace("Research")
    llm = FakeLLM("Do the thing.")

    result = await env.assistant(llm=llm).next_actions(workspace.id)

    assert "say which item it comes from" in llm.calls[0][0].content
    assert result.mode == "next_actions"


@pytest.mark.asyncio
async def test_the_result_carries_the_context_it_was_grounded_in(env) -> None:
    """So a caller can see exactly what the model was shown, rather than
    trusting that it was shown something."""
    workspace = await env.workspaces.create_workspace("Research")

    result = await env.assistant().summarize(workspace.id)

    assert result.context is not None
    assert result.context.workspace_id == workspace.id
    assert result.as_dict()["context"]["workspace_name"] == "Research"


@pytest.mark.asyncio
async def test_a_caller_budget_reaches_the_context(env) -> None:
    workspace = await env.workspaces.create_workspace("Research")
    for index in range(20):
        await env.workspaces.create_note(workspace.id, f"Note {index}", content="x" * 300)

    result = await env.assistant().assist(workspace.id, budget_chars=300)

    assert result.context is not None
    assert result.context.used_chars <= 300


# --- validation -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_unknown_mode_is_rejected(env) -> None:
    workspace = await env.workspaces.create_workspace("Research")

    with pytest.raises(ServiceError, match="Unknown assist mode"):
        await env.assistant().assist(workspace.id, mode="interpretive-dance")


@pytest.mark.asyncio
async def test_ask_without_a_question_is_rejected(env) -> None:
    workspace = await env.workspaces.create_workspace("Research")

    with pytest.raises(ServiceError, match="requires a question"):
        await env.assistant().assist(workspace.id, mode="ask", question="   ")


@pytest.mark.asyncio
async def test_assisting_an_unknown_workspace_raises(env) -> None:
    with pytest.raises(ServiceError, match="does not exist"):
        await env.assistant().summarize("nope")


# --- degradation ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_unreachable_provider_returns_the_context_verbatim(env) -> None:
    """The posture ``KnowledgeService.ask`` already set, and the only one
    compatible with an offline-first product."""
    workspace = await env.workspaces.create_workspace("Research")
    await env.workspaces.create_note(workspace.id, "Standup", content="we discussed it")

    result = await env.assistant(llm=FakeLLM(fail=True)).summarize(workspace.id)

    assert result.synthesized is False
    assert "Standup" in result.answer


@pytest.mark.asyncio
async def test_an_empty_answer_counts_as_no_answer(env) -> None:
    workspace = await env.workspaces.create_workspace("Research")
    await env.workspaces.create_note(workspace.id, "Standup")

    result = await env.assistant(llm=FakeLLM("   ")).summarize(workspace.id)

    assert result.synthesized is False
    assert "Standup" in result.answer


@pytest.mark.asyncio
async def test_a_provider_raising_something_unexpected_still_degrades(env) -> None:
    class _Exploding:
        name = "boom"

        async def complete(self, messages, **kwargs):
            raise RuntimeError("segfault in the tokenizer")

    workspace = await env.workspaces.create_workspace("Research")

    result = await env.assistant(llm=_Exploding()).summarize(workspace.id)

    assert result.synthesized is False


@pytest.mark.asyncio
async def test_a_context_with_nothing_in_it_degrades_to_a_sentence(env) -> None:
    """Rather than an empty string, which reads as a broken response.

    Driven through a context manager with no workspace service reads to
    contribute, because a real workspace always renders at least its own
    header -- this is the shape of the degenerate case, reached the way
    a caller would reach it.
    """

    class _EmptyContext:
        async def context(self, workspace_id: str, *, budget_chars: int | None = None):
            from jarvis.domain.ai_workspace.models import WorkspaceContext

            return WorkspaceContext(workspace_id=workspace_id)

    assistant = env.assistant(llm=FakeLLM(fail=True), context_manager=_EmptyContext())

    result = await assistant.summarize("w1")

    assert result.answer == "There is nothing in this workspace yet."
    assert result.synthesized is False


@pytest.mark.asyncio
async def test_the_assistant_works_without_a_retriever(env) -> None:
    workspace = await env.workspaces.create_workspace("Research")

    result = await env.assistant(retriever=None).ask(workspace.id, "anything?")

    assert result.citations == ()
    assert result.answer


@pytest.mark.asyncio
async def test_retrieve_without_a_retriever_returns_nothing(env) -> None:
    workspace = await env.workspaces.create_workspace("Research")

    assert await env.assistant(retriever=None).retrieve(workspace.id, "q") == []


# --- facade + events ------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_facade_exposes_context_retrieval_and_listing(env) -> None:
    """One AI-facing surface for REST and the agent tools, so the two
    cannot assemble context differently."""
    workspace = await env.workspaces.create_workspace("Research")
    hit = SearchResult(
        id="n1",
        title="t",
        content="c",
        source="notes",
        score=1.0,
        metadata={"workspace_id": workspace.id},
    )
    assistant = env.assistant(search=_Search([hit]))

    context = await assistant.context(workspace.id)
    results = await assistant.retrieve(workspace.id, "t")
    listed = await assistant.list_workspaces()

    assert context.workspace_name == "Research"
    assert [r.id for r in results] == ["n1"]
    assert listed == [{"id": workspace.id, "name": "Research", "status": "active"}]


@pytest.mark.asyncio
async def test_listing_without_a_workspace_service_is_empty(env) -> None:
    assert await env.assistant(workspace_service=None).list_workspaces() == []


@pytest.mark.asyncio
async def test_an_assist_publishes_one_event(env) -> None:
    workspace = await env.workspaces.create_workspace("Research")

    await env.assistant().summarize(workspace.id)

    assert len(env.events) == 1
    assert env.events[0].workspace_id == workspace.id
    assert env.events[0].mode == "summarize"
    assert env.events[0].synthesized is True


@pytest.mark.asyncio
async def test_the_event_reports_a_degraded_answer_as_degraded(env) -> None:
    workspace = await env.workspaces.create_workspace("Research")

    await env.assistant(llm=FakeLLM(fail=True)).summarize(workspace.id)

    assert env.events[0].synthesized is False


@pytest.mark.asyncio
async def test_the_event_carries_no_answer_text(env) -> None:
    """Relaying it would put a model's full output into every connected
    client's replay buffer for a request only one of them made."""
    workspace = await env.workspaces.create_workspace("Research")

    await env.assistant(llm=FakeLLM("something private")).summarize(workspace.id)

    assert "something private" not in str(env.events[0])


@pytest.mark.asyncio
async def test_the_assistant_persists_nothing(env) -> None:
    workspace = await env.workspaces.create_workspace("Stable")
    await env.workspaces.create_note(workspace.id, "N")
    before = (await env.workspaces.metadata(workspace.id)).as_dict()

    assistant = env.assistant()
    for _ in range(2):
        await assistant.summarize(workspace.id)
        await assistant.ask(workspace.id, "anything?")

    assert (await env.workspaces.metadata(workspace.id)).as_dict() == before


@pytest.mark.asyncio
async def test_the_assistant_works_without_an_event_bus(env) -> None:
    workspace = await env.workspaces.create_workspace("Quiet")

    result = await env.assistant(event_bus=None).summarize(workspace.id)

    assert result.answer
    assert env.events == []
