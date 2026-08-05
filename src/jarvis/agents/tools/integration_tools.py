"""Agent tools wrapping
:class:`~jarvis.services.integration_service.IntegrationService`
(Milestone 11 Task Group E).

Four tools rather than one per vendor operation. The catalogue holds 65
operations today and will hold hundreds; putting each on the tool
registry would flood the tool-selection prompt with near-identical
entries and make the agent worse at choosing among them. Instead the
agent *discovers* what is connected and what it can do, then invokes by
name -- which is how a human uses an API reference too.

**No tool authorizes anything.** Starting an OAuth flow means opening a
consent screen in a browser and a person deciding; an agent cannot do
that on the user's behalf and should not appear to. Authorization is the
REST surface's job, and these tools report an unauthorized integration
as something the *user* needs to connect.

**Mutating operations are still gated, exactly as elsewhere.** These
tools call the same :meth:`IntegrationService.invoke` the REST route
does, so both permission gates apply. The agent gets no privileged
path.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from langchain_core.tools import BaseTool, tool

from jarvis.core.logging.logger import get_logger

if TYPE_CHECKING:
    from jarvis.services.integration_service import IntegrationService

_logger = get_logger("jarvis.agents.tools.integration")

#: How much of a vendor response to hand back. A Gmail thread or a Drive
#: listing can be tens of kilobytes of JSON, and pasting all of it into
#: the agent's context crowds out everything else it needs.
_MAX_RESULT_CHARS = 4_000


def build_integration_tools(integrations: IntegrationService) -> list[BaseTool]:
    @tool
    async def list_integrations() -> str:
        """List connected external integrations (Gmail, Calendar, Drive,
        ...) and whether each is authorized. Call this first -- the other
        integration tools need an integration id, and an integration that
        is not connected cannot be used."""
        try:
            rows = await integrations.list_installed()
        except Exception as err:
            _logger.warning("list_integrations tool failed: {}", err)
            return f"Couldn't list integrations: {err}"
        if not rows:
            return (
                "No integrations are installed. The user can connect one from the "
                "integrations settings; you cannot authorize one yourself."
            )
        lines = []
        for row in rows:
            authed = bool(row.get("auth", {}).get("authenticated"))
            lines.append(
                f"- [{row['provider_id']}] {row['metadata']['name']}: "
                f"{row['state']}, {'authorized' if authed else 'NOT authorized'}"
            )
        return "\n".join(lines)

    @tool
    async def describe_integration(integration_id: str) -> str:
        """List the operations one integration offers, with the
        parameters each takes. Call this before invoke_integration so you
        use a real operation name and real parameter names."""
        try:
            spec = integrations.describe(integration_id)
        except Exception as err:
            _logger.warning("describe_integration tool failed: {}", err)
            return f"Couldn't describe that integration: {err}"
        lines = [f"{spec['name']} ({spec['integration_id']}) -- {spec['description']}"]
        if spec.get("availability_note"):
            lines.append(f"NOTE: {spec['availability_note']}")
        for operation in spec["operations"]:
            params = sorted({*operation["path_params"], *operation["query"], *operation["body"]})
            required = operation["required"]
            lines.append(
                f"- {operation['name']} ({operation['method']}): {operation['description']}"
            )
            lines.append(f"    params: {params or 'none'}; required: {required or 'none'}")
        return "\n".join(lines)

    @tool
    async def search_integration(integration_id: str, query: str, top_k: int = 5) -> str:
        """Search inside one connected integration using the vendor's own
        search (Gmail messages, Drive files, contacts). Prefer this over
        listing everything and filtering."""
        try:
            rows = await integrations.search(integration_id, query, top_k=top_k)
        except Exception as err:
            _logger.warning("search_integration tool failed: {}", err)
            return f"Couldn't search that integration: {err}"
        if not rows:
            return f"Nothing in {integration_id} matches {query!r}."
        return _clip(json.dumps(rows[:top_k], indent=2, default=str))

    @tool
    async def invoke_integration(
        integration_id: str, operation: str, params: dict[str, Any] | None = None
    ) -> str:
        """Call one operation on a connected integration. Use
        describe_integration first to get the operation and parameter
        names. Operations that send, create, update or delete take real
        effect -- confirm with the user before calling one."""
        try:
            result = await integrations.invoke(integration_id, operation, params or {})
        except Exception as err:
            _logger.warning("invoke_integration tool failed: {}", err)
            return f"Couldn't call {integration_id}.{operation}: {err}"
        return _clip(json.dumps(result.get("data"), indent=2, default=str))

    return [list_integrations, describe_integration, search_integration, invoke_integration]


def _clip(text: str) -> str:
    if len(text) <= _MAX_RESULT_CHARS:
        return text
    return (
        text[:_MAX_RESULT_CHARS]
        + f"\n... (truncated at {_MAX_RESULT_CHARS} characters; narrow the query "
        "or ask for fewer results)"
    )
