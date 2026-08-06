# Milestone Report — M22: Installer UI & Provisioning Integration

**Version:** 0.35.0
**Branch:** `feature/m22-installer-ui`
**Baseline:** v0.34.0 (`424a1ef`, M22 Task Group B)
**Date:** 2026-08-06

> **Correction to the previous report.** v0.34.0's report stated *"No
> installer UI changes. TG-A's wizard is unchanged; wiring its Install
> step to this engine needs the Tauri command bridge, which belongs with
> packaging in TG-C."* That was true when written and is now wrong in
> its second half: the wiring shipped here **without** the Tauri bridge,
> because the wizard reaches the engine through an injected transport.
> Only the transport's *host implementation* waits on packaging. The
> CHANGELOG's 0.34.0 entry carries the same correction.

---

## 1. Executive summary

The installer wizard now runs a real installation. Progress, per-item
download state, resume, failure recovery and completion all render from
the provisioning engine's own events, and `/install` is reachable for
the first time.

**The engine is unchanged.** pytest, black, ruff and mypy are identical
to v0.34.0, and TG-B's 30 engine tests pass untouched. What changed on
the Python side is three *additive* integration hooks that leave existing
behaviour byte-identical.

---

## 2. Status of M22

| Task group | Status |
|---|---|
| **A — Universal Installer Foundation** | ✅ Complete (v0.33.0) |
| **B — Runtime Provisioning** | ✅ **Complete** (v0.34.0) |
| **Installer UI integration** | ✅ Complete (v0.35.0, this report) |
| **C — Windows packaging & host bridge** | ⬜ Not started |

TG-B is complete and unmodified by this work. Its engine — dependency
detection, resumable checksum-verified downloads, the durable journal,
parallel verification, first-run preparation and the manifest — is the
authority the UI renders; nothing in it was redesigned to accommodate a
screen.

---

## 3. The gap the brief assumed away

The brief said *"support the provisioning events already emitted by the
backend"*. Those events did not reach the frontend:

| Required | Reality before this work |
|---|---|
| Live progress | `provision` emitted one document **after** the run |
| Per-item `verifying` | No such state — verification was silent |
| Speed / time remaining | Not emitted |
| Models vs Voices grouping | `DownloadProgress` had no `kind` |
| A reachable wizard | Mounted nowhere; no route |

Three additive hooks closed it, each leaving the existing path
untouched: `--stream` (NDJSON; the flagless output is byte-identical),
`DownloadState.VERIFYING`, and `kind`.

---

## 4. Architecture decisions

**The backend stays authoritative.** Step, percentage, per-item state and
byte counts are stored exactly as received. There is no client-side step
machine — a UI tracking its own idea of progress alongside the engine's
would eventually disagree, and the engine would be right.

**Two values are derived, deliberately.** Speed and time remaining are
computed in the UI because a rate is a property of an observer over an
interval, not a fact about a download; a stopwatch in the engine would
report different numbers to two consumers. They derive from the
authoritative byte counts, never from an independent tally.

**Transport is injected, following TG-A's own pattern.** `loadPlan` was
already a prop; `runProvisioning` is the same shape. The wizard has no
opinion about how the host reaches the engine, which is exactly what
lets TG-C supply a real transport without touching the UI.

---

## 5. The deferred host bridge — stated plainly

**`provisioning-transport.ts` defines a contract that nothing implements
yet, and this is deliberate.**

`@tauri-apps/plugin-shell` is not a dependency of this project, and no
Rust command exists to spawn `python -m jarvis.installer`. Adding either
is packaging work and a dependency change; making it to have a screen
look finished is not a call to take unilaterally.

So the transport does two honest things rather than one dishonest one:

1. **It writes down the contract** TG-C must satisfy —
   command `run_provisioning`, event `provisioning://event`, NDJSON
   payloads — so packaging implements against an interface rather than
   inventing one, and the UI needs no change when it lands.
2. **It rejects with a readable reason** when the host cannot provide it.
   `classifyFailure` turns that into friendly copy with a Retry, which is
   correct for a capability that may genuinely appear later in a session.

A stub that resolved quietly, or emitted invented progress, would make
the installer *look* complete while installing nothing.

**Verified in a real browser:** `/install` renders full-screen, the
wizard advances through licence, location and account, and the hardware
scan reports *"needs the JARVIS desktop application"* — not a hang, and
not fabricated progress.

### What TG-C must build

| Item | Contract |
|---|---|
| `run_provisioning` | Tauri command. Args `{ location, accountType }`. Spawns `python -m jarvis.installer provision --stream`, relays each stdout line, resolves on exit. |
| `load_installation_plan` | Tauri command. Args `{ location, accountType }`. Returns the `plan` document. |
| `provisioning://event` | Tauri event. Payload is one NDJSON line (string) or the parsed object; both are accepted. |
| `launch_application`, `open_installation_folder` | Tauri commands, no args. |
| `@tauri-apps/plugin-shell` | Dependency plus the Rust-side capability to spawn a process. |

---

## 6. Defects found and fixed

1. **A React render loop.** `selectDownloadsByKind` built a new object
   per call; zustand compares selector results by reference, so every
   render looked like a state change until React aborted with "Maximum
   update depth exceeded".
2. **`defaultLocation=""`** permanently disabled Continue on the
   Location step, with no explanation — the same class of bug TG-A's
   flow test caught, in the one path that test could not reach because
   it supplied a location itself.
3. **The installer rendered inside the app shell**, with the sidebar and
   header of the application it was installing.
4. **A group headed "Local AI" containing an item also called "Local
   AI".**
5. **A test of my own that was too blunt** — it flagged the install
   folder *the user typed themselves* as a leak. `manifest_path`,
   dependency paths and download sources were verified admin-gated, and
   the assertion was made precise rather than deleted.

---

## 7. Quality gates

| Gate | Result | vs v0.34.0 |
|---|---|---|
| `pytest` | 2291 passed, 1 skipped | **unchanged** |
| `npm test` | **658 passed, 74 files** | +81, +3 files |
| `npm run lint` | 16 warnings, 1 category | **unchanged** |
| `npm run typecheck` | clean | unchanged |
| `npm run build` | clean | unchanged |
| `black --check src tests` | clean | **unchanged** |
| `ruff check src tests` | 21 categories | **unchanged** |
| `mypy src` | 262 errors | **unchanged** |

---

## 8. Remaining work

- **The host bridge** (§5) — TG-C.
- **No packaging**: no MSI, EXE, portable edition, shortcuts, auto-start
  or code signing.
- **No configured download source.** The registry still ships empty by
  design; a concrete host would be the hardcoded URL the brief forbids.
- **No published checksums**, so downloads verify as *present but
  unverifiable*. That becomes real verification when TG-C configures a
  source publishing digests.
- **Linux and macOS** remain detected-and-warned rather than supported.

---

## 9. Version, commit, push

- **Version:** 0.34.0 → **0.35.0**, both `pyproject.toml` and
  `jarvis/__version__.py` (the consistency test enforces it).
- **Commits:** `8308a31`, `6e2e465`, `de618af`, plus this
  documentation commit.
- **Branch:** `feature/m22-installer-ui` · **Push:** confirmed.

Awaiting approval before Task Group C.
