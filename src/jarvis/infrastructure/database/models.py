"""SQLAlchemy 2.x ORM models.

Milestone 1 only defines the tables it actually needs: ``conversations``
and ``messages``. Milestone 3 will extend this schema with tasks, memories,
etc. — all future models must inherit from :class:`Base` below so Alembic
picks them up automatically.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _uuid() -> str:
    return uuid4().hex


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Common declarative base — every ORM model inherits from this."""


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String(256), default="New conversation")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    messages: Mapped[list[Message]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_conv_created", "conversation_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    conversation_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # system|user|assistant|tool
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


# ---------------------------------------------------------------------------
# Milestone 3 — Semantic Memory
# ---------------------------------------------------------------------------
class Memory(Base):
    """A single semantic memory entry.

    The ``vector_id`` mirrors the row id and is used verbatim as the
    document id inside ChromaDB — keeps the two stores in lock-step so a
    row lookup by primary key resolves the vector too.
    """

    __tablename__ = "memories"
    __table_args__ = (
        Index("ix_memories_created", "created_at"),
        Index("ix_memories_source", "source"),
        Index("ix_memories_type", "memory_type"),
        Index("ix_memories_archived", "archived"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(64), default="user")
    # One of jarvis.core.types.MemoryType — kept as a plain string column
    # (not a DB enum) so new types never require a migration.
    memory_type: Mapped[str] = mapped_column(String(32), default="conversation")
    # JSON-encoded metadata; kept as text to avoid a JSON column dep on
    # the sqlite side.
    meta_json: Mapped[str] = mapped_column(Text, default="{}")
    conversation_id: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
    )
    # --- Lifecycle / memory-policy fields (Milestone 3) -----------------
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_accessed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class Tag(Base):
    """A user- or system-created tag applied to memories."""

    __tablename__ = "tags"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class MemoryTag(Base):
    """Join table between memories and tags."""

    __tablename__ = "memory_tags"

    memory_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("memories.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )


# ---------------------------------------------------------------------------
# Milestone 9 Task Group B — Session Manager
# ---------------------------------------------------------------------------
class RuntimeSession(Base):
    """A runtime session -- one connected client/runtime context (today:
    the desktop UI's own primary session; future: one per WebSocket
    connection once M9 Task Group B's Runtime WebSocket API is in use).

    Deliberately its own id space rather than reusing ``Conversation.id``
    or the agent orchestrator's LangGraph ``thread_id`` -- those model two
    different things (a saved chat history; a LangGraph checkpoint
    lineage) that a session may reference but does not replace. Both FKs
    are nullable: a session can exist before either is chosen.
    """

    __tablename__ = "runtime_sessions"
    __table_args__ = (Index("ix_runtime_sessions_closed_at", "closed_at"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    conversation_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True
    )
    # Not a FK -- AgentCheckpointer's AsyncSqliteSaver owns thread lineage
    # in its own store; this column only records which thread a session
    # was last associated with.
    thread_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    last_active_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    meta_json: Mapped[str] = mapped_column(Text, default="{}")


# ---------------------------------------------------------------------------
# Milestone 4 — AI Automation Engine
# ---------------------------------------------------------------------------
class TaskHistory(Base):
    """One executed automation step (see ``jarvis.domain.automation.TaskRecord``)."""

    __tablename__ = "automation_task_history"
    __table_args__ = (
        Index("ix_task_history_created", "created_at"),
        Index("ix_task_history_action", "action"),
        Index("ix_task_history_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    plan_id: Mapped[str] = mapped_column(String(32), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    args_json: Mapped[str] = mapped_column(Text, default="{}")
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[float] = mapped_column(default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


# ---------------------------------------------------------------------------
# Milestone 10A — Universal Search & Knowledge Platform
# ---------------------------------------------------------------------------
class KnowledgeEntity(Base):
    """A named thing (person, project, file, topic, ...) extracted from
    memory content -- the node type of the knowledge graph.

    Deliberately a plain string ``entity_type`` column, not a DB enum,
    matching ``Memory.memory_type``'s own "never requires a migration to
    add a new value" reasoning.
    """

    __tablename__ = "knowledge_entities"
    __table_args__ = (
        Index("ix_knowledge_entities_name", "name"),
        Index("ix_knowledge_entities_type", "entity_type"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(32), default="other")
    description: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(default=0.7)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class KnowledgeRelationship(Base):
    """A directed, predicated edge between two :class:`KnowledgeEntity`
    rows -- the knowledge graph's edge type.

    ``superseded`` implements Milestone 10A's correction/Learning
    Acceptance Criterion: a correction never hard-deletes the relationship
    it replaces (auditable history), it marks the old edge
    ``superseded=True`` and inserts a new one with higher confidence --
    every read path filters ``superseded=False`` by default.
    """

    __tablename__ = "knowledge_relationships"
    __table_args__ = (
        Index("ix_knowledge_rel_subject", "subject_id"),
        Index("ix_knowledge_rel_object", "object_id"),
        Index("ix_knowledge_rel_superseded", "superseded"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    subject_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("knowledge_entities.id", ondelete="CASCADE"), nullable=False
    )
    predicate: Mapped[str] = mapped_column(String(64), nullable=False)
    object_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("knowledge_entities.id", ondelete="CASCADE"), nullable=False
    )
    confidence: Mapped[float] = mapped_column(default=0.7)
    source_memory_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("memories.id", ondelete="SET NULL"), nullable=True
    )
    superseded: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class KnowledgeEntityMemory(Base):
    """Join table: which memories mention/support a knowledge entity --
    mirrors :class:`MemoryTag`'s join-table shape."""

    __tablename__ = "knowledge_entity_memories"

    entity_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("knowledge_entities.id", ondelete="CASCADE"), primary_key=True
    )
    memory_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("memories.id", ondelete="CASCADE"), primary_key=True
    )


# ---------------------------------------------------------------------------
# Milestone 10B — Intelligence Layer
# ---------------------------------------------------------------------------
class Goal(Base):
    """A user or AI-tracked goal -- Goal Manager's data model. Self-
    referential ``parent_goal_id`` gives the hierarchy the milestone's
    own Key Features list calls for; the flat CRUD + progress shape M23B's
    much larger Goal Management module later extends at full
    orchestration scale, not a competing one."""

    __tablename__ = "goals"
    __table_args__ = (
        Index("ix_goals_status", "status"),
        Index("ix_goals_parent", "parent_goal_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="active")  # active|completed|abandoned
    progress_percent: Mapped[int] = mapped_column(default=0)
    parent_goal_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("goals.id", ondelete="CASCADE"), nullable=True
    )
    target_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Routine(Base):
    """A learned recurring behavior pattern -- Routine Learning's data
    model. ``hour_of_day``/``day_of_week`` are nullable "any" wildcards
    so a routine can be as coarse as "uses this often" or as specific as
    "every Monday at 9am"; repeated observations of the same pattern
    increment ``observation_count``/``confidence`` on the existing row
    rather than creating duplicates (deduplication happens at the
    service layer, mirroring ``KnowledgeService.learn_from_text``'s own
    find-or-create pattern)."""

    __tablename__ = "routines"
    __table_args__ = (Index("ix_routines_action_type", "action_type"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    action_type: Mapped[str] = mapped_column(String(128), nullable=False)
    hour_of_day: Mapped[int | None] = mapped_column(nullable=True)
    day_of_week: Mapped[int | None] = mapped_column(nullable=True)
    observation_count: Mapped[int] = mapped_column(default=1)
    confidence: Mapped[float] = mapped_column(default=0.3)
    last_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Preference(Base):
    """A learned or explicitly-stated user preference -- Preference
    Learning's data model. Distinct from M3's freeform
    ``MemoryType.PREFERENCE`` memories (unstructured notes like "call me
    Sam"): this is a structured key/value store Predictive Suggestions
    can query by key, the capability neither M3 nor the Knowledge Graph
    already provides."""

    __tablename__ = "preferences"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(default=0.7)
    source: Mapped[str] = mapped_column(String(32), default="inferred")  # explicit|inferred
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


# ---------------------------------------------------------------------------
# Milestone 11 Task Group A — Workspace Foundation
# ---------------------------------------------------------------------------
class Workspace(Base):
    """The top-level container every later part of Milestone 11 hangs
    its data off -- Tasks, Calendar, Files and AI context all need
    somewhere to belong, and this is it.

    Deliberately *not* the M5 "workspace" concept (``ui/views/
    workspaces/``), which is a set of dashboard screens named Voice,
    Files, Browser and so on. Those are views; this is a persisted
    domain entity. The name collision is unfortunate and was inherited,
    but renaming M5's shipped views to avoid it would churn a completed
    milestone's identity for a docstring's benefit.

    ``settings_json`` holds a serialized ``WorkspaceSettings`` -- see
    ``domain/workspace/models.py`` for why preferences live in one
    JSON-text column while anything queryable stays a real column, and
    for the ``Memory.meta_json`` precedent it follows.
    """

    __tablename__ = "workspaces"
    __table_args__ = (Index("ix_workspaces_status", "status"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="active")  # active|archived
    settings_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    projects: Mapped[list[Project]] = relationship(
        back_populates="workspace",
        cascade="all, delete-orphan",
        order_by="Project.created_at",
    )
    notes: Mapped[list[Note]] = relationship(
        back_populates="workspace",
        cascade="all, delete-orphan",
        order_by="Note.created_at",
    )
    # Milestone 11 Task Group B. These three exist for the cascade, not
    # for convenience: SQLite ignores ``ON DELETE`` unless
    # ``PRAGMA foreign_keys=ON`` is set, and this application never sets
    # it -- so every ``ondelete=`` in this file is documentation of
    # intent, and the ORM-level ``cascade`` on a relationship is what
    # actually deletes children. A child table with a workspace foreign
    # key and no relationship here would silently survive its parent.
    tasks: Mapped[list[Task]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan"
    )
    calendars: Mapped[list[Calendar]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan"
    )
    reminders: Mapped[list[Reminder]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan"
    )


class Project(Base):
    """A unit of work inside a workspace.

    Flat rather than self-referential, unlike ``Goal``: a project tree
    is a feature nobody has asked for, and ``Goal`` already provides
    hierarchy for the case that wants it. Adding ``parent_project_id``
    later is additive; removing an unused hierarchy is not.
    """

    __tablename__ = "projects"
    __table_args__ = (
        Index("ix_projects_workspace", "workspace_id"),
        Index("ix_projects_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="active")  # active|completed|archived
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    workspace: Mapped[Workspace] = relationship(back_populates="projects")
    notes: Mapped[list[Note]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="Note.created_at",
    )


class Note(Base):
    """A note, belonging to a workspace and *optionally* to a project.

    ``workspace_id`` is required and ``project_id`` is not, on purpose:
    a thought worth capturing rarely arrives already filed. A note taken
    against the workspace can be moved into a project later; forcing the
    filing decision up front is how notes stop getting written.

    Deleting a project therefore cannot orphan its notes silently -- the
    service reassigns them to the workspace rather than letting the
    cascade take them, which is the one place this model's shape and the
    ORM's default disagree. See ``WorkspaceService.delete_project``.
    """

    __tablename__ = "notes"
    __table_args__ = (
        Index("ix_notes_workspace", "workspace_id"),
        Index("ix_notes_project", "project_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    content: Mapped[str] = mapped_column(Text, default="")
    content_format: Mapped[str] = mapped_column(String(16), default="markdown")  # markdown|plain
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    workspace: Mapped[Workspace] = relationship(back_populates="notes")
    project: Mapped[Project | None] = relationship(back_populates="notes")


# ---------------------------------------------------------------------------
# Milestone 11 Task Group B — Productivity Core
# ---------------------------------------------------------------------------
class Task(Base):
    """A unit of work. Shaped like ``Note``: required ``workspace_id``,
    optional ``project_id`` -- a task jotted down before it is filed is
    the normal case, and Task Group A's substrate is what makes that
    "unfiled but not homeless" state expressible.

    ``tags_json`` holds a normalized list (lower-cased, de-duplicated;
    see ``domain/productivity/models.py``). A tag table would be the
    right call once tags need their own metadata -- colour, description,
    rename-everywhere -- and none of that exists yet, so this follows
    the ``Memory.meta_json`` precedent rather than adding a join for a
    list of strings.
    """

    __tablename__ = "tasks"
    __table_args__ = (
        Index("ix_tasks_workspace", "workspace_id"),
        Index("ix_tasks_project", "project_id"),
        Index("ix_tasks_status", "status"),
        Index("ix_tasks_due", "due_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="todo")
    priority: Mapped[str] = mapped_column(String(16), default="normal")
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    tags_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    workspace: Mapped[Workspace] = relationship(back_populates="tasks")
    reminders: Mapped[list[Reminder]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )


class Calendar(Base):
    """A named container for events, scoped to a workspace.

    A separate table rather than events hanging off the workspace
    directly, because "Work" and "Personal" are the first thing anyone
    wants to toggle independently, and a colour on a calendar is what
    makes that visible. External providers (Google, Outlook) are Task
    Group E's -- this is the local engine only, and ``is_default``
    exists so a caller creating an event without naming a calendar has
    somewhere to put it.
    """

    __tablename__ = "calendars"
    __table_args__ = (Index("ix_calendars_workspace", "workspace_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    color: Mapped[str] = mapped_column(String(32), default="")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    workspace: Mapped[Workspace] = relationship(back_populates="calendars")
    events: Mapped[list[CalendarEvent]] = relationship(
        back_populates="calendar",
        cascade="all, delete-orphan",
        order_by="CalendarEvent.starts_at",
    )


class CalendarEvent(Base):
    """One event on a calendar.

    ``recurrence_json`` stores a ``RecurrenceRule`` -- the *rule*, never
    its expansion. Materializing occurrences as rows would mean a yearly
    event writes 100 rows nobody asked for, and editing the series would
    have to find and rewrite all of them. Expansion is a pure function
    over the stored rule (``RecurrenceRule.occurrences``), computed when
    a view asks for a date range.

    Deliberately no ``workspace_id``: the calendar owns that, and
    duplicating it here would create a second source of truth that can
    disagree the moment a calendar is moved. Queries that need it join
    through ``calendars``.
    """

    __tablename__ = "calendar_events"
    __table_args__ = (
        Index("ix_calendar_events_calendar", "calendar_id"),
        Index("ix_calendar_events_starts", "starts_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    calendar_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("calendars.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    location: Mapped[str] = mapped_column(String(256), default="")
    category: Mapped[str] = mapped_column(String(32), default="general")
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    all_day: Mapped[bool] = mapped_column(Boolean, default=False)
    recurrence_json: Mapped[str] = mapped_column(Text, default="{}")
    meta_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    calendar: Mapped[Calendar] = relationship(back_populates="events")
    reminders: Mapped[list[Reminder]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )


class Reminder(Base):
    """A "tell me at this time" record.

    **Scheduling metadata only.** ``remind_at`` says when it *should*
    fire and ``status`` says what has happened to it -- but nothing in
    this task group fires anything. There is no loop, no queue and no
    timer; ``status`` only ever leaves ``pending`` because a caller
    dismissed or cancelled it. Execution is M7's Scheduler (Phase 6),
    which has not shipped, and inventing a second scheduler here is
    exactly the duplication this repository has spent several milestones
    avoiding.

    ``task_id`` and ``event_id`` are both optional and both nullable: a
    reminder can stand alone, or hang off a task or an event. Two
    explicit columns rather than a polymorphic ``target_type``/
    ``target_id`` pair, because two is the whole set today and a real
    foreign key catches a dangling reference that a string pair would
    not.
    """

    __tablename__ = "reminders"
    __table_args__ = (
        Index("ix_reminders_workspace", "workspace_id"),
        Index("ix_reminders_status", "status"),
        Index("ix_reminders_remind_at", "remind_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True
    )
    event_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("calendar_events.id", ondelete="CASCADE"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="")
    remind_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    recurrence_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    workspace: Mapped[Workspace] = relationship(back_populates="reminders")
    task: Mapped[Task | None] = relationship(back_populates="reminders")
    event: Mapped[CalendarEvent | None] = relationship(back_populates="reminders")
