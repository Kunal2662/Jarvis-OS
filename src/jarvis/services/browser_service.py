"""Browser service -- safe wrapper over the Playwright adapter."""

from __future__ import annotations

from typing import TYPE_CHECKING

from jarvis.core.logging.logger import get_logger

if TYPE_CHECKING:
    from jarvis.core.config.settings import Settings
    from jarvis.core.interfaces.browser import IBrowserAutomation

_logger = get_logger("jarvis.services.browser")


class BrowserService:
    """Thin, logged façade over :class:`IBrowserAutomation`.

    Every automation action that touches the browser (``LaunchUrlAction``,
    ``SearchGoogleAction``, ``CloseAppAction`` with ``scope="tabs"``, ...)
    goes through this service rather than the adapter directly, so this is
    the one place startup/logging/error-normalisation lives.
    """

    def __init__(self, browser: IBrowserAutomation, settings: Settings) -> None:
        self._browser = browser
        self._settings = settings

    async def open(self, url: str) -> None:
        if not self._settings.browser.enabled:
            _logger.warning("Browser automation disabled in settings; ignoring open({}).", url)
            return
        _logger.info("Opening {}", url)
        await self._browser.open(url)

    async def click(self, selector: str) -> None:
        await self._browser.click(selector)

    async def fill_form(self, selector: str, text: str) -> None:
        await self._browser.fill(selector, text)

    async def read_text(self, selector: str) -> str:
        return await self._browser.extract_text(selector)

    async def extract_links(self) -> list[str]:
        return await self._browser.extract_links()

    async def download_file(self, trigger_selector: str, output_path: str) -> str:
        return await self._browser.download(trigger_selector, output_path)

    async def take_screenshot(self, output_path: str, *, full_page: bool = False) -> str:
        return await self._browser.screenshot(output_path, full_page=full_page)

    async def close_all_tabs(self) -> int:
        closed = await self._browser.close_all_tabs()
        _logger.info("Closed {} browser tab(s).", closed)
        return closed

    async def shutdown(self) -> None:
        await self._browser.stop()
