"""AI Workspace services -- Milestone 11 Task Group D.

Two services over the workspace substrate Task Groups A-C shipped:

* :class:`WorkspaceKnowledgeService` owns the ``workspace_knowledge_links``
  table and the ingestion that fills it -- the *Knowledge integration*
  half of this task group. It writes.
* :class:`WorkspaceAssistantService` grounds an LLM in one workspace's
  assembled context and answers with it -- the *AI assistance* half. It
  writes nothing.

They share a module for the same reason ``file_service.py`` holds three:
they are one bounded context, read together, and splitting a 200-line
coordinator into its own file would be filing for its own sake.

**What this task group does not build.** No second search engine: every
retrieval goes through M10A's ``SearchService`` (see
``workspace_ai_managers.WorkspaceRetriever``). No second extractor:
entity extraction is ``KnowledgeService.learn_from_text``, called, not
reimplemented. No second conversation store: an assist call returns its
answer and publishes an event, and nothing about it is persisted --
``ConversationService`` owns chat history and would be the place to put
it if a caller wanted that. No embeddings and no vector index over
workspace content; that needs the semantic indexing Task Group C
explicitly deferred.

**Why the assistant degrades instead of failing.** ``assist()`` falls
back to returning the assembled context verbatim when no LLM answers,
marked ``synthesized=False``. This is the posture
``KnowledgeService.ask`` already set ("returning raw context"), and it
is the only one compatible with an offline-first product: a local model
being unreachable must cost synthesis, not the whole answer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from jarvis.core.exceptions import LLMProviderError, ServiceError
from jarvis.core.logging.logger import get_logger
from jarvis.core.types import ChatMessage
from jarvis.domain.ai_workspace.models import (
    ASSIST_MODES,
    LINK_SOURCES,
    LINK_TARGETS,
    build_assist_prompt,
    render_results,
)
from jarvis.infrastructure.database.repositories import (
    KnowledgeRepository,
    WorkspaceLinkRepository,
)

if TYPE_CHECKING:
    from jarvis.core.events.event_bus import EventBus
    from jarvis.core.interfaces.database import IDatabase
    from jarvis.core.interfaces.llm_provider import ILLMProvider
    from jarvis.core.interfaces.search import SearchResult
    from jarvis.domain.ai_workspace.models import WorkspaceContext
    from jarvis.infrastructure.database.models import WorkspaceKnowledgeLink
    from jarvis.services.file_service import FileService
    from jarvis.services.knowledge_service import KnowledgeService
    from jarvis.services.workspace_ai_managers import (
        WorkspaceContextManager,
        WorkspaceRetriever,
    )
    from jarvis.services.workspace_service import WorkspaceService

_logger = get_logger("jarvis.services.workspace_ai")

#: The four narrow columns, in the order the repository takes them.
_NARROW_COLUMNS: tuple[str, ...] = ("project_id", "note_id", "task_id", "file_id")

#: ``target`` name -> column, ``None`` for the workspace itself. Mirrors
#: ``file_service._TARGET_COLUMNS``; a shorter map, because a knowledge
#: link only exists for prose-bearing entities (see ``LINK_TARGETS``).
_TARGET_COLUMNS: dict[str, str | None] = {
    "workspace": None,
    "project": "project_id",
    "note": "note_id",
    "task": "task_id",
    "file": "file_id",
}

#: The ORM class behind each narrow target, resolved lazily so this
#: module keeps importing nothing from ``infrastructure.database.models``
#: at import time.
_TARGET_MODELS: dict[str, str] = {
    "project": "Project",
    "note": "Note",
    "task": "Task",
    "file": "File",
}

#: How much of one target's text is handed to the extractor. Entity
#: extraction is an LLM call, and a 200 KiB indexed file would make one
#: ingestion cost more than every other call in this task group put
#: together. The cap is generous for prose and brutal for logs, which is
#: the right trade for a knowledge graph.
MAX_INGEST_CHARS = 8_000


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class IngestionResult:
    """What one ingestion run did.

    Counts rather than the links themselves: a workspace-wide run can
    touch hundreds, and a caller showing "12 notes read, 34 entities
    linked" needs four numbers, not a payload that grows with the
    corpus. ``skipped`` is a real outcome, not a failure -- an empty
    note has nothing to extract from and saying so beats reporting zero
    entities as though extraction had run.
    """

    targets_processed: int = 0
    targets_skipped: int = 0
    entities_linked: int = 0
    links_created: int = 0
    links_replaced: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "targets_processed": self.targets_processed,
            "targets_skipped": self.targets_skipped,
            "entities_linked": self.entities_linked,
            "links_created": self.links_created,
            "links_replaced": self.links_replaced,
        }

    def merged(self, other: IngestionResult) -> IngestionResult:
        """Frozen, so accumulating over many targets produces a new
        result rather than mutating one a caller may already hold --
        the same rule every value object in ``domain/`` follows."""
        return IngestionResult(
            targets_processed=self.targets_processed + other.targets_processed,
            targets_skipped=self.targets_skipped + other.targets_skipped,
            entities_linked=self.entities_linked + other.entities_linked,
            links_created=self.links_created + other.links_created,
            links_replaced=self.links_replaced + other.links_replaced,
        )


@dataclass(frozen=True, slots=True)
class Citation:
    """One retrieved item the answer was allowed to draw on.

    Carried separately from the answer text because a caller wants to
    link to the note or file behind a claim, and asking a model to
    format citations it can then get wrong is a worse contract than
    reporting what was actually in the prompt.
    """

    id: str
    title: str
    source: str
    uri: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "title": self.title, "source": self.source, "uri": self.uri}


@dataclass(frozen=True, slots=True)
class AssistResult:
    workspace_id: str
    mode: str
    answer: str
    #: ``False`` means no LLM produced this -- the answer is the
    #: assembled context, returned verbatim. The one fact about an
    #: answer a reader cannot infer from the text.
    synthesized: bool = True
    question: str = ""
    citations: tuple[Citation, ...] = field(default_factory=tuple)
    context: WorkspaceContext | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "mode": self.mode,
            "answer": self.answer,
            "synthesized": self.synthesized,
            "question": self.question,
            "citations": [citation.as_dict() for citation in self.citations],
            "context": self.context.as_dict() if self.context is not None else None,
        }


# ---------------------------------------------------------------------------
# Knowledge integration
# ---------------------------------------------------------------------------
class WorkspaceKnowledgeService:
    """Owns ``workspace_knowledge_links``: which knowledge entities each
    thing in a workspace is about, and the ingestion that finds out.

    ``knowledge_service`` is required rather than optional, unlike every
    collaborator on the read-side managers: this service exists to be
    the bridge between two subsystems, and one without the other half is
    not a degraded bridge, it is a link table with no way to fill
    itself. ``workspace_service`` and ``file_service`` *are* optional --
    they only widen what can be ingested, and a container without them
    can still link and list.
    """

    def __init__(
        self,
        *,
        database: IDatabase,
        knowledge_service: KnowledgeService,
        workspace_service: WorkspaceService | None = None,
        file_service: FileService | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        self._db = database
        self._knowledge = knowledge_service
        self._workspaces = workspace_service
        self._files = file_service
        self._event_bus = event_bus

    # ------------------------------------------------------------------
    # Links
    # ------------------------------------------------------------------
    async def link(
        self,
        workspace_id: str,
        entity_id: str,
        *,
        target: str = "workspace",
        target_id: str | None = None,
        source: str = "manual",
        confidence: float = 0.7,
    ) -> WorkspaceKnowledgeLink:
        """Records that *target* is about *entity_id*.

        Idempotent. A second call for the same (workspace, entity,
        target) returns the row that already exists rather than a
        duplicate -- ingestion re-runs constantly and a link table that
        grew a row per run would be an audit log nobody asked for.

        The one exception is a promotion: an ``extracted`` link that a
        caller then asserts by hand becomes ``manual``, because a human
        saying "yes, this note is about that" is a stronger claim than
        an extractor guessing it, and a later re-ingestion must not be
        free to delete it.
        """
        _validate(target, LINK_TARGETS, "link target")
        _validate(source, LINK_SOURCES, "link source")
        column = _TARGET_COLUMNS[target]
        if column is None and target_id:
            raise ServiceError(
                "A workspace link takes no target id -- the workspace itself is the target."
            )
        if column is not None and not target_id:
            raise ServiceError(f"Linking a {target} requires a target id.")

        columns = _target_columns(target, target_id)
        async with self._db.session() as sess:
            entity = await KnowledgeRepository(sess).get_entity(entity_id)  # type: ignore[arg-type]
            if entity is None:
                raise ServiceError(f"Knowledge entity {entity_id!r} does not exist.")
            await _require_workspace(sess, workspace_id)
            await _require_link_target(sess, target, target_id, workspace_id)

            links = WorkspaceLinkRepository(sess)  # type: ignore[arg-type]
            existing = await links.find(workspace_id, entity_id, **columns)
            if existing is None:
                created = await links.add(
                    workspace_id,
                    entity_id,
                    source=source,
                    confidence=confidence,
                    **columns,
                )
                link_id, action = created.id, "linked"
            elif source == "manual" and existing.source == "extracted":
                existing.source = "manual"
                existing.confidence = max(existing.confidence, confidence)
                link_id, action = existing.id, "promoted"
            else:
                return existing  # already exactly this link; nothing changed

        # A promotion is published as well as a creation: it changes what
        # a later re-ingestion is allowed to remove, which is exactly the
        # kind of state a subscriber showing links needs to know about.
        await self._publish_link(
            link_id, workspace_id, entity_id, target, target_id or "", source, action=action
        )
        return await self.require_link(link_id)

    async def get_link(self, link_id: str) -> WorkspaceKnowledgeLink | None:
        async with self._db.session() as sess:
            return await WorkspaceLinkRepository(sess).get(link_id)  # type: ignore[arg-type]

    async def require_link(self, link_id: str) -> WorkspaceKnowledgeLink:
        link = await self.get_link(link_id)
        if link is None:
            raise ServiceError(f"Knowledge link {link_id!r} does not exist.")
        return link

    async def list_links(
        self,
        *,
        workspace_id: str | None = None,
        entity_id: str | None = None,
        target: str | None = None,
        target_id: str | None = None,
        source: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[WorkspaceKnowledgeLink]:
        if target is not None:
            _validate(target, LINK_TARGETS, "link target")
        if source is not None:
            _validate(source, LINK_SOURCES, "link source")
        columns = (
            _target_columns(target, target_id)
            if target is not None
            else dict.fromkeys(_NARROW_COLUMNS)
        )
        async with self._db.session() as sess:
            links = WorkspaceLinkRepository(sess)  # type: ignore[arg-type]
            # `limit` is passed only when the caller set one, so the
            # repository's own default cap still applies otherwise.
            # Typed `Any` because it is unpacked alongside `**columns`,
            # whose values are `str | None`.
            bound: dict[str, Any] = {} if limit is None else {"limit": limit}
            return await links.list_links(
                workspace_id=workspace_id,
                entity_id=entity_id,
                source=source,
                offset=offset,
                **bound,
                **columns,
            )

    async def unlink(self, link_id: str) -> bool:
        async with self._db.session() as sess:
            links = WorkspaceLinkRepository(sess)  # type: ignore[arg-type]
            link = await links.get(link_id)
            if link is None:
                return False
            workspace_id, entity_id, source = link.workspace_id, link.entity_id, link.source
            target, target_id = describe_link_target(link)
            await links.delete(link_id)
        await self._publish_link(
            link_id, workspace_id, entity_id, target, target_id, source, action="unlinked"
        )
        return True

    async def entities_for(self, workspace_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        """The knowledge entities this workspace is recorded to be about,
        most-linked first.

        Distinct from ``KnowledgeService.search(workspace.name)``, which
        answers "what in the graph mentions these words". This answers
        "what did this workspace's own text produce", which is the
        question Task Group A's context could not ask.
        """
        async with self._db.session() as sess:
            rows = await WorkspaceLinkRepository(sess).entities_for_workspace(  # type: ignore[arg-type]
                workspace_id, limit=limit
            )
        return [
            {
                "id": entity.id,
                "name": entity.name,
                "entity_type": entity.entity_type,
                "description": entity.description,
                "link_count": count,
                "confidence": confidence,
                "uri": f"knowledge://entity/{entity.id}",
            }
            for entity, count, confidence in rows
        ]

    async def link_count(self, workspace_id: str) -> int:
        async with self._db.session() as sess:
            return await WorkspaceLinkRepository(sess).count_for_workspace(  # type: ignore[arg-type]
                workspace_id
            )

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------
    async def ingest_text(
        self,
        workspace_id: str,
        text: str,
        *,
        target: str = "workspace",
        target_id: str | None = None,
        replace: bool = True,
    ) -> IngestionResult:
        """Extract entities from *text* and link them to *target*.

        Extraction is ``KnowledgeService.learn_from_text`` -- the same
        call M10A's reflection path uses, not a second extractor. Only
        the linking is this service's own work.

        *replace* clears this target's previous ``extracted`` links
        first, so an edited note stops claiming entities its text no
        longer mentions. ``manual`` links are never touched by it: a
        person's assertion outlives a re-read of the file.

        The workspace and the target are checked **before** extraction
        runs, for two reasons: an unstorable link should fail as a bad
        request rather than as an ``IntegrityError`` five layers down
        (the gap Task Group C found and closed for attachments), and
        extraction is an LLM call -- paying for one whose result cannot
        be recorded is worse than refusing early.
        """
        _validate(target, LINK_TARGETS, "link target")
        text = (text or "").strip()
        if not text:
            return IngestionResult(targets_skipped=1)

        async with self._db.session() as sess:
            await _require_workspace(sess, workspace_id)
            await _require_link_target(sess, target, target_id, workspace_id)

        extraction = await self._knowledge.learn_from_text(text[:MAX_INGEST_CHARS])
        entity_ids = list(extraction.entity_ids)
        columns = _target_columns(target, target_id)

        replaced = 0
        created = 0
        async with self._db.session() as sess:
            links = WorkspaceLinkRepository(sess)  # type: ignore[arg-type]
            knowledge = KnowledgeRepository(sess)  # type: ignore[arg-type]
            if replace:
                replaced = await links.delete_extracted_for_target(workspace_id, **columns)
            for entity_id in entity_ids:
                entity = await knowledge.get_entity(entity_id)
                if entity is None:  # pragma: no cover -- defensive
                    continue
                if await links.find(workspace_id, entity_id, **columns) is not None:
                    continue
                await links.add(
                    workspace_id,
                    entity_id,
                    source="extracted",
                    confidence=entity.confidence,
                    **columns,
                )
                created += 1

        if created or replaced:
            # Once per target, not once per link: a subscriber refreshing
            # a view of this note wants one signal, not forty.
            await self._publish_link(
                "",
                workspace_id,
                "",
                target,
                target_id or "",
                "extracted",
                action="reingested",
            )
        return IngestionResult(
            targets_processed=1,
            entities_linked=len(entity_ids),
            links_created=created,
            links_replaced=replaced,
        )

    async def ingest_note(self, note_id: str, *, replace: bool = True) -> IngestionResult:
        if self._workspaces is None:
            raise ServiceError("Note ingestion needs a workspace service; none is wired.")
        note = await self._workspaces.require_note(note_id)
        return await self.ingest_text(
            note.workspace_id,
            f"{note.title}\n\n{note.content}",
            target="note",
            target_id=note.id,
            replace=replace,
        )

    async def ingest_file(self, file_id: str, *, replace: bool = True) -> IngestionResult:
        """Ingests a file's *indexed* text, never the file on disk.

        Task Group C already decided which files are readable as text
        and bounded how much of each it keeps; re-reading the file here
        would be a second answer to both questions. An unindexed file is
        skipped rather than opened.
        """
        if self._files is None:
            raise ServiceError("File ingestion needs a file service; none is wired.")
        file = await self._files.require_file(file_id)
        record = await self._files.index_record(file_id)
        body = record.content_text if record is not None else ""
        if not body.strip():
            return IngestionResult(targets_skipped=1)
        return await self.ingest_text(
            file.workspace_id,
            f"{file.filename}\n\n{body}",
            target="file",
            target_id=file.id,
            replace=replace,
        )

    async def ingest_workspace(
        self,
        workspace_id: str,
        *,
        include_notes: bool = True,
        include_files: bool = True,
        limit: int = 50,
    ) -> IngestionResult:
        """Runs ingestion across one workspace's prose.

        Bounded by *limit* per corpus, and on demand only -- nothing in
        this task group schedules it. That is the same posture
        ``KnowledgeService.learn_from_recent_memories`` and
        ``IntelligenceService.generate_daily_briefing`` already take, and
        for the same reason: M7's Scheduler (Phase 6) has not shipped,
        and inventing a second one here is exactly the duplication this
        repository has spent several milestones avoiding.
        """
        if self._workspaces is None:
            raise ServiceError("Workspace ingestion needs a workspace service; none is wired.")
        workspace = await self._workspaces.require_workspace(workspace_id)

        result = await self.ingest_text(
            workspace_id,
            f"{workspace.name}\n\n{workspace.description}",
            target="workspace",
        )

        if include_notes:
            notes = await self._workspaces.list_notes(workspace_id=workspace_id)
            for note in notes[: max(limit, 0)]:
                result = result.merged(await self.ingest_note(note.id))

        if include_files and self._files is not None:
            files = await self._files.list_files(workspace_id=workspace_id)
            for file in files[: max(limit, 0)]:
                result = result.merged(await self.ingest_file(file.id))

        _logger.info(
            "Workspace {} ingested: {} target(s), {} link(s) created.",
            workspace_id,
            result.targets_processed,
            result.links_created,
        )
        return result

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------
    async def _publish_link(
        self,
        link_id: str,
        workspace_id: str,
        entity_id: str,
        target: str,
        target_id: str,
        source: str,
        *,
        action: str,
    ) -> None:
        if self._event_bus is None:
            return
        from jarvis.core.events.events import WorkspaceKnowledgeLinkedEvent

        await self._event_bus.publish(
            WorkspaceKnowledgeLinkedEvent(
                link_id=link_id,
                workspace_id=workspace_id,
                entity_id=entity_id,
                target=target,
                target_id=target_id,
                source=source,
                action=action,
            )
        )


# ---------------------------------------------------------------------------
# AI assistance
# ---------------------------------------------------------------------------
class WorkspaceAssistantService:
    """Answers questions about one workspace, grounded in that
    workspace's own assembled context.

    The AI-facing facade for the workspace domain: the REST layer and
    the agent tools both talk to this one class rather than each
    assembling context and prompting a model their own way, which is how
    two surfaces end up giving different answers to the same question.

    Deliberately *not* an agent. It runs no graph, selects no tools and
    takes no actions -- ``AgentOrchestrator`` (M10) is this project's
    agent, and this service is one of the things it can now call
    (``agents/tools/workspace_tools.py``). A second orchestrator here
    would be the parallel-runtime duplication this architecture forbids.
    """

    def __init__(
        self,
        *,
        llm: ILLMProvider,
        context_manager: WorkspaceContextManager,
        retriever: WorkspaceRetriever | None = None,
        workspace_service: WorkspaceService | None = None,
        event_bus: EventBus | None = None,
        default_top_k: int = 5,
    ) -> None:
        self._llm = llm
        self._context = context_manager
        self._retriever = retriever
        self._workspaces = workspace_service
        self._event_bus = event_bus
        self._default_top_k = default_top_k

    # ------------------------------------------------------------------
    # Assistance
    # ------------------------------------------------------------------
    async def assist(
        self,
        workspace_id: str,
        *,
        mode: str = "summarize",
        question: str = "",
        top_k: int | None = None,
        budget_chars: int | None = None,
    ) -> AssistResult:
        _validate(mode, ASSIST_MODES, "assist mode")
        question = (question or "").strip()
        if mode == "ask" and not question:
            raise ServiceError("Asking a workspace a question requires a question.")

        context = await self._context.context(workspace_id, budget_chars=budget_chars)
        citations: tuple[Citation, ...] = ()
        retrieved_text = ""
        if mode == "ask" and self._retriever is not None:
            results = await self._retriever.retrieve(
                workspace_id, question, top_k=top_k or self._default_top_k
            )
            citations = tuple(
                Citation(id=r.id, title=r.title, source=r.source, uri=r.uri) for r in results
            )
            retrieved_text = render_results([(r.source, r.title, r.content) for r in results])

        prompt = build_assist_prompt(
            mode=mode,
            workspace_name=context.workspace_name or workspace_id,
            context_text=context.render(),
            retrieved_text=retrieved_text,
            question=question,
        )

        answer, synthesized = await self._synthesize(prompt, context)
        await self._publish_assist(workspace_id, mode, synthesized, len(citations))
        return AssistResult(
            workspace_id=workspace_id,
            mode=mode,
            answer=answer,
            synthesized=synthesized,
            question=question,
            citations=citations,
            context=context,
        )

    async def summarize(self, workspace_id: str, **kwargs: Any) -> AssistResult:
        return await self.assist(workspace_id, mode="summarize", **kwargs)

    async def ask(self, workspace_id: str, question: str, **kwargs: Any) -> AssistResult:
        return await self.assist(workspace_id, mode="ask", question=question, **kwargs)

    async def next_actions(self, workspace_id: str, **kwargs: Any) -> AssistResult:
        return await self.assist(workspace_id, mode="next_actions", **kwargs)

    # ------------------------------------------------------------------
    # Delegated reads -- so one facade serves REST and the agent tools
    # ------------------------------------------------------------------
    async def context(
        self, workspace_id: str, *, budget_chars: int | None = None
    ) -> WorkspaceContext:
        return await self._context.context(workspace_id, budget_chars=budget_chars)

    async def retrieve(
        self,
        workspace_id: str,
        query: str,
        *,
        top_k: int | None = None,
        include_global: bool = False,
    ) -> list[SearchResult]:
        if self._retriever is None:
            return []
        return await self._retriever.retrieve(
            workspace_id,
            query,
            top_k=top_k or self._default_top_k,
            include_global=include_global,
        )

    async def list_workspaces(self) -> list[dict[str, str]]:
        """Name-and-id pairs, so a caller holding no id (an agent, most
        obviously) can find one. Nothing else: this is a lookup, not a
        second workspace listing API."""
        if self._workspaces is None:
            return []
        return [
            {"id": workspace.id, "name": workspace.name, "status": workspace.status}
            for workspace in await self._workspaces.list_workspaces()
        ]

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    async def _synthesize(self, prompt: str, context: WorkspaceContext) -> tuple[str, bool]:
        """``(answer, synthesized)``.

        Any provider failure -- unreachable, timing out, refusing --
        degrades to the assembled context rather than raising. A caller
        that asked what is going on in a workspace is better served by
        the facts unsynthesized than by an error, and ``synthesized``
        tells them which they got.
        """
        try:
            answer = await self._llm.complete([ChatMessage(role="user", content=prompt)])
        except LLMProviderError as err:
            _logger.warning("Workspace assist synthesis failed, returning raw context: {}", err)
            return _fallback(context), False
        except Exception as err:  # a provider bug must not become a 500 here
            _logger.warning("Workspace assist synthesis raised unexpectedly: {}", err)
            return _fallback(context), False
        cleaned = (answer or "").strip()
        return (cleaned, True) if cleaned else (_fallback(context), False)

    async def _publish_assist(
        self, workspace_id: str, mode: str, synthesized: bool, citation_count: int
    ) -> None:
        if self._event_bus is None:
            return
        from jarvis.core.events.events import WorkspaceAssistCompletedEvent

        await self._event_bus.publish(
            WorkspaceAssistCompletedEvent(
                workspace_id=workspace_id,
                mode=mode,
                synthesized=synthesized,
                citation_count=citation_count,
            )
        )


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------
def describe_link_target(link: WorkspaceKnowledgeLink) -> tuple[str, str]:
    """Flattens the four nullable foreign keys into ``(target, id)``.

    The row keeps real constraints; every reader wants the pair. Public
    for the same reason ``file_service.describe_target`` is: the REST
    layer serialises it too, and two implementations of one collapse
    drift.
    """
    for name, column in _TARGET_COLUMNS.items():
        if column is None:
            continue
        value = getattr(link, column, None)
        if value:
            return name, str(value)
    return "workspace", link.workspace_id


def _target_columns(target: str | None, target_id: str | None) -> dict[str, str | None]:
    columns: dict[str, str | None] = dict.fromkeys(_NARROW_COLUMNS)
    column = _TARGET_COLUMNS.get(target or "workspace")
    if column is not None:
        columns[column] = target_id
    return columns


def _validate(value: str, allowed: frozenset[str], label: str) -> None:
    if value not in allowed:
        raise ServiceError(f"Unknown {label} {value!r}; allowed: {sorted(allowed)}.")


async def _require_workspace(sess: object, workspace_id: str) -> None:
    from jarvis.infrastructure.database import models as db_models

    workspace = await sess.get(db_models.Workspace, workspace_id)  # type: ignore[attr-defined]
    if workspace is None:
        raise ServiceError(f"Workspace {workspace_id!r} does not exist.")


async def _require_link_target(
    sess: object, target: str, target_id: str | None, workspace_id: str
) -> None:
    """Proves the link target exists and lives in this workspace, before
    the insert.

    Foreign keys already refuse a fabricated parent, but they refuse it
    as an ``IntegrityError`` several layers down, which reaches the
    caller as a 500 -- the gap Task Group C found and closed for
    attachments. The workspace check is the part a foreign key cannot
    make at all: a valid note id says nothing about the note being in
    *this* workspace, and a link spanning two would be a claim no view
    could coherently show.

    Simpler than ``file_service._require_target`` in one way that
    matters: all four of these targets carry ``workspace_id``
    themselves, so there is no calendar join and no special case.
    """
    from jarvis.infrastructure.database import models as db_models

    if target == "workspace" or not target_id:
        return
    model = getattr(db_models, _TARGET_MODELS[target])
    row = await sess.get(model, target_id)  # type: ignore[attr-defined]
    if row is None:
        raise ServiceError(f"{target.capitalize()} {target_id!r} does not exist.")
    owner = getattr(row, "workspace_id", None)
    if owner is not None and owner != workspace_id:
        raise ServiceError(
            f"{target.capitalize()} {target_id!r} belongs to a different workspace; "
            "a knowledge link cannot span two."
        )


def _fallback(context: WorkspaceContext) -> str:
    rendered = context.render()
    return rendered or "There is nothing in this workspace yet."
