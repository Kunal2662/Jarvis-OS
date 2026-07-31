"""AI Voice Announcements (Milestone 5, section 10F).

During updates JARVIS should *naturally* announce phase changes. This
service maps a :class:`UpdatePhase` to a short spoken sentence (varied by
``style``) and, if a real :class:`VoiceService` is available, speaks it
through the existing TTS pipeline; otherwise it falls back to a mock that
just logs the line -- so this works identically in a headless test
environment and in the full desktop app. "Use mock services only" from
the brief is satisfied either way: no new TTS backend is added here, this
only reuses (or logs in place of) the one Milestone 2 already built.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from jarvis.core.logging.logger import get_logger
from jarvis.domain.updates.models import UpdatePhase
from jarvis.domain.voice_announcements.events import AnnouncementEvent

if TYPE_CHECKING:
    from jarvis.core.config.settings import Settings
    from jarvis.services.voice_service import VoiceService

_logger = get_logger("jarvis.services.voice_announcements")

_PHRASES: dict[UpdatePhase, dict[str, str]] = {
    UpdatePhase.CHECKING: {
        "formal": "Checking for available updates.",
        "friendly": "Just checking if there's anything new for me!",
        "concise": "Checking updates.",
    },
    UpdatePhase.DOWNLOADING: {
        "formal": "Downloading the update package.",
        "friendly": "Grabbing the update now, hang tight.",
        "concise": "Downloading.",
    },
    UpdatePhase.INSTALLING: {
        "formal": "Installing the update.",
        "friendly": "Installing the new bits for you.",
        "concise": "Installing.",
    },
    UpdatePhase.VERIFYING: {
        "formal": "Verifying the installation.",
        "friendly": "Double-checking everything looks right.",
        "concise": "Verifying.",
    },
    UpdatePhase.OPTIMIZING: {
        "formal": "Optimizing performance after the update.",
        "friendly": "Tidying things up for best performance.",
        "concise": "Optimizing.",
    },
    UpdatePhase.RESTART_REQUIRED: {
        "formal": "A restart is required to finish this update.",
        "friendly": "Almost done -- I'll need a quick restart.",
        "concise": "Restart required.",
    },
    UpdatePhase.ROLLBACK_STARTED: {
        "formal": "The update did not complete successfully. Restoring your previous version.",
        "friendly": "That didn't go as planned -- rolling things back now.",
        "concise": "Rolling back.",
    },
    UpdatePhase.ROLLBACK_COMPLETED: {
        "formal": "Your previous version, data and configuration have been restored.",
        "friendly": "All back to normal -- nothing was lost.",
        "concise": "Rollback complete.",
    },
    UpdatePhase.COMPLETED: {
        "formal": "The update has completed successfully.",
        "friendly": "All done -- you're on the latest version!",
        "concise": "Update complete.",
    },
    UpdatePhase.FAILED: {
        "formal": "The update did not complete successfully.",
        "friendly": "Hmm, that update didn't work out.",
        "concise": "Update failed.",
    },
}

# Milestone 5, section 9 -- the general app-lifecycle event vocabulary
# (startup through notifications), separate from the update-pipeline
# phrases above. Same three styles, same "log if no real VoiceService"
# fallback.
_EVENT_PHRASES: dict[AnnouncementEvent, dict[str, str]] = {
    AnnouncementEvent.STARTUP: {
        "formal": "JARVIS is now online.",
        "friendly": "Hey, I'm up and ready!",
        "concise": "Online.",
    },
    AnnouncementEvent.SHUTDOWN: {
        "formal": "Shutting down. Goodbye.",
        "friendly": "Powering down, see you soon!",
        "concise": "Shutting down.",
    },
    AnnouncementEvent.WAKE_WORD: {
        "formal": "Wake word detected.",
        "friendly": "Yes? I'm listening!",
        "concise": "Wake word.",
    },
    AnnouncementEvent.LISTENING: {
        "formal": "Listening.",
        "friendly": "Go ahead, I'm listening.",
        "concise": "Listening.",
    },
    AnnouncementEvent.THINKING: {
        "formal": "Processing your request.",
        "friendly": "Let me think about that…",
        "concise": "Thinking.",
    },
    AnnouncementEvent.SPEAKING: {
        "formal": "Responding now.",
        "friendly": "Here's what I found.",
        "concise": "Speaking.",
    },
    AnnouncementEvent.TASK_STARTED: {
        "formal": "Task started.",
        "friendly": "On it!",
        "concise": "Task started.",
    },
    AnnouncementEvent.TASK_COMPLETED: {
        "formal": "Task completed successfully.",
        "friendly": "All done!",
        "concise": "Task complete.",
    },
    AnnouncementEvent.BROWSER_AUTOMATION: {
        "formal": "Executing a browser automation.",
        "friendly": "Working in the browser for you.",
        "concise": "Browser automation.",
    },
    AnnouncementEvent.DESKTOP_AUTOMATION: {
        "formal": "Executing a desktop automation.",
        "friendly": "Working on your desktop now.",
        "concise": "Desktop automation.",
    },
    AnnouncementEvent.MEMORY_SAVED: {
        "formal": "Memory saved.",
        "friendly": "Got it, I'll remember that.",
        "concise": "Memory saved.",
    },
    AnnouncementEvent.MEMORY_RETRIEVED: {
        "formal": "Memory retrieved.",
        "friendly": "Found it in my memory.",
        "concise": "Memory retrieved.",
    },
    AnnouncementEvent.PLUGIN_ENABLED: {
        "formal": "Plugin enabled.",
        "friendly": "Plugin's turned on.",
        "concise": "Plugin enabled.",
    },
    AnnouncementEvent.PLUGIN_DISABLED: {
        "formal": "Plugin disabled.",
        "friendly": "Plugin's turned off.",
        "concise": "Plugin disabled.",
    },
    AnnouncementEvent.API_CONNECTED: {
        "formal": "API connection established.",
        "friendly": "Connected successfully!",
        "concise": "API connected.",
    },
    AnnouncementEvent.API_FAILED: {
        "formal": "API connection failed.",
        "friendly": "Hmm, that connection didn't work.",
        "concise": "API failed.",
    },
    AnnouncementEvent.SMART_HOME_CONNECTED: {
        "formal": "Smart home hub connected.",
        "friendly": "Your smart home is linked up!",
        "concise": "Smart home connected.",
    },
    AnnouncementEvent.DEVICE_OFFLINE: {
        "formal": "A device has gone offline.",
        "friendly": "Heads up, a device dropped offline.",
        "concise": "Device offline.",
    },
    AnnouncementEvent.NOTIFICATION_RECEIVED: {
        "formal": "You have a new notification.",
        "friendly": "New notification for you!",
        "concise": "New notification.",
    },
}


class VoiceAnnouncementService:
    def __init__(self, settings: Settings, *, voice_service: VoiceService | None = None) -> None:
        self._settings = settings
        self._voice_service = voice_service
        self.history: list[str] = []  # useful for the settings-page preview + tests

    async def announce(self, phase: UpdatePhase) -> str | None:
        cfg = self._settings.voice_announce
        if not cfg.enabled:
            return None

        phrase = _PHRASES.get(phase, {}).get(cfg.style, phase.value.replace("_", " "))
        return await self._speak(phrase)

    async def announce_event(self, event: AnnouncementEvent) -> str | None:
        """Milestone 5, section 9 -- announce a general app-lifecycle
        event (startup, wake word, task lifecycle, automation, memory,
        plugins, APIs, smart home, notifications)."""
        cfg = self._settings.voice_announce
        if not cfg.enabled:
            return None

        phrase = _EVENT_PHRASES.get(event, {}).get(cfg.style, event.value.replace("_", " "))
        return await self._speak(phrase)

    async def _speak(self, phrase: str) -> str:
        self.history.append(phrase)
        if self._voice_service is not None:
            try:
                await self._voice_service.speak(phrase)
            except Exception as err:
                _logger.warning("Voice announcement failed, continuing silently: {}", err)
        else:
            _logger.info("[voice-announce:mock] {}", phrase)
        return phrase
