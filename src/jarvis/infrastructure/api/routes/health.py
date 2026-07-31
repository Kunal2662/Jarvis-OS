"""Health-check endpoints — the only router implemented at Milestone 0."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter

from jarvis.__version__ import __version__

if TYPE_CHECKING:
    pass

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok", "version": __version__}


@router.get("/ready")
async def ready() -> dict[str, str]:
    """Readiness probe — extended in later milestones to check providers."""
    return {"status": "ready", "version": __version__}
