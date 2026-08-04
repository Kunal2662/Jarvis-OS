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
