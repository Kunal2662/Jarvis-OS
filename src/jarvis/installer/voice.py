"""Voice component planning -- M22 Task Group A.

Decides which voice components an installation should include, per
`ARCHITECTURE.md` §22.6:

    Persistent voice identity: JARVIS always sounds like JARVIS. Users
    never select providers. Automatic failover. Administrators manage
    providers.

So this module plans **components**, not a user choice. The installer
never shows a personal user a voice-provider list; it shows them a
voice, and a Test Voice button.

**Nothing is downloaded here** -- same rule as
:mod:`jarvis.installer.local_model`. The plan states what will be
installed and what it will cost.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

from jarvis.installer.hardware import HardwareProfile

VoiceRole = Literal["tts_local", "tts_cloud", "stt_local"]


@dataclass(frozen=True, slots=True)
class VoiceComponent:
    key: str
    label: str
    role: VoiceRole
    approximate_download_mb: int
    required: bool
    """A required component is not offered as a choice. Local TTS and
    STT are required because §22.1 forbids an installation that can only
    speak with a network connection."""
    enabled: bool
    reason: str


@dataclass(frozen=True, slots=True)
class VoicePlan:
    identity_name: str
    """The single voice JARVIS speaks with, on every provider. Fixed --
    it is a property of the product, not a preference."""
    components: tuple[VoiceComponent, ...]
    can_test_offline: bool
    """Whether the Test Voice step will work without a connection. True
    whenever local TTS is included, which is always."""
    notes: tuple[str, ...]

    @property
    def total_download_mb(self) -> int:
        return sum(c.approximate_download_mb for c in self.components if c.enabled)

    def to_dict(self, *, include_providers: bool) -> dict[str, Any]:
        """*include_providers* is ``False`` for a personal user.

        §22.12 puts provider names off-limits, and "Piper" and
        "ElevenLabs" are provider names. A personal user sees the voice
        identity, the download size and whether it works offline -- which
        is everything that affects them.
        """
        data: dict[str, Any] = {
            "identity_name": self.identity_name,
            "can_test_offline": self.can_test_offline,
            "total_download_mb": self.total_download_mb,
            "notes": list(self.notes),
        }
        if include_providers:
            data["components"] = [asdict(c) for c in self.components]
        else:
            data["component_count"] = sum(1 for c in self.components if c.enabled)
        return data


#: The one voice, across every provider. §22.6's "JARVIS always sounds
#: like JARVIS" is only true if failover maps onto the same identity, so
#: the identity is named here rather than per-provider.
VOICE_IDENTITY = "JARVIS"


def plan_voice(
    profile: HardwareProfile,
    *,
    include_cloud_voice: bool = False,
) -> VoicePlan:
    """Plan the voice components for this machine.

    *include_cloud_voice* enables the optional cloud TTS component. It
    defaults to ``False`` and is an Administrator decision -- it needs an
    API key, and §22.11 reserves credential management to
    Administrators.
    """
    notes: list[str] = []

    # Local TTS. Required: an installation that cannot speak offline
    # would make voice a cloud feature, which §22.1 forbids.
    components = [
        VoiceComponent(
            key="piper",
            label="Local speech synthesis",
            role="tts_local",
            approximate_download_mb=65,
            required=True,
            enabled=True,
            reason="Lets JARVIS speak without a connection.",
        )
    ]

    # Local STT. Model size follows the machine, same principle as the
    # LLM tier: a different execution strategy, not a different feature.
    cores = profile.cpu.physical_cores or 0
    ram_gb = profile.memory.total_gb
    if ram_gb >= 8 and cores >= 4:
        stt_label, stt_mb = "Speech recognition (standard)", 480
    else:
        stt_label, stt_mb = "Speech recognition (compact)", 150
        notes.append(
            "A compact speech-recognition model was selected to suit this device's memory."
        )

    components.append(
        VoiceComponent(
            key="faster_whisper",
            label=stt_label,
            role="stt_local",
            approximate_download_mb=stt_mb,
            required=True,
            enabled=True,
            reason="Lets JARVIS listen without a connection.",
        )
    )

    # Optional cloud TTS.
    components.append(
        VoiceComponent(
            key="elevenlabs",
            label="Enhanced cloud speech",
            role="tts_cloud",
            approximate_download_mb=0,
            required=False,
            enabled=include_cloud_voice,
            reason=(
                "Higher-quality speech when a connection is available. Requires an API key."
                if not include_cloud_voice
                else "Enabled by the administrator. Falls back to local speech automatically."
            ),
        )
    )

    if include_cloud_voice:
        notes.append(
            "Cloud speech is an enhancement: JARVIS falls back to local speech automatically "
            "and keeps the same voice."
        )

    if profile.internet is False:
        notes.append(
            "No connection was detected, so voice components will be installed from the local "
            "package. Voice works offline either way."
        )

    return VoicePlan(
        identity_name=VOICE_IDENTITY,
        components=tuple(components),
        # Always true today: local TTS is required. Computed rather than
        # hardcoded so it stays correct if that ever changes.
        can_test_offline=any(c.role == "tts_local" and c.enabled for c in components),
        notes=tuple(notes),
    )
