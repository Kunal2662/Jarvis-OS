"""AI Workspace domain tests -- Milestone 11 Task Group D.

The pure half: clipping, packing, ordering, rendering and prompt
construction. No database, no service, no container -- every assertion
here is about a total function, which is the whole reason this logic
lives in ``domain/`` rather than inside the manager that calls it.
"""

from __future__ import annotations

import pytest

from jarvis.domain.ai_workspace.models import (
    ASSIST_MODES,
    CONTEXT_SECTIONS,
    DEFAULT_CONTEXT_BUDGET_CHARS,
    LINK_SOURCES,
    LINK_TARGETS,
    MIN_CONTEXT_BUDGET_CHARS,
    SECTION_ORDER,
    ContextItem,
    ContextSection,
    WorkspaceContext,
    build_assist_prompt,
    clip,
    order_sections,
    pack,
    render_results,
)

# --- vocabularies ---------------------------------------------------------------


def test_section_order_and_membership_agree() -> None:
    """One list, two uses. If they ever disagree, a section could be
    rendered under a name nothing recognises."""
    assert sorted(CONTEXT_SECTIONS) == sorted(SECTION_ORDER)
    assert len(SECTION_ORDER) == len(set(SECTION_ORDER))


def test_link_targets_exclude_events_and_reminders() -> None:
    """Deliberately not attachments' five. A knowledge link records that
    prose was about something, and an event's workspace lives on its
    calendar -- see ``WorkspaceKnowledgeLink``'s docstring."""
    assert sorted(LINK_TARGETS) == ["file", "note", "project", "task", "workspace"]
    assert "event" not in LINK_TARGETS
    assert "reminder" not in LINK_TARGETS


def test_link_sources_separate_extraction_from_assertion() -> None:
    assert sorted(LINK_SOURCES) == ["extracted", "manual"]


def test_assist_modes_are_the_three_shipped() -> None:
    assert sorted(ASSIST_MODES) == ["ask", "next_actions", "summarize"]


# --- clip -----------------------------------------------------------------------


def test_clip_leaves_short_text_alone() -> None:
    assert clip("hello", 20) == "hello"


def test_clip_collapses_whitespace() -> None:
    """Rendered into prompts and JSON, so a note written with newlines
    must not become a multi-line context item."""
    assert clip("a\n\n  b\tc", 20) == "a b c"


def test_clip_marks_that_it_trimmed() -> None:
    trimmed = clip("x" * 50, 10)
    assert len(trimmed) == 10
    assert trimmed.endswith("...")


def test_clip_of_zero_or_negative_is_empty() -> None:
    assert clip("anything", 0) == ""
    assert clip("anything", -5) == ""


def test_clip_below_the_ellipsis_width_still_bounds() -> None:
    assert clip("abcdef", 2) == "ab"


# --- items and sections ---------------------------------------------------------


def test_item_renders_title_only_without_detail() -> None:
    assert ContextItem(title="Ship it").render() == "- Ship it"


def test_item_renders_title_and_detail() -> None:
    assert ContextItem(title="Ship it", detail="by Friday").render() == "- Ship it -- by Friday"


def test_item_render_respects_the_item_budget() -> None:
    rendered = ContextItem(title="t" * 100, detail="d" * 100).render(item_chars=40)
    assert len(rendered) <= 40 + len("- ")


def test_empty_section_renders_as_nothing() -> None:
    """A prompt full of headings with nothing under them teaches a model
    that this workspace has headings, not notes."""
    assert ContextSection(name="notes").render() == ""


def test_section_reports_truncation_with_a_count() -> None:
    section = ContextSection(name="tasks", items=(ContextItem(title="one"),), total=40)
    assert section.truncated is True
    assert "(+39 more)" in section.render()


def test_untruncated_section_says_nothing_about_more() -> None:
    section = ContextSection(name="tasks", items=(ContextItem(title="one"),), total=1)
    assert section.truncated is False
    assert "more)" not in section.render()


def test_section_as_dict_carries_the_truncation_flag() -> None:
    payload = ContextSection(name="notes", items=(ContextItem(title="n"),), total=3).as_dict()
    assert payload["truncated"] is True
    assert payload["total"] == 3
    assert payload["items"][0]["title"] == "n"


# --- ordering -------------------------------------------------------------------


def test_order_sections_uses_the_fixed_editorial_order() -> None:
    scrambled = [ContextSection(name=name) for name in ("memories", "workspace", "tasks")]
    assert [s.name for s in order_sections(scrambled)] == ["workspace", "tasks", "memories"]


def test_an_unknown_section_sorts_last_rather_than_raising() -> None:
    """A rendering helper losing a section silently would be worse than
    showing it late."""
    sections = [ContextSection(name="mystery"), ContextSection(name="workspace")]
    assert [s.name for s in order_sections(sections)] == ["workspace", "mystery"]


# --- packing --------------------------------------------------------------------


def _section(name: str, count: int, *, width: int = 20) -> ContextSection:
    items = tuple(ContextItem(title=f"{name}-{i}" + "x" * width) for i in range(count))
    return ContextSection(name=name, items=items, total=count)


def test_pack_keeps_everything_when_the_budget_is_ample() -> None:
    context = pack(
        [_section("workspace", 1), _section("notes", 2)],
        workspace_id="w1",
        budget_chars=DEFAULT_CONTEXT_BUDGET_CHARS,
    )
    assert [s.name for s in context.sections] == ["workspace", "notes"]
    assert not context.truncated_sections
    assert context.used_chars > 0


def test_pack_spends_the_budget_in_section_order() -> None:
    """Greedy and ordered: the workspace header survives and the tail is
    what goes, which is the priority the ordering encodes."""
    context = pack(
        [_section("workspace", 1), _section("memories", 20)],
        workspace_id="w1",
        budget_chars=MIN_CONTEXT_BUDGET_CHARS,
    )
    assert len(context.section("workspace").items) == 1  # type: ignore[union-attr]
    memories = context.section("memories")
    assert memories is not None
    assert len(memories.items) < 20


def test_pack_never_exceeds_the_budget() -> None:
    context = pack(
        [_section(name, 30) for name in SECTION_ORDER],
        workspace_id="w1",
        budget_chars=500,
    )
    assert context.used_chars <= 500
    assert len(context.render()) <= 500 + len(SECTION_ORDER) * 2


def test_pack_raises_a_too_small_budget_to_the_floor() -> None:
    """An empty context is a worse answer than a small one."""
    context = pack([_section("workspace", 1)], workspace_id="w1", budget_chars=5)
    assert context.budget_chars == MIN_CONTEXT_BUDGET_CHARS
    assert context.section("workspace").items  # type: ignore[union-attr]


def test_pack_reports_sections_it_could_not_fit_at_all() -> None:
    context = pack(
        [_section("workspace", 5, width=200), _section("memories", 5, width=200)],
        workspace_id="w1",
        budget_chars=MIN_CONTEXT_BUDGET_CHARS,
    )
    assert "memories" in context.dropped_sections


def test_pack_preserves_totals_so_truncation_is_visible() -> None:
    """A section holding three of forty tasks must say so, instead of
    looking like a workspace with three tasks."""
    context = pack([_section("tasks", 40)], workspace_id="w1", budget_chars=300)
    tasks = context.section("tasks")
    assert tasks is not None
    assert tasks.total == 40
    assert len(tasks.items) < 40
    assert "tasks" in context.truncated_sections


def test_pack_carries_the_workspace_name() -> None:
    context = pack([], workspace_id="w1", workspace_name="Research")
    assert context.workspace_name == "Research"
    assert context.as_dict()["workspace_name"] == "Research"


def test_pack_of_nothing_is_an_empty_context() -> None:
    context = pack([], workspace_id="w1")
    assert context.is_empty is True
    assert context.render() == ""


def test_context_section_lookup_misses_return_none() -> None:
    assert WorkspaceContext(workspace_id="w1").section("nope") is None


def test_context_as_dict_includes_the_rendered_text() -> None:
    """One object serves the prompt and the REST payload, so the two can
    never disagree about what the model was shown."""
    context = pack([_section("workspace", 1)], workspace_id="w1")
    payload = context.as_dict()
    assert payload["text"] == context.render()
    assert payload["budget_chars"] == context.budget_chars


# --- prompts --------------------------------------------------------------------


def test_prompt_states_the_grounding_rule_for_every_mode() -> None:
    for mode in sorted(ASSIST_MODES):
        prompt = build_assist_prompt(
            mode=mode, workspace_name="Research", context_text="Context here"
        )
        assert "Do not invent" in prompt
        assert "Workspace: Research" in prompt
        assert "Context here" in prompt


def test_ask_mode_includes_the_question() -> None:
    prompt = build_assist_prompt(
        mode="ask", workspace_name="W", context_text="c", question="what is late?"
    )
    assert "Question: what is late?" in prompt


def test_summarize_mode_omits_a_question_line() -> None:
    prompt = build_assist_prompt(mode="summarize", workspace_name="W", context_text="c")
    assert "Question:" not in prompt


def test_next_actions_mode_demands_provenance() -> None:
    prompt = build_assist_prompt(mode="next_actions", workspace_name="W", context_text="c")
    assert "say which item it comes from" in prompt


def test_unknown_mode_falls_back_to_summarize_rather_than_raising() -> None:
    """Mode validation belongs to the service, which rejects with a
    ``ServiceError``. This function is total on purpose."""
    prompt = build_assist_prompt(mode="nonsense", workspace_name="W", context_text="c")
    assert "Summarize the state of this workspace" in prompt


def test_empty_context_is_stated_rather_than_left_blank() -> None:
    prompt = build_assist_prompt(mode="summarize", workspace_name="W", context_text="")
    assert "(no workspace context available)" in prompt


def test_retrieved_text_is_a_separate_labelled_block() -> None:
    prompt = build_assist_prompt(
        mode="ask",
        workspace_name="W",
        context_text="c",
        retrieved_text="- [notes] hit",
        question="q",
    )
    assert "Retrieved for this question:" in prompt
    assert "- [notes] hit" in prompt


def test_render_results_labels_each_row_with_its_source() -> None:
    rendered = render_results([("notes", "Standup", "we discussed the migration")])
    assert rendered.startswith("- [notes] Standup")
    assert "migration" in rendered


def test_render_results_of_nothing_is_empty() -> None:
    assert render_results([]) == ""


@pytest.mark.parametrize("budget", [MIN_CONTEXT_BUDGET_CHARS, 1000, DEFAULT_CONTEXT_BUDGET_CHARS])
def test_packing_is_deterministic(budget: int) -> None:
    """Same input, same output -- the property that lets a prompt be
    asserted at all."""
    sections = [_section(name, 12) for name in SECTION_ORDER]
    first = pack(sections, workspace_id="w1", budget_chars=budget)
    second = pack(sections, workspace_id="w1", budget_chars=budget)
    assert first.render() == second.render()
    assert first.used_chars == second.used_chars
