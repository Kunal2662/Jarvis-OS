"""Small, framework-free LLM helpers -- a safe single-turn completion call
and best-effort JSON extraction from free-form model output.

Lives in ``jarvis.utils`` (not ``jarvis.agents``) because both matter to
code outside the agent graph: originally written for the LangGraph node
prompts (``agents/nodes/*.py``, which still import both names from
``agents/prompting.py`` for backward compatibility -- see that module),
and reused as-is by ``services/knowledge_service.py`` for its own
JSON-decision extraction prompts. Neither function has any LangGraph or
``AgentState`` coupling -- both only depend on
:class:`~jarvis.core.interfaces.llm_provider.ILLMProvider`, a
``core.interfaces`` port -- so this module can sit below both ``services``
and ``agents`` in the dependency graph without either importing the other.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

from jarvis.core.exceptions import LLMProviderError
from jarvis.core.logging.logger import get_logger
from jarvis.core.types import ChatMessage

if TYPE_CHECKING:
    from jarvis.core.interfaces.llm_provider import ILLMProvider

_logger = get_logger("jarvis.utils.llm_json")

_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


async def safe_complete(llm: ILLMProvider, prompt: str, *, fallback: str) -> str:
    """Call ``llm.complete`` for a single-turn prompt; never raises.

    Every caller must degrade gracefully rather than crash on a transient
    provider error -- matching ``MemoryService.summarize``'s "fall back to
    truncation" precedent.
    """
    try:
        result = await llm.complete([ChatMessage(role="user", content=prompt)])
        return (result or "").strip() or fallback
    except LLMProviderError as err:
        _logger.warning("LLM call failed, using fallback: {}", err)
        return fallback


def parse_json_object(text: str) -> dict[str, Any]:
    """Best-effort extraction of a JSON object from LLM output.

    Tolerates markdown code fences and leading/trailing prose by taking
    the first ``{...}`` span. Returns ``{}`` (never raises) on anything
    that still doesn't parse, so callers always get a dict to read
    ``.get(...)`` off of.
    """
    text = (text or "").strip()
    match = _JSON_BLOCK.search(text)
    candidate = match.group(0) if match else text
    try:
        parsed = json.loads(candidate)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        _logger.warning("Non-JSON LLM output: {!r}", text[:200])
        return {}
