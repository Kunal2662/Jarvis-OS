"""``DefaultPlatformAdapter`` -- the real, first (and today, only)
implementation of ``core.interfaces.platform.IPlatformAdapter``
(Milestone 9 Task Group D, Universal Compatibility).

Wraps the existing ``platform_detector.detect()`` (unused anywhere
until now, but already the right, real OS-detection primitive --
reused rather than duplicated) and adds genuinely-verified capability
probes: each one actually attempts the real check (an optional
dependency import, a CUDA query) rather than inferring availability
from OS family alone. A capability this process can't verify one way
or the other is reported unavailable, never assumed present.

A future Linux/macOS-specific adapter -- if one is ever needed because
a capability probe stops being cross-platform-safe to run generically
-- is a second class implementing the same port, registered instead of
this one in ``core/di/container.py``; nothing above this file's own
boundary needs to change.
"""

from __future__ import annotations

from functools import lru_cache

from jarvis.core.interfaces.platform import CAPABILITY_VOCABULARY, PlatformFamily, PlatformInfo
from jarvis.infrastructure.platform import platform_detector

_FAMILY_BY_SYSTEM = {
    "Windows": PlatformFamily.WINDOWS,
    "Linux": PlatformFamily.LINUX,
    "Darwin": PlatformFamily.MACOS,
}

# ``platform.machine()`` returns the OS's own native spelling, not this
# project's ``supported_arch`` vocabulary
# (``core/plugins/manifest.py``'s ``SUPPORTED_ARCH_VALUES`` --
# "x86_64"/"arm64"/"x86") -- Windows in particular reports "AMD64", not
# "x86_64". Found as a real bug (Milestone 9 Task Group E route tests,
# the first tests to exercise this class against a real, unfaked
# Windows machine rather than a hardcoded "x86_64" test double): every
# plugin manifest's default ``supported_arch`` was silently rejecting
# every real Windows x86_64 install. Normalizing here, once, at the PAL
# boundary, is exactly what this layer exists for -- every caller above
# it keeps using the one canonical vocabulary.
_ARCH_NORMALIZATION = {
    "amd64": "x86_64",
    "x86_64": "x86_64",
    "aarch64": "arm64",
    "arm64": "arm64",
    "i386": "x86",
    "i686": "x86",
    "x86": "x86",
}


def _normalize_architecture(raw: str) -> str:
    return _ARCH_NORMALIZATION.get(raw.lower(), raw.lower())


class DefaultPlatformAdapter:
    """Implements ``IPlatformAdapter``. Stateless and cheap -- safe as
    a DI Singleton, matching every other adapter in this container."""

    def info(self) -> PlatformInfo:
        detected = platform_detector.detect()
        return PlatformInfo(
            family=_FAMILY_BY_SYSTEM.get(detected.system, PlatformFamily.UNKNOWN),
            os_release=detected.release,
            architecture=_normalize_architecture(detected.machine),
            python_version=detected.python,
        )

    def has_capability(self, capability: str) -> bool:
        if capability not in CAPABILITY_VOCABULARY:
            return False
        probe = _CAPABILITY_PROBES.get(capability)
        if probe is None:
            return False
        return probe()

    def resolve_entry_point(
        self, entry_point: str | dict[str, str], *, default_key: str = "default"
    ) -> str | None:
        if isinstance(entry_point, str):
            return entry_point
        family = self.info().family.value
        if family in entry_point:
            return entry_point[family]
        return entry_point.get(default_key)


@lru_cache(maxsize=1)
def _probe_global_hotkey() -> bool:
    try:
        import pynput  # noqa: F401
    except ImportError:
        return False
    return True


@lru_cache(maxsize=1)
def _probe_windows_automation() -> bool:
    if platform_detector.detect().system != "Windows":
        return False
    try:
        import pywinauto  # noqa: F401
    except ImportError:
        return False
    return True


@lru_cache(maxsize=1)
def _probe_gpu() -> bool:
    try:
        import torch
    except ImportError:
        return False
    try:
        return bool(torch.cuda.is_available())
    except Exception:
        # A real-world CUDA/driver query can fail in ways that aren't
        # ImportError (missing driver, broken toolkit install) -- any
        # failure here honestly means "not usable", not "unknown".
        return False


_CAPABILITY_PROBES = {
    "global_hotkey": _probe_global_hotkey,
    "windows_automation": _probe_windows_automation,
    "gpu": _probe_gpu,
}
