import { describe, expect, it } from "vitest";
import contract from "@/services/websocket/event-contract.generated.json";
import {
  isRelayedEvent,
  RELAYED_EVENTS,
  TRANSPORT_FRAMES,
  type AgentStepPayload,
  type AutomationStepPayload,
  type HealthUpdatedPayload,
  type PluginNotificationPayload,
  type UpdatePhasePayload,
  type VoiceStateChangedPayload,
} from "@/services/websocket";

/**
 * The frontend half of the WebSocket contract gate.
 *
 * `event-contract.generated.json` is written by
 * `scripts/export_ws_contract.py` from the backend's `EVENT_TYPE_NAMES`,
 * and `tests/unit/test_ws_contract_export.py` fails if that file is stale.
 * This file fails if the TypeScript disagrees with it. Together the two
 * mean an event cannot be added, renamed, or reshaped on one side without
 * turning something red -- which is the failure mode Phase 1 shipped
 * (eleven invented event names, three wrong payload shapes) and this
 * phase is fixing.
 */

const contractEvents = Object.keys(contract.events).sort();

describe("relayed event vocabulary", () => {
  it("matches the backend's EVENT_TYPE_NAMES exactly", () => {
    expect([...RELAYED_EVENTS].sort()).toEqual(contractEvents);
  });

  it("has no duplicates", () => {
    expect(new Set(RELAYED_EVENTS).size).toBe(RELAYED_EVENTS.length);
  });

  it("names every event <category>.<event>", () => {
    for (const name of RELAYED_EVENTS) {
      expect(name).toMatch(/^[a-z][a-z_]*\.[a-z][a-z_]*$/);
    }
  });

  it("keeps transport frames out of the relayed set", () => {
    for (const frame of TRANSPORT_FRAMES) {
      expect(contractEvents).not.toContain(frame);
      expect(isRelayedEvent(frame)).toBe(false);
    }
    expect([...TRANSPORT_FRAMES].sort()).toEqual([...contract.transport_frames].sort());
  });

  it("isRelayedEvent() accepts real names and rejects invented ones", () => {
    expect(isRelayedEvent("voice.state_changed")).toBe(true);
    expect(isRelayedEvent("agent.step")).toBe(true);
    // Every one of these was in Phase 1's hand-written list and none has
    // ever existed. Named explicitly so a future edit that "restores"
    // them fails rather than quietly reintroducing dead handlers.
    for (const invented of [
      "ai.token",
      "ai.step",
      "ai.complete",
      "voice.transcript_partial",
      "voice.transcript_final",
      "automation.step_started",
      "automation.step_completed",
      "automation.workflow_finished",
      "progress.update",
      "notification.created",
      "runtime.module_state_changed",
    ]) {
      expect(isRelayedEvent(invented)).toBe(false);
    }
  });
});

/**
 * Each payload interface is checked by constructing a value with exactly
 * the contract's field names. TypeScript rejects a missing or misspelled
 * key at compile time (`npm run typecheck`), and the runtime assertion
 * catches the reverse -- a field the backend has that the interface has
 * forgotten.
 */
describe("payload shapes", () => {
  function expectFields(eventName: keyof typeof contract.events, value: object): void {
    expect(Object.keys(value).sort()).toEqual([...contract.events[eventName]].sort());
  }

  it("voice.state_changed", () => {
    const payload: VoiceStateChangedPayload = { state: "listening", detail: "" };
    expectFields("voice.state_changed", payload);
  });

  it("agent.step", () => {
    const payload: AgentStepPayload = {
      thread_id: "t1",
      step: 1,
      node: "plan",
      status: "ok",
      detail: "",
    };
    expectFields("agent.step", payload);
  });

  it("automation.step", () => {
    const payload: AutomationStepPayload = { step_id: "s1", action: "click", status: "ok" };
    expectFields("automation.step", payload);
  });

  it("notification.plugin", () => {
    const payload: PluginNotificationPayload = { plugin_id: "p", title: "t", message: "m" };
    expectFields("notification.plugin", payload);
  });

  it("progress.update_phase", () => {
    const payload: UpdatePhasePayload = {
      session_id: "s",
      phase: "download",
      progress_percent: 10,
      message: "",
    };
    expectFields("progress.update_phase", payload);
  });

  it("health.updated", () => {
    const payload: HealthUpdatedPayload = { snapshot: {} };
    expectFields("health.updated", payload);
  });
});
