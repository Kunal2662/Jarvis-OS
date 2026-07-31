"""Small filesystem helpers."""

from __future__ import annotations

from pathlib import Path


def ensure_parent(path: Path) -> Path:
    """Create the parent directory of *path* if missing; return *path*."""
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def human_bytes(n: int) -> str:
    """Return a human-readable size (``1536 → '1.5 KB'``)."""
    step = 1024.0
    units = ("B", "KB", "MB", "GB", "TB", "PB")
    size = float(n)
    for unit in units:
        if size < step:
            return f"{size:.1f} {unit}"
        size /= step
    return f"{size:.1f} EB"
