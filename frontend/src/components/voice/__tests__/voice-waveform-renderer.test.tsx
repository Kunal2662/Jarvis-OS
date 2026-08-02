import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { VoiceWaveformRenderer } from "@/components/voice/voice-waveform-renderer";

describe("VoiceWaveformRenderer", () => {
  it("renders as an accessible image labeled with the current state, never visible state text", () => {
    render(<VoiceWaveformRenderer voiceState="idle" />);

    expect(screen.getByRole("img", { name: "Idle" })).toBeInTheDocument();
    expect(screen.queryByText("Idle")).not.toBeInTheDocument();
    expect(screen.queryByText(/listening/i)).not.toBeInTheDocument();
  });

  it("updates its accessible label per voice state", () => {
    const { rerender } = render(<VoiceWaveformRenderer voiceState="idle" />);
    expect(screen.getByRole("img", { name: "Idle" })).toBeInTheDocument();

    rerender(<VoiceWaveformRenderer voiceState="wake" />);
    expect(screen.getByRole("img", { name: "Waking up" })).toBeInTheDocument();
  });

  it("renders 40 animated bars, not an empty placeholder", () => {
    const { container } = render(<VoiceWaveformRenderer voiceState="listening" />);
    const bars = container.querySelectorAll('[role="img"] > span[aria-hidden="true"]');
    expect(bars).toHaveLength(40);
  });

  it("renders no glow layer for idle (minimal by default) but does for an active state", () => {
    const { container: idleContainer } = render(<VoiceWaveformRenderer voiceState="idle" />);
    expect(idleContainer.querySelector(".blur-2xl")).toBeNull();

    const { container: wakeContainer } = render(<VoiceWaveformRenderer voiceState="wake" />);
    expect(wakeContainer.querySelector(".blur-2xl")).not.toBeNull();
  });

  it("works with only voiceState -- microphoneLevel/ttsLevel/intensity all have honest defaults", () => {
    expect(() => render(<VoiceWaveformRenderer voiceState="speaking" />)).not.toThrow();
  });

  it("accepts explicit microphoneLevel/ttsLevel/intensity without throwing, across the full range", () => {
    expect(() =>
      render(<VoiceWaveformRenderer voiceState="speaking" microphoneLevel={1} ttsLevel={1} intensity={0} />),
    ).not.toThrow();
  });
});
