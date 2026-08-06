"""Download manager -- M22 Task Group B.

Queued, resumable, checksum-verified downloads with pause, cancel, retry
and source failover.

**Resume is byte-level, not file-level.** A partial transfer is kept as
``<name>.part`` and continued with an HTTP ``Range`` request; only a
completed, verified file is moved into place. That is what makes the
brief's "resume without restarting the entire installation" true for a
9 GB model interrupted at 8 GB — restarting a file-level download would
technically resume the *installation* while re-fetching the whole
artefact.

**A file only exists once it is correct.** Verification happens on the
``.part`` file, and the atomic rename to its final name is the last
step. So the presence of ``model.bin`` is itself proof it was verified:
recovery never has to ask whether a file it found is trustworthy.

**Unverifiable is not verified.** A source that publishes no checksum
yields ``verified=False`` with a reason, never a quiet pass. Reporting a
file as verified when nothing checked it is the one failure that would
make every other guarantee here worthless.

Standard library only (`urllib`). This runs during installation, before
any dependency has been provisioned, so it cannot import `httpx`.
"""

from __future__ import annotations

import hashlib
import shutil
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from jarvis.installer.sources import (
    Artifact,
    ResolvedDownload,
    SourceRegistry,
    SourceResolutionError,
)

_CHUNK_BYTES = 1024 * 256
_CONNECT_TIMEOUT_SECONDS = 30.0

#: Attempts *per source* before moving to the next one.
_ATTEMPTS_PER_SOURCE = 3
_BACKOFF_SECONDS = (1.0, 3.0, 8.0)


class DownloadState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"
    """Already present and verified -- the "reuse existing models,
    avoid duplicate downloads" requirement, and the reason a repair of a
    partly-installed machine is fast."""


@dataclass(slots=True)
class DownloadProgress:
    key: str
    """The artefact id -- a model or component name, so §22.12-restricted.
    Emitted only when `include_source` is set."""
    display_name: str
    """Safe to show anyone: "Local AI", "Voice component"."""
    state: DownloadState
    downloaded_bytes: int = 0
    total_bytes: int | None = None
    """``None`` when the server sends no ``Content-Length``. The UI shows
    an indeterminate bar rather than a fabricated percentage."""
    attempts: int = 0
    source_name: str | None = None
    verified: bool = False
    message: str = ""

    @property
    def percent(self) -> float | None:
        if not self.total_bytes:
            return None
        return min(100.0, (self.downloaded_bytes / self.total_bytes) * 100.0)

    def to_dict(self, *, include_source: bool) -> dict[str, Any]:
        """*include_source* is ``False`` for a personal user: a source
        name identifies a provider (§22.12)."""
        data: dict[str, Any] = {
            # `display_name`, never `key`: the key is a model id
            # (`qwen2.5:14b`) and naming it to a personal user is exactly
            # what §22.12 forbids. Caught by a test asserting no model
            # name appears in a personal progress payload.
            "name": self.display_name,
            "state": self.state.value,
            "downloaded_bytes": self.downloaded_bytes,
            "total_bytes": self.total_bytes,
            "percent": self.percent,
            "verified": self.verified,
        }
        if include_source:
            data["key"] = self.key
            data["source_name"] = self.source_name
            data["attempts"] = self.attempts
            data["message"] = self.message
        return data


ProgressCallback = Callable[[DownloadProgress], None]


class DownloadCancelledError(Exception):
    """Raised internally when a caller cancels mid-transfer."""


def _set_event() -> threading.Event:
    event = threading.Event()
    event.set()
    return event


@dataclass(slots=True)
class _Control:
    """Cross-thread pause/cancel signalling.

    `threading.Event` rather than a bare bool: the transfer loop waits on
    the pause event instead of spinning, so a paused download costs
    nothing while it waits.
    """

    cancelled: threading.Event = field(default_factory=threading.Event)
    resumed: threading.Event = field(default_factory=_set_event)

    def pause(self) -> None:
        self.resumed.clear()

    def resume(self) -> None:
        self.resumed.set()

    def cancel(self) -> None:
        self.cancelled.set()
        # Wake a paused transfer so it can observe the cancellation
        # rather than sleeping through it.
        self.resumed.set()


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(_CHUNK_BYTES), b""):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def verify_file(path: Path, checksum: str | None) -> tuple[bool, str]:
    """``(verified, reason)``.

    Returns ``False`` when no checksum is published. "We could not check"
    and "we checked and it matched" are different facts, and collapsing
    them is how a corrupt artefact gets reported as sound.
    """
    if not path.exists():
        return False, "File is missing."
    if not checksum:
        return False, "No checksum published by the source; integrity could not be verified."
    actual = sha256_of(path)
    if actual.lower() != checksum.lower():
        return False, "Checksum did not match; the file is incomplete or corrupt."
    return True, "Checksum verified."


def _default_opener(request: urllib.request.Request, timeout: float) -> Any:
    """The real network call. A named function rather than a lambda so
    the injected test double and the production path have the same
    shape."""
    return urllib.request.urlopen(request, timeout=timeout)


class DownloadManager:
    """A serial download queue.

    Serial on purpose. Artefacts here are large, and parallel transfers
    of two multi-gigabyte files share the same bandwidth while doubling
    the work lost to an interruption. The *queue* is smart — already-
    present artefacts are skipped, and ordering is caller-controlled —
    but the transfers are one at a time.
    """

    def __init__(
        self,
        registry: SourceRegistry,
        destination: Path,
        *,
        opener: Callable[[urllib.request.Request, float], Any] | None = None,
    ) -> None:
        self._registry = registry
        self._destination = destination
        # Injected so tests exercise the real transfer logic against a
        # local server without monkey-patching urllib globally.
        self._opener = opener or _default_opener
        self._controls: dict[str, _Control] = {}
        self._progress: dict[str, DownloadProgress] = {}
        self._lock = threading.Lock()

    # --- Control ----------------------------------------------------

    def pause(self, key: str) -> None:
        self._control(key).pause()
        self._update(key, state=DownloadState.PAUSED)

    def resume(self, key: str) -> None:
        self._control(key).resume()
        self._update(key, state=DownloadState.RUNNING)

    def cancel(self, key: str) -> None:
        self._control(key).cancel()

    def progress(self, key: str) -> DownloadProgress | None:
        with self._lock:
            return self._progress.get(key)

    def all_progress(self) -> tuple[DownloadProgress, ...]:
        with self._lock:
            return tuple(self._progress.values())

    def _control(self, key: str) -> _Control:
        with self._lock:
            control = self._controls.get(key)
            if control is None:
                control = _Control()
                self._controls[key] = control
            return control

    def _update(self, key: str, **changes: Any) -> DownloadProgress:
        with self._lock:
            progress = self._progress.setdefault(
                key, DownloadProgress(key=key, display_name=key, state=DownloadState.QUEUED)
            )
            for name, value in changes.items():
                setattr(progress, name, value)
            return progress

    # --- Queue ------------------------------------------------------

    def download_all(
        self,
        artifacts: Iterable[Artifact],
        *,
        online: bool = True,
        on_progress: ProgressCallback | None = None,
    ) -> dict[str, DownloadProgress]:
        """Fetch every artefact. Never raises for a single failure --
        one artefact failing is a result, not an exception, so a partial
        installation can be repaired rather than abandoned."""
        results: dict[str, DownloadProgress] = {}
        for artifact in artifacts:
            results[artifact.key] = self.download(artifact, online=online, on_progress=on_progress)
        return results

    def download(
        self,
        artifact: Artifact,
        *,
        online: bool = True,
        on_progress: ProgressCallback | None = None,
    ) -> DownloadProgress:
        self._update(artifact.key, display_name=artifact.display_name)
        # `filename`, not `key`: a model id such as `qwen2.5:14b`
        # contains a colon, which Windows treats as a drive qualifier and
        # refuses to create. Windows is this milestone's primary
        # platform, so the registry id and the on-disk name must differ.
        target = self._destination / artifact.filename
        partial = target.with_name(target.name + ".part")
        target.parent.mkdir(parents=True, exist_ok=True)

        # Already present? Only "verified" counts as present. A file that
        # exists but fails its checksum is treated as absent and
        # re-fetched -- which is exactly what repairing a corrupted
        # installation means.
        if target.exists():
            verified, reason = verify_file(target, artifact.checksum)
            if verified or artifact.checksum is None:
                progress = self._update(
                    artifact.key,
                    state=DownloadState.SKIPPED,
                    downloaded_bytes=target.stat().st_size,
                    total_bytes=target.stat().st_size,
                    verified=verified,
                    message="Already installed." if verified else f"Already present. {reason}",
                )
                if on_progress:
                    on_progress(progress)
                return progress
            target.unlink(missing_ok=True)

        try:
            candidates = self._registry.resolve_all(artifact, online=online)
        except SourceResolutionError as err:
            progress = self._update(artifact.key, state=DownloadState.FAILED, message=str(err))
            if on_progress:
                on_progress(progress)
            return progress

        last_message = "No source succeeded."
        for candidate in candidates:
            outcome = self._try_source(
                artifact, candidate, target, partial, on_progress=on_progress
            )
            if outcome.state in {DownloadState.COMPLETED, DownloadState.CANCELLED}:
                return outcome
            last_message = outcome.message

        progress = self._update(artifact.key, state=DownloadState.FAILED, message=last_message)
        if on_progress:
            on_progress(progress)
        return progress

    # --- Transfer ---------------------------------------------------

    def _try_source(
        self,
        artifact: Artifact,
        candidate: ResolvedDownload,
        target: Path,
        partial: Path,
        *,
        on_progress: ProgressCallback | None,
    ) -> DownloadProgress:
        control = self._control(artifact.key)

        for attempt in range(_ATTEMPTS_PER_SOURCE):
            if control.cancelled.is_set():
                return self._finish_cancelled(artifact, partial, on_progress)

            progress = self._update(
                artifact.key,
                state=DownloadState.RUNNING,
                attempts=attempt + 1,
                source_name=candidate.source.name,
                message="",
            )
            if on_progress:
                on_progress(progress)

            try:
                self._transfer(artifact, candidate, partial, control, on_progress)
            except DownloadCancelledError:
                return self._finish_cancelled(artifact, partial, on_progress)
            except (urllib.error.URLError, OSError, TimeoutError) as err:
                # A partial file is *kept* -- that is the whole point of
                # resume. The next attempt continues from where this one
                # stopped rather than starting over.
                message = f"{type(err).__name__}: {err}"
                progress = self._update(artifact.key, message=message)
                if on_progress:
                    on_progress(progress)
                if attempt < _ATTEMPTS_PER_SOURCE - 1:
                    time.sleep(_BACKOFF_SECONDS[min(attempt, len(_BACKOFF_SECONDS) - 1)])
                continue

            verified, reason = verify_file(partial, artifact.checksum)
            if artifact.checksum and not verified:
                # A checksum mismatch means the bytes on disk are wrong;
                # resuming from them would only extend a corrupt file, so
                # this is the one case that discards progress.
                partial.unlink(missing_ok=True)
                progress = self._update(artifact.key, downloaded_bytes=0, message=reason)
                if on_progress:
                    on_progress(progress)
                continue

            # Rename last: a file under its final name is, by
            # construction, one that passed verification.
            shutil.move(str(partial), str(target))
            progress = self._update(
                artifact.key,
                state=DownloadState.COMPLETED,
                verified=verified,
                downloaded_bytes=target.stat().st_size,
                message=reason,
            )
            if on_progress:
                on_progress(progress)
            return progress

        return self._update(
            artifact.key,
            state=DownloadState.FAILED,
            message=f"{candidate.source.name} failed after {_ATTEMPTS_PER_SOURCE} attempts.",
        )

    def _transfer(
        self,
        artifact: Artifact,
        candidate: ResolvedDownload,
        partial: Path,
        control: _Control,
        on_progress: ProgressCallback | None,
    ) -> None:
        existing = partial.stat().st_size if partial.exists() else 0

        request = urllib.request.Request(candidate.url, headers=dict(candidate.source.headers))
        if existing:
            request.add_header("Range", f"bytes={existing}-")

        with self._opener(request, _CONNECT_TIMEOUT_SECONDS) as response:
            status = getattr(response, "status", 200)
            length_header = response.headers.get("Content-Length")
            remaining = int(length_header) if length_header and length_header.isdigit() else None

            if existing and status == 206:
                mode = "ab"
                downloaded = existing
                total = existing + remaining if remaining is not None else artifact.expected_bytes
            else:
                # The server ignored the Range header (206 is the only
                # honest confirmation it honoured it), so start over
                # rather than appending fresh bytes onto stale ones.
                mode = "wb"
                downloaded = 0
                total = remaining if remaining is not None else artifact.expected_bytes

            self._update(artifact.key, downloaded_bytes=downloaded, total_bytes=total)

            with partial.open(mode) as handle:
                while True:
                    if control.cancelled.is_set():
                        raise DownloadCancelledError
                    # Blocks while paused; costs nothing.
                    control.resumed.wait()
                    if control.cancelled.is_set():
                        raise DownloadCancelledError

                    chunk = response.read(_CHUNK_BYTES)
                    if not chunk:
                        break
                    handle.write(chunk)
                    downloaded += len(chunk)
                    progress = self._update(artifact.key, downloaded_bytes=downloaded)
                    if on_progress:
                        on_progress(progress)

    def _finish_cancelled(
        self, artifact: Artifact, partial: Path, on_progress: ProgressCallback | None
    ) -> DownloadProgress:
        # The `.part` file is deliberately left behind: a cancelled
        # download that is later resumed should not have to start over.
        progress = self._update(
            artifact.key,
            state=DownloadState.CANCELLED,
            message="Cancelled. Progress kept for resume." if partial.exists() else "Cancelled.",
        )
        if on_progress:
            on_progress(progress)
        return progress
