"""Automation service -- the public facade for the AI Automation Engine.

Wires together, in order: parser -> planner -> validator -> permission ->
executor -> undo -> history -> recipes. Every other layer of the app
(voice controller, chat service, agent orchestrator, UI automation panel)
only ever talks to :class:`AutomationService`; it never touches the
parser/planner/executor classes directly.
"""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

from jarvis.core.config import paths as _paths
from jarvis.core.logging.logger import get_logger
from jarvis.domain.automation.models import PlanResult, Recipe, UndoRecord
from jarvis.features.automation.executor import ActionExecutor
from jarvis.features.automation.history import HistoryService, TaskHistoryEntry
from jarvis.features.automation.permission import ConfirmationCallback, PermissionGate
from jarvis.features.automation.planner import TaskPlanner
from jarvis.features.automation.recipes import RecipeManager
from jarvis.features.automation.undo import UndoManager
from jarvis.features.automation.validator import SafetyValidator
from jarvis.infrastructure.automation.actions.base import ActionContext

if TYPE_CHECKING:
    from jarvis.core.config.settings import Settings
    from jarvis.core.events.event_bus import EventBus
    from jarvis.core.interfaces.automation import IOSAutomation
    from jarvis.core.interfaces.database import IDatabase
    from jarvis.services.browser_service import BrowserService

_logger = get_logger("jarvis.services.automation")

_BUNDLED_RECIPES_DIR = _paths.RESOURCES_DIR / "recipes"


class AutomationService:
    def __init__(
        self,
        os_automation: IOSAutomation,
        settings: Settings,
        *,
        browser_service: BrowserService | None = None,
        database: IDatabase | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        self._settings = settings
        self._ctx = ActionContext(
            settings=settings,
            os_automation=os_automation,
            browser_service=browser_service,
            event_bus=event_bus,
        )
        self._planner = TaskPlanner(default_max_retries=settings.automation.max_retries)
        self._undo = UndoManager(max_size=settings.automation.undo_stack_size)
        self._history = HistoryService(database) if database is not None else None
        self._permission = PermissionGate(
            auto_deny_when_unconfirmable=settings.automation.auto_deny_when_unconfirmable
        )
        self._executor = ActionExecutor(
            ctx=self._ctx,
            validator=SafetyValidator(),
            permission=self._permission,
            undo=self._undo,
            history=self._history,
            event_bus=event_bus,
            retry_backoff_seconds=settings.automation.retry_backoff_seconds,
        )
        self._recipes = RecipeManager(_paths.recipes_dir(settings.resolved_data_dir))
        self._seed_bundled_recipes()

    # ------------------------------------------------------------------
    # Primary entry point
    # ------------------------------------------------------------------
    async def run_command(
        self, text: str, *, confirm: ConfirmationCallback | None = None
    ) -> PlanResult:
        """Parse, plan and execute one natural-language instruction (which
        may itself contain multiple steps, e.g. separated by "then")."""
        if not self._settings.automation.enabled:
            _logger.warning("Automation engine disabled in settings; ignoring: {}", text)
            return PlanResult(plan_id="disabled")

        plan = self._planner.build_plan(text)
        _logger.info("Built plan {} with {} step(s) from: {!r}", plan.id, len(plan.steps), text)
        return await self._executor.run_plan(plan, confirm=confirm)

    # ------------------------------------------------------------------
    # Undo
    # ------------------------------------------------------------------
    async def undo_last(self) -> UndoRecord | None:
        return await self._undo.undo_last(self._ctx)

    async def undo_step(self, step_id: str) -> bool:
        return await self._undo.undo_step(self._ctx, step_id)

    @property
    def undo_history(self) -> list[UndoRecord]:
        return self._undo.history

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------
    async def list_history(self, *, limit: int = 50) -> list[TaskHistoryEntry]:
        if self._history is None:
            return []
        return await self._history.list_recent(limit=limit)

    async def clear_history(self) -> int:
        if self._history is None:
            return 0
        return await self._history.clear()

    # ------------------------------------------------------------------
    # Recipes
    # ------------------------------------------------------------------
    def list_recipes(self) -> list[Recipe]:
        return self._recipes.list_recipes()

    def save_recipe(self, recipe: Recipe) -> None:
        self._recipes.save(recipe)

    async def run_recipe(
        self, name: str, *, confirm: ConfirmationCallback | None = None
    ) -> PlanResult:
        recipe = self._recipes.get(name)
        return await self.run_command(self._recipes.to_instruction_text(recipe), confirm=confirm)

    def _seed_bundled_recipes(self) -> None:
        """Copy any bundled example recipes into the user's recipes dir the
        first time they're missing, so a fresh install has something to run."""
        if not _BUNDLED_RECIPES_DIR.exists():
            return
        for src in _BUNDLED_RECIPES_DIR.glob("*.json"):
            dest = _paths.recipes_dir(self._settings.resolved_data_dir) / src.name
            if not dest.exists():
                try:
                    shutil.copy2(src, dest)
                except OSError as err:
                    _logger.debug("Could not seed bundled recipe {}: {}", src.name, err)

    # ------------------------------------------------------------------
    # Backward-compatible convenience wrapper (pre-Milestone-4 call sites)
    # ------------------------------------------------------------------
    async def launch(self, executable: str) -> PlanResult:
        return await self.run_command(f"open {executable}")
