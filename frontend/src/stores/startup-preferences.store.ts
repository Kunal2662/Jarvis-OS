import { create } from "zustand";
import { persist } from "zustand/middleware";

interface StartupPreferencesState {
  /** Skips the cinematic startup sequence entirely -- straight into the
   *  real app once real initialization finishes. Real init still runs
   *  either way; only the choreography is skipped. */
  skipStartupAnimation: boolean;
  /** Originally scoped to the startup sequence's own glow/blur (Task
   *  Group I); Task Group J's Glass design system wired every real
   *  glass surface it added (Sidebar, Card, Command Palette,
   *  DesktopShell's ambient glow) to this same flag rather than
   *  inventing a second one -- one real "disable glass" preference,
   *  not two that can drift out of sync. `VoiceWaveformRenderer`'s own
   *  panel styling is intentionally untouched either way (its glow is
   *  part of the state-communication contract, not decorative). The
   *  toggle itself is exposed via Developer Mode's Startup Preview
   *  panel today; a real Settings > Accessibility surface remains a
   *  later task group's job. */
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
