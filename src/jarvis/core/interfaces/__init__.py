"""Abstract interfaces (ports) that every infrastructure adapter must implement.

Higher layers depend on these types, **never** on concrete adapters.
"""

from __future__ import annotations

from jarvis.core.interfaces.agent import IAgentOrchestrator
from jarvis.core.interfaces.audio import (
    AudioChunk,
    IAudioPlayer,
    IAudioRecorder,
)
from jarvis.core.interfaces.automation import IOSAutomation
from jarvis.core.interfaces.browser import IBrowserAutomation
from jarvis.core.interfaces.database import IDatabase
from jarvis.core.interfaces.hotkey import IHotkeyListener
from jarvis.core.interfaces.llm_provider import ILLMProvider
from jarvis.core.interfaces.memory import IMemoryRecallHook, NoopMemoryRecall
from jarvis.core.interfaces.ocr_provider import IOCRProvider
from jarvis.core.interfaces.providers import (
    ActivityItem,
    ConnectionStatus,
    IFinanceProvider,
    IGmailProvider,
    IPluginProvider,
    ISmartHomeProvider,
    ISpotifyProvider,
    ITranscriptProvider,
    IUpdateProvider,
    IWeatherProvider,
    ProviderCapabilities,
)
from jarvis.core.interfaces.stt_provider import ISTTProvider
from jarvis.core.interfaces.tts_provider import ITTSProvider
from jarvis.core.interfaces.vector_store import IVectorStore
from jarvis.core.interfaces.vision_provider import IVisionProvider
from jarvis.core.interfaces.wake_word import IWakeWordDetector

__all__ = [
    "ActivityItem",
    "AudioChunk",
    "ConnectionStatus",
    "IAgentOrchestrator",
    "IAudioPlayer",
    "IAudioRecorder",
    "IBrowserAutomation",
    "IDatabase",
    "IFinanceProvider",
    "IGmailProvider",
    "IHotkeyListener",
    "ILLMProvider",
    "IMemoryRecallHook",
    "IOCRProvider",
    "IOSAutomation",
    "IPluginProvider",
    "ISTTProvider",
    "ISmartHomeProvider",
    "ISpotifyProvider",
    "ITTSProvider",
    "ITranscriptProvider",
    "IUpdateProvider",
    "IVectorStore",
    "IVisionProvider",
    "IWakeWordDetector",
    "IWeatherProvider",
    "NoopMemoryRecall",
    "ProviderCapabilities",
]
