# Resources

Runtime assets bundled with the application:

| Path                | Purpose                                            |
|---------------------|----------------------------------------------------|
| `themes/*.qss`      | Qt stylesheets loaded by `ThemeManager`.           |
| `icons/`            | SVG / PNG icons used by the UI.                    |
| `fonts/`            | Custom fonts bundled for a consistent typography.  |
| `assets/`           | Splash screens, tray icons, etc.                   |

**Naming rules**

* All filenames are `kebab-case`.
* `.qss` files must match a value of :class:`jarvis.core.types.ThemeName`.
* Icons should be provided as SVG whenever possible.
