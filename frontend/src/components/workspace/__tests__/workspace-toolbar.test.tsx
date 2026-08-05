import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { WorkspaceToolbar } from "@/components/workspace/workspace-toolbar";
import { panelRegistry, resetPanelRegistryForTesting } from "@/core/panel-registry";
import {
  createDefaultLayout,
  SCHEMA_VERSION,
  selectActiveWorkspace,
  useWorkspaceLayoutStore,
} from "@/stores/workspace-layout.store";

vi.mock("sonner", () => ({
  toast: { error: vi.fn(), warning: vi.fn(), success: vi.fn() },
}));

const active = () => selectActiveWorkspace(useWorkspaceLayoutStore.getState());
const store = () => useWorkspaceLayoutStore.getState();

beforeEach(() => {
  vi.spyOn(console, "error").mockImplementation(() => {});
  resetPanelRegistryForTesting();
  panelRegistry.register({
    id: "home.dashboard",
    moduleId: "home",
    title: "Dashboard",
    icon: "home",
    defaultZone: "main",
    render: () => null,
  });
  panelRegistry.register({
    id: "core.activity",
    moduleId: "core",
    title: "Activity",
    icon: "activity",
    defaultZone: "right",
    render: () => null,
  });

  const workspace = createDefaultLayout("Default");
  useWorkspaceLayoutStore.setState({ workspaces: [workspace], activeWorkspaceId: workspace.id });
});

async function openWorkspaceMenu(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: /Default/ }));
}

describe("workspace management", () => {
  it("names the active workspace", () => {
    render(<WorkspaceToolbar />);
    expect(screen.getByRole("button", { name: /Default/ })).toBeInTheDocument();
  });

  it("creates a workspace", async () => {
    const user = userEvent.setup();
    render(<WorkspaceToolbar />);

    await openWorkspaceMenu(user);
    await user.click(await screen.findByText("New workspace"));

    expect(store().workspaces).toHaveLength(2);
  });

  it("renames through an inline field", async () => {
    const user = userEvent.setup();
    render(<WorkspaceToolbar />);

    await openWorkspaceMenu(user);
    await user.click(await screen.findByText(/Rename/));

    const field = await screen.findByLabelText("Workspace name");
    await user.clear(field);
    await user.type(field, "Research{Enter}");

    expect(active().name).toBe("Research");
  });

  it("abandons a rename on Escape", async () => {
    const user = userEvent.setup();
    render(<WorkspaceToolbar />);

    await openWorkspaceMenu(user);
    await user.click(await screen.findByText(/Rename/));
    const field = await screen.findByLabelText("Workspace name");
    await user.clear(field);
    await user.type(field, "Discarded{Escape}");

    expect(active().name).toBe("Default");
  });

  it("duplicates", async () => {
    const user = userEvent.setup();
    render(<WorkspaceToolbar />);

    await openWorkspaceMenu(user);
    await user.click(await screen.findByText("Duplicate"));

    expect(store().workspaces).toHaveLength(2);
    expect(active().name).toBe("Default copy");
  });

  it("resets the layout", async () => {
    const user = userEvent.setup();
    store().openPanel("core.activity");
    render(<WorkspaceToolbar />);

    await openWorkspaceMenu(user);
    await user.click(await screen.findByText("Reset layout"));

    expect(active().panels.map((p) => p.panelId)).toEqual(["home.dashboard"]);
  });

  it("disables deleting the only workspace", async () => {
    const user = userEvent.setup();
    render(<WorkspaceToolbar />);

    await openWorkspaceMenu(user);

    expect(await screen.findByText("Delete workspace")).toHaveAttribute("aria-disabled", "true");
  });

  it("switches between workspaces", async () => {
    const user = userEvent.setup();
    const secondId = store().createWorkspace("Second");
    render(<WorkspaceToolbar />);

    await user.click(screen.getByRole("button", { name: /Second/ }));
    await user.click(await screen.findByText("Default"));

    expect(store().activeWorkspaceId).not.toBe(secondId);
  });
});

describe("panel menu", () => {
  it("lists every registered panel", async () => {
    const user = userEvent.setup();
    render(<WorkspaceToolbar />);

    await user.click(screen.getByRole("button", { name: "Panel" }));

    expect(await screen.findByText("Activity")).toBeInTheDocument();
  });

  it("opens a panel", async () => {
    const user = userEvent.setup();
    render(<WorkspaceToolbar />);

    await user.click(screen.getByRole("button", { name: "Panel" }));
    await user.click(await screen.findByText("Activity"));

    expect(active().panels.map((p) => p.panelId)).toContain("core.activity");
  });

  it("disables an already-open panel instead of hiding it", async () => {
    const user = userEvent.setup();
    render(<WorkspaceToolbar />);

    await user.click(screen.getByRole("button", { name: "Panel" }));

    // `home.dashboard` is in the default layout.
    expect(await screen.findByText("Dashboard")).toHaveAttribute("aria-disabled", "true");
  });
});

describe("export", () => {
  it("downloads the standard envelope under a slugged filename", async () => {
    const user = userEvent.setup();
    const createObjectURL = vi.fn(() => "blob:workspace");
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", { ...URL, createObjectURL, revokeObjectURL });

    const clicked: HTMLAnchorElement[] = [];
    const realCreate = document.createElement.bind(document);
    vi.spyOn(document, "createElement").mockImplementation((tag: string) => {
      const element = realCreate(tag);
      if (tag === "a") {
        vi.spyOn(element as HTMLAnchorElement, "click").mockImplementation(() => {
          clicked.push(element as HTMLAnchorElement);
        });
      }
      return element;
    });

    store().renameWorkspace(active().id, "My Research Space");
    render(<WorkspaceToolbar />);
    await user.click(screen.getByRole("button", { name: /My Research Space/ }));
    await user.click(await screen.findByText("Export…"));

    expect(createObjectURL).toHaveBeenCalled();
    expect(clicked[0]?.download).toBe("my-research-space.jarvis-workspace.json");
    // Not leaking the object URL -- a long session would otherwise hold
    // every export it ever made.
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:workspace");

    vi.mocked(document.createElement).mockRestore();
    vi.unstubAllGlobals();
  });

  it("produces a document the store can import back", () => {
    const json = store().exportWorkspace(active().id);
    expect(JSON.parse(json).schemaVersion).toBe(SCHEMA_VERSION);
    expect(() => store().importWorkspace(json)).not.toThrow();
  });
});
