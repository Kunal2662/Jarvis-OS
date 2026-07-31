"""Named colour palette shared between QSS themes and Python code."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Palette:
    bg: str
    surface: str
    surface_alt: str
    text: str
    text_muted: str
    border: str
    accent: str
    accent_hover: str
    danger: str
    success: str
    warning: str


DARK_PALETTE = Palette(
    bg="#0B0F14",
    surface="#111820",
    surface_alt="#1A2330",
    text="#E6EEF7",
    text_muted="#8A97A8",
    border="#22303C",
    accent="#00E5FF",
    accent_hover="#00B8CC",
    danger="#FF5A6E",
    success="#4CE0B3",
    warning="#FFC857",
)

LIGHT_PALETTE = Palette(
    bg="#F7F9FC",
    surface="#FFFFFF",
    surface_alt="#EEF2F7",
    text="#0B1B2B",
    text_muted="#5B6B7E",
    border="#D6DCE5",
    accent="#0077B6",
    accent_hover="#005F8E",
    danger="#D62839",
    success="#0E9F6E",
    warning="#B76E00",
)

JARVIS_PALETTE = Palette(
    bg="#050914",
    surface="#0A1122",
    surface_alt="#0F1A33",
    text="#DFF6FF",
    text_muted="#6D8BAA",
    border="#12253F",
    accent="#00E5FF",
    accent_hover="#39FFF6",
    danger="#FF3860",
    success="#00E39A",
    warning="#FFD166",
)
