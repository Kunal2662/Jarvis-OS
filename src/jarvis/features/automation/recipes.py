"""Recipes -- named, reusable sequences of automation instructions.

Stored as one JSON file per recipe under ``<data_dir>/recipes``. A recipe
is just a list of the same natural-language lines the planner already
understands, so running one is `"\\n".join(recipe.steps)` fed straight
back through :class:`~jarvis.features.automation.planner.TaskPlanner` --
no separate execution path to maintain.
"""

from __future__ import annotations

import json
from pathlib import Path

from jarvis.core.exceptions import RecipeError
from jarvis.core.logging.logger import get_logger
from jarvis.domain.automation.models import Recipe

_logger = get_logger("jarvis.features.automation.recipes")


class RecipeManager:
    def __init__(self, recipes_dir: Path) -> None:
        self._dir = recipes_dir
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path_for(self, name: str) -> Path:
        safe_name = "".join(c for c in name if c.isalnum() or c in ("-", "_")).strip()
        if not safe_name:
            raise RecipeError(f"Invalid recipe name: {name!r}")
        return self._dir / f"{safe_name}.json"

    def list_recipes(self) -> list[Recipe]:
        recipes: list[Recipe] = []
        for path in sorted(self._dir.glob("*.json")):
            try:
                recipes.append(self._load_file(path))
            except (json.JSONDecodeError, KeyError) as err:
                _logger.warning("Skipping malformed recipe {}: {}", path, err)
        return recipes

    def get(self, name: str) -> Recipe:
        path = self._path_for(name)
        if not path.exists():
            raise RecipeError(f"No recipe named {name!r}.")
        return self._load_file(path)

    def save(self, recipe: Recipe) -> Path:
        path = self._path_for(recipe.name)
        payload = {
            "name": recipe.name,
            "description": recipe.description,
            "steps": recipe.steps,
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path

    def delete(self, name: str) -> bool:
        path = self._path_for(name)
        if path.exists():
            path.unlink()
            return True
        return False

    def to_instruction_text(self, recipe: Recipe) -> str:
        return "\n".join(recipe.steps)

    def _load_file(self, path: Path) -> Recipe:
        data = json.loads(path.read_text(encoding="utf-8"))
        return Recipe(
            name=data["name"],
            steps=list(data["steps"]),
            description=data.get("description", ""),
        )
