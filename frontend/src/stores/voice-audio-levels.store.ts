import { create } from "zustand";

interface VoiceAudioLevelsStoreShape {
  /** 0..1, real microphone input amplitude. Always `0` today -- no
   *  real audio capture pipeline exists yet (`core/interfaces/voice-
   *  integration.ts`'s header comment: speech recognition is entirely
   *  M2's backend scope). This is the exact field a future mic-level
   *  WebSocket event or Web Audio API analyser node writes to; nothing
   *  else in this codebase reads or writes it, so it stays honestly at
   *  rest until one exists. */
  microphoneLevel: number;
  /** 0..1, real TTS output amplitude -- same "always 0 until a real
   *  pipeline exists" honesty as `microphoneLevel` above. */
  ttsLevel: number;
  setMicrophoneLevel: (level: number) => void;
  setTtsLevel: (level: number) => void;
}

function clamp01(value: number): number {
  return Math.min(1, Math.max(0, value));
}

/**
 * Real-time voice audio levels (Phase 4, Task Group H revision) -- the
 * live integration point `components/voice/voice-waveform-renderer.tsx`
 * accepts as props, separate from `stores/voice-state.store.ts`'s
 * discrete state (Idle/Listening/...). Kept as its own store rather
 * than folded into `voice-state.store.ts` since these are a different
 * kind of value entirely: a continuously-varying real number a future
 * audio pipeline streams many times per second, not a validated,
 * discrete state transition.
 */
export const useVoiceAudioLevelsStore = create<VoiceAudioLevelsStoreShape>()((set) => ({
  microphoneLevel: 0,
  ttsLevel: 0,
  setMicrophoneLevel: (level) => set({ microphoneLevel: clamp01(level) }),
  setTtsLevel: (level) => set({ ttsLevel: clamp01(level) }),
}));
