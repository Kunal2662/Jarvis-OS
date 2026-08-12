"""Dependency detection -- M22 Task Group B.

Reports what is present and what version. It **never installs, upgrades
or overwrites anything** — the brief's "never silently overwrite" is
enforced by this module having no code path that writes.

A missing dependency is a *finding*, not a failure. Most of what is
probed here is optional acceleration: CUDA, DirectML and ONNX Runtime
make JARVIS faster, and their absence changes the execution strategy
rather than the feature set (`ARCHITECTURE.md` §22.9). Only the Python
runtime is genuinely required, and by the time this code runs it is
self-evidently present.

Same rule as :mod:`jarvis.installer.hardware`: a version we could not
read is ``None``, never a guess.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from jarvis.infrastructure.platform.platform_detector import detect as detect_platform

_PROBE_TIMEOUT_SECONDS = 5.0

DependencyStatus = Literal["present", "missing", "unknown"]


@dataclass(frozen=True, slots=True)
class Dependency:
    key: str
    label: str
    status: DependencyStatus
    version: str | None
    required: bool
    """Only the Python runtime. Everything else is acceleration or
    convenience, and its absence must not block an installation."""
    detail: str
    path: str | None = None

    def to_dict(self, *, include_paths: bool) -> dict[str, Any]:
        """*include_paths* is ``False`` for a personal user: a filesystem
        path to a CUDA install is developer information (§22.12)."""
        data = asdict(self)
        if not include_paths:
            data.pop("path")
        return data


@dataclass(frozen=True, slots=True)
class DependencyReport:
    dependencies: tuple[Dependency, ...]

    @property
    def satisfied(self) -> bool:
        """Only required dependencies count. An installation is not
        blocked by a missing GPU runtime."""
        return all(d.status == "present" for d in self.dependencies if d.required)

    @property
    def missing_required(self) -> tuple[Dependency, ...]:
        return tuple(d for d in self.dependencies if d.required and d.status != "present")

    @property
    def acceleration(self) -> tuple[Dependency, ...]:
        return tuple(d for d in self.dependencies if not d.required and d.status == "present")

    def to_dict(self, *, include_paths: bool = False) -> dict[str, Any]:
        return {
            "satisfied": self.satisfied,
            "dependencies": [d.to_dict(include_paths=include_paths) for d in self.dependencies],
        }


def _run(command: list[str]) -> str | None:
    """Bounded, non-fatal probe. Identical contract to
    :func:`jarvis.installer.hardware._run`."""
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=_PROBE_TIMEOUT_SECONDS,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return (completed.stdout or completed.stderr).strip() or None


def _dependency(
    key: str,
    label: str,
    *,
    status: DependencyStatus,
    version: str | None = None,
    required: bool = False,
    detail: str,
    path: str | None = None,
) -> Dependency:
    return Dependency(
        key=key,
        label=label,
        status=status,
        version=version,
        required=required,
        detail=detail,
        path=path,
    )


def detect_python() -> Dependency:
    version = ".".join(str(part) for part in sys.version_info[:3])
    return _dependency(
        "python",
        "Python runtime",
        status="present",
        version=version,
        required=True,
        detail=f"Python {version}.",
        path=sys.executable,
    )


def detect_git() -> Dependency:
    executable = shutil.which("git")
    if not executable:
        return _dependency(
            "git",
            "Git",
            status="missing",
            detail="Not found. Only needed to install plugins from a repository.",
        )
    raw = _run([executable, "--version"]) or ""
    version = raw.replace("git version", "").strip() or None
    return _dependency(
        "git",
        "Git",
        status="present",
        version=version,
        detail=f"Git {version}." if version else "Git is available.",
        path=executable,
    )


def detect_visual_cpp() -> Dependency:
    """The Visual C++ runtime, on Windows only.

    Probed by looking for the redistributable DLLs the runtime installs
    into System32 rather than by reading the registry: the registry keys
    differ across redistributable versions and architectures, while the
    DLL either loads or it does not — which is the thing that actually
    matters to a native extension.
    """
    info = detect_platform()
    if not info.is_windows:
        return _dependency(
            "visual_cpp",
            "Visual C++ runtime",
            status="present",
            detail="Not required on this platform.",
        )

    system32 = Path(os.environ.get("SYSTEMROOT", "C:/Windows")) / "System32"
    for name in ("vcruntime140.dll", "msvcp140.dll"):
        candidate = system32 / name
        if candidate.exists():
            return _dependency(
                "visual_cpp",
                "Visual C++ runtime",
                status="present",
                detail="Installed.",
                path=str(candidate),
            )

    return _dependency(
        "visual_cpp",
        "Visual C++ runtime",
        status="missing",
        detail=(
            "Not found. Some native components need it. "
            "Install the Microsoft Visual C++ Redistributable."
        ),
    )


def detect_cuda() -> Dependency:
    """CUDA, via `nvidia-smi`'s reported driver capability.

    Deliberately not by looking for a CUDA *toolkit* install: JARVIS
    consumes CUDA through a runtime that ships its own libraries, so what
    matters is whether the driver supports it, not whether a developer
    toolkit is present.
    """
    executable = shutil.which("nvidia-smi")
    if not executable:
        return _dependency(
            "cuda",
            "CUDA acceleration",
            status="missing",
            detail="No NVIDIA driver detected. JARVIS will run on the processor.",
        )

    version = _run([executable, "--query-gpu=driver_version", "--format=csv,noheader"])
    if not version:
        return _dependency(
            "cuda",
            "CUDA acceleration",
            status="unknown",
            detail="An NVIDIA driver is present but did not report its version.",
            path=executable,
        )
    first = version.splitlines()[0].strip()
    return _dependency(
        "cuda",
        "CUDA acceleration",
        status="present",
        version=first,
        detail=f"NVIDIA driver {first}.",
        path=executable,
    )


def detect_directml() -> Dependency:
    """DirectML — Windows-only GPU acceleration that works across
    vendors, so it is the fallback when CUDA is absent."""
    info = detect_platform()
    if not info.is_windows:
        return _dependency(
            "directml",
            "DirectML acceleration",
            status="missing",
            detail="Windows only.",
        )

    system32 = Path(os.environ.get("SYSTEMROOT", "C:/Windows")) / "System32"
    candidate = system32 / "DirectML.dll"
    if candidate.exists():
        return _dependency(
            "directml",
            "DirectML acceleration",
            status="present",
            detail="Available.",
            path=str(candidate),
        )
    return _dependency(
        "directml",
        "DirectML acceleration",
        status="missing",
        detail="Not present. JARVIS will use another accelerator or the processor.",
    )


def detect_onnx_runtime() -> Dependency:
    """ONNX Runtime as an importable module.

    `importlib.util.find_spec` rather than importing it: importing a
    large native extension during a hardware scan costs real time and
    can print vendor warnings into the installer's stdout, which the CLI
    contract reserves for JSON.
    """
    try:
        spec = importlib.util.find_spec("onnxruntime")
    except (ImportError, ValueError):
        spec = None

    if spec is None:
        return _dependency(
            "onnx_runtime",
            "ONNX Runtime",
            status="missing",
            detail="Not installed. Used by some voice and vision components.",
        )
    return _dependency(
        "onnx_runtime",
        "ONNX Runtime",
        status="present",
        detail="Available.",
        path=spec.origin,
    )


def detect_dependencies() -> DependencyReport:
    """One full scan. Never raises, never writes."""
    return DependencyReport(
        dependencies=(
            detect_python(),
            detect_visual_cpp(),
            detect_git(),
            detect_cuda(),
            detect_directml(),
            detect_onnx_runtime(),
        )
    )


def describe_acceleration(report: DependencyReport) -> str:
    """One sentence a personal user can read, naming no library.

    §22.12 keeps `CUDA` and `DirectML` — which are provider/runtime
    names — out of a personal user's product, so the *capability* is
    described instead of the mechanism.
    """
    available = {d.key for d in report.acceleration}
    if available & {"cuda", "directml"}:
        return "Your graphics hardware will be used to speed JARVIS up."
    return "JARVIS will run on your processor."
