"""Smart Lighting repository -- Milestone 12 Connectivity REST + Smart
Lighting.

One repository over ``smart_lighting_scenes``, following
``smart_home_repository.py``'s shape exactly: constructed with an
``AsyncSession``, no session or transaction management of its own (the
service owns that via ``db.session()``), ``flush()`` rather than
``commit()`` after an insert so the caller's transaction boundary stays
the caller's.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jarvis.infrastructure.database.models import LightingScene


class SceneRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, home_id: str, name: str, *, targets_json: str = "[]") -> LightingScene:
        scene = LightingScene(home_id=home_id, name=name, targets_json=targets_json)
        self._s.add(scene)
        await self._s.flush()
        return scene

    async def get(self, scene_id: str) -> LightingScene | None:
        return await self._s.get(LightingScene, scene_id)

    async def list_scenes(
        self, *, home_id: str | None = None, limit: int = 200, offset: int = 0
    ) -> list[LightingScene]:
        stmt = (
            select(LightingScene)
            .order_by(LightingScene.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if home_id is not None:
            stmt = stmt.where(LightingScene.home_id == home_id)
        return list((await self._s.execute(stmt)).scalars().all())

    async def update(
        self, scene_id: str, *, name: str | None = None, targets_json: str | None = None
    ) -> LightingScene | None:
        scene = await self.get(scene_id)
        if scene is None:
            return None
        if name is not None:
            scene.name = name
        if targets_json is not None:
            scene.targets_json = targets_json
        return scene

    async def delete(self, scene_id: str) -> bool:
        scene = await self.get(scene_id)
        if scene is None:
            return False
        await self._s.delete(scene)
        return True
