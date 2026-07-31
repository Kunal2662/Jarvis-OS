"""Vector-store port."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class VectorRecord:
    id: str
    document: str
    metadata: dict[str, str | int | float | bool] | None = None


@dataclass(frozen=True, slots=True)
class VectorSearchResult:
    id: str
    document: str
    score: float
    metadata: dict[str, str | int | float | bool] | None = None


@runtime_checkable
class IVectorStore(Protocol):
    """Abstract vector store (Chroma, FAISS, Qdrant, …)."""

    async def upsert(self, records: Sequence[VectorRecord]) -> None: ...

    async def query(
        self,
        text: str,
        *,
        top_k: int = 5,
        where: dict[str, object] | None = None,
    ) -> list[VectorSearchResult]: ...

    async def delete(self, ids: Sequence[str]) -> None: ...

    async def count(self) -> int: ...
