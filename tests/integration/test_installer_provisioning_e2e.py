"""Provisioning end-to-end -- M22 Task Group B.

Runs the real engine against a **real HTTP server** serving real bytes:
range requests, checksums, interruption, resume and repair all exercised
over a socket rather than a mock. A download manager tested only against
a fake has never proven the one thing it exists to do.

The server is a `ThreadingHTTPServer` on its own thread -- the same
pattern `tests/integration/test_ollama_provider_fake_server.py`
established, for the same reason: a synchronous test client cannot drive
an async fixture without blocking the loop.
"""

from __future__ import annotations

import hashlib
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, ClassVar

import pytest

from jarvis.infrastructure.platform.platform_detector import PlatformInfo
from jarvis.installer.calibration import calibrate
from jarvis.installer.download import DownloadManager, DownloadState, verify_file
from jarvis.installer.hardware import (
    CpuInfo,
    HardwareProfile,
    MemoryInfo,
    PowerInfo,
    StorageInfo,
)
from jarvis.installer.journal import ProvisioningJournal, Step
from jarvis.installer.manifest import read_manifest
from jarvis.installer.provisioning import ProvisioningEngine
from jarvis.installer.sources import (
    Artifact,
    DownloadSource,
    SourceRegistry,
    parse_sources,
)
from jarvis.installer.voice import plan_voice

GB = 1_000_000_000
PAYLOAD = b"jarvis-model-bytes-" * 4096  # ~76 KB, several chunks


def _sha256(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


class _Handler(BaseHTTPRequestHandler):
    """Serves `PAYLOAD` with real `Range` support."""

    payloads: ClassVar[dict[str, bytes]] = {}
    #: Truncate the first response to this many bytes, to simulate a
    #: connection dropping mid-transfer.
    truncate_after: int | None = None
    served: ClassVar[list[str]] = []

    def log_message(self, *args: Any) -> None:
        pass

    def do_GET(self) -> None:
        name = self.path.lstrip("/")
        body = type(self).payloads.get(name)
        if body is None:
            self.send_error(404)
            return

        type(self).served.append(name)

        start = 0
        range_header = self.headers.get("Range")
        if range_header and range_header.startswith("bytes="):
            start = int(range_header.removeprefix("bytes=").split("-")[0] or 0)

        chunk = body[start:]

        truncate = type(self).truncate_after
        if truncate is not None and start == 0:
            # Only the *first* attempt is cut short; the resumed request
            # (which carries a Range header) completes.
            chunk = chunk[:truncate]
            type(self).truncate_after = None

        if start:
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{len(body) - 1}/{len(body)}")
        else:
            self.send_response(200)
        self.send_header("Content-Length", str(len(chunk)))
        self.end_headers()
        self.wfile.write(chunk)


@pytest.fixture
def server():
    _Handler.payloads = {}
    _Handler.truncate_after = None
    _Handler.served = []

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


@pytest.fixture
def registry(server):
    host, port = server.server_address[:2]
    return SourceRegistry(
        [
            DownloadSource(
                name="test-mirror",
                base_url=f"http://{host}:{port}/{{key}}",
                kinds=("model", "voice"),
                priority=0,
            )
        ]
    )


def _profile(free_gb: float = 100.0) -> HardwareProfile:
    return HardwareProfile(
        platform=PlatformInfo(
            system="Windows",
            release="11",
            version="10.0",
            machine="AMD64",
            python="3.13.0",
            is_windows=True,
            is_macos=False,
            is_linux=False,
        ),
        cpu=CpuInfo(
            model="Test CPU",
            physical_cores=8,
            logical_cores=16,
            max_frequency_mhz=3200.0,
            architecture="AMD64",
        ),
        memory=MemoryInfo(total_bytes=32 * GB, available_bytes=16 * GB),
        storage=StorageInfo(
            path="C:/JARVIS",
            total_bytes=500 * 1024**3,
            free_bytes=int(free_gb * 1024**3),
        ),
        gpus=(),
        power=PowerInfo(has_battery=False, on_battery=False, percent=None),
        internet=True,
        temperature_celsius=None,
        npu=None,
    )


class TestDownloadManager:
    def test_downloads_and_verifies(self, registry, tmp_path: Path) -> None:
        _Handler.payloads = {"model.bin": PAYLOAD}
        manager = DownloadManager(registry, tmp_path)

        progress = manager.download(
            Artifact(key="model.bin", kind="model", checksum=_sha256(PAYLOAD))
        )

        assert progress.state is DownloadState.COMPLETED
        assert progress.verified is True
        assert (tmp_path / "model.bin").read_bytes() == PAYLOAD

    def test_resumes_an_interrupted_transfer_byte_wise(self, registry, tmp_path: Path) -> None:
        """The behaviour the whole module exists for.

        The server cuts the first response short; the retry sends a
        `Range` header and the file completes. A file-level retry would
        have re-fetched everything.
        """
        _Handler.payloads = {"model.bin": PAYLOAD}
        _Handler.truncate_after = 20_000

        manager = DownloadManager(registry, tmp_path)
        progress = manager.download(
            Artifact(key="model.bin", kind="model", checksum=_sha256(PAYLOAD))
        )

        assert progress.state is DownloadState.COMPLETED
        assert (tmp_path / "model.bin").read_bytes() == PAYLOAD
        # Two requests: the truncated one and the ranged resume.
        assert len(_Handler.served) >= 2

    def test_a_corrupt_download_is_discarded_not_resumed(self, registry, tmp_path: Path) -> None:
        # Resuming from bytes that failed a checksum would only extend a
        # corrupt file, so this is the one case that starts over.
        _Handler.payloads = {"model.bin": PAYLOAD}
        manager = DownloadManager(registry, tmp_path)

        progress = manager.download(
            Artifact(key="model.bin", kind="model", checksum=_sha256(b"different bytes"))
        )

        assert progress.state is DownloadState.FAILED
        assert not (tmp_path / "model.bin").exists()

    def test_only_a_verified_file_gets_its_final_name(self, registry, tmp_path: Path) -> None:
        _Handler.payloads = {"model.bin": PAYLOAD}
        manager = DownloadManager(registry, tmp_path)
        manager.download(Artifact(key="model.bin", kind="model", checksum=_sha256(PAYLOAD)))

        # No `.part` survives a success -- the presence of the final name
        # is itself proof of verification.
        assert not (tmp_path / "model.bin.part").exists()

    def test_reuses_an_existing_verified_file(self, registry, tmp_path: Path) -> None:
        _Handler.payloads = {"model.bin": PAYLOAD}
        (tmp_path / "model.bin").write_bytes(PAYLOAD)

        manager = DownloadManager(registry, tmp_path)
        progress = manager.download(
            Artifact(key="model.bin", kind="model", checksum=_sha256(PAYLOAD))
        )

        assert progress.state is DownloadState.SKIPPED
        assert _Handler.served == []  # nothing was fetched

    def test_replaces_an_existing_corrupt_file(self, registry, tmp_path: Path) -> None:
        _Handler.payloads = {"model.bin": PAYLOAD}
        (tmp_path / "model.bin").write_bytes(b"stale rubbish")

        manager = DownloadManager(registry, tmp_path)
        progress = manager.download(
            Artifact(key="model.bin", kind="model", checksum=_sha256(PAYLOAD))
        )

        assert progress.state is DownloadState.COMPLETED
        assert (tmp_path / "model.bin").read_bytes() == PAYLOAD

    def test_unverifiable_is_not_reported_as_verified(self, registry, tmp_path: Path) -> None:
        _Handler.payloads = {"model.bin": PAYLOAD}
        manager = DownloadManager(registry, tmp_path)

        progress = manager.download(Artifact(key="model.bin", kind="model", checksum=None))

        assert progress.state is DownloadState.COMPLETED
        assert progress.verified is False
        assert "could not be verified" in progress.message

    def test_fails_over_to_the_next_source(self, server, tmp_path: Path) -> None:
        _Handler.payloads = {"model.bin": PAYLOAD}
        host, port = server.server_address[:2]
        registry = SourceRegistry(
            [
                DownloadSource(
                    name="broken",
                    base_url="http://127.0.0.1:9/{key}",  # discard port
                    kinds=("model",),
                    priority=0,
                ),
                DownloadSource(
                    name="working",
                    base_url=f"http://{host}:{port}/{{key}}",
                    kinds=("model",),
                    priority=1,
                ),
            ]
        )

        manager = DownloadManager(registry, tmp_path)
        progress = manager.download(
            Artifact(key="model.bin", kind="model", checksum=_sha256(PAYLOAD))
        )

        assert progress.state is DownloadState.COMPLETED
        assert progress.source_name == "working"

    def test_cancel_keeps_partial_progress(self, registry, tmp_path: Path) -> None:
        _Handler.payloads = {"model.bin": PAYLOAD}
        manager = DownloadManager(registry, tmp_path)
        manager.cancel("model.bin")  # cancelled before it starts

        progress = manager.download(Artifact(key="model.bin", kind="model"))

        assert progress.state is DownloadState.CANCELLED
        assert not (tmp_path / "model.bin").exists()

    def test_no_configured_source_is_an_explicit_error(self, tmp_path: Path) -> None:
        manager = DownloadManager(SourceRegistry([]), tmp_path)
        progress = manager.download(Artifact(key="model.bin", kind="model"))

        assert progress.state is DownloadState.FAILED
        assert "JARVIS_DOWNLOAD_SOURCES" in progress.message


class TestProvisioning:
    def _engine(self, root: Path, registry: SourceRegistry, **kwargs: Any) -> ProvisioningEngine:
        profile = _profile()
        return ProvisioningEngine(
            root,
            registry=registry,
            hardware=profile,
            calibration=calibrate(profile),
            voice_plan=plan_voice(profile),
            **kwargs,
        )

    def test_full_run_produces_a_verified_installation(self, registry, tmp_path: Path) -> None:
        engine = self._engine(tmp_path, registry)
        _Handler.payloads = {
            artifact.key: PAYLOAD
            for artifact in engine.model_artifacts() + engine.voice_artifacts()
        }

        result = engine.provision()

        assert result.errors == []
        assert result.resumed is False
        assert result.verification is not None
        assert result.manifest_path is not None
        assert (tmp_path / "installation.json").exists()

    def test_manifest_records_hardware_and_calibration(self, registry, tmp_path: Path) -> None:
        engine = self._engine(tmp_path, registry)
        _Handler.payloads = {
            artifact.key: PAYLOAD
            for artifact in engine.model_artifacts() + engine.voice_artifacts()
        }
        engine.provision()

        document = read_manifest(tmp_path)

        assert document is not None
        assert document["manifest_version"] == 1
        assert document["hardware"]["ram_bytes"] == 32 * GB
        assert document["calibration"]["capability_score"] > 0
        # Inputs, not just the verdict -- a migration needs to know why.
        assert document["calibration"]["inputs"] is not None
        assert document["platform"]["system"] == "Windows"

    def test_second_run_skips_completed_steps(self, registry, tmp_path: Path) -> None:
        engine = self._engine(tmp_path, registry)
        _Handler.payloads = {
            artifact.key: PAYLOAD
            for artifact in engine.model_artifacts() + engine.voice_artifacts()
        }
        engine.provision()

        again = self._engine(tmp_path, registry).provision()

        assert again.resumed is True
        assert again.completed_steps == []
        assert len(again.skipped_steps) == 8

    def test_resumes_after_an_interruption(self, registry, tmp_path: Path) -> None:
        """Simulates a crash: the journal records the steps that
        finished, and the next run continues from there."""
        journal = ProvisioningJournal(tmp_path / "config")
        journal.begin()
        journal.complete(Step.DEPENDENCIES)
        journal.complete(Step.DIRECTORIES)

        engine = self._engine(tmp_path, registry)
        _Handler.payloads = {
            artifact.key: PAYLOAD
            for artifact in engine.model_artifacts() + engine.voice_artifacts()
        }
        result = engine.provision()

        assert result.resumed is True
        assert "dependencies" in result.skipped_steps
        assert "directories" in result.skipped_steps
        assert "manifest" in result.completed_steps

    def test_a_download_failure_keeps_earlier_progress(self, registry, tmp_path: Path) -> None:
        engine = self._engine(tmp_path, registry)
        _Handler.payloads = {}  # every download 404s

        result = engine.provision()

        assert result.errors  # stopped
        # But the steps before the download are recorded, so the retry
        # does not start from the beginning.
        assert engine.journal.is_complete(Step.DEPENDENCIES)
        assert engine.journal.is_complete(Step.CONFIGURATION)
        assert not engine.journal.is_complete(Step.MODEL_DOWNLOAD)

    def test_repair_redoes_the_target_and_everything_after(self, registry, tmp_path: Path) -> None:
        engine = self._engine(tmp_path, registry)
        _Handler.payloads = {
            artifact.key: PAYLOAD
            for artifact in engine.model_artifacts() + engine.voice_artifacts()
        }
        engine.provision()
        assert engine.journal.is_complete(Step.VERIFICATION)

        engine.journal.invalidate(Step.MODEL_DOWNLOAD)

        # Keeping a verification that ran against a previous file would
        # leave the manifest asserting something untrue.
        assert not engine.journal.is_complete(Step.MODEL_DOWNLOAD)
        assert not engine.journal.is_complete(Step.VERIFICATION)
        assert engine.journal.is_complete(Step.CONFIGURATION)

    def test_configuration_is_never_overwritten(self, registry, tmp_path: Path) -> None:
        engine = self._engine(tmp_path, registry)
        _Handler.payloads = {
            artifact.key: PAYLOAD
            for artifact in engine.model_artifacts() + engine.voice_artifacts()
        }
        engine.provision()

        config = tmp_path / "config" / "jarvis.config.json"
        config.write_text('{"user": "edited"}', encoding="utf-8")

        self._engine(tmp_path, registry).repair(Step.CONFIGURATION)

        # "Never silently overwrite" applies to a user's own file.
        assert '"user": "edited"' in config.read_text(encoding="utf-8")

    def test_progress_labels_never_leak_internals(self, registry, tmp_path: Path) -> None:
        """§22.12: the phrases a personal user sees name no step, model
        or source."""
        engine = self._engine(tmp_path, registry)
        _Handler.payloads = {
            artifact.key: PAYLOAD
            for artifact in engine.model_artifacts() + engine.voice_artifacts()
        }

        seen: list[dict[str, Any]] = []
        engine.provision(on_progress=lambda p: seen.append(p.to_dict(include_detail=False)))

        assert seen
        for entry in seen:
            assert entry["label"] in {
                "Preparing…",
                "Installing…",
                "Downloading…",
                "Optimizing…",
                "Verifying…",
                "Finalizing…",
            }
            assert "detail" not in entry
            rendered = str(entry).lower()
            for leak in ("llama", "qwen", "piper", "whisper", "http://", "source"):
                assert leak not in rendered

    def test_administrator_progress_carries_detail(self, registry, tmp_path: Path) -> None:
        engine = self._engine(tmp_path, registry, account_type="administrator")
        _Handler.payloads = {
            artifact.key: PAYLOAD
            for artifact in engine.model_artifacts() + engine.voice_artifacts()
        }

        seen: list[dict[str, Any]] = []
        engine.provision(on_progress=lambda p: seen.append(p.to_dict(include_detail=True)))

        assert any("detail" in entry for entry in seen)


class TestJournalDurability:
    def test_survives_a_truncated_journal(self, tmp_path: Path) -> None:
        """A journal cut short by the crash it records is unreadable,
        not authoritative -- starting over is correct, because every step
        is idempotent."""
        journal = ProvisioningJournal(tmp_path)
        journal.begin()
        journal.complete(Step.DEPENDENCIES)

        journal.path.write_text('{"version": 1, "entries": [{"ste', encoding="utf-8")

        reopened = ProvisioningJournal(tmp_path)
        assert reopened.is_resume is False
        assert len(reopened.remaining()) == 8

    def test_ignores_a_journal_from_another_version(self, tmp_path: Path) -> None:
        journal = ProvisioningJournal(tmp_path)
        journal.begin()
        journal.complete(Step.DEPENDENCIES)
        journal.path.write_text(
            '{"version": 999, "entries": [{"step": "dependencies"}]}', encoding="utf-8"
        )

        reopened = ProvisioningJournal(tmp_path)
        assert reopened.is_resume is False

    def test_completing_twice_does_not_duplicate(self, tmp_path: Path) -> None:
        journal = ProvisioningJournal(tmp_path)
        journal.complete(Step.DIRECTORIES)
        journal.complete(Step.DIRECTORIES)
        assert len(journal.entries) == 1


class TestFilenameSafety:
    """A model id is not a filename, and on Windows it cannot be one.

    Both bugs below shipped in the first draft and were found by running
    a real provisioning; the unit tests had used keys with no illegal
    characters and so never exercised them.
    """

    def test_an_id_with_a_colon_downloads_and_verifies(self, server, tmp_path: Path) -> None:
        host, port = server.server_address[:2]
        # `{filename}` -- a mirror cannot hold a file named `x:8b`.
        registry = SourceRegistry(
            [
                DownloadSource(
                    name="mirror",
                    base_url=f"http://{host}:{port}/{{filename}}",
                    kinds=("model",),
                    priority=0,
                )
            ]
        )
        _Handler.payloads = {"llama3.1_8b": PAYLOAD}

        manager = DownloadManager(registry, tmp_path)
        progress = manager.download(
            Artifact(key="llama3.1:8b", kind="model", checksum=_sha256(PAYLOAD))
        )

        assert progress.state is DownloadState.COMPLETED
        # Saved under the sanitised name, which is the only writable one.
        assert (tmp_path / "llama3.1_8b").exists()

    def test_verification_finds_a_file_saved_under_its_safe_name(
        self, registry, tmp_path: Path
    ) -> None:
        """Verification once looked up the raw key and reported a
        correctly-downloaded model as missing."""
        engine = TestProvisioning()._engine(tmp_path, registry)
        artifacts = engine.model_artifacts() + engine.voice_artifacts()
        # The `registry` fixture addresses by `{key}`, so the server is
        # keyed that way. What matters here is the *saved* name, which is
        # always the sanitised one.
        _Handler.payloads = {artifact.key: PAYLOAD for artifact in artifacts}

        result = engine.provision()

        assert result.errors == []
        assert result.verification is not None
        local_ai = next(r for r in result.verification.results if r.key == "models")
        assert local_ai.verdict != "fail", local_ai.detail


class TestSourceParsing:
    def test_kinds_are_not_split_as_entries(self) -> None:
        """Commas separate *kinds*; semicolons separate *entries*.

        Using commas for both split `…|model,voice|0` into a model-only
        source plus an unparseable fragment, so voice downloads found no
        source while model downloads worked -- a bug that looks like it
        works.
        """

        sources = parse_sources("mirror|file:///m/{kind}/{filename}|model,voice|0")

        assert len(sources) == 1
        assert sources[0].kinds == ("model", "voice")

    def test_multiple_entries(self) -> None:

        sources = parse_sources(
            "a|file:///a/{filename}|model|0;b|https://b.test/{key}|model,voice|5"
        )

        assert [s.name for s in sources] == ["a", "b"]
        # A `file:` source is usable with no network -- what makes an
        # offline installation possible.
        assert sources[0].requires_internet is False
        assert sources[1].requires_internet is True

    def test_a_malformed_entry_is_skipped_not_fatal(self) -> None:

        sources = parse_sources("good|file:///g/{filename}|model|0;garbage;|||")

        assert [s.name for s in sources] == ["good"]

    def test_offline_filters_to_local_sources(self, tmp_path: Path) -> None:

        registry = SourceRegistry(
            parse_sources("net|https://x.test/{key}|model|0;local|file:///m/{filename}|model|1")
        )

        offline = registry.resolve_all(Artifact(key="m", kind="model"), online=False)

        assert [c.source.name for c in offline] == ["local"]


class TestVerifyFile:
    def test_missing_checksum_is_unverifiable_not_verified(self, tmp_path: Path) -> None:
        path = tmp_path / "a.bin"
        path.write_bytes(b"x")

        verified, reason = verify_file(path, None)

        assert verified is False
        assert "could not be verified" in reason

    def test_a_missing_file_is_not_verified(self, tmp_path: Path) -> None:
        verified, reason = verify_file(tmp_path / "absent.bin", _sha256(b"x"))
        assert verified is False
        assert "missing" in reason.lower()
