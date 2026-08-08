"""Connection Testing -- Milestone 11 Task Group B.

The explicit, user-triggered "can this configured integration actually
reach and authenticate to its vendor right now" check. Deliberately
distinct from Task Group C's ``health()`` (local-only, periodic): this
is the one place in the M11 Integration Platform allowed to make a
real, bounded, read-only vendor request. See
``docs/M11_API_CENTER_LOGIC_CONTRACT.md`` §11 for the full boundary and
§21 for the error taxonomy ``error_code`` draws from.

:class:`ConnectionTestResult` never carries a request/response body, a
header, or a credential value -- only a classification, a status code,
a latency, and a human-readable message drawn from a small, reviewed
set of safe strings (never an interpolated vendor payload or exception
string).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

#: The caller-facing bound Connection Testing enforces at the network
#: boundary (``GatewayRequest.timeout_seconds``, honoured by ``httpx``
#: itself) -- deliberately shorter than ``ApiGateway``'s own general
#: ``DEFAULT_TIMEOUT_SECONDS`` (30s), because this is a synchronous,
#: user-facing diagnostic, not a background call.
DEFAULT_CONNECTION_TEST_TIMEOUT_SECONDS = 10.0

#: A caller may ask for a shorter timeout but never a longer one --
#: this is the one place a request body could otherwise be used to make
#: JARVIS hold a vendor connection open indefinitely.
MAX_CONNECTION_TEST_TIMEOUT_SECONDS = 10.0


@dataclass(frozen=True, slots=True)
class ConnectionTestResult:
    """One Connection Test's outcome. Never serializes a secret,
    header, or raw vendor response body -- see :meth:`as_dict`."""

    integration_id: str
    outcome: str  # "success" | "failure"
    error_code: str = ""  # empty when outcome == "success"
    status_code: int | None = None
    latency_ms: float | None = None
    message: str = ""
    tested_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def as_dict(self) -> dict[str, Any]:
        return {
            "integration_id": self.integration_id,
            "outcome": self.outcome,
            "error_code": self.error_code,
            "status_code": self.status_code,
            "latency_ms": round(self.latency_ms, 2) if self.latency_ms is not None else None,
            "message": self.message,
            "tested_at": self.tested_at.isoformat(),
        }
