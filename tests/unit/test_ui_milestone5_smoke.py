"""Smoke tests -- Milestone 5 UI widgets construct without error.

These deliberately don't assert on rendered pixels (that's what "pixel
perfect" review means checking the running app, not unit tests) -- they
only guard against import errors, signal/slot typos, and constructor
crashes across the new component library, dashboard, and Developer Mode
shell. Requires ``QT_QPA_PLATFORM=offscreen`` in headless CI, which
conftest sets automatically for this module.
"""

from __future__ import annotations

import os
from datetime import UTC
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


def test_component_library_constructs(qapp) -> None:
    from jarvis.ui.components import (
        Card,
        IconTextButton,
        LabeledProgressBar,
        PillButton,
        SectionCard,
        ServiceCard,
        SimpleListPanel,
        StatTile,
        StatusBadge,
        StepProgress,
    )

    Card()
    SectionCard("Today's Schedule", action_text="View Calendar")
    ServiceCard("📧", "Gmail", "5 Unread")
    StatTile("NIFTY 50", "24,467.30", "+0.85%")
    StatusBadge("Connected", "connected")
    PillButton("📧", "Summarize my emails")
    IconTextButton("📸", "Take Screenshot")
    bar = LabeledProgressBar("Downloading")
    bar.set_progress(42)
    steps = StepProgress(["Download", "Install"])
    steps.set_status("Download", "succeeded")
    panel = SimpleListPanel()
    panel.add_row("Complete report", "", "Today", checkable=True)


def test_sidebar_has_all_official_nav_items(qapp) -> None:
    from jarvis.ui.widgets.sidebar import NAV_ITEMS, Sidebar

    sidebar = Sidebar()
    for item_id, _icon, _label in NAV_ITEMS:
        assert item_id in sidebar._buttons
    sidebar.select("chat")
    sidebar.show_update_progress(50, "Downloading")
    sidebar.hide_update_progress()


def test_home_view_constructs(qapp) -> None:
    from jarvis.ui.views.home_view import HomeView

    HomeView("Aditya")


def test_chat_page_constructs(qapp) -> None:
    from jarvis.ui.widgets.chat_page import ChatPage

    page = ChatPage()
    assert page.chat_view is not None
    assert page.prompt is not None


def test_private_transcript_dialog(qapp) -> None:
    from jarvis.ui.dialogs.private_transcript_dialog import PrivateTranscriptDialog

    dlg = PrivateTranscriptDialog()
    dlg.add_message("user", "hello")


def test_private_transcript_live_streaming_and_toolbar(qapp, tmp_path: Path) -> None:
    from jarvis.ui.dialogs.private_transcript_dialog import PrivateTranscriptDialog

    dlg = PrivateTranscriptDialog()

    # User turn (typed/voice-final) + streamed assistant reply.
    dlg.add_message("user", "What's on my calendar today?")
    dlg.begin_assistant_stream()
    dlg.append_assistant_token("You have ")
    dlg.append_assistant_token("3 meetings today.")
    dlg.end_assistant_stream()

    assert len(dlg._turns) == 2
    assert dlg._turns[0] == ("user", "What's on my calendar today?", dlg._turns[0][2])
    assert dlg._turns[1][1] == "You have 3 meetings today."

    # Search doesn't crash on hit or miss.
    dlg._search.setText("meetings")
    dlg._find_next()
    dlg._search.setText("nonexistent-query-xyz")
    dlg._find_next()

    # Copy -> clipboard contains both turns.
    dlg.copy_transcript()
    clipboard_text = qapp.clipboard().text()
    assert "What's on my calendar today?" in clipboard_text
    assert "3 meetings today." in clipboard_text

    # Export -> real file on disk with timestamped turns.
    export_path = tmp_path / "transcript.txt"
    with open(export_path, "w", encoding="utf-8") as fh:
        fh.write(dlg._as_plain_text())
    contents = export_path.read_text(encoding="utf-8")
    assert "You have 3 meetings today." in contents

    # Pinned mode resizes/repositions without crashing.
    dlg._pinned_check.setChecked(True)
    assert dlg._pinned is True
    dlg._pinned_check.setChecked(False)
    assert dlg._pinned is False

    # Always-on-top toggle.
    dlg._always_on_top_check.setChecked(False)
    assert dlg._always_on_top is False

    # Clear wipes both the view and the turn history.
    dlg.clear()
    assert dlg._turns == []


def test_update_terminal_dialog(qapp) -> None:
    from jarvis.core.events.event_bus import EventBus
    from jarvis.ui.dialogs.update_terminal_dialog import UpdateTerminalDialog

    dlg = UpdateTerminalDialog(EventBus())
    dlg.append_line("test line")
    dlg._search.setText("test")


def test_update_terminal_dock_modes_and_persistence(qapp) -> None:
    from jarvis.core.events.event_bus import EventBus
    from jarvis.ui.dialogs.update_terminal_dialog import UpdateTerminalDialog

    dlg = UpdateTerminalDialog(EventBus())
    for mode, handler in [
        ("dock_bottom", dlg._dock_bottom),
        ("dock_left", dlg._dock_left),
        ("dock_right", dlg._dock_right),
        ("float", dlg._float),
    ]:
        handler()
        assert dlg._mode == mode
        assert dlg._mode_buttons[mode].isChecked()
        # Exactly one mode button is checked at a time.
        assert sum(b.isChecked() for b in dlg._mode_buttons.values()) == 1

    dlg._dock_left()
    saved_mode = dlg._settings.value("mode")
    assert saved_mode == "dock_left"

    was_visible = dlg._body.isVisible()
    dlg._toggle_collapse()
    assert dlg._body.isVisible() != was_visible
    assert dlg._settings.value("collapsed", type=bool) == (not dlg._body.isVisible())


def test_api_center_view_seeds_builtins(qapp, tmp_path: Path) -> None:
    from jarvis.core.config.settings import Settings
    from jarvis.services.api_center_service import ApiCenterService
    from jarvis.ui.views.developer.api_center_view import ApiCenterView

    settings = Settings(data_dir=tmp_path)
    service = ApiCenterService(settings)
    view = ApiCenterView(service)
    assert view._list_layout.count() == 15  # 14 builtins + trailing stretch


def test_module_manager_expanded_view_and_registry(qapp, tmp_path: Path) -> None:
    from jarvis.core.config.settings import Settings
    from jarvis.features.modules.mock_registry import ModuleRegistryService
    from jarvis.ui.views.developer.module_manager_view import ModuleManagerView

    settings = Settings(data_dir=tmp_path)
    registry = ModuleRegistryService(settings)
    all_modules = registry.list_all()
    assert len(all_modules) >= 8
    first = all_modules[0]
    assert first.version
    assert isinstance(first.dependencies, list)

    view = ModuleManagerView(settings)
    assert view._rows_container.count() == len(all_modules)


@pytest.mark.asyncio
async def test_module_registry_enable_disable_reload_update(tmp_path: Path) -> None:
    from jarvis.core.config.settings import Settings
    from jarvis.features.modules.mock_registry import ModuleRegistryService

    settings = Settings(data_dir=tmp_path)
    registry = ModuleRegistryService(settings)
    name = "Windows Desktop Automation"

    disabled = await registry.disable(name)
    assert disabled.enabled is False
    assert disabled.status == "stopped"

    enabled = await registry.enable(name)
    assert enabled.enabled is True
    assert enabled.status == "running"

    reloaded = await registry.reload(name)
    assert reloaded.status == "running"

    result = await registry.check_update(name)
    assert result["module"] == name
    assert "update_available" in result


def test_plugin_manager_expanded_view(qapp, tmp_path: Path) -> None:
    """The view takes an injected provider now -- it no longer builds a
    mock for itself (Aug 2026 backlog pass)."""
    from jarvis.features.plugins.registry_provider import PluginRegistryProvider
    from jarvis.ui.views.developer.plugin_manager_view import PluginManagerView

    view = PluginManagerView(PluginRegistryProvider(_plugin_registry(tmp_path)))
    assert view._tabs.count() == 2
    assert view._tabs.tabText(0) == "Installed"
    assert view._tabs.tabText(1) == "Marketplace"


def _plugin_registry(tmp_path: Path):
    """A real ``PluginRegistry`` over a real on-disk plugin, built the
    same way ``tests/unit/test_plugin_registry.py`` builds one."""
    import json

    from jarvis.core.events.event_bus import EventBus
    from jarvis.core.interfaces.platform import PlatformFamily, PlatformInfo
    from jarvis.core.plugins.loader import PluginLoader
    from jarvis.core.plugins.permissions import PermissionModel
    from jarvis.core.plugins.registry import PluginRegistry
    from jarvis.core.plugins.sandbox import PluginSandbox

    class _Platform:
        def info(self) -> PlatformInfo:
            return PlatformInfo(
                family=PlatformFamily.WINDOWS,
                os_release="test",
                architecture="x86_64",
                python_version="3.13.0",
            )

        def has_capability(self, capability: str) -> bool:
            return False

        def resolve_entry_point(self, entry_point, *, default_key="default"):
            return entry_point if isinstance(entry_point, str) else entry_point.get(default_key)

    plugins_dir = tmp_path / "plugins"
    plugin_dir = plugins_dir / "demo"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "manifest.json").write_text(
        json.dumps(
            {
                "name": "demo",
                "display_name": "Demo Plugin",
                "version": "1.0.0",
                "entry_point": "plugin:HelloPlugin",
                "permissions": ["notifications"],
                "developer_metadata": {"author": "Test Author"},
            }
        ),
        encoding="utf-8",
    )
    (plugin_dir / "plugin.py").write_text(
        "class HelloPlugin:\n"
        "    async def on_load(self, context) -> None: ...\n"
        "    async def on_start(self) -> None: ...\n"
        "    async def on_stop(self) -> None: ...\n",
        encoding="utf-8",
    )

    bus = EventBus()
    return PluginRegistry(
        loader=PluginLoader(plugins_dir, platform_adapter=_Platform(), app_version="0.20.0"),
        sandbox=PluginSandbox(),
        permission_model=PermissionModel(bus, store_path=tmp_path / "permissions.json"),
        event_bus=bus,
        platform_adapter=_Platform(),
        plugin_data_root=tmp_path / "plugin-data",
    )


@pytest.mark.asyncio
async def test_registry_provider_reports_the_real_registry(tmp_path: Path) -> None:
    """The Plugin Manager's provider reads the shipped Plugin Platform.
    Before this pass it returned two invented plugins from a mock, which
    is exactly the fabricated data M8 AC2 forbids."""
    from jarvis.core.interfaces.providers import IPluginProvider
    from jarvis.features.plugins.registry_provider import PluginRegistryProvider

    registry = _plugin_registry(tmp_path)
    provider = PluginRegistryProvider(registry)
    assert isinstance(provider, IPluginProvider)

    # Nothing discovered yet -- an empty list, not invented examples.
    assert await provider.list_installed() == []

    await registry.discover_and_load_all()
    installed = await provider.list_installed()

    assert [row["id"] for row in installed] == ["demo"]
    assert installed[0]["name"] == "Demo Plugin"
    assert installed[0]["version"] == "1.0.0"
    assert installed[0]["author"] == "Test Author"
    assert installed[0]["enabled"] is True
    assert installed[0]["status"] == "enabled"


@pytest.mark.asyncio
async def test_registry_provider_performs_real_lifecycle_transitions(tmp_path: Path) -> None:
    """Enable/Disable/Reload move the *registry's* state, rather than a
    private dict the UI keeps to itself."""
    from jarvis.features.plugins.registry_provider import PluginRegistryProvider

    registry = _plugin_registry(tmp_path)
    provider = PluginRegistryProvider(registry)
    await registry.discover_and_load_all()

    assert await provider.disable("demo") is True
    assert registry.snapshot()[0].state == "disabled"
    assert (await provider.list_installed())[0]["enabled"] is False

    assert await provider.enable("demo") is True
    assert registry.snapshot()[0].state == "running"

    assert await provider.reload("demo") is True
    assert registry.snapshot()[0].state == "running"


@pytest.mark.asyncio
async def test_registry_provider_marketplace_is_empty_without_an_index(tmp_path: Path) -> None:
    """An empty catalogue is a true statement about this install;
    inventing entries to fill the tab is what the mock did wrong."""
    from jarvis.features.plugins.registry_provider import PluginRegistryProvider

    provider = PluginRegistryProvider(_plugin_registry(tmp_path))

    assert await provider.list_marketplace() == []


@pytest.mark.asyncio
async def test_registry_provider_reads_a_real_marketplace_index(tmp_path: Path) -> None:
    from jarvis.core.plugins.marketplace import MarketplaceListing
    from jarvis.features.plugins.registry_provider import PluginRegistryProvider

    class _Repo:
        def list_all(self):
            return (
                MarketplaceListing(
                    plugin_id="demo",
                    display_name="Demo",
                    description="A demo listing.",
                    author="Someone",
                    versions=("1.0.0", "1.1.0"),
                ),
            )

    from jarvis.core.plugins.marketplace import Marketplace

    provider = PluginRegistryProvider(_plugin_registry(tmp_path), Marketplace(_Repo()))
    listings = await provider.list_marketplace()

    assert [entry["id"] for entry in listings] == ["demo"]
    assert listings[0]["version"] == "1.1.0"  # newest, not the first


@pytest.mark.asyncio
async def test_registry_provider_reports_install_paths_as_unwired(tmp_path: Path) -> None:
    """The registry implements all three, but each needs a source
    directory this surface does not ask for -- so it says ``False``
    rather than guessing at one."""
    from jarvis.features.plugins.registry_provider import PluginRegistryProvider

    provider = PluginRegistryProvider(_plugin_registry(tmp_path))

    assert await provider.install("anything") is False
    assert await provider.uninstall("anything") is False
    assert await provider.update("anything") is False


def test_sidebar_update_history_row(qapp) -> None:
    from jarvis.ui.widgets.sidebar import Sidebar

    sidebar = Sidebar()
    assert sidebar._history_summary_label.text() == "No updates yet"
    assert sidebar._history_badge.isHidden() is True

    from dataclasses import dataclass
    from datetime import datetime

    @dataclass
    class _FakeSession:
        succeeded: bool | None
        to_version: str
        from_version: str
        finished_at: datetime | None
        rollback_report: object | None = None

    now = datetime.now(UTC)
    sidebar.set_update_history([_FakeSession(True, "1.1.0", "1.0.0", now)])
    assert "1.1.0" in sidebar._history_summary_label.text()
    assert sidebar._history_badge.isHidden() is True

    sidebar.set_update_history(
        [
            _FakeSession(False, "1.1.0", "1.0.0", now),
            _FakeSession(True, "1.0.0", "0.9.0", now),
        ]
    )
    assert sidebar._history_badge.isHidden() is False
    assert sidebar._history_badge.text() == "1"


@pytest.mark.asyncio
async def test_update_service_tracks_session_history(tmp_path: Path) -> None:
    from jarvis.core.config.settings import Settings
    from jarvis.services.update_service import UpdateService

    settings = Settings(data_dir=tmp_path)
    service = UpdateService(settings)

    assert service.session_history() == []
    assert service.last_successful_session() is None
    assert service.last_failed_session() is None

    session = await service.run_update()
    history = service.session_history()
    assert len(history) == 1
    assert history[0].id == session.id
    if session.succeeded:
        assert service.last_successful_session() is not None
    else:
        assert service.last_failed_session() is not None

    failed_session = await service.run_update(simulate_failure=True)
    assert failed_session.succeeded is False
    assert service.last_failed_session() is not None
    assert service.last_failed_session().id == failed_session.id
    # Rollback happens automatically on simulated failure (restore point
    # created by default), so a rollback report should be surfaced.
    assert service.last_rollback_report() is not None
    assert len(service.session_history()) == 2
    # Most-recent-first ordering.
    assert service.session_history()[0].id == failed_session.id


def test_main_window_populates_and_refreshes_update_history(qapp, tmp_path: Path) -> None:
    import asyncio

    from jarvis.core.config.settings import Settings
    from jarvis.core.di.container import Container
    from jarvis.ui.main_window import MainWindow

    asyncio.set_event_loop(asyncio.new_event_loop())

    class _Fake:
        def __getattr__(self, name):
            async def _noop(*a, **k):
                return None

            return _noop

    settings = Settings(data_dir=tmp_path)
    container = Container()
    container.settings.override(settings)
    for provider_name in (
        "llm_provider",
        "memory_service",
        "voice_service",
        "hotkey_service",
        "chat_service",
        "conversation_service",
    ):
        getattr(container, provider_name).override(_Fake())

    window = MainWindow(settings, container)
    # Populated on startup even with zero history (shouldn't crash).
    assert window._sidebar._history_summary_label.text() == "No updates yet"
    # Shortcut doesn't crash with an empty history either.
    window._show_update_history_popup()


@pytest.mark.asyncio
async def test_voice_announcement_service_covers_all_lifecycle_events(tmp_path: Path) -> None:
    from jarvis.core.config.settings import Settings
    from jarvis.domain.voice_announcements.events import AnnouncementEvent
    from jarvis.services.voice_announcement_service import VoiceAnnouncementService

    settings = Settings(data_dir=tmp_path)
    service = VoiceAnnouncementService(settings)

    for event in AnnouncementEvent:
        phrase = await service.announce_event(event)
        assert phrase, f"no phrase for {event}"

    assert len(service.history) == len(list(AnnouncementEvent))

    # Existing UpdatePhase API is untouched.
    from jarvis.domain.updates.models import UpdatePhase

    update_phrase = await service.announce(UpdatePhase.CHECKING)
    assert update_phrase


@pytest.mark.asyncio
async def test_plugin_manager_announces_enable_disable(qapp, tmp_path: Path) -> None:
    from jarvis.core.config.settings import Settings
    from jarvis.features.plugins.registry_provider import PluginRegistryProvider
    from jarvis.services.voice_announcement_service import VoiceAnnouncementService
    from jarvis.ui.views.developer.plugin_manager_view import PluginManagerView

    settings = Settings(data_dir=tmp_path)
    announcer = VoiceAnnouncementService(settings)
    registry = _plugin_registry(tmp_path)
    await registry.discover_and_load_all()
    view = PluginManagerView(PluginRegistryProvider(registry), voice_announcer=announcer)

    # A real plugin id now, and a real lifecycle transition underneath.
    await view._toggle("demo", True)
    assert any("disabled" in h.lower() for h in announcer.history)

    await view._toggle("demo", False)
    assert any("enabled" in h.lower() for h in announcer.history)


def test_theme_service_switch_no_longer_raises(tmp_path: Path) -> None:
    from jarvis.core.config.settings import Settings
    from jarvis.core.types import ThemeName
    from jarvis.services.theme_service import ThemeService

    settings = Settings(data_dir=tmp_path)
    service = ThemeService(settings)
    assert service.active() == ThemeName.JARVIS

    service.switch(ThemeName.DARK)
    assert service.active() == ThemeName.DARK
    service.switch(ThemeName.LIGHT)
    assert service.active() == ThemeName.LIGHT


def test_theme_engine_default_accent_leaves_qss_byte_identical(tmp_path: Path) -> None:
    from pathlib import Path as _Path

    from jarvis.core.config.settings import Settings
    from jarvis.core.types import ThemeName
    from jarvis.services.theme_service import ThemeService

    settings = Settings(data_dir=tmp_path)
    service = ThemeService(settings)
    for theme in ThemeName:
        raw = (_Path("resources/themes") / f"{theme.value}.qss").read_text(encoding="utf-8")
        assert service.load(theme) == raw, f"{theme} QSS changed with untouched accent"


def test_all_themes_have_visible_button_focus_indicator(tmp_path: Path) -> None:
    """Milestone 5.5 accessibility fix: previously only text inputs had
    a QSS :focus rule -- every button (sidebar nav, quick actions,
    dialogs) was invisible to keyboard-only navigation. Regression
    guard: every theme must define a QPushButton:focus rule, and it
    must actually specify a visible border (not just reset to none)."""
    from pathlib import Path as _Path

    from jarvis.core.types import ThemeName

    for theme in ThemeName:
        qss = (_Path("resources/themes") / f"{theme.value}.qss").read_text(encoding="utf-8")
        assert "QPushButton:focus" in qss, f"{theme.value} has no button focus indicator"
        # The focus rule block must include a real border declaration,
        # not just "outline: none" with nothing replacing it.
        focus_block_start = qss.index("QPushButton:focus")
        focus_block = qss[focus_block_start : focus_block_start + 200]
        assert "border:" in focus_block or "border-color:" in focus_block


def test_theme_engine_accent_override_recolors_qss(tmp_path: Path) -> None:
    from jarvis.core.config.settings import Settings
    from jarvis.core.types import ThemeName
    from jarvis.services.theme_service import ThemeService

    settings = Settings(data_dir=tmp_path)
    service = ThemeService(settings)

    service.set_accent("green")
    assert settings.ui.accent == "#3DDC97"
    recolored = service.load(ThemeName.JARVIS)
    assert "#3DDC97" in recolored
    assert "#00E5FF" not in recolored

    with pytest.raises(ValueError):
        service.set_accent("not-a-color")


def test_theme_engine_tokens_and_custom_theme_discovery(tmp_path: Path) -> None:
    from jarvis.core.config.settings import Settings
    from jarvis.services.theme_service import ThemeService

    settings = Settings(data_dir=tmp_path)
    service = ThemeService(settings)
    tokens = service.tokens()
    assert tokens.accent == settings.ui.accent
    assert tokens.border_radius_px > 0

    assert service.list_custom_themes() == []
    custom_dir = service.custom_themes_dir()
    (custom_dir / "midnight.qss").write_text("QWidget { color: white; }", encoding="utf-8")
    assert "midnight" in service.list_custom_themes()
    assert "color: white" in service.load_custom("midnight")


def test_theme_service_derives_accents_from_palette_not_duplicated_literals(tmp_path: Path) -> None:
    """Audit fix: ThemeService used to hardcode its own accent dict that
    happened to duplicate palette.py's values. Now it reads palette.py
    directly -- this test would fail if that wiring regresses."""
    from jarvis.core.types import ThemeName
    from jarvis.services.theme_service import _DEFAULT_ACCENTS
    from jarvis.ui.themes.palette import DARK_PALETTE, JARVIS_PALETTE, LIGHT_PALETTE

    assert _DEFAULT_ACCENTS[ThemeName.JARVIS] == JARVIS_PALETTE.accent
    assert _DEFAULT_ACCENTS[ThemeName.DARK] == DARK_PALETTE.accent
    assert _DEFAULT_ACCENTS[ThemeName.LIGHT] == LIGHT_PALETTE.accent


def test_theme_page_accent_swatches(qapp, tmp_path: Path) -> None:
    import asyncio

    from jarvis.core.config.settings import Settings
    from jarvis.core.di.container import Container
    from jarvis.ui.dialogs.settings_pages.theme_page import ThemePage
    from jarvis.ui.themes.theme_manager import ThemeManager

    asyncio.set_event_loop(asyncio.new_event_loop())

    settings = Settings(data_dir=tmp_path)
    container = Container()
    container.settings.override(settings)
    theme_manager = ThemeManager(container.theme_service())
    theme_manager.apply(qapp, theme=settings.ui.theme)

    page = ThemePage(settings, container.settings_service(), theme_manager)
    assert len(page._accent_buttons) >= 5
    page._on_accent_change("purple")
    assert settings.ui.accent == "#A855F7"
    assert page._accent_buttons["purple"].isChecked() is True


def test_virtual_table_handles_large_row_counts(qapp) -> None:
    from jarvis.ui.components.virtual_list import VirtualTable

    table = VirtualTable(["Col A", "Col B"])
    rows = [[f"row-{i}-a", f"row-{i}-b"] for i in range(5000)]
    table.set_rows(rows)
    assert table.row_count() == 5000
    # Model-backed: the view exists without materializing 5000 * 2
    # item objects (that's the whole point vs SimpleTable/QTableWidget).
    assert table.model().rowCount() == 5000
    assert table.model().data(table.model().index(4999, 0)) == "row-4999-a"


def test_gmail_workspace_uses_virtual_table(qapp) -> None:
    from jarvis.ui.components.virtual_list import VirtualTable
    from jarvis.ui.views.workspaces.gmail_workspace import GmailWorkspace

    workspace = GmailWorkspace()
    assert isinstance(workspace._table, VirtualTable)


@pytest.mark.asyncio
async def test_greeting_service_generates_via_llm(tmp_path: Path) -> None:
    import sys

    sys.path.insert(0, "tests")
    from fakes.fake_llm import FakeLLM
    from jarvis.core.config.settings import Settings
    from jarvis.services.greeting_service import GreetingService

    settings = Settings(data_dir=tmp_path)
    llm = FakeLLM(canned="Good morning, Aditya. Ready to pick up where we left off?")
    service = GreetingService(settings, llm)

    context = await service.build_context("Aditya", current_workspace="home")
    assert context.user_name == "Aditya"
    assert context.active_tasks or context.is_weekend  # weekday has mock tasks
    assert context.current_project == settings.app_name

    greeting = await service.generate(context)
    assert greeting == "Good morning, Aditya. Ready to pick up where we left off?"
    assert service.history == [greeting]
    # The context sent to the LLM actually included the gathered signals.
    sent = llm.calls[-1]
    assert any("Aditya" in m.content for m in sent)


@pytest.mark.asyncio
async def test_greeting_service_falls_back_when_llm_unavailable(tmp_path: Path) -> None:
    import sys

    sys.path.insert(0, "tests")
    from fakes.fake_llm import FakeLLM
    from jarvis.core.config.settings import Settings
    from jarvis.services.greeting_service import GreetingService

    settings = Settings(data_dir=tmp_path)
    failing_llm = FakeLLM(fail=True)
    service = GreetingService(settings, failing_llm)
    context = await service.build_context("Aditya")

    greeting = await service.generate(context)
    assert greeting  # never empty/silent even when the LLM call fails
    assert "Aditya" in greeting

    # No LLM configured at all still produces a greeting.
    service2 = GreetingService(settings, None)
    context2 = await service2.build_context("Aditya")
    greeting2 = await service2.generate(context2)
    assert greeting2


@pytest.mark.asyncio
async def test_greeting_service_avoids_immediate_repeats(tmp_path: Path) -> None:
    from jarvis.core.config.settings import Settings
    from jarvis.services.greeting_service import GreetingService

    settings = Settings(data_dir=tmp_path)
    service = GreetingService(settings, None)  # fallback-only path

    seen: set[str] = set()
    for _ in range(10):
        context = await service.build_context("Aditya")
        greeting = await service.generate(context)
        seen.add(greeting)
    # Not a hard guarantee of zero repeats (finite template pool), but a
    # single fixed greeting every time would be exactly the "never use
    # fixed greetings" failure the brief calls out.
    assert len(seen) > 1


@pytest.mark.asyncio
async def test_greeting_history_persists_across_service_instances(tmp_path: Path) -> None:
    from jarvis.core.config.settings import Settings
    from jarvis.services.greeting_service import GreetingService

    settings = Settings(data_dir=tmp_path)
    service1 = GreetingService(settings, None)
    context = await service1.build_context("Aditya")
    greeting = await service1.generate(context)

    # A fresh instance (simulating app restart) loads the same history
    # from disk, so "never repeat frequently" holds across restarts.
    service2 = GreetingService(settings, None)
    assert greeting in service2.history

    history_file = settings.resolved_data_dir / "greeting_history.json"
    assert history_file.is_file()


def test_home_view_set_greeting_replaces_header_text(qapp) -> None:
    from jarvis.ui.views.home_view import HomeView

    view = HomeView("Aditya")
    view.set_greeting("Good evening, Aditya. Your workspace is ready.")
    assert view._greeting_title.text() == "Good evening, Aditya. Your workspace is ready."


def test_greeting_service_registered_in_container(tmp_path: Path) -> None:
    from jarvis.core.config.settings import Settings
    from jarvis.core.di.container import Container

    settings = Settings(data_dir=tmp_path)
    container = Container()
    container.settings.override(settings)
    service = container.greeting_service()
    assert service is not None
    # Singleton -- same instance every call, so history accumulates correctly.
    assert container.greeting_service() is service


def test_main_window_calls_greet_user_on_start(qapp, tmp_path: Path) -> None:
    import asyncio

    from jarvis.core.config.settings import Settings
    from jarvis.core.di.container import Container
    from jarvis.ui.main_window import MainWindow

    asyncio.set_event_loop(asyncio.new_event_loop())

    class _Fake:
        def __getattr__(self, name):
            async def _noop(*a, **k):
                return None

            return _noop

    settings = Settings(data_dir=tmp_path)
    container = Container()
    container.settings.override(settings)
    for provider_name in (
        "llm_provider",
        "memory_service",
        "voice_service",
        "hotkey_service",
        "chat_service",
        "conversation_service",
    ):
        getattr(container, provider_name).override(_Fake())

    window = MainWindow(settings, container)
    assert window._user_name == "Aditya"

    loop = asyncio.get_event_loop()
    loop.run_until_complete(window._greet_user())
    # The default time-of-day greeting should have been replaced.
    assert window._home_view._greeting_title.text() != ""
    history_file = settings.resolved_data_dir / "greeting_history.json"
    assert history_file.is_file()


def test_main_window_close_event_routes_through_graceful_shutdown(qapp, tmp_path: Path) -> None:
    """Milestone 5.5 reliability fix: closing the window via closeEvent
    (OS X button / Alt+F4) used to bypass _graceful_quit() entirely and
    just stop the loop directly. It must now go through the same
    cleanup path the tray/menu Quit action uses."""
    import asyncio

    from PySide6.QtGui import QCloseEvent

    from jarvis.core.config.settings import Settings
    from jarvis.core.di.container import Container
    from jarvis.ui.main_window import MainWindow

    asyncio.set_event_loop(asyncio.new_event_loop())

    class _Fake:
        def __getattr__(self, name):
            async def _noop(*a, **k):
                return None

            return _noop

    settings = Settings(data_dir=tmp_path)
    container = Container()
    container.settings.override(settings)
    for provider_name in (
        "llm_provider",
        "memory_service",
        "voice_service",
        "hotkey_service",
        "chat_service",
        "conversation_service",
        "browser_service",
        "database",
    ):
        getattr(container, provider_name).override(_Fake())

    window = MainWindow(settings, container)
    assert window._shutting_down is False

    graceful_quit_called = {"count": 0}
    original = window._graceful_quit

    async def _tracked_graceful_quit():
        graceful_quit_called["count"] += 1
        # Don't actually run the full cleanup chain (needs a real loop
        # tick per fire_and_forget); just confirm it was reached and
        # that the guard flag was set before this ran.
        assert window._shutting_down is True

    window._graceful_quit = _tracked_graceful_quit

    event = QCloseEvent()
    window.closeEvent(event)

    # First close request must be ignored (deferred to async cleanup),
    # not accepted immediately -- otherwise Qt would tear the window
    # down before _graceful_quit() ever got a chance to run.
    assert event.isAccepted() is False
    assert window._shutting_down is True

    # Let the fire_and_forget task actually run.
    loop = asyncio.get_event_loop()
    loop.run_until_complete(asyncio.sleep(0.05))
    assert graceful_quit_called["count"] == 1

    window._graceful_quit = original


def test_main_window_registers_shutdown_hooks_in_correct_order(qapp, tmp_path: Path) -> None:
    """Milestone 5.5: shutdown sequencing now lives in RuntimeManager
    (Milestone 5.5's ShutdownManager, generalized under Milestone 9),
    registered declaratively by MainWindow instead of hand-sequenced
    inline in _graceful_quit. Verify the registration itself, not just
    the end-to-end effect (covered by the other two shutdown tests)."""
    from jarvis.core.config.settings import Settings
    from jarvis.core.di.container import Container
    from jarvis.ui.main_window import MainWindow

    class _Fake:
        def __getattr__(self, name):
            async def _noop(*a, **k):
                return None

            return _noop

    settings = Settings(data_dir=tmp_path)
    container = Container()
    container.settings.override(settings)
    for provider_name in (
        "llm_provider",
        "memory_service",
        "voice_service",
        "hotkey_service",
        "chat_service",
        "conversation_service",
        "browser_service",
        "database",
    ):
        getattr(container, provider_name).override(_Fake())

    # Keep a reference (even though unused) rather than a bare expression --
    # PySide6 widget lifetime should stay explicit rather than implicit.
    _window = MainWindow(settings, container)
    manager = container.runtime_manager()

    # Announce-shutdown must run first (voice needs to still be fully up),
    # database must run last (the most "final" resource) -- preserving
    # the exact sequence this app always shut down in.
    assert manager.registered_names[0] == "voice_announcement"
    assert manager.registered_names[-1] == "database"
    assert set(manager.registered_names) == {
        "voice_announcement",
        "voice_service",
        "agent_orchestrator",
        "browser_service",
        "hotkey_service",
        "database",
    }


def test_main_window_graceful_quit_releases_all_resources(qapp, tmp_path: Path) -> None:
    """Milestone 5.5 reliability fix: _graceful_quit() must actually call
    browser_service.shutdown() and database.dispose() (previously never
    called anywhere -- a real resource leak), stop voice
    listening/speaking/wake-word, and do all of it independently -- one
    resource failing to clean up must not block the others."""
    import asyncio

    from jarvis.core.config.settings import Settings
    from jarvis.core.di.container import Container
    from jarvis.ui.main_window import MainWindow

    asyncio.set_event_loop(asyncio.new_event_loop())

    calls: list[str] = []

    class _Fake:
        def __getattr__(self, name):
            async def _noop(*a, **k):
                calls.append(name)

            return _noop

    class _FailingBrowserService:
        async def shutdown(self):
            calls.append("browser_service.shutdown (failed)")
            raise RuntimeError("simulated browser shutdown failure")

    class _TrackedDatabase:
        async def dispose(self):
            calls.append("database.dispose")

    class _TrackedVoiceService:
        is_listening = True

        def on_state_changed(self, callback):
            pass

        async def stop_wake_word(self):
            calls.append("voice_service.stop_wake_word")

        async def stop_speaking(self):
            calls.append("voice_service.stop_speaking")

        async def stop_listening(self):
            calls.append("voice_service.stop_listening")

    settings = Settings(data_dir=tmp_path)
    container = Container()
    container.settings.override(settings)
    for provider_name in (
        "llm_provider",
        "memory_service",
        "hotkey_service",
        "chat_service",
        "conversation_service",
    ):
        getattr(container, provider_name).override(_Fake())
    container.browser_service.override(providers_factory_stub(_FailingBrowserService))
    container.database.override(providers_factory_stub(_TrackedDatabase))
    container.voice_service.override(providers_factory_stub(_TrackedVoiceService))

    window = MainWindow(settings, container)
    loop = asyncio.get_event_loop()
    loop.run_until_complete(window._graceful_quit())

    # The browser shutdown failing must not have prevented the rest.
    assert "browser_service.shutdown (failed)" in calls
    assert "database.dispose" in calls
    assert "voice_service.stop_wake_word" in calls
    assert "voice_service.stop_speaking" in calls
    assert "voice_service.stop_listening" in calls


def test_main_window_graceful_quit_publishes_shutdown_requested_event(qapp, tmp_path: Path) -> None:
    """Milestone 9, Application Lifecycle: _graceful_quit() publishes
    ShutdownRequestedEvent on the real EventBus before RuntimeManager
    releases any resource, so a subscriber sees "shutting down" as the
    app is *starting* to quit, not after resources are already gone."""
    import asyncio

    from jarvis.core.config.settings import Settings
    from jarvis.core.di.container import Container
    from jarvis.core.events.events import ShutdownRequestedEvent
    from jarvis.ui.main_window import MainWindow

    asyncio.set_event_loop(asyncio.new_event_loop())

    calls: list[str] = []

    class _Fake:
        def __getattr__(self, name):
            async def _noop(*a, **k):
                calls.append(name)

            return _noop

    settings = Settings(data_dir=tmp_path)
    container = Container()
    container.settings.override(settings)
    for provider_name in (
        "llm_provider",
        "memory_service",
        "voice_service",
        "hotkey_service",
        "chat_service",
        "conversation_service",
        "browser_service",
        "database",
    ):
        getattr(container, provider_name).override(_Fake())

    async def _on_shutdown_requested(event: ShutdownRequestedEvent) -> None:
        calls.append("shutdown_requested_event")

    container.event_bus().subscribe(ShutdownRequestedEvent, _on_shutdown_requested)

    window = MainWindow(settings, container)
    # MainWindow construction alone can trigger incidental service calls
    # (e.g. a status widget's health poll) unrelated to shutdown -- only
    # assert relative order from this point on, not that the event fires
    # before literally anything else has ever happened.
    calls.clear()

    loop = asyncio.get_event_loop()
    loop.run_until_complete(window._graceful_quit())

    assert "shutdown_requested_event" in calls
    assert "dispose" in calls  # real shutdown work (database.dispose) still ran
    assert calls.index("shutdown_requested_event") < calls.index("dispose")


def providers_factory_stub(cls):
    """Small helper: wrap a plain class as a dependency-injector Object
    provider so it can override a Singleton/Factory provider in tests."""
    from dependency_injector import providers

    return providers.Object(cls())


def test_update_center_view_checks_for_updates(qapp, tmp_path: Path) -> None:
    """Repository stabilization pass: this test's ``def`` line had been lost
    at some point, leaving its body as dead/unreachable code inside
    ``providers_factory_stub`` above (caught by ruff's F821 undefined-name
    check on ``tmp_path``) -- silently dropping all coverage of
    ``UpdateCenterView._check_for_updates``. Restored verbatim; no new
    assertions added beyond what the orphaned code already exercised."""
    from jarvis.core.config.settings import Settings
    from jarvis.services.update_service import UpdateService
    from jarvis.ui.views.developer.update_center_view import UpdateCenterView

    settings = Settings(data_dir=tmp_path)
    service = UpdateService(settings)
    view = UpdateCenterView(service)
    view._check_for_updates()


def test_developer_dashboard_builds_all_fifteen_sections(qapp, tmp_path: Path) -> None:
    from jarvis.core.config.settings import Settings
    from jarvis.core.di.container import Container
    from jarvis.ui.views.developer.developer_dashboard import DeveloperDashboard

    settings = Settings(data_dir=tmp_path)
    container = Container()
    container.settings.override(settings)

    dashboard = DeveloperDashboard(settings, container)
    # 13 sections as of Milestone 5, +1 "Agent Trace" (Milestone 5-Agents),
    # +1 "Vision Status" (Milestone 6, Phase 6).
    assert dashboard._stack.count() == 15


def test_main_window_constructs_with_stubbed_heavy_providers(qapp, tmp_path: Path) -> None:
    import asyncio

    from jarvis.core.config.settings import Settings
    from jarvis.core.di.container import Container
    from jarvis.ui.main_window import MainWindow

    asyncio.set_event_loop(asyncio.new_event_loop())

    class _Fake:
        def __getattr__(self, name):
            async def _noop(*a, **k):
                return None

            return _noop

    settings = Settings(data_dir=tmp_path)
    container = Container()
    container.settings.override(settings)
    for provider_name in (
        "llm_provider",
        "memory_service",
        "voice_service",
        "hotkey_service",
        "chat_service",
        "conversation_service",
    ):
        getattr(container, provider_name).override(_Fake())

    window = MainWindow(settings, container)
    # Only Home/Chat (always real) and Automations (still a
    # ComingSoonView placeholder) are built eagerly. The 9 completion-pass
    # workspaces are lazy -- built on first visit, see
    # MainWindow._on_nav_selected -- so they should NOT be in the stack yet.
    assert set(window._page_index.keys()) == {"home", "chat", "automations"}

    for workspace_id in (
        "voice",
        "files",
        "browser",
        "coding",
        "finance",
        "smart_home",
        "calendar",
        "gmail",
        "spotify",
    ):
        window._on_nav_selected(workspace_id)
        assert workspace_id in window._page_index
        assert window._last_real_nav_id == workspace_id
        # Visiting again must reuse the cached page, not rebuild it.
        first_index = window._page_index[workspace_id]
        window._on_nav_selected(workspace_id)
        assert window._page_index[workspace_id] == first_index

    window._on_nav_selected("chat")
    assert window._last_real_nav_id == "chat"
    window._on_nav_selected("settings")
    assert window._last_real_nav_id == "chat"  # settings doesn't steal the highlight
