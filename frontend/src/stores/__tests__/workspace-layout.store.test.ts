import { beforeEach, describe, expect, it } from "vitest";
import { panelRegistry, resetPanelRegistryForTesting } from "@/core/panel-registry";
import {
  createDefaultLayout,
  MIN_PANEL_FRACTION,
  panelsInZone,
  SCHEMA_VERSION,
  selectActiveWorkspace,
  useWorkspaceLayoutStore,
  WorkspaceImportError,
} from "@/stores/workspace-layout.store";

/**
 * The layout store is the whole Universal Workspace Framework's source
 * of truth, so these tests pin the invariants the rendering layer
 * assumes: a zone's sizes always sum to 1, orders are always dense, and
 * a workspace can never be deleted out from under the app.
 */

function stubPanel(id: string, defaultZone: "left" | "main" | "right" | "bottom" = "main") {
  panelRegistry.register({
    id,
    moduleId: "test",
    title: id,
    icon: "square",
    defaultZone,
    render: () => null,
  });
}

function reset() {
  resetPanelRegistryForTesting();
  stubPanel("home.dashboard", "main");
  stubPanel("test.alpha", "main");
  stubPanel("test.beta", "right");
  stubPanel("test.gamma", "bottom");

  const workspace = createDefaultLayout("Default");
  useWorkspaceLayoutStore.setState({
    workspaces: [workspace],
    activeWorkspaceId: workspace.id,
  });
}

const store = () => useWorkspaceLayoutStore.getState();
const active = () => selectActiveWorkspace(useWorkspaceLayoutStore.getState());

beforeEach(reset);

describe("workspace lifecycle", () => {
  it("starts with one workspace holding the dashboard", () => {
    expect(store().workspaces).toHaveLength(1);
    expect(panelsInZone(active(), "main").map((p) => p.panelId)).toEqual(["home.dashboard"]);
  });

  it("creates and activates a new workspace", () => {
    const id = store().createWorkspace("Research");

    expect(store().workspaces).toHaveLength(2);
    expect(store().activeWorkspaceId).toBe(id);
    expect(active().name).toBe("Research");
  });

  it("renames, ignoring a blank name", () => {
    store().renameWorkspace(active().id, "  Renamed  ");
    expect(active().name).toBe("Renamed");

    store().renameWorkspace(active().id, "   ");
    expect(active().name).toBe("Renamed");
  });

  it("refuses to delete the last workspace", () => {
    // An app with no workspace has nothing to render, so this is a
    // guard rather than a preference.
    store().deleteWorkspace(active().id);
    expect(store().workspaces).toHaveLength(1);
  });

  it("moves to a surviving workspace when the active one is deleted", () => {
    const first = active().id;
    store().createWorkspace("Second");

    store().deleteWorkspace(first);

    expect(store().workspaces).toHaveLength(1);
    expect(store().activeWorkspaceId).toBe(store().workspaces[0].id);
  });

  it("duplicates with fresh panel instance ids", () => {
    const sourceIds = active().panels.map((p) => p.instanceId);
    const copyId = store().duplicateWorkspace(active().id);

    const copy = store().workspaces.find((w) => w.id === copyId);
    expect(copy?.name).toBe("Default copy");
    // Sharing an instance id across two workspaces would make every
    // panel action ambiguous.
    for (const panel of copy?.panels ?? []) {
      expect(sourceIds).not.toContain(panel.instanceId);
    }
  });

  it("resets the layout while keeping identity and backend binding", () => {
    const id = active().id;
    store().bindBackendWorkspace(id, "backend-ws-1");
    store().renameWorkspace(id, "Kept");
    store().openPanel("test.beta");

    store().resetWorkspace(id);

    expect(active().id).toBe(id);
    expect(active().name).toBe("Kept");
    expect(active().backendWorkspaceId).toBe("backend-ws-1");
    expect(active().panels.map((p) => p.panelId)).toEqual(["home.dashboard"]);
  });

  it("ignores an unknown workspace on switch", () => {
    const current = store().activeWorkspaceId;
    store().setActiveWorkspace("nope");
    expect(store().activeWorkspaceId).toBe(current);
  });
});

describe("backend workspace binding", () => {
  it("stores only the id, never backend data", () => {
    store().bindBackendWorkspace(active().id, "ws-42");
    expect(active().backendWorkspaceId).toBe("ws-42");

    // The layout holds a reference, not a copy -- there is no name,
    // project list or any other mirrored field to go stale.
    expect(Object.keys(active())).toEqual(
      expect.arrayContaining(["id", "name", "backendWorkspaceId", "panels", "zoneSizes"]),
    );
    expect(Object.keys(active())).toHaveLength(5);
  });

  it("unbinds with null", () => {
    store().bindBackendWorkspace(active().id, "ws-42");
    store().bindBackendWorkspace(active().id, null);
    expect(active().backendWorkspaceId).toBeNull();
  });
});

describe("panel lifecycle", () => {
  it("opens a panel into its registered default zone", () => {
    store().openPanel("test.beta");
    expect(panelsInZone(active(), "right").map((p) => p.panelId)).toEqual(["test.beta"]);
  });

  it("opens into an explicit zone when asked", () => {
    store().openPanel("test.beta", "left");
    expect(panelsInZone(active(), "left").map((p) => p.panelId)).toEqual(["test.beta"]);
  });

  it("returns null for a panel that is not registered", () => {
    expect(store().openPanel("nope.missing")).toBeNull();
  });

  it("focuses an already-open panel rather than opening a second", () => {
    const first = store().openPanel("test.beta");
    const second = store().openPanel("test.beta");

    expect(second).toBe(first);
    expect(active().panels.filter((p) => p.panelId === "test.beta")).toHaveLength(1);
  });

  it("expands a collapsed panel when re-opened", () => {
    const id = store().openPanel("test.beta");
    store().toggleCollapsed(id!);
    expect(active().panels.find((p) => p.instanceId === id)?.collapsed).toBe(true);

    store().openPanel("test.beta");
    expect(active().panels.find((p) => p.instanceId === id)?.collapsed).toBe(false);
  });

  it("closes a panel", () => {
    const id = store().openPanel("test.beta");
    store().closePanel(id!);
    expect(active().panels.find((p) => p.instanceId === id)).toBeUndefined();
  });

  it("moves a panel between zones", () => {
    const id = store().openPanel("test.beta");
    store().movePanel(id!, "bottom");

    expect(panelsInZone(active(), "right")).toHaveLength(0);
    expect(panelsInZone(active(), "bottom").map((p) => p.panelId)).toEqual(["test.beta"]);
  });
});

describe("zone normalisation", () => {
  it("keeps a zone's sizes summing to 1 as panels are added", () => {
    store().openPanel("test.alpha", "main");
    store().openPanel("test.beta", "main");

    const total = panelsInZone(active(), "main").reduce((sum, p) => sum + p.size, 0);
    expect(total).toBeCloseTo(1, 5);
  });

  it("re-normalises after a panel in the middle is closed", () => {
    store().openPanel("test.alpha", "main");
    const beta = store().openPanel("test.beta", "main");
    store().closePanel(beta!);

    const panels = panelsInZone(active(), "main");
    expect(panels.reduce((sum, p) => sum + p.size, 0)).toBeCloseTo(1, 5);
    // Dense, gap-free ordering -- the renderer indexes on it.
    expect(panels.map((p) => p.order)).toEqual([0, 1]);
  });

  it("resizes one panel and gives the remainder to its siblings", () => {
    store().openPanel("test.alpha", "main");
    const target = panelsInZone(active(), "main")[0];

    store().resizePanel(target.instanceId, 0.7);

    const panels = panelsInZone(active(), "main");
    expect(panels.find((p) => p.instanceId === target.instanceId)?.size).toBeCloseTo(0.7, 5);
    expect(panels.reduce((sum, p) => sum + p.size, 0)).toBeCloseTo(1, 5);
  });

  it("never resizes a panel below the minimum", () => {
    store().openPanel("test.alpha", "main");
    const target = panelsInZone(active(), "main")[0];

    store().resizePanel(target.instanceId, 0.001);

    expect(panelsInZone(active(), "main").find((p) => p.instanceId === target.instanceId)?.size)
      .toBeGreaterThanOrEqual(MIN_PANEL_FRACTION);
  });

  it("is a no-op when a panel is alone in its zone", () => {
    const only = panelsInZone(active(), "main")[0];
    store().resizePanel(only.instanceId, 0.3);
    // Nothing to take the remaining 70% -- so the panel keeps the zone.
    expect(panelsInZone(active(), "main")[0].size).toBeCloseTo(1, 5);
  });

  it("clamps a zone fraction to its allowed range", () => {
    store().resizeZone("left", 0.99);
    expect(active().zoneSizes.left).toBeLessThanOrEqual(0.45);

    store().resizeZone("left", 0.01);
    expect(active().zoneSizes.left).toBeGreaterThanOrEqual(0.12);
  });
});

describe("detach and restore", () => {
  it("detaches with a frame and remembers where it came from", () => {
    const id = store().openPanel("test.beta");
    store().detachPanel(id!);

    const panel = active().panels.find((p) => p.instanceId === id);
    expect(panel?.placement).toBe("detached");
    expect(panel?.frame).not.toBeNull();
    expect(panel?.restoreTo).toEqual({ placement: "right", order: 0 });
  });

  it("restores to where it was, not to the default zone", () => {
    const id = store().openPanel("test.beta", "left");
    store().detachPanel(id!);
    store().restorePanel(id!);

    // `test.beta`'s registered default is `right`; it was in `left`.
    expect(active().panels.find((p) => p.instanceId === id)?.placement).toBe("left");
  });

  it("clears the floating frame on restore", () => {
    const id = store().openPanel("test.beta");
    store().detachPanel(id!);
    store().restorePanel(id!);

    expect(active().panels.find((p) => p.instanceId === id)?.frame).toBeNull();
  });

  it("cascades so two detached panels do not stack exactly", () => {
    const a = store().openPanel("test.alpha");
    const b = store().openPanel("test.beta");
    store().detachPanel(a!);
    store().detachPanel(b!);

    const frames = active()
      .panels.filter((p) => p.placement === "detached")
      .map((p) => `${p.frame?.x},${p.frame?.y}`);
    expect(new Set(frames).size).toBe(2);
  });

  it("moves a detached panel's frame", () => {
    const id = store().openPanel("test.beta");
    store().detachPanel(id!);
    store().moveDetached(id!, { x: 300, y: 200 });

    const frame = active().panels.find((p) => p.instanceId === id)?.frame;
    expect(frame).toMatchObject({ x: 300, y: 200 });
  });
});

describe("export and import", () => {
  it("round-trips a workspace", () => {
    store().openPanel("test.beta");
    const sourceId = active().id;
    store().renameWorkspace(sourceId, "Exported");
    const json = store().exportWorkspace(sourceId);

    const importedId = store().importWorkspace(json);
    const imported = store().workspaces.find((w) => w.id === importedId);

    expect(imported?.name).toBe("Exported");
    expect(imported?.panels.map((p) => p.panelId).sort()).toEqual(
      ["home.dashboard", "test.beta"].sort(),
    );
    // A fresh id -- importing must not collide with the source, which is
    // still there alongside it.
    expect(importedId).not.toBe(sourceId);
    expect(store().workspaces).toHaveLength(2);
  });

  it("activates the imported workspace", () => {
    const json = store().exportWorkspace(active().id);
    const importedId = store().importWorkspace(json);
    expect(store().activeWorkspaceId).toBe(importedId);
  });

  it("exports the standard {schemaVersion, ...} envelope", () => {
    const parsed = JSON.parse(store().exportWorkspace(active().id));
    expect(parsed.schemaVersion).toBe(SCHEMA_VERSION);
    expect(parsed.workspace.name).toBe("Default");
  });

  it("rejects malformed JSON with a readable message", () => {
    expect(() => store().importWorkspace("{not json")).toThrow(WorkspaceImportError);
  });

  it("rejects a different schema version rather than guessing", () => {
    const json = JSON.stringify({ schemaVersion: 99, workspace: { name: "x", panels: [] } });
    expect(() => store().importWorkspace(json)).toThrow(/version/i);
  });

  it("rejects a document with no workspace", () => {
    const json = JSON.stringify({ schemaVersion: SCHEMA_VERSION, workspace: { name: "x" } });
    expect(() => store().importWorkspace(json)).toThrow(WorkspaceImportError);
  });

  it("drops panels this build does not have rather than failing the import", () => {
    const json = JSON.stringify({
      schemaVersion: SCHEMA_VERSION,
      workspace: {
        name: "From another build",
        backendWorkspaceId: null,
        zoneSizes: { left: 0.2, right: 0.2, bottom: 0.25 },
        panels: [
          { instanceId: "a", panelId: "test.alpha", placement: "main", order: 0, collapsed: false, size: 1, frame: null, restoreTo: null },
          { instanceId: "b", panelId: "module.that.was.removed", placement: "main", order: 1, collapsed: false, size: 1, frame: null, restoreTo: null },
        ],
      },
    });

    const id = store().importWorkspace(json);
    const imported = store().workspaces.find((w) => w.id === id);

    expect(imported?.panels.map((p) => p.panelId)).toEqual(["test.alpha"]);
  });

  it("does not export a workspace that does not exist", () => {
    expect(() => store().exportWorkspace("nope")).toThrow(WorkspaceImportError);
  });
});
