"""Memory settings page — Milestone 3.

Exposes the tunables in :class:`~jarvis.core.config.settings.MemorySettings`
plus the maintenance actions (`Clear Memory`, `Export Memory`,
`Import Memory`) backed by :class:`~jarvis.services.memory_service.MemoryService`.

This page is only functional when a ``memory_service`` instance is passed
into :class:`SettingsPage` (see ``SettingsDialog``); if it's missing (e.g.
a test harness didn't wire one) the maintenance buttons are disabled but
the tunable fields still work.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
)

from jarvis.ui.dialogs.settings_pages.base import SettingsPage
from jarvis.utils.async_utils import fire_and_forget


class MemoryPage(SettingsPage):
    id = "memory"
    title = "Memory"
    category = "Memory"

    def build(self) -> None:
        title = QLabel(self.title)
        title.setStyleSheet("font-size:20px; font-weight:600;")
        self._layout.addWidget(title)

        subtitle = QLabel(
            "Semantic memory over your conversations — SQLite for facts, "
            "ChromaDB for similarity search."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color:#6D8BAA;")
        self._layout.addWidget(subtitle)

        form = QFormLayout()
        form.setContentsMargins(0, 8, 0, 0)
        form.setSpacing(12)

        self._enabled = QCheckBox("Enable memory")
        self._enabled.setChecked(self._settings.memory.enabled)
        self._enabled.toggled.connect(
            lambda v: self._persist(
                "JARVIS_MEMORY_ENABLED", "true" if v else "false", "memory.enabled", v
            )
        )
        form.addRow(self._enabled)

        self._max_memories = QSpinBox()
        self._max_memories.setRange(0, 1_000_000)
        self._max_memories.setSpecialValueText("Unlimited")
        self._max_memories.setValue(self._settings.memory.max_memories)
        self._max_memories.valueChanged.connect(self._on_max_memories)
        form.addRow("Maximum memories", self._max_memories)

        self._retention_days = QSpinBox()
        self._retention_days.setRange(0, 3650)
        self._retention_days.setSpecialValueText("Keep forever")
        self._retention_days.setValue(self._settings.memory.retention_days)
        self._retention_days.valueChanged.connect(self._on_retention_days)
        form.addRow("Retention (days)", self._retention_days)

        self._auto_summarize = QCheckBox("Auto-summarize conversations into long-term memory")
        self._auto_summarize.setChecked(self._settings.memory.auto_summarize)
        self._auto_summarize.toggled.connect(
            lambda v: self._persist(
                "JARVIS_MEMORY_AUTO_SUMMARIZE", "true" if v else "false", "memory.auto_summarize", v
            )
        )
        form.addRow(self._auto_summarize)

        self._recall_top_k = QSpinBox()
        self._recall_top_k.setRange(1, 50)
        self._recall_top_k.setValue(self._settings.memory.recall_top_k)
        self._recall_top_k.valueChanged.connect(self._on_top_k)
        form.addRow("Memories per chat turn", self._recall_top_k)

        self._recall_min_score = QDoubleSpinBox()
        self._recall_min_score.setRange(0.0, 1.0)
        self._recall_min_score.setSingleStep(0.05)
        self._recall_min_score.setValue(self._settings.memory.recall_min_score)
        self._recall_min_score.valueChanged.connect(self._on_min_score)
        form.addRow("Minimum relevance score", self._recall_min_score)

        self._layout.addLayout(form)

        # --- Stats -----------------------------------------------------
        self._stats_label = QLabel("Stats: —")
        self._stats_label.setStyleSheet("color:#6D8BAA;")
        self._layout.addWidget(self._stats_label)

        # --- Maintenance actions ----------------------------------------
        actions = QHBoxLayout()
        self._clear_btn = QPushButton("Clear Memory")
        self._clear_btn.clicked.connect(self._on_clear_clicked)
        self._export_btn = QPushButton("Export Memory…")
        self._export_btn.clicked.connect(self._on_export_clicked)
        self._import_btn = QPushButton("Import Memory…")
        self._import_btn.clicked.connect(self._on_import_clicked)
        actions.addWidget(self._clear_btn)
        actions.addWidget(self._export_btn)
        actions.addWidget(self._import_btn)
        actions.addStretch(1)
        self._layout.addLayout(actions)

        if self._memory_service is None:
            for btn in (self._clear_btn, self._export_btn, self._import_btn):
                btn.setEnabled(False)
            self._stats_label.setText("Stats unavailable (memory service not wired).")
        else:
            fire_and_forget(self._refresh_stats())

        self._layout.addStretch(1)

    # ------------------------------------------------------------------
    # Field persistence
    # ------------------------------------------------------------------
    def _persist(self, env_key: str, env_value: str, attr_path: str, live_value) -> None:
        node = self._settings
        parts = attr_path.split(".")
        for p in parts[:-1]:
            node = getattr(node, p)
        setattr(node, parts[-1], live_value)
        fire_and_forget(self._service.set_env(env_key, env_value))

    def _on_max_memories(self, value: int) -> None:
        self._persist("JARVIS_MEMORY_MAX_MEMORIES", str(value), "memory.max_memories", value)

    def _on_retention_days(self, value: int) -> None:
        self._persist("JARVIS_MEMORY_RETENTION_DAYS", str(value), "memory.retention_days", value)
        if self._memory_service is not None:
            fire_and_forget(self._do_restamp_retention())

    async def _do_restamp_retention(self) -> None:
        """Milestone 3.1 — re-stamp existing rows, then re-run policies so
        a lowered retention window archives newly-expired memories right
        away instead of waiting for the next startup/scheduled pass.
        """
        try:
            await self._memory_service.restamp_retention()
            await self._memory_service.enforce_policies()
            await self._refresh_stats()
        except Exception:
            pass

    def _on_top_k(self, value: int) -> None:
        self._persist("JARVIS_MEMORY_RECALL_TOP_K", str(value), "memory.recall_top_k", value)

    def _on_min_score(self, value: float) -> None:
        self._persist(
            "JARVIS_MEMORY_RECALL_MIN_SCORE", f"{value:.2f}", "memory.recall_min_score", value
        )

    # ------------------------------------------------------------------
    # Maintenance actions
    # ------------------------------------------------------------------
    async def _refresh_stats(self) -> None:
        try:
            stats = await self._memory_service.stats()
            self._stats_label.setText(
                f"Stats: {stats.sql_count} memories · {stats.vector_count} vectors indexed"
            )
        except Exception as err:
            self._stats_label.setText(f"Stats unavailable: {err}")

    def _on_clear_clicked(self) -> None:
        if self._memory_service is None:
            return
        confirm = QMessageBox.question(
            self,
            "Clear Memory",
            "This permanently deletes every stored memory. This cannot be undone. Continue?",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        fire_and_forget(self._do_clear())

    async def _do_clear(self) -> None:
        removed = await self._memory_service.forget_all()
        await self._refresh_stats()
        QMessageBox.information(self, "Clear Memory", f"Removed {removed} memories.")

    def _on_export_clicked(self) -> None:
        if self._memory_service is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Memory", "jarvis-memory-export.json", "JSON files (*.json)"
        )
        if not path:
            return
        fire_and_forget(self._do_export(path))

    async def _do_export(self, path: str) -> None:
        try:
            dump = await self._memory_service.export_memories()
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(dump)
            QMessageBox.information(self, "Export Memory", f"Exported to {path}")
        except Exception as err:
            QMessageBox.warning(self, "Export Memory", f"Export failed: {err}")

    def _on_import_clicked(self) -> None:
        if self._memory_service is None:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Import Memory", "", "JSON files (*.json)")
        if not path:
            return
        fire_and_forget(self._do_import(path))

    async def _do_import(self, path: str) -> None:
        try:
            with open(path, encoding="utf-8") as fh:
                data = fh.read()
            imported = await self._memory_service.import_memories(data)
            await self._refresh_stats()
            QMessageBox.information(self, "Import Memory", f"Imported {imported} memories.")
        except Exception as err:
            QMessageBox.warning(self, "Import Memory", f"Import failed: {err}")
