"""Mock OCR adapter.

Milestone 6 (Vision & Multimodal) — Phase 3. The only concrete
:class:`~jarvis.core.interfaces.ocr_provider.IOCRProvider` this phase
provides: it honestly reports that no OCR provider is configured yet,
following the same "clean interface, mock-backed until a real adapter
exists" pattern already used for
:class:`~jarvis.core.interfaces.providers.IGmailProvider` /
:class:`~jarvis.features.integrations.mocks.MockGmailProvider`. No
OCR, no image processing, no real capability of any kind.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from jarvis.core.interfaces.ocr_provider import IOCRProvider
from jarvis.core.types import ProviderStatus

if TYPE_CHECKING:
    from jarvis.core.config.settings import OCRSettings

_UNAVAILABLE_DETAIL = "OCR provider not yet configured — capture/OCR deferred to a later phase."


class MockOCRProvider(IOCRProvider):
    """Always-unavailable OCR provider."""

    name: str = "mock"

    def __init__(self, settings: OCRSettings) -> None:
        self._settings = settings

    async def health(self) -> ProviderStatus:
        return ProviderStatus(
            name=self.name,
            enabled=False,
            healthy=False,
            detail=_UNAVAILABLE_DETAIL,
        )
