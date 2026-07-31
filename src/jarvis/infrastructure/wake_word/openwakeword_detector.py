"""openWakeWord detector — free, offline, community wake-word models.

Streams microphone frames through ``openwakeword``'s ONNX models on a
background thread. Requires the ``openwakeword`` and ``sounddevice``
packages.
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

_logger = get_logger("jarvis.infrastructure.wake_word.openwakeword")

_FRAME_MS = 80
_SAMPLE_RATE = 16000


class OpenWakeWordDetector:
    name: str = "openwakeword"
    supported: bool = True

    def __init__(self, wake: WakeWordSettings) -> None:
        self._wake = wake
        self._thread: threading.Thread | None = None
        self._stop_flag = threading.Event()

    def _build_model(self):
        try:
            from openwakeword.model import Model
        except ImportError as err:
            raise WakeWordError(
                "openWakeWord engine selected but the 'openwakeword' "
                "package isn't installed. Run `pip install openwakeword`."
            ) from err
        kwargs = {}
        if self._wake.model_path:
            kwargs["wakeword_models"] = [self._wake.model_path]
        return Model(**kwargs)

    async def health(self) -> bool:
        try:
            import openwakeword

            return True
        except ImportError:
            return False

    async def start(self, keywords: list[str], callback: DetectionCallback) -> None:
        await self.stop()
        self._stop_flag.clear()
        loop = asyncio.get_running_loop()
        model = self._build_model()
        threshold = self._wake.sensitivity

        def _run() -> None:
            try:
                import numpy as np
                import sounddevice as sd
            except (ImportError, OSError):
                _logger.error("sounddevice/numpy not available; openWakeWord cannot start.")
                return
            frame_len = int(_SAMPLE_RATE * _FRAME_MS / 1000)
            with sd.InputStream(
                samplerate=_SAMPLE_RATE, channels=1, dtype="int16", blocksize=frame_len
            ) as stream:
                while not self._stop_flag.is_set():
                    frame, _ = stream.read(frame_len)
                    audio = np.frombuffer(frame.tobytes(), dtype=np.int16)
                    predictions = model.predict(audio)
                    for name, score in predictions.items():
                        if score >= threshold:
                            asyncio.run_coroutine_threadsafe(_invoke(callback, name), loop)

        async def _invoke(cb: DetectionCallback, word: str) -> None:
            result = cb(word)
            if asyncio.iscoroutine(result):
                await result

        self._thread = threading.Thread(target=_run, name="openwakeword", daemon=True)
        self._thread.start()

    async def stop(self) -> None:
        self._stop_flag.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
