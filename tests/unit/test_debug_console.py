"""Unit tests for ``jarvis.core.devtools.debug_console`` (Milestone 9
Task Group E)."""

from __future__ import annotations

import asyncio
import time

import pytest
from loguru import logger as loguru_logger

from jarvis.core.devtools.debug_console import DebugConsole
from jarvis.core.events.event_bus import EventBus
from jarvis.core.events.events import DebugLogCapturedEvent


def _wait_for(predicate, *, timeout: float = 2.0) -> None:
    """Loguru's ``enqueue=True`` sink runs on a background thread --
    give it a real chance to catch up rather than asserting
    immediately after logging."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("Condition not met within timeout.")


def test_not_running_until_started():
    console = DebugConsole(EventBus())
    assert console.is_running is False


def test_start_is_idempotent():
    console = DebugConsole(EventBus())
    console.start(level="DEBUG")
    console.start(level="DEBUG")  # second call must not attach a duplicate sink
    try:
        loguru_logger.bind(logger="jarvis.test.idempotent").info("only once")
        _wait_for(lambda: len(console) >= 1)
    finally:
        console.stop()

    matches = [e for e in console.entries() if e.message == "only once"]
    assert len(matches) == 1


def test_capture_and_query(tmp_path):
    console = DebugConsole(EventBus())
    console.start(level="DEBUG")
    try:
        loguru_logger.bind(logger="jarvis.test.debug_console").info("hello from the test")
        _wait_for(lambda: len(console) >= 1)
    finally:
        console.stop()

    entries = console.entries(contains="hello from the test")
    assert len(entries) == 1
    assert entries[0].message == "hello from the test"
    assert entries[0].logger == "jarvis.test.debug_console"


def test_filter_by_level():
    console = DebugConsole(EventBus())
    console.start(level="DEBUG")
    try:
        loguru_logger.bind(logger="jarvis.test.levels").warning("a warning line")
        loguru_logger.bind(logger="jarvis.test.levels").info("an info line")
        _wait_for(lambda: len(console) >= 2)
    finally:
        console.stop()

    warnings = console.entries(level="WARNING", logger="jarvis.test.levels")
    assert all(e.level == "WARNING" for e in warnings)
    assert any(e.message == "a warning line" for e in warnings)


def test_stop_detaches_sink():
    console = DebugConsole(EventBus())
    console.start()
    console.stop()
    assert console.is_running is False
    before = len(console)
    loguru_logger.bind(logger="jarvis.test.after_stop").info("should not be captured")
    time.sleep(0.1)
    assert len(console) == before


def test_max_entries_bounds_buffer():
    console = DebugConsole(EventBus(), max_entries=3)
    console.start(level="DEBUG")
    try:
        for i in range(10):
            loguru_logger.bind(logger="jarvis.test.bound").info("line {}", i)
        _wait_for(lambda: len(console) == 3)
    finally:
        console.stop()
    assert len(console) == 3


@pytest.mark.asyncio
async def test_capture_publishes_event():
    bus = EventBus()
    received = []
    bus.subscribe(DebugLogCapturedEvent, received.append)
    console = DebugConsole(bus)
    console.start(level="DEBUG")
    try:
        loguru_logger.bind(logger="jarvis.test.event").info("event-carrying line")
        _wait_for(lambda: len(received) >= 1)
    finally:
        console.stop()
    # publish_nowait's fallback path runs synchronously on the sink's own
    # thread; give the current loop one tick to observe it, matching the
    # same real-world timing this event's own docstring describes.
    await asyncio.sleep(0)
    assert any(e.message == "event-carrying line" for e in received)


def test_clear_empties_buffer():
    console = DebugConsole(EventBus())
    console.start(level="DEBUG")
    try:
        loguru_logger.bind(logger="jarvis.test.clear").info("to be cleared")
        _wait_for(lambda: len(console) >= 1)
    finally:
        console.stop()
    console.clear()
    assert len(console) == 0
