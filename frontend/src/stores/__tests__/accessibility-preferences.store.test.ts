import { beforeEach, describe, expect, it } from "vitest";
import { useAccessibilityPreferencesStore } from "@/stores/accessibility-preferences.store";

describe("useAccessibilityPreferencesStore", () => {
  beforeEach(() => {
    useAccessibilityPreferencesStore.setState({
      skipStartupAnimation: false,
      reducedMotion: false,
      disableGlassEffects: false,
    });
  });

  it("starts with every preference off", () => {
    expect(useAccessibilityPreferencesStore.getState().skipStartupAnimation).toBe(false);
    expect(useAccessibilityPreferencesStore.getState().reducedMotion).toBe(false);
    expect(useAccessibilityPreferencesStore.getState().disableGlassEffects).toBe(false);
  });

  it("setSkipStartupAnimation() updates only that flag", () => {
    useAccessibilityPreferencesStore.getState().setSkipStartupAnimation(true);

    expect(useAccessibilityPreferencesStore.getState().skipStartupAnimation).toBe(true);
    expect(useAccessibilityPreferencesStore.getState().reducedMotion).toBe(false);
    expect(useAccessibilityPreferencesStore.getState().disableGlassEffects).toBe(false);
  });

  it("setReducedMotion() updates only that flag", () => {
    useAccessibilityPreferencesStore.getState().setReducedMotion(true);

    expect(useAccessibilityPreferencesStore.getState().reducedMotion).toBe(true);
    expect(useAccessibilityPreferencesStore.getState().skipStartupAnimation).toBe(false);
    expect(useAccessibilityPreferencesStore.getState().disableGlassEffects).toBe(false);
  });

  it("setDisableGlassEffects() updates only that flag", () => {
    useAccessibilityPreferencesStore.getState().setDisableGlassEffects(true);

    expect(useAccessibilityPreferencesStore.getState().disableGlassEffects).toBe(true);
    expect(useAccessibilityPreferencesStore.getState().skipStartupAnimation).toBe(false);
    expect(useAccessibilityPreferencesStore.getState().reducedMotion).toBe(false);
  });
});
