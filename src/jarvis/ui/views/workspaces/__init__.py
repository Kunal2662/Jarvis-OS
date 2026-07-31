"""Full desktop workspaces for the sidebar nav destinations that used to
be ``ComingSoonView`` placeholders (Milestone 5, section 1): Voice,
Browser, Files & Drive, Coding, Finance, Smart Home, Gmail, Spotify,
Calendar. Every workspace is built from the shared scaffold in
``ui/components/workspace.py`` and renders realistic mock data only --
no real API calls are made from any of these views.

Milestone 5.5 performance fix: this package used to eagerly import all
9 workspace submodules here (a classic "convenience re-export"
``__init__.py``), which meant *any* dotted import of a single submodule
-- e.g. ``jarvis.ui.views.workspaces.gmail_workspace`` -- forced Python
to run this file first, which then imported the other 8 anyway. That
silently defeated ``main_window.py``'s lazy-workspace-loading fix
entirely (measured: ~358ms wasted, ~20% of that module's whole import
chain). Uses `PEP 562 <https://peps.python.org/pep-0562/>`_ module
``__getattr__`` instead: ``from jarvis.ui.views.workspaces import
GmailWorkspace`` (or any of the other 8) still works exactly as before
for any caller, but each name is only resolved -- and its submodule
only imported -- on first actual access.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Zero runtime cost -- only evaluated by type checkers/IDEs, never
    # at import time, so this doesn't reintroduce the eager-import cost
    # the __getattr__ below exists to avoid.
    from jarvis.ui.views.workspaces.browser_workspace import BrowserWorkspace
    from jarvis.ui.views.workspaces.calendar_workspace import CalendarWorkspace
    from jarvis.ui.views.workspaces.coding_workspace import CodingWorkspace
    from jarvis.ui.views.workspaces.files_workspace import FilesWorkspace
    from jarvis.ui.views.workspaces.finance_workspace import FinanceWorkspace
    from jarvis.ui.views.workspaces.gmail_workspace import GmailWorkspace
    from jarvis.ui.views.workspaces.smart_home_workspace import SmartHomeWorkspace
    from jarvis.ui.views.workspaces.spotify_workspace import SpotifyWorkspace
    from jarvis.ui.views.workspaces.voice_workspace import VoiceWorkspace

__all__ = [
    "BrowserWorkspace",
    "CalendarWorkspace",
    "CodingWorkspace",
    "FilesWorkspace",
    "FinanceWorkspace",
    "GmailWorkspace",
    "SmartHomeWorkspace",
    "SpotifyWorkspace",
    "VoiceWorkspace",
]

_CLASS_TO_MODULE = {
    "BrowserWorkspace": "browser_workspace",
    "CalendarWorkspace": "calendar_workspace",
    "CodingWorkspace": "coding_workspace",
    "FilesWorkspace": "files_workspace",
    "FinanceWorkspace": "finance_workspace",
    "GmailWorkspace": "gmail_workspace",
    "SmartHomeWorkspace": "smart_home_workspace",
    "SpotifyWorkspace": "spotify_workspace",
    "VoiceWorkspace": "voice_workspace",
}


def __getattr__(name: str):
    module_name = _CLASS_TO_MODULE.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = importlib.import_module(f"{__name__}.{module_name}")
    value = getattr(module, name)
    globals()[name] = value  # cache on the package so repeat access is free
    return value
