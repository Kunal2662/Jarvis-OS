import { create } from "zustand";
import { persist } from "zustand/middleware";

interface StartupPreferencesState {
  /** Skips the cinematic startup sequence entirely -- straight into the
   *  real app once real initialization finishes. Real init still runs
   *  either way; only the choreography is skipped. */
  skipStartupAnimation: boolean;
  /** Scoped to the startup sequence's own glass/blur surfaces for this
   *  task group (the sequence never touches `VoiceWaveformRenderer`'s
   *  own panel styling, which stays exactly as shipped) -- an
   *  app-wide "disable glass everywhere" toggle is a later,
   *  dedicated accessibility task group's job. */
  disableGlassEffects: boolean;
  setSkipStartupAnimation: (skip: boolean) => void;
  setDisableGlassEffects: (disable: boolean) => void;
}

/**
 * Accessibility preferences for the startup experience (Phase 4, Task
 * Group I). Persisted like `sidebar.store.ts`/`dock.store.ts` -- a
 * skip/reduce-motion choice should survive restarts, not reset every
 * launch. Both default to `false`; OS-level `prefers-reduced-motion`
 * (via Motion's `useReducedMotion()`) is honored automatically on top
 * of this, independent of whether the user has set either flag here.
 */
export const useStartupPreferencesStore = create<StartupPreferencesState>()(
  persist(
    (set) => ({
      skipStartupAnimation: false,
      disableGlassEffects: false,
      setSkipStartupAnimation: (skip) => set({ skipStartupAnimation: skip }),
      setDisableGlassEffects: (disable) => set({ disableGlassEffects: disable }),
    }),
    { name: "jarvis.startup-preferences" },
  ),
);
