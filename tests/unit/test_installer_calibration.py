"""Installer calibration, model tiers and validation -- M22 Task Group A.

The rule these tests exist to protect is the one the whole package is
built on: **a field is either measured or it is ``None``.** An installer
that guesses produces a calibration that is confidently wrong in ways
the user cannot see, so most of what follows is about what happens when
a probe has no answer.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.infrastructure.platform.platform_detector import PlatformInfo
from jarvis.installer.calibration import calibrate
from jarvis.installer.hardware import (
    CpuInfo,
    GpuInfo,
    HardwareProfile,
    MemoryInfo,
    PowerInfo,
    StorageInfo,
)
from jarvis.installer.local_model import (
    InsufficientMemoryError,
    recommend_model,
    tier_to_dict,
)
from jarvis.installer.validation import validate_installation
from jarvis.installer.voice import plan_voice

GB_DECIMAL = 1_000_000_000
GIB = 1024**3


def _platform(system: str = "Windows") -> PlatformInfo:
    return PlatformInfo(
        system=system,
        release="11",
        version="10.0.26200",
        machine="AMD64",
        python="3.13.0",
        is_windows=system == "Windows",
        is_macos=system == "Darwin",
        is_linux=system == "Linux",
    )


def profile(
    *,
    ram_gb: float = 16,
    cores: int | None = 8,
    frequency: float | None = 3200.0,
    gpus: tuple[GpuInfo, ...] = (),
    free_gb: float = 100.0,
    internet: bool | None = True,
    on_battery: bool | None = False,
    npu: str | None = None,
    temperature: float | None = None,
    system: str = "Windows",
    architecture: str = "AMD64",
) -> HardwareProfile:
    return HardwareProfile(
        platform=_platform(system),
        cpu=CpuInfo(
            model="Test CPU",
            physical_cores=cores,
            logical_cores=(cores * 2) if cores else None,
            max_frequency_mhz=frequency,
            architecture=architecture,
        ),
        memory=MemoryInfo(
            total_bytes=int(ram_gb * GB_DECIMAL), available_bytes=int(ram_gb * GB_DECIMAL * 0.4)
        ),
        storage=StorageInfo(
            path="C:/JARVIS", total_bytes=int(500 * GIB), free_bytes=int(free_gb * GIB)
        ),
        gpus=gpus,
        power=PowerInfo(has_battery=on_battery is not None, on_battery=on_battery, percent=80.0),
        internet=internet,
        temperature_celsius=temperature,
        npu=npu,
    )


class TestModelRecommendation:
    def test_tier_thresholds_use_decimal_gb(self) -> None:
        """A real 16 GB machine reports ~15.7 GiB.

        Comparing that against a binary 16 GiB threshold offers it the
        8 GB tier -- and *every* 16 GB machine would miss, since none
        ever reports 16.0 GiB. Found on real hardware.
        """
        sixteen_gb_machine = 16_857_645_056  # measured on a real laptop
        assert recommend_model(sixteen_gb_machine).key == "standard"

    @pytest.mark.parametrize(
        ("ram_gb", "expected"),
        [
            (4, "tiny"),
            (6, "tiny"),
            (8, "small"),
            (12, "small"),
            (16, "standard"),
            (32, "advanced"),
            (128, "advanced"),
        ],
    )
    def test_tier_for_ram(self, ram_gb: int, expected: str) -> None:
        assert recommend_model(ram_gb * GB_DECIMAL).key == expected

    def test_below_the_smallest_tier_raises(self) -> None:
        with pytest.raises(InsufficientMemoryError, match="below"):
            recommend_model(2 * GB_DECIMAL)

    def test_vram_promotes_by_one_tier(self) -> None:
        # 16 GB RAM alone is Standard; a 12 GB GPU earns Advanced.
        assert recommend_model(16 * GB_DECIMAL).key == "standard"
        assert recommend_model(16 * GB_DECIMAL, vram_bytes=int(12 * GIB)).key == "advanced"

    def test_vram_never_promotes_more_than_one_tier(self) -> None:
        # A huge GPU does not compensate for a system that will swap.
        assert recommend_model(8 * GB_DECIMAL, vram_bytes=int(48 * GIB)).key == "standard"

    def test_absent_vram_never_demotes(self) -> None:
        # A probe that could not answer must not penalise the machine.
        assert recommend_model(32 * GB_DECIMAL, vram_bytes=None).key == "advanced"

    def test_personal_payload_has_no_model_id(self) -> None:
        tier = recommend_model(16 * GB_DECIMAL)
        assert "model_id" not in tier_to_dict(tier, include_model_id=False)
        assert "model_id" in tier_to_dict(tier, include_model_id=True)


class TestCalibration:
    def test_score_is_bounded(self) -> None:
        weak = calibrate(profile(ram_gb=4, cores=2, frequency=1600))
        strong = calibrate(
            profile(
                ram_gb=128,
                cores=32,
                frequency=5000,
                gpus=(
                    GpuInfo(
                        name="RTX", vram_bytes=int(24 * GIB), vendor="NVIDIA", source="nvidia-smi"
                    ),
                ),
            )
        )
        assert 0 <= weak.score <= 100
        assert 0 <= strong.score <= 100
        assert strong.score > weak.score

    def test_records_what_it_could_not_measure(self) -> None:
        result = calibrate(profile(gpus=(), temperature=None, internet=None))

        assert any("Graphics memory" in entry for entry in result.missing_inputs)
        assert any("Temperature" in entry for entry in result.missing_inputs)
        assert any("Internet" in entry for entry in result.missing_inputs)

    def test_unmeasurable_cpu_scores_mid_range_not_zero(self) -> None:
        """Zero would push an unmeasurable machine into the conservative
        profile purely for being unmeasurable."""
        result = calibrate(profile(cores=None, frequency=None))
        cpu = next(c for c in result.components if c.name == "Processor")

        assert cpu.points > 0
        assert "assumed mid-range" in cpu.detail

    def test_no_gpu_scores_zero_for_that_component_only(self) -> None:
        result = calibrate(profile(gpus=()))
        accelerator = next(c for c in result.components if c.name == "Accelerator")

        assert accelerator.points == 0
        assert result.score > 0  # RAM and CPU still count

    def test_npu_counts_without_measurable_vram(self) -> None:
        without = calibrate(profile(npu=None)).score
        with_npu = calibrate(profile(npu="Intel AI Boost")).score
        assert with_npu > without

    def test_battery_softens_the_profile(self) -> None:
        plugged = calibrate(profile(ram_gb=128, cores=32, frequency=5000, on_battery=False))
        unplugged = calibrate(profile(ram_gb=128, cores=32, frequency=5000, on_battery=True))

        assert plugged.performance_profile == "performance"
        assert unplugged.performance_profile == "balanced"
        assert any("battery" in w.lower() for w in unplugged.warnings)

    def test_cloud_usage_is_never_never(self) -> None:
        """§22.1 makes cloud the second step, always -- never absent."""
        for ram in (4, 8, 16, 64, 256):
            result = calibrate(profile(ram_gb=ram))
            assert result.cloud_usage in {"preferred", "balanced", "minimal"}

    def test_offline_machine_still_gets_a_cloud_preference(self) -> None:
        # The check is a snapshot taken during installation; a laptop
        # installed on a train is not permanently offline.
        result = calibrate(profile(internet=False))
        assert result.cloud_usage in {"preferred", "balanced", "minimal"}
        assert any("internet" in w.lower() for w in result.warnings)

    def test_machine_below_the_smallest_tier_still_calibrates(self) -> None:
        result = calibrate(profile(ram_gb=2))

        assert result.recommended_model is None
        assert any("cloud AI" in w for w in result.warnings)
        assert result.score >= 0  # total function -- no exception

    def test_warns_when_the_model_will_not_fit(self) -> None:
        result = calibrate(profile(ram_gb=32, free_gb=5))
        assert any("free on the installation drive" in w for w in result.warnings)


class TestAccountShaping:
    """§22.11/§22.12: a personal payload does not *contain* the
    technical detail, rather than containing it and hiding it."""

    def test_personal_payload_omits_internals(self) -> None:
        data = calibrate(profile()).to_dict(account_type="personal")

        assert "components" not in data
        assert "inputs" not in data
        assert "resource_limits" not in data
        assert "model_id" not in (data["recommended_model"] or {})

    def test_administrator_payload_includes_them(self) -> None:
        data = calibrate(profile()).to_dict(account_type="administrator")

        assert "components" in data
        assert "resource_limits" in data
        assert "model_id" in data["recommended_model"]

    def test_personal_voice_plan_names_no_provider(self) -> None:
        plan = plan_voice(profile())
        data = plan.to_dict(include_providers=False)

        rendered = str(data).lower()
        for provider in ("piper", "whisper", "elevenlabs"):
            assert provider not in rendered
        assert data["identity_name"] == "JARVIS"


class TestVoicePlan:
    def test_local_speech_is_always_included(self) -> None:
        """An installation that can only speak online would make voice a
        cloud feature, which §22.1 forbids."""
        plan = plan_voice(profile(internet=False))

        local_tts = [c for c in plan.components if c.role == "tts_local"]
        assert local_tts and local_tts[0].enabled and local_tts[0].required
        assert plan.can_test_offline is True

    def test_cloud_voice_is_off_by_default(self) -> None:
        plan = plan_voice(profile())
        cloud = next(c for c in plan.components if c.role == "tts_cloud")
        assert cloud.enabled is False
        assert cloud.required is False

    def test_small_machine_gets_the_compact_recogniser(self) -> None:
        big = plan_voice(profile(ram_gb=32, cores=8))
        small = plan_voice(profile(ram_gb=4, cores=2))
        assert small.total_download_mb < big.total_download_mb

    def test_one_identity_regardless_of_components(self) -> None:
        assert (
            plan_voice(profile()).identity_name
            == plan_voice(profile(ram_gb=4, cores=2), include_cloud_voice=True).identity_name
        )


class TestValidation:
    def test_a_healthy_machine_can_install(self, tmp_path: Path) -> None:
        report = validate_installation(profile(), install_target=tmp_path)
        assert report.can_install is True
        assert report.failures == ()

    def test_insufficient_disk_blocks(self, tmp_path: Path) -> None:
        report = validate_installation(profile(free_gb=1), install_target=tmp_path)
        assert report.can_install is False
        assert any(r.key == "disk" for r in report.failures)

    def test_low_memory_warns_but_does_not_block(self, tmp_path: Path) -> None:
        # JARVIS still runs cloud-first; refusing to install helps nobody.
        report = validate_installation(profile(ram_gb=2), install_target=tmp_path)
        assert report.can_install is True
        assert any(r.key == "memory" and r.verdict == "warn" for r in report.results)

    def test_offline_warns_but_does_not_block(self, tmp_path: Path) -> None:
        # A local-first product must install without a network.
        report = validate_installation(profile(internet=False), install_target=tmp_path)
        assert report.can_install is True
        assert any(r.key == "internet" and r.verdict == "warn" for r in report.results)

    def test_unknown_internet_warns_rather_than_fails(self, tmp_path: Path) -> None:
        report = validate_installation(profile(internet=None), install_target=tmp_path)
        assert any(r.key == "internet" and r.verdict == "warn" for r in report.results)
        assert report.can_install is True

    def test_unsupported_architecture_blocks(self, tmp_path: Path) -> None:
        report = validate_installation(profile(architecture="mips"), install_target=tmp_path)
        assert report.can_install is False

    def test_unmeasurable_architecture_warns(self, tmp_path: Path) -> None:
        """Only a *measured* shortfall blocks."""
        report = validate_installation(profile(architecture=""), install_target=tmp_path)
        assert any(r.key == "architecture" and r.verdict == "warn" for r in report.results)
        assert report.can_install is True

    def test_non_windows_warns_this_task_group(self, tmp_path: Path) -> None:
        report = validate_installation(profile(system="Linux"), install_target=tmp_path)
        assert any(r.key == "os" and r.verdict == "warn" for r in report.results)
        assert report.can_install is True

    def test_unwritable_target_blocks(self, tmp_path: Path) -> None:
        target = tmp_path / "a-file-not-a-directory"
        target.write_text("x", encoding="utf-8")

        report = validate_installation(profile(), install_target=target)

        assert report.can_install is False
        assert any(r.key == "permissions" for r in report.failures)

    def test_blocking_matches_verdict(self, tmp_path: Path) -> None:
        report = validate_installation(profile(free_gb=1), install_target=tmp_path)
        for result in report.results:
            assert result.blocking == (result.verdict == "fail")
