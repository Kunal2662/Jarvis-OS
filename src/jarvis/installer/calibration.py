"""AI calibration -- M22 Task Group A.

Turns a :class:`~jarvis.installer.hardware.HardwareProfile` into an **AI
Capability Score** and the configuration that follows from it, per
`ARCHITECTURE.md` §22.8 (Hardware Calibration) and §22.9 (Universal
Performance Engine).

§22.9's rule governs the whole module:

    The same user experience across all hardware. A different execution
    strategy, not different features.

So nothing here disables a capability. A weak machine gets smaller local
models, tighter resource ceilings and a greater willingness to reach for
cloud; it does not get a lesser JARVIS.

**The score is explainable, not a black box.** Every component is
recorded with the input that produced it, and every input that could not
be measured is listed in ``missing_inputs``. A recommendation the user
cannot interrogate is one they cannot correct -- and on hardware
detection, gaps are normal (see :mod:`jarvis.installer.hardware`).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from jarvis.installer.hardware import HardwareProfile
from jarvis.installer.local_model import (
    InsufficientMemoryError,
    ModelTier,
    recommend_model,
)

_BYTES_PER_GB = 1024**3

AccountType = Literal["personal", "administrator"]
PerformanceProfile = Literal["conservative", "balanced", "performance"]

# Component weights. RAM dominates because it is both the binding
# constraint on local inference and the one figure measurable everywhere;
# GPU is worth a lot when present but must never be required, since a
# machine with an unprobeable GPU would otherwise be scored as though it
# had none.
_WEIGHT_RAM = 45
_WEIGHT_CPU = 30
_WEIGHT_GPU = 25


@dataclass(frozen=True, slots=True)
class ScoreComponent:
    name: str
    points: float
    maximum: float
    detail: str


@dataclass(frozen=True, slots=True)
class CalibrationInputs:
    """What calibration actually had to work with."""

    total_ram_gb: float
    physical_cores: int | None
    max_frequency_mhz: float | None
    total_vram_gb: float | None
    has_npu: bool
    on_battery: bool | None
    internet: bool | None


@dataclass(frozen=True, slots=True)
class ResourceLimits:
    """Ceilings written into the installed configuration.

    Fractions of the machine, not absolute figures -- the same profile
    then means the same thing on a 4 GB laptop and a 128 GB workstation.
    """

    max_memory_fraction: float
    max_cpu_fraction: float
    use_gpu: bool


@dataclass(frozen=True, slots=True)
class AICalibration:
    score: int
    """0-100. Higher means more work can be done locally."""
    components: tuple[ScoreComponent, ...]
    inputs: CalibrationInputs
    performance_profile: PerformanceProfile
    recommended_model: ModelTier | None
    """``None`` only when the machine is below the smallest tier -- the
    installer then explains that JARVIS will run cloud-first."""
    resource_limits: ResourceLimits
    cloud_usage: Literal["preferred", "balanced", "minimal"]
    """How readily this machine should reach for cloud AI. Never
    "never": §22.1 makes cloud an enhancement, and never a requirement,
    but also never forbidden."""
    missing_inputs: tuple[str, ...]
    """Inputs detection could not measure. Surfaced verbatim in the UI."""
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self, *, account_type: AccountType = "personal") -> dict[str, Any]:
        """JSON for the installer UI.

        A personal payload carries no model id and no resource
        fractions: §22.11 says normal users never manage technical
        configuration, and the honest way to enforce that is for the
        data not to reach them. An Administrator gets everything.
        """
        data: dict[str, Any] = {
            "score": self.score,
            "performance_profile": self.performance_profile,
            "cloud_usage": self.cloud_usage,
            "missing_inputs": list(self.missing_inputs),
            "warnings": list(self.warnings),
        }

        if self.recommended_model is not None:
            model = asdict(self.recommended_model)
            if account_type == "personal":
                model.pop("model_id")
            data["recommended_model"] = model
        else:
            data["recommended_model"] = None

        if account_type == "administrator":
            data["components"] = [asdict(component) for component in self.components]
            data["inputs"] = asdict(self.inputs)
            data["resource_limits"] = asdict(self.resource_limits)

        return data


def _score_ram(ram_gb: float) -> ScoreComponent:
    """Full marks at 32 GB, which is where the Advanced tier begins."""
    ratio = min(ram_gb / 32.0, 1.0)
    return ScoreComponent(
        name="Memory",
        points=round(_WEIGHT_RAM * ratio, 1),
        maximum=_WEIGHT_RAM,
        detail=f"{ram_gb:.1f} GB of system memory",
    )


def _score_cpu(cores: int | None, frequency_mhz: float | None) -> ScoreComponent:
    if cores is None:
        # Cannot be measured: award the midpoint rather than zero. A
        # zero here would push an unmeasurable machine into the
        # conservative profile purely for being unmeasurable.
        return ScoreComponent(
            name="Processor",
            points=_WEIGHT_CPU / 2,
            maximum=_WEIGHT_CPU,
            detail="Core count unavailable; assumed mid-range",
        )

    # Full marks at 8 physical cores; a clock above 3 GHz adds the last
    # slice, so a fast quad-core is not scored as though it were slow.
    core_ratio = min(cores / 8.0, 1.0)
    clock_ratio = min((frequency_mhz or 0) / 3000.0, 1.0) if frequency_mhz else 0.5
    ratio = core_ratio * 0.75 + clock_ratio * 0.25

    detail = f"{cores} physical core{'s' if cores != 1 else ''}"
    if frequency_mhz:
        detail += f" at up to {frequency_mhz / 1000:.1f} GHz"

    return ScoreComponent(
        name="Processor",
        points=round(_WEIGHT_CPU * ratio, 1),
        maximum=_WEIGHT_CPU,
        detail=detail,
    )


def _score_gpu(vram_gb: float | None, has_npu: bool) -> ScoreComponent:
    if vram_gb is None and not has_npu:
        return ScoreComponent(
            name="Accelerator",
            points=0.0,
            maximum=_WEIGHT_GPU,
            detail="No GPU or NPU detected",
        )

    if vram_gb is None:
        # An NPU with no measurable VRAM still accelerates real work.
        return ScoreComponent(
            name="Accelerator",
            points=round(_WEIGHT_GPU * 0.4, 1),
            maximum=_WEIGHT_GPU,
            detail="Neural processing unit detected",
        )

    # Full marks at 12 GB of VRAM.
    ratio = min(vram_gb / 12.0, 1.0)
    points = _WEIGHT_GPU * ratio
    detail = f"{vram_gb:.1f} GB of graphics memory"
    if has_npu:
        points = min(points + _WEIGHT_GPU * 0.1, _WEIGHT_GPU)
        detail += " plus a neural processing unit"

    return ScoreComponent(
        name="Accelerator", points=round(points, 1), maximum=_WEIGHT_GPU, detail=detail
    )


def _profile_for(score: int) -> PerformanceProfile:
    if score >= 70:
        return "performance"
    if score >= 40:
        return "balanced"
    return "conservative"


def _limits_for(profile: PerformanceProfile, has_gpu: bool) -> ResourceLimits:
    if profile == "performance":
        return ResourceLimits(max_memory_fraction=0.6, max_cpu_fraction=0.8, use_gpu=has_gpu)
    if profile == "balanced":
        return ResourceLimits(max_memory_fraction=0.45, max_cpu_fraction=0.6, use_gpu=has_gpu)
    return ResourceLimits(max_memory_fraction=0.3, max_cpu_fraction=0.4, use_gpu=has_gpu)


def _cloud_usage_for(
    score: int, internet: bool | None
) -> Literal["preferred", "balanced", "minimal"]:
    """How readily to reach for cloud.

    Note what this never returns: "never". §22.1 fixes the priority as
    Local → Cloud → Failover, which means cloud is always the second
    step, never absent. A strong machine simply needs it less.

    An offline machine still gets a *preference*, because the check is a
    snapshot taken during installation -- a laptop installed on a train
    is not permanently offline, and writing that assumption into its
    configuration would be wrong an hour later.
    """
    if score >= 70:
        return "minimal"
    if score >= 40:
        return "balanced"
    return "preferred"


def calibrate(profile: HardwareProfile) -> AICalibration:
    """Score a machine and derive its configuration.

    Total function: every field of ``profile`` may be ``None`` and this
    still returns a usable calibration, because on real hardware several
    of them usually are.
    """
    missing: list[str] = []
    warnings: list[str] = []

    ram_gb = profile.memory.total_gb

    vram_bytes = profile.total_vram_bytes
    vram_gb = vram_bytes / _BYTES_PER_GB if vram_bytes is not None else None
    if vram_gb is None:
        missing.append("Graphics memory could not be measured")

    if profile.cpu.physical_cores is None:
        missing.append("Processor core count unavailable")
    if profile.temperature_celsius is None:
        missing.append("Temperature sensors unavailable")
    if profile.internet is None:
        missing.append("Internet connectivity could not be checked")

    has_npu = profile.npu is not None

    components = (
        _score_ram(ram_gb),
        _score_cpu(profile.cpu.physical_cores, profile.cpu.max_frequency_mhz),
        _score_gpu(vram_gb, has_npu),
    )
    score = round(sum(component.points for component in components))

    performance_profile = _profile_for(score)

    # A machine on battery gets the gentler profile regardless of score:
    # saturating the CPU of an unplugged laptop is a bad first impression
    # whatever its specification. It moves back up when plugged in --
    # this is an installation-time default, not a permanent ceiling.
    if profile.power.on_battery and performance_profile == "performance":
        performance_profile = "balanced"
        warnings.append(
            "This device is running on battery, so JARVIS starts in its balanced profile. "
            "You can raise it once plugged in."
        )

    try:
        recommended = recommend_model(profile.memory.total_bytes, vram_bytes=vram_bytes)
    except InsufficientMemoryError:
        recommended = None
        warnings.append(
            f"With {ram_gb:.1f} GB of memory this device is below the minimum for a local model. "
            "JARVIS will run using cloud AI where available."
        )

    if profile.internet is False:
        warnings.append(
            "No internet connection was detected. JARVIS will install and run locally; "
            "cloud features become available when a connection returns."
        )

    free_gb = profile.storage.free_gb
    if recommended is not None and free_gb < recommended.approximate_download_gb * 2:
        warnings.append(
            f"Only {free_gb:.1f} GB is free on the installation drive. "
            f"The {recommended.label} model needs about "
            f"{recommended.approximate_download_gb:.1f} GB plus room to run."
        )

    return AICalibration(
        score=score,
        components=components,
        inputs=CalibrationInputs(
            total_ram_gb=round(ram_gb, 2),
            physical_cores=profile.cpu.physical_cores,
            max_frequency_mhz=profile.cpu.max_frequency_mhz,
            total_vram_gb=round(vram_gb, 2) if vram_gb is not None else None,
            has_npu=has_npu,
            on_battery=profile.power.on_battery,
            internet=profile.internet,
        ),
        performance_profile=performance_profile,
        recommended_model=recommended,
        resource_limits=_limits_for(performance_profile, has_gpu=vram_gb is not None or has_npu),
        cloud_usage=_cloud_usage_for(score, profile.internet),
        missing_inputs=tuple(missing),
        warnings=tuple(warnings),
    )
