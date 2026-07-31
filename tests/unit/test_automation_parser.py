"""Unit tests for :class:`IntentParser` against every example command in the
Milestone 4 brief, plus a few edge cases."""

from __future__ import annotations

import pytest

from jarvis.domain.automation.models import ActionType
from jarvis.features.automation.parser import IntentParser


@pytest.fixture()
def parser() -> IntentParser:
    return IntentParser()


@pytest.mark.parametrize(
    ("text", "expected_action", "expected_target"),
    [
        ("Open Chrome", ActionType.OPEN_APP, "Chrome"),
        ("Launch VS Code", ActionType.OPEN_APP, "VS Code"),
        ("Open Spotify", ActionType.OPEN_APP, "Spotify"),
        ("Close all Chrome tabs", ActionType.CLOSE_APP, "Chrome"),
        ("Search Google for Tesla", ActionType.SEARCH_GOOGLE, "Tesla"),
        ("Create folder named Work", ActionType.CREATE_FOLDER, "Work"),
        ("Take screenshot", ActionType.SCREENSHOT, None),
        ("Mute volume", ActionType.MUTE, None),
        ("Increase brightness", ActionType.SET_BRIGHTNESS, None),
        ("Shutdown after 30 minutes", ActionType.SHUTDOWN, None),
        ("Empty the recycle bin", ActionType.EMPTY_RECYCLE_BIN, None),
        ("Lock the pc", ActionType.LOCK_PC, None),
        ("Open downloads", ActionType.OPEN_DOWNLOADS, None),
    ],
)
def test_parses_example_commands(
    parser: IntentParser, text: str, expected_action: ActionType, expected_target: str | None
) -> None:
    intent = parser.parse(text)
    assert intent.action is expected_action
    assert intent.target == expected_target
    assert intent.confidence > 0.9


def test_move_extracts_source_and_destination(parser: IntentParser) -> None:
    intent = parser.parse("Move report.pdf to Desktop")
    assert intent.action is ActionType.MOVE
    assert intent.arguments["source"] == "report.pdf"
    assert intent.arguments["destination"] == "Desktop"


def test_shutdown_after_minutes_converts_to_seconds(parser: IntentParser) -> None:
    intent = parser.parse("Shutdown after 30 minutes")
    assert intent.arguments["delay_seconds"] == 30 * 60


def test_unknown_instruction_has_low_confidence(parser: IntentParser) -> None:
    intent = parser.parse("play me a song about the ocean")
    assert intent.action is ActionType.UNKNOWN
    assert intent.confidence == 0.0


def test_empty_string_is_unknown(parser: IntentParser) -> None:
    intent = parser.parse("   ")
    assert intent.action is ActionType.UNKNOWN
