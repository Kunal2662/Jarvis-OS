import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { WorkspaceBinding } from "@/components/workspace/workspace-binding";
import { setApiBaseUrl } from "@/services/api/client";
import { useConnectionStore } from "@/stores/connection.store";
import {
  createDefaultLayout,
  selectActiveWorkspace,
  useWorkspaceLayoutStore,
} from "@/stores/workspace-layout.store";

/**
 * M8 Phase 5 shipped five dashboard widgets whose empty state reads
 * "Bind this workspace to a JARVIS workspace to see its tasks" — and the
 * Phase 7 pass found no control anywhere in the app that could do it.
 * `bindBackendWorkspace` had only tests calling it and `workspacesApi`
 * had no caller at all. These tests cover the control that closed that
 * dead end.
 */

const BASE = "http://127.0.0.1:8000/api/v1";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const WORKSPACES = {
  data: [
    { id: "ws-1", name: "Research", description: "", status: "active", created_at: null, updated_at: null },
    { id: "ws-2", name: "Personal", description: "", status: "active", created_at: null, updated_at: null },
  ],
  meta: { count: 2, limit: 50, offset: 0, has_more: false },
};

let fetchMock: ReturnType<typeof vi.fn>;

const active = () => selectActiveWorkspace(useWorkspaceLayoutStore.getState());

function setLive(live: boolean) {
  useConnectionStore.setState({
    state: live ? "ready" : "unreachable",
    detail: "",
    socket: live ? "connected" : "offline",
    authenticated: live,
    hasAttempted: true,
  });
}

beforeEach(() => {
  setApiBaseUrl(BASE);
  fetchMock = vi.fn(() => Promise.resolve(jsonResponse(WORKSPACES)));
  vi.stubGlobal("fetch", fetchMock);
  const layout = createDefaultLayout("Default");
  useWorkspaceLayoutStore.setState({ workspaces: [layout], activeWorkspaceId: layout.id });
  setLive(true);
});

afterEach(() => vi.unstubAllGlobals());

describe("WorkspaceBinding", () => {
  it("says there is no data source until one is chosen", async () => {
    render(<WorkspaceBinding />);
    expect(await screen.findByText("No data source")).toBeInTheDocument();
  });

  it("lists the backend's real workspaces", async () => {
    const user = userEvent.setup();
    render(<WorkspaceBinding />);

    await user.click(screen.getByRole("button"));

    expect(await screen.findByText("Research")).toBeInTheDocument();
    expect(screen.getByText("Personal")).toBeInTheDocument();
    expect(fetchMock.mock.calls[0][0]).toContain(`${BASE}/workspaces`);
  });

  it("binds the layout to the chosen workspace", async () => {
    const user = userEvent.setup();
    render(<WorkspaceBinding />);

    await user.click(screen.getByRole("button"));
    await user.click(await screen.findByText("Research"));

    expect(active().backendWorkspaceId).toBe("ws-1");
  });

  it("stores only the id, never the backend's data", async () => {
    const user = userEvent.setup();
    render(<WorkspaceBinding />);
    await user.click(screen.getByRole("button"));
    await user.click(await screen.findByText("Research"));

    // A copied name would go stale the moment it is renamed on the
    // backend. The layout holds a foreign key and nothing else.
    expect(JSON.stringify(active())).not.toContain("Research");
  });

  it("shows the bound workspace's current name", async () => {
    useWorkspaceLayoutStore.getState().bindBackendWorkspace(active().id, "ws-2");

    render(<WorkspaceBinding />);

    expect(await screen.findByText("Personal")).toBeInTheDocument();
  });

  it("says so when bound to a workspace the backend no longer has", async () => {
    // A layout imported from another install, or a workspace deleted
    // elsewhere. Rendering a blank name would look like a bug.
    useWorkspaceLayoutStore.getState().bindBackendWorkspace(active().id, "ws-gone");

    render(<WorkspaceBinding />);

    expect(await screen.findByText("Unavailable")).toBeInTheDocument();
  });

  it("unlinks", async () => {
    const user = userEvent.setup();
    useWorkspaceLayoutStore.getState().bindBackendWorkspace(active().id, "ws-1");
    render(<WorkspaceBinding />);

    await user.click(await screen.findByRole("button"));
    await user.click(await screen.findByText("Unlink"));

    expect(active().backendWorkspaceId).toBeNull();
  });

  it("offers no unlink when nothing is bound", async () => {
    const user = userEvent.setup();
    render(<WorkspaceBinding />);

    await user.click(screen.getByRole("button"));
    await screen.findByText("Research");

    expect(screen.queryByText("Unlink")).not.toBeInTheDocument();
  });

  it("says the backend is unreachable rather than showing an empty list", async () => {
    const user = userEvent.setup();
    setLive(false);

    render(<WorkspaceBinding />);
    await user.click(screen.getByRole("button"));

    expect(await screen.findByText("Backend unreachable")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("distinguishes no workspaces from a failed load", async () => {
    const user = userEvent.setup();
    fetchMock.mockResolvedValue(jsonResponse({ data: [], meta: { count: 0, limit: 50, offset: 0, has_more: false } }));

    render(<WorkspaceBinding />);
    await user.click(screen.getByRole("button"));

    expect(await screen.findByText("No JARVIS workspaces yet")).toBeInTheDocument();
  });
});
