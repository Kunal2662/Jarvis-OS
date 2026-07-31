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
