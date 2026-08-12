"""Download source abstraction -- M22 Task Group B.

**No URL is hardcoded anywhere in this package.** A source is declared
in configuration and resolved at runtime, which is what makes the brief's
"all downloads must use provider abstraction" true rather than merely
stated.

That is not ceremony. Three concrete consequences:

* An air-gapped or enterprise deployment points JARVIS at an internal
  mirror without editing code.
* An administrator can reorder sources (`ARCHITECTURE.md` §22.11 gives
  them download-source control; personal users get none).
* The failover in :mod:`jarvis.installer.download` has somewhere to fail
  *over to* -- a single baked-in URL has no second attempt.

**Nothing here performs I/O.** Resolution is pure: artefact plus source
in, request out. The downloader owns the network, this module owns the
addressing, and keeping them apart is what lets every resolution rule be
tested without a server.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

#: Environment variable an administrator or a deployment sets to point
#: the installer at a mirror. Deliberately the *only* place a concrete
#: host can enter this package.
SOURCE_ENV_VAR = "JARVIS_DOWNLOAD_SOURCES"


class SourceResolutionError(Exception):
    """No configured source can serve an artefact."""


#: Characters Windows forbids in a filename. A model id like
#: `qwen2.5:14b` is a perfectly good *registry* identifier and an
#: impossible *filename* -- the colon makes `Path` treat it as a drive
#: qualifier and the write fails. Windows is this milestone's primary
#: platform, so the two must not be the same string.
_UNSAFE_FILENAME_CHARS = ':*?"<>|/\\'


def safe_filename(key: str) -> str:
    """A filename that survives every supported platform.

    Substitution rather than hashing so the file stays recognisable to a
    human looking at the models folder, which matters when someone is
    diagnosing a half-finished installation by hand.
    """
    cleaned = "".join(
        "_" if character in _UNSAFE_FILENAME_CHARS else character for character in key
    )
    return cleaned.strip(". ") or "artifact"


@dataclass(frozen=True, slots=True)
class Artifact:
    """Something the installer needs to fetch.

    ``key`` is opaque to this module: a model tier's id, a voice
    component's key. The source decides how to turn it into a path, so a
    mirror with a different layout is a configuration change rather than
    a code change.
    """

    key: str
    kind: str
    """`model` or `voice`. Sources may serve one kind and not the other."""
    label: str = ""
    """What a personal user is shown -- "Local AI", "Voice". ``key`` is a
    model or component id and is therefore §22.12-restricted; progress
    reported to a personal user carries this instead. Defaults to a
    generic description of the kind rather than to the key, so forgetting
    to set it cannot leak one."""
    expected_bytes: int | None = None
    """``None`` when the size is not known ahead of time -- the
    downloader then reports indeterminate progress rather than inventing
    a denominator."""
    checksum: str | None = None
    """``sha256:<hex>``. ``None`` means the source publishes no checksum;
    :mod:`jarvis.installer.download` treats that as *unverifiable* rather
    than *verified*, and says so."""

    @property
    def filename(self) -> str:
        """Where this lands on disk. **Not** ``key`` -- see
        :func:`safe_filename`."""
        return safe_filename(self.key)

    @property
    def display_name(self) -> str:
        """Safe to show anyone."""
        return self.label or ("Local AI" if self.kind == "model" else "Voice component")


@dataclass(frozen=True, slots=True)
class DownloadSource:
    """One place artefacts can come from."""

    name: str
    """Administrator-facing. Never shown to a personal user (§22.12)."""
    base_url: str
    kinds: tuple[str, ...]
    priority: int
    """Lower is tried first."""
    requires_internet: bool = True
    """``False`` for a `file://` mirror bundled with the installer, which
    is what makes a genuinely offline installation possible."""
    headers: dict[str, str] = field(default_factory=dict)

    def supports(self, artifact: Artifact) -> bool:
        return artifact.kind in self.kinds

    def resolve(self, artifact: Artifact) -> str:
        """The URL for *artifact* from this source.

        Three placeholders, and the choice between the first two
        matters:

        ``{key}``
            The registry id, e.g. ``llama3.1:8b``. What an upstream
            registry addresses by.
        ``{filename}``
            The filesystem-safe form, e.g. ``llama3.1_8b``. What a
            ``file://`` mirror on Windows *must* use, since NTFS forbids
            a colon in a filename -- a mirror simply cannot hold a file
            named after the raw key.
        ``{kind}``
            ``model`` or ``voice``.

        Both are offered rather than one being inferred from the scheme,
        because an HTTP mirror may equally have been populated by a
        script that sanitised the names. The administrator describing
        the mirror knows its layout; this module should not guess it.

        A ``base_url`` with no placeholder gets the safe filename
        appended -- the flat-directory case, where the raw key would be
        unwritable on the primary platform.
        """
        if not self.supports(artifact):
            raise SourceResolutionError(f"Source {self.name!r} does not serve {artifact.kind!r}.")

        if any(token in self.base_url for token in ("{key}", "{kind}", "{filename}")):
            return self.base_url.format(
                key=artifact.key, kind=artifact.kind, filename=artifact.filename
            )
        return f"{self.base_url.rstrip('/')}/{artifact.filename}"


@dataclass(frozen=True, slots=True)
class ResolvedDownload:
    artifact: Artifact
    source: DownloadSource
    url: str


class SourceRegistry:
    """The ordered set of sources the installer may use.

    **Ships empty.** There is no default host, and that is the point:
    with nothing configured, `resolve_all` raises a message naming the
    environment variable to set. An installer that silently falls back
    to a hardcoded vendor URL would defeat the abstraction on the one
    path that matters -- the default one.
    """

    def __init__(self, sources: list[DownloadSource] | None = None) -> None:
        self._sources: list[DownloadSource] = sorted(
            sources or [], key=lambda source: source.priority
        )

    @property
    def sources(self) -> tuple[DownloadSource, ...]:
        return tuple(self._sources)

    def register(self, source: DownloadSource) -> None:
        self._sources.append(source)
        self._sources.sort(key=lambda item: item.priority)

    def resolve_all(self, artifact: Artifact, *, online: bool = True) -> list[ResolvedDownload]:
        """Every candidate for *artifact*, best first.

        A list rather than a single answer because the downloader retries
        against the next source when one fails -- the failover the brief
        asks for is only possible if resolution returns alternatives.

        *online* ``False`` filters to sources that need no network, so an
        offline installation uses a bundled mirror instead of failing.
        """
        if not self._sources:
            raise SourceResolutionError(
                "No download sources are configured. Set "
                f"{SOURCE_ENV_VAR} or register a source before provisioning."
            )

        candidates = [
            ResolvedDownload(artifact=artifact, source=source, url=source.resolve(artifact))
            for source in self._sources
            if source.supports(artifact) and (online or not source.requires_internet)
        ]
        if not candidates:
            raise SourceResolutionError(
                f"No configured source can serve {artifact.kind} {artifact.key!r}"
                + ("" if online else " without an internet connection")
                + "."
            )
        return candidates

    def to_dict(self, *, include_urls: bool) -> dict[str, Any]:
        """*include_urls* is ``False`` for a personal user.

        A base URL names a provider as surely as the provider's own name
        does, so §22.12 keeps it out of a personal payload. The *count*
        is safe and still tells the user something useful.
        """
        if not include_urls:
            return {"source_count": len(self._sources)}
        return {
            "sources": [
                {
                    "name": source.name,
                    "base_url": source.base_url,
                    "kinds": list(source.kinds),
                    "priority": source.priority,
                    "requires_internet": source.requires_internet,
                }
                for source in self._sources
            ]
        }


def parse_sources(specification: str) -> list[DownloadSource]:
    """Parse ``JARVIS_DOWNLOAD_SOURCES``.

    Format -- ``name|base_url|kinds[|priority]``, entries separated by
    **semicolons**::

        mirror|file:///opt/jarvis/{kind}/{filename}|model,voice|0;
        upstream|https://example.test/{kind}/{key}|model,voice|10

    Semicolons between entries, commas within ``kinds``. The first
    version used commas for both, which silently split
    ``…|model,voice|0`` into a model-only source plus an unparseable
    fragment -- so voice downloads found no source while model downloads
    worked, which is the worst kind of bug: it looks like it works.
    Found by running a real provisioning against a `file://` mirror.

    A deliberately small format: it is read at installation time on a
    machine that may have nothing installed yet, so it must not need a
    parser beyond the standard library, and an administrator must be
    able to type it into an environment variable.

    A malformed entry is skipped rather than fatal -- one bad mirror in a
    list of three should not prevent an installation the other two can
    serve.
    """
    sources: list[DownloadSource] = []
    for index, raw in enumerate(specification.split(";")):
        entry = raw.strip()
        if not entry:
            continue
        parts = [part.strip() for part in entry.split("|")]
        if len(parts) < 3 or not parts[0] or not parts[1] or not parts[2]:
            continue

        name, base_url, kinds_raw = parts[0], parts[1], parts[2]
        priority = index
        if len(parts) >= 4 and parts[3].lstrip("-").isdigit():
            priority = int(parts[3])

        kinds = tuple(kind for kind in (k.strip() for k in kinds_raw.split(",")) if kind)
        if not kinds:
            continue

        sources.append(
            DownloadSource(
                name=name,
                base_url=base_url,
                kinds=kinds,
                priority=priority,
                # A `file://` mirror is what makes an offline install
                # work; inferring it from the scheme means an
                # administrator does not have to remember a flag.
                requires_internet=not base_url.startswith("file:"),
            )
        )
    return sources


def registry_from_environment(environ: dict[str, str] | None = None) -> SourceRegistry:
    """Build the registry from the environment.

    Returns an **empty** registry when nothing is configured, which
    `resolve_all` turns into an explicit error naming the variable. No
    fallback host, by design.
    """
    env = environ if environ is not None else dict(os.environ)
    specification = env.get(SOURCE_ENV_VAR, "").strip()
    return SourceRegistry(parse_sources(specification) if specification else [])
