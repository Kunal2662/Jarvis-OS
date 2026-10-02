# M12 Sensor Service — Domain/Component Fallback Logic Contract

**Status: Phase 1 planning document only. Contains zero source-code
changes.** Written per the M0–M12 Structured Rework Audit's P1-2
finding, following the identical evidence-gathering discipline used
for the already-shipped `ApplianceService` fix (commit `d585264`,
"P1-1"). No implementation accompanies this document, and none is
authorized by it.

## 1. Current behavior

`SensorService._kind_for` (`src/jarvis/services/sensor_service.py:103-107`):

```python
def _kind_for(device: Device) -> str:
    return "binary" if _metadata(device).get("domain") == "binary_sensor" else "numeric"
```

Reads exactly one metadata key, `domain`, and nothing else. Any device
whose `metadata_json` does not contain `"domain": "binary_sensor"` —
including one that legitimately *is* a binary sensor but was
discovered by a path that never wrote `domain` — is classified
`"numeric"`.

`_kind_for` is called from two places, both payload builders:
`_sensor_list_payload` (line 152) and `_sensor_full_payload` (line
157) — the `kind` field drives which normalization branch
`_sensor_full_payload` takes (`_parse_binary`/`_binary_state_label` vs.
`_parse_numeric`/`_numeric_state_label`, lines 178-188). A
misclassified binary sensor therefore doesn't just report the wrong
`"kind"` string — it gets numerically parsed (`_parse_numeric("on")`
→ `None`, since `"on"` isn't a float), so `value`/`state` both come
back `null` for a device that is actually reporting a real boolean
signal.

## 2. Verified defect

Confirmed by direct read of both connectors:

- `HomeAssistantConnector._entity_to_discovered_device`
  (`src/jarvis/core/connectivity/connectors/home_assistant.py:263-295`)
  writes `metadata = {"domain": domain}` (line 280) — HA-REST-sourced
  sensors are unaffected by this defect.
- `MqttConnector._handle_ha_discovery`
  (`src/jarvis/core/connectivity/connectors/mqtt.py:507-561`) writes
  `metadata = {"component": component, "discovery_topic": topic}`
  (line 538) — **never `"domain"`**. In Home Assistant's own MQTT
  Discovery topic scheme (`<prefix>/<component>/<node_id>/<object_id>/
  config`), `component` is drawn from literally the same vocabulary as
  HA's REST `domain` field — for a binary sensor, `component ==
  "binary_sensor"`, the exact string `_kind_for` already compares
  against.

So: an MQTT-HA-Discovery-sourced binary sensor (e.g. a Zigbee2MQTT or
Tasmota door/motion/smoke sensor bridged through HA's MQTT Discovery
convention) is real, connected, and reporting valid `"on"`/`"off"`
status — but `_kind_for` reports it as `"numeric"`, and the resulting
payload silently shows `value: null, state: null` instead of the
correct `open`/`closed`, `detected`/`clear`, etc. label. The device is
never rejected or flagged as an error — it is silently misclassified
and silently unreadable.

## 3. Root cause

`docs/M12_SENSORS_LOGIC_CONTRACT.md` §16 ("MQTT mapping") confirms
`SensorService` was designed and built against `domain` only —
the document describes capturing `device_class` from MQTT Discovery
config but at no point proposes reading `component` as a `kind`
signal, because **the domain→component fallback convention did not
exist yet when Sensors shipped**. That convention was established
later, first by `SirenService` (its own `_domain_for` docstring:
"applied here to `device_type=\"other\"` for the first time"), and
has since been adopted by `VacuumHumidifierService`,
`MediaPlayerService`, the Water Heater service,
`AlarmControlPanelService`, and — as of the P1-1 fix — `Appliance
Service`. `SensorService` is the one remaining `device_type` category
never backported to the convention. This is the identical root cause
and identical defect shape as P1-1, in a different service.

## 4. Required behavior

1. `metadata["domain"]` present and non-empty → use it (unchanged
   from today).
2. `metadata["domain"]` absent or empty → fall back to
   `metadata["component"]`.
3. Both absent → preserve current behavior exactly: `_kind_for`
   returns `"numeric"` (the existing, tested "detect at use, not
   fabricate" default — `test_device_with_no_recorded_domain_defaults_
   to_numeric`, `test_m12_sensor_service.py:456-470` — asserts this
   today and must keep passing unchanged).
4. `domain` always takes precedence over `component` when both are
   present — matching every sibling implementation's fallback order
   exactly (`appliance_service.py:162-178`,
   `siren_service.py:252-266`, `vacuum_humidifier_service.py:174-183`,
   et al.).

## 5. Exact fallback semantics

Mirrors the established `_domain_for`-style helper's exact shape,
adapted to `_kind_for`'s boolean-classification return type rather
than a `str | None` return type (the sibling services return the
resolved domain string itself; `_kind_for` only ever needs to *compare*
the resolved value against the literal `"binary_sensor"`, so no new
public helper needs to expose the resolved string — an internal
`domain or component` resolution inside `_kind_for` is sufficient and
matches `vacuum_humidifier_service.py`'s single-expression `value =
metadata.get("domain") or metadata.get("component")` variant of the
same pattern, since `_kind_for` has no separate need to distinguish
"empty string" from "absent" the way a `str | None`-returning helper
does):

```
resolved = metadata.get("domain") or metadata.get("component")
kind = "binary" if resolved == "binary_sensor" else "numeric"
```

This is semantically identical to the `if domain: return ...;
component = ...; return ...` long form used in `appliance_service.py`/
`siren_service.py` — both forms give an empty-string `domain` the same
treatment (falsy, falls through to `component`), and both give "both
absent" the same treatment (`None or None` → `None` → not equal to
`"binary_sensor"` → `"numeric"`, matching requirement 3 above exactly).
The exact implementation form (long if/return vs. single `or`
expression) is an implementation-time choice with no behavioral
difference; Phase 2 will pick one and note which sibling it mirrors.

## 6. Affected device categories

Only `device_type="sensor"`, and within that, only the
`kind`-classification computed by `_kind_for` (binary vs. numeric).
No other `SensorService` method reads `domain`/`component` —
`_device_class_for` (line 110-112) reads the separate `device_class`
metadata key, untouched by this fix. `list_sensors`, `get_sensor_state`,
permission enforcement, and the offline/availability logic are all
unaffected; none of them branch on `domain`/`component`.

## 7. HA behavior (must remain unchanged)

`HomeAssistantConnector` always writes `metadata["domain"]` for every
discovered entity, sensors included — never `component`. Every
existing HA-sourced test (`_home_and_sensor`'s default
`connector_type="home_assistant"`, all 13
`test_binary_sensor_friendly_labels` parametrizations,
`test_numeric_sensor_*`, `test_list_sensors_reports_domain_derived_
kind_and_device_class`) passes `domain=` directly and must keep
passing byte-for-byte unchanged, since `domain` still wins when
present — requirement 4 above.

## 8. MQTT behavior (the actual fix target)

An MQTT-HA-Discovery-sourced sensor device registered with
`metadata={"component": "binary_sensor", ...}` and no `domain` key
must, after the fix, classify as `kind="binary"` — today it
classifies as `kind="numeric"`, which is the verified defect (§2).

## 9. Permission impact

None. `_require_permission`/`SENSOR_PRINCIPAL`/`SMART_HOME_SCOPE` are
untouched — this fix is entirely inside the private `_kind_for`
classification helper, called only after permission checks already
passed.

## 10. REST impact

None. `src/jarvis/infrastructure/api/routes/sensors.py` contains zero
references to `domain`, `component`, or `_kind_for` (verified by
direct grep) — it only forwards `SensorService`'s already-built payload
dicts. The `kind`/`value`/`state` fields in the JSON response will
simply become *correct* for the affected MQTT-native devices; the
response shape itself does not change.

## 11. Tool impact

None. `src/jarvis/agents/tools/sensor_tools.py` contains zero
references to `domain`, `component`, or `_kind_for` (verified by
direct grep) — same reasoning as §10.

## 12. Connector impact

**None.** No connector file is touched. `HomeAssistantConnector`
already writes `domain`; `MqttConnector._handle_ha_discovery` already
writes `component`. Both are correct and unchanged — this fix only
changes which of the two keys `SensorService` itself reads, exactly
matching the P1-1 precedent (`ApplianceService`'s fix also required
zero connector changes).

## 13. Test strategy

New regression tests in `tests/unit/test_m12_sensor_service.py`,
following `_home_and_sensor`'s existing fixture shape extended with an
optional `domain_key`/component-only variant (mirroring
`test_m12_appliance_service.py`'s own `domain_key` parameter added for
P1-1):

1. `component`-only metadata (`domain` absent) with `component=
   "binary_sensor"` → `kind == "binary"`, and a full
   `get_sensor_state` read correctly parses/labels a binary status.
2. `component`-only metadata with `component="sensor"` (or any
   non-`"binary_sensor"` value) → `kind == "numeric"`.
3. Both `domain="binary_sensor"` and `component="sensor"` present →
   `domain` wins → `kind == "binary"` (precedence test, requirement 4).
4. Empty-string `domain` (`domain=""`) with `component="binary_sensor"`
   present → falls back to `component` → `kind == "binary"`.
5. Neither `domain` nor `component` present → `kind == "numeric"`
   (re-asserts the existing `test_device_with_no_recorded_domain_
   defaults_to_numeric` behavior is preserved, not just re-tested by
   coincidence).
6. An end-to-end MQTT-discovered binary sensor test using a real
   `mqtt_connector`/`mqtt_service` instance (mirroring
   `test_mqtt_discovered_fan_can_be_commanded`'s shape from the P1-1
   test suite), confirming a genuinely MQTT-HA-Discovery-registered
   device resolves to the correct `kind` end-to-end, not just through
   a hand-constructed `metadata` dict.
7. A "wrong component" guard: `component="switch"` (a real, valid
   component value for a *different* domain) does not cause
   `SensorService` to misidentify anything, since `_require_sensor`
   still gates on `device.device_type`, independent of `_kind_for` —
   confirms this fix does not weaken the existing device-type
   rejection path.

No existing test is expected to change behavior; every currently
passing test in `test_m12_sensor_service.py` uses `domain=` directly
(via `_home_and_sensor`'s default) and must continue to pass
unmodified.

## 14. Regression strategy

Identical discipline to P1-1: focused `SensorService` tests, sibling
regression (`test_m12_sensors_route.py`, `test_m12_sensor_tools.py`,
any test importing `SensorService` — `test_m12_smart_home_memory_
service.py` does not, since sensors are permanently excluded from
Smart Home Memory snapshots), full M12 regression, M11+M12 regression,
full backend regression, Black/Ruff/Mypy with baseline comparison
against the current `d585264` checkpoint (not the pre-P1-1 baseline).

## 15. Acceptance criteria

- `metadata["domain"]` present and non-empty → used, unchanged from
  today (§7 unaffected).
- `metadata["domain"]` absent/empty, `metadata["component"]` present →
  used as fallback (§8, the fix).
- Both absent → `kind == "numeric"`, unchanged (§4 requirement 3).
- `domain` takes precedence when both present (§4 requirement 4).
- Zero REST/tool/connector/permission/EventBus/Scheduler/database
  changes (§9-§12).
- All new tests in §13 pass; zero existing test behavior changes.
- Full backend regression green; Black/Ruff/Mypy show zero new
  findings versus the `d585264` baseline.

## 16. Explicit forbidden scope

Per the Structured Rework Closure's own global rules, this fix does
**not**:
- touch `HomeAssistantConnector` or `MqttConnector` (§12);
- add a `device_class`-equivalent capture for any new field;
- change `_DEVICE_TYPES`/device-type vocabulary in any way;
- add an EventBus publish for sensor reads (sensors are read-only;
  no such capability was ever proposed and none is proposed here);
- touch the Scheduler (none exists; irrelevant to this fix);
- change the database schema;
- extract a shared `_domain_for`-style helper into a common module —
  each sibling service's own private helper stays private, per the
  Final Exit Assessment's own "no extraction without a concrete
  architectural benefit" finding, reaffirmed by the Structured Rework
  Audit's cross-cutting "Services" section;
- rename, restructure, or otherwise touch anything in
  `SensorService` outside `_kind_for` itself;
- perform any frontend, roadmap, or CHANGELOG change (this document
  is the entire Phase 1 deliverable).
