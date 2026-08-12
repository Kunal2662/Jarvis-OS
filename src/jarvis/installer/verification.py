"""Post-installation verification -- M22 Task Group B.

Checks what was actually installed, as opposed to
:mod:`jarvis.installer.validation`, which checks whether a machine
*could* be installed to. The two are separate because they answer
different questions at different times, and a single "checks" module
would blur pre-flight into post-flight.

**Verification runs in parallel** because the checks are independent and
I/O-bound — a checksum over a 9 GB model and a permissions probe have no
reason to wait for each other. The thread pool is small and the checks
are read-only, so there is no ordering to get wrong.

Same three verdicts as validation: only a *measured* shortfall fails.
"""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from jarvis.__version__ import __version__
from jarvis.installer.download import verify_file
from jarvis.installer.first_run import CONFIG_FILENAME, DIRECTORIES

Verdict = Literal["pass", "warn", "fail"]

#: Enough headroom for logs, cache and a model's working files.
MINIMUM_FREE_DISK_GB_AFTER_INSTALL = 2.0

_MAX_WORKERS = 6


@dataclass(frozen=True, slots=True)
class CheckResult:
    key: str
    label: str
    verdict: Verdict
    detail: str
    repairable: bool = False
    """Whether :func:`jarvis.installer.provisioning.repair` can fix this
    without a full reinstall. Drives which repair buttons the UI offers,
    so it is data rather than a UI guess."""
    repair_step: str | None = None


@dataclass(frozen=True, slots=True)
class VerificationReport:
    results: tuple[CheckResult, ...]

    @property
    def healthy(self) -> bool:
        return not any(result.verdict == "fail" for result in self.results)

    @property
    def failures(self) -> tuple[CheckResult, ...]:
        return tuple(r for r in self.results if r.verdict == "fail")

    @property
    def repairable_failures(self) -> tuple[CheckResult, ...]:
        return tuple(r for r in self.failures if r.repairable)

    def to_dict(self) -> dict[str, Any]:
        return {
            "healthy": self.healthy,
            "results": [asdict(result) for result in self.results],
        }


def _result(
    key: str,
    label: str,
    verdict: Verdict,
    detail: str,
    *,
    repairable: bool = False,
    repair_step: str | None = None,
) -> CheckResult:
    return CheckResult(
        key=key,
        label=label,
        verdict=verdict,
        detail=detail,
        repairable=repairable,
        repair_step=repair_step,
    )


def check_directories(root: Path) -> CheckResult:
    missing = [relative for relative, _ in DIRECTORIES if not (root / relative).is_dir()]
    if missing:
        return _result(
            "directories",
            "Application folders",
            "fail",
            f"{len(missing)} folder(s) missing: {', '.join(missing[:3])}"
            + ("…" if len(missing) > 3 else ""),
            repairable=True,
            repair_step="directories",
        )
    return _result("directories", "Application folders", "pass", "All present.")


def check_configuration(root: Path) -> CheckResult:
    path = root / "config" / CONFIG_FILENAME
    if not path.exists():
        return _result(
            "configuration",
            "Configuration",
            "fail",
            "Configuration file is missing.",
            repairable=True,
            repair_step="configuration",
        )
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as err:
        return _result(
            "configuration",
            "Configuration",
            "fail",
            f"Configuration file is unreadable: {err}",
            repairable=True,
            repair_step="configuration",
        )

    for required in ("installation_root", "paths", "profile"):
        if required not in document:
            return _result(
                "configuration",
                "Configuration",
                "fail",
                f"Configuration is missing '{required}'.",
                repairable=True,
                repair_step="configuration",
            )
    return _result("configuration", "Configuration", "pass", "Valid.")


def check_database_location(root: Path) -> CheckResult:
    """The database *location*, not its schema.

    The installer never creates tables — the application does, on first
    launch, through the frozen schema it owns. So the only honest check
    here is that the directory exists and is writable; a missing file is
    the expected state before first launch, not a fault.
    """
    directory = root / "data"
    if not directory.is_dir():
        return _result(
            "database",
            "Database location",
            "fail",
            "Data folder is missing.",
            repairable=True,
            repair_step="directories",
        )
    if not os.access(directory, os.W_OK):
        return _result("database", "Database location", "fail", f"{directory} is not writable.")

    database = root / "data" / "jarvis.db"
    if database.exists():
        return _result("database", "Database", "pass", "Present.")
    return _result(
        "database",
        "Database",
        "pass",
        "Will be created on first launch.",
    )


def check_memory_storage(root: Path) -> CheckResult:
    directory = root / "data" / "memory"
    if not directory.is_dir():
        return _result(
            "memory_storage",
            "Memory storage",
            "fail",
            "Memory folder is missing.",
            repairable=True,
            repair_step="directories",
        )
    return _result("memory_storage", "Memory storage", "pass", "Ready.")


def check_permissions(root: Path) -> CheckResult:
    """An actual write, for the reason `validation.check_permissions`
    gives: `os.access` reports permission bits, not the effective
    outcome, and on Windows it is routinely wrong."""
    probe = root / ".jarvis-write-probe"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as err:
        return _result("permissions", "Permissions", "fail", f"{root} is not writable: {err}")
    return _result("permissions", "Permissions", "pass", "Writable.")


def check_disk_space(root: Path) -> CheckResult:
    try:
        usage = shutil.disk_usage(root)
    except OSError as err:
        return _result("disk", "Disk space", "warn", f"Could not be measured: {err}")

    free_gb = usage.free / (1024**3)
    if free_gb < MINIMUM_FREE_DISK_GB_AFTER_INSTALL:
        return _result(
            "disk",
            "Disk space",
            "fail",
            f"Only {free_gb:.1f} GB free. JARVIS needs room for logs and cache.",
        )
    return _result("disk", "Disk space", "pass", f"{free_gb:.1f} GB free.")


def _check_artifacts(
    directory: Path, expected: dict[str, str | None], key: str, label: str, repair_step: str
) -> CheckResult:
    """Shared by model and voice verification -- same shape, same rules."""
    if not expected:
        return _result(key, label, "pass", "Nothing was scheduled for installation.")

    if not directory.is_dir():
        return _result(
            key,
            label,
            "fail",
            f"{label} folder is missing.",
            repairable=True,
            repair_step=repair_step,
        )

    missing: list[str] = []
    corrupt: list[str] = []
    unverifiable = 0

    for name, checksum in expected.items():
        path = directory / name
        if not path.exists():
            missing.append(name)
            continue
        verified, _reason = verify_file(path, checksum)
        if checksum is None:
            unverifiable += 1
        elif not verified:
            corrupt.append(name)

    if missing or corrupt:
        parts = []
        if missing:
            parts.append(f"{len(missing)} missing")
        if corrupt:
            parts.append(f"{len(corrupt)} failed integrity checks")
        return _result(
            key,
            label,
            "fail",
            f"{label}: {', '.join(parts)}.",
            repairable=True,
            repair_step=repair_step,
        )

    if unverifiable:
        # Present but unchecked is not the same as verified, and saying
        # "pass" here would be the exact overstatement this package
        # exists to avoid.
        return _result(
            key,
            label,
            "warn",
            f"All present, but {unverifiable} could not be integrity-checked "
            "because the source published no checksum.",
        )
    return _result(key, label, "pass", f"All {len(expected)} present and verified.")


def check_models(root: Path, expected: dict[str, str | None]) -> CheckResult:
    return _check_artifacts(root / "models", expected, "models", "Local AI", "model_download")


def check_voice(root: Path, expected: dict[str, str | None]) -> CheckResult:
    return _check_artifacts(root / "voice", expected, "voice", "Voice components", "voice_download")


def check_version_compatibility(manifest: dict[str, Any] | None) -> CheckResult:
    """Whether the installation was made by this build.

    A manifest from a different installer version is a *warning*, not a
    failure: that is exactly the situation a future migration is meant
    to handle, and blocking would strand an upgrade.
    """
    if manifest is None:
        return _result(
            "version",
            "Version",
            "warn",
            "No installation manifest found; this installation predates manifests.",
        )
    recorded = manifest.get("installer_version")
    if recorded == __version__:
        return _result("version", "Version", "pass", f"Installed by version {__version__}.")
    return _result(
        "version",
        "Version",
        "warn",
        f"Installed by version {recorded}; this installer is {__version__}. "
        "A migration may be needed.",
    )


def verify_installation(
    root: Path,
    *,
    expected_models: dict[str, str | None] | None = None,
    expected_voice: dict[str, str | None] | None = None,
    manifest: dict[str, Any] | None = None,
) -> VerificationReport:
    """Run every check, in parallel.

    Checksumming a multi-gigabyte model is the slow one; running it
    alongside the cheap filesystem probes rather than after them is the
    difference between a verification pass that feels instant and one
    that looks hung.
    """
    checks: list[Callable[[], CheckResult]] = [
        lambda: check_directories(root),
        lambda: check_configuration(root),
        lambda: check_database_location(root),
        lambda: check_memory_storage(root),
        lambda: check_permissions(root),
        lambda: check_disk_space(root),
        lambda: check_models(root, expected_models or {}),
        lambda: check_voice(root, expected_voice or {}),
        lambda: check_version_compatibility(manifest),
    ]

    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
        results = tuple(pool.map(lambda check: check(), checks))

    return VerificationReport(results=results)
