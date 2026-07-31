"""Vision provider factory.

Milestone 6 (Vision & Multimodal) — Phase 3. Unlike the LLM/STT/TTS
factories, there is no backend selection yet — no real vision provider
exists, so this always returns :class:`MockVisionProvider`. A future
phase will add backend dispatch here once a real adapter is approved,
following the same shape as
:func:`~jarvis.infrastructure.stt.provider_factory.build_stt_provider`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from jarvis.core.interfaces.vision_provider import IVisionProvider

if TYPE_CHECKING:
    from jarvis.core.config.settings import VisionSettings


def build_vision_provider(vision: VisionSettings) -> IVisionProvider:
    from jarvis.infrastructure.vision.mock_provider import MockVisionProvider

    return MockVisionProvider(vision)
