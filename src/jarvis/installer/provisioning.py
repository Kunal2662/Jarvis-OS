"""The provisioning engine -- M22 Task Group B.

Runs the installation: dependencies, directories, configuration,
downloads, first-run preparation, verification, manifest. Resumable at
step granularity through :mod:`jarvis.installer.journal`, and at byte
granularity within a download through
:mod:`jarvis.installer.download`.

**Every step is idempotent.** That is what makes recovery simple enough
to trust: the engine never has to reason about how far a step got before
a crash, because re-running it from the beginning is always safe. The
journal records only completions, so an interrupted step is re-run and a
finished one is skipped.

**Progress phrases are fixed by `ARCHITECTURE.md` §22.12.** A personal
user sees "Preparing…", "Downloading…", "Verifying…" — never a step id,
a model name, a source or a path. The phase vocabulary lives in
:data:`PHASE_LABEL` so it is data rather than strings scattered through
the engine.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jarvis.installer.calibration import AICalibration
from jarvis.installer.dependencies import DependencyReport, detect_dependencies
from jarvis.installer.download import DownloadManager, DownloadProgress, DownloadState
from jarvis.installer.first_run import prepare_directories, prepare_first_run
from jarvis.installer.hardware import HardwareProfile
from jarvis.installer.journal import STEP_ORDER, ProvisioningJournal, Step
from jarvis.installer.manifest import build_manifest, read_manifest, write_manifest
from jarvis.installer.sources import Artifact, SourceRegistry
from jarvis.installer.verification import VerificationReport, verify_installation
from jarvis.installer.voice import VoicePlan

#: What each step is called on screen. §22.12's mandated vocabulary --
#: the user is told what is happening to *them*, not which subsystem is
#: running.
PHASE_LABEL: dict[Step, str] = {
    Step.DEPENDENCIES: "Preparing…",
    Step.DIRECTORIES: "Preparing…",
    Step.CONFIGURATION: "Installing…",
    Step.MODEL_DOWNLOAD: "Downloading…",
    Step.VOICE_DOWNLOAD: "Downloading…",
    Step.FIRST_RUN: "Optimizing…",
    Step.VERIFICATION: "Verifying…",
    Step.MANIFEST: "Finalizing…",
}


@dataclass(slots=True)
class ProvisioningProgress:
    step: Step
    label: str
    """The §22.12 phrase. Safe to show anyone."""
    completed_steps: int
    total_steps: int
    detail: str = ""
    """Administrator-facing. May name a component, so the UI shows it
    only in administrator mode."""
    download: DownloadProgress | None = None

    @property
    def percent(self) -> float:
        return (self.completed_steps / self.total_steps) * 100.0

    def to_dict(self, *, include_detail: bool) -> dict[str, Any]:
        data: dict[str, Any] = {
            "step": self.step.value,
            "label": self.label,
            "completed_steps": self.completed_steps,
            "total_steps": self.total_steps,
            "percent": round(self.percent, 1),
        }
        if include_detail:
            data["detail"] = self.detail
        if self.download is not None:
            data["download"] = self.download.to_dict(include_source=include_detail)
        return data


ProgressCallback = Callable[[ProvisioningProgress], None]


@dataclass(slots=True)
class ProvisioningResult:
    root: Path
    resumed: bool
    completed_steps: list[str] = field(default_factory=list)
    skipped_steps: list[str] = field(default_factory=list)
    downloads: dict[str, DownloadProgress] = field(default_factory=dict)
    verification: VerificationReport | None = None
    manifest_path: Path | None = None
    dependencies: DependencyReport | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def succeeded(self) -> bool:
        return not self.errors and (self.verification is None or self.verification.healthy)

    def to_dict(self, *, include_detail: bool) -> dict[str, Any]:
        data: dict[str, Any] = {
            "root": str(self.root),
            "resumed": self.resumed,
            "succeeded": self.succeeded,
            "completed_steps": list(self.completed_steps),
            "skipped_steps": list(self.skipped_steps),
            "errors": list(self.errors),
        }
        if self.verification is not None:
            data["verification"] = self.verification.to_dict()
        if include_detail:
            data["downloads"] = {
                key: progress.to_dict(include_source=True)
                for key, progress in self.downloads.items()
            }
            if self.dependencies is not None:
                data["dependencies"] = self.dependencies.to_dict(include_paths=True)
            data["manifest_path"] = str(self.manifest_path) if self.manifest_path else None
        return data


class ProvisioningEngine:
    """Runs, resumes and repairs an installation."""

    def __init__(
        self,
        root: Path,
        *,
        registry: SourceRegistry,
        hardware: HardwareProfile,
        calibration: AICalibration,
        voice_plan: VoicePlan,
        account_type: str = "personal",
        online: bool = True,
        download_manager: DownloadManager | None = None,
    ) -> None:
        self._root = root
        self._registry = registry
        self._hardware = hardware
        self._calibration = calibration
        self._voice_plan = voice_plan
        self._account_type = account_type
        self._online = online

        # Directories must exist before the journal can be written into
        # them -- this is the one ordering the journal itself cannot
        # bootstrap.
        prepare_directories(root)
        self._journal = ProvisioningJournal(root / "config")
        self._downloads = download_manager or DownloadManager(registry, root)

    @property
    def journal(self) -> ProvisioningJournal:
        return self._journal

    # --- Artefacts --------------------------------------------------

    def model_artifacts(self) -> list[Artifact]:
        """The model to fetch, or nothing.

        Empty when the machine is below the smallest tier -- the
        calibration already decided that and recorded a warning, so this
        does not re-litigate it.
        """
        tier = self._calibration.recommended_model
        if tier is None:
            return []
        return [
            Artifact(
                key=tier.model_id,
                kind="model",
                # What a personal user sees while it downloads. `key` is
                # the model id and is §22.12-restricted.
                label="Local AI",
                expected_bytes=int(tier.approximate_download_gb * 1_000_000_000),
                # No checksum: this build resolves no concrete source, so
                # there is no published digest to carry. `verify_file`
                # reports such a file as *unverifiable* rather than
                # verified, and verification surfaces that as a warning.
                checksum=None,
            )
        ]

    def voice_artifacts(self) -> list[Artifact]:
        return [
            Artifact(
                key=component.key,
                kind="voice",
                label=component.label,
                expected_bytes=component.approximate_download_mb * 1_000_000,
                checksum=None,
            )
            for component in self._voice_plan.components
            if component.enabled and component.approximate_download_mb > 0
        ]

    # --- Run --------------------------------------------------------

    def provision(self, *, on_progress: ProgressCallback | None = None) -> ProvisioningResult:
        """Run every outstanding step.

        Safe to call repeatedly: completed steps are skipped, so this is
        simultaneously "install", "resume after a crash" and "continue
        after a network failure". There is no separate resume entry
        point, because a resume that took a different code path from an
        install would be the path least often exercised and most often
        broken.
        """
        self._journal.begin()
        result = ProvisioningResult(root=self._root, resumed=self._journal.is_resume)

        total = len(STEP_ORDER)
        for index, step in enumerate(STEP_ORDER):
            if self._journal.is_complete(step):
                result.skipped_steps.append(step.value)
                continue

            progress = ProvisioningProgress(
                step=step,
                label=PHASE_LABEL[step],
                completed_steps=index,
                total_steps=total,
            )
            if on_progress:
                on_progress(progress)

            try:
                self._run_step(step, result, progress, on_progress)
            except Exception as err:
                # A step failing stops provisioning but does not lose
                # what came before: the journal keeps every completed
                # step, so the next run resumes here rather than at the
                # beginning.
                result.errors.append(f"{step.value}: {err}")
                return result

            result.completed_steps.append(step.value)

        return result

    def _run_step(
        self,
        step: Step,
        result: ProvisioningResult,
        progress: ProvisioningProgress,
        on_progress: ProgressCallback | None,
    ) -> None:
        if step is Step.DEPENDENCIES:
            report = detect_dependencies()
            result.dependencies = report
            if not report.satisfied:
                missing = ", ".join(d.label for d in report.missing_required)
                raise RuntimeError(f"Required dependencies are missing: {missing}")
            self._journal.complete(step, data=report.to_dict(include_paths=True))

        elif step is Step.DIRECTORIES:
            prepared = prepare_directories(self._root)
            self._journal.complete(step, data=prepared.to_dict())

        elif step is Step.CONFIGURATION:
            limits = (
                {
                    "max_memory_fraction": self._calibration.resource_limits.max_memory_fraction,
                    "max_cpu_fraction": self._calibration.resource_limits.max_cpu_fraction,
                    "use_gpu": self._calibration.resource_limits.use_gpu,
                }
                if self._account_type == "administrator"
                else None
            )
            prepared = prepare_first_run(
                self._root,
                performance_profile=self._calibration.performance_profile,
                cloud_usage=self._calibration.cloud_usage,
                model_tier=(
                    self._calibration.recommended_model.key
                    if self._calibration.recommended_model
                    else None
                ),
                account_type=self._account_type,
                resource_limits=limits,
            )
            self._journal.complete(step, data=prepared.to_dict())

        elif step in {Step.MODEL_DOWNLOAD, Step.VOICE_DOWNLOAD}:
            artifacts = (
                self.model_artifacts() if step is Step.MODEL_DOWNLOAD else self.voice_artifacts()
            )
            if not artifacts:
                self._journal.complete(step, detail="Nothing to download.")
                return

            def relay(download: DownloadProgress) -> None:
                progress.download = download
                progress.detail = f"{download.key}: {download.state.value}"
                if on_progress:
                    on_progress(progress)

            destination = self._root / ("models" if step is Step.MODEL_DOWNLOAD else "voice")
            manager = DownloadManager(self._registry, destination)
            outcomes = manager.download_all(artifacts, online=self._online, on_progress=relay)
            result.downloads.update(outcomes)

            failed = [
                key
                for key, outcome in outcomes.items()
                if outcome.state in {DownloadState.FAILED, DownloadState.CANCELLED}
            ]
            if failed:
                raise RuntimeError(f"{len(failed)} download(s) did not complete.")

            self._journal.complete(
                step,
                data={key: outcome.state.value for key, outcome in outcomes.items()},
            )

        elif step is Step.FIRST_RUN:
            prepared = prepare_first_run(
                self._root,
                performance_profile=self._calibration.performance_profile,
                cloud_usage=self._calibration.cloud_usage,
                model_tier=(
                    self._calibration.recommended_model.key
                    if self._calibration.recommended_model
                    else None
                ),
                account_type=self._account_type,
            )
            self._journal.complete(step, data=prepared.to_dict())

        elif step is Step.VERIFICATION:
            # Distinct name from the dependency branch's `report`: one
            # local reused for two unrelated types reads fine and does
            # not type-check.
            verification = self._verify()
            result.verification = verification
            self._journal.complete(step, data=verification.to_dict())

        elif step is Step.MANIFEST:
            path = self._write_manifest(result)
            result.manifest_path = path
            self._journal.complete(step, detail=str(path))

    def _expected_artifacts(self) -> tuple[dict[str, str | None], dict[str, str | None]]:
        """Keyed by **filename**, not key.

        Verification looks these names up on disk, and the download
        manager writes under `Artifact.filename` -- the sanitised form,
        because a model id like `llama3.1:8b` cannot be a Windows
        filename. Keying by `key` here made verification report a
        correctly-downloaded model as missing, since it searched for a
        name that can never exist on the primary platform. Found by a
        real end-to-end provisioning run; the unit tests had used keys
        with no illegal characters and so never exercised it.
        """
        models = {artifact.filename: artifact.checksum for artifact in self.model_artifacts()}
        voice = {artifact.filename: artifact.checksum for artifact in self.voice_artifacts()}
        return models, voice

    def _verify(self) -> VerificationReport:
        models, voice = self._expected_artifacts()
        return verify_installation(
            self._root,
            expected_models=models,
            expected_voice=voice,
            manifest=read_manifest(self._root),
        )

    def _write_manifest(self, result: ProvisioningResult) -> Path:
        dependencies = result.dependencies or detect_dependencies()
        verification = result.verification or self._verify()

        document = build_manifest(
            root=self._root,
            hardware=self._hardware.to_dict(),
            # Administrator shaping: the manifest is read by software,
            # never displayed, so it carries full detail.
            calibration=self._calibration.to_dict(account_type="administrator"),
            account_type=self._account_type,
            installed_components=[
                {
                    "key": component.key,
                    "label": component.label,
                    "role": component.role,
                    "enabled": component.enabled,
                }
                for component in self._voice_plan.components
            ],
            installed_models=[
                {"key": artifact.key, "expected_bytes": artifact.expected_bytes}
                for artifact in self.model_artifacts()
            ],
            voice_configuration={
                "identity": self._voice_plan.identity_name,
                "can_test_offline": self._voice_plan.can_test_offline,
            },
            verification=verification.to_dict(),
            dependencies=dependencies.to_dict(include_paths=True),
        )
        return write_manifest(self._root, document)

    # --- Repair -----------------------------------------------------

    def repair(
        self, target: Step, *, on_progress: ProgressCallback | None = None
    ) -> ProvisioningResult:
        """Redo *target* and everything after it.

        Not just *target*: a later step's result can depend on an earlier
        one, so re-fetching a model while keeping the verification that
        ran against the previous file would leave the manifest asserting
        something untrue. `journal.invalidate` enforces that ordering.
        """
        self._journal.invalidate(target)
        return self.provision(on_progress=on_progress)


def repair_step_from_key(key: str) -> Step | None:
    """Map a verification result's ``repair_step`` onto a journal step.

    Returns ``None`` for an unknown key rather than raising: the caller
    is acting on a user's click, and an unrecognised repair target should
    be ignored, not crash the installer.
    """
    try:
        return Step(key)
    except ValueError:
        return None
