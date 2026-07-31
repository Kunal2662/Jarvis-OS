#!/usr/bin/env python3
"""Root entry-point that delegates to :mod:`jarvis.main`.

Enables ``python main.py`` from the repo root without installing the
package first.
"""
from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent / "src"
if _SRC.exists() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from jarvis.main import main

if __name__ == "__main__":
    raise SystemExit(main())
