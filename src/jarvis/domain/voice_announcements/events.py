"""Voice announcement event vocabulary (Milestone 5, section 9).

A separate, general-purpose event enum from ``UpdatePhase`` --
announcements now cover the app's everyday lifecycle (startup, wake
word, task lifecycle, automation, memory, plugins, APIs, smart home,
notifications), not just the update pipeline. Kept as pure data so the
mapping to spoken phrases (see ``services/voice_announcement_service.py``)
and the *triggering* of each event (wherever that subsystem lives) stay
decoupled.
"""

from __future__ import annotations

from enum import Enum


class AnnouncementEvent(str, Enum):
    STARTUP = "startup"
    SHUTDOWN = "shutdown"
    WAKE_WORD = "wake_word"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    TASK_STARTED = "task_started"
    TASK_COMPLETED = "task_completed"
    BROWSER_AUTOMATION = "browser_automation"
    DESKTOP_AUTOMATION = "desktop_automation"
    MEMORY_SAVED = "memory_saved"
    MEMORY_RETRIEVED = "memory_retrieved"
    PLUGIN_ENABLED = "plugin_enabled"
    PLUGIN_DISABLED = "plugin_disabled"
    API_CONNECTED = "api_connected"
    API_FAILED = "api_failed"
    SMART_HOME_CONNECTED = "smart_home_connected"
    DEVICE_OFFLINE = "device_offline"
    NOTIFICATION_RECEIVED = "notification_received"
