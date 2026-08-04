"""Plugin Marketplace Foundation + Permission Management API --
Milestone 9 Task Group E.

The real REST surface `docs/MASTER_ROADMAP.md` section 8 M9's
Developer Platform Tools module calls "the backend index/install/
uninstall API that M8's Marketplace UI renders" -- a thin FastAPI
layer over Task Group D's real domain classes
(:class:`~jarvis.core.plugins.registry.PluginRegistry`,
:class:`~jarvis.core.plugins.store.PluginStore`,
:class:`~jarvis.core.plugins.permissions.PermissionModel`,
:class:`~jarvis.core.plugins.marketplace.Marketplace`), not a
reimplementation of any of them. Every route validates shape only
(Pydantic); every real decision (install/uninstall/grant/deny) is made
by the domain layer this router calls exactly one method on.

Follows ``docs/ARCHITECTURE.md`` section 5's contract in full -- the
first real resource routes to do so since ``/api/v1/sessions``'s two
documented exceptions (see ``routes/sessions.py``): the ``{data, meta}``
envelope and ``Depends(get_current_session)`` Bearer auth on every
route.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from jarvis.infrastructure.api.auth import Envelope, envelope, get_current_session

if TYPE_CHECKING:
    from jarvis.core.plugins.marketplace import Marketplace, MarketplaceListing
    from jarvis.core.plugins.permissions import PermissionModel
    from jarvis.core.plugins.registry import PluginRegistry, PluginSnapshot
    from jarvis.core.plugins.store import PluginStore

router = APIRouter(tags=["plugins"], dependencies=[Depends(get_current_session)])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------
class PluginSnapshotResponse(BaseModel):
    plugin_id: str
    display_name: str
    version: str
    state: str
    error: str = ""
    permissions: tuple[str, ...] = ()


class PluginDetailResponse(PluginSnapshotResponse):
    healthy: bool
    health_detail: str = ""


class PermissionEntryResponse(BaseModel):
    plugin_id: str
    scope: str
    state: str


class AuditEntryResponse(BaseModel):
    plugin_id: str
    scope: str
    action: str
    at: str


class MarketplaceListingResponse(BaseModel):
    plugin_id: str
    display_name: str
    description: str
    author: str
    versions: tuple[str, ...]
    sdk_range: str = ""
    homepage: str | None = None
    category: str = "uncategorized"
    tags: tuple[str, ...] = ()


class ReviewResponse(BaseModel):
    plugin_id: str
    reviewer: str
    stars: int
    comment: str = ""
    at: str


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------
class InstallRequest(BaseModel):
    source_path: str = Field(description="A local directory or .zip package path.")


class UpdateRequest(BaseModel):
    source_path: str = Field(description="A local directory or .zip package path.")


class RateRequest(BaseModel):
    reviewer: str
    stars: int
    comment: str = ""


# ---------------------------------------------------------------------------
# Container accessors
# ---------------------------------------------------------------------------
def _plugin_registry(request: Request) -> PluginRegistry:
    return cast("PluginRegistry", request.app.state.container.plugin_registry())


def _plugin_store(request: Request) -> PluginStore:
    return cast("PluginStore", request.app.state.container.plugin_store())


def _permission_model(request: Request) -> PermissionModel:
    return cast("PermissionModel", request.app.state.container.permission_model())


def _marketplace(request: Request) -> Marketplace:
    return cast("Marketplace", request.app.state.container.marketplace())


def _to_snapshot_response(snapshot: PluginSnapshot) -> PluginSnapshotResponse:
    return PluginSnapshotResponse(
        plugin_id=snapshot.plugin_id,
        display_name=snapshot.display_name,
        version=snapshot.version,
        state=snapshot.state,
        error=snapshot.error,
        permissions=snapshot.permissions,
    )


def _require_plugin(registry: PluginRegistry, plugin_id: str) -> None:
    if not registry.is_registered(plugin_id):
        raise HTTPException(status_code=404, detail=f"Plugin {plugin_id!r} is not registered.")


# ---------------------------------------------------------------------------
# Plugin registry routes
# ---------------------------------------------------------------------------
@router.get("/plugins", response_model=Envelope[tuple[PluginSnapshotResponse, ...]])
async def list_plugins(request: Request) -> Envelope[tuple[PluginSnapshotResponse, ...]]:
    registry = _plugin_registry(request)
    snapshots = tuple(_to_snapshot_response(s) for s in registry.snapshot())
    return envelope(snapshots, meta={"count": len(snapshots)})


@router.get("/plugins/{plugin_id}", response_model=Envelope[PluginDetailResponse])
async def get_plugin(plugin_id: str, request: Request) -> Envelope[PluginDetailResponse]:
    registry = _plugin_registry(request)
    _require_plugin(registry, plugin_id)
    (snapshot,) = [s for s in registry.snapshot() if s.plugin_id == plugin_id]
    health = registry.health(plugin_id)
    detail = PluginDetailResponse(
        **_to_snapshot_response(snapshot).model_dump(),
        healthy=health.healthy,
        health_detail=health.detail,
    )
    return envelope(detail)


@router.post("/plugins/{plugin_id}/enable", response_model=Envelope[dict[str, Any]])
async def enable_plugin(plugin_id: str, request: Request) -> Envelope[dict[str, Any]]:
    registry = _plugin_registry(request)
    _require_plugin(registry, plugin_id)
    ok = await registry.enable(plugin_id)
    return envelope({"enabled": ok})


@router.post("/plugins/{plugin_id}/disable", response_model=Envelope[dict[str, Any]])
async def disable_plugin(plugin_id: str, request: Request) -> Envelope[dict[str, Any]]:
    registry = _plugin_registry(request)
    _require_plugin(registry, plugin_id)
    ok = await registry.disable(plugin_id)
    return envelope({"disabled": ok})


@router.post("/plugins/install", response_model=Envelope[dict[str, Any]], status_code=201)
async def install_plugin(body: InstallRequest, request: Request) -> Envelope[dict[str, Any]]:
    store = _plugin_store(request)
    try:
        plugin_id = await store.install(Path(body.source_path))
    except Exception as err:
        raise HTTPException(status_code=422, detail=str(err)) from err
    return envelope({"plugin_id": plugin_id})


@router.post("/plugins/{plugin_id}/uninstall", response_model=Envelope[dict[str, Any]])
async def uninstall_plugin(plugin_id: str, request: Request) -> Envelope[dict[str, Any]]:
    registry = _plugin_registry(request)
    _require_plugin(registry, plugin_id)
    ok = await registry.uninstall(plugin_id)
    return envelope({"uninstalled": ok})


@router.post("/plugins/{plugin_id}/update", response_model=Envelope[dict[str, Any]])
async def update_plugin(
    plugin_id: str, body: UpdateRequest, request: Request
) -> Envelope[dict[str, Any]]:
    store = _plugin_store(request)
    registry = _plugin_registry(request)
    _require_plugin(registry, plugin_id)
    try:
        ok = await store.update(plugin_id, Path(body.source_path))
    except Exception as err:
        raise HTTPException(status_code=422, detail=str(err)) from err
    return envelope({"updated": ok})


# ---------------------------------------------------------------------------
# Permission management routes
# ---------------------------------------------------------------------------
@router.get(
    "/plugins/{plugin_id}/permissions", response_model=Envelope[tuple[PermissionEntryResponse, ...]]
)
async def get_plugin_permissions(
    plugin_id: str, request: Request
) -> Envelope[tuple[PermissionEntryResponse, ...]]:
    registry = _plugin_registry(request)
    _require_plugin(registry, plugin_id)
    permission_model = _permission_model(request)
    (snapshot,) = [s for s in registry.snapshot() if s.plugin_id == plugin_id]
    entries = tuple(
        PermissionEntryResponse(
            plugin_id=plugin_id, scope=scope, state=permission_model.state(plugin_id, scope).value
        )
        for scope in snapshot.permissions
    )
    return envelope(entries)


@router.post(
    "/plugins/{plugin_id}/permissions/{scope}/grant", response_model=Envelope[dict[str, Any]]
)
async def grant_permission(
    plugin_id: str, scope: str, request: Request
) -> Envelope[dict[str, Any]]:
    await _permission_model(request).grant(plugin_id, scope)
    return envelope({"plugin_id": plugin_id, "scope": scope, "state": "granted"})


@router.post(
    "/plugins/{plugin_id}/permissions/{scope}/deny", response_model=Envelope[dict[str, Any]]
)
async def deny_permission(plugin_id: str, scope: str, request: Request) -> Envelope[dict[str, Any]]:
    await _permission_model(request).deny(plugin_id, scope)
    return envelope({"plugin_id": plugin_id, "scope": scope, "state": "denied"})


@router.post(
    "/plugins/{plugin_id}/permissions/{scope}/revoke", response_model=Envelope[dict[str, Any]]
)
async def revoke_permission(
    plugin_id: str, scope: str, request: Request
) -> Envelope[dict[str, Any]]:
    await _permission_model(request).revoke(plugin_id, scope)
    return envelope({"plugin_id": plugin_id, "scope": scope, "state": "pending"})


@router.get("/permissions/pending", response_model=Envelope[tuple[PermissionEntryResponse, ...]])
async def list_pending_permissions(
    request: Request,
) -> Envelope[tuple[PermissionEntryResponse, ...]]:
    permission_model = _permission_model(request)
    entries = tuple(
        PermissionEntryResponse(plugin_id=plugin_id, scope=scope, state="pending")
        for plugin_id, scope in permission_model.pending()
    )
    return envelope(entries)


@router.get("/permissions/audit-log", response_model=Envelope[tuple[AuditEntryResponse, ...]])
async def get_permission_audit_log(request: Request) -> Envelope[tuple[AuditEntryResponse, ...]]:
    permission_model = _permission_model(request)
    entries = tuple(
        AuditEntryResponse(
            plugin_id=e.plugin_id, scope=e.scope, action=e.action, at=e.at.isoformat()
        )
        for e in permission_model.audit_log
    )
    return envelope(entries, meta={"count": len(entries)})


# ---------------------------------------------------------------------------
# Marketplace routes
# ---------------------------------------------------------------------------
def _to_listing_response(listing: MarketplaceListing) -> MarketplaceListingResponse:
    return MarketplaceListingResponse(
        plugin_id=listing.plugin_id,
        display_name=listing.display_name,
        description=listing.description,
        author=listing.author,
        versions=listing.versions,
        sdk_range=listing.sdk_range,
        homepage=listing.homepage,
        category=listing.category,
        tags=listing.tags,
    )


@router.get("/marketplace", response_model=Envelope[tuple[MarketplaceListingResponse, ...]])
async def browse_marketplace(
    request: Request, category: str | None = None
) -> Envelope[tuple[MarketplaceListingResponse, ...]]:
    listings = _marketplace(request).browse(category=category)
    return envelope(tuple(_to_listing_response(listing) for listing in listings))


@router.get("/marketplace/search", response_model=Envelope[tuple[MarketplaceListingResponse, ...]])
async def search_marketplace(
    q: str, request: Request
) -> Envelope[tuple[MarketplaceListingResponse, ...]]:
    listings = _marketplace(request).search(q)
    return envelope(tuple(_to_listing_response(listing) for listing in listings))


@router.get("/marketplace/categories", response_model=Envelope[tuple[str, ...]])
async def list_marketplace_categories(request: Request) -> Envelope[tuple[str, ...]]:
    return envelope(_marketplace(request).categories())


@router.get("/marketplace/{plugin_id}", response_model=Envelope[MarketplaceListingResponse])
async def get_marketplace_listing(
    plugin_id: str, request: Request
) -> Envelope[MarketplaceListingResponse]:
    listing = _marketplace(request).get(plugin_id)
    if listing is None:
        raise HTTPException(status_code=404, detail=f"No marketplace listing for {plugin_id!r}.")
    return envelope(_to_listing_response(listing))


@router.get("/marketplace/{plugin_id}/reviews", response_model=Envelope[tuple[ReviewResponse, ...]])
async def get_marketplace_reviews(
    plugin_id: str, request: Request
) -> Envelope[tuple[ReviewResponse, ...]]:
    marketplace = _marketplace(request)
    reviews = tuple(
        ReviewResponse(
            plugin_id=r.plugin_id,
            reviewer=r.reviewer,
            stars=r.stars,
            comment=r.comment,
            at=r.at.isoformat(),
        )
        for r in marketplace.reviews_for(plugin_id)
    )
    return envelope(reviews, meta={"average_rating": marketplace.average_rating(plugin_id)})


@router.post(
    "/marketplace/{plugin_id}/reviews", response_model=Envelope[dict[str, Any]], status_code=201
)
async def rate_marketplace_plugin(
    plugin_id: str, body: RateRequest, request: Request
) -> Envelope[dict[str, Any]]:
    marketplace = _marketplace(request)
    try:
        marketplace.rate(plugin_id, body.reviewer, body.stars, body.comment)
    except ValueError as err:
        raise HTTPException(status_code=422, detail=str(err)) from err
    return envelope({"average_rating": marketplace.average_rating(plugin_id)})
