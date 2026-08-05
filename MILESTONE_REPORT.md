# Milestone Report — M8 Phase 2: Universal Application Framework & Logic

**Version:** 0.29.0
**Branch:** `feature/m8-phase-2`
**Baseline:** v0.28.0 (`49efc48`, M11 Task Group F merged to `main` at `47cd99e`)
**Date:** 2026-08-06

---

## 1. Scope

M8 Phase 2 as specified in `docs/IMPLEMENTATION_ROADMAP.md` §2 — the
mandatory Business Logic → State Machine → Service Layer → Hooks → Store
shape, plus Authentication, Permissions, Storage, Settings, API layer,
Voice/AI/Automation integration, Offline support and Error handling.

**Only this milestone.** No M7 work, no M8 Phase 3, no M12.

One sub-block of §2 is **not** delivered and is documented as such rather
than quietly marked done — see §9.

---

## 2. What the phase actually turned out to be

Phase 1 built the frontend frameworks. The expectation going in was that
Phase 2 would mostly wire them to the backend. Roughly half of it was.

The other half was a single recurring defect: **Phase 1's REST and
WebSocket layers were written against `ARCHITECTURE.md`'s illustrative
examples before the backend routes existed, and the examples were
illustrative.** Three separate contracts had drifted from the running
server, all silently — the failure mode in each case is a handler that
never fires or a message that never surfaces, with no error anywhere.

That framing drove the phase's most important deliverable, which was not
on the checklist: a generated contract that makes this class of drift
impossible to reintroduce (§5).

---

## 3. Checklist status

| §2 item | Status | Where |
|---|---|---|
| Business Logic → State Machine → Service Layer → Hooks → Store | ✅ | `core/module-lifecycle.ts` (Phase 1 port, verified faithful), `services/`, `hooks/use-backend-status.ts` |
| Authentication flow | ✅ | `services/api/session.ts` |
| Permissions from the Authorization Engine | ✅ (M9's, not M14's — §9) | `services/permissions-sync.ts` |
| Storage | ✅ (verified sufficient, not rebuilt) | `core/storage-framework.ts` |
| Settings — API layer + store | ✅ | `routes/settings.py`, `stores/settings.store.ts` |
| API layer — typed REST + WebSocket | ✅ | `services/api/`, `services/websocket/` |
| Voice Integration | ✅ | `voice.state_changed` → `services/realtime-bridge.ts` |
| AI Integration | ✅ | `agent.step` → `stores/agent-activity.store.ts` |
| Automation Integration | ✅ | `automation.step` |
| Offline support | ✅ | `services/backend-connection.ts`, `stores/connection.store.ts` |
| Error handling | ✅ | `providers/error-boundary.tsx` + `services/error-reporting.ts` |
| **API Integration Rework** (10 items) | ❌ **not delivered** | §9 |

---

## 4. Defects found and fixed

### 4.1 Security — OAuth client secrets leaked by `SettingsService.snapshot()`

Pydantic redacts a `SecretStr` on dump, which covers `openai.api_key` and
its neighbours. It does not cover a secret living inside a plain
container, and `integrations.clients` — introduced by M11 Task Group E —
is a `dict[str, dict[str, str]]` whose `client_secret` entries dump
verbatim.

The leak was **latent**: the only caller was the in-process PySide6
Configuration Manager, inside the same trust boundary as the `.env` file
it displays. But adding a settings API is precisely the change that makes
it live, and without this fix Phase 2 would have shipped a route
publishing Google OAuth client secrets to any authenticated caller.

Fixed by splitting into two methods — `snapshot()` (in-process,
unredacted) and `public_snapshot()` (redacted, the only form that may
cross a process boundary) — matching the
`Credential.to_storage_dict`/`to_public_dict` split already used in
`core/mcp/auth/credentials.py`. Two methods rather than one with a flag,
because a method callers must remember to sanitise is one somebody
forgets.

Redaction is **by key name**, not by type. A type-based check cannot work
here: nothing about `dict[str, str]` says "secret". Verified that
`client_id` — public by design — survives, so a settings screen can still
show which client is configured.

### 4.2 Eleven of fourteen client WebSocket event names did not exist

`ai.token`, `ai.step`, `ai.complete`, `voice.transcript_partial`,
`voice.transcript_final`, `automation.step_started`,
`automation.step_completed`, `automation.workflow_finished`,
`progress.update`, `notification.created`, `runtime.module_state_changed`
— none is emitted by anything. Replaced with the real 61 from
`EVENT_TYPE_NAMES`.

Three of the six payload interfaces this phase types were also wrong
(`AutomationStepPayload` and `PluginNotificationPayload` had invented
field names; `UpdatePhasePayload` was missing `session_id`) — a mistake I
made *while writing the fix*, caught by generating the contract from the
backend rather than by reading.

### 4.3 The REST client discarded every backend error message

It understood only the `{"error": {...}}` envelope from
`ARCHITECTURE.md` §9, which no route produces — every route raises
`HTTPException`, serialising as `{"detail": "..."}`. A real "Workspace
not found" surfaced as "Request failed with status 404".

### 4.4 The REST client expected cursor pagination

It read `meta.next_cursor`. The backend ships offset paging
(`{count, limit, offset, has_more}`) as of M11 Task Group F, which
recorded that divergence from the spec rather than hiding it.

### 4.5 A 2xx with a non-envelope body threw a bare `TypeError`

Found by a test, not by inspection. Now raises `MALFORMED_RESPONSE`
naming the offending route and flows through the normal error path.

### 4.6 Ruff caught a dead branch in my own redaction code

`return REDACTED if not isinstance(value, dict | list) else REDACTED` —
both branches identical (RUF034). Simplified.

---

## 5. The contract gate (not on the checklist)

`scripts/export_ws_contract.py` generates
`frontend/src/services/websocket/event-contract.generated.json` from
`EVENT_TYPE_NAMES` and each event's dataclass fields.

- `tests/unit/test_ws_contract_export.py` fails if the checked-in file is
  stale → a backend event added without regenerating breaks the Python
  suite.
- `websocket-contract.test.ts` fails if the TypeScript disagrees with the
  file → a client vocabulary that drifts breaks the frontend suite.

Neither side can drift without something going red. This is the only
durable fix for §4.2; correcting the names alone would have left the next
milestone free to repeat the mistake. The frontend test names all eleven
invented events explicitly, so a future edit that "restores" one fails.

---

## 6. Backend changes

| File | Change |
|---|---|
| `src/jarvis/services/settings_service.py` | `public_snapshot()`, `_redact()`, `_is_secret_key()`, `REDACTED` (§4.1) |
| `src/jarvis/infrastructure/api/routes/settings.py` | **new** — `GET /settings`, `GET /settings/{dotted_key}` |
| `src/jarvis/infrastructure/api/fastapi_server.py` | register the router at `/api/v1` |
| `scripts/export_ws_contract.py` | **new** — contract generator |

The settings route is **read-only, deliberately**. `set_env` writes
`.env`; exposing that over HTTP would let a browser request rewrite the
process's own configuration — a privilege-escalation surface belonging
with M14's Security Platform, not with a frontend phase whose job is to
read real values. `test_no_write_route_exists` asserts the absence so a
later addition is deliberate rather than unnoticed.

**No existing service, repository, registry or manager was duplicated.**
The settings route delegates to the existing `SettingsService` via the
existing DI container; permissions reuse M9's `PermissionModel` and the
existing `core/permission-framework.ts`; every event goes through the
existing `EventBus` → `RuntimeWebSocketHub` relay.

---

## 7. Frontend changes

**New:** `services/api/endpoints.ts`, `services/api/session.ts`,
`services/backend-connection.ts`, `services/realtime-bridge.ts`,
`services/permissions-sync.ts`, `services/error-reporting.ts`,
`stores/connection.store.ts`, `stores/settings.store.ts`,
`stores/agent-activity.store.ts`, `hooks/use-backend-status.ts`,
`services/websocket/event-contract.generated.json`.

**Rewritten:** `services/api/client.ts`, `services/websocket/types.ts`,
`services/websocket/connection-manager.ts`, `services/websocket/index.ts`.

**Modified:** `core/startup-orchestrator.ts` (the `low` tier is now real —
it was honestly empty before), `stores/notifications.store.ts` (stale
event name in a comment), `package.json`.

Design decisions worth flagging:

- **The session token is not persisted.** Backend sessions do not survive
  a backend restart, so a persisted token is usually stale by the time it
  is read; and M11 Task Group F tightened `/sessions/{id}` precisely
  because a leaked id is a real problem. One request at startup is
  cheaper than that risk.
- **`BackendState` distinguishes `unreachable` from `unauthenticated`.**
  Collapsing them produces a UI that says "something went wrong" when the
  truth is "JARVIS isn't running".
- **A failed request while offline does not toast.** The condition is
  already on screen persistently; a stack of identical complaints about
  it is noise. `reportError` returns `false` rather than failing
  silently, and `force: true` overrides for user-triggered actions.
- **All WebSocket subscriptions are installed once at startup**, not
  inside component effects — voice state must be correct whether or not
  the voice orb is mounted. `ensureRealtimeBridge()` is idempotent
  because React StrictMode double-invokes effects in development, and a
  second registration would record every step twice: a duplicate-data bug
  that only reproduces in development.

---

## 8. Quality gates

| Gate | Result |
|---|---|
| `pytest` | ✅ **2218 passed, 1 skipped** (2219 collected, 156 files) — was 2184/1/2185, so +34, matching the 34 tests added. The skip is a pre-existing platform guard (symlink creation). |
| `npm run lint` | ✅ 16 warnings, **1 category** (`react(only-export-components)`) — identical to baseline. One new `no-unused-vars` I introduced was fixed. |
| `npm run typecheck` | ✅ clean |
| `npm test` | ✅ **58 files, 404 tests passed** (was 48/293 — +10 files, +111 tests) |
| `npm run build` | ✅ built in 1.62s |
| `black --check src tests` | ✅ 567 files unchanged |
| `ruff check src tests` | ✅ **21 categories** — identical to baseline |
| `mypy src` | ✅ **262 errors** — identical to baseline (one new error I introduced was fixed) |

### 8.1 A note on the `typecheck` gate — a deviation, stated

The instruction was `npm run typecheck` using `tsc --noEmit`. Run
verbatim, that gate **checks zero files and always passes**: the root
`tsconfig.json` is a solution file (`"files": []`) whose real projects
live behind `references`, which plain `tsc` ignores. Confirmed
empirically with `--listFilesOnly` (empty output, exit 0) before
deviating.

The script is therefore `tsc -b --noEmit` — build mode, which honours the
project references. It caught six real errors on its first run.

---

## 9. What was deliberately not delivered

**The "API Integration Rework" sub-block of §2** — Real API Activation,
Provider Registry, Runtime Provider Registration, API Validation,
Connection Testing, Health Checks, Automatic Provider Loading, Provider
Failover, No Fake Providers, Runtime Provider Switching.

These ten items are **backend provider-lifecycle work**, tied by §2's own
cross-reference to M11's API Center Architecture module. They are not
frontend framework work, and a client that can merely *display* provider
state would not honestly satisfy any of them. They remain unchecked in
`IMPLEMENTATION_ROADMAP.md` §2 with an explicit note, and are called out
in `MASTER_ROADMAP.md`'s M8 entry, rather than being marked done.

**A note on the Permissions item.** §2 specifies "the backend's
Authorization Engine (M14)". M14 does not exist. The Authorization Engine
that does exist is M9's `PermissionModel`, which owns the same ten-scope
vocabulary `core/permission-framework.ts` already mirrors exactly
(verified against `core/plugins/sdk.py`'s `PERMISSION_SCOPES`). Phase 2
surfaces that one; `services/api/endpoints.ts` is the single place that
repoints if a future M14 supersedes it.

---

## 10. Tests added

**Backend (34):** `tests/unit/test_ws_contract_export.py` (9),
`tests/unit/test_settings_redaction.py` (15),
`tests/integration/test_settings_api_e2e.py` (10).

The e2e tests assert the security property directly — the raw response
text must not contain the planted secrets — rather than asserting that a
redaction function was called.

**Frontend (111 across 10 files):** `client.test.ts` (22),
`session.test.ts` (10), `websocket-contract.test.ts` (11),
`backend-connection.test.ts` (11), `realtime-bridge.test.ts` (11),
`error-reporting.test.ts` (13), `permissions-sync.test.ts` (9),
`connection.store.test.ts` (8), `settings.store.test.ts` (8),
`agent-activity.store.test.ts` (9).

---

## 11. Documentation updated

`CHANGELOG.md` (0.29.0), `docs/IMPLEMENTATION_ROADMAP.md` (§2 checkboxes
+ the deferred-backlog entry), `docs/MASTER_ROADMAP.md` (§1 status, §8
M8 entry), `docs/ROADMAP.md` (a pointer for M7+ rather than fabricated
entries — the file genuinely stops at M6 and disclaims itself),
`pyproject.toml` (0.28.0 → 0.29.0).

---

## 12. Public contract changes

- **Added:** `GET /api/v1/settings`, `GET /api/v1/settings/{dotted_key}`.
- **Changed:** `SettingsService.snapshot()` keeps its behaviour;
  `public_snapshot()` is new. No caller of `snapshot()` changed.
- **No breaking changes.**

---

## 13. Known gaps

- `frontend/package.json` still reports `"version": "0.0.0"` and
  `tauri.conf.json` `"0.1.0"`. Both predate this phase and neither is
  read by anything; left alone rather than changed as a drive-by.
- The connection layer is wired and tested but has no UI surface yet — no
  offline banner, no settings screen. Those are Phase 3/Phase 5 view
  work. The stores and hooks they will read are complete.
- `resolveWebSocketUrl` derives the socket URL from the REST base URL, so
  the two cannot diverge. Not exercised against a non-default
  `VITE_API_BASE_URL` in CI.

---

## 14. Status

**M8 Phase 2 is complete** except for the API Integration Rework
sub-block documented in §9. All five mandated quality gates pass, with
mypy, ruff, Black and lint at exactly their pre-existing baselines.

**Stopping here for approval before any further milestone work.**
