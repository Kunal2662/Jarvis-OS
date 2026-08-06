# Milestone Report — M22 Task Group C: Windows Packaging & Host Bridge

**Version:** 0.36.0
**Branch:** `feature/m22-task-group-c`
**Baseline:** v0.35.0 (`de618af`, M22 Installer UI integration)
**Date:** 2026-08-06

---

## 1. Executive summary

The host bridge is built. `src-tauri/src/installer.rs` spawns
`python -m jarvis.installer`, relays its NDJSON stdout to the UI as
`provisioning://event`, and implements the four commands the frontend
has been calling into empty space since v0.35.0.

**Not one payload, command name or event name changed.** The contract
was written first — in `provisioning-transport.ts`, before any host
existed — specifically so the UI would need no edit on the day the
bridge landed. It needed none. That is the result the contract-first
split was for, and it is worth stating as the headline because the
alternative (a bridge that forced UI changes) would have meant the
contract was never really a contract.

**Status: Implementation Complete — Build Verification Pending.** Every
line of Rust and every config change described in this report has been
written and reviewed; none of it has been compiled. There is no Rust
toolchain on this machine. §7 states exactly what that leaves proven and
unproven. §9A is the explicit list of ten checks — the **Build
Verification Tasks** — that gate TG-C from Implementation Complete to
**Fully Complete**. This report does not claim TG-C is finished; it
claims the implementation behind it is.

---

## 2. Status of M22

| Task group | Status |
|---|---|
| **A — Universal Installer Foundation** | ✅ Complete (v0.33.0) |
| **B — Runtime Provisioning** | ✅ Complete (v0.34.0) |
| **Installer UI integration** | ✅ Complete (v0.35.0) |
| **C — Windows Packaging & Host Bridge** | 🟡 **Implementation Complete — Build Verification Pending** (v0.36.0, this report) |
| **D–F** | ⬜ Not started — blocked on TG-C reaching Fully Complete |

TG-A and TG-B are unmodified by this work. The provisioning engine, the
download manager, the manifest, the checksum verification, the journal
and the CLI are byte-identical to v0.35.0.

### Execution order

M22 runs out of numeric order, between M8 and M9:

```
M1 … M8  ✅ → M22 (current) → M9 … M21 → M23 deferred
```

It owns installation and packaging, so until it ships there is no way to
deliver M1–M8 to a machine that is not a development checkout.

---

## 3. What was built

| Piece | File |
|---|---|
| Host bridge — 5 commands, event relay, process management | `frontend/src-tauri/src/installer.rs` |
| Command registration, unconditional logging | `frontend/src-tauri/src/lib.rs` |
| Windows/NSIS packaging configuration | `frontend/src-tauri/tauri.conf.json` |
| Cancel transport | `frontend/src/features/installer/provisioning-transport.ts` |
| Cancel control | `frontend/src/features/installer/install-progress-step.tsx` |
| Rust/TypeScript contract suite (13 tests) | `frontend/src/features/installer/__tests__/host-bridge-contract.test.ts` |
| Desktop version parity test | `tests/unit/test_version_consistency.py` |

### Three rules the bridge follows

**stdout is data, stderr is diagnostics.** Only stdout lines become
events; the CLI reserves stdout for JSON so a log line can never be
parsed as progress. stderr is captured for logging and, on an unexpected
exit, its last line becomes the error message — which is what makes a
failure diagnosable rather than "exit code 1".

**It never hangs.** Three independent guards: an inactivity timeout, an
explicit cancel command, and a kill on drop. One of the three did not
work when first written — see §5.

**It never fabricates progress.** If the process cannot start, the
command returns an error naming the reason. No synthetic event is
emitted on any failure path.

### Cancellation, which the UI had modelled but could not reach

Since v0.35.0 the frontend has had a full cancelled state — the
classifier matches `/cancel/i`, the store carries a "Cancelled" label,
the progress list has an icon for it — and **nothing could trigger any of
it.** TG-C's scope names cancellation, so this closes the loop: a host
command, a transport function, and a Cancel control on the progress
screen that appears only when a host can actually act on it.

The control says *"You can continue later from where it stops."* The
journal makes that true, and saying so matters: without it the honest
question "will this leave a broken half-installation?" has no answer, and
the user's alternative is killing the window — the same stop with none of
the cleanup.

---

## 4. The dependency that was planned and should not be added

`IMPLEMENTATION_ROADMAP.md` listed *"`@tauri-apps/plugin-shell`
dependency plus the Rust-side capability to spawn a process"* as a TG-C
item. **It was not added, and planning it was the error.**

A `#[tauri::command]` calling `std::process::Command` needs no plugin.
The shell plugin exists to let *JavaScript* spawn processes — a strictly
larger capability than an installer needs, granted to the surface with
the largest attack area. Spawning stays in Rust behind five named
commands with fixed shapes.

The roadmap item is closed by deciding against it. The capability file
was left at its original minimal permission set for the same reason:
Tauri v2's ACL gates *plugin* commands, and commands registered through
`invoke_handler` are application code, so adding permission identifiers
would have been unverifiable additions with no effect.

---

## 5. Defects found and fixed

All four were in code written during this task group, and three of them
were found by tools rather than by re-reading.

**An inactivity timeout that could never fire.** The check ran *after*
reading a line from stdout. A process that hangs producing no output —
precisely and only the case the timeout exists for — blocks forever
inside the read and never reaches the check. The file's own header
promised "it never hangs" while the guard for the main hang case was
inert. stdout now feeds an `mpsc` channel and the loop waits with
`recv_timeout`, which makes the timeout real and cancellation prompt
instead of dependent on the child speaking first.

**A process that outlived the installer.** Rust's `Child` *detaches* on
drop rather than killing. Closing the installer window mid-run left
Python downloading gigabytes with no window to show for it and no way to
stop it. `ProvisioningState` now implements `Drop`.

**`launch_application` took an argument no caller sends.** Written as
`(location: String)` while `installer-route.tsx` invokes it with none —
a clean compile on both sides and a guaranteed runtime failure the first
time a user pressed the button on the completion screen. Fixed by having
the host remember where it installed, which keeps the documented
no-argument contract intact rather than changing the contract to suit the
implementation. **Found by the new contract suite**, and it is the reason
that suite exists.

**Cancelling reported "the installer process disappeared."** The cancel
path clears the child handle and the exit-status branch ran first, so an
ordinary cancellation surfaced as an error — and missed the word "cancel"
that the failure classifier matches on, so it would have rendered as a
generic failure rather than the cancelled state built for it.

---

## 6. Quality gates

| Gate | Result |
|---|---|
| `pytest` (backend, full suite) | **2293 collected**, exit 0; 1 skipped (a symlink the platform will not create) |
| `vitest` | 75 files, **675 tests** passing (658 at baseline + 17 new) |
| `tsc -b --noEmit` | Clean |
| `oxlint` | 16 warnings, **0 errors**; none in installer files |
| `vite build` | Clean, 1.71s |
| `black --check` | 586 files unchanged |
| `ruff` (`src/jarvis/installer`) | Clean |
| `mypy` (`src/jarvis/installer`) | 16 files, no issues |
| `cargo build` / `tauri build` | ⛔ **Not run — no Rust toolchain** |

`ruff` over the whole repository reports 1111 pre-existing findings,
unchanged by this work; the one finding in a file this task group
touched (`PLC0415` in `test_version_consistency.py`) is present on the
baseline too.

The backend suite passed in full, 2293 tests. TG-B's engine suite is
30 of them — the number this project's docs have carried since v0.34.0,
confirmed by collection rather than repeated from the last report. The
installer-specific subsets
(`test_installer_calibration.py`,
`test_installer_provisioning_e2e.py`, `test_architecture.py`,
`test_version_consistency.py` — 77 tests) were also run on their own and
pass; TG-B's engine is untouched by this work.

### 6.1 New tests

**13 Rust/TypeScript contract tests.** They read `installer.rs` as
*text* rather than compiling it. That is deliberately weaker than an
integration test and is the point: it needs no toolchain, so it runs in
the ordinary `vitest` pass on any machine, including this one. It pins
command names, argument arity, `invoke_handler` registration and the
event name.

Mutation-tested: reintroducing the `launch_application(location: String)`
defect makes it fail with
`launch_application expects location: String but is invoked with no arguments`.

**4 cancel-path tests** — the control appears while running, calls the
host, states that stopping is safe, and is absent both when the host
cannot cancel and after a run has already failed.

**1 desktop version-parity test.** `tauri.conf.json` is now held to
`__version__`. TG-C is the first milestone to produce a packaged
artifact, so it is the first where that file's version is something a
user reads — in Add/Remove Programs and the executable's properties —
while `/api/v1/health` reports the other number. That is the same drift
`test_version_consistency.py` was written for, one file wider. It caught
a live mismatch immediately: `tauri.conf.json` was at 0.36.0 while the
package was still at 0.35.0.

---

## 7. What is proven, and what is not

**Unproven — no Rust toolchain (`cargo` and `rustc` both absent):**

- Nothing in `src-tauri/` has been **compiled**. Type errors, borrow
  errors and missing imports in `installer.rs` and `lib.rs` would not
  have been caught here.
- No `tauri build` has run. **No installer has been produced.**
- No shortcut, icon, install flow, uninstall flow or Add/Remove Programs
  entry has been observed.
- **The application icon is Tauri's default logo, not JARVIS
  branding.** The icon set is complete and valid, so a build will not
  fail — but the installer, both shortcuts, the taskbar and Add/Remove
  Programs would all show Tauri's emblem. Found by opening the PNG
  rather than by checking the files exist, which is all the earlier
  "all five icons present" check established. Replacing it needs real
  artwork and is not something this task group should invent.
- Desktop and Start Menu shortcuts are left to Tauri's default NSIS
  template, which is believed to create both. This is **not confirmed**,
  and v2.11's `NsisConfig` has no shortcut toggle — only
  `startMenuFolder` (which would nest a single app in a needless
  subfolder) and `installerHooks`. Forcing the desktop shortcut through
  an untested `.nsh` would risk breaking the entire installer build to
  guarantee one icon, so the default is trusted and flagged rather than
  overridden blind.
- The runtime behaviour of every path in §5 — the timeout, the kill on
  drop, the cancel ordering — is reasoned, not executed.

**Proven without a toolchain:**

- Both JSON configs parse.
- All five referenced icons exist on disk.
- Every NSIS key used is a real key in the bundled
  `@tauri-apps/cli/config.schema.json` (v2.11.4) — checked against the
  schema, not from memory.
- The Rust/TypeScript contract holds, by the 13 tests above.
- **The Python side of the bridge, by running it.** Both commands were
  executed with the exact argv `build_command` constructs, against a
  real temporary target:
  - `plan --target X --account-type personal` → exit 0, one JSON
    document on stdout, which is what `load_installation_plan` parses.
  - `provision --target X --account-type personal --stream` → **exit 2**
    and 6 NDJSON lines, one object per line, ending
    `{"event": "result", …}`. Exactly the shape the relay loop emits and
    `parseEventLine` consumes.
  - Exit 2 is the engine's "blocked" code, and the run reached it
    honestly: three steps completed, then `model_download` failed
    because no download source is configured — the empty-registry
    behaviour TG-B designed. This confirms the branch in `installer.rs`
    that distinguishes exit 2 ("already described by the stream, report
    saved progress") from an unexpected crash is the branch that fires
    in practice, not a theoretical case.
- The frontend builds, typechecks, lints and passes 675 tests.

What remains unproven about the bridge is therefore **the Rust half
specifically** — the spawning, relaying and lifecycle code — not the
contract it sits between, both ends of which have now been exercised.

**This task group should not be considered complete until someone runs
`npm run tauri build` on a machine with the Rust toolchain.** The first
build will likely surface compile errors; that is expected of ~450 lines
of uncompiled Rust and does not indicate a design problem. §9 turns this
list into the ten explicit Build Verification Tasks that gate TG-C to
Fully Complete.

---

## 8. Constraint compliance

| Constraint | Held |
|---|---|
| Do NOT modify TG-A or TG-B functionality | ✅ Engine, downloads, manifest, journal, CLI byte-identical |
| Use the existing documented transport contract | ✅ No payload, command name or event renamed |
| Do NOT redesign payloads / rename events | ✅ `provisioning://event` unchanged; contract test pins it |
| Maintain backward compatibility | ✅ `provision` without `--stream` unchanged |
| Do not add unrelated plugins | ✅ None added — including the one the roadmap planned |
| Do not modify provisioning logic | ✅ No file under `src/jarvis/installer/` changed |
| Do NOT implement Linux or macOS packaging | ✅ NSIS only |
| Do not implement Auto Start | ✅ Not implemented |
| Never hang | ✅ Three guards, one of which had to be fixed to be real |
| Never fake progress | ✅ No synthetic events on any path |
| Always display actionable errors | ✅ stderr's last line surfaced; exit 2 distinguished from a crash |
| Do NOT expand the roadmap | ✅ One roadmap item closed by decision, none added |

**File associations** were deferred, per the brief's "defer if not
planned" — nothing in the roadmap plans them.

---

## 9. Build Verification Tasks — gate to Fully Complete

**TG-C is Implementation Complete, not Fully Complete.** These ten
checks are what closes the gap, in the order a build machine would
naturally hit them. Every one requires a Rust toolchain (`cargo`,
`rustc`) that this machine does not have, so **none has been run**. Each
row states what already exists to support the check and what "pass"
means; none of that existing support is a substitute for running it.

| # | Task | What exists toward it | Verified? |
|---|---|---|---|
| 1 | Build the Windows installer with the Rust toolchain | `tauri.conf.json` targets `nsis`; both JSON configs parse; all referenced icons exist on disk | ⬜ Not run |
| 2 | Verify the installer builds successfully | ~450 lines of `installer.rs` have never been compiled — expect and fix compile errors on the first attempt | ⬜ Not run |
| 3 | Verify desktop shortcut creation | Relies on Tauri's default NSIS template; v2.11's `NsisConfig` has no shortcut toggle to configure either way | ⬜ Not run |
| 4 | Verify Start Menu shortcut creation | Same default template; `startMenuFolder` was deliberately left unset (a single app does not need its own subfolder) | ⬜ Not run |
| 5 | Replace all default Tauri branding with official JARVIS branding | **Not started.** `frontend/src-tauri/icons/` currently holds Tauri's own logo (confirmed by opening the PNG, not just checking the files exist) — the installer, both shortcuts, the taskbar and Add/Remove Programs would all show it. Needs real JARVIS icon artwork before any build is public-facing | ⬜ Not started |
| 6 | Verify installer metadata | `publisher`, `copyright`, `category`, `shortDescription`, `longDescription` are set in `tauri.conf.json`; not yet seen rendered in a real installer or Properties dialog | ⬜ Not run |
| 7 | Verify the uninstall entry | NSIS generates one by default; per-user install mode (`installMode: "currentUser"`) chosen so it needs no elevation; never produced or inspected | ⬜ Not run |
| 8 | Verify Launch JARVIS | `launch_application` takes no arguments, reads the location the host recorded during the run, and is unit-tested against the frontend's call site (§6.1) — but has never launched a packaged executable | ⬜ Not run |
| 9 | Verify Open Installation Folder | `open_installation_folder` — same no-argument shape, same test coverage, same "never run for real" status | ⬜ Not run |
| 10 | Verify the provisioning bridge in the packaged application | The bridge's Python side was exercised directly (§7) and the Rust/TypeScript contract is tested (§6.1), but the full path — packaged `.exe` spawning the bundled Python, relaying real progress into a real webview — has not | ⬜ Not run |

**Task 5 is not merely unverified — it is unstarted work**, distinct
from the other nine, which are verification of something already built.
Branding needs real artwork before it can be checked at all.

**Gate:** TG-C moves from Implementation Complete to **Fully Complete**
only once all ten rows above read pass. TG-D does not begin until then,
and only with explicit approval — this report does not request that
approval; it requests approval to run the verification pass.

---

## 10. Recommended next step

Get access to a machine with the Rust toolchain and work through §9 in
order — each task assumes the ones above it passed. Report the outcome
of all ten (or exactly where one fails) before TG-D starts. TG-D's
Linux/macOS packaging would otherwise be built on top of a Windows
packaging configuration that has never produced an artifact.
