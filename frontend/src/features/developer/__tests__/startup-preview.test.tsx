import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/components/startup/startup-sequence", () => ({
  StartupSequence: ({ onComplete }: { onComplete: () => void }) => (
    <div data-testid="replaying">
      <button onClick={onComplete}>done</button>
    </div>
  ),
}));

import { StartupPreview } from "@/features/developer/startup-preview";
import { useAccessibilityPreferencesStore } from "@/stores/accessibility-preferences.store";

describe("StartupPreview", () => {
  beforeEach(() => {
    useAccessibilityPreferencesStore.setState({
      skipStartupAnimation: false,
      reducedMotion: false,
      disableGlassEffects: false,
    });
  });

  it("does not render the startup sequence until Replay is clicked", () => {
    render(<StartupPreview />);
    expect(screen.queryByTestId("replaying")).not.toBeInTheDocument();
  });

  it("Replay renders the real StartupSequence, which self-clears on completion", async () => {
    render(<StartupPreview />);

    await userEvent.click(screen.getByRole("button", { name: "Replay startup sequence" }));
    expect(screen.getByTestId("replaying")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "done" }));
    expect(screen.queryByTestId("replaying")).not.toBeInTheDocument();
  });

  it("toggles the real skipStartupAnimation preference", async () => {
    render(<StartupPreview />);

    await userEvent.click(screen.getByRole("button", { name: /Skip startup animation/ }));

    expect(useAccessibilityPreferencesStore.getState().skipStartupAnimation).toBe(true);
  });

  it("toggles the real reducedMotion preference", async () => {
    render(<StartupPreview />);

    await userEvent.click(screen.getByRole("button", { name: /Reduced motion/ }));

    expect(useAccessibilityPreferencesStore.getState().reducedMotion).toBe(true);
  });

  it("toggles the real disableGlassEffects preference", async () => {
    render(<StartupPreview />);

    await userEvent.click(screen.getByRole("button", { name: /Disable glass effects/ }));

    expect(useAccessibilityPreferencesStore.getState().disableGlassEffects).toBe(true);
  });
});
