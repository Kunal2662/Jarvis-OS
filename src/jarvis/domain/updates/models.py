"""Update Center domain models -- pure data, no I/O (mock services only)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from uuid import uuid4


def _uuid() -> str:
    return uuid4().hex


def _utcnow() -> datetime:
    return datetime.now(UTC)


class UpdateChannel(str, Enum):
    STABLE = "stable"
    BETA = "beta"
    DEVELOPER = "developer"
    NIGHTLY = "nightly"


class UpdatePhase(str, Enum):
    CHECKING = "checking_updates"
    DOWNLOADING = "downloading"
    INSTALLING = "installing"
    VERIFYING = "verifying"
    OPTIMIZING = "optimizing"
    RESTART_REQUIRED = "restart_required"
    ROLLBACK_STARTED = "rollback_started"
    ROLLBACK_COMPLETED = "rollback_completed"
    COMPLETED = "update_completed"
    FAILED = "failed"
    IDLE = "idle"


class UpdatePhaseStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class ReleaseNote:
    version: str
    channel: UpdateChannel
    released_at: datetime
    highlights: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class RestorePoint:
    """Snapshot taken automatically before every update (Milestone 5.10E)."""

    id: str
    version: str
    created_at: datetime
    includes: list[str] = field(default_factory=list)  # e.g. ["settings", "memory", ...]
    size_mb: float = 0.0


@dataclass(frozen=True, slots=True)
class RollbackReport:
    restore_point_id: str
    started_at: datetime
    finished_at: datetime
    succeeded: bool
    restored: list[str] = field(default_factory=list)
    notes: str = ""


@dataclass(slots=True)
class UpdateSession:
    """One run of the (mock) update pipeline, start to finish."""

    id: str = field(default_factory=_uuid)
    channel: UpdateChannel = UpdateChannel.STABLE
    from_version: str = ""
    to_version: str = ""
    phase: UpdatePhase = UpdatePhase.IDLE
    progress_percent: int = 0
    started_at: datetime = field(default_factory=_utcnow)
    finished_at: datetime | None = None
    succeeded: bool | None = None
    restore_point_id: str | None = None
    rollback_report: RollbackReport | None = None
    logs: list[str] = field(default_factory=list)
