"""Single entry point: show the password gate, then the dashboard.

Kept as its own tiny module so :class:`MainWindow` doesn't need to know
the gate/dashboard sequencing -- it just calls
:func:`open_developer_mode`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QWidget

from jarvis.ui.views.developer.developer_dashboard import DeveloperDashboard
from jarvis.ui.views.developer.developer_gate_dialog import DeveloperGateDialog

if TYPE_CHECKING:
    from jarvis.core.config.settings import Settings
    from jarvis.core.di.container import Container


def open_developer_mode(
    settings: Settings, container: Container, parent: QWidget | None = None
) -> None:
    dev_mode = container.developer_mode_service()

    if dev_mode.is_unlocked():
        DeveloperDashboard(settings, container, parent).exec()
        return

    gate = DeveloperGateDialog(dev_mode, parent)
    if gate.exec():
        DeveloperDashboard(settings, container, parent).exec()
