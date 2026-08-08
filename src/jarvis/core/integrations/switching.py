"""Runtime Switching -- Milestone 11 Task Group E.

The explicit, user-triggered "use this catalogue-backed integration
instead of that one" operation. Concretely: activate the target (an
already-installed, capability-compatible, credentialed integration),
then deactivate the source -- in that order, so a target that fails to
activate never causes the source to be falsely reported inactive.
Reuses :meth:`~jarvis.services.integration_service.IntegrationService.
connect`/``disconnect`` (Task Group D) verbatim; no second activation
mechanism.

There is no existing "active integration per capability" registry
anywhere in this codebase for a switch to update -- every caller
already names an ``integration_id`` directly. ``capability`` here is
therefore an audit label (which operation this switch was about), not
a routing key backed by new state; eligibility is checked against the
same :class:`~jarvis.core.integrations.models.IntegrationSpec` model
every other M11 capability check already uses (``has_operation``), not
a duplicated taxonomy. See ``docs/M11_API_CENTER_LOGIC_CONTRACT.md``
§14 for the full boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class SwitchResult:
    """One Runtime Switch's outcome. Never carries a credential value."""

    capability: str
    from_integration_id: str
    to_integration_id: str
    outcome: str  # "success" | "failure"
    error_code: str = ""  # empty when outcome == "success"
    requested_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def as_dict(self) -> dict[str, Any]:
        return {
            "capability": self.capability,
            "from_integration_id": self.from_integration_id,
            "to_integration_id": self.to_integration_id,
            "outcome": self.outcome,
            "error_code": self.error_code,
            "requested_at": self.requested_at.isoformat(),
        }
