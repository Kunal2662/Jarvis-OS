"""Unit tests for ``jarvis.infrastructure.api.auth`` (Milestone 9 Task
Group E)."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from jarvis.infrastructure.api.auth import Envelope, envelope, get_current_session


class _FakeSessionManager:
    def __init__(self, sessions: dict[str, object]) -> None:
        self._sessions = sessions

    def get(self, session_id: str):
        return self._sessions.get(session_id)


class _FakeContainer:
    def __init__(self, session_manager: _FakeSessionManager) -> None:
        self._session_manager = session_manager

    def session_manager(self):
        return self._session_manager


class _FakeAppState:
    def __init__(self, container: _FakeContainer) -> None:
        self.container = container


class _FakeApp:
    def __init__(self, container: _FakeContainer) -> None:
        self.state = _FakeAppState(container)


class _FakeRequest:
    def __init__(self, container: _FakeContainer) -> None:
        self.app = _FakeApp(container)


def _request(sessions: dict[str, object]) -> _FakeRequest:
    return _FakeRequest(_FakeContainer(_FakeSessionManager(sessions)))


@pytest.mark.asyncio
async def test_valid_bearer_token_returns_session():
    info = object()
    request = _request({"abc123": info})
    result = await get_current_session(request, authorization="Bearer abc123")
    assert result is info


@pytest.mark.asyncio
async def test_missing_header_raises_401():
    request = _request({})
    with pytest.raises(HTTPException) as exc_info:
        await get_current_session(request, authorization=None)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_malformed_scheme_raises_401():
    request = _request({"abc123": object()})
    with pytest.raises(HTTPException) as exc_info:
        await get_current_session(request, authorization="Basic abc123")
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_unknown_token_raises_401():
    request = _request({})
    with pytest.raises(HTTPException) as exc_info:
        await get_current_session(request, authorization="Bearer does-not-exist")
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_empty_bearer_token_raises_401():
    request = _request({})
    with pytest.raises(HTTPException) as exc_info:
        await get_current_session(request, authorization="Bearer ")
    assert exc_info.value.status_code == 401


def test_envelope_wraps_data_with_default_empty_meta():
    result = envelope({"name": "hello-world"})
    assert result.data == {"name": "hello-world"}
    assert result.meta == {}


def test_envelope_carries_explicit_meta():
    result = envelope([1, 2, 3], meta={"count": 3})
    assert result.data == [1, 2, 3]
    assert result.meta == {"count": 3}


def test_envelope_model_is_json_serializable():
    result: Envelope[dict] = envelope({"a": 1})
    dumped = result.model_dump()
    assert dumped == {"data": {"a": 1}, "meta": {}}
