# Connectivity Layer — Module Logic Contract

**Milestone:** M12 — Smart Home & IoT Platform, Task Group B
**Status:** Phase 1 (foundation) — written before Phase 1 implementation, per
`MASTER_ROADMAP.md` §4's binding rule: *"No implementation may begin
until its module's Logic Contract is complete."*
**Scope of this document:** the Connectivity Layer module as a whole
(all three approved phases). Per-phase delivery status is called out
inline where it matters, since the module is built incrementally, not
in one pass.

This follows the field list `MASTER_ROADMAP.md` §4 defines for every
Logic Contract, and lives here — a standalone module design doc — per
that same section's own "or the module's own design doc" allowance,
alongside `ARCHITECTURE.md` §10's Module Manifest specification (which
this module also satisfies at the DI/plugin-manifest level, not
duplicated here).

---

## Purpose

Give Task Group A's `SmartHomeService` a real way to discover, pair,
read the state of, and command actual devices — closing the gap Task
Group A's own report named explicitly: Device Discovery and Pairing
were built as domain-level status transitions with "no real hardware
behind them," deferred to "M12's own Connectivity Layer module."

## Responsibilities

- Own the lifecycle of one connection per configured connector
  (connect, disconnect, reconnect).
- Translate a connector's protocol-specific view of a device into
  Task Group A's own domain calls (`SmartHomeService.
  register_discovered_device`, a new `report_device_state`).
- Own credential storage for connectors that need one (a Home
  Assistant long-lived token; future vendor OAuth tokens).
- Provide the one extensibility seam (`ConnectorFactoryRegistry`) a
  future connector plugs into without this module or `SmartHomeService`
  changing — mirroring `TransportFactoryRegistry`'s own precedent
  exactly.

**Explicitly not this module's responsibility:** interpreting *what a
command means* (a scene, an automation trigger) — that is Home
Automation/AI Home Assistant, later M12 modules. Enforcing
`safety_critical` confirmation (M12 AC3) — that is M4's existing
`SafetyValidator`/`UndoManager` infrastructure, wired in by whichever
later module first exposes device commands to chat/automation; this
module's `send_command` is the single chokepoint that infrastructure
will gate, not something it bypasses, but wiring the gate itself is
out of scope here.

## Business logic

- A connector reports devices and state in its own vocabulary; this
  module is the only thing that translates that into `Device`/`Home`
  domain calls. No connector talks to the database directly.
- A device is owned by exactly one connector at a time, recorded as
  `connector_type` inside `Device.metadata_json` (the column Task
  Group A built specifically "so a later task group has somewhere to
  write") — not a new schema column, per this task group's own
  "do not modify unrelated modules" constraint balanced against
  Task Group A's own documented forward-reference.
- Connecting, discovering, and sending a command are each independent,
  idempotent operations — a discovery run against an already-known
  device updates it, never duplicates it (enforced by `external_id`
  lookup before create, added as part of this module's own service
  logic).

## Inputs

- Connector configuration (base URL, broker address, credentials) —
  operator-supplied, via settings.
- Protocol traffic from the connector's own transport (HA's REST/WS
  responses, MQTT messages) — untrusted, validated before it reaches
  `SmartHomeService`.

## Outputs

- Real `Device`/`Home` rows via `SmartHomeService`.
- `HomeUpdatedEvent`/`DeviceUpdatedEvent` (existing, Task Group A) for
  domain changes; a new `ConnectivityStatusChangedEvent` for
  connector-level connect/disconnect, relayed the same way.
- `CommandResult` values back to whichever caller invoked
  `send_command` (a REST route in a later phase; a fake in Phase 1's
  own tests today).

## Dependencies

Per M12's own Dependencies note (`MASTER_ROADMAP.md`): M11
(cloud-vendor OAuth/API access, not yet needed by the HA/MQTT connectors
this task group builds), M14 (Security Platform, for credential
storage) — **not blocking**, because this module reuses the existing
encrypted-at-rest pattern `core/mcp/auth/store.py` established, the
same way M11 Task Group E built real OAuth2 ahead of full M14. Within
this task group: `SmartHomeService` (Task Group A, existing),
`jarvis.utils.crypto` (existing Fernet helpers), `EventBus` (existing).

## Permission model

Reuses the **existing** fixed vocabulary (`core/plugins/sdk.py`'s
`PERMISSION_SCOPES`) — `smart_home` (the capability), `network` (any
connector's outbound calls) — through the existing `PermissionModel`.
No new permission scope is introduced; a second permission vocabulary
alongside the real one is exactly the kind of duplication this
project's engineering standards forbid.

## State machine

Per connector connection: `disconnected → connecting → connected →
disconnecting → disconnected`, plus `connected → reconnecting →
connected` on a dropped link (a later phase's concern once a real
connector exists to actually drop). Per device, unchanged from Task
Group A's own `DEVICE_STATUSES`: `discovered → paired`, and now, for
real, `paired ↔ offline`/`unreachable` — driven by this module instead
of never firing.

## Validation rules

- `ConnectorFactoryRegistry.register` rejects any type outside
  `CONNECTOR_TYPES`, mirroring `TransportFactoryRegistry`'s own
  enforcement — a typo'd connector type fails at registration, not at
  first use.
- A discovered device's reported `device_type` is checked against Task
  Group A's own `DEVICE_TYPES` closed vocabulary before
  `register_discovered_device` is called — an unrecognized value maps
  to `"other"` rather than being rejected outright, since refusing to
  register a real device over a vocabulary gap is worse than an
  imprecise category (the same reasoning `domain/smart_home/models.py`
  already states for `DEVICE_TYPES` itself).

## Failure behaviour

- A connector that fails to connect raises a typed `ConnectivityError`
  subclass; `ConnectivityService` does not retry silently — the caller
  (eventually a REST route, a fake in Phase 1's tests) decides whether
  to retry, matching this project's "no silent recovery that hides a
  real failure" posture used throughout the installer engine.
- A single bad record from a discovery batch does not abort the whole
  batch — mirrors `CredentialStore._ensure_loaded`'s own "one
  unreadable record must not make every other credential unavailable"
  fault-isolation rule, applied to discovery results instead of stored
  credentials.

## Recovery behaviour

- Reconnection policy is a later-phase concern (needs a real connector
  to observe real disconnect behaviour against, the same "don't design
  against a hypothetical" discipline this project applies elsewhere).
  Phase 1 ships `disconnect()`/`connect()` as explicit, caller-driven
  operations only.

## Logging

- Connector id and outcome only, never a credential value or raw
  protocol payload that might carry one — mirrors
  `core/mcp/auth/credentials.py`'s own redacting-`__repr__` discipline,
  applied to `ConnectorCredential` in this module too.

## Telemetry / Events

- `ConnectivityStatusChangedEvent` (new) — connector connect/disconnect,
  relayed over the existing WebSocket hub (`connectivity.status_changed`),
  wired in this same phase per Task Group A's own precedent of wiring
  new events into the relay immediately rather than leaving a pinned-test
  gap for a later phase to trip over.
- `HomeUpdatedEvent`/`DeviceUpdatedEvent` (existing, Task Group A) —
  reused as-is for domain-level changes this module produces.

## Tests

- Fakes-first, per `MASTER_ROADMAP.md` §4's own stated convention
  (`tests/fakes/`): a `FakeDeviceConnector` implementing
  `IDeviceConnector` in-memory, no network.
- Real (temp-file) persistence tests for `ConnectorCredentialStore`,
  matching every other store in this codebase — no mocked filesystem.
- `ConnectivityService` orchestration tests against the fake connector
  and a real `SmartHomeService` (real temp-file SQLite), matching Task
  Group A's own "no mocked repository" discipline.

## Acceptance criteria (this task group's own, distinct from M12's milestone-level AC)

1. `IDeviceConnector`, `DiscoveredDevice`, `DeviceState`, `CommandResult`
   exist and are the named Protocol/value objects M12 AC5 requires
   before any adapter is built.
2. `ConnectorFactoryRegistry` rejects an unknown connector type and
   accepts a registered one, mirroring `TransportFactoryRegistry`'s
   own tested behaviour.
3. `ConnectorCredentialStore` round-trips a credential through
   encrypted persistence and refuses to persist without a configured
   key, mirroring `CredentialStore`'s own tested behaviour.
4. `ConnectivityService` correctly discovers, registers, and updates
   device state through a fake connector, with zero direct database
   access from the fake itself.
5. Every new event is wired into the WebSocket relay in the same
   change that introduces it — no repeat of the pinned-test gap Task
   Group A found and fixed.
