"""Unit tests for ``jarvis.core.lifecycle.shutdown_manager.ShutdownManager``
(Milestone 5.5)."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_shutdown_manager_runs_hooks_in_priority_order() -> None:
    from jarvis.core.lifecycle.shutdown_manager import ShutdownManager

    order: list[str] = []
    manager = ShutdownManager()

    async def _first():
        order.append("first")

    async def _middle():
        order.append("middle")

    async def _last():
        order.append("last")

    manager.register("last", _last, priority=100)
    manager.register("first", _first, priority=0)
    manager.register("middle", _middle, priority=50)

    assert manager.registered_names == ["first", "middle", "last"]
    await manager.shutdown()
    assert order == ["first", "middle", "last"]


@pytest.mark.asyncio
async def test_shutdown_manager_same_priority_preserves_registration_order() -> None:
    from jarvis.core.lifecycle.shutdown_manager import ShutdownManager

    order: list[str] = []
    manager = ShutdownManager()

    async def _a():
        order.append("a")

    async def _b():
        order.append("b")

    async def _c():
        order.append("c")

    manager.register("a", _a, priority=10)
    manager.register("b", _b, priority=10)
    manager.register("c", _c, priority=10)

    await manager.shutdown()
    assert order == ["a", "b", "c"]


@pytest.mark.asyncio
async def test_shutdown_manager_one_failure_does_not_block_others() -> None:
    from jarvis.core.lifecycle.shutdown_manager import ShutdownManager

    order: list[str] = []
    manager = ShutdownManager()

    async def _ok_1():
        order.append("ok_1")

    async def _fails():
        order.append("fails")
        raise RuntimeError("simulated cleanup failure")

    async def _ok_2():
        order.append("ok_2")

    manager.register("ok_1", _ok_1, priority=0)
    manager.register("fails", _fails, priority=10)
    manager.register("ok_2", _ok_2, priority=20)

    results = await manager.shutdown()

    assert order == ["ok_1", "fails", "ok_2"]  # failure didn't stop the sequence
    by_name = {r.name: r for r in results}
    assert by_name["ok_1"].succeeded is True
    assert by_name["fails"].succeeded is False
    assert "simulated cleanup failure" in by_name["fails"].error
    assert by_name["ok_2"].succeeded is True


@pytest.mark.asyncio
async def test_shutdown_manager_records_duration() -> None:
    from jarvis.core.lifecycle.shutdown_manager import ShutdownManager

    manager = ShutdownManager()

    async def _hook():
        pass

    manager.register("only", _hook)
    results = await manager.shutdown()
    assert len(results) == 1
    assert results[0].duration_ms >= 0


@pytest.mark.asyncio
async def test_shutdown_manager_is_idempotent() -> None:
    from jarvis.core.lifecycle.shutdown_manager import ShutdownManager

    calls = []
    manager = ShutdownManager()

    async def _hook():
        calls.append(1)

    manager.register("only", _hook)
    results1 = await manager.shutdown()
    assert len(calls) == 1
    assert len(results1) == 1

    # Second call must be a safe no-op, not re-run everything.
    results2 = await manager.shutdown()
    assert len(calls) == 1
    assert results2 == []


def test_shutdown_manager_register_replaces_not_duplicates() -> None:
    from jarvis.core.lifecycle.shutdown_manager import ShutdownManager

    manager = ShutdownManager()

    async def _v1():
        pass

    async def _v2():
        pass

    manager.register("resource", _v1)
    manager.register("resource", _v2)  # re-registering the same name replaces it

    assert manager.registered_names == ["resource"]
    assert manager.is_registered("resource") is True
    assert manager.is_registered("nonexistent") is False

    manager.unregister("resource")
    assert manager.is_registered("resource") is False
    assert manager.registered_names == []


@pytest.mark.asyncio
async def test_shutdown_manager_empty_manager_is_safe() -> None:
    """No hooks registered at all -- e.g. a headless/CLI mode that never
    wires up MainWindow's hooks -- must not error."""
    from jarvis.core.lifecycle.shutdown_manager import ShutdownManager

    manager = ShutdownManager()
    results = await manager.shutdown()
    assert results == []
