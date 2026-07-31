"""Developer Dashboard -- the Developer Mode shell (Milestone 5, 10A).

A password-gated window (see :class:`DeveloperGateDialog`) with a left
nav across the 12 required sections and a stacked content area, built
entirely from the same component library as the rest of the app.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from jarvis.ui.components import KeyValueRow, SectionCard, StatTile
from jarvis.ui.components.buttons import NavItemButton
from jarvis.ui.views.developer.agent_trace_view import AgentTraceView
from jarvis.ui.views.developer.ai_model_manager_view import AiModelManagerView
from jarvis.ui.views.developer.api_center_view import ApiCenterView
from jarvis.ui.views.developer.backup_restore_view import BackupRestoreView
from jarvis.ui.views.developer.configuration_manager_view import ConfigurationManagerView
from jarvis.ui.views.developer.developer_console_view import DeveloperConsoleView
from jarvis.ui.views.developer.logs_diagnostics_view import LogsDiagnosticsView
from jarvis.ui.views.developer.module_manager_view import ModuleManagerView
from jarvis.ui.views.developer.performance_monitor_view import PerformanceMonitorView
from jarvis.ui.views.developer.plugin_manager_view import PluginManagerView
from jarvis.ui.views.developer.security_center_view import SecurityCenterView
from jarvis.ui.views.developer.system_information_view import SystemInformationView
from jarvis.ui.views.developer.update_center_view import UpdateCenterView
from jarvis.ui.views.developer.vision_status_view import VisionStatusView

if TYPE_CHECKING:
    from jarvis.core.config.settings import Settings
    from jarvis.core.di.container import Container


class _DashboardOverview(QWidget):
    """Section 1 of Developer Mode -- the landing "Developer Dashboard" page."""

    def __init__(
        self, settings: Settings, container: Container, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(14)

        title = QLabel("Developer Dashboard")
        title.setObjectName("greetingTitle")
        outer.addWidget(title)

        row = QHBoxLayout()
        api_count = len(container.api_center_service().list_apis())
        row.addWidget(StatTile("Configured APIs", str(api_count)))
        row.addWidget(StatTile("Current Version", container.update_service().current_version))
        row.addWidget(StatTile("Update Channel", settings.update.channel.title()))
        row.addWidget(
            StatTile("Restore Points", str(len(container.update_service().list_restore_points())))
        )
        outer.addLayout(row)

        card = SectionCard("Quick Facts")
        card.body.addWidget(KeyValueRow("Environment", settings.env.value))
        card.body.addWidget(KeyValueRow("Data directory", str(settings.resolved_data_dir)))
        card.body.addWidget(
            KeyValueRow(
                "Automation engine", "Enabled" if settings.automation.enabled else "Disabled"
            )
        )
        outer.addWidget(card)
        outer.addStretch(1)


# (id, icon, label, builder) -- builder returns a fresh QWidget for that section.
_SECTIONS: list[tuple[str, str, str]] = [
    ("dashboard", "📊", "Developer Dashboard"),
    ("api_center", "🔌", "API Center"),
    ("update_center", "⬆", "Update Center"),
    ("modules", "🧩", "Module Manager"),
    ("plugins", "🧷", "Plugin Manager"),
    ("ai_models", "🤖", "AI Model Manager"),
    ("performance", "📈", "Performance Monitor"),
    ("logs", "📜", "Logs & Diagnostics"),
    ("configuration", "⚙", "Configuration Manager"),
    ("security", "🛡", "Security Center"),
    ("backup", "💾", "Backup & Restore"),
    ("console", "⌁", "Developer Console"),
    ("system_info", "🖥", "System Information"),
    ("agent_trace", "🧠", "Agent Trace"),
    ("vision_status", "👁", "Vision Status"),
]


class DeveloperDashboard(QDialog):
    def __init__(
        self, settings: Settings, container: Container, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Developer Mode — JARVIS OS")
        self.resize(1100, 720)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        nav_panel = QWidget()
        nav_panel.setObjectName("devModeNav")
        nav_panel.setFixedWidth(230)
        nav_layout = QVBoxLayout(nav_panel)
        nav_layout.setContentsMargins(16, 18, 16, 16)
        nav_layout.setSpacing(2)

        header = QLabel("🔒 Developer Mode")
        header.setObjectName("devModeTitle")
        nav_layout.addWidget(header)
        nav_layout.addSpacing(10)

        self._stack = QStackedWidget()
        group = QButtonGroup(self)
        group.setExclusive(True)

        builders = {
            "dashboard": lambda: _DashboardOverview(settings, container),
            "api_center": lambda: ApiCenterView(container.api_center_service()),
            "update_center": lambda: UpdateCenterView(container.update_service()),
            "modules": lambda: ModuleManagerView(settings),
            "plugins": lambda: PluginManagerView(
                settings, voice_announcer=container.voice_announcement_service()
            ),
            "ai_models": lambda: AiModelManagerView(settings),
            "performance": lambda: PerformanceMonitorView(),
            "logs": lambda: LogsDiagnosticsView(settings),
            "configuration": lambda: ConfigurationManagerView(container.settings_service()),
            "security": lambda: SecurityCenterView(settings, container.developer_mode_service()),
            "backup": lambda: BackupRestoreView(container.update_service()),
            "console": lambda: DeveloperConsoleView(container.automation_service()),
            "system_info": lambda: SystemInformationView(settings),
            "agent_trace": lambda: AgentTraceView(container),
            "vision_status": lambda: VisionStatusView(container),
        }

        for section_id, icon, label in _SECTIONS:
            btn = NavItemButton(icon, label)
            btn.clicked.connect(lambda _c=False, sid=section_id: self._show(sid))
            group.addButton(btn)
            nav_layout.addWidget(btn)
            self._stack.addWidget(builders[section_id]())
            if section_id == "dashboard":
                btn.setChecked(True)

        nav_layout.addStretch(1)
        close_btn = QPushButton("Lock & Close")
        close_btn.clicked.connect(self._lock_and_close)
        nav_layout.addWidget(close_btn)

        root.addWidget(nav_panel)
        root.addWidget(self._stack, 1)

        self._container = container
        self._section_ids = [s[0] for s in _SECTIONS]

        # Auto-lock when the session timeout elapses, even if the window stays open.
        self._session_timer = QTimer(self)
        self._session_timer.setInterval(5000)
        self._session_timer.timeout.connect(self._check_session)
        self._session_timer.start()

    def _show(self, section_id: str) -> None:
        self._stack.setCurrentIndex(self._section_ids.index(section_id))

    def _check_session(self) -> None:
        if not self._container.developer_mode_service().is_unlocked():
            self.close()

    def _lock_and_close(self) -> None:
        self._container.developer_mode_service().lock()
        self.close()
