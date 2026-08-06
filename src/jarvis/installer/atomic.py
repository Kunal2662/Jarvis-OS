"""Atomic, durable JSON writes -- M22 Task Group B.

Shared by the journal and the manifest because both must survive the
event they exist to record: a power cut. A plain ``write()`` leaves the
bytes in the OS page cache, so the file that describes what happened is
exactly the file most likely to be lost by it.

``os.replace`` is atomic on POSIX and Windows alike, so a reader -- which
after a crash is the *next run* -- never observes a half-written file.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def write_json_atomically(path: Path, payload: dict[str, Any]) -> None:
    """Write *payload* to *path*, or leave the previous contents intact."""
    path.parent.mkdir(parents=True, exist_ok=True)

    descriptor, temporary = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}-", suffix=".tmp"
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
