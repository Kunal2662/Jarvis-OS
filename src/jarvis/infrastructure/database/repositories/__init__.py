"""Repositories for ``conversations``, ``messages``, ``memories``,
the knowledge graph, the intelligence layer (goals/routines/
preferences), the workspace domain (workspaces/projects/notes), and
the productivity core (tasks/calendars/events/reminders), the file
platform (folders/files/metadata/attachments), and the AI workspace
(workspace/knowledge links)."""

from __future__ import annotations

from jarvis.infrastructure.database.repositories.ai_workspace_repository import (
    WorkspaceLinkRepository,
)
from jarvis.infrastructure.database.repositories.conversation_repository import (
    ConversationRepository,
)
from jarvis.infrastructure.database.repositories.file_repository import (
    AttachmentRepository,
    FileRepository,
    FolderRepository,
    MetadataRepository,
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
from jarvis.infrastructure.database.repositories.productivity_repository import (
    CalendarRepository,
    ReminderRepository,
    TaskRepository,
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
    "AttachmentRepository",
    "CalendarRepository",
    "ConversationRepository",
    "FileRepository",
    "FolderRepository",
    "IntelligenceRepository",
    "KnowledgeRepository",
    "MemoryRepository",
    "MessageRepository",
    "MetadataRepository",
    "NoteRepository",
    "ProjectRepository",
    "ReminderRepository",
    "RuntimeSessionRepository",
    "TaskHistoryRepository",
    "TaskRepository",
    "WorkspaceLinkRepository",
    "WorkspaceRepository",
]
