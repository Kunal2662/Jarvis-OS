# Plugin Guide

Status: **superseded by the real backend Plugin Platform (M9 Task
Group D, Aug 2026) — this document now describes only the legacy M5
PySide6 Developer Mode view below, not the current plugin
architecture.** A real Plugin SDK, Loader, Sandbox, Extension API,
Permission Model, Registration System, Store, and Marketplace
foundation now exist in `core/plugins/` — see `docs/MASTER_ROADMAP.md`
§8's Plugin Platform module and `docs/IMPLEMENTATION_ROADMAP.md` §5
Task Group D for the real, shipped architecture. That backend is
**not yet wired to the PySide6 view described below** — replacing
`MockPluginProvider` with a real `IPluginProvider` adapter over
`core/plugins/registry.py`'s `PluginRegistry`, and building the real
Marketplace UI, is M8's React frontend's job per the roadmap's own
design (the PySide6 UI is not the surface future plugin management
renders through). Everything below this line still accurately
describes the M5 PySide6 mock, unchanged by Task Group D.

## What exists today (PySide6 Developer Mode, still mocked)

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

## What now exists for real (M9 Task Group D, `core/plugins/`)

All four items this section used to describe as future work now exist,
for real, in the new backend package — just not yet wired to the
PySide6 view above:

1. A real plugin manifest format — `core/plugins/manifest.py`'s
   `PluginManifest`, read from `<plugins_dir>/<id>/manifest.json` (real
   validation, not `MockPluginProvider._seed()`'s illustrative shape).
2. A real loader/sandbox/registry that actually imports and isolates
   plugin code — `core/plugins/loader.py` + `sandbox.py` +
   `registry.py`'s `PluginRegistry`. This is **not** a
   `PluginProvider(IPluginProvider)` implementation — `PluginRegistry`
   has its own, richer interface (state tracking, permission
   declaration, health/status), so wiring it behind
   `plugin_manager_view.py` still means writing a real adapter that
   maps `IPluginProvider`'s narrower method set onto it, not a
   drop-in replacement.
3. Real `install` / `uninstall` / `update` (with rollback support) —
   `PluginRegistry.install()`/`.uninstall()`/`.update()`. Wiring the
   view's buttons to them is still open work.
4. A real, if v1-scoped, marketplace backend —
   `core/plugins/marketplace.py`'s `Marketplace` +
   `LocalPluginRepository`, not `list_marketplace()`'s hard-coded
   catalog.

See `docs/MASTER_ROADMAP.md` §8's Plugin Platform module and the Aug
2026 M9 Task Group D changelog addendum for the full design.

## Anti-patterns

* Do not have UI code import `MockPluginProvider` by name outside of
  its DI wiring — depend on `IPluginProvider`.
* Do not silently enable Install/Uninstall/Update — they must stay
  disabled-with-tooltip until a real backend exists, per the "no real
  plugin installation" rule this milestone was built under.
