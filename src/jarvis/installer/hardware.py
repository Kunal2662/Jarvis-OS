"""Hardware detection for the installer -- M22 Task Group A.

Reads what the machine will actually tell us and reports ``None`` for
everything else. That rule is the whole design:

    A field is either measured or it is ``None``. It is never estimated,
    defaulted to something plausible, or inferred from a different
    field.

An installer that invents a GPU or a temperature produces a calibration
that is confidently wrong, and the user has no way to see it happened.
``None`` is visible -- the UI renders "Not detected", and
:mod:`jarvis.installer.calibration` records the gap in its
``missing_inputs`` list so the recommendation can be honest about what
it did not know.

**Every probe is bounded and non-fatal.** Detection runs on an unknown
machine during installation; a hung ``nvidia-smi`` or a WMI call that
throws must degrade to ``None``, never hang or crash the installer.
"""

from __future__ import annotations

import platform
import re
import shutil
import socket
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import psutil

from jarvis.infrastructure.platform.platform_detector import PlatformInfo
from jarvis.infrastructure.platform.platform_detector import detect as detect_platform

# A probe that has not answered in this long is treated as unavailable.
# Generous enough for a cold `nvidia-smi`, short enough that a wedged
# tool cannot stall an installation.
_PROBE_TIMEOUT_SECONDS = 5.0

_BYTES_PER_GB = 1024**3


@dataclass(frozen=True, slots=True)
class CpuInfo:
    """``model`` is whatever the OS reports, which on some Linux builds
    is an empty string -- hence ``str | None`` rather than a placeholder."""

    model: str | None
    physical_cores: int | None
    logical_cores: int | None
    max_frequency_mhz: float | None
    architecture: str


@dataclass(frozen=True, slots=True)
class MemoryInfo:
    total_bytes: int
    available_bytes: int

    @property
    def total_gb(self) -> float:
        return self.total_bytes / _BYTES_PER_GB


@dataclass(frozen=True, slots=True)
class GpuInfo:
    """One discrete or integrated GPU.

    ``vram_bytes`` is ``None`` whenever the vendor tool did not report
    it -- notably for integrated GPUs enumerated through WMI, where the
    reported adapter RAM is unreliable for anything above 4 GB.
    """

    name: str
    vram_bytes: int | None
    vendor: str | None
    source: str
    """Which probe produced this entry -- `nvidia-smi`, `wmic`, … Kept so
    a support conversation can tell a measured VRAM figure from an
    absent one."""


@dataclass(frozen=True, slots=True)
class StorageInfo:
    path: str
    total_bytes: int
    free_bytes: int

    @property
    def free_gb(self) -> float:
        return self.free_bytes / _BYTES_PER_GB


@dataclass(frozen=True, slots=True)
class PowerInfo:
    """``on_battery`` is ``None`` on a machine with no battery *and* on a
    machine whose battery cannot be read -- the two are indistinguishable
    through :func:`psutil.sensors_battery`, so neither is claimed."""

    has_battery: bool | None
    on_battery: bool | None
    percent: float | None


@dataclass(frozen=True, slots=True)
class HardwareProfile:
    platform: PlatformInfo
    cpu: CpuInfo
    memory: MemoryInfo
    storage: StorageInfo
    gpus: tuple[GpuInfo, ...]
    power: PowerInfo
    internet: bool | None
    """``None`` means the check itself could not run; ``False`` means it
    ran and found no route out."""
    temperature_celsius: float | None
    npu: str | None
    notes: tuple[str, ...] = field(default_factory=tuple)
    """Human-readable reasons a field is ``None``, surfaced in the
    installer UI so a gap is explained rather than merely blank."""

    @property
    def total_vram_bytes(self) -> int | None:
        """Summed across GPUs that reported VRAM. ``None`` when none did
        -- deliberately not ``0``, which would read as "a GPU with no
        memory" rather than "we could not measure it"."""
        measured = [gpu.vram_bytes for gpu in self.gpus if gpu.vram_bytes is not None]
        return sum(measured) if measured else None

    def to_dict(self) -> dict[str, Any]:
        """JSON-ready, for the CLI the installer UI consumes."""
        data = asdict(self)
        data["total_vram_bytes"] = self.total_vram_bytes
        data["memory"]["total_gb"] = round(self.memory.total_gb, 2)
        data["storage"]["free_gb"] = round(self.storage.free_gb, 2)
        return data


# --- Probes ----------------------------------------------------------
#
# Each returns its own value or None. None of them raises.


def _run(command: list[str]) -> str | None:
    """Run a probe command, or return ``None``.

    Swallows every failure on purpose: a missing tool, a non-zero exit,
    a timeout and a permissions error are all just "this probe has no
    answer" as far as an installer is concerned.
    """
    try:
        # Fixed argv, never a shell string -- no injection surface.
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=_PROBE_TIMEOUT_SECONDS,
            check=False,
            # Windows: keep a console window from flashing during a GUI
            # installation.
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None


def detect_cpu() -> CpuInfo:
    frequency = None
    try:
        measured = psutil.cpu_freq()
        frequency = measured.max or None if measured else None
    except (OSError, NotImplementedError, AttributeError):
        # `cpu_freq` is unavailable on several platforms and raises
        # rather than returning None.
        frequency = None

    return CpuInfo(
        model=platform.processor() or None,
        physical_cores=psutil.cpu_count(logical=False),
        logical_cores=psutil.cpu_count(logical=True),
        max_frequency_mhz=frequency,
        architecture=platform.machine(),
    )


def detect_memory() -> MemoryInfo:
    virtual = psutil.virtual_memory()
    return MemoryInfo(total_bytes=virtual.total, available_bytes=virtual.available)


def detect_storage(target: Path | None = None) -> StorageInfo:
    """Free space on the volume JARVIS would be installed to.

    The install directory usually **does not exist yet** -- that is the
    normal case during installation, not an edge case -- and
    ``shutil.disk_usage`` raises on a missing path. So this walks up to
    the nearest existing ancestor, which resolves to the target's own
    drive root at worst.

    The first version fell back to the current working directory
    instead, which reported free space on whichever drive the installer
    was launched from. On Windows that is routinely a different volume,
    so the summary would state a figure for the wrong disk and a machine
    with a full target drive could sail through the disk-space check.
    Caught by running against a real install path.
    """
    candidate = (target or Path.home()).expanduser()

    for path in (candidate, *candidate.parents):
        try:
            usage = shutil.disk_usage(path)
        except OSError:
            continue
        # Report the *requested* location, since that is what the user
        # chose; the measurement is of its volume either way.
        return StorageInfo(path=str(candidate), total_bytes=usage.total, free_bytes=usage.free)

    # Every ancestor unreadable -- a malformed or disconnected path.
    usage = shutil.disk_usage(Path.cwd())
    return StorageInfo(path=str(Path.cwd()), total_bytes=usage.total, free_bytes=usage.free)


def _parse_nvidia_smi(output: str) -> list[GpuInfo]:
    gpus: list[GpuInfo] = []
    for line in output.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 2:
            continue
        name = parts[0]
        # `--format=csv,noheader,nounits` gives MiB as a bare integer.
        vram = None
        if parts[1].isdigit():
            vram = int(parts[1]) * 1024 * 1024
        gpus.append(GpuInfo(name=name, vram_bytes=vram, vendor="NVIDIA", source="nvidia-smi"))
    return gpus


def _parse_wmic_video(output: str) -> list[GpuInfo]:
    """`wmic path win32_VideoController get AdapterRAM,Name /format:csv`.

    ``AdapterRAM`` is a 32-bit field, so anything above 4 GiB wraps and
    is reported wrong. Values at or above that ceiling are dropped to
    ``None`` rather than passed on as a measurement -- an 8 GB card
    reported as 4 GB would silently push the calibration into the wrong
    tier.
    """
    gpus: list[GpuInfo] = []
    for line in output.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 3 or parts[1].lower() in {"adapterram", ""}:
            continue
        raw_ram, name = parts[1], parts[2]
        vram: int | None = None
        if raw_ram.isdigit():
            value = int(raw_ram)
            if 0 < value < 4 * _BYTES_PER_GB:
                vram = value
        if name:
            vendor = None
            for candidate in ("NVIDIA", "AMD", "Intel", "Qualcomm"):
                if candidate.lower() in name.lower():
                    vendor = candidate
                    break
            gpus.append(GpuInfo(name=name, vram_bytes=vram, vendor=vendor, source="wmic"))
    return gpus


def detect_gpus() -> tuple[tuple[GpuInfo, ...], tuple[str, ...]]:
    """Every GPU we can enumerate, plus notes explaining any gap."""
    notes: list[str] = []

    nvidia = _run(
        [
            "nvidia-smi",
            "--query-gpu=name,memory.total",
            "--format=csv,noheader,nounits",
        ]
    )
    if nvidia:
        parsed = _parse_nvidia_smi(nvidia)
        if parsed:
            return tuple(parsed), ()

    info = detect_platform()
    if info.is_windows:
        wmic = _run(
            ["wmic", "path", "win32_VideoController", "get", "AdapterRAM,Name", "/format:csv"]
        )
        if wmic:
            parsed = _parse_wmic_video(wmic)
            if parsed:
                if all(gpu.vram_bytes is None for gpu in parsed):
                    notes.append(
                        "GPU memory could not be measured reliably on this system; "
                        "calibration used CPU and RAM only."
                    )
                return tuple(parsed), tuple(notes)

    notes.append("No GPU could be detected. Calibration used CPU and RAM only.")
    return (), tuple(notes)


def detect_power() -> PowerInfo:
    try:
        battery = psutil.sensors_battery()
    except (AttributeError, NotImplementedError, OSError):
        return PowerInfo(has_battery=None, on_battery=None, percent=None)

    if battery is None:
        # Genuinely ambiguous: a desktop and an unreadable battery look
        # identical here, so neither is asserted.
        return PowerInfo(has_battery=None, on_battery=None, percent=None)

    return PowerInfo(
        has_battery=True,
        on_battery=not battery.power_plugged,
        percent=float(battery.percent),
    )


def detect_temperature() -> tuple[float | None, str | None]:
    """Highest current core temperature, or ``None`` with a reason.

    ``psutil.sensors_temperatures`` does not exist on Windows at all,
    which is the primary platform for this task group -- so ``None``
    here is the expected result, not a failure, and the note says so.
    """
    getter = getattr(psutil, "sensors_temperatures", None)
    if getter is None:
        return None, "Temperature sensors are not exposed by this operating system."

    try:
        readings = getter()
    except (OSError, NotImplementedError):
        return None, "Temperature sensors could not be read."

    values = [entry.current for group in readings.values() for entry in group if entry.current]
    if not values:
        return None, "No temperature sensors reported a reading."
    return max(values), None


def detect_internet(host: str = "1.1.1.1", port: int = 53, timeout: float = 2.0) -> bool | None:
    """A real outbound connection, not a DNS lookup.

    Resolving a name can succeed against a captive portal or a cached
    entry while the machine has no route out; opening a socket to a
    known resolver is the cheaper and more truthful test.
    """
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False
    except Exception:
        # A probe must never break detection, whatever it raises.
        return None


_NPU_HINTS = re.compile(r"\b(npu|neural|ai boost|hexagon|ane)\b", re.IGNORECASE)


def detect_npu() -> str | None:
    """Best-effort NPU identification.

    Deliberately conservative. There is no portable NPU enumeration API,
    and reporting "no NPU" on a machine that has one is less harmful than
    claiming one that is not there -- the calibration treats an NPU as a
    bonus, never as a requirement. Returns the device name only when a
    hardware enumeration actually names something NPU-like.
    """
    info = detect_platform()
    if not info.is_windows:
        return None

    output = _run(["wmic", "path", "win32_PnPEntity", "get", "Name", "/format:csv"])
    if not output:
        return None

    for line in output.splitlines():
        name = line.split(",")[-1].strip()
        if name and _NPU_HINTS.search(name):
            return name
    return None


def detect_hardware(install_target: Path | None = None) -> HardwareProfile:
    """One full scan. Safe to call on any machine; never raises."""
    gpus, gpu_notes = detect_gpus()
    temperature, temperature_note = detect_temperature()

    notes = list(gpu_notes)
    if temperature_note:
        notes.append(temperature_note)

    return HardwareProfile(
        platform=detect_platform(),
        cpu=detect_cpu(),
        memory=detect_memory(),
        storage=detect_storage(install_target),
        gpus=gpus,
        power=detect_power(),
        internet=detect_internet(),
        temperature_celsius=temperature,
        npu=detect_npu(),
        notes=tuple(notes),
    )
