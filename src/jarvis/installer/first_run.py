"""First-run preparation -- M22 Task Group B.

Creates the directory tree and configuration JARVIS needs on its first
launch.

**It does not create the database schema, and that is deliberate.** The
schema is frozen and owned by `infrastructure/database/`; an installer
that wrote tables would be a second definition of it, guaranteed to
drift the first time a model changes. So this prepares the *location*
and records it in the configuration, and the application's own
`initialize()` creates the schema on first launch — the same code path
every other run uses.

Same reasoning for memory and knowledge storage: directories, not
contents.

**Every operation is idempotent.** Provisioning can be interrupted and
resumed, so running this twice must be indistinguishable from running it
once. Nothing here overwrites a file that already exists.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

#: The tree created under the installation root. Relative paths so the
#: whole installation stays movable -- and portable-mode friendly, which
#: a later task group needs.
DIRECTORIES: tuple[tuple[str, str], ...] = (
    ("data", "Application data"),
    ("data/memory", "Memory storage"),
    ("data/knowledge", "Knowledge database"),
    ("data/workspaces", "Workspaces"),
    ("data/files", "File storage"),
    ("models", "Local AI models"),
    ("voice", "Voice components"),
    ("logs", "Logs"),
    ("cache", "Cache"),
    ("config", "Configuration"),
)

CONFIG_FILENAME = "jarvis.config.json"


@dataclass(slots=True)
class FirstRunResult:
    root: Path
    created: list[str] = field(default_factory=list)
    existing: list[str] = field(default_factory=list)
    config_path: Path | None = None
    config_written: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": str(self.root),
            "created": list(self.created),
            "existing": list(self.existing),
            "config_path": str(self.config_path) if self.config_path else None,
            "config_written": self.config_written,
        }


def prepare_directories(root: Path) -> FirstRunResult:
    """Create the tree. Existing directories are left untouched."""
    result = FirstRunResult(root=root)
    for relative, _label in DIRECTORIES:
        path = root / relative
        if path.is_dir():
            result.existing.append(relative)
            continue
        path.mkdir(parents=True, exist_ok=True)
        result.created.append(relative)
    return result


def build_configuration(
    root: Path,
    *,
    performance_profile: str,
    cloud_usage: str,
    model_tier: str | None,
    account_type: str,
    resource_limits: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """The first-launch configuration document.

    Deliberately **not** a `.env` file and deliberately not written into
    the application's own settings tree: `JARVIS_*` environment
    variables and `SettingsService` are the frozen configuration
    surface, and an installer writing into it would be modifying frozen
    behaviour. This is the installer's own record of what it chose,
    which the application reads once on first launch.
    """
    document: dict[str, Any] = {
        "schema_version": 1,
        "installation_root": str(root),
        "paths": {
            "data": str(root / "data"),
            "memory": str(root / "data" / "memory"),
            "knowledge": str(root / "data" / "knowledge"),
            "workspaces": str(root / "data" / "workspaces"),
            "files": str(root / "data" / "files"),
            "models": str(root / "models"),
            "voice": str(root / "voice"),
            "logs": str(root / "logs"),
            "cache": str(root / "cache"),
            # The file the application will create and migrate itself.
            # The installer names the location and stops there.
            "database": str(root / "data" / "jarvis.db"),
        },
        "profile": {
            "performance": performance_profile,
            "cloud_usage": cloud_usage,
            "account_type": account_type,
        },
        "local_ai": {"tier": model_tier},
        "voice": {"identity": "JARVIS"},
        "first_run_completed": False,
    }

    # Resource limits are administrator-facing technical configuration
    # (§22.11), so a personal installation simply does not carry them.
    if resource_limits and account_type == "administrator":
        document["profile"]["resource_limits"] = resource_limits

    return document


def write_configuration(root: Path, document: dict[str, Any]) -> tuple[Path, bool]:
    """Write the configuration if absent.

    Returns ``(path, written)``. An existing configuration is **never**
    overwritten: on a resumed or repaired installation it may carry
    choices a user has since changed, and silently replacing it is
    exactly the "never silently overwrite" the brief forbids.
    """
    config_dir = root / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    path = config_dir / CONFIG_FILENAME

    if path.exists():
        return path, False

    path.write_text(json.dumps(document, indent=2), encoding="utf-8")
    return path, True


def prepare_first_run(
    root: Path,
    *,
    performance_profile: str,
    cloud_usage: str,
    model_tier: str | None,
    account_type: str,
    resource_limits: dict[str, Any] | None = None,
) -> FirstRunResult:
    """Directories plus configuration, idempotently."""
    result = prepare_directories(root)
    document = build_configuration(
        root,
        performance_profile=performance_profile,
        cloud_usage=cloud_usage,
        model_tier=model_tier,
        account_type=account_type,
        resource_limits=resource_limits,
    )
    path, written = write_configuration(root, document)
    result.config_path = path
    result.config_written = written
    return result
