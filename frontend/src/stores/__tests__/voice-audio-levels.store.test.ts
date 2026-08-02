import { beforeEach, describe, expect, it } from "vitest";
import { useVoiceAudioLevelsStore } from "@/stores/voice-audio-levels.store";

describe("useVoiceAudioLevelsStore", () => {
  beforeEach(() => {
    useVoiceAudioLevelsStore.setState({ microphoneLevel: 0, ttsLevel: 0 });
  });

  it("starts at 0 -- no real audio pipeline exists yet", () => {
    expect(useVoiceAudioLevelsStore.getState().microphoneLevel).toBe(0);
    expect(useVoiceAudioLevelsStore.getState().ttsLevel).toBe(0);
  });

  it("setMicrophoneLevel() updates only the microphone level", () => {
    useVoiceAudioLevelsStore.getState().setMicrophoneLevel(0.6);

    expect(useVoiceAudioLevelsStore.getState().microphoneLevel).toBe(0.6);
    expect(useVoiceAudioLevelsStore.getState().ttsLevel).toBe(0);
  });

  it("setTtsLevel() updates only the TTS level", () => {
    useVoiceAudioLevelsStore.getState().setTtsLevel(0.8);

    expect(useVoiceAudioLevelsStore.getState().ttsLevel).toBe(0.8);
    expect(useVoiceAudioLevelsStore.getState().microphoneLevel).toBe(0);
  });

  it("clamps values to [0, 1]", () => {
    useVoiceAudioLevelsStore.getState().setMicrophoneLevel(2.5);
    expect(useVoiceAudioLevelsStore.getState().microphoneLevel).toBe(1);

    useVoiceAudioLevelsStore.getState().setTtsLevel(-1);
    expect(useVoiceAudioLevelsStore.getState().ttsLevel).toBe(0);
  });
});
