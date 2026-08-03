import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";
import { DesktopShell } from "@/components/layout/desktop-shell";
import { useStartupPreferencesStore } from "@/stores/startup-preferences.store";

/**
 * Smoke test only -- proves the composed layout (Sidebar, Dock, Header,
 * Workspace, Status Bar, Developer Panel, plus the 4 new reserved
 * layers) renders without crashing. Sidebar/Dock/Workspace each own
 * their own, more detailed tests; this only guards the composition
 * itself.
 */
describe("DesktopShell", () => {
  beforeEach(() => {
    useStartupPreferencesStore.setState({ disableGlassEffects: false });
  });

  it("renders without crashing", () => {
    const { container } = render(
      <MemoryRouter>
        <DesktopShell />
      </MemoryRouter>,
    );

    expect(container.querySelector("aside")).toBeInTheDocument(); // Sidebar
    expect(container.querySelector("header")).toBeInTheDocument(); // Header
    expect(container.querySelector("footer")).toBeInTheDocument(); // Status Bar
  });

  describe("glass surface (Task Group J)", () => {
    it("renders the ambient glow behind glass surfaces by default", () => {
      render(
        <MemoryRouter>
          <DesktopShell />
        </MemoryRouter>,
      );
      expect(screen.getByTestId("ambient-glow")).toBeInTheDocument();
    });

    it("skips the ambient glow entirely when the real disableGlassEffects preference is set", () => {
      useStartupPreferencesStore.setState({ disableGlassEffects: true });
      render(
        <MemoryRouter>
          <DesktopShell />
        </MemoryRouter>,
      );
      expect(screen.queryByTestId("ambient-glow")).not.toBeInTheDocument();
    });
  });
});
