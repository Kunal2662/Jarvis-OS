"""Assembles the full agent tool list from whichever services are injected.

Every service the roadmap names (``ChatService``, ``VoiceService``,
``MemoryService``, ``AutomationService``, ``BrowserService``,
``SystemService``) is optional here on purpose: ``AgentOrchestrator``'s
constructor keeps ``memory``/``automation``/``browser`` required (its
pre-existing signature) and ``chat``/``voice``/``system`` optional, so
tests and future call sites can build a narrower agent without wiring
every service.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from langchain_core.tools import BaseTool

if TYPE_CHECKING:
    from jarvis.services.alarm_control_panel_service import AlarmControlPanelService
    from jarvis.services.appliance_service import ApplianceService
    from jarvis.services.automation_service import AutomationService
    from jarvis.services.browser_service import BrowserService
    from jarvis.services.chat_service import ChatService
    from jarvis.services.integration_service import IntegrationService
    from jarvis.services.intelligence_service import IntelligenceService
    from jarvis.services.knowledge_service import KnowledgeService
    from jarvis.services.media_player_service import MediaPlayerService
    from jarvis.services.memory_service import MemoryService
    from jarvis.services.security_service import SecurityService
    from jarvis.services.sensor_service import SensorService
    from jarvis.services.siren_service import SirenService
    from jarvis.services.smart_home_memory_service import SmartHomeMemoryService
    from jarvis.services.smart_lighting_service import SmartLightingService
    from jarvis.services.smart_lock_service import SmartLockService
    from jarvis.services.smart_switch_service import SmartSwitchService
    from jarvis.services.system_service import SystemService
    from jarvis.services.thermostat_service import ThermostatService
    from jarvis.services.vacuum_humidifier_service import VacuumHumidifierService
    from jarvis.services.vision_service import VisionService
    from jarvis.services.voice_service import VoiceService
    from jarvis.services.water_heater_service import WaterHeaterService
    from jarvis.services.workspace_ai_service import WorkspaceAssistantService


def build_tool_registry(
    *,
    memory: MemoryService | None = None,
    automation: AutomationService | None = None,
    browser: BrowserService | None = None,
    system: SystemService | None = None,
    voice: VoiceService | None = None,
    chat: ChatService | None = None,
    vision: VisionService | None = None,
    knowledge: KnowledgeService | None = None,
    intelligence: IntelligenceService | None = None,
    workspace_assistant: WorkspaceAssistantService | None = None,
    integrations: IntegrationService | None = None,
    smart_lighting: SmartLightingService | None = None,
    smart_lock: SmartLockService | None = None,
    sensors: SensorService | None = None,
    smart_switch: SmartSwitchService | None = None,
    appliances: ApplianceService | None = None,
    thermostats: ThermostatService | None = None,
    vacuum_humidifier: VacuumHumidifierService | None = None,
    media_players: MediaPlayerService | None = None,
    water_heaters: WaterHeaterService | None = None,
    security: SecurityService | None = None,
    siren: SirenService | None = None,
    alarm_control_panels: AlarmControlPanelService | None = None,
    smart_home_memory: SmartHomeMemoryService | None = None,
) -> list[BaseTool]:
    tools: list[BaseTool] = []

    if memory is not None:
        from jarvis.agents.tools.memory_tools import build_memory_tools

        tools += build_memory_tools(memory)
    if knowledge is not None:
        from jarvis.agents.tools.knowledge_tools import build_knowledge_tools

        tools += build_knowledge_tools(knowledge)
    if intelligence is not None:
        from jarvis.agents.tools.intelligence_tools import build_intelligence_tools

        tools += build_intelligence_tools(intelligence)
    if workspace_assistant is not None:
        # Milestone 11 Task Group D. Optional like every other service
        # here, and deliberately *not* passed by `_build_search_service`'s
        # own `build_tool_registry` call: the assistant composes
        # `SearchService`, so resolving it there would close a cycle at
        # the composition root.
        from jarvis.agents.tools.workspace_tools import build_workspace_tools

        tools += build_workspace_tools(workspace_assistant)
    if integrations is not None:
        # Milestone 11 Task Group E. Four discovery-and-invoke tools
        # rather than one per vendor operation -- see
        # `agents/tools/integration_tools.py` for why the catalogue does
        # not belong on the tool-selection prompt.
        from jarvis.agents.tools.integration_tools import build_integration_tools

        tools += build_integration_tools(integrations)
    if smart_lighting is not None:
        # Milestone 12 Connectivity REST + Smart Lighting. One tool per
        # normalized operation -- see `agents/tools/smart_lighting_tools.py`
        # for why this differs from the integrations catalogue's
        # discover-then-invoke pair.
        from jarvis.agents.tools.smart_lighting_tools import build_smart_lighting_tools

        tools += build_smart_lighting_tools(smart_lighting)
    if smart_lock is not None:
        # Milestone 12 Smart Locks. Four tools, mirroring Smart
        # Lighting's own registration exactly -- see
        # `agents/tools/smart_lock_tools.py`.
        from jarvis.agents.tools.smart_lock_tools import build_smart_lock_tools

        tools += build_smart_lock_tools(smart_lock)
    if sensors is not None:
        # Milestone 12 Sensors. Four read-only tools, mirroring Smart
        # Locks' own registration exactly -- see
        # `agents/tools/sensor_tools.py`.
        from jarvis.agents.tools.sensor_tools import build_sensor_tools

        tools += build_sensor_tools(sensors)
    if smart_switch is not None:
        # Milestone 12 Energy Management (Core Energy Slice). Four
        # tools, mirroring Smart Locks' own registration exactly -- see
        # `agents/tools/smart_switch_tools.py`.
        from jarvis.agents.tools.smart_switch_tools import build_smart_switch_tools

        tools += build_smart_switch_tools(smart_switch)
    if appliances is not None:
        # Milestone 12 Appliance Control (Core Appliance Slice: Fans +
        # Covers). Eight tools, mirroring Smart Switches' own
        # registration, doubled for the two capabilities -- see
        # `agents/tools/appliance_tools.py`.
        from jarvis.agents.tools.appliance_tools import build_appliance_tools

        tools += build_appliance_tools(appliances)
    if thermostats is not None:
        # Milestone 12 Appliance Control (Climate / Thermostat Slice).
        # Three tools -- mutation is one merged `set_thermostat_state`,
        # mirroring Smart Lighting's own single `set_light_state` rather
        # than one tool per attribute -- see
        # `agents/tools/thermostat_tools.py`.
        from jarvis.agents.tools.thermostat_tools import build_thermostat_tools

        tools += build_thermostat_tools(thermostats)
    if vacuum_humidifier is not None:
        # Milestone 12 Appliance Control (Vacuum + Humidifier Core
        # Slice). Nine tools: six vacuum verbs mirroring Fan/Cover's
        # one-tool-per-command shape, three humidifier tools with a
        # merged mutation mirroring Thermostat's shape -- see
        # `agents/tools/vacuum_humidifier_tools.py`.
        from jarvis.agents.tools.vacuum_humidifier_tools import build_vacuum_humidifier_tools

        tools += build_vacuum_humidifier_tools(vacuum_humidifier)
    if media_players is not None:
        # Milestone 12 Appliance Control (Media Player Core Slice).
        # Eight tools: five transport verbs mirroring Vacuum's
        # one-tool-per-command shape, one merged state tool mirroring
        # Thermostat's shape -- see
        # `agents/tools/media_player_tools.py`.
        from jarvis.agents.tools.media_player_tools import build_media_player_tools

        tools += build_media_player_tools(media_players)
    if water_heaters is not None:
        # Milestone 12 Appliance Control (Water Heater Core Slice).
        # Three tools: mutation is one merged `set_water_heater_state`,
        # mirroring Thermostat's own single `set_thermostat_state`
        # rather than one tool per attribute -- see
        # `agents/tools/water_heater_tools.py`.
        from jarvis.agents.tools.water_heater_tools import build_water_heater_tools

        tools += build_water_heater_tools(water_heaters)
    if security is not None:
        # Milestone 12 Security & Safety (Read-Only Alert/Status
        # Slice). Two read-only tools, mirroring Sensors' own
        # "terse re-shaping of one underlying call" registration -- see
        # `agents/tools/security_tools.py`.
        from jarvis.agents.tools.security_tools import build_security_tools

        tools += build_security_tools(security)
    if siren is not None:
        # Milestone 12 Security & Safety (Siren Integration Slice).
        # Four tools, mirroring Smart Switch's own registration --
        # `turn_siren_on` alone is added to
        # `AgentSettings.confirm_required_tools`, the existing
        # confirmation mechanism, not a new one -- see
        # `agents/tools/siren_tools.py`.
        from jarvis.agents.tools.siren_tools import build_siren_tools

        tools += build_siren_tools(siren)
    if alarm_control_panels is not None:
        # Milestone 12 Security & Safety (alarm_control_panel
        # Integration Slice). Five tools, mirroring Siren's own
        # registration -- `disarm` alone is added to
        # `AgentSettings.confirm_required_tools`, the existing
        # confirmation mechanism, not a new one -- see
        # `agents/tools/alarm_control_panel_tools.py`. No tool accepts
        # a code/pin argument.
        from jarvis.agents.tools.alarm_control_panel_tools import (
            build_alarm_control_panel_tools,
        )

        tools += build_alarm_control_panel_tools(alarm_control_panels)
    if smart_home_memory is not None:
        # Milestone 12 Smart Home Memory (Manual/On-Demand Device
        # Snapshot Slice). Two tools, mirroring Security's own
        # "terse re-shaping of one underlying call" registration -- see
        # `agents/tools/smart_home_memory_tools.py`.
        from jarvis.agents.tools.smart_home_memory_tools import build_smart_home_memory_tools

        tools += build_smart_home_memory_tools(smart_home_memory)
    if automation is not None:
        from jarvis.agents.tools.automation_tools import build_automation_tools

        tools += build_automation_tools(automation)
    if browser is not None:
        from jarvis.agents.tools.browser_tools import build_browser_tools

        tools += build_browser_tools(browser)
    if system is not None:
        from jarvis.agents.tools.system_tools import build_system_tools

        tools += build_system_tools(system)
    if voice is not None:
        from jarvis.agents.tools.voice_tools import build_voice_tools

        tools += build_voice_tools(voice)
    if chat is not None:
        from jarvis.agents.tools.chat_tools import build_chat_tools

        tools += build_chat_tools(chat)
    if vision is not None:
        from jarvis.agents.tools.vision_tools import build_vision_tools

        tools += build_vision_tools(vision)

    return tools
