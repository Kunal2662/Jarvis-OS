import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { StartupSequence } from "@/components/startup/startup-sequence";
import { useAccessibilityPreferencesStore } from "@/stores/accessibility-preferences.store";
import { useVoiceStateStore } from "@/stores/voice-state.store";

// VoiceString's continuous useTime()/requestAnimationFrame loop
// (components/voice/voice-string.tsx) fights with fake timers, same
// reason it's mocked out in voice-state-preview.test.tsx -- this file
// is about the sequence's own phase choreography, not VoiceString's
// own rendering (which has its own dedicated test file).
vi.mock("@/components/voice/voice-string", () => ({ VoiceString: () => null }));

// Cumulative ms to reach the start of each named phase -- point(400) +
// ripple(600) + logo-assemble(900) + logo-pulse(400) = 2300 to reach
// voice-morph; + voice-activate(500) on top of voice-morph's own
// 400 = 900 more to reach voice-expand; total choreography is 4200.
const MS_TO_VOICE_MORPH = 2300;
const MS_VOICE_MORPH_TO_VOICE_EXPAND = 900;
const MS_TOTAL = 4200;

describe("StartupSequence", () => {
  beforeEach(() => {
    useAccessibilityPreferencesStore.setState({ skipStartupAnimation: false, disableGlassEffects: false });
    useVoiceStateStore.setState({ voiceState: "idle", history: [{ state: "idle", at: new Date().toISOString() }] });
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("does not call onComplete before the choreography finishes", () => {
    const onComplete = vi.fn();
    render(<StartupSequence onComplete={onComplete} />);

    act(() => vi.advanceTimersByTime(500));

    expect(onComplete).not.toHaveBeenCalled();
  });

  it("calls onComplete exactly once the full choreography finishes", () => {
    const onComplete = vi.fn();
    render(<StartupSequence onComplete={onComplete} />);

    act(() => vi.advanceTimersByTime(MS_TOTAL));

    expect(onComplete).toHaveBeenCalledOnce();
  });

  it("drives the real voice state store: idle -> wake at the morph beat", () => {
    render(<StartupSequence onComplete={() => {}} />);

    act(() => vi.advanceTimersByTime(MS_TO_VOICE_MORPH));

    expect(useVoiceStateStore.getState().voiceState).toBe("wake");
  });

  it("drives the real voice state store: wake -> idle at the expand beat", () => {
    render(<StartupSequence onComplete={() => {}} />);

    act(() => vi.advanceTimersByTime(MS_TO_VOICE_MORPH + MS_VOICE_MORPH_TO_VOICE_EXPAND));

    expect(useVoiceStateStore.getState().voiceState).toBe("idle");
  });

  it("has an sr-only status announcement, and no visible startup text anywhere", () => {
    render(<StartupSequence onComplete={() => {}} />);

    expect(screen.getByRole("status")).toHaveTextContent("JARVIS is starting up.");
    expect(screen.queryByText(/loading/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/initializing/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/ready/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/%/)).not.toBeInTheDocument();
  });

  it("respects disableGlassEffects -- no blur glow layer rendered", () => {
    useAccessibilityPreferencesStore.setState({ disableGlassEffects: true });
    const { container } = render(<StartupSequence onComplete={() => {}} />);

    act(() => vi.advanceTimersByTime(MS_TO_VOICE_MORPH));

    expect(container.querySelector(".blur-3xl")).toBeNull();
  });

  it("shows the blur glow layer once glass effects are enabled (the default)", () => {
    const { container } = render(<StartupSequence onComplete={() => {}} />);

    act(() => vi.advanceTimersByTime(MS_TO_VOICE_MORPH));

    expect(container.querySelector(".blur-3xl")).not.toBeNull();
  });
});
