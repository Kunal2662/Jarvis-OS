"""Automatic Integration Discovery -- Milestone 11 Task Group F.

Enumerates ``core/integrations/catalogue.py`` -- the only trusted
source -- and registers every entry not yet installed, reusing
:meth:`~jarvis.services.integration_service.IntegrationService.install`
(Task Group D) verbatim. No second registration mechanism, no
filesystem scanning, no arbitrary import, no network access: discovery
never leaves the process, and never contacts a vendor.

**Discover + register, never activate.** A newly discovered entry
lands exactly where :meth:`install` already leaves it -- registered,
uncredentialed unless a credential already existed, not connected.
Activation stays Task Group D's own explicit :meth:`connect`.

See ``docs/M11_API_CENTER_LOGIC_CONTRACT.md`` §9 for the discovery
boundary this implements, and this task group's own kickoff message
for the registration-behavior refinement it adds on top (§9's original
text described a passive "discoverable listing"; this task group's
approved instructions are explicit that discovery actively registers
unregistered catalogue entries through the existing mechanism -- see
the Task Group F final report's Diff Summary for the reconciliation).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class DiscoveryResult:
    """One catalogue entry's discovery outcome. Never carries a
    credential, token, or header -- only catalogue-sourced metadata
    that was already public (``core/integrations/catalogue.py``'s own
    ``describe_catalogue()`` surfaces the same fields)."""

    integration_id: str
    vendor: str
    status: str  # "registered" | "already_registered" | "rejected"
    reason: str = ""  # only set when status == "rejected"
    version: str = ""
    capabilities: tuple[str, ...] = ()
    discovered_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def as_dict(self) -> dict[str, Any]:
        return {
            "integration_id": self.integration_id,
            "vendor": self.vendor,
            "status": self.status,
            "reason": self.reason,
            "version": self.version,
            "capabilities": list(self.capabilities),
            "discovered_at": self.discovered_at.isoformat(),
        }
