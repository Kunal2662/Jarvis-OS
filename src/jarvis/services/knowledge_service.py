"""Knowledge service — Milestone 10A, Universal Search & Knowledge Platform.

Turns the M3 Memory Platform's flat semantic store into a real, queryable
knowledge base: entities and relationships extracted from memory content
(Knowledge Graph / Relationship Graph), a correction primitive that
measurably updates future recall (Learning, scoped -- see module docstring
of ``agents/permission.py``-style "interim, not a full engine" framing),
and an LLM-synthesized "what do you know about X" answer (AI Search).

Communicates with the memory store *only* through :class:`MemoryService`'s
public interface (``recall``/``browse``/``summarize``/``set_pinned``) --
never touches memory SQL rows directly, so the two services' storage
concerns stay fully separated, matching this project's existing
service-layering rule (``AgentOrchestrator`` -> services -> repositories).

"Persistent Memory" (M10A's own key feature) is deliberately *not* a
second durability mechanism: it reuses ``MemoryService.set_pinned`` --
M3's existing pinned memories already skip retention-policy expiry, which
is exactly what "survives well beyond the retention window" means.

"Reflection Foundation" is deliberately *not* a scheduled background job
(no RuntimeManager hook, no scheduler) -- :meth:`learn_from_recent_memories`
is an on-demand batch-extraction method, callable via the REST API or an
agent tool today; wiring it to M7's Scheduler for periodic execution is
explicitly future work for a later milestone, not built here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from jarvis.core.exceptions import LLMProviderError, ServiceError, VectorStoreError
from jarvis.core.interfaces.search import SearchResult
from jarvis.core.interfaces.vector_store import VectorRecord
from jarvis.core.logging.logger import get_logger
from jarvis.core.types import ChatMessage
from jarvis.infrastructure.database.repositories import KnowledgeRepository
from jarvis.utils.llm_json import parse_json_object, safe_complete

if TYPE_CHECKING:
    from jarvis.core.events.event_bus import EventBus
    from jarvis.core.interfaces.database import IDatabase
    from jarvis.core.interfaces.llm_provider import ILLMProvider
    from jarvis.core.interfaces.vector_store import IVectorStore
    from jarvis.infrastructure.database.models import KnowledgeEntity
    from jarvis.services.memory_service import MemoryService

_logger = get_logger("jarvis.services.knowledge")

_ENTITY_RECORD_TYPE = "knowledge_entity"
_EMB_META_KEY = "__embedding__"
_CORRECTION_CONFIDENCE = 0.95
_DEFAULT_CONFIDENCE = 0.7

_EXTRACTION_INSTRUCTIONS = (
    "You are JARVIS's knowledge-extraction module. Read the text below and "
    "identify any named entities (people, projects, files, topics) and the "
    "relationships between them.\n"
    "Respond with ONLY a JSON object, no prose, no markdown fences:\n"
    '{"entities": [{"name": "<name>", "type": "person|project|file|topic|other", '
    '"description": "<short description>"}], '
    '"relationships": [{"subject": "<entity name>", "predicate": "<relation, e.g. '
    'works_on, occurs_on, located_in>", "object": "<entity name>"}]}\n'
    "If nothing is worth extracting, return empty lists for both."
)
_EXTRACTION_FALLBACK = '{"entities": [], "relationships": []}'


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class EntityRelationship:
    predicate: str
    other_entity: str
    direction: str  # "outgoing" | "incoming"
    confidence: float


@dataclass(frozen=True, slots=True)
class EntityDetail:
    id: str
    name: str
    entity_type: str
    description: str
    confidence: float
    relationships: list[EntityRelationship] = field(default_factory=list)
    memory_contents: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    entities_created: int
    relationships_created: int
    #: Every entity the extraction *resolved*, created or pre-existing,
    #: in the order the text mentioned them (Milestone 11 Task Group D).
    #:
    #: Added because ``entities_created`` alone cannot answer "which
    #: entities is this note about" -- a note mentioning a project the
    #: graph already knows creates nothing and would look, from the
    #: counts, like a note about nothing. Task Group D's workspace links
    #: need the ids, and the alternative (searching the graph for the
    #: names afterwards) would be a second, weaker implementation of the
    #: resolution this method already did.
    #:
    #: Defaulted and last, so every pre-existing construction site and
    #: assertion keeps working unchanged.
    entity_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CorrectionResult:
    entities_touched: int
    relationships_superseded: int
    relationships_created: int


class KnowledgeService:
    """Entity/relationship extraction, correction, and AI-synthesized
    query answering over the knowledge graph."""

    def __init__(
        self,
        database: IDatabase,
        vector_store: IVectorStore,
        llm: ILLMProvider,
        memory: MemoryService,
        *,
        event_bus: EventBus | None = None,
    ) -> None:
        self._db = database
        self._vs = vector_store
        self._llm = llm
        self._memory = memory
        self._event_bus = event_bus

    # ------------------------------------------------------------------
    # Extraction / learning
    # ------------------------------------------------------------------
    async def learn_from_text(
        self, text: str, *, source_memory_id: str | None = None
    ) -> ExtractionResult:
        """Extract entities/relationships from *text* and persist them.
        Never raises: extraction failures degrade to "nothing extracted"
        rather than breaking the caller (same posture as every other
        LLM-driven node in this codebase)."""
        text = (text or "").strip()
        if not text:
            return ExtractionResult(entities_created=0, relationships_created=0)

        decision = await self._extract(text)
        entity_ids: dict[str, str] = {}
        entities_created = 0
        relationships_created = 0

        async with self._db.session() as sess:
            repo = KnowledgeRepository(sess)  # type: ignore[arg-type]
            for raw in decision.get("entities", []):
                if not isinstance(raw, dict):
                    continue
                name = str(raw.get("name") or "").strip()
                if not name:
                    continue
                existing = await repo.find_entity_by_name(name)
                if existing is not None:
                    entity_ids[name.lower()] = existing.id
                    entity = existing
                else:
                    entity = await repo.add_entity(
                        name,
                        entity_type=str(raw.get("type") or "other"),
                        description=str(raw.get("description") or ""),
                        confidence=_DEFAULT_CONFIDENCE,
                    )
                    entity_ids[name.lower()] = entity.id
                    entities_created += 1
                    await self._index_entity(entity)
                if source_memory_id:
                    await repo.link_entity_memory(entity.id, source_memory_id)

            for raw in decision.get("relationships", []):
                if not isinstance(raw, dict):
                    continue
                predicate = str(raw.get("predicate") or "").strip()
                subj_name = str(raw.get("subject") or "").strip().lower()
                obj_name = str(raw.get("object") or "").strip().lower()
                subject_id = entity_ids.get(subj_name)
                object_id = entity_ids.get(obj_name)
                if not (predicate and subject_id and object_id):
                    continue
                await repo.add_relationship(
                    subject_id,
                    predicate,
                    object_id,
                    confidence=_DEFAULT_CONFIDENCE,
                    source_memory_id=source_memory_id,
                )
                relationships_created += 1

        result = ExtractionResult(
            entities_created=entities_created,
            relationships_created=relationships_created,
            # Insertion-ordered by ``dict``, which is mention order here
            # -- ``entity_ids`` is populated as the extraction walks the
            # text. Milestone 11 Task Group D's workspace links consume
            # this; see ``ExtractionResult.entity_ids``.
            entity_ids=tuple(entity_ids.values()),
        )
        if entities_created or relationships_created:
            await self._publish_entity_updated()
        return result

    async def learn_from_recent_memories(self, *, limit: int = 20) -> ExtractionResult:
        """Batch extraction over the most recent memories -- the
        Reflection Foundation capability, called on demand (REST/agent
        tool), never scheduled by this service itself."""
        records = await self._memory.browse(limit=limit)
        total_entities = 0
        total_relationships = 0
        # Deduplicated across the batch, order preserved: two memories
        # mentioning the same project resolve to one entity, and
        # reporting it twice would make a caller's link count disagree
        # with the graph's.
        resolved: dict[str, None] = {}
        for record in records:
            result = await self.learn_from_text(record.content, source_memory_id=record.id)
            total_entities += result.entities_created
            total_relationships += result.relationships_created
            resolved.update(dict.fromkeys(result.entity_ids))
        return ExtractionResult(
            entities_created=total_entities,
            relationships_created=total_relationships,
            entity_ids=tuple(resolved),
        )

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------
    async def resolve_entity(self, name: str) -> KnowledgeEntity | None:
        """Exact name match first; falls back to a keyword search over
        name/description when nothing matches exactly."""
        async with self._db.session() as sess:
            repo = KnowledgeRepository(sess)  # type: ignore[arg-type]
            entity = await repo.find_entity_by_name(name)
            if entity is not None:
                return entity
            hits = await repo.search_entities(name, limit=1)
            return hits[0] if hits else None

    async def get_entity_detail(self, name: str) -> EntityDetail | None:
        async with self._db.session() as sess:
            repo = KnowledgeRepository(sess)  # type: ignore[arg-type]
            entity = await repo.find_entity_by_name(name)
            if entity is None:
                hits = await repo.search_entities(name, limit=1)
                entity = hits[0] if hits else None
            if entity is None:
                return None

            rels = await repo.list_relationships_for_entity(entity.id)
            relationships: list[EntityRelationship] = []
            for rel in rels:
                if rel.subject_id == entity.id:
                    other = await repo.get_entity(rel.object_id)
                    direction = "outgoing"
                else:
                    other = await repo.get_entity(rel.subject_id)
                    direction = "incoming"
                if other is not None:
                    relationships.append(
                        EntityRelationship(
                            predicate=rel.predicate,
                            other_entity=other.name,
                            direction=direction,
                            confidence=rel.confidence,
                        )
                    )

            memory_ids = set(await repo.list_memory_ids_for_entity(entity.id))

        memory_contents: list[str] = []
        if memory_ids:
            records = await self._memory.browse(limit=1000)
            memory_contents = [r.content for r in records if r.id in memory_ids][:10]

        return EntityDetail(
            id=entity.id,
            name=entity.name,
            entity_type=entity.entity_type,
            description=entity.description,
            confidence=entity.confidence,
            relationships=relationships,
            memory_contents=memory_contents,
        )

    async def ask(self, query: str) -> str:
        """AI Search: a coherent, LLM-synthesized answer drawing on the
        knowledge graph *and* memory recall -- Acceptance Criterion 1
        ("what do you know about Project X")."""
        query = (query or "").strip()
        if not query:
            return ""

        detail = await self.get_entity_detail(query)
        memories = await self._memory.recall(query, top_k=5)

        context_lines: list[str] = []
        if detail is not None:
            context_lines.append(f"Entity: {detail.name} ({detail.entity_type})")
            if detail.description:
                context_lines.append(f"Description: {detail.description}")
            for rel in detail.relationships:
                arrow = "->" if rel.direction == "outgoing" else "<-"
                context_lines.append(
                    f"  {detail.name} {arrow} {rel.predicate} {arrow} {rel.other_entity}"
                )
        for record in memories:
            context_lines.append(f"- {record.content}")

        if not context_lines:
            return "I don't have any knowledge about that yet."

        prompt = (
            "Answer the user's question using only the knowledge below. Be "
            "concise and synthesize a coherent answer rather than listing "
            "raw facts verbatim.\n\n"
            f"Question: {query}\n\nKnowledge:\n" + "\n".join(context_lines)
        )
        try:
            answer = await self._llm.complete([ChatMessage(role="user", content=prompt)])
            return (answer or "").strip() or "\n".join(context_lines)
        except LLMProviderError as err:
            _logger.warning("Knowledge ask() synthesis failed, returning raw context: {}", err)
            return "\n".join(context_lines)

    async def search(self, query: str, *, top_k: int = 10) -> list[SearchResult]:
        """Entity-name/description search -- the ``KnowledgeSearchSource``
        adapter's backing method (see ``services/search_sources.py``)."""
        query = (query or "").strip()
        if not query:
            return []
        async with self._db.session() as sess:
            repo = KnowledgeRepository(sess)  # type: ignore[arg-type]
            hits = await repo.search_entities(query, limit=top_k)
        return [
            SearchResult(
                id=e.id,
                title=e.name,
                content=e.description,
                source="knowledge",
                score=e.confidence,
                uri=f"knowledge://entity/{e.id}",
                metadata={"entity_type": e.entity_type},
            )
            for e in hits
        ]

    # ------------------------------------------------------------------
    # Correction (Learning, scoped)
    # ------------------------------------------------------------------
    async def correct(self, statement: str) -> CorrectionResult:
        """A correction ("actually, my meeting is on Thursday not
        Wednesday") measurably updates future recall -- Acceptance
        Criterion 3. Extracts the corrected fact(s) from *statement* and
        supersedes any prior relationship sharing the same (subject,
        predicate) pair, rather than deleting history."""
        statement = (statement or "").strip()
        if not statement:
            raise ServiceError("Cannot correct with an empty statement.")

        decision = await self._extract(statement)
        superseded_total = 0
        created_total = 0
        entities_touched: set[str] = set()

        async with self._db.session() as sess:
            repo = KnowledgeRepository(sess)  # type: ignore[arg-type]
            entity_ids: dict[str, str] = {}
            for raw in decision.get("entities", []):
                if not isinstance(raw, dict):
                    continue
                name = str(raw.get("name") or "").strip()
                if not name:
                    continue
                existing = await repo.find_entity_by_name(name)
                entity = existing or await repo.add_entity(
                    name,
                    entity_type=str(raw.get("type") or "other"),
                    description=str(raw.get("description") or ""),
                )
                entity_ids[name.lower()] = entity.id
                entities_touched.add(entity.id)
                if existing is None:
                    await self._index_entity(entity)

            for raw in decision.get("relationships", []):
                if not isinstance(raw, dict):
                    continue
                predicate = str(raw.get("predicate") or "").strip()
                subject_id = entity_ids.get(str(raw.get("subject") or "").strip().lower())
                object_id = entity_ids.get(str(raw.get("object") or "").strip().lower())
                if not (predicate and subject_id and object_id):
                    continue
                new_rel = await repo.add_relationship(
                    subject_id, predicate, object_id, confidence=_CORRECTION_CONFIDENCE
                )
                created_total += 1
                superseded_total += await repo.supersede_relationships(
                    subject_id, predicate, exclude_id=new_rel.id
                )

        if created_total or superseded_total:
            await self._publish_correction_applied()
        return CorrectionResult(
            entities_touched=len(entities_touched),
            relationships_superseded=superseded_total,
            relationships_created=created_total,
        )

    # ------------------------------------------------------------------
    # Export / Import (Acceptance Criterion 2)
    # ------------------------------------------------------------------
    async def export_graph(self) -> str:
        async with self._db.session() as sess:
            repo = KnowledgeRepository(sess)  # type: ignore[arg-type]
            entities = await repo.list_all_entities()
            relationships = await repo.list_all_relationships()
        payload = {
            "version": 1,
            "entities": [
                {
                    "id": e.id,
                    "name": e.name,
                    "entity_type": e.entity_type,
                    "description": e.description,
                    "confidence": e.confidence,
                }
                for e in entities
            ],
            "relationships": [
                {
                    "subject_id": r.subject_id,
                    "predicate": r.predicate,
                    "object_id": r.object_id,
                    "confidence": r.confidence,
                    "superseded": r.superseded,
                }
                for r in relationships
            ],
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    async def import_graph(self, data: str) -> ExtractionResult:
        """Import a graph previously produced by :meth:`export_graph`.
        Entity ids are preserved so relationships resolve correctly;
        an entity whose id already exists is skipped, not duplicated."""
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError as err:
            raise ServiceError(f"Invalid knowledge graph export file: {err}") from err

        entities = parsed.get("entities", [])
        relationships = parsed.get("relationships", [])
        if not isinstance(entities, list) or not isinstance(relationships, list):
            raise ServiceError("Knowledge graph export must contain entities/relationships lists.")

        async with self._db.session() as sess:
            repo = KnowledgeRepository(sess)  # type: ignore[arg-type]
            entities_created = await self._import_entities(repo, entities, relationships)
            relationships_created = await self._import_relationships(repo, relationships)

        return ExtractionResult(
            entities_created=entities_created, relationships_created=relationships_created
        )

    async def _import_entities(
        self,
        repo: KnowledgeRepository,
        entities: list[Any],
        relationships: list[Any],
    ) -> int:
        """Creates every not-yet-present entity from an export, re-keying
        *relationships* in place from each export's old id to the freshly
        assigned one so :meth:`_import_relationships` can resolve them."""
        created = 0
        for raw in entities:
            if not isinstance(raw, dict):
                continue
            entity_id = str(raw.get("id") or "")
            if entity_id and await repo.get_entity(entity_id) is not None:
                continue
            name = str(raw.get("name") or "").strip()
            if not name:
                continue
            entity = await repo.add_entity(
                name,
                entity_type=str(raw.get("entity_type") or "other"),
                description=str(raw.get("description") or ""),
                confidence=float(raw.get("confidence") or _DEFAULT_CONFIDENCE),
            )
            if entity_id:
                self._rekey_relationships(relationships, entity_id, entity.id)
            created += 1
        return created

    @staticmethod
    def _rekey_relationships(relationships: list[Any], old_id: str, new_id: str) -> None:
        for rel in relationships:
            if not isinstance(rel, dict):
                continue
            if rel.get("subject_id") == old_id:
                rel["subject_id"] = new_id
            if rel.get("object_id") == old_id:
                rel["object_id"] = new_id

    async def _import_relationships(
        self, repo: KnowledgeRepository, relationships: list[Any]
    ) -> int:
        created = 0
        for raw in relationships:
            if not isinstance(raw, dict):
                continue
            subject_id = str(raw.get("subject_id") or "")
            object_id = str(raw.get("object_id") or "")
            predicate = str(raw.get("predicate") or "")
            if not (subject_id and object_id and predicate):
                continue
            if (
                await repo.get_entity(subject_id) is None
                or await repo.get_entity(object_id) is None
            ):
                continue
            rel = await repo.add_relationship(
                subject_id,
                predicate,
                object_id,
                confidence=float(raw.get("confidence") or _DEFAULT_CONFIDENCE),
            )
            rel.superseded = bool(raw.get("superseded", False))
            created += 1
        return created

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    async def _extract(self, text: str) -> dict[str, Any]:
        prompt = f"{_EXTRACTION_INSTRUCTIONS}\n\nText:\n{text}"
        raw = await safe_complete(self._llm, prompt, fallback=_EXTRACTION_FALLBACK)
        return parse_json_object(raw)

    async def _index_entity(self, entity: KnowledgeEntity) -> None:
        """Best-effort semantic indexing of an entity's name+description
        into the *existing* vector store collection, tagged
        ``record_type: knowledge_entity`` so it can be filtered separately
        from (or searched alongside) memory content. Never raises."""
        try:
            embedding = await self._embed(f"{entity.name}. {entity.description}")
        except LLMProviderError as err:
            _logger.warning("Skipping entity vector index (embedding failed): {}", err)
            return
        try:
            document = f"{entity.name}. {entity.description}"
            entity_meta: dict[str, Any] = {
                "record_type": _ENTITY_RECORD_TYPE,
                "entity_type": entity.entity_type,
                _EMB_META_KEY: embedding,
            }
            await self._vs.upsert(
                [VectorRecord(id=entity.id, document=document, metadata=entity_meta)]
            )
        except VectorStoreError as err:
            _logger.warning("Entity vector index upsert failed for {}: {}", entity.id, err)

    async def _embed(self, text: str) -> list[float]:
        embeddings = await self._llm.embed([text])
        if not embeddings or not embeddings[0]:
            raise LLMProviderError("Embedding provider returned no vector.")
        return list(embeddings[0])

    async def _publish_entity_updated(self) -> None:
        if self._event_bus is None:
            return
        from jarvis.core.events.events import KnowledgeEntityUpdatedEvent

        await self._event_bus.publish(KnowledgeEntityUpdatedEvent())

    async def _publish_correction_applied(self) -> None:
        if self._event_bus is None:
            return
        from jarvis.core.events.events import KnowledgeCorrectionAppliedEvent

        await self._event_bus.publish(KnowledgeCorrectionAppliedEvent())
