"""Application and URL launch/close actions."""

from __future__ import annotations

import asyncio
import webbrowser
from typing import Any

from jarvis.domain.automation.models import ActionType, RiskLevel
from jarvis.infrastructure.automation.actions.base import ActionContext, BaseAction
from jarvis.infrastructure.automation.platform_ops import get_platform_ops


class OpenAppAction(BaseAction):
    """``"Open Chrome"``, ``"Launch VS Code"``."""

    action_type = ActionType.OPEN_APP
    risk_level = RiskLevel.SAFE
    reversible = False

    async def run(self, ctx: ActionContext, args: dict[str, Any]) -> dict[str, Any]:
        name = str(args.get("target") or args.get("name") or "").strip()
        if not name:
            raise ValueError("open_app requires a target application name.")
        ops = get_platform_ops()
        await asyncio.to_thread(ops.open_app, name)
        return {"opened": name}


class CloseAppAction(BaseAction):
    """``"Close all Chrome tabs"`` maps here with ``args={"scope": "tabs"}``."""

    action_type = ActionType.CLOSE_APP
    risk_level = RiskLevel.LOW
    reversible = False

    async def run(self, ctx: ActionContext, args: dict[str, Any]) -> dict[str, Any]:
        name = str(args.get("target") or args.get("name") or "").strip()
        if not name:
            raise ValueError("close_app requires a target application name.")
        scope = args.get("scope")
        if scope == "tabs" and ctx.browser_service is not None:
            await ctx.browser_service.close_all_tabs()
            return {"closed_tabs_for": name}
        ops = get_platform_ops()
        await asyncio.to_thread(ops.close_app, name)
        return {"closed": name}


class LaunchUrlAction(BaseAction):
    """``"Open website"`` / arbitrary URL navigation."""

    action_type = ActionType.LAUNCH_URL
    risk_level = RiskLevel.SAFE
    reversible = False

    async def run(self, ctx: ActionContext, args: dict[str, Any]) -> dict[str, Any]:
        url = str(args.get("target") or args.get("url") or "").strip()
        if not url:
            raise ValueError("launch_url requires a target URL.")
        if "://" not in url:
            url = f"https://{url}"
        if ctx.browser_service is not None:
            await ctx.browser_service.open(url)
        else:
            await asyncio.to_thread(webbrowser.open, url)
        return {"opened_url": url}
