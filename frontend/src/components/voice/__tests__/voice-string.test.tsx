import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { VoiceString } from "@/components/voice/voice-string";
import { useVoiceStateStore } from "@/stores/voice-state.store";

describe("VoiceString", () => {
  beforeEach(() => {
    useVoiceStateStore.setState({ voiceState: "idle", history: [{ state: "idle", at: new Date().toISOString() }] });
  });

  it("renders as an accessible image labeled with the current state, never visible state text", () => {
    render(<VoiceString />);

    const svg = screen.getByRole("img", { name: "Idle" });
    expect(svg).toBeInTheDocument();
    expect(screen.queryByText("Idle")).not.toBeInTheDocument();
    expect(screen.queryByText(/listening/i)).not.toBeInTheDocument();
  });

  it("updates its accessible label when the voice state changes", () => {
    const { rerender } = render(<VoiceString />);
    expect(screen.getByRole("img", { name: "Idle" })).toBeInTheDocument();

    useVoiceStateStore.getState().transition("wake");
    rerender(<VoiceString />);

    expect(screen.getByRole("img", { name: "Waking up" })).toBeInTheDocument();
  });

  it("renders a real SVG path, not an empty placeholder", () => {
    const { container } = render(<VoiceString />);
    const path = container.querySelector("path");
    expect(path).not.toBeNull();
    expect(path?.getAttribute("d")).toMatch(/^M /);
  });

  it("renders no glow layer for idle (minimal by default) but does for an active state", () => {
    const { container: idleContainer } = render(<VoiceString />);
    expect(idleContainer.querySelectorAll("path")).toHaveLength(1);

    useVoiceStateStore.getState().transition("wake");
    const { container: wakeContainer } = render(<VoiceString />);
    expect(wakeContainer.querySelectorAll("path")).toHaveLength(2);
  });
});
