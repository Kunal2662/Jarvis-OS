"""Environment-override parsing for list-valued settings.

pydantic-settings classifies any ``list[str]`` field as a *complex* value and
runs ``json.loads()`` on the raw environment string **before** any
``mode="before"`` field validator sees it. A comma-separated value is not
valid JSON, so the parse raises and ``Settings()`` fails with
``SettingsError`` -- the field's own CSV-splitting validator never runs at
all. ``Annotated[list[str], NoDecode]`` suppresses that pre-decode and hands
the validator the raw string, which is what makes both shapes work.

Why this matters for wake words specifically: the desktop Settings UI writes
the value back as a comma-joined string --
``wake_word_page.py`` does ``self._persist("JARVIS_WAKE_KEYWORDS", ",".join(keys), ...)``
-- straight into ``.env``. Without ``NoDecode`` that write is a delayed
crash: the app keeps running, and the *next* launch dies on startup because
it can no longer parse its own persisted setting.
"""

from __future__ import annotations

import pytest

from jarvis.core.config.settings import ApiSettings, WakeWordSettings

KEYWORD_ENV = "JARVIS_WAKE_KEYWORDS"
CORS_ENV = "JARVIS_API_CORS_ORIGINS"


class TestWakeWordKeywordsFromEnv:
    """``WakeWordSettings.keywords`` -- the field the Settings UI persists."""

    def test_comma_separated_value_is_split(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The shape the desktop Settings UI actually writes."""
        monkeypatch.setenv(KEYWORD_ENV, "jarvis,aarya")

        assert WakeWordSettings().keywords == ["jarvis", "aarya"]

    def test_single_keyword_is_accepted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A lone keyword is not valid JSON either -- ``json.loads("jarvis")``
        raises -- so this is the same bug with the smallest possible input, and
        the default (one keyword) makes it the most likely real value."""
        monkeypatch.setenv(KEYWORD_ENV, "jarvis")

        assert WakeWordSettings().keywords == ["jarvis"]

    def test_json_array_value_is_parsed_as_json(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The one shape that worked *before* the fix must keep working, and
        must not be naively comma-split -- doing that to ``["jarvis","aarya"]``
        yields the silent garbage ``['["jarvis"', '"aarya"]']``."""
        monkeypatch.setenv(KEYWORD_ENV, '["jarvis","aarya"]')

        assert WakeWordSettings().keywords == ["jarvis", "aarya"]

    def test_surrounding_whitespace_is_stripped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The UI renders the field with ``", ".join(...)``, so a user editing
        it round-trips values with spaces after each comma."""
        monkeypatch.setenv(KEYWORD_ENV, " jarvis , hey jarvis ")

        assert WakeWordSettings().keywords == ["jarvis", "hey jarvis"]

    def test_empty_entries_are_discarded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A trailing comma is an easy thing to leave behind in a text field."""
        monkeypatch.setenv(KEYWORD_ENV, "jarvis,,aarya,")

        assert WakeWordSettings().keywords == ["jarvis", "aarya"]

    def test_unset_env_keeps_the_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(KEYWORD_ENV, raising=False)

        assert WakeWordSettings().keywords == ["jarvis"]


class TestSettingsUiRoundTrip:
    """The exact persist -> reload cycle the desktop Settings UI performs.

    ``wake_word_page.py`` joins the user's keywords with ``","`` and writes
    that to ``JARVIS_WAKE_KEYWORDS``. Reading it back has to return the same
    list, or changing wake-word settings bricks the following launch.
    """

    @pytest.mark.parametrize(
        "keywords",
        [
            ["jarvis"],
            ["jarvis", "aarya"],
            ["jarvis", "hey jarvis", "aarya"],
        ],
    )
    def test_ui_persisted_value_reloads_identically(
        self, monkeypatch: pytest.MonkeyPatch, keywords: list[str]
    ) -> None:
        # Exactly what wake_word_page.py::_on_keywords writes.
        persisted = ",".join(keywords)
        monkeypatch.setenv(KEYWORD_ENV, persisted)

        assert WakeWordSettings().keywords == keywords

    def test_ui_display_join_also_round_trips(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The UI *displays* with ``", "`` (comma-space); a user who retypes
        what they see must not end up with leading spaces baked into keywords."""
        keywords = ["jarvis", "hey jarvis"]
        monkeypatch.setenv(KEYWORD_ENV, ", ".join(keywords))

        assert WakeWordSettings().keywords == keywords


class TestCorsOriginsFromEnv:
    """``ApiSettings.cors_origins`` has the identical shape, and an operator
    overriding it is the documented escape hatch for a deployment whose
    frontend origin differs -- so it is pinned here alongside wake words
    rather than left to the CORS suite alone."""

    def test_comma_separated_value_is_split(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(CORS_ENV, "http://tauri.localhost,http://localhost:3000")

        assert ApiSettings().cors_origins == [
            "http://tauri.localhost",
            "http://localhost:3000",
        ]

    def test_json_array_value_is_parsed_as_json(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(CORS_ENV, '["http://tauri.localhost","tauri://localhost"]')

        assert ApiSettings().cors_origins == [
            "http://tauri.localhost",
            "tauri://localhost",
        ]

    def test_single_origin_is_accepted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(CORS_ENV, "http://tauri.localhost")

        assert ApiSettings().cors_origins == ["http://tauri.localhost"]
