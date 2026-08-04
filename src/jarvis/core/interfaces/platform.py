"""Platform Abstraction Layer (PAL) port -- Milestone 9 Task Group D.

The Plugin Platform must be platform-independent by design (Windows is
the primary implementation target, not the only one it can ever
support). Rather than let plugin code -- or the Plugin SDK itself --
call ``sys.platform``/``os.name``/``platform.machine()`` directly, both
sides go through this single port. A concrete adapter
(``infrastructure/platform/adapter.py``) implements it once; a future
Linux/macOS-specific adapter is a second implementation of this same
Protocol, not a redesign of anything above it -- the same ports &
adapters rule every other external system in this codebase already
follows (``docs/ARCHITECTURE.md`` section 1).

Deliberately narrow: this is capability *detection* (what does this OS/
process actually support right now), not capability *execution*. A
plugin that needs to actually press a global hotkey or read the
filesystem still goes through the Extension API's permission-gated
methods (Phase 4/5) -- this port only answers "is that kind of thing
possible here at all."
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


class PlatformFamily(enum.StrEnum):
    WINDOWS = "windows"
    LINUX = "linux"
    MACOS = "macos"
    UNKNOWN = "unknown"


# Fixed vocabulary, same "closed set, not a free-form string" convention
# ``core/plugins/sdk.py``'s ``PERMISSION_SCOPES`` uses. A plugin manifest's
# ``required_capabilities`` (Task Group D, Universal Compatibility) is
# validated against this set -- new capabilities are added here, never
# invented ad hoc by a manifest.
CAPABILITY_VOCABULARY: frozenset[str] = frozenset(
    {
        "global_hotkey",  # pynput-backed system-wide hotkey registration
        "windows_automation",  # pywinauto desktop UI automation (Windows only)
        "gpu",  # CUDA-capable GPU available to this process
    }
)


@dataclass(frozen=True, slots=True)
class PlatformInfo:
    """A cheap, process-wide snapshot -- safe to compute once and reuse
    (the underlying facts don't change during a run)."""

    family: PlatformFamily
    os_release: str
    architecture: str
    python_version: str


@runtime_checkable
class IPlatformAdapter(Protocol):
    """The Plugin Loader (Phase 2) uses :meth:`info` and
    :meth:`resolve_entry_point` to honor a manifest's
    ``supported_os``/``supported_arch``/``entry_point`` fields before
    ever importing plugin code. The Extension API (Phase 4) exposes
    :meth:`has_capability` to loaded plugins directly, read-only, so a
    plugin can branch on what's available without reaching for a raw OS
    API itself."""

    def info(self) -> PlatformInfo:
        """Current OS family, release, CPU architecture, Python
        version. Never raises."""
        ...

    def has_capability(self, capability: str) -> bool:
        """Whether *capability* (must be in :data:`CAPABILITY_VOCABULARY`)
        is genuinely available in this process right now -- a real,
        verified check (e.g. "does the optional dependency this needs
        actually import"), never a guess based on OS family alone.
        Returns ``False`` for an unrecognized capability rather than
        raising -- a forward-compatible plugin probing a capability
        newer than this JARVIS build's vocabulary should degrade
        gracefully, not crash."""
        ...

    def resolve_entry_point(
        self, entry_point: str | dict[str, str], *, default_key: str = "default"
    ) -> str | None:
        """A manifest's ``entry_point`` is either one cross-platform
        string (the common case -- "share a common core") or a
        ``{os_family: "module:Class"}`` mapping for plugins that need a
        genuinely different implementation per platform, with an
        optional ``"default"`` fallback key. Returns ``None`` if the
        current platform has neither a specific nor a default entry --
        the Loader treats that as "not supported here", not an error."""
        ...
