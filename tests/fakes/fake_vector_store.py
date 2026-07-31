"""Deterministic in-memory fake for :class:`IVectorStore`.

Mimics just enough of :class:`ChromaVectorStore` for
:class:`MemoryService` unit tests: cosine similarity over the tiny
4-dim vectors produced by :class:`tests.fakes.fake_llm.FakeLLM`, plus
metadata ``where`` filtering.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from jarvis.core.interfaces.vector_store import (
    IVectorStore,
    VectorRecord,
    VectorSearchResult,
)


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


class FakeVectorStore(IVectorStore):
    def __init__(self) -> None:
        self._docs: dict[str, str] = {}
        self._metas: dict[str, dict] = {}
        self._embeddings: dict[str, list[float]] = {}

    async def upsert(self, records: Sequence[VectorRecord]) -> None:
        for rec in records:
            meta = dict(rec.metadata or {})
            emb = meta.pop("__embedding__", None)
            self._docs[rec.id] = rec.document
            self._metas[rec.id] = meta
            if emb is not None:
                self._embeddings[rec.id] = list(emb)

    async def query(
        self,
        text: str,
        *,
        top_k: int = 5,
        where: dict[str, object] | None = None,
    ) -> list[VectorSearchResult]:
        # Text-only query has no embedding to compare against in the
        # fake — return recent-first, filtered by `where`.
        ids = self._filtered_ids(where)
        return [
            VectorSearchResult(id=i, document=self._docs[i], score=0.5, metadata=self._metas[i])
            for i in ids[:top_k]
        ]

    async def query_with_embedding(
        self,
        embedding: Sequence[float],
        *,
        top_k: int = 5,
        where: dict[str, object] | None = None,
    ) -> list[VectorSearchResult]:
        ids = self._filtered_ids(where)
        scored = [(i, _cosine(list(embedding), self._embeddings.get(i, []))) for i in ids]
        scored.sort(key=lambda t: t[1], reverse=True)
        return [
            VectorSearchResult(id=i, document=self._docs[i], score=s, metadata=self._metas[i])
            for i, s in scored[:top_k]
        ]

    async def delete(self, ids: Sequence[str]) -> None:
        for i in ids:
            self._docs.pop(i, None)
            self._metas.pop(i, None)
            self._embeddings.pop(i, None)

    async def count(self) -> int:
        return len(self._docs)

    def _filtered_ids(self, where: dict[str, object] | None) -> list[str]:
        ids = list(self._docs.keys())
        if not where:
            return ids
        return [i for i in ids if all(self._metas.get(i, {}).get(k) == v for k, v in where.items())]
