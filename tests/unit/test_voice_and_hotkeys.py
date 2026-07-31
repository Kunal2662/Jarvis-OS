"""Unit tests for :class:`VoiceService` and :class:`HotkeyService`."""

from __future__ import annotations

import pytest

from jarvis.core.config.settings import Settings
from jarvis.services.hotkey_service import HotkeyService
from jarvis.services.voice_service import VoiceService
from tests.fakes.fake_voice import (
    FakeHotkeyListener,
    FakePlayer,
    FakeRecorder,
    FakeSTT,
    FakeTTS,
)


def _settings() -> Settings:
    return Settings()  # defaults are fine for these unit tests


@pytest.mark.asyncio
async def test_voice_service_listen_returns_transcription() -> None:
    stt = FakeSTT("captured text")
    tts = FakeTTS()
    rec = FakeRecorder(canned=b"\x01\x02" * 100)
    player = FakePlayer()

    svc = VoiceService(stt, tts, rec, player, _settings())
    await svc.start_listening()
    assert svc.is_listening
    text = await svc.stop_listening()
    assert text == "captured text"
    assert not svc.is_listening


@pytest.mark.asyncio
async def test_voice_service_empty_recording_yields_empty_text() -> None:
    stt = FakeSTT("should not appear")
    rec = FakeRecorder(canned=b"")
    svc = VoiceService(stt, FakeTTS(), rec, FakePlayer(), _settings())
    await svc.start_listening()
    text = await svc.stop_listening()
    assert text == ""


@pytest.mark.asyncio
async def test_voice_service_speak_calls_player() -> None:
    tts = FakeTTS(b"AUDIO-BYTES")
    player = FakePlayer()
    svc = VoiceService(FakeSTT(), tts, FakeRecorder(), player, _settings())

    await svc.speak("Hello, world")

    assert len(player.played) == 1
    data, mime = player.played[0]
    assert data == b"AUDIO-BYTES"
    assert mime.startswith("audio/")


@pytest.mark.asyncio
async def test_voice_service_speak_ignores_empty_text() -> None:
    tts = FakeTTS(b"AUDIO")
    player = FakePlayer()
    svc = VoiceService(FakeSTT(), tts, FakeRecorder(), player, _settings())

    await svc.speak("   ")

    assert player.played == []


@pytest.mark.asyncio
async def test_voice_service_speak_stream_chunks_by_sentence() -> None:
    tts = FakeTTS(b"AUDIO")
    player = FakePlayer()
    svc = VoiceService(FakeSTT(), tts, FakeRecorder(), player, _settings())

    async def tokens():
        for tok in ["Hello there. ", "How are you? ", "Great"]:
            yield tok

    await svc.speak_stream(tokens())

    # Three sentence-shaped chunks: "Hello there.", "How are you?", "Great"
    assert len(player.played) == 3
    assert svc.state.value == "idle"


@pytest.mark.asyncio
async def test_voice_service_state_transitions_on_listen() -> None:
    svc = VoiceService(
        FakeSTT("hi"), FakeTTS(), FakeRecorder(canned=b"\x01\x02" * 50), FakePlayer(), _settings()
    )
    seen: list[str] = []
    svc.on_state_changed(lambda state, detail: seen.append(state.value))

    await svc.start_listening()
    await svc.stop_listening()

    assert "listening" in seen
    assert "thinking" in seen


@pytest.mark.asyncio
async def test_voice_service_interrupt_cancels_playback() -> None:
    tts = FakeTTS(b"AUDIO")
    player = FakePlayer()
    # A recorder whose stream immediately reports loud audio, simulating
    # the user talking over JARVIS mid-reply.
    rec = FakeRecorder(canned=b"\x7f\x7f" * 4000)
    settings = _settings()
    svc = VoiceService(FakeSTT(), tts, rec, player, settings)

    async def tokens():
        yield "This will be interrupted."

    await svc.speak_stream(tokens())

    # Either it played fully (barge-in lost the race) or it was cut off —
    # either way the service must land back in a sane, non-speaking state.
    assert svc.state.value in ("idle", "listening")


@pytest.mark.asyncio
async def test_hotkey_service_registers_and_fires() -> None:
    settings = _settings()
    listener = FakeHotkeyListener()
    svc = HotkeyService(listener, settings)

    fired: list[str] = []

    async def _on_ptt() -> None:
        fired.append("ptt")

    await svc.start()
    svc.register("ptt", "Ctrl+Space", _on_ptt)
    assert listener.started
    assert "ctrl+space" in listener.bindings

    await listener.trigger("ctrl+space")
    assert fired == ["ptt"]


@pytest.mark.asyncio
async def test_hotkey_service_rebinds_when_combo_changes() -> None:
    listener = FakeHotkeyListener()
    svc = HotkeyService(listener, _settings())
    await svc.start()

    fired: list[str] = []

    def _cb() -> None:
        fired.append("x")

    svc.register("ptt", "ctrl+a", _cb)
    svc.register("ptt", "ctrl+b", _cb)

    assert "ctrl+a" not in listener.bindings
    assert "ctrl+b" in listener.bindings
    assert svc.current_combo("ptt") == "ctrl+b"


@pytest.mark.asyncio
async def test_hotkey_service_disabled_when_config_off() -> None:
    settings = _settings()
    settings.hotkey.enabled = False
    listener = FakeHotkeyListener()
    svc = HotkeyService(listener, settings)

    await svc.start()

    assert listener.started is False


@pytest.mark.asyncio
async def test_hotkey_service_stop_delegates_to_listener() -> None:
    """stop() had zero test coverage -- directly relevant since it's
    registered with ShutdownManager (Milestone 5.5)."""
    listener = FakeHotkeyListener()
    svc = HotkeyService(listener, _settings())
    await svc.start()

    await svc.stop()

    assert listener.started is False


def test_hotkey_service_register_ignores_empty_combo() -> None:
    """Real guard clause that was untested: registering with a blank/
    whitespace-only combo (e.g. the user cleared a Settings field) must
    be a no-op, not bind an empty string as a hotkey."""
    listener = FakeHotkeyListener()
    svc = HotkeyService(listener, _settings())

    svc.register("ptt", "   ", lambda: None)

    assert listener.bindings == {}
    assert svc.current_combo("ptt") is None


def test_hotkey_service_register_same_combo_rebinds_callback() -> None:
    """The 'previous == combo' branch: re-registering the *same* combo
    (e.g. saving Settings without changing the hotkey) must still
    rebind with the fresh callback, not silently keep the stale one."""
    listener = FakeHotkeyListener()
    svc = HotkeyService(listener, _settings())

    calls = []
    svc.register("ptt", "ctrl+a", lambda: calls.append("old"))
    svc.register("ptt", "ctrl+a", lambda: calls.append("new"))  # same combo, new callback

    assert svc.current_combo("ptt") == "ctrl+a"
    listener.bindings["ctrl+a"]()
    assert calls == ["new"]  # the fresh callback fired, not the stale one


def test_hotkey_service_unregister_unbinds_and_clears_combo() -> None:
    """unregister() had zero test coverage at all."""
    listener = FakeHotkeyListener()
    svc = HotkeyService(listener, _settings())
    svc.register("ptt", "ctrl+a", lambda: None)

    svc.unregister("ptt")

    assert "ctrl+a" not in listener.bindings
    assert svc.current_combo("ptt") is None


def test_hotkey_service_unregister_unknown_semantic_is_a_no_op() -> None:
    """Real edge case: unregistering something never registered (e.g. a
    cleanup path that runs unconditionally) must not raise."""
    listener = FakeHotkeyListener()
    svc = HotkeyService(listener, _settings())

    svc.unregister("never-registered")  # must not raise
    assert listener.bindings == {}
