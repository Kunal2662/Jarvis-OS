import { beforeEach, describe, expect, it } from "vitest";
import {
  ApplicationRegistry,
  DuplicateModuleError,
  MissingDependencyError,
} from "@/core/application-registry";
import { TestApplication } from "@/core/test-utils/test-application";

describe("ApplicationRegistry", () => {
  let registry: ApplicationRegistry;

  beforeEach(() => {
    registry = new ApplicationRegistry();
  });

  it("registers and looks up a module", () => {
    const app = new TestApplication({ name: "a" });
    registry.register(app);
    expect(registry.get("a")).toBe(app);
  });

  it("rejects a duplicate registration", () => {
    const app = new TestApplication({ name: "dup" });
    registry.register(app);
    expect(() => registry.register(app)).toThrow(DuplicateModuleError);
  });

  it("rejects a module whose dependency isn't registered yet", () => {
    const app = new TestApplication({ name: "needs-b", dependencies: ["b"] });
    expect(() => registry.register(app)).toThrow(MissingDependencyError);
  });

  it("allows registration once the dependency exists", () => {
    registry.register(new TestApplication({ name: "b" }));
    const app = new TestApplication({ name: "needs-b-2", dependencies: ["b"] });
    expect(() => registry.register(app)).not.toThrow();
  });

  it("resolves initialization order so dependencies come first", () => {
    registry.register(new TestApplication({ name: "base" }));
    registry.register(new TestApplication({ name: "mid", dependencies: ["base"] }));
    registry.register(new TestApplication({ name: "top", dependencies: ["mid"] }));

    const order = registry.resolveInitializationOrder();
    expect(order.indexOf("base")).toBeLessThan(order.indexOf("mid"));
    expect(order.indexOf("mid")).toBeLessThan(order.indexOf("top"));
  });

  it("getByCapability filters correctly", () => {
    registry.register(new TestApplication({ name: "ai-mod", capabilities: ["ai"] }));
    registry.register(new TestApplication({ name: "plain-mod", capabilities: [] }));

    const aiModules = registry.getByCapability("ai");
    expect(aiModules.map((m) => m.manifest.name)).toEqual(["ai-mod"]);
  });

  it("refuses to unregister a module that others depend on", () => {
    registry.register(new TestApplication({ name: "core-mod" }));
    registry.register(new TestApplication({ name: "dependent-mod", dependencies: ["core-mod"] }));

    expect(() => registry.unregister("core-mod")).toThrow(/dependent-mod/);
  });

  it("getAll() returns a referentially-stable array between mutations", () => {
    registry.register(new TestApplication({ name: "a" }));

    // Regression guard: ModuleStateInspector feeds getAll() into
    // useSyncExternalStore, which requires getSnapshot() to return the
    // same reference when nothing changed -- a fresh array on every call
    // reads as "always changed" and causes an infinite render loop
    // (reproduced in-browser before this cache existed).
    expect(registry.getAll()).toBe(registry.getAll());
  });

  it("getAll() returns a new reference after a register() or unregister()", () => {
    registry.register(new TestApplication({ name: "a" }));
    const beforeRegister = registry.getAll();
    registry.register(new TestApplication({ name: "b" }));
    expect(registry.getAll()).not.toBe(beforeRegister);

    const beforeUnregister = registry.getAll();
    registry.unregister("b");
    expect(registry.getAll()).not.toBe(beforeUnregister);
  });
});

// These tests call `registry.register()` directly on a fresh, isolated
// `ApplicationRegistry` instance rather than `app.initialize()`
// (inherited from BaseApplication), which registers with the *shared*
// singleton (application-registry.ts's exported `applicationRegistry`)
// instead -- that shared-registry path is covered by
// base-application.test.ts.
