"""Agent tools wrapping :class:`~jarvis.services.browser_service.BrowserService`."""

from __future__ import annotations

from typing import TYPE_CHECKING

from langchain_core.tools import BaseTool, tool

from jarvis.core.logging.logger import get_logger

if TYPE_CHECKING:
    from jarvis.services.browser_service import BrowserService

_logger = get_logger("jarvis.agents.tools.browser")

_MAX_TEXT_CHARS = 4000
_MAX_LINKS = 50


def build_browser_tools(browser: BrowserService) -> list[BaseTool]:
    @tool
    async def browse_url(url: str) -> str:
        """Open a URL in the automated browser."""
        try:
            await browser.open(url)
        except Exception as err:
            _logger.warning("browse_url tool failed: {}", err)
            return f"Failed to open {url}: {err}"
        return f"Opened {url}."

    @tool
    async def read_page_text(selector: str = "body") -> str:
        """Extract visible text from the current browser page at a CSS
        selector (defaults to the whole page body). Truncated to a few
        thousand characters."""
        try:
            text = await browser.read_text(selector)
        except Exception as err:
            _logger.warning("read_page_text tool failed: {}", err)
            return f"Failed to read page text: {err}"
        return text[:_MAX_TEXT_CHARS]

    @tool
    async def extract_page_links() -> str:
        """List hyperlinks found on the current browser page."""
        try:
            links = await browser.extract_links()
        except Exception as err:
            _logger.warning("extract_page_links tool failed: {}", err)
            return f"Failed to extract links: {err}"
        if not links:
            return "No links found."
        return "\n".join(links[:_MAX_LINKS])

    return [browse_url, read_page_text, extract_page_links]
