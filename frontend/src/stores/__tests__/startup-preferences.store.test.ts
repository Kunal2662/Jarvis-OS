import { beforeEach, describe, expect, it } from "vitest";
import { useStartupPreferencesStore } from "@/stores/startup-preferences.store";

describe("useStartupPreferencesStore", () => {
  beforeEach(() => {
    useStartupPreferencesStore.setState({ skipStartupAnimation: false, disableGlassEffects: false });
  });

  it("starts with both preferences off", () => {
    expect(useStartupPreferencesStore.getState().skipStartupAnimation).toBe(false);
    expect(useStartupPreferencesStore.getState().disableGlassEffects).toBe(false);
  });

  it("setSkipStartupAnimation() updates only that flag", () => {
    useStartupPreferencesStore.getState().setSkipStartupAnimation(true);

    expect(useStartupPreferencesStore.getState().skipStartupAnimation).toBe(true);
    expect(useStartupPreferencesStore.getState().disableGlassEffects).toBe(false);
  });

  it("setDisableGlassEffects() updates only that flag", () => {
    useStartupPreferencesStore.getState().setDisableGlassEffects(true);

    expect(useStartupPreferencesStore.getState().disableGlassEffects).toBe(true);
    expect(useStartupPreferencesStore.getState().skipStartupAnimation).toBe(false);
  });
});
