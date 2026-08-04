"""Workspace domain models -- Milestone 11 Task Group A.

Two value objects that are deliberately *not* ORM rows, plus the three
closed vocabularies the persisted models validate against.

**Why settings are a value object serialized into one column, rather
than columns on the table.** ``WorkspaceSettings`` is presentation and
preference — a colour, an icon, a default project. Every later task
group in this milestone (Tasks, Calendar, Files, AI context) will want
to add one, and a column per preference means a migration per
preference on a table that is not being queried by them. The precedent
is already in this schema: ``Memory.meta_json`` and
``TaskHistory.args_json`` both keep structured-but-unqueried data as
JSON text rather than paying for a JSON column dependency
(``models.py``'s own note). Anything a query needs to *filter* on --
status, name, timestamps -- stays a real column.

**Why metadata is derived and never stored.** ``WorkspaceMetadata``
counts projects and notes and reports the last activity across them.
Storing those would create a second source of truth that drifts the
moment a note is deleted through any path that forgot to decrement it —
the exact bug class this repository has spent two backlog passes
removing. It is computed on read, from the rows themselves.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

#: A workspace is either in use or put away. Deliberately not a
#: free-form string: ``list_workspaces(status=...)`` filters on it, and
#: a typo'd status would silently return nothing.
WORKSPACE_STATUSES: frozenset[str] = frozenset({"active", "archived"})

#: Project lifecycle. ``archived`` is kept distinct from ``completed``
#: because "finished" and "put away" are different answers to "why is
#: this not on my list", and a later task group's reporting will care.
PROJECT_STATUSES: frozenset[str] = frozenset({"active", "completed", "archived"})

#: How a note's body should be interpreted. Stored rather than guessed,
#: so a renderer never has to sniff content.
NOTE_FORMATS: frozenset[str] = frozenset({"markdown", "plain"})


@dataclass(frozen=True, slots=True)
class WorkspaceSettings:
    """Per-workspace preferences. Frozen, like every other value object
    in ``domain/`` -- a settings change produces a new object rather
    than mutating one another caller may be holding."""

    color: str = ""
    icon: str = ""
    default_project_id: str | None = None
    #: Room for a later task group's own preferences without a schema
    #: change. Kept explicitly separate from the named fields above so
    #: "is this a real setting or something someone stashed here" stays
    #: answerable.
    extra: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "color": self.color,
            "icon": self.icon,
            "default_project_id": self.default_project_id,
            "extra": dict(self.extra),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> WorkspaceSettings:
        """Tolerant by design: an unknown or malformed key yields the
        default rather than raising. These are preferences read on every
        workspace load, and a bad colour must not make a workspace
        unopenable."""
        payload = payload or {}
        extra = payload.get("extra")
        return cls(
            color=str(payload.get("color") or ""),
            icon=str(payload.get("icon") or ""),
            default_project_id=payload.get("default_project_id") or None,
            extra=dict(extra) if isinstance(extra, dict) else {},
        )


@dataclass(frozen=True, slots=True)
class WorkspaceMetadata:
    """Derived counts and activity for one workspace. Computed on read;
    never persisted -- see this module's docstring."""

    workspace_id: str
    project_count: int = 0
    note_count: int = 0
    active_project_count: int = 0
    last_activity_at: datetime | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "project_count": self.project_count,
            "note_count": self.note_count,
            "active_project_count": self.active_project_count,
            "last_activity_at": (
                self.last_activity_at.isoformat() if self.last_activity_at else None
            ),
        }
