"""Playwright browser adapter.

Lazily starts a single, long-lived Chromium/Firefox/WebKit context shared
by every ``open``/``click``/``type_text`` call -- this mirrors how a human
uses one browser window across many actions, and lets ``close_all_tabs``
mean exactly what it says.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from jarvis.core.exceptions import BrowserAutomationError
from jarvis.core.interfaces.browser import IBrowserAutomation
from jarvis.core.logging.logger import get_logger

if TYPE_CHECKING:
    from playwright.async_api import Browser, BrowserContext, Page, Playwright

    from jarvis.core.config.settings import BrowserSettings

_logger = get_logger("jarvis.infrastructure.browser")


class PlaywrightBrowser(IBrowserAutomation):
    def __init__(self, settings: BrowserSettings) -> None:
        self._settings = settings
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None

    async def start(self) -> None:
        if self._context is not None:
            return
        try:
            from playwright.async_api import async_playwright
        except ImportError as err:
            raise BrowserAutomationError(
                "playwright is not installed. Run `pip install playwright` and "
                "`playwright install` to enable browser automation."
            ) from err

        try:
            self._playwright = await async_playwright().start()
            engine = getattr(self._playwright, self._settings.engine)
            self._browser = await engine.launch(headless=self._settings.headless)
            self._context = await self._browser.new_context()
            _logger.info(
                "Playwright started (engine={}, headless={}).",
                self._settings.engine,
                self._settings.headless,
            )
        except Exception as err:
            await self.stop()
            raise BrowserAutomationError(f"Failed to start Playwright: {err}") from err

    async def stop(self) -> None:
        if self._context is not None:
            await self._context.close()
            self._context = None
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None
        _logger.info("Playwright stopped.")

    async def _active_page(self) -> Page:
        await self.start()
        assert self._context is not None
        pages = self._context.pages
        if pages:
            return pages[-1]
        return await self._context.new_page()

    async def open(self, url: str) -> None:
        page = await self._active_page()
        try:
            await page.goto(url, wait_until="domcontentloaded")
        except Exception as err:
            raise BrowserAutomationError(f"Failed to open {url!r}: {err}") from err

    async def click(self, selector: str) -> None:
        page = await self._active_page()
        try:
            await page.click(selector, timeout=10_000)
        except Exception as err:
            raise BrowserAutomationError(f"Failed to click {selector!r}: {err}") from err

    async def type_text(self, selector: str, text: str) -> None:
        page = await self._active_page()
        try:
            await page.fill(selector, text, timeout=10_000)
        except Exception as err:
            raise BrowserAutomationError(f"Failed to type into {selector!r}: {err}") from err

    async def extract_text(self, selector: str) -> str:
        page = await self._active_page()
        try:
            content = await page.text_content(selector, timeout=10_000)
            return content or ""
        except Exception as err:
            raise BrowserAutomationError(f"Failed to read {selector!r}: {err}") from err

    async def screenshot(self, output_path: str, *, full_page: bool = False) -> str:
        page = await self._active_page()
        try:
            await page.screenshot(path=output_path, full_page=full_page)
            return output_path
        except Exception as err:
            raise BrowserAutomationError(f"Failed to screenshot page: {err}") from err

    async def fill(self, selector: str, text: str) -> None:
        await self.type_text(selector, text)

    async def extract_links(self) -> list[str]:
        page = await self._active_page()
        try:
            return await page.eval_on_selector_all(
                "a[href]", "elements => elements.map(e => e.href)"
            )
        except Exception as err:
            raise BrowserAutomationError(f"Failed to extract links: {err}") from err

    async def download(self, trigger_selector: str, output_path: str) -> str:
        page = await self._active_page()
        try:
            async with page.expect_download() as download_info:
                await page.click(trigger_selector, timeout=10_000)
            download = await download_info.value
            await download.save_as(output_path)
            return output_path
        except Exception as err:
            raise BrowserAutomationError(
                f"Failed to download via {trigger_selector!r}: {err}"
            ) from err

    async def close_all_tabs(self) -> int:
        if self._context is None:
            return 0
        pages = list(self._context.pages)
        for page in pages:
            await page.close()
        return len(pages)
