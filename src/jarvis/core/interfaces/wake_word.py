"""Wake-word detector port.

Reserved architecture for Milestone 2+. Concrete adapters (Porcupine,
openWakeWord, Vosk keyword-mode) will implement this port in a later
milestone; the port itself lives here so the ``VoiceService`` and settings
UI can be written today.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol, runtime_checkable

DetectionCallback = Callable[[str], "Awaitable[None] | None"]


@runtime_checkable
class IWakeWordDetector(Protocol):
    """Always-on keyword spotter."""

    name: str
    supported: bool

    async def start(self, keywords: list[str], callback: DetectionCallback) -> None: ...
    async def stop(self) -> None: ...
    async def health(self) -> bool: ...
