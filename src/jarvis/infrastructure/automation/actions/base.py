"""Base class + execution context shared by every concrete automation action."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from jarvis.domain.automation.models import ActionType, RiskLevel

if TYPE_CHECKING:
    from jarvis.core.config.settings import Settings
    from jarvis.core.events.event_bus import EventBus
    from jarvis.core.interfaces.automation import IOSAutomation
    from jarvis.services.browser_service import BrowserService


@dataclass(slots=True)
class ActionContext:
    """Everything a concrete action needs, injected once by the service layer.

    Kept deliberately small and provider-agnostic: actions never import a
    concrete adapter directly, only these ports (``os_automation``,
    ``browser_service``) plus ``settings`` for tunables like the trash dir.
    """

    settings: Settings
    os_automation: IOSAutomation
    browser_service: BrowserService | None = None
    event_bus: EventBus | None = None


class BaseAction(ABC):
    """Contract every action class implements.

    Subclasses are intentionally thin: all async I/O and subprocess calls
    happen inside :meth:`run`, and (if ``reversible``) :meth:`undo` knows
    how to reverse exactly the side effect ``run`` produced, using the
    ``undo_args`` that ``run`` returned.
    """

    action_type: ActionType
    risk_level: RiskLevel = RiskLevel.SAFE
    reversible: bool = False
    requires_confirmation: bool = False

    @abstractmethod
    async def run(self, ctx: ActionContext, args: dict[str, Any]) -> dict[str, Any]:
        """Execute the action.

        Returns a JSON-serialisable dict. If ``reversible`` is True, the
        dict **must** include an ``"undo_args"`` key with everything
        :meth:`undo` needs.
        """

    async def undo(self, ctx: ActionContext, undo_args: dict[str, Any]) -> None:
        """Reverse a previous :meth:`run` call. Only invoked when reversible."""
        raise NotImplementedError(f"{type(self).__name__} is not undoable.")
