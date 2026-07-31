"""Fake audio, hotkey, STT, TTS providers for unit tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

from jarvis.core.interfaces.audio import AudioChunk, IAudioPlayer, IAudioRecorder
from jarvis.core.interfaces.hotkey import HotkeyCallback, IHotkeyListener
from jarvis.core.interfaces.stt_provider import ISTTProvider
from jarvis.core.interfaces.tts_provider import ITTSProvider
from jarvis.core.types import ProviderStatus


class FakeRecorder(IAudioRecorder):
    name = "fake"

    def __init__(self, canned: bytes = b"\x00\x00" * 8000, sample_rate: int = 16000) -> None:
        self._canned = canned
        self._sr = sample_rate
        self._started = False

    async def health(self) -> bool:
        return True

    async def start(self) -> None:
        self._started = True

    async def stop(self) -> AudioChunk:
        if not self._started:
            return AudioChunk(b"", self._sr)
        self._started = False
        return AudioChunk(self._canned, self._sr)

    async def stream(self) -> AsyncIterator[AudioChunk]:  # pragma: no cover
        yield AudioChunk(self._canned, self._sr)


class FakePlayer(IAudioPlayer):
    name = "fake"

    def __init__(self) -> None:
        self.played: list[tuple[bytes, str]] = []
        self.stopped: int = 0
        self._playing: bool = False

    async def health(self) -> bool:
        return True

    async def play_bytes(self, data: bytes, *, mime: str = "audio/mpeg") -> None:
        self._playing = True
        self.played.append((data, mime))
        self._playing = False

    async def play_stream(self, chunks: AsyncIterator[bytes], *, mime: str = "audio/mpeg") -> None:
        self._playing = True
        async for chunk in chunks:
            self.played.append((chunk, mime))
        self._playing = False

    async def stop(self) -> None:
        self.stopped += 1
        self._playing = False

    @property
    def is_playing(self) -> bool:
        return self._playing


class FakeHotkeyListener(IHotkeyListener):
    name = "fake"

    def __init__(self) -> None:
        self.bindings: dict[str, HotkeyCallback] = {}
        self.started: bool = False

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.started = False

    def bind(self, combo: str, callback: HotkeyCallback) -> None:
        self.bindings[combo.lower()] = callback

    def unbind(self, combo: str) -> None:
        self.bindings.pop(combo.lower(), None)

    def rebind(self, old: str, new: str, callback: HotkeyCallback) -> None:
        self.unbind(old)
        self.bind(new, callback)

    async def trigger(self, combo: str) -> None:
        """Test helper — simulate a hotkey press."""
        cb = self.bindings.get(combo.lower())
        if cb is None:
            raise KeyError(combo)
        import asyncio

        result = cb()
        if asyncio.iscoroutine(result):
            await result


class FakeSTT(ISTTProvider):
    name = "fake_stt"

    def __init__(self, canned: str = "hello world") -> None:
        self._canned = canned

    async def health(self) -> ProviderStatus:
        return ProviderStatus(name=self.name, enabled=True, healthy=True)

    async def transcribe_file(self, audio_path: Path, *, language: str | None = None) -> str:
        return self._canned

    async def transcribe_bytes(
        self, audio: bytes, *, sample_rate: int, language: str | None = None
    ) -> str:
        return self._canned if audio else ""


class FakeTTS(ITTSProvider):
    name = "fake_tts"
    supports_streaming = False

    def __init__(self, canned: bytes = b"FAKE-AUDIO") -> None:
        self._canned = canned

    async def health(self) -> ProviderStatus:
        return ProviderStatus(name=self.name, enabled=True, healthy=True)

    async def synthesize_to_bytes(
        self, text: str, *, voice: str | None = None, model: str | None = None
    ) -> bytes:
        return self._canned if text.strip() else b""

    async def synthesize_to_file(
        self,
        text: str,
        output_path: Path,
        *,
        voice: str | None = None,
        model: str | None = None,
    ) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(self._canned)
        return output_path

    async def synthesize_stream(
        self, text: str, *, voice: str | None = None, model: str | None = None
    ) -> AsyncIterator[bytes]:
        if text.strip():
            yield self._canned
