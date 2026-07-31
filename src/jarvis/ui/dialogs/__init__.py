"""Settings dialog architecture.

Design principles
-----------------
* **Category-driven, extensible**: each page is a self-contained
  ``SettingsPage`` subclass that declares its own ``id``, ``title`` and
  ``category``. New pages are registered in
  :data:`jarvis.ui.dialogs.settings_pages.PAGE_REGISTRY` — no dialog
  code changes required.
* **Milestone-aware**: pages that are not yet implemented render a
  polite "Coming in Milestone X" placeholder so users can see the
  full product surface from day one.
* **Two-column layout**: `QListWidget` sidebar + `QStackedWidget` right
  panel. Category headings are non-selectable items.

Public API::

    from jarvis.ui.dialogs.settings_dialog import SettingsDialog
"""

from __future__ import annotations

from jarvis.ui.dialogs.settings_dialog import SettingsDialog

__all__ = ["SettingsDialog"]
