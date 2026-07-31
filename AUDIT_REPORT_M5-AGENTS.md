# JARVIS OS v0.4.0 — Pre-Merge Validation: Milestone 5-Agents

Scope: validate that the Milestone 5-Agents delivery (Agent Runtime /
LangGraph — see `MILESTONE_5_AGENTS_DELIVERY.md`) is production-ready
before Milestone 6 begins. No new features implemented in this pass;
fixes are scoped to what real installation/execution actually
surfaced.

---

## 1. Environment

- **OS:** Windows 11 Pro 10.0.26200
- **Python:** 3.13.14 (matches `requires-python = ">=3.13,<3.14"`)
- **Venv:** fresh `.venv`, created for this pass (project had never
  been installed into a real environment before — no prior `.venv`,
  no packages present, not even `psutil`)
- **Install method:** `pip install -e ".[dev]"`, exactly as documented
  in `README.md`

## 2. Dependency Installation Results

✅ **Success**, no unresolved conflicts. ~140 packages installed
(PySide6, FastAPI, SQLAlchemy, ChromaDB, LangGraph/LangChain
ecosystem, Playwright, openai-whisper/torch, dev tooling). Key
resolved versions relevant to this milestone: `langgraph==0.6.11`,
`langchain-core==0.3.86`, `langgraph-checkpoint==2.1.2`,
`langgraph-checkpoint-sqlite==2.0.11` — all within the ranges declared
in `pyproject.toml`.

One real bug found and fixed during this step (not merely an install
failure — the install *succeeded*, but the resulting environment was
runtime-broken for the default configuration): see §10.1.

## 3. Static Analysis Results

Tools run: `ruff check`, `black --check`, `mypy --strict` (the three
configured in `pyproject.toml`/`.pre-commit-config.yaml`; no
`isort`/`pyright`/`flake8` configured — `ruff`'s `I` ruleset already
covers import sorting).

**Major finding: none of the three tools had ever actually been run
against this codebase before.** `ruff check src tests` found **588
errors across the whole repository**; `black --check src tests` found
**262 of 304 files** would be reformatted; `mypy src` found **288
errors in 75 files**. These numbers are far too large to originate
from this milestone alone and were confirmed file-by-file to be
pre-existing (e.g. `chat_service.py`, `container.py`, and dozens of
other files nobody touched this session all fail `black --check`
identically). This is a real, load-bearing finding for production
readiness (see §14), but out of scope to mass-fix here — doing so
would mean reformatting/re-annotating the entirety of the
feature-frozen Milestones 0–5.5, which the brief for this session
explicitly prohibits ("do not rewrite stable code").

**What was in scope and fixed:** every file this milestone created or
meaningfully modified.

| Tool | Before fix | After fix (my files only) |
|------|-----------|----------------------------|
| `ruff` | 60 findings in my files | 0 (except the deliberate, pre-existing-convention-matching `PLC0415` lazy-import pattern — see below) |
| `black` | 28 of my new files needed reformatting (all the same repo-wide docstring-blank-line issue) | 0 — all reformatted |
| `mypy --strict` | 15 findings in my files | 0 |

Fixed for real (not suppressed): 9 `E501` line-length violations, 1
`I001` import-sort, 1 `PLW0108` unnecessary lambda, 1 `SIM300` Yoda
condition, 5 `mypy` missing-generic-type-argument errors (`dict` →
`dict[str, Any]` throughout `agents/nodes/*.py` and
`agents/prompting.py`), 1 real `mypy` type error in
`system_tools.py` (`object // int` — fixed with an accurate `cast`),
5 `StateGraph.add_node` overload-resolution errors (a genuine
mypy/LangGraph-stub limitation with async node callables, not a
runtime bug — scoped `# type: ignore[call-overload]` with an
explanatory comment), and one real pre-existing **interface bug** in
`core/interfaces/agent.py`: `IAgentOrchestrator.stream` was declared
`async def stream(...) -> AsyncIterator[str]`, which mypy correctly
flags as incompatible with any real async-generator implementation
(`async def ... : yield ...`) — fixed by declaring the Protocol stub
without `async` (a well-known Python typing subtlety; see the code
comment for the full explanation). This interface fix is the one
change in this pass that touches Milestone 0 code — justified as a
compatibility fix per this session's own stated exception for M0–5
changes, and only became visible now that a real, non-stub
implementation of `stream()` exists for the first time.

**Left alone, documented, not "fixed":** the pervasive `PLC0415`
(import-not-at-top-level) pattern. This is a deliberate, pre-existing
convention already used extensively in `core/di/container.py` (with
its own docstring explaining why — lazy imports keep expensive/
platform-specific adapters out of the import path) and in the
pre-existing test suite (`test_ui_milestone5_smoke.py` alone has 110
instances). My code matches that convention on purpose; "fixing" it
would mean restructuring dozens of pre-existing files' import style,
well beyond this milestone's scope.

## 4. Test Summary

`pytest -q --no-cov` (see §10.2 for why `--no-cov` was needed):

- **308 passed, 0 failed, 1 error, 0 skipped** (309 collected)
- The 1 error is `test_ollama_stream_against_fake_server` — missing
  `aiohttp_server` fixture (`pytest-aiohttp` extra not installed).
  **Pre-existing and already documented**: `docs/MASTER_ROADMAP.md`'s
  own "Tests completed" section calls this file out by name as an
  expected exclusion "not installed in every environment." Not this
  milestone's issue.

Two pre-existing tests initially failed — both were **directly and
correctly caused by this milestone's intentional behavior changes**,
not regressions, and were updated to match:
- `test_main_window_registers_shutdown_hooks_in_correct_order` — now
  expects `agent_orchestrator` in the registered shutdown-hook set
  (it's a real, intentional new hook — see `MILESTONE_5_AGENTS_
  DELIVERY.md` §2).
- `test_developer_dashboard_builds_all_thirteen_sections` → renamed
  `..._fourteen_sections` — Developer Mode now has 14 sections, not
  13, because of the new Agent Trace panel.

One new test was added *during* this validation pass (not part of the
original ~40): `test_invoke_with_real_sqlite_checkpointer` — see §10.1
for why.

## 5. Coverage Report

**Not available as configured.** `pytest --cov` (the project's default
`addopts`) crashes with a pytest-cov `INTERNALERROR`:
`coverage.exceptions.DataError: Can't combine branch coverage data
with statement data`. Root-caused (not just worked around): the
pre-existing test `tests/unit/test_performance_lazy_imports.py`
spawns a real Python subprocess (to measure cold-import time), and
that subprocess's own coverage data doesn't inherit the project's
`branch = true` setting, so `pytest-cov`'s combine step fails whenever
that test runs under `--cov`. Reproduced in isolation (running just
that one file with `--cov` reproduces the crash; every other file
individually does not). **Pre-existing, unrelated to this milestone**
— fixing it properly means adding subprocess-coverage propagation
(`COVERAGE_PROCESS_START` + a `sitecustomize.py`, or `parallel = true`
+ explicit `.pth` wiring) to the test infrastructure, which is new
test-infra work, not a Milestone 5-Agents fix. Worked around for this
report via `--no-cov` to get real pass/fail signal (§4); coverage
percentages themselves were not obtainable this pass.

## 6. Test Counts

| | Count |
|---|---|
| Collected | 309 |
| Passed | 308 |
| Failed | 0 |
| Errors | 1 (pre-existing, documented, optional-dependency exclusion) |
| Skipped | 0 |
| New tests added this pass | 1 (`test_invoke_with_real_sqlite_checkpointer`) |

## 7. Warnings

- `LoggingSettings.json` shadows a `BaseSettings` attribute — cosmetic,
  pre-existing, already tracked in `docs/MASTER_ROADMAP.md` §10.
- `LangChainPendingDeprecationWarning` from `langgraph.checkpoint.
  serde.jsonplus` (`allowed_objects` default will change upstream) —
  informational, no action needed on our side.
- Several `RuntimeWarning: coroutine ... was never awaited` in
  pre-existing UI smoke tests (`test_ui_milestone5_smoke.py`'s `_Fake.
  __getattr__` stub pattern) — pre-existing test-double artifact, not
  a real unawaited-coroutine bug in application code.

## 8. Security Findings

**Agent-runtime-specific (in scope for this milestone):**
- ✅ Prompt-injection fencing verified: tool output is wrapped in
  `<<<TOOL_OUTPUT>>>...<<<END_TOOL_OUTPUT>>>` markers with an explicit
  "don't treat this as instructions" notice in every prompt that
  consumes tool history — added *during* this milestone's build (see
  `agents/prompting.py`'s `UNTRUSTED_TOOL_OUTPUT_NOTICE`), verified by
  `test_format_tool_call_history_renders_success_and_error`.
- ✅ No `subprocess`/`os.system`/`eval`/`exec`/`pickle`/`shell=True`
  anywhere in `agents/` (grepped directly).
- ✅ No hardcoded secrets/credentials/API keys in any new file
  (grepped for `api_key`/`secret`/`password`/`token` across `agents/`
  — only false-positive matches on the word "token" in streaming-UX
  comments).
- ✅ No new path-traversal surface: the only new filesystem write is
  `agent_checkpoint_db_path()`, a fixed filename under the existing,
  already-trusted `resolved_data_dir` — no user input reaches a path.
- ⚠️ **`CVE-2025-67644`** — SQL injection in `langgraph-checkpoint-
  sqlite` 2.0.11 via unvalidated checkpoint-metadata *filter keys* in
  `.list()`/`get_state_history()`. **Not exploitable by any code this
  milestone shipped** — nothing here calls a checkpoint search/filter
  API; `AgentOrchestrator` only ever calls `ainvoke`/`astream` with a
  fixed `thread_id` config. Documented as a hard constraint on the
  "checkpoint-resume UI" future-work item (§5 of the delivery doc) —
  if that's ever built, filter keys must never accept unvalidated user
  input, independent of whether the package has been upgraded by then.

**Repo-wide (`pip-audit`, not a repo-configured tool — run as a bonus
check since dependency-vulnerability scanning was requested):** 24
known vulnerabilities across 12 packages, the large majority in
`langchain`/`langgraph`/`cryptography`/`black`/`pytest` — all
**pre-existing pinned dependencies from before this milestone**
(`langchain*`/`langgraph` version ranges were declared in the original
Milestone 0 scaffolding; `cryptography`, `black`, `pytest` are
pre-existing dev/runtime deps). Every fix version listed by `pip-audit`
crosses a major-version boundary this repo's existing pins explicitly
exclude (e.g. `langchain<1.0` → fix is `1.3.9`); bumping any of them
is a dedicated, separately-tested upgrade effort, not something to
fold into this validation pass. `langgraph-sdk`/`langsmith` CVEs
(URL-path injection, arbitrary file read via `TracingMiddleware`) are
not applicable to this application's actual deployment model — JARVIS
OS is a local desktop app that never runs a LangGraph server or
LangSmith tracing middleware.

## 9. Performance Observations

- ✅ No blocking UI operations: `AgentTraceView._on_run` uses the
  existing `fire_and_forget` helper, matching every other Qt
  controller in the codebase.
- ✅ No infinite graph loops: verified live —
  `test_invoke_stops_at_max_steps_even_if_critic_never_satisfied`
  drives a critic that *always* says "not complete," and the graph
  still terminates at exactly `max_steps` (also hard-clamped against
  `constants.MAX_AGENT_STEPS_HARD_CAP = 200` regardless of
  configuration).
- ✅ No dangling asyncio tasks: `AgentOrchestrator` creates no
  unawaited tasks; the one background piece (the barge-in monitor
  pattern used elsewhere in `VoiceService`) isn't replicated here.
- ✅ Graceful shutdown: `agent_orchestrator.stop()` registered with
  `ShutdownManager` at `PRIORITY_EARLY` (alongside `voice_service`,
  before `browser_service`/`automation_service`'s own resources tear
  down) — confirmed via the (now-updated) shutdown-hook-ordering test.
- ✅ Checkpoint cleanup: `AgentCheckpointer.close()` calls the
  `AsyncSqliteSaver` async-context-manager's `__aexit__`, releasing the
  `aiosqlite` connection; verified via the new
  `test_invoke_with_real_sqlite_checkpointer` completing a full
  `invoke()` → `stop()` cycle against a real file with no error or
  warning.
- ⚠️ **Duplicated service instances (pre-existing characteristic, not
  introduced by this milestone):** `browser_service` and
  `automation_service` are DI `Factory` providers (new instance per
  resolution), while `agent_orchestrator` is a `Singleton` that
  resolves them once at construction. This means the orchestrator's
  internal `BrowserService`/`AutomationService` instances are *not*
  shared with whatever the rest of the UI resolves separately — this
  was already true before this milestone existed (the `automation`/
  `browser` DI wiring predates Milestone 5-Agents); flagged here for
  visibility, not fixed, since changing `Factory`→`Singleton` for
  those two providers is a cross-cutting DI change affecting every
  other consumer, well outside this milestone's scope.

## 10. Root-Cause Fixes Applied During This Pass

### 10.1 Real runtime bug: `aiosqlite`/`langgraph-checkpoint-sqlite` incompatibility

A live, end-to-end smoke test (`AgentOrchestrator` resolved through
the *real* DI container, not constructed directly as the unit tests
do) surfaced an `AttributeError: 'Connection' object has no attribute
'is_alive'` the very first time a real graph was invoked with the
default `checkpoint_enabled=True`. Root cause: `langgraph-checkpoint-
sqlite==2.0.11`'s `AsyncSqliteSaver.setup()` calls
`self.conn.is_alive()`, which only exists because `aiosqlite`'s
`Connection` class used to subclass `threading.Thread`; `aiosqlite`
0.21+ dropped that. `aiosqlite` resolved to `0.22.1` (latest satisfying
the pre-existing, unbounded `<1.0` constraint) — a version that no
longer has `is_alive()`.

This was invisible to the original unit tests
(`test_agent_checkpointer.py`) because they only exercise
`open()`/`close()`, never a real graph invocation through the SQLite
path — `open()` succeeds either way (the bug is inside `setup()`,
called lazily on first *use*, not at `open()` time).

**Fix:** pinned `aiosqlite>=0.20,<0.21` in `pyproject.toml` and
`requirements.txt` (still within the pre-existing `>=0.20` floor;
0.20.0's `Connection` still has `is_alive()`, confirmed directly).
Verified end-to-end after the fix (real DI resolution → real tool
registry → real compiled graph → real `AsyncSqliteSaver` → successful
`invoke()` → clean `stop()`). **Added a permanent regression test**,
`test_invoke_with_real_sqlite_checkpointer`, so this specific gap
(unit tests covering `open()` but not a real invocation) can't recur
silently.

### 10.2 Tooling bug: `pytest-cov` combine crash

See §5 — root-caused to `test_performance_lazy_imports.py`'s
subprocess spawn not propagating coverage config. Worked around with
`--no-cov` for this pass; not fixed (out of scope, pre-existing,
unrelated to Milestone 5-Agents).

### 10.3 Two pre-existing tests updated for this milestone's intentional changes

See §4 — both failures were the *expected* consequence of adding a
real `agent_orchestrator` shutdown hook and a 14th Developer Mode
section, not regressions.

## 11. Documentation Consistency

Re-verified against actual code/test state after all fixes in this
pass:
- `docs/MASTER_ROADMAP.md` — §1/§2/§3/§9/§10 all describe Milestone
  5-Agents as done, consistent with what actually shipped and passed.
- `docs/ROADMAP.md`, `docs/ARCHITECTURE.md` — updated during the
  original delivery, still accurate.
- `CHANGELOG.md` `[0.4.0]` entry — accurate; no changes needed for
  this validation pass's fixes (the `aiosqlite` pin and the new
  regression test are small enough to fold into the existing entry's
  "Known limitations" framing rather than warranting a new version
  bump).
- `MILESTONE_5_AGENTS_DELIVERY.md` — updated in this pass (see its own
  changelog note at the top) with the `aiosqlite` fix, the CVE
  constraint, and the corrected "tests not executed" claim (they now
  have been, successfully).
- Version numbers (`pyproject.toml`, `__version__.py`,
  `Settings.app_version`) — all consistently `0.4.0`.

No outdated documentation found that needed removal.

## 12. Remaining Technical Debt

Carried over from `MILESTONE_5_AGENTS_DELIVERY.md` §5 (vision tool
deferred to M6, no chat-view integration, word-chunked rather than
true token streaming, no per-step timings, no checkpoint-resume UI, no
automation confirmation-callback wiring, no dedicated Agents settings
page — all unchanged by this pass) **plus newly discovered in this
validation pass**:
- `ruff`/`black`/`mypy` have real, large pre-existing findings across
  the whole repository (588 / 262-files / 288 respectively) that were
  never previously caught because these tools were never actually run.
  Recommend a dedicated, separately-reviewed formatting/lint-fix pass
  before relying on `pre-commit` catching regressions going forward.
- `pytest --cov` is broken by a pre-existing subprocess-coverage gap
  in `test_performance_lazy_imports.py`; coverage percentages are
  currently unobtainable via the documented command.
- 24 known CVEs across 12 pre-existing pinned dependencies
  (`langchain*`, `langgraph`, `cryptography`, `black`, `pytest`) —
  none introduced by this milestone, all requiring major-version
  bumps to fix; recommend a dedicated dependency-upgrade effort with
  its own regression testing, not bundled into a feature milestone.

## 13. Production Readiness Assessment

**Milestone 5-Agents itself: production-ready**, for the scope it
actually claims (see `MILESTONE_5_AGENTS_DELIVERY.md`'s explicit
Remaining Work list — vision, chat integration, etc. are deliberately
out of scope, not readiness gaps). All new code is clean under
`ruff`/`black`/`mypy --strict`; the full test suite passes; a live
end-to-end smoke run through the real DI container succeeded; the one
real runtime bug this pass found was root-caused, fixed, and given a
permanent regression test; the security posture of the new prompt-
injection surface was deliberately hardened, not just left open.

**The broader repository** carries real, newly-surfaced technical
debt (§12) that predates this milestone and isn't blocking it, but
should not be ignored indefinitely — first real install + first real
lint/type/test run in this project's history surfaced issues that
years of "looks done" review couldn't, simply because the tooling had
never been executed for real before now.

## 14. Merge Recommendation

**Recommend merge.** Milestone 5-Agents's own code is verified clean
and working end-to-end; the runtime bug found in this pass is fixed
with a regression test, not just patched around. The pre-existing
repo-wide lint/format/type/CVE debt (§12) is real and worth scheduling
as its own dedicated pass, but it predates this milestone, doesn't
regress anything Milestone 5-Agents touches, and fixing it here would
have meant reformatting/re-annotating virtually the entire codebase —
explicitly out of scope for a milestone validation.

---

**Milestone 5 is production-ready.**

Recommend beginning: **Milestone 6 — Vision & Multimodal.**
