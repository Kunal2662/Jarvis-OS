"""Milestone 7, Phase 1 -- domain/config/event scaffolding tests for
Workflow Intelligence.

Only verifies the new domain models (``WorkflowStep``,
``WorkflowDefinition``, ``ScheduleDefinition``), the new settings
(``AutomationSettings.max_parallel_steps``, ``AgentSettings.max_parallel_steps``,
``SchedulerSettings``), and the new events (``WorkflowStepEvent``,
``ScheduledJobFiredEvent``) construct correctly with the right defaults.
No builder, recorder, scheduler, executor, or agent-graph code exists yet
-- those are later phases; nothing here is wired into any service, tool,
or the DI container.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.core.config.settings import (
    AgentSettings,
    AutomationSettings,
    SchedulerSettings,
    Settings,
)
from jarvis.core.events.events import ScheduledJobFiredEvent, WorkflowStepEvent
from jarvis.domain.workflow import (
    ScheduleDefinition,
    ScheduleKind,
    WorkflowDefinition,
    WorkflowStep,
    WorkflowStepKind,
)

# ---------------------------------------------------------------------------
# Domain models
# ---------------------------------------------------------------------------


def test_workflow_step_defaults() -> None:
    step = WorkflowStep(kind=WorkflowStepKind.AUTOMATION)

    assert step.id
    assert step.instruction == ""
    assert step.tool_name == ""
    assert step.tool_args == {}
    assert step.depends_on == []
    assert step.label == ""


def test_workflow_step_automation_kind() -> None:
    step = WorkflowStep(kind=WorkflowStepKind.AUTOMATION, instruction="open notepad")

    assert step.kind is WorkflowStepKind.AUTOMATION
    assert step.instruction == "open notepad"


def test_workflow_step_agent_tool_kind() -> None:
    step = WorkflowStep(
        kind=WorkflowStepKind.AGENT_TOOL,
        tool_name="run_automation",
        tool_args={"instruction": "screenshot"},
    )

    assert step.kind is WorkflowStepKind.AGENT_TOOL
    assert step.tool_name == "run_automation"
    assert step.tool_args == {"instruction": "screenshot"}


def test_workflow_step_ids_are_unique() -> None:
    a = WorkflowStep(kind=WorkflowStepKind.AUTOMATION)
    b = WorkflowStep(kind=WorkflowStepKind.AUTOMATION)

    assert a.id != b.id


def test_workflow_step_depends_on_default_is_independent_per_instance() -> None:
    a = WorkflowStep(kind=WorkflowStepKind.AUTOMATION)
    b = WorkflowStep(kind=WorkflowStepKind.AUTOMATION)
    a.depends_on.append("something")

    assert b.depends_on == []


def test_workflow_definition_defaults() -> None:
    workflow = WorkflowDefinition(name="Morning briefing")

    assert workflow.name == "Morning briefing"
    assert workflow.steps == []
    assert workflow.description == ""
    assert workflow.id
    assert workflow.created_at is not None


def test_workflow_definition_holds_steps_in_order() -> None:
    step1 = WorkflowStep(kind=WorkflowStepKind.AUTOMATION, instruction="open notepad")
    step2 = WorkflowStep(
        kind=WorkflowStepKind.AUTOMATION, instruction="close notepad", depends_on=[step1.id]
    )
    workflow = WorkflowDefinition(name="Notepad cycle", steps=[step1, step2])

    assert workflow.steps == [step1, step2]
    assert workflow.steps[1].depends_on == [step1.id]


def test_schedule_definition_defaults_to_interval() -> None:
    schedule = ScheduleDefinition(workflow_id="wf-1")

    assert schedule.kind is ScheduleKind.INTERVAL
    assert schedule.interval_seconds == 0.0
    assert schedule.cron_expression == ""
    assert schedule.enabled is True
    assert schedule.id
    assert schedule.last_fired_at is None


def test_schedule_definition_cron_kind() -> None:
    schedule = ScheduleDefinition(
        workflow_id="wf-1", kind=ScheduleKind.CRON, cron_expression="0 8 * * *"
    )

    assert schedule.kind is ScheduleKind.CRON
    assert schedule.cron_expression == "0 8 * * *"


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


def test_automation_settings_max_parallel_steps_default() -> None:
    settings = AutomationSettings()

    assert settings.max_parallel_steps == 4


def test_agent_settings_max_parallel_steps_default() -> None:
    settings = AgentSettings()

    assert settings.max_parallel_steps == 4


def test_scheduler_settings_defaults() -> None:
    settings = SchedulerSettings()

    assert settings.enabled is True
    assert settings.poll_interval_seconds == 30.0
    assert settings.max_concurrent_jobs == 2


def test_automation_settings_max_parallel_steps_env_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JARVIS_AUTOMATION_MAX_PARALLEL_STEPS", "8")

    settings = AutomationSettings()

    assert settings.max_parallel_steps == 8


def test_agent_settings_max_parallel_steps_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JARVIS_AGENT_MAX_PARALLEL_STEPS", "6")

    settings = AgentSettings()

    assert settings.max_parallel_steps == 6


def test_scheduler_settings_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JARVIS_SCHEDULER_ENABLED", "false")
    monkeypatch.setenv("JARVIS_SCHEDULER_POLL_INTERVAL_SECONDS", "5")

    settings = SchedulerSettings()

    assert settings.enabled is False
    assert settings.poll_interval_seconds == 5.0


def test_scheduler_settings_ignores_unknown_keys() -> None:
    # extra="ignore" -- must not raise on an unrelated env var carrying
    # the same prefix-adjacent shape, matching every other settings block.
    settings = SchedulerSettings(unrelated_field="x")  # type: ignore[call-arg]

    assert settings.enabled is True


def test_root_settings_exposes_scheduler_block(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)

    assert isinstance(settings.scheduler, SchedulerSettings)
    assert settings.scheduler.enabled is True
    # Backward compatibility: existing blocks are untouched by this addition.
    assert settings.automation.max_parallel_steps == 4
    assert settings.agent.max_parallel_steps == 4


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------


def test_workflow_step_event_defaults() -> None:
    event = WorkflowStepEvent()

    assert event.workflow_id == ""
    assert event.step_id == ""
    assert event.status == ""
    assert event.id
    assert event.occurred_at is not None


def test_workflow_step_event_fields() -> None:
    event = WorkflowStepEvent(workflow_id="wf-1", step_id="step-1", status="succeeded")

    assert event.workflow_id == "wf-1"
    assert event.step_id == "step-1"
    assert event.status == "succeeded"


def test_scheduled_job_fired_event_defaults() -> None:
    event = ScheduledJobFiredEvent()

    assert event.schedule_id == ""
    assert event.workflow_id == ""
    assert event.status == ""


def test_scheduled_job_fired_event_fields() -> None:
    event = ScheduledJobFiredEvent(schedule_id="sched-1", workflow_id="wf-1", status="fired")

    assert event.schedule_id == "sched-1"
    assert event.workflow_id == "wf-1"
    assert event.status == "fired"
