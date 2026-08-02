import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";
import { Sidebar } from "@/components/layout/sidebar";
import { applicationRegistry } from "@/core/application-registry";
import { TestApplication } from "@/core/test-utils/test-application";
import { useModuleEnablementStore } from "@/stores/module-enablement.store";
import { useSidebarStore } from "@/stores/sidebar.store";
import { useWorkspaceStore } from "@/stores/workspace.store";

interface TestModuleOptions {
  name: string;
  displayName: string;
  icon: string;
  routes: string[];
  isCore?: boolean;
  parentGroup?: string;
}

function registerTestModule(options: TestModuleOptions): Promise<void> {
  return new TestApplication(options).initialize();
}

async function registerMinimalTaxonomy(): Promise<void> {
  await registerTestModule({ name: "home", displayName: "Dashboard", icon: "home", routes: ["/"], isCore: true });
  await registerTestModule({
    name: "chat",
    displayName: "Conversation",
    icon: "sparkles",
    routes: ["/chat"],
    isCore: true,
    parentGroup: "ai",
  });
  await registerTestModule({
    name: "voice",
    displayName: "Voice",
    icon: "mic",
    routes: ["/voice"],
    isCore: true,
    parentGroup: "ai",
  });
  await registerTestModule({ name: "settings", displayName: "Settings", icon: "settings", routes: ["/settings"], isCore: true });
  // Optional -- not enabled by default.
  await registerTestModule({ name: "gmail", displayName: "Gmail", icon: "mail", routes: ["/gmail"] });
}

describe("Sidebar", () => {
  beforeEach(() => {
    for (const module of applicationRegistry.getAll()) {
      applicationRegistry.unregister(module.manifest.name);
    }
    useSidebarStore.setState({ isCollapsed: false, expandedGroupIds: ["ai"] });
    useModuleEnablementStore.setState({ enabledModuleIds: [] });
    useWorkspaceStore.setState({ activeModuleId: null });
  });

  describe("registry + enablement gating", () => {
    it("renders core modules by default, with optional modules hidden", async () => {
      await registerMinimalTaxonomy();
      render(
        <MemoryRouter>
          <Sidebar />
        </MemoryRouter>,
      );

      expect(screen.getByRole("link", { name: "Dashboard" })).toBeInTheDocument();
      expect(screen.getByRole("link", { name: "Settings" })).toBeInTheDocument();
      expect(screen.queryByRole("link", { name: "Gmail" })).not.toBeInTheDocument();
    });

    it("shows an optional module only once both registered and enabled", async () => {
      await registerMinimalTaxonomy();
      const { rerender } = render(
        <MemoryRouter>
          <Sidebar />
        </MemoryRouter>,
      );
      expect(screen.queryByRole("link", { name: "Gmail" })).not.toBeInTheDocument();

      useModuleEnablementStore.getState().enableModule("gmail");
      rerender(
        <MemoryRouter>
          <Sidebar />
        </MemoryRouter>,
      );
      expect(screen.getByRole("link", { name: "Gmail" })).toBeInTheDocument();
    });

    it("enabled optional modules render under an 'Installed Modules' group", async () => {
      await registerMinimalTaxonomy();
      useModuleEnablementStore.setState({ enabledModuleIds: ["gmail"] });
      render(
        <MemoryRouter>
          <Sidebar />
        </MemoryRouter>,
      );

      const installedGroup = screen.getByRole("group", { name: "Installed Modules" });
      expect(within(installedGroup).getByRole("link", { name: "Gmail" })).toBeInTheDocument();
    });

    it("a disabled core module is impossible to express -- isCore always wins over the enablement store", async () => {
      await registerMinimalTaxonomy();
      // Explicitly do NOT enable "home"/"settings" -- isModuleEnabled()
      // must still report them enabled because isCore short-circuits.
      render(
        <MemoryRouter>
          <Sidebar />
        </MemoryRouter>,
      );

      expect(screen.getByRole("link", { name: "Dashboard" })).toBeInTheDocument();
      expect(screen.getByRole("link", { name: "Settings" })).toBeInTheDocument();
    });
  });

  describe("nested AI group", () => {
    it("groups modules sharing a parentGroup under a synthesized, labeled parent", async () => {
      await registerMinimalTaxonomy();
      render(
        <MemoryRouter>
          <Sidebar />
        </MemoryRouter>,
      );

      expect(screen.getByRole("button", { name: "AI" })).toBeInTheDocument();
      expect(screen.getByRole("link", { name: "Conversation" })).toBeInTheDocument();
      expect(screen.getByRole("link", { name: "Voice" })).toBeInTheDocument();
    });

    it("collapsing the AI group hides its children but keeps the header", async () => {
      const user = userEvent.setup();
      await registerMinimalTaxonomy();
      render(
        <MemoryRouter>
          <Sidebar />
        </MemoryRouter>,
      );

      await user.click(screen.getByRole("button", { name: "AI" }));

      expect(screen.getByRole("button", { name: "AI" })).toHaveAttribute("aria-expanded", "false");
      expect(screen.queryByRole("link", { name: "Conversation" })).not.toBeInTheDocument();
    });

    it("auto-expands a collapsed group that contains the active module", async () => {
      await registerMinimalTaxonomy();
      useSidebarStore.setState({ expandedGroupIds: [] }); // user collapsed "ai"
      useWorkspaceStore.setState({ activeModuleId: "voice" });

      render(
        <MemoryRouter>
          <Sidebar />
        </MemoryRouter>,
      );

      expect(screen.getByRole("link", { name: "Voice" })).toBeInTheDocument();
      expect(screen.getByRole("link", { name: "Voice" })).toHaveAttribute("aria-current", "page");
    });

    it("collapsed (icon-only) sidebar flattens group children to plain icons, ignoring expand state", async () => {
      await registerMinimalTaxonomy();
      useSidebarStore.setState({ isCollapsed: true, expandedGroupIds: [] });

      render(
        <MemoryRouter>
          <Sidebar />
        </MemoryRouter>,
      );

      expect(screen.getByRole("link", { name: "Conversation" })).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "AI" })).not.toBeInTheDocument();
    });
  });

  describe("active state (WorkspaceManager, not routing)", () => {
    it("highlights the module WorkspaceManager reports active, never derived from the route", async () => {
      await registerMinimalTaxonomy();
      useWorkspaceStore.setState({ activeModuleId: "chat" });

      render(
        <MemoryRouter initialEntries={["/settings"]}>
          <Sidebar />
        </MemoryRouter>,
      );

      expect(screen.getByRole("link", { name: "Conversation" })).toHaveAttribute("aria-current", "page");
      expect(screen.getByRole("link", { name: "Settings" })).not.toHaveAttribute("aria-current");
    });
  });

  describe("collapse / expand", () => {
    it("collapses to icon-only, keeping every visible link present", async () => {
      await registerMinimalTaxonomy();
      useSidebarStore.setState({ isCollapsed: true });
      render(
        <MemoryRouter>
          <Sidebar />
        </MemoryRouter>,
      );

      expect(screen.queryByText("Dashboard")).not.toBeInTheDocument();
      expect(screen.getByRole("link", { name: "Dashboard" })).toBeInTheDocument();
    });

    it("toggle button flips and persists isCollapsed via the existing sidebar store", async () => {
      await registerMinimalTaxonomy();
      const user = userEvent.setup();
      render(
        <MemoryRouter>
          <Sidebar />
        </MemoryRouter>,
      );

      await user.click(screen.getByRole("button", { name: "Collapse sidebar" }));
      expect(useSidebarStore.getState().isCollapsed).toBe(true);
    });

    it("shows a tooltip with the module's display name only when collapsed", async () => {
      await registerMinimalTaxonomy();
      useSidebarStore.setState({ isCollapsed: true });
      const user = userEvent.setup();
      render(
        <MemoryRouter>
          <Sidebar />
        </MemoryRouter>,
      );

      await user.hover(screen.getByRole("link", { name: "Dashboard" }));
      expect(await screen.findByRole("tooltip")).toHaveTextContent("Dashboard");
    });
  });

  describe("keyboard navigation", () => {
    it("ArrowDown moves roving focus, skipping into an expanded group's children", async () => {
      useWorkspaceStore.setState({ activeModuleId: "home" });
      await registerMinimalTaxonomy();
      const user = userEvent.setup();
      render(
        <MemoryRouter>
          <Sidebar />
        </MemoryRouter>,
      );

      screen.getByRole("link", { name: "Dashboard" }).focus();
      await user.keyboard("{ArrowDown}"); // -> AI group header
      expect(screen.getByRole("button", { name: "AI" })).toHaveFocus();

      await user.keyboard("{ArrowDown}"); // -> Conversation (AI expanded by default)
      expect(screen.getByRole("link", { name: "Conversation" })).toHaveFocus();
    });

    it("ArrowDown skips a collapsed group's hidden children entirely", async () => {
      useWorkspaceStore.setState({ activeModuleId: "home" });
      await registerMinimalTaxonomy();
      useSidebarStore.setState({ expandedGroupIds: [] });
      const user = userEvent.setup();
      render(
        <MemoryRouter>
          <Sidebar />
        </MemoryRouter>,
      );

      screen.getByRole("link", { name: "Dashboard" }).focus();
      await user.keyboard("{ArrowDown}"); // -> AI group header
      await user.keyboard("{ArrowDown}"); // children hidden -> Settings, not Conversation
      expect(screen.getByRole("link", { name: "Settings" })).toHaveFocus();
    });

    it("Home/End jump to the first/last visible entry", async () => {
      useWorkspaceStore.setState({ activeModuleId: "chat" });
      await registerMinimalTaxonomy();
      useModuleEnablementStore.setState({ enabledModuleIds: ["gmail"] });
      const user = userEvent.setup();
      render(
        <MemoryRouter>
          <Sidebar />
        </MemoryRouter>,
      );

      screen.getByRole("link", { name: "Conversation" }).focus();
      await user.keyboard("{End}");
      expect(screen.getByRole("link", { name: "Gmail" })).toHaveFocus();

      await user.keyboard("{Home}");
      expect(screen.getByRole("link", { name: "Dashboard" })).toHaveFocus();
    });

    it("Space toggles a focused group header", async () => {
      useWorkspaceStore.setState({ activeModuleId: "home" });
      await registerMinimalTaxonomy();
      const user = userEvent.setup();
      render(
        <MemoryRouter>
          <Sidebar />
        </MemoryRouter>,
      );

      screen.getByRole("button", { name: "AI" }).focus();
      await user.keyboard(" ");
      expect(screen.getByRole("button", { name: "AI" })).toHaveAttribute("aria-expanded", "false");
    });
  });

  describe("accessibility", () => {
    it("has an accessible primary navigation landmark", async () => {
      await registerMinimalTaxonomy();
      render(
        <MemoryRouter>
          <Sidebar />
        </MemoryRouter>,
      );
      expect(screen.getByRole("navigation", { name: "Primary" })).toBeInTheDocument();
    });

    it("the AI group header exposes aria-expanded reflecting its real state", async () => {
      await registerMinimalTaxonomy();
      render(
        <MemoryRouter>
          <Sidebar />
        </MemoryRouter>,
      );
      expect(screen.getByRole("button", { name: "AI" })).toHaveAttribute("aria-expanded", "true");
    });
  });
});
