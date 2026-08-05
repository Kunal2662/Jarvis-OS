"""File Platform domain -- Milestone 11 Task Group C.

Vocabularies, the attachment-target enumeration, and the two pure
helpers the platform's safety rests on: :func:`safe_join` and
:func:`extract_text`.

**Why the storage root is a hard boundary, enforced by a pure
function.** This platform reads and writes real files. A path that
escapes its workspace's directory -- through ``..``, an absolute path,
or a symlink -- would turn a file catalogue into arbitrary filesystem
access. :func:`safe_join` is the single place containment is decided,
it is pure and total (every input either returns a contained path or
raises), and it is called on construction *and* again on every read.
Belt and braces on purpose: the second check costs a ``resolve()`` and
buys immunity to any future code path that builds a row some other way.

**Extraction is deliberately shallow.** Task Group C indexes plain text
from seven extensions and nothing else -- no OCR, no PDF parsing, no
embeddings, no summarisation. Those need Vision (M6's remainder),
Document Intelligence and the vector store, and each belongs to a later
task group. A platform that claims to index a PDF and silently returns
nothing is worse than one that says which seven extensions it reads.
"""

from __future__ import annotations

import mimetypes
from pathlib import Path

#: Folder and file names are rejected outright if they contain any of
#: these. ``..`` and the separators are the traversal vectors;
#: the rest are reserved on Windows and would produce files that cannot
#: be opened, renamed or deleted through normal tooling.
_ILLEGAL_NAME_FRAGMENTS: tuple[str, ...] = (
    "..",
    "/",
    "\\",
    "\0",
    ":",
    "*",
    "?",
    '"',
    "<",
    ">",
    "|",
)

#: Reserved device names on Windows. A file called ``con.txt`` is
#: unopenable there, so it is refused everywhere rather than producing a
#: catalogue that only breaks on one platform.
_RESERVED_STEMS: frozenset[str] = frozenset(
    {
        "con",
        "prn",
        "aux",
        "nul",
        *(f"com{i}" for i in range(1, 10)),
        *(f"lpt{i}" for i in range(1, 10)),
    }
)

#: Extensions this build extracts plain text from. Everything else is
#: catalogued -- name, size, MIME type, tags -- but contributes no
#: searchable body, and its index record says so rather than pretending
#: the file was empty.
TEXT_EXTRACTABLE_EXTENSIONS: frozenset[str] = frozenset(
    {".txt", ".md", ".json", ".yaml", ".yml", ".csv", ".xml"}
)

#: Hard ceiling on extracted text. A 2 GB log file must not become a
#: 2 GB database row; search over the first slice of a huge file is
#: still useful, and the record reports that it was truncated.
MAX_EXTRACT_BYTES = 1_048_576  # 1 MiB

#: What an index record can say about itself. ``skipped`` is a real,
#: successful outcome -- the file was catalogued, its type just is not
#: one this build reads.
INDEX_STATUSES: frozenset[str] = frozenset({"indexed", "skipped", "truncated", "failed"})

#: The entities a file can be attached to. ``workspace`` means "filed
#: against the workspace itself", which is the default rather than an
#: error -- the same posture ``Note`` takes toward projects.
ATTACHMENT_TARGETS: tuple[str, ...] = (
    "workspace",
    "project",
    "note",
    "task",
    "event",
    "reminder",
)

#: MIME type used when the extension is unknown. Named rather than
#: inlined so a caller can compare against it.
DEFAULT_MIME_TYPE = "application/octet-stream"


class FilePathError(ValueError):
    """A path or name that would escape the storage root, or that no
    filesystem would accept."""


def validate_name(name: str, *, label: str = "name") -> str:
    """Returns the stripped name, or raises :class:`FilePathError`.

    Applied to folder names and file names alike, at creation *and* at
    rename -- a rename is just as capable of introducing ``..`` as a
    create, and the two used to be easy to protect unevenly.
    """
    cleaned = (name or "").strip()
    if not cleaned:
        raise FilePathError(f"A {label} must not be empty.")
    if cleaned in {".", ".."}:
        raise FilePathError(f"A {label} must not be {cleaned!r}.")
    for fragment in _ILLEGAL_NAME_FRAGMENTS:
        if fragment in cleaned:
            raise FilePathError(f"A {label} must not contain {fragment!r}.")
    if cleaned.split(".")[0].lower() in _RESERVED_STEMS:
        raise FilePathError(f"{cleaned!r} is a reserved device name and cannot be used.")
    return cleaned


def safe_join(root: Path, *parts: str) -> Path:
    """Join *parts* under *root* and prove the result stays inside it.

    ``Path.resolve()`` on both sides before comparing, so a symlink
    pointing out of the root is caught as well as a literal ``..``.
    Raises rather than clamping: silently rewriting a caller's path to
    something inside the root would be a surprising answer to a request
    that should simply have been refused.
    """
    resolved_root = root.resolve()
    candidate = resolved_root
    for part in parts:
        # Each segment is validated, so a caller cannot smuggle a
        # separator through a single "name".
        candidate = candidate / validate_name(part, label="path segment")
    resolved = candidate.resolve()
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise FilePathError(f"Path {resolved}! escapes the storage root {resolved_root}.")
    return resolved


def guess_mime_type(filename: str) -> str:
    """Extension-based only -- no content sniffing.

    Sniffing means reading the file, and this is called while
    catalogueing entries whose bytes may not be worth touching. An
    honest guess from the name, with a documented fallback, beats a
    confident one that costs a read.
    """
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or DEFAULT_MIME_TYPE


def extension_of(filename: str) -> str:
    """Lower-cased, with the dot. ``""`` for a name with no extension,
    not ``None`` -- it is a queried column and a nullable one would make
    every filter say ``OR IS NULL``."""
    return Path(filename).suffix.lower()


def extract_text(path: Path, *, max_bytes: int = MAX_EXTRACT_BYTES) -> tuple[str, str]:
    """Read a supported file's text. Returns ``(text, status)``.

    Pure in the sense that matters: it reads one path and returns a
    value, touching no database and mutating nothing, so indexing can be
    tested without a session and re-run without side effects.

    Decoding is ``utf-8`` with ``errors="replace"``. A file with one bad
    byte is still worth indexing, and refusing the whole thing over an
    encoding artefact would lose more than the replacement characters
    cost.
    """
    if extension_of(path.name) not in TEXT_EXTRACTABLE_EXTENSIONS:
        return "", "skipped"
    try:
        raw = path.read_bytes()
    except OSError:
        return "", "failed"

    truncated = len(raw) > max_bytes
    text = raw[:max_bytes].decode("utf-8", errors="replace")
    return text, "truncated" if truncated else "indexed"
