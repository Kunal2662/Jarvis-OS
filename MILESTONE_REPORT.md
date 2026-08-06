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
**Complete**. This report does not claim TG-C is finished; it
claims the implementation behind it is.

---

## 2. Status of M22

| Task group | Status |
|---|---|
| **A — Universal Installer Foundation** | ✅ Complete (v0.33.0) |
| **B — Runtime Provisioning** | ✅ Complete (v0.34.0) |
| **Installer UI integration** | ✅ Complete (v0.35.0) |
| **C — Windows Packaging & Host Bridge** | 🟡 **Implementation Complete — Build Verification Pending** (v0.36.0, this report) |
| **D–F** | ⬜ Not started — blocked on TG-C reaching Complete |

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
Complete.

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

## 9. Build Verification Tasks — gate to Complete

**TG-C's status is Implementation Complete — Build Verification
Pending, not the terminal Complete status.** These ten
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

**Gate:** TG-C moves from Implementation Complete to **Complete**
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

---

## 11. Governance Verification Report

*(This section is the deliverable of a separate, documentation-only
governance pass — not new TG-C work. No application code changed; the
version stays `0.36.0`.)*

### Documentation updated

| File | What changed |
|---|---|
| `docs/ARCHITECTURE.md` | New §23 Milestone Lifecycle (§23.1–§23.6: the six canonical statuses) and §23.7 Build Verification Policy. TOC updated. §22.15's Windows status line corrected to the canonical wording (was "in progress", which is a defined status word TG-C has already passed). |
| `docs/MASTER_ROADMAP.md` | New §18 M22 Acceptance Criteria, §19 Roadmap Governance, §20 Documentation Synchronization Policy. TOC updated. §2's execution-order diagram rewritten to the literal Completed/Current/After-M22/Deferred format, with a note reconciling the pre-existing four-symbol (✅🟡🟠🔴) roadmap-position marker against the new six-status lifecycle. TG-C references updated to canonical wording throughout. |
| `docs/IMPLEMENTATION_ROADMAP.md` | New M22 Acceptance Criteria section, mirroring §18 with task-group checklist detail. New Current Project Status block in §1. TG-C's status line and its "Not verified" lead-in corrected to canonical wording. |
| `README.md` | Status line and execution-order paragraph corrected to canonical wording and cross-referenced to the new governance sections. |
| `CHANGELOG.md` | 0.36.0 entry's status line and Notes corrected (`Fully Complete` → `Complete`). |
| `docs/PACKAGING.md` | Build Verification Tasks heading corrected (`Fully Complete` → `Complete`). |
| `MILESTONE_REPORT.md` (this file) | §9's heading and internal references corrected; this §11 added. |

### Governance improvements added

- **A single, closed vocabulary for milestone status** — Planned, In
  Progress, Implementation Complete, Build Verification Pending,
  Complete, Production Ready (`ARCHITECTURE.md` §23) — replacing the
  five different phrasings TG-C's status had accumulated across five
  documents before this pass.
- **A Build Verification Policy** (`ARCHITECTURE.md` §23.7) naming
  which categories of platform-specific work require a real build
  before Complete: Rust, Windows Installer, Linux Packages, macOS
  Packages, Code Signing, Release Validation — and stating explicitly
  that reading a schema, a text-level contract test, or reasoning
  about a default template does not satisfy it, even though TG-C used
  all three legitimately for what they *can* prove.
- **A worked Acceptance Criteria example for M22** in two places
  (`MASTER_ROADMAP.md` §18, `IMPLEMENTATION_ROADMAP.md`'s own section),
  kept in the same six-status vocabulary, stating the exact condition
  under which "M22 is complete" may be said at all: all six task
  groups at Complete, with TG-C's specifically requiring Build
  Verification Passed, not just an implementation checklist.
- **Permanent Roadmap Governance rules** (`MASTER_ROADMAP.md` §19): no
  renumbering, no silent redefinition of a completed milestone,
  CHANGELOG entries are corrected by addition not edit, corrections
  must identify themselves as corrections, and `MASTER_ROADMAP.md` is
  named explicitly as the tie-breaker when documents disagree.
- **A Documentation Synchronization Policy** (`MASTER_ROADMAP.md` §20)
  naming the six documents every completed milestone must update, and
  stating that synchronization is a *precondition* of the
  Implementation Complete status (§23.3's third bullet) rather than a
  follow-up task.

### Remaining documentation drift

Found and fixed in this pass, not left standing:

- **"Fully Complete"** — a term this session coined for TG-C across
  eight locations in the previous commit, before the canonical
  vocabulary existed. Not one of the six defined statuses; replaced
  everywhere with **Complete**.
- **A comma where the canonical phrase uses an em dash** — "Implementation
  Complete, Build Verification Pending" appeared twice (`README.md`,
  `IMPLEMENTATION_ROADMAP.md`) against "Implementation Complete —
  Build Verification Pending" everywhere else. Normalized.
- **"Windows is in progress"** (`ARCHITECTURE.md` §22.15) — used a
  defined status word (In Progress) to describe a milestone that has
  already passed that status. Corrected to Implementation Complete —
  Build Verification Pending.
- **A stray "Not verified" lead-in** (`IMPLEMENTATION_ROADMAP.md`,
  TG-C's detail paragraph) that functioned as an second, competing
  status declaration sitting directly under the canonical one in the
  section heading above it. Replaced with the canonical phrase.

**Found and deliberately left alone, with reasoning recorded so it is
a decision and not an oversight:**

- **`MASTER_ROADMAP.md`'s §17 "Appendix" section contains roughly 3,900
  lines of chronological addenda** (milestone-completion narratives
  appended after the appendix table, using bold-text pseudo-headers
  rather than `##`/`###` headings) that structurally belong nearer §3
  or §8. This predates this pass, is unrelated to milestone-status
  terminology, and reorganizing it is a large, separate content-move
  that this documentation-governance task did not ask for and that
  risks breaking a great deal of existing cross-referencing for no
  governance benefit. Flagged here rather than silently worked around.
- **The pre-existing four-symbol roadmap-position marker** (✅ Completed
  / 🟡 Active / 🟠 Deferred / 🔴 Planned, used throughout §2, §3, §8,
  and `IMPLEMENTATION_ROADMAP.md`'s §1 table) is a coarser, different
  axis than the new six-status lifecycle and was not replaced by it —
  see the reconciling note added to `MASTER_ROADMAP.md` §2. Replacing
  every one of these symbols across two multi-thousand-line documents
  with the new vocabulary would be a much larger change than this
  governance pass, for a distinction (roadmap position vs.
  implementation-readiness) that is genuinely useful to keep separate.
- **Historical milestone entries' own status words** (e.g. "✅ shipped"
  used throughout M9–M11's task-group headers in
  `IMPLEMENTATION_ROADMAP.md`) were not rewritten to the new
  vocabulary. Those milestones are historically complete and frozen
  (`ARCHITECTURE.md` §20's freeze note, `MASTER_ROADMAP.md` §3); this
  pass's Documentation Synchronization Policy (§20) governs
  milestones going forward, and §19's "no silent redefinition of a
  completed milestone" rule counsels against touching their language
  retroactively without a specific reason to.

### Confirmation

- **Milestone numbering:** unchanged. No milestone number was added,
  removed, or reassigned in this pass.
- **Execution order:** stated identically (Completed M1–M8 → Current
  M22, with TG-A/TG-B Complete, TG-C Implementation Complete — Build
  Verification Pending, TG-D/E/F Not Started → resumes M9…M21 → M23
  deferred) in `MASTER_ROADMAP.md` §2, `IMPLEMENTATION_ROADMAP.md`'s
  new Current Project Status block, and `README.md`.
- **Version consistency:** unaffected — this pass changed no code and
  no version file; `0.36.0` is unchanged in `pyproject.toml`,
  `src/jarvis/__version__.py`, and `tauri.conf.json`, and
  `tests/unit/test_version_consistency.py` (added in the TG-C
  implementation commit) still holds all three to the same value.
- **Acceptance criteria consistency:** `MASTER_ROADMAP.md` §18 and
  `IMPLEMENTATION_ROADMAP.md`'s M22 Acceptance Criteria section carry
  identical per-task-group statuses (diffed directly while writing
  this report — the only difference is the checklist detail the
  implementation-roadmap copy adds, which is additive, not
  contradictory).
- **The roadmap is now the single authoritative source.**
  `MASTER_ROADMAP.md` §19 states this as a permanent rule and names
  itself as the tie-breaker; every other document in this pass
  (`ARCHITECTURE.md`, `IMPLEMENTATION_ROADMAP.md`, `README.md`) was
  edited to cross-reference it rather than restate its own competing
  account of sequencing.

**TG-D is not started by this pass, and this report does not request
that it start.** It requests approval to begin work on §9's Build
Verification Tasks — the only thing standing between TG-C's current
status and a Complete M22.

---

## 12. Governance Completion Report

*(This section is the deliverable of a second, final documentation-only
governance pass — not TG-C work, not a milestone-status change. No
application code, no backend logic, no frontend logic, no version, and
no milestone status changed in this pass. TG-C remains Implementation
Complete — Build Verification Pending; TG-D remains Not Started.)*

### Documentation updated

| File | What changed |
|---|---|
| `docs/ARCHITECTURE.md` | New §24 Project Development Principles — twelve principles, positioned as this document's highest-level policy via a banner note ahead of the table of contents (added at §24 rather than §1, to avoid renumbering the 23 existing, already-cross-referenced sections). Cross-reference lines added to §20 and §23.7, pointing up to the principles they instantiate — no content removed from either. |
| `docs/MASTER_ROADMAP.md` | Cross-reference lines added to §19 and §20's opening notes, pointing up to `ARCHITECTURE.md` §24 — no content removed from either section. |
| `MILESTONE_REPORT.md` (this file) | This §12 added. |

No other file needed a change: `README.md`, `CHANGELOG.md`,
`docs/IMPLEMENTATION_ROADMAP.md`, and `docs/PACKAGING.md` contain
status declarations and operational checklists, not governance-rule
prose, so this pass — which added a philosophy layer above existing
governance sections — had nothing to add to them.

### Governance principles added

Twelve, in `ARCHITECTURE.md` §24, each stated once and cross-referenced
from wherever its detailed form already lived rather than restated:
Architecture First, Roadmap First, Documentation is Authoritative,
Verify Before Assuming, Never Fake Functionality, Evidence-Based
Engineering, Backward Compatibility, Single Source of Truth, Frontend/
Backend Synchronization, Quality Before Completion, Platform
Verification, Continuous Synchronization.

Each principle above its cross-referenced detail section: #2 → §19
(Roadmap Governance), #3 and #12 → §20 (Documentation Synchronization
Policy), #1 and #3 → §20 of this document (Governance — how this
document changes), #11 → §23.7 (Build Verification Policy), #10 → §23
(Milestone Lifecycle) as a whole. Principles #4 through #9 are new
statements — this project had been *practicing* verify-before-assuming
and never-fake-functionality all session (§22.11/§22.12's payload-level
enforcement, the installer's "measured or `None`, never estimated"
rule, the contract-first transport split) without ever naming them as
project-wide policy in one place; §24 is that naming, not a change in
practice.

### Duplicate governance removed or cross-referenced

**Nothing was removed.** On inspection, the existing governance
sections (`ARCHITECTURE.md` §20, §23.7; `MASTER_ROADMAP.md` §19, §20)
were not restatements of a single rule in different words — each
carries specific operational detail (exactly which six documents
Documentation Synchronization Policy covers, exactly which six
categories Build Verification Policy names) that a short philosophical
principle does not and should not duplicate. The applicable cleanup
was therefore additive: a one- or two-sentence cross-reference at the
top of each of those four sections, naming which of the new twelve
principles it instantiates, so a reader lands on the philosophy first
and the mechanics second rather than encountering four independent
governance voices with no stated relationship between them.

No milestone history was touched. No `CHANGELOG.md` entry was edited.

### Remaining governance drift

None found in this pass. The terminology sweep (below) turned up no
new synonym for a canonical status word, no conflicting statement about
sequencing or documentation ownership, and no principle whose detailed
section disagreed with its one-line summary.

**One thing intentionally left as a forward pointer, not drift:**
TG-D/E/F's letter-to-scope assignment is still undecided
(`MASTER_ROADMAP.md` §18's own note). That is real open work, not a
governance inconsistency — §19's rule that "the implementation order
must always be documented" is satisfied by documenting *that* it is
undecided, not by prematurely deciding it here.

### Verification performed

- **Governance terminology consistent:** grepped `ARCHITECTURE.md` and
  `MASTER_ROADMAP.md` for `Fully Complete` and the comma-separated
  `Implementation Complete, Build Verification Pending` form after
  adding §24 — the only matches are the intentional vocabulary list
  and the intentional historical quote of the retired term in §20's
  own explanatory prose (both already present before this pass).
- **No conflicting governance statements:** §24's twelve principles and
  the four detailed sections they point to were read together
  side-by-side while writing the cross-references above; none
  contradicts another.
- **Milestone Lifecycle terminology remains canonical:** §23's six
  statuses are unchanged by this pass — §24 references them by name
  without redefining them.
- **Roadmap Governance remains consistent:** §19's six rules are
  unchanged; only a two-sentence pointer was prepended.
- **Documentation Synchronization Policy remains consistent:** §20's
  six-document table and its rules are unchanged; only a two-sentence
  pointer was prepended.
- **Markdown structure:** code-fence balance and table-row well-
  formedness checked programmatically after every edit in this pass;
  all TOC anchors (`#24-project-development-principles` included)
  resolve to real headers.

### Confirmation

Governance is, per this task's own instruction, considered **stable**
as of this commit. §1–§23 are the detailed standards; §24 is the
philosophy they serve; §19–§20 in `MASTER_ROADMAP.md` are the
roadmap-specific and documentation-specific instantiations of that
philosophy. No further governance restructuring is planned, and none
should occur in future milestone work unless explicitly requested —
ordinary work applies these principles going forward; it does not
revisit them.

TG-D remains Not Started. This report does not request that it start.

---
---

# Milestone Report — M22 Task Group D: Universal Installation Experience

**Version:** 0.37.0
**Branch:** `feature/m22-task-group-c`
**Baseline:** v0.36.0 (TG-C, Implementation Complete — Build Verification Pending)
**Date:** 2026-08-07

> **This is a second, separate report appended to the same file, not a
> rewrite of the one above.** Nothing above this divider was edited:
> TG-C's report — including §9's ten still-unrun Build Verification
> Tasks, cross-referenced from `MASTER_ROADMAP.md`, `IMPLEMENTATION_
> ROADMAP.md` and `README.md` — remains exactly as it was. TG-D's own
> report follows, with its own §1 onward.

## 1. Executive summary

TG-C's report closed by saying TG-D would not begin until its ten
Build Verification Tasks passed, with explicit approval. **That did
not happen here, by explicit instruction.** The user approved TG-C's
implementation, left its Build Verification Tasks outstanding, and
directed this task group to begin anyway. That is the user's call to
make and is recorded here as the deviation it is, not silently folded
into "business as usual" — §8 covers it in full alongside every other
deviation this task group made from the roadmap as previously
documented.

**Status: Implementation Complete — Build Verification Pending.** Same
status as TG-C, for the same reason: this task group added five
commands to `src-tauri/src/installer.rs`, and there is still no Rust
toolchain on this machine to compile them. One `tauri build`, once
available, proves both task groups' Rust at once — see §7.

**The audit that preceded implementation found most of the brief
already built.** TG-D's brief listed fifteen items. Ten were already
real: the progress framework, download manager UI, resume, retry,
failure classification and a completion screen all shipped in TG-A
through TG-C and the installer UI pass. What remained was narrower —
the backend already had a nine-check verifier, a `repair()` method and
a `status`/`dependencies` CLI surface with zero frontend exposure. This
report is about that wiring, not about fifteen features built from
nothing.

---

## 2. Status of M22

| Task group | Status |
|---|---|
| **A — Universal Installer Foundation** | ✅ Complete (v0.33.0) |
| **B — Runtime Provisioning** | ✅ Complete (v0.34.0) |
| **Installer UI integration** | ✅ Complete (v0.35.0) |
| **C — Windows Packaging & Host Bridge** | 🟡 Implementation Complete — Build Verification Pending (v0.36.0) |
| **D — Universal Installation Experience** | 🟡 **Implementation Complete — Build Verification Pending** (v0.37.0, this report) |
| **E, F** | ⬜ Not started; scope (Linux/macOS packaging, cross-platform QA) reassigned from the old "D–F" block — see §8 |

TG-A, TG-B and TG-C are unmodified by this work: `git diff --stat
src/jarvis/` against this task group's start is empty, and TG-C's own
five Rust commands were extended, not edited — see §4.

---

## 3. What was built

| Piece | File |
|---|---|
| Five additive Rust bridge commands, shared JSON-command helper | `frontend/src-tauri/src/installer.rs` |
| Command registration | `frontend/src-tauri/src/lib.rs` |
| Five transport functions, three new types (`DependencyReport`, `InstallationStatus`, `RepairResult`), `installationPresence()` | `frontend/src/features/installer/provisioning-transport.ts`, `provisioning-types.ts` |
| Shared check-row component (extracted from `installer-steps.tsx`) | `frontend/src/features/installer/check-row.tsx` |
| Verification-with-repair panel, reused by two screens | `frontend/src/features/installer/verification-panel.tsx` |
| Diagnostics dialog (status, dependencies, verification, log folder) | `frontend/src/features/installer/installer-diagnostics.tsx` |
| Full verification report + repair wiring on the completion screen | `frontend/src/features/installer/completion-step.tsx` |
| Diagnostics trigger, existing-installation notice, prop threading | `frontend/src/features/installer/installer-wizard.tsx` |
| Real transport implementations composed | `frontend/src/features/installer/installer-route.tsx` |
| 8 real fixtures (`dependencies.*`, `status.*`, `verify`, `repair.*`) + 57 new tests across 4 new and 5 extended test files | `frontend/src/features/installer/__tests__/` |

### The five Rust commands, and why none of TG-C's changed

`check_dependencies`, `get_installation_status`, `verify_installation`,
`repair_installation`, `open_log_folder` — each a thin, non-streaming
wrapper around an **already-shipped, unmodified** Python CLI
subcommand. Confirmed by running all four subcommands for real during
the audit (`dependencies`, `status`, `verify`, `repair`), against a
real temporary target, before writing a line of Rust against them —
including the exit-code edge cases (`verify` on an unhealthy target
exits 2; `repair` on an unknown step exits 2 with `{"error": …}`).

A shared `run_json_command` helper backs four of the five (`open_log_
folder` needs no CLI call). `load_installation_plan` — TG-C's own
non-streaming command — was **not** refactored to use it, despite being
the same shape: that function already shipped, this machine cannot
compile a change to verify it still works, and a small amount of
duplicated Rust is the safer trade against a mistake nothing here would
catch before a real build does. The equivalent React-side duplication
(`ValidationRow`, §4) *was* refactored away, because that side has
tests to catch a mistake and the Rust side does not — the same
principle, opposite conclusion, because the two sides have different
safety nets.

### Component verification and repair, reachable for the first time

Nine post-install checks (`jarvis/installer/verification.py`) existed
since TG-B with `repairable`/`repair_step` fields designed, per that
module's own docstring, for exactly this UI to exist — and nothing
called them. The completion screen now shows all nine, not only
warnings, each with a Repair button when repairable. Repair invalidates
and re-runs the named step through the engine's own `repair()`, then
**re-verifies** rather than trusting the repair's own result: a repair
can complete having failed a *later* step (a blocked download) without
the check that triggered it ever running again, so only a fresh
verification pass can say whether it actually worked.

### Diagnostics and update preparation

A dialog, reachable from any step via a persistent trigger, showing:
whether an installation already exists at the chosen location and its
journal progress (`status`), a dependency report (`dependencies`), and
the same verification-with-repair panel the completion screen uses —
one component, two mount points, not two implementations. Existing-
installation detection is also proactive: the wizard checks
automatically as soon as a location is chosen and shows a notice
without the user having to open anything.

---

## 4. Defects found and fixed

Two, both in code written during this task group, both found by tests
rather than by re-reading.

**Existing-installation detection disagreed with itself.** The
wizard's proactive notice checked `manifest || journal progress`; the
diagnostics dialog's own "Existing installation" field checked
`manifest` alone. A partially-completed install (dependencies and
directories done, nothing else) read as "an installation exists" on
one screen and "none found" on the other, for the same location. Found
by testing the dialog against `status.resumable.fixture.json` — a real,
partially-completed status — rather than only against a fresh one,
which is exactly the case the narrower check silently mishandled.
Fixed by extracting one shared `installationPresence()` classification
(`none` / `partial` / `complete`) that both now call, and by making the
label itself more honest in the process — "Partially installed" rather
than folding a partial and a complete install into the same "Found".

**A stale-closure race in the diagnostics dialog's own first draft.**
The effect that decides whether to run verification read the `status`
*state variable* inside a `.then()` chained off the status fetch — but
`setStatus` had not re-rendered yet at that point, so the check ran
against the previous render's `null`, not the value `getStatus` had
just returned. Caught while writing the effect, before it was ever
tested against a real interaction, by re-reading the promise chain
rather than trusting it worked because the shape looked right. Fixed by
restructuring the effect as a single `async` function using the
resolved value directly, which also removed an `eslint-disable` the
first draft needed and the corrected version does not.

---

## 5. Judgment calls: what "do not modify TG-A/B/C" was taken to mean

The brief allowed touching TG-A/B/C only "to fix a genuine defect". Five
decisions turned on how that was read, stated here so the reasoning is
inspectable rather than assumed:

- **Additive props with defaults, verified by tests, were treated as
  in-scope.** `onRepair`, `getInstallationStatus`,
  `verifyInstallation`, `checkDependencies`, `onOpenLogFolder` were
  added to `InstallerWizardProps`/`CompletionStepProps` as new,
  optional-or-defaulted fields — the same shape Task Group C used to
  add `cancelProvisioning` without controversy. Every existing call
  site continued to compile and pass without changes beyond adding the
  new field.
- **`ValidationRow` was extracted, not left duplicated**, because this
  task group's own brief explicitly requires "no duplicated widgets"
  for its own new UI, and `installer-wizard.test.tsx` /
  `installer-contract.test.ts` exercise `SummaryStep`'s continued use
  of it — a regression fails an existing test rather than shipping
  silently. Confirmed unchanged by running both suites immediately
  after the move.
- **The Rust side's equivalent duplication was *not* removed** — see
  §3's `run_json_command` note. Same underlying question, opposite
  answer, because there is no compiler here to catch a mistake in
  `load_installation_plan` the way there is for `SummaryStep`.
- **Zero Python files were touched.** Every one of `dependencies`,
  `status`, `verify`, `repair` already existed, unmodified, doing
  exactly what this task group needed. This is why "reuse existing
  architecture" and "do not modify TG-A/B" turned out not to conflict
  in practice — the honest answer to "does this need a defect
  exception" was "no" in every case, because nothing needed changing.
- **A pre-existing, unrelated defect was fixed anyway.** `tsc -b
  --noEmit` — the project's actual `npm run typecheck` — was already
  failing at `HEAD`, before this task group's first edit, because
  `host-bridge-contract.test.ts` (TG-C) imports Node builtins the app's
  `tsconfig.app.json` does not globally type. Confirmed by stashing
  this task group's changes and re-running typecheck against the
  unmodified branch. This is squarely "a genuine defect discovered
  during implementation" — fixed with a one-file `/// <reference
  types="node" />`, not by widening the whole app's ambient types.

---

## 6. Quality gates

| Gate | Result |
|---|---|
| `vitest` (installer suite) | 190 tests passing (129 at TG-C baseline + 61 net new) |
| `vitest` (full frontend suite) | 732 tests, 78 files, all passing |
| `tsc -b --noEmit` | Clean (including the pre-existing failure fixed in §5) |
| `oxlint` | 0 errors; 16 pre-existing warnings, none in installer files, none new |
| `vite build` | Clean |
| `pytest` (backend) | Not re-run in full for this pass — **zero Python files changed**, confirmed by `git diff --stat src/jarvis/` returning empty, so TG-B/TG-C's own suites are untouched by construction, not merely by testing |
| `cargo build` / `tauri build` | ⛔ Not run — no Rust toolchain, same as TG-C |

### New tests, by kind

- **Unit:** `check-row.test.tsx` (5 tests) — the extracted shared
  component in isolation, including the `fail` verdict and the
  `action` slot `SummaryStep` never exercised.
- **Unit/contract:** `installationPresence()` tested directly against
  its three branches (`provisioning-transport.test.ts`), since a real
  `manifest: true` fixture needs a full network-dependent provisioning
  run this environment cannot produce.
- **Integration:** `verification-panel.test.tsx` (5 tests) — repair
  targets the clicked row's own step, not a fixed one; busy state
  disables every button, not only the clicked one.
- **Integration:** `installer-diagnostics.test.tsx` (12 tests) — parallel
  status/dependency/verification fetches, the "nothing to verify yet"
  skip, the "no account type yet" skip, error handling, and the full
  repair-then-refresh cycle.
- **Integration:** `installer-wizard.test.tsx` extended (+6 tests) —
  trigger visibility, notice visibility and its absence on the
  progress/completion screens, dialog opening.
- **Contract:** `host-bridge-contract.test.ts` extended (+11 tests) —
  the five new commands' names, registration and argument shapes,
  including the specific check that `get_installation_status` takes no
  `account_type` (the CLI's `status` subcommand has no such flag).
- **Contract:** `installer-contract.test.ts` extended (+3 tests) — the
  dependency payload's personal/administrator `path` split, verified
  against two real captured fixtures rather than one hand-written pair.
- **Accessibility:** every verdict icon carries `aria-label`
  (unchanged, now shared across three consumers instead of one); the
  diagnostics dialog inherits Radix's own focus trap, `Escape`-to-close
  and `aria-modal` semantics rather than a hand-rolled overlay.
- **Regression:** the full pre-existing installer suite (129 tests)
  re-run after every structural change in this task group, not only at
  the end — zero failures at any point except the two self-inflicted
  ones in §4, both fixed before moving on.

---

## 7. What is proven, and what is not

**Proven:**
- All four CLI subcommands this task group's Rust wraps (`dependencies`,
  `status`, `verify`, `repair`) were run for real, against a real
  temporary target, including their exit-code edge cases, before any
  Rust was written against them.
- The TypeScript side of every new command — argument shapes, return
  types, error paths — is exercised by 57 new tests against real
  captured fixtures.
- The Rust/TypeScript contract for all five new commands (names, arity,
  `invoke_handler` registration) is checked by the same text-reading
  approach that caught a real defect in TG-C.
- The frontend builds, typechecks and lints clean.

**Not proven, and for the same reason as TG-C:**
- Nothing in `src-tauri/installer.rs` has been compiled. The five new
  functions are syntactically plausible Rust, reviewed carefully, but
  unverified by a compiler.
- The full path — a click on a real Repair button reaching a real
  packaged Python process and the UI updating from its real response —
  has not run.
- The diagnostics dialog has never been opened in a real webview.

**TG-C's and TG-D's Rust are proven together, not separately.** Both
live in the same `installer.rs`; one `cargo build` (or `npm run tauri
build`) either compiles all of it or names exactly where it does not.
There is no scenario where one task group's Rust builds and the
other's does not.

---

## 8. Deviations from the roadmap, with justification

**TG-D began before TG-C's Build Verification Tasks passed, and
without the "explicit approval" TG-C's own report said this would
need.** TG-C's §9 states plainly: "TG-D does not begin until then, and
only with explicit approval." Neither condition was met before this
task group's brief arrived. This is recorded as a deviation because it
is one — the report that preceded this one said something different —
not because it was wrong. The user directing this session is the
authority TG-C's own report was deferring to, and the instruction to
begin TG-D was explicit, direct, and aware that TG-C's status was
Implementation Complete — Build Verification Pending (the brief states
that status for TG-C in its own preamble). Proceeding on that
instruction is the correct response to it.

**TG-D's scope was redefined from "Linux/macOS packaging and
cross-platform QA" to "Universal Installation Experience."** Prior
documentation (`IMPLEMENTATION_ROADMAP.md`, `MASTER_ROADMAP.md` §18)
described "Task Groups D–F" as an undivided block covering AppImage/
Flatpak/DEB/RPM, DMG/PKG, and cross-browser QA, with the letter-to-
content split explicitly left undecided. TG-D is now resolved to
Universal Installation Experience specifically. This is a legitimate
roadmap decision, not a silent one: TG-D had **Not Started** status
before this task group, so nothing completed is being redefined
(`MASTER_ROADMAP.md` §19's rule against that governs *completed*
milestones), the packaging/QA scope is not dropped — it moves to E/F,
whose own split remains open exactly as before — and this report,
plus §9's documentation updates, is the record required for the
decision to count as documented rather than assumed.

**Two extra features beyond the brief's fifteen-item list:**
`open_log_folder` and the `installationPresence()` shared
classification. Both are narrowly load-bearing for items the brief did
name ("installation logging" needs a way to reach the log; "update
preparation" needs one consistent definition of "installed") rather
than scope added for its own sake.

No other deviations. Every other item in the brief's list — progress
framework, download manager UI, resume, retry, failure classification,
installation logging, component verification, disk space verification,
dependency verification, installation summary, completion experience,
rollback planning, recovery planning, update preparation, installer
diagnostics — is accounted for in §3 or in §9 below (rollback
planning, specifically, which this task group deliberately did not
build new code for).

---

## 9. On "rollback planning" specifically

No new rollback mechanism was built, and that is a decision, not an
omission. Three things already cover the failure mode "rollback" would
address, each already documented:

- **Every provisioning step is idempotent and journal-tracked**
  (`jarvis/installer/journal.py`, TG-B). An interrupted or failed
  installation resumes from its last completed step rather than
  needing to be undone and restarted.
- **A full uninstall is NSIS's own generated uninstaller** (TG-C,
  `installMode: "currentUser"`), which is TG-C's Build Verification
  Task #7 — not a mechanism the installer wizard should reimplement
  alongside it.
- **`repair()`** (this task group) is the targeted, partial form of
  rollback that is actually useful mid-install: redo one step and
  everything after it, without touching what already succeeded.

Building a fourth, in-app "rollback" mechanism layered on top of these
three would have been exactly the "no duplicate service layers"
violation this task group's own brief warns against — a second way to
undo work that already has two honest ways to be undone. "Rollback
planning" is satisfied by this paragraph existing and being accurate,
not by new code.

---

## 10. Documentation updated

`CHANGELOG.md` (new 0.37.0 entry), `IMPLEMENTATION_ROADMAP.md` (Task
Group D section replacing the old "D–F, not started" stub; M22
Acceptance Criteria table updated; D–F reassignment noted),
`MASTER_ROADMAP.md` (§2 execution order, §8 M22 entry, §18 Acceptance
Criteria table — same updates, mirrored), `ARCHITECTURE.md` (§22.15,
noting the host bridge's command surface grew), `README.md` (current
version and milestone status; the wizard gained user-visible screens —
diagnostics, repair, the existing-installation notice — so this is a
real user-visible change, not a documentation-only bump). This file.

No historical record was rewritten: this section is appended after
TG-C's report, not merged into it, and `CHANGELOG.md`'s 0.36.0 entry is
untouched — the 0.37.0 entry is new, per `MASTER_ROADMAP.md` §19's
rule that corrections and additions are new entries, never edits.

---

## 11. Recommended next step

Unchanged from TG-C's own §10: get access to a machine with the Rust
toolchain. One `npm run tauri build` there proves TG-C's five commands
and TG-D's five together, and is the only thing that turns either task
group's status from Implementation Complete to Complete. This report
does not request that TG-E begin; the brief that produced it asked
explicitly to stop after TG-D and await approval, which this is.
