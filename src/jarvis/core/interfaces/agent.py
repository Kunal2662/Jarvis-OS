"""Agent-orchestrator port (backed by LangGraph at the infra/agents layer)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class AgentRequest:
    prompt: str
    thread_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AgentResponse:
    text: str
    thread_id: str
    steps: int
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class IAgentOrchestrator(Protocol):
    """Abstract LangGraph orchestrator."""

    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def invoke(self, request: AgentRequest) -> AgentResponse: ...

    # No `async` here on purpose: a concrete implementation using `yield`
    # is an async *generator* function, whose call signature already
    # returns `AsyncIterator[str]` directly rather than a coroutine that
    # resolves to one. Declaring this with `async def ... -> AsyncIterator`
    # (as if it were a plain coroutine method) makes mypy see it as
    # `Coroutine[Any, Any, AsyncIterator[str]]`, which no async-generator
    # implementation can satisfy — a real mismatch mypy only caught once
    # Milestone 5-Agents shipped the first non-stub implementation.
    def stream(self, request: AgentRequest) -> AsyncIterator[str]: ...
