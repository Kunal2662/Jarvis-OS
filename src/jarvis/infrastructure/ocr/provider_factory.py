"""OCR provider factory.

Milestone 6 (Vision & Multimodal) — Phase 3. Unlike the LLM/STT/TTS
factories, there is no backend selection yet — no real OCR provider
exists, so this always returns :class:`MockOCRProvider`. A future
phase will add backend dispatch here once a real adapter is approved,
following the same shape as
:func:`~jarvis.infrastructure.stt.provider_factory.build_stt_provider`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from jarvis.core.interfaces.ocr_provider import IOCRProvider

if TYPE_CHECKING:
    from jarvis.core.config.settings import OCRSettings


def build_ocr_provider(ocr: OCRSettings) -> IOCRProvider:
    from jarvis.infrastructure.ocr.mock_provider import MockOCRProvider

    return MockOCRProvider(ocr)
