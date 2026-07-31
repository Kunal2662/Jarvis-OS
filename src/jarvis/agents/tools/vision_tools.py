"""Agent tools wrapping :class:`~jarvis.services.vision_service.VisionService`.

Milestone 6 (Vision & Multimodal) — Phase 5. Reports provider
availability only — no capture, OCR, image analysis, or processing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from langchain_core.tools import BaseTool, tool

if TYPE_CHECKING:
    from jarvis.services.vision_service import VisionService


def build_vision_tools(vision: VisionService) -> list[BaseTool]:
    @tool
    async def vision_status() -> str:
        """Check whether JARVIS's vision and OCR providers are available.
        Returns their current status; does not capture, analyze, or
        process any image."""
        return str(await vision.status())

    return [vision_status]
