"""Unit tests for ``jarvis.core.lifecycle.runtime_manager.RuntimeManager``
(Milestone 5.5's ``ShutdownManager``, generalized to also cover startup
hooks under Milestone 9's Runtime Core module).

Shutdown-side tests mirror the original ``ShutdownManager`` suite
one-for-one to prove the rename/generalization didn't change existing
behavior; startup-side tests are their symmetric counterparts."""

from __future__ import annotations

import pytest

# --- Shutdown side (regression coverage for the ShutdownManager rename) -----


@pytest.mark.asyncio
async def test_shutdown_hooks_run_in_priority_order() -> None:
    from jarvis.core.lifecycle.runtime_manager import RuntimeManager

    order: list[str] = []
    manager = RuntimeManager()

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
async def test_shutdown_same_priority_preserves_registration_order() -> None:
    from jarvis.core.lifecycle.runtime_manager import RuntimeManager

    order: list[str] = []
    manager = RuntimeManager()

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
async def test_shutdown_one_failure_does_not_block_others() -> None:
    from jarvis.core.lifecycle.runtime_manager import RuntimeManager

    order: list[str] = []
    manager = RuntimeManager()

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
async def test_shutdown_records_duration() -> None:
    from jarvis.core.lifecycle.runtime_manager import RuntimeManager

    manager = RuntimeManager()

    async def _hook():
        pass

    manager.register("only", _hook)
    results = await manager.shutdown()
    assert len(results) == 1
    assert results[0].duration_ms >= 0


@pytest.mark.asyncio
async def test_shutdown_is_idempotent() -> None:
    from jarvis.core.lifecycle.runtime_manager import RuntimeManager

    calls = []
    manager = RuntimeManager()

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


def test_shutdown_register_replaces_not_duplicates() -> None:
    from jarvis.core.lifecycle.runtime_manager import RuntimeManager

    manager = RuntimeManager()

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
async def test_shutdown_empty_manager_is_safe() -> None:
    """No hooks registered at all -- e.g. a headless/CLI mode that never
    wires up MainWindow's hooks -- must not error."""
    from jarvis.core.lifecycle.runtime_manager import RuntimeManager

    manager = RuntimeManager()
    results = await manager.shutdown()
    assert results == []


# --- Startup side (Milestone 9, new) -----------------------------------


@pytest.mark.asyncio
async def test_startup_hooks_run_in_priority_order() -> None:
    from jarvis.core.lifecycle.runtime_manager import RuntimeManager

    order: list[str] = []
    manager = RuntimeManager()

    async def _first():
        order.append("first")

    async def _middle():
        order.append("middle")

    async def _last():
        order.append("last")

    manager.register_startup("last", _last, priority=100)
    manager.register_startup("first", _first, priority=0)
    manager.register_startup("middle", _middle, priority=50)

    assert manager.registered_startup_names == ["first", "middle", "last"]
    await manager.startup()
    assert order == ["first", "middle", "last"]


@pytest.mark.asyncio
async def test_startup_same_priority_preserves_registration_order() -> None:
    from jarvis.core.lifecycle.runtime_manager import RuntimeManager

    order: list[str] = []
    manager = RuntimeManager()

    async def _a():
        order.append("a")

    async def _b():
        order.append("b")

    async def _c():
        order.append("c")

    manager.register_startup("a", _a, priority=10)
    manager.register_startup("b", _b, priority=10)
    manager.register_startup("c", _c, priority=10)

    await manager.startup()
    assert order == ["a", "b", "c"]


@pytest.mark.asyncio
async def test_startup_one_failure_does_not_block_others() -> None:
    """The exact guarantee `app.py`'s memory-policy-enforcement and
    Whisper-preload comments already promised ("must never block
    boot") -- now enforced by RuntimeManager itself instead of two
    separate hand-written try/except blocks."""
    from jarvis.core.lifecycle.runtime_manager import RuntimeManager

    order: list[str] = []
    manager = RuntimeManager()

    async def _ok_1():
        order.append("ok_1")

    async def _fails():
        order.append("fails")
        raise RuntimeError("simulated startup failure")

    async def _ok_2():
        order.append("ok_2")

    manager.register_startup("ok_1", _ok_1, priority=0)
    manager.register_startup("fails", _fails, priority=10)
    manager.register_startup("ok_2", _ok_2, priority=20)

    results = await manager.startup()

    assert order == ["ok_1", "fails", "ok_2"]  # failure didn't stop the sequence
    by_name = {r.name: r for r in results}
    assert by_name["ok_1"].succeeded is True
    assert by_name["fails"].succeeded is False
    assert "simulated startup failure" in by_name["fails"].error
    assert by_name["ok_2"].succeeded is True


@pytest.mark.asyncio
async def test_startup_records_duration() -> None:
    from jarvis.core.lifecycle.runtime_manager import RuntimeManager

    manager = RuntimeManager()

    async def _hook():
        pass

    manager.register_startup("only", _hook)
    results = await manager.startup()
    assert len(results) == 1
    assert results[0].duration_ms >= 0


@pytest.mark.asyncio
async def test_startup_is_idempotent() -> None:
    from jarvis.core.lifecycle.runtime_manager import RuntimeManager

    calls = []
    manager = RuntimeManager()

    async def _hook():
        calls.append(1)

    manager.register_startup("only", _hook)
    results1 = await manager.startup()
    assert len(calls) == 1
    assert len(results1) == 1

    # Second call must be a safe no-op, not re-run everything.
    results2 = await manager.startup()
    assert len(calls) == 1
    assert results2 == []


def test_startup_register_replaces_not_duplicates() -> None:
    from jarvis.core.lifecycle.runtime_manager import RuntimeManager

    manager = RuntimeManager()

    async def _v1():
        pass

    async def _v2():
        pass

    manager.register_startup("resource", _v1)
    manager.register_startup("resource", _v2)  # re-registering the same name replaces it

    assert manager.registered_startup_names == ["resource"]
    assert manager.is_startup_registered("resource") is True
    assert manager.is_startup_registered("nonexistent") is False

    manager.unregister_startup("resource")
    assert manager.is_startup_registered("resource") is False
    assert manager.registered_startup_names == []


@pytest.mark.asyncio
async def test_startup_empty_manager_is_safe() -> None:
    from jarvis.core.lifecycle.runtime_manager import RuntimeManager

    manager = RuntimeManager()
    results = await manager.startup()
    assert results == []


# --- Cross-cutting: the two directions are tracked independently -----------


@pytest.mark.asyncio
async def test_startup_and_shutdown_hooks_are_independent() -> None:
    """Registering a hook for one direction must have zero effect on
    the other -- a resource that only needs startup work (e.g. memory
    policy enforcement) shouldn't accidentally show up in the shutdown
    sequence, and vice versa."""
    from jarvis.core.lifecycle.runtime_manager import RuntimeManager

    manager = RuntimeManager()

    async def _noop():
        pass

    manager.register_startup("startup_only", _noop)
    manager.register("shutdown_only", _noop)

    assert manager.registered_startup_names == ["startup_only"]
    assert manager.registered_names == ["shutdown_only"]
    assert manager.is_startup_registered("shutdown_only") is False
    assert manager.is_registered("startup_only") is False

    await manager.startup()
    await manager.shutdown()

    # Running one direction must not mark the other as having run.
    assert (await manager.startup()) == []  # already ran -- idempotent no-op
    assert (await manager.shutdown()) == []  # already ran -- idempotent no-op
