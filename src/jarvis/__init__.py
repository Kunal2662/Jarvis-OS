"""JARVIS OS — a local-first personal AI operating system for Windows 11.

Package layout follows a strict layered architecture:

    ui         → features → services → agents → core.interfaces
    infrastructure ─────────────────────────────→ core.interfaces

See :mod:`jarvis.core` for the abstractions every other layer depends on.
"""

from __future__ import annotations

from jarvis.__version__ import __version__

__all__ = ["__version__"]
