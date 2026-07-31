"""Memory service — semantic + keyword recall over SQLite + Chroma.

Responsibilities:

* Persist a memory row in SQLite (source of truth for text + metadata).
* Compute an embedding via the injected :class:`ILLMProvider` and upsert
  into ChromaDB using the same id as the SQL row.
* Retrieve top-k memories using **hybrid recall**:
    1. Semantic query against Chroma (primary signal).
    2. SQL LIKE keyword prefilter (permissive).
    3. Merge with Reciprocal Rank Fusion (RRF) so exact-keyword hits
       don't get lost in the vector space.

The engine is *storage-first* — nothing here talks to the LLM except for
embedding calls, and the LLM adapters translate every third-party
exception into `LLMProviderError` for us. Failures from the vector
store or the embedding call are non-fatal for :meth:`recall` — we log
and return an empty list so upstream callers (chat, agents) keep
working.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Literal

from jarvis.core.exceptions import LLMProviderError, ServiceError, VectorStoreError
from jarvis.core.interfaces.vector_store import VectorRecord
from jarvis.core.logging.logger import get_logger
from jarvis.core.types import MemoryType
from jarvis.infrastructure.database.models import Memory
from jarvis.infrastructure.database.repositories import MemoryRepository

if TYPE_CHECKING:
    from jarvis.core.config.settings import Settings
    from jarvis.core.interfaces.database import IDatabase
    from jarvis.core.interfaces.llm_provider import ILLMProvider
    from jarvis.core.interfaces.vector_store import IVectorStore

_logger = get_logger("jarvis.services.memory")

SearchMode = Literal["semantic", "keyword", "hybrid", "recent"]


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class MemoryRecord:
    id: str
    content: str
    source: str
    metadata: dict
    score: float
    created_at: datetime
    memory_type: str = MemoryType.CONVERSATION.value
    pinned: bool = False
    archived: bool = False


@dataclass(frozen=True, slots=True)
class MemoryStats:
    sql_count: int
    vector_count: int


@dataclass(frozen=True, slots=True)
class PolicyReport:
    """Result of running the memory-management policies once."""

    expired: int = 0
    pruned: int = 0
    max_memories: int = 0
    retention_days: int = 0


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------
class MemoryService:
    """Persist, search and manage semantic memories."""

    _EMB_META_KEY = "__embedding__"

    def __init__(
        self,
        database: IDatabase,
        vector_store: IVectorStore,
        llm: ILLMProvider,
        settings: Settings,
    ) -> None:
        self._db = database
        self._vs = vector_store
        self._llm = llm
        self._settings = settings

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------
    async def remember(
        self,
        content: str,
        *,
        source: str = "user",
        memory_type: MemoryType | str = MemoryType.CONVERSATION,
        metadata: dict | None = None,
        conversation_id: str | None = None,
        pinned: bool = False,
        expires_at: datetime | None = None,
    ) -> str:
        """Store *content* and index it in the vector store. Returns the id.

        If *expires_at* is not given and the configured
        ``settings.memory.retention_days`` is non-zero, an expiry is
        derived automatically (skipped for pinned memories).
        """
        content = (content or "").strip()
        if not content:
            raise ServiceError("Cannot remember empty content.")

        mtype = memory_type.value if isinstance(memory_type, MemoryType) else str(memory_type)

        if expires_at is None and not pinned:
            retention_days = getattr(self._settings.memory, "retention_days", 0)
            if retention_days and retention_days > 0:
                expires_at = datetime.now(UTC) + timedelta(days=retention_days)

        meta = dict(metadata or {})
        meta_json = json.dumps(meta, ensure_ascii=False, sort_keys=True)

        # 1. Persist the SQL row first (the source of truth).
        async with self._db.session() as sess:  # type: ignore[assignment]
            repo = MemoryRepository(sess)  # type: ignore[arg-type]
            row = await repo.add(
                content=content,
                source=source,
                memory_type=mtype,
                meta_json=meta_json,
                conversation_id=conversation_id,
                pinned=pinned,
                expires_at=expires_at,
            )
            memory_id = row.id

        # 2. Best-effort embed + upsert into the vector store.
        try:
            embedding = await self._embed(content)
        except LLMProviderError as err:
            _logger.warning("Skipping vector upsert (embedding failed): {}", err)
            return memory_id

        try:
            chroma_meta = {
                **meta,
                "source": source,
                "memory_type": mtype,
                "conversation_id": conversation_id or "",
                self._EMB_META_KEY: embedding,
            }
            await self._vs.upsert(
                [VectorRecord(id=memory_id, document=content, metadata=chroma_meta)]
            )
        except VectorStoreError as err:
            _logger.warning("Vector upsert failed for memory {}: {}", memory_id, err)

        return memory_id

    async def forget(self, memory_id: str) -> None:
        """Delete a memory from both stores."""
        async with self._db.session() as sess:  # type: ignore[assignment]
            await MemoryRepository(sess).delete(memory_id)  # type: ignore[arg-type]
        try:
            await self._vs.delete([memory_id])
        except VectorStoreError:
            _logger.warning("Vector delete failed for {}.", memory_id)

    async def forget_all(self) -> int:
        """Clear every memory from both stores. Returns the count removed.

        Used by Settings ▸ Memory ▸ "Clear Memory". Irreversible.
        """
        async with self._db.session() as sess:  # type: ignore[assignment]
            repo = MemoryRepository(sess)  # type: ignore[arg-type]
            rows = await repo.list(limit=1_000_000, include_archived=True)
            ids = [r.id for r in rows]
            removed = await repo.delete_all()
        if ids:
            try:
                await self._vs.delete(ids)
            except VectorStoreError as err:
                _logger.warning("Vector bulk-delete failed: {}", err)
        _logger.info("Cleared {} memories.", removed)
        return removed

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------
    async def recall(
        self,
        query: str,
        *,
        top_k: int = 5,
        min_score: float = 0.0,
    ) -> list[MemoryRecord]:
        """Hybrid recall — semantic + keyword, merged via RRF.

        Never raises; on error, returns an empty list and logs.
        """
        query = (query or "").strip()
        if not query:
            return []

        # 1. Vector recall (primary).
        vector_hits: list[tuple[str, float]] = []
        try:
            embedding = await self._embed(query)
            results = await self._vs_query(embedding, top_k=top_k)
            vector_hits = [(r.id, r.score) for r in results if r.score >= min_score]
        except (LLMProviderError, VectorStoreError) as err:
            _logger.warning("Semantic recall failed: {}", err)

        # 2. Keyword recall (secondary).
        keyword_hits: list[str] = []
        try:
            async with self._db.session() as sess:  # type: ignore[assignment]
                rows = await MemoryRepository(sess).keyword_search(  # type: ignore[arg-type]
                    query, limit=top_k * 2
                )
                keyword_hits = [row.id for row in rows]
        except Exception as err:
            _logger.warning("Keyword recall failed: {}", err)

        # 3. Rank-fusion.
        fused_ids = _reciprocal_rank_fusion(
            [row_id for row_id, _ in vector_hits],
            keyword_hits,
            k=60,
        )
        if not fused_ids:
            return []

        # 4. Materialise ordered SQL rows.
        return await self._load_ordered(fused_ids[:top_k], vector_scores=dict(vector_hits))

    async def search(
        self,
        query: str = "",
        *,
        mode: SearchMode = "hybrid",
        top_k: int = 20,
        min_score: float = 0.0,
        memory_type: MemoryType | str | None = None,
    ) -> list[MemoryRecord]:
        """General-purpose retrieval used by the Memory UI / timeline.

        * ``"hybrid"``   — same fusion as :meth:`recall`.
        * ``"semantic"`` — vector similarity only.
        * ``"keyword"``  — SQL ``LIKE`` only.
        * ``"recent"``   — most-recent-first, ignores *query* entirely.
        """
        mtype = memory_type.value if isinstance(memory_type, MemoryType) else memory_type

        if mode == "recent" or not query.strip():
            async with self._db.session() as sess:  # type: ignore[assignment]
                rows = await MemoryRepository(sess).list(  # type: ignore[arg-type]
                    limit=top_k, memory_type=mtype, include_archived=False
                )
            return [_row_to_record(r, score=0.0) for r in rows]

        if mode == "keyword":
            async with self._db.session() as sess:  # type: ignore[assignment]
                rows = await MemoryRepository(sess).keyword_search(  # type: ignore[arg-type]
                    query, limit=top_k, memory_type=mtype
                )
            return [_row_to_record(r, score=0.0) for r in rows]

        if mode == "semantic":
            try:
                embedding = await self._embed(query)
                where = {"memory_type": mtype} if mtype else None
                results = await self._vs_query(embedding, top_k=top_k, where=where)
            except (LLMProviderError, VectorStoreError) as err:
                _logger.warning("Semantic search failed: {}", err)
                return []
            hits = [(r.id, r.score) for r in results if r.score >= min_score]
            if not hits:
                return []
            return await self._load_ordered([h[0] for h in hits], vector_scores=dict(hits))

        # mode == "hybrid" — reuse recall() then optionally filter by type.
        results = await self.recall(query, top_k=top_k, min_score=min_score)
        if mtype is not None:
            results = [r for r in results if r.memory_type == mtype]
        return results

    async def browse(
        self,
        *,
        memory_type: MemoryType | str | None = None,
        pinned_only: bool = False,
        include_archived: bool = False,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        limit: int = 200,
    ) -> list[MemoryRecord]:
        """Filtered, non-semantic listing for the Memory ▸ Timeline UI view.

        Browsing by type/date/pinned/archived state, independent of the
        recall/search machinery above. Never raises: on failure logs and
        returns an empty list, matching the rest of the read surface.
        """
        mtype = memory_type.value if isinstance(memory_type, MemoryType) else memory_type
        try:
            async with self._db.session() as sess:  # type: ignore[assignment]
                rows = await MemoryRepository(sess).list_filtered(  # type: ignore[arg-type]
                    memory_type=mtype,
                    pinned_only=pinned_only,
                    include_archived=include_archived,
                    start_date=start_date,
                    end_date=end_date,
                    limit=limit,
                )
        except Exception as err:
            _logger.warning("Memory browse failed: {}", err)
            return []
        return [_row_to_record(r, score=0.0) for r in rows]

    async def set_pinned(self, memory_id: str, *, pinned: bool) -> None:
        async with self._db.session() as sess:  # type: ignore[assignment]
            await MemoryRepository(sess).set_pinned(  # type: ignore[arg-type]
                memory_id, pinned=pinned
            )

    async def archive_memory(self, memory_id: str) -> None:
        async with self._db.session() as sess:  # type: ignore[assignment]
            await MemoryRepository(sess).archive(memory_id)  # type: ignore[arg-type]

    async def restamp_retention(self) -> int:
        """Re-derive ``expires_at`` on every existing unpinned/active row
        from the *current* ``settings.memory.retention_days`` instead of
        leaving already-stored rows on whatever value was in effect when
        they were written. Call this whenever the retention setting
        changes; follow with :meth:`enforce_policies` to actually archive
        anything that newly falls outside the window.
        """
        retention_days = getattr(self._settings.memory, "retention_days", 0) or 0
        async with self._db.session() as sess:  # type: ignore[assignment]
            changed = await MemoryRepository(sess).restamp_expirations(  # type: ignore[arg-type]
                retention_days=retention_days
            )
        if changed:
            _logger.info(
                "Re-stamped expires_at on {} memories (retention_days={}).",
                changed,
                retention_days,
            )
        return changed

    async def stats(self) -> MemoryStats:
        vc = 0
        try:
            vc = await self._vs.count()
        except VectorStoreError:
            pass
        async with self._db.session() as sess:  # type: ignore[assignment]
            rows = await MemoryRepository(sess).list(limit=10_000)  # type: ignore[arg-type]
            return MemoryStats(sql_count=len(rows), vector_count=vc)

    # ------------------------------------------------------------------
    # Summarization
    # ------------------------------------------------------------------
    async def summarize(
        self,
        text_or_messages: str | list,
        *,
        conversation_id: str | None = None,
        store: bool = True,
    ) -> str:
        """Summarize a conversation/blob of text into a short note.

        When *store* is true (the default) the summary is persisted as a
        ``MemoryType.LONG_TERM`` memory so future recalls benefit from it
        without re-processing the full transcript. Never raises: on LLM
        failure the raw (truncated) input is returned as a naive fallback.
        """
        if isinstance(text_or_messages, str):
            raw = text_or_messages
        else:
            raw = "\n".join(
                f"{getattr(m, 'role', 'user')}: {getattr(m, 'content', m)}"
                for m in text_or_messages
            )
        raw = raw.strip()
        if not raw:
            return ""

        from jarvis.core.types import ChatMessage

        prompt = (
            "Summarize the following in 1-3 concise sentences, preserving "
            "any facts, preferences, or decisions worth remembering "
            "long-term:\n\n" + raw
        )
        try:
            summary = await self._llm.complete([ChatMessage(role="user", content=prompt)])
            summary = (summary or "").strip() or raw[:280]
        except LLMProviderError as err:
            _logger.warning("Summarize failed, falling back to truncation: {}", err)
            summary = raw[:280]

        if store:
            await self.remember(
                summary,
                source="summary",
                memory_type=MemoryType.LONG_TERM,
                conversation_id=conversation_id,
                metadata={"origin": "summarize"},
            )
        return summary

    # ------------------------------------------------------------------
    # Memory policies (max size / pruning / expiration / archival)
    # ------------------------------------------------------------------
    async def enforce_policies(self) -> PolicyReport:
        """Apply retention + max-size policies. Safe to call repeatedly
        (e.g. on app startup and periodically); every step is best-effort
        and never raises.
        """
        max_memories = getattr(self._settings.memory, "max_memories", 0) or 0
        retention_days = getattr(self._settings.memory, "retention_days", 0) or 0

        expired_ids: list[str] = []
        pruned_ids: list[str] = []

        # 1. Expiration — rows whose explicit expires_at has passed.
        try:
            async with self._db.session() as sess:  # type: ignore[assignment]
                repo = MemoryRepository(sess)  # type: ignore[arg-type]
                expired_rows = await repo.list_expired(as_of=datetime.now(UTC))
                for row in expired_rows:
                    await repo.archive(row.id)
                    expired_ids.append(row.id)
        except Exception as err:
            _logger.warning("Expiration pass failed: {}", err)

        # 2. Pruning — enforce the max-memories cap by archiving the
        #    oldest unpinned rows first.
        if max_memories > 0:
            try:
                async with self._db.session() as sess:  # type: ignore[assignment]
                    repo = MemoryRepository(sess)  # type: ignore[arg-type]
                    prunable = await repo.list_prunable(keep=max_memories)
                    for row in prunable:
                        await repo.archive(row.id)
                        pruned_ids.append(row.id)
            except Exception as err:
                _logger.warning("Pruning pass failed: {}", err)

        if expired_ids or pruned_ids:
            _logger.info(
                "Memory policy pass: expired={} pruned={} (archived, not deleted).",
                len(expired_ids),
                len(pruned_ids),
            )
        return PolicyReport(
            expired=len(expired_ids),
            pruned=len(pruned_ids),
            max_memories=max_memories,
            retention_days=retention_days,
        )

    async def delete_archived(self) -> int:
        """Hard-delete every archived memory from both stores.

        Call this after :meth:`enforce_policies` to actually reclaim
        space, or leave archived rows in place for manual review.
        """
        async with self._db.session() as sess:  # type: ignore[assignment]
            repo = MemoryRepository(sess)  # type: ignore[arg-type]
            rows = await repo.list(limit=1_000_000, include_archived=True)
            archived_ids = [r.id for r in rows if r.archived]
            for mid in archived_ids:
                await repo.delete(mid)
        if archived_ids:
            try:
                await self._vs.delete(archived_ids)
            except VectorStoreError as err:
                _logger.warning("Vector delete failed for archived rows: {}", err)
        return len(archived_ids)

    # ------------------------------------------------------------------
    # Export / Import
    # ------------------------------------------------------------------
    async def export_memories(self) -> str:
        """Dump every memory as a JSON array (content + metadata, not
        embeddings) for the Settings ▸ Memory ▸ "Export Memory" action.
        """
        async with self._db.session() as sess:  # type: ignore[assignment]
            rows = await MemoryRepository(sess).list(  # type: ignore[arg-type]
                limit=1_000_000, include_archived=True
            )
        payload = [
            {
                "id": r.id,
                "content": r.content,
                "source": r.source,
                "memory_type": r.memory_type,
                "metadata": json.loads(r.meta_json or "{}"),
                "conversation_id": r.conversation_id,
                "pinned": r.pinned,
                "archived": r.archived,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]
        return json.dumps({"version": 1, "memories": payload}, ensure_ascii=False, indent=2)

    async def import_memories(self, data: str) -> int:
        """Import memories previously produced by :meth:`export_memories`.

        Re-embeds every imported row (ids are regenerated) and returns the
        number of memories successfully imported. Malformed entries are
        skipped and logged rather than aborting the whole import.
        """
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError as err:
            raise ServiceError(f"Invalid memory export file: {err}") from err

        entries = parsed.get("memories", parsed) if isinstance(parsed, dict) else parsed
        if not isinstance(entries, list):
            raise ServiceError("Memory export must contain a list of memories.")

        imported = 0
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            content = str(entry.get("content", "")).strip()
            if not content:
                continue
            try:
                await self.remember(
                    content,
                    source=str(entry.get("source", "import")),
                    memory_type=str(entry.get("memory_type", MemoryType.CONVERSATION.value)),
                    metadata=entry.get("metadata") or {},
                    conversation_id=entry.get("conversation_id"),
                    pinned=bool(entry.get("pinned", False)),
                )
                imported += 1
            except ServiceError as err:
                _logger.warning("Skipping malformed memory entry on import: {}", err)
        _logger.info("Imported {} memories.", imported)
        return imported

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    async def _embed(self, text: str) -> list[float]:
        embeddings = await self._llm.embed([text])
        if not embeddings or not embeddings[0]:
            raise LLMProviderError("Embedding provider returned no vector.")
        return list(embeddings[0])

    async def _vs_query(
        self,
        embedding: list[float],
        *,
        top_k: int,
        where: dict[str, object] | None = None,
    ):
        # ChromaVectorStore exposes an extra, embedding-aware method;
        # fall back to text query for adapters that don't have it.
        vs = self._vs
        method = getattr(vs, "query_with_embedding", None)
        if method is not None:
            return await method(embedding, top_k=top_k, where=where)
        return await vs.query("", top_k=top_k, where=where)  # pragma: no cover — fallback

    async def _load_ordered(
        self,
        ids: list[str],
        *,
        vector_scores: dict[str, float],
    ) -> list[MemoryRecord]:
        async with self._db.session() as sess:  # type: ignore[assignment]
            repo = MemoryRepository(sess)  # type: ignore[arg-type]
            rows: list[Memory] = []
            for mid in ids:
                row = await repo.get(mid)
                if row is not None:
                    rows.append(row)
        return [_row_to_record(row, score=float(vector_scores.get(row.id, 0.0))) for row in rows]


# ---------------------------------------------------------------------------
# Row → value-object mapping
# ---------------------------------------------------------------------------
def _row_to_record(row: Memory, *, score: float = 0.0) -> MemoryRecord:
    try:
        meta = json.loads(row.meta_json or "{}")
    except json.JSONDecodeError:
        meta = {}
    return MemoryRecord(
        id=row.id,
        content=row.content,
        source=row.source,
        metadata=meta,
        score=score,
        created_at=row.created_at,
        memory_type=row.memory_type,
        pinned=row.pinned,
        archived=row.archived,
    )


# ---------------------------------------------------------------------------
# RRF utility
# ---------------------------------------------------------------------------
def _reciprocal_rank_fusion(*rankings: list[str], k: int = 60) -> list[str]:
    """Reciprocal Rank Fusion — small, well-known merger for hybrid search.

    See Cormack et al., 2009. `k=60` is the canonical default.
    """
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores, key=lambda d: scores[d], reverse=True)
