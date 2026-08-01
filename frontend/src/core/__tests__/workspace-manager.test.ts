import { beforeEach, describe, expect, it } from "vitest";
import { applicationRegistry } from "@/core/application-registry";
import { TestApplication } from "@/core/test-utils/test-application";
import { WorkspaceManager } from "@/core/workspace-manager";

describe("WorkspaceManager", () => {
  let manager: WorkspaceManager;

  beforeEach(() => {
    for (const module of applicationRegistry.getAll()) {
      applicationRegistry.unregister(module.manifest.name);
    }
    manager = new WorkspaceManager();
  });

  it("resolves a module purely from ApplicationRegistry, never a hardcoded list", async () => {
    const app = new TestApplication({ name: "unusual-module", routes: ["/some/unusual/path"] });
    await app.initialize();

    expect(manager.resolveModuleForPath("/some/unusual/path")?.manifest.name).toBe("unusual-module");
  });

  it("mounts the module owning the current path", async () => {
    const app = new TestApplication({ name: "gmail", routes: ["/gmail"] });
    await app.initialize();

    manager.switchTo("/gmail");

    expect(app.calls).toContain("onMount");
    expect(manager.activeModule).toBe("gmail");
  });

  it("unmounts the previously-active module when switching to a different one", async () => {
    const first = new TestApplication({ name: "gmail", routes: ["/gmail"] });
    const second = new TestApplication({ name: "calendar", routes: ["/calendar"] });
    await first.initialize();
    await second.initialize();

    manager.switchTo("/gmail");
    manager.switchTo("/calendar");

    expect(first.calls).toContain("onUnmount");
    expect(second.calls).toContain("onMount");
    expect(manager.activeModule).toBe("calendar");
  });

  it("does not mount twice for the same resolved module -- no duplicate mounts", async () => {
    const app = new TestApplication({ name: "gmail", routes: ["/gmail"] });
    await app.initialize();

    manager.switchTo("/gmail");
    manager.switchTo("/gmail");
    manager.switchTo("/gmail");

    expect(app.calls.filter((c) => c === "onMount")).toHaveLength(1);
    expect(app.calls.filter((c) => c === "onUnmount")).toHaveLength(0);
  });

  it("treats an index route ('/') and a nested path under a module's route as the same module", async () => {
    const app = new TestApplication({ name: "files", routes: ["/files"] });
    await app.initialize();

    manager.switchTo("/files");
    manager.switchTo("/files/inbox");

    // Same resolved module both times -- still exactly one mount.
    expect(app.calls.filter((c) => c === "onMount")).toHaveLength(1);
  });

  it("leaves activeModule null and does not throw when no module matches the path", () => {
    expect(() => manager.switchTo("/nothing-registered-here")).not.toThrow();
    expect(manager.activeModule).toBeNull();
  });

  it("unmountActive() tears down the active module and clears state -- no leaked mount", async () => {
    const app = new TestApplication({ name: "gmail", routes: ["/gmail"] });
    await app.initialize();

    manager.switchTo("/gmail");
    manager.unmountActive();

    expect(app.calls.filter((c) => c === "onUnmount")).toHaveLength(1);
    expect(manager.activeModule).toBeNull();
  });

  it("unmountActive() is a safe no-op when nothing is active", () => {
    expect(() => manager.unmountActive()).not.toThrow();
    expect(manager.activeModule).toBeNull();
  });
});
