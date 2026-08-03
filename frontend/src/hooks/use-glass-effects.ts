import { useAccessibilityPreferencesStore } from "@/stores/accessibility-preferences.store";

/**
 * Whether glass surfaces (backdrop blur + translucency) should render.
 * Wraps the real, persisted `disableGlassEffects` preference
 * (`stores/accessibility-preferences.store.ts`) behind a name that
 * reads correctly at every glass-aware call site -- Sidebar, Card, and
 * Command Palette. Some users get real visual strain from blur/
 * transparency effects, so every glass surface must offer a solid
 * fallback, not just a decorative default.
 */
export function useGlassEffectsEnabled(): boolean {
  return !useAccessibilityPreferencesStore((state) => state.disableGlassEffects);
}
