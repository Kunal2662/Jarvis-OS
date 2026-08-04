"""Unit tests for ``jarvis.core.plugins.sandbox`` (Milestone 9 Task
Group D, Phase 3)."""

from __future__ import annotations

import asyncio
import textwrap

import pytest

from jarvis.core.plugins.sandbox import PluginProcessSandbox, PluginSandbox

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Tier 1 -- in-process.
# ---------------------------------------------------------------------------
class _GoodPlugin:
    def __init__(self) -> None:
        self.loaded_context = None
        self.started = False
        self.stopped = False

    async def on_load(self, context) -> None:
        self.loaded_context = context

    async def on_start(self) -> None:
        self.started = True

    async def on_stop(self) -> None:
        self.stopped = True


class _FailingPlugin:
    async def on_load(self, context) -> None: ...

    async def on_start(self) -> None:
        raise RuntimeError("boom")

    async def on_stop(self) -> None: ...


class _HangingPlugin:
    async def on_load(self, context) -> None: ...

    async def on_start(self) -> None:
        await asyncio.sleep(10)

    async def on_stop(self) -> None: ...


async def test_run_hook_success():
    sandbox = PluginSandbox()
    plugin = _GoodPlugin()
    result = await sandbox.run_hook("p", plugin, "on_load", {"ctx": True})
    assert result.succeeded is True
    assert plugin.loaded_context == {"ctx": True}


async def test_run_hook_isolates_exception():
    sandbox = PluginSandbox()
    result = await sandbox.run_hook("p", _FailingPlugin(), "on_start")
    assert result.succeeded is False
    assert "boom" in result.error


async def test_run_hook_isolates_timeout():
    sandbox = PluginSandbox(hook_timeout_seconds=0.05)
    result = await sandbox.run_hook("p", _HangingPlugin(), "on_start")
    assert result.succeeded is False
    assert "timed out" in result.error


async def test_run_hook_unknown_hook_name():
    sandbox = PluginSandbox()
    result = await sandbox.run_hook("p", _GoodPlugin(), "on_explode")
    assert result.succeeded is False
    assert "on_explode" in result.error


async def test_run_hook_reports_duration():
    sandbox = PluginSandbox()
    result = await sandbox.run_hook("p", _GoodPlugin(), "on_start")
    assert result.duration_ms >= 0.0


# ---------------------------------------------------------------------------
# Tier 2 -- out-of-process. Slower (real spawn) -- kept to the essentials.
# ---------------------------------------------------------------------------
_GOOD_CHILD_PLUGIN_PY = textwrap.dedent(
    """
    class ChildPlugin:
        async def on_load(self, context) -> None:
            self.plugin_id = context.plugin_id

        async def on_start(self) -> None:
            pass

        async def on_stop(self) -> None:
            pass

    class FailingChildPlugin:
        async def on_load(self, context) -> None:
            pass

        async def on_start(self) -> None:
            raise RuntimeError("child boom")

        async def on_stop(self) -> None:
            pass
    """
)


@pytest.fixture
def child_plugin_file(tmp_path):
    path = tmp_path / "child_plugin.py"
    path.write_text(_GOOD_CHILD_PLUGIN_PY, encoding="utf-8")
    return path


async def test_process_sandbox_start_and_call_hooks(child_plugin_file):
    sandbox = PluginProcessSandbox("child-plugin", child_plugin_file, "ChildPlugin")
    try:
        start_result = sandbox.start()
        assert start_result.succeeded is True
        assert sandbox.is_alive is True

        load_result = sandbox.call_hook("on_load")
        assert load_result.succeeded is True

        start_hook_result = sandbox.call_hook("on_start")
        assert start_hook_result.succeeded is True
    finally:
        sandbox.terminate()
    assert sandbox.is_alive is False


async def test_process_sandbox_isolates_child_exception(child_plugin_file):
    sandbox = PluginProcessSandbox("child-plugin", child_plugin_file, "FailingChildPlugin")
    try:
        assert sandbox.start().succeeded is True
        result = sandbox.call_hook("on_start")
        assert result.succeeded is False
        assert "child boom" in result.error
        # The child process itself survives one hook raising -- only the
        # call failed, not the whole sandbox.
        assert sandbox.is_alive is True
    finally:
        sandbox.terminate()


async def test_process_sandbox_no_budget_configured_always_ok(child_plugin_file):
    sandbox = PluginProcessSandbox("child-plugin", child_plugin_file, "ChildPlugin")
    try:
        sandbox.start()
        assert sandbox.check_resource_budget().succeeded is True
    finally:
        sandbox.terminate()


async def test_process_sandbox_budget_check_on_dead_process_is_ok(child_plugin_file):
    sandbox = PluginProcessSandbox(
        "child-plugin", child_plugin_file, "ChildPlugin", max_memory_mb=1.0
    )
    result = sandbox.check_resource_budget()
    assert result.succeeded is True


async def test_process_sandbox_call_hook_before_start_fails(child_plugin_file):
    sandbox = PluginProcessSandbox("child-plugin", child_plugin_file, "ChildPlugin")
    result = sandbox.call_hook("on_start")
    assert result.succeeded is False


async def test_process_sandbox_missing_class_reports_failure(child_plugin_file):
    sandbox = PluginProcessSandbox("child-plugin", child_plugin_file, "GhostClass")
    result = sandbox.start()
    assert result.succeeded is False
    assert sandbox.is_alive is False
