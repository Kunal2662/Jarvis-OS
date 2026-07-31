"""Initial schema — conversations, messages, memories, tags, memory_tags.

Milestone 3.1. This is the Alembic baseline: it reflects exactly what
``Base.metadata.create_all`` has been producing since Milestone 1 (chat)
and Milestone 3 (memory), so that new environments can be brought up with
``alembic upgrade head`` instead of the create_all fallback, and existing
M3-era databases can be brought under Alembic's control with a single
``alembic stamp head`` (the schema already matches — no structural change
needed for those installs).

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-07-30
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("title", sa.String(256), nullable=False, server_default="New conversation"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "messages",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.String(32),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_messages_conv_created", "messages", ["conversation_id", "created_at"]
    )

    op.create_table(
        "memories",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source", sa.String(64), nullable=False, server_default="user"),
        sa.Column("memory_type", sa.String(32), nullable=False, server_default="conversation"),
        sa.Column("meta_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column(
            "conversation_id",
            sa.String(32),
            sa.ForeignKey("conversations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("pinned", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_memories_created", "memories", ["created_at"])
    op.create_index("ix_memories_source", "memories", ["source"])
    op.create_index("ix_memories_type", "memories", ["memory_type"])
    op.create_index("ix_memories_archived", "memories", ["archived"])

    op.create_table(
        "tags",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "memory_tags",
        sa.Column(
            "memory_id",
            sa.String(32),
            sa.ForeignKey("memories.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "tag_id",
            sa.String(32),
            sa.ForeignKey("tags.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )


def downgrade() -> None:
    op.drop_table("memory_tags")
    op.drop_table("tags")
    op.drop_index("ix_memories_archived", table_name="memories")
    op.drop_index("ix_memories_type", table_name="memories")
    op.drop_index("ix_memories_source", table_name="memories")
    op.drop_index("ix_memories_created", table_name="memories")
    op.drop_table("memories")
    op.drop_index("ix_messages_conv_created", table_name="messages")
    op.drop_table("messages")
    op.drop_table("conversations")
