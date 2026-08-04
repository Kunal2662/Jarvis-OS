"""Plugin SDK -- Milestone 9 Task Group D, Phase 1.

The stable contract every plugin (and every layer of this platform
built on top of it -- Loader, Sandbox, Extension API) is written
against: :class:`IPlugin`'s three lifecycle hooks, the fixed
permission vocabulary, a minimal semver comparator for
``sdk_range``/``min_jarvis_version`` checks (no new dependency --
``packaging`` isn't in this project's pinned set and pulling it in for
three comparison operators isn't worth a new supply-chain entry), and
:class:`PluginConfigSchema` for a plugin's own settings.

:class:`IPermissionChecker` is defined here, not in ``permissions.py``
(Phase 5), so :mod:`extension_api` (Phase 4) can depend on the
*shape* of permission checking without depending on Phase 5's concrete
class -- the same relationship ``core/interfaces/service.py``'s
``IService`` already has with ``ServiceManager``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from jarvis.core.plugins.extension_api import PluginContext

SDK_VERSION = "1.0.0"

# Fixed vocabulary -- ``docs/ARCHITECTURE.md`` section 10's Module
# Manifest specification, table row for ``permissions``. A manifest
# declaring anything outside this set fails validation (``manifest.py``)
# rather than silently granting an unknown scope.
PERMISSION_SCOPES: frozenset[str] = frozenset(
    {
        "network",
        "filesystem",
        "hotkey",
        "agent_tools",
        "voice.stt",
        "voice.tts",
        "memory.read",
        "memory.write",
        "smart_home",
        "notifications",
    }
)

_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]*$")


class PluginError(Exception):
    """Base class for every Plugin Platform error."""


@runtime_checkable
class IPlugin(Protocol):
    """A plugin's own top-level object -- one instance per loaded
    plugin, constructed by the Loader (Phase 2) from the manifest's
    ``entry_point``, then driven through these three hooks by the
    Sandbox (Phase 3). Mirrors ``IService``'s "never a seventh
    lifecycle method" rule: anything domain-specific a plugin needs
    lives behind the :class:`~jarvis.core.plugins.extension_api.
    PluginContext` it receives in :meth:`on_load`, not as a fourth hook
    here."""

    async def on_load(self, context: PluginContext) -> None:
        """Called once, immediately after construction. Store *context*
        (the plugin's only channel to the rest of JARVIS) and register
        whatever the manifest declared (commands, voice commands) --
        no side effects beyond registration; real work starts in
        :meth:`on_start`."""
        ...

    async def on_start(self) -> None:
        """Begin real work. May raise -- the Sandbox isolates the
        failure to this one plugin, the same guarantee
        ``ServiceManager.start_all()`` gives every other service."""
        ...

    async def on_stop(self) -> None:
        """Graceful, idempotent stop -- release everything acquired in
        :meth:`on_start`. Always called on disable/uninstall/shutdown,
        even if :meth:`on_start` never ran or failed."""
        ...


@runtime_checkable
class IPermissionChecker(Protocol):
    """The shape :mod:`extension_api` (Phase 4) needs from a permission
    system, without depending on :mod:`permissions` (Phase 5)'s
    concrete :class:`~jarvis.core.plugins.permissions.PermissionModel`
    directly."""

    def is_granted(self, plugin_id: str, scope: str) -> bool:
        """Whether *plugin_id* currently holds *scope*. Never raises
        for an unknown plugin or an unrecognized scope -- both simply
        read as "not granted", matching this platform's least-privilege
        default."""
        ...


# ---------------------------------------------------------------------------
# Semver -- just enough to evaluate ``sdk_range``/``min_jarvis_version``.
# ---------------------------------------------------------------------------
_SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:[-+].*)?$")
_CLAUSE_RE = re.compile(r"^(>=|<=|==|>|<)\s*(\d+\.\d+\.\d+)$")


def parse_semver(version: str) -> tuple[int, int, int]:
    """Parses the ``MAJOR.MINOR.PATCH`` core of *version*, ignoring any
    pre-release/build metadata suffix. Raises :class:`PluginError` for
    anything that isn't at least that -- a plugin declaring a
    non-semver version string is a manifest error, not a runtime
    surprise later."""
    match = _SEMVER_RE.match(version.strip())
    if match is None:
        raise PluginError(f"Not a valid semantic version: {version!r}")
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def version_in_range(version: str, range_spec: str) -> bool:
    """Evaluates *version* against a comma-separated AND of clauses,
    e.g. ``">=1.0.0,<2.0.0"`` (the exact ``sdk_range`` shape
    ``docs/ARCHITECTURE.md`` section 10 specifies). An empty/blank
    *range_spec* matches everything -- "no constraint declared", not
    "matches nothing"."""
    range_spec = range_spec.strip()
    if not range_spec:
        return True
    actual = parse_semver(version)
    for raw_clause in range_spec.split(","):
        clause = raw_clause.strip()
        if not clause:
            continue
        match = _CLAUSE_RE.match(clause)
        if match is None:
            raise PluginError(f"Not a valid version range clause: {clause!r}")
        op, bound_str = match.group(1), match.group(2)
        bound = parse_semver(bound_str)
        if not _compare(actual, op, bound):
            return False
    return True


def _compare(actual: tuple[int, int, int], op: str, bound: tuple[int, int, int]) -> bool:
    if op == ">=":
        return actual >= bound
    if op == "<=":
        return actual <= bound
    if op == "==":
        return actual == bound
    if op == ">":
        return actual > bound
    if op == "<":
        return actual < bound
    raise PluginError(f"Unsupported version range operator: {op!r}")  # pragma: no cover


def is_valid_plugin_name(name: str) -> bool:
    """``lowercase, matches the module's DI-container key``, per
    ``docs/ARCHITECTURE.md`` section 10's ``name`` field -- plugins
    reuse the same naming rule first-party modules already follow."""
    return bool(_NAME_RE.match(name))


# ---------------------------------------------------------------------------
# Plugin-declared settings schema.
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class PluginConfigField:
    type: str  # "string" | "integer" | "number" | "boolean"
    default: Any = None
    required: bool = False


_TYPE_CHECKS: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
}


@dataclass(frozen=True, slots=True)
class PluginConfigSchema:
    """A plugin's ``settings_schema`` (manifest field), made real code.
    Mirrors ``docs/ARCHITECTURE.md`` section 11's Settings standard at
    plugin scale: every field has a declared default, nothing is
    inferred, values are validated (never applied raw)."""

    fields: dict[str, PluginConfigField] = field(default_factory=dict)

    def defaults(self) -> dict[str, Any]:
        return {name: f.default for name, f in self.fields.items()}

    def validate(self, values: dict[str, Any]) -> dict[str, Any]:
        """Returns a full, validated value set: every declared field
        present (from *values* or its default), extra keys in *values*
        dropped, wrong-typed/missing-required values raising
        :class:`PluginError` rather than being silently coerced."""
        result: dict[str, Any] = {}
        for name, spec in self.fields.items():
            if name in values:
                value = values[name]
                allowed = _TYPE_CHECKS.get(spec.type, ())
                if allowed and not isinstance(value, allowed):
                    raise PluginError(
                        f"Config field {name!r} expects type {spec.type!r}, "
                        f"got {type(value).__name__!r}."
                    )
                result[name] = value
            elif spec.required:
                raise PluginError(f"Config field {name!r} is required but missing.")
            else:
                result[name] = spec.default
        return result
