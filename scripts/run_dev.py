#!/usr/bin/env python3
"""Convenience launcher used during development."""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
os.chdir(REPO_ROOT)
sys.path.insert(0, str(REPO_ROOT / "src"))

from jarvis.main import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
