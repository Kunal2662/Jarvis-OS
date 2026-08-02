import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { VoiceString } from "@/components/voice/voice-string";
import { useVoiceAudioLevelsStore } from "@/stores/voice-audio-levels.store";
import { useVoiceStateStore } from "@/stores/voice-state.store";

// VoiceString is deliberately a thin store-wiring layer (see its own
// header comment) -- this file tests exactly that wiring, not
// rendering, which VoiceWaveformRenderer's own dedicated test file
// already covers.
vi.mock("@/components/voice/voice-waveform-renderer", () => ({
  VoiceWaveformRenderer: (props: Record<string, unknown>) => (
    <div data-testid="renderer" data-props={JSON.stringify(props)} />
  ),
}));

function rendererProps(): Record<string, unknown> {
  return JSON.parse(screen.getByTestId("renderer").getAttribute("data-props") ?? "{}") as Record<string, unknown>;
}

describe("VoiceString", () => {
  beforeEach(() => {
    useVoiceStateStore.setState({ voiceState: "idle", history: [{ state: "idle", at: new Date().toISOString() }] });
    useVoiceAudioLevelsStore.setState({ microphoneLevel: 0, ttsLevel: 0 });
  });

  it("wires the real voice state into the renderer", () => {
    useVoiceStateStore.getState().transition("wake");
    render(<VoiceString />);

    expect(rendererProps().voiceState).toBe("wake");
  });

  it("wires the real audio levels into the renderer", () => {
    useVoiceAudioLevelsStore.setState({ microphoneLevel: 0.4, ttsLevel: 0.2 });
    render(<VoiceString />);

    expect(rendererProps().microphoneLevel).toBe(0.4);
    expect(rendererProps().ttsLevel).toBe(0.2);
  });

  it("passes className through to the renderer", () => {
    render(<VoiceString className="my-class" />);
    expect(rendererProps().className).toBe("my-class");
  });
});
