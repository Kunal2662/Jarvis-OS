"""Health-check endpoints — the only router implemented at Milestone 0.

Served at **both** ``/api/health`` and ``/api/v1/health`` (likewise
``/ready``). ``docs/ARCHITECTURE.md`` §5/§6 have always documented the
``/v1`` form, while this router has answered on ``/api`` since M0; the
Aug 2026 backlog pass added the documented path rather than moving the
route, because an unversioned liveness probe is exactly the URL
external monitoring is most likely to have hard-coded.

Deliberately outside the ``{data, meta}`` envelope §5 mandates for
resource routes: a liveness probe is polled by tooling that expects a
flat, minimal body, and wrapping it would buy consistency with
resources it is not one of.
"""

from __future__ import annotations

from fastapi import APIRouter

from jarvis.__version__ import __version__

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok", "version": __version__}


@router.get("/ready")
async def ready() -> dict[str, str]:
    """Readiness probe — extended in later milestones to check providers."""
    return {"status": "ready", "version": __version__}
