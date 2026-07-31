"""Unit tests for :class:`SafetyValidator`."""

from __future__ import annotations

import pytest

from jarvis.domain.automation.models import ActionType, Intent, RiskLevel
from jarvis.features.automation.validator import SafetyValidator


def test_rm_rf_root_is_critical() -> None:
    validator = SafetyValidator()
    intent = Intent(
        action=ActionType.TERMINAL_COMMAND,
        arguments={"command": "rm -rf /"},
        raw_text="run command rm -rf /",
    )
    issues = validator.validate(intent)
    assert any(i.risk is RiskLevel.CRITICAL for i in issues)


def test_fork_bomb_is_critical() -> None:
    validator = SafetyValidator()
    intent = Intent(
        action=ActionType.TERMINAL_COMMAND,
        arguments={"command": ":(){ :|:& };:"},
        raw_text="run command :(){ :|:& };:",
    )
    issues = validator.validate(intent)
    assert any(i.risk is RiskLevel.CRITICAL for i in issues)


def test_benign_command_has_no_critical_issues() -> None:
    validator = SafetyValidator()
    intent = Intent(
        action=ActionType.TERMINAL_COMMAND,
        arguments={"command": "echo hello"},
        raw_text="run command echo hello",
    )
    issues = validator.validate(intent)
    assert not any(i.risk is RiskLevel.CRITICAL for i in issues)


def test_deleting_system_path_is_critical() -> None:
    validator = SafetyValidator()
    intent = Intent(action=ActionType.DELETE_FOLDER, target="/etc", raw_text="delete folder /etc")
    issues = validator.validate(intent)
    assert any(i.risk is RiskLevel.CRITICAL for i in issues)


def test_wildcard_delete_is_high_risk() -> None:
    validator = SafetyValidator()
    intent = Intent(
        action=ActionType.DELETE_FOLDER, target="Downloads/*", raw_text="delete folder Downloads/*"
    )
    issues = validator.validate(intent)
    assert any(i.risk is RiskLevel.HIGH for i in issues)


def test_deleting_ordinary_folder_has_no_critical_issue() -> None:
    validator = SafetyValidator()
    intent = Intent(action=ActionType.DELETE_FOLDER, target="Work", raw_text="delete folder Work")
    issues = validator.validate(intent)
    assert not any(i.risk is RiskLevel.CRITICAL for i in issues)


def test_highest_risk_picks_the_max() -> None:
    from jarvis.domain.automation.models import ValidationIssue

    issues = [
        ValidationIssue(RiskLevel.LOW, "a"),
        ValidationIssue(RiskLevel.CRITICAL, "b"),
        ValidationIssue(RiskLevel.MEDIUM, "c"),
    ]
    assert SafetyValidator.highest_risk(issues) is RiskLevel.CRITICAL


def test_highest_risk_of_no_issues_is_safe() -> None:
    assert SafetyValidator.highest_risk([]) is RiskLevel.SAFE


# --- Milestone 5.5 security fix: LAUNCH_URL scheme validation -------------
# Previously LaunchUrlAction was hardcoded RiskLevel.SAFE with zero URL
# scheme checking anywhere in the pipeline. file://, javascript:, and
# data: URIs could read arbitrary local files or execute script content
# via the browser automation pipeline.


def test_https_url_has_no_issues() -> None:
    validator = SafetyValidator()
    intent = Intent(action=ActionType.LAUNCH_URL, target="https://example.com")
    issues = validator.validate(intent)
    assert issues == []


def test_bare_domain_is_treated_as_https_and_has_no_issues() -> None:
    """LaunchUrlAction itself auto-prefixes a bare domain with https:// at
    execution time -- the validator must mirror that, not flag every
    ordinary "open google.com" instruction."""
    validator = SafetyValidator()
    intent = Intent(action=ActionType.LAUNCH_URL, target="google.com")
    issues = validator.validate(intent)
    assert issues == []


def test_localhost_with_port_is_not_flagged() -> None:
    """Regression guard: Python's urlsplit() misparses a bare
    "host:port" with no "//" as having scheme="host" (e.g.
    "localhost:8080" -> scheme="localhost"). An earlier version of this
    fix used an *allowlist* of http/https, which would have wrongly
    flagged and auto-denied this completely ordinary local-dev URL.
    The denylist approach must not have this false positive."""
    for target in ("localhost:8080", "localhost:3000", "127.0.0.1:8000", "my-dev-server:9000"):
        issues = SafetyValidator().validate(Intent(action=ActionType.LAUNCH_URL, target=target))
        assert issues == [], f"{target!r} was wrongly flagged: {issues}"


def test_file_scheme_url_is_critical() -> None:
    validator = SafetyValidator()
    intent = Intent(action=ActionType.LAUNCH_URL, target="file:///etc/passwd")
    issues = validator.validate(intent)
    assert any(i.risk is RiskLevel.CRITICAL for i in issues)


def test_file_scheme_windows_path_is_critical() -> None:
    validator = SafetyValidator()
    intent = Intent(
        action=ActionType.LAUNCH_URL,
        target=r"file:///C:/Users/victim/AppData/Roaming/secrets.json",
    )
    issues = validator.validate(intent)
    assert any(i.risk is RiskLevel.CRITICAL for i in issues)


def test_javascript_scheme_url_is_critical() -> None:
    validator = SafetyValidator()
    intent = Intent(action=ActionType.LAUNCH_URL, target="javascript:alert(document.cookie)")
    issues = validator.validate(intent)
    assert any(i.risk is RiskLevel.CRITICAL for i in issues)


def test_data_scheme_url_is_critical() -> None:
    validator = SafetyValidator()
    intent = Intent(action=ActionType.LAUNCH_URL, target="data:text/html,<script>alert(1)</script>")
    issues = validator.validate(intent)
    assert any(i.risk is RiskLevel.CRITICAL for i in issues)


def test_url_target_from_arguments_dict_is_also_checked() -> None:
    """Some call sites pass the URL via intent.arguments rather than
    intent.target -- both must be checked."""
    validator = SafetyValidator()
    intent = Intent(action=ActionType.LAUNCH_URL, arguments={"url": "file:///etc/shadow"})
    issues = validator.validate(intent)
    assert any(i.risk is RiskLevel.CRITICAL for i in issues)


def test_blank_url_target_produces_no_issues() -> None:
    """An empty target isn't this validator's concern -- LaunchUrlAction
    itself raises ValueError for a missing target at execution time."""
    validator = SafetyValidator()
    intent = Intent(action=ActionType.LAUNCH_URL, target="")
    issues = validator.validate(intent)
    assert issues == []


@pytest.mark.asyncio
async def test_dangerous_url_scheme_denies_via_permission_gate() -> None:
    """End-to-end: a file:// LAUNCH_URL intent must be auto-denied by
    PermissionGate, not merely flagged."""
    from jarvis.core.exceptions import AutomationPermissionDeniedError
    from jarvis.features.automation.permission import PermissionGate

    validator = SafetyValidator()
    intent = Intent(action=ActionType.LAUNCH_URL, target="file:///etc/passwd")
    issues = validator.validate(intent)

    gate = PermissionGate()
    with pytest.raises(AutomationPermissionDeniedError):
        await gate.authorize(intent, issues)
