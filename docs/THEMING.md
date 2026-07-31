# Theming

## Files

* **QSS**: `resources/themes/<name>.qss`
* **Python palettes**: `src/jarvis/ui/themes/palette.py`
* **ThemeService** (pure Python): `src/jarvis/services/theme_service.py`
* **ThemeManager** (Qt side effects): `src/jarvis/ui/themes/theme_manager.py`

## Built-in themes

| Name     | Vibe                                            |
|----------|-------------------------------------------------|
| `jarvis` | Deep navy + electric cyan HUD (default).        |
| `dark`   | Neutral dark — dev-friendly.                    |
| `light`  | Clean light theme for daytime use.              |

The active theme is picked by `JARVIS_UI_THEME`.

## How it works

1. `ThemeService.load(name)` reads `resources/themes/<name>.qss` and
   returns it as a `str` — pure, framework-free, unit-testable.
2. `ThemeManager.apply(app, theme)` calls
   `QApplication.setStyleSheet(qss)` and logs the switch.
3. Widgets may customise their look further via **Qt property selectors**
   (e.g. `QPushButton[variant="primary"]`) — this keeps global QSS lean
   and avoids per-widget `setStyleSheet` calls.

## Adding a theme

1. Add a value to `jarvis.core.types.ThemeName`.
2. Add a matching `Palette` in `palette.py`.
3. Add `resources/themes/<value>.qss`.
4. Done — the settings enum + service pick it up automatically.

## Anti-patterns

* Hard-coding colours anywhere except in QSS or `palette.py`.
* Calling `setStyleSheet` from inside widget classes (defeats theming).
* Baking dark-mode logic into feature code — always route through
  `ThemeService`.

## Theme Engine (Milestone 5, section 10)

`ThemeService` was completed in the Milestone 5 pass:

* **`switch(name)`** actually switches the active theme in-memory now
  (was a `NotImplementedError` stub inherited from Milestone 1). Disk
  persistence still goes through `SettingsService.set_env("JARVIS_UI_THEME", ...)`
  — see `ui/dialogs/settings_pages/theme_page.py` — since `Settings`
  intentionally owns no file I/O itself.
* **Accent colors** — `settings.ui.accent` (already a field) now
  actually does something: `ThemeService.load()` applies it as a safe,
  literal find-and-replace of the theme's default accent hex. At the
  factory-default accent this is a no-op — every theme's QSS comes back
  byte-identical to the file on disk — so the official UI's pixel-exact
  look is untouched unless a user deliberately picks a different
  accent from the swatch picker on the Theme settings page.
  `ThemeService.available_accents()` returns the curated palette;
  `set_accent(name_or_hex)` validates and switches it.
* **Design tokens** — `ThemeService.tokens()` returns a `ThemeTokens`
  dataclass (font family/size, spacing unit, border radius, animation
  duration, blur radius, glow color) as structured metadata for any
  future tool that wants to stay visually consistent without parsing
  QSS by hand.
* **Future custom themes** — drop a `.qss` file into
  `<data_dir>/themes/custom/` (a user-writable location, not the
  installed `resources/` folder) and it shows up in
  `ThemeService.list_custom_themes()`; `load_custom(name)` returns its
  contents. Deliberately kept separate from the strict `ThemeName` enum
  that `Settings.ui.theme` is validated against — custom themes are
  opt-in and orthogonal to the three built-in ones, not a fourth enum
  value.
