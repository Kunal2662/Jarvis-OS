# Development Guide

## 1. Prerequisites

* **Python 3.13** (use `pyenv-win` on Windows, `pyenv`/`uv` elsewhere).
* **Git**.
* Optional: [Ollama](https://ollama.com) for local LLMs.

## 2. First-time setup

```bash
git clone <repo> jarvis-os
cd jarvis-os

python -m venv .venv
source .venv/bin/activate         # macOS/Linux
.\.venv\Scripts\activate          # Windows

pip install --upgrade pip
pip install -e ".[dev]"

python scripts/bootstrap.py       # creates .env, data/ dirs, installs Playwright
pre-commit install
```

## 3. Day-to-day commands

| Command                              | Purpose                                    |
|--------------------------------------|--------------------------------------------|
| `python -m jarvis`                   | Launch the desktop app (GUI mode).         |
| `python -m jarvis --headless`        | Run without UI.                            |
| `python -m jarvis --api-only`        | Only the FastAPI control-plane.            |
| `jarvis-api`                         | Same as `--api-only` (console entry).      |
| `pytest -m unit`                     | Fast test loop.                            |
| `pytest -m integration`              | Slower tests that touch disk / network.    |
| `pytest -m "not windows"`            | Skip Windows-only tests on Linux/macOS.    |
| `ruff check src tests --fix`         | Lint + auto-fix.                           |
| `black src tests`                    | Format.                                    |
| `mypy src`                           | Type-check (strict).                       |

## 4. Database migrations (Alembic — Milestone 3.1)

Schema changes for the SQLite database (`conversations`, `messages`,
`memories`, `tags`, `memory_tags`) now go through Alembic instead of
hand-editing `Base.metadata.create_all` expectations. The URL is resolved
at runtime from JARVIS settings (`JARVIS_DB_URL` / `.env`), not from
`alembic.ini`, so there is one source of truth.

| Command                                   | Purpose                                             |
|--------------------------------------------|------------------------------------------------------|
| `alembic upgrade head`                     | Bring a **fresh** database up to the latest schema.   |
| `alembic downgrade -1`                     | Roll back the most recent migration.                  |
| `alembic revision -m "add X"`              | Scaffold a new migration.                             |
| `alembic stamp head`                       | Mark an **existing M3-era** database (created via the old `create_all` path) as already at the latest revision, without re-running DDL — the schema already matches `0001_initial_schema`. |

`SQLiteDatabase.initialize()` still calls `create_all` as an idempotent
dev/test convenience (safe — `create_all` never touches tables that
already exist), but any *new* schema change from here on should ship as
an Alembic revision, not a `models.py` edit alone.

## 5. Coding standards

* **Style**: `black` (line 100), `ruff` with the ruleset in `pyproject.toml`.
* **Types**: mandatory. `mypy --strict` runs on every PR.
* **Docstrings**: NumPy style. Every public function/class must have one.
* **Imports**: absolute (`from jarvis.core.config import Settings`), never
  relative except within the same subpackage.
* **Naming**:
  * Interfaces: `IThingProvider`
  * Services: `ThingService`
  * Adapters: `<Provider>ThingAdapter` or `<Provider>ThingProvider`
* **Constructor injection everywhere** — no service reaches into the DI
  container itself.

## 6. Adding a feature

1. Create a folder under `src/jarvis/features/<feature_name>/`.
2. Add a Qt controller/view-model that receives services via `__init__`.
3. Register any new service on `core/di/container.py`.
4. Add unit tests under `tests/unit/features/<feature_name>/`.
5. Update `docs/ROADMAP.md`.

## 7. Adding a new provider

See §5 of [`ARCHITECTURE.md`](ARCHITECTURE.md).

## 8. Git workflow

* Trunk-based development.
* Feature branches: `feat/<milestone>-<short-name>`.
* Bug fixes: `fix/<short-name>`.
* All PRs require: green `pytest`, `mypy`, `ruff`, `black --check`.

## 9. Logging tips

* Never call `print()`.
* Use `get_logger(__name__)`.
* Structured fields via `.bind(request_id=..., user=...)`.
* Sensitive data (API keys, prompts marked `sensitive=True`) is scrubbed by
  the JSON sink.

## 10. Milestone 5 UI guides

* [`WORKSPACE_GUIDE.md`](WORKSPACE_GUIDE.md) — building/extending a
  full desktop workspace (Voice, Files & Drive, Browser, Coding,
  Finance, Smart Home, Calendar, Gmail, Spotify).
* [`PLUGIN_GUIDE.md`](PLUGIN_GUIDE.md) — the plugin architecture
  prepared this milestone (no real loader yet).
* [`FUTURE_INTEGRATION_GUIDE.md`](FUTURE_INTEGRATION_GUIDE.md) — how to
  swap a mock service provider (Gmail/Spotify/Weather/Finance/Smart
  Home/Plugins) for a real one without touching UI code.
* [`THEMING.md`](THEMING.md) — includes the completed Theme Engine
  (accent colors, design tokens, future custom themes).
* [`PACKAGING.md`](PACKAGING.md) — Windows build/distribution status
  (honest: foundational, not release-ready).
* [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md) — real, verified issues
  and their fixes/workarounds.
