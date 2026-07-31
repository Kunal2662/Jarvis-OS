"""ChromaDB adapter — persistent client anchored at
``<data_dir>/vectorstore/``.

Embeddings are supplied by the caller (via the injected LLM provider)
so the vector store never talks to the internet on its own — it just
stores whatever floats it's given.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from jarvis.core.exceptions import VectorStoreError
from jarvis.core.interfaces.vector_store import (
    IVectorStore,
    VectorRecord,
    VectorSearchResult,
)
from jarvis.core.logging.logger import get_logger

if TYPE_CHECKING:
    from jarvis.core.config.settings import VectorStoreSettings

_logger = get_logger("jarvis.infrastructure.vectorstore.chroma")


class ChromaVectorStore(IVectorStore):
    """Persistent Chroma collection.

    Records may carry precomputed ``embedding`` values in their
    ``metadata`` dict under the reserved key ``"__embedding__"``. When
    absent, the caller is responsible for providing embeddings out of
    band via :meth:`upsert_with_embeddings` / :meth:`query_with_embedding`.
    """

    _EMB_KEY = "__embedding__"

    def __init__(self, settings: VectorStoreSettings) -> None:
        self._settings = settings
        self._client = None
        self._collection = None

    # ------------------------------------------------------------------
    def _client_or_init(self):
        if self._client is not None:
            return self._client
        try:
            import chromadb
            from chromadb.config import Settings as ChromaSettings
        except ImportError as err:  # pragma: no cover
            raise VectorStoreError(
                "chromadb not installed. Add `chromadb` to requirements.txt."
            ) from err

        self._settings.dir.mkdir(parents=True, exist_ok=True)
        try:
            self._client = chromadb.PersistentClient(
                path=str(self._settings.dir),
                settings=ChromaSettings(anonymized_telemetry=False),
            )
            self._collection = self._client.get_or_create_collection(
                name=self._settings.collection,
                metadata={"hnsw:space": "cosine"},
            )
            _logger.info(
                "Chroma ready at {} (collection={}).",
                self._settings.dir,
                self._settings.collection,
            )
            return self._client
        except Exception as err:
            raise VectorStoreError(f"Cannot initialise Chroma: {err}") from err

    def _coll(self):
        self._client_or_init()
        return self._collection

    # ------------------------------------------------------------------
    # IVectorStore
    # ------------------------------------------------------------------
    async def upsert(self, records: Sequence[VectorRecord]) -> None:
        """Upsert records.

        Each record's ``metadata['__embedding__']`` must be a
        ``list[float]``. When missing, this method falls back to
        Chroma's default embedding function (which uses the network
        — avoid in production).
        """
        if not records:
            return
        ids: list[str] = []
        docs: list[str] = []
        metas: list[dict] = []
        embeddings: list[list[float]] = []
        has_embeddings = True
        for rec in records:
            ids.append(rec.id)
            docs.append(rec.document)
            meta = dict(rec.metadata or {})
            emb = meta.pop(self._EMB_KEY, None)
            if emb is None:
                has_embeddings = False
            else:
                embeddings.append(list(emb))
            metas.append(meta or {"_": ""})

        try:
            if has_embeddings and len(embeddings) == len(ids):
                self._coll().upsert(ids=ids, documents=docs, metadatas=metas, embeddings=embeddings)
            else:
                self._coll().upsert(ids=ids, documents=docs, metadatas=metas)
        except Exception as err:
            raise VectorStoreError(f"Chroma upsert failed: {err}") from err

    async def query(
        self,
        text: str,
        *,
        top_k: int = 5,
        where: dict[str, object] | None = None,
    ) -> list[VectorSearchResult]:
        """Text-based query — Chroma will embed the query on the fly."""
        try:
            result = self._coll().query(
                query_texts=[text],
                n_results=top_k,
                where=where or None,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as err:
            raise VectorStoreError(f"Chroma query failed: {err}") from err
        return _format_results(result)

    async def query_with_embedding(
        self,
        embedding: Sequence[float],
        *,
        top_k: int = 5,
        where: dict[str, object] | None = None,
    ) -> list[VectorSearchResult]:
        """Query using a precomputed embedding — the primary path used
        by :class:`MemoryService` so the LLM provider owns embeddings.
        """
        try:
            result = self._coll().query(
                query_embeddings=[list(embedding)],
                n_results=top_k,
                where=where or None,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as err:
            raise VectorStoreError(f"Chroma query failed: {err}") from err
        return _format_results(result)

    async def delete(self, ids: Sequence[str]) -> None:
        if not ids:
            return
        try:
            self._coll().delete(ids=list(ids))
        except Exception as err:
            raise VectorStoreError(f"Chroma delete failed: {err}") from err

    async def count(self) -> int:
        try:
            return int(self._coll().count())
        except Exception as err:
            raise VectorStoreError(f"Chroma count failed: {err}") from err


def _format_results(result: dict) -> list[VectorSearchResult]:
    ids = (result.get("ids") or [[]])[0]
    docs = (result.get("documents") or [[]])[0]
    metas = (result.get("metadatas") or [[]])[0]
    dists = (result.get("distances") or [[]])[0]
    out: list[VectorSearchResult] = []
    for i, doc_id in enumerate(ids):
        # Cosine distance in [0,2]; convert to a 0..1 similarity.
        distance = float(dists[i]) if i < len(dists) else 0.0
        score = max(0.0, 1.0 - distance)
        out.append(
            VectorSearchResult(
                id=str(doc_id),
                document=str(docs[i] if i < len(docs) else ""),
                score=score,
                metadata=metas[i] if i < len(metas) else None,
            )
        )
    return out
