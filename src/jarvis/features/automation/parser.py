"""Natural-language intent parser.

Rule-based on purpose: this runs on every voice/chat turn before we know
whether the user even wants automation, so it must be instant and have
zero external dependencies (no LLM round-trip). Patterns are tried in
order; the first match wins. Anything unmatched becomes
``ActionType.UNKNOWN`` with low confidence so callers (typically
:class:`~jarvis.services.chat_service.ChatService`) can fall back to a
normal conversational reply instead of attempting automation.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from jarvis.domain.automation.models import ActionType, Intent

_Builder = Callable[[re.Match[str]], tuple[str | None, dict[str, Any]]]


@dataclass(frozen=True, slots=True)
class _Rule:
    pattern: re.Pattern[str]
    action: ActionType
    build: _Builder


def _rule(pattern: str, action: ActionType, build: _Builder) -> _Rule:
    return _Rule(re.compile(pattern, re.IGNORECASE), action, build)


def _num(text: str, default: int = 0) -> int:
    match = re.search(r"-?\d+", text)
    return int(match.group()) if match else default


_RULES: list[_Rule] = [
    # --- Specific "open X" rules must come before the generic OPEN_APP
    # catch-all below, or "open downloads" would match as OPEN_APP(target=
    # "downloads"). ---------------------------------------------------
    _rule(
        r"^open\s+(?:file\s+)?explorer(?:\s+(?:at|in)\s+(.+))?$",
        ActionType.OPEN_EXPLORER,
        lambda m: (m.group(1).strip() if m.group(1) else None, {}),
    ),
    _rule(r"^open\s+downloads?$", ActionType.OPEN_DOWNLOADS, lambda m: (None, {})),
    _rule(r"^open\s+documents?$", ActionType.OPEN_DOCUMENTS, lambda m: (None, {})),
    _rule(r"^open\s+settings$", ActionType.OPEN_SETTINGS, lambda m: (None, {})),
    _rule(
        r"^empty\s+(?:the\s+)?recycle\s+bin$",
        ActionType.EMPTY_RECYCLE_BIN,
        lambda m: (None, {}),
    ),
    # --- Apps ------------------------------------------------------------
    _rule(
        r"^(?:open|launch|start)\s+(.+)$",
        ActionType.OPEN_APP,
        lambda m: (m.group(1).strip(), {}),
    ),
    _rule(
        r"^close\s+all\s+(.+?)\s+tabs?$",
        ActionType.CLOSE_APP,
        lambda m: (m.group(1).strip(), {"scope": "tabs"}),
    ),
    _rule(
        r"^(?:close|quit|kill)\s+(.+)$",
        ActionType.CLOSE_APP,
        lambda m: (m.group(1).strip(), {}),
    ),
    # --- Search ------------------------------------------------------------
    _rule(
        r"^search\s+google\s+for\s+(.+)$",
        ActionType.SEARCH_GOOGLE,
        lambda m: (m.group(1).strip(), {}),
    ),
    _rule(
        r"^google\s+(.+)$",
        ActionType.SEARCH_GOOGLE,
        lambda m: (m.group(1).strip(), {}),
    ),
    _rule(
        r"^search\s+youtube\s+for\s+(.+)$",
        ActionType.SEARCH_YOUTUBE,
        lambda m: (m.group(1).strip(), {}),
    ),
    # --- Filesystem --------------------------------------------------------
    _rule(
        r"^create\s+(?:a\s+)?folder\s+(?:named\s+|called\s+)?(.+)$",
        ActionType.CREATE_FOLDER,
        lambda m: (m.group(1).strip(), {}),
    ),
    _rule(
        r"^delete\s+(?:the\s+)?folder\s+(.+)$",
        ActionType.DELETE_FOLDER,
        lambda m: (m.group(1).strip(), {}),
    ),
    _rule(
        r"^rename\s+(.+?)\s+to\s+(.+)$",
        ActionType.RENAME,
        lambda m: (
            m.group(1).strip(),
            {"source": m.group(1).strip(), "destination": m.group(2).strip()},
        ),
    ),
    _rule(
        r"^move\s+(.+?)\s+(?:in)?to\s+(.+)$",
        ActionType.MOVE,
        lambda m: (
            m.group(1).strip(),
            {"source": m.group(1).strip(), "destination": m.group(2).strip()},
        ),
    ),
    _rule(
        r"^copy\s+(.+?)\s+to\s+(.+)$",
        ActionType.COPY,
        lambda m: (
            m.group(1).strip(),
            {"source": m.group(1).strip(), "destination": m.group(2).strip()},
        ),
    ),
    # --- System / hardware ---------------------------------------------
    _rule(r"^(?:take\s+(?:a\s+)?)?screenshot$", ActionType.SCREENSHOT, lambda m: (None, {})),
    _rule(
        r"^copy\s+(.+)\s+to\s+clipboard$",
        ActionType.CLIPBOARD_COPY,
        lambda m: (m.group(1).strip(), {"text": m.group(1).strip()}),
    ),
    _rule(r"^paste$", ActionType.CLIPBOARD_PASTE, lambda m: (None, {})),
    _rule(
        r"^set\s+volume\s+to\s+(\d+)%?$",
        ActionType.SET_VOLUME,
        lambda m: (m.group(1), {"level": int(m.group(1))}),
    ),
    _rule(r"^mute(?:\s+volume)?$", ActionType.MUTE, lambda m: (None, {"muted": True})),
    _rule(r"^unmute(?:\s+volume)?$", ActionType.MUTE, lambda m: (None, {"muted": False})),
    _rule(
        r"^increase\s+volume(?:\s+by\s+(\d+)%?)?$",
        ActionType.SET_VOLUME,
        lambda m: (None, {"delta": _num(m.group(0), 10)}),
    ),
    _rule(
        r"^decrease\s+volume(?:\s+by\s+(\d+)%?)?$",
        ActionType.SET_VOLUME,
        lambda m: (None, {"delta": -_num(m.group(0), 10)}),
    ),
    _rule(
        r"^set\s+brightness\s+to\s+(\d+)%?$",
        ActionType.SET_BRIGHTNESS,
        lambda m: (m.group(1), {"level": int(m.group(1))}),
    ),
    _rule(
        r"^increase\s+brightness(?:\s+by\s+(\d+)%?)?$",
        ActionType.SET_BRIGHTNESS,
        lambda m: (None, {"delta": _num(m.group(0), 10)}),
    ),
    _rule(
        r"^decrease\s+brightness(?:\s+by\s+(\d+)%?)?$",
        ActionType.SET_BRIGHTNESS,
        lambda m: (None, {"delta": -_num(m.group(0), 10)}),
    ),
    _rule(
        r"^shut\s*down(?:\s+(?:the\s+)?(?:computer|pc))?(?:\s+after\s+(\d+)\s+minutes?)?$",
        ActionType.SHUTDOWN,
        lambda m: (None, {"delay_seconds": _num(m.group(1) or "0") * 60}),
    ),
    _rule(
        r"^restart(?:\s+(?:the\s+)?(?:computer|pc))?(?:\s+after\s+(\d+)\s+minutes?)?$",
        ActionType.RESTART,
        lambda m: (None, {"delay_seconds": _num(m.group(1) or "0") * 60}),
    ),
    _rule(r"^(?:go\s+to\s+)?sleep$", ActionType.SLEEP, lambda m: (None, {})),
    _rule(
        r"^lock(?:\s+(?:the\s+)?(?:computer|pc|screen))?$", ActionType.LOCK_PC, lambda m: (None, {})
    ),
    _rule(
        r"^(?:run|execute)\s+(?:command|terminal command)\s+(.+)$",
        ActionType.TERMINAL_COMMAND,
        lambda m: (m.group(1).strip(), {"command": m.group(1).strip()}),
    ),
]


class IntentParser:
    """Extracts a single :class:`Intent` from one line of natural language."""

    def parse(self, text: str) -> Intent:
        cleaned = text.strip().rstrip(".!")
        if not cleaned:
            return Intent(action=ActionType.UNKNOWN, raw_text=text, confidence=0.0)

        for rule in _RULES:
            match = rule.pattern.match(cleaned)
            if match:
                target, extra_args = rule.build(match)
                return Intent(
                    action=rule.action,
                    target=target,
                    arguments=extra_args,
                    raw_text=text,
                    confidence=0.95,
                )

        return Intent(action=ActionType.UNKNOWN, raw_text=text, confidence=0.0)

    def parse_many(self, lines: list[str]) -> list[Intent]:
        return [self.parse(line) for line in lines if line.strip()]
