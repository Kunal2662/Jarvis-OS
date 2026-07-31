"""Speech-to-text provider port."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from jarvis.core.types import ProviderStatus


@runtime_checkable
class ISTTProvider(Protocol):
    """Abstract STT provider."""

    name: str

    async def health(self) -> ProviderStatus: ...

    async def transcribe_file(
        self,
        audio_path: Path,
        *,
        language: str | None = None,
    ) -> str: ...

    async def transcribe_bytes(
        self,
        audio: bytes,
        *,
        sample_rate: int,
        language: str | None = None,
    ) -> str: ...
