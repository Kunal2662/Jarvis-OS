"""Pre-installation validation -- M22 Task Group A.

Answers "can this machine install JARVIS?" before anything is written to
disk. Every check returns one of three verdicts, and the distinction
carries real weight:

``pass``
    Verified. The check ran and the machine satisfies it.
``warn``
    Either the machine is marginal, or the check could not run. The
    installation proceeds; the user is told.
``fail``
    Verified as insufficient. The installation is blocked.

**Only a measured shortfall blocks.** A check that could not run warns
-- never fails. Blocking an installation because a probe was
unavailable would strand a perfectly capable machine, and this package's
governing rule is that an unmeasured value is unknown rather than bad.
"""

from __future__ import annotations

import os
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from jarvis.installer.hardware import HardwareProfile
from jarvis.installer.local_model import MODEL_TIERS

Verdict = Literal["pass", "warn", "fail"]

#: Below this, JARVIS cannot be installed at all -- application, runtime
#: and the smallest local model, with room to run.
MINIMUM_FREE_DISK_GB = 3.0

#: Below this, installation works but will be uncomfortable.
COMFORTABLE_FREE_DISK_GB = 12.0

#: The smallest tier's floor; below it there is no local model at all.
MINIMUM_RAM_GB = float(MODEL_TIERS[0].minimum_ram_gb)

#: `pyproject.toml` requires >=3.13,<3.14.
MINIMUM_PYTHON = (3, 13)


@dataclass(frozen=True, slots=True)
class ValidationResult:
    key: str
    label: str
    verdict: Verdict
    detail: str
    blocking: bool
    """``True`` only for a ``fail``. Kept explicit so the UI never has to
    re-derive "does this stop me?" from the verdict string."""


@dataclass(frozen=True, slots=True)
class ValidationReport:
    results: tuple[ValidationResult, ...]

    @property
    def can_install(self) -> bool:
        return not any(result.blocking for result in self.results)

    @property
    def failures(self) -> tuple[ValidationResult, ...]:
        return tuple(r for r in self.results if r.verdict == "fail")

    @property
    def warnings(self) -> tuple[ValidationResult, ...]:
        return tuple(r for r in self.results if r.verdict == "warn")

    def to_dict(self) -> dict[str, Any]:
        return {
            "can_install": self.can_install,
            "results": [asdict(result) for result in self.results],
        }


def _result(key: str, label: str, verdict: Verdict, detail: str) -> ValidationResult:
    return ValidationResult(
        key=key, label=label, verdict=verdict, detail=detail, blocking=verdict == "fail"
    )


def check_disk_space(profile: HardwareProfile) -> ValidationResult:
    free_gb = profile.storage.free_gb
    if free_gb < MINIMUM_FREE_DISK_GB:
        return _result(
            "disk",
            "Disk space",
            "fail",
            f"{free_gb:.1f} GB free on {profile.storage.path}. "
            f"At least {MINIMUM_FREE_DISK_GB:.0f} GB is required.",
        )
    if free_gb < COMFORTABLE_FREE_DISK_GB:
        return _result(
            "disk",
            "Disk space",
            "warn",
            f"{free_gb:.1f} GB free. Enough to install, but a larger local model "
            "will not fit comfortably.",
        )
    return _result(
        "disk", "Disk space", "pass", f"{free_gb:.1f} GB free on {profile.storage.path}."
    )


def check_memory(profile: HardwareProfile) -> ValidationResult:
    ram_gb = profile.memory.total_gb
    if ram_gb < MINIMUM_RAM_GB:
        # Warns rather than fails: JARVIS still runs, cloud-first. §22.1
        # requires a local model in every installation, but refusing to
        # install on a small machine helps nobody.
        return _result(
            "memory",
            "Memory",
            "warn",
            f"{ram_gb:.1f} GB of memory. Below the {MINIMUM_RAM_GB:.0f} GB needed for a "
            "local model, so JARVIS will rely on cloud AI.",
        )
    return _result("memory", "Memory", "pass", f"{ram_gb:.1f} GB of memory.")


def check_operating_system(profile: HardwareProfile) -> ValidationResult:
    info = profile.platform
    if info.is_windows:
        # `platform.release()` is "10" or "11"; Windows 11 reports "10"
        # on some builds, so the release string is reported rather than
        # gate-kept on a number that is known to lie.
        return _result("os", "Operating system", "pass", f"Windows {info.release}.")
    if info.is_linux or info.is_macos:
        return _result(
            "os",
            "Operating system",
            "warn",
            f"{info.system} is supported from a later task group. "
            "Windows is the platform this installer targets today.",
        )
    return _result("os", "Operating system", "fail", f"{info.system} is not supported.")


def check_python() -> ValidationResult:
    current = sys.version_info[:2]
    if current < MINIMUM_PYTHON:
        return _result(
            "python",
            "Runtime",
            "fail",
            f"Python {current[0]}.{current[1]} found; "
            f"{MINIMUM_PYTHON[0]}.{MINIMUM_PYTHON[1]} or newer is required.",
        )
    return _result("python", "Runtime", "pass", f"Python {current[0]}.{current[1]}.")


def check_permissions(target: Path | None = None) -> ValidationResult:
    """Whether we can actually write where we intend to.

    Writes a real temporary file rather than consulting `os.access`,
    which reports the permission bits and not the effective outcome --
    on Windows it is routinely wrong about directories governed by ACLs
    or controlled-folder-access policies.
    """
    directory = target or Path.home()
    try:
        directory.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=directory, prefix=".jarvis-install-", delete=True):
            pass
    except (OSError, PermissionError) as err:
        return _result(
            "permissions",
            "Permissions",
            "fail",
            f"Cannot write to {directory}: {err.strerror or err}. "
            "Choose a different location or run the installer with sufficient rights.",
        )
    return _result("permissions", "Permissions", "pass", f"{directory} is writable.")


def check_internet(profile: HardwareProfile) -> ValidationResult:
    if profile.internet is None:
        return _result(
            "internet",
            "Internet",
            "warn",
            "Connectivity could not be checked. Installation continues; "
            "cloud features need a connection.",
        )
    if profile.internet is False:
        # Never blocking: a local-first product must install offline.
        return _result(
            "internet",
            "Internet",
            "warn",
            "No connection detected. JARVIS installs and runs locally; "
            "cloud features become available when a connection returns.",
        )
    return _result("internet", "Internet", "pass", "Connected.")


def check_hardware_compatibility(profile: HardwareProfile) -> ValidationResult:
    architecture = (profile.cpu.architecture or "").lower()
    if architecture in {"amd64", "x86_64", "arm64", "aarch64"}:
        return _result(
            "architecture", "Processor architecture", "pass", f"{profile.cpu.architecture}."
        )
    if not architecture:
        return _result(
            "architecture",
            "Processor architecture",
            "warn",
            "Architecture could not be determined.",
        )
    return _result(
        "architecture",
        "Processor architecture",
        "fail",
        f"{profile.cpu.architecture} is not a supported architecture.",
    )


def validate_installation(
    profile: HardwareProfile, *, install_target: Path | None = None
) -> ValidationReport:
    """Run every pre-flight check."""
    target = install_target or Path(profile.storage.path)
    return ValidationReport(
        results=(
            check_operating_system(profile),
            check_python(),
            check_hardware_compatibility(profile),
            check_memory(profile),
            check_disk_space(profile),
            check_permissions(target),
            check_internet(profile),
        )
    )


def default_install_location() -> Path:
    """Where the installer proposes to install.

    ``%LOCALAPPDATA%`` on Windows rather than ``Program Files``: a
    per-user install needs no elevation, and JARVIS writes its database,
    models and logs beneath its own directory. Elevation for a
    single-user desktop assistant is a cost with no matching benefit.
    """
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA")
        if base:
            return Path(base) / "JARVIS"
    return Path.home() / ".jarvis"
