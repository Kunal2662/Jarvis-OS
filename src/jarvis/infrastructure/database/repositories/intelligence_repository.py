"""Intelligence repository — CRUD over ``goals`` / ``routines`` /
``preferences`` (Milestone 10B), mirroring ``KnowledgeRepository``'s
shape."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from jarvis.infrastructure.database.models import Goal, Preference, Routine


class IntelligenceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    # ------------------------------------------------------------------
    # Goals
    # ------------------------------------------------------------------
    async def add_goal(
        self,
        title: str,
        *,
        description: str = "",
        parent_goal_id: str | None = None,
        target_date: datetime | None = None,
    ) -> Goal:
        goal = Goal(
            title=title,
            description=description,
            parent_goal_id=parent_goal_id,
            target_date=target_date,
        )
        self._s.add(goal)
        await self._s.flush()
        return goal

    async def get_goal(self, goal_id: str) -> Goal | None:
        return await self._s.get(Goal, goal_id)

    async def list_goals(self, *, status: str | None = None, limit: int = 200) -> list[Goal]:
        """Every goal regardless of hierarchy level -- use
        :meth:`list_child_goals` to list one goal's direct children."""
        stmt = select(Goal).order_by(Goal.created_at.desc()).limit(limit)
        if status is not None:
            stmt = stmt.where(Goal.status == status)
        return list((await self._s.execute(stmt)).scalars().all())

    async def list_top_level_goals(
        self, *, status: str | None = None, limit: int = 200
    ) -> list[Goal]:
        stmt = (
            select(Goal)
            .where(Goal.parent_goal_id.is_(None))
            .order_by(Goal.created_at.desc())
            .limit(limit)
        )
        if status is not None:
            stmt = stmt.where(Goal.status == status)
        return list((await self._s.execute(stmt)).scalars().all())

    async def list_child_goals(self, parent_goal_id: str) -> list[Goal]:
        stmt = (
            select(Goal)
            .where(Goal.parent_goal_id == parent_goal_id)
            .order_by(Goal.created_at.desc())
        )
        return list((await self._s.execute(stmt)).scalars().all())

    async def update_goal_progress(self, goal_id: str, progress_percent: int) -> Goal | None:
        goal = await self.get_goal(goal_id)
        if goal is None:
            return None
        goal.progress_percent = max(0, min(100, progress_percent))
        return goal

    async def set_goal_status(self, goal_id: str, status: str) -> Goal | None:
        goal = await self.get_goal(goal_id)
        if goal is None:
            return None
        goal.status = status
        if status == "completed":
            goal.completed_at = datetime.now(UTC)
            goal.progress_percent = 100
        return goal

    async def delete_goal(self, goal_id: str) -> None:
        goal = await self.get_goal(goal_id)
        if goal is not None:
            await self._s.delete(goal)

    async def count_goals(self, *, status: str | None = None) -> int:
        stmt = select(func.count()).select_from(Goal)
        if status is not None:
            stmt = stmt.where(Goal.status == status)
        return int((await self._s.execute(stmt)).scalar_one())

    async def search_goals(self, query: str, *, limit: int = 20) -> list[Goal]:
        tokens = [t for t in query.split() if t]
        if not tokens:
            return []
        clauses = [
            or_(Goal.title.ilike(f"%{t}%"), Goal.description.ilike(f"%{t}%")) for t in tokens
        ]
        stmt = select(Goal).where(or_(*clauses)).limit(limit)
        return list((await self._s.execute(stmt)).scalars().all())

    # ------------------------------------------------------------------
    # Routines
    # ------------------------------------------------------------------
    async def find_matching_routine(
        self, action_type: str, *, hour_of_day: int | None, day_of_week: int | None
    ) -> Routine | None:
        stmt = select(Routine).where(
            Routine.action_type == action_type,
            Routine.hour_of_day == hour_of_day,
            Routine.day_of_week == day_of_week,
        )
        return (await self._s.execute(stmt)).scalars().first()

    async def add_routine(
        self,
        action_type: str,
        *,
        hour_of_day: int | None,
        day_of_week: int | None,
        confidence: float = 0.3,
    ) -> Routine:
        routine = Routine(
            action_type=action_type,
            hour_of_day=hour_of_day,
            day_of_week=day_of_week,
            confidence=confidence,
        )
        self._s.add(routine)
        await self._s.flush()
        return routine

    async def reinforce_routine(self, routine_id: str, *, confidence_step: float = 0.1) -> None:
        routine = await self._s.get(Routine, routine_id)
        if routine is None:
            return
        routine.observation_count += 1
        routine.confidence = min(1.0, routine.confidence + confidence_step)
        routine.last_observed_at = datetime.now(UTC)

    async def list_routines(
        self,
        *,
        hour_of_day: int | None = None,
        day_of_week: int | None = None,
        limit: int = 200,
    ) -> list[Routine]:
        """When *hour_of_day*/*day_of_week* are given, matches routines
        pinned to that exact slot *or* wildcarded (``None``) on that
        dimension -- both count as "applies now"."""
        stmt = select(Routine).order_by(Routine.confidence.desc()).limit(limit)
        if hour_of_day is not None:
            stmt = stmt.where(
                or_(Routine.hour_of_day.is_(None), Routine.hour_of_day == hour_of_day)
            )
        if day_of_week is not None:
            stmt = stmt.where(
                or_(Routine.day_of_week.is_(None), Routine.day_of_week == day_of_week)
            )
        return list((await self._s.execute(stmt)).scalars().all())

    async def count_routines(self) -> int:
        stmt = select(func.count()).select_from(Routine)
        return int((await self._s.execute(stmt)).scalar_one())

    # ------------------------------------------------------------------
    # Preferences
    # ------------------------------------------------------------------
    async def get_preference(self, key: str) -> Preference | None:
        stmt = select(Preference).where(Preference.key == key)
        return (await self._s.execute(stmt)).scalars().first()

    async def upsert_preference(
        self, key: str, value: str, *, confidence: float = 0.7, source: str = "inferred"
    ) -> Preference:
        existing = await self.get_preference(key)
        if existing is not None:
            existing.value = value
            existing.confidence = confidence
            existing.source = source
            return existing
        pref = Preference(key=key, value=value, confidence=confidence, source=source)
        self._s.add(pref)
        await self._s.flush()
        return pref

    async def list_preferences(self, *, limit: int = 200) -> list[Preference]:
        stmt = select(Preference).order_by(Preference.updated_at.desc()).limit(limit)
        return list((await self._s.execute(stmt)).scalars().all())

    async def delete_preference(self, key: str) -> None:
        pref = await self.get_preference(key)
        if pref is not None:
            await self._s.delete(pref)

    async def count_preferences(self) -> int:
        stmt = select(func.count()).select_from(Preference)
        return int((await self._s.execute(stmt)).scalar_one())
