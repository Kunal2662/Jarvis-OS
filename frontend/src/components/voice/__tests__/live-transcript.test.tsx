import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LiveTranscript } from "@/components/voice/live-transcript";
import { useVoiceTranscriptStore } from "@/stores/voice-transcript.store";

describe("LiveTranscript", () => {
  beforeEach(() => {
    useVoiceTranscriptStore.setState({ words: [] });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("renders nothing when the transcript is empty -- no placeholder text", () => {
    const { container } = render(<LiveTranscript />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders real words from the store, in order", () => {
    useVoiceTranscriptStore.setState({
      words: [
        { id: "1", text: "Hello" },
        { id: "2", text: "there" },
      ],
    });

    render(<LiveTranscript />);

    expect(screen.getByText("Hello")).toBeInTheDocument();
    expect(screen.getByText("there")).toBeInTheDocument();
  });

  it("has a live region so screen readers announce new words", () => {
    useVoiceTranscriptStore.setState({ words: [{ id: "1", text: "Hello" }] });
    render(<LiveTranscript />);

    expect(screen.getByText("Hello").closest('[aria-live="polite"]')).toBeInTheDocument();
  });

  it("clears the transcript after 4s of inactivity", () => {
    vi.useFakeTimers();
    useVoiceTranscriptStore.setState({ words: [{ id: "1", text: "Hello" }] });

    render(<LiveTranscript />);
    expect(useVoiceTranscriptStore.getState().words).toHaveLength(1);

    vi.advanceTimersByTime(4000);
    expect(useVoiceTranscriptStore.getState().words).toHaveLength(0);
  });

  it("resets the fade timer when a new word arrives", () => {
    vi.useFakeTimers();
    useVoiceTranscriptStore.setState({ words: [{ id: "1", text: "Hello" }] });
    const { rerender } = render(<LiveTranscript />);

    vi.advanceTimersByTime(3000);
    useVoiceTranscriptStore.getState().appendWord("world");
    rerender(<LiveTranscript />);

    vi.advanceTimersByTime(3000); // 6s total, but only 3s since the reset
    expect(useVoiceTranscriptStore.getState().words.length).toBeGreaterThan(0);

    vi.advanceTimersByTime(1000); // now 4s since the reset
    expect(useVoiceTranscriptStore.getState().words).toHaveLength(0);
  });
});
