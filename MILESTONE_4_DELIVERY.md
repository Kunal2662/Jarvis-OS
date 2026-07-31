# Milestone 4 — AI Automation Engine: Delivery Summary

## 1. Files Created

**Domain (framework-free value objects)**
- `src/jarvis/domain/__init__.py`
- `src/jarvis/domain/automation/__init__.py`
- `src/jarvis/domain/automation/models.py` — `ActionType`, `RiskLevel`, `PermissionDecision`, `StepStatus`, `Intent`, `Step`, `ExecutionPlan`, `StepResult`, `PlanResult`, `ValidationIssue`, `UndoRecord`, `TaskRecord`, `Recipe`

**Feature layer** (`src/jarvis/features/automation/`)
- `parser.py` — `IntentParser` (rule-based NLP → `Intent`)
- `planner.py` — `TaskPlanner` (`Intent`(s) → `ExecutionPlan`)
- `validator.py` — `SafetyValidator` (safety layer)
- `permission.py` — `PermissionGate` + `ConfirmationCallback`
- `executor.py` — `ActionExecutor` (retries, rollback, history, events)
- `undo.py` — `UndoManager`
- `history.py` — `HistoryService`
- `recipes.py` — `RecipeManager`

**Infrastructure — automation actions** (`src/jarvis/infrastructure/automation/`)
- `platform_ops.py` — `WindowsOps` / `MacOps` / `LinuxOps` / `NoopOps` strategy classes
- `actions/__init__.py`, `actions/base.py` — `BaseAction`, `ActionContext`
- `actions/app_actions.py` — Open/Close App, Launch URL
- `actions/file_actions.py` — Create/Delete Folder, Rename, Move, Copy, Explorer, Downloads, Documents, Empty Recycle Bin
- `actions/system_actions.py` — Screenshot, Clipboard Copy/Paste, Volume, Mute, Brightness, Shutdown, Restart, Sleep, Lock, Settings, Terminal Command
- `actions/search_actions.py` — Search Google, Search YouTube
- `actions/registry.py` — `ActionType → BaseAction` registry

**Database**
- `src/jarvis/infrastructure/database/repositories/task_history_repository.py`

**Tests**
- `tests/fakes/fake_os_automation.py`
- `tests/unit/test_automation_parser.py`
- `tests/unit/test_automation_validator.py`
- `tests/unit/test_automation_permission.py`
- `tests/unit/test_automation_planner.py`
- `tests/unit/test_automation_executor.py`
- `tests/unit/test_automation_undo.py`
- `tests/unit/test_automation_recipes.py`
- `tests/unit/test_task_history_repository.py`
- `tests/unit/test_automation_service.py`

**Data / resources**
- `data/recipes/` (runtime, user-writable — created at startup)
- `resources/recipes/morning_routine.json` (bundled example, seeded into `data/recipes` on first run)

## 2. Files Modified (additive only — nothing removed or renamed)

| File | Change |
|---|---|
| `core/exceptions.py` | Appended `AutomationError` hierarchy (8 new exception classes) |
| `core/events/events.py` | Appended `AutomationStepEvent` |
| `core/config/constants.py` | Appended `RECIPES_SUBDIR`, `TRASH_SUBDIR` |
| `core/config/paths.py` | Appended `recipes_dir()`, `automation_trash_dir()`; registered both in `ensure_runtime_dirs()` |
| `core/config/settings.py` | Appended `AutomationSettings` block, registered on `Settings` |
| `core/interfaces/browser.py` | Appended 4 new protocol methods (`fill`, `extract_links`, `download`, `close_all_tabs`) |
| `core/di/container.py` | Wired `automation_service` with `browser_service`, `database`, `event_bus`; reordered `browser_service` before `automation_service` |
| `infrastructure/database/models.py` | Appended `TaskHistory` ORM model |
| `infrastructure/database/repositories/__init__.py` | Exported `TaskHistoryRepository` |
| `infrastructure/automation/windows_adapter.py` | Implemented (was `NotImplementedError` stub) |
| `infrastructure/browser/playwright_adapter.py` | Implemented (was `NotImplementedError` stub) |
| `services/automation_service.py` | Rewritten as the Milestone-4 orchestration facade |
| `services/browser_service.py` | Implemented (was `NotImplementedError` stub) |

No existing class, method signature, or file was deleted or renamed. `core/interfaces/automation.py` (the `IOSAutomation` port) was **not** touched.

## 3. Architecture Diagram

```
                       ┌─────────────────────────────┐
 voice / chat / UI --> │      AutomationService       │   (services/automation_service.py)
                       │  run_command / undo_last /   │
                       │  list_history / run_recipe    │
                       └──────────────┬───────────────┘
                                      │
        ┌─────────────┬──────────────┼───────────────┬──────────────┐
        ▼             ▼              ▼               ▼              ▼
  IntentParser   TaskPlanner   SafetyValidator  PermissionGate  ActionExecutor
  (parser.py)    (planner.py)  (validator.py)   (permission.py)  (executor.py)
                                                                     │
                                              ┌──────────────────────┼───────────────────┐
                                              ▼                      ▼                   ▼
                                        UndoManager           HistoryService       ActionRegistry
                                        (undo.py)              (history.py)      (actions/registry.py)
                                                                     │                   │
                                                              TaskHistoryRepository   BaseAction subclasses
                                                              (SQLite / SQLAlchemy)   (app/file/system/search)
                                                                                          │
                                                                          ┌───────────────┼────────────────┐
                                                                          ▼               ▼                ▼
                                                                    IOSAutomation   BrowserService     platform_ops
                                                                    (existing port) (Playwright)   (Windows/Mac/Linux)
```

Ports-and-adapters is preserved throughout: actions depend only on `ActionContext` (which carries `IOSAutomation`, `BrowserService`, `Settings`, `EventBus` — all existing ports), never on a concrete adapter. `RecipeManager` sits beside `AutomationService` and simply feeds recorded instruction text back through the same `run_command` path.

## 4. Flow Diagram — one instruction, end to end

```
"Create folder Work then move report.pdf to Work"
        │
        ▼
TaskPlanner.build_plan()
   splits on "then" ─▶ IntentParser.parse() per line ─▶ [Step(create_folder), Step(move, depends_on=[step1])]
        │
        ▼
ActionExecutor.run_plan()
        │
        ├─ Step 1: create_folder
        │     SafetyValidator.validate()  -> []  (no issues)
        │     PermissionGate.authorize()  -> ALLOW
        │     CreateFolderAction.run()    -> creates dir, returns undo_args
        │     UndoManager.push(undo_record)
        │     HistoryService.record()     -> SQLite row (status=succeeded)
        │     EventBus.publish(AutomationStepEvent)
        │
        └─ Step 2: move  (depends_on step 1 -> ran, so proceeds)
              SafetyValidator.validate()  -> []
              PermissionGate.authorize()  -> ALLOW
              MoveAction.run()
                 ├─ success -> undo pushed, history recorded, plan succeeds
                 └─ failure (e.g. file missing) -> retries (backoff) -> still fails
                        -> ActionExecutor rolls back Step 1 via UndoManager
                        -> remaining steps marked SKIPPED
                        -> PlanResult.succeeded == False
```

For a **dangerous** instruction ("delete folder Downloads", "shutdown", any `TERMINAL_COMMAND`):
`SafetyValidator` raises risk to MEDIUM/HIGH/CRITICAL → `PermissionGate.decide()` returns `DENY` (CRITICAL, e.g. `rm -rf /`) or `REQUIRE_CONFIRMATION` → the supplied `ConfirmationCallback` is awaited → declined/absent confirmation raises `AutomationPermissionDeniedError` and the step is recorded as `denied`, never executed.

## 5. Remaining TODOs

- **Download action**: `BrowserService.download_file()` exists and is exposed, but there's no `ActionType.DOWNLOAD` / parser rule yet to trigger it from a plain instruction like "download this image" — the milestone's own worked example ("Download image") currently parses as `UNKNOWN`. Needs a URL/link-target extraction step.
- **Windows volume/brightness**: no first-party Windows CLI exists for these; the adapter shells out to `nircmd` (volume/mute) if present on PATH and raises a clear `ActionExecutionError` otherwise. Consider bundling `nircmd` or switching to a `pycaw`/WMI-only implementation.
- **`windows/ linux/ mac/` folder split**: implemented as three `PlatformOps` strategy classes in one file (`platform_ops.py`) rather than three physical packages, since each backend is currently a handful of 1–3 line subprocess calls. Splitting into real packages is a mechanical follow-up once any one OS backend grows real per-platform logic.
- **Registry / Admin actions**: the brief's permission list mentions "registry" and "admin" explicitly; today both route through `TERMINAL_COMMAND` (already confirmation-gated) rather than having dedicated `ActionType`s. Add `REGISTRY_EDIT` / an `elevated=True` flag on `TERMINAL_COMMAND` if first-class support is wanted.
- **UI**: Automation Panel / Running Tasks / History / Undo / Permissions / Progress / Task Queue widgets are not built — `AutomationService` exposes everything a Qt ViewModel would need (`run_command`, `undo_last`, `list_history`, `list_recipes`), following the same MVVM pattern as `VoiceController`, but the actual PySide6 views are unbuilt.
- **Voice wiring**: `VoiceController`/`ChatService` don't yet call `AutomationService.run_command()` automatically on a transcribed command — routing "is this automation or conversation" (using `Intent.confidence`) into the existing voice/chat pipeline is unbuilt.
- **True OS recycle bin / undo of `EMPTY_RECYCLE_BIN` and post-delay `SHUTDOWN`**: emptying the OS trash is not reversible by this engine (by design — it's the OS's own trash, not ours); a scheduled shutdown can be cancelled up until it fires, but not after.
- **Confirmation channel wiring**: `ConfirmationCallback` is a plain async protocol; nothing yet bridges it to an actual Qt dialog / voice prompt — callers must supply one (defaults to auto-deny for safety).
- **Retention job**: `HistoryService.purge_expired()` exists but nothing schedules it against `AutomationSettings.history_retention_days` yet (needs a periodic task, e.g. on app boot or a QTimer).
- **Parallel execution**: the planner marks steps with empty `depends_on` when "at the same time" is detected, but `ActionExecutor.run_plan()` still executes steps sequentially — true concurrent execution (`asyncio.gather` over independent steps) is not implemented.

## 6. Manual Testing Checklist

Run from the repo root with `pip install -e .` (or `pip install -r requirements.txt`) done first.

- [ ] `pytest tests/unit -k automation` — all new unit tests pass (parser, validator, permission, planner, executor, undo, recipes, history repo, service e2e)
- [ ] `pytest tests/unit` (full suite) — no regressions in existing Milestones 1–3 tests
- [ ] Launch the app; say/type **"Open Chrome"** → Chrome opens, no confirmation prompt, history shows one `succeeded` row
- [ ] **"Close all Chrome tabs"** → all Chrome tabs close (requires `browser.enabled=true` and Playwright installed: `playwright install`)
- [ ] **"Create folder named TestFolder"** → folder appears in your home directory
- [ ] **"Delete folder TestFolder"** → a confirmation prompt appears; declining leaves the folder intact and records a `denied` history row; confirming deletes it and the action becomes undoable
- [ ] **"Undo"** (or call `AutomationService.undo_last()`) right after the delete above → `TestFolder` reappears
- [ ] **"Move report.pdf to Desktop"** with a real `report.pdf` in your home dir → file relocates; undo puts it back
- [ ] **"Search Google for Tesla"** → default browser/Playwright context navigates to a Google search results page
- [ ] **"Take screenshot"** → a PNG appears under `<data_dir>/cache/screenshots/`
- [ ] **"Mute volume"** / **"Increase brightness"** → OS volume mutes / brightness changes (Linux needs `pactl`/`amixer` and `brightnessctl`; macOS needs the `brightness` CLI for brightness; Windows needs `nircmd` for volume)
- [ ] **"Shutdown after 30 minutes"** → confirmation prompt appears; confirming schedules a real OS shutdown (⚠️ test on a VM, or decline the prompt) and the plan is marked undoable (cancel) until it fires
- [ ] **"Run command echo hello"** → confirmation prompt (all terminal commands require it) → succeeds and returns stdout
- [ ] **"Run command rm -rf /"** → denied outright, no confirmation offered, `SafetyValidator` blocks it (CRITICAL)
- [ ] Save and run a recipe: `AutomationService.save_recipe(...)` then `run_recipe("morning_routine")` → each step executes in order
- [ ] Kill power/network mid-plan (or force a step to fail) on a multi-step instruction → verify prior successful steps roll back and later steps show `skipped`

## 7. Example Commands

```
Open Chrome
Launch VS Code
Open Spotify
Close all Chrome tabs
Search Google for Tesla
Search YouTube for lofi beats
Create folder named Work
Delete folder Work
Rename notes.txt to notes-old.txt
Move report.pdf to Desktop
Copy photo.png to Documents
Open explorer
Open downloads
Open documents
Empty the recycle bin
Take screenshot
Mute volume
Unmute volume
Increase volume by 20%
Set brightness to 50%
Shutdown after 30 minutes
Restart after 5 minutes
Lock the pc
Open settings
Run command echo hello
Create folder named Work then move report.pdf to Work then take screenshot
```
