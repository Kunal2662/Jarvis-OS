"""Unit tests for ``jarvis.core.devtools.api_inspector`` (Milestone 9
Task Group E)."""

from __future__ import annotations

import pytest

from jarvis.core.devtools.api_inspector import ApiInspector, api_inspector_middleware


def test_empty_inspector():
    inspector = ApiInspector()
    assert len(inspector) == 0
    assert inspector.recent() == ()


def test_record_and_recent_most_recent_first():
    inspector = ApiInspector()
    inspector.record(method="GET", path="/api/v1/plugins", status_code=200, duration_ms=1.0)
    inspector.record(
        method="POST", path="/api/v1/plugins/install", status_code=201, duration_ms=2.0
    )

    recent = inspector.recent()
    assert len(recent) == 2
    assert recent[0].path == "/api/v1/plugins/install"
    assert recent[1].path == "/api/v1/plugins"


def test_recent_respects_limit():
    inspector = ApiInspector()
    for i in range(5):
        inspector.record(method="GET", path=f"/api/v1/x/{i}", status_code=200, duration_ms=1.0)
    assert len(inspector.recent(limit=2)) == 2


def test_recent_filters_by_path_contains():
    inspector = ApiInspector()
    inspector.record(method="GET", path="/api/v1/plugins", status_code=200, duration_ms=1.0)
    inspector.record(method="GET", path="/api/v1/devtools/logs", status_code=200, duration_ms=1.0)
    filtered = inspector.recent(path_contains="devtools")
    assert len(filtered) == 1
    assert filtered[0].path == "/api/v1/devtools/logs"


def test_max_records_bounds_history():
    inspector = ApiInspector(max_records=3)
    for i in range(10):
        inspector.record(method="GET", path=f"/x/{i}", status_code=200, duration_ms=1.0)
    assert len(inspector) == 3


def test_clear():
    inspector = ApiInspector()
    inspector.record(method="GET", path="/x", status_code=200, duration_ms=1.0)
    inspector.clear()
    assert len(inspector) == 0


class _FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


class _FakeRequest:
    def __init__(self, method: str, path: str) -> None:
        self.method = method

        class _URL:
            def __init__(self, path: str) -> None:
                self.path = path

        self.url = _URL(path)


@pytest.mark.asyncio
async def test_middleware_records_real_call():
    inspector = ApiInspector()

    async def call_next(request):
        return _FakeResponse(status_code=200)

    request = _FakeRequest("GET", "/api/v1/plugins")
    response = await api_inspector_middleware(request, call_next, inspector=inspector)

    assert response.status_code == 200
    recent = inspector.recent()
    assert len(recent) == 1
    assert recent[0].method == "GET"
    assert recent[0].path == "/api/v1/plugins"
    assert recent[0].duration_ms >= 0.0
