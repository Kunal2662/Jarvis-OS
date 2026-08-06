# Packaging & Distribution

> **Two packaging paths exist, and the newer one supersedes the older.**
> Everything below the "Legacy" heading describes the **PySide6**
> desktop application packaged with PyInstaller and Inno Setup, written
> during the Milestone 5.5 stabilization pass. The frontend has since
> migrated to React + Tauri (M8), and Windows packaging is now
> **Tauri/NSIS** — see the section immediately below. The legacy
> material is kept because the Python backend it packages is unchanged
> and the section's honesty notes still apply to it; it is *not* the
> current route to a Windows installer.

## Current: Tauri + NSIS (M22 Task Group C, v0.36.0)

**Status: Implementation Complete — Build Verification Pending.**

Configured in `frontend/src-tauri/tauri.conf.json`:

* **Target: `nsis`.** One installer, per-user (`installMode:
  "currentUser"`), so no elevation prompt. English only, no language
  selector for a single-language product. `allowDowngrades: false`.
* **Icons are wired but are still Tauri's defaults.**
  `frontend/src-tauri/icons/` holds a complete, valid `.ico` and PNG set,
  so the build will not fail for a missing icon — but the artwork is the
  **Tauri logo** from `tauri init`, not JARVIS branding. As it stands the
  installer, desktop and Start Menu shortcuts, taskbar entry and
  Add/Remove Programs listing would all show Tauri's emblem. The legacy
  section's "no application icon" gap is therefore *not* closed; it has
  moved from missing to wrong, which is less obvious and worth catching
  before any public build. Replacing the set requires real artwork.
* **The host bridge** (`frontend/src-tauri/src/installer.rs`) is what
  makes the packaged app able to *install itself*: it spawns
  `python -m jarvis.installer` and relays its progress to the installer
  UI. See `ARCHITECTURE.md` §22.15.
* **Logging is unconditional**, to the platform log directory under
  `jarvis-installer`. A release build is exactly where an install
  failure needs a log.

### Build Verification Tasks — gate to Complete

No Rust toolchain on the machine this was written on, so none of the
ten tasks below has run. All ten must pass before this task group is
Complete, and Linux/macOS packaging (Task Groups D+) waits for
that plus explicit approval:

1. Build the Windows installer with the Rust toolchain.
2. Verify the installer builds successfully.
3. Verify desktop shortcut creation — relies on Tauri's default NSIS
   template; v2.11's `NsisConfig` exposes no shortcut toggle, only
   `startMenuFolder` and `installerHooks`, so the default is trusted
   rather than forced through an untested `.nsh`.
4. Verify Start Menu shortcut creation — same template.
5. **Replace all default Tauri branding with official JARVIS
   branding.** Unstarted, not merely unverified — see above.
6. Verify installer metadata (publisher, copyright, descriptions).
7. Verify the uninstall entry.
8. Verify Launch JARVIS against a real packaged executable.
9. Verify Open Installation Folder against a real install.
10. Verify the provisioning bridge end to end inside the packaged
    application — the packaged `.exe` spawning bundled Python and
    relaying real progress into a real webview, not the CLI run
    standalone or the Rust/TypeScript contract, both already checked
    (see `MILESTONE_REPORT.md` §7).

Also still open on this path, independent of the gate above: portable
edition, auto-start, native notifications, code signing, and CI.

**First job for whoever has a Rust toolchain:** work through the ten in
order — `npm run tauri build` in `frontend/` first, expecting compile
errors in ~450 lines of never-compiled Rust — then report the outcome
of all ten before Task Group D starts.

### Not superseded

The Python side is unchanged by the Tauri migration. `pyproject.toml`'s
entry points, and the packaging of the backend itself, are as described
below.

---

## Legacy: PyInstaller + Inno Setup (PySide6 era)

**Status as of the Milestone 5.5 production-stabilization pass: foundational,
not release-ready.** This document is deliberately specific about what
exists, what was verified, what wasn't, and why -- rather than claiming a
packaging pipeline is "done" when it hasn't produced or tested a real
Windows executable.

## What exists today

* **A proper, pip-installable Python package.** `pyproject.toml` declares
  `[project.scripts]` entry points (`jarvis`, `jarvis-api`) and a real
  `[build-system]` (setuptools). `pip install -e .` and `python main.py`
  both work and are exercised indirectly by the test suite's own
  environment setup.
* **`packaging/jarvis.spec`** -- a PyInstaller spec file with hidden-imports
  and data-file collection reasoned through against this project's actual
  dependency list (PySide6, chromadb, alembic, tiktoken, langgraph -- the
  packages most likely to trip up PyInstaller's static import analysis).
  The `collect_all()`/`collect_data_files()` calls in it were verified to
  execute successfully against the real installed packages (confirmed:
  PySide6 → 3401 data files / 221 binaries / 84 hidden-imports discovered;
  chromadb → 240 data files / 129 hidden-imports; alembic → 20 data files).
* **`packaging/build_windows.ps1`** -- a build script wrapping the spec
  file, including the easy-to-miss step of downloading Playwright's
  browser binaries separately (PyInstaller bundles the Python package,
  not the browser itself), plus an optional, gracefully-skipped code
  signing step (RC1, section 3) -- signs the built .exe if
  `JARVIS_SIGN_CERT_PATH` / `JARVIS_SIGN_CERT_PASSWORD` environment
  variables are set, otherwise clearly warns and continues with an
  unsigned development build rather than failing.
* **`packaging/jarvis_installer.iss`** -- an Inno Setup installer script
  (RC1, section 2): per-user install (no admin prompt needed), Start
  Menu + optional desktop shortcut, a generated uninstaller with
  repair/modify support, and upgrade support via a fixed `AppId` (Inno
  Setup handles "install a newer version over an older one" once the
  AppId matches, no extra scripting needed). Deliberately does **not**
  delete the user's data directory on uninstall -- conversations,
  memories, and settings survive an uninstall/reinstall cycle.

## What does NOT exist yet (honest gaps)

* **No real Windows build has been produced or tested.** PyInstaller
  cannot cross-compile a Windows `.exe` from a Linux build environment,
  and no Windows machine was available during this pass. The spec file
  and build script above are a documented, reasoned starting point for
  whoever runs the first real build -- not a verified artifact. Expect to
  need at least one iteration fixing missing hidden-imports that only
  surface at actual runtime on Windows.
* **`packaging/jarvis_installer.iss` is similarly unverified** -- there's
  no Inno Setup Compiler available in this environment to actually
  compile and test the installer it describes.
* **No application icon.** `resources/icons/` is currently empty (just a
  `.gitkeep`). Both the spec file and installer script have their
  `icon=`/`SetupIconFile` lines present but commented out with a `TODO`
  rather than pointing at a real `.ico` -- adding one requires real icon
  artwork, which wasn't available to generate as part of this pass.
* **No code-signing certificate.** The signing step in
  `build_windows.ps1` is real and functional, but gracefully no-ops
  without a configured certificate -- getting an actual cert is a
  business/ops decision outside this pass's scope.
* **No CI build pipeline.** Nothing currently runs `pyinstaller`/`iscc`
  on every release the way the test suite runs on every change.
* **No first-run/onboarding wizard exists in the application itself**
  (mic permission, voice setup, AI provider setup, etc.) -- this is a UI
  feature, not packaging, and building one was out of scope for a
  stabilization-only pass (see the note in this doc's revision history /
  the RC1 audit report for why it wasn't added here).

## Recommended next steps (in order)

1. Get access to a real Windows build machine or CI runner and run
   `packaging/build_windows.ps1` for the first time. Fix whatever
   PyInstaller hidden-import gaps surface (there will be some -- this is
   normal for a first PyInstaller pass on a project this size).
2. Compile `packaging/jarvis_installer.iss` with Inno Setup on that same
   machine and test a real install/upgrade/uninstall cycle.
3. Commission or generate a real `.ico` app icon; wire it into both
   `packaging/jarvis.spec`'s `icon=` line and the installer's
   `SetupIconFile`.
4. Obtain a code-signing certificate and set `JARVIS_SIGN_CERT_PATH` /
   `JARVIS_SIGN_CERT_PASSWORD` before any public release build.
5. Design and build a first-run onboarding flow (separate UI work, not
   a packaging task).
6. Wire the above into CI so a release build isn't a manual, one-off
   process.

## Version consistency

*(Updated for M22 Task Group C. This section previously recorded both
versions as `"0.3.0"` and called an automated check "a good candidate
… not implemented yet". It exists now, and it exists because the drift
it was proposed to prevent happened: M8 Phase 7 found `pyproject.toml`
at `0.31.0` while `__version__.py` — whose own docstring calls itself
the single source of truth — still said `0.28.0`.)*

`tests/unit/test_version_consistency.py` enforces that these agree:

| File | What reads it |
|---|---|
| `src/jarvis/__version__.py` | `GET /api/v1/health`, `jarvis --version` |
| `pyproject.toml` | the built wheel |
| `frontend/src-tauri/tauri.conf.json` | the NSIS installer, Add/Remove Programs, the `.exe`'s file properties |

The third was added by Task Group C, the first milestone to produce a
packaged artifact — before it, that file's version was cosmetic. It
caught a live mismatch on the day it was written.

**Bump all three together.** The test fails if you don't.
