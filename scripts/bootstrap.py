#!/usr/bin/env python3
"""Bootstrap script — one-shot developer setup.

Usage::

    python scripts/bootstrap.py

Steps
-----
1. Ensure Python >= 3.13.
2. Create a `.env` from `.env.example` if missing.
3. Ensure the runtime data directories exist.
4. Install Playwright browsers (chromium).

The script is idempotent: running it twice is a no-op.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _check_python() -> None:
    if sys.version_info < (3, 13):
        sys.exit(f"Python 3.13+ is required, found {sys.version.split()[0]}")


def _copy_env() -> None:
    src, dst = REPO_ROOT / ".env.example", REPO_ROOT / ".env"
    if not dst.exists():
        shutil.copy(src, dst)
        print(f"[bootstrap] Created {dst.relative_to(REPO_ROOT)} from .env.example")


def _make_data_dirs() -> None:
    for sub in ("db", "vectorstore", "logs", "cache"):
        (REPO_ROOT / "data" / sub).mkdir(parents=True, exist_ok=True)
    print("[bootstrap] Runtime directories under ./data are ready.")


def _install_playwright() -> None:
    try:
        subprocess.check_call([sys.executable, "-m", "playwright", "install", "chromium"])
    except (subprocess.CalledProcessError, FileNotFoundError) as err:
        print(f"[bootstrap] Skipping Playwright install ({err}).")


def main() -> int:
    _check_python()
    _copy_env()
    _make_data_dirs()
    _install_playwright()
    print("[bootstrap] Done. Next: `python -m jarvis` or `jarvis`.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
