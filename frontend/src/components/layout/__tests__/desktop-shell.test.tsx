import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { DesktopShell } from "@/components/layout/desktop-shell";

/**
 * Smoke test only -- proves the composed layout (Sidebar, Dock, Header,
 * Workspace, Status Bar, Developer Panel, plus the 4 new reserved
 * layers) renders without crashing. Sidebar/Dock/Workspace each own
 * their own, more detailed tests; this only guards the composition
 * itself.
 */
describe("DesktopShell", () => {
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
});
