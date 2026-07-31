# Troubleshooting

Practical answers to problems that can actually occur, based on this
project's real, verified behavior -- not a generic template.

## App won't start / settings seem reset to defaults

If `.env` (in the app's working directory, or the data directory) was
corrupted -- most commonly by a power loss or forced shutdown mid-write
-- JARVIS now falls back to default settings rather than crashing (see
`CHANGELOG.md`, 0.3.0). You'll see a warning on stderr:
`WARNING: could not read .env config (...); starting with defaults
instead of crashing.` This means your saved preferences (theme, accent
color, etc.) were lost, but the app still starts. Reconfigure via
Settings; your conversations/memories (stored in the database, not
`.env`) are unaffected.

## Browser automation doesn't work after a fresh install/build

Playwright's Python package is bundled by the build, but its actual
browser binaries are downloaded separately and are **not** bundled by
PyInstaller. If you built from source: run `python -m playwright install
chromium` (the build script, `packaging/build_windows.ps1`, does this
automatically).

## Voice features are silent / microphone not detected

Check Settings → Voice for the configured input/output device
(`settings.voice.input_device` / `output_device`) -- if the device name
changed (e.g. after an OS update or a different USB headset), voice
input/output falls back to the system default, which may not be what
you expect. There's no first-run device picker yet (see
`docs/PACKAGING.md`'s onboarding gap) -- device selection currently
lives in Settings only.

## Developer Mode won't unlock

The Developer Mode password is stored as a salted PBKDF2-HMAC-SHA256
hash (`services/developer_mode_service.py`), not recoverable if
forgotten. There's no "forgot password" flow currently -- resetting
requires clearing the stored hash from settings and setting a new
password from a fresh state.

## An automation was blocked / needs confirmation I didn't expect

By design: deletions, shutdown/restart, terminal commands, and a few
other action types always require explicit confirmation regardless of
how "safe" the specific instruction looks (see
`features/automation/permission.py`). Browser navigation to a
`file://`, `javascript:`, `data:`, or a few other non-http(s) URL scheme
is automatically **denied** outright (not just confirmed) -- this is
intentional (it could otherwise read local files or execute script
content via the browser). Ordinary `http(s)://` URLs and bare domains
(`example.com`) are unaffected, as is a plain `host:port` address like
`localhost:8080` for local development.

## "Task was destroyed but it is pending!" warnings in logs

If you see this on a build predating the 0.3.0 stabilization pass, it's
a known, since-fixed reliability issue (55 sites, see `CHANGELOG.md`).
Update to a build that includes the `ShutdownManager`/`fire_and_forget`
fixes. If you see it on a current build, that's a regression worth
reporting -- it shouldn't occur anymore.

## Building from source: PyInstaller/Inno Setup complain about missing modules

`packaging/jarvis.spec` and `packaging/jarvis_installer.iss` are
foundational and not yet build-verified on real Windows hardware (see
`docs/PACKAGING.md`) -- if PyInstaller's static import analysis misses
something at actual Windows runtime, add it to the `_hiddenimports` list
in `jarvis.spec` and re-run. This is expected to need at least one
iteration on the first real build.

## Where to look next

- `docs/ARCHITECTURE.md` -- how the codebase is laid out and why.
- `docs/PACKAGING.md` -- honest build/install status.
- `AUDIT_REPORT_M0-M5.md` -- the full evidence-based engineering audit
  this project has been through, including every known remaining gap.
