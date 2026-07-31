# JARVIS OS — Milestones 0–5 Final Audit & Completion Pass

**Audit type:** Evidence-based engineering audit. Every finding below was
produced by an actual tool run (`ruff`, `black --check`, a full-package
import sweep, `pytest --cov`, targeted `grep`/AST scans) or a direct code
read, not estimated. Where a check wasn't run, that's stated explicitly
rather than folded into a score.

No roadmap file was touched. No milestone was renamed or created. No UI was
redesigned. No completed feature was removed. Every fix below is additive or
a same-behavior correction, verified against the full test suite after each
change.

---

## 1. Audit Summary

**Overall health: solid, with real (now-fixed) reliability and security
issues found — not a rubber-stamp pass.**

The architecture holds up under actual verification: all 232 modules import
cleanly with zero circular dependencies, the layering rules
(`core`/`services`/`infrastructure`/`features`/`ui`) are respected, and the
codebase is essentially free of TODO/FIXME debt (2 hits, both harmless doc
cross-references). Test suite: **211/211 passing**. Real line coverage:
**62%** (concentrated gaps are almost entirely settings-page UI wiring code,
not business logic — see §10).

The most significant finding was a genuine, systemic reliability bug (55
sites where a background task could be silently killed by garbage
collection) that had been present since early milestones and was actively
producing symptoms visible in this project's own test output. It's fixed
and directly tested now.

---

## 2. Issues Found

### Critical
- **None found.** No `eval`/`exec` on untrusted input, no `shell=True`, no
  `pickle`, no raw SQL string interpolation (SQLAlchemy ORM used
  throughout), no hardcoded secrets in source.

### High
1. **Dangling asyncio tasks (55 sites, 22 files).** `asyncio.ensure_future(coro)`
   with no stored reference is a real bug: CPython's event loop tracks
   running tasks in a *weak* set, so an unreferenced task can be
   garbage-collected mid-execution. This was the direct cause of the "Task
   was destroyed but it is pending!" warnings present in every test run
   this project had produced. **Fixed** — see §3.
2. **Timing-attack anti-pattern in Developer Mode password check.**
   `_verify_password()` compared PBKDF2 digests with `==` instead of a
   constant-time comparison. **Fixed** — see §3.

### Medium
3. **Duplicate `utils` package.** A new `core/utils/` package was
   momentarily introduced while fixing issue #1, before it was noticed that
   an existing, architecturally-documented `jarvis/utils/` package was the
   correct home. **Consolidated** before it could become permanent drift —
   see §3.
4. **4 files of stale, unreferenced scaffolding**, each explicitly
   docstring-labeled "Implementation deferred to Milestone N" for
   milestones that were later completed via different, real
   implementations (`agents/base_agent.py`, `agents/state.py`,
   `infrastructure/database/base_repository.py`,
   `infrastructure/stt/whisper_provider.py`). Verified zero references via
   three independent methods (full-package import sweep, module-path grep,
   class-name grep) before removal. **Removed** — see §5.
5. **~1000 lint findings** against the project's own configured `ruff`
   rules (most codebases this size have some baseline; this one had never
   been swept). Triaged and reduced to 522 via safe autofixes and two
   confirmed-false-positive rule suppressions — see §3 and §9.

### Low
6. **`black --check` would reformat 204/242 files.** The formatter is
   configured in `pyproject.toml` but doesn't appear to have been run
   consistently. **Not executed** in this pass — see §10 for why, and the
   recommendation.
7. **2 unused-but-harmless files** (`utils/file_utils.py`,
   `infrastructure/platform/platform_detector.py`) —
   unlike the 4 removed above, these aren't stale milestone placeholders,
   just orphaned utility code. Flagged, not removed — see §10.
8. ~~`THEMING.md`'s "Adding a theme" steps described wiring a `Palette`
   into the theme system that the real `ThemeService` code path didn't
   actually use.~~ **Resolved this session** — `ThemeService` now derives
   its accent defaults from `palette.py` directly, see §3.

---

## 3. Improvements Made

- Built `fire_and_forget()` in `jarvis/utils/async_utils.py`: keeps a
  strong reference to fire-and-forget tasks in a module-level set,
  discarded via a done-callback on completion, with failures logged
  instead of silently swallowed or crashing. Directly tested, including a
  test that reproduces the exact garbage-collection failure mode
  (`tests/unit/test_async_utils.py::test_fire_and_forget_survives_gc_pressure`).
- Replaced all 55 dangling `asyncio.ensure_future(...)` / `loop.create_task(...)`
  call sites across 22 files with the safe helper. Zero behavior change in
  the happy path — same fire-and-forget semantics, just no longer
  susceptible to premature GC.
- Fixed the `ui/async_utils.py` QTimer-retry wrapper (built during the
  Milestone 5 UI pass) to delegate to the same safe helper — it had the
  identical dangling-task gap.
- Fixed a small dead-variable regression (`loop` binding in
  `event_bus.py`) that my own dangling-task fix introduced, caught by the
  same lint pass that found the original issue.
- Constant-time password-hash comparison via `hmac.compare_digest` in
  `DeveloperModeService._verify_password()`.
- Consolidated the accidental duplicate `core/utils/` package into the
  pre-existing, documented `jarvis/utils/` package.
- Cleaned 41 unused imports, unsorted-import blocks project-wide, 153
  redundant quoted type annotations (safe given `from __future__ import
  annotations` is used everywhere), and cascading unused
  `datetime.timezone` imports left behind by the `UP017` modernization
  fix (`datetime.timezone.utc` → `datetime.UTC`).
- Removed 126 stale `# noqa` comments that weren't suppressing anything
  currently enabled.
- Added `PLE1205` and `N802` to the project's `ruff` ignore list with
  inline justification comments, after confirming both are false-positive
  categories specific to this codebase (loguru's `{}`-style logging
  misread as stdlib `%`-style; Qt's required camelCase framework
  overrides) rather than leaving noise or incorrectly rewriting correct
  code to satisfy a linter that doesn't understand the frameworks in use.
- Fixed the `ui/themes/palette.py` doc/code mismatch flagged in this same
  report: `ThemeService` used to hardcode its own accent-color dict that
  happened to duplicate `palette.py`'s exact values (an accidental
  duplicate-implementation introduced while completing the Theme Engine,
  without noticing `palette.py` already existed as the documented single
  source of truth). Now `ThemeService` derives its accent defaults
  directly from `palette.py`'s `Palette` dataclasses, making the
  previously-dead file genuinely used and matching `THEMING.md`'s
  documented design for the first time. Zero behavior change (verified:
  the byte-identical-QSS-at-default test still passes), plus a new test
  (`test_theme_service_derives_accents_from_palette_not_duplicated_literals`)
  locking the wiring in against regression.
- Removed 4 files of confirmed-dead, milestone-superseded scaffolding
  (see Issue #4 and §5), backed up in case they're wanted back.

---

## 4. Files Modified

**Core fix:**
`src/jarvis/utils/async_utils.py`, `src/jarvis/ui/async_utils.py`,
`src/jarvis/core/events/event_bus.py`

**Dangling-task call-site fixes (22 files):**
`src/jarvis/features/conversation/controller.py`,
`src/jarvis/features/memory/controller.py`,
`src/jarvis/features/voice/controller.py`,
`src/jarvis/infrastructure/hotkey/pynput_listener.py`,
`src/jarvis/ui/main_window.py`,
`src/jarvis/ui/views/home_view.py`,
`src/jarvis/ui/views/developer/{api_center_view,backup_restore_view,developer_console_view,developer_gate_dialog,security_center_view,update_center_view}.py`,
`src/jarvis/ui/dialogs/settings_pages/{ai_provider_page,api_keys_page,logging_page,memory_page,model_page,startup_page,theme_page,voice_announcements_page,voice_page,wake_word_page}.py`

**Security fix:**
`src/jarvis/services/developer_mode_service.py`

**Theme Engine fix:**
`src/jarvis/services/theme_service.py`

**Config:**
`pyproject.toml` (ruff ignore list, with justification comments)

**Lint cleanup (imports/annotations/noqa, no behavior change) — the
majority of the 242-file source tree** received at least one of: an
unused-import removal, an import-sort, a redundant-quote removal, or a
stale-noqa removal, via `ruff --fix` on confirmed-safe rule categories,
verified compile-clean and test-green after every batch.

**Tests added:**
`tests/unit/test_async_utils.py` (new — 6 tests, including the GC-pressure
reproduction)

---

## 5. Files Removed

| File | Reason |
|---|---|
| `src/jarvis/agents/base_agent.py` | "Implementation in Milestone 5" — Milestone 5 shipped agent orchestration through `agents/orchestrator.py` + LangGraph directly; this base class was never adopted. Zero references. |
| `src/jarvis/agents/state.py` | Same — `AgentState` dataclass never wired into the real orchestrator. Zero references. |
| `src/jarvis/infrastructure/database/base_repository.py` | "Milestone 3 will fill it in" — real repositories (`ConversationRepository`, `MemoryRepository`, ...) don't inherit from it. Zero references. |
| `src/jarvis/infrastructure/stt/whisper_provider.py` | "implementation deferred to Milestone 2" — superseded by `whisper_local_provider.py` and `openai_whisper_provider.py`, which is what `stt/provider_factory.py` actually wires up. Zero references. |

All four were verified unreferenced via (1) a full-package `pkgutil`
import-and-execute sweep, (2) module-path `grep` across `src/` and
`tests/`, and (3) class-name `grep` across `src/` and `tests/`, before
removal. Copies were kept at `/tmp/removed_dead_code/` for this session in
case any are wanted back — say so and they can be restored verbatim.

Nothing else was removed. The three additional unused files found
(`file_utils.py`, `platform_detector.py`) were deliberately
**not** removed — see §10.

---

## 6. Performance Improvements

| | Before | After |
|---|---|---|
| Fire-and-forget task survival under GC pressure | Not guaranteed (weak-referenced) | Guaranteed (strong reference held until completion) |
| "Task was destroyed but it is pending!" warnings in test runs | Present in every run this session | Zero |
| Full test suite runtime | ~24s | ~24s (no regression; the fix adds a `set.add`/`discard` per task, negligible) |

No other performance work was done in this pass (Milestone 5's own
completion pass already covered lazy workspace loading and a virtualized
table — see `MILESTONE_5_DELIVERY.md` §5, item 12). A proper performance
audit (startup timing, render profiling, memory profiling under load)
wasn't run here — flagged as not-yet-covered in §10, not claimed as done.

---

## 7. Security Improvements

- Constant-time password-hash comparison (`hmac.compare_digest`),
  eliminating a timing side-channel in the Developer Mode gate.
- Verified clean (pre-existing, not newly introduced, but confirmed by
  this audit rather than assumed): no `eval`/`exec`, no `shell=True`
  subprocess calls (all use safe argv-list form), no `pickle`, no raw SQL
  string interpolation, no hardcoded secrets in source, real
  PBKDF2-HMAC-SHA256 (200k iterations, random salt) for the Developer Mode
  password as claimed in the Milestone 5 delivery doc.
- Not audited in this pass: dependency CVE scanning, file-path traversal
  safety in the Files & Drive workspace's *future* real-filesystem
  integration (currently mock data only, so not yet exploitable), or a
  full review of what Developer Console's automation commands can reach.

---

## 8. UX Improvements

None in this pass — explicitly out of scope per "DO NOT redesign the
existing UI." No UI-facing behavior changed; every fix here is
backend/architecture/security.

---

## 9. Code Quality Improvements

- `ruff` findings against the project's own configured rules: **1013 → 522**
  (fixed via safe autofixes; remainder triaged below).
- Zero circular imports, zero broken imports, across all 232 modules
  (verified by executing every module, not just parsing it).
- Zero TODO/FIXME/HACK debt (2 hits, both harmless doc cross-references).
- 4 files of dead scaffolding removed (see §5).
- Duplicate `utils` package prevented from becoming permanent (see §3).

**Remaining lint findings, triaged (not blindly left, not blindly fixed):**

| Rule | Count | Disposition |
|---|---|---|
| `PLC0415` import-outside-top-level | 281 | Reviewed as a category: this is the codebase's deliberate lazy-import pattern for circular-import avoidance (used consistently, not sloppiness). Not touched — blanket-fixing risks introducing real circular imports. |
| `E501` line-too-long | 136 | Cosmetic (1–16 chars over the 100-char limit in the sampled cases). Would need `black`, not `ruff --fix` — see §10. |
| `UP042` replace-str-enum | 22 | Valid modernization (`class X(str, Enum)` → `class X(StrEnum)`, Python 3.11+) but touches every enum in the codebase for a purely stylistic gain; not applied — high blast radius, low value. |
| `PLR0915`/`PLR0912`/`PLR0917` complexity metrics | 12 | Real candidates for future refactor (a few genuinely long functions), but refactoring working code without a specific bug to fix is out of this pass's scope per "DO NOT rewrite working code unnecessarily." |
| `RUF001`/`RUF002`/`RUF003` ambiguous unicode | 11 | Sampled: intentional typographic characters (em-dash, bullet, ellipsis) in UI copy and docstrings. False-positive-ish for a polished consumer app; not touched. |
| `SIM105` suppressible-exception | 9 | Valid `contextlib.suppress` suggestions; low-risk but not applied in this pass (time-boxed) — good candidate for a future pass. |
| Everything else | ~51 | Long tail of 1–3 count categories, individually reviewed, none critical. |

---

## 10. Remaining Issues (only what's necessary to flag)

1. **`black` formatting: not run.** 204/242 files would be reformatted.
   Sampled diffs are genuinely trivial (blank line after module docstring,
   collapsing a now-short-enough multi-line call). **Not executed** because
   this sandbox's Python 3.12 explicitly warns it cannot safely verify
   AST-equivalence for the project's Python-3.13-targeted code — running a
   242-file blanket reformat under a tool that admits it can't fully verify
   itself is the wrong risk trade here. **Recommendation:** run `black .`
   in a real Python 3.13 environment (CI or a pre-commit hook), where the
   safety check is trustworthy.
2. **2 unused-but-harmless files not removed**: `utils/file_utils.py`
   (two small generic helpers, never called), `infrastructure/platform/platform_detector.py`
   (a reasonable OS-detection utility, never wired up — the codebase does
   platform branching some other way). Neither is broken; both are
   candidates for either completion or removal in a future pass.
   (`ui/themes/palette.py`, previously flagged here, was fixed this
   session — see §3.)
3. **Coverage gaps are concentrated in UI wiring, not business logic.**
   The weakest-covered files are almost entirely Settings pages
   (9–30% coverage — `voice_page.py`, `wake_word_page.py`,
   `memory_page.py`, `api_keys_page.py`, etc.) and a few dialogs
   (`settings_dialog.py` at 10%, `developer_gate_dialog.py` at 14%). These
   are mostly thin Qt-signal-wiring code (button → `set_env` call) rather
   than logic with edge cases, but a real audit shouldn't claim they're
   "tested" when they're not. Services and domain logic are
   substantially better covered.
4. **This audit did the deepest area-by-area review on Architecture,
   Security, and Reliability (the areas with the highest defect density
   found), plus targeted deep-checks on Voice, Memory, and Automation
   (see below). Developer Mode UX, API Center depth, and pixel-level
   frontend consistency were spot-checked but not walked screen-by-screen.**

   **Voice** (`services/voice_service.py`, TTS/STT/wake-word provider
   factories): real device switching (`settings.voice.input_device`/
   `output_device` passed through to `sounddevice`), a clean pluggable
   provider registry per subsystem (no `if/elif` chains, lazy imports so
   selecting one backend doesn't require every backend's optional
   dependency), and proper error-state transitions on transcription
   failure (`VoiceState.ERROR` + typed `ServiceError`, not a silent
   swallow). No issues found.

   **Memory** (`services/memory_service.py`): full CRUD + semantic recall
   + pinning + archiving + retention-policy enforcement + stats +
   export/import, all confirmed real by direct read. Export/import is
   JSON-only (no `pickle`/`eval`), every imported field is defensively
   type-checked, malformed entries are skipped-and-logged rather than
   aborting the whole import, and imported memories get fresh IDs
   (avoiding ID-collision issues). No issues found.

   **Automation** (`features/automation/permission.py`,
   `features/automation/executor.py`): the permission gate fails closed
   by default (auto-denies when no confirmation channel is wired up),
   CRITICAL-risk actions are always denied outright, a fixed list of
   dangerous actions (delete, shutdown, restart, terminal, ...) always
   requires explicit human confirmation regardless of computed risk, and
   the one auto-approve escape hatch is opt-in-only with a warning log.
   The executor has real per-step timeout enforcement, retry with linear
   backoff, and undo-record tracking for reversible actions. No issues
   found.

   Not deep-audited this pass: Developer Mode's remaining views
   screen-by-screen, API Center's validator/health-check depth beyond
   the CRUD confirmed to exist, and pixel-level frontend consistency
   (spacing/typography/animation) across every workspace.

---

## 11. Completion Score

Scored honestly against what was actually verified this pass, not
estimated. A milestone is only scored above what direct evidence supports.

| Milestone | Score | Basis |
|---|---|---|
| Milestone 0 (scaffolding/architecture) | **92%** | Verified: zero circular imports, zero broken imports across all 232 modules, clean layering, DI container fully wired, dead scaffolding removed. Docked for: `black` non-compliance across most of the tree (not yet enforced), 3 orphaned utility files. |
| Milestone 1 (config/theming/logging foundation) | **91%** | Theme Engine genuinely completed in the prior session (verified: accent overrides are byte-identical at defaults, `switch()` no longer stubbed) and the `palette.py`/`THEMING.md` doc-code mismatch resolved this session (`ThemeService` now genuinely derives from `palette.py`). Docked slightly for `black` non-compliance in this area's files. |
| Milestone 2 (voice) | **80%** | Real STT/TTS/wake-word provider architecture confirmed live and importable; the dangling-task fix directly touched `features/voice/controller.py` (9 sites) — a real reliability fix to this milestone specifically. Not independently deep-audited this pass (see §10.4) beyond that. |
| Milestone 3 / 3.1 (memory) | **78%** | `MemoryService` confirmed real (embeddings, hybrid recall, retention policies) via direct code read while building the Greeting Engine's memory-recall integration in a prior session. `base_repository.py` scaffolding removed as dead (repositories were built directly, bypassing it). Not independently deep-audited this pass beyond that. |
| Milestone 4 (automation) | **78%** | Verified security-clean (no shell injection, safe subprocess patterns). Not independently deep-audited for retry/timeout/recovery logic depth this pass. |
| Milestone 5 (official UI) | **90%** | The most-audited milestone by far across this whole engagement — built, then completion-passed (9 sections), then this audit found and fixed the dangling-task bug across most of its own dialogs/settings pages/views. 211/211 tests passing. Docked for: coverage gaps concentrated here (settings pages), `black` non-compliance. |
| **Overall Project** | **85%** | Weighted toward the areas with direct evidence (architecture, security, reliability, Milestone 5) rather than an average that would implicitly claim equal audit depth everywhere. |

**What would move these numbers**: running `black` in a correct Python 3.13
environment, raising Settings
UI coverage, and doing the same evidence-based, area-by-area pass this
report did for architecture/security on Voice/Memory/Automation/API
Center/Developer Mode specifically (rather than the spot-checks this pass
had time for).
