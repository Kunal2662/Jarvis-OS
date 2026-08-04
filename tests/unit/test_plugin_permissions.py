"""Unit tests for ``jarvis.core.plugins.permissions`` (Milestone 9 Task
Group D, Phase 5)."""

from __future__ import annotations

import pytest

from jarvis.core.events.event_bus import EventBus
from jarvis.core.events.events import PluginPermissionDeniedEvent, PluginPermissionGrantedEvent
from jarvis.core.plugins.permissions import PermissionModel, PermissionState
from jarvis.core.plugins.sdk import IPermissionChecker


def _model(tmp_path, bus=None):
    return PermissionModel(bus or EventBus(), store_path=tmp_path / "permissions.json")


def test_satisfies_ipermission_checker_protocol(tmp_path):
    assert isinstance(_model(tmp_path), IPermissionChecker)


def test_undeclared_scope_is_not_granted(tmp_path):
    model = _model(tmp_path)
    assert model.is_granted("p1", "network") is False


def test_declare_sets_pending_state(tmp_path):
    model = _model(tmp_path)
    model.declare("p1", ["network", "filesystem"])
    assert model.state("p1", "network") is PermissionState.PENDING
    assert model.state("p1", "filesystem") is PermissionState.PENDING
    assert model.is_granted("p1", "network") is False


@pytest.mark.asyncio
async def test_grant_makes_is_granted_true_and_publishes_event(tmp_path):
    bus = EventBus()
    received = []
    bus.subscribe(PluginPermissionGrantedEvent, received.append)
    model = _model(tmp_path, bus)
    model.declare("p1", ["network"])

    await model.grant("p1", "network")

    assert model.is_granted("p1", "network") is True
    assert model.state("p1", "network") is PermissionState.GRANTED
    assert len(received) == 1
    assert received[0].plugin_id == "p1"
    assert received[0].scope == "network"


@pytest.mark.asyncio
async def test_deny_keeps_is_granted_false_and_publishes_event(tmp_path):
    bus = EventBus()
    received = []
    bus.subscribe(PluginPermissionDeniedEvent, received.append)
    model = _model(tmp_path, bus)
    model.declare("p1", ["network"])

    await model.deny("p1", "network")

    assert model.is_granted("p1", "network") is False
    assert model.state("p1", "network") is PermissionState.DENIED
    assert len(received) == 1


@pytest.mark.asyncio
async def test_revoke_returns_to_pending(tmp_path):
    model = _model(tmp_path)
    model.declare("p1", ["network"])
    await model.grant("p1", "network")
    assert model.is_granted("p1", "network") is True

    await model.revoke("p1", "network")

    assert model.state("p1", "network") is PermissionState.PENDING
    assert model.is_granted("p1", "network") is False


@pytest.mark.asyncio
async def test_declaring_twice_does_not_reset_a_decision(tmp_path):
    model = _model(tmp_path)
    model.declare("p1", ["network"])
    await model.grant("p1", "network")

    model.declare("p1", ["network", "filesystem"])

    assert model.state("p1", "network") is PermissionState.GRANTED
    assert model.state("p1", "filesystem") is PermissionState.PENDING


def test_pending_lists_only_undecided_scopes(tmp_path):
    model = _model(tmp_path)
    model.declare("p1", ["network", "filesystem"])
    model.declare("p2", ["memory.read"])
    assert set(model.pending()) == {
        ("p1", "network"),
        ("p1", "filesystem"),
        ("p2", "memory.read"),
    }


@pytest.mark.asyncio
async def test_pending_shrinks_after_decision(tmp_path):
    model = _model(tmp_path)
    model.declare("p1", ["network", "filesystem"])
    await model.grant("p1", "network")
    assert set(model.pending()) == {("p1", "filesystem")}


@pytest.mark.asyncio
async def test_grants_persist_across_instances(tmp_path):
    store_path = tmp_path / "permissions.json"
    bus = EventBus()
    model = PermissionModel(bus, store_path=store_path)
    model.declare("p1", ["network"])
    await model.grant("p1", "network")

    reloaded = PermissionModel(EventBus(), store_path=store_path)
    assert reloaded.is_granted("p1", "network") is True


def test_load_tolerates_missing_store(tmp_path):
    model = PermissionModel(EventBus(), store_path=tmp_path / "does-not-exist.json")
    assert model.is_granted("p1", "network") is False


def test_load_tolerates_corrupt_store(tmp_path):
    store_path = tmp_path / "permissions.json"
    store_path.write_text("{not valid json", encoding="utf-8")
    model = PermissionModel(EventBus(), store_path=store_path)
    assert model.is_granted("p1", "network") is False


def test_denied_check_recorded_in_audit_log(tmp_path):
    model = _model(tmp_path)
    model.is_granted("p1", "network")
    actions = [entry.action for entry in model.audit_log]
    assert "denied_check" in actions


@pytest.mark.asyncio
async def test_grant_recorded_in_audit_log(tmp_path):
    model = _model(tmp_path)
    model.declare("p1", ["network"])
    await model.grant("p1", "network")
    actions = [entry.action for entry in model.audit_log]
    assert "declared" in actions
    assert "granted" in actions


def test_audit_log_is_bounded(tmp_path):
    model = PermissionModel(EventBus(), store_path=tmp_path / "permissions.json", audit_log_size=3)
    for i in range(10):
        model.is_granted("p1", f"scope-{i}")
    assert len(model.audit_log) == 3
