"""Voice input/output settings page.

Redesigned so every TTS provider (Piper, Kokoro, Edge TTS, ElevenLabs,
OpenAI) can be switched from here with zero code changes — the provider
factory (:mod:`jarvis.infrastructure.tts.provider_factory`) is a
registry keyed by the same ``TTSBackend`` enum this page edits.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QStackedWidget,
    QWidget,
)

from jarvis.core.types import STTBackend, TTSBackend, VoiceMode
from jarvis.ui.dialogs.settings_pages.base import SettingsPage
from jarvis.utils.async_utils import fire_and_forget

_TTS_MODELS = ["tts-1", "tts-1-hd"]
_WHISPER_MODELS = ["tiny", "base", "small", "medium", "large-v3"]
_EDGE_VOICES = ["en-US-AriaNeural", "en-US-GuyNeural", "en-GB-RyanNeural", "en-GB-SoniaNeural"]


def _list_audio_devices() -> tuple[list[str], list[str]]:
    """Best-effort list of (input names, output names). Empty on failure."""
    try:
        import sounddevice as sd

        devices = sd.query_devices()
        inputs = [d["name"] for d in devices if d.get("max_input_channels", 0) > 0]
        outputs = [d["name"] for d in devices if d.get("max_output_channels", 0) > 0]
        return inputs, outputs
    except Exception:
        return [], []


class VoicePage(SettingsPage):
    id = "voice"
    title = "Voice Input & Output"
    category = "Voice"

    def build(self) -> None:
        title = QLabel(self.title)
        title.setStyleSheet("font-size:20px; font-weight:600;")
        self._layout.addWidget(title)

        form = QFormLayout()
        form.setContentsMargins(0, 8, 0, 0)
        form.setSpacing(12)

        # --- STT --------------------------------------------------------
        self._stt_enabled = QCheckBox("Speech-to-text enabled")
        self._stt_enabled.setChecked(self._settings.stt.enabled)
        self._stt_enabled.toggled.connect(
            lambda v: self._persist(
                "JARVIS_STT_ENABLED", "true" if v else "false", "stt.enabled", v
            )
        )
        form.addRow(self._stt_enabled)

        self._stt_backend = QComboBox()
        for b in STTBackend:
            self._stt_backend.addItem(b.value, b)
        idx = self._stt_backend.findData(self._settings.stt.backend)
        if idx >= 0:
            self._stt_backend.setCurrentIndex(idx)
        self._stt_backend.currentIndexChanged.connect(self._on_stt_backend)
        form.addRow("STT backend", self._stt_backend)

        self._whisper_model = QComboBox()
        self._whisper_model.setEditable(True)
        self._whisper_model.addItems(_WHISPER_MODELS)
        self._whisper_model.setCurrentText(self._settings.stt.model)
        self._whisper_model.editTextChanged.connect(self._on_whisper_model)
        form.addRow("Whisper model", self._whisper_model)

        self._stt_lang = QLineEdit(self._settings.stt.language)
        self._stt_lang.editingFinished.connect(self._on_stt_lang)
        form.addRow("Language (ISO code)", self._stt_lang)

        # --- TTS provider selection --------------------------------------
        self._tts_enabled = QCheckBox("Text-to-speech enabled")
        self._tts_enabled.setChecked(self._settings.tts.enabled)
        self._tts_enabled.toggled.connect(
            lambda v: self._persist(
                "JARVIS_TTS_ENABLED", "true" if v else "false", "tts.enabled", v
            )
        )
        form.addRow(self._tts_enabled)

        self._tts_backend = QComboBox()
        for b in TTSBackend:
            self._tts_backend.addItem(b.value, b)
        idx = self._tts_backend.findData(self._settings.tts.backend)
        if idx >= 0:
            self._tts_backend.setCurrentIndex(idx)
        self._tts_backend.currentIndexChanged.connect(self._on_tts_backend)
        form.addRow("TTS provider", self._tts_backend)

        # Per-provider fields — one stacked page per backend, switched by
        # the combo box above. No provider-specific logic anywhere else.
        self._provider_stack = QStackedWidget()
        self._provider_pages: dict[TTSBackend, QWidget] = {}
        for backend in TTSBackend:
            page = self._build_provider_page(backend)
            self._provider_pages[backend] = page
            self._provider_stack.addWidget(page)
        current_backend: TTSBackend = self._tts_backend.currentData()
        self._provider_stack.setCurrentWidget(self._provider_pages[current_backend])
        form.addRow(self._provider_stack)

        self._tts_streaming = QCheckBox(
            "Streaming synthesis (speak before the full reply is ready)"
        )
        self._tts_streaming.setChecked(self._settings.tts.streaming)
        self._tts_streaming.toggled.connect(
            lambda v: self._persist(
                "JARVIS_TTS_STREAMING", "true" if v else "false", "tts.streaming", v
            )
        )
        form.addRow(self._tts_streaming)

        self._tts_speed = QDoubleSpinBox()
        self._tts_speed.setRange(0.25, 4.0)
        self._tts_speed.setSingleStep(0.05)
        self._tts_speed.setValue(self._settings.tts.playback_speed)
        self._tts_speed.valueChanged.connect(self._on_tts_speed)
        form.addRow("Playback speed", self._tts_speed)

        self._tts_pitch = QDoubleSpinBox()
        self._tts_pitch.setRange(0.5, 2.0)
        self._tts_pitch.setSingleStep(0.05)
        self._tts_pitch.setValue(self._settings.tts.pitch)
        self._tts_pitch.valueChanged.connect(
            lambda v: self._persist("JARVIS_TTS_PITCH", f"{v:.2f}", "tts.pitch", v)
        )
        form.addRow("Pitch", self._tts_pitch)

        self._tts_volume = QDoubleSpinBox()
        self._tts_volume.setRange(0.0, 2.0)
        self._tts_volume.setSingleStep(0.05)
        self._tts_volume.setValue(self._settings.tts.volume)
        self._tts_volume.valueChanged.connect(
            lambda v: self._persist("JARVIS_TTS_VOLUME", f"{v:.2f}", "tts.volume", v)
        )
        form.addRow("Volume", self._tts_volume)

        self._speak_replies = QCheckBox("Auto-speak assistant replies")
        self._speak_replies.setChecked(self._settings.tts.speak_replies)
        self._speak_replies.toggled.connect(
            lambda v: self._persist(
                "JARVIS_TTS_SPEAK_REPLIES", "true" if v else "false", "tts.speak_replies", v
            )
        )
        form.addRow(self._speak_replies)

        # --- Devices ------------------------------------------------------
        inputs, outputs = _list_audio_devices()
        self._input_device = QComboBox()
        self._input_device.setEditable(True)
        self._input_device.addItem("")
        self._input_device.addItems(inputs)
        self._input_device.setCurrentText(self._settings.voice.input_device)
        self._input_device.currentTextChanged.connect(
            lambda t: self._persist("JARVIS_VOICE_INPUT_DEVICE", t, "voice.input_device", t)
        )
        form.addRow("Microphone", self._input_device)

        self._output_device = QComboBox()
        self._output_device.setEditable(True)
        self._output_device.addItem("")
        self._output_device.addItems(outputs)
        self._output_device.setCurrentText(self._settings.voice.output_device)
        self._output_device.currentTextChanged.connect(
            lambda t: self._persist("JARVIS_VOICE_OUTPUT_DEVICE", t, "voice.output_device", t)
        )
        form.addRow("Speaker", self._output_device)

        # --- Interaction mode + hotkeys -----------------------------------
        self._voice_mode = QComboBox()
        for m in VoiceMode:
            self._voice_mode.addItem(m.value, m)
        idx = self._voice_mode.findData(self._settings.voice.mode)
        if idx >= 0:
            self._voice_mode.setCurrentIndex(idx)
        self._voice_mode.currentIndexChanged.connect(self._on_mode)
        form.addRow("Interaction mode", self._voice_mode)

        self._ptt_hotkey = QLineEdit(self._settings.voice.push_to_talk_hotkey)
        self._ptt_hotkey.editingFinished.connect(self._on_ptt_hotkey)
        form.addRow("Push-to-talk hotkey", self._ptt_hotkey)

        self._toggle_hotkey = QLineEdit(self._settings.voice.toggle_hotkey)
        self._toggle_hotkey.editingFinished.connect(self._on_toggle_hotkey)
        form.addRow("Toggle listen hotkey", self._toggle_hotkey)

        self._continuous = QCheckBox("Continuous conversation (auto-listen after JARVIS replies)")
        self._continuous.setChecked(self._settings.voice.continuous_conversation)
        self._continuous.toggled.connect(
            lambda v: self._persist(
                "JARVIS_VOICE_CONTINUOUS_CONVERSATION",
                "true" if v else "false",
                "voice.continuous_conversation",
                v,
            )
        )
        form.addRow(self._continuous)

        self._interrupt_enabled = QCheckBox("Allow interrupting JARVIS while speaking")
        self._interrupt_enabled.setChecked(self._settings.voice.interrupt_enabled)
        self._interrupt_enabled.toggled.connect(
            lambda v: self._persist(
                "JARVIS_VOICE_INTERRUPT_ENABLED",
                "true" if v else "false",
                "voice.interrupt_enabled",
                v,
            )
        )
        form.addRow(self._interrupt_enabled)

        self._interrupt_threshold = QDoubleSpinBox()
        self._interrupt_threshold.setRange(0.0, 1.0)
        self._interrupt_threshold.setSingleStep(0.01)
        self._interrupt_threshold.setDecimals(3)
        self._interrupt_threshold.setValue(self._settings.voice.interrupt_vad_threshold)
        self._interrupt_threshold.valueChanged.connect(
            lambda v: self._persist(
                "JARVIS_VOICE_INTERRUPT_VAD_THRESHOLD",
                f"{v:.3f}",
                "voice.interrupt_vad_threshold",
                v,
            )
        )
        form.addRow("Interrupt sensitivity", self._interrupt_threshold)

        self._layout.addLayout(form)

        note = QLabel(
            "Hotkey, device and mode changes take effect on the next launch. "
            "Wake-word setup lives on the Wake Word page."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color:#6D8BAA;")
        self._layout.addWidget(note)
        self._layout.addStretch(1)

    # ------------------------------------------------------------------
    # Per-provider sub-pages
    # ------------------------------------------------------------------
    def _build_provider_page(self, backend: TTSBackend) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(8)

        if backend is TTSBackend.PIPER:
            voice = QLineEdit(self._settings.piper.voice)
            voice.editingFinished.connect(
                lambda: self._persist(
                    "JARVIS_PIPER_VOICE", voice.text().strip(), "piper.voice", voice.text().strip()
                )
            )
            form.addRow("Piper voice model", voice)
            exe = QLineEdit(self._settings.piper.executable)
            exe.editingFinished.connect(
                lambda: self._persist(
                    "JARVIS_PIPER_EXECUTABLE",
                    exe.text().strip(),
                    "piper.executable",
                    exe.text().strip(),
                )
            )
            form.addRow("Piper executable", exe)
            hint = QLabel("Fully offline — no API key or network needed.")
            hint.setStyleSheet("color:#6D8BAA;")
            form.addRow(hint)

        elif backend is TTSBackend.KOKORO:
            voice = QLineEdit(self._settings.kokoro.voice)
            voice.editingFinished.connect(
                lambda: self._persist(
                    "JARVIS_KOKORO_VOICE",
                    voice.text().strip(),
                    "kokoro.voice",
                    voice.text().strip(),
                )
            )
            form.addRow("Kokoro voice", voice)
            lang = QLineEdit(self._settings.kokoro.language)
            lang.editingFinished.connect(
                lambda: self._persist(
                    "JARVIS_KOKORO_LANGUAGE",
                    lang.text().strip(),
                    "kokoro.language",
                    lang.text().strip(),
                )
            )
            form.addRow("Language", lang)
            hint = QLabel("Offline, requires the optional 'kokoro-onnx' package.")
            hint.setStyleSheet("color:#6D8BAA;")
            form.addRow(hint)

        elif backend is TTSBackend.EDGE_TTS:
            voice = QComboBox()
            voice.setEditable(True)
            voice.addItems(_EDGE_VOICES)
            voice.setCurrentText(self._settings.edge_tts.voice)
            voice.currentTextChanged.connect(
                lambda t: self._persist(
                    "JARVIS_EDGE_TTS_VOICE", t.strip(), "edge_tts.voice", t.strip()
                )
            )
            form.addRow("Edge voice", voice)
            hint = QLabel("Free, online, streams incrementally — good low-latency default.")
            hint.setWordWrap(True)
            hint.setStyleSheet("color:#6D8BAA;")
            form.addRow(hint)

        elif backend is TTSBackend.ELEVENLABS:
            voice_id = QLineEdit(self._settings.elevenlabs.voice_id)
            voice_id.editingFinished.connect(
                lambda: self._persist(
                    "JARVIS_ELEVENLABS_VOICE_ID",
                    voice_id.text().strip(),
                    "elevenlabs.voice_id",
                    voice_id.text().strip(),
                )
            )
            form.addRow("Voice ID", voice_id)
            api_key = QLineEdit()
            api_key.setEchoMode(QLineEdit.EchoMode.Password)
            api_key.setPlaceholderText("sk_... (leave blank to keep current)")
            api_key.editingFinished.connect(
                lambda: self._persist_secret("JARVIS_ELEVENLABS_API_KEY", api_key)
            )
            form.addRow("API key", api_key)
            hint = QLabel("Premium, online, most natural voices — streams incrementally.")
            hint.setWordWrap(True)
            hint.setStyleSheet("color:#6D8BAA;")
            form.addRow(hint)

        else:  # OpenAI
            voice = QComboBox()
            voice.setEditable(True)
            voice.addItems(["alloy", "echo", "fable", "onyx", "nova", "shimmer"])
            voice.setCurrentText(self._settings.tts.voice)
            voice.currentTextChanged.connect(
                lambda t: self._persist("JARVIS_TTS_VOICE", t.strip(), "tts.voice", t.strip())
            )
            form.addRow("Voice", voice)
            model = QComboBox()
            model.setEditable(True)
            model.addItems(_TTS_MODELS)
            model.setCurrentText(self._settings.tts.model)
            model.currentTextChanged.connect(
                lambda t: self._persist("JARVIS_TTS_MODEL", t.strip(), "tts.model", t.strip())
            )
            form.addRow("Model", model)
            hint = QLabel("Online, uses the OpenAI API key from the AI page.")
            hint.setStyleSheet("color:#6D8BAA;")
            form.addRow(hint)

        return page

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _persist(self, env_key: str, env_value: str, attr_path: str, live_value) -> None:
        # Apply live value on the in-memory settings.
        node = self._settings
        parts = attr_path.split(".")
        for p in parts[:-1]:
            node = getattr(node, p)
        setattr(node, parts[-1], live_value)
        fire_and_forget(self._service.set_env(env_key, env_value))

    def _persist_secret(self, env_key: str, field: QLineEdit) -> None:
        text = field.text().strip()
        if not text:
            return
        from pydantic import SecretStr

        node = self._settings
        for p in ["elevenlabs"]:
            node = getattr(node, p)
        node.api_key = SecretStr(text)
        fire_and_forget(self._service.set_env(env_key, text))
        field.clear()

    def _on_stt_backend(self) -> None:
        b: STTBackend = self._stt_backend.currentData()
        self._persist("JARVIS_STT_BACKEND", b.value, "stt.backend", b)

    def _on_whisper_model(self, text: str) -> None:
        text = text.strip()
        if text:
            self._persist("JARVIS_STT_MODEL", text, "stt.model", text)

    def _on_stt_lang(self) -> None:
        text = self._stt_lang.text().strip()
        if text:
            self._persist("JARVIS_STT_LANGUAGE", text, "stt.language", text)

    def _on_tts_backend(self) -> None:
        b: TTSBackend = self._tts_backend.currentData()
        self._persist("JARVIS_TTS_BACKEND", b.value, "tts.backend", b)
        self._provider_stack.setCurrentWidget(self._provider_pages[b])

    def _on_tts_speed(self, value: float) -> None:
        self._persist("JARVIS_TTS_PLAYBACK_SPEED", f"{value:.2f}", "tts.playback_speed", value)

    def _on_mode(self) -> None:
        m: VoiceMode = self._voice_mode.currentData()
        self._persist("JARVIS_VOICE_MODE", m.value, "voice.mode", m)

    def _on_ptt_hotkey(self) -> None:
        text = self._ptt_hotkey.text().strip()
        if text:
            self._persist(
                "JARVIS_VOICE_PUSH_TO_TALK_HOTKEY", text, "voice.push_to_talk_hotkey", text
            )

    def _on_toggle_hotkey(self) -> None:
        text = self._toggle_hotkey.text().strip()
        if text:
            self._persist("JARVIS_VOICE_TOGGLE_HOTKEY", text, "voice.toggle_hotkey", text)
