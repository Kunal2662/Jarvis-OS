"""No-op wake-word detector — used when wake-word detection is disabled.

Always "supported" (there's nothing to fail), never actually fires. This
lets ``VoiceService`` treat "wake word off" the same as "wake word on
with an engine" structurally — no ``if detector is None`` branches.
"""

from __future__ import annotations


class NoopWakeWordDetector:
    name: str = "none"
    supported: bool = True

    async def start(self, keywords: list[str], callback) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def health(self) -> bool:
        return True
