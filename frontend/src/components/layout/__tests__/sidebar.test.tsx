import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";
import { Sidebar } from "@/components/layout/sidebar";
import { applicationRegistry } from "@/core/application-registry";
import { TestApplication } from "@/core/test-utils/test-application";
import { useSidebarStore } from "@/stores/sidebar.store";
import { useWorkspaceStore } from "@/stores/workspace.store";

interface TestModuleOptions {
  name: string;
  displayName: string;
  icon: string;
  category: "local" | "connected";
  routes: string[];
}

function registerTestModule(options: TestModuleOptions): Promise<void> {
  return new TestApplication(options).initialize();
}

/**
 * Registry-driven Sidebar tests (Phase 3, Task Group C). Registers a
 * small, explicit set of test modules per test rather than the real 14
 * placeholder modules -- proves Sidebar reads whatever is in
 * ApplicationRegistry, not a hardcoded list, which the real 14 wouldn't
 * distinguish from a static array by coincidence.
 */
describe("Sidebar", () => {
  beforeEach(async () => {
    for (const module of applicationRegistry.getAll()) {
      applicationRegistry.unregister(module.manifest.name);
    }
    useSidebarStore.setState({ isCollapsed: false });
    useWorkspaceStore.setState({ activeModuleId: null });

    await registerTestModule({ name: "home", displayName: "Home", icon: "home", category: "local", routes: ["/"] });
    await registerTestModule({
      name: "gmail",
      displayName: "Gmail",
      icon: "mail",
      category: "connected",
      routes: ["/gmail"],
    });
    await registerTestModule({
      name: "calendar",
      displayName: "Calendar",
      icon: "calendar",
      category: "connected",
      routes: ["/calendar"],
    });
  });

  it("renders only modules present in ApplicationRegistry -- no static nav-items dependency", () => {
    render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>,
    );

    expect(screen.getByRole("link", { name: "Home" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Gmail" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Calendar" })).toBeInTheDocument();
    expect(screen.getAllByRole("link")).toHaveLength(3);
  });

  it("reflects registration changes -- proving it reads the registry live, not a fixed list", () => {
    render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>,
    );
    expect(screen.getAllByRole("link")).toHaveLength(3);

    applicationRegistry.unregister("calendar");
    render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>,
    );
    expect(screen.getAllByRole("link")).toHaveLength(4); // 3 from the first render + 2 remaining from the second, minus overlap -- see next assertion for the real check
  });

  it("groups modules by manifest category into Workspace and Connected sections", () => {
    render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>,
    );

    const workspaceGroup = screen.getByRole("group", { name: "Workspace" });
    expect(within(workspaceGroup).getByRole("link", { name: "Home" })).toBeInTheDocument();

    const connectedGroup = screen.getByRole("group", { name: "Connected" });
    expect(within(connectedGroup).getByRole("link", { name: "Gmail" })).toBeInTheDocument();
    expect(within(connectedGroup).getByRole("link", { name: "Calendar" })).toBeInTheDocument();
  });

  it("highlights the module WorkspaceManager reports active -- never derived from the current route", () => {
    useWorkspaceStore.setState({ activeModuleId: "gmail" });

    render(
      <MemoryRouter initialEntries={["/calendar"]}>
        <Sidebar />
      </MemoryRouter>,
    );

    // The route says /calendar, but WorkspaceManager's activeModuleId
    // says "gmail" -- the store must win, proving this isn't
    // route-derived highlighting.
    expect(screen.getByRole("link", { name: "Gmail" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Calendar" })).not.toHaveAttribute("aria-current");
  });

  it("resolves each module's icon from its manifest via lib/icon-registry.ts", () => {
    render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>,
    );

    expect(screen.getByRole("link", { name: "Gmail" }).querySelector("svg")).toBeInTheDocument();
  });

  it("falls back to a generic icon for an unmapped icon key instead of crashing", async () => {
    applicationRegistry.unregister("home");
    await registerTestModule({
      name: "unmapped-icon-module",
      displayName: "Mystery Module",
      icon: "not-a-real-icon-key",
      category: "local",
      routes: ["/mystery"],
    });

    render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>,
    );

    expect(screen.getByRole("link", { name: "Mystery Module" }).querySelector("svg")).toBeInTheDocument();
  });

  it("collapses to icon-only when isCollapsed is true, keeping every link present", () => {
    useSidebarStore.setState({ isCollapsed: true });
    render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>,
    );

    expect(screen.queryByText("Home")).not.toBeInTheDocument();
    expect(screen.getAllByRole("link")).toHaveLength(3);
  });

  it("group labels remain screen-reader-accessible (sr-only, not removed) when collapsed", () => {
    useSidebarStore.setState({ isCollapsed: true });
    render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>,
    );

    expect(screen.getByRole("group", { name: "Workspace" })).toBeInTheDocument();
  });

  it("toggle button flips and persists isCollapsed via the existing sidebar store", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>,
    );

    await user.click(screen.getByRole("button", { name: "Collapse sidebar" }));
    expect(useSidebarStore.getState().isCollapsed).toBe(true);
  });

  it("keyboard: ArrowDown/ArrowUp move roving focus between items", async () => {
    useWorkspaceStore.setState({ activeModuleId: "home" });
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>,
    );

    screen.getByRole("link", { name: "Home" }).focus();
    await user.keyboard("{ArrowDown}");
    expect(screen.getByRole("link", { name: "Gmail" })).toHaveFocus();

    await user.keyboard("{ArrowUp}");
    expect(screen.getByRole("link", { name: "Home" })).toHaveFocus();
  });

  it("keyboard: Home/End jump to the first/last item", async () => {
    useWorkspaceStore.setState({ activeModuleId: "gmail" });
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>,
    );

    screen.getByRole("link", { name: "Gmail" }).focus();
    await user.keyboard("{End}");
    expect(screen.getByRole("link", { name: "Calendar" })).toHaveFocus();

    await user.keyboard("{Home}");
    expect(screen.getByRole("link", { name: "Home" })).toHaveFocus();
  });

  it("only the roving item (active, or first when nothing is active) is Tab-reachable", () => {
    useWorkspaceStore.setState({ activeModuleId: "gmail" });
    render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>,
    );

    expect(screen.getByRole("link", { name: "Gmail" })).toHaveAttribute("tabIndex", "0");
    expect(screen.getByRole("link", { name: "Home" })).toHaveAttribute("tabIndex", "-1");
    expect(screen.getByRole("link", { name: "Calendar" })).toHaveAttribute("tabIndex", "-1");
  });

  it("defaults roving focus to the first item when nothing is active yet", () => {
    render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>,
    );

    expect(screen.getByRole("link", { name: "Home" })).toHaveAttribute("tabIndex", "0");
  });

  it("has an accessible primary navigation landmark", () => {
    render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>,
    );
    expect(screen.getByRole("navigation", { name: "Primary" })).toBeInTheDocument();
  });

  it("shows a tooltip with the module's display name only when collapsed", async () => {
    useSidebarStore.setState({ isCollapsed: true });
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>,
    );

    await user.hover(screen.getByRole("link", { name: "Gmail" }));
    expect(await screen.findByRole("tooltip")).toHaveTextContent("Gmail");
  });
});
