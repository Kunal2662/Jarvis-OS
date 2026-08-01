import { beforeEach, describe, expect, it } from "vitest";
import { applicationRegistry } from "@/core/application-registry";
import { TestApplication } from "@/core/test-utils/test-application";

describe("BaseApplication", () => {
  beforeEach(() => {
    for (const module of applicationRegistry.getAll()) {
      applicationRegistry.unregister(module.manifest.name);
    }
  });

  it("initialize() builds framework instances and registers with the ApplicationRegistry", async () => {
    const app = new TestApplication({ name: "app-a" });
    await app.initialize();

    expect(app.calls).toContain("onInitialize");
    expect(applicationRegistry.has("app-a")).toBe(true);
  });

  it("a local-category module starts in the empty state, a connected one in not_configured", async () => {
    const local = new TestApplication({ name: "local-app", category: "local" });
    const connected = new TestApplication({ name: "connected-app", category: "connected" });
    await local.initialize();
    await connected.initialize();

    expect(local.health().state).toBe("empty");
    expect(connected.health().state).toBe("not_configured");
  });

  it("mount() registers navigation, unmount() tears it down", async () => {
    const app = new TestApplication({ name: "app-b" });
    await app.initialize();

    app.mount();
    expect(app.calls).toContain("onMount");
    app.unmount();
    expect(app.calls).toContain("onUnmount");
  });

  it("start() through stop() calls every hook, in order", async () => {
    const app = new TestApplication({ name: "app-c" });
    await app.initialize();
    await app.start();
    await app.pause();
    await app.resume();
    await app.stop();

    expect(app.calls).toEqual(["onInitialize", "onStart", "onPause", "onResume", "onStop"]);
  });

  it("shutdown() is terminal and idempotent", async () => {
    const app = new TestApplication({ name: "app-d" });
    await app.initialize();
    await app.shutdown();
    await app.shutdown(); // second call must not throw or run onShutdown twice

    expect(app.calls.filter((c) => c === "onShutdown")).toHaveLength(1);
    expect(app.health().state).toBe("shutdown");
    expect(app.health().healthy).toBe(false);
  });

  it("dispose() is idempotent and runs after shutdown", async () => {
    const app = new TestApplication({ name: "app-e" });
    await app.initialize();
    await app.shutdown();
    app.dispose();
    app.dispose();

    expect(app.calls.filter((c) => c === "onDispose")).toHaveLength(1);
  });

  it("status() reports the module's real state history", async () => {
    const app = new TestApplication({ name: "app-f" });
    await app.initialize();
    await app.shutdown();

    const status = app.status();
    expect(status.moduleId).toBe("app-f");
    expect(status.history.map((h) => h.state)).toEqual(["empty", "shutdown"]);
  });
});
