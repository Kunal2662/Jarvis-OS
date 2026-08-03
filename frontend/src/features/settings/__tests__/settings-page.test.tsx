import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { SettingsPage } from "@/features/settings/settings-page";
import { useAccessibilityPreferencesStore } from "@/stores/accessibility-preferences.store";

describe("SettingsPage", () => {
  beforeEach(() => {
    useAccessibilityPreferencesStore.setState({
      skipStartupAnimation: false,
      reducedMotion: false,
      disableGlassEffects: false,
    });
  });

  it("renders the real, current state of every accessibility preference", () => {
    useAccessibilityPreferencesStore.setState({ reducedMotion: true });
    render(<SettingsPage />);

    expect(screen.getByRole("switch", { name: "Skip startup animation" })).toHaveAttribute(
      "aria-checked",
      "false",
    );
    expect(screen.getByRole("switch", { name: "Reduced motion" })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("switch", { name: "Disable glass effects" })).toHaveAttribute(
      "aria-checked",
      "false",
    );
  });

  it("toggles the real skipStartupAnimation preference", async () => {
    render(<SettingsPage />);

    await userEvent.click(screen.getByRole("switch", { name: "Skip startup animation" }));

    expect(useAccessibilityPreferencesStore.getState().skipStartupAnimation).toBe(true);
  });

  it("toggles the real reducedMotion preference", async () => {
    render(<SettingsPage />);

    await userEvent.click(screen.getByRole("switch", { name: "Reduced motion" }));

    expect(useAccessibilityPreferencesStore.getState().reducedMotion).toBe(true);
  });

  it("toggles the real disableGlassEffects preference", async () => {
    render(<SettingsPage />);

    await userEvent.click(screen.getByRole("switch", { name: "Disable glass effects" }));

    expect(useAccessibilityPreferencesStore.getState().disableGlassEffects).toBe(true);
  });
});
