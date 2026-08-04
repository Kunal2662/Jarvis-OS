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

    app.include_router(health_routes.router, prefix="/api")

    app.state.container = container
    if container is not None:
        from jarvis.infrastructure.api.routes import devtools as devtools_routes
        from jarvis.infrastructure.api.routes import plugins as plugin_routes
        from jarvis.infrastructure.api.routes import runtime_ws as runtime_ws_routes
        from jarvis.infrastructure.api.routes import sessions as session_routes

        app.state.runtime_ws_hub = container.runtime_ws_hub()
        app.include_router(session_routes.router, prefix="/api/v1")
        app.include_router(runtime_ws_routes.router, prefix="/api/v1")
        app.include_router(plugin_routes.router, prefix="/api/v1")
        app.include_router(devtools_routes.router, prefix="/api/v1")

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
