"""Unit tests for agent tool wrappers and the registry (Milestone 5-Agents).

Uses tiny duck-typed fake services (not the real ``MemoryService`` etc,
which need a live DB/vector store) — each fake only implements the one
or two methods its tool wrapper actually calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from jarvis.core.exceptions import AutomationPermissionDeniedError

pytest.importorskip("langchain_core")


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------
class _FakeMemoryService:
    def __init__(self) -> None:
        self.remembered: list[tuple[str, str]] = []

    async def remember(self, content: str, *, memory_type: str = "long_term") -> str:
        self.remembered.append((content, memory_type))
        return "mem-123"

    async def recall(self, query: str, *, top_k: int = 5):
        @dataclass
        class _Record:
            content: str

        if query == "nothing":
            return []
        return [_Record(content=f"relevant note about {query}")]


@dataclass
class _FakeStepResult:
    status: str = "succeeded"


@dataclass
class _FakePlanResult:
    plan_id: str = "plan-1"
    step_results: list = field(default_factory=lambda: [_FakeStepResult()])

    @property
    def failed_steps(self):
        return [r for r in self.step_results if r.status != "succeeded"]


class _FakeAutomationService:
    def __init__(self, *, deny: bool = False, error: bool = False) -> None:
        self._deny = deny
        self._error = error

    async def run_command(self, instruction: str) -> _FakePlanResult:
        if self._deny:
            raise AutomationPermissionDeniedError("dangerous action denied")
        if self._error:
            from jarvis.core.exceptions import AutomationError

            raise AutomationError("boom")
        return _FakePlanResult()


class _FakeBrowserService:
    def __init__(self) -> None:
        self.opened: list[str] = []

    async def open(self, url: str) -> None:
        self.opened.append(url)

    async def read_text(self, selector: str) -> str:
        return f"text at {selector}"

    async def extract_links(self) -> list[str]:
        return ["https://a.example", "https://b.example"]


class _FakeSystemService:
    async def status(self) -> dict:
        return {
            "available": True,
            "cpu_percent": 12.5,
            "cpu_count": 8,
            "memory_percent": 40.0,
            "memory_used_mb": 4096.0,
            "memory_total_mb": 16384.0,
            "disk_percent": 55.0,
            "disk_free_gb": 100.0,
            "process_count": 200,
            "uptime_seconds": 7200.0,
        }


class _FakeVoiceService:
    def __init__(self) -> None:
        self.spoken: list[str] = []

    async def speak(self, text: str) -> None:
        self.spoken.append(text)


class _FakeChatService:
    async def ask(self, conversation_id: str, question: str) -> str:
        return f"answer for {conversation_id}: {question}"


# ---------------------------------------------------------------------------
# Memory tools
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_remember_tool_stores_content() -> None:
    from jarvis.agents.tools.memory_tools import build_memory_tools

    service = _FakeMemoryService()
    (remember, _recall) = build_memory_tools(service)

    result = await remember.ainvoke({"content": "the sky is blue"})

    assert "mem-123" in result
    assert service.remembered == [("the sky is blue", "long_term")]


@pytest.mark.asyncio
async def test_recall_memory_tool_formats_hits_and_empty() -> None:
    from jarvis.agents.tools.memory_tools import build_memory_tools

    (_remember, recall_memory) = build_memory_tools(_FakeMemoryService())

    hit = await recall_memory.ainvoke({"query": "cats"})
    assert "relevant note about cats" in hit

    miss = await recall_memory.ainvoke({"query": "nothing"})
    assert miss == "No relevant memories found."


# ---------------------------------------------------------------------------
# Automation tools
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_run_automation_tool_success() -> None:
    from jarvis.agents.tools.automation_tools import build_automation_tools

    (run_automation,) = build_automation_tools(_FakeAutomationService())

    result = await run_automation.ainvoke({"instruction": "open notepad"})

    assert "plan-1" in result
    assert "completed successfully" in result


@pytest.mark.asyncio
async def test_run_automation_tool_reports_denial() -> None:
    from jarvis.agents.tools.automation_tools import build_automation_tools

    (run_automation,) = build_automation_tools(_FakeAutomationService(deny=True))

    result = await run_automation.ainvoke({"instruction": "delete everything"})

    assert result.startswith("Denied:")


# ---------------------------------------------------------------------------
# Browser tools
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_browse_url_and_read_text_and_links() -> None:
    from jarvis.agents.tools.browser_tools import build_browser_tools

    service = _FakeBrowserService()
    (browse_url, read_page_text, extract_page_links) = build_browser_tools(service)

    assert "Opened" in await browse_url.ainvoke({"url": "https://example.com"})
    assert service.opened == ["https://example.com"]
    assert "text at body" in await read_page_text.ainvoke({})
    links = await extract_page_links.ainvoke({})
    assert "https://a.example" in links


# ---------------------------------------------------------------------------
# System / voice / chat tools
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_system_status_tool_formats_metrics() -> None:
    from jarvis.agents.tools.system_tools import build_system_tools

    (get_system_status,) = build_system_tools(_FakeSystemService())

    result = await get_system_status.ainvoke({})

    assert "CPU: 12.5%" in result
    assert "Processes: 200" in result


@pytest.mark.asyncio
async def test_speak_text_tool_calls_voice_service() -> None:
    from jarvis.agents.tools.voice_tools import build_voice_tools

    service = _FakeVoiceService()
    (speak_text,) = build_voice_tools(service)

    result = await speak_text.ainvoke({"text": "hello there"})

    assert result == "Spoken."
    assert service.spoken == ["hello there"]


@pytest.mark.asyncio
async def test_ask_conversation_tool_delegates_to_chat_service() -> None:
    from jarvis.agents.tools.chat_tools import build_chat_tools

    (ask_conversation,) = build_chat_tools(_FakeChatService())

    result = await ask_conversation.ainvoke({"conversation_id": "c1", "question": "what's next?"})

    assert result == "answer for c1: what's next?"


# ---------------------------------------------------------------------------
# Registry composition
# ---------------------------------------------------------------------------
def test_registry_includes_only_injected_services() -> None:
    from jarvis.agents.tools.registry import build_tool_registry

    tools = build_tool_registry(memory=_FakeMemoryService(), browser=_FakeBrowserService())
    names = {t.name for t in tools}

    assert names == {
        "remember",
        "recall_memory",
        "browse_url",
        "read_page_text",
        "extract_page_links",
    }


def test_registry_is_empty_with_no_services() -> None:
    from jarvis.agents.tools.registry import build_tool_registry

    assert build_tool_registry() == []


def test_registry_includes_every_service_when_all_injected() -> None:
    from jarvis.agents.tools.registry import build_tool_registry

    tools = build_tool_registry(
        memory=_FakeMemoryService(),
        automation=_FakeAutomationService(),
        browser=_FakeBrowserService(),
        system=_FakeSystemService(),
        voice=_FakeVoiceService(),
        chat=_FakeChatService(),
    )
    names = {t.name for t in tools}

    assert "run_automation" in names
    assert "get_system_status" in names
    assert "speak_text" in names
    assert "ask_conversation" in names
