# Milestone Report — M22 Task Group A: Universal Installer Foundation

**Version:** 0.33.0
**Branch:** `feature/m22-task-group-a`
**Baseline:** v0.32.0 (`a04db04`)
**Date:** 2026-08-06

---

## 1. Executive summary

The installer experience and the hardware calibration that drives it.
Eleven-step wizard, real hardware detection, an AI Capability Score, a
local-model recommendation, a voice plan and seven pre-installation
checks — all working against **this machine's actual hardware**, not a
fixture.

Running it on real hardware immediately found three defects that reading
the code would not have: free space measured on the wrong drive, a
16 GB machine that could never qualify for the 16 GB model tier, and a
React effect that cancelled every scan it started.

**Backend untouched.** No route, model, schema, event or contract
changed. The installer is a new, isolated package that imports no
service, no repository and no container — it has to be, because it runs
before JARVIS is installed.

---

## 2. The architectural question this task group had to answer first

The brief freezes API contracts; hardware detection is inherently
Python; the installer UI is React. So how do they talk?

**A JSON-emitting CLI, not a REST route.** `python -m jarvis.installer`
exposes `detect`, `plan` and `validate`. An installer cannot call an API
served by the application it is installing, and adding a route would
have modified a frozen contract. Shelling out is what installers
actually do, and it keeps this milestone purely additive.

`InstallerWizard` takes `loadPlan` as a **prop** rather than importing a
client. The real implementation invokes that CLI through Tauri; tests
inject a stub. That is also what lets Task Group B swap in the packaged
runtime without touching the UI.

---

## 3. The rule the package is built on

> A field is either measured or it is `None`. It is never estimated,
> defaulted to something plausible, or inferred from a different field.

An installer that invents a GPU or a temperature produces a calibration
that is confidently wrong and invisible to the user. `None` is visible:
the UI renders **"Not detected"**, `HardwareProfile.notes` explains why
in the user's own words, and `AICalibration.missing_inputs` records what
the recommendation did not know.

On this machine that is not hypothetical — Windows exposes no
temperature sensors and no GPU was probeable, so three fields came back
`None` and the UI says so rather than showing zeros.

---

## 4. Defects found by running on real hardware

### 4.1 Free space measured on the wrong drive 🔴

`detect_storage` fell back to the current working directory when the
target path did not exist — **which is the normal case during
installation**, since the install directory has not been created yet.
The plan reported free space for whichever drive the installer was
launched from. On Windows that is routinely a different volume, so a
machine with a full target drive would have sailed through the
disk-space check.

Fixed by walking up to the nearest existing ancestor, which resolves to
the target's own drive root at worst.

### 4.2 A 16 GB machine could never reach the 16 GB tier 🔴

Detection on this laptop returned 15.7 GB and recommended **Small**. RAM
is sold in decimal GB — a "16 GB" machine has 16 × 10⁹ bytes, which is
15.7 *GiB* — so comparing against a binary threshold meant **every**
16 GB machine on earth would miss its tier and be offered the 8 GB one.

Fixed by comparing RAM in the same units the machine is advertised in.
VRAM stays binary, because that is how every vendor tool reports it.

### 4.3 An effect that cancelled every scan it started 🟠

The wizard's scan effect used a per-run `cancelled` flag and listed
`scanning` among its dependencies. `beginScan()` sets `scanning`, so
starting a scan re-ran the effect, whose cleanup cancelled the request
it had just started — and the re-run's own guard then refused to retry.
The scan resolved into a discarded closure every time and the step sat
on its skeleton forever.

Replaced with a request-id ref, which survives re-runs. Caught by the
wizard's flow test.

### 4.4 Two smaller ones

- **The Location step's Continue was dead.** It displayed the proposed
  default but never committed it, so `canAdvance` saw `null` and the
  only way forward was to retype the path already on screen.
- **Each account card's accessible name was ~40 words** — icon, title,
  blurb and three bullets — and ambiguous, since the Administrator
  card's blurb contains the word "Personal". Now `aria-label` names the
  choice and `aria-describedby` carries the detail.

---

## 5. What was built

**Python — `src/jarvis/installer/` (7 modules, zero mypy errors):**

| Module | Responsibility |
|---|---|
| `hardware.py` | CPU, RAM, storage, GPU/VRAM, battery, temperature, internet, NPU. Every probe bounded and non-fatal. |
| `calibration.py` | AI Capability Score (RAM 45 / CPU 30 / accelerator 25), performance profile, resource limits, cloud-usage preference. |
| `local_model.py` | Four tiers (Tiny/Small/Standard/Advanced) and the recommendation. **Downloads nothing and knows no URL.** |
| `voice.py` | Voice component plan and the single voice identity. |
| `validation.py` | Seven pre-flight checks with pass/warn/fail. |
| `__main__.py` | The JSON CLI. |

**React — `src/features/installer/`:** the eleven-step wizard, its
store, and typed contracts pinned against real CLI output.

---

## 6. Security and account model

`ARCHITECTURE.md` §22.11/§22.12 are enforced **at the payload**, not in
the UI: a personal plan genuinely does not contain model ids, score
components, resource limits or provider names, because the Python side
omits them. What never arrives cannot leak through a rendering mistake.

A test asserts the serialised personal payload contains none of
`piper`, `whisper`, `elevenlabs`, `llama`, `qwen`, `openai`, `gemini` or
`groq` — and that it still carries everything that affects the user:
the score, the tier's human label and size, the voice identity, and
every validation result.

No secrets, credentials or API keys are read, written or displayed
anywhere in this task group.

---

## 7. Quality gates

| Gate | Result | vs v0.32.0 |
|---|---|---|
| `pytest` | 2261 passed, 1 skipped | +40 |
| `npm test` | **577 passed, 71 files** | +31, +2 files |
| `npm run lint` | 16 warnings, 1 category | **unchanged** |
| `npm run typecheck` | clean | unchanged |
| `npm run build` | clean, no warnings | unchanged |
| `black --check src tests` | clean | unchanged |
| `ruff check src tests` | **21 categories** | **unchanged** |
| `mypy src` | **262 errors**, 405 files | **unchanged**, +7 files all clean |

Ruff initially flagged five issues in the new code, including four new
categories; all were fixed rather than suppressed.

---

## 8. Deliberately not built

Stated plainly, because an installer that appears to do more than it
does is the worst kind:

- **Nothing is downloaded.** No model, no voice component. The brief
  says recommendation only for this task group, and the modules know no
  download URL at all — a module that *could* start a multi-gigabyte
  transfer is one somebody eventually calls by accident.
- **No installation engine.** The Install step says so on screen rather
  than animating a progress bar that measures nothing.
- **Test Voice and Launch JARVIS are disabled**, with a reason on hover.
  The components they need are not installed yet. A button that appears
  to work and does not is worse than one that explains itself.
- **No Windows packaging** — no MSI, no shortcuts, no auto-start, no
  portable edition, no code signing. Those are Task Group B.
- **Linux and macOS** are detected and warned about, per the brief's
  "Windows is the primary platform".
- **NPU detection is conservative.** There is no portable enumeration
  API; a name is reported only when hardware enumeration actually
  identifies something NPU-like. Reporting "no NPU" on a machine that
  has one is less harmful than claiming one that is absent — the
  calibration treats it as a bonus, never a requirement.

---

## 9. Version, commit, push

- **Version:** 0.32.0 → **0.33.0**, bumped in both `pyproject.toml` and
  `jarvis/__version__.py` — the consistency test added in M8 Phase 7
  would have failed otherwise.
- **Branch:** `feature/m22-task-group-a` · **Push:** confirmed.

Awaiting approval before Task Group B.
