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

import re
from pathlib import Path

from jarvis.__version__ import __version__

PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"

_VERSION_RE = re.compile(r'^version\s*=\s*"([^"]+)"', re.MULTILINE)


def _packaging_version() -> str:
    match = _VERSION_RE.search(PYPROJECT.read_text(encoding="utf-8"))
    assert match is not None, "pyproject.toml has no [project] version"
    return match.group(1)


def test_package_version_matches_pyproject() -> None:
    """Bump both, or neither."""
    assert __version__ == _packaging_version(), (
        f"jarvis.__version__ is {__version__!r} but pyproject.toml says "
        f"{_packaging_version()!r}. Both must be bumped together -- "
        "__version__ is what /api/v1/health and `jarvis --version` report."
    )


def test_version_is_semver() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__), f"{__version__!r} is not MAJOR.MINOR.PATCH"


def test_health_route_reports_the_package_version() -> None:
    """The route reads the constant rather than hardcoding a string."""
    from jarvis.infrastructure.api.routes import health

    source = Path(health.__file__).read_text(encoding="utf-8")
    assert "from jarvis.__version__ import __version__" in source
    assert '"version": __version__' in source
