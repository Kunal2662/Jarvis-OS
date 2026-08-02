import { create } from "zustand";

export interface TranscriptWord {
  id: string;
  text: string;
}

interface VoiceTranscriptStoreShape {
  words: TranscriptWord[];
  /** Appends one streamed word -- the real Live Transcript's unit of
   *  update once a real STT stream exists (`core/interfaces/voice-
   *  integration.ts`'s header comment: speech recognition is entirely
   *  M2's backend scope, reached through the WebSocket layer). Never
   *  called by anything in this codebase yet -- starts and stays empty,
   *  the same honest-emptiness pattern every other "no backend yet"
   *  surface in this app already follows. */
  appendWord: (text: string) => void;
  clear: () => void;
}

export const useVoiceTranscriptStore = create<VoiceTranscriptStoreShape>()((set) => ({
  words: [],
  appendWord: (text) =>
    set((s) => ({ words: [...s.words, { id: `${Date.now()}-${s.words.length}`, text }] })),
  clear: () => set({ words: [] }),
}));
