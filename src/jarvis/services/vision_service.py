"""Vision service — reports vision/OCR provider availability.

Milestone 6 (Vision & Multimodal) — Phase 4. Deliberately as thin as
:class:`~jarvis.services.system_service.SystemService`: the only
concrete providers wired in so far are the Phase 3 mocks, so the only
honest thing this service can do is report that vision/OCR are
unavailable. No capture, OCR, image handling, or image storage.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from jarvis.core.config.settings import Settings
    from jarvis.core.interfaces.ocr_provider import IOCRProvider
    from jarvis.core.interfaces.vision_provider import IVisionProvider


class VisionService:
    def __init__(self, vision: IVisionProvider, ocr: IOCRProvider, settings: Settings) -> None:
        self._vision = vision
        self._ocr = ocr
        self._settings = settings

    async def status(self) -> dict[str, object]:
        """Reports vision/OCR provider availability by querying both
        providers' ``health()``. Honestly reflects that no real provider
        exists yet -- neither section will report ``healthy: True``."""
        vision_status = await self._vision.health()
        ocr_status = await self._ocr.health()
        return {
            "vision": {
                "provider": vision_status.name,
                "enabled": vision_status.enabled,
                "healthy": vision_status.healthy,
                "detail": vision_status.detail,
            },
            "ocr": {
                "provider": ocr_status.name,
                "enabled": ocr_status.enabled,
                "healthy": ocr_status.healthy,
                "detail": ocr_status.detail,
            },
        }
