#!/usr/bin/env python3
"""Build a Windows executable via PyInstaller.

Run on a **Windows 11** host with:

    python scripts/build_windows.py

Produces ``dist/JarvisOS/JarvisOS.exe`` and a matching ``build/`` folder.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    if not sys.platform.startswith("win"):
        print("[build] Skipping — Windows-only build script.")
        return 0

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", "JarvisOS",
        "--noconfirm", "--clean", "--windowed",
        "--icon", str(REPO_ROOT / "resources" / "icons" / "app.ico"),
        "--add-data", f"{REPO_ROOT / 'resources'};resources",
        "--paths", str(REPO_ROOT / "src"),
        str(REPO_ROOT / "src" / "jarvis" / "main.py"),
    ]
    print("[build]", " ".join(cmd))
    return subprocess.call(cmd, cwd=REPO_ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
