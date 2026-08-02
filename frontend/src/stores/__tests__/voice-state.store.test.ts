import { beforeEach, describe, expect, it } from "vitest";
import { InvalidVoiceStateTransitionError } from "@/core/voice-state-machine";
import { useVoiceStateStore } from "@/stores/voice-state.store";

describe("useVoiceStateStore", () => {
  beforeEach(() => {
    useVoiceStateStore.setState({ voiceState: "idle", history: [{ state: "idle", at: new Date().toISOString() }] });
  });

  it("starts idle -- no real voice backend exists to produce any other state", () => {
    expect(useVoiceStateStore.getState().voiceState).toBe("idle");
  });

  it("transition() applies a legal transition", () => {
    useVoiceStateStore.getState().transition("wake");
    expect(useVoiceStateStore.getState().voiceState).toBe("wake");
  });

  it("transition() throws on an illegal jump and does not mutate state", () => {
    expect(() => useVoiceStateStore.getState().transition("speaking")).toThrow(InvalidVoiceStateTransitionError);
    expect(useVoiceStateStore.getState().voiceState).toBe("idle");
  });

  it("records every transition in history, oldest first", () => {
    useVoiceStateStore.getState().transition("wake");
    useVoiceStateStore.getState().transition("listening");

    const states = useVoiceStateStore.getState().history.map((entry) => entry.state);
    expect(states).toEqual(["idle", "wake", "listening"]);
  });

  it("caps history at 20 entries", () => {
    let state = useVoiceStateStore.getState().voiceState;
    for (let i = 0; i < 30; i++) {
      const next = state === "idle" ? "wake" : "idle";
      useVoiceStateStore.getState().transition(next);
      state = next;
    }
    expect(useVoiceStateStore.getState().history.length).toBeLessThanOrEqual(20);
  });
});
