"""Checkpointer lifecycle for the agent graph (Milestone 5-Agents).

``AgentSettings.checkpoint_enabled`` (already declared in
``core/config/settings.py`` since Milestone 0's scaffolding) toggles
between a real SQLite-backed checkpointer — state survives an app
restart, per the roadmap's "long-running tasks survive restarts"
acceptance criterion — and a plain in-memory one, used when persistence
is explicitly disabled or when ``langgraph-checkpoint-sqlite`` isn't
installed (degrade, don't crash).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from jarvis.core.config import paths as _paths
from jarvis.core.logging.logger import get_logger

if TYPE_CHECKING:
    from jarvis.core.config.settings import Settings

_logger = get_logger("jarvis.agents.checkpointer")


class AgentCheckpointer:
    """Owns the lifecycle of whichever LangGraph checkpoint saver is active.

    ``AsyncSqliteSaver`` is itself an async context manager wrapping one
    ``aiosqlite`` connection; this class is the thin owner that opens it
    once in :meth:`open` (called from ``AgentOrchestrator.start``) and
    closes it once in :meth:`close` (called from
    ``AgentOrchestrator.stop``, itself registered with the app's
    ``RuntimeManager`` — see ``ui/main_window.py``).
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._cm: Any | None = None
        self.saver: Any = None

    async def open(self) -> Any:
        if self.saver is not None:
            return self.saver

        if not self._settings.agent.checkpoint_enabled:
            self.saver = _memory_saver()
            _logger.info("Agent checkpointing disabled in settings; using in-memory saver.")
            return self.saver

        try:
            from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
        except ImportError:
            _logger.warning(
                "langgraph-checkpoint-sqlite not installed; agent state will not "
                "survive a restart this session. Install it (see requirements.txt) "
                "to enable persistent checkpointing."
            )
            self.saver = _memory_saver()
            return self.saver

        db_path = _paths.agent_checkpoint_db_path(self._settings.resolved_data_dir)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._cm = AsyncSqliteSaver.from_conn_string(str(db_path))
        self.saver = await self._cm.__aenter__()
        _logger.info("Agent checkpointer opened at {}.", db_path)
        return self.saver

    async def close(self) -> None:
        if self._cm is not None:
            try:
                await self._cm.__aexit__(None, None, None)
            except Exception:
                _logger.exception("Error closing agent checkpointer.")
            finally:
                self._cm = None
        self.saver = None


def _memory_saver() -> Any:
    from langgraph.checkpoint.memory import MemorySaver

    return MemorySaver()
