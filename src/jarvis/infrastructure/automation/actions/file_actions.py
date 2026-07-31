"""Filesystem actions.

Reversible operations (create/delete/rename/move/copy) never touch the
real OS trash; they stage removed files under
``<data_dir>/cache/automation_trash/<step_id>/`` so :meth:`undo` can move
them straight back. This keeps undo instant and OS-independent instead of
depending on a platform recycle-bin API.
"""

from __future__ import annotations

import asyncio
import shutil
import uuid
from pathlib import Path
from typing import Any

from jarvis.core.config import paths as _paths
from jarvis.domain.automation.models import ActionType, RiskLevel
from jarvis.infrastructure.automation.actions.base import ActionContext, BaseAction
from jarvis.infrastructure.automation.platform_ops import get_platform_ops

_WELL_KNOWN_DIRS = {
    "desktop": "Desktop",
    "downloads": "Downloads",
    "documents": "Documents",
    "pictures": "Pictures",
    "music": "Music",
    "videos": "Videos",
}


def resolve_path(raw: str) -> Path:
    """Resolve a spoken path fragment (``"Desktop"``, ``"report.pdf"``) to an
    absolute :class:`Path`. Bare filenames resolve relative to the user's
    home directory since that is what a voice command almost always means.
    """
    raw = raw.strip().strip('"').strip("'")
    key = raw.lower()
    if key in _WELL_KNOWN_DIRS:
        return Path.home() / _WELL_KNOWN_DIRS[key]
    candidate = Path(raw).expanduser()
    if candidate.is_absolute():
        return candidate
    # Prefer an existing relative-to-home match; otherwise still resolve
    # relative to home so "create folder Work" lands somewhere sane.
    return Path.home() / candidate


def _trash_dir(ctx: ActionContext, step_id: str) -> Path:
    trash_root = _paths.automation_trash_dir(ctx.settings.resolved_data_dir)
    d = trash_root / step_id
    d.mkdir(parents=True, exist_ok=True)
    return d


class CreateFolderAction(BaseAction):
    action_type = ActionType.CREATE_FOLDER
    risk_level = RiskLevel.SAFE
    reversible = True

    async def run(self, ctx: ActionContext, args: dict[str, Any]) -> dict[str, Any]:
        target = str(args.get("target") or "").strip()
        if not target:
            raise ValueError("create_folder requires a target folder name/path.")
        path = resolve_path(target)
        already_existed = path.exists()
        await asyncio.to_thread(path.mkdir, parents=True, exist_ok=True)
        return {
            "created": str(path),
            "undo_args": {"path": str(path), "pre_existing": already_existed},
        }

    async def undo(self, ctx: ActionContext, undo_args: dict[str, Any]) -> None:
        if undo_args.get("pre_existing"):
            return  # it already existed before us — don't delete the user's folder
        path = Path(undo_args["path"])
        if path.exists() and not any(path.iterdir()):
            await asyncio.to_thread(path.rmdir)


class DeleteFolderAction(BaseAction):
    action_type = ActionType.DELETE_FOLDER
    risk_level = RiskLevel.HIGH
    reversible = True
    requires_confirmation = True

    async def run(self, ctx: ActionContext, args: dict[str, Any]) -> dict[str, Any]:
        target = str(args.get("target") or "").strip()
        if not target:
            raise ValueError("delete_folder requires a target folder path.")
        path = resolve_path(target)
        if not path.exists():
            raise FileNotFoundError(f"{path} does not exist.")
        step_id = args.get("_step_id") or uuid.uuid4().hex
        staging = _trash_dir(ctx, step_id) / path.name
        await asyncio.to_thread(shutil.move, str(path), str(staging))
        return {
            "deleted": str(path),
            "undo_args": {"staged_at": str(staging), "original_path": str(path)},
        }

    async def undo(self, ctx: ActionContext, undo_args: dict[str, Any]) -> None:
        staged = Path(undo_args["staged_at"])
        original = Path(undo_args["original_path"])
        if staged.exists():
            await asyncio.to_thread(shutil.move, str(staged), str(original))


class RenameAction(BaseAction):
    action_type = ActionType.RENAME
    risk_level = RiskLevel.LOW
    reversible = True

    async def run(self, ctx: ActionContext, args: dict[str, Any]) -> dict[str, Any]:
        source = args.get("source") or args.get("target")
        dest_name = args.get("destination")
        if not source or not dest_name:
            raise ValueError("rename requires 'source' and 'destination'.")
        src_path = resolve_path(str(source))
        dest_path = src_path.parent / str(dest_name).strip()
        if not src_path.exists():
            raise FileNotFoundError(f"{src_path} does not exist.")
        await asyncio.to_thread(src_path.rename, dest_path)
        return {
            "renamed_to": str(dest_path),
            "undo_args": {"current_path": str(dest_path), "original_path": str(src_path)},
        }

    async def undo(self, ctx: ActionContext, undo_args: dict[str, Any]) -> None:
        current = Path(undo_args["current_path"])
        original = Path(undo_args["original_path"])
        if current.exists():
            await asyncio.to_thread(current.rename, original)


class MoveAction(BaseAction):
    action_type = ActionType.MOVE
    risk_level = RiskLevel.LOW
    reversible = True

    async def run(self, ctx: ActionContext, args: dict[str, Any]) -> dict[str, Any]:
        source = args.get("source") or args.get("target")
        destination = args.get("destination")
        if not source or not destination:
            raise ValueError("move requires 'source' and 'destination'.")
        src_path = resolve_path(str(source))
        dest_dir = resolve_path(str(destination))
        if not src_path.exists():
            raise FileNotFoundError(f"{src_path} does not exist.")
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / src_path.name
        await asyncio.to_thread(shutil.move, str(src_path), str(dest_path))
        return {
            "moved_to": str(dest_path),
            "undo_args": {"current_path": str(dest_path), "original_path": str(src_path)},
        }

    async def undo(self, ctx: ActionContext, undo_args: dict[str, Any]) -> None:
        current = Path(undo_args["current_path"])
        original = Path(undo_args["original_path"])
        if current.exists():
            await asyncio.to_thread(shutil.move, str(current), str(original))


class CopyAction(BaseAction):
    action_type = ActionType.COPY
    risk_level = RiskLevel.SAFE
    reversible = True

    async def run(self, ctx: ActionContext, args: dict[str, Any]) -> dict[str, Any]:
        source = args.get("source") or args.get("target")
        destination = args.get("destination")
        if not source or not destination:
            raise ValueError("copy requires 'source' and 'destination'.")
        src_path = resolve_path(str(source))
        dest_dir = resolve_path(str(destination))
        if not src_path.exists():
            raise FileNotFoundError(f"{src_path} does not exist.")
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / src_path.name

        def _copy() -> None:
            if src_path.is_dir():
                shutil.copytree(src_path, dest_path)
            else:
                shutil.copy2(src_path, dest_path)

        await asyncio.to_thread(_copy)
        return {"copied_to": str(dest_path), "undo_args": {"copy_path": str(dest_path)}}

    async def undo(self, ctx: ActionContext, undo_args: dict[str, Any]) -> None:
        copy_path = Path(undo_args["copy_path"])
        if copy_path.is_dir():
            await asyncio.to_thread(shutil.rmtree, copy_path, True)
        elif copy_path.exists():
            await asyncio.to_thread(copy_path.unlink)


class OpenExplorerAction(BaseAction):
    action_type = ActionType.OPEN_EXPLORER
    risk_level = RiskLevel.SAFE

    async def run(self, ctx: ActionContext, args: dict[str, Any]) -> dict[str, Any]:
        target = str(args.get("target") or str(Path.home()))
        path = resolve_path(target)
        await asyncio.to_thread(get_platform_ops().open_path, str(path))
        return {"opened_explorer_at": str(path)}


class OpenDownloadsAction(BaseAction):
    action_type = ActionType.OPEN_DOWNLOADS
    risk_level = RiskLevel.SAFE

    async def run(self, ctx: ActionContext, args: dict[str, Any]) -> dict[str, Any]:
        path = Path.home() / "Downloads"
        await asyncio.to_thread(get_platform_ops().open_path, str(path))
        return {"opened": str(path)}


class OpenDocumentsAction(BaseAction):
    action_type = ActionType.OPEN_DOCUMENTS
    risk_level = RiskLevel.SAFE

    async def run(self, ctx: ActionContext, args: dict[str, Any]) -> dict[str, Any]:
        path = Path.home() / "Documents"
        await asyncio.to_thread(get_platform_ops().open_path, str(path))
        return {"opened": str(path)}


class EmptyRecycleBinAction(BaseAction):
    action_type = ActionType.EMPTY_RECYCLE_BIN
    risk_level = RiskLevel.HIGH
    requires_confirmation = True
    reversible = False  # emptying the OS recycle bin is not reversible by us

    async def run(self, ctx: ActionContext, args: dict[str, Any]) -> dict[str, Any]:
        await asyncio.to_thread(get_platform_ops().empty_recycle_bin)
        return {"emptied": True}
