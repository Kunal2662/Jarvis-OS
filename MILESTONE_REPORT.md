# Milestone Report — M8 Phase 7: Production Readiness

**Version:** 0.32.0
**Branch:** `feature/m8-phase-7`
**Baseline:** v0.31.0 (`6e2c636`)
**Date:** 2026-08-06

---

## 1. Executive summary

An audit milestone, run against a **live backend** rather than by reading
code. I started the real FastAPI app with a real DI container and a real
health poll, drove the React client against it, killed the backend
mid-session, and brought it back.

That found **four defects that code review had missed**, including a
version drift three releases deep and a status selector that reported a
fault where none existed. All four are fixed, and three of them now have
tests that would have caught them.

No new functionality. No backend change — pytest, black, ruff and mypy
are unchanged from v0.31.0 apart from the version constant and its new
test.

---

## 2. Defects found and fixed

### 2.1 Version drift — three releases deep 🔴

`GET /api/v1/health` reported **`0.28.0`** while `pyproject.toml` said
`0.31.0`. `src/jarvis/__version__.py` — whose own docstring calls itself
*"single source of truth for the package version"* — had not been bumped
since v0.28.0, because v0.29.0–v0.31.0 each only bumped
`pyproject.toml`.

That constant is what the health endpoint returns, what
`jarvis --version` prints, and what a support conversation starts from.
An installation reporting a version three releases behind the artifact
it was built from is a real diagnostic hazard.

**Fixed:** both set to `0.32.0`, plus
`tests/unit/test_version_consistency.py` — three tests asserting they
match, that the version is semver, and that the health route reads the
constant rather than hardcoding a string. Nothing compared them before,
which is exactly why it drifted.

### 2.2 A dead-end user journey 🟠

M8 Phase 5 shipped five dashboard widgets whose empty state reads
*"Bind this workspace to a JARVIS workspace to see its tasks."* — and
**no control anywhere in the app could do that**. `bindBackendWorkspace`
had only tests calling it; `workspacesApi` had no caller at all. Five
widgets instructed the user to perform an action the UI did not offer.

**Fixed:** `components/workspace/workspace-binding.tsx`, in the workspace
toolbar. Every part already existed — the store action (Phase 3), the
typed endpoint (Phase 2), the widgets that read the binding (Phase 5).
This is the control that connects them, not a new feature. 10 tests,
including that the layout stores an **id and never the backend's data**,
and that a binding to a deleted workspace says "Unavailable" rather than
rendering blank.

### 2.3 A status selector reporting a fault that did not exist 🟠

Found against the live backend: Memory and Knowledge Graph showed
**Degraded** amber on a perfectly healthy system.

`selectSourceStatus` treated "the `workspace_platform` collector is not
reporting at all" the same as "it is reporting, and this source is
missing from its list". The first is *unknown*; only the second is a
degradation. A backend running without that collector — the API-only
runtime, for instance — lit up amber for no reason.
`selectServiceStatus` beside it already drew the distinction correctly.

**Fixed**, and pinned by two tests covering both sides of the
distinction.

### 2.4 Two stories for one condition 🟡

While offline, the five health widgets said *"Waiting for the backend to
report system health"* — implying a report was coming — while the
REST-backed widgets beside them correctly said *"Offline"*. The health
widgets read a store rather than issuing a request, so they never went
through `ResourceView`.

**Fixed:** `AwaitingBackend` now distinguishes *offline* from *connected
but not yet reported*. Verified in the browser: 5 uniform offline
messages, zero stale "waiting".

### 2.5 A footgun in the shared fetch hook 🟡

`useBackendResource`'s default emptiness check did not understand the
`Page<T>` shape (`{items, meta}`) that most endpoints return — a
non-empty object whose `items` may be empty. Empty collections rendered
as an empty list instead of an empty *state*. Three callers had already
worked around it with their own `isEmpty`; a fourth forgot, which is how
it surfaced.

**Fixed at the default**, and the three workarounds deleted. Fixing the
trap beats patching the call site.

---

## 3. Live verification

Ran the real backend (`create_app` + real `Container` + real
`HealthMonitor` poll) against the dev client:

| Verified | Result |
|---|---|
| Startup with no backend | Reveals correctly; explicit offline states; no fake data |
| `health.updated` → store → widgets | Real values: 1% CPU, 108 MB memory, 150 GB disk free, uptime, service counts |
| Backend killed mid-session | **No stale numbers survive** — the pre-outage snapshot is dropped, not shown as current |
| Backend restarted | **Reconnected automatically, no page reload**; offline messages cleared |
| Connected but no snapshot yet | Correctly distinguished from offline |
| `/workspace` route, panel chrome | Collapse / options / close all present and operable |

The disconnect behaviour is the one I most wanted to confirm: "never
fake data" has to hold *during* an outage, not just at startup.

---

## 4. Security review

**`ARCHITECTURE.md` §22.12 now has an executable guard.**
`core/__tests__/restricted-surface.test.ts` scans every source file: any
module reading a restricted source (`mcpApi`, `devtoolsApi`, `auditApi`,
`selectProviders`, `selectEgressStats`) must also consult the audience
gate.

The behavioural tests check *existing* surfaces. This catches the
failure that actually worries me — a **new** surface added later that
reads provider names and never gets a gate, where no existing test would
fail because none knows about it. That is precisely how the Phase 3
Activity Center leak survived a whole milestone.

**I mutation-tested it**: removing the gate from the Diagnostics panel
made it fail with the offending filename; restoring it made it pass. It
also guards against passing vacuously (asserts it found >50 files).

| Check | Result |
|---|---|
| Provider names leaked to personal users | None — 2 surfaces read them, both gated |
| Secrets exposed | None — server-redacted; the admin panel reports *configured or not*, never values |
| Debug data in personal mode | None — Developer Dashboard gated twice (menu filter + component) |
| Developer panels visible in personal mode | No — verified by test |
| Internal IDs exposed | Workspace/panel ids are client-generated and non-sensitive; backend ids appear only in Developer surfaces |

---

## 5. Code quality

**Removed** (each verified as having zero importers first):
`healthApi` (a stub documenting a decision a comment documents better),
`useWideLayout` + `WIDE_MIN_WIDTH` (never called — the workspace has one
breakpoint, not three tiers), and duplicated skeleton markup collapsed
into one `StatShape`.

**Deliberately kept**, with reasons:

- `components/ui/{alert-dialog,context-menu,label,separator,tabs}.tsx` —
  vendored shadcn primitives. Unused, but **already tree-shaken out of
  the bundle**, so removal saves zero bytes; `context-menu` is named in
  the roadmap as the primitive for the deferred Context Menu system.
- `core/interfaces/{ai,automation}-integration.ts` — the documented
  module contract surface. Removing them would be an architecture
  change, which this milestone forbids.
- `selectThreadSteps` — unused in production but tested, with a
  documented near-term consumer.

**Reported, not removed:** TanStack Query is mounted (`QueryProvider`)
and **never used** — no `useQuery` anywhere — costing 24.5 kB (7.28 kB
gzipped) in the initial bundle. `services/api/query-keys.ts` is its
empty pattern file. Removing it would be an architecture change against
an approved dependency, so it is flagged for a decision rather than
taken unilaterally. **Recommendation:** either adopt it for paginated
collections or drop it in a milestone empowered to change the stack.

---

## 6. Quality gate results

| Gate | Result | vs v0.31.0 |
|---|---|---|
| `pytest` | 2221 passed, 1 skipped | +3 (version consistency) |
| `npm test` | **546 passed, 69 files** | +16, +2 files |
| `npm run lint` | 16 warnings, 1 category | **unchanged** |
| `npm run typecheck` | clean | unchanged |
| `npm run build` | clean, no warnings | unchanged |
| `black --check src tests` | 568 files clean | unchanged |
| `ruff check src tests` | 21 categories | **unchanged** |
| `mypy src` | 262 errors | **unchanged** |

`npm run typecheck` earned its keep again: the §22.12 guard originally
used `node:fs`, which vitest accepts and the app's browser-targeted
tsconfig does not. Rewritten with Vite's `import.meta.glob`.

---

## 7. Release readiness checklist

| Item | Status | Evidence |
|---|---|---|
| Backend frozen verified | ✅ | Zero backend changes but the version constant; all Python gates unchanged |
| API contracts verified | ✅ | 172 operations enumerated in Phase 5; no route added or altered since |
| Documentation updated | ✅ | README, CHANGELOG, both roadmaps, this report |
| No mock data | ✅ | Verified live: real health numbers; nothing seeded |
| No fake APIs | ✅ | Every client path checked against the OpenAPI dump |
| Performance validated | ✅ | 15 chunks, largest app chunk 31.76 kB gzipped; virtual lists on all unbounded lists |
| Accessibility reviewed | 🟡 | ARIA labels, roles, live regions, keyboard-operable splitters, focus order verified in the a11y tree. **No screen-reader or contrast-ratio audit run** — see §8 |
| Security reviewed | ✅ | §22.12 guard, mutation-tested |
| Workspace validated | ✅ | 36 store tests + 12 container + 13 toolbar + 10 binding; create/rename/delete/duplicate/reset/import/export/switch/restore/dock/float/collapse/resize/persist |
| Dashboard validated | ✅ | Live data verified; gating tested |
| Search validated | ✅ | 9 tests; real `POST /api/v1/search`; offline path asserted |
| Voice validated | 🟡 | State machine and store tested; **no real voice backend exists** to validate against |
| Memory validated | 🟡 | Status surfaced from the health snapshot; no dedicated memory UI exists |
| Notifications validated | ✅ | 9 tests; real store; virtualised |
| Developer Mode validated | ✅ | Gating tested both directions |
| Admin Mode validated | ✅ | Gated; developer ≠ admin asserted |
| Personal Mode validated | ✅ | 11 Activity Center tests + source-level guard |
| Cross-browser verified | ❌ | **Not done** — Chromium only. See §8 |
| Ready for M22 | ✅ | With §8 read first |

---

## 8. Remaining work — read before calling this shipped

Being accurate matters more here than being reassuring:

- **Cross-browser testing was not performed.** Verification ran in the
  in-app Chromium browser only. The Tauri shell uses the platform
  webview — WebKit on macOS, WebView2 on Windows — and neither was
  exercised. This is genuinely open, and M22 (cross-platform
  distribution) is where it belongs.
- **No screen-reader pass and no contrast-ratio measurement.** I verified
  the accessibility *tree* — roles, names, live regions, focus order —
  which is necessary but not sufficient. No NVDA/VoiceOver run, no
  computed contrast check against WCAG AA.
- **Eleven modules remain placeholders** — Chat, Memory, Knowledge Graph,
  Automation, Projects, Calendar, Files, Browser, Vision, and others. The
  brief asked to confirm "no placeholder routes for completed modules";
  the accurate finding is that **these modules are not completed**, so
  their placeholders are correct, not a regression. Only Dashboard,
  Voice, Settings, Workspace, Plugins, Diagnostics and the three
  dashboards have real UI.
- **Voice and Memory cannot be meaningfully validated** — no voice
  backend exists, and there is no memory UI. Their status rows come from
  the health snapshot and are honest about being unknown.
- **TanStack Query decision** — see §5.
- Image optimization, window state persistence beyond the existing Tauri
  plugin, DPI scaling and multi-monitor remain open, all blocked on Tauri
  window APIs.

---

## 9. Version, commit, push

- **Application version:** 0.31.0 → **0.32.0**, now consistent across
  `pyproject.toml` and `jarvis/__version__.py` for the first time since
  v0.28.0.
- **Branch:** `feature/m8-phase-7` · **Push:** confirmed to `origin`.
