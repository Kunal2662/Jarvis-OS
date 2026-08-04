"""Plugin manifest schema and validation -- Milestone 9 Task Group D,
Phase 1.

``docs/ARCHITECTURE.md`` section 10's Module Manifest specification,
made real, loadable code for plugins specifically (a first-party
module's own manifest is a separate, lighter-weight concern -- this
class is the plugin-facing superset), extended with the Universal
Compatibility fields requirement 5 asks for: ``supported_os``,
``supported_arch``, ``required_capabilities``, ``min_jarvis_version``,
alongside the existing ``permissions``.

**Platform-neutral by default.** A manifest that omits
``supported_os``/``supported_arch`` entirely declares itself compatible
with everything this JARVIS build knows about -- a plugin author who
writes pure-Python, OS-agnostic code should not have to enumerate every
platform by hand to be loadable everywhere. A plugin that genuinely
needs a specific OS (e.g. Windows-only automation) declares that
explicitly and narrowly, the exception rather than the default.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from jarvis.core.interfaces.platform import CAPABILITY_VOCABULARY
from jarvis.core.plugins.sdk import (
    PERMISSION_SCOPES,
    PluginConfigField,
    PluginConfigSchema,
    PluginError,
    is_valid_plugin_name,
    parse_semver,
)

SUPPORTED_OS_VALUES: tuple[str, ...] = ("windows", "linux", "macos")
SUPPORTED_ARCH_VALUES: tuple[str, ...] = ("x86_64", "arm64", "x86")


class PluginManifestError(PluginError):
    """Raised for a structurally or semantically invalid manifest."""


class PluginCommand(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    description: str = ""


class VoiceCommandBinding(BaseModel):
    model_config = ConfigDict(frozen=True)
    phrase: str
    command: str


class AutomationSupport(BaseModel):
    model_config = ConfigDict(frozen=True)
    actions: list[str] = Field(default_factory=list)
    reversible: list[str] = Field(default_factory=list)


class DeveloperMetadata(BaseModel):
    model_config = ConfigDict(frozen=True)
    author: str = "unknown"
    homepage: str | None = None
    repository: str | None = None


class PluginManifest(BaseModel):
    """``plugins/<name>/manifest.json``. A module without a manifest
    cannot be loaded by the Plugin Loader (Phase 2) -- enforcement, not
    optional documentation, per ``docs/ARCHITECTURE.md`` section 10."""

    model_config = ConfigDict(frozen=True)

    name: str
    display_name: str
    version: str
    sdk_range: str = ""
    min_jarvis_version: str = "0.0.0"
    entry_point: str | dict[str, str]
    dependencies: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    supported_os: list[str] = Field(default_factory=lambda: list(SUPPORTED_OS_VALUES))
    supported_arch: list[str] = Field(default_factory=lambda: list(SUPPORTED_ARCH_VALUES))
    required_capabilities: list[str] = Field(default_factory=list)
    commands: list[PluginCommand] = Field(default_factory=list)
    voice_commands: list[VoiceCommandBinding] = Field(default_factory=list)
    automation_support: AutomationSupport | None = None
    settings_schema: dict[str, Any] = Field(default_factory=dict)
    icons: dict[str, str] = Field(default_factory=dict)
    developer_metadata: DeveloperMetadata = Field(default_factory=DeveloperMetadata)

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        if not is_valid_plugin_name(value):
            raise ValueError(
                f"Plugin name {value!r} must be lowercase, matching ^[a-z][a-z0-9_-]*$."
            )
        return value

    @field_validator("version", "min_jarvis_version")
    @classmethod
    def _validate_semver(cls, value: str) -> str:
        try:
            parse_semver(value)
        except PluginError as err:
            # pydantic only auto-wraps ValueError/AssertionError/TypeError
            # raised inside a validator into its own ValidationError --
            # PluginError (this module's own error type, used everywhere
            # else) would otherwise escape model_validate() unwrapped.
            raise ValueError(str(err)) from err
        return value

    @field_validator("permissions")
    @classmethod
    def _validate_permissions(cls, value: list[str]) -> list[str]:
        unknown = sorted(set(value) - PERMISSION_SCOPES)
        if unknown:
            raise ValueError(
                f"Unknown permission scope(s) {unknown}; allowed: {sorted(PERMISSION_SCOPES)}"
            )
        return value

    @field_validator("supported_os")
    @classmethod
    def _validate_supported_os(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("supported_os must declare at least one platform.")
        unknown = sorted(set(value) - set(SUPPORTED_OS_VALUES))
        if unknown:
            raise ValueError(
                f"Unknown supported_os entries {unknown}; allowed: {SUPPORTED_OS_VALUES}"
            )
        return value

    @field_validator("supported_arch")
    @classmethod
    def _validate_supported_arch(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("supported_arch must declare at least one architecture.")
        unknown = sorted(set(value) - set(SUPPORTED_ARCH_VALUES))
        if unknown:
            raise ValueError(
                f"Unknown supported_arch entries {unknown}; allowed: {SUPPORTED_ARCH_VALUES}"
            )
        return value

    @field_validator("required_capabilities")
    @classmethod
    def _validate_capabilities(cls, value: list[str]) -> list[str]:
        unknown = sorted(set(value) - CAPABILITY_VOCABULARY)
        if unknown:
            allowed = sorted(CAPABILITY_VOCABULARY)
            raise ValueError(f"Unknown required_capabilities entries {unknown}; allowed: {allowed}")
        return value

    @model_validator(mode="after")
    def _validate_no_self_dependency(self) -> PluginManifest:
        if self.name in self.dependencies:
            raise ValueError(f"Plugin {self.name!r} cannot declare itself as a dependency.")
        return self

    @property
    def plugin_id(self) -> str:
        return self.name

    def config_schema(self) -> PluginConfigSchema:
        """Real-izes the raw ``settings_schema`` JSON dict (per
        ``docs/ARCHITECTURE.md`` section 11) into a usable
        :class:`~jarvis.core.plugins.sdk.PluginConfigSchema`."""
        fields: dict[str, PluginConfigField] = {}
        for key, spec in self.settings_schema.items():
            if not isinstance(spec, dict) or "type" not in spec:
                raise PluginManifestError(
                    f"settings_schema field {key!r} must be an object with a 'type'."
                )
            fields[key] = PluginConfigField(
                type=spec["type"],
                default=spec.get("default"),
                required=bool(spec.get("required", False)),
            )
        return PluginConfigSchema(fields=fields)


def load_manifest(path: Path) -> PluginManifest:
    """Reads and validates ``manifest.json`` at *path*. Raises
    :class:`PluginManifestError` for missing/unreadable/malformed-JSON/
    schema-invalid input -- never a raw ``OSError``/``ValueError``/
    pydantic ``ValidationError`` escaping this module's boundary, the
    same "one clear error type per module" convention
    ``core/lifecycle/crash_recovery.py`` already follows."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as err:
        raise PluginManifestError(f"Could not read manifest at {path}: {err}") from err
    try:
        data = json.loads(raw)
    except ValueError as err:
        raise PluginManifestError(f"Manifest at {path} is not valid JSON: {err}") from err
    try:
        return PluginManifest.model_validate(data)
    except ValidationError as err:
        raise PluginManifestError(f"Manifest at {path} failed validation: {err}") from err
