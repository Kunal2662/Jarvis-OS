"""System Information -- Milestone 5, section 10A.

Real data: platform, Python version, process uptime (via psutil if
available), app version and data directory.
"""

from __future__ import annotations

import platform
import sys
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from jarvis.ui.components import KeyValueRow, SectionCard

if TYPE_CHECKING:
    from jarvis.core.config.settings import Settings


class SystemInformationView(QWidget):
    def __init__(self, settings: Settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(14)

        title = QLabel("System Information")
        title.setObjectName("greetingTitle")
        outer.addWidget(title)

        card = SectionCard("Runtime")
        rows = [
            ("App version", settings.app_version),
            ("Environment", settings.env.value),
            ("Platform", platform.platform()),
            ("Python", sys.version.split()[0]),
            ("Data directory", str(settings.resolved_data_dir)),
            ("Default LLM provider", settings.llm_default_provider.value),
        ]
        try:
            import psutil

            boot = psutil.boot_time()
            import datetime

            rows.append(
                (
                    "System boot time",
                    datetime.datetime.fromtimestamp(boot).strftime("%Y-%m-%d %H:%M:%S"),
                )
            )
            rows.append(("Logical CPUs", str(psutil.cpu_count(logical=True))))
        except ImportError:
            pass

        for key, value in rows:
            card.body.addWidget(KeyValueRow(key, value))
        outer.addWidget(card)
        outer.addStretch(1)
