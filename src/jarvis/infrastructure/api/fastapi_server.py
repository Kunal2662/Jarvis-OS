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
    from jarvis.core.di.container import Container


def create_app(settings: Settings, container: Container | None = None) -> FastAPI:
    """Build and return the FastAPI application.

    *container* is optional only so a bare ``create_app(settings)`` stays
    cheap for callers that genuinely don't need it (e.g. a future
    health-only smoke test) -- routes that need real services
    (``/api/v1/ws``, ``/api/v1/sessions``, Milestone 9 Task Group B) are
    only mounted when a real container is supplied, since without one
    they would have nothing to relay/persist through and would become
    exactly the "placeholder implementation" this task group was asked
    not to build.
    """
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

    # Mounted twice on purpose (Aug 2026 backlog pass, closing the §15
    # "health router mount prefix mismatch" item). `docs/ARCHITECTURE.md`
    # §5/§6 have always documented `/api/v1/health`, but this router has
    # served `/api/health` since M0 and may be polled by external tooling
    # that predates the docs. Adding the documented path is additive;
    # removing the original would break those callers for no benefit, so
    # both stay live and the docs now say so.
    app.include_router(health_routes.router, prefix="/api")
    app.include_router(health_routes.router, prefix="/api/v1")

    app.state.container = container
    if container is not None:
        from jarvis.infrastructure.api.routes import agent as agent_routes
        from jarvis.infrastructure.api.routes import ai_workspace as ai_workspace_routes
        from jarvis.infrastructure.api.routes import devtools as devtools_routes
        from jarvis.infrastructure.api.routes import files as file_routes
        from jarvis.infrastructure.api.routes import intelligence as intelligence_routes
        from jarvis.infrastructure.api.routes import knowledge as knowledge_routes
        from jarvis.infrastructure.api.routes import mcp as mcp_routes
        from jarvis.infrastructure.api.routes import plugins as plugin_routes
        from jarvis.infrastructure.api.routes import productivity as productivity_routes
        from jarvis.infrastructure.api.routes import runtime_ws as runtime_ws_routes
        from jarvis.infrastructure.api.routes import sessions as session_routes
        from jarvis.infrastructure.api.routes import workspaces as workspace_routes

        app.state.runtime_ws_hub = container.runtime_ws_hub()
        app.include_router(session_routes.router, prefix="/api/v1")
        app.include_router(runtime_ws_routes.router, prefix="/api/v1")
        app.include_router(plugin_routes.router, prefix="/api/v1")
        app.include_router(devtools_routes.router, prefix="/api/v1")
        app.include_router(agent_routes.router, prefix="/api/v1")
        app.include_router(knowledge_routes.router, prefix="/api/v1")
        app.include_router(intelligence_routes.router, prefix="/api/v1")
        app.include_router(mcp_routes.router, prefix="/api/v1")
        app.include_router(workspace_routes.router, prefix="/api/v1")
        app.include_router(productivity_routes.router, prefix="/api/v1")
        app.include_router(file_routes.router, prefix="/api/v1")
        app.include_router(ai_workspace_routes.router, prefix="/api/v1")

        # Milestone 9 Task Group E -- API Inspector. A real
        # Starlette BaseHTTPMiddleware, not a decorator-based
        # ``@app.middleware("http")`` (which can't take the
        # constructor-time ``inspector`` argument cleanly); bound via
        # functools.partial so the recording logic stays owned by
        # ``core/devtools/api_inspector.py``, not duplicated here.
        if settings.devtools.api_inspector_enabled:
            import functools

            from starlette.middleware.base import BaseHTTPMiddleware

            from jarvis.core.devtools.api_inspector import api_inspector_middleware

            app.add_middleware(
                BaseHTTPMiddleware,
                dispatch=functools.partial(
                    api_inspector_middleware, inspector=container.api_inspector()
                ),
            )

    return app


def run() -> None:
    """Console entry-point: run only the FastAPI server (no UI)."""
    import uvicorn

    from jarvis.core.config.settings import load_settings
    from jarvis.core.di.container import Container

    settings = load_settings()
    container = Container()
    container.settings.override(settings)

    app = create_app(settings, container)
    uvicorn.run(
        app,
        host=settings.api.host,
        port=settings.api.port,
    )
