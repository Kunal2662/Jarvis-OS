"""Repositories for ``conversations``, ``messages``, ``memories``,
the knowledge graph, the intelligence layer (goals/routines/
preferences), and the workspace domain (workspaces/projects/notes)."""

from __future__ import annotations

from jarvis.infrastructure.database.repositories.conversation_repository import (
    ConversationRepository,
)
from jarvis.infrastructure.database.repositories.intelligence_repository import (
    IntelligenceRepository,
)
from jarvis.infrastructure.database.repositories.knowledge_repository import (
    KnowledgeRepository,
)
from jarvis.infrastructure.database.repositories.memory_repository import (
    MemoryRepository,
)
from jarvis.infrastructure.database.repositories.message_repository import (
    MessageRepository,
)
from jarvis.infrastructure.database.repositories.runtime_session_repository import (
    RuntimeSessionRepository,
)
from jarvis.infrastructure.database.repositories.task_history_repository import (
    TaskHistoryRepository,
)
from jarvis.infrastructure.database.repositories.workspace_repository import (
    NoteRepository,
    ProjectRepository,
    WorkspaceRepository,
)

__all__ = [
    "ConversationRepository",
    "IntelligenceRepository",
    "KnowledgeRepository",
    "MemoryRepository",
    "MessageRepository",
    "NoteRepository",
    "ProjectRepository",
    "RuntimeSessionRepository",
    "TaskHistoryRepository",
    "WorkspaceRepository",
]
