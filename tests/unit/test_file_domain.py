"""File Platform domain tests -- Milestone 11 Task Group C.

``domain/files/models.py`` is pure -- no database, no service, no
container -- so it is tested that way. The two functions here are the
ones the platform's safety rests on, and they are worth pinning
directly rather than only through the services that call them.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.domain.files.models import (
    DEFAULT_MIME_TYPE,
    INDEX_STATUSES,
    MAX_EXTRACT_BYTES,
    TEXT_EXTRACTABLE_EXTENSIONS,
    FilePathError,
    extension_of,
    extract_text,
    guess_mime_type,
    safe_join,
    validate_name,
)

# --- validate_name --------------------------------------------------------------


@pytest.mark.parametrize("name", ["notes.md", "My Report (final).txt", "2026-08-05", "a.b.c"])
def test_ordinary_names_are_accepted(name: str) -> None:
    assert validate_name(name) == name


def test_surrounding_whitespace_is_stripped_not_rejected(name: str = "  notes.md  ") -> None:
    assert validate_name(name) == "notes.md"


@pytest.mark.parametrize(
    "name",
    [
        "",
        "   ",
        ".",
        "..",
        "../etc",
        "a/b",
        "a\\b",
        "a:b",
        "a*b",
        "a?b",
        'a"b',
        "a<b",
        "a>b",
        "a|b",
        "a\0b",
    ],
)
def test_every_traversal_and_illegal_fragment_is_rejected(name: str) -> None:
    with pytest.raises(FilePathError):
        validate_name(name)


@pytest.mark.parametrize("name", ["con", "CON.txt", "nul", "com1.log", "LPT9"])
def test_windows_device_names_are_rejected_on_every_platform(name: str) -> None:
    """A file called ``con.txt`` is unopenable on Windows, so it is
    refused everywhere rather than producing a catalogue that only
    breaks on one platform."""
    with pytest.raises(FilePathError, match="reserved device name"):
        validate_name(name)


def test_the_error_message_names_what_was_wrong(tmp_path: Path) -> None:
    with pytest.raises(FilePathError, match="folder name"):
        validate_name("../x", label="folder name")


# --- safe_join ------------------------------------------------------------------


def test_safe_join_builds_a_contained_path(tmp_path: Path) -> None:
    joined = safe_join(tmp_path, "ws1", "docs", "notes.md")

    assert joined == (tmp_path / "ws1" / "docs" / "notes.md").resolve()
    assert tmp_path.resolve() in joined.parents


def test_safe_join_returns_the_root_itself_for_no_parts(tmp_path: Path) -> None:
    assert safe_join(tmp_path) == tmp_path.resolve()


@pytest.mark.parametrize("part", ["..", "../..", "a/../..", "/etc/passwd", "C:\\Windows"])
def test_safe_join_refuses_rather_than_clamping(tmp_path: Path, part: str) -> None:
    """Silently rewriting a caller's path to something inside the root
    would be a surprising answer to a request that should simply have
    been refused."""
    with pytest.raises(FilePathError):
        safe_join(tmp_path, part)


def test_safe_join_catches_a_symlink_pointing_out_of_the_root(tmp_path: Path) -> None:
    """``resolve()`` on both sides, so a link is caught as well as a
    literal ``..``."""
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (root / "escape").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):  # pragma: no cover - needs privilege
        pytest.skip("This platform does not permit creating symlinks here.")

    with pytest.raises(FilePathError, match="escapes the storage root"):
        safe_join(root, "escape")


# --- MIME + extension -----------------------------------------------------------


def test_extension_is_lowercased_with_its_dot() -> None:
    assert extension_of("Report.PDF") == ".pdf"
    assert extension_of("archive.tar.gz") == ".gz"
    # Empty string, not None -- it is a queried column, and a nullable
    # one would make every filter say ``OR IS NULL``.
    assert extension_of("Makefile") == ""


def test_mime_type_falls_back_to_a_named_default() -> None:
    assert guess_mime_type("a.json") == "application/json"
    assert guess_mime_type("a.unknown-extension") == DEFAULT_MIME_TYPE


# --- extract_text ---------------------------------------------------------------


def test_a_supported_file_is_indexed(tmp_path: Path) -> None:
    path = tmp_path / "a.md"
    # write_bytes, not write_text: on Windows the latter would translate
    # the newline and the assertion would be about io policy, not
    # extraction.
    path.write_bytes(b"# Title\nbody")

    assert extract_text(path) == ("# Title\nbody", "indexed")


def test_an_unsupported_type_is_skipped_not_failed(tmp_path: Path) -> None:
    """``skipped`` is a real, successful outcome -- the file was
    catalogued, its type just is not one this build reads. Collapsing it
    into "no text" would make an unreadable file indistinguishable from
    an empty one."""
    path = tmp_path / "a.png"
    path.write_bytes(b"\x89PNG\r\n")

    assert extract_text(path) == ("", "skipped")


def test_a_missing_file_is_reported_as_failed_not_raised(tmp_path: Path) -> None:
    assert extract_text(tmp_path / "gone.txt") == ("", "failed")


def test_a_large_file_is_truncated_and_says_so(tmp_path: Path) -> None:
    path = tmp_path / "a.txt"
    path.write_bytes(b"0123456789")

    assert extract_text(path, max_bytes=4) == ("0123", "truncated")


def test_a_bad_byte_does_not_lose_the_whole_file(tmp_path: Path) -> None:
    """One encoding artefact costs a replacement character, not the
    entire document."""
    path = tmp_path / "a.txt"
    path.write_bytes(b"good\xffmore")

    text, status = extract_text(path)
    assert status == "indexed"
    assert text.startswith("good") and text.endswith("more")


def test_the_vocabularies_are_closed_and_honest() -> None:
    """No OCR, no PDF, no embeddings -- and the constants say exactly
    which seven extensions this build reads."""
    assert ".pdf" not in TEXT_EXTRACTABLE_EXTENSIONS
    assert ".docx" not in TEXT_EXTRACTABLE_EXTENSIONS
    assert sorted(TEXT_EXTRACTABLE_EXTENSIONS) == [
        ".csv",
        ".json",
        ".md",
        ".txt",
        ".xml",
        ".yaml",
        ".yml",
    ]
    assert sorted(INDEX_STATUSES) == ["failed", "indexed", "skipped", "truncated"]
    assert MAX_EXTRACT_BYTES == 1_048_576
