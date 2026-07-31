"""Command-line and desktop entry-point.

Responsibilities:
    * Parse minimal CLI flags (``--headless``, ``--api-only``, ``--version``).
    * Delegate startup to :class:`jarvis.app.ApplicationBootstrapper`.
    * Ensure the process exits with a proper status code so tools like
      PyInstaller and Windows service wrappers behave correctly.

This module intentionally contains **no business logic** — everything lives
inside :mod:`jarvis.app`.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from jarvis.__version__ import __version__


def _build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jarvis",
        description="JARVIS OS — personal AI desktop assistant.",
    )
    parser.add_argument("--version", action="version", version=f"JARVIS OS {__version__}")
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run without launching the PySide6 UI (agents + FastAPI only).",
    )
    parser.add_argument(
        "--api-only",
        action="store_true",
        help="Start only the FastAPI control-plane server (no UI, no agents).",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to an alternate .env file (overrides the default lookup).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Application entry-point. Returns a POSIX exit code."""
    # Local import to keep ``--version`` / ``--help`` fast and side-effect-free.
    from jarvis.app import ApplicationBootstrapper, RunMode

    args = _build_argument_parser().parse_args(argv)

    mode = RunMode.GUI
    if args.api_only:
        mode = RunMode.API_ONLY
    elif args.headless:
        mode = RunMode.HEADLESS

    bootstrapper = ApplicationBootstrapper(env_file=args.config, mode=mode)
    return bootstrapper.run()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
