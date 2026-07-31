# Plugin Guide

Status: **architecture only — no real plugin loader exists yet.** This
document describes what Milestone 5 prepared, not a shipped feature.

## What exists today

* **`core/interfaces/providers.py` → `IPluginProvider`** — the port
  every future real plugin backend implements: `list_installed`,
  `list_marketplace`, `enable`, `disable`, `reload`, and the
  not-yet-wired `install` / `uninstall` / `update`.
* **`features/plugins/mock_provider.py` → `MockPluginProvider`** — the
  only implementation today. Seeds two illustrative example plugins
  plus whatever real folders exist under `<data_dir>/plugins/` (given
  honest placeholder metadata, since there's no real manifest format
  yet either). `enable` / `disable` / `reload` mutate real in-memory
  state; `install` / `uninstall` / `update` always return `False`.
* **`ui/views/developer/plugin_manager_view.py`** — Developer Mode's
  Plugin Manager. Shows installed-plugin details (version, author,
  dependencies, permissions, status), an Installed/Marketplace tab
  split, and Enable/Disable/Reload wired to the provider above.
  Install/Uninstall/Update buttons are visibly present but disabled
  with a tooltip explaining why, rather than hidden — so the eventual
  real feature has an obvious landing spot.
* **Voice announcements** — enabling/disabling a plugin fires
  `AnnouncementEvent.PLUGIN_ENABLED` / `PLUGIN_DISABLED` through
  `VoiceAnnouncementService.announce_event()`.

## What a real plugin loader would need to add

1. A real plugin manifest format (name/version/author/dependencies/
   permissions) read from `<data_dir>/plugins/<id>/manifest.json` or
   similar — `MockPluginProvider._seed()` shows the exact shape the UI
   already expects.
2. A real `PluginProvider(IPluginProvider)` that actually imports and
   sandboxes plugin code, replacing `MockPluginProvider` in
   `core/di/container.py` — the view code needs **no changes** since it
   only depends on the `IPluginProvider` interface.
3. Real implementations of `install` / `uninstall` / `update`, and
   flipping their buttons from disabled to enabled in
   `plugin_manager_view.py`.
4. A real marketplace backend behind `list_marketplace()` (currently a
   hard-coded placeholder catalog).

## Anti-patterns

* Do not have UI code import `MockPluginProvider` by name outside of
  its DI wiring — depend on `IPluginProvider`.
* Do not silently enable Install/Uninstall/Update — they must stay
  disabled-with-tooltip until a real backend exists, per the "no real
  plugin installation" rule this milestone was built under.
