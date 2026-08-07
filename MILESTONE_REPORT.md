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

---
---

# Milestone Report — M22 Task Group E: Windows Packaging & Installer Distribution

**Version:** 0.38.0
**Branch:** `feature/m22-task-group-c`
**Baseline:** v0.37.0 (TG-D, Implementation Complete — Build Verification Pending)
**Date:** 2026-08-07

> **A third, separate report appended to the same file.** Nothing above
> this divider was edited — TG-C's and TG-D's reports, including TG-C's
> own still-unrun Build Verification Tasks table, stand exactly as
> written. TG-E's own report follows, with its own §1 onward.

## 1. Executive summary

The brief listed nineteen items under "Windows Packaging & Installer
Distribution." An audit before writing anything found most of them
already real: NSIS configuration, the installer/uninstaller/Add-Remove-
Programs machinery, version metadata, installation logging, launch-
after-install and open-installation-folder are all Task Group C/D
capability, not gaps. What was genuinely missing was narrower and more
consequential than any single checklist item — **every icon in this
project was still Tauri's own placeholder logo**, a fact Task Group C's
own report had already found and flagged as unstarted work.

That gap became directly actionable mid-task-group: the user supplied
and approved the official JARVIS master logo (a commissioned image,
provided as a chat attachment) partway through this task group's work.
This report covers both halves honestly — the packaging-config audit
that came first, and the branding integration that followed once a
real asset existed to integrate.

**Status: Implementation Complete — Build Verification Pending**, the
same status TG-C and TG-D carry, for the same reason: this task group
touched no `src-tauri/` Rust logic, but the icon files it replaced are
part of what a real `tauri build` packages, so it inherits the same
unverified-without-a-toolchain gate.

---

## 2. Status of M22

| Task group | Status |
|---|---|
| **A — Universal Installer Foundation** | ✅ Complete (v0.33.0) |
| **B — Runtime Provisioning** | ✅ Complete (v0.34.0) |
| **Installer UI integration** | ✅ Complete (v0.35.0) |
| **C — Windows Packaging & Host Bridge** | 🟡 Implementation Complete — Build Verification Pending (v0.36.0) |
| **D — Universal Installation Experience** | 🟡 Implementation Complete — Build Verification Pending (v0.37.0) |
| **E — Windows Packaging & Installer Distribution** | 🟡 **Implementation Complete — Build Verification Pending** (v0.38.0, this report) |
| **F** | ⬜ Not started; absorbs the Linux/macOS packaging and cross-platform QA scope previously split between E/F — see §9 |

TG-A through TG-D are unmodified by this work: `git diff --stat
src/jarvis/` is empty (zero Python files touched, same as TG-D), and no
existing Rust command, transport function, or React component's
behavior changed — only icon *content* and one animated component's
internals changed, both additive/replacement, not behavioral edits to
anything TG-C/D built.

---

## 3. Audit findings

Performed before any code changed, per this task group's own brief:

- **Rust toolchain:** confirmed absent, fresh (not assumed from
  memory) — `cargo`, `rustc`, `rustup`, and `~/.cargo` all checked
  directly and found missing.
- **TG-D implementation:** verified intact against its own
  documentation — all 5 Rust commands present and registered in
  `lib.rs`, all frontend files present, transport wired, matching
  `MILESTONE_REPORT.md`'s own TG-D entry exactly.
- **Quality gates, fresh:** tsc clean, oxlint 0 errors, 736/736 vitest
  passing, build clean, before this task group's first edit.
- **One false alarm, resolved by checking rather than assuming:** the
  scratchpad directory contained files named with a "tgf"/"tge"
  pattern. `git log --all --oneline` across every branch confirmed
  these were unrelated leftovers from M11 Task Group F (v0.28.0, a
  different, already-merged milestone earlier in this session) — not
  evidence of undocumented M22 work.
- **TG-E's nineteen-item brief cross-referenced against reality:** see
  §4 for what was already built vs. genuinely missing.
- **Real JARVIS branding assets, searched for before assuming none
  existed:** found `components/startup/jarvis-logo.tsx`, an original
  (if simple) animated emblem, not Tauri's placeholder — this became
  the starting point for the icon work before the master logo arrived
  and superseded it.
- **`npx tauri icon` (the CLI's own icon-generation subcommand),
  tested rather than assumed to work:** confirmed functional in this
  environment (no native dependencies missing), and confirmed *how*
  it behaves — accepts SVG or PNG input, defaults to generating a
  broader cross-platform set (including iOS/Android artifacts this
  project does not target) unless custom sizes are requested.

---

## 4. The nineteen-item brief against reality

| Item | Status before this task group | What this task group did |
|---|---|---|
| Windows installer generation | Config exists (TG-C) | Unchanged; gated on Build Verification |
| NSIS configuration | Complete (TG-C) | Unchanged |
| Installer branding | **Unstarted** — TG-C's own flagged gap | **Built** — see §5 |
| Installer icon | Tauri placeholder | **Replaced** |
| Application icon | Tauri placeholder | **Replaced** |
| File associations | N/A | Evaluated, confirmed not applicable — no custom file format exists |
| Start Menu shortcut | Relies on NSIS default template (TG-C) | Unchanged; still gated on a real build to observe |
| Desktop shortcut | Same | Unchanged |
| Uninstaller | NSIS auto-generates (TG-C) | Unchanged |
| Add/Remove Programs | Automatic via NSIS + TG-C metadata | Unchanged |
| Installer metadata | Set (TG-C) | Unchanged |
| Product information | Set (TG-C) | Unchanged |
| Version metadata | Enforced by `test_version_consistency.py` | Unchanged; version bumped to 0.38.0 per the established per-task-group precedent |
| Upgrade path | `allowDowngrades: false` + fixed identifier (TG-C) | Unchanged; NSIS's own in-place-upgrade default, not additional config |
| Silent installation support | NSIS's own `/S` flag, no config surface exists for it | Unchanged; documented, not built, since there is nothing to configure |
| Installation logging | Complete (TG-C logger + TG-D `open_log_folder`) | Unchanged |
| Launch after installation | Complete (TG-C `launch_application`) | Unchanged |
| Open installation folder | Complete (TG-C) | Unchanged |
| Installer verification | TG-C's own 10-item Build Verification Tasks gate | **Extended** with a new mechanical script — see §5 |
| Packaging diagnostics | Nothing existed | **Built** — `verify_tauri_build.ps1`'s pass/fail output |

Fifteen of nineteen items were already real capability inherited from
TG-C/TG-D. Four were genuine gaps, and all four are now closed to the
extent achievable without a Rust toolchain.

---

## 5. What was built

| Piece | File |
|---|---|
| Master logo (source of truth) | `frontend/src-tauri/icons/master-logo.png` |
| Full premium icon set (16–1024px, `.ico`, `.icns`) | `frontend/src-tauri/icons/`, `frontend/public/branding/premium/` |
| Simplified small-icon variant, hand-authored | `frontend/src-tauri/icons/small-icon-source.svg`, `frontend/public/branding/small-icon/` |
| Hybrid multi-resolution `icon.ico` | Built by a one-off Python PNG-in-ICO packer (see §6) |
| Browser favicon, replaced | `frontend/public/favicon.svg` |
| Startup animation, recreated as SVG | `frontend/src/components/startup/jarvis-logo.tsx` |
| Build-verification script | `packaging/verify_tauri_build.ps1` |
| 11 packaging/branding contract tests | `frontend/src/features/installer/__tests__/packaging-contract.test.ts` |
| `jarvis-logo.tsx` test suite, rewritten | `frontend/src/components/startup/__tests__/jarvis-logo.test.tsx` |

### Two variants, not one, and why

The master logo rasterized directly to 32×32 was tested for real and
found near-illegible — a dark, low-contrast blur, confirmed by
rendering and looking at it, not assumed from the artwork's general
busyness. This is the empirical justification for the brief's own
"two official variants" requirement, not just a instruction followed
on faith:

- **Variant A (premium):** the master logo, used as-is, for sizes
  where its metallic gradients and glow read clearly — 128px and
  above, and anywhere in the running app that eventually shows a large
  mark (About, splash, marketing).
- **Variant B (small icon):** a hand-authored, high-contrast
  simplification — flat colours instead of gradients, no blur filter,
  thicker strokes, a darker outer tone chosen so the shape holds up on
  both light and dark Windows themes rather than the master's paler
  mid-tones. Not a vector trace (no tracing tool was available in this
  environment) — a deliberate reinterpretation of the same silhouette,
  verified by rendering it at 16/32/48px and looking at the result
  before finalizing.

### The hybrid `.ico`

`tauri icon` generates a multi-resolution `.ico` from one source image
uniformly — it cannot mix two different source images into one file's
frames. Since Windows reads a single `icon.ico` for the taskbar,
Explorer, and the large-icon view alike, using only Variant A would
make the small frames illegible again, and using only Variant B would
throw away the premium detail everywhere large. Built instead: a small,
self-contained Python script using only the standard library (`struct`)
to hand-write a valid ICONDIR/ICONDIRENTRY header embedding
already-rasterized PNGs directly (PNG-in-ICO, valid since Windows
Vista) — small frames (16/24/32/48) from Variant B, large frames
(128/256) from Variant A. Verified structurally sound by reading the
file back and confirming every directory entry's claimed dimensions
match its embedded PNG's own `IHDR` — not merely "the script ran
without an error."

### The startup animation

`jarvis-logo.tsx` mounts for exactly two of `startup-sequence.tsx`'s
eight already-choreographed phases (~1.3s of a ~4.2s total sequence).
Rather than widen that component's own phase API — which would mean
changing a separate, already-tuned system out of scope for a branding
task group — the richer nine-beat sequence the brief described was
built *inside* the existing `assembling`/`pulsing` window via staggered
Framer Motion animations, using the master logo's own geometry (the
same paths `small-icon-source.svg` uses, so the startup mark and the
taskbar icon are visibly one identity). Every animated property is
`opacity`, a transform, or SVG `pathLength` — never a layout-triggering
property — which is what the brief's "60 FPS, GPU accelerated, no
layout shifts" requirement actually depends on structurally, not
something to assert as true separately from which properties are
touched.

---

## 6. Defects found and fixed

Three, all in code written during this task group, all found by
actually running something rather than by re-reading it.

**A verification heuristic that broke on its own first real input.**
`verify_tauri_build.ps1`'s original icon check asserted "the file is
small enough to be the real icon" (a magnitude heuristic against an
early placeholder size). The moment the real hybrid `.ico` existed —
larger than the Tauri placeholder it replaced, not smaller, because it
now embeds six frames instead of Tauri's own smaller default set — that
heuristic failed against genuinely correct output. Replaced with a
negative match against the placeholder's own exact, fixed byte size
(37,710 bytes), which does not need updating as this project's real
icon content continues to change. The same fix was made in
`packaging-contract.test.ts`, kept deliberately consistent with the
script rather than inventing a second technique for the same question.

**A double hyphen inside an SVG comment, found twice.** Tauri's icon
generator panics on a parse error if an SVG comment contains `--`
anywhere in its body — valid, common Markdown/prose style in this
project's own documentation, invalid XML. First occurrence: the
comment itself, describing the design. Second, more subtle occurrence:
inside a sentence *about* the rule, which quoted the literal
forbidden string while explaining it. Both found by actually running
`npx tauri icon` against the file and reading the panic, not by
proofreading the SVG source and assuming it would parse — confirmed by
also testing an intentionally-reduced isolated case (a comment with no
double hyphen at all) to prove the double hyphen specifically was the
cause before accepting the fix.

**A compounding double-opacity animation.** `jarvis-logo.tsx`'s first
draft had a parent `motion.g` and its child `motion.path` elements each
independently animate their own `opacity` toward 1. Opacity composes
multiplicatively down the DOM, not additively, so this produced a
slower, muddier fade than either animation alone intended — a real
defect, though a subtle one that live visual inspection might well have
missed even with a working browser compositor (see §7). Found on a
careful manual re-read of the component specifically prompted by not
being able to verify it visually; fixed by leaving opacity entirely to
the children's own draw-on animation and having the group own only the
shared upward translate.

---

## 7. What is proven, and what is not

**Proven:**
- `npx tauri icon` runs successfully in this environment and produces
  the documented output for both SVG and PNG input.
- The generated icon files are structurally valid: `icon.ico`'s own
  ICONDIR header, directory entries, and embedded PNG payloads were
  read back and cross-checked against each other, not just assumed
  correct because the packer script exited 0.
- The master logo rasterized at 32×32 is genuinely close to illegible
  — confirmed by rendering and inspecting it, which is *why* Variant B
  exists rather than being a precaution taken on faith.
- Variant B is legible at 16, 32, and 48px — confirmed the same way.
- `jarvis-logo.tsx` mounts with the correct DOM structure (5 paths, 2
  groups, 1–3 circles depending on phase) in a real, running dev
  server — confirmed via direct DOM inspection through the browser
  tooling.
- Framer Motion correctly recognizes and initializes every animated
  SVG element, including setting `transform-box: fill-box` and
  `transform-origin: 50% 50%` automatically for the `motion.g`
  elements — confirmed by reading the actual inline styles the library
  applied, not assumed from documentation.
- Zero console errors or warnings across several real mounts of the
  full startup sequence.
- `verify_tauri_build.ps1` runs correctly against this project's real,
  current, unbuilt state: correctly fails the one check that should
  fail (no installer produced yet) and passes every check that does
  not depend on a build existing, including the icon check against the
  real generated file.
- Zero Python files changed; the full backend version-consistency
  suite passes.
- 750 frontend tests pass (up from 736 at this task group's start),
  tsc clean, oxlint 0 new errors, production build clean, and
  `public/branding/` assets confirmed present in the actual `dist/`
  output.

**Not proven, honestly:**
- **The startup animation's actual visual motion was never observed.**
  This is the significant gap in this task group's verification, and
  it is a genuine one, not a formality. The sandboxed Browser pane
  available in this session does not composite frames at all —
  confirmed directly, not inferred: a bare `requestAnimationFrame`
  loop was run in that tab and never fired within a full second.
  `computer.screenshot` failing independent of timing (even against
  already-loaded, static content) is the same root cause. Since Framer
  Motion's engine is itself driven by `requestAnimationFrame`, nothing
  animates in that pane regardless of which component is involved —
  this is a property of the tooling in this session, not evidence
  specific to `jarvis-logo.tsx`. What stands in its place: correct
  structure, correct Framer Motion initialization, zero errors across
  real mounts, and a careful manual review that *did* find and fix a
  real bug (§6's compounding-opacity defect) without ever seeing a
  frame render. The choreography's actual feel — timing, overlap,
  whether the "breathing" reads as breathing rather than a flicker —
  needs a real compositor to judge, and should be watched once one is
  available, before calling this piece finished rather than merely
  built.
- **Nothing in `src-tauri/` has been compiled**, same gate as TG-C and
  TG-D. The icon files are real inputs to a real build that has not
  run.
- **Desktop/Start Menu shortcuts, the uninstaller, and Add/Remove
  Programs** were not newly verified here — they remain exactly where
  TG-C's own Build Verification Tasks table left them.

---

## 8. Architecture decisions

- **Two icon variants, not one, with a hand-written hybrid `.ico`
  rather than picking a single compromise size/style.** Reasoned
  through in §5; the alternative (one icon, one size class) would have
  meant either an illegible taskbar icon or a premium mark nobody ever
  sees at its intended size.
- **`jarvis-logo.tsx`'s phase API left unchanged.** The richer
  animation was built to fit the existing `assembling`/`pulsing`
  window rather than widening `startup-sequence.tsx`'s own
  choreography — see §5. This is the same "do not change architecture
  without justification" discipline applied to a component boundary,
  not just to backend services.
- **Branding assets split by role, not merged into one folder.**
  `src-tauri/icons/` holds build *inputs* (what `tauri icon` and the
  bundle config consume); `public/branding/` holds runtime-servable
  *outputs* (what a future React component would `<img src>`). The
  master logo and small-icon source exist in both roles deliberately —
  same file, two purposes — documented in each location's own comments
  rather than left to look like accidental duplication.
- **No new UI surfaces invented.** About Window, Settings branding,
  Notifications branding, Navigation branding, and an Update Dialog
  were all searched for and confirmed absent from this codebase before
  concluding there was nothing to update there. Building any of them
  now, solely to give the new logo a home, would have been exactly the
  roadmap expansion this project's own governance rules (`ARCHITECTURE
  .md` §24, principle #2) exist to prevent.

---

## 9. Deviations from the roadmap, with justification

**TG-E's scope was redefined from an undivided "Linux/macOS packaging
and QA" placeholder (shared, split undecided, with TG-F) to Windows
Packaging & Installer Distribution specifically.** TG-E had **Not
Started** status beforehand, so nothing completed is being redefined
(`MASTER_ROADMAP.md` §19's rule governs *completed* milestones). The
displaced scope is not dropped — it moves entirely to Task Group F,
which now absorbs what would previously have been split between the
two letters.

**Branding integration reached slightly beyond a strict reading of
"installer distribution."** The startup animation and the browser
favicon are general application branding, not installer-specific
surfaces. Both were done on direct, explicit instruction, and both
serve the same underlying identity the installer icon does — the
judgment call was to treat "no placeholder logos remain anywhere in
the project" as the operative instruction once the master logo
existed, rather than drawing an artificial line at the installer's own
boundary. Settings/Notifications/About/Navigation were *not* extended
to, per §8, because nothing there exists yet to extend to.

**File associations were evaluated as out of scope for a different
reason: not applicable, not merely deferred.** JARVIS OS has no custom
file format (searched for directly — no `.jarvis`-extension project
file, no custom document type anywhere in the codebase). The brief's
own "(if applicable)" qualifier covers this; nothing was built, and
nothing should be.

---

## 10. Documentation updated

`CHANGELOG.md` (new 0.38.0 entry), `IMPLEMENTATION_ROADMAP.md` (Task
Group E section, Acceptance Criteria table, Task Group F scope note),
`MASTER_ROADMAP.md` (§2 execution order, §8 M22 entry, §18 Acceptance
Criteria — same updates, mirrored), `README.md` (current version and
milestone status; the running app's own visible identity changed, so
this is a real user-visible update, not paperwork), `ARCHITECTURE.md`
(a short §22.15 note on the icon-variant/hybrid-ICO pattern, since a
future platform's own icon work will hit the same small-size
legibility problem). This file.

No historical record was rewritten: this section is appended after
TG-D's report, not merged into it; TG-C's and TG-D's reports are
untouched above the divider; `CHANGELOG.md`'s 0.36.0 and 0.37.0
entries are untouched — 0.38.0 is a new entry, per `MASTER_ROADMAP.md`
§19.

---

## 11. Remaining work for TG-E

- **Watch the startup animation in a real, compositing browser** once
  one is available in this session or a future one, and confirm the
  choreography actually reads as intended — see §7's honest account of
  why this could not be done here.
- Everything TG-C's own Build Verification Tasks table already lists
  remains open, now additionally covering whether the new icon
  actually renders correctly once embedded in a real build (shortcuts,
  taskbar, Explorer, Add/Remove Programs).

## 12. Recommended next step

Same as TG-C's and TG-D's: get access to a machine with the Rust
toolchain. `npm run tauri build` there proves all three task groups'
`src-tauri/` content at once, including whether the new icon actually
looks right once Windows is the one rendering it rather than a PNG
viewer. This report does not request that TG-F begin; the brief that
produced it asked explicitly to stop after TG-E and await approval,
which this is.

---
---

# Milestone Report — M22 Task Group F: Final Build Verification, Cross-Platform Readiness & Release Validation

**Version:** 0.38.0 (unchanged — see §1)
**Branch:** `feature/m22-task-group-c`
**Baseline:** v0.38.0 (TG-E, Implementation Complete — Build Verification Pending)
**Date:** 2026-08-07

> **A fourth report, appended to the same file.** Nothing above this
> divider was edited — TG-C's, TG-D's and TG-E's reports stand exactly
> as written. TG-F's own report follows, with its own §1 onward.

## 1. Executive summary

TG-F's brief was explicit about what it is and is not: verification,
validation and release readiness, not new features, and — separately
— an audit of cross-platform readiness without implementing Linux or
macOS. Both halves were done for real. The verification half split
cleanly into two kinds of evidence: things provable without a Rust
toolchain (the Python provisioning engine, run for real against a
scratch install target — fresh install, resume, a deliberately induced
failure, repair, re-verification) and things that are not (everything
downstream of `tauri build`, which still has not run on this machine,
same root cause as TG-C, TG-D and TG-E). The cross-platform half
produced a genuine, evidence-based migration checklist in
`docs/PACKAGING.md`, built by reading every `#[cfg(windows)]`, `wmic`
call and Windows-only path assumption in the codebase, not by
guessing what a new platform would typically need.

One genuine defect was found and fixed: `docs/PACKAGING.md` still
described Task Group E's own icon work as unstarted — a documentation
regression from the fact that Task Group E's own documentation pass
did not touch this file. No application code defect was found. **No
version bump** — consistent with this project's own established rule
that a documentation/verification pass with no shipped application
change does not bump the version (the same call `11a8f6f`'s governance
pass made).

**Status: Implementation Complete — Build Verification Pending.** TG-F
is, by its own brief, the task group whose job is closing M22's
build-verification gate — and it cannot close what it cannot run. Every
item that needs a compiled `.exe` remains exactly where TG-C left it.
What TG-F adds is real evidence for everything that *doesn't* need one,
and an honest, itemized account of what still does.

---

## 2. Audit findings

Fresh, not reused from TG-E's own audit:

- **Rust toolchain:** still absent — `cargo`, `rustc`, `rustup`,
  `~/.cargo` all re-checked and still missing.
- **TG-E's own deliverables:** every icon file TG-E's report claims to
  exist was re-checked on disk (`master-logo.png`, `small-icon-
  source.svg`, `icon.ico` at its reported 60,057 bytes, the four new
  small PNG sizes) — all present, all matching.
- **Version consistency:** `pyproject.toml`, `src/jarvis/__version__.py`
  and `tauri.conf.json` all independently re-read — all `0.38.0`,
  agreeing with each other and with `test_version_consistency.py`.
- **`docs/PACKAGING.md` found stale** (§4 below) — the one genuine
  defect this task group found, by reading the file rather than
  trusting its own table of contents.
- **The legacy PyInstaller/Inno Setup packaging path**
  (`packaging/jarvis.spec`, `packaging/jarvis_installer.iss`,
  `packaging/build_windows.ps1`) confirmed still correctly labeled
  superseded in `PACKAGING.md`'s own header — not a second live
  packaging system to reconcile with the Tauri one, and not touched.
- **No `frontend/src-tauri/Cargo.lock`** — does not exist anywhere in
  the repository, because `cargo` has never run against it. A real
  build-reproducibility gap, not fixable without the toolchain this
  environment lacks; recorded as a new Build Verification Task rather
  than silently noted and dropped.

---

## 3. Verification summary

### What a Rust toolchain gates (not performed, honestly)

Windows installer verification, NSIS verification (beyond static
config parsing, already done in TG-C), desktop/Start Menu shortcut
verification, Add/Remove Programs verification, icon-as-rendered-by-
Windows verification, uninstall verification, launch-after-install
against a real packaged `.exe`, open-installation-folder against a
real install, and the provisioning bridge end to end inside a packaged
webview. All twelve items in `docs/PACKAGING.md`'s Build Verification
Tasks list (ten from TG-C, two added by this task group — see §4 of
that document) remain unchecked. Fresh installation and upgrade
installation *as NSIS itself performs them* are in this category too
— `allowDowngrades: false` and the fixed `identifier` are config
this environment can read but not exercise.

### What was actually run, for real, in this environment

The Python provisioning engine (`python -m jarvis.installer`) needs no
Rust toolchain — it is what the eventual Rust bridge spawns, but it
runs standalone identically either way. Rather than trust TG-B's and
TG-D's own unit tests a second time, this task group exercised it
directly against a scratch target directory it created and destroyed
for this purpose:

- **Fresh installation:** `provision --target <scratch> --account-type
  personal` on an empty directory genuinely created `data/`, `models/`,
  `voice/`, `logs/`, `cache/`, `config/` on disk, wrote a real
  `jarvis.config.json`, and completed the `dependencies`,
  `directories` and `configuration` steps for real (each entry in the
  resulting journal carries this machine's actual detected Python,
  Git, DirectML and CUDA state). It then failed at `model_download`
  with `"1 download(s) did not complete"` — expected and by design:
  TG-B's source registry ships empty (§4 "No hardcoded URLs"), so a
  real download was never going to succeed in this environment, and
  the engine correctly reported that as a real failure rather than
  papering over it.
- **Existing installation detection:** `status` against that same
  target reported `is_resume: true`, `completed: [dependencies,
  directories, configuration]`, `manifest: false` — exactly the shape
  `provisioning-types.ts`'s `installationPresence()` reads (`manifest`
  → complete, non-empty `journal.completed` → partial, neither →
  none). Read side-by-side, the real CLI's field names and the
  frontend's classification function agree exactly; this was not
  assumed from both having been written once, it was checked against
  a real payload.
- **Resume installation:** re-running the identical `provision`
  command against the same target reported `resumed: true` and
  `skipped_steps: [dependencies, directories, configuration]` — the
  three already-done steps were not redone, only `model_download` was
  attempted again (and failed the same, expected way).
- **Interrupted installation recovery:** the journal file
  (`config/provisioning.journal.json`) was deliberately truncated
  mid-object to simulate a crash during the durable write it is
  designed to survive. `status` against the corrupted file reported a
  clean, fresh-install state (`is_resume: false`, nothing completed) —
  read as a possible defect at first, then traced to
  `journal.py`'s own `_load()`, whose docstring already reasons through
  exactly this case: *"A journal truncated by the very crash it
  records is unreadable, not authoritative. Starting over is correct;
  every step is idempotent."* This is confirmed-correct, deliberate
  behavior, not a defect — restoring the journal from a backup taken
  before the corruption immediately returned `status` to reporting the
  real partial progress, proving nothing was actually lost on disk,
  only the journal's own record of it was transiently unreadable.
- **Repair workflow and verification workflow, together:** the real
  `config/jarvis.config.json` written by the fresh install above was
  deleted outright. `verify` correctly reported `"configuration":
  {"verdict": "fail", "repairable": true, "repair_step":
  "configuration"}` (exit code 2, the documented "real finding"
  convention `installer.rs`'s own `run_json_command` already relies
  on). `repair configuration` against the same target recreated the
  file for real; a second `verify` immediately after reported
  `"configuration": {"verdict": "pass", "detail": "Valid."}` — repair
  re-verifying after acting, not trusting its own success, exactly as
  TG-D's report described and as tested here against a real induced
  failure rather than only a mocked one.
- **Dependency verification:** `dependencies --account-type personal`
  returned this machine's real, live-probed dependency report (Python
  3.13.14, Git 2.55.0, DirectML present, CUDA missing — "No NVIDIA
  driver detected. JARVIS will run on the processor") — not a fixture.
- **Installer diagnostics verification:** the diagnostics dialog's
  underlying data sources (`dependencies`, `status`, `verify`) were
  each independently confirmed correct above; what remains unverified
  is only the Rust bridge's relay of that same data into the dialog,
  which needs the same toolchain everything else in this section does.

Upgrade installation specifically — a second `provision` run against
an already-*complete* installation (one that reached the `manifest`
step) — could not be exercised even at the CLI level: reaching a
complete installation requires a real model download to succeed, which
this environment's empty source registry makes structurally
impossible here, by the same design TG-B documented rather than a gap
this task group introduced.

---

## 4. Defects discovered

One, in documentation, not application code.

**`docs/PACKAGING.md` claimed Task Group E's icon work was unstarted,
after Task Group E had shipped it.** The "Current: Tauri + NSIS"
section's icon paragraph and Build Verification Task 5 both still read
as TG-C originally wrote them — "Icons are wired but are still Tauri's
defaults... Replacing the set requires real artwork" — a claim that
was true when TG-C wrote it and false by the time this task group
read it, because TG-E's own documentation pass updated
`MILESTONE_REPORT.md`, `CHANGELOG.md`, both roadmap files, `README.md`
and `ARCHITECTURE.md` but not `PACKAGING.md`, which was outside its
own stated sync list. Found by reading the file directly as part of
this task group's audit, not flagged by any test — `PACKAGING.md` is
prose, not something a test suite checks against the repo's real
state.

---

## 5. Defects fixed

The one above. `docs/PACKAGING.md`'s icon paragraph now describes the
real, current two-variant/hybrid-ICO state and cites TG-E's own report
and `ARCHITECTURE.md` §22.15; Build Verification Task 5 is now struck
through and marked done, with a note that what remains under items 3,
4 and 6 is *observing* the real branding render correctly in a build,
not the branding work itself. Verified by re-reading the corrected
section against `MILESTONE_REPORT.md`'s TG-E entry and the real files
on disk, the same way the original staleness was found.

No code defect was found in TG-A through TG-E during this pass. The
journal-corruption behavior investigated in §3 was a candidate and was
ruled out as intentional, documented, verified-correct design, not a
defect — recorded here so the investigation itself is not lost, even
though it did not conclude with a fix.

---

## 6. Quality gate results

Run fresh, not reused from TG-E's own run:

- **Backend:** `pytest tests/` — full suite, run twice (once with this
  project's default coverage reporting, once without, to get a clean
  pass/fail summary past the coverage table); both runs exit 0, no
  failures, one pre-existing skip (`test_file_domain.py`'s symlink
  case, which this platform does not permit). ~78% overall coverage,
  unchanged in character from prior task groups' runs.
- **Frontend:** `tsc --noEmit` clean; `oxlint` — zero errors (the same
  pre-existing Fast-Refresh-only warnings TG-E's own run reported,
  none new); `vitest run` — **750 of 750 passing**, unchanged count
  from TG-E, confirming this task group's one documentation edit
  introduced no regression; `npm run build` — clean, `dist/branding/`
  confirmed present in the output.
- **Version consistency:** re-confirmed by direct read (§2), not only
  by the test that enforces it.

---

## 7. Platform readiness

Full detail, including the concrete migration checklist, now lives in
`docs/PACKAGING.md`'s new "Cross-platform readiness" section — kept
there rather than duplicated here, since that document is what a
future Linux/macOS task group will actually open. Summary:

**Already generalises:** a real `PlatformInfo` OS-detection module
(`src/jarvis/infrastructure/platform/platform_detector.py`) is used
consistently across hardware and dependency detection, with every
Windows-only probe degrading to an honest, documented fallback on
other platforms rather than failing or lying. The provisioning
engine's eight steps are plain, OS-agnostic `pathlib` Python. The
frontend's installer copy is already platform-neutral. The Tauri
command contract is deliberately argument-free specifically so a
platform difference does not have to grow into it.

**Genuinely Windows-only today**, each found by reading the real
source rather than assumed: `find_python()`'s `.venv/Scripts/
python.exe` search path; `launch_application()`'s hardcoded `"JARVIS
OS.exe"`; `open_installation_folder()` / `open_log_folder()`'s
`explorer`-only implementation (already structured as an honest
"unsupported on this platform" stub elsewhere, which is the right
shape to extend rather than redesign); GPU/NPU detection's `wmic`
fallback with no Linux/macOS equivalent; `tauri.conf.json`'s
`nsis`-only bundle target.

**Nothing here was implemented** — TG-F's own brief was explicit that
this is an audit-and-document pass, not a Linux/macOS build.

---

## 8. Documentation updated

`docs/PACKAGING.md` (the stale-icon-paragraph fix, the Build
Verification Tasks list extended to twelve items, and the new
Cross-platform readiness section with its migration checklist),
`CHANGELOG.md` (new entry, no version bump — see §1), this file.
`IMPLEMENTATION_ROADMAP.md` and `MASTER_ROADMAP.md` updated to record
TG-F's own status and the real verification evidence from §3.
`README.md` not changed — no user-visible behavior changed this pass.
`ARCHITECTURE.md` not changed — no architecture decision changed;
§22.15 already carries the icon-variant pattern this task group's
checklist points back to rather than repeating.

No historical record was rewritten: this section is appended after
TG-E's, not merged into it; TG-C's, TG-D's and TG-E's reports are
untouched above the divider; `CHANGELOG.md`'s 0.36.0, 0.37.0 and 0.38.0
entries are untouched.

---

## 9. Remaining risks

- **Everything gated on the Rust toolchain remains gated.** This is
  not a new risk TG-F introduced; it is the same one TG-C named first,
  now inherited by four task groups at once, all provable together by
  one real build.
- **`Cargo.lock` does not exist.** The first real build will generate
  it; it should be committed at that point, not left generated-but-
  ignored, so the exact dependency set a release was built against is
  reproducible afterward.
- **Upgrade installation specifically cannot be exercised even at the
  CLI level** in this environment, because reaching a *complete*
  installation to upgrade over requires a real model download, and
  this environment's download-source registry ships empty by design.
  This is a narrower, more specific gap than "no Rust toolchain" and
  is worth naming on its own so it is not assumed closed once a
  toolchain is eventually available — a real source will also need to
  be configured before this specific scenario is provable.
- **Accessibility verification remains static.** Role/`aria-*`-based
  test coverage exists and passes (44 assertions across five installer
  test files, confirmed in this task group's fresh run), but no
  automated contrast or axe-based scan tool exists in this project,
  and no screen-reader pass has been performed — both remain open,
  unchanged from what TG-C/D/E's own reports already said.
- **Runtime performance and memory cannot be measured** without a
  compiled, running, packaged application — the production bundle's
  static composition was reviewed (code-split, ~3.5 MB total `dist/`,
  dominated by one variable-weight font file) but this is not a
  substitute for measuring a real running process.

---

## 10. Recommendation: can M22 be marked Complete?

**No.** Per `MASTER_ROADMAP.md` §18's own Acceptance Criteria, M22 is
Complete only when TG-A and TG-B read Complete (they do) *and* TG-C,
TG-D, TG-E and TG-F each read Build Verification Passed — meaning
every row in the (now twelve-item) Build Verification Tasks table is
checked, not merely that each task group's implementation checklist
is. None of the twelve is checked. This is not a new blocker this
task group introduced; it is the same one TG-C named in the first
report this milestone produced, now confirmed to still be the single
blocking factor across all four Windows-packaging task groups at once
— nothing found during this pass changed that, and nothing found
during this pass was a substitute for it.

**What TG-F adds to the case for Complete, once a toolchain exists:**
real, run-for-real evidence that the Python provisioning engine
itself — the part every Rust command in `installer.rs` is a thin
wrapper around — behaves exactly as documented under fresh install,
resume, corruption-recovery, repair and re-verification, on this
actual machine, today. What remains is proving the Rust layer around
it faithfully relays that same behavior into a real packaged
application, which was true before this task group and remains true
after it.

This report does not request that M23 begin, and TG-F's own brief
asked explicitly to stop after it and await approval, which this is.
