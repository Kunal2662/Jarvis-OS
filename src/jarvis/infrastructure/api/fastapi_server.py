"""FastAPI application factory.

Kept intentionally minimal — feature milestones will register routers on
the ``routes`` package. This module is **only** responsible for:

* building the ``FastAPI`` instance,
* configuring CORS,
* mounting the routers.

No business logic — everything is delegated to services via DI.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

    from jarvis.core.config.settings import Settings


def create_app(settings: Settings) -> FastAPI:
    """Build and return the FastAPI application."""
    # Deferred import so importing this module stays cheap.
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    from jarvis.infrastructure.api.routes import health as health_routes

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url="/docs" if settings.debug else None,
        redoc_url=None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.api.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_routes.router, prefix="/api")
    return app


def run() -> None:
    """Console entry-point: run only the FastAPI server (no UI)."""
    import uvicorn

    from jarvis.core.config.settings import load_settings

    settings = load_settings()
    uvicorn.run(
        "jarvis.infrastructure.api.fastapi_server:create_app",
        factory=False,
        host=settings.api.host,
        port=settings.api.port,
        reload=settings.api.reload,
    )
