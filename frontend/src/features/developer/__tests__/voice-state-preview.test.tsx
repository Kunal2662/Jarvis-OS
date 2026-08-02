import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { VoiceStatePreview } from "@/features/developer/voice-state-preview";
import { useVoiceStateStore } from "@/stores/voice-state.store";

// VoiceString's continuous useTime()/requestAnimationFrame loop
// (components/voice/voice-string.tsx) fights with fake timers below,
// hanging the auto-cycle tests -- it has its own dedicated test file
// (components/voice/__tests__/voice-string.test.tsx); this file is
// about the preview panel's transition logic, not VoiceString's own
// rendering, so it's mocked out rather than exercised here.
vi.mock("@/components/voice/voice-string", () => ({ VoiceString: () => null }));

describe("VoiceStatePreview", () => {
  beforeEach(() => {
    useVoiceStateStore.setState({ voiceState: "idle", history: [{ state: "idle", at: new Date().toISOString() }] });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("shows the real current state", () => {
    render(<VoiceStatePreview />);
    expect(screen.getByText("Idle")).toBeInTheDocument();
  });

  it("only offers buttons for legal next states from idle", () => {
    render(<VoiceStatePreview />);

    expect(screen.getByRole("button", { name: "Wake" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Listening" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Speaking" })).not.toBeInTheDocument();
  });

  it("clicking a manual transition button drives the real voice state store", async () => {
    render(<VoiceStatePreview />);

    await userEvent.click(screen.getByRole("button", { name: "Wake" }));

    expect(useVoiceStateStore.getState().voiceState).toBe("wake");
  });

  it("auto-cycle steps through the real flow on a timer", () => {
    vi.useFakeTimers();
    render(<VoiceStatePreview />);

    // `fireEvent`, not `userEvent`, here -- userEvent's own internal
    // async/act scheduling fights vitest's fake timers (a well-known
    // interaction), hanging the test. fireEvent.click is synchronous
    // and doesn't have that problem.
    fireEvent.click(screen.getByRole("button", { name: "Auto-cycle for QA" }));

    act(() => vi.advanceTimersByTime(1800));
    expect(useVoiceStateStore.getState().voiceState).toBe("wake");

    act(() => vi.advanceTimersByTime(1800));
    expect(useVoiceStateStore.getState().voiceState).toBe("listening");
  });

  it("stopping auto-cycle clears the interval -- no further transitions happen", () => {
    vi.useFakeTimers();
    render(<VoiceStatePreview />);

    fireEvent.click(screen.getByRole("button", { name: "Auto-cycle for QA" }));
    act(() => vi.advanceTimersByTime(1800));
    fireEvent.click(screen.getByRole("button", { name: "Stop auto-cycle" }));

    const stateAfterStop = useVoiceStateStore.getState().voiceState;
    act(() => vi.advanceTimersByTime(5000));
    expect(useVoiceStateStore.getState().voiceState).toBe(stateAfterStop);
  });
});
