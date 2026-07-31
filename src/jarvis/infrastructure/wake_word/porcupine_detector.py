"""Picovoice Porcupine wake-word detector.

Runs Porcupine's frame-based detector against the default microphone on
a background thread, invoking ``callback(keyword)`` on the asyncio loop
whenever a keyword fires. Requires the ``pvporcupine`` + ``pvrecorder``
packages and a free Picovoice AccessKey.
"""

from __future__ import annotations

import asyncio
import threading
from typing import TYPE_CHECKING

from jarvis.core.exceptions import WakeWordError
from jarvis.core.interfaces.wake_word import DetectionCallback
from jarvis.core.logging.logger import get_logger

if TYPE_CHECKING:
    from jarvis.core.config.settings import WakeWordSettings

_logger = get_logger("jarvis.infrastructure.wake_word.porcupine")


class PorcupineWakeWordDetector:
    name: str = "porcupine"
    supported: bool = True

    def __init__(self, wake: WakeWordSettings) -> None:
        self._wake = wake
        self._thread: threading.Thread | None = None
        self._stop_flag = threading.Event()

    def _build_engine(self, keywords: list[str]):
        try:
            import pvporcupine
        except ImportError as err:
            raise WakeWordError(
                "Porcupine wake-word engine selected but 'pvporcupine' "
                "isn't installed. Run `pip install pvporcupine pvrecorder`."
            ) from err
        access_key = self._wake.access_key.get_secret_value()
        if not access_key:
            raise WakeWordError(
                "Porcupine wake-word engine selected but JARVIS_WAKE_ACCESS_KEY "
                "is empty. Get a free AccessKey from console.picovoice.ai."
            )
        try:
            if self._wake.model_path and self._wake.model_path.endswith(".ppn"):
                return pvporcupine.create(
                    access_key=access_key, keyword_paths=[self._wake.model_path]
                )
            return pvporcupine.create(access_key=access_key, keywords=keywords or ["jarvis"])
        except Exception as err:
            raise WakeWordError(f"Failed to initialize Porcupine: {err}") from err

    async def health(self) -> bool:
        try:
            import pvporcupine

            return True
        except ImportError:
            return False

    async def start(self, keywords: list[str], callback: DetectionCallback) -> None:
        await self.stop()
        self._stop_flag.clear()
        loop = asyncio.get_running_loop()
        engine = self._build_engine(keywords)

        def _run() -> None:
            try:
                from pvrecorder import PvRecorder
            except ImportError:
                _logger.error("pvrecorder not installed; Porcupine loop cannot start.")
                return
            recorder = PvRecorder(frame_length=engine.frame_length)
            recorder.start()
            try:
                while not self._stop_flag.is_set():
                    pcm = recorder.read()
                    idx = engine.process(pcm)
                    if idx >= 0:
                        word = keywords[idx] if idx < len(keywords) else "jarvis"
                        asyncio.run_coroutine_threadsafe(_invoke(callback, word), loop)
            finally:
                recorder.stop()
                recorder.delete()
                engine.delete()

        async def _invoke(cb: DetectionCallback, word: str) -> None:
            result = cb(word)
            if asyncio.iscoroutine(result):
                await result

        self._thread = threading.Thread(target=_run, name="porcupine-wake-word", daemon=True)
        self._thread.start()

    async def stop(self) -> None:
        self._stop_flag.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
