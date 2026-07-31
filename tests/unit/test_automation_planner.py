"""Unit tests for :class:`TaskPlanner`."""

from __future__ import annotations

from jarvis.domain.automation.models import ActionType
from jarvis.features.automation.planner import TaskPlanner


def test_single_instruction_is_one_step() -> None:
    plan = TaskPlanner().build_plan("Open Chrome")
    assert len(plan.steps) == 1
    assert plan.steps[0].action is ActionType.OPEN_APP
    assert plan.steps[0].depends_on == []


def test_multi_step_instruction_chains_dependencies() -> None:
    plan = TaskPlanner().build_plan(
        "Create folder named Work\nOpen Chrome\nSearch Google for Tesla"
    )
    assert len(plan.steps) == 3
    assert plan.steps[0].depends_on == []
    assert plan.steps[1].depends_on == [plan.steps[0].id]
    assert plan.steps[2].depends_on == [plan.steps[1].id]


def test_then_separator_splits_into_steps() -> None:
    plan = TaskPlanner().build_plan("Open Chrome then Open Spotify then Take screenshot")
    assert [s.action for s in plan.steps] == [
        ActionType.OPEN_APP,
        ActionType.OPEN_APP,
        ActionType.SCREENSHOT,
    ]


def test_parallel_marker_breaks_the_dependency_chain() -> None:
    plan = TaskPlanner().build_plan("Open Chrome\nOpen Spotify at the same time")
    assert plan.steps[1].depends_on == []


def test_max_retries_propagates_to_steps() -> None:
    plan = TaskPlanner(default_max_retries=2).build_plan("Open Chrome")
    assert plan.steps[0].max_retries == 2


def test_plan_preserves_raw_text() -> None:
    text = "Open Chrome"
    plan = TaskPlanner().build_plan(text)
    assert plan.raw_text == text
