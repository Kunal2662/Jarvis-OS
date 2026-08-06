# Milestone Report — M22 Task Group B: Runtime Provisioning

**Version:** 0.34.0
**Branch:** `feature/m22-task-group-b`
**Baseline:** v0.33.0 (`ce1f8a2`)
**Date:** 2026-08-06

---

## 1. Executive summary

TG-A planned an installation. TG-B performs one: dependency detection, a
resumable checksum-verified download manager, a durable provisioning
journal, parallel verification, first-run preparation and an
`installation.json` manifest — all driven by a single engine that is
simultaneously *install*, *resume* and *repair*.

The success criterion was **planning → provisioning → downloading →
verifying → recovering → preparing first launch, without touching the
frozen backend**. That path runs end to end: a real provisioning against
a `file://` mirror completes all eight steps, writes a manifest, and a
second run skips all eight.

Running it for real found **four defects** that the unit tests had not,
including one that looked like it worked.

**Backend untouched.** No route, model, schema, event or contract
changed. `src/jarvis/installer/` still imports no service, repository or
container.

---

## 2. Defects found by running it end to end

### 2.1 A model id is not a filename 🔴

`qwen2.5:14b` is a valid registry identifier and an **impossible Windows
filename** — NTFS reads the colon as a drive qualifier and the write
fails. Since Windows is this milestone's primary platform, every model
download would have failed on it.

Fixed by separating the two concepts: `Artifact.key` addresses the
source, `Artifact.filename` is the sanitised on-disk name. Sources gained
a `{filename}` placeholder alongside `{key}`, because a `file://` mirror
*cannot* store a file named after the raw key.

### 2.2 The same confusion, a second time 🔴

Verification then looked artefacts up by `key` while the downloader had
written them under `filename`, so a correctly-downloaded model was
reported **missing**. Two places had to agree and did not.

Fixed at the source of truth — `_expected_artifacts` keys by filename.

### 2.3 A source spec that looked like it worked 🟠

`JARVIS_DOWNLOAD_SOURCES` used commas both between entries *and* within
`kinds`, so `mirror|url|model,voice|0` silently split into a model-only
source plus an unparseable fragment. **Model downloads worked; voice
downloads found no source.** A bug that half-works is worse than one that
fails outright.

Entries are now semicolon-separated.

### 2.4 A §22.12 leak in my own progress payload 🟠

`DownloadProgress.to_dict(include_source=False)` still carried `key` —
the model id — into a personal user's progress. Caught by the test
asserting no model name appears in a personal payload, which failed on
`qwen2.5:14b`.

Personal progress now carries `display_name` ("Local AI"); the id is
administrator-only.

---

## 3. What was built

| Module | Responsibility |
|---|---|
| `sources.py` | Download-source abstraction. **No URL anywhere in the package.** Ships empty; with nothing configured it names the environment variable rather than falling back to a vendor host. |
| `download.py` | Queued, **byte-level resumable** (HTTP `Range`), checksum-verified downloads with pause/cancel/retry and source failover. |
| `dependencies.py` | Python, Git, Visual C++, CUDA, DirectML, ONNX Runtime. **No code path that writes** — "never silently overwrite" enforced structurally. |
| `journal.py` | Durable, fsynced, atomically-replaced provisioning record. Only completions are written. |
| `first_run.py` | Directory tree and configuration. Idempotent; never overwrites an existing config. |
| `verification.py` | Nine checks, run in parallel. |
| `manifest.py` | `installation.json` — the migration contract. |
| `provisioning.py` | The engine: eight ordered, idempotent steps. |
| `atomic.py` | The shared atomic-write helper the journal and manifest both need. |

CLI: `dependencies`, `provision`, `verify`, `repair <step>`, `status`.

---

## 4. Design decisions worth stating

**There is no separate `resume` command.** `provision` skips whatever the
journal records as complete, so resuming *is* running it again. A resume
that took a different code path would be the path least often exercised
and most often broken.

**Only completions are journalled.** An interrupted step leaves no entry
and is re-run. That is the safe direction, because every step is
idempotent — whereas skipping a step that did not finish leaves a broken
installation that reports itself complete.

**A file only exists once it is verified.** Downloads land in `.part`,
are checksummed there, and are renamed last. So the presence of a file
under its final name is itself proof it passed — recovery never has to
ask whether what it found is trustworthy.

**Unverifiable is not verified.** A source publishing no checksum yields
`verified=False` with a reason, and verification reports it as a
*warning*. Reporting a file as verified when nothing checked it would
make every other guarantee here worthless.

**Repair invalidates forward.** Repairing the model download also forgets
verification and the manifest, because keeping a verification that ran
against a previous file would leave the manifest asserting something
untrue.

---

## 5. Security notes

- **No credentials are read, written or logged.** The installer never
  touches API keys; §22.11 reserves those to an administrator through the
  application, not the installer.
- **§22.12 enforced at the payload**: personal progress carries no model
  id, source name, dependency path or attempt count. Asserted by a test
  that scans a full personal provisioning run for `llama`, `qwen`,
  `piper`, `whisper`, `http://` and `source`.
- **Downloads are integrity-checked where a checksum exists** and
  honestly reported as unverifiable where none does.
- **`file://` sources are marked as not requiring internet**, which is
  what makes a genuinely offline, air-gapped installation possible.

---

## 6. Quality gates

| Gate | Result | vs v0.33.0 |
|---|---|---|
| `pytest` | *(see below)* | +30 |
| `npm test` | 577 passed, 71 files | **unchanged** |
| `npm run lint` | 16 warnings, 1 category | **unchanged** |
| `npm run typecheck` | clean | unchanged |
| `npm run build` | clean | unchanged |
| `black --check src tests` | clean | unchanged |
| `ruff check src tests` | **21 categories** | **unchanged** |
| `mypy src` | **262 errors**, 414 files | **unchanged**, +9 files all clean |

Ruff initially rose to **33 categories** on the new code — 12 new ones.
All were fixed rather than suppressed: `StrEnum` instead of `str, Enum`,
an `Error` suffix on the exception, a named opener instead of a lambda,
`ClassVar` annotations, hoisted imports, and a shared `atomic.py` that
removed two `SIM115` violations by removing the duplication that caused
them.

---

## 7. Deliberately not built

- **No packaging** — no MSI, no EXE, no code signing. Explicitly out of
  scope for this task group.
- **No real download source is configured.** The registry ships empty by
  design; a concrete host would be the hardcoded URL the brief forbids.
  Provisioning against a configured mirror is exercised end to end.
- **No checksums are published**, because no upstream source is wired.
  Verification reports downloads as *present but unverifiable* rather
  than pretending otherwise — the honest state, and it becomes verified
  the moment a source publishes digests.
- **The installer does not create the database schema.** It prepares the
  location and records it; the application's own `initialize()` creates
  the schema on first launch, through the frozen code that owns it. An
  installer writing tables would be a second definition guaranteed to
  drift.
- **No installer UI changes.** TG-A's wizard is unchanged; wiring its
  Install step to this engine needs the Tauri command bridge, which
  belongs with packaging in TG-C.

---

## 8. Version, commit, push

- **Version:** 0.33.0 → **0.34.0**, bumped in both `pyproject.toml` and
  `jarvis/__version__.py` (the M8 Phase 7 consistency test enforces it).
- **Branch:** `feature/m22-task-group-b` · **Push:** confirmed.

Awaiting approval before Task Group C.
