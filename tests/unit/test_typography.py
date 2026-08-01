"""UI overhaul, Phase 2 -- typography scale tests.

``Typography`` is pure data (no PySide6 import), so this file tests the
scale directly plus enforces that every QSS theme's ``font-size``/
``font-weight`` declaration is drawn from that exact scale -- if the
scale ever changes without updating the QSS (or vice versa), this is
the test that catches the drift.
"""

from __future__ import annotations

import re
from pathlib import Path

from jarvis.core.config import paths
from jarvis.ui.themes.typography import FontWeight, Typography

_FONT_SIZE_RE = re.compile(r"font-size:\s*(\d+)px")
_FONT_WEIGHT_RE = re.compile(r"font-weight:\s*(\d+)")


def test_scale_has_seven_named_styles() -> None:
    scale = Typography.scale()

    assert set(scale) == {
        "app_title",
        "section_title",
        "card_title",
        "widget_title",
        "body",
        "secondary",
        "caption",
    }


def test_scale_sizes_are_strictly_descending() -> None:
    ordered = [
        Typography.APP_TITLE,
        Typography.SECTION_TITLE,
        Typography.CARD_TITLE,
        Typography.WIDGET_TITLE,
        Typography.BODY,
        Typography.SECONDARY,
        Typography.CAPTION,
    ]
    sizes = [style.size_px for style in ordered]

    assert sizes == sorted(sizes, reverse=True)
    assert len(set(sizes)) == len(sizes)  # no two tiers share a size


def test_allowed_sizes_match_the_named_scale() -> None:
    assert Typography.allowed_sizes_px() == {32, 24, 20, 18, 16, 14, 12}


def test_allowed_weights_are_exactly_the_four_specified() -> None:
    assert Typography.allowed_weights() == {400, 500, 600, 700}


def test_font_weight_enum_values_match_allowed_weights() -> None:
    assert {int(w) for w in FontWeight} == Typography.allowed_weights()


def test_font_family_stack_starts_with_inter() -> None:
    assert Typography.FONT_FAMILY_STACK.startswith('"Inter"')
    assert Typography.FONT_FAMILY == "Inter"


def test_bundled_font_file_exists() -> None:
    assert (paths.FONTS_DIR / "Inter.ttf").is_file()


def _qss_files() -> list[Path]:
    return sorted(paths.THEMES_DIR.glob("*.qss"))


def test_every_qss_font_size_is_in_the_typography_scale() -> None:
    allowed = Typography.allowed_sizes_px()
    violations: list[str] = []

    for qss_path in _qss_files():
        text = qss_path.read_text(encoding="utf-8")
        for match in _FONT_SIZE_RE.finditer(text):
            size = int(match.group(1))
            if size not in allowed:
                line = text[: match.start()].count("\n") + 1
                violations.append(f"{qss_path.name}:{line} font-size: {size}px")

    assert not violations, "Non-canonical font sizes found:\n" + "\n".join(violations)


def test_every_qss_font_weight_is_in_the_typography_scale() -> None:
    allowed = Typography.allowed_weights()
    violations: list[str] = []

    for qss_path in _qss_files():
        text = qss_path.read_text(encoding="utf-8")
        for match in _FONT_WEIGHT_RE.finditer(text):
            weight = int(match.group(1))
            if weight not in allowed:
                line = text[: match.start()].count("\n") + 1
                violations.append(f"{qss_path.name}:{line} font-weight: {weight}")

    assert not violations, "Non-canonical font weights found:\n" + "\n".join(violations)


def test_every_qss_declares_inter_first_in_its_font_family() -> None:
    for qss_path in _qss_files():
        text = qss_path.read_text(encoding="utf-8")
        assert 'font-family: "Inter"' in text, f"{qss_path.name} does not lead with Inter"
