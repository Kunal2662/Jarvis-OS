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
    assert result["response_mode"] == "composed"


# ---------------------------------------------------------------------------
# Milestone 10 -- Intent Engine
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_intent_classifier_node_parses_valid_intent() -> None:
    from jarvis.agents.nodes.intent_classifier import make_intent_classifier_node

    llm = ScriptedFakeLLM(
        {"intent classification module": '{"intent": "direct_answer", "confidence": 0.9}'}
    )
    node = make_intent_classifier_node(llm)

    result = await node({"prompt": "what is the capital of France?"})

    assert result["intent"] == "direct_answer"
    assert result["intent_confidence"] == 0.9
    assert result["last_node"] == "intent_classifier"


@pytest.mark.asyncio
async def test_intent_classifier_node_falls_back_on_invalid_intent() -> None:
    from jarvis.agents.nodes.intent_classifier import make_intent_classifier_node

    llm = ScriptedFakeLLM(
        {"intent classification module": '{"intent": "nonsense", "confidence": 2.0}'}
    )
    node = make_intent_classifier_node(llm)

    result = await node({"prompt": "hi"})

    assert result["intent"] == "tool_use"
    assert result["intent_confidence"] == 1.0  # clamped


@pytest.mark.asyncio
async def test_intent_classifier_node_falls_back_on_llm_failure() -> None:
    from jarvis.agents.nodes.intent_classifier import make_intent_classifier_node

    node = make_intent_classifier_node(ScriptedFakeLLM({}, fail=True))

    result = await node({"prompt": "hi"})

    assert result["intent"] == "tool_use"


# ---------------------------------------------------------------------------
# Milestone 10 -- Context Engine
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_context_engine_node_returns_empty_when_no_memory_service() -> None:
    from jarvis.agents.nodes.context_engine import make_context_engine_node

    node = make_context_engine_node(None)

    result = await node({"prompt": "what's my birthday?"})

    assert result["context"] == ""
    assert result["last_node"] == "context_engine"


@pytest.mark.asyncio
async def test_context_engine_node_formats_recalled_memories() -> None:
    from dataclasses import dataclass

    from jarvis.agents.nodes.context_engine import make_context_engine_node

    @dataclass
    class _Rec:
        content: str

    class _Memory:
        async def recall(self, query: str, *, top_k: int = 5) -> list[_Rec]:
            return [_Rec(content="Birthday is in March"), _Rec(content="Likes tea")]

    node = make_context_engine_node(_Memory())

    result = await node({"prompt": "what's my birthday?"})

    assert "Birthday is in March" in result["context"]
    assert "Likes tea" in result["context"]


@pytest.mark.asyncio
async def test_context_engine_node_tolerates_memory_failure() -> None:
    from jarvis.agents.nodes.context_engine import make_context_engine_node

    class _BrokenMemory:
        async def recall(self, query: str, *, top_k: int = 5) -> list[object]:
            raise RuntimeError("db unavailable")

    node = make_context_engine_node(_BrokenMemory())

    result = await node({"prompt": "x"})

    assert result["context"] == ""


@pytest.mark.asyncio
async def test_context_engine_node_includes_knowledge_when_supplied() -> None:
    """Milestone 10A closes M10's own documented deferral: Context Engine
    now also draws on the knowledge graph when one is supplied."""
    from dataclasses import dataclass, field

    from jarvis.agents.nodes.context_engine import make_context_engine_node

    @dataclass
    class _Rel:
        predicate: str
        other_entity: str
        direction: str
        confidence: float = 0.9

    @dataclass
    class _Detail:
        id: str = "e1"
        name: str = "Project X"
        entity_type: str = "project"
        description: str = "A project."
        confidence: float = 0.9
        relationships: list = field(default_factory=lambda: [_Rel("works_on", "Alice", "incoming")])
        memory_contents: list = field(default_factory=list)

    class _Knowledge:
        async def get_entity_detail(self, query: str):
            return _Detail()

    node = make_context_engine_node(None, _Knowledge())

    result = await node({"prompt": "what do you know about Project X?"})

    assert "Project X" in result["context"]
    assert "works_on" in result["context"]


@pytest.mark.asyncio
async def test_context_engine_node_tolerates_knowledge_failure() -> None:
    from jarvis.agents.nodes.context_engine import make_context_engine_node

    class _BrokenKnowledge:
        async def get_entity_detail(self, query: str):
            raise RuntimeError("db unavailable")

    node = make_context_engine_node(None, _BrokenKnowledge())

    result = await node({"prompt": "x"})

    assert result["context"] == ""


# ---------------------------------------------------------------------------
# Milestone 10 AC1 -- parallel tool dispatch
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_tool_selector_node_chooses_parallel_tools() -> None:
    from jarvis.agents.nodes.tool_selector import make_tool_selector_node

    llm = ScriptedFakeLLM(
        {
            "tool-selection module": (
                '{"action": "tool_parallel", "tools": '
                '[{"tool": "add_numbers", "args": {"a": 1, "b": 2}}, '
                '{"tool": "add_numbers", "args": {"a": 3, "b": 4}}]}'
            )
        }
    )
    node = make_tool_selector_node(llm, [_make_add_tool()])

    result = await node({"prompt": "add two pairs", "plan": "", "tool_calls": []})

    assert result["next_action"] == "tool_parallel"
    assert result["pending_tool_calls"] == [
        {"tool": "add_numbers", "args": {"a": 1, "b": 2}},
        {"tool": "add_numbers", "args": {"a": 3, "b": 4}},
    ]


@pytest.mark.asyncio
async def test_tool_selector_node_parallel_drops_hallucinated_tools() -> None:
    from jarvis.agents.nodes.tool_selector import make_tool_selector_node

    llm = ScriptedFakeLLM(
        {
            "tool-selection module": (
                '{"action": "tool_parallel", "tools": ' '[{"tool": "does_not_exist", "args": {}}]}'
            )
        }
    )
    node = make_tool_selector_node(llm, [_make_add_tool()])

    result = await node({"prompt": "x", "plan": "", "tool_calls": []})

    # every proposed call was hallucinated -> falls back to "final"
    assert result["next_action"] == "final"


@pytest.mark.asyncio
async def test_tool_executor_node_dispatches_parallel_calls_concurrently() -> None:
    from jarvis.agents.nodes.tool_executor import make_tool_executor_node

    add_numbers = _make_add_tool()
    node = make_tool_executor_node({add_numbers.name: add_numbers}, max_parallel_steps=4)
    state: AgentState = {
        "next_action": "tool_parallel",
        "pending_tool_calls": [
            {"tool": "add_numbers", "args": {"a": 1, "b": 2}},
            {"tool": "add_numbers", "args": {"a": 3, "b": 4}},
        ],
        "tool_calls": [],
        "step": 0,
    }

    result = await node(state)

    assert result["step"] == 2
    results = {c["result"] for c in result["tool_calls"]}
    assert results == {"3", "7"}
    assert result["pending_tool_calls"] == []


# ---------------------------------------------------------------------------
# Milestone 10 AC3 -- Permission Validation (interim)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_permission_validator_allows_unrestricted_tool() -> None:
    from jarvis.agents.nodes.permission_validator import make_permission_validator_node
    from jarvis.agents.permission import AgentPermissionGate

    gate = AgentPermissionGate(confirm_required_tools=frozenset({"run_automation"}))
    node = make_permission_validator_node(gate)

    result = await node(
        {
            "next_action": "tool",
            "tool_name": "recall_memory",
            "tool_args": {},
            "tool_calls": [],
            "step": 0,
        }
    )

    assert result["permission_denied"] is False
    assert "tool_calls" not in result


@pytest.mark.asyncio
async def test_permission_validator_denies_gated_tool_without_confirm() -> None:
    from jarvis.agents.nodes.permission_validator import make_permission_validator_node
    from jarvis.agents.permission import AgentPermissionGate

    gate = AgentPermissionGate(confirm_required_tools=frozenset({"run_automation"}))
    node = make_permission_validator_node(gate)

    result = await node(
        {
            "next_action": "tool",
            "tool_name": "run_automation",
            "tool_args": {"instruction": "shutdown"},
            "tool_calls": [],
            "step": 0,
        }
    )

    assert result["permission_denied"] is True
    assert result["tool_calls"][0]["error"].startswith("Denied:")
    assert result["step"] == 1


@pytest.mark.asyncio
async def test_permission_validator_parallel_filters_denied_calls() -> None:
    from jarvis.agents.nodes.permission_validator import make_permission_validator_node
    from jarvis.agents.permission import AgentPermissionGate

    gate = AgentPermissionGate(confirm_required_tools=frozenset({"run_automation"}))
    node = make_permission_validator_node(gate)

    result = await node(
        {
            "next_action": "tool_parallel",
            "pending_tool_calls": [
                {"tool": "recall_memory", "args": {}},
                {"tool": "run_automation", "args": {"instruction": "shutdown"}},
            ],
            "tool_calls": [],
            "step": 0,
        }
    )

    assert result["pending_tool_calls"] == [{"tool": "recall_memory", "args": {}}]
    assert len(result["tool_calls"]) == 1
    assert result["tool_calls"][0]["tool"] == "run_automation"
    assert result["step"] == 1
