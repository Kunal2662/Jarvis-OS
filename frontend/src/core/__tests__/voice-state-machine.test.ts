import { describe, expect, it } from "vitest";
import {
  InvalidVoiceStateTransitionError,
  assertValidVoiceStateTransition,
  canTransitionVoiceState,
  reachableVoiceStates,
  VOICE_STATES,
} from "@/core/voice-state-machine";

describe("voice-state-machine", () => {
  it("lists exactly the 7 states the voice experience brief specifies", () => {
    expect(VOICE_STATES).toEqual(["idle", "wake", "listening", "thinking", "speaking", "success", "error"]);
  });

  it("allows the real end-to-end flow: idle -> wake -> listening -> thinking -> speaking -> success -> idle", () => {
    const flow = ["idle", "wake", "listening", "thinking", "speaking", "success", "idle"] as const;
    for (let i = 0; i < flow.length - 1; i++) {
      expect(canTransitionVoiceState(flow[i], flow[i + 1])).toBe(true);
    }
  });

  it("allows error from listening, thinking, or speaking, and error always returns to idle", () => {
    expect(canTransitionVoiceState("listening", "error")).toBe(true);
    expect(canTransitionVoiceState("thinking", "error")).toBe(true);
    expect(canTransitionVoiceState("speaking", "error")).toBe(true);
    expect(canTransitionVoiceState("error", "idle")).toBe(true);
  });

  it("allows a wake-word timeout back to idle without ever listening", () => {
    expect(canTransitionVoiceState("wake", "idle")).toBe(true);
  });

  it("rejects an illegal jump, e.g. idle straight to speaking", () => {
    expect(canTransitionVoiceState("idle", "speaking")).toBe(false);
    expect(() => assertValidVoiceStateTransition("idle", "speaking")).toThrow(InvalidVoiceStateTransitionError);
  });

  it("always allows a self-transition", () => {
    expect(canTransitionVoiceState("thinking", "thinking")).toBe(true);
  });

  it("reachableVoiceStates matches canTransitionVoiceState exactly", () => {
    for (const from of VOICE_STATES) {
      for (const to of VOICE_STATES) {
        if (from === to) continue;
        expect(reachableVoiceStates(from).includes(to)).toBe(canTransitionVoiceState(from, to));
      }
    }
  });
});
