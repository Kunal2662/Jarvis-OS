"""Safety layer -- flags dangerous instructions before they ever execute.

Runs *before* :mod:`~jarvis.features.automation.permission` on every
:class:`Intent`. The validator only classifies risk and gives reasons; it
never decides pass/fail on its own -- that decision (allow / confirm /
deny) is :class:`~jarvis.features.automation.permission.PermissionGate`'s
job, using the issues this module raises as its input.
"""

from __future__ import annotations

import re

from jarvis.domain.automation.models import ActionType, Intent, RiskLevel, ValidationIssue

# Command substrings that are near-certainly destructive if executed
# verbatim in a shell. This is a defence-in-depth deny-list, not the only
# safety mechanism -- PermissionGate still requires explicit confirmation
# for every TERMINAL_COMMAND regardless of this list.
_DANGEROUS_SHELL_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"rm\s+-rf\s+/(\s|$)"),
    re.compile(r"rm\s+-rf\s+~"),
    re.compile(r"rm\s+-rf\s+\*"),
    re.compile(r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:"),  # fork bomb
    re.compile(r"\bmkfs(\.\w+)?\b"),
    re.compile(r"\bdd\s+if="),
    re.compile(r"format\s+[a-zA-Z]:"),
    re.compile(r"del\s+/f\s+/s\s+/q\s+[a-zA-Z]:\\?$"),
    re.compile(r">\s*/dev/sd[a-z]"),
    re.compile(r"\bshutdown\b.*\bnow\b.*&&.*\bshutdown\b"),  # repeated-shutdown pattern
]

_SYSTEM_PATH_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^[cC]:\\+(windows|program\s*files)\\?$", re.IGNORECASE),
    re.compile(r"^/+(etc|usr|bin|sbin|boot|system|lib|var)/?$"),
    re.compile(r"^/+$"),
    re.compile(r"^[a-zA-Z]:\\+$"),
]

_MASS_DELETE_TARGET = re.compile(r"[*]")

# Milestone 5.5 security fix: LaunchUrlAction is hardcoded RiskLevel.SAFE
# and had zero URL-scheme validation anywhere in the pipeline --
# file://, javascript:, and data: URIs could read arbitrary local files
# or execute script content via the browser automation pipeline.
#
# Deliberately a *denylist* of specific dangerous schemes, not an
# allowlist of "only http/https": Python's urlsplit() has a real parsing
# quirk where a bare "host:port" with no "//" (e.g. "localhost:8080",
# a completely ordinary local-dev URL) gets misparsed with scheme=
# "localhost" -- an allowlist would wrongly flag and auto-deny that
# legitimate case. None of these specific dangerous scheme names
# collide with any realistic hostname.
_DANGEROUS_URL_SCHEMES = {
    "file",
    "javascript",
    "vbscript",
    "data",
    "about",
    "chrome",
    "chrome-extension",
    "resource",
    "jar",
}


class SafetyValidator:
    """Classifies an :class:`Intent` into zero or more :class:`ValidationIssue`."""

    def validate(self, intent: Intent) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []

        if intent.action is ActionType.TERMINAL_COMMAND:
            command = str(intent.arguments.get("command") or intent.target or "")
            issues.extend(self._check_shell_command(command))

        if intent.action is ActionType.LAUNCH_URL:
            target = str(
                intent.target or intent.arguments.get("target") or intent.arguments.get("url") or ""
            )
            issues.extend(self._check_url_scheme(target))

        if intent.action in (ActionType.DELETE_FOLDER, ActionType.EMPTY_RECYCLE_BIN):
            target = str(intent.target or "")
            if self._is_system_path(target):
                issues.append(
                    ValidationIssue(
                        RiskLevel.CRITICAL,
                        f"{target!r} looks like a protected system folder.",
                    )
                )
            elif _MASS_DELETE_TARGET.search(target):
                issues.append(
                    ValidationIssue(
                        RiskLevel.HIGH,
                        "Wildcard delete target detected -- looks like a mass-delete.",
                    )
                )

        if intent.action in (ActionType.SHUTDOWN, ActionType.RESTART):
            issues.append(
                ValidationIssue(RiskLevel.MEDIUM, "Power-state changes require confirmation.")
            )

        if intent.action is ActionType.UNKNOWN:
            issues.append(ValidationIssue(RiskLevel.LOW, "Instruction could not be understood."))

        return issues

    def _check_url_scheme(self, url: str) -> list[ValidationIssue]:
        from urllib.parse import urlsplit

        stripped = url.strip()
        if not stripped:
            return []
        # urlsplit correctly extracts a scheme from any of:
        #   "https://example.com" -> "https"
        #   "javascript:alert(1)" -> "javascript"  (single colon, no "//")
        #   "data:text/html,..."  -> "data"
        #   "google.com"          -> ""  (no scheme at all)
        # A bare domain (empty scheme) is exactly what LaunchUrlAction
        # itself auto-prefixes with https:// at execution time, so it's
        # never flagged here -- only an *explicit*, non-http(s) scheme is.
        scheme = urlsplit(stripped).scheme.lower()
        if scheme in _DANGEROUS_URL_SCHEMES:
            return [
                ValidationIssue(
                    RiskLevel.CRITICAL,
                    f"URL scheme {scheme!r} is not allowed for browser navigation "
                    f"-- could read local files or execute script content.",
                )
            ]
        return []

    def _check_shell_command(self, command: str) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        lowered = command.lower()
        for pattern in _DANGEROUS_SHELL_PATTERNS:
            if pattern.search(lowered):
                issues.append(
                    ValidationIssue(
                        RiskLevel.CRITICAL,
                        f"Command matches a known-destructive pattern: {pattern.pattern!r}.",
                    )
                )
        # crude infinite-loop heuristic: "while true"/"for(;;)" with no break/sleep
        if re.search(r"while\s*\(?\s*true\s*\)?\s*;?\s*do", lowered) and "sleep" not in lowered:
            issues.append(
                ValidationIssue(RiskLevel.HIGH, "Unbounded loop with no sleep/backoff detected.")
            )
        if not issues and any(tok in lowered for tok in ("sudo", "chmod 777", "chown -r")):
            issues.append(
                ValidationIssue(RiskLevel.MEDIUM, "Command requests elevated/broad permissions.")
            )
        return issues

    def _is_system_path(self, target: str) -> bool:
        stripped = target.strip()
        return any(p.match(stripped) for p in _SYSTEM_PATH_PATTERNS)

    @staticmethod
    def highest_risk(issues: list[ValidationIssue]) -> RiskLevel:
        if not issues:
            return RiskLevel.SAFE
        order = [
            RiskLevel.SAFE,
            RiskLevel.LOW,
            RiskLevel.MEDIUM,
            RiskLevel.HIGH,
            RiskLevel.CRITICAL,
        ]
        return max(issues, key=lambda i: order.index(i.risk)).risk
