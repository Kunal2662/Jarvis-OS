"""A minimal, real MCP peer that speaks newline-delimited JSON-RPC over
stdin/stdout -- the counterpart ``StdioTransport`` connects to in
Milestone 10.5 Task Group B's tests.

Run as a subprocess: ``python tests/fixtures/mcp_stdio_peer.py``.

Deliberately a real process rather than a mock: the stdio transport's
whole job is process lifecycle plus stream framing, and neither is
actually exercised by a stubbed object. Stays dependency-free (stdlib
only) so it starts fast and cannot fail for reasons unrelated to the
transport under test.

``--fail-handshake`` makes ``initialize`` return no agreed version, so a
test can drive the negotiation-failure path against a real peer.
``--exit-after N`` makes the peer exit after N requests, so a test can
drive the peer-died path.
"""

from __future__ import annotations

import json
import sys

PROTOCOL_VERSION = "2025-06-18"

CAPABILITIES = [
    {
        "name": "echo",
        "version": "1.0.0",
        "kind": "tool",
        "description": "Echoes its input back.",
        "permissions": ["agent_tools"],
        "metadata": {},
    },
    {
        "name": "read_secret",
        "version": "1.0.0",
        "kind": "tool",
        "description": "Requires a permission the test does not grant.",
        "permissions": ["filesystem"],
        "metadata": {},
    },
]


def _handle(method: str, params: dict, *, fail_handshake: bool) -> dict:
    if method == "initialize":
        if fail_handshake:
            return {
                "server_id": "stdio-peer",
                "agreed_version": "",
                "failure_reason": "No shared protocol version (forced by test).",
            }
        offered = params.get("protocol_versions") or []
        agreed = PROTOCOL_VERSION if PROTOCOL_VERSION in offered else ""
        return {
            "server_id": "stdio-peer",
            "agreed_version": agreed,
            "protocol_versions": [PROTOCOL_VERSION],
            "failure_reason": "" if agreed else "No shared protocol version.",
        }
    if method == "capabilities/list":
        return {"capabilities": CAPABILITIES}
    if method == "capabilities/call":
        name = params.get("name")
        if name == "echo":
            return {"result": {"echoed": params.get("arguments", {}).get("text", "")}}
        raise ValueError(f"Unknown capability {name!r}")
    if method == "ping":
        return {"pong": True, "server_id": "stdio-peer"}
    raise ValueError(f"Unknown method {method!r}")


def main() -> None:
    fail_handshake = "--fail-handshake" in sys.argv
    exit_after = 0
    if "--exit-after" in sys.argv:
        exit_after = int(sys.argv[sys.argv.index("--exit-after") + 1])

    handled = 0
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except ValueError:
            continue

        request_id = message.get("id")
        try:
            result = _handle(
                message.get("method", ""),
                message.get("params") or {},
                fail_handshake=fail_handshake,
            )
            response = {"jsonrpc": "2.0", "id": request_id, "result": result}
        except Exception as err:  # report as a JSON-RPC error, never crash
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32601, "message": str(err)},
            }

        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()

        handled += 1
        if exit_after and handled >= exit_after:
            return


if __name__ == "__main__":
    main()
