"""Finance workspace -- portfolio dashboard backed by
``MockFinanceProvider`` (Milestone 5, section 1 + future integration
interface ``IFinanceProvider``).
"""

from __future__ import annotations

import random

from PySide6.QtWidgets import QVBoxLayout, QWidget

from jarvis.features.integrations.mocks import MockFinanceProvider
from jarvis.ui.async_utils import fire_and_forget
from jarvis.ui.components import (
    ActivityFeed,
    CardGrid,
    MiniLineChart,
    QuickActionsRow,
    ScrollableColumn,
    SectionCard,
    SimpleTable,
    StatTile,
    WorkspaceHeader,
)


class FinanceWorkspace(QWidget):
    def __init__(
        self, provider: MockFinanceProvider | None = None, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._provider = provider or MockFinanceProvider()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = ScrollableColumn()
        outer.addWidget(scroll)
        column = scroll.column

        self._header = WorkspaceHeader(
            "Finance",
            subtitle="Portfolio overview · mock brokerage feed",
            status_text="Market Open",
            status_state="success",
            search_placeholder="Search holdings…",
        )
        column.addWidget(self._header)

        stats = CardGrid(columns=3)
        self._total_tile = StatTile("Total Value", "—")
        self._change_tile = StatTile("Today's Change", "—")
        self._holdings_tile = StatTile("Holdings", "—")
        for tile in (self._total_tile, self._change_tile, self._holdings_tile):
            stats.add_card(tile)
        column.addWidget(stats)

        chart_card = SectionCard("Performance (30 Days)")
        self._chart = MiniLineChart([100 + random.uniform(-4, 4) * i * 0.3 for i in range(30)])
        chart_card.body.addWidget(self._chart)
        column.addWidget(chart_card)

        holdings_card = SectionCard("Holdings")
        self._table = SimpleTable(["Symbol", "Qty", "Value", "Change %"])
        holdings_card.body.addWidget(self._table)
        column.addWidget(holdings_card)

        txn_card = SectionCard("Recent Transactions")
        self._txn_table = SimpleTable(["Type", "Symbol", "Qty", "Price"])
        txn_card.body.addWidget(self._txn_table)
        column.addWidget(txn_card)

        self._activity = ActivityFeed("Recent Activity")
        column.addWidget(self._activity)

        actions = QuickActionsRow(
            [("connect", "link", "Connect Brokerage"), ("export", "download", "Export CSV")]
        )
        column.addWidget(actions)
        column.addStretch(1)

        fire_and_forget(self._load())

    async def _load(self) -> None:
        status = await self._provider.get_connection_status()
        summary = await self._provider.get_portfolio_summary()
        holdings = await self._provider.list_holdings()
        transactions = await self._provider.list_transactions(10)
        activity = await self._provider.get_recent_activity(6)

        self._header.set_status(
            "Connected" if status.connected else "Disconnected",
            "success" if status.connected else "danger",
        )
        self._total_tile.set_value(f"₹{summary['total_value']:,.0f}")
        sign = "+" if summary["day_change_pct"] >= 0 else ""
        self._change_tile.set_value(
            f"{sign}₹{summary['day_change_value']:,.0f}",
            f"{sign}{summary['day_change_pct']:.2f}%",
            positive=summary["day_change_pct"] >= 0,
        )
        self._holdings_tile.set_value(str(len(holdings)))
        self._table.set_rows(
            [
                [h["symbol"], str(h["qty"]), f"₹{h['value']:,.0f}", f"{h['change_pct']:+.2f}%"]
                for h in holdings
            ]
        )
        self._txn_table.set_rows(
            [[t["type"], t["symbol"], str(t["qty"]), f"₹{t['price']:,.0f}"] for t in transactions]
        )
        self._activity.set_items(
            [(a.icon, a.text, a.timestamp.strftime("%H:%M")) for a in activity]
        )
