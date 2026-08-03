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
import { useStartupPreferencesStore } from "@/stores/startup-preferences.store";

describe("StartupPreview", () => {
  beforeEach(() => {
    useStartupPreferencesStore.setState({ skipStartupAnimation: false, disableGlassEffects: false });
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

    expect(useStartupPreferencesStore.getState().skipStartupAnimation).toBe(true);
  });

  it("toggles the real disableGlassEffects preference", async () => {
    render(<StartupPreview />);

    await userEvent.click(screen.getByRole("button", { name: /Disable glass effects/ }));

    expect(useStartupPreferencesStore.getState().disableGlassEffects).toBe(true);
  });
});
