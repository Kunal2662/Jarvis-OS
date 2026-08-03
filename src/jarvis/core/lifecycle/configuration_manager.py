"""``ConfigurationManager`` -- the existing ``pydantic-settings``
configuration layer (``core/config/settings.py``), now with a real
live-reload path (Milestone 9 Task Group B), per `docs/MASTER_ROADMAP.md`
M9's own wording for this feature.

This does **not** replace :class:`~jarvis.services.settings_service.SettingsService`
(the existing ``.env``-persistence service the Settings UI writes
through) -- it composes on top of it. ``SettingsService`` answers "what
can the user *persist* for next launch"; ``ConfigurationManager``
answers "what can change *right now*, in the already-running process,
without a restart."

**Why only a curated subset of fields reload live.** This project's
Settings module already documents a deliberate design decision
(``settings_service.py``'s own docstring): *"We do not try to hot-swap
providers here ... That's simpler and safer for a single-user desktop
app than in-flight DI re-wiring."* Every provider-credential/``enabled``
field (``openai``, ``ollama``, ``stt``, ``tts``, ...) is baked into a
Singleton built once, at DI-container-declaration time
(``core/di/container.py``'s ``_build_*`` factories) -- silently
updating the *settings value* for one of these without also rebuilding
the provider would make the Settings UI lie about what's actually
running. ``SAFE_RELOAD_SECTIONS`` below is restricted to sections whose
consumers already read the live ``Settings`` object on every call
(``ChatService.stream()`` reads ``settings.ui.system_prompt`` fresh
every time, for example) -- reloading these is genuinely live, not a
cosmetic value change with no real effect.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from jarvis.core.config.settings import load_settings
from jarvis.core.events.events import ConfigurationUpdatedEvent
from jarvis.core.logging.logger import get_logger

if TYPE_CHECKING:
    from pathlib import Path

    from jarvis.core.config.settings import Settings
    from jarvis.core.events.event_bus import EventBus

_logger = get_logger("jarvis.core.lifecycle.configuration")

# Sections read live, per-call, by their consumers -- see module
# docstring. Every other section (provider credentials/enabled flags,
# `db`, `api`, `vector`, `security`, ...) is immutable startup
# configuration: still user-editable via `SettingsService.set_env()`
# for the *next* launch, just not safe to apply to the running process.
SAFE_RELOAD_SECTIONS: frozenset[str] = frozenset(
    {"ui", "voice_announce", "memory", "update", "dev_mode"}
)


class ConfigurationManager:
    def __init__(
        self,
        settings: Settings,
        event_bus: EventBus,
        env_file: Path | None = None,
    ) -> None:
        # The *live* Settings instance every already-constructed service
        # holds a reference to -- `reload()` mutates its fields in place
        # (never replaces the object) so the change is visible to
        # consumers without re-injecting anything.
        self._settings = settings
        self._event_bus = event_bus
        self._env_file = env_file

    async def reload(self) -> tuple[str, ...]:
        """Re-parse configuration from the environment/``.env`` file
        (the same source the process originally booted from) and apply
        only the fields in :data:`SAFE_RELOAD_SECTIONS` that actually
        changed, onto the live `Settings` object in place. Publishes
        :class:`ConfigurationUpdatedEvent` (naming the changed dotted
        keys, never values -- some are secrets) only if something
        actually changed. Returns the changed keys."""
        load_settings.cache_clear()
        try:
            fresh = load_settings(env_file=self._env_file)
        finally:
            # Never leave the process-wide cache pointing at `fresh` --
            # `self._settings` (the object every service was injected
            # with) remains the one live instance; a stray cached
            # `fresh` would let some future, unrelated `load_settings()`
            # call silently diverge from it.
            load_settings.cache_clear()

        changed: list[str] = []
        for section_name in sorted(SAFE_RELOAD_SECTIONS):
            live_section = getattr(self._settings, section_name)
            fresh_section = getattr(fresh, section_name)
            for field_name in type(live_section).model_fields:
                live_value = getattr(live_section, field_name)
                fresh_value = getattr(fresh_section, field_name)
                if live_value != fresh_value:
                    setattr(live_section, field_name, fresh_value)
                    changed.append(f"{section_name}.{field_name}")

        if changed:
            _logger.info("Configuration reload applied {} change(s): {}", len(changed), changed)
            await self._event_bus.publish(ConfigurationUpdatedEvent(keys=tuple(changed)))
        else:
            _logger.debug("Configuration reload found no safe-to-apply changes.")
        return tuple(changed)

    def feature_flags(self) -> dict[str, bool]:
        """A real, read-only view of every provider's existing
        ``enabled`` bool -- the "providers as feature flags" convention
        `core/config/settings.py`'s own module docstring already
        establishes, surfaced as one map instead of a fresh flag system
        disconnected from what the app actually checks at runtime."""
        flags: dict[str, bool] = {}
        for section_name in type(self._settings).model_fields:
            section: Any = getattr(self._settings, section_name)
            enabled = getattr(section, "enabled", None)
            if isinstance(enabled, bool):
                flags[section_name] = enabled
        return flags

    def safe_reload_sections(self) -> tuple[str, ...]:
        """Which sections `reload()` is willing to touch -- exposed for
        Developer Mode diagnostics and tests, not just an internal
        constant."""
        return tuple(sorted(SAFE_RELOAD_SECTIONS))
