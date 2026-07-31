"""Tests for ``jarvis.core.config.settings.load_settings`` crash
recovery (Release Candidate 1, section 6).

Reproduces a realistic power-loss scenario: a ``.env`` file left
truncated/binary-corrupted mid-write. Before this fix, this crashed
startup with an uncaught ``UnicodeDecodeError`` before a single log
line could be written.
"""

from __future__ import annotations

from pathlib import Path

from jarvis.core.config.settings import load_settings


def test_load_settings_survives_binary_corrupted_env_file(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_bytes(b"\x00\x01\xff\xfe garbage binary data \x00\x00")

    settings = load_settings(env_file=env_file)  # must not raise

    # Falls back to defaults rather than crashing or half-loading.
    assert settings.app_name == "JARVIS OS"


def test_load_settings_survives_truncated_env_file(tmp_path: Path) -> None:
    """A less severe corruption: a value cut off mid-write (power loss
    partway through an fsync) rather than pure binary garbage."""
    env_file = tmp_path / ".env"
    env_file.write_text("JARVIS_UI_THEME=jarvis\nJARVIS_LLM_DEFAULT_PROVID")

    settings = load_settings(env_file=env_file)  # must not raise
    assert settings is not None


def test_load_settings_still_works_normally_with_valid_env_file(tmp_path: Path) -> None:
    """Regression guard: the try/except fallback must not mask normal,
    successful .env loading."""
    env_file = tmp_path / ".env"
    env_file.write_text("JARVIS_DEBUG=true\n")

    settings = load_settings(env_file=env_file)

    assert settings.debug is True


def test_load_settings_with_nonexistent_env_file_uses_defaults(tmp_path: Path) -> None:
    """A missing file (fresh install, no config written yet) is not an
    error case at all -- distinct from a corrupted one."""
    missing = tmp_path / "does-not-exist.env"

    settings = load_settings(env_file=missing)  # must not raise
    assert settings.app_name == "JARVIS OS"
