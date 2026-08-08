import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  ensureRealtimeBridge,
  installRealtimeBridge,
  resetRealtimeBridgeForTesting,
} from "@/services/realtime-bridge";
import { websocketManager } from "@/services/websocket";
import type { WebSocketEventType, WebSocketMessage } from "@/services/websocket";
import { useAgentActivityStore } from "@/stores/agent-activity.store";
import { useNotificationsStore } from "@/stores/notifications.store";
import { useVoiceStateStore } from "@/stores/voice-state.store";

/**
 * The bridge is where a wrong event name stops being a compile concern
 * and becomes a silent runtime one, so these tests drive it the way the
 * real socket does: by dispatching a message through the manager's own
 * handler registry rather than calling store actions directly.
 */

type Handler = (message: WebSocketMessage<never>) => void;

const handlers = new Map<string, Set<Handler>>();

function dispatch(type: WebSocketEventType, payload: unknown, at = "2026-08-05T12:00:00Z"): void {
  const message = { type, id: `evt-${type}`, occurred_at: at, payload } as WebSocketMessage<never>;
  for (const handler of handlers.get(type) ?? []) handler(message);
}

let teardown: (() => void) | null = null;

beforeEach(() => {
  handlers.clear();
  vi.spyOn(websocketManager, "on").mockImplementation((type, handler) => {
    const set = handlers.get(type) ?? new Set<Handler>();
    set.add(handler as Handler);
    handlers.set(type, set);
    return () => set.delete(handler as Handler);
  });

  useVoiceStateStore.setState({ voiceState: "idle", history: [] });
  useAgentActivityStore.setState({ agentSteps: [], automationSteps: [] });
  useNotificationsStore.setState({ items: [] });
  teardown = installRealtimeBridge();
});

afterEach(() => {
  teardown?.();
  teardown = null;
  resetRealtimeBridgeForTesting();
  vi.restoreAllMocks();
});

describe("voice integration", () => {
  it("moves the voice state machine on voice.state_changed", () => {
    dispatch("voice.state_changed", { state: "wake", detail: "" });
    expect(useVoiceStateStore.getState().voiceState).toBe("wake");

    dispatch("voice.state_changed", { state: "listening", detail: "" });
    expect(useVoiceStateStore.getState().voiceState).toBe("listening");
  });

  it("ignores a state this client does not know", () => {
    dispatch("voice.state_changed", { state: "transcribing", detail: "" });
    expect(useVoiceStateStore.getState().voiceState).toBe("idle");
  });

  it("ignores a repeat of the current state", () => {
    dispatch("voice.state_changed", { state: "idle", detail: "" });
    expect(useVoiceStateStore.getState().voiceState).toBe("idle");
  });

  it("follows the backend even across a transition the local graph rejects", () => {
    // `idle -> speaking` is not a legal edge here, but the backend's
    // pipeline is the authority on what state it is actually in; showing
    // a stale state would be the worse outcome.
    dispatch("voice.state_changed", { state: "speaking", detail: "" });
    expect(useVoiceStateStore.getState().voiceState).toBe("speaking");
  });
});

describe("AI integration", () => {
  it("records agent.step with the event's own timestamp", () => {
    dispatch("agent.step", {
      thread_id: "t1",
      step: 1,
      node: "plan",
      status: "running",
      detail: "thinking",
    });

    const [step] = useAgentActivityStore.getState().agentSteps;
    expect(step.thread_id).toBe("t1");
    expect(step.node).toBe("plan");
    expect(step.receivedAt).toBe("2026-08-05T12:00:00Z");
  });

  it("keeps steps in arrival order", () => {
    dispatch("agent.step", { thread_id: "t1", step: 1, node: "a", status: "ok", detail: "" });
    dispatch("agent.step", { thread_id: "t1", step: 2, node: "b", status: "ok", detail: "" });
    expect(useAgentActivityStore.getState().agentSteps.map((s) => s.node)).toEqual(["a", "b"]);
  });
});

describe("automation integration", () => {
  it("records automation.step", () => {
    dispatch("automation.step", { step_id: "s1", action: "open_browser", status: "ok" });

    const [step] = useAgentActivityStore.getState().automationSteps;
    expect(step).toMatchObject({ step_id: "s1", action: "open_browser", status: "ok" });
  });

  it("keeps agent and automation steps separate", () => {
    dispatch("agent.step", { thread_id: "t1", step: 1, node: "a", status: "ok", detail: "" });
    dispatch("automation.step", { step_id: "s1", action: "x", status: "ok" });

    expect(useAgentActivityStore.getState().agentSteps).toHaveLength(1);
    expect(useAgentActivityStore.getState().automationSteps).toHaveLength(1);
  });
});

describe("notifications", () => {
  it("adds a notification.plugin event to the centre", () => {
    dispatch("notification.plugin", {
      plugin_id: "weather",
      title: "Rain expected",
      message: "Bring an umbrella.",
    });

    const [item] = useNotificationsStore.getState().items;
    expect(item).toMatchObject({
      title: "Rain expected",
      message: "Bring an umbrella.",
      read: false,
    });
    expect(item.createdAt).toBe("2026-08-05T12:00:00Z");
  });
});

describe("lifecycle", () => {
  it("teardown stops every subscription", () => {
    teardown?.();
    teardown = null;

    dispatch("agent.step", { thread_id: "t1", step: 1, node: "a", status: "ok", detail: "" });
    dispatch("voice.state_changed", { state: "wake", detail: "" });

    expect(useAgentActivityStore.getState().agentSteps).toEqual([]);
    expect(useVoiceStateStore.getState().voiceState).toBe("idle");
  });

  it("ensureRealtimeBridge() does not double-register under a repeat call", () => {
    // React StrictMode invokes effects twice in development; a second
    // registration would record every step twice.
    ensureRealtimeBridge();
    ensureRealtimeBridge();

    dispatch("agent.step", { thread_id: "t1", step: 1, node: "a", status: "ok", detail: "" });

    // One from the `beforeEach` install, one from `ensureRealtimeBridge`
    // -- and crucially not three, which is what a non-idempotent
    // `ensure` would produce.
    expect(useAgentActivityStore.getState().agentSteps).toHaveLength(2);
  });
});
