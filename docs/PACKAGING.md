# Packaging & Distribution

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

`pyproject.toml`'s `version` and `Settings.app_version` (in
`core/config/settings.py`) are both `"0.3.0"` and were confirmed in sync
as of this pass. Keep them in lockstep on every version bump -- nothing
currently enforces this automatically (a good candidate for a small CI
check, not implemented yet).
