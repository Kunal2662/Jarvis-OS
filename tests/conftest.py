"""Shared pytest fixtures.

Populated in Milestone 1. Kept minimal here to keep the test session clean.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make the src-layout importable when running ``pytest`` from the repo root
# without a prior ``pip install -e .``.
_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
