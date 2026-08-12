"""The package version and the packaging metadata never diverge.

M8 Phase 7 found them three releases apart: ``pyproject.toml`` said
0.31.0 while ``jarvis/__version__.py`` -- whose own docstring calls
itself "single source of truth for the package version" -- still said
0.28.0. Nothing caught it, because nothing compared them.

That drift is not cosmetic. ``__version__`` is what
``GET /api/v1/health`` returns, what ``jarvis --version`` prints, and
what a support conversation starts from; ``pyproject.toml`` is what a
built wheel is stamped with. An installation reporting a version three
releases behind the artifact it was built from is a real diagnostic
hazard.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from jarvis.__version__ import __version__

_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = _ROOT / "pyproject.toml"
TAURI_CONF = _ROOT / "frontend" / "src-tauri" / "tauri.conf.json"

_VERSION_RE = re.compile(r'^version\s*=\s*"([^"]+)"', re.MULTILINE)


def _packaging_version() -> str:
    match = _VERSION_RE.search(PYPROJECT.read_text(encoding="utf-8"))
    assert match is not None, "pyproject.toml has no [project] version"
    return match.group(1)


def _desktop_version() -> str:
    return str(json.loads(TAURI_CONF.read_text(encoding="utf-8"))["version"])


def test_package_version_matches_pyproject() -> None:
    """Bump both, or neither."""
    assert __version__ == _packaging_version(), (
        f"jarvis.__version__ is {__version__!r} but pyproject.toml says "
        f"{_packaging_version()!r}. Both must be bumped together -- "
        "__version__ is what /api/v1/health and `jarvis --version` report."
    )


def test_desktop_bundle_matches_the_package_version() -> None:
    """The Windows installer is stamped from ``tauri.conf.json``.

    Added by M22 Task Group C, the milestone that first produces a
    packaged artifact. Until then this file's version was cosmetic;
    now it is what the NSIS installer, the Add/Remove Programs entry
    and the executable's file properties report -- while
    ``/api/v1/health`` reports ``__version__``. Two numbers, two places
    a user reads a version, and nothing compared them: exactly the
    drift this module was written for, one file wider.
    """
    assert _desktop_version() == __version__, (
        f"tauri.conf.json says {_desktop_version()!r} but jarvis.__version__ is "
        f"{__version__!r}. The installer would report a different version than "
        "the running application."
    )


def test_version_is_semver() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__), f"{__version__!r} is not MAJOR.MINOR.PATCH"


def test_health_route_reports_the_package_version() -> None:
    """The route reads the constant rather than hardcoding a string."""
    from jarvis.infrastructure.api.routes import health

    source = Path(health.__file__).read_text(encoding="utf-8")
    assert "from jarvis.__version__ import __version__" in source
    assert '"version": __version__' in source
