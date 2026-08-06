"""The provisioning journal -- M22 Task Group B.

An append-only record of what provisioning has completed, so an
interrupted installation can be resumed rather than restarted.

**Written durably, because the failure it exists to survive is a power
cut.** Each append writes a temporary file, flushes it, calls
``os.fsync`` and then atomically replaces the journal. A journal written
with a plain ``write()`` would sit in the OS page cache and be lost by
exactly the event it is meant to protect against — which would make it
worse than useless, since resume would trust a record that had silently
lost its last entries.

**Only completions are recorded.** A step that started and did not
finish leaves no entry, so resume re-runs it. That is the safe
direction: every provisioning step is written to be idempotent, so
re-running one is free, whereas skipping one that did not finish leaves
a broken installation that reports itself complete.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from jarvis.installer.atomic import write_json_atomically

JOURNAL_FILENAME = "provisioning.journal.json"

#: Bumped when the journal's shape changes. A journal from a different
#: version is discarded rather than misread -- resuming from a record
#: this build cannot interpret is worse than starting over.
JOURNAL_VERSION = 1


class Step(StrEnum):
    """The provisioning steps, in execution order.

    An enum rather than free strings so a typo in a resume check is a
    failure at import time instead of a step that silently never runs.
    """

    DEPENDENCIES = "dependencies"
    DIRECTORIES = "directories"
    CONFIGURATION = "configuration"
    MODEL_DOWNLOAD = "model_download"
    VOICE_DOWNLOAD = "voice_download"
    FIRST_RUN = "first_run"
    VERIFICATION = "verification"
    MANIFEST = "manifest"


STEP_ORDER: tuple[Step, ...] = (
    Step.DEPENDENCIES,
    Step.DIRECTORIES,
    Step.CONFIGURATION,
    Step.MODEL_DOWNLOAD,
    Step.VOICE_DOWNLOAD,
    Step.FIRST_RUN,
    Step.VERIFICATION,
    Step.MANIFEST,
)


@dataclass(frozen=True, slots=True)
class JournalEntry:
    step: str
    completed_at: str
    detail: str = ""
    data: dict[str, Any] | None = None


class ProvisioningJournal:
    """Resumable provisioning state on disk."""

    def __init__(self, directory: Path) -> None:
        self._path = directory / JOURNAL_FILENAME
        self._entries: list[JournalEntry] = []
        self._started_at: str | None = None
        self._load()

    @property
    def path(self) -> Path:
        return self._path

    @property
    def entries(self) -> tuple[JournalEntry, ...]:
        return tuple(self._entries)

    @property
    def started_at(self) -> str | None:
        return self._started_at

    @property
    def is_resume(self) -> bool:
        """Whether an earlier run got part-way. Drives the installer's
        "Resuming your installation" wording."""
        return bool(self._entries)

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            # A journal truncated by the very crash it records is
            # unreadable, not authoritative. Starting over is correct;
            # every step is idempotent.
            return

        if raw.get("version") != JOURNAL_VERSION:
            return

        self._started_at = raw.get("started_at")
        for item in raw.get("entries", []):
            if isinstance(item, dict) and "step" in item:
                self._entries.append(
                    JournalEntry(
                        step=str(item["step"]),
                        completed_at=str(item.get("completed_at", "")),
                        detail=str(item.get("detail", "")),
                        data=item.get("data"),
                    )
                )

    def _flush(self) -> None:
        """Atomic, fsynced write.

        `os.replace` is atomic on both POSIX and Windows, so a reader
        never observes a half-written journal — including a reader that
        is the next run after a crash mid-write.
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": JOURNAL_VERSION,
            "started_at": self._started_at,
            "entries": [asdict(entry) for entry in self._entries],
        }

        write_json_atomically(self._path, payload)

    def begin(self) -> None:
        """Record the start of a provisioning run, once."""
        if self._started_at is None:
            self._started_at = datetime.now(UTC).isoformat()
            self._flush()

    def is_complete(self, step: Step) -> bool:
        return any(entry.step == step.value for entry in self._entries)

    def complete(self, step: Step, *, detail: str = "", data: dict[str, Any] | None = None) -> None:
        """Record a finished step. Re-completing is a no-op, so a
        resumed run that redoes a step does not duplicate its entry."""
        if self.is_complete(step):
            return
        self._entries.append(
            JournalEntry(
                step=step.value,
                completed_at=datetime.now(UTC).isoformat(),
                detail=detail,
                data=data,
            )
        )
        self._flush()

    def remaining(self) -> tuple[Step, ...]:
        """Steps still to run, in order."""
        return tuple(step for step in STEP_ORDER if not self.is_complete(step))

    def invalidate(self, step: Step) -> None:
        """Forget a step so it runs again.

        The repair path: repairing the AI runtime forgets
        ``MODEL_DOWNLOAD`` and everything after it, because a step's
        result can depend on an earlier one. Forgetting a step in the
        middle while keeping later ones would leave the journal claiming
        a verification that ran against different inputs.
        """
        if step not in STEP_ORDER:
            return
        index = STEP_ORDER.index(step)
        invalid = {s.value for s in STEP_ORDER[index:]}
        self._entries = [entry for entry in self._entries if entry.step not in invalid]
        self._flush()

    def reset(self) -> None:
        self._entries = []
        self._started_at = None
        self._path.unlink(missing_ok=True)

    def to_dict(self) -> dict[str, Any]:
        return {
            "started_at": self._started_at,
            "is_resume": self.is_resume,
            "completed": [entry.step for entry in self._entries],
            "remaining": [step.value for step in self.remaining()],
        }
