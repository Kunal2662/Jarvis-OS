"""Milestone 5 component library.

Every screen introduced by Milestone 5 (Home dashboard, Developer Mode,
API Center, Update Center, ...) is built exclusively from these building
blocks, so the whole app inherits one consistent design language instead
of each screen hand-rolling its own cards/badges/buttons.
"""

from __future__ import annotations

from jarvis.ui.components.badges import StatusBadge
from jarvis.ui.components.buttons import IconTextButton, PillButton
from jarvis.ui.components.card import Card, SectionCard, ServiceCard, StatTile
from jarvis.ui.components.charts import MiniBarChart, MiniLineChart
from jarvis.ui.components.icons import Icon, icon_registry
from jarvis.ui.components.lists import KeyValueRow, SimpleListPanel
from jarvis.ui.components.progress import LabeledProgressBar, StepProgress
from jarvis.ui.components.service_widget import ServiceWidget
from jarvis.ui.components.table import SimpleTable
from jarvis.ui.components.virtual_list import VirtualTable
from jarvis.ui.components.workspace import (
    ActivityFeed,
    CardGrid,
    EmptyState,
    ErrorState,
    LoadingState,
    QuickActionsRow,
    ScrollableColumn,
    Toolbar,
    WorkspaceHeader,
    WorkspaceStateStack,
)

__all__ = [
    "ActivityFeed",
    "Card",
    "CardGrid",
    "EmptyState",
    "ErrorState",
    "Icon",
    "IconTextButton",
    "KeyValueRow",
    "LabeledProgressBar",
    "LoadingState",
    "MiniBarChart",
    "MiniLineChart",
    "PillButton",
    "QuickActionsRow",
    "ScrollableColumn",
    "SectionCard",
    "ServiceCard",
    "ServiceWidget",
    "SimpleListPanel",
    "SimpleTable",
    "StatTile",
    "StatusBadge",
    "StepProgress",
    "Toolbar",
    "VirtualTable",
    "WorkspaceHeader",
    "WorkspaceStateStack",
    "icon_registry",
]
