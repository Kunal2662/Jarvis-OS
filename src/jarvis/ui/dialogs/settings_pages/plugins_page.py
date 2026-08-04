"""Plugins settings page -- Milestone 9 Task Group D (Plugin Platform).

Was a `make_placeholder(...)` entry reading "Coming in Milestone 5 —
Agents" until the Aug 2026 final backlog pass. The Plugin Platform
shipped in M9: `PluginSettings` is real, and `PluginRegistry`,
`PluginLoader`, `PluginSandbox`, `PermissionModel` and `PluginStore` all
read it. The placeholder had been wrong since M9 closed, and pointed at
a milestone that never owned this feature.

Exposes the settings that already existed. Building nothing new, and
deliberately *not* a second plugin-management surface: enable/disable of
an individual plugin lives in Developer Mode's Plugin Manager, and
duplicating it here would be two UIs racing the same registry.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
)

from jarvis.ui.dialogs.settings_pages.base import SettingsPage
from jarvis.utils.async_utils import fire_and_forget

#: The two tiers `PluginSandbox` implements. Kept in the order the
#: settings docstring describes them, weakest isolation first.
_SANDBOX_MODES = ("in_process", "subprocess")


class PluginsPage(SettingsPage):
    id = "plugins"
    title = "Plugins"
    category = "Plugins"

    def build(self) -> None:
        title = QLabel(self.title)
        title.setStyleSheet("font-size:20px; font-weight:600;")
        self._layout.addWidget(title)

        subtitle = QLabel(
            "Platform-wide defaults for the plugin runtime. Individual plugins are "
            "enabled, disabled and inspected in Developer Mode → Plugin Manager."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color:#6D8BAA;")
        self._layout.addWidget(subtitle)

        form = QFormLayout()
        form.setContentsMargins(0, 8, 0, 0)
        form.setSpacing(12)

        self._enabled = QCheckBox("Enable the plugin platform")
        self._enabled.setChecked(self._settings.plugins.enabled)
        self._enabled.toggled.connect(
            lambda v: self._persist(
                "JARVIS_PLUGINS_ENABLED", "true" if v else "false", "plugins.enabled", v
            )
        )
        form.addRow(self._enabled)

        self._sandbox_mode = QComboBox()
        self._sandbox_mode.addItems(list(_SANDBOX_MODES))
        self._sandbox_mode.setCurrentText(self._settings.plugins.sandbox_mode)
        self._sandbox_mode.setToolTip(
            "The default tier a plugin gets when its manifest doesn't request one. "
            "A manifest can still ask for the other tier."
        )
        self._sandbox_mode.currentTextChanged.connect(
            lambda v: self._persist("JARVIS_PLUGINS_SANDBOX_MODE", v, "plugins.sandbox_mode", v)
        )
        form.addRow("Default sandbox mode", self._sandbox_mode)

        self._hook_timeout = QDoubleSpinBox()
        self._hook_timeout.setRange(0.1, 300.0)
        self._hook_timeout.setSingleStep(0.5)
        self._hook_timeout.setSuffix(" s")
        self._hook_timeout.setValue(self._settings.plugins.hook_timeout_seconds)
        self._hook_timeout.valueChanged.connect(
            lambda v: self._persist(
                "JARVIS_PLUGINS_HOOK_TIMEOUT_SECONDS",
                f"{v:.1f}",
                "plugins.hook_timeout_seconds",
                v,
            )
        )
        form.addRow("Hook timeout", self._hook_timeout)

        self._max_cpu = QDoubleSpinBox()
        self._max_cpu.setRange(1.0, 100.0)
        self._max_cpu.setSuffix(" %")
        self._max_cpu.setValue(self._settings.plugins.max_cpu_percent)
        self._max_cpu.valueChanged.connect(
            lambda v: self._persist(
                "JARVIS_PLUGINS_MAX_CPU_PERCENT", f"{v:.1f}", "plugins.max_cpu_percent", v
            )
        )
        form.addRow("CPU ceiling", self._max_cpu)

        self._max_memory = QDoubleSpinBox()
        self._max_memory.setRange(16.0, 16384.0)
        self._max_memory.setSingleStep(64.0)
        self._max_memory.setSuffix(" MB")
        self._max_memory.setValue(self._settings.plugins.max_memory_mb)
        self._max_memory.valueChanged.connect(
            lambda v: self._persist(
                "JARVIS_PLUGINS_MAX_MEMORY_MB", f"{v:.0f}", "plugins.max_memory_mb", v
            )
        )
        form.addRow("Memory ceiling", self._max_memory)

        self._allow_unsigned = QCheckBox("Allow installing unsigned packages")
        self._allow_unsigned.setChecked(self._settings.plugins.allow_unsigned_packages)
        self._allow_unsigned.setToolTip(
            "On by default because no signing authority exists yet — not because "
            "signatures don't matter."
        )
        self._allow_unsigned.toggled.connect(
            lambda v: self._persist(
                "JARVIS_PLUGINS_ALLOW_UNSIGNED_PACKAGES",
                "true" if v else "false",
                "plugins.allow_unsigned_packages",
                v,
            )
        )
        form.addRow(self._allow_unsigned)

        self._index_path = QLineEdit(self._settings.plugins.marketplace_index_path)
        self._index_path.setPlaceholderText("(none — the Marketplace tab will be empty)")
        self._index_path.editingFinished.connect(self._on_index_path)
        form.addRow("Marketplace index", self._index_path)

        self._layout.addLayout(form)

        note = QLabel(
            "Sandbox mode, resource ceilings and the marketplace index take effect the "
            "next time a plugin is loaded, not retroactively for one already running."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color:#6D8BAA;")
        self._layout.addWidget(note)

        self._layout.addStretch(1)

    def _on_index_path(self) -> None:
        value = self._index_path.text().strip()
        self._persist(
            "JARVIS_PLUGINS_MARKETPLACE_INDEX_PATH",
            value,
            "plugins.marketplace_index_path",
            value,
        )

    def _persist(self, env_key: str, env_value: str, attr_path: str, live_value: object) -> None:
        node: object = self._settings
        parts = attr_path.split(".")
        for part in parts[:-1]:
            node = getattr(node, part)
        setattr(node, parts[-1], live_value)
        fire_and_forget(self._service.set_env(env_key, env_value))
