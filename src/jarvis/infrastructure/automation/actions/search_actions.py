"""Search-engine actions — reuse LaunchUrlAction's browser plumbing."""

from __future__ import annotations

import asyncio
import webbrowser
from typing import Any
from urllib.parse import quote_plus

from jarvis.domain.automation.models import ActionType, RiskLevel
from jarvis.infrastructure.automation.actions.base import ActionContext, BaseAction


class SearchGoogleAction(BaseAction):
    action_type = ActionType.SEARCH_GOOGLE
    risk_level = RiskLevel.SAFE

    async def run(self, ctx: ActionContext, args: dict[str, Any]) -> dict[str, Any]:
        query = str(args.get("target") or args.get("query") or "").strip()
        if not query:
            raise ValueError("search_google requires a query.")
        url = f"https://www.google.com/search?q={quote_plus(query)}"
        if ctx.browser_service is not None:
            await ctx.browser_service.open(url)
        else:
            await asyncio.to_thread(webbrowser.open, url)
        return {"searched": query, "url": url}


class SearchYoutubeAction(BaseAction):
    action_type = ActionType.SEARCH_YOUTUBE
    risk_level = RiskLevel.SAFE

    async def run(self, ctx: ActionContext, args: dict[str, Any]) -> dict[str, Any]:
        query = str(args.get("target") or args.get("query") or "").strip()
        if not query:
            raise ValueError("search_youtube requires a query.")
        url = f"https://www.youtube.com/results?search_query={quote_plus(query)}"
        if ctx.browser_service is not None:
            await ctx.browser_service.open(url)
        else:
            await asyncio.to_thread(webbrowser.open, url)
        return {"searched": query, "url": url}
