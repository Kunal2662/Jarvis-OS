import { beforeEach, describe, expect, it } from "vitest";
import { useVoiceTranscriptStore } from "@/stores/voice-transcript.store";

describe("useVoiceTranscriptStore", () => {
  beforeEach(() => {
    useVoiceTranscriptStore.setState({ words: [] });
  });

  it("starts empty -- no real speech-to-text stream exists yet", () => {
    expect(useVoiceTranscriptStore.getState().words).toEqual([]);
  });

  it("appendWord() adds a word, preserving order", () => {
    useVoiceTranscriptStore.getState().appendWord("Hello");
    useVoiceTranscriptStore.getState().appendWord("world");

    expect(useVoiceTranscriptStore.getState().words.map((w) => w.text)).toEqual(["Hello", "world"]);
  });

  it("assigns each word a unique id", () => {
    useVoiceTranscriptStore.getState().appendWord("Hello");
    useVoiceTranscriptStore.getState().appendWord("world");

    const ids = useVoiceTranscriptStore.getState().words.map((w) => w.id);
    expect(new Set(ids).size).toBe(2);
  });

  it("clear() empties the transcript", () => {
    useVoiceTranscriptStore.getState().appendWord("Hello");
    useVoiceTranscriptStore.getState().clear();

    expect(useVoiceTranscriptStore.getState().words).toEqual([]);
  });
});
