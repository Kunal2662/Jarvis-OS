import { VoiceWaveformRenderer } from "@/components/voice/voice-waveform-renderer";
import { useVoiceAudioLevelsStore } from "@/stores/voice-audio-levels.store";
import { useVoiceStateStore } from "@/stores/voice-state.store";

/**
 * JARVIS's voice identity (Phase 4, Task Group H) -- the thin layer
 * that wires real store state into `VoiceWaveformRenderer`
 * (`components/voice/voice-waveform-renderer.tsx`), which does the
 * actual rendering and has no store dependency of its own. Kept
 * separate on purpose: state management and rendering are two
 * different concerns, and the renderer alone is what a test, a
 * Storybook-style preview, or Developer Mode's manual level sliders
 * needs to drive directly without touching global state.
 */
export function VoiceString({ className }: { className?: string }) {
  const voiceState = useVoiceStateStore((s) => s.voiceState);
  const microphoneLevel = useVoiceAudioLevelsStore((s) => s.microphoneLevel);
  const ttsLevel = useVoiceAudioLevelsStore((s) => s.ttsLevel);

  return (
    <VoiceWaveformRenderer
      voiceState={voiceState}
      microphoneLevel={microphoneLevel}
      ttsLevel={ttsLevel}
      className={className}
    />
  );
}
