"""Unit tests for individual LangGraph node factories (Milestone 5-Agents).

Each node is tested in isolation with :class:`ScriptedFakeLLM` so the
graph's control flow (tool vs. final, complete vs. needs-more-work) can
be asserted deterministically without a real LLM or the compiled graph.
"""

from __future__ import annotations

import pytest

from jarvis.agents.state import AgentState
from tests.fakes.fake_scripted_llm import ScriptedFakeLLM

pytest.importorskip("langchain_core")


def _make_add_tool():
    from langchain_core.tools import tool

    @tool
    async def add_numbers(a: int, b: int) -> str:
        """Add two numbers together."""
        return str(a + b)

    return add_numbers


@pytest.mark.asyncio
async def test_planner_node_sets_plan() -> None:
    from jarvis.agents.nodes.planner import make_planner_node

    llm = ScriptedFakeLLM({"planning module": "1. Add the numbers.\n2. Reply with the sum."})
    node = make_planner_node(llm, [_make_add_tool()])

    result = await node({"prompt": "what is 2 + 2?"})

    assert result["plan"] == "1. Add the numbers.\n2. Reply with the sum."
    assert result["last_node"] == "planner"


@pytest.mark.asyncio
async def test_planner_node_falls_back_on_llm_failure() -> None:
    from jarvis.agents.nodes.planner import make_planner_node

    llm = ScriptedFakeLLM({}, fail=True)
    node = make_planner_node(llm, [])

    result = await node({"prompt": "hello"})

    assert "directly" in result["plan"].lower()


@pytest.mark.asyncio
async def test_tool_selector_node_chooses_valid_tool() -> None:
    from jarvis.agents.nodes.tool_selector import make_tool_selector_node

    llm = ScriptedFakeLLM(
        {
            "tool-selection module": (
                '{"action": "tool", "tool": "add_numbers", "args": {"a": 2, "b": 2}}'
            )
        }
    )
    node = make_tool_selector_node(llm, [_make_add_tool()])

    result = await node({"prompt": "what is 2 + 2?", "plan": "add them", "tool_calls": []})

    assert result["next_action"] == "tool"
    assert result["tool_name"] == "add_numbers"
    assert result["tool_args"] == {"a": 2, "b": 2}


@pytest.mark.asyncio
async def test_tool_selector_node_rejects_unknown_tool_name() -> None:
    from jarvis.agents.nodes.tool_selector import make_tool_selector_node

    llm = ScriptedFakeLLM(
        {"tool-selection module": '{"action": "tool", "tool": "does_not_exist", "args": {}}'}
    )
    node = make_tool_selector_node(llm, [_make_add_tool()])

    result = await node({"prompt": "x", "plan": "", "tool_calls": []})

    # A hallucinated tool name must never be trusted through to the executor.
    assert result["next_action"] == "final"


@pytest.mark.asyncio
async def test_tool_selector_node_final_action() -> None:
    from jarvis.agents.nodes.tool_selector import make_tool_selector_node

    llm = ScriptedFakeLLM(
        {"tool-selection module": '{"action": "final", "final_text": "The answer is 4."}'}
    )
    node = make_tool_selector_node(llm, [_make_add_tool()])

    result = await node({"prompt": "what is 2 + 2?", "plan": "", "tool_calls": []})

    assert result["next_action"] == "final"
    assert result["final_response"] == "The answer is 4."


@pytest.mark.asyncio
async def test_tool_executor_node_runs_selected_tool() -> None:
    from jarvis.agents.nodes.tool_executor import make_tool_executor_node

    add_numbers = _make_add_tool()
    node = make_tool_executor_node({add_numbers.name: add_numbers})
    state: AgentState = {
        "tool_name": "add_numbers",
        "tool_args": {"a": 2, "b": 2},
        "tool_calls": [],
        "step": 0,
    }

    result = await node(state)

    assert result["step"] == 1
    assert result["tool_calls"][0]["result"] == "4"
    assert "error" not in result["tool_calls"][0]


@pytest.mark.asyncio
async def test_tool_executor_node_records_error_for_unknown_tool() -> None:
    from jarvis.agents.nodes.tool_executor import make_tool_executor_node

    node = make_tool_executor_node({})

    result = await node({"tool_name": "missing", "tool_args": {}, "tool_calls": [], "step": 0})

    assert "Unknown tool" in result["tool_calls"][0]["error"]
    assert result["step"] == 1


@pytest.mark.asyncio
async def test_tool_executor_node_captures_tool_exception() -> None:
    from langchain_core.tools import tool as lc_tool

    from jarvis.agents.nodes.tool_executor import make_tool_executor_node

    @lc_tool
    async def boom() -> str:
        """Always fails."""
        raise RuntimeError("kaboom")

    node = make_tool_executor_node({"boom": boom})

    result = await node({"tool_name": "boom", "tool_args": {}, "tool_calls": [], "step": 0})

    assert "kaboom" in result["tool_calls"][0]["error"]


@pytest.mark.asyncio
async def test_critic_node_marks_complete() -> None:
    from jarvis.agents.nodes.critic import make_critic_node

    llm = ScriptedFakeLLM({"self-critique module": '{"complete": true, "reason": "done"}'})
    node = make_critic_node(llm)

    result = await node({"prompt": "x", "plan": "", "tool_calls": []})

    assert result["needs_more_work"] is False
    assert result["critique"] == "done"


@pytest.mark.asyncio
async def test_critic_node_requests_more_work() -> None:
    from jarvis.agents.nodes.critic import make_critic_node

    llm = ScriptedFakeLLM({"self-critique module": '{"complete": false, "reason": "need more"}'})
    node = make_critic_node(llm)

    result = await node({"prompt": "x", "plan": "", "tool_calls": []})

    assert result["needs_more_work"] is True


@pytest.mark.asyncio
async def test_responder_node_uses_existing_final_response() -> None:
    from jarvis.agents.nodes.responder import make_responder_node

    node = make_responder_node(ScriptedFakeLLM({}))

    result = await node(
        {"prompt": "x", "plan": "", "tool_calls": [], "final_response": "already answered"}
    )

    assert result["last_node"] == "responder"
    assert "final_response" not in result  # untouched — selector already wrote it


@pytest.mark.asyncio
async def test_responder_node_composes_answer_from_tool_results() -> None:
    from jarvis.agents.nodes.responder import make_responder_node

    llm = ScriptedFakeLLM({"Compose the final answer": "The sum is 4."})
    node = make_responder_node(llm)

    result = await node(
        {
            "prompt": "what is 2 + 2?",
            "plan": "add",
            "tool_calls": [{"tool": "add_numbers", "args": {}, "result": "4"}],
            "final_response": "",
        }
    )

    assert result["final_response"] == "The sum is 4."
