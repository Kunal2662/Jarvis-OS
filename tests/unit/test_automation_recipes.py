"""Unit tests for :class:`RecipeManager`."""

from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.core.exceptions import RecipeError
from jarvis.domain.automation.models import Recipe
from jarvis.features.automation.recipes import RecipeManager


@pytest.fixture()
def manager(tmp_path: Path) -> RecipeManager:
    return RecipeManager(tmp_path / "recipes")


def test_save_and_get_roundtrip(manager: RecipeManager) -> None:
    recipe = Recipe(name="morning_routine", steps=["Open Chrome", "Open Slack"], description="AM")
    manager.save(recipe)

    loaded = manager.get("morning_routine")
    assert loaded.steps == ["Open Chrome", "Open Slack"]
    assert loaded.description == "AM"


def test_list_recipes_finds_saved_files(manager: RecipeManager) -> None:
    manager.save(Recipe(name="a", steps=["Open Chrome"]))
    manager.save(Recipe(name="b", steps=["Open Spotify"]))
    names = {r.name for r in manager.list_recipes()}
    assert names == {"a", "b"}


def test_get_missing_recipe_raises(manager: RecipeManager) -> None:
    with pytest.raises(RecipeError):
        manager.get("does_not_exist")


def test_delete_recipe(manager: RecipeManager) -> None:
    manager.save(Recipe(name="temp", steps=["Open Chrome"]))
    assert manager.delete("temp") is True
    assert manager.delete("temp") is False


def test_to_instruction_text_joins_steps_with_newlines(manager: RecipeManager) -> None:
    recipe = Recipe(name="x", steps=["Open Chrome", "Open Slack"])
    assert manager.to_instruction_text(recipe) == "Open Chrome\nOpen Slack"
