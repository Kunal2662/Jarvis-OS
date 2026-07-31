"""Mock vision adapter.

Milestone 6 (Vision & Multimodal) — Phase 3. The only concrete
:class:`~jarvis.core.interfaces.vision_provider.IVisionProvider`
this phase provides: it honestly reports that no vision provider is
configured yet, following the same "clean interface, mock-backed
until a real adapter exists" pattern already used for
:class:`~jarvis.core.interfaces.providers.IGmailProvider` /
:class:`~jarvis.features.integrations.mocks.MockGmailProvider`. No
capture, no image processing, no real capability of any kind.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from jarvis.core.interfaces.vision_provider import IVisionProvider
from jarvis.core.types import ProviderStatus

if TYPE_CHECKING:
    from jarvis.core.config.settings import VisionSettings

_UNAVAILABLE_DETAIL = "Vision provider not yet configured — capture/OCR deferred to a later phase."


class MockVisionProvider(IVisionProvider):
    """Always-unavailable vision provider."""

    name: str = "mock"

    def __init__(self, settings: VisionSettings) -> None:
        self._settings = settings

    async def health(self) -> ProviderStatus:
        return ProviderStatus(
            name=self.name,
            enabled=False,
            healthy=False,
            detail=_UNAVAILABLE_DETAIL,
        )
