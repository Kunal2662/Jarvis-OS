"""Tests for ``jarvis.services.browser_service.BrowserService``
(Milestone 5.5, section 4).

Zero coverage existed before this file -- a real gap for a service that
(a) is directly registered with ``RuntimeManager`` (Milestone 5.5's own
shutdown work depends on ``shutdown()`` behaving correctly) and (b) has
a real safety-relevant behavioral branch (the ``browser.enabled=False``
guard on ``open()``) that was completely unverified.
"""

from __future__ import annotations

import pytest

from jarvis.services.browser_service import BrowserService


class _FakeBrowser:
    """Implements IBrowserAutomation, tracking every call for assertions."""

    def __init__(self, *, fail_on: set[str] | None = None) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []
        self._fail_on = fail_on or set()

    def _record(self, name: str, *args, **kwargs):
        self.calls.append((name, args, kwargs))
        if name in self._fail_on:
            raise RuntimeError(f"simulated {name} failure")

    async def start(self):
        self._record("start")

    async def stop(self):
        self._record("stop")

    async def open(self, url: str):
        self._record("open", url)

    async def click(self, selector: str):
        self._record("click", selector)

    async def type_text(self, selector: str, text: str):
        self._record("type_text", selector, text)

    async def extract_text(self, selector: str) -> str:
        self._record("extract_text", selector)
        return "extracted text"

    async def screenshot(self, output_path: str, *, full_page: bool = False) -> str:
        self._record("screenshot", output_path, full_page=full_page)
        return output_path

    async def fill(self, selector: str, text: str):
        self._record("fill", selector, text)

    async def extract_links(self) -> list[str]:
        self._record("extract_links")
        return ["https://example.com"]

    async def download(self, trigger_selector: str, output_path: str) -> str:
        self._record("download", trigger_selector, output_path)
        return output_path

    async def close_all_tabs(self) -> int:
        self._record("close_all_tabs")
        return 3


def _settings(tmp_path, *, browser_enabled: bool = True):
    from jarvis.core.config.settings import Settings

    settings = Settings(data_dir=tmp_path)
    settings.browser.enabled = browser_enabled
    return settings


@pytest.mark.asyncio
async def test_open_delegates_when_browser_enabled(tmp_path) -> None:
    fake = _FakeBrowser()
    service = BrowserService(fake, _settings(tmp_path, browser_enabled=True))

    await service.open("https://example.com")

    assert fake.calls == [("open", ("https://example.com",), {})]


@pytest.mark.asyncio
async def test_open_is_a_no_op_when_browser_disabled(tmp_path) -> None:
    """Real safety-relevant behavior that had zero test coverage: if the
    user has disabled browser automation in settings, open() must not
    reach the underlying browser at all."""
    fake = _FakeBrowser()
    service = BrowserService(fake, _settings(tmp_path, browser_enabled=False))

    await service.open("https://malicious-or-unwanted.example.com")

    assert fake.calls == []  # never reached the underlying browser


@pytest.mark.asyncio
async def test_all_other_methods_delegate_regardless_of_enabled_flag(tmp_path) -> None:
    """Only open() checks the enabled flag (matches current, deliberate
    behavior -- other methods are invoked directly by automation actions
    that already checked permissions upstream). Pin this down explicitly
    so a future change to open()'s guard doesn't silently spread to
    every method without a conscious decision."""
    fake = _FakeBrowser()
    service = BrowserService(fake, _settings(tmp_path, browser_enabled=False))

    await service.click("#btn")
    await service.fill_form("#input", "hello")
    assert await service.read_text("#el") == "extracted text"
    assert await service.extract_links() == ["https://example.com"]
    assert await service.download_file("#trigger", "/tmp/out") == "/tmp/out"
    assert await service.take_screenshot("/tmp/shot.png") == "/tmp/shot.png"
    assert await service.close_all_tabs() == 3

    called_names = [c[0] for c in fake.calls]
    assert called_names == [
        "click",
        "fill",
        "extract_text",
        "extract_links",
        "download",
        "screenshot",
        "close_all_tabs",
    ]


@pytest.mark.asyncio
async def test_shutdown_delegates_to_stop(tmp_path) -> None:
    """Directly protects the RuntimeManager registration added in
    Milestone 5.5 -- confirms shutdown() actually reaches the
    underlying browser's stop(), not just that it doesn't crash."""
    fake = _FakeBrowser()
    service = BrowserService(fake, _settings(tmp_path))

    await service.shutdown()

    assert fake.calls == [("stop", (), {})]


@pytest.mark.asyncio
async def test_shutdown_failure_propagates_to_caller(tmp_path) -> None:
    """BrowserService itself doesn't swallow errors -- that's
    RuntimeManager's job (verified separately in test_runtime_manager.py).
    Confirms the propagation contract those tests rely on."""
    fake = _FakeBrowser(fail_on={"stop"})
    service = BrowserService(fake, _settings(tmp_path))

    with pytest.raises(RuntimeError, match="simulated stop failure"):
        await service.shutdown()


@pytest.mark.asyncio
async def test_close_all_tabs_returns_actual_count(tmp_path) -> None:
    fake = _FakeBrowser()
    service = BrowserService(fake, _settings(tmp_path))

    closed = await service.close_all_tabs()

    assert closed == 3
    assert fake.calls == [("close_all_tabs", (), {})]


@pytest.mark.asyncio
async def test_underlying_browser_failure_propagates_not_swallowed(tmp_path) -> None:
    """A real production failure mode: the browser process crashes
    mid-automation. BrowserService must not silently eat the error --
    the caller (automation executor, which has real retry/timeout logic)
    needs to see it."""
    fake = _FakeBrowser(fail_on={"click"})
    service = BrowserService(fake, _settings(tmp_path))

    with pytest.raises(RuntimeError, match="simulated click failure"):
        await service.click("#btn")
