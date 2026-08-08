"""Vendor Integration Failover -- Milestone 11 Task Group E.

A second-order response to something
:class:`~jarvis.core.integrations.gateway.ApiGateway` already tried and
gave up on -- never a replacement for the gateway's own retry policy.
Triggered only by a persisting ``GatewayError.retryable`` (timeout,
network failure, vendor 5xx, 429) on
:meth:`~jarvis.services.integration_service.IntegrationService.
invoke_with_failover`; an authorization/credential/configuration
failure is never a failover condition.

**Exactly one candidate, always caller-named.** There is no catalogue
scan and no "find me an alternate" search here -- Task Group E must not
implement discovery, so the caller supplies the one candidate
integration id it considers eligible, and this module only validates
and uses it. That single-candidate ceiling is also what makes an
``A -> B -> A -> B`` failover loop structurally impossible: there is no
retry-of-a-retry path for this to recurse through.

See ``docs/M11_API_CENTER_LOGIC_CONTRACT.md`` §15 for the full policy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class FailoverAttempt:
    """One failover attempt's outcome. Never carries a credential value
    or a raw vendor response."""

    capability: str
    failed_integration_id: str
    candidate_integration_id: str | None
    outcome: str  # "recovered" | "no_candidate" | "failed"
    attempt: int = 1
    error_code: str = ""
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def as_dict(self) -> dict[str, Any]:
        return {
            "capability": self.capability,
            "failed_integration_id": self.failed_integration_id,
            "candidate_integration_id": self.candidate_integration_id,
            "outcome": self.outcome,
            "attempt": self.attempt,
            "error_code": self.error_code,
            "occurred_at": self.occurred_at.isoformat(),
        }
