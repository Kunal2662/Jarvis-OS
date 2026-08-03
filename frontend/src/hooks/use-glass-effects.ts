import { useStartupPreferencesStore } from "@/stores/startup-preferences.store";

/**
 * Whether glass surfaces (backdrop blur + translucency) should render.
 * Wraps the real, persisted `disableGlassEffects` preference (Phase 4,
 * Task Group I) behind a name that reads correctly at every glass-aware
 * call site -- Sidebar, Card, and Command Palette have nothing to do
 * with startup, even though the preference itself still lives in
 * `startup-preferences.store.ts` alongside `skipStartupAnimation`.
 * Some users get real visual strain from blur/transparency effects, so
 * every glass surface must offer a solid fallback, not just a
 * decorative default.
 */
export function useGlassEffectsEnabled(): boolean {
  return !useStartupPreferencesStore((state) => state.disableGlassEffects);
}
