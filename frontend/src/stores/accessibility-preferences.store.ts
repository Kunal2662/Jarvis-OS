import { create } from "zustand";
import { persist } from "zustand/middleware";

interface AccessibilityPreferencesState {
  /** Skips the cinematic startup sequence entirely -- straight into the
   *  real app once real initialization finishes. Real init still runs
   *  either way; only the choreography is skipped. */
  skipStartupAnimation: boolean;
  /** An app-level override on top of the OS-level `prefers-reduced-motion`
   *  media query Motion's `useReducedMotion()` already honors everywhere
   *  (`MotionConfig`'s app-wide `reducedMotion="user"`) -- lets a user
   *  turn animation down from inside JARVIS even when their OS-level
   *  setting doesn't (or can't) express it. Wired directly into
   *  `MotionConfig`'s own `reducedMotion` prop (`providers/app-providers.tsx`):
   *  `true` here maps to Motion's `"always"`, which makes every existing
   *  `useReducedMotion()` consumer (the Voice Waveform's continuous
   *  `useTime()` loop, the startup sequence, etc.) report reduced motion
   *  unconditionally -- zero changes needed in any of them. */
  reducedMotion: boolean;
  /** Real glass surfaces this preference gates: Sidebar, the shared
   *  `Card` primitive, Command Palette (Task Group J), and the startup
   *  sequence's own glow (Task Group I) -- one real "disable glass"
   *  preference, app-wide, not several that could drift out of sync.
   *  `VoiceWaveformRenderer`'s own panel styling is intentionally
   *  untouched either way (its glow is part of the state-communication
   *  contract, not decorative). */
  disableGlassEffects: boolean;
  setSkipStartupAnimation: (skip: boolean) => void;
  setReducedMotion: (reduced: boolean) => void;
  setDisableGlassEffects: (disable: boolean) => void;
}

/**
 * Real, persisted accessibility preferences -- started life scoped to
 * the startup sequence alone (Phase 4, Task Group I, as
 * `startup-preferences.store.ts`), then Task Group J's Glass design
 * system made `disableGlassEffects` genuinely app-wide, and Task Group
 * K (Accessibility settings) added `reducedMotion` and gave all three a
 * real, non-Developer-Mode home (`features/settings/`) -- renamed here
 * to match what the store actually is today. Persisted like
 * `sidebar.store.ts`/`dock.store.ts` -- an accessibility choice should
 * survive restarts, not reset every launch. All three default to
 * `false`: OS-level `prefers-reduced-motion` is still honored
 * automatically regardless of `reducedMotion`'s own value here (Motion's
 * `"user"` mode falls back to it), so leaving this off never removes
 * the OS-level protection a user already has.
 */
export const useAccessibilityPreferencesStore = create<AccessibilityPreferencesState>()(
  persist(
    (set) => ({
      skipStartupAnimation: false,
      reducedMotion: false,
      disableGlassEffects: false,
      setSkipStartupAnimation: (skip) => set({ skipStartupAnimation: skip }),
      setReducedMotion: (reduced) => set({ reducedMotion: reduced }),
      setDisableGlassEffects: (disable) => set({ disableGlassEffects: disable }),
    }),
    { name: "jarvis.accessibility-preferences" },
  ),
);
