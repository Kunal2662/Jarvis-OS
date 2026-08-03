import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/providers/router-provider", () => ({ RouterProvider: () => <div data-testid="real-app" /> }));
vi.mock("@/core/startup-orchestrator", () => ({ runStartupSequence: vi.fn() }));
vi.mock("@/components/startup/startup-sequence", () => ({
  StartupSequence: ({ onComplete }: { onComplete: () => void }) => (
    <button onClick={onComplete}>finish choreography</button>
  ),
}));

import { runStartupSequence } from "@/core/startup-orchestrator";
import { StartupGate } from "@/components/startup/startup-gate";
import { useAccessibilityPreferencesStore } from "@/stores/accessibility-preferences.store";

describe("StartupGate", () => {
  beforeEach(() => {
    useAccessibilityPreferencesStore.setState({ skipStartupAnimation: false, disableGlassEffects: false });
    vi.mocked(runStartupSequence).mockReset();
  });

  it("renders the startup sequence first, not the real app", () => {
    vi.mocked(runStartupSequence).mockReturnValue(new Promise(() => {}));

    render(<StartupGate />);

    expect(screen.getByRole("button", { name: "finish choreography" })).toBeInTheDocument();
    expect(screen.queryByTestId("real-app")).not.toBeInTheDocument();
  });

  it("does not reveal the real app when the choreography finishes but real init hasn't", async () => {
    vi.mocked(runStartupSequence).mockReturnValue(new Promise(() => {}));
    render(<StartupGate />);

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "finish choreography" }));
    });

    expect(screen.queryByTestId("real-app")).not.toBeInTheDocument();
  });

  it("does not reveal the real app when real init finishes but the choreography hasn't", async () => {
    let resolveWork!: () => void;
    vi.mocked(runStartupSequence).mockReturnValue(new Promise<void>((resolve) => (resolveWork = resolve)));
    render(<StartupGate />);

    await act(async () => {
      resolveWork();
      await Promise.resolve();
    });

    expect(screen.queryByTestId("real-app")).not.toBeInTheDocument();
  });

  it("reveals the real app once BOTH real init and the choreography are done", async () => {
    let resolveWork!: () => void;
    vi.mocked(runStartupSequence).mockReturnValue(new Promise<void>((resolve) => (resolveWork = resolve)));
    render(<StartupGate />);

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "finish choreography" }));
    });
    await act(async () => {
      resolveWork();
      await Promise.resolve();
    });

    expect(screen.getByTestId("real-app")).toBeInTheDocument();
  });

  it("skips the choreography and reveals as soon as real init finishes, when skipStartupAnimation is set", async () => {
    useAccessibilityPreferencesStore.setState({ skipStartupAnimation: true });
    vi.mocked(runStartupSequence).mockResolvedValue(undefined);

    render(<StartupGate />);

    expect(await screen.findByTestId("real-app")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "finish choreography" })).not.toBeInTheDocument();
  });
});
