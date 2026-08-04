"""Register every Settings page.

Import order matters: fully-implemented pages first (so they appear at the
top of their category), then placeholders for future milestones.
"""

from __future__ import annotations

# Implemented pages
from jarvis.ui.dialogs.settings_pages.ai_provider_page import AIProviderPage
from jarvis.ui.dialogs.settings_pages.api_keys_page import APIKeysPage
from jarvis.ui.dialogs.settings_pages.automation_page import (
    BrowserAutomationPage,
    DesktopAutomationPage,
)
from jarvis.ui.dialogs.settings_pages.base import (
    CATEGORY_ORDER,
    PAGE_REGISTRY,
    PageDescriptor,
    SettingsPage,
    make_placeholder,
    register,
)

# Milestone 5 -- Official UI & Frontend Framework
from jarvis.ui.dialogs.settings_pages.developer_mode_page import DeveloperModePage
from jarvis.ui.dialogs.settings_pages.logging_page import LoggingPage
from jarvis.ui.dialogs.settings_pages.memory_page import MemoryPage
from jarvis.ui.dialogs.settings_pages.model_page import ModelPage
from jarvis.ui.dialogs.settings_pages.plugins_page import PluginsPage
from jarvis.ui.dialogs.settings_pages.startup_page import StartupPage
from jarvis.ui.dialogs.settings_pages.theme_page import ThemePage
from jarvis.ui.dialogs.settings_pages.vision_page import VisionPage
from jarvis.ui.dialogs.settings_pages.voice_announcements_page import VoiceAnnouncementsPage
from jarvis.ui.dialogs.settings_pages.voice_page import VoicePage
from jarvis.ui.dialogs.settings_pages.wake_word_page import WakeWordPage

# General
register(PageDescriptor("theme", ThemePage.title, ThemePage.category, ThemePage))
register(PageDescriptor("startup", StartupPage.title, StartupPage.category, StartupPage))
register(PageDescriptor("logging", LoggingPage.title, LoggingPage.category, LoggingPage))

# AI
register(
    PageDescriptor("ai_provider", AIProviderPage.title, AIProviderPage.category, AIProviderPage)
)
register(PageDescriptor("model", ModelPage.title, ModelPage.category, ModelPage))
register(PageDescriptor("api_keys", APIKeysPage.title, APIKeysPage.category, APIKeysPage))

# Voice — implemented in Milestone 2 (+ Milestone 5 voice announcements)
register(PageDescriptor("voice", VoicePage.title, VoicePage.category, VoicePage))
register(PageDescriptor("wake_word", WakeWordPage.title, WakeWordPage.category, WakeWordPage))
register(
    PageDescriptor(
        "voice_announcements",
        VoiceAnnouncementsPage.title,
        VoiceAnnouncementsPage.category,
        VoiceAnnouncementsPage,
    )
)

# Memory — implemented in Milestone 3
register(PageDescriptor("memory", MemoryPage.title, MemoryPage.category, MemoryPage))

# Vision — configuration scaffolding implemented in Milestone 6, Phase 6
# (the vision/OCR providers themselves are still unavailable; see VisionPage).
register(PageDescriptor("vision", VisionPage.title, VisionPage.category, VisionPage))

# Developer — implemented in Milestone 5 (Developer Mode gate + shell)
register(
    PageDescriptor(
        "developer_mode", DeveloperModePage.title, DeveloperModePage.category, DeveloperModePage
    )
)

# Automation — implemented in Milestone 4 (Automation Platform)
register(
    PageDescriptor(
        "browser",
        BrowserAutomationPage.title,
        BrowserAutomationPage.category,
        BrowserAutomationPage,
    )
)
register(
    PageDescriptor(
        "desktop_automation",
        DesktopAutomationPage.title,
        DesktopAutomationPage.category,
        DesktopAutomationPage,
    )
)

# Plugins — implemented in Milestone 9 Task Group D (Plugin Platform)
register(PageDescriptor("plugins", PluginsPage.title, PluginsPage.category, PluginsPage))

# ---- Future milestones (placeholders) ------------------------------------
# These three were labelled with milestones that had already shipped
# ("Milestone 4 — Automation", "Milestone 5 — Agents") until the Aug 2026
# final backlog pass promoted them to real pages above. The two below are
# genuinely future, and now name the milestone that actually owns them
# rather than the retired "Milestone 6 — Ecosystem" grouping.
register(
    make_placeholder("smart_home", "Smart Home", "Smart Home", "Milestone 12 — Smart Home & IoT")
)
register(make_placeholder("security", "Security & Privacy", "Security", "Milestone 14 — Security"))


__all__ = ["CATEGORY_ORDER", "PAGE_REGISTRY", "SettingsPage"]
