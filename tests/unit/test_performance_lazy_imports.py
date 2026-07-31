"""Milestone 5.5, section 3 (performance): verifies workspace modules
are genuinely import-deferred, not just construction-deferred.

Measured finding: eagerly importing all 9 workspace modules at
``main_window`` import time cost ~358ms (``python -X importtime``),
~20% of that module's whole import chain -- even for a session that
never visits most of them. Root cause was two-layered: ``main_window.py``
imported them eagerly at module top, *and* (even after fixing that)
``ui/views/workspaces/__init__.py`` itself eagerly re-exported all 9,
which Python's import system forces to run before *any* dotted
sub-import of that package can resolve -- silently defeating the first
fix. Both are now lazy (PEP 562 module ``__getattr__`` for the
package, deferred ``importlib.import_module`` for the factories).

This runs in a **subprocess**, not sharing ``sys.modules`` with the
rest of the pytest run -- module-import assertions are inherently
fragile/order-dependent in a shared process where other test files may
have already imported workspace submodules directly. A subprocess
gives a clean, reliable answer immune to test ordering.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap

# pytest-cov auto-starts coverage in any subprocess that inherits these env
# vars (pytest_cov/embed.py's .pth hook). This test's subprocess changes
# `cwd` to `src/`, which breaks that hook's ability to resolve the repo's
# `pyproject.toml` coverage config from there, so it silently falls back to
# statement-only mode -- which then fails to combine with the parent run's
# branch-coverage data (`coverage.exceptions.DataError: Can't combine branch
# coverage data with statement data`), crashing the *entire* pytest session
# with an INTERNALERROR whenever `--cov` is passed. This subprocess only
# ever needs to be checked for its stdout, never for coverage of itself, so
# excluding it from coverage collection is fully behavior-preserving.
_NO_COVERAGE_ENV = {
    k: v
    for k, v in os.environ.items()
    if not k.startswith("COV_CORE_") and k != "COVERAGE_PROCESS_START"
}


def test_workspace_modules_not_imported_until_first_navigation() -> None:
    script = textwrap.dedent(
        """
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        import sys, tempfile, pathlib

        def loaded():
            return {
                name for name in sys.modules
                if name.startswith("jarvis.ui.views.workspaces.")
                and name != "jarvis.ui.views.workspaces"
            }

        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])

        from jarvis.core.config.settings import Settings
        from jarvis.core.di.container import Container
        from jarvis.ui.main_window import MainWindow

        class _Fake:
            def __getattr__(self, name):
                async def _noop(*a, **k):
                    return None
                return _noop

        settings = Settings(data_dir=pathlib.Path(tempfile.mkdtemp()))
        container = Container()
        container.settings.override(settings)
        for p in ("llm_provider", "memory_service", "voice_service",
                  "hotkey_service", "chat_service", "conversation_service"):
            getattr(container, p).override(_Fake())

        window = MainWindow(settings, container)
        assert loaded() == set(), f"eager at construction: {loaded()}"

        window._on_nav_selected("gmail")
        assert loaded() == {"jarvis.ui.views.workspaces.gmail_workspace"}, loaded()

        window._on_nav_selected("spotify")
        assert loaded() == {
            "jarvis.ui.views.workspaces.gmail_workspace",
            "jarvis.ui.views.workspaces.spotify_workspace",
        }, loaded()

        print("SUBPROCESS_OK")
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd="src" if __import__("pathlib").Path("src").is_dir() else None,
        env={**_NO_COVERAGE_ENV, "PYTHONPATH": "src"},
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert "SUBPROCESS_OK" in result.stdout, f"stdout:\n{result.stdout}\n\nstderr:\n{result.stderr}"
