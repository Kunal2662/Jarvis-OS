"""The installation manifest -- M22 Task Group B.

Writes ``installation.json``: what was installed, onto what hardware,
with which profile, and whether it verified.

**This is the migration contract.** The brief says future migrations
should consume it, which makes its shape a compatibility surface rather
than a log file. Two consequences run through the module:

* ``manifest_version`` is explicit and separate from the installer
  version, so a future reader can tell "written by an older installer"
  from "written in an older format".
* The manifest records **measurements, not conclusions** — the capability
  score alongside the inputs that produced it. A migration that only
  knew the score could not tell an 8 GB machine that scored 40 from a
  32 GB machine that scored 40 on battery.

Written with the same atomic, fsynced discipline as the journal: a
manifest lost to a power cut would leave an installation that works but
cannot be migrated.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jarvis.__version__ import __version__
from jarvis.installer.atomic import write_json_atomically

MANIFEST_FILENAME = "installation.json"

#: The manifest's own schema version. Bumped when the shape changes,
#: independently of the application version.
MANIFEST_VERSION = 1


def build_manifest(
    *,
    root: Path,
    hardware: dict[str, Any],
    calibration: dict[str, Any],
    account_type: str,
    installed_components: list[dict[str, Any]],
    installed_models: list[dict[str, Any]],
    voice_configuration: dict[str, Any],
    verification: dict[str, Any],
    dependencies: dict[str, Any],
) -> dict[str, Any]:
    """Assemble the manifest document.

    Note what is *not* filtered here. Unlike every user-facing payload in
    this package, the manifest always carries full detail — model ids,
    dependency paths, the score breakdown — because its reader is a
    future migration, not a person. §22.11/§22.12 govern what a *user*
    sees; a file on disk that only the software reads is a different
    audience. The installer never displays this document.
    """
    platform = hardware.get("platform", {})
    cpu = hardware.get("cpu", {})
    memory = hardware.get("memory", {})
    storage = hardware.get("storage", {})
    gpus = hardware.get("gpus", [])

    return {
        "manifest_version": MANIFEST_VERSION,
        "installer_version": __version__,
        "installed_at": datetime.now(UTC).isoformat(),
        "installation_root": str(root),
        "account_type": account_type,
        "platform": {
            "system": platform.get("system"),
            "release": platform.get("release"),
            "machine": platform.get("machine"),
            "python": platform.get("python"),
        },
        "hardware": {
            "cpu": {
                "model": cpu.get("model"),
                "physical_cores": cpu.get("physical_cores"),
                "architecture": cpu.get("architecture"),
            },
            "gpu": [{"name": gpu.get("name"), "vram_bytes": gpu.get("vram_bytes")} for gpu in gpus],
            "ram_bytes": memory.get("total_bytes"),
            "storage": {
                "path": storage.get("path"),
                "total_bytes": storage.get("total_bytes"),
                "free_bytes_at_install": storage.get("free_bytes"),
            },
            "npu": hardware.get("npu"),
        },
        "calibration": {
            "capability_score": calibration.get("score"),
            "performance_profile": calibration.get("performance_profile"),
            "cloud_usage": calibration.get("cloud_usage"),
            # The inputs, not just the verdict -- a migration needs to
            # know *why* a profile was chosen to decide whether it still
            # applies.
            "components": calibration.get("components"),
            "inputs": calibration.get("inputs"),
            "missing_inputs": calibration.get("missing_inputs", []),
        },
        "dependencies": dependencies,
        "installed_components": installed_components,
        "installed_models": installed_models,
        "voice": voice_configuration,
        "verification": verification,
    }


def write_manifest(root: Path, document: dict[str, Any]) -> Path:
    """Atomically write ``installation.json``.

    Overwrites deliberately, unlike the configuration: the manifest
    describes the *current* state of the installation, so a repair that
    re-verified components must replace it. Configuration carries user
    choices; a manifest carries facts, and stale facts are worse than
    none.
    """
    path = root / MANIFEST_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)

    write_json_atomically(path, document)

    return path


def read_manifest(root: Path) -> dict[str, Any] | None:
    """Read an existing manifest, or ``None``.

    Unreadable is treated as absent: a corrupt manifest cannot be
    trusted to describe the installation, and verification already
    reports a missing one as a warning rather than a failure.
    """
    path = root / MANIFEST_FILENAME
    if not path.exists():
        return None
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return document if isinstance(document, dict) else None
