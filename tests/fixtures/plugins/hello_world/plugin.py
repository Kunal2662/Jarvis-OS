"""Reference "hello world" plugin -- proves the Plugin Platform's own
acceptance criterion (``docs/MASTER_ROADMAP.md`` section 8 M9's Plugin
Platform module): *"A hello-world plugin registers a slash command and
a hotkey."* Used by ``tests/integration/test_plugin_platform_e2e.py``
against the real Loader/Sandbox/Permission Model/Registry stack -- not
a mock of any of them.
"""

from __future__ import annotations


class HelloWorldPlugin:
    def __init__(self) -> None:
        self.context = None
        self.last_greeted = None
        self.hotkey_fired = False

    async def on_load(self, context) -> None:
        self.context = context
        context.commands.register("hello.greet", self._greet)
        context.hotkeys.register("greet", "ctrl+alt+h", self._on_hotkey)

    async def on_start(self) -> None:
        pass

    async def on_stop(self) -> None:
        if self.context is not None:
            self.context.hotkeys.unregister_all()

    async def _greet(self, who: str | None = None) -> str:
        name = who or self.context.config.get("default_name")
        self.last_greeted = name
        return f"Hello, {name}!"

    def _on_hotkey(self) -> None:
        self.hotkey_fired = True
