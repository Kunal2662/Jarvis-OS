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

## Current: Tauri + NSIS (M22 Task Groups C–E, v0.36.0–v0.38.0)

**Status: Implementation Complete — Build Verification Pending.**

Configured in `frontend/src-tauri/tauri.conf.json`:

* **Target: `nsis`.** One installer, per-user (`installMode:
  "currentUser"`), so no elevation prompt. English only, no language
  selector for a single-language product. `allowDowngrades: false`.
* **Icons are the official JARVIS master logo, not Tauri's defaults**
  *(corrected here — this paragraph previously described Task Group
  C's state and was never updated when Task Group E replaced the
  artwork; caught during Task Group F's documentation-sync audit, not
  by a reader filing a bug)*. `frontend/src-tauri/icons/` holds two
  deliberate variants derived from the approved master asset — the
  logo as-is for 128px and above, and a hand-simplified,
  high-contrast form for 16–48px, where the master was tested and
  found near-illegible — combined into one hand-packed hybrid
  `icon.ico`. The installer, both shortcuts, the taskbar and Add/
  Remove Programs will show real JARVIS branding once built. See
  `MILESTONE_REPORT.md`'s Task Group E entry and `ARCHITECTURE.md`
  §22.15 for the full reasoning.
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
Complete, and Linux/macOS packaging (Task Group F) waits for that plus
explicit approval:

1. Build the Windows installer with the Rust toolchain.
2. Verify the installer builds successfully.
3. Verify desktop shortcut creation — relies on Tauri's default NSIS
   template; v2.11's `NsisConfig` exposes no shortcut toggle, only
   `startMenuFolder` and `installerHooks`, so the default is trusted
   rather than forced through an untested `.nsh`.
4. Verify Start Menu shortcut creation — same template.
5. ~~Replace all default Tauri branding with official JARVIS
   branding.~~ **Done (Task Group E, v0.38.0)** — real artwork is in
   place; what remains is *observing* it render correctly in a real
   build, which is items 3–4 and 6 below, not this item on its own.
6. Verify installer metadata (publisher, copyright, descriptions).
7. Verify the uninstall entry.
8. Verify Launch JARVIS against a real packaged executable.
9. Verify Open Installation Folder against a real install.
10. Verify the provisioning bridge end to end inside the packaged
    application — the packaged `.exe` spawning bundled Python and
    relaying real progress into a real webview, not the CLI run
    standalone or the Rust/TypeScript contract, both already checked
    (see `MILESTONE_REPORT.md` §7).

**Task Group F (v0.38.0, Windows packaging verification pass) added
two items this list did not previously carry, neither closeable
without the same missing Rust toolchain:**

11. Watch the startup animation (`jarvis-logo.tsx`, Task Group E)
    actually run in a real compositing browser — this session's
    sandboxed preview pane does not composite frames at all (a bare
    `requestAnimationFrame` loop never fired), so nothing built on
    Framer Motion could be observed running in it.
12. Generate and commit `frontend/src-tauri/Cargo.lock` after the
    first successful build. It does not exist yet — `cargo` has never
    run against this repository — and Rust's own convention for a
    binary application (as opposed to a library) is to check the
    lockfile in, so the exact dependency versions a release was built
    against are reproducible later.

Also still open on this path, independent of the gate above: portable
edition, auto-start, native notifications, code signing, and CI.

**First job for whoever has a Rust toolchain:** work through the
twelve in order — `npm run tauri build` in `frontend/` first,
expecting compile errors in ~800 lines of never-compiled Rust — then
report the outcome of all twelve before Task Group F's own status can
move from Implementation Complete to Complete.

### Cross-platform readiness (M22 Task Group F, v0.38.0)

*(Added Aug 2026. Task Group F's brief was explicit: do not implement
Linux or macOS packaging — audit what would be needed, and record it.
Every item below was found by reading the real, current source, not
inferred from what "usually" needs to change for a new platform.)*

**What already generalises.** A real OS-abstraction layer exists and
is used consistently, not just in the one place `ARCHITECTURE.md`
§22.15 calls out:

* `src/jarvis/infrastructure/platform/platform_detector.py` — a single
  `PlatformInfo` dataclass (`is_windows` / `is_macos` / `is_linux`)
  computed once from `platform.system()`. `hardware.py`,
  `dependencies.py` and `validation.py` all branch on it rather than
  scattering their own `sys.platform` checks, and every Windows-only
  probe (Visual C++, DirectML, the `wmic`-based GPU/NPU fallback)
  degrades to an honest "Not required on this platform" / "Windows
  only" result instead of failing or lying when it isn't Windows —
  confirmed by reading each call site, not assumed from the pattern
  holding once.
* The provisioning engine's eight steps (`src/jarvis/installer/`) are
  plain `pathlib`-based Python with no OS-specific branching found in
  them at all — the platform-specific surface is narrower than "the
  installer," it's specifically hardware detection and the native
  host bridge below.
* The frontend's installer copy is already platform-neutral ("Open
  Installation Folder," not "Open in Explorer") — the Windows-specific
  wording lives only in the Rust implementation behind it, not in
  anything a user reads.
* The Tauri command contract is deliberately argument-free where a
  platform difference could otherwise leak into it (`launch_application`
  and `open_installation_folder` take no arguments; the host remembers
  the install location) — a boundary chosen specifically so the
  frontend contract does not have to grow a parameter per platform.

**What is genuinely Windows-only today**, found by grepping
`frontend/src-tauri/src/installer.rs` and `src/jarvis/installer/` for
every `#[cfg(windows)]`, `wmic`, and `.exe` reference rather than
guessing which ones would matter:

* `find_python()` (`installer.rs`) only looks for
  `.venv/Scripts/python.exe` beside the bundled resources and
  `python.exe` / `python3.exe` / `python` on `PATH` — the Windows
  venv layout (`Scripts/`, `.exe` suffix). A non-Windows build needs a
  `.venv/bin/python` branch alongside it.
* `launch_application()` hardcodes the executable name
  `"JARVIS OS.exe"`. Linux ships an extensionless binary; macOS an
  `.app` bundle, a directory rather than a flat file — the resolution
  logic, not just the filename, differs per platform.
* `open_installation_folder()` and `open_log_folder()` are Windows-only
  by explicit `#[cfg(windows)]` / `#[cfg(not(windows))]` branches that
  currently return a clear "only supported on Windows in this build"
  error on any other target — an honest stub, not a silent no-op, and
  the right shape to extend: add an `xdg-open`/`open` branch to each
  rather than redesigning the error contract. Neither call passes
  user-controlled text through a shell (arguments are passed as
  literal `Command` args, never string-interpolated), so the same
  pattern is safe to replicate for the new branches.
* GPU/NPU enumeration falls back to `wmic path win32_VideoController`
  / `win32_PnPEntity` (`hardware.py`) when `nvidia-smi` is absent, and
  only on Windows — no Linux (`/sys/class/drm`, `lspci`) or macOS
  (`system_profiler SPDisplaysDataType`) equivalent exists yet. The
  current fallback ("No GPU could be detected. Calibration used CPU
  and RAM only.") is honest, not wrong, but Linux/macOS installs get a
  less complete hardware picture than Windows ones until these are
  written.
* `tauri.conf.json`'s `bundle.targets` is `["nsis"]` only, with a
  `bundle.windows.nsis` config block and no `bundle.linux` /
  `bundle.macOS` equivalent yet.
* `frontend/src-tauri/src/main.rs`'s
  `#[cfg_attr(not(debug_assertions), windows_subsystem = "windows")]`
  is a Windows-only concept; expected to be a harmless no-op on other
  targets per how the attribute is defined, but this has not been
  confirmed against a real non-Windows build, since none exists to
  test against.

**Migration checklist for a future Linux/macOS task group** — in the
order the items above were found, not a priority ranking:

- [ ] Add a `.venv/bin/python` branch to `find_python()`, alongside
      the existing Windows one.
- [ ] Resolve the installed executable per platform in
      `launch_application()` — extensionless binary (Linux), `.app`
      bundle path (macOS), `"JARVIS OS.exe"` (Windows, unchanged).
- [ ] Add `xdg-open` (Linux) / `open` (macOS) branches to
      `open_installation_folder()` and `open_log_folder()`, matching
      the existing literal-argument `Command` pattern — no shell
      interpolation, on any platform.
- [ ] Add Linux and macOS GPU/NPU probes to `hardware.py`'s
      `detect_gpus()`, gated the same way the existing `wmic` branch
      is (`info.is_windows` → the new `info.is_linux` / `is_macos`
      branch → the existing honest "not detected" fallback last).
- [ ] Add `bundle.linux` (deb/rpm/AppImage) and `bundle.macOS` (dmg)
      target lists and config blocks to `tauri.conf.json`.
- [ ] Confirm on a real non-Windows build that `main.rs`'s
      `windows_subsystem` attribute compiles cleanly (expected, not
      yet observed).
- [ ] Apply `ARCHITECTURE.md` §22.15's two-variant icon pattern to
      `.icns` (macOS) and the target Linux desktop icon theme, rather
      than re-deriving the legibility-at-small-sizes lesson from
      scratch — the master logo's 32×32 illegibility is a property of
      the artwork, not of Windows, and will reproduce on any platform
      that renders a small icon from it.
- [ ] Decide, per platform, what "no elevation, per-user install" and
      "no downgrades" (the two product guarantees the current NSIS
      config encodes) map to mechanically — these are commitments to
      keep, not Windows-specific config to port literally.
- [ ] Generate and commit `Cargo.lock` on the first successful build
      on any platform, if it does not already exist from an earlier
      one (see Build Verification Task 12 above).

Nothing in this checklist was implemented as part of Task Group F —
its own brief was explicit that this pass audits and documents, and
does not build Linux or macOS support.

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
