"""``jarvis mcp`` developer CLI -- Milestone 10.5 Task Group E,
deliverable 2.

A thin delivery shim over :class:`~jarvis.core.mcp.diagnostics.
MCPDiagnostics`, exactly as ``infrastructure/api/routes/mcp.py`` is a
thin shim over the same runtime. It owns argument parsing and output
formatting, and no logic of its own -- the same rule
``docs/ARCHITECTURE.md`` §1 states for FastAPI routers, applied to the
second delivery mechanism.

**Read-only, like the REST surface.** Every subcommand inspects;
none connects, authenticates, installs or mutates. That keeps the tool
safe to run against a live install, and means it can never be the thing
that broke a provider.

**No vendor-specific commands**, per this task group's scope: the
commands describe the *platform*, and a provider appears in them only
because it was registered.

Lives in ``infrastructure/cli/`` alongside ``infrastructure/api/`` --
both are delivery mechanisms over the same core, and neither is
privileged over the other.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence

    from jarvis.core.mcp.diagnostics import MCPDiagnostics

_COMMANDS = (
    "status",
    "validate",
    "list",
    "inspect",
    "capabilities",
    "transports",
    "providers",
    "auth",
    "connections",
)


def build_mcp_parser() -> argparse.ArgumentParser:
    """The ``jarvis mcp ...`` parser. Built separately from ``main.py``'s
    so it can be tested without launching the app."""
    parser = argparse.ArgumentParser(
        prog="jarvis mcp",
        description="Inspect the MCP & Integration Platform. Read-only.",
    )
    parser.add_argument("command", choices=_COMMANDS, help="What to inspect.")
    parser.add_argument(
        "target",
        nargs="?",
        default="",
        help="Provider or capability id, for 'inspect'.",
    )
    parser.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="Emit JSON instead of a human-readable table.",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to an alternate .env file, matching `jarvis --config`.",
    )
    return parser


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
def _render_table(rows: Sequence[dict[str, Any]], columns: Sequence[str]) -> str:
    """A dependency-free fixed-width table.

    No new dependency for this: the project ships no CLI table library,
    and adding one for a developer tool would be a poor trade against
    twenty lines here.
    """
    if not rows:
        return "(none)"

    header = [c.replace("_", " ") for c in columns]
    widths = [len(h) for h in header]
    cells: list[list[str]] = []
    for row in rows:
        line = [_scalar(row.get(c)) for c in columns]
        widths = [max(w, len(v)) for w, v in zip(widths, line, strict=True)]
        cells.append(line)

    out = ["  ".join(h.ljust(w) for h, w in zip(header, widths, strict=True))]
    out.append("  ".join("-" * w for w in widths))
    out.extend("  ".join(v.ljust(w) for v, w in zip(line, widths, strict=True)) for line in cells)
    return "\n".join(out)


def _scalar(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, list | tuple):
        return ", ".join(str(v) for v in value) or "-"
    return str(value)


def _render_validation(payload: dict[str, Any]) -> str:
    lines = [
        (
            "OK -- no problems found."
            if payload["ok"] and not payload["warning_count"]
            else f"{payload['error_count']} error(s), {payload['warning_count']} warning(s)."
        )
    ]
    for issue in payload["issues"]:
        marker = "ERROR" if issue["severity"] == "error" else "WARN "
        subject = f" ({issue['subject']})" if issue["subject"] else ""
        lines.append(f"  {marker} [{issue['code']}]{subject}: {issue['message']}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------
async def run_command(
    diagnostics: MCPDiagnostics,
    command: str,
    target: str = "",
    *,
    as_json: bool = False,
) -> tuple[str, int]:
    """Executes one subcommand. Returns ``(output, exit_code)`` rather
    than printing, so tests assert on the value instead of capturing
    stdout, and ``main`` owns the one place that writes.

    Four commands need their own shape -- a key/value summary, an issue
    list with its own exit code, several tables at once, and a lookup
    that can miss. Everything else is one table, handled by
    :func:`_run_table_command`.
    """
    if command == "status":
        return await _run_status(diagnostics, as_json=as_json)
    if command == "validate":
        return _run_validate(diagnostics, as_json=as_json)
    if command == "list":
        return await _run_list(diagnostics, as_json=as_json)
    if command == "inspect":
        return await _run_inspect(diagnostics, target)
    return _run_table_command(diagnostics, command, as_json=as_json)


async def _run_status(diagnostics: MCPDiagnostics, *, as_json: bool) -> tuple[str, int]:
    payload = await diagnostics.summary()
    if as_json:
        return json.dumps(payload, indent=2, default=str), 0
    lines = (f"{key.replace('_', ' ')}: {_scalar(value)}" for key, value in payload.items())
    return "\n".join(lines), 0


def _run_validate(diagnostics: MCPDiagnostics, *, as_json: bool) -> tuple[str, int]:
    """The one command whose exit code carries meaning: non-zero on a
    real error so it is usable in a pre-commit hook, zero when only
    warnings were found, because a warning describes something that
    works."""
    payload = diagnostics.validate()
    code = 0 if payload["ok"] else 1
    if as_json:
        return json.dumps(payload, indent=2, default=str), code
    return _render_validation(payload), code


async def _run_list(diagnostics: MCPDiagnostics, *, as_json: bool) -> tuple[str, int]:
    if as_json:
        return json.dumps(await diagnostics.report(), indent=2, default=str), 0

    sections = (
        ("Capabilities", list(diagnostics.capabilities()), ["name", "kind", "permissions"]),
        ("Transports", list(diagnostics.transports()), ["id", "registered", "summary"]),
        ("Providers", list(diagnostics.providers()), ["provider_id", "state", "transport"]),
        ("Connections", list(diagnostics.connections()), ["server_id", "state", "transport"]),
    )
    rendered = (f"{title}\n{_render_table(rows, cols)}" for title, rows, cols in sections)
    return "\n\n".join(rendered), 0


async def _run_inspect(diagnostics: MCPDiagnostics, target: str) -> tuple[str, int]:
    """Exit 2 for misuse, 1 for 'ran fine, found nothing' -- the shell
    convention, so a script can tell a typo from an absent provider.

    Always JSON, with or without ``--json``: an inspection is a nested
    document joining four subsystems, and flattening it into a table
    would lose exactly the nesting that makes it useful.
    """
    if not target:
        return "inspect requires a provider or capability id.", 2
    found = await diagnostics.inspect_provider(target) or diagnostics.inspect_capability(target)
    if found is None:
        return f"No provider or capability named {target!r}.", 1
    return json.dumps(found, indent=2, default=str), 0


def _run_table_command(
    diagnostics: MCPDiagnostics, command: str, *, as_json: bool
) -> tuple[str, int]:
    """Every command that is one list of rows and a column selection."""
    tables: dict[str, tuple[list[dict[str, Any]], list[str]]] = {
        "capabilities": (
            list(diagnostics.capabilities()),
            ["name", "version", "kind", "permissions"],
        ),
        "transports": (
            list(diagnostics.transports()),
            ["id", "registered", "stateful", "local_only", "summary"],
        ),
        "providers": (
            list(diagnostics.providers()),
            ["provider_id", "state", "enabled", "transport"],
        ),
        "connections": (
            list(diagnostics.connections()),
            ["server_id", "state", "transport", "agreed_version"],
        ),
        "auth": (
            [_auth_row(entry) for entry in diagnostics.auth()],
            ["provider_id", "authenticated", "status", "session_state", "expires_at"],
        ),
    }
    rows, columns = tables[command]
    if as_json:
        return json.dumps(rows, indent=2, default=str), 0
    return _render_table(rows, columns), 0


def _auth_row(entry: dict[str, Any]) -> dict[str, Any]:
    """Flattens one authentication status for tabular display. Reads
    only from the public payload, which carries no token."""
    credential = entry.get("credential") or {}
    return {
        "provider_id": entry["provider_id"],
        "authenticated": entry["authenticated"],
        "status": credential.get("status", "missing"),
        "session_state": entry["session"]["state"],
        "expires_at": credential.get("expires_at"),
    }


def run_mcp_cli(argv: Sequence[str], *, container: Any = None) -> int:
    """Entry point for ``jarvis mcp ...``.

    Resolves ``mcp_diagnostics`` from the DI container rather than
    assembling its own -- the same singleton ``/api/v1/mcp/diagnostics``
    resolves, so the CLI can never report a different truth than the API
    does.
    """
    args = build_mcp_parser().parse_args(list(argv))

    if container is None:
        from jarvis.core.config.settings import load_settings
        from jarvis.core.di.container import Container

        container = Container()
        container.settings.override(load_settings(env_file=args.config))

    output, code = asyncio.run(
        run_command(container.mcp_diagnostics(), args.command, args.target, as_json=args.as_json)
    )
    # The one place this module writes: every other function returns
    # its output so a caller (or a test) can use the value.
    print(output)
    return code
