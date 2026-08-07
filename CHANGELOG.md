# Changelog

All notable changes to JARVIS OS are documented here. Format loosely
follows [Keep a Changelog](https://keepachangelog.com/).

## M12 Task Group B, Phase 3: MQTT Connector

**No version bump**, matching Task Group A and Phases 1-2's own
precedent; `0.38.0` is unchanged.

Phase 2 shipped the first real `IDeviceConnector` (Home Assistant, REST
over `httpx`). Phase 3, approved the same day on direct, separate
instruction preceded by its own 17-point read-only architectural
audit, builds the second: an MQTT connector, closing this task group's
three-phase implementation plan.

### Added
- **Library selection, corrected during implementation** — the audit's
  originally-preferred `aiomqtt` (wraps `paho-mqtt`) was replaced with
  `gmqtt` after connecting each against a real local broker found
  `aiomqtt` raises `NotImplementedError` on Windows' default
  `ProactorEventLoop` (needs `loop.add_reader`/`add_writer`, which only
  `SelectorEventLoop` implements on Windows -- and `SelectorEventLoop`
  cannot run this project's existing subprocess-based MCP
  `StdioTransport`). `gmqtt` connected cleanly on the same loop with no
  workaround. `requirements.txt`/`requirements-lock.txt`/`pyproject.toml`
  updated to `gmqtt>=0.7,<1.0`, zero `aiomqtt`/`paho-mqtt` remnants.
- **JARVIS-native message envelope** (`core/connectivity/connectors/
  mqtt_envelope.py`) -- the canonical protocol for future JARVIS-native
  devices (ESP32 and similar): one JSON shape (`schema_version`,
  `device_id`, `type`, `timestamp`, `payload`) covering state/command/
  discovery/availability/error, with explicit schema versioning.
- **`MqttConnector`** (`core/connectivity/connectors/mqtt.py`) -- the
  second real `IDeviceConnector`. Speaks Home Assistant MQTT Discovery
  (interoperating with Zigbee2MQTT/zwave-js-to-mqtt/Tasmota/ESPHome
  with no dedicated connector for any of them) and the JARVIS-native
  envelope. State is push-based and cached, not pulled. Commands
  publish at QoS 1, never retained. Reconnection is `gmqtt`'s own
  automatic retry paired with unconditional resubscription on every
  `on_connect`.
- **`build_mqtt_connector`** (`core/connectivity/connectors/factory.py`)
  -- registered into `build_default_connector_registry()` alongside
  Home Assistant. Both `CONNECTOR_TYPES` entries are now registered.
- **`tests/fakes/fake_mqtt_broker.py`** -- a real, hand-written,
  in-process MQTT 3.1.1 broker (no stdlib broker exists to reuse,
  unlike Phases 1-2's `http.server`/`websockets`), supporting
  CONNECT/CONNACK auth, SUBSCRIBE/UNSUBSCRIBE with wildcards, PUBLISH
  at QoS 0/1 with PUBACK, retained-message replay, and Last Will and
  Testament.
- **68 new tests** -- envelope round-trip/validation (26), connector
  coverage across connect/disconnect, auth, TLS config, HA + native
  discovery, state cache, availability, retained-message handling, QoS,
  commands, and automatic reconnect-with-resubscription (42), plus MQTT
  factory tests -- all against the real fake broker, no mocked `gmqtt`
  client.

### Notes
- **`CONNECTOR_TYPES` fully realized.** `home_assistant` and `mqtt` are
  both registered; Task Group B's three-phase plan is closed.
- Full backend regression: **2477 passed, 1 skipped (pre-existing), 0
  failed.** Full frontend: **750/750**, plus a clean `tsc`/`oxlint`.
- **M12 is still 🟡 Active, not Complete** -- Smart Home Core and
  Connectivity Layer are two modules of fifteen; thirteen remain
  entirely unstarted.

## M12 Task Group B, Phase 2: Home Assistant Connector

**No version bump**, matching Task Group A and Phase 1's own
precedent; `0.38.0` is unchanged.

Phase 1 shipped the port/adapter foundation with no protocol code
behind it. Phase 2, approved the same day on direct, separate
instruction per Phase 1's own recommendation, builds the first real
`IDeviceConnector`: a Home Assistant connector speaking REST over
`httpx`.

### Added
- **`HomeAssistantConnector`** (`core/connectivity/connectors/
  home_assistant.py`) — `connect()`/`disconnect()` manage a pooled
  `httpx.AsyncClient` with a real reachability probe (`GET /api/`),
  the same "fail at connect, not at first use" discipline
  `HttpTransport` established for MCP. `discover()` lists
  `/api/states` and maps each entity onto a `DiscoveredDevice` through
  a closed allowlist of eighteen physical-device domains (onto Task
  Group A's own `DEVICE_TYPES`); a domain outside the allowlist
  (`automation`, `script`, `scene`, `zone`, `person`, ...) is skipped,
  never registered as a device. `read_state()` reads
  `/api/states/{entity_id}`. `send_command()` posts to
  `/api/services/{domain}/{service}`, reporting a device-level
  rejection as `CommandResult.success=False` rather than raising.
- **`core/connectivity/connectors/factory.py`** — `build_home_assistant_
  connector` (validates `base_url`/`token` at construction) and
  `build_default_connector_registry()`, mirroring
  `build_default_transport_registry()`. Registers `home_assistant`
  only; `mqtt` stays unregistered.
- **DI wiring** — `_build_connectivity_registry` now calls
  `build_default_connector_registry()` instead of constructing an
  empty registry directly.
- **26 new tests** — `test_home_assistant_connector.py` against a real
  local `http.server.HTTPServer` (no mocked `httpx` client, matching
  `test_mcp_transports_live.py`'s own convention for MCP's network
  transports) and `test_connectivity_connector_factory.py` for the
  factory/registration surface.

### Notes
- **Still no MQTT code.** `CONNECTOR_TYPES` continues to name `mqtt`;
  Phase 3 (MQTT) remains a separate, later, individually-approved
  pass.
- **No frontend or event changes.** Phase 1 wired
  `ConnectivityStatusChangedEvent` into the WebSocket relay; this phase
  reuses it unchanged and adds no REST route — `ConnectivityService`
  still has no HTTP caller, by design (a later M12 module's job).
- **M12 is still 🟡 Active, not Complete** — Connectivity Layer now has
  one of its two approved protocol adapters; thirteen of fifteen
  modules remain entirely unstarted.

## M12 Task Group B, Phase 1: Connectivity Layer Foundation

**No version bump**, matching Task Group A's own precedent; `0.38.0`
is unchanged.

An approved five-step plan (audit, connectivity-technology analysis,
architecture design, phased plan, risk analysis — no code) broke this
task group into three separately-approved phases. Phase 1 builds the
port/adapter foundation every later phase plugs into; it talks to no
real device and ships no protocol adapter.

### Added
- **`IDeviceConnector` port** (`core/interfaces/connectivity.py`) plus
  `DiscoveredDevice`/`DeviceState`/`CommandResult` value objects —
  mirrors `IMCPTransport`'s own shape. `CONNECTOR_TYPES` deliberately
  narrow: `home_assistant`, `mqtt` — only this task group's approved
  scope, not the milestone's full connectivity vocabulary.
- **`ConnectorFactoryRegistry`** (`core/connectivity/registry.py`) —
  mirrors `TransportFactoryRegistry`; empty of real connectors.
- **`ConnectorCredentialStore`** (`core/connectivity/credential_store.py`)
  — Fernet-encrypted-at-rest, refuses to persist without a real key. A
  structural sibling of MCP's own `CredentialStore`, not a shared
  instance.
- **`ConnectivityService`** (`services/connectivity_service.py`) —
  idempotent connect/disconnect, discovery idempotent by home +
  external id, state refresh mapped onto Task Group A's closed device
  statuses, and `send_command` — the single chokepoint a later M12
  module will gate safety-critical devices against.
- **`SmartHomeService` extensions** — `register_discovered_device`
  gained a `metadata` kwarg (written to the existing
  `Device.metadata_json` column, no schema change),
  `get_device_by_external_id`, `report_device_state`.
- **DI wiring** — `connectivity_registry`, `connectivity_credential_
  store`, `connectivity_service` singletons.
- **`ConnectivityStatusChangedEvent`** — new WebSocket relay event,
  wired into `runtime_ws_hub.py`, the generated contract, frontend
  `RELAYED_EVENTS`, and both pinned relay-vocabulary tests in the same
  change.
- **107 new/affected tests** — `FakeDeviceConnector` plus three new
  suites (registry, credential store, service) and extended
  `SmartHomeService` coverage, all against real (temp-file) SQLite or
  real file-backed credential storage.

### Notes
- **No protocol code.** `CONNECTOR_TYPES` names `home_assistant` and
  `mqtt`; neither has an implementation. Phase 2 (Home Assistant) and
  Phase 3 (MQTT) are separate, later, individually-approved passes.
- Full backend regression: **2379 passed, 1 skipped (pre-existing), 0
  failed.** Full frontend: **750/750**, plus a clean `tsc`/`oxlint`/
  production build.
- **M12 is still 🟡 Active, not Complete** — Smart Home Core and
  Connectivity Layer's own foundation are two modules of fifteen;
  thirteen remain entirely unstarted.

## M12 Task Group A: Smart Home Core

**No version bump, by explicit instruction.** Unlike M22's own task
groups (each of which bumped the version for its own shipped code),
this one did not; `0.38.0` is unchanged. An earlier draft of this
entry briefly described a `0.39.0` bump that was reverted before
commit — this entry describes what actually shipped, at the real,
unchanged version.

A roadmap audit (`MASTER_ROADMAP.md`, `IMPLEMENTATION_ROADMAP.md`)
found M12 — Smart Home & IoT Platform is the next milestone actually
marked Not Started in the M9→M21 resumption order: M10 is Partial and
M11 is Active (Task Groups A–F shipped, not closed), so neither
qualifies even though both precede M12 numerically. Started while M22
remains open — a second deliberate exception to "one active milestone
at a time," on direct instruction.

### Added
- **Smart Home domain** (`domain/smart_home/models.py`) — closed
  vocabularies for home status, device status and device type, plus
  derived `HomeMetadata` (never stored, computed on read).
- **Five ORM models** (`infrastructure/database/models.py`) — `Home`
  → `Zone` → `Room` → `Device`, plus `DeviceGroup` /
  `DeviceGroupMember` as a cross-cutting grouping independent of that
  hierarchy.
- **`SmartHomeService`** — lifecycle CRUD for all five entities,
  derived home metadata (Device Health Monitoring / Status Dashboard),
  event publishing, search hooks. Device Discovery and Pairing are
  modeled as domain status transitions
  (`register_discovered_device` / `pair_device`) — neither talks to
  real hardware; no Connectivity Layer exists yet.
- **REST** — `/api/v1/homes`, `/api/v1/devices`,
  `/api/v1/smart-home/{zones,rooms,device-groups}`, plus
  `/homes/{id}/metadata`, device-group membership routes, and
  `POST /devices/{id}/pair`.
- **Two new search sources** (`homes`, `devices`) registered on M10A's
  existing provider registry.
- **Two new WebSocket relay events** (`home.updated`,
  `device.updated`), wired into `runtime_ws_hub.py`'s relay mapping
  and both sides of the WebSocket contract (backend
  `event-contract.generated.json` regenerated; frontend
  `RELAYED_EVENTS` updated to match).
- **89 tests** across service, repository, REST and contract-
  consistency layers, all against real (temp-file) SQLite — no mocked
  repository.

### Fixed
- Two pinned search-source-vocabulary tests
  (`test_platform_integration.py`, `test_knowledge_route.py`) and two
  pinned relay-vocabulary tests (`test_platform_integration.py`,
  `test_runtime_ws_hub.py`) hadn't been extended for the new sources
  and events — found by actually running the full suite, not assumed.
- `IMPLEMENTATION_ROADMAP.md`'s top-level milestone status table
  incorrectly read "M11 onward: Planned, not started," contradicting
  its own §5G section. M11 is Active (backend shipped across six task
  groups; not closed — the React/Tauri UI half waits on M8).

### Notes
- **Scope boundary, drawn the same way M11 Task Group B drew one
  around `Reminder`:** this task group builds the domain layer only.
  No real device talks to it. Fourteen of M12's fifteen modules
  (starting with Connectivity Layer, which real discovery/pairing
  depends on) are separate, later task groups.
- M10 and M11's own open status is reported, not resolved, by this
  entry — see `MILESTONE_REPORT.md`'s M12 Task Group A entry for the
  full roadmap audit.
- **M12 is now 🟡 Active, not Complete** — Task Group A is one module
  of fifteen; fourteen remain unstarted.

## M22 Task Group F: Final Build Verification, Cross-Platform Readiness & Release Validation

**No version bump.** Consistent with this project's own precedent
(the governance documentation pass, `11a8f6f`): a verification and
documentation pass with no shipped application change does not bump
the version. Version remains `0.38.0`.

**Status: Implementation Complete — Build Verification Pending**, for
the same reason 0.36.0 through 0.38.0 carry it: no Rust toolchain
exists on this build machine, so nothing gated on a real `tauri build`
has been proven. What this pass adds is everything that *doesn't* need
one, run for real rather than assumed.

### Verified for real (no Rust toolchain required)
- **Fresh installation, resume, and existing-installation detection**
  — `python -m jarvis.installer provision` run against a real scratch
  directory: genuinely created the directory tree, wrote a real
  config file, completed three real steps, then failed at
  `model_download` exactly as expected (this environment's download
  source registry ships empty by design). Re-running the same command
  correctly skipped the three completed steps rather than redoing
  them.
- **Interrupted installation recovery** — the provisioning journal was
  deliberately truncated mid-write to simulate a crash. Confirmed
  correct, intentional behavior (`journal.py`'s own documented
  design: an unreadable journal is treated as absent, and every step
  is idempotent, so starting over is safe) rather than a defect.
- **Repair and verification workflows, together** — a real
  installation's config file was deleted; `verify` correctly reported
  it failed and repairable; `repair configuration` recreated it; a
  second `verify` immediately confirmed the fix, re-verifying after
  acting rather than trusting its own result.
- **Dependency verification** — ran against this machine's real,
  live-probed state (Python, Git, DirectML, CUDA), not a fixture.

### Fixed
- **`docs/PACKAGING.md`'s icon paragraph and Build Verification Task 5
  were stale**, still describing Task Group E's branding work as
  unstarted after Task Group E had shipped it — a documentation
  regression from that file being outside Task Group E's own
  documentation sync list. Corrected to describe the real, current
  two-variant/hybrid-ICO state.

### Added
- **`docs/PACKAGING.md` "Cross-platform readiness" section** — an
  evidence-based audit of every Windows-specific assumption in the
  codebase (found by reading every `#[cfg(windows)]`, `wmic` call and
  hardcoded path, not by guessing) and a concrete migration checklist
  for a future Linux/macOS task group. Nothing in it was implemented —
  this task group's own brief was explicit that it audits and
  documents, and does not build Linux or macOS support.
- **Two new Build Verification Tasks** (now twelve total, in
  `docs/PACKAGING.md`): watching the startup animation actually run in
  a real compositing browser (still not possible in this session's
  sandboxed preview pane), and generating and committing
  `frontend/src-tauri/Cargo.lock`, which does not exist yet because
  `cargo` has never run against this repository.

### Notes
- **M22 cannot be marked Complete.** Per `MASTER_ROADMAP.md` §18, all
  of TG-C, TG-D, TG-E and TG-F must reach Build Verification Passed —
  none of the twelve Build Verification Tasks is checked. This is the
  same blocker TG-C's own first report named, now confirmed to still
  be the single blocking factor across four task groups at once.
- Full audit findings, the complete real-CLI verification evidence,
  and the itemized remaining-risk list are in `MILESTONE_REPORT.md`'s
  Task Group F entry.

## [0.38.0] — M22 Task Group E: Windows Packaging & Installer Distribution

**Status: Implementation Complete — Build Verification Pending**, for
the same reason 0.36.0 and 0.37.0 carry that status: no Rust toolchain
exists on the build machine, so nothing new in `src-tauri/` has been
compiled.

An audit before implementation found most of this task group's
nineteen-item brief already built by Task Groups A–D: NSIS
configuration, installer/uninstaller/Add-Remove-Programs registration,
version metadata, installation logging, launch-after-install, and
open-installation-folder are all real, shipped capability, not new
work. What was genuinely missing was the application's actual branding
— every icon in the repository was still Tauri's own placeholder logo
— and that gap became directly actionable mid-task-group when the
user supplied and approved the official JARVIS master logo.

### Added
- **The approved master logo**, integrated as the project's brand
  identity: `frontend/src-tauri/icons/master-logo.png` (the source of
  truth), a full production icon set (16 through 1024px PNG, `.ico`,
  `.icns`), and `frontend/public/branding/premium/` for future in-app
  use (About, Settings, notifications — none of which exist yet in
  this codebase; nothing was invented to house them early).
- **A second, simplified icon variant**, hand-authored specifically
  for the sizes where the master's metallic gradients stop reading —
  confirmed empirically: the master rasterized to plain 32×32 renders
  as a near-illegible dark blur. `frontend/src-tauri/icons/small-icon-
  source.svg` is a bold, high-contrast reinterpretation of the same
  ring-and-blade silhouette, used for 16–48px contexts (taskbar, system
  tray, Explorer, window title bar) and `frontend/public/branding/
  small-icon/`.
- **A hybrid multi-resolution `icon.ico`**, built by a small
  hand-written PNG-in-ICO packer (no Pillow/ImageMagick available):
  small frames (16/24/32/48) from the simplified variant, large frames
  (128/256) from the master, so the one file Windows actually reads is
  legible at every size it gets asked to render, not just the large
  ones.
- **The startup animation's logo recreated as SVG** (`components/
  startup/jarvis-logo.tsx`), replacing the earlier hexagon placeholder
  with the approved logo's own geometry, animated with Framer Motion
  across the existing `assembling`/`pulsing` phases — ring channels
  drawing, the outer ring fading in, the center blade rising, the side
  blades sliding up, a glow igniting, a pulse travelling outward, one
  soft breathing cycle. Every animated property is opacity, a
  transform translate/scale, or SVG `pathLength` — never a
  layout-triggering property — so this composites on the GPU without
  forcing layout.
- **The browser-tab favicon replaced** (`public/favicon.svg`) — was an
  unrelated purple abstract mark (a Vite/template-era placeholder, not
  even the same shape family as the hexagon logo elsewhere), found only
  by checking `index.html` directly rather than assuming the favicon
  was already covered by the icon work.
- **`packaging/verify_tauri_build.ps1`**, a new build-verification
  script that turns part of Task Group C's manual Build Verification
  Tasks list into mechanical pass/fail checks: the installer artifact
  exists, its version metadata matches this project's single source of
  truth, its product/publisher fields are real, and the shipped icon is
  provably not Tauri's placeholder. Run for real against this
  project's current (unbuilt) state — correctly reports the one
  failure that should exist (no installer yet) and passes every check
  that does not depend on a build existing.
- **11 new packaging/branding contract tests** plus a rewritten
  `jarvis-logo.tsx` test suite (7 tests, up from 4) — 750 tests total
  in the frontend suite, up from 736.

### Fixed
- **A verification heuristic that broke on its own first real input.**
  The build-verification script's original icon check asserted "small
  enough to be the real icon" against an early placeholder; Task Group
  E's actual hybrid `.ico` is a multi-resolution file that ended up
  *larger* than the Tauri placeholder it replaced, not smaller,
  immediately failing that heuristic against genuinely correct output.
  Replaced with a negative match against the placeholder's own known,
  fixed byte size — a check that does not need updating every time this
  project's real artwork does.
- **A double hyphen inside an SVG comment**, twice, while authoring
  `small-icon-source.svg` — XML forbids `--` inside comment text and
  Tauri's icon generator enforces it strictly, panicking with a parse
  error rather than a readable message. Found by actually running the
  generator against the file before treating it as done, not by
  inspecting the SVG source and assuming it would parse.
- **A compounding double-opacity animation** in `jarvis-logo.tsx`'s
  first draft — a parent group and its child paths each independently
  animated `opacity` toward 1, which compose multiplicatively rather
  than additively, producing a slower, muddier fade than either
  animation alone intended. Found on review, not by observation (see
  Notes); fixed by leaving opacity solely to the paths that actually
  need it and letting the group own only the shared translate.

### Notes
- **Roadmap scope, resolved further.** Prior documentation described
  "Task Groups E–F" as an undivided Linux/macOS-packaging-and-QA block
  with the letter split undecided. Task Group E is now resolved
  specifically to Windows Packaging & Installer Distribution; that
  packaging/QA scope moves entirely to Task Group F, which absorbs
  what would have been split between the two.
- **Live browser animation verification was not possible in this
  session's environment.** The sandboxed Browser pane used for
  UI verification does not composite frames at all —
  `requestAnimationFrame` was confirmed, directly, to never fire in
  that tab — which explains why `computer.screenshot` also failed
  independent of timing. This is a property of that specific pane, not
  evidence the animation code is broken: Framer Motion's engine is
  itself driven by `requestAnimationFrame`, so nothing animated in that
  session regardless of which component was involved. What *was*
  verified without a working compositor: correct DOM/SVG structure,
  Framer Motion correctly initializing every element's `initial` state
  (including SVG-specific `transform-box`/`transform-origin` handling),
  zero console errors across several real mounts, and a careful manual
  review that found and fixed the compounding-opacity bug above. See
  `MILESTONE_REPORT.md`'s Task Group E entry for the full account.
- **Two deviations from what a strict reading of "Windows Packaging &
  Installer Distribution" would cover**, both directly instructed:
  integrating branding into the startup animation and favicon reaches
  slightly beyond "installer distribution" into general app branding;
  and file associations were evaluated and found not applicable — this
  project has no custom file format — documented as N/A rather than
  invented to fill a checklist item.

## [0.37.0] — M22 Task Group D: Universal Installation Experience

**Status: Implementation Complete — Build Verification Pending**, for
the same reason 0.36.0 carries that status: this task group adds five
commands to `src-tauri/src/installer.rs`, and there is still no Rust
toolchain on the build machine to compile them. One `tauri build`
proves both this task group's Rust and Task Group C's.

TG-D's brief listed fifteen items. The audit that preceded this release
found ten of them already real, shipped by Task Groups A–C and this
milestone's own installer UI pass: the progress framework, the download
manager UI, byte-level resume, retry-via-journal, seven-category
failure classification, and a completion screen. What was missing was
narrower — the backend already had a nine-check post-install verifier,
a `repair()` engine method, and a `status`/`verify`/`dependencies` CLI
surface, none of it wired to the frontend. This release is that wiring.

### Added
- **Five Rust bridge commands** (`check_dependencies`,
  `get_installation_status`, `verify_installation`,
  `repair_installation`, `open_log_folder`), additive to Task Group C's
  surface the same way `cancel_provisioning` was — the documented
  four-command contract is a floor, not a ceiling. Each wraps an
  **already-shipped, unmodified** CLI subcommand; zero Python files
  changed.
- **Component verification, on screen.** The completion step now shows
  all nine post-install checks, not only their warnings, each with a
  Repair button when the underlying failure is repairable.
- **Repair**, wired end to end: a click invalidates and re-runs the
  named step through the engine's own `repair()`, then **re-verifies**
  rather than trusting the repair's own result — a repair can complete
  having failed a *later* step (a blocked download) without the
  originally-failed check ever running again.
- **Installer diagnostics.** A dialog, reachable from any step, showing
  whether an installation already exists at the chosen location, its
  journal progress, a dependency report (Python, Git, CUDA, DirectML,
  ONNX Runtime, Visual C++), and the same verification-with-repair view
  the completion screen uses — reused, not duplicated.
- **Update preparation.** The wizard now detects an existing or
  partially-completed installation automatically, as soon as a location
  is chosen, and says so — "An installation already exists at this
  location. Continuing will update it — anything already set up is
  kept."
- **`open_log_folder`**, revealing the log directory Task Group C's
  logger has written to, unreachable by any UI, since v0.36.0.
- **57 new tests** (190 total in the installer suite, up from 129),
  including 13 new Rust/TypeScript contract checks and a dependency
  contract test mirroring the existing plan-payload one.

### Fixed
- **A real inconsistency, found by testing against a genuine
  partially-completed status fixture rather than only a fresh one.**
  The proactive wizard-wide notice and the diagnostics dialog's own
  "Existing installation" field checked different things — one looked
  at manifest-or-journal-progress, the other at manifest alone — so an
  interrupted install read as "found" on one screen and "none found" on
  the other for the same location. Both now call one shared
  `installationPresence()` classification (`none` / `partial` /
  `complete`).

### Notes
- **Roadmap scope, made explicit.** Prior documentation described
  "Task Groups D–F" as an undivided block of Linux/macOS packaging and
  cross-platform QA. This release resolves TG-D specifically to
  Universal Installation Experience; that packaging and QA scope is not
  dropped — it moves to Task Groups E/F, whose own letter-to-content
  assignment remains open. See `MASTER_ROADMAP.md` §19 (Roadmap
  Governance) for why this is a documented decision, not a silent
  redefinition.
- **What repair cannot yet show:** the CLI's `repair` subcommand has no
  `--stream` flag, and adding one means editing Task Group B's
  `__main__.py`, which this task group's brief reserves for a genuine
  defect. A repair that re-downloads a large artefact therefore blocks
  with an honest, indeterminate "Repairing…" state, not a percentage
  this bridge cannot produce.
- **Not verified**, same gate as v0.36.0: no `cargo build`, no
  `tauri build`, nothing in `src-tauri/` compiled. See
  `MILESTONE_REPORT.md`'s Task Group D entry for what is and is not
  proven without a toolchain.

## [0.36.0] — M22 Task Group C: Windows Packaging & Host Bridge

**Status: Implementation Complete — Build Verification Pending.**

Implements the host side of the transport contract v0.35.0 defined, and
configures the Windows installer. **Not one payload, command name or
event name changed** — the contract was written first so the UI would
need no edit on the day the host landed, and it needed none.

There is no Rust toolchain on the build machine, so nothing in
`src-tauri/` has been compiled, no `tauri build` has run, and no
installer has been produced. Ten Build Verification Tasks — build the
installer, confirm it builds, confirm the desktop and Start Menu
shortcuts, replace Tauri's default logo with real JARVIS branding
(unstarted, not just unverified), confirm installer metadata, the
uninstall entry, Launch JARVIS, Open Installation Folder, and the
provisioning bridge inside the packaged app — gate this task group to
Complete; none has run. See Notes and `MILESTONE_REPORT.md` §9
for the full list.

### Added
- **`src-tauri/src/installer.rs`** — the Windows host bridge. Spawns
  `python -m jarvis.installer`, relays stdout, captures stderr, and
  implements the four contract commands: `run_provisioning`,
  `load_installation_plan`, `launch_application`,
  `open_installation_folder`.
- **`cancel_provisioning`**, additive to the contract, plus the Cancel
  control that calls it. The UI has modelled a cancelled run since
  v0.35.0 — classifier, label, icon — with nothing able to trigger it;
  Task Group C's scope names cancellation, so the state is now
  reachable instead of decorative.
- **Interpreter discovery** — `JARVIS_PYTHON`, then a runtime bundled
  beside the executable, then the project virtual environment, then
  `PATH`. Returns "Python unavailable" rather than failing later with an
  opaque spawn error.
- **Windows packaging configuration** — NSIS target, per-user install
  (no elevation), publisher, copyright, descriptions, icons.
- **Unconditional structured logging** to the platform log directory,
  not debug-only: an installer failing on a user's machine is where a
  log is worth most, and that machine runs a release build.
- **A Rust/TypeScript contract suite** (13 tests) pinning command names,
  argument arity and the event name. It reads the Rust as *text*, so it
  needs no toolchain and runs in the ordinary `vitest` pass.
- **`tauri.conf.json` is now version-checked** against `__version__`.
  This is the first milestone producing a packaged artifact, so it is
  the first where that file's version is something a user reads — in
  Add/Remove Programs, while `/api/v1/health` reports the other one.

### Fixed
- **An inactivity timeout that could not fire.** It was checked *after*
  reading a line from stdout, so a process that hung producing no output
  — precisely the case it exists for — blocked forever in the read and
  never reached the check. stdout now feeds a channel and the loop waits
  with a timeout, which also makes cancellation prompt rather than
  dependent on the child saying something first.
- **A process that outlived the installer.** Rust's `Child` detaches on
  drop rather than killing, so closing the window mid-run left Python
  downloading gigabytes with no window and no way to stop it.
- **`launch_application` took an argument no caller sends.** Written as
  `(location: String)` while the frontend invokes it with none — a clean
  compile on both sides and a guaranteed runtime failure the first time
  a user pressed the button on the completion screen. The host now
  remembers where it installed, which keeps the documented no-argument
  contract intact. Found by the new contract suite.
- **Cancelling reported "the installer process disappeared."** The
  cancel path clears the child handle, and the exit-status branch ran
  first, so an ordinary cancel surfaced as an error — and missed the
  word "cancel" that the failure classifier matches on.

### Notes
- **`@tauri-apps/plugin-shell` was not added, and planning to add it was
  the error.** A `#[tauri::command]` spawning `std::process::Command`
  needs no plugin. The shell plugin exists to let *JavaScript* spawn
  processes — a strictly larger capability than this needs, on the
  surface with the largest attack area. The roadmap line item is closed
  by deciding against it.
- **What is unproven.** No compilation, no `tauri build`, no installer,
  no shortcut or icon observed, and the desktop/Start Menu shortcuts are
  left to Tauri's default NSIS template rather than forced through an
  untested `.nsh` hook. What *is* checked without a toolchain: both JSON
  configs parse, every referenced icon exists, the NSIS keys used are
  real keys in the bundled `config.schema.json`, and the contract suite
  above. `MILESTONE_REPORT.md` carries the full split.
- **The application icon is still Tauri's default logo**, not JARVIS
  branding — found by opening the PNG, not by checking the files exist.
  This is unstarted work, not a verification gap: it needs real artwork
  before it can even be checked.
- **Ten Build Verification Tasks gate this task group to Fully
  Complete**, none run: build the installer; confirm it builds; confirm
  the desktop shortcut; confirm the Start Menu shortcut; replace Tauri's
  branding with JARVIS's; confirm installer metadata; confirm the
  uninstall entry; confirm Launch JARVIS; confirm Open Installation
  Folder; confirm the provisioning bridge inside the packaged app. See
  `MILESTONE_REPORT.md` §9. Task Group D does not begin until all ten
  pass and that is explicitly approved.

## [0.35.0] — M22: Installer UI & Provisioning Integration

Connects the installer wizard to the provisioning engine. The engine
itself is unchanged: pytest, black, ruff and mypy are identical to
0.34.0, and TG-B's 30 engine tests pass untouched.

### Added
- **Provisioning event stream.** `provision --stream` emits
  newline-delimited JSON — one `progress` event per engine callback, then
  a final `result`. Without the flag the output is byte-identical to
  0.34.0. The brief asked the UI to "support the provisioning events
  already emitted by the backend"; those events existed only as a Python
  callback, so a UI could not show live progress for a multi-gigabyte
  download from a value it received once the download was over.
- **`DownloadState.VERIFYING`**, emitted around the checksum pass.
  Checksumming a large file takes long enough that leaving the state on
  "running" reads as a hang.
- **`kind` on `DownloadProgress`**, so the UI can group Models and Voices
  without inspecting an id it is not permitted to display.
- **Installation screen** — phase in the backend's own §22.12 wording,
  overall progress, steps, bytes, speed, time remaining, and a per-item
  download list with all seven states (waiting, downloading, checking,
  ready, already installed, failed, cancelled), each carried by text
  *and* an accessible label rather than by colour.
- **Resume, failure and completion screens.** Failures map the engine's
  own error text onto the seven required categories and show copy that
  names no internal cause — "Connection lost", never "URLError". Retry
  is worded "Continue installation" because the journal makes it a
  resume.
- **`/install` route.** TG-A and TG-B left the wizard mounted nowhere.
  It sits *outside* `DesktopShell`: rendering an installer inside the
  sidebar and header of the application it is installing is incoherent
  and invites navigating away mid-run.
- **Host-bridge contract** (`provisioning-transport.ts`) — see Notes.

### Fixed
- **A React render loop.** `selectDownloadsByKind` built a new object per
  call, and zustand compares selector results by reference, so using it
  as a hook selector made every render look like a state change until
  React aborted with "Maximum update depth exceeded". Grouping is now a
  `useMemo` over the stable array.
- **`defaultLocation` defaulted to `""`**, permanently disabling
  Continue on the Location step with no explanation. The route now
  proposes `%LOCALAPPDATA%\JARVIS` (or `~/.jarvis`), and the step says
  "Enter a folder to continue" while the field is blank.
- **A group headed "Local AI" containing an item also called "Local
  AI"** — groups renamed to Models / Voices / Assets.

### Notes
- **Speed and time remaining are derived in the UI, not emitted by the
  engine.** A rate is a property of an observer over an interval, not a
  fact about a download; a stopwatch in the engine would report
  different numbers to two consumers. They are derived from the
  authoritative byte counts, smoothed over 3s, and are `null` rather
  than `0` until there is signal — "0 B/s" reads as stalled where "—"
  reads as not yet known.
- **The host bridge is intentionally deferred to Task Group C.**
  `@tauri-apps/plugin-shell` is not a dependency and no Rust command
  exists to spawn the Python process. Rather than adding a dependency to
  make a screen look finished, the transport *defines the contract* — one
  command (`run_provisioning`), one event (`provisioning://event`) — and
  rejects with a readable reason when the host cannot provide it, which
  the failure classifier turns into friendly copy with a Retry. A stub
  that resolved quietly, or emitted invented progress, would make the
  installer look complete while installing nothing.
- **81 tests added**, including a contract suite driven by a *captured
  real stream* rather than a hand-written approximation, and assertions
  that no model id, registry key or URL reaches a personal payload.

## [0.34.0] — M22 Task Group B: Runtime Provisioning

Task Group A planned an installation; this performs one. Dependency
detection, a resumable checksum-verified download manager, a durable
provisioning journal, parallel verification, first-run preparation and an
`installation.json` manifest — behind one engine that is simultaneously
install, resume and repair.

The success path runs end to end: a real provisioning against a `file://`
mirror completes all eight steps and writes a manifest; a second run
skips all eight.

**Backend untouched.** No route, model, schema, event or contract
changed; the installer package still imports no service, repository or
container.

### Added
- **`sources.py`** — download-source abstraction. **No URL exists
  anywhere in the package.** The registry ships empty: with nothing
  configured it names the environment variable to set rather than
  falling back to a vendor host, because a silent fallback would defeat
  the abstraction on the one path that matters.
- **`download.py`** — queued, **byte-level resumable** (HTTP `Range`),
  checksum-verified downloads with pause, cancel, retry and source
  failover. A file lands in `.part`, is verified there, and is renamed
  last — so a file under its final name is *by construction* one that
  passed.
- **`dependencies.py`** — Python, Git, Visual C++, CUDA, DirectML, ONNX
  Runtime. It has **no code path that writes**, which is how "never
  silently overwrite" is enforced rather than merely promised.
- **`journal.py`** — durable, fsynced, atomically-replaced provisioning
  record. Only *completions* are written, so an interrupted step is
  re-run and a finished one skipped.
- **`verification.py`** — nine checks in parallel; **`manifest.py`** —
  `installation.json` as the migration contract; **`first_run.py`**,
  **`provisioning.py`**, **`atomic.py`**.
- CLI: `dependencies`, `provision`, `verify`, `repair <step>`, `status`.

### Fixed *(all four found by running it end to end)*
- **A model id is not a filename.** `qwen2.5:14b` is a valid registry id
  and an impossible Windows filename — NTFS reads the colon as a drive
  qualifier — so every model download would have failed on the primary
  platform. `key` now addresses the source; `filename` is the sanitised
  on-disk name, and sources gained a `{filename}` placeholder because a
  `file://` mirror cannot store a file named after the raw key.
- **The same confusion, a second time:** verification looked artefacts up
  by `key` while the downloader wrote them under `filename`, reporting a
  correctly-downloaded model as missing.
- **A source spec that looked like it worked.** Commas separated both
  entries and `kinds`, so `mirror|url|model,voice|0` split into a
  model-only source plus an unparseable fragment — model downloads
  worked, voice downloads found no source. Entries are now
  semicolon-separated.
- **A §22.12 leak in the progress payload**: personal progress carried
  the model id. It now carries a display name; the id is
  administrator-only.

### Notes
- **There is no separate resume command.** `provision` skips whatever the
  journal records as complete, so resuming *is* running it again — a
  resume on its own code path would be the least-exercised and most
  often broken.
- **Unverifiable is not verified.** No upstream source is wired, so no
  checksums are published; downloads are reported as *present but
  unverifiable* rather than as verified.
- **The installer does not create the database schema.** It prepares the
  location; the application's `initialize()` creates the schema on first
  launch through the frozen code that owns it.
- **No packaging** — no MSI, EXE or code signing, per the brief.
  *(Superseded by 0.35.0: this entry originally said the wizard's Install
  step was unchanged and that wiring it required the Tauri bridge. The
  wiring shipped in 0.35.0 without that bridge — the UI reaches the
  engine through an injected transport, and only the transport's host
  implementation waits on packaging.)*
- Ruff rose to 33 categories on the new code and was brought back to the
  21-category baseline — `StrEnum`, an `Error` suffix, a named opener,
  `ClassVar` annotations, and a shared `atomic.py` that removed two
  `SIM115` violations by removing the duplication behind them.

## [0.33.0] — M22 Task Group A: Universal Installer Foundation

The installer experience and the hardware calibration that drives it.
Eleven-step wizard, real hardware detection, an AI Capability Score, a
local-model recommendation, a voice plan and seven pre-installation
checks — verified against this machine's actual hardware.

**Backend untouched.** The installer is a new, isolated package that
imports no service, no repository and no container. It has to be: it
runs *before* JARVIS is installed, on a machine where none of those
exist yet. No route, model, schema or contract changed.

### Added
- **`src/jarvis/installer/`** — hardware detection (CPU, RAM, storage,
  GPU/VRAM, battery, temperature, internet, NPU), AI calibration,
  model tiers, voice planning and pre-flight validation. Zero mypy
  errors across seven new modules.
- **`python -m jarvis.installer`** — a JSON-emitting CLI (`detect`,
  `plan`, `validate`). **A CLI rather than a REST route**: an installer
  cannot call an API served by the application it is installing, and
  adding a route would have modified a frozen contract.
- **`src/features/installer/`** — the eleven-step wizard, its store, and
  types pinned against real CLI output by a contract test.

### Fixed *(all three found by running on real hardware)*
- **Free space was measured on the wrong drive.** `detect_storage` fell
  back to the current working directory when the target did not exist —
  which is the *normal* case during installation. On Windows the
  installer is routinely launched from a different volume, so a machine
  with a full target drive would have passed the disk-space check.
- **A 16 GB machine could never reach the 16 GB tier.** RAM is sold in
  decimal GB: a "16 GB" machine has 16 × 10⁹ bytes = 15.7 *GiB*.
  Comparing against a binary threshold meant every 16 GB machine missed
  its tier and was offered the 8 GB one. Detection on this laptop
  returned 15.7 and recommended Small.
- **The wizard's scan effect cancelled every scan it started.**
  `beginScan()` sets `scanning`, which was an effect dependency, so
  starting a scan re-ran the effect, whose cleanup cancelled the request
  it had just started — and the guard then refused to retry. Replaced
  with a request-id ref.
- The Location step's Continue was dead unless the user retyped the path
  already shown; each account card's accessible name was ~40 words and
  ambiguous between the two options.

### Notes
- **The governing rule:** a field is either measured or `null` — never
  estimated or defaulted to something plausible. The UI renders "Not
  detected", `notes` explains why, and `missing_inputs` records what the
  recommendation did not know. On this machine three fields came back
  `null` (no temperature sensors on Windows, no probeable GPU) and the
  installer says so rather than showing zeros.
- **§22.11/§22.12 are enforced at the payload**, not in the UI: a
  personal plan genuinely does not contain model ids, score components,
  resource limits or provider names. A test asserts the serialised
  personal payload contains none of `piper`, `whisper`, `elevenlabs`,
  `llama`, `qwen`, `openai`, `gemini`, `groq` — and that it still
  carries everything that affects the user.
- **Nothing is downloaded, and no installation is performed.** The
  modules know no download URL at all. The Install step says so on
  screen rather than animating a progress bar that measures nothing;
  Test Voice and Launch JARVIS are disabled with a reason on hover.
  Windows packaging (MSI, shortcuts, auto-start, portable, signing) is
  Task Group B.

## [0.32.0] — M8 Phase 7: Production Readiness

An audit milestone, run against a **live backend** rather than by
reading code — the real FastAPI app with a real DI container and a real
health poll, driven from the React client, with the backend killed
mid-session and restarted.

That found **four defects code review had missed**. No new
functionality; no backend change beyond the version constant.

### Fixed
- **Version drift, three releases deep.** `GET /api/v1/health` reported
  `0.28.0` while `pyproject.toml` said `0.31.0` —
  `src/jarvis/__version__.py`, whose docstring calls itself "single
  source of truth for the package version", had not been bumped since
  v0.28.0. That constant is what the health endpoint returns and what
  `jarvis --version` prints, so an installation was misreporting its own
  version by three releases. Both now `0.32.0`, with
  `tests/unit/test_version_consistency.py` asserting they can never
  diverge again — nothing compared them before, which is why they drifted.
- **A dead-end user journey.** Five dashboard widgets shipped in Phase 5
  say "Bind this workspace to a JARVIS workspace to see its tasks", and
  no control anywhere could do it: `bindBackendWorkspace` had only tests
  calling it and `workspacesApi` had no caller at all. The binding
  control now exists in the workspace toolbar, wiring the store action,
  the typed endpoint and the widgets that were already built.
- **A status selector reporting a fault that did not exist.** Memory and
  Knowledge Graph showed Degraded amber on a healthy system:
  `selectSourceStatus` conflated "the collector is not reporting at all"
  with "it is reporting and this source is missing". Only the second is
  a degradation.
- **Two stories for one condition.** While offline the health widgets
  said "Waiting for the backend to report…" — implying a report was
  coming — beside REST-backed widgets correctly saying "Offline".
- **A footgun in the shared fetch hook.** `useBackendResource`'s default
  emptiness check did not understand the `Page<T>` shape most endpoints
  return, so empty collections rendered as an empty list rather than an
  empty state. Three callers had already worked around it; a fourth
  forgot. Fixed at the default and the workarounds deleted.

### Added
- **An executable guard for `ARCHITECTURE.md` §22.12.**
  `restricted-surface.test.ts` scans every source file: any module
  reading provider names, routing or debug state must also consult the
  audience gate. The behavioural tests check *existing* surfaces; this
  catches a **new** one added later that never gets a gate — precisely
  how the Phase 3 Activity Center leak survived a milestone.
  Mutation-tested: removing a gate makes it fail by filename.

### Removed
- `healthApi` (a stub documenting a decision a comment documents
  better), `useWideLayout`/`WIDE_MIN_WIDTH` (never called), and
  duplicated skeleton markup. Each verified as having zero importers.

### Notes
- **Verified live:** real health values flowing over `health.updated`;
  **no stale numbers survive a backend outage** (the pre-outage snapshot
  is dropped, not shown as current); **automatic reconnection without a
  page reload**; "connected but no snapshot yet" correctly distinguished
  from offline.
- **TanStack Query is mounted and never used** — no `useQuery` anywhere
  — costing 24.5 kB (7.28 kB gzipped) in the initial bundle. Flagged
  rather than removed: dropping an approved dependency is an
  architecture change this milestone forbids.
- **Not done, and it matters:** no cross-browser testing (Chromium
  only — the Tauri shell uses WebKit/WebView2), no screen-reader pass,
  no contrast-ratio measurement.
- **Eleven modules remain placeholders.** The brief asked to confirm "no
  placeholder routes for completed modules"; the accurate finding is
  that those modules are *not completed*, so their placeholders are
  correct rather than a regression.

## [0.31.0] — M8 Phase 5 + Phase 6: Module Integration & Production UX

Phase 5 turned the workspace into the JARVIS operating environment;
Phase 6 hardened it. Delivered as one milestone.

**Backend untouched** — no route, model, schema, event or contract
changed. pytest, black, ruff and mypy are byte-identical to v0.30.0,
which is the evidence rather than the assertion that the freeze held.

**The milestone began with an API audit, and the audit changed the
plan.** All 172 REST operations the frozen backend exposes were
enumerated before any UI was written. Three findings shaped everything
after.

### Added
- **AI Dashboard — 11 widgets, every one on real backend data**, joining
  the *existing* `dashboardWidgetRegistry`: System Overview, Subsystem
  Status, Performance, Knowledge Graph, Suggestions (M10B's real
  engine), Recent Tasks, Projects, Pinned Notes, Recent Files, Upcoming
  Calendar, Notification Summary.
- **Developer Dashboard** (Developer Mode only) — providers & routing,
  outbound API counters, API inspector, performance metrics, agent
  trace, the relay's 61-event vocabulary, runtime state.
- **Administrator Dashboard** (Administrator only) — six panels with a
  real API, plus one naming the seven that have none.
- **Plugins** and **Diagnostics** panels, joining the existing
  `panelRegistry`.
- **`core/user-mode.ts` + `stores/user-mode.store.ts`** — one audience
  gate for §22.11/§22.12: three modes, seven restricted classes of
  information. Derived from Developer Mode's existing session unlock
  rather than a second flag; two flags that can disagree about whether
  provider names may be shown will eventually disagree permissively.
- **`useBackendResource` + `ResourceView`** — one fetch hook and one set
  of honest loading / empty / offline / error states, replacing what
  would have been fifteen hand-rolled `useEffect` triples. Connection
  recovery is free at the widget level because `isLive` is a dependency.
- **Skeleton loaders** shaped like the content they replace, not a
  generic grey box that makes the layout jump.
- **`installConnectionRecovery()`** — re-runs ping → session → socket.
  The socket's own retry reuses a token that a *restarted* backend will
  refuse forever, which is the most common real outage.

### Fixed
- **A §22.12 leak shipped in M8 Phase 3.** The Activity Center rendered
  `agent.step`'s raw `node` field — `planner`, `tool_executor`,
  `critic` — to every audience. The Phase 3 milestone report flagged it
  as a gating requirement before a personal-user build ships; this is
  that gate. Personal users now see §22.12's mandated progress
  vocabulary, with step count, ordering and status identical in both
  modes — fewer *words*, not less truth.

### Notes
- **`GET /health` is a bare liveness probe** (`{status, version}`). The
  rich subsystem data every "… Status" widget needs is published as the
  `health.updated` **WebSocket** event, which nothing on the frontend
  was reading. The dashboards subscribe rather than poll — no new
  endpoint, and the numbers move on their own.
- **Seven Administrator panels have no backend and are named, not
  mocked**: users, daily/monthly budgets, provider priority, calibration
  status, analytics, synchronization. All are `ARCHITECTURE.md` §22 —
  approved and not built. An administrator seeing "Budget: $0.00" would
  reasonably conclude nothing had been spent.
- **Two AI Dashboard widgets from the brief have no data source.**
  *Recent Conversations* — no conversation-history route exists.
  *Pinned Projects* — `Project` has no `pinned` column; `Note` and
  `Workspace` do, so **Pinned Notes** ships in its place and projects
  surface by their real `status` field.
- **Provider Status moved to the Developer Dashboard.** Real data, but
  §22.12 puts provider names off-limits to personal users. That is the
  architecture decision winning over the brief's widget list,
  deliberately.
- **Six separate "… Status" widgets ship as one.** They share a data
  source and a presentation; six cards showing one light each would be
  six copies of four lines, and worse for the question a user actually
  asks.
- **Two gates, not one.** Restricted panels are filtered from the panel
  menu *and* refused by the dashboard components — a workspace layout
  can be exported from a developer's machine and imported on a personal
  one. This is a render gate, not a security boundary: the backend
  authenticates, the frontend decides what to show.
- **A correction to the Phase 3 report**, which claimed the Status Bar's
  "AI Provider" item names a provider. It does not — it renders "Not
  configured" and never leaked.

## [Unreleased] — Documentation: approved architecture decisions

Documentation only. **No application code changed** — no backend, no
frontend, no version bump. The application version stays `0.30.0`;
`MASTER_ROADMAP.md`'s own document version moves 3.0 → 3.1.

Records eighteen approved architecture decisions as the binding target
architecture, and the development freeze that accompanies them.

### Added
- **`docs/ARCHITECTURE.md` §22 — Approved architecture decisions (Aug
  2026)**, eighteen subsections covering Local AI First (§22.1), the
  Universal AI/API Calibration Engine (§22.2), the AI Cost Optimizer
  (§22.3), the three-tier AI strategy (§22.4), the Oracle Cloud role
  (§22.5), the voice platform (§22.6), AI providers (§22.7), hardware
  calibration (§22.8), the Universal Performance Engine (§22.9), the
  installation platform (§22.10), Personal/Administrator accounts
  (§22.11), hidden backend operations (§22.12), cross-agent
  collaboration (§22.13), the AI Health Dashboard (§22.14),
  cross-platform distribution (§22.15), JARVIS Core Intelligence's
  deferral (§22.16), recommended free infrastructure (§22.17), and where
  the rest gets built (§22.18).

### Changed
- **`docs/MASTER_ROADMAP.md`** — the development-policy freeze at the
  top; a note at the head of §8 Future Roadmap making §22 binding across
  every milestone; §13 AI Provider Roadmap reframed as available
  providers reached *through* the Calibration Engine rather than a
  selection menu; **Cross-Platform Distribution added to M22**, filed
  there because the OS abstraction layer is the same substrate M22's
  hardware backends need.
- **`docs/IMPLEMENTATION_ROADMAP.md`** — the same freeze, stated as a
  pre-flight check before starting a phase, plus an explicit note that
  none of §22 is in any checklist in that document.
- **`README.md`** — a pointer to §22 and the freeze.

### Notes
- **Approved is not built.** Every decision in §22 is signed off as the
  target architecture and **none of it exists in code**. The section is
  written as a contract for future work, and says so in its first line,
  so it cannot be misread as a description of the running system.
- **Two places where §22 constrains what already exists** are called out
  rather than left to be discovered later: today's configuration-driven
  provider selection (`JARVIS_LLM_DEFAULT_PROVIDER`) becomes an *input*
  to the Calibration Engine rather than a competing mechanism (§22.1);
  and the Status Bar's "AI Provider" item plus the Activity Center's
  agent node names both leak routing detail that §22.12 forbids to
  personal users — acceptable while Developer Mode is the audience, and
  now a tracked gating requirement before a personal-user build ships.
- **Nothing was scheduled** beyond M22. The rest awaits milestone
  assignment under `ARCHITECTURE.md` §20's governance process;
  `MASTER_ROADMAP.md` stays the single source of truth for sequencing.

## [0.30.0] — M8 Phase 3: Universal Workspace Framework

Panels. The frontend gains a dockable, resizable, persistable workspace
in which any module's content can sit alongside any other's, plus the
three shell-level panels that framework existed to make possible.

Backend untouched: no route, model, schema or contract changed. Every
Python gate is byte-identical to v0.29.0's, which is the intended result
of a frontend-only milestone rather than a coincidence.

### Added
- **Universal Workspace Layout** — four dock zones (`left`, `main`,
  `right`, `bottom`) plus a floating layer, each zone collapsing out of
  the layout entirely when empty, so a one-panel workspace looks like a
  single-pane app rather than a grid with three blank cells.
- **Panel system** — every panel supports the seven required operations:
  open, close, resize, collapse, detach, move, restore.
  `core/panel-registry.ts` is a `ContributionRegistry` instance, not a
  fourth hand-rolled registry — the generic mechanism exists for exactly
  this.
- **Multi-workspace support** — create, rename, delete, duplicate, reset,
  import, export, switch, and restore-on-launch. Layouts persist to
  `localStorage` under the established `jarvis.<name>` key convention.
- **Notification Center** — the persistent panel over
  `core/notification-framework.ts`'s already-real data. Listed in
  `IMPLEMENTATION_ROADMAP.md` Phase 3 and deferred since Phase 1 because
  it had nowhere to live; `notification-layer.tsx` has been a reserved
  `return null` anchor all along. The header's notification bell finally
  has a handler, for the same reason.
- **Activity Center** — one timeline merging background tasks, `agent.step`
  and `automation.step`. It merges live store reads rather than keeping a
  fourth copy of the same facts.
- **Global Search** — backed by the real `POST /api/v1/search` (M10A's
  13 registered sources). Distinct from the Command Palette, which
  navigates the app locally and instantly; this searches content over the
  network, and says so plainly when the backend is unreachable rather
  than returning an empty list that looks like "no results".
- **Responsive layout** — `hooks/use-responsive-layout.ts` shares the
  Sidebar's existing 768px breakpoint. Below it the rails are dropped and
  `main` fills, rather than three rails being squeezed to unusability.
- **Performance** — route splitting (`routes/lazy-routes.ts`), lazily
  imported panels, `<Suspense>` at both boundaries with one shared
  fallback, `memo` on `PanelFrame`, and `components/common/virtual-list.tsx`
  for the two unbounded lists. The build now emits eight feature chunks
  where it previously emitted one bundle.

### Notes
- **"Workspace" now means three things, deliberately kept apart.**
  `WorkspaceManager`/`workspace.store.ts` is which *module* the route has
  mounted; the backend `Workspace` (M11 Task Group A) is a data scope
  owning projects, notes, tasks and files; and this phase's
  `workspace-layout.store.ts` is a named *arrangement of panels*. The
  third links to the second through `backendWorkspaceId` — an id, never a
  copy of backend data — and does not touch the first.
- **Layouts persist locally, and that is not a compromise.** There is no
  endpoint for panel geometry and the backend contract is frozen; a
  layout is also genuinely per-device state, since an arrangement that
  suits a 34" monitor is wrong on a laptop.
- **Detached panels float inside the viewport, not in OS windows.** A
  real second window needs Tauri's multi-window API — its own React root,
  store bridge and IPC — which is `IMPLEMENTATION_ROADMAP.md` Phase 3's
  separate, still-open "Window management" item. The store's `frame`
  geometry is already in the shape that work would need.
- **Nine modules deliberately register no panel.** Conversation, Memory,
  Automation, Files, Browser, Coding, Finance, Smart Home, Calendar,
  Gmail and Spotify still render `PlaceholderRoute` — they have no real
  content. Wrapping "this module hasn't been built yet" in a title bar
  with resize handles would dress an unbuilt module up as a working one.
  They register on the day they have something to show; the framework
  needs no change when they do.
- **`skipHydration` on the layout store.** Zustand rehydrates on import,
  which can precede panel registration; since rehydration drops panels
  whose contribution is unknown, a layout restored at that moment would
  come back empty and the user would have lost their arrangement to an
  import-order accident. The startup sequence registers panels and *then*
  rehydrates, explicitly.

## [0.29.0] — M8 Phase 2: Universal Application Framework & Logic

The React client stops being a self-contained shell and starts talking to
the Python process. Most of this phase was not writing new frameworks —
Phase 1 built those — but connecting them to a backend that had moved on
underneath them, and finding that in three places the client's idea of
the backend was simply wrong.

**The recurring defect: a client written against the spec, not the
server.** Phase 1 shipped its REST and WebSocket layers before the
backend routes existed, using `ARCHITECTURE.md`'s illustrative examples
as the contract. The examples were illustrative. Every drift below is the
same mistake, and the fix is the same idea in each case — assert against
the running server, not the document.

### Security
- **`SettingsService.snapshot()` leaked OAuth client secrets.** Pydantic
  redacts a `SecretStr` on dump, which covers `openai.api_key` and its
  neighbours. It does not cover a secret inside a plain container, and
  `integrations.clients` (added by M11 Task Group E) is a
  `dict[str, dict[str, str]]` whose `client_secret` entries dump
  verbatim. The leak was latent — the only caller was the in-process
  PySide6 Configuration Manager — but adding a settings API is precisely
  the change that would have made it live, and it would have shipped a
  route that published Google OAuth client secrets to any authenticated
  caller. `public_snapshot()` now redacts by *key name* (the only check
  that catches a secret whose type says nothing about it), and the REST
  route serves that and never `snapshot()`. Two methods rather than one
  with a flag, matching `Credential.to_storage_dict`/`to_public_dict`:
  a method callers must remember to sanitise is one somebody forgets.

### Fixed
- **Eleven of the client's fourteen WebSocket event names did not
  exist.** `ai.token`, `ai.step`, `ai.complete`,
  `voice.transcript_partial`, `voice.transcript_final`,
  `automation.step_started`, `automation.step_completed`,
  `automation.workflow_finished`, `progress.update`,
  `notification.created` and `runtime.module_state_changed` were never
  emitted by anything. A handler registered for any of them would never
  fire — silently, with no error anywhere. The vocabulary is now the real
  61 names from `EVENT_TYPE_NAMES`, and three of the six payload
  interfaces this phase types had wrong field names too
  (`AutomationStepPayload` and `PluginNotificationPayload` were
  invented; `UpdatePhasePayload` was missing `session_id`).
- **The REST client discarded every error message the backend sent.** It
  understood only the `{"error": {...}}` envelope from `ARCHITECTURE.md`
  §9, which no route produces — every route raises `HTTPException`, which
  serialises as `{"detail": "..."}`. So a real "Workspace not found"
  surfaced as "Request failed with status 404". Both shapes are handled,
  `detail` first because it is the one that occurs.
- **The REST client expected cursor pagination.** It read
  `meta.next_cursor`; the backend ships offset paging
  (`{count, limit, offset, has_more}`) as of M11 Task Group F, which
  recorded that divergence rather than hiding it. `apiList` follows the
  server.
- **A 2xx with a non-envelope body threw a bare `TypeError`** from inside
  the client, naming nothing. It now raises `MALFORMED_RESPONSE` naming
  the route, and flows through the normal error path. Found by a test.
- **`notification.created` in `notifications.store.ts`** — a comment
  documenting an event that has never existed. The real one is
  `notification.plugin`.

### Added
- **A generated WebSocket contract, asserted from both sides.**
  `scripts/export_ws_contract.py` writes
  `frontend/src/services/websocket/event-contract.generated.json` from
  `EVENT_TYPE_NAMES` and each event's dataclass fields.
  `tests/unit/test_ws_contract_export.py` fails if the checked-in file is
  stale; `websocket-contract.test.ts` fails if the TypeScript disagrees
  with it. Neither side can drift without something going red — which is
  the only durable fix for the class of defect above.
- **`GET /api/v1/settings` and `/api/v1/settings/{dotted_key}`** —
  read-only, session-authenticated, `{data, meta}` envelope, secrets
  redacted. Read-only deliberately: writing a setting means writing
  `.env`, which is a privilege-escalation surface belonging with M14's
  Security Platform, not with a frontend phase whose job is to read real
  values.
- **Frontend service layer** — `services/api/client.ts` (typed REST,
  configurable base URL via `VITE_API_BASE_URL`),
  `services/api/session.ts` (the authentication flow; the token is
  deliberately not persisted), `services/api/endpoints.ts` (typed
  helpers for every M9–M11 surface the client reads),
  `services/backend-connection.ts` (the ping → session → socket
  ordering, in one place), `services/realtime-bridge.ts` (every
  WebSocket subscription, installed once at startup rather than inside
  component effects), `services/permissions-sync.ts`,
  `services/error-reporting.ts`.
- **Stores and hooks** — `connection.store.ts`, `settings.store.ts`,
  `agent-activity.store.ts`, `use-backend-status.ts`.
- **`npm run typecheck`** as a permanent quality gate. It runs
  `tsc -b --noEmit`, not `tsc --noEmit`: the root `tsconfig.json` is a
  solution file (`"files": []`), so plain `tsc --noEmit` type-checks zero
  files and exits 0 — a gate that always passes. Verified with
  `--listFilesOnly` before choosing build mode. It caught six real errors
  on its first run.

### Notes
- **Offline is an explicit state, never fake data.** `BackendState`
  distinguishes `unreachable` (the process is not answering) from
  `unauthenticated` (it is, but refused a session), because collapsing
  them produces a UI that says "something went wrong" when the truth is
  "JARVIS isn't running". A failed request while offline deliberately
  does *not* toast — the condition is already on screen persistently.
- **Permissions are surfaced from M9's `PermissionModel`.** The roadmap
  files this under "the backend's Authorization Engine (M14)"; M14 does
  not exist. The Authorization Engine that does exist owns the same
  ten-scope vocabulary `core/permission-framework.ts` already mirrors, so
  Phase 2 surfaces that one and `services/api/endpoints.ts` is the single
  place that repoints if M14 supersedes it.
- **Storage needed no new work.** `core/storage-framework.ts` already
  implements the four sensitivity tiers ARCHITECTURE.md §12 specifies,
  including refusing client-side encryption rather than pretending to
  offer it. Verified, not rebuilt.
- **The "API Integration Rework" sub-block is not included.** Those ten
  items (Real API Activation, Provider Registry, Runtime Provider
  Registration, failover, …) are backend provider-lifecycle work tied to
  M11's API Center Architecture module, not frontend framework work, and
  they are not honestly completable in this phase. They remain unchecked
  in `IMPLEMENTATION_ROADMAP.md` with this note.

## [0.28.0] — M11 Task Group F: Platform Integration & Closure

An audit of every cross-cutting surface M11 built, and the fixes the
audit turned up. Four defects were real; the rest of the platform was
already consistent, and this entry says which is which rather than
implying everything needed work.

**What was audited, with evidence.** 170 REST routes, 1 WebSocket route,
66 event classes, 88 DI providers, 13 search sources, 37 settings
sections. Findings are pinned as tests in
`tests/unit/test_platform_integration.py`, so the invariants cannot
quietly regress.

### Security
- **A session could be read and closed by anyone who learned its id.**
  `GET`/`DELETE /api/v1/sessions/{id}` took the id in the URL path and
  required nothing else — but a session id *is* the Bearer token for
  the rest of this API, so anyone who saw one in a proxy log, a browser
  history entry or a `Referer` header could confirm it was live and,
  worse, close it, logging the real holder out. Both routes now require
  the Bearer token **and** check it names the same session as the path.
  A caller can only read or close its own. Cross-session access returns
  `404`, not `403`, so a valid token for one session cannot be used to
  discover whether another exists. (RFC 6750 §2.3 is the general rule
  this violated.)

### Fixed
- **Collections truncated silently.** Every repository already capped
  its queries (200 on the workspace tables, 500 on files and links),
  nothing above them exposed the cap, and `meta` reported only `count`
  — so a workspace holding 250 notes returned 200, said `"count": 200`,
  and gave the caller no way to tell a complete answer from a truncated
  one nor any way to reach the rest. The cap was right; its invisibility
  was the bug. All nine M11 collections now take `limit`/`offset` and
  report `{count, limit, offset, has_more}` through one shared helper
  (`infrastructure/api/pagination.py`), not a parameter invented per
  router.
- **`memory_recall_hook` was registered twice in the DI container.** An
  earlier `NoopMemoryRecall` binding that the real
  `SemanticMemoryRecallHook` silently replaced. Behaviour was correct —
  the last binding wins — but a reader following the first one would
  have concluded the chat pipeline ran with recall disabled. The dead
  registration and its now-unreferenced factory are gone.
- **M11's subsystems reported nothing to `HealthMonitor`.** Task Groups
  A–E shipped five subsystems and none of them appeared in `/health`,
  in the `health.updated` relay, or in Developer Mode: a file storage
  root that had become unwritable, or an integration gateway failing
  every outbound call, was invisible. One new collector
  (`workspace_platform`) closes that on the extension point that
  already exists.

### Added
- `infrastructure/api/pagination.py` — `Page`, `page_params`,
  `page_meta`. Over-fetch by one to answer `has_more` exactly, rather
  than a `COUNT(*)` beside every listing that would double the queries
  and still be racy.
- `offset` on the nine list repositories that already took `limit`, and
  `limit`/`offset` pass-through on their services.
- `tests/unit/test_pagination.py` and
  `tests/unit/test_platform_integration.py` — the audit invariants as
  tests.

### Notes — what the audit found already correct
These were checked and needed no change; they are recorded so a future
audit knows they were verified rather than skipped:
- **Auth coverage.** 170 routes; exactly six are session-free, and all
  six are deliberate: `/health`, `/ready`, `POST /sessions` (how a token
  is obtained), the two session routes above (now token-checked), and
  the OAuth callback (a browser redirect carries no header; its
  single-use `state` is the defence).
- **Response envelope.** Every resource route returns `{data, meta}`.
  The five exceptions are `/health`, `/ready` (flat by design for
  probes) and `/agent/stream` (SSE).
- **Error handling.** 14 probes across every M11 domain: unknown id →
  `404`, invalid input → `400`, zero deviations.
- **Events.** 66 declared, 61 relayed, 5 absent and all 5 on the
  documented exception list. No duplicate relay names; every name is
  `<category>.<event>` lowercase; every relayed event is really
  published.
- **Search.** 13 sources, each registered exactly once, none missing —
  and every service `search*` method sits behind exactly one of them.
- **Dependency injection.** 88 providers, 84 singletons and 3 factories
  (all deliberate), no two providers building the same target.
- **Settings.** 37 sections, every one under `JARVIS_`, no duplicate
  prefixes, every one constructible from defaults — so a fresh install
  with no `.env` starts.
- **Workspace isolation.** Cross-workspace writes are refused with a
  `400` naming the reason: a note cannot join another workspace's
  project, a file cannot attach to another workspace's task, and
  workspace-scoped listings do not leak.
- 49 new tests (2136 → 2185). mypy 263 → **262** (the deleted legacy
  factory carried an untyped parameter), ruff 21 categories unchanged.

### Remaining
- **The React/Tauri workspace UI is not built.** The original M11 Task
  Group F brief paired "UI Integration" with "Platform Closure"; the
  frontend half belongs to M8, which is deferred, and this task group
  delivered the backend integration only. No UI work is claimed.
- OpenAPI descriptions are uneven — routes carry docstrings where the
  reasoning mattered and not elsewhere. Cosmetic, and mass-adding
  summaries would be noise rather than documentation.

## [0.27.0] — M11 Task Group E: Integration Platform

The outbound half of M11: OAuth2, one audited egress point, and vendor
connectors that run as MCP providers. Built entirely on M10.5's MCP
platform — every connector is registered in the same provider registry,
driven by the same lifecycle, gated by the same permission model and
reported by the same health collector.

Google Workspace ships (11 integrations, 65 operations). Phases 2–6 of
the brief are catalogue entries against the same engine and are **not**
built — see Notes.

### Added
- **OAuth2, closing M10.5's deferral** — `core/mcp/auth/oauth2.py`: the
  authorization-code grant with **mandatory PKCE** (S256), the
  client-credentials grant, `OAuthFlowStore` (single-use, expiring
  `state`; the PKCE verifier never leaves the server), and
  `BoundOAuth2Strategy` for per-provider refresh and remote revoke. Both
  register into the **existing** `AuthStrategyRegistry` — the one call
  Task Group D's docstring predicted.
- **API Gateway** — `core/integrations/gateway.py`: the single audited
  egress point. One `httpx` pool, retry for idempotent methods only,
  bounded `Retry-After` handling, and a short account-keyed response
  cache that any mutation invalidates.
- **Connectors as data** — `core/integrations/models.py`:
  `IntegrationSpec` / `OperationSpec` / `AuthSpec`, validated at
  registration, with path rendering and parameter splitting as the
  security boundary.
- **`RestIntegrationProvider`** — an `IMCPProvider` for vendor REST
  APIs. Same `MCPProviderRegistry`, same `MCPProviderManager`, same
  events, same `MCPCapabilityRegistry`, same `PermissionModel`, same
  health collector.
- **Google Workspace (Phase 1)** — Gmail, Calendar, Meet, Drive, Docs,
  Sheets, Slides, Contacts, Tasks, Keep, Photos.
- **`IntegrationService`** — catalogue, install, the two-step OAuth
  flow, invoke, preview, per-vendor search, gateway stats.
- **REST** — `/api/v1/integrations/*`: catalogue, install/uninstall,
  connect/disconnect, `oauth/authorize`, `oauth/callback`,
  `invoke`, `preview`, `search`, `gateway/stats`.
- **Search** — one `ISearchSource` per connected integration, added to
  M10A's registry on connect and removed on disconnect. No change to
  `SearchService`.
- **Agent tools** — `list_integrations`, `describe_integration`,
  `search_integration`, `invoke_integration`, on the existing registry.
- **Event** — `IntegrationCallCompletedEvent`, relayed as
  `integration.call_completed`.
- **Settings** — `JARVIS_INTEGRATIONS_*`, including per-vendor OAuth
  clients (`CLIENTS__GOOGLE__CLIENT_ID`) and the redirect URI.

### Changed
- **`MCPProviderManager.install` gained an optional `provider=`** — the
  seam `core/interfaces/mcp.py` promised in prose, made real by the
  first integration that needed it. Defaulted, so every existing call
  site is unchanged.
- **`MCPAuthManager` gained `auth_header`, `needs_refresh` and
  `bind_strategy`.** The first is the single sanctioned route a token
  takes out of the auth subsystem (a formatted header, never a bare
  token). The last exists because the shared registry keys on *method*
  while OAuth2 refresh needs a token endpoint and client id —
  configuration, which a `Credential` deliberately does not carry.

### Fixed
- **`IntegrationError` reached the REST layer as a 500.** An undeclared
  parameter or a duplicate install was refused correctly but reported
  as a server fault. `IntegrationService` now translates the `MCPError`
  family into `ServiceError` at the boundary, through one context
  manager rather than a try/except per method — the same class of gap
  Task Group C found with attachments.

### Security
- **A caller supplies parameters, never a path.** Every path
  placeholder is percent-encoded with `safe=""`, so `..` or `/` in a
  value becomes one literal segment instead of changing the endpoint. A
  parameter the spec does not declare is refused rather than forwarded.
- **Mutating calls are never retried.** A retried send sends twice.
- **Exactly one route is session-free** — the OAuth callback, because a
  browser redirect carries no `Authorization` header. Its `state` is
  generated with `secrets`, single-use and expiring; unknown, replayed
  and stale values are all refused (RFC 6749 §10.12). It lives on its
  own router so the exception is visible in review.
- **Two permission gates per call**, and the refusal names which one
  said no: the operator's grant in the shared `PermissionModel`, and the
  vendor scopes the token actually carries. Checked per call, so
  revoking a grant bites on the next call.
- **No token appears in a response, an event, a log line or a preview.**
  The audit payload carries query *keys*, never values, and never a body.
- **Vendor scopes are the narrow ones** where a narrow one exists —
  `drive.file` over `drive`, `gmail.readonly` over `mail.google.com`.
- **HTTPS is required** for every endpoint; loopback is allowed so the
  engine can be tested against a local server.

### Notes
- **Phases 2–6 are not built.** Microsoft 365, GitHub/GitLab,
  Slack/Discord/Teams, Notion/Jira/Trello/ClickUp/Linear/Asana and
  Dropbox/Box run on this engine as spec data. They were deliberately
  not written from memory: a subtly wrong endpoint path or scope name
  ships a connector that fails at the first real call, and a wrong
  catalogue entry is worse than an absent one because it claims to work.
- **No two-way sync** for Google Tasks or Keep. Pull and push
  operations ship; a *sync* needs a conflict policy and a scheduler
  (M7 Phase 6). One-directional import that works beats a mirror that
  silently loses an edit.
- **Google Keep is Workspace-only** and says so in its
  `availability_note`, so the REST surface reports it before a caller
  spends an OAuth round trip.
- **Google Meet has no scheduling API** — a Meet link is
  `conferenceData` on a Calendar event, so that lives on the Calendar
  spec; `google_meet` exposes the conference *records* the Meet API
  actually offers.
- **Also absent:** webhooks and inbound delivery, a durable outbound
  queue, resumable/multipart upload (simple upload ships, correct to
  5 MB), and Oracle Cloud sync.
- 200 new tests (1936 → 2136). mypy 263 → 263, ruff 21 categories, both
  unchanged.

## [0.26.0] — M11 Task Group D: AI Workspace

The AI layer over the substrate Task Groups A–C shipped: a real
workspace↔knowledge association, a budgeted context a model can be given
whole, retrieval scoped to one workspace, and grounded assistance
reachable from REST and from the existing agent. On-demand only — nothing
here schedules anything, and no assist call is persisted.

### Added
- **Domain** — `domain/ai_workspace/models.py`: `ContextItem`,
  `ContextSection`, `WorkspaceContext`, the greedy `pack()` and its
  character budget, `clip()`, `order_sections()`, `render_results()` and
  `build_assist_prompt()`, plus the four closed vocabularies
  (`SECTION_ORDER`, `LINK_TARGETS`, `LINK_SOURCES`, `ASSIST_MODES`).
  Pure: no database, no service, no provider.
- **Schema** — one table, `workspace_knowledge_links`: workspace +
  entity, four nullable narrow foreign keys (project/note/task/file),
  `source` (`extracted` | `manual`) and `confidence`. The association
  table Task Group A's `WorkspaceManager.context` explicitly declined to
  invent until this task group had said what it needed.
- **Repository** — `WorkspaceLinkRepository`, with an exact-match `find`
  (nulls compared, so "this note is about Ada" and "this workspace is
  about Ada" stay distinct rows), `delete_extracted_for_target`, and an
  aggregate `entities_for_workspace` join.
- **Services** — `WorkspaceKnowledgeService` (link/unlink, idempotent
  linking with extracted→manual promotion, and ingestion over a
  workspace's own text, its notes and its files' index records) and
  `WorkspaceAssistantService` (`summarize` / `ask` / `next_actions`,
  grounded, with citations).
- **Managers** — `WorkspaceContextManager` (the budgeted context across
  every M11 subsystem plus Knowledge and Memory) and `WorkspaceRetriever`
  (workspace-scoped retrieval over the shared `SearchService`).
- **Agent tools** — `list_workspaces`, `workspace_context`,
  `search_workspace`, `ask_workspace`, `summarize_workspace`, on the
  **existing** registry via `build_tool_registry`'s new optional
  `workspace_assistant` argument.
- **Events** — `WorkspaceKnowledgeLinkedEvent` and
  `WorkspaceAssistCompletedEvent`, relayed as
  `workspace.knowledge_linked` and `workspace.assisted`.
- **REST** — `/api/v1/workspace-ai/{id}/context`, `/retrieve`,
  `/assist`, `/ingest`, `/entities`, plus `/api/v1/knowledge-links`
  (create/list/read/delete). Same Bearer auth and `{data, meta}`
  envelope as every resource router.
- **Settings** — `JARVIS_AI_WORKSPACE_*`: `context_budget_chars`,
  `context_section_items`, `context_item_chars`, `retrieval_top_k`,
  `retrieval_overfetch`, `ingest_max_targets`.

### Changed
- **`WorkspaceManager.context` gained `linked_knowledge`** alongside the
  existing `related_knowledge`. The two answer different questions —
  what this workspace's text *produced* versus what merely shares a word
  with its name — and both are kept, because a brand-new workspace has
  produced nothing yet. Additive: nothing that was in the payload moved.
- **`ExtractionResult` gained `entity_ids`** (M10A). The counts alone
  cannot say *which* entities a text is about: one mentioning an entity
  the graph already knows creates nothing and looks, from the counts,
  like a text about nothing. Defaulted and last, so every existing
  construction site and assertion is unchanged.

### Fixed
- **Tasks with no due date were missing from the assembled context.**
  `TaskManager.agenda` answers "what is due", which is right for a badge
  and wrong for a context — an undated task is neither overdue nor due
  soon, and most tasks are undated. The tasks section now lists open
  tasks as a third group; the urgency judgement still comes from the
  manager that owns it.

### Notes
- **No second anything.** Retrieval narrows M10A's `SearchService` by
  the `workspace_id` its sources already publish, rather than building a
  workspace index — widening `ISearchSource.search` would change all
  thirteen registered sources, most of which have no workspace concept.
  Extraction is `KnowledgeService.learn_from_text`, called. The agent is
  M10's `AgentOrchestrator`, reached as tools; this milestone runs no
  graph of its own.
- **No search source was registered** — the first M11 task group not to
  add three. Knowledge entities are already searchable through
  `KnowledgeSearchSource`, and a second source over the same rows would
  return one entity twice with no way to tell the hits apart.
- **Re-ingestion replaces what it extracted and never what a person
  asserted.** An edited note stops claiming entities its text no longer
  mentions; a `manual` link survives. Asserting a link the extractor had
  already found promotes it rather than duplicating it.
- **The budget is in characters, and truncation is reported.**
  `pack()` is greedy in a fixed section order, so the tail is what is
  dropped under pressure, and every section keeps its pre-packing
  `total` — a section holding three of forty tasks says so. Characters
  rather than tokens because tokenization belongs to a provider.
- **The assistant degrades instead of failing.** No reachable provider
  returns the assembled context verbatim with `synthesized=false` — the
  posture `KnowledgeService.ask` already set, and the only one
  compatible with an offline-first product.
- **Nothing is scheduled, and no assist call is stored.** Ingestion runs
  on demand (M7 Phase 6 owns scheduling); an assist returns its answer
  and publishes an event, and `ConversationService` remains the only
  transcript store. `workspace.assisted` deliberately carries no answer
  text.
- **No embeddings over workspace content.** Retrieval is the shared
  keyword index narrowed by workspace, not a vector search; semantic
  indexing needs the vector-store work Task Group C deferred.
- 199 new tests (1737 → 1936). mypy 263 → 263, ruff 21 categories, both
  unchanged.

## [0.25.0] — M11 Task Group C: File Platform

A local file subsystem hanging off the Workspace substrate Task Group A
shipped: folders, files, tags, extensible metadata, plain-text indexing,
and attachments to five workspace entities. Local files only — no
Drive, no Dropbox, no OneDrive, no cloud sync.

### Added
- **Domain** — `domain/files/models.py`: `safe_join` (the single place
  path containment is decided), `validate_name`, `extract_text`, the MIME
  and extension helpers, and the closed vocabularies
  (`TEXT_EXTRACTABLE_EXTENSIONS`, `INDEX_STATUSES`, `ATTACHMENT_TARGETS`).
- **Schema** — six tables: `folders` (self-referential, with a
  denormalized `relative_path` cache), `files`, `file_tags` (a real join
  table), `file_metadata` (key/value rows), `file_index_records` (1:1
  with a file, four-way status), `workspace_attachments` (five nullable
  foreign keys, one per target kind).
- **Repositories** — `FolderRepository`, `FileRepository`,
  `MetadataRepository`, `AttachmentRepository`.
- **Services** — `FolderService` (create/rename/move/delete with cycle
  prevention and subtree path rewriting), `FileService` (CRUD, move,
  rename, tags, metadata, indexing, stats, search), `AttachmentService`.
- **Managers** — `FolderManager` (tree with depths, file counts and
  unfiled files), `FileManager` (context and workspace overview),
  `AttachmentManager` (both directions of the link).
- **Events** — `FileUpdatedEvent`, `FolderUpdatedEvent`,
  `AttachmentUpdatedEvent`, relayed as `file.updated`, `folder.updated`,
  `attachment.updated`.
- **Search** — `FileSearchSource`, `FolderSearchSource`,
  `AttachmentSearchSource`, registered through M10A's provider registry.
  `files` is the first source whose corpus includes extracted document
  text rather than only stored fields.
- **REST** — `/api/v1/files`, `/api/v1/folders`, `/api/v1/attachments`,
  same Bearer auth and `{data, meta}` envelope as every resource router.
- **Settings** — `JARVIS_FILES_*`: `storage_dir` (defaults to
  `<data_dir>/files`), `index_enabled`, `index_max_bytes`,
  `max_upload_bytes`.

### Security
- **The storage root is a hard boundary.** Every path resolves through
  `safe_join`, which resolves both sides before comparing so a symlink
  out of the root is caught as well as a literal `..`, and which raises
  rather than clamping. It runs at construction *and* again on every
  read. The REST API accepts no path fragment at all — callers name a
  folder by id — so the input class that could escape is not part of the
  surface.
- **Attachment targets are validated before the insert.** Foreign keys
  already refuse a fabricated parent, but as an `IntegrityError` that
  reaches the caller as a 500. `AttachmentService` now returns a 400
  naming what is missing, and additionally rejects an attachment
  spanning two workspaces — the one rule a foreign key cannot express.

### Notes
- **Indexing reads seven extensions and nothing else** (`.txt`, `.md`,
  `.json`, `.yaml`, `.yml`, `.csv`, `.xml`), bounded at 1 MiB per file.
  No OCR, no PDF parsing, no embeddings, no summarisation. `skipped` is
  a successful catalogue entry, not a failure — which is why
  `IndexRecord.status` has four values rather than a boolean.
- **Deleting a non-empty folder requires `recursive=true`.** The
  database cascade would take the subtree happily; that is the wrong
  default for a destructive operation on real bytes.
- **Detaching is not deleting.** Removing an attachment leaves the file
  untouched; deleting the *target* removes only the link.
- File bytes travel as base64 inside the envelope rather than as
  multipart, because `python-multipart` is not a declared dependency of
  this project and building a shipped endpoint on a transitive package
  is a break waiting for someone else's lockfile.
- 116 new tests (1621 → 1737). mypy 263 → 263, ruff 21 categories,
  both unchanged.

## [0.24.1] — Database integrity: SQLite foreign-key enforcement

A stabilization patch, ahead of M11 Task Group C introducing more
relational models (folders, files, attachments, indexing).

### Fixed
- **Foreign keys are now enforced.** SQLite ships with
  `PRAGMA foreign_keys` off and scopes it per *connection*, so every
  `ON DELETE`/`ON UPDATE` clause in `models.py` had been decorative
  since M1. `SQLiteDatabase` now issues the pragma from a single
  `connect` event listener on the engine — SQLAlchemy's documented
  pattern — rather than per repository or per session.
- **`POST /api/v1/sessions` accepted an unvalidated foreign key.**
  `conversation_id` went straight from the request body into a real FK
  column; an unknown id silently created a session pointing at nothing
  and still returned `201`. `SessionManager.create` now checks the
  conversation exists and the route returns `400`. `thread_id` is
  deliberately still unchecked — it is not a foreign key (LangGraph's
  checkpointer owns that id space).
- Three tests were fabricating parent ids (`"mem-1"`, `"conv-1"`) that
  no row matched. They now seed real rows; the assertions are unchanged.

### Added
- `tests/unit/test_database_integrity.py` — pins the pragma across
  pooled connections, proves an orphan insert is rejected and a valid
  one still works, proves a declared `ON DELETE CASCADE` now actually
  fires through raw SQL (no ORM cascade involved), and covers the new
  session validation on both the reject and accept paths.

### Notes
- **Nullable foreign keys are unaffected.** `ON DELETE SET NULL`
  columns stay optional — an unfiled note, a session with no
  conversation. Enforcement rejects what is broken, not what is unset.
- `ondelete=` and the ORM's `cascade=` remain two mechanisms, both now
  live. See `ARCHITECTURE.md` §12 for which governs what.
- 1613 → 1621 tests, all passing. mypy 263 → 263; ruff 21 categories
  unchanged; black clean. No roadmap milestone was modified.

## [0.24.0] — M11 Task Group B, Productivity Core

Tasks, the local Calendar engine, and Reminders — the three domains
that hang off Task Group A's Workspace substrate. None of them invented
a container, which was the argument for building A first.

### Added
- **Task domain** — `Task` model, `TaskRepository`, `TaskService`,
  `TaskManager`. Status, priority, due dates, normalized tags, and an
  agenda (overdue / due-soon / status counts) with an injectable clock.
- **Local Calendar engine** — `Calendar`, `CalendarEvent`,
  `CalendarRepository`, `CalendarService`, `CalendarManager`. Event
  CRUD, categories, metadata, per-workspace default calendar, and
  recurrence **rules**.
- **`RecurrenceRule`** — a small explicit subset of RFC 5545 (four
  frequencies, interval, one of count/until) with bounded, pure
  expansion. Month arithmetic clamps: the 31st plus one month is the
  28th, not the 3rd.
- **`CalendarManager.occurrences`** — expands stored rules into the
  concrete datetimes in a window. The capability no single service call
  provides, because the repository can only filter on an event's
  *stored* start.
- **Reminder domain** — `Reminder`, `ReminderRepository`,
  `ReminderService`, `ReminderManager`. Scheduling metadata, status
  transitions, target resolution across Tasks and Calendar.
- **Four relay events** — `task.updated`, `calendar.updated`,
  `calendar.event_updated`, `reminder.updated`, each one class with an
  `action` field.
- **Three search sources** — `tasks`, `calendar`, `reminders`, through
  M10A's provider registry with no change to `SearchService`.
- **REST** — `/api/v1/tasks`, `/api/v1/calendar/*`, `/api/v1/reminders`
  plus `/tasks/agenda`, `/calendar/occurrences`, `/reminders/due` and
  per-entity `/context`.
- DI singletons for all three services and all three managers.

### Fixed
- **The workspace cascade did not reach any Task Group B table.**
  `ON DELETE CASCADE` is declared on every foreign key, but SQLite
  ignores it unless `PRAGMA foreign_keys=ON` is set and this
  application never sets it — so Task Group A's cascade had been
  working purely through SQLAlchemy's ORM-level `cascade` on
  `Workspace.projects`/`notes`. New child tables silently survived
  their parent. Fixed by adding the relationships, and documented in
  `models.py` so the next task group does not rediscover it.
- `ReminderService.next_occurrence_after` returned the naive datetime
  SQLite hands back, which would raise on comparison against
  `datetime.now(UTC)`. Now always aware.

### Notes
- **Nothing in this task group fires a reminder.** `due_before()` and
  `/reminders/due` *report*; there is no loop, no timer, no queue, and
  deliberately no `reminder.fired` event. Delivery is M7's Scheduler
  (Phase 6). Three tests assert the boundary at the service, manager
  and HTTP layers.
- **Local calendar only** — no Google, no Outlook, no synchronization.
  Those are Task Group E.
- Not built: File Manager/Search (C), workspace AI context (D), every
  external integration (E), the React UI (F).
- 1516 → 1613 tests, all passing. mypy 263 → 263; ruff 21 categories
  unchanged; black clean.

## [0.23.0] — M11 Task Group A, Workspace Foundation

The first implementation pass on M11, and the substrate the rest of the
milestone hangs off. M11 was restructured into six task groups (A–F)
before any code was written: the original "Integrations & Cloud
Platform" brief is now Task Group E, sitting on top of a shared
Workspace model rather than each integration inventing its own
container. No milestone was renumbered.

### Added
- **Workspace domain** — `Workspace`, `Project` and `Note` ORM models,
  plus `WorkspaceSettings` (a value object serialized into one JSON
  column) and `WorkspaceMetadata` (derived on read, never stored).
- **Three repositories** — `WorkspaceRepository`, `ProjectRepository`,
  `NoteRepository`, following `IntelligenceRepository`'s shape exactly.
- **`WorkspaceService`** — lifecycle, CRUD, settings, metadata, search
  hooks and event publishing. Shaped like `IntelligenceService`: an
  `IDatabase` per call, repository inside the session, optional
  `EventBus`.
- **`WorkspaceManager`** — composes the service with Knowledge, Search
  and Memory. Collects and never computes; every collaborator optional.
- **Three relay events** — `workspace.updated`, `project.updated`,
  `note.updated`, each one class carrying an `action` field, the shape
  `memory.updated`/`goal.updated` established.
- **Three search sources** — registered through M10A's provider
  registry with no change to `SearchService` itself.
- **REST** — `/api/v1/workspaces`, `/api/v1/projects`, `/api/v1/notes`
  (CRUD), plus `/workspaces/{id}/metadata`, `/overview` and `/context`.
- DI singletons `workspace_service` and `workspace_manager`.

### Notes
- **A note belongs to a workspace and only optionally to a project** —
  a thought worth capturing rarely arrives already filed. Consequently
  deleting a project *keeps* its notes, moving them back to the
  workspace, rather than letting the ORM cascade take them. Deleting a
  workspace does cascade, because that is an explicit "remove all of
  this".
- **Not built, by scope:** Tasks, Calendar, Reminders (TG-B); File
  Manager and File Search (TG-C); workspace AI context beyond a
  deterministic text match (TG-D); every external integration (TG-E);
  the React workspace UI (TG-F). No collaboration, sharing or sync
  endpoints — those need an identity model and a conflict story that do
  not exist yet.
- 1460 → 1516 tests, all passing. mypy 263 → 263; ruff 21 categories
  unchanged; black clean.

## [0.22.0] — Final Backlog Completion Pass (pre-M11)

The second and last backlog pass before M11. Where `0.21.0` closed the
§15 items the roadmap had written down, this one closed what the
roadmap had *not* — three Settings pages and one spoken greeting that
had quietly become false as the milestones behind them shipped.

### Fixed
- **The startup greeting invented the user's day.** `build_context` fed
  the LLM an invented task list, invented calendar events, an invented
  "recent achievement", a fabricated temperature and a fabricated
  now-playing track — then the greeting was *spoken aloud* as fact.
  Work context now comes from M10B's real Goal Manager (open goals,
  completed goals); calendar, weather, music and smart-home stay empty
  until M11/M12 give them a real source, and the prompt simply drops
  what it has no context for. `features/greeting/mock_context.py` is
  deleted.
- **Three Settings pages advertised milestones that had already
  shipped.** "Browser Automation" and "Desktop Automation" read *Coming
  in Milestone 4 — Automation* while `BrowserSettings` and
  `WindowsAutomationSettings` were real and consumed by shipped
  services; "Plugins" read *Coming in Milestone 5 — Agents* while the
  whole Plugin Platform shipped in M9. All three are now real pages
  over the settings that already existed.
- **Home dashboard service cards showed a green "connected" light over
  invented data.** Gmail, Spotify, Weather, Finance and Smart Home read
  as genuine readings of the user's inbox, music and local weather.
  They now render a `preview` state: offline indicator plus a visible
  "Preview — no integration connected yet" note. The illustrative data
  stays (it is what M5 shipped and what proves the widget works); the
  claim to be connected does not.

### Added
- `BrowserAutomationPage`, `DesktopAutomationPage` (M4 settings) and
  `PluginsPage` (M9 settings) — 15 real Settings pages now, 2
  placeholders.
- A `preview` key in `ServiceWidget`'s refresh contract, which forces
  the offline indicator regardless of what the payload claims.

### Changed
- The two remaining Settings placeholders name the milestone that
  actually owns them (M12 Smart Home & IoT, M14 Security) instead of
  the retired "Milestone 6 — Ecosystem" grouping.
- `GreetingService` takes an optional `intelligence_service`, wired by
  DI. Absent or failing, the greeting loses its work context and
  nothing else — same best-effort contract every other context source
  in that method already had.

### Notes
- Sweep found **zero** `TODO`/`FIXME`/`HACK`/`XXX` in `src/`, zero dead
  routes (all nine routers mounted), and zero unwired DI services.
- Remaining stand-ins are all owned by unstarted milestones and are
  now labelled as such: the integration providers (M11/M12), the vision
  and OCR providers (M6's remainder, already reporting themselves
  unavailable), the module registry (no module hot-reload machinery
  exists), and the Automations workspace placeholder.
- 1451 → 1460 tests, all passing. mypy 265 → 263; ruff 22 → 21
  categories; black clean.

## [0.21.0] — Backlog Completion & Stabilization Pass (pre-M11)

Not a milestone. A pass over the documented backlog of milestones that
are already complete, plus the UI/runtime audit that surfaced two
places where a screen was showing invented data next to a working
backend.

### Fixed
- **The desktop Plugin Manager rendered fabricated plugins.** It was
  still wired to an M5-era `MockPluginProvider` that seeded two invented
  entries ("Weather Widget", "Spotify Connector") and a three-item
  invented marketplace. M9 Task Group C shipped the real Plugin Platform
  — registry, loader, sandbox, permission model, marketplace — and this
  view was simply never rewired. It now reads the live `PluginRegistry`
  through a new `PluginRegistryProvider`; Enable/Disable/Reload perform
  real lifecycle transitions, a failed plugin shows its actual error,
  and an install with no plugins shows an empty state. The mock was
  deleted rather than left beside the real thing.
- **The Module Manager invented update availability.** `check_update`
  rolled `random.random() < 0.3` and fabricated a bumped version number
  when it came up, so the same click told the user a different story
  each time. There is no module update channel; the button now says
  "No update channel" instead of the equally untrue "Up to Date".
- Install/Uninstall/Update tooltips in the Plugin Manager claimed "no
  plugin loader exists yet", which stopped being true at M9. They now
  name the real reason (each needs a source directory this surface does
  not ask for) and point at the REST route that does the job.

### Added
- **Five WebSocket relay categories that were published but never
  relayed** (`MASTER_ROADMAP.md` §15, M9 Task Group B): `voice.state_changed`,
  `automation.step`, `progress.update_phase`, `notification.plugin` and
  `plugin.custom`. Every one had a real publisher; only the
  `EVENT_TYPE_NAMES` entry was missing, so no subscriber could ever see
  them. `UNPUBLISHED_EVENT_TYPES` now names the four event classes still
  deliberately absent, and a test fails if one of them gains a publisher
  without gaining a relay entry.
- **Disk metrics in the health snapshot** (§15, M9 Task Group C):
  `disk_percent`, `disk_free_bytes`, `disk_total_bytes`, as flat
  top-level keys so `ResourceManager.register_budget()` can target them
  — which was the whole point of tracking the item. GPU stays
  unimplemented and unfaked: it needs a vendor library this project does
  not depend on.
- `/api/v1/health` and `/api/v1/ready` (§15): the paths
  `docs/ARCHITECTURE.md` has always documented. The original
  `/api/health` and `/api/ready` keep working — one router, mounted
  twice, with a test pinning that both return identical bodies.

### Changed
- **BREAKING — `/api/v1/sessions` now returns the `{data, meta}`
  envelope** (§15). It was the last route outside the envelope
  `ARCHITECTURE.md` §5 mandates; §15 deferred the change until a second
  resource route existed to prove the shape, and six now do. Callers
  read `response.json()["data"]["session_id"]`. The route keeps its
  separate authentication exemption — it is what issues the token every
  other route needs.
- `HealthMonitor` takes a `disk_path`, wired by DI to the data directory
  — the volume JARVIS can actually fill.

### Notes
- **M8's deferred backlog is untouched, deliberately.** Notification
  Center, Context Menu system, Workspace views, window management,
  responsive/DPI/multi-monitor, Phases 2/5/6/7 — that is the M8
  milestone itself, not stabilization, and M8 is an *active* frontend
  migration whose PySide6 surfaces are slated for replacement. Building
  them in the outgoing stack would be work thrown away twice.
- M7's Scheduler, M10A's File Search, M10B's scheduled briefing, M10's
  Learning/Feedback and M10.5's two partial acceptance criteria all
  remain open with named owners (M7 Phase 6, M11B, M15, M16, M14, M11).
  Each is blocked on a milestone that has not started, not on effort.
- 1433 → 1451 tests, all passing. mypy 266 → 265; ruff category list
  unchanged at 22; black clean.

## [0.20.0] — M10.5 Task Group E, SDK, Developer Experience & Milestone Closure

The last task group of M10.5. It ships nothing a *user* sees and
everything an integration *author* needs, then closes the milestone.
Still no real provider, no OAuth flow and no vendor integration — those
were always M11's scope.

### Added
- **MCP SDK** (`core/mcp/sdk/`) — `CapabilityBuilder`,
  `ProviderBuilder`, `TransportBuilder`, `AuthBuilder` and
  `ConfigBuilder`, each producing the **existing** runtime model rather
  than a new type. `build()` validates and raises with the whole problem
  list, so a bad permission scope surfaces while the provider is being
  written rather than at first connect. The dataclasses stay public and
  directly constructible — the builders are a convenience, not a gate.
- **Registry helpers** — `register_provider` validates metadata and
  config *together* before anything enters the registry;
  `expose_capabilities` is all-or-nothing, so a batch with one bad entry
  never leaves the server half-published.
- **Validation framework** (`core/mcp/sdk/validation.py`) —
  `ValidationReport` / `ValidationIssue` with stable codes and
  ERROR/WARNING severity, plus validators for capabilities, provider
  metadata, provider config, transport config, authentication and
  **registry consistency**: the cross-object checks (a transport nothing
  registered, an auth method no strategy implements, a scope still
  awaiting a grant) that no single model can make about itself.
- **`jarvis mcp` developer CLI** (`infrastructure/cli/mcp_cli.py`) —
  `status`, `validate`, `list`, `inspect`, `capabilities`, `transports`,
  `providers`, `auth`, `connections`, with `--json` and `--config`.
  Dispatched from `main.py` before the run-mode parser, so inspecting an
  install never launches it.
- **Example implementations** (`core/mcp/sdk/examples.py`) — a
  capability, provider, config, transport and auth strategy, all
  self-contained and all imported by tests, so they cannot rot the way a
  code sample in a document does.
- **`MCPDiagnostics`** (`core/mcp/diagnostics.py`) — one read-only
  aggregator over every MCP subsystem, including `inspect_provider`,
  which answers "why will this provider not work" across registration,
  connection, authentication and health in a single call.
- Read-only REST: `GET /api/v1/mcp/diagnostics`, `GET /api/v1/mcp/validate`.
- DI singleton `mcp_diagnostics`, resolved by both the CLI and the REST
  layer.

### Changed
- `AuthBuilder` coerces a string method to `AuthMethod`, so
  `AuthBuilder("bearer_tokn")` fails on the typo rather than several
  calls later.
- `routes/mcp.py` documented as complete and deliberately read-only;
  provider *management* endpoints land with M11's first real provider.

### Fixed
- Stale comment on `TRANSPORT_TYPES` claiming only `in_process` had a
  shipped implementation — Task Group B shipped the other four.
- Dead `SessionState` import in `core/mcp/auth/manager.py`, left by Task
  Group D.

### Security
- **Diagnostics and the CLI expose no credential.** Every read goes
  through `MCPAuthManager.public_snapshot` / `status`, which carry
  metadata only. Asserted against raw serialized output — the full
  diagnostics report, every CLI command in both formats, and the REST
  response text — rather than a parsed field, so a leak through an
  unexpected key cannot slip past.
- **Read-only by construction.** Nothing in the diagnostics aggregator
  or the CLI connects, authenticates, installs or mutates; a test runs
  every read twice with the world captured either side to prove that
  inspecting changes nothing.
- `AuthBuilder` redacts its secret in `repr`/`str`, the same rule
  `Credential` follows.

### Notes
- **Final Runtime Review** found no duplicate registry, lifecycle
  manager, permission system, health system or authentication system.
  One `PermissionModel`, one `HealthMonitor` collector named `mcp`, one
  `MCPAuthManager`, one `CredentialStore`; four registries each holding
  a distinct kind of thing. Full findings in `MASTER_ROADMAP.md`'s Task
  Group E addendum.
- **M10.5 is closed** across five task groups, `0.16.0`–`0.20.0`. Two
  acceptance criteria remain 🟡 and are named with where they land:
  Agent Trace integration for MCP tool calls, and a server-side network
  listener — both M11.
- 137 new tests across six files; suite 1296 → 1433, all passing. mypy
  266 → 266 unchanged; ruff category list identical to the baseline's 22
  (`F401` improved 3 → 2).

## [0.19.0] — M10.5 Task Group D, Authentication & Provider Integration Foundation

The authentication framework every future MCP provider uses.
Infrastructure only: **no real providers**, no vendor code, and **no
OAuth flow** — that needs an authorization server and a callback
endpoint, neither of which this task group ships.

### Added
- **`AuthMethod`** vocabulary — `api_key`, `bearer_token`,
  `personal_access_token`, `oauth2`, `client_credentials`, and `none`
  (a real state: a local stdio peer needs no credential, and modelling
  that honestly avoids a fake empty credential standing in for it).
- **`Credential`** — access/refresh tokens, expiry, scopes, provider id,
  account id and encryption metadata. Frozen, so a failed refresh cannot
  leave a half-updated credential behind.
- **`CredentialStore`** — encrypted at rest via the existing Fernet
  helpers, in the existing `config/` convention. Rotation-ready: each
  record carries the `key_id` that encrypted it, and `rotate()` re-writes
  every record under a new key.
- **`AuthStrategyRegistry`** + `StaticTokenStrategy` / `NoAuthStrategy` —
  one strategy per method, in a registry a future method plugs into.
- **`ProviderSession`** — per-provider authentication state, counters and
  runtime status.
- **`MCPAuthManager`** — authenticate / refresh / revoke / validate /
  expire / reconnect, plus the permission bridge and the health payload.
- **`mcp.auth_changed`** relay event carrying an `action` field for all
  eight documented transitions.
- Read-only REST: `GET /api/v1/mcp/auth`, `/auth/methods`,
  `/auth/{provider}`, `/auth/{provider}/status`.
- DI singletons `mcp_credential_store`, `mcp_auth_strategies`,
  `mcp_auth_manager`.

### Security
- **Tokens are never exposed.** `Credential` redacts its own `repr`/`str`;
  storage and public serializers are separate methods so "safe to show"
  is a deliberate choice, not something to remember. Tests assert against
  raw REST response text, raw event payloads, the raw health snapshot and
  the raw on-disk file.
- **Refuses plaintext persistence.** Unlike `ApiCenterService` (which
  writes plaintext when no key is configured — acceptable for mostly
  non-secret API metadata), this store raises rather than writing a token
  unencrypted, and writes no file at all. In-memory operation still works,
  with the caveat recorded on the session, so an unconfigured install can
  authenticate for the session and simply will not remember it.
- **Revoking clears the tokens**, not just a flag — a revoked credential
  still holding its secret is a credential waiting to leak.

### The permission bridge
Two independent gates, deliberately not conflated: the **JARVIS-side**
scope the operator granted (M9's `PermissionModel`, namespaced
`mcp:<provider_id>`) and the **provider-side** scope the token actually
carries. `authorize_capability` names which gate refused, because the
two call for completely different fixes. No new permission vocabulary
and no second permission store.

### Reused, not duplicated
`utils/crypto.py`'s Fernet helpers, the `config/` storage convention,
M9's `PermissionModel`, `HealthMonitor.register_collector` (expiry
detection rides the existing poll rather than a second timer), the
`EventBus`, and the DI singleton pattern. M9's `SessionManager` is
untouched — it owns *user* sessions; this owns *provider* sessions.

### Deferred
The OAuth2 and client-credentials flows (listed in the vocabulary and
reported as unsupported rather than half-implemented); login and OAuth
callback endpoints; write endpoints; every vendor integration (M11).

### Testing
101 new tests across five files, including on-disk encryption
verification, a restart round trip, both permission gates, expiry,
refresh, revoke, reconnect and failure paths, and an end-to-end suite
through the real DI container with events verified over the real
WebSocket relay. mypy 266 → 266, unchanged, zero errors in any new file;
ruff category list identical to the baseline's 22.

## [0.18.0] — M10.5 Task Group C, MCP Provider Framework

The generic framework every future MCP integration plugs into **without
modifying the MCP runtime**. Infrastructure only: **no real providers**,
no OAuth, no authentication, no vendor code — those are Task Group D and
M11.

### Added
- **`IMCPProvider`** (`core/interfaces/mcp.py`) — a transport-independent
  provider port whose six lifecycle methods mirror `IService` exactly,
  plus `suspend`/`resume`, the two moves an integration genuinely needs
  that a service does not.
- **`ProviderMetadata` / `ProviderConfig`** — inert, validated
  dataclasses separating *what a provider is* from *how this install
  runs it*, so a deployment can move a provider stdio → websocket
  without editing the provider. Config carries `enabled`, transport,
  runtime options, and reconnect/retry/heartbeat policies.
- **`MCPProviderRegistry`** — register/unregister/lookup/enumerate plus
  `discover()` filtered by transport, capability, state, protocol,
  permission scope and enabled-ness, combining with AND. Registration
  is **inert**: no transport built, no subprocess spawned — which is
  what makes discovery side-effect free.
- **`MCPProviderManager`** — install/initialize/connect/disconnect/
  suspend/resume/shutdown/remove, with fault-isolated batch operations
  (`connect_all` never lets one provider's failure stop another's).
- **`TransportBackedProvider`** — the generic implementation covering
  every "point at an MCP server with this transport config" case, which
  is every integration M11 currently anticipates.
- **`mcp.provider_changed`** relay event carrying an `action` field for
  all eight documented transitions, plus the resting `state` — the two
  genuinely differ for `resumed`, which lands in `connected`.
- Read-only REST: `GET /api/v1/mcp/providers` (with the registry's
  discovery filters as query params), `/providers/{id}`,
  `/providers/{id}/health`, `/providers/{id}/metadata`.
- DI singletons `mcp_provider_registry` and `mcp_provider_manager`.

### Reused, not duplicated
Connection management delegates to Task Group A's `MCPClientRuntime`;
transport construction to Task Group B's `TransportFactoryRegistry`;
permissions to M9's `PermissionModel` (namespaced `mcp:<provider_id>`,
**no new scope vocabulary** — a provider may only request scopes the
plugin platform already defines); health to
`HealthMonitor.register_collector`; shutdown ordering to
`RuntimeManager` hooks. No second registry, lifecycle manager, health
subsystem or permission system.

### Security note
`ProviderConfig.as_dict()` reports option **key names only, never
values** — those will carry credentials once M11's providers exist, and
the reporting surface is built for that now rather than retrofitted.

### Deferred
Real providers, authentication and OAuth (Task Group D); GitHub, Gmail,
Slack, Calendar, Drive and every other vendor integration (M11);
create/update/delete provider endpoints.

### Testing
84 new tests across five files, including a full end-to-end lifecycle
against a **real stdio peer subprocess** through the real DI container
and real `PermissionModel`, with lifecycle events verified over the real
WebSocket relay. mypy 266 → 266, unchanged, zero errors in any new file;
ruff category list identical to the baseline's 22.

## [0.17.0] — M10.5 Task Group B, MCP Transport Layer & Runtime Connectivity

Fills the seam Task Group A left: all four transports the milestone
names are now real. **Still not the whole milestone** — no provider
integration ships, and OAuth/cloud sync remain M11's scope.

### Added
- **Stdio transport** — spawns a peer process, speaks newline-delimited
  JSON-RPC over its stdin/stdout, and shuts it down gracefully (close
  stdin, wait, escalate to kill).
- **WebSocket transport** — persistent outbound JSON-RPC over
  `websockets`. Distinct from `RuntimeWebSocketHub`, which serves
  JARVIS's *own* event relay inbound; they share a wire technology and
  nothing else.
- **HTTP transport** — stateless JSON-RPC over POST, with an honest
  `connect` that distinguishes an unreachable host from a peer-level
  error (see Fixed).
- **IPC transport** — a Windows named pipe or a Unix domain socket, not
  loopback TCP: a TCP socket would occupy a port, be reachable by any
  local process, and carry none of the OS-level access control the real
  primitives do.
- `JsonRpcStreamChannel` — newline framing plus request/response
  correlation over an asyncio stream pair, shared by `stdio` and `ipc`
  (which differ only in how they obtain that pair). `websocket` does
  not reuse it — a WebSocket already delivers discrete messages.
- **Transport factory** — builds any transport from plain config and
  registers all five into Task Group A's registry at the DI composition
  root, which is exactly what that registry was left empty for.
- **Transport discovery/query** — `discover()`, `describe()`,
  `describe_all()` on the existing registry, backed by declarative
  traits so a transport can be described without constructing one.
- **`MCPHeartbeatMonitor`** — one loop over every connected peer
  (mirroring `HealthMonitor`, not a timer per peer), riding the
  `request` primitive rather than a new port method, so a future
  transport gets heartbeat for free. `ping` was registered on the
  server through Task Group A's own `register_method` seam.
- Four new relay events — `mcp.handshake_completed`,
  `mcp.negotiation_completed`, `mcp.transport_failed`, `mcp.heartbeat`
  — deliberately distinct: a transport failure is a connectivity
  problem, whereas a permission denial or negotiation rejection is the
  protocol working correctly.
- `MCPConnectionState.RECONNECTING`, so a subscriber can tell recovery
  from initial setup without tracking prior state.
- REST (still read-only) — `GET /api/v1/mcp/transports` now returns one
  descriptor per transport; `GET /api/v1/mcp/transports/{id}` adds the
  connections using it; `GET /api/v1/mcp/heartbeat` reports the last
  probe per peer without ever forcing one.

### Fixed
- `HttpTransport.connect` routed its reachability probe through
  `request`, which wraps every `httpx` failure as `MCPTransportError` —
  so an unreachable host was swallowed and the transport reported
  itself connected. Caught by a functional test against a real closed
  port; the probe now uses `httpx` directly, and only a genuine
  transport failure fails the connect.

### Reused, not duplicated
Reconnect, handshake, discovery and negotiation stay
`MCPClientRuntime`'s; permission enforcement stays
`MCPServerRuntime`'s; health rides `HealthMonitor.register_collector`;
lifecycle rides `RuntimeManager` hooks. No second connection manager,
no transport base class — every transport satisfies the Protocol
structurally.

### Deferred
Provider integrations, OAuth and cloud sync (M11); MCP tools surfaced
through the agent Tool Registry / Agent Trace; a server-side network
listener (Task Group B ships the outbound/client half of all four
transports); write endpoints for provider management.

### Testing
100 new tests across eight files, against **real** peers throughout: a
real subprocess for stdio, a real `websockets` server, a real HTTP
server, and a real named pipe / Unix socket for IPC. mypy 266 → 266,
unchanged, zero errors in any MCP file; ruff's category list identical
to the baseline's 22 after fixing the two genuinely-new findings this
pass introduced.

## [0.16.0] — M10.5 Task Group A, MCP & Integration Platform (core runtime)

The first implementation pass on M10.5. Ships the **MCP runtime
foundation only** — no network transport and no provider integration —
so the milestone stays 🟡 Active, not complete. Every piece plugs into
something that already exists rather than adding a parallel runtime.

### Added
- MCP Capability Registry -- `core/mcp/capabilities.py`, mirroring
  `SearchService`'s M10A provider-registry shape
  (`register`/`unregister`/`get`/`list_capabilities`), with one
  deliberate divergence: a duplicate capability name is an error unless
  `replace=True`, because a capability shadowing another's name would
  silently change what an existing permission grant authorizes.
- Transport abstraction -- `IMCPTransport` in `core/interfaces/mcp.py`
  plus `TransportFactoryRegistry` in `core/mcp/transport.py`.
  `stdio`/`websocket`/`http`/`ipc` are *named* in `TRANSPORT_TYPES` but
  deliberately **not implemented**; `GET /api/v1/mcp/transports`
  reports the known-versus-registered gap honestly. One reference
  transport ships: `InProcessTransport`, how JARVIS consumes its own
  MCP server.
- MCP Client Runtime -- `core/mcp/client.py`: connection management,
  handshake, capability discovery, health, and bounded-retry reconnect.
  Lifecycle only; no provider implementations.
- MCP Server Runtime -- `core/mcp/server.py`: capability exposure,
  permission enforcement, protocol dispatch
  (`initialize`/`capabilities/list`/`capabilities/call`, extensible via
  `register_method`), and an `IService`-shaped lifecycle.
- Capability negotiation -- `core/mcp/negotiation.py`: pure functions,
  no I/O. Version mismatch fails the negotiation; an unsupported kind
  or ungranted scope is rejected per-capability and never fails the
  connection. Graceful fallback to an older shared protocol revision.
- `mcp` WebSocket category on the existing Runtime relay --
  `mcp.connection_changed` (one relay name, `state` payload field),
  `mcp.capabilities_changed`, `mcp.permission_denied`.
- `infrastructure/api/routes/mcp.py` -- `GET /api/v1/mcp/status`,
  `/capabilities`, `/connections`, `/transports`. Read-only by design:
  registering/connecting/granting is a later task group's surface, so
  every route is a `GET` and the write endpoints land additively.
- `MCPSettings` (`JARVIS_MCP_*`) and DI wiring for all three runtimes.

### Reused, not duplicated
- **Permissions**: M9's `PermissionModel` outright — same store, same
  persisted grants, same audit log, same `PENDING`-until-granted
  default. MCP principals are namespaced `mcp:<client_id>` so an MCP
  peer and a plugin cannot collide while both stay in the one
  `pending()` queue. **No new permission vocabulary** — capabilities
  declare scopes from the existing `PERMISSION_SCOPES`.
- **Health**: `HealthMonitor.register_collector`, the extension point
  M9 built for exactly this and that nothing had used until now. One
  health channel, not a second.
- **Lifecycle**: plain DI singletons with their own `start`/`stop`, the
  same class `MemoryService`/`KnowledgeService` occupy. No new
  lifecycle manager, no background supervisor, no `RuntimeManager`
  change beyond registering hooks.

### Deferred (documented, not silently dropped)
- Network transports (`stdio`, `websocket`, `http`, `ipc`) -- later
  task groups; the registry seam is ready for each.
- Provider integrations, OAuth, cloud sync -- M11's scope throughout.
- MCP tools surfaced through the agent Tool Registry / Agent Trace --
  a later task group.
- Write endpoints for provider management -- Task Group B.

### Testing
89 new tests across seven files, covering the registry, negotiation,
transports, both lifecycles, permission enforcement against the *real*
`PermissionModel` on a real temp-file store, DI construction, the REST
surface, and the real WebSocket relay. mypy 266 -> 266, unchanged,
zero errors in any MCP file. Ruff's category list is identical to the
baseline's 22 categories (growth is entirely `PLC0415`, the established
lazy-import convention) after fixing the three genuinely-new findings
this pass introduced.

## [0.15.0] — M10B, Intelligence Layer (complete)

M10B extends the M10A Universal Search & Knowledge Platform rather than
introducing a parallel system: `IntelligenceService` mirrors
`KnowledgeService`'s exact architecture (same `database`/`event_bus`
constructor shape, same repository-per-session pattern, same lazy
event-import idiom), `IntelligenceRepository` mirrors
`KnowledgeRepository`, and Goal Manager registers into `SearchService`'s
existing provider registry as a fourth source (`GoalSearchSource`) with
zero changes to `SearchService` itself -- the extensibility M10A's
registry design was built for. No RuntimeManager changes, no new
lifecycle manager, no background scheduler.

### Added
- Goal Manager -- `Goal` (self-referential parent/child hierarchy) in
  `infrastructure/database/models.py`; `IntelligenceRepository` CRUD +
  hierarchy + progress + status + search; `IntelligenceService` auto-
  completes a goal at >=100% progress and publishes `goal.updated`
  (`action`: created/progress_updated/completed/deleted).
- Routine Learning -- deterministic, direct-observation reinforcement
  (not LLM-driven pattern mining): `Routine` rows keyed by
  hour-of-day/day-of-week wildcards, `IntelligenceRepository.
  reinforce_routine()` increments `observation_count` and confidence on
  a repeated observation; a routine only surfaces in suggestions once
  it crosses `_ROUTINE_SUGGESTION_MIN_OBSERVATIONS`.
- Preference Learning -- a structured `Preference` key-value store,
  separate from M3's freeform `MemoryType.PREFERENCE` memories; a
  `suggestion_boost_keyword` preference multiplies a matching
  suggestion's score, giving Predictive Suggestions a second,
  independent way to change from learned signal (plain keyword-boost
  logic, not an LLM reranker -- consistent with M10A's own deferred AI
  reranking).
- Context Awareness -- `IntelligenceService.get_context_signals()`
  (hour of day, day of week, recent memory snippets via
  `MemoryService.browse()`, active conversation id); intentionally
  *not* wired into the agent graph's `context_engine.py` node, since
  it answers a different question (time/activity signals for
  suggestions) than that node's LLM-prompt context assembly. No
  location signal -- no location provider exists anywhere in the
  codebase yet, documented rather than faked.
- Predictive Suggestions -- `IntelligenceService.predict_suggestions()`
  combines due-soon goals, reinforced routines, and the preference-
  boost pass into a single ranked list.
- Daily Briefing -- `IntelligenceService.generate_daily_briefing()`,
  on-demand only, publishes `briefing.generated`. **Automatic scheduled
  delivery is explicitly deferred**, the same gap M10A left with
  Scheduled Reflection: M7's Scheduler (Phase 6) does not exist yet
  (`SchedulerSettings` has been declared for forward compatibility only
  since Phase 1) -- this route/tool is the only way to produce one
  today.
- Agent integration -- `agents/tools/intelligence_tools.py`
  (`create_goal`/`list_goals`/`update_goal_progress`/`get_suggestions`/
  `get_daily_briefing`).
- `infrastructure/api/routes/intelligence.py` -- `POST/GET /api/v1/goals`,
  `GET /api/v1/goals/{id}`, `PATCH /api/v1/goals/{id}/progress`,
  `POST /api/v1/goals/{id}/complete`, `DELETE /api/v1/goals/{id}`,
  `GET /api/v1/intelligence/context|suggestions|briefing`,
  `POST/GET /api/v1/intelligence/preferences`. Same Bearer auth +
  envelope convention as `routes/knowledge.py`.
- `goal`/`briefing` WebSocket categories on the Runtime WebSocket relay
  -- `goal.updated`, `briefing.generated`.
- Universal Search -- `GoalSearchSource` registered as a fourth
  provider (`memory`, `knowledge`, `goals`, `commands`).

### Deferred (documented, not silently dropped)
- Automatic scheduled Daily Briefing delivery -- needs M7's Scheduler
  (Phase 6), not started; Daily Briefing is on-demand only today.
- Location-aware Context Signals -- no location provider exists in the
  codebase.
- AI reranking of Predictive Suggestions -- plain keyword-boost logic
  only, matching M10A's own deferred AI reranking of search results.

### Permissions
No new scopes introduced. Reuses M10A's existing `memory.read`/
`memory.write` scopes; no `goal.read`/`goal.write` introduced.

### Testing
936/936 tests passing (+48), zero regressions -- one integration test
per Acceptance Criterion (AC1 goal persistence + progress tracking over
REST and the real WebSocket relay, AC2 a learned routine measurably
changing a future Predictive Suggestion, AC3 Daily Briefing generation
relayed over the real WebSocket), each against a real temp-file SQLite
database and the real DI container. One pre-existing M10A test
(`test_search_returns_envelope`) asserted an exact 3-source set; updated
to the now-correct 4-source set rather than treated as a regression, since
Goal Manager registering a fourth provider is the exact extensibility
the Search Provider Registry was designed for. mypy diffed against a
clean baseline via `git stash -u`: 266 -> 266, byte-for-byte unchanged
after removing 14 genuinely-unnecessary `type: ignore` comments from
`intelligence_service.py`. Ruff findings proportional to the
pre-existing accepted baseline (665 -> 720, +55, entirely `PLC0415`
lazy-import lines matching `KnowledgeService`'s already-accepted
pattern) -- zero new categories introduced.

## [0.14.0] — M10A, Universal Search & Knowledge Platform (complete)

Unlike M10, M10A's own declared dependencies (M3 Memory Platform, M5A
Agent Orchestrator exposure) were both already shipped, so this
milestone was buildable to near-full completion in one pass. Every new
component extends an existing one rather than introducing a parallel
system: `RuntimeManager`, `ServiceManager`, `MemoryService`,
`ChromaVectorStore`, `AgentOrchestrator`, Context Engine, `EventBus`,
the Runtime WebSocket Hub, `PluginRegistry`, and the Tool Registry are
all reused as-is. **One key feature is explicitly deferred, not
dropped:** File Search needs M11B's File Manager surface, which
doesn't exist yet.

### Added
- Knowledge Graph / Relationship Graph -- `KnowledgeEntity` /
  `KnowledgeRelationship` / `KnowledgeEntityMemory` in the existing
  `infrastructure/database/models.py`; `KnowledgeRepository` mirrors
  `MemoryRepository`'s shape. LLM-driven entity/relationship
  extraction reuses the agent nodes' existing JSON-decision pattern
  (relocated to `jarvis/utils/llm_json.py` so `services/` could reuse
  it without creating a `services -> agents` dependency;
  `agents/prompting.py` re-exports both names unchanged).
- Persistent Memory -- reuses `MemoryService.set_pinned` rather than a
  second durability mechanism.
- Reflection Foundation -- `KnowledgeService.learn_from_recent_memories()`,
  on-demand only (REST or agent tool), never a scheduled background
  job.
- Correction / scoped Learning (Acceptance Criterion 3) --
  `KnowledgeService.correct()` supersedes the prior relationship and
  inserts a higher-confidence replacement rather than deleting
  history.
- Universal Search / Search Provider Registry --
  `services/search_service.py`'s `SearchService` owns
  `register_source`/`unregister_source`/`get_sources`
  (`core/interfaces/search.py`'s `ISearchSource` protocol); three
  sources registered today (`MemorySearchSource`,
  `KnowledgeSearchSource`, `CommandSearchSource` -- agent tools +
  live-read plugin commands). `SearchResult` is deliberately
  extensible: `confidence`/`reason` fields exist now, unpopulated, for
  a future AI-reranking milestone.
- ChromaDB integration -- reuses the single existing collection,
  tagged `record_type: "knowledge_entity"` metadata; no second vector
  store.
- Agent integration -- `agents/tools/knowledge_tools.py`
  (`ask_knowledge`/`search_knowledge`); `context_engine.py` gained an
  optional `knowledge` parameter, closing M10's own documented
  Context Engine knowledge-graph deferral.
- `infrastructure/api/routes/knowledge.py` -- `POST /api/v1/search`,
  `GET /api/v1/knowledge/entities/{name}`, `GET /api/v1/knowledge/ask`,
  `POST /api/v1/knowledge/correct`, `POST /api/v1/knowledge/learn`,
  `GET/POST /api/v1/knowledge/export|import`. Same Bearer auth +
  envelope convention as `routes/plugins.py`/`routes/devtools.py`/
  `routes/agent.py`.
- `memory`/`knowledge` WebSocket categories on the Runtime WebSocket
  relay -- `memory.updated`/`memory.recalled` finally realize the
  category `docs/ARCHITECTURE.md` §6 has documented as a target since
  before the Milestone 9 managers existed; `knowledge.entity_updated`/
  `knowledge.correction_applied` are new. `MemoryService` gained an
  optional `event_bus` constructor parameter to publish these.

### Deferred (documented, not silently dropped)
- File Search -- needs M11B's File Manager surface (not started).
- AI reranking -- `SearchResult.confidence`/`.reason` exist but are
  unpopulated.
- Scheduled Reflection -- `learn_from_recent_memories()` is on-demand
  only; M7 Scheduler integration is future work.
- A full, general-purpose Learning Engine -- `correct()` is a scoped
  primitive, not that engine.

### Permissions
No new scopes introduced. Plugin access reuses M9's existing
`memory.read`/`memory.write` Plugin SDK scopes.

### Testing
888/888 tests passing (+49), zero regressions -- one integration test
per Acceptance Criterion (AC1 `ask()` synthesis, AC2 export/import
round-trip, AC3 correction relayed over the real WebSocket, AC4
Universal Search spanning ≥2 real source types), each against a real
temp-file SQLite database and the real DI container. mypy diffed
against a clean baseline via `git stash -u`: 266 -> 266, byte-for-byte
unchanged after two real fixes in `knowledge_service.py`. Ruff
findings proportional to the pre-existing accepted baseline -- zero
new categories left unresolved.

## [0.13.0] — M10, AI Orchestrator (partial -- buildable-now scope)

Milestone 10 formally depends on M10A (Universal Search & Knowledge
Platform) and M14 (Authorization Engine), neither of which has started.
Rather than block, this release ships the full subset of M10 buildable
without them -- extending M5A's `AgentOrchestrator` graph directly, no
rewrite -- and documents the M10A/M14/M16-dependent remainder as
explicitly deferred, the same "Completed / Deferred with a documented
reason" discipline this project has applied since the M0-M9 audit.
**M10 is not 100% complete; see Deferred below.**

### Added
- Intent Engine -- `agents/nodes/intent_classifier.py`, a new node
  before `planner` classifying the request into `tool_use` /
  `direct_answer` / `clarification_needed` with a confidence score.
  Diagnostic only in this release (does not yet gate graph routing).
- Context Engine (scoped) -- `agents/nodes/context_engine.py`, assembles
  context from M3 Memory before planning. The M10A knowledge-graph half
  of Context Engine is deferred (see below); this is the M3-only subset
  that's real today.
- Parallel tool dispatch -- Milestone 10 Acceptance Criterion 1, also
  absorbing M7 Phase 3's deferred cross-tool-parallelism scope.
  `tool_selector` gained a `tool_parallel` decision shape alongside the
  existing `tool`/`final` ones; `tool_executor` dispatches independent
  calls concurrently via the existing `gather_with_concurrency`, bounded
  by `AgentSettings.max_parallel_steps` (declared in M7, unread by any
  code until now). The single-tool path is unchanged, byte-for-byte.
- Permission Validation (interim) -- Milestone 10 Acceptance Criterion 3.
  `agents/permission.py`'s `AgentPermissionGate` + a new
  `permission_validator` node inserted between tool selection and
  execution: the one enforcement point every proposed tool call (single
  or parallel) now passes through, replacing the pre-M10 gap where only
  `run_automation` had any permission awareness at all, and that only
  internal to `AutomationService`. Interim and explicitly documented as
  such -- M10's own spec routes this through M14's Authorization Engine
  "once that milestone ships"; `AgentPermissionGate` is a single, narrow
  class so that swap means replacing its `authorize()` body, not the
  graph wiring. `AgentSettings.confirm_required_tools` (default
  `{"run_automation"}`) is the interim policy.
- Real token-level streaming -- Milestone 10 Acceptance Criterion 2.
  `AgentOrchestrator.stream()` now yields real per-token output from
  `ILLMProvider.stream()` for the dominant path (an answer composed from
  tool results), via a second, responder-less compiled graph variant
  (`build_agent_graph(..., include_responder=False)`) and a prompt
  builder (`agents/nodes/responder.py`'s `build_final_response_prompt`)
  shared with the non-streaming path so the two can't drift. One path
  remains a documented, scoped exception: `tool_selector`'s "final"
  shortcut (no tool needed) still composes its answer inside a JSON
  decision object and replays it in the pre-M10 chunked style, since
  token-streaming JSON-embedded text cleanly would mean restructuring
  tool selection itself.
- Decision Engine -- `responder` node gained `response_mode`
  (`"direct"` / `"composed"`) in `AgentState`, per M10's description of
  it as "the responder node's successor, deciding final response shape
  and routing."
- `agent.step` added to the Runtime WebSocket API's event relay
  (`core/lifecycle/runtime_ws_hub.py`) -- real-time Agent Trace
  visibility over the same `/api/v1/ws` transport M9 built, not a
  second channel.
- `infrastructure/api/routes/agent.py` -- `POST /api/v1/agent/invoke`
  (blocking, `{data, meta}` envelope) and `POST /api/v1/agent/stream`
  (real token-level Server-Sent Events -- a documented, scoped exception
  to the envelope rule, the same way `/api/v1/sessions` already is).
  Same `Depends(get_current_session)` Bearer auth as `routes/plugins.py`
  / `routes/devtools.py`.

### Fixed
- None -- Task Group D/E's Windows architecture-normalization fix
  shipped in 0.12.0; no regression found in this release.

### Deferred (documented, not silently dropped)
- Context Engine's knowledge-graph half -- needs M10A (not started).
- Learning / Feedback closing through M16's Reflection Engine -- needs
  M16 (not started).
- Permission Validation's final form routed through M14's Authorization
  Engine -- needs M14 (not started); `AgentPermissionGate` is the
  interim single enforcement point in the meantime.
- Intent Engine gating graph routing (vs. diagnostic-only today) --
  revisit once M10A/M10B give the classifier real signal to act on.
- `tool_selector`'s "final" shortcut path's real token streaming -- see
  Added, above.
- PySide6 Agent Trace view / React frontend wiring to `/api/v1/agent` --
  M8's own remaining phases, unchanged by this release.

### Testing
839/839 tests passing (unit + integration), zero regressions -- up from
815 in 0.12.0 (+24: node/permission/route unit tests, three new
orchestrator integration tests exercising parallel dispatch, permission
denial, and real streaming end-to-end). Ruff/mypy findings proportional
to the pre-existing accepted baseline; zero new categories introduced.

## [0.12.0] — M9, Task Group E (Developer Platform Tools) — closes out Milestone 9

The last of M9's modules. **Milestone 9 (Runtime & Core Services) is
now 100% complete** across all five task groups (A: Runtime Core: B:
Service/Session/Configuration Manager, Health Monitor, Runtime
WebSocket API; C: Reliability; D: Plugin Platform; E: this release).
Architecture unchanged -- Python + FastAPI + Tauri, no migration.

### Added
- `core/devtools/` -- Debug Console + Live Logs (`debug_console.py`,
  a real loguru sink with a bounded, filterable buffer), Performance
  Profiler (`performance_profiler.py`, real time-series history over
  `HealthMonitor`'s existing poll-tick snapshots), State Inspector
  (`state_inspector.py`, a unified view combining `ServiceManager`,
  `PluginRegistry`, and `RuntimeManager`'s own real state), API
  Inspector (`api_inspector.py`, a real Starlette middleware recording
  this app's own `/api/v1/*` request/response metadata -- method,
  path, status, duration only, never bodies or headers).
- `infrastructure/api/auth.py` -- the real `Depends(get_current_session)`
  Bearer-auth dependency and `{data, meta}` `Envelope` helper
  `docs/ARCHITECTURE.md` section 5 has referenced by name since Task
  Group B but that no route had ever actually used until now.
- `infrastructure/api/routes/plugins.py` -- the real "Plugin
  Marketplace Foundation" + Permission Management REST API: full
  plugin lifecycle (list/get/enable/disable/install/uninstall/update),
  permission management (per-plugin grant/deny/revoke, pending queue,
  audit log), and marketplace browse/search/categories/get/reviews --
  all thin routes over Task Group D's real domain classes. The first
  real resource routes to follow `docs/ARCHITECTURE.md` section 5's
  full contract (envelope + Bearer auth), resolving the two documented
  exceptions `/api/v1/sessions` needed.
- `infrastructure/api/routes/devtools.py` -- REST reads over the new
  `core/devtools/` components, plus Plugin Diagnostics (one combined
  view: a plugin's status, health, recent related logs, and permission
  audit trail).
- Fourteen new `plugin.*`/`devtools.*` relay categories: eleven
  `plugin.*` events (Task Group D's event types, now actually relayed
  -- see the 0.11.0 entry) plus `devtools.log_captured` extend
  `RuntimeWebSocketHub.EVENT_TYPE_NAMES`.
- `DevToolsSettings` (`core/config/settings.py`) --
  `debug_console_enabled`, `debug_console_level`,
  `debug_console_max_entries`, `performance_history_size`,
  `api_inspector_enabled`, `api_inspector_max_records`.
- 74 new unit/integration tests across nine files, including a real
  end-to-end test (`tests/integration/test_devtools_platform_e2e.py`)
  proving the new REST API genuinely drives Task Group D's
  `PluginRegistry`/`PermissionModel` *and* that the result is relayed
  over the real Runtime WebSocket API -- install over REST, watch
  `plugin.installed`/`plugin.load_failed` arrive over the socket; grant
  a permission over REST, watch `plugin.permission_granted` arrive;
  enable over REST, watch `plugin.loaded`/`plugin.enabled` arrive.

### Fixed
- **A real, Windows-first-breaking bug in Task Group D**, found by
  these same end-to-end tests running for the first time against a
  genuine Windows machine (Task Group D's own tests only ever used a
  hardcoded-`"x86_64"` test double): `platform.machine()` reports
  `"AMD64"` on Windows, not `"x86_64"` -- every plugin manifest's
  *default* `supported_arch` list (`["x86_64", "arm64", "x86"]`) was
  silently rejecting every real Windows x86_64 plugin install.
  `infrastructure/platform/adapter.py`'s `DefaultPlatformAdapter.info()`
  now normalizes the OS-reported architecture string to this project's
  own canonical vocabulary at the Platform Abstraction Layer boundary
  -- exactly what that layer exists for.

### Changed
- `app.py` gained `_register_task_group_e_hooks`: Debug Console and
  Performance Profiler bookend every other startup/shutdown hook
  (startup priority -1, one before Configuration Manager; shutdown
  priority 8, one after Crash Recovery's mark-clean) so they capture as
  much of the real lifecycle as observability tooling reasonably can.
- `core/di/container.py` gained `debug_console`, `performance_profiler`,
  `state_inspector`, and `api_inspector` providers.
- `infrastructure/api/fastapi_server.py` mounts the two new routers and
  conditionally attaches the API Inspector middleware.

### Known limitations (documented, not silently implied otherwise)
- Debug Console's real-time relay publishes one `EventBus` event per
  captured log line via `publish_nowait`'s no-running-loop fallback
  (loguru's `enqueue=True` sink runs on its own background thread) --
  a real per-line cost, acceptable for a developer-only, opt-in tool,
  not free.
- Performance Profiler's "per-service" data is honestly process-wide
  (service **state** is per-service; CPU/memory are not -- the same
  limit `core/plugins/sandbox.py` already documents for the same
  underlying `psutil.Process` reason).
- API Inspector never records request/response bodies or headers
  (secrets-handling boundary, `docs/ARCHITECTURE.md` section 17) --
  method/path/status/duration only.

Full suite: 815 passed (up from 741 at 0.11.0), zero regressions;
frontend unaffected (this release is backend-only). mypy/ruff/black
diffed against a clean pre-task-group `git stash -u` baseline: zero
new findings outside the same accepted `PLC0415` lazy-import pattern
every prior task group's own tests already carry (every other finding
category's count is byte-for-byte unchanged).

## [0.11.0] — M9, Task Group D (Plugin Platform)

Closes out M9's Plugin Platform module in full, preserving the
original scope unchanged. Architecture unchanged -- Python + FastAPI +
Tauri, no migration. Only Task Group E (Developer Platform Tools)
remains open in M9.

### Added
- `core/plugins/` -- the full Plugin Platform: `sdk.py` (`IPlugin`
  lifecycle hooks, the fixed 10-scope permission vocabulary, a
  hand-rolled semver/range comparator), `manifest.py` (`PluginManifest`,
  extended with the Universal Compatibility fields `supported_os`,
  `supported_arch`, `required_capabilities`, `min_jarvis_version`),
  `loader.py` (discovery, Kahn's-algorithm dependency ordering, version/
  platform compatibility checks, real hot reload), `sandbox.py`
  (in-process fault-isolated + timeout-bounded execution, plus an
  opt-in out-of-process `multiprocessing` tier with `psutil`-based
  resource-budget monitoring), `extension_api.py` (`PluginContext`:
  permission-gated filesystem/network/hotkeys/notifications,
  unrestricted events/commands scoped to the plugin's own declared
  surface, config, platform capability queries), `permissions.py` (the
  real `IPermissionChecker` -- least-privilege declare -> pending ->
  grant/deny, persisted and audited), `registry.py` (`PluginRegistry`:
  enable/disable/install/uninstall/update with real rollback support),
  `store.py` (directory/`.zip` package staging, SHA-256 integrity
  checks, real Ed25519 signature verification), `marketplace.py`
  (`IPluginRepository` abstraction, `LocalPluginRepository`, search/
  categories, in-memory ratings/reviews).
- `core/interfaces/platform.py` + `infrastructure/platform/adapter.py`
  -- a new Platform Abstraction Layer for Universal Compatibility;
  Windows is the only implemented adapter today, but nothing above
  `IPlatformAdapter` branches on OS directly.
- Fourteen new events (`core/events/events.py`): `PluginDiscoveredEvent`,
  `PluginLoadedEvent`, `PluginLoadFailedEvent`, `PluginUnloadedEvent`,
  `PluginCrashedEvent`, `PluginEnabledEvent`, `PluginDisabledEvent`,
  `PluginPermissionGrantedEvent`, `PluginPermissionDeniedEvent`,
  `PluginInstalledEvent`, `PluginUninstalledEvent`, `PluginUpdatedEvent`,
  `PluginCustomEvent`, `PluginNotificationEvent` -- eleven of which
  (excluding the plugin-authored `PluginCustomEvent`/
  `PluginNotificationEvent`, and `PluginCrashedEvent`, not yet published
  anywhere) are relayed over the Runtime WebSocket API.
- `PluginSettings` (`core/config/settings.py`) -- `enabled`,
  `sandbox_mode`, `hook_timeout_seconds`, `max_cpu_percent`,
  `max_memory_mb`, `allow_unsigned_packages`, `marketplace_index_path`.
- `tests/fixtures/plugins/hello_world/` -- a real reference plugin
  (registers a slash command and a hotkey) used by a new end-to-end
  integration test, `tests/integration/test_plugin_platform_e2e.py`,
  proving this module's own acceptance criterion against the real
  Loader -> Sandbox -> Permission Model -> Registry stack, including
  the full least-privilege permission workflow.
- 199 new unit/integration tests across twelve files.

### Changed
- `app.py` gained `_register_task_group_d_hooks`, wiring `PluginRegistry`
  into `RuntimeManager` as the outermost layer over an already-running
  core: plugins start last (priority 12, after Task Group C's 10-11)
  and stop first (priority -1, before Task Group B's own chain). A
  no-op when `settings.plugins.enabled` is false.
- `core/lifecycle/runtime_ws_hub.py`'s `EVENT_TYPE_NAMES` gained eleven
  `plugin.*` entries.
- `core/config/constants.py`/`paths.py` gained `PLUGINS_SUBDIR` and a
  `plugins_dir()` helper, included in `ensure_runtime_dirs()`.
- `core/di/container.py` gained `platform_adapter`, `plugin_loader`,
  `plugin_sandbox`, `permission_model`, `plugin_registry`,
  `plugin_store`, and `marketplace` providers.

### Known limitations (documented, not silently implied otherwise)
- Process-isolated plugins receive a minimal `MinimalPluginContext` in
  `on_load`, not the full in-process `PluginContext` -- a live
  `EventBus` reference cannot cross a process boundary by value. A real
  IPC-relayed Extension API for that tier is future work.
- The `network` permission scope is a declaration check only -- this
  platform does not yet mediate or quota a plugin's actual outbound
  HTTP calls.
- No hosted, signed Plugin Store index exists yet (`LocalPluginRepository`
  is the real, complete v1 implementation of the roadmap's own "no
  hosted infra for v1" design); a `GitHubPluginRepository`/
  `CloudPluginRepository` is a second `IPluginRepository`
  implementation away, not a redesign.
- Ratings/reviews (`InMemoryReviewStore`) do not persist across a
  restart and have no real user-identity system beyond a
  caller-supplied reviewer string.
- The permission-approval *workflow* (declare/pending/grant/deny,
  persisted and audited) is real; an interactive approval UI is Task
  Group E's Developer Platform Tools to build.

Full suite: 741 passed (up from 542 at 0.10.0), zero regressions;
frontend: 293 passed, unaffected (this release is backend-only).
mypy/ruff/black diffed against a clean pre-task-group `git stash -u`
baseline: zero new findings outside the same pre-existing,
already-accepted `providers.Singleton` annotation and `PLC0415`
lazy-import patterns `MASTER_ROADMAP.md` §15 documents.

## [0.10.0] — M9, Task Group C (Background Task Manager, Crash Recovery, Resource Manager)

Closes out M9's Reliability module in full (Health Monitor's
foundational slice already shipped under Task Group B). Follows the
Aug 2026 roadmap reconciliation pass (docs-only, no source changes).
Architecture unchanged -- Python + FastAPI + Tauri, no migration.

### Added
- `core/lifecycle/background_task_manager.py` -- `BackgroundTaskManager`:
  a bounded-concurrency (`asyncio.Semaphore`) task queue with per-task
  fault isolation. `submit()`/`cancel()`/`stop()` (graceful drain). A
  done-callback fallback handles a task cancelled before its
  coroutine's first scheduling turn -- Python never enters an unstarted
  coroutine's own body to run its `except CancelledError`, so `_run()`'s
  in-body handler alone can't catch that case.
- `core/lifecycle/crash_recovery.py` -- `CrashRecoveryManager`: a
  "mark dirty at start, mark clean at end" on-disk marker
  (`runtime_state.json`, existing `config_dir` JSON-config-store
  convention) detects an unclean previous shutdown and publishes
  `CrashRecoveredEvent`. Does not claim to auto-respawn a crashed
  process -- real, separate, future work.
- `core/lifecycle/resource_manager.py` -- `ResourceManager`: CPU/
  memory budget tracking (new `ResourceSettings`,
  `core/config/settings.py`), subscribing to `HealthMonitor`'s existing
  `HealthUpdatedEvent` instead of polling `psutil` a second time.
  Publishes `ResourceBudgetExceededEvent` only on the transition into
  violation.
- Five new events (`core/events/events.py`): `TaskStartedEvent`,
  `TaskCompletedEvent`, `TaskFailedEvent`, `CrashRecoveredEvent`,
  `ResourceBudgetExceededEvent` -- all relayed over the Runtime
  WebSocket API (`runtime.crash_recovered`,
  `task.started/completed/failed`, `resource.budget_exceeded`).
- 29 new tests across three files covering bounded concurrency, fault
  isolation, both cancellation code paths (mid-run and
  pre-first-scheduling-turn), crash detection across independent
  marker-file instances, corrupt-marker resilience, and
  budget-transition-only event publishing.

### Changed
- `app.py` gained `_register_task_group_c_hooks`, wiring all three new
  managers into `RuntimeManager`: Crash Recovery's dirty-check runs
  immediately after Configuration Manager (before Service Manager);
  Background Task Manager and Resource Manager join at the end of
  startup. Shutdown reverses this, with Crash Recovery marking the run
  clean *last of all*. Task Group B's own five shutdown-hook priorities
  were renumbered (0-4 -> 2-6, in-place, no migration concern) to make
  room.
- `core/lifecycle/runtime_ws_hub.py`'s `EVENT_TYPE_NAMES` gained five
  more entries for the events above.

### Fixed (Project Completion Audit, ahead of M9 Task Group D)
- **Version drift** — `pyproject.toml`, `Settings.app_version`, and
  `src/jarvis/__version__.py` were still `"0.5.2"` despite this
  changelog already being at `0.10.0`; all three now read `"0.10.0"`
  in lockstep. The same drift this project's own `MASTER_ROADMAP.md`
  §15 previously recorded as "Resolved" during the M5A pass had
  quietly recurred.

### Documentation (Project Completion Audit)
- Full-repository sweep for TODOs, placeholders, mocks, deprecated
  code, doc/implementation mismatches, and missing tests across M0–M9.
  Found: three stale "M8" labels on Plugin-Platform-related
  `MASTER_ROADMAP.md` §15 Future items (relabeled M9 Task Group D --
  scope never changed, only the label, from before the Aug 2026
  retitling); §16's development-order table using the pre-reconciliation
  🟢/no-symbol convention on the M7/M8/M9 rows (now 🟡 Active,
  consistent with §2/§14); `docs/ARCHITECTURE.md` §5 still saying "no
  FastAPI layer exists yet" (false since M9 Task Group B); two
  undocumented, real exceptions to §5's own contract
  (`/api/v1/sessions`'s response isn't wrapped in the `{data, meta}`
  envelope; the real health router mounts at `/api/health`, not
  `/api/v1/health`, since M0) -- both now documented in place rather
  than left as silent drift; `README.md`'s "Roadmap" section still
  claiming only M0–M2 and the core of M3 were implemented, and its
  project-layout diagram missing `frontend/` entirely.
- `MASTER_ROADMAP.md` §15 Pending gained a consolidated "M8/M9-era
  items" entry cross-referencing M8's Deferred Backlog and M9 Task
  Group B/C's own Future Work notes, plus the two new API-contract
  exceptions and the health-router prefix mismatch above -- so §15
  remains the one place every open item in the repository is tracked,
  not just M0–M7's.
- No new source-code behavior changed beyond the version-string fix
  above; `pytest`/`mypy`/`ruff`/`black` re-verified against the same
  baseline M9 Task Group C already validated.

## [0.9.0] — M9, Task Group B (Service/Session/Configuration Manager, Health Monitor, Runtime WebSocket API)

Second and final Runtime Core deliverable, closing out every M9
Runtime Core bullet Task Group A deferred. Architecture unchanged from
Task Group A's own addendum -- Python + FastAPI + Tauri, no migration;
this entry documents implementation only.

### Added
- `core/interfaces/service.py` -- `IService` Protocol
  (`docs/ARCHITECTURE.md` §8) made real code for the first time, plus
  `HealthStatus`/`ServiceStatus` frozen dataclasses.
- `core/lifecycle/service_manager.py` -- `ServiceManager`: dependency-
  ordered startup/shutdown, `restart()`, health polling, fault
  isolation. Wraps `ConversationService`/`ChatService`/`MemoryService`/
  `ThemeService` in thin `IService` adapters (composition, not a
  retrofit of the wrapped services themselves).
- `core/lifecycle/session_manager.py` -- `SessionManager` and a new
  `runtime_sessions` table (`infrastructure/database/models.py`,
  `RuntimeSessionRepository`): persisted session creation/close,
  dangling-session recovery after an unclean shutdown, optional
  (nullable) links to `Conversation.id` and the agent orchestrator's
  LangGraph `thread_id`.
- `core/lifecycle/configuration_manager.py` -- `ConfigurationManager`:
  live `reload()` restricted to a `SAFE_RELOAD_SECTIONS` allowlist
  (`ui`, `voice_announce`, `memory`, `update`, `dev_mode`), publishing
  `ConfigurationUpdatedEvent` with the changed dotted keys only.
- `core/lifecycle/health_monitor.py` -- `HealthMonitor`: non-blocking
  `psutil`-based CPU/RAM/uptime/startup-duration/service-health/
  restart-count polling, `HealthUpdatedEvent` per tick,
  `register_collector()` extension point for future metrics.
- `core/lifecycle/runtime_ws_hub.py` + `infrastructure/api/routes/
  runtime_ws.py` -- `RuntimeWebSocketHub`, the first real
  implementation of `docs/ARCHITECTURE.md` §6's WebSocket standard at
  `/api/v1/ws`: envelope, 30s heartbeat, `resume`/60s replay buffer,
  relaying all eleven new events (`runtime.started/ready/stopping/
  shutdown`, `service.started/stopped/failed`,
  `configuration.updated`, `session.created/closed`,
  `health.updated`).
- `infrastructure/api/routes/sessions.py` -- `POST`/`GET`/`DELETE
  /api/v1/sessions` -- issues the session id used as the WebSocket
  `token` query param, the real `Depends(get_current_session)`
  mechanism §5/§6 reference.
- `infrastructure/api/embedded_server.py` -- `EmbeddedApiServer` embeds
  the FastAPI app inside the existing PySide6/qasync loop so the
  WebSocket relay is reachable from the app's one real running process.
- Nine new events (`core/events/events.py`): `RuntimeStartedEvent`,
  `RuntimeShutdownCompleteEvent`, `ServiceStartedEvent`,
  `ServiceStoppedEvent`, `ServiceFailedEvent`, `SessionCreatedEvent`,
  `SessionClosedEvent`, `ConfigurationUpdatedEvent`,
  `HealthUpdatedEvent`.
- 58 new tests across six files covering dependency ordering, restart
  behavior, failure isolation, session persistence/recovery, safe
  live-reload, non-blocking health polling, and the real FastAPI
  WebSocket transport end-to-end (auth, relay, resume/replay) via
  `TestClient` against a real SQLite database.

### Changed
- `core/lifecycle/runtime_manager.py`'s `RuntimeManager` gained an
  optional `event_bus` constructor parameter (every existing zero-arg
  call site unaffected) so `startup()`/`shutdown()` publish
  `RuntimeStartedEvent`/`RuntimeShutdownCompleteEvent` at the very
  start/end of each sequence.
- `app.py`'s `_run_gui()` wires all five new managers into
  `RuntimeManager` via a new `_register_task_group_b_hooks` method
  (split out to keep `_run_gui`'s statement count readable) in
  deterministic order -- Configuration Manager -> Service Manager ->
  Session Manager -> Health Monitor/WebSocket relay/embedded API
  server -> Application Ready -- shutdown reverse. The `memory_policies`
  startup hook that lived directly in `app.py` since Task Group A moved
  into `MemoryServiceAdapter.start()`.
- `infrastructure/api/fastapi_server.py`'s `create_app()` now accepts
  an optional DI `Container`, mounting the new session/WebSocket
  routers only when one is supplied.

### Documentation (roadmap reconciliation pass, ahead of M9 Task Group C)
- `MASTER_ROADMAP.md` §2 ("Current status") was stale since before M8
  even started (`0.5.2`, "In progress: M7", no mention of M8/M9) --
  corrected to `0.9.0` with real M7/M8/M9 status.
- `MASTER_ROADMAP.md` §14 (version timeline): every milestone now
  carries exactly one of four states (✅ Completed, 🟡 Active, 🟠
  Deferred, 🔴 Planned) instead of a `🟡` used ambiguously for both
  "active" (M8) and "fully unstarted" (M10-M23B).
- `MASTER_ROADMAP.md` §8 M8 gained a **Deferred Backlog** subsection
  (Notification Center, Context Menu system, Background Task Manager,
  Workspace views, Window management, Responsive/DPI/Multi-monitor,
  Settings & User Profiles, Developer Mode's 9 read-only viewers,
  Premium UI Polish, Optimization & QA) -- verified against the actual
  repository (`notification-layer.tsx`/`context-menu-layer.tsx` are
  real, empty, reserved anchors; `background-tasks.store.ts` is
  display-only), not assumed from prior notes. **M8 remains explicitly
  not 100% complete.**
- `MASTER_ROADMAP.md` §8 M9's Reliability/Plugin Platform/Developer
  Platform Tools modules gained explicit Task Group C/D/E labels.
- `IMPLEMENTATION_ROADMAP.md` gained a matching §6 Deferred Backlog
  (checklist-level detail) and explicit Task Group C/D/E entries under
  §5; Phase 3's checklist gained the three previously-undocumented
  items (Notification Center, Context Menu system, Background Task
  Manager) it was missing.
- No source code changed in this pass -- `pytest`/`mypy`/`ruff`/`black`
  re-verified clean against the same baseline M9 Task Group B already
  validated.

## [0.8.0] — M9, Task Group A (Runtime Manager & Application Lifecycle)

First real M9 (Runtime & Core Services) deliverable, consuming the
Version Timeline's reserved `0.8` slot. Follows an architecture review
the user requested and then explicitly closed: keep Python + FastAPI +
Tauri as the official architecture, unchanged — see
`docs/MASTER_ROADMAP.md`'s own changelog addendum for the full
reasoning. Scopes only Runtime Core's first two bullets (Runtime
Manager, Application Lifecycle), not all of M9.

### Added
- `stt_provider.preload()`-style startup work now registers with
  `RuntimeManager` instead of a hand-written `try`/`except` block in
  `app.py` -- memory-policy enforcement and Whisper preload both
  converted, matching the exact "must never block boot" guarantee
  their existing comments already promised, now enforced by
  `RuntimeManager` itself.
- `AppReadyEvent`/`ShutdownRequestedEvent` (`core/events/events.py`)
  now genuinely publish on the real `EventBus` -- previously declared
  but unused "placeholder examples for milestone authors."
  `AppReadyEvent` fires once every registered `RuntimeManager` startup
  hook has run; `ShutdownRequestedEvent` fires at the start of
  `MainWindow._graceful_quit()`, before any resource releases.
- `tests/unit/test_runtime_manager.py` -- extends the original
  `test_shutdown_manager.py` one-for-one (regression coverage for the
  rename) plus new startup-side and cross-direction-independence
  coverage.

### Changed
- `core/lifecycle/shutdown_manager.py`'s `ShutdownManager` (Milestone
  5.5) renamed and generalized to `core/lifecycle/runtime_manager.py`'s
  `RuntimeManager` -- the shutdown-side API (`register`/`unregister`/
  `shutdown`) is behavior-unchanged, just renamed alongside a new,
  symmetric startup-side API. The DI container's `shutdown_manager`
  provider is renamed to `runtime_manager`; every real call site
  across `src/` and `tests/` updated to match.

## [0.7.5] — M8 Phase 4, Task Group L (Dashboard widget drag-and-drop)

Fifth and final task group of the Premium UI & Voice Experience
initiative. Ships real mouse-driven drag-to-reorder for Dashboard
widgets, additive alongside the existing Move up/down buttons.

### Added
- `stores/dashboard-layout.store.ts`'s `reorderPeers(peerIds, pinned)`
  -- applies a full drag-produced permutation of one pin group, leaving
  the opposite pin group and hidden widgets' positions untouched.
  Additive alongside the existing `moveWidget()`; both operate on the
  same `order` array.
- `features/dashboard/dashboard-grid.tsx` -- two `motion/react`
  `Reorder.Group` instances (one per pin group, `Reorder.Item` per
  widget) with a dedicated drag handle (`dragListener={false}` +
  `useDragControls()`) so dragging doesn't conflict with the card's own
  five buttons or its real content. Dragging only ever reorders a
  widget among its own pin-group peers, matching the Move buttons'
  existing constraint.
- `e2e/dashboard-widgets.spec.ts` -- real, mouse-driven Playwright
  verification (`page.mouse`) that the drag gesture actually reorders
  widgets and persists to the real store, plus a regression test
  confirming Move up/down still work unchanged.

## [0.7.4] — M8 Phase 4, Task Group K (Accessibility settings)

Fourth task group of the Premium UI & Voice Experience initiative.
Ships a real Settings > Accessibility page for the preferences `[0.7.2]`
and `[0.7.3]` already made real, and adds a genuine third one.

### Added
- `features/settings/settings-page.tsx` -- the Settings module's real
  route element, replacing its `PlaceholderRoute`. An Accessibility
  section with three real, working toggles (Skip startup animation,
  Reduced motion, Disable glass effects), the first non-Developer-Mode
  surface for these preferences.
- `reducedMotion` -- a new, real, persisted preference: an app-level
  override on top of the OS-level `prefers-reduced-motion` `MotionConfig`
  already honors, for users whose OS setting doesn't (or can't)
  express it.
- `providers/app-providers.tsx`'s `AccessibleMotionConfig` feeds the
  real preference into `MotionConfig`'s own `reducedMotion` prop, so
  every declarative Motion animation in the app (`DesktopShell`'s
  stagger reveal, `JarvisLogo`'s pulse, etc.) respects it automatically.
- Developer Mode's Startup Preview panel gained a matching "Reduced
  motion" toggle alongside its existing two.

### Changed
- `stores/startup-preferences.store.ts` renamed to `stores/
  accessibility-preferences.store.ts` (`useStartupPreferencesStore` ->
  `useAccessibilityPreferencesStore`, persist key `jarvis.startup-
  preferences` -> `jarvis.accessibility-preferences`) -- it now backs
  real, app-wide UI, not just the startup sequence, and the old name
  had become misleading.

### Fixed
- **`startup-gate.tsx` and `voice-waveform-renderer.tsx` ignored the
  new `reducedMotion` preference entirely.** Both called Motion's
  public `useReducedMotion()` hook, which only ever reads the OS-level
  media query and completely ignores `MotionConfig`'s own
  `reducedMotion` context value -- the app preference had zero effect
  on either real call site. Fixed by switching both to Motion's own
  `useReducedMotionConfig()`, the hook Motion itself uses internally to
  combine the OS query and the `MotionConfig` value.
- `e2e/app-shell.spec.ts` was still seeding the old, now-stale
  `jarvis.startup-preferences` localStorage key, silently falling back
  to the real ~4.2s startup animation on every test run instead of
  skipping it. Updated to seed the renamed key.

## [0.7.3] — M8 Phase 4, Task Group J (Glass design system)

Third task group of the Premium UI & Voice Experience initiative.
Ships real glassmorphism on the three surfaces the brief names —
Sidebar, Card, Command Palette — all wired to the `disableGlassEffects`
preference `[0.7.2]` already shipped, making it genuinely app-wide for
the first time.

### Added
- `hooks/use-glass-effects.ts` -- `useGlassEffectsEnabled()`, a thin
  wrapper around the real, persisted `disableGlassEffects` preference
  so UI primitives can read it under a name that makes sense outside a
  startup context.
- `components/layout/desktop-shell.tsx` -- a subtle, static ambient
  glow behind the shell (two blurred accent/primary blobs, `aria-hidden`,
  skipped entirely when glass effects are disabled) so the new glass
  surfaces have real visual content to blur.
- Sidebar: `bg-card/70 backdrop-blur-xl`, falling back to solid
  `bg-card`.
- `components/ui/card.tsx`: a conservative `bg-card/85 backdrop-blur-md`
  on the shared primitive every dashboard widget/dialog/panel already
  builds on -- lighter blur than Sidebar/Command Palette since Cards
  hold dense text at every size.
- Command Palette: `bg-popover/70 backdrop-blur-2xl`, scoped to
  `CommandDialog`'s own `DialogContent` override in `components/ui/
  command.tsx` -- the shared `Dialog`/`Command` primitives other real
  dialogs render through are untouched.

### Changed
- `stores/startup-preferences.store.ts`'s `disableGlassEffects` now
  gates every real glass surface in the app, not just the startup
  sequence's own glow -- one real preference, not a second one that
  could drift out of sync.

## [0.7.2] — M8 Phase 4, Task Group I (Startup Experience & Lazy Loading)

Second task group of the Premium UI & Voice Experience initiative.
Reuses `[0.7.0]`/`[0.7.1]`'s Voice String as the centerpiece of a new
cinematic startup sequence, per the brief's explicit instruction not to
redesign or replace it.

### Added
- **Startup sequence** (`components/startup/startup-sequence.tsx`) --
  a choreographed ~4.2s animation: energy point, ripple, logo assemble/
  pulse (`components/startup/jarvis-logo.tsx`), morph into the Voice
  String, Voice String activation and expansion, then a center-outward
  glass reveal. Drives the real `voice-state.store.ts` (`wake` then
  `idle`) at the relevant phases -- the Voice String shown during
  startup is the exact same store-driven component used everywhere
  else. The reveal is a real animated CSS `mask-image:
  radial-gradient(...)` (`useMotionTemplate`/`useMotionValue`), not an
  opacity approximation. No startup text ever renders -- only an
  `sr-only role="status"` string for assistive tech.
- `core/startup-orchestrator.ts` -- the real work the animation hides.
  `STARTUP_TASKS` maps the brief's High/Medium/Low tiers onto this
  codebase's actual registration calls (`registerCoreStatusBarItems`,
  `registerCoreDashboardWidgets`, `registerPlaceholderModules`), moved
  here from `main.tsx`. `low` has no real task yet -- left honestly
  empty rather than padded with a fabricated delay. `runStartupSequence()`
  is idempotent (caches its own promise), so any number of callers
  share one real execution.
- `components/startup/startup-gate.tsx` -- reveals the real app only
  once both the real orchestrator work and the animation finish.
  Skips straight to the dashboard when the new persisted
  `skipStartupAnimation` preference (`stores/startup-preferences.store.ts`)
  is set, or when `useReducedMotion()` reports a system preference.
- Developer Mode's **Startup Preview** section
  (`features/developer/startup-preview.tsx`) -- replays the real
  `StartupSequence` on demand and toggles both real preferences, for
  QA without restarting the app.
- `components/layout/desktop-shell.tsx` gained an additive staggered
  fade/rise for its Sidebar/Header/Status-Bar/Dock regions on first
  mount -- since the real dashboard only mounts once startup is truly
  done, this stagger doubles as the brief's "Dashboard Reveal"
  sequence.

### Fixed
- **React `<StrictMode>` double-invoke hang**: `StartupGate`'s
  initializing effect runs twice in development by design; the second
  call to `registerPlaceholderModules()` threw (a module can't
  register with `ApplicationRegistry` twice), and the resulting
  unhandled promise rejection silently stalled the reveal forever.
  Fixed by making `runStartupSequence()` idempotent at its source
  rather than guarding each call site.
- `StoreProvider` was missing the new `useStartupPreferencesStore` from
  its persisted-store hydration gate, which could let `StartupGate`
  read the stale default before rehydration completed. Added it to the
  `persistedStores` array.

## [0.7.1] — Voice String revision (real-time multi-bar waveform)

Same-day revision of `[0.7.0]`'s Voice String, once the Premium UI &
Voice Experience brief asked specifically for a "premium real-time
voice waveform" (many animated bars, matching modern voice-assistant
quality) rather than a single sine-path line.

### Changed
- **Voice String** is now a glassmorphism panel of 40 independently-
  animated bars, not a single SVG path. Split into
  `components/voice/voice-waveform-renderer.tsx` (the pure renderer --
  zero store dependency, accepts `voiceState`, `microphoneLevel`,
  `ttsLevel`, `intensity` as props) and `components/voice/voice-
  string.tsx` (now just the thin layer wiring real store state in) --
  direct answer to the brief's "separate rendering from state
  management" and "design it so the future voice backend can stream
  real audio amplitudes directly into the renderer" requirements.
- Each bar derives its height from one shared `useTime()` clock via
  `useTransform` (one requestAnimationFrame loop feeding many cheap
  derived values, bound straight to the DOM, `transform`-only --
  GPU-compositable, no layout shifts) rather than 40 independent RAF
  subscriptions.
- Per-state "envelope" shapes implement the brief's state-by-state spec
  directly: Wake's center-outward pulse, Thinking's slow traveling
  wave (distinct from Listening), Listening/Speaking's reactive look
  (two overlapping deterministic sine terms per bar -- a fixed
  per-bar phase seed, not `Math.random()`, for "smooth interpolation,
  no jitter" rather than actual jitter).
- Glass-panel styling (blurred translucent background, soft
  state-colored bloom) uses this app's existing semantic color tokens,
  not new hardcoded hex values, for the brief's "cyan/blue gradient"
  look.

### Added
- `stores/voice-audio-levels.store.ts` -- real `microphoneLevel`/
  `ttsLevel` fields, always `0` today (no audio pipeline exists),
  additively boosting the renderer's procedural ambient motion once
  real, with bars nearer the panel's center reacting more strongly.
- Developer Mode's Voice State Preview panel now drives the raw
  renderer directly, with manual mic/TTS level sliders (writing to the
  real store above) and a local intensity control, so the renderer's
  full prop surface can be QA'd before either real backend exists.

## [0.7.0] — M8 Phase 4, Task Group H (Voice State Architecture)

First task group of the Premium UI & Voice Experience initiative.

### Added
- **Voice String** (`components/voice/voice-string.tsx`) -- JARVIS's
  voice identity, replacing the Orb concept (never built in this
  frontend to begin with). A continuous animated wave whose color,
  speed, and amplitude communicate Idle/Wake/Listening/Thinking/
  Speaking/Success/Error -- no visible state label ("Listening...")
  ever renders; an `aria-label` carries the state name for screen
  readers only. Respects `useReducedMotion()` directly, since it's a
  continuous `useTime()`/`useTransform` loop, not a discrete `animate`
  transition `MotionConfig`'s app-wide `reducedMotion="user"` already
  covers.
- `core/voice-state-machine.ts` -- a real, validated state machine
  (mirrors `core/module-lifecycle.ts`'s established pattern: fixed
  states, a transition graph, a typed `InvalidVoiceStateTransitionError`
  on an illegal jump) for the full 7-state set.
- `stores/voice-state.store.ts` -- the single source of truth. Starts
  and stays `idle`: no real voice backend exists yet
  (`core/interfaces/voice-integration.ts` only covers command
  bindings; no WebSocket voice event relay exists). The one real entry
  point, `transition()`, is exactly what a future voice pipeline will
  call.
- **Live Transcript** (`components/voice/live-transcript.tsx` +
  `stores/voice-transcript.store.ts`) -- streaming word-by-word,
  fades 4s after the last word. Starts and stays empty until a real
  STT stream exists.
- **Developer Mode's Voice State Preview** panel
  (`features/developer/voice-state-preview.tsx`) -- manually drives or
  auto-cycles the real `useVoiceStateStore`, for animation QA only.
  Disabled by default, never an end-user surface. Manual buttons only
  ever offer legal next states, so a click can never hit the store's
  own validation and throw.
- `voice` module now has a real route element
  (`features/voice/voice-page.tsx`), replacing its `PlaceholderRoute`.

## [0.6.4] — M8 Phase 3, Task Group G (Command Palette)

### Added
- **Command Palette** -- fills in `components/layout/command-palette-
  layer.tsx`, the DesktopShell region reserved since Phase 3's own
  foundation pass. Opens on `Ctrl+K` **and** `Ctrl+Shift+P`
  (`providers/command-palette-provider.tsx`) -- the roadmap's canonical
  binding is `Ctrl+Shift+P`, but the header's Search button has
  visually promised "Ctrl+K" since Phase 1; both are honored so neither
  promise is silently broken.
- "Navigate" entries: real, registry- and enablement-driven module
  links (`ApplicationRegistry` + `ModuleEnablementStore`), the same
  data Sidebar/Dock already read.
- "Commands" entries: `getAllCommandPaletteEntries()`
  (`core/interfaces/navigation-interface.ts`, M8 Phase 2) -- confirmed
  real, already-wired infrastructure (every module's mount/unmount
  already calls `registerNavigation()` via `BaseApplication`), not dead
  code. **No new `ContributionRegistry` instance was built for this** --
  reusing the mechanism that already exists rather than duplicating it.

### Fixed
- `components/ui/command.tsx`'s `CommandDialog` never wrapped its
  `children` in cmdk's own `<Command>` root -- any `CommandInput`/
  `CommandList`/`CommandItem` rendered inside it threw at render time
  ("Cannot read properties of undefined (reading 'subscribe')"), since
  there was no cmdk context above them. Never caught before because
  nothing had used `CommandDialog` until this task group. Fixed at the
  primitive.
- Added a `scrollIntoView` no-op stub to `test/setup.ts` -- jsdom
  doesn't implement it and cmdk's list uses it internally; same
  category as the existing `ResizeObserver`/`matchMedia` stubs already
  there.

## [0.6.3] — M8 Phase 3, Task Group F (Dashboard Widget Grid)

### Added
- **Dashboard (Home) view** is now a real page
  (`features/dashboard/dashboard-grid.tsx`), replacing
  `PlaceholderRoute` for the `home` module -- registry- and
  enablement-driven, the same pattern Sidebar/Dock/Status Bar
  establish. Widgets support add/remove, resize (4 fixed grid
  footprints: 1×1, 2×1, 1×2, 2×2), move (reorder among same-pinned-
  state peers), pin/unpin, and layout export/import as one validated
  JSON document.
- `stores/dashboard-layout.store.ts` (new, persisted) -- the grid's own
  preference layer (visible/size/order/pinned per widget id), kept
  separate from `DashboardWidgetRegistry`'s "what widgets exist," the
  same split `dock.store.ts`/`application-registry.ts` already
  establish.
- `DashboardWidgetContribution` gained `isCore`, matching
  `StatusBarContribution.isCore`'s reasoning (Core JARVIS's widgets
  register under the reserved `moduleId: "core"`, which isn't a real
  `ApplicationRegistry` entry an enablement check could resolve
  `isCore` from otherwise).
- Core JARVIS's 4 built-in widgets, all backed by real state: **Notifications**
  (the notification center), **Recent Activity** (a merged timeline of
  notifications and background task completions/failures, sorted by
  real timestamps), **Quick Actions** (real navigation links to core
  modules), **System Status** (real connection status, background task
  state, and honest "Not configured" for AI Provider/Voice/Automation,
  reusing the exact same labels as the Status Bar via the new shared
  `lib/connection-status-display.ts`).
- `BackgroundTask` gained a `timestamp` field (set internally on every
  status transition, never caller-supplied) so Recent Activity has a
  real ordering signal.

### Fixed
- The root `.gitignore`'s Python-oriented `lib/`/`lib64/` patterns
  (unanchored) were silently matching `frontend/src/lib/` too --
  `icon-registry.ts`, `motion.ts`, and `utils.ts` had **never actually
  been committed to `origin/main`** despite being depended on
  throughout the frontend since Phase 1; a fresh clone would not have
  built. Anchored both patterns to the repo root (`/lib/`, `/lib64/`)
  and committed the previously-invisible files.

### Not shipped (documented, not faked)
- **Tasks, Calendar, and Notes widgets were not built.** No real
  backing store, data model, or backend endpoint exists anywhere in
  this codebase for any of the three -- a widget with a title but no
  real feature behind it would be exactly the fake/placeholder
  implementation this project's standing rule forbids. Each becomes a
  real widget once its own feature ships (see `MASTER_ROADMAP.md`'s
  Task Group F addendum for the reasoning and target milestones).
  `DashboardWidgetRegistry` places no cap on widget count, so this is
  additive later, not a rework.

## [0.6.2] — M8 Phase 3, Task Group E (Status Bar)

### Added
- **Status Bar** is now `ContributionRegistry`-driven -- a fourth named
  instance (`statusBarRegistry`, `core/interfaces/status-bar-interface.ts`)
  alongside Navigation and Dashboard Widgets, not a new bespoke
  registry. No hardcoded status items anywhere in
  `components/layout/status-bar.tsx`.
- Core JARVIS's 9 built-in items, registered through the same path a
  future plugin's own status item would use: left (Current Workspace,
  Active Module), center (Current Running Task, Background Task
  Progress), right (AI Provider, Voice Status, Automation Status,
  Internet/Offline, Notification Indicator). Six are real data today
  (`WorkspaceManager`, `background-tasks.store.ts`,
  `notifications.store.ts`, the existing WebSocket connection hook);
  three (AI Provider, Voice Status, Automation Status) have no real
  backend data source yet and honestly show "Not configured" rather
  than fabricated values.

### Changed
- `DashboardWidgetContribution.render` retyped from `() => unknown` to
  a real component reference, matching `StatusBarContribution.render`'s
  contract -- building an actual consumer (the Status Bar) clarified
  the correct shape: each contribution renders as its own element and
  manages its own reactivity, which calling a plain callback inside a
  `.map()` over a variable-length list cannot do without violating
  React's Rules of Hooks.

## [0.6.1] — M8 Phase 3, Task Group D (Dock) + Contribution Registry unification

### Fixed
- `DashboardWidgetRegistry`, added in `[0.6.0]`, was its own bespoke
  class mirroring `ApplicationRegistry`'s pattern -- exactly the
  "multiple unrelated registries" anti-pattern to avoid. Extracted the
  shared mechanism into `core/contribution-registry.ts`'s generic
  `ContributionRegistry<T>`; `DashboardWidgetRegistry` is now a thin
  named instance of it. `NavigationContribution`'s internal storage
  (previously its own raw `Map`) migrated onto the same class. Both
  public APIs are unchanged -- no consuming code needed to change.

### Added
- **Phase 3, Task Group D — Dock**: registry- and enablement-driven,
  same pattern as Sidebar (Task Group C) -- pinned modules only render
  if also registered *and* enabled; a pinned-but-disabled module
  disappears from the Dock. Active-state highlighting from
  `WorkspaceManager`, not the route. `routes/nav-items.ts` is now read
  by nothing in the app.
- Test coverage for `core/contribution-registry.ts` (the canonical
  suite every contribution-holding registry's own tests now stay thin
  against) and `core/interfaces/navigation-interface.ts` (had none
  before this pass).

## [0.6.0] — Milestone 8 (in progress): React Frontend Foundation & Desktop Workspace

Consolidated entry -- M8's earlier phases (React Foundation, Universal
Application Framework) and Phase 3's first three task groups shipped
across several prior sessions without individual `CHANGELOG.md`
entries; this is a single retroactive summary of where M8 actually
stands today, not a claim that everything below landed at once.
Milestone is **not** complete -- see `docs/IMPLEMENTATION_ROADMAP.md`
for the live, checkbox-level status.

### Added
- **Phase 1 — React Foundation**: `frontend/` scaffolded (React 19,
  TypeScript, Vite, Tauri shell), Tailwind + shadcn/ui + Radix + Motion
  + Lucide, design tokens ported from the real `Typography`/palette
  Python source, base layout components, React Router, Zustand store
  scaffold, API/WebSocket client architecture, Vitest + Playwright
  testing foundation.
- **Phase 2 — Universal Application Framework**: `BaseApplication`,
  `ApplicationRegistry`, `ModuleManifest`, `ModuleLifecycle`
  (TypeScript port of the backend `ModuleStateMachine`), Permission/
  Settings/Storage/Notification Frameworks, AI/Voice/Automation/API/
  Window/Navigation interfaces -- the framework every module (first-
  party or, eventually, plugin) is built on.
- **Phase 3, Task Group A — Foundation**: the 14 workspace modules
  converted from a static nav array into real, registered
  `ApplicationRegistry` entries.
- **Phase 3, Task Group B — Desktop Shell**: `DesktopShell`'s 8 named
  layout regions, `WorkspaceManager` (route -> real module mount/
  unmount lifecycle), Workspace Routing.
- **Phase 3, Task Group C — Dynamic Sidebar**: registry-driven
  Sidebar, initially with flat category grouping, then revised the
  same session per the UI Architecture Update review (below) to a
  minimal core taxonomy with a nested "AI" group and enablement
  gating.
- **UI Architecture Update** *(this session)*: `ModuleManifest.isCore`/
  `parentGroup` fields; `ModuleEnablementStore` (installed-vs-enabled
  state, distinct from registration); `DashboardWidgetRegistry` +
  `DashboardWidgetContribution` (foundation only -- no widget grid UI
  yet); Sidebar's default nav reduced to 7 core modules (Dashboard,
  AI [Conversation/Voice/Memory], Automation, Files, Settings), every
  other module (Browser, Coding, Finance, Smart Home, Calendar, Gmail,
  Spotify) now disabled by default and hidden until a user enables it.
  Full design in `docs/MASTER_ROADMAP.md` §8 M8/M9's Aug 2026 UI
  Architecture Update addendum.

### Fixed
- `ApplicationRegistry.getAll()` returned a fresh array on every call,
  which broke `useSyncExternalStore` consumers (`ModuleStateInspector`)
  with a real, reproduced-in-browser "Maximum update depth exceeded"
  crash once the registry held real data -- now cached, invalidated
  only on `register()`/`unregister()`.
- Sidebar's collapsed (icon-only) mode rendered every nav link with no
  accessible name at all (icon `aria-hidden`, label hidden) -- fixed
  with an explicit `aria-label` on every link, in both states.
- `Header`/`router.tsx` still read the retired `routes/nav-items.ts`
  static list after Sidebar moved off it, which would have shown
  stale labels ("Home" instead of "Dashboard") the moment Sidebar's
  taxonomy changed -- both now read `modules/module-definitions.ts`/
  `WorkspaceManager` directly, the same source Sidebar uses.

### Known gaps (tracked, not regressions)
- `components/layout/dock.tsx` is the one remaining reader of
  `routes/nav-items.ts` -- its own registry-driven rewrite is Phase 3
  Task Group D.
- Dashboard Widget Grid's actual UI (built-in widgets, drag/resize/
  pin, layout persistence) is foundation-only as of this entry -- see
  `docs/IMPLEMENTATION_ROADMAP.md` Phase 3.

## [0.5.2] — Critical Architecture Fix: DI container lazy loading

Out-of-band architecture fix — no roadmap change, no feature addition, no
API/interface change. Fixes the #1 Critical technical-debt item flagged by
the repository stabilization pass's performance baseline: `Container()`
construction cost ~2.5–2.9s, ~99% of which was import time, not
instantiation.

### Root cause
`dependency_injector`'s string-path provider form
(`providers.Singleton("dotted.path.Class", ...)`) resolves and imports its
target **eagerly, at class-declaration time** — contradicting
`container.py`'s own docstring claim that importing it "stays cheap and
side-effect-free." Most application services used this form. The worst
offender was `agent_orchestrator`, which pulled in
`jarvis.agents.graph` → LangGraph/LangChain/LangSmith (~1.6s alone) on
every `import jarvis.core.di.container`, whether or not the agent was ever
used in that process.

### Changed
- `src/jarvis/core/di/container.py`: converted 4 of 20 string-path
  providers to the existing `_build_*` lazy-callable pattern (already used
  by all 14 infrastructure adapters), each confirmed by direct measurement
  — not assumption — to justify the conversion:
  - `agent_orchestrator` (highest priority: ~1.6s, LangGraph/LangChain/
    LangSmith; confirmed never resolved during app boot in
    `app.py`/`main_window.py`, only on first agent/chat use)
  - `memory_service` (~1.07s; makes the cost conditional on
    `settings.memory.enabled` instead of always-paid)
  - `automation_service` (~1.07s; `Factory`-based, genuinely on-demand)
  - `conversation_service` (~0.89s; keeps bare `import container.py`
    cheap for tests/tooling)
  - The other 16 string-path services were measured and left unchanged —
    each within ~0.1s of the shared `Settings`+logger import floor the
    container pays regardless, so converting them would add boilerplate
    for no measurable benefit. See `docs/DEPENDENCY_INJECTION.md` §6 for
    the full before/after and the rule for classifying future services.
- `pyproject.toml`: added a `[tool.ruff.lint.per-file-ignores]` entry
  scoping `PLC0415` (import-not-at-top-level) off for `container.py` —
  the whole file's design requires function-local imports for laziness;
  same treatment already given to `PLE1205`/`N802` elsewhere in this
  config for the same "principled exception" reason.
- `docs/DEPENDENCY_INJECTION.md`: documented the two provider forms'
  opposite import timing, which providers are lazy today and why, and the
  measured before/after.
- Version bumped `0.5.1` → `0.5.2` — a PATCH release per
  `docs/MASTER_ROADMAP.md` §6's policy, not a milestone-driven MINOR bump.

### Performance (measured, same machine, back-to-back runs)
| Metric | Before | After | Change |
|---|---|---|---|
| `import jarvis.core.di.container` | 2.940s | 1.595s | **−45.7%** |
| `Container()` construction | ~4.19s\* | 1.735s | **−58.6%**\* |
| Resolve a cheap service (`settings_service`) | ~3.46s\* | 1.613s | **−53.3%**\* |
| RSS at that checkpoint | ~101MB\* | 55.5MB | **−45.1%**\* |
| Resolve `agent_orchestrator` (first AI/chat use) | 5.503s | 5.425s | ~unchanged (expected) |
| RSS after resolving `agent_orchestrator` | 106.1MB | 106.1MB | unchanged (expected) |

\*Measured via a controlled, verbatim pre-fix copy of the container run
back-to-back with the fixed version, since this is a from-source
(non-git) checkout with no prior commit to diff against.

The "first AI request" cost did not disappear — it correctly moved from
"paid unconditionally at every process start" to "paid once, on first
actual use," which is the intended effect of lazy loading, not a
regression.

### Verified
- Full regression suite: 402 tests collected (unchanged), exit code 0 on
  two independent full runs — zero failures, zero errors.
- `ruff`: `container.py` clean (0 findings). Repo-wide PLC0415 findings
  (446, across test files with function-local imports) confirmed
  pre-existing and unrelated via a controlled before/after comparison —
  out of scope for this fix.
- `black`: `container.py` unchanged, already formatted.
- `mypy`: `container.py` errors reduced 21 → 17 (confirmed via a
  controlled before/after comparison) — converting 4 providers to typed
  callables incidentally fixed 4 pre-existing `var-annotated` gaps that
  mypy cannot infer through the string-path form. Zero new errors.
  Remaining 17 are pre-existing, on providers this fix intentionally did
  not touch.
- `pip check`: no broken requirements.

## [0.5.1] — Security: `cryptography` dependency upgrade

Dependency-only patch release — no application code, feature, or
roadmap change. Follows the repository stabilization pass's security
review, which flagged `cryptography` 43.0.3 as carrying 5 known
vulnerabilities and recommended a dedicated upgrade pass rather than a
same-PR bump.

### Changed
- `cryptography` upgraded `43.0.3` → `48.0.1` (`pyproject.toml`,
  `requirements.txt`, `requirements-lock.txt`). Resolves all 5 known
  advisories against the previous version: `PYSEC-2026-35`,
  `PYSEC-2026-1284`, `PYSEC-2026-2141`, `GHSA-537c-gmf6-5ccf`, and one
  additional CVE fixed in an intermediate release
  (`CVE-2026-39892`, non-contiguous-buffer overflow, fixed in
  `46.0.7`). Confirmed via `pip-audit`: `cryptography` no longer
  appears in the vulnerability report (24 → 19 total findings across
  the repo, all 5 removed entries were `cryptography`'s).
  - Target version chosen deliberately below the very latest release
    (`50.0.0`, published the day before this upgrade, effectively
    unfield-tested) — `48.0.1` is the minimum version resolving every
    known advisory and has ~7 weeks of real-world usage.
  - Reviewed the full upstream changelog from `43.0.3` through
    `48.0.1`: every breaking change in that range (Python 3.8 support
    removal, X.509 CRL/elliptic-curve/OpenSSL-version changes, stricter
    key-loading error types) is in code paths this app never
    exercises. `utils/crypto.py` uses only `Fernet`/`InvalidToken`,
    whose API and on-disk token format are unaffected.
  - Version bumped `0.5.0` → `0.5.1` (`pyproject.toml`,
    `__version__.py`, `Settings.app_version`) — a PATCH release per
    `docs/MASTER_ROADMAP.md` §6's policy ("reserved for out-of-band
    fixes shipped between milestones"), not a milestone-driven MINOR
    bump.

### Fixed
- Regenerated the editable-install package metadata
  (`jarvis_os.egg-info`), which had gone stale after the Milestone 6
  version bump and was still advertising the old
  `cryptography<44.0,>=43.0` constraint — `pip` flagged this as a
  self-referential dependency conflict the moment `cryptography` was
  upgraded. `pip check` now reports no broken requirements.

### Verified
- Full regression suite: 402/402 passing, zero failures, zero errors
  (identical to the pre-upgrade baseline).
- `ruff`/`black`/`mypy`: identical finding counts to the pre-upgrade
  baseline (438 / 0 / 264) — zero new findings anywhere in the repo.
- Fernet round-trip (`test_api_center_service.py::test_secrets_are_encrypted_at_rest`,
  which encrypts with one service instance and decrypts with a fresh
  one to simulate an app restart) passes.
- Manual verification: key generation, `encrypt()`/`decrypt()`
  round-trip, invalid-key error handling, and invalid-token error
  handling all behave identically to before the upgrade; the Fernet
  token format (`gAAA...` prefix) is unchanged.

## [0.5.0] — Milestone 6: Vision & Multimodal (Architecture Layer)

See `MILESTONE_6_VISION_DELIVERY.md` for full detail. This release
ships M6's **provider-abstraction layer only** — the Ports & Adapters
plumbing, not real vision/OCR capability. No vision/OCR dependency
was added; no capture, OCR, or image-processing code exists yet.

### Added
- `IVisionProvider` / `IOCRProvider` ports (`core/interfaces/`) —
  mirror `ILLMProvider`'s shape (`name: str`, `async health()`),
  deliberately minimal until a real backend exists to validate a
  fuller method surface against.
- `VisionSettings` / `OCRSettings` — `enabled: bool = False` by
  default; `JARVIS_VISION_ENABLED` / `JARVIS_OCR_ENABLED` added to
  the Settings-UI writable key whitelist.
- `MockVisionProvider` / `MockOCRProvider` — the only concretes wired
  in; both honestly report `enabled=False, healthy=False` rather than
  simulating capability. New `infrastructure/vision/` and
  `infrastructure/ocr/` packages, each with a provider factory
  (no backend-selection logic yet — nothing to select between).
- `VisionService.status()` — reports both providers' health as a
  plain dict; no other methods exposed.
- `VisionProviderStatusEvent` — defined on the `EventBus`, matching
  `AgentStepEvent`'s shape; not yet published anywhere.
- Agent tool `vision_status` (`agents/tools/vision_tools.py`) —
  reports provider availability only, registered in
  `agents/tools/registry.py` behind the existing optional-service
  pattern.
- Developer Mode **Vision Status** section (status-only, no
  image/screenshot/OCR-text/camera-feed/trace content) and a real
  **Vision** Settings page (two toggles, clearly labelled
  "unavailable / not yet implemented," replacing the pre-existing
  placeholder page).
- `vision_provider`, `ocr_provider`, `vision_service` registered as
  DI Singletons.
- 92 new tests across 7 phases (interfaces, settings, mock providers,
  service, agent tool/orchestrator wiring, Developer Mode view,
  Settings page), all passing.

### Changed
- `AgentOrchestrator` gained one additive, backward-compatible
  optional constructor kwarg, `vision: VisionService | None = None`
  (mirroring how `chat`/`voice`/`system` were added in M5A), threaded
  into its existing `build_tool_registry()` call — required because
  that call has exactly one call site, inside `AgentOrchestrator`
  itself. Defaults to `None`; an orchestrator built exactly as before
  this release behaves identically (regression-tested).
- `core/di/container.py`'s `agent_orchestrator` Singleton now also
  receives `vision=vision_service`.
- Version bumped `0.4.0` → `0.5.0` (`pyproject.toml`,
  `__version__.py`, `Settings.app_version`), per this milestone's
  entry in `docs/MASTER_ROADMAP.md` §6 Versioning policy.

### Known limitations (see `MILESTONE_6_VISION_DELIVERY.md` for the full list)
- No real vision or OCR provider exists — both mock providers always
  report unavailable.
- No screen capture, camera capture, clipboard image support, or
  drag-and-drop image input.
- No Image Question Answering; no multimodal chat.
- `ChatMessage.content` remains `str`-only — the message-model fork
  needed for multimodal chat was deliberately left as an open
  decision for whenever real vision input is built, not resolved now.
- No image preprocessing, compression, or bounded temp storage (the
  already-scaffolded `paths.cache_dir()` hook remains unclaimed).

## [0.4.0] — Milestone 5-Agents: Agent Runtime (LangGraph)

See `MILESTONE_5_AGENTS_DELIVERY.md` for full detail.

### Added
- `AgentOrchestrator` (`agents/orchestrator.py`) — a real, compiled
  LangGraph `StateGraph`: `planner → tool_selector → tool_executor →
  critic → responder`, with a loop-back edge from critic to
  tool-selector for multi-step tasks and a hard `max_steps` stop.
  Previously every method raised `NotImplementedError`.
- Tool registry (`agents/tools/`) — `MemoryService`, `AutomationService`,
  `BrowserService`, `SystemService`, `VoiceService` and `ChatService`
  auto-exposed as `langchain_core` structured tools; tool *selection*
  is driven by structured-JSON prompts over the existing `ILLMProvider`
  port, not a second langchain-native chat-model port.
- SQLite checkpointer (`agents/checkpointer.py`,
  `langgraph-checkpoint-sqlite`) — a thread's agent state survives an
  app restart when `AgentSettings.checkpoint_enabled` is true; falls
  back to an in-memory saver otherwise.
- `SystemService.status()` — real `psutil`-backed CPU/memory/disk/
  process/uptime snapshot (was a `NotImplementedError` stub since
  Milestone 1).
- `AgentStepEvent` (`core/events/events.py`) and a new Developer Mode
  **Agent Trace** section (`ui/views/developer/agent_trace_view.py`) —
  run an ad-hoc prompt through the orchestrator and watch each graph
  step arrive live.
- Prompt-injection mitigation: tool output is now fenced with an
  explicit `<<<TOOL_OUTPUT>>>...<<<END_TOOL_OUTPUT>>>` marker plus an
  instruction telling the model never to treat that text as
  instructions (`agents/prompting.py`'s `UNTRUSTED_TOOL_OUTPUT_NOTICE`)
  — closes the gap flagged during the Milestone 5.5 audit before this
  runtime existed.
- `JARVIS_AGENT_MAX_STEPS` / `JARVIS_AGENT_TIMEOUT_SECONDS` /
  `JARVIS_AGENT_CHECKPOINT_ENABLED` added to the Settings-UI writable
  key whitelist.
- ~40 new tests (`unit/test_system_service.py`,
  `unit/test_agent_prompting.py`, `unit/test_agent_nodes.py`,
  `unit/test_agent_tools_registry.py`, `unit/test_agent_checkpointer.py`,
  `integration/test_agent_orchestrator.py`) and a new `ScriptedFakeLLM`
  test double.

### Fixed (found during pre-merge validation — see `AUDIT_REPORT_M5-AGENTS.md`)
- **Reliability**: the default agent configuration
  (`checkpoint_enabled=True`) crashed on the *first real graph
  invocation* with `AttributeError: 'Connection' object has no
  attribute 'is_alive'` — a real incompatibility between
  `langgraph-checkpoint-sqlite==2.0.11` and `aiosqlite>=0.21` (which
  dropped the `Thread`-based `Connection` class that method depended
  on). `open()`/`close()` alone never triggered it, which is why the
  original unit tests missed it; only found via a live end-to-end
  smoke run through the real DI container. Fixed by pinning
  `aiosqlite>=0.20,<0.21`; covered going forward by a new regression
  test, `test_invoke_with_real_sqlite_checkpointer`.
- Two pre-existing tests
  (`test_main_window_registers_shutdown_hooks_in_correct_order`,
  `test_developer_dashboard_builds_all_thirteen_sections` → renamed
  `..._fourteen_sections`) updated for this milestone's own intentional
  changes (a new shutdown hook, a 14th Developer Mode section) — not
  regressions, just stale hardcoded expectations.

### Changed
- Version bumped `0.3.0` → `0.4.0` (`pyproject.toml`, `__version__.py`,
  `Settings.app_version`) — closes the version-drift note tracked in
  `docs/MASTER_ROADMAP.md` §10 since Milestone 3.1.
- `Container.agent_orchestrator` now also receives `chat`, `voice`,
  `system` and `event_bus` (previously only `settings`, `llm`,
  `memory`, `automation`, `browser`).
- `AgentOrchestrator.stop()` registered with `ShutdownManager` at
  `PRIORITY_EARLY` (`ui/main_window.py`), alongside `voice_service`.

### Known limitations (see `MILESTONE_5_AGENTS_DELIVERY.md` for the full list)
- Vision tool deliberately deferred to Milestone 6.
- The existing Chat view still talks to `ChatService` directly; the
  agent is not yet wired into the primary chat UI.
- `stream()` re-chunks the fully-composed final answer rather than
  streaming real LLM tokens from inside the responder node.
- No per-step timings in the Agent Trace panel.
- `run_automation` never passes a confirmation callback — any action
  needing interactive confirmation is auto-denied rather than asked.

## [0.3.0] — Milestone 5.5 Production Stabilization Pass (unreleased)

Not a feature milestone -- a stabilization pass over Milestones 0-5,
following an evidence-based audit (see `AUDIT_REPORT_M0-M5.md`).

### Fixed
- **Reliability**: 55 sites across 22 files where a fire-and-forget
  async task had no stored reference and could be garbage-collected
  mid-execution -- root cause of "Task was destroyed but it is pending!"
  warnings seen throughout the test suite. Fixed via a shared
  `fire_and_forget()` helper (`jarvis.utils.async_utils`).
- **Reliability**: app shutdown (both the tray/menu Quit action and the
  OS window-close button) now releases every real resource
  (voice/browser/hotkeys/database) via a new `ShutdownManager`
  (`core.lifecycle.shutdown_manager`) instead of a hand-sequenced,
  partially-incomplete inline sequence. The window-close path previously
  bypassed resource cleanup entirely.
- **Reliability**: a corrupted/binary-garbage `.env` config file (e.g.
  from a power loss mid-write) previously crashed startup with an
  uncaught `UnicodeDecodeError`. Now falls back to defaults with a clear
  warning instead of refusing to start.
- **Security**: `DeveloperModeService` password verification used a
  non-constant-time string comparison (`==`); switched to
  `hmac.compare_digest`.
- **Security**: browser automation's `LAUNCH_URL` action had no URL
  scheme validation -- `file://`/`javascript:`/`data:` URIs would have
  been auto-allowed with no confirmation. Added scheme validation to
  `SafetyValidator` (denylist-based, specifically to avoid a false
  positive on ordinary `localhost:8080`-style local-dev URLs that a
  naive allowlist approach would have wrongly flagged).
- **Architecture**: `ThemeService` had a hardcoded accent-color dict
  that duplicated values already defined in `ui/themes/palette.py`,
  which existed but was never wired in. Now derives from `palette.py`
  directly.
- **Accessibility**: buttons (sidebar nav, quick actions, dialogs) had
  no visible keyboard-focus indicator -- only text inputs did. Added a
  `QPushButton:focus` rule to all three themes.
- **Performance**: all 9 workspace modules were imported eagerly at
  `main_window` import time regardless of whether a user ever visited
  them (measured: ~358ms, ~20% of that module's import chain). Fixed at
  both the `main_window.py` call site and the root cause (a
  `ui/views/workspaces/__init__.py` package `__init__.py` that itself
  eagerly re-exported all 9, silently defeating the first fix). Measured
  result: `MainWindow` construction time dropped from ~256ms to ~109ms.
- Removed 4 files of dead, milestone-superseded scaffolding
  (`agents/base_agent.py`, `agents/state.py`,
  `infrastructure/database/base_repository.py`,
  `infrastructure/stt/whisper_provider.py`) -- each explicitly labeled
  "Implementation deferred to Milestone N" for milestones later
  completed via different, real implementations. Verified zero
  references before removal.

### Added
- Packaging foundation: `packaging/jarvis.spec` (PyInstaller),
  `packaging/build_windows.ps1` (build + optional code signing),
  `packaging/jarvis_installer.iss` (Inno Setup). None yet
  build-verified on real Windows hardware -- see `docs/PACKAGING.md`.
- `docs/PACKAGING.md`, this changelog.
- ~65 new regression/reliability/security tests across the areas above.

### Known gaps (see `docs/PACKAGING.md` and the RC1 audit report for full detail)
- No real Windows build has been produced or tested.
- No application icon exists yet.
- No first-run/onboarding wizard.
- Coverage gaps remain concentrated in Settings-page UI wiring code.

## [Earlier history]

Milestones 0 through 5 (architecture scaffolding through the official
PySide6 UI, Developer Mode, Update Center, and the 9 feature
workspaces) predate this changelog's introduction and are documented in
`MILESTONE_5_DELIVERY.md` and `AUDIT_REPORT_M0-M5.md` rather than
retroactively reconstructed here.
