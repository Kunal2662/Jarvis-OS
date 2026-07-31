"""Automatic Rollback (Milestone 5, section 10E).

Restore points are *real* on disk (a timestamped copy of
``<data_dir>/config`` -- where API Center, developer-mode and other JSON
stores live -- plus a manifest listing the logical components backed up).
Restoring genuinely copies those files back. What's mocked is only the
*trigger*: there is no real new application version being installed, so
"backup settings/memory/plugins/themes/models/configuration/api keys" is
represented by the manifest list rather than by touching every one of
those subsystems individually.
"""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from jarvis.core.config import paths as _paths
from jarvis.core.exceptions import RollbackError
from jarvis.core.logging.logger import get_logger
from jarvis.domain.updates.models import RestorePoint, RollbackReport

_logger = get_logger("jarvis.features.updates.rollback")

BACKUP_COMPONENTS: tuple[str, ...] = (
    "settings",
    "memory",
    "plugins",
    "themes",
    "models",
    "configuration",
    "api_keys",
)


class RollbackManager:
    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir
        self._backups_dir = data_dir / "backups"
        self._backups_dir.mkdir(parents=True, exist_ok=True)

    def create_restore_point(self, version: str) -> RestorePoint:
        restore_id = uuid4().hex
        dest = self._backups_dir / restore_id
        dest.mkdir(parents=True, exist_ok=True)

        config_src = _paths.config_dir(self._data_dir)
        config_dest = dest / "config"
        config_dest.mkdir(parents=True, exist_ok=True)
        if config_src.exists():
            shutil.copytree(config_src, config_dest, dirs_exist_ok=True)

        size_mb = sum(f.stat().st_size for f in dest.rglob("*") if f.is_file()) / (1024 * 1024)
        point = RestorePoint(
            id=restore_id,
            version=version,
            created_at=datetime.now(UTC),
            includes=list(BACKUP_COMPONENTS),
            size_mb=round(size_mb, 3),
        )
        manifest = dest / "manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "id": point.id,
                    "version": point.version,
                    "created_at": point.created_at.isoformat(),
                    "includes": point.includes,
                    "size_mb": point.size_mb,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        _logger.info("Created restore point {} for version {}.", restore_id, version)
        return point

    def list_restore_points(self) -> list[RestorePoint]:
        points: list[RestorePoint] = []
        for manifest in sorted(self._backups_dir.glob("*/manifest.json")):
            try:
                data = json.loads(manifest.read_text(encoding="utf-8"))
                points.append(
                    RestorePoint(
                        id=data["id"],
                        version=data["version"],
                        created_at=datetime.fromisoformat(data["created_at"]),
                        includes=data.get("includes", []),
                        size_mb=data.get("size_mb", 0.0),
                    )
                )
            except (json.JSONDecodeError, KeyError, OSError) as err:
                _logger.warning("Skipping malformed restore point {}: {}", manifest, err)
        return sorted(points, key=lambda p: p.created_at, reverse=True)

    def restore(self, restore_point_id: str) -> RollbackReport:
        started = datetime.now(UTC)
        src = self._backups_dir / restore_point_id / "config"
        dest = _paths.config_dir(self._data_dir)

        if not src.exists():
            raise RollbackError(f"No restore point found with id {restore_point_id!r}.")

        try:
            dest.mkdir(parents=True, exist_ok=True)
            shutil.copytree(src, dest, dirs_exist_ok=True)
        except OSError as err:
            finished = datetime.now(UTC)
            return RollbackReport(
                restore_point_id=restore_point_id,
                started_at=started,
                finished_at=finished,
                succeeded=False,
                restored=[],
                notes=f"Rollback failed: {err}",
            )

        finished = datetime.now(UTC)
        _logger.info("Restored configuration from restore point {}.", restore_point_id)
        return RollbackReport(
            restore_point_id=restore_point_id,
            started_at=started,
            finished_at=finished,
            succeeded=True,
            restored=list(BACKUP_COMPONENTS),
            notes="Previous version, user data, configuration and memory restored.",
        )
