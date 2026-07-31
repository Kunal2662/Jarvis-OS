"""Runtime platform detection.

A dedicated module (rather than scattered ``sys.platform`` checks) keeps
Windows-specific branches easy to grep and easy to mock in tests.
"""

from __future__ import annotations

import platform
import sys
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PlatformInfo:
    system: str
    release: str
    version: str
    machine: str
    python: str
    is_windows: bool
    is_macos: bool
    is_linux: bool


def detect() -> PlatformInfo:
    system = platform.system()
    return PlatformInfo(
        system=system,
        release=platform.release(),
        version=platform.version(),
        machine=platform.machine(),
        python=sys.version.split()[0],
        is_windows=system == "Windows",
        is_macos=system == "Darwin",
        is_linux=system == "Linux",
    )
