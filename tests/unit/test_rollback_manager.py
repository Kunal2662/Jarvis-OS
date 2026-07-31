"""Unit tests for :class:`RollbackManager` -- Milestone 5, section 10E."""

from __future__ import annotations

import json
from pathlib import Path

from jarvis.features.updates.rollback_manager import BACKUP_COMPONENTS, RollbackManager


def test_create_restore_point_writes_manifest(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "api_center.json").write_text('{"apis": []}', encoding="utf-8")

    manager = RollbackManager(tmp_path)
    point = manager.create_restore_point("1.0.0")

    assert point.version == "1.0.0"
    assert list(point.includes) == list(BACKUP_COMPONENTS)

    manifest_path = tmp_path / "backups" / point.id / "manifest.json"
    assert manifest_path.exists()
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert data["version"] == "1.0.0"


def test_list_restore_points_newest_first(tmp_path: Path) -> None:
    manager = RollbackManager(tmp_path)
    first = manager.create_restore_point("1.0.0")
    second = manager.create_restore_point("1.1.0")

    points = manager.list_restore_points()
    assert points[0].id == second.id
    assert points[1].id == first.id


def test_restore_copies_config_back(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "api_center.json").write_text('{"apis": ["original"]}', encoding="utf-8")

    manager = RollbackManager(tmp_path)
    point = manager.create_restore_point("1.0.0")

    # Simulate the "update" corrupting/changing the config.
    (config_dir / "api_center.json").write_text('{"apis": ["corrupted"]}', encoding="utf-8")

    report = manager.restore(point.id)

    assert report.succeeded is True
    assert set(report.restored) == set(BACKUP_COMPONENTS)
    restored_content = (config_dir / "api_center.json").read_text(encoding="utf-8")
    assert "original" in restored_content


def test_restore_missing_point_reports_failure() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        manager = RollbackManager(Path(tmp))
        import pytest

        from jarvis.core.exceptions import RollbackError

        with pytest.raises(RollbackError):
            manager.restore("does-not-exist")
