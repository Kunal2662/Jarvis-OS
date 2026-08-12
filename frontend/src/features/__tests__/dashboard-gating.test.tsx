import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { AdministratorDashboard } from "@/features/admin/administrator-dashboard";
import { DeveloperDashboard } from "@/features/developer/developer-dashboard";
import { atLeast } from "@/core/user-mode";
import { panelRegistry, registerCorePanels, resetPanelRegistryForTesting } from "@/core/panel-registry";
import { setApiBaseUrl } from "@/services/api/client";
import { useConnectionStore } from "@/stores/connection.store";
import { useDeveloperModeStore } from "@/stores/developer-mode.store";
import { resetUserModeForTesting, setAdministrator } from "@/stores/user-mode.store";

/**
 * `ARCHITECTURE.md` §22.12 is enforced in two independent places, and
 * both are tested here: the panel *menu* filters restricted panels out,
 * and each dashboard component refuses to render regardless of how it
 * was reached. Two gates because a workspace layout can be exported
 * from a developer's machine and imported on a personal one — the menu
 * filter alone would not stop that.
 */

beforeEach(() => {
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      disconnect() {}
    },
  );
  vi.stubGlobal("fetch", vi.fn(() => new Promise(() => {})));
  setApiBaseUrl("http://127.0.0.1:8000/api/v1");
  resetUserModeForTesting();
  // Offline, so no panel below actually issues a request; these tests
  // are about the gate, not the data.
  useConnectionStore.setState({
    state: "unreachable",
    detail: "",
    socket: "offline",
    authenticated: false,
    hasAttempted: true,
  });
});

describe("DeveloperDashboard", () => {
  it("refuses to render for a personal user", () => {
    render(<DeveloperDashboard />);

    expect(screen.getByText("Developer Mode required")).toBeInTheDocument();
    // The restricted headings must not be in the tree at all — not
    // merely hidden with CSS.
    expect(screen.queryByText("Providers & routing")).not.toBeInTheDocument();
    expect(screen.queryByText("Agent trace")).not.toBeInTheDocument();
  });

  it("renders once Developer Mode is unlocked", () => {
    useDeveloperModeStore.getState().unlock();

    render(<DeveloperDashboard />);

    expect(screen.queryByText("Developer Mode required")).not.toBeInTheDocument();
    expect(screen.getByText("Providers & routing")).toBeInTheDocument();
  });

  it("renders for an administrator, who outranks developer", () => {
    setAdministrator(true);
    render(<DeveloperDashboard />);
    expect(screen.getByText("Providers & routing")).toBeInTheDocument();
  });
});

describe("AdministratorDashboard", () => {
  it("refuses to render for a personal user", () => {
    render(<AdministratorDashboard />);
    expect(screen.getByText("Administrator access required")).toBeInTheDocument();
  });

  it("refuses to render for a developer — developer is not an admin", () => {
    useDeveloperModeStore.getState().unlock();

    render(<AdministratorDashboard />);

    expect(screen.getByText("Administrator access required")).toBeInTheDocument();
    expect(screen.queryByText("Audit log")).not.toBeInTheDocument();
  });

  it("renders for an administrator", () => {
    setAdministrator(true);

    render(<AdministratorDashboard />);

    expect(screen.getByText("AI health")).toBeInTheDocument();
    expect(screen.getByText("Audit log")).toBeInTheDocument();
  });

  it("names what it cannot show rather than faking it", () => {
    setAdministrator(true);

    render(<AdministratorDashboard />);

    // Budgets, users and analytics have no backend. An administrator
    // seeing "Budget: $0.00" would reasonably conclude nothing had been
    // spent; this is the honest alternative.
    expect(screen.getByText("Not yet available")).toBeInTheDocument();
    expect(screen.getByText("Daily & monthly budgets")).toBeInTheDocument();
    expect(screen.getByText("Users & roles")).toBeInTheDocument();
    expect(screen.queryByText(/\$0\.00/)).not.toBeInTheDocument();
  });
});

describe("panel registry gating", () => {
  beforeEach(() => {
    resetPanelRegistryForTesting();
    registerCorePanels();
  });

  it("marks the two restricted panels and leaves the rest open", () => {
    const developer = panelRegistry.get("core.developer");
    const administrator = panelRegistry.get("core.administrator");
    const search = panelRegistry.get("core.search");

    expect(developer?.requiredMode).toBe("developer");
    expect(administrator?.requiredMode).toBe("administrator");
    expect(search?.requiredMode).toBeUndefined();
  });

  it("a personal user is offered neither restricted panel", () => {
    const offered = panelRegistry
      .getAll()
      .filter((panel) => atLeast("personal", panel.requiredMode ?? "personal"))
      .map((panel) => panel.id);

    expect(offered).not.toContain("core.developer");
    expect(offered).not.toContain("core.administrator");
    expect(offered).toContain("core.notifications");
  });

  it("a developer is offered the developer panel but not the administrator one", () => {
    const offered = panelRegistry
      .getAll()
      .filter((panel) => atLeast("developer", panel.requiredMode ?? "personal"))
      .map((panel) => panel.id);

    expect(offered).toContain("core.developer");
    expect(offered).not.toContain("core.administrator");
  });
});
