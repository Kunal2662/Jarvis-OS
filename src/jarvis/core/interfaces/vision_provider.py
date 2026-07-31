"""Vision provider port.

Milestone 6 (Vision & Multimodal) — Phase 1. Mirrors the shape of
:class:`~jarvis.core.interfaces.llm_provider.ILLMProvider`, kept
intentionally minimal (``name`` + ``health()`` only) until a real
provider exists to validate the full method surface against, exactly
as :class:`~jarvis.core.interfaces.providers.IGmailProvider` stayed
read-mostly until a real Gmail adapter was built.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from jarvis.core.types import ProviderStatus


@runtime_checkable
class IVisionProvider(Protocol):
    """Abstract vision provider.

    Implementations must be safe to share across coroutines (a single
    provider instance is registered as a DI singleton).
    """

    name: str

    async def health(self) -> ProviderStatus: ...
