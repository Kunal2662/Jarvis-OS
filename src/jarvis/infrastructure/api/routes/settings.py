"""Settings API -- Milestone 8 Phase 2.

``/api/v1/settings`` -- the endpoint the React settings store reads, so
that store shows *real* configuration rather than a client-side copy of
what the defaults probably are. Phase 2's hard rule is "no fake data";
a settings screen is the easiest place in an application to break it.

Same ``Depends(get_current_session)`` Bearer auth and ``{data, meta}``
envelope as every other resource router. Owns no state and no logic.

**Read-only, deliberately.** ``SettingsService.set_env`` writes to the
``.env`` file on disk. Exposing that over HTTP would make a browser
request able to rewrite the process's own configuration -- a privilege
escalation surface that belongs with M14's Security Platform and its
Authorization Engine, not with a frontend phase whose job is to *read*
real values. The PySide6 Settings dialog keeps writing locally, where
the caller is already inside the trust boundary.

**Secrets never leave through here.** The route serves
``public_snapshot()``, never ``snapshot()``. The difference is not
cosmetic: ``integrations.clients`` holds OAuth client secrets in a plain
dict that pydantic's ``SecretStr`` redaction does not cover, so the full
snapshot would publish them verbatim. See
``services/settings_service.py`` for why redaction is by key name.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Request

from jarvis.infrastructure.api.auth import Envelope, envelope, get_current_session

if TYPE_CHECKING:
    from jarvis.services.settings_service import SettingsService

router = APIRouter(tags=["settings"], dependencies=[Depends(get_current_session)])


def _settings(request: Request) -> SettingsService:
    return cast("SettingsService", request.app.state.container.settings_service())


@router.get("/settings", response_model=Envelope[dict[str, Any]])
async def read_settings(request: Request) -> Envelope[dict[str, Any]]:
    """The whole settings tree, secrets redacted.

    One call rather than a key-at-a-time surface: the settings screen
    renders every section at once, and a request per key would be a
    hundred round trips to draw one page.
    """
    service = _settings(request)
    return envelope(
        service.public_snapshot(),
        meta={"writable_keys": service.writable_keys(), "read_only": True},
    )


@router.get("/settings/{dotted_key}", response_model=Envelope[dict[str, Any]])
async def read_setting(dotted_key: str, request: Request) -> Envelope[dict[str, Any]]:
    """One value, addressed as ``section.field`` (``ui.theme``).

    Redacted through the same path as the tree: the value is read out of
    the *public* snapshot rather than off the settings object, so a
    caller cannot use this route to fetch a single secret that the tree
    route would have hidden.
    """
    node: Any = _settings(request).public_snapshot()
    for part in dotted_key.split("."):
        if not isinstance(node, dict) or part not in node:
            raise HTTPException(status_code=404, detail=f"Unknown setting {dotted_key!r}.")
        node = node[part]
    return envelope({"key": dotted_key, "value": node})
