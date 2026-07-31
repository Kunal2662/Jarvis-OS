"""System-level actions: screenshot, clipboard, volume/brightness, power, terminal."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from jarvis.core.exceptions import ActionExecutionError
from jarvis.domain.automation.models import ActionType, RiskLevel
from jarvis.infrastructure.automation.actions.base import ActionContext, BaseAction
from jarvis.infrastructure.automation.platform_ops import get_platform_ops


def _read_clipboard() -> str:
    """Stdlib-only clipboard read via a throwaway hidden Tk root."""
    import tkinter as tk

    root = tk.Tk()
    root.withdraw()
    try:
        return root.clipboard_get()
    except tk.TclError:
        return ""
    finally:
        root.destroy()


def _write_clipboard(text: str) -> None:
    import tkinter as tk

    root = tk.Tk()
    root.withdraw()
    try:
        root.clipboard_clear()
        root.clipboard_append(text)
        root.update()  # keep the clipboard alive after the root is destroyed
    finally:
        root.destroy()


class ScreenshotAction(BaseAction):
    action_type = ActionType.SCREENSHOT
    risk_level = RiskLevel.SAFE

    async def run(self, ctx: ActionContext, args: dict[str, Any]) -> dict[str, Any]:
        out_dir = Path(ctx.settings.resolved_data_dir) / "cache" / "screenshots"
        out_dir.mkdir(parents=True, exist_ok=True)
        filename = args.get("filename") or f"screenshot_{datetime.now():%Y%m%d_%H%M%S}.png"
        out_path = str(out_dir / filename)

        # Prefer the injected OS-automation port; fall back to the platform
        # strategy (covers macOS/Linux, where IOSAutomation is a no-op).
        if getattr(ctx.os_automation, "supported", False):
            try:
                saved = await ctx.os_automation.screenshot(out_path)
                return {"saved_to": saved}
            except Exception:
                pass
        saved = await asyncio.to_thread(get_platform_ops().screenshot, out_path)
        return {"saved_to": saved}


class ClipboardCopyAction(BaseAction):
    """Sets clipboard text. Reversible — restores whatever was there before."""

    action_type = ActionType.CLIPBOARD_COPY
    risk_level = RiskLevel.SAFE
    reversible = True

    async def run(self, ctx: ActionContext, args: dict[str, Any]) -> dict[str, Any]:
        text = str(args.get("text") or args.get("target") or "")
        previous = await asyncio.to_thread(_read_clipboard)
        await asyncio.to_thread(_write_clipboard, text)
        return {"copied": text, "undo_args": {"previous_text": previous}}

    async def undo(self, ctx: ActionContext, undo_args: dict[str, Any]) -> None:
        await asyncio.to_thread(_write_clipboard, undo_args.get("previous_text", ""))


class ClipboardPasteAction(BaseAction):
    """Reads the clipboard (used by higher-level flows, not itself reversible)."""

    action_type = ActionType.CLIPBOARD_PASTE
    risk_level = RiskLevel.SAFE

    async def run(self, ctx: ActionContext, args: dict[str, Any]) -> dict[str, Any]:
        text = await asyncio.to_thread(_read_clipboard)
        return {"clipboard_text": text}


class SetVolumeAction(BaseAction):
    action_type = ActionType.SET_VOLUME
    risk_level = RiskLevel.SAFE

    async def run(self, ctx: ActionContext, args: dict[str, Any]) -> dict[str, Any]:
        level = args.get("level")
        if level is None:
            raise ValueError("set_volume requires an integer 'level' (0-100).")
        level = max(0, min(100, int(level)))
        await asyncio.to_thread(get_platform_ops().set_volume, level)
        return {"volume": level}


class MuteAction(BaseAction):
    action_type = ActionType.MUTE
    risk_level = RiskLevel.SAFE

    async def run(self, ctx: ActionContext, args: dict[str, Any]) -> dict[str, Any]:
        muted = bool(args.get("muted", True))
        await asyncio.to_thread(get_platform_ops().mute, muted)
        return {"muted": muted}


class SetBrightnessAction(BaseAction):
    action_type = ActionType.SET_BRIGHTNESS
    risk_level = RiskLevel.SAFE

    async def run(self, ctx: ActionContext, args: dict[str, Any]) -> dict[str, Any]:
        level = args.get("level")
        if level is None:
            raise ValueError("set_brightness requires an integer 'level' (0-100).")
        level = max(0, min(100, int(level)))
        await asyncio.to_thread(get_platform_ops().set_brightness, level)
        return {"brightness": level}


class ShutdownAction(BaseAction):
    action_type = ActionType.SHUTDOWN
    risk_level = RiskLevel.CRITICAL
    requires_confirmation = True
    reversible = True  # only reversible up until the delay elapses

    async def run(self, ctx: ActionContext, args: dict[str, Any]) -> dict[str, Any]:
        delay_seconds = int(args.get("delay_seconds", 0))
        await asyncio.to_thread(get_platform_ops().shutdown, delay_seconds)
        return {
            "shutdown_in_seconds": delay_seconds,
            "undo_args": {"scheduled": True},
        }

    async def undo(self, ctx: ActionContext, undo_args: dict[str, Any]) -> None:
        await asyncio.to_thread(get_platform_ops().cancel_scheduled_shutdown)


class RestartAction(BaseAction):
    action_type = ActionType.RESTART
    risk_level = RiskLevel.CRITICAL
    requires_confirmation = True
    reversible = True

    async def run(self, ctx: ActionContext, args: dict[str, Any]) -> dict[str, Any]:
        delay_seconds = int(args.get("delay_seconds", 0))
        await asyncio.to_thread(get_platform_ops().restart, delay_seconds)
        return {"restart_in_seconds": delay_seconds, "undo_args": {"scheduled": True}}

    async def undo(self, ctx: ActionContext, undo_args: dict[str, Any]) -> None:
        await asyncio.to_thread(get_platform_ops().cancel_scheduled_shutdown)


class SleepAction(BaseAction):
    action_type = ActionType.SLEEP
    risk_level = RiskLevel.MEDIUM
    requires_confirmation = True

    async def run(self, ctx: ActionContext, args: dict[str, Any]) -> dict[str, Any]:
        await asyncio.to_thread(get_platform_ops().sleep)
        return {"sleeping": True}


class LockPcAction(BaseAction):
    action_type = ActionType.LOCK_PC
    risk_level = RiskLevel.LOW

    async def run(self, ctx: ActionContext, args: dict[str, Any]) -> dict[str, Any]:
        await asyncio.to_thread(get_platform_ops().lock)
        return {"locked": True}


class OpenSettingsAction(BaseAction):
    action_type = ActionType.OPEN_SETTINGS
    risk_level = RiskLevel.SAFE

    async def run(self, ctx: ActionContext, args: dict[str, Any]) -> dict[str, Any]:
        await asyncio.to_thread(get_platform_ops().open_settings)
        return {"opened_settings": True}


class TerminalCommandAction(BaseAction):
    """Runs an arbitrary shell command.

    This is the highest-risk action in the engine: the
    :mod:`~jarvis.features.automation.validator` and
    :mod:`~jarvis.features.automation.permission` layers are the actual
    safety boundary here (deny-list + mandatory confirmation) — this class
    assumes it has already been cleared and focuses purely on execution
    with a hard timeout.
    """

    action_type = ActionType.TERMINAL_COMMAND
    risk_level = RiskLevel.HIGH
    requires_confirmation = True

    async def run(self, ctx: ActionContext, args: dict[str, Any]) -> dict[str, Any]:
        command = str(args.get("command") or args.get("target") or "").strip()
        if not command:
            raise ValueError("terminal_command requires a 'command' string.")
        timeout = float(args.get("timeout_seconds", 30))

        started = time.monotonic()
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except TimeoutError as err:
            proc.kill()
            raise ActionExecutionError(f"Command timed out after {timeout}s: {command}") from err

        duration = time.monotonic() - started
        if proc.returncode != 0:
            raise ActionExecutionError(
                f"Command exited {proc.returncode}: {stderr.decode(errors='replace').strip()}"
            )
        return {
            "command": command,
            "stdout": stdout.decode(errors="replace"),
            "duration_seconds": duration,
        }
