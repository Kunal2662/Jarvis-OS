"""Integration catalogue -- Milestone 11 Task Group E.

"What could be installed", as opposed to "what is installed". The
latter is M10.5's ``MCPProviderRegistry`` and stays there; this module
is a lookup over the specs this build ships, so a caller can list
available integrations and install one by id without importing a vendor
module directly.

**Not a second registry.** No class, no state, no lifecycle -- a
mapping of builder functions and three helpers over it. A registry class
here would be a parallel system to the provider registry that owns the
live objects, which is precisely what this task group is forbidden to
build.

**Builders rather than instances.** A spec is cheap but not free
(``gmail_spec()`` allocates twelve operations), and most installs touch
one vendor. Building on demand keeps importing this module cheap, which
matters because the REST layer imports it to answer "what is
available".
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from jarvis.core.integrations.google import GOOGLE_SPECS
from jarvis.core.integrations.models import IntegrationError, IntegrationSpec

if TYPE_CHECKING:
    from collections.abc import Callable

#: Every integration this build can install, by id.
#:
#: Phase 1 (Google Workspace) is populated. Phases 2-6 -- Microsoft 365,
#: GitHub/GitLab, Slack/Discord/Teams, Notion/Jira/Trello/ClickUp/
#: Linear/Asana, Dropbox/Box -- are catalogue entries against the same
#: engine, deliberately not written from memory: an endpoint path or a
#: scope name that is subtly wrong ships an integration that fails at
#: the first real call, and a wrong entry is worse than an absent one
#: because it claims to work.
AVAILABLE_SPECS: dict[str, Callable[[], IntegrationSpec]] = dict(GOOGLE_SPECS)


def available_ids() -> tuple[str, ...]:
    return tuple(sorted(AVAILABLE_SPECS))


def build_spec(integration_id: str) -> IntegrationSpec:
    """The spec for *integration_id*, validated.

    Validation happens here rather than at import so a malformed
    catalogue entry fails when someone tries to install it, naming the
    entry -- not at interpreter start, where it would take the whole
    application down for a typo in a vendor description.
    """
    builder = AVAILABLE_SPECS.get(integration_id)
    if builder is None:
        raise IntegrationError(
            f"Unknown integration {integration_id!r}. Available: {list(available_ids())}."
        )
    spec = builder()
    spec.validate()
    return spec


def build_all() -> tuple[IntegrationSpec, ...]:
    """Every shipped spec, validated. Used by the catalogue endpoint and
    by the test that proves the whole catalogue is well-formed."""
    return tuple(build_spec(integration_id) for integration_id in available_ids())


def describe_catalogue() -> tuple[dict[str, Any], ...]:
    """Summaries for the REST surface -- enough to choose an integration
    without the full operation list for every one of them."""
    summaries: list[dict[str, Any]] = []
    for spec in build_all():
        summaries.append(
            {
                "integration_id": spec.integration_id,
                "name": spec.name,
                "vendor": spec.vendor,
                "description": spec.description,
                "tags": list(spec.tags),
                "operation_count": len(spec.operations),
                "auth_method": spec.auth.method.value,
                "required_permissions": list(spec.required_permissions),
                "availability_note": spec.availability_note,
            }
        )
    return tuple(summaries)


def vendors() -> tuple[str, ...]:
    return tuple(sorted({spec.vendor for spec in build_all()}))
