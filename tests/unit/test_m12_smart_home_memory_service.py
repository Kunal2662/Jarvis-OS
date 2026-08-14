"""SmartHomeMemoryService tests -- Milestone 12 Smart Home Memory
(Manual/On-Demand Device Snapshot Slice).

Real (temp-file) SQLite ``SmartHomeService``, real
``SmartLightingService``/``SmartSwitchService``/``ThermostatService``,
a real ``MemoryService`` (with ``FakeLLM``/``FakeVectorStore`` in place
of network-backed embedding/vector infrastructure), and a real
``PermissionModel`` throughout -- only the device connector itself is
faked (``FakeDeviceConnector``), matching every prior M12 service
test's own pattern.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.core.connectivity.registry import ConnectorFactoryRegistry
from jarvis.core.events.event_bus import EventBus
from jarvis.core.exceptions import ServiceError
from jarvis.core.interfaces.connectivity import DeviceState
from jarvis.core.plugins.permissions import PermissionModel
from jarvis.services.connectivity_service import ConnectivityService
from jarvis.services.memory_service import MemoryService
from jarvis.services.smart_home_memory_service import (
    SMART_HOME_MEMORY_PRINCIPAL,
    SMART_HOME_SCOPE,
    SNAPSHOT_MEMORY_TYPE,
    SmartHomeMemoryPermissionError,
    SmartHomeMemoryService,
    UnsupportedSnapshotCategoryError,
)
from jarvis.services.smart_home_service import SmartHomeService
from jarvis.services.smart_lighting_service import SmartLightingService
from jarvis.services.smart_switch_service import SmartSwitchService
from jarvis.services.thermostat_service import ThermostatService
from tests.fakes.fake_device_connector import FakeDeviceConnector
from tests.fakes.fake_llm import FakeLLM
from tests.fakes.fake_vector_store import FakeVectorStore

_LIGHT_EXTERNAL_ID = "light.living_room"
_SWITCH_EXTERNAL_ID = "switch.kitchen"
_THERMOSTAT_EXTERNAL_ID = "climate.hallway"


def _settings(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("JARVIS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("JARVIS_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'jarvis.db'}")
    monkeypatch.setenv("JARVIS_OPENAI_ENABLED", "false")
    monkeypatch.setenv("JARVIS_OLLAMA_ENABLED", "true")

    from jarvis.core.config import settings as settings_mod

    settings_mod.load_settings.cache_clear()  # type: ignore[attr-defined]
    return settings_mod.load_settings()


@pytest.fixture
async def db(tmp_path: Path, monkeypatch):
    settings = _settings(tmp_path, monkeypatch)
    from jarvis.infrastructure.database.sqlite_client import SQLiteDatabase

    database = SQLiteDatabase(settings.db)
    await database.initialize()
    try:
        yield database, settings
    finally:
        await database.dispose()


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


@pytest.fixture
def smart_home(db, bus: EventBus) -> SmartHomeService:
    database, _ = db
    return SmartHomeService(database=database, event_bus=bus)


@pytest.fixture
def fake_connector() -> FakeDeviceConnector:
    return FakeDeviceConnector()


@pytest.fixture
def registry(fake_connector: FakeDeviceConnector) -> ConnectorFactoryRegistry:
    reg = ConnectorFactoryRegistry()
    reg.register("home_assistant", lambda config: fake_connector)
    return reg


@pytest.fixture
def connectivity(
    registry: ConnectorFactoryRegistry, smart_home: SmartHomeService, bus: EventBus
) -> ConnectivityService:
    return ConnectivityService(registry=registry, smart_home=smart_home, event_bus=bus)


@pytest.fixture
def permissions(tmp_path: Path, bus: EventBus) -> PermissionModel:
    return PermissionModel(bus, store_path=tmp_path / "permissions.json")


@pytest.fixture
def smart_lighting(
    db,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
) -> SmartLightingService:
    database, _ = db
    return SmartLightingService(
        database=database,
        smart_home=smart_home,
        connectivity=connectivity,
        permissions=permissions,
    )


@pytest.fixture
def smart_switch(
    smart_home: SmartHomeService, connectivity: ConnectivityService, permissions: PermissionModel
) -> SmartSwitchService:
    return SmartSwitchService(
        smart_home=smart_home, connectivity=connectivity, permissions=permissions
    )


@pytest.fixture
def thermostats(
    smart_home: SmartHomeService, connectivity: ConnectivityService, permissions: PermissionModel
) -> ThermostatService:
    return ThermostatService(
        smart_home=smart_home, connectivity=connectivity, permissions=permissions
    )


@pytest.fixture
def memory(db) -> MemoryService:
    database, settings = db
    return MemoryService(
        database=database, vector_store=FakeVectorStore(), llm=FakeLLM(), settings=settings
    )


@pytest.fixture
def service(
    smart_home: SmartHomeService,
    smart_lighting: SmartLightingService,
    smart_switch: SmartSwitchService,
    thermostats: ThermostatService,
    memory: MemoryService,
    permissions: PermissionModel,
) -> SmartHomeMemoryService:
    return SmartHomeMemoryService(
        smart_home=smart_home,
        smart_lighting=smart_lighting,
        smart_switch=smart_switch,
        thermostats=thermostats,
        memory=memory,
        permissions=permissions,
    )


async def _grant(permissions: PermissionModel) -> None:
    await permissions.grant(SMART_HOME_MEMORY_PRINCIPAL, SMART_HOME_SCOPE)


async def _light(smart_home: SmartHomeService, *, room_id: str | None = None):
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id,
        "Living Room Light",
        device_type="light",
        room_id=room_id,
        external_id=_LIGHT_EXTERNAL_ID,
        metadata={"connector_type": "home_assistant", "secret_token": "sh-abc123"},
    )
    return home, device


async def _switch(smart_home: SmartHomeService):
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id,
        "Kitchen Switch",
        device_type="switch",
        external_id=_SWITCH_EXTERNAL_ID,
        metadata={"connector_type": "home_assistant"},
    )
    return home, device


async def _thermostat(smart_home: SmartHomeService):
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id,
        "Hallway Thermostat",
        device_type="thermostat",
        external_id=_THERMOSTAT_EXTERNAL_ID,
        metadata={"connector_type": "home_assistant"},
    )
    return home, device


# --- Permission (Logic Contract §10) ------------------------------------------------


@pytest.mark.asyncio
async def test_permission_declared_pending_at_construction(permissions: PermissionModel) -> None:
    assert permissions.state(SMART_HOME_MEMORY_PRINCIPAL, SMART_HOME_SCOPE).value == "pending"


@pytest.mark.asyncio
async def test_snapshot_denied_without_grant(
    service: SmartHomeMemoryService, smart_home: SmartHomeService
) -> None:
    _, device = await _light(smart_home)
    with pytest.raises(SmartHomeMemoryPermissionError):
        await service.snapshot_device(device.id)


@pytest.mark.asyncio
async def test_list_snapshots_denied_without_grant(service: SmartHomeMemoryService) -> None:
    """Retrieval is gated too -- a deliberate departure from most M12
    modules' "reads ungated" precedent (Logic Contract §10)."""
    with pytest.raises(SmartHomeMemoryPermissionError):
        await service.list_snapshots()


@pytest.mark.asyncio
async def test_permission_checked_before_device_lookup(
    service: SmartHomeMemoryService, permissions: PermissionModel
) -> None:
    """Permission denied -> before any device lookup (Logic Contract
    §18) -- an unknown device id must not leak past an ungranted
    permission check as a different error."""
    with pytest.raises(SmartHomeMemoryPermissionError):
        await service.snapshot_device("no-such-device")


# --- Device-category scope (Logic Contract §5) ---------------------------------------


@pytest.mark.asyncio
async def test_unknown_device_raises_plain_service_error(
    service: SmartHomeMemoryService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    with pytest.raises(ServiceError) as exc_info:
        await service.snapshot_device("no-such-device")
    assert not isinstance(exc_info.value, UnsupportedSnapshotCategoryError)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "device_type,metadata",
    [
        ("sensor", {}),
        ("lock", {}),
        ("camera", {}),
        ("other", {}),
        ("appliance", {"domain": "vacuum"}),
        ("appliance", {"domain": "humidifier"}),
        ("appliance", {"domain": "media_player"}),
        ("appliance", {"domain": "water_heater"}),
    ],
)
async def test_unsupported_category_is_a_distinct_error(
    service: SmartHomeMemoryService,
    smart_home: SmartHomeService,
    permissions: PermissionModel,
    device_type: str,
    metadata: dict,
) -> None:
    """Sensors/Locks are excluded on privacy/security grounds, the
    appliance-domain categories on architectural grounds (Logic
    Contract §5) -- all raise the same distinct
    `UnsupportedSnapshotCategoryError`, never a plain unknown-device
    `ServiceError`."""
    await _grant(permissions)
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id, "Unsupported Device", device_type=device_type, external_id="x.y", metadata=metadata
    )
    with pytest.raises(UnsupportedSnapshotCategoryError, match="only supported for"):
        await service.snapshot_device(device.id)


# --- Snapshot creation: light / switch / thermostat -----------------------------------


@pytest.mark.asyncio
async def test_snapshot_light_captures_verbatim_state(
    service: SmartHomeMemoryService,
    smart_home: SmartHomeService,
    smart_lighting: SmartLightingService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _light(smart_home)
    fake_connector.states[_LIGHT_EXTERNAL_ID] = DeviceState(
        external_id=_LIGHT_EXTERNAL_ID,
        status="on",
        attributes={"brightness": 80, "color_temp_kelvin": 3000},
    )
    expected_state = await smart_lighting.get_light_state(device.id)

    result = await service.snapshot_device(device.id)

    assert result["device_id"] == device.id
    assert result["device_type"] == "light"
    assert result["memory_id"]
    assert result["snapshot_at"]

    rows = await service.list_snapshots(device_id=device.id)
    assert len(rows) == 1
    assert rows[0]["state"] == expected_state
    assert rows[0]["device_type"] == "light"
    assert rows[0]["home_id"] == device.home_id


@pytest.mark.asyncio
async def test_snapshot_switch_captures_verbatim_state(
    service: SmartHomeMemoryService,
    smart_home: SmartHomeService,
    smart_switch: SmartSwitchService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _switch(smart_home)
    fake_connector.states[_SWITCH_EXTERNAL_ID] = DeviceState(
        external_id=_SWITCH_EXTERNAL_ID, status="on", attributes={}
    )
    expected_state = await smart_switch.get_switch_state(device.id)

    result = await service.snapshot_device(device.id)

    assert result["device_type"] == "switch"
    rows = await service.list_snapshots(device_id=device.id)
    assert rows[0]["state"] == expected_state


@pytest.mark.asyncio
async def test_snapshot_thermostat_captures_verbatim_state(
    service: SmartHomeMemoryService,
    smart_home: SmartHomeService,
    thermostats: ThermostatService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _thermostat(smart_home)
    fake_connector.states[_THERMOSTAT_EXTERNAL_ID] = DeviceState(
        external_id=_THERMOSTAT_EXTERNAL_ID,
        status="heat",
        attributes={"current_temperature": 20.0, "temperature": 21.5},
    )
    expected_state = await thermostats.get_thermostat_state(device.id)

    result = await service.snapshot_device(device.id)

    assert result["device_type"] == "thermostat"
    rows = await service.list_snapshots(device_id=device.id)
    assert rows[0]["state"] == expected_state


# --- Unavailable device honesty (Logic Contract §18/§20) ------------------------------


@pytest.mark.asyncio
async def test_unavailable_device_still_produces_honest_snapshot(
    service: SmartHomeMemoryService,
    smart_home: SmartHomeService,
    permissions: PermissionModel,
) -> None:
    """No connector connected -- the light read falls back to
    available/unknown fields rather than raising, and the snapshot must
    still be created, capturing that honestly (never fabricated, never
    silently skipped)."""
    await _grant(permissions)
    _, device = await _light(smart_home)

    result = await service.snapshot_device(device.id)

    rows = await service.list_snapshots(device_id=device.id)
    assert len(rows) == 1
    assert rows[0]["state"]["on"] is None
    assert result["memory_id"]


# --- No fabricated / leaked data (Logic Contract §17B/§20) ----------------------------


@pytest.mark.asyncio
async def test_snapshot_never_leaks_device_metadata_json_secrets(
    service: SmartHomeMemoryService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    """`_light`'s fixture device carries a `secret_token` in
    `Device.metadata_json` -- the snapshot must never surface it,
    because metadata/content are built only from the owning service's
    own normalized read model, never from `Device.metadata_json`
    directly."""
    await _grant(permissions)
    _, device = await _light(smart_home)

    await service.snapshot_device(device.id)

    rows = await service.list_snapshots(device_id=device.id)
    assert "sh-abc123" not in str(rows[0])
    assert "secret_token" not in str(rows[0])
    assert "connector_type" not in rows[0]["state"]


@pytest.mark.asyncio
async def test_snapshot_at_is_close_to_now(
    service: SmartHomeMemoryService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    from datetime import UTC, datetime

    await _grant(permissions)
    _, device = await _light(smart_home)
    before = datetime.now(UTC)

    result = await service.snapshot_device(device.id)

    after = datetime.now(UTC)
    snapshot_at = datetime.fromisoformat(result["snapshot_at"])
    assert before <= snapshot_at <= after


# --- Memory representation (Logic Contract §6) -----------------------------------------


@pytest.mark.asyncio
async def test_memory_type_and_source_are_device_snapshot(
    service: SmartHomeMemoryService,
    smart_home: SmartHomeService,
    memory: MemoryService,
    permissions: PermissionModel,
) -> None:
    await _grant(permissions)
    _, device = await _light(smart_home)

    result = await service.snapshot_device(device.id)

    records = await memory.browse(memory_type=SNAPSHOT_MEMORY_TYPE)
    match = next(r for r in records if r.id == result["memory_id"])
    assert match.memory_type == SNAPSHOT_MEMORY_TYPE
    assert match.source == SNAPSHOT_MEMORY_TYPE


# --- Retrieval (Logic Contract §7) ------------------------------------------------------


@pytest.mark.asyncio
async def test_list_snapshots_empty_by_default(
    service: SmartHomeMemoryService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    assert await service.list_snapshots() == []


@pytest.mark.asyncio
async def test_list_snapshots_filters_by_device_id(
    service: SmartHomeMemoryService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    _, light = await _light(smart_home)
    _, switch = await _switch(smart_home)
    await service.snapshot_device(light.id)
    await service.snapshot_device(switch.id)

    light_only = await service.list_snapshots(device_id=light.id)
    assert len(light_only) == 1
    assert light_only[0]["device_id"] == light.id

    switch_only = await service.list_snapshots(device_id=switch.id)
    assert len(switch_only) == 1
    assert switch_only[0]["device_id"] == switch.id

    everything = await service.list_snapshots()
    assert len(everything) == 2


@pytest.mark.asyncio
async def test_list_snapshots_respects_limit(
    service: SmartHomeMemoryService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    _, light = await _light(smart_home)
    for _ in range(3):
        await service.snapshot_device(light.id)

    rows = await service.list_snapshots(limit=2)
    assert len(rows) == 2


@pytest.mark.asyncio
async def test_list_snapshots_most_recent_first(
    service: SmartHomeMemoryService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    _, light = await _light(smart_home)
    first = await service.snapshot_device(light.id)
    second = await service.snapshot_device(light.id)

    rows = await service.list_snapshots(device_id=light.id)

    assert rows[0]["memory_id"] == second["memory_id"]
    assert rows[1]["memory_id"] == first["memory_id"]


@pytest.mark.asyncio
async def test_list_snapshots_unknown_device_returns_empty_not_error(
    service: SmartHomeMemoryService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    assert await service.list_snapshots(device_id="no-such-device") == []


# --- Cross-cutting invariants (Logic Contract §12/§13/§14/§21) ------------------------
#
# These guards scan the module's *code*, not its docstrings -- the
# module docstring itself explains, in prose, everything this slice
# deliberately does NOT do (EventBus, Scheduler, automatic history,
# ...), which would otherwise collide with a naive whole-source scan.
# `_code_without_docstrings` strips every module/function/class
# docstring via an AST transform before re-serializing, so these tests
# check actual code, never explanatory prose.


def _code_without_docstrings(source: str) -> str:
    import ast

    tree = ast.parse(source)
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            and node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        ):
            node.body.pop(0)
            if not node.body:
                node.body.append(ast.Pass())
    return ast.unparse(tree)


def _service_code() -> str:
    import inspect

    from jarvis.services import smart_home_memory_service

    return _code_without_docstrings(inspect.getsource(smart_home_memory_service))


def test_service_has_no_eventbus_reference() -> None:
    source = _service_code()
    assert "event_bus" not in source
    assert "EventBus" not in source


def test_service_has_no_scheduler_reference() -> None:
    source = _service_code()
    assert "Scheduler" not in source
    assert "schedule" not in source.lower()


def test_service_has_no_analytics_reference() -> None:
    source = _service_code()
    assert "Analytics" not in source
    assert "trend" not in source.lower()


def test_service_does_not_import_connectors_directly() -> None:
    import inspect

    from jarvis.services import smart_home_memory_service

    import_lines = [
        line
        for line in inspect.getsource(smart_home_memory_service).splitlines()
        if line.strip().startswith(("import ", "from "))
    ]
    joined = "\n".join(import_lines)
    assert "HomeAssistantConnector" not in joined
    assert "MqttConnector" not in joined
    assert "ConnectivityService" not in joined


def test_service_has_no_deletion_tooling() -> None:
    """`MemoryService.forget` already exists generically -- this slice
    deliberately does not add a snapshot-specific delete path (Logic
    Contract §7)."""
    source = _service_code()
    assert "forget" not in source.lower()
    assert "delete" not in source.lower()


def test_no_deferred_functionality_exists() -> None:
    """Every item in Logic Contract §21's deferred table must have no
    corresponding code path here."""
    source = _service_code().lower()
    for deferred_term in (
        "automatic_history",
        "continuous",
        "predict",
        "notification",
        "home_wide",
        "batch_snapshot",
    ):
        assert deferred_term not in source
