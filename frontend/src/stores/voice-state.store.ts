import { create } from "zustand";
import { assertValidVoiceStateTransition, type VoiceState } from "@/core/voice-state-machine";

export interface VoiceStateHistoryEntry {
  state: VoiceState;
  at: string;
}

const MAX_HISTORY = 20;

interface VoiceStateStoreShape {
  voiceState: VoiceState;
  /** Oldest first, capped -- Developer Mode's Voice State Preview panel
   *  diagnostic use only, mirroring `ModuleLifecycle.getHistory()`'s own
   *  "never drives application logic" rule. */
  history: VoiceStateHistoryEntry[];
  /** The one real entry point that changes voice state -- validated
   *  against `core/voice-state-machine.ts`'s transition graph, so an
   *  illegal jump throws rather than silently rendering a state the
   *  app never actually reached. The future real voice pipeline calls
   *  this exact function; Developer Mode's preview panel calls it too.
   *  No separate "fake preview" code path exists. */
  transition: (next: VoiceState) => void;
}

/**
 * The single source of truth for JARVIS's current voice state (Phase 4,
 * Task Group H). Starts and stays `"idle"` in normal operation: no real
 * voice backend exists yet (see `core/voice-state-machine.ts`'s header
 * comment), so nothing in production code ever calls `transition()`
 * today except Developer Mode's Voice State Preview panel
 * (`features/developer/voice-state-preview.tsx`), which is disabled by
 * default and never renders for end users.
 */
export const useVoiceStateStore = create<VoiceStateStoreShape>()((set, get) => ({
  voiceState: "idle",
  history: [{ state: "idle", at: new Date().toISOString() }],
  transition: (next) => {
    const current = get().voiceState;
    assertValidVoiceStateTransition(current, next);
    set((s) => ({
      voiceState: next,
      history: [...s.history, { state: next, at: new Date().toISOString() }].slice(-MAX_HISTORY),
    }));
  },
}));
