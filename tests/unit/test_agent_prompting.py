"""Unit tests for the shared node-prompt helpers (Milestone 5-Agents)."""

from __future__ import annotations

import pytest

from jarvis.agents.prompting import (
    format_tool_call_history,
    format_tool_descriptions,
    parse_json_object,
    safe_complete,
)
from tests.fakes.fake_llm import FakeLLM


def test_parse_json_object_plain() -> None:
    assert parse_json_object('{"action": "final", "final_text": "hi"}') == {
        "action": "final",
        "final_text": "hi",
    }


def test_parse_json_object_strips_markdown_fence_and_prose() -> None:
    text = 'Sure, here you go:\n```json\n{"complete": true, "reason": "done"}\n```\nThanks!'
    assert parse_json_object(text) == {"complete": True, "reason": "done"}


def test_parse_json_object_returns_empty_dict_on_garbage() -> None:
    assert parse_json_object("not json at all") == {}
    assert parse_json_object("") == {}


def test_format_tool_call_history_empty() -> None:
    assert format_tool_call_history([]) == "(none yet)"


def test_format_tool_call_history_renders_success_and_error() -> None:
    calls = [
        {"tool": "recall_memory", "args": {"query": "x"}, "result": "found it"},
        {"tool": "run_automation", "args": {"instruction": "y"}, "error": "denied"},
    ]
    rendered = format_tool_call_history(calls)
    # Successful results are fenced as untrusted data (prompt-injection
    # mitigation — see UNTRUSTED_TOOL_OUTPUT_NOTICE in agents/prompting.py).
    expected_success = (
        "recall_memory({'query': 'x'}) -> <<<TOOL_OUTPUT>>>found it<<<END_TOOL_OUTPUT>>>"
    )
    assert expected_success in rendered
    assert "run_automation({'instruction': 'y'}) -> ERROR: denied" in rendered


def test_format_tool_descriptions_empty() -> None:
    assert format_tool_descriptions([]) == "(no tools available)"


def test_format_tool_descriptions_lists_name_args_and_description() -> None:
    pytest.importorskip("langchain_core")
    from langchain_core.tools import tool

    @tool
    async def example_tool(query: str, top_k: int = 5) -> str:
        """Look something up."""
        return "unused"

    rendered = format_tool_descriptions([example_tool])
    assert "example_tool(" in rendered
    assert "query" in rendered
    assert "Look something up." in rendered


@pytest.mark.asyncio
async def test_safe_complete_returns_fallback_on_provider_error() -> None:
    llm = FakeLLM(fail=True)
    result = await safe_complete(llm, "hello", fallback="fallback text")
    assert result == "fallback text"


@pytest.mark.asyncio
async def test_safe_complete_returns_llm_output_on_success() -> None:
    llm = FakeLLM("real answer")
    result = await safe_complete(llm, "hello", fallback="fallback text")
    assert result == "real answer"
