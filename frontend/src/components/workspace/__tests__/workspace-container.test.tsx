import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { WorkspaceContainer } from "@/components/workspace/workspace-container";
import { panelRegistry, resetPanelRegistryForTesting } from "@/core/panel-registry";
import {
  createDefaultLayout,
  panelsInZone,
  selectActiveWorkspace,
  useWorkspaceLayoutStore,
} from "@/stores/workspace-layout.store";

/**
 * The container is where the store's model becomes a layout, so these
 * tests drive it the way a user does -- through the rendered chrome --
 * rather than asserting store calls. A panel that is in the store but
 * not on screen is the failure worth catching.
 */

// jsdom has no matchMedia; the workspace asks for the compact breakpoint
// on every render. Desktop by default, overridden per test.
let compact = false;

beforeEach(() => {
  vi.stubGlobal(
    "matchMedia",
    vi.fn((query: string) => ({
      matches: query.includes("max-width") ? compact : !compact,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })),
  );
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      disconnect() {}
    },
  );

  compact = false;
  resetPanelRegistryForTesting();

  panelRegistry.register({
    id: "home.dashboard",
    moduleId: "home",
    title: "Dashboard",
    icon: "home",
    defaultZone: "main",
    render: () => <p>dashboard content</p>,
    hideOnCompact: true,
  });
  panelRegistry.register({
    id: "core.notifications",
    moduleId: "core",
    title: "Notifications",
    icon: "bell",
    defaultZone: "right",
    render: () => <p>notification content</p>,
  });

  const workspace = createDefaultLayout("Default");
  useWorkspaceLayoutStore.setState({ workspaces: [workspace], activeWorkspaceId: workspace.id });
});

const active = () => selectActiveWorkspace(useWorkspaceLayoutStore.getState());

describe("rendering", () => {
  it("renders the panels the active workspace holds", async () => {
    render(<WorkspaceContainer />);
    expect(await screen.findByText("dashboard content")).toBeInTheDocument();
  });

  it("renders a zone only when it has panels", async () => {
    render(<WorkspaceContainer />);
    await screen.findByText("dashboard content");

    expect(document.querySelector('[data-zone="right"]')).toBeNull();

    useWorkspaceLayoutStore.getState().openPanel("core.notifications");
    expect(await screen.findByText("notification content")).toBeInTheDocument();
    expect(document.querySelector('[data-zone="right"]')).not.toBeNull();
  });

  it("shows an empty state when the centre holds nothing", async () => {
    const only = active().panels[0];
    useWorkspaceLayoutStore.getState().closePanel(only.instanceId);

    render(<WorkspaceContainer />);

    expect(await screen.findByText("Empty workspace")).toBeInTheDocument();
  });

  it("distinguishes an empty centre from a wholly empty workspace", async () => {
    const only = active().panels[0];
    useWorkspaceLayoutStore.getState().closePanel(only.instanceId);
    useWorkspaceLayoutStore.getState().openPanel("core.notifications");

    render(<WorkspaceContainer />);

    expect(await screen.findByText("Nothing in the centre")).toBeInTheDocument();
  });
});

describe("panel operations", () => {
  it("closes a panel from its own chrome", async () => {
    const user = userEvent.setup();
    render(<WorkspaceContainer />);
    await screen.findByText("dashboard content");

    await user.click(screen.getByRole("button", { name: "Close Dashboard" }));

    expect(screen.queryByText("dashboard content")).not.toBeInTheDocument();
    expect(active().panels).toHaveLength(0);
  });

  it("collapses a panel, hiding its content but keeping its title bar", async () => {
    const user = userEvent.setup();
    render(<WorkspaceContainer />);
    await screen.findByText("dashboard content");

    await user.click(screen.getByRole("button", { name: "Collapse Dashboard" }));

    expect(screen.queryByText("dashboard content")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Expand Dashboard" })).toBeInTheDocument();
  });

  it("moves a panel to another zone from its menu", async () => {
    const user = userEvent.setup();
    render(<WorkspaceContainer />);
    await screen.findByText("dashboard content");

    await user.click(screen.getByRole("button", { name: "Dashboard panel options" }));
    await user.click(await screen.findByText("Move to right"));

    expect(panelsInZone(active(), "right").map((p) => p.panelId)).toEqual(["home.dashboard"]);
  });

  it("detaches a panel into the floating layer", async () => {
    const user = userEvent.setup();
    render(<WorkspaceContainer />);
    await screen.findByText("dashboard content");

    await user.click(screen.getByRole("button", { name: "Dashboard panel options" }));
    await user.click(await screen.findByText("Detach"));

    expect(active().panels[0].placement).toBe("detached");
    const layer = screen.getByLabelText("Detached panels");
    expect(within(layer).getByRole("region", { name: "Dashboard" })).toBeInTheDocument();
  });
});

describe("splitters", () => {
  it("exposes each zone divider as a keyboard-operable separator", async () => {
    const user = userEvent.setup();
    useWorkspaceLayoutStore.getState().openPanel("core.notifications");
    render(<WorkspaceContainer />);
    await screen.findByText("notification content");

    const splitter = screen.getByRole("separator", { name: "Resize right panels" });
    const before = active().zoneSizes.right;

    splitter.focus();
    await user.keyboard("{ArrowLeft}");

    // Right rail is inverted -- ArrowLeft grows it.
    expect(active().zoneSizes.right).toBeGreaterThan(before);
  });

  it("clamps at the maximum with End", async () => {
    const user = userEvent.setup();
    useWorkspaceLayoutStore.getState().openPanel("core.notifications");
    render(<WorkspaceContainer />);
    await screen.findByText("notification content");

    const splitter = screen.getByRole("separator", { name: "Resize right panels" });
    splitter.focus();
    await user.keyboard("{End}");

    expect(active().zoneSizes.right).toBeCloseTo(0.45, 5);
  });
});

describe("responsive layout", () => {
  it("drops the rails at compact widths", async () => {
    useWorkspaceLayoutStore.getState().openPanel("core.notifications");
    compact = true;

    render(<WorkspaceContainer />);

    // The panel is still in the workspace -- it is the *layout* that
    // drops the rail, not the store that loses the panel.
    expect(document.querySelector('[data-zone="right"]')).toBeNull();
    expect(panelsInZone(active(), "right")).toHaveLength(1);
  });

  it("hides a panel marked hideOnCompact rather than squeezing it", async () => {
    compact = true;
    render(<WorkspaceContainer />);

    expect(screen.queryByText("dashboard content")).not.toBeInTheDocument();
    expect(await screen.findByText("Empty workspace")).toBeInTheDocument();
  });
});
